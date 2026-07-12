"""Pure authorization and read-only target preflight for S1C2A."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from collections.abc import Mapping
from datetime import date
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from typing import Literal

from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import StrictBool
from pydantic import field_validator
from pydantic import model_validator

from mathmongo.source_catalog_migration.canonical import canonical_json
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.decisions import DecisionError
from mathmongo.source_catalog_migration.decisions import DecisionSet
from mathmongo.source_catalog_migration.decisions import ValidatedDecisions
from mathmongo.source_catalog_migration.decisions import validate_decisions
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.manifest import ManifestExpectedCounts
from mathmongo.source_catalog_migration.manifest import ManifestInvariantHashes
from mathmongo.source_catalog_migration.models import PLANNER_VERSION
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.models import ReviewStatus
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_SNAPSHOT_COUNTS
from mathmongo.source_catalog_migration.planner import semantic_plan_payload
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport

AUTHORITATIVE_ZIP_SHA256 = "9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8"
AUTHORITATIVE_PLAN_SEMANTIC_SHA256 = (
    "e91599d50c58bb88014911590d34c9f0fc46b1c989dec8f3f25fed007a33b44f"
)
AUTHORITATIVE_PLANNER_VERSION = PLANNER_VERSION
AUTHORITATIVE_EXPECTED_COUNTS = ManifestExpectedCounts(
    concepts=186,
    source_candidates=16,
    concepts_with_reference=145,
    concepts_without_reference=41,
    reference_candidates=20,
    bindings=186,
    conflicts=0,
    review_items=5,
    weak_suggestions=2,
)

ISOLATED_TARGET_PREFIXES = (
    "MathV0_s1c2_validation_",
    "mathmongo_s1c2_validation_",
)
FORBIDDEN_TARGET_DATABASES = frozenset({"mathv0", "mathmongo", "admin", "config", "local"})
PRODUCTION_TARGET_DATABASE = "MathV0"
PRODUCTION_CONFIRMATION_PHRASE = "APPLY SOURCE CATALOG TO MathV0"
LEGACY_COLLECTIONS = tuple(sorted(AUTHORITATIVE_SNAPSHOT_COUNTS))
CATALOG_COLLECTIONS = ("sources", "references")
MAX_DATABASE_NAME_BYTES = 63
MAX_DOCUMENTS_PER_COLLECTION = 10_000
MAX_TOTAL_CANONICAL_BYTES = 256 * 1024 * 1024
MAX_INDEXES_PER_COLLECTION = 1_024
MAX_DRIFT_DETAILS = 64
MAX_DRIFT_DETAIL_LENGTH = 240
READ_OPERATION_MAX_TIME_MS = 10_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TARGET_SUFFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ApplySafetyError(ValueError):
    """A closed authorization, plan, decisions, or target preflight failure."""

    def __init__(self, code: str, message: str) -> None:
        """Expose a stable code and a bounded non-secret explanation."""
        self.code = code
        super().__init__(message)


class SafetyModel(BaseModel):
    """Strict immutable base for apply-safety evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProductionBackupEvidence(SafetyModel):
    """Path-free proof that a fresh private MathV0 backup passed validation."""

    database_name: Literal["MathV0"]
    file_name: str
    sha256: str
    size_bytes: int
    exported_at: datetime
    completed_at: datetime
    write_freeze_at: datetime
    validated_at: datetime
    format_name: str
    format_version: str
    collection_counts: dict[str, int]
    legacy_aggregate_sha256: str
    media_aggregate_sha256: str
    media_file_count: int
    file_mode: str
    parent_mode: str
    fresh: bool
    validation_passed: Literal[True] = True

    @field_validator("file_name")
    @classmethod
    def file_name_is_a_basename(cls, value: Any) -> str:
        """Keep private absolute backup paths out of durable/public evidence."""
        text = str(value or "")
        if not text or "/" in text or "\\" in text or text in {".", ".."}:
            raise ValueError("backup evidence must contain only a safe file basename")
        return text

    @field_validator("sha256", "legacy_aggregate_sha256", "media_aggregate_sha256")
    @classmethod
    def backup_hash_is_sha256(cls, value: Any) -> str:
        """Require the complete lowercase digest validated from the backup bytes."""
        text = str(value or "")
        if not _SHA256_RE.fullmatch(text):
            raise ValueError("backup evidence requires a lowercase SHA-256 digest")
        return text

    @field_validator("size_bytes")
    @classmethod
    def backup_size_is_positive(cls, value: Any) -> int:
        """Reject empty or non-integral backup evidence."""
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("backup evidence size must be a positive integer")
        return value

    @field_validator("media_file_count")
    @classmethod
    def media_count_is_bounded(cls, value: Any) -> int:
        """Reject an invalid or unbounded backup media inventory."""
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
            raise ValueError("backup media count must be an integer between 0 and 10000")
        return value

    @field_validator("exported_at", "completed_at", "write_freeze_at", "validated_at")
    @classmethod
    def backup_timestamps_are_aware_utc(cls, value: datetime) -> datetime:
        """Normalize every ordering timestamp without accepting naive wall time."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("backup evidence timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("collection_counts")
    @classmethod
    def backup_counts_are_bounded(cls, value: dict[str, int]) -> dict[str, int]:
        """Retain only compact, non-negative collection count evidence."""
        if len(value) > 64 or any(
            not isinstance(name, str)
            or not name
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for name, count in value.items()
        ):
            raise ValueError("backup collection count evidence is invalid")
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def backup_ordering_is_coherent(self) -> ProductionBackupEvidence:
        """Prove freeze < export completion < production validation."""
        if self.exported_at < self.write_freeze_at:
            raise ValueError("backup export started before the write freeze")
        if self.completed_at < self.exported_at:
            raise ValueError("backup completion precedes its export start")
        if self.validated_at < self.completed_at:
            raise ValueError("backup validation precedes export completion")
        return self


class ApplyAuthorization(SafetyModel):
    """All independent operator assertions required before target access."""

    target_database: str
    allow_isolated_write: StrictBool = False
    allow_production_write: StrictBool = False
    confirmed_database: str
    expected_zip_sha: str
    expected_plan_sha: str
    confirm_production_phrase: str | None = None
    production_backup: ProductionBackupEvidence | None = None
    production_backup_path: Path | None = None
    production_backup_sha: str | None = None
    confirm_production_backup_sha: str | None = None
    write_freeze_at: datetime | None = None

    @field_validator("target_database", "confirmed_database")
    @classmethod
    def database_names_are_text(cls, value: Any) -> str:
        """Reject whitespace changes and non-text database assertions."""
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError("database names must be nonempty exact strings")
        return value

    @field_validator("expected_zip_sha", "expected_plan_sha")
    @classmethod
    def expected_hashes_are_sha256(cls, value: Any) -> str:
        """Require complete lowercase hashes instead of prefixes."""
        text = str(value or "")
        if not _SHA256_RE.fullmatch(text):
            raise ValueError("expected hashes must be complete lowercase SHA-256 digests")
        return text

    @field_validator("production_backup_sha", "confirm_production_backup_sha")
    @classmethod
    def optional_backup_hashes_are_sha256(cls, value: Any) -> str | None:
        """Require full digests whenever production backup assertions are supplied."""
        if value is None:
            return None
        text = str(value)
        if not _SHA256_RE.fullmatch(text):
            raise ValueError("production backup hashes must be lowercase SHA-256 digests")
        return text

    @field_validator("write_freeze_at")
    @classmethod
    def optional_write_freeze_is_aware(cls, value: datetime | None) -> datetime | None:
        """Reject an unauditable naive write-freeze timestamp."""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("write freeze timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


class PlanPreflight(SafetyModel):
    """Validated immutable authority shared by bootstrap and its report."""

    zip_sha256: str
    plan_semantic_sha256: str
    decisions_sha256: str
    planner_version: str
    expected_counts: ManifestExpectedCounts
    source_candidate_keys: tuple[str, ...]
    reference_candidate_keys: tuple[str, ...]
    weak_suggestion_keys: tuple[str, ...]
    locator_review_keys: tuple[str, ...]
    zip_hash_matches: bool
    plan_hash_matches: bool
    decisions_complete: bool
    invariants_passed: bool
    conflicts_absent: bool

    @property
    def passed(self) -> bool:
        """Return whether every explicit plan proof obligation passed."""
        return all(
            (
                self.zip_hash_matches,
                self.plan_hash_matches,
                self.decisions_complete,
                self.invariants_passed,
                self.conflicts_absent,
            )
        )


class LegacyCollectionSnapshot(SafetyModel):
    """Bounded count and content/index hashes for one legacy collection."""

    collection: str
    present: bool
    count: int
    documents_sha256: str
    bson_documents_sha256: str
    indexes_sha256: str

    @field_validator("count")
    @classmethod
    def count_is_bounded(cls, value: Any) -> int:
        """Reject invalid or unsafe observed document counts."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("legacy collection count must be an integer")
        if not 0 <= value <= MAX_DOCUMENTS_PER_COLLECTION:
            raise ValueError("legacy collection count exceeds the read limit")
        return value

    @field_validator("documents_sha256", "bson_documents_sha256", "indexes_sha256")
    @classmethod
    def hashes_are_sha256(cls, value: Any) -> str:
        """Validate complete snapshot hashes."""
        text = str(value or "")
        if not _SHA256_RE.fullmatch(text):
            raise ValueError("legacy snapshot hashes must be lowercase SHA-256")
        return text


class LegacySnapshot(SafetyModel):
    """One complete read-only target observation with no document bodies."""

    database_name: str
    all_collection_names: tuple[str, ...]
    collections: tuple[LegacyCollectionSnapshot, ...]
    collection_counts_sha256: str
    collection_documents_sha256: str
    live_bson_documents_sha256: str
    legacy_indexes_sha256: str
    aggregate_sha256: str
    total_canonical_bytes: int
    read_operations: tuple[str, ...]
    writes_attempted: int = 0

    @field_validator(
        "collection_counts_sha256",
        "collection_documents_sha256",
        "live_bson_documents_sha256",
        "legacy_indexes_sha256",
        "aggregate_sha256",
    )
    @classmethod
    def aggregate_hashes_are_sha256(cls, value: Any) -> str:
        """Validate complete aggregate hashes."""
        text = str(value or "")
        if not _SHA256_RE.fullmatch(text):
            raise ValueError("legacy aggregate hashes must be lowercase SHA-256")
        return text

    @field_validator("total_canonical_bytes")
    @classmethod
    def total_bytes_are_bounded(cls, value: Any) -> int:
        """Reject invalid or unsafe canonical payload sizes."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("total canonical bytes must be an integer")
        if not 0 <= value <= MAX_TOTAL_CANONICAL_BYTES:
            raise ValueError("legacy snapshot exceeds the total byte limit")
        return value

    @field_validator("writes_attempted")
    @classmethod
    def writes_are_nonnegative(cls, value: Any) -> int:
        """Retain an explicit proof that snapshot capture made zero writes."""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("writes_attempted must be a non-negative integer")
        return value

    @property
    def sources_collection_present(self) -> bool:
        """Return physical presence rather than inferring from document count."""
        return "sources" in self.all_collection_names

    @property
    def references_collection_present(self) -> bool:
        """Return physical presence rather than inferring from document count."""
        return "references" in self.all_collection_names

    @property
    def manifest_collection_present(self) -> bool:
        """Return whether the bootstrap manifest collection already exists."""
        return MANIFEST_COLLECTION in self.all_collection_names

    @property
    def unexpected_collection_names(self) -> tuple[str, ...]:
        """Return collections outside the legacy and bootstrap write boundary."""
        allowed = {*LEGACY_COLLECTIONS, *CATALOG_COLLECTIONS, MANIFEST_COLLECTION}
        return tuple(sorted(set(self.all_collection_names) - allowed))


class LegacySnapshotComparison(SafetyModel):
    """Explicit double-read proof for an isolated target before any write."""

    database_name: str
    expected_zip_sha256: str
    expected_aggregate_sha256: str
    before_aggregate_sha256: str
    after_aggregate_sha256: str
    before_indexes_sha256: str
    after_indexes_sha256: str
    snapshot_drift: bool
    live_database_drift: bool
    writes_attempted: int
    counts_match: bool
    fingerprints_match: bool
    legacy_indexes_stable: bool
    sources_collection_absent: bool
    references_collection_absent: bool
    manifest_collection_absent: bool = True
    catalog_absence_required: bool
    drift_details: tuple[str, ...] = ()

    @field_validator("drift_details")
    @classmethod
    def details_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Bound safe drift diagnostics without retaining document content."""
        if len(value) > MAX_DRIFT_DETAILS or any(
            not item or len(item) > MAX_DRIFT_DETAIL_LENGTH for item in value
        ):
            raise ValueError("legacy drift details exceed report limits")
        return value

    @property
    def successful(self) -> bool:
        """Return success only when every explicit S1C2A guard passed."""
        catalog_safe = (
            self.sources_collection_absent and self.references_collection_absent
            if self.catalog_absence_required
            else True
        )
        return all(
            (
                not self.snapshot_drift,
                not self.live_database_drift,
                self.writes_attempted == 0,
                self.counts_match,
                self.fingerprints_match,
                self.legacy_indexes_stable,
                catalog_safe,
                self.manifest_collection_absent if self.catalog_absence_required else True,
            )
        )


def validate_apply_authorization(authorization: ApplyAuthorization) -> ApplyAuthorization:
    """Fail before configuration or client access unless all write gates agree."""
    target = authorization.target_database
    if len(target.encode("utf-8")) > MAX_DATABASE_NAME_BYTES:
        raise ApplySafetyError("invalid_target", "The target database name is too long.")
    if authorization.confirmed_database != target:
        raise ApplySafetyError(
            "database_confirmation_mismatch",
            "The exact target database confirmation does not match.",
        )
    if authorization.expected_zip_sha != AUTHORITATIVE_ZIP_SHA256:
        raise ApplySafetyError("zip_hash_mismatch", "The expected ZIP hash is not authoritative.")
    if authorization.expected_plan_sha != AUTHORITATIVE_PLAN_SEMANTIC_SHA256:
        raise ApplySafetyError(
            "plan_hash_mismatch",
            "The expected semantic plan hash is not authoritative.",
        )

    if target == PRODUCTION_TARGET_DATABASE:
        if authorization.allow_production_write is not True:
            raise ApplySafetyError(
                "production_write_not_authorized",
                "MathV0 apply requires the explicit production-write authorization flag.",
            )
        if authorization.allow_isolated_write is True:
            raise ApplySafetyError(
                "authorization_mode_conflict",
                "Production and isolated write authorizations cannot be combined.",
            )
        if authorization.confirm_production_phrase != PRODUCTION_CONFIRMATION_PHRASE:
            raise ApplySafetyError(
                "production_phrase_mismatch",
                "The exact MathV0 production confirmation phrase does not match.",
            )
        backup = authorization.production_backup
        if backup is None or backup.validation_passed is not True:
            raise ApplySafetyError(
                "production_backup_required",
                "MathV0 apply requires a fully validated fresh backup.",
            )
        if backup.database_name != PRODUCTION_TARGET_DATABASE:
            raise ApplySafetyError(
                "production_backup_database_mismatch",
                "The validated backup does not identify MathV0.",
            )
        if authorization.production_backup_path is None:
            raise ApplySafetyError(
                "production_backup_path_required",
                "MathV0 apply requires the validated backup path for revalidation.",
            )
        if (
            authorization.production_backup_sha is None
            or authorization.confirm_production_backup_sha is None
            or authorization.production_backup_sha != authorization.confirm_production_backup_sha
            or authorization.production_backup_sha != backup.sha256
        ):
            raise ApplySafetyError(
                "production_backup_hash_mismatch",
                "The two backup confirmations and validated digest must match exactly.",
            )
        if authorization.write_freeze_at != backup.write_freeze_at:
            raise ApplySafetyError(
                "production_backup_freeze_mismatch",
                "The backup evidence is not bound to the confirmed write-freeze timestamp.",
            )
        return authorization

    if target.casefold() in FORBIDDEN_TARGET_DATABASES:
        raise ApplySafetyError("forbidden_target", "The requested database is always read-only.")
    prefix = next((item for item in ISOLATED_TARGET_PREFIXES if target.startswith(item)), None)
    suffix = target[len(prefix) :] if prefix is not None else ""
    if prefix is None or not _TARGET_SUFFIX_RE.fullmatch(suffix):
        raise ApplySafetyError(
            "invalid_target",
            "The target database does not use an approved isolated validation prefix.",
        )
    if authorization.allow_isolated_write is not True:
        raise ApplySafetyError(
            "write_not_authorized",
            "Apply requires the explicit isolated-write authorization flag.",
        )
    if (
        authorization.allow_production_write is True
        or authorization.confirm_production_phrase is not None
        or authorization.production_backup is not None
        or authorization.production_backup_path is not None
        or authorization.production_backup_sha is not None
        or authorization.confirm_production_backup_sha is not None
        or authorization.write_freeze_at is not None
    ):
        raise ApplySafetyError(
            "unexpected_production_authorization",
            "Production-only authorization fields are forbidden for isolated targets.",
        )
    return authorization


def _plan_counts(plan: MigrationPlan) -> ManifestExpectedCounts:
    return ManifestExpectedCounts(
        concepts=plan.summary.concept_count,
        source_candidates=plan.summary.source_candidate_count,
        concepts_with_reference=plan.summary.embedded_reference_count,
        concepts_without_reference=plan.summary.missing_reference_count,
        reference_candidates=plan.summary.reference_candidate_count,
        bindings=plan.summary.binding_count,
        conflicts=plan.summary.conflict_count,
        review_items=plan.summary.review_item_count,
        weak_suggestions=plan.summary.weak_suggestion_count,
    )


def validate_authoritative_plan(plan: MigrationPlan, decisions: Any) -> PlanPreflight:
    """Validate the fixed S1C1 plan and complete human decisions without I/O."""
    computed_plan_sha = sha256_digest(semantic_plan_payload(plan))
    if plan.input_snapshot.database_name != "MathV0":
        raise ApplySafetyError(
            "snapshot_database_mismatch",
            "The authoritative input snapshot must remain labelled MathV0.",
        )
    if plan.input_snapshot.sha256 != AUTHORITATIVE_ZIP_SHA256:
        raise ApplySafetyError("zip_hash_mismatch", "The plan references another ZIP snapshot.")
    if plan.semantic_sha256 != computed_plan_sha:
        raise ApplySafetyError(
            "plan_self_hash_mismatch",
            "The semantic plan field does not match its canonical payload.",
        )
    if computed_plan_sha != AUTHORITATIVE_PLAN_SEMANTIC_SHA256:
        raise ApplySafetyError("plan_hash_mismatch", "The semantic plan is not authoritative.")
    if plan.planner_version != AUTHORITATIVE_PLANNER_VERSION:
        raise ApplySafetyError("planner_version_mismatch", "The planner version is unsupported.")
    counts = _plan_counts(plan)
    if counts != AUTHORITATIVE_EXPECTED_COUNTS:
        raise ApplySafetyError("plan_count_mismatch", "The plan cardinalities are not approved.")
    if not plan.invariants.passed:
        raise ApplySafetyError("plan_invariant_failed", "At least one S1C1 invariant failed.")
    if plan.conflicts or plan.summary.conflict_count:
        raise ApplySafetyError(
            "plan_conflict",
            "Bibliographic conflicts block Source Catalog bootstrap.",
        )

    reference_keys = tuple(
        sorted(candidate.reference_candidate_key for candidate in plan.reference_candidates)
    )
    safe_reference_keys = {
        candidate.reference_candidate_key
        for candidate in plan.reference_candidates
        if candidate.classification == ReviewStatus.SAFE_EXACT
    }
    if len(safe_reference_keys) != len(reference_keys):
        raise ApplySafetyError(
            "non_exact_reference_candidate",
            "Every authoritative Reference candidate must be safe_exact.",
        )
    try:
        if isinstance(decisions, ValidatedDecisions):
            decision_set = decisions.decisions
        elif isinstance(decisions, DecisionSet):
            decision_set = decisions
        elif isinstance(decisions, BaseModel):
            decision_set = DecisionSet.model_validate(decisions.model_dump(mode="python"))
        else:
            decision_set = DecisionSet.model_validate(decisions)
        validated_decisions = validate_decisions(
            decision_set,
            plan,
            expected_zip_sha256=AUTHORITATIVE_ZIP_SHA256,
            expected_plan_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        )
    except (DecisionError, ValueError) as exc:
        raise ApplySafetyError(
            "invalid_decisions",
            "Human decisions are incomplete or incompatible with the plan.",
        ) from exc
    if set(validated_decisions.effective_reference_candidates) != safe_reference_keys:
        raise ApplySafetyError(
            "incomplete_reference_acceptance",
            "Every safe_exact Reference candidate requires explicit acceptance.",
        )

    weak_keys = tuple(
        sorted(suggestion.suggestion_key for suggestion in plan.weak_reference_suggestions)
    )
    if validated_decisions.weak_suggestion_keys != weak_keys:
        raise ApplySafetyError(
            "weak_decisions_mismatch",
            "Weak-suggestion decisions must cover the plan exactly.",
        )
    locator_keys = tuple(sorted(item.review_key for item in plan.review_items))
    if validated_decisions.locator_review_keys != locator_keys:
        raise ApplySafetyError(
            "locator_decisions_mismatch",
            "Locator review decisions must cover the plan exactly.",
        )

    source_keys = tuple(sorted(item.source_candidate_key for item in plan.source_candidates))
    return PlanPreflight(
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=computed_plan_sha,
        decisions_sha256=validated_decisions.decisions_sha256,
        planner_version=plan.planner_version,
        expected_counts=counts,
        source_candidate_keys=source_keys,
        reference_candidate_keys=reference_keys,
        weak_suggestion_keys=weak_keys,
        locator_review_keys=locator_keys,
        zip_hash_matches=True,
        plan_hash_matches=True,
        decisions_complete=True,
        invariants_passed=True,
        conflicts_absent=True,
    )


def validate_authoritative_inputs(
    export: LoadedLegacyExport,
    plan: MigrationPlan,
    decisions: Any,
) -> PlanPreflight:
    """Bind the in-memory export, plan, and decisions to the same fixed snapshot."""
    if export.input_identity.sha256 != AUTHORITATIVE_ZIP_SHA256:
        raise ApplySafetyError("zip_hash_mismatch", "The loaded ZIP identity is not authoritative.")
    if export.input_snapshot.sha256 != export.input_identity.sha256:
        raise ApplySafetyError(
            "zip_identity_mismatch",
            "The loaded ZIP snapshot and filesystem identity differ.",
        )
    if export.input_snapshot != plan.input_snapshot:
        raise ApplySafetyError(
            "export_plan_mismatch",
            "The plan was not built from this exact loaded export snapshot.",
        )
    return validate_authoritative_plan(plan, decisions)


def _legacy_json_safe(value: Any) -> Any:
    """Match legacy export JSON while normalizing live BSON scalar wrappers."""
    if isinstance(value, BaseModel):
        return _legacy_json_safe(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return _legacy_json_safe(value.value)
    if isinstance(value, Mapping):
        return {str(key): _legacy_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_legacy_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        safe = [_legacy_json_safe(item) for item in value]
        return sorted(safe, key=canonical_json)
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        raise ApplySafetyError(
            "unsupported_legacy_scalar",
            "A legacy document contains bytes that the authoritative JSON cannot represent.",
        )
    if value.__class__.__module__.startswith("bson"):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ApplySafetyError(
        "unsupported_legacy_scalar",
        "A legacy document contains an unsupported scalar value.",
    )


def _legacy_canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            _legacy_json_safe(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ApplySafetyError(
            "unsupported_legacy_scalar",
            "A legacy document cannot be represented by canonical JSON.",
        ) from exc


def _bson_canonical_json(value: Any) -> str:
    """Preserve BSON scalar identity for live before/after drift checks."""
    try:
        return bson_json_dumps(
            value,
            json_options=CANONICAL_JSON_OPTIONS,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ApplySafetyError(
            "unsupported_bson_scalar",
            "A live legacy document cannot be represented by canonical Extended JSON.",
        ) from exc


def _index_rows(collection: Any, collection_name: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    cursor = collection.list_indexes()
    try:
        for index, raw in enumerate(cursor, start=1):
            if index > MAX_INDEXES_PER_COLLECTION:
                raise ApplySafetyError(
                    "index_limit_exceeded",
                    f"Legacy collection {collection_name} exceeds the safe index limit.",
                )
            if not isinstance(raw, Mapping):
                raise ApplySafetyError(
                    "invalid_index_spec",
                    f"Legacy collection {collection_name} returned an invalid index spec.",
                )
            row: dict[str, Any] = {}
            for option, value in raw.items():
                option_name = str(option)
                if option_name == "key":
                    key_items = (
                        list(value.items()) if hasattr(value, "items") else list(value or ())
                    )
                    row[option_name] = [
                        [str(key), json.loads(_bson_canonical_json(direction))]
                        for key, direction in key_items
                    ]
                else:
                    row[option_name] = json.loads(_bson_canonical_json(value))
            rows.append(row)
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()
    return tuple(sorted(rows, key=canonical_json))


def _snapshot_from_documents(
    *,
    database_name: str,
    all_collection_names: Iterable[str],
    documents: Mapping[str, Iterable[Mapping[str, Any]]],
    indexes: Mapping[str, tuple[dict[str, Any], ...]],
    read_operations: tuple[str, ...],
) -> LegacySnapshot:
    collection_snapshots: list[LegacyCollectionSnapshot] = []
    total_bytes = 0
    total_bson_bytes = 0
    names = tuple(sorted(set(all_collection_names)))
    for collection_name in LEGACY_COLLECTIONS:
        rows = tuple(dict(row) for row in documents.get(collection_name, ()))
        if len(rows) > MAX_DOCUMENTS_PER_COLLECTION:
            raise ApplySafetyError(
                "document_limit_exceeded",
                f"Legacy collection {collection_name} exceeds the safe document limit.",
            )
        canonical_rows: list[str] = []
        bson_rows: list[str] = []
        for row in rows:
            serialized = _legacy_canonical_json(row)
            bson_serialized = _bson_canonical_json(row)
            total_bytes += len(serialized.encode("utf-8"))
            total_bson_bytes += len(bson_serialized.encode("utf-8"))
            if total_bytes > MAX_TOTAL_CANONICAL_BYTES:
                raise ApplySafetyError(
                    "byte_limit_exceeded",
                    "Legacy target data exceeds the safe canonical byte limit.",
                )
            if total_bson_bytes > MAX_TOTAL_CANONICAL_BYTES:
                raise ApplySafetyError(
                    "byte_limit_exceeded",
                    "Legacy BSON identity data exceeds the safe canonical byte limit.",
                )
            canonical_rows.append(serialized)
            bson_rows.append(bson_serialized)
        index_rows = indexes.get(collection_name, ())
        collection_snapshots.append(
            LegacyCollectionSnapshot(
                collection=collection_name,
                present=collection_name in names,
                count=len(rows),
                documents_sha256=sha256_digest(sorted(canonical_rows)),
                bson_documents_sha256=sha256_digest(sorted(bson_rows)),
                indexes_sha256=sha256_digest(index_rows),
            )
        )
    count_payload = {
        item.collection: item.count
        for item in sorted(collection_snapshots, key=lambda x: x.collection)
    }
    document_payload = {
        item.collection: item.documents_sha256
        for item in sorted(collection_snapshots, key=lambda x: x.collection)
    }
    bson_document_payload = {
        item.collection: item.bson_documents_sha256
        for item in sorted(collection_snapshots, key=lambda x: x.collection)
    }
    index_payload = {
        item.collection: item.indexes_sha256
        for item in sorted(collection_snapshots, key=lambda x: x.collection)
    }
    aggregate_payload = {
        "legacy_presence": {
            item.collection: item.present
            for item in sorted(collection_snapshots, key=lambda x: x.collection)
        },
        "counts": count_payload,
        "documents": document_payload,
        "indexes": index_payload,
    }
    return LegacySnapshot(
        database_name=database_name,
        all_collection_names=names,
        collections=tuple(sorted(collection_snapshots, key=lambda item: item.collection)),
        collection_counts_sha256=sha256_digest(count_payload),
        collection_documents_sha256=sha256_digest(document_payload),
        live_bson_documents_sha256=sha256_digest(bson_document_payload),
        legacy_indexes_sha256=sha256_digest(index_payload),
        aggregate_sha256=sha256_digest(aggregate_payload),
        total_canonical_bytes=total_bytes,
        read_operations=read_operations,
        writes_attempted=0,
    )


def legacy_snapshot_from_documents(
    documents: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    database_name: str,
) -> LegacySnapshot:
    """Hash a validated portable set of the ten legacy collection payloads."""
    return _snapshot_from_documents(
        database_name=database_name,
        all_collection_names=LEGACY_COLLECTIONS,
        documents={name: documents.get(name, ()) for name in LEGACY_COLLECTIONS},
        indexes={},
        read_operations=("validated_zip_memory",),
    )


def legacy_snapshot_from_export(export: LoadedLegacyExport) -> LegacySnapshot:
    """Build portable expected hashes from the already validated ZIP in memory."""
    if (
        export.input_snapshot.sha256 != AUTHORITATIVE_ZIP_SHA256
        or export.input_identity.sha256 != AUTHORITATIVE_ZIP_SHA256
    ):
        raise ApplySafetyError("zip_hash_mismatch", "The loaded export is not authoritative.")
    actual_counts = {name: len(export.collections.get(name, ())) for name in LEGACY_COLLECTIONS}
    if actual_counts != AUTHORITATIVE_SNAPSHOT_COUNTS:
        raise ApplySafetyError(
            "export_count_mismatch",
            "The loaded export collection counts are not authoritative.",
        )
    return legacy_snapshot_from_documents(
        export.collections,
        database_name=export.input_snapshot.database_name,
    )


def capture_legacy_snapshot(database: Any) -> LegacySnapshot:
    """Capture all ten legacy collections and indexes without issuing a write."""
    if database is None or not hasattr(database, "__getitem__"):
        raise ApplySafetyError("invalid_database", "An explicit target database is required.")
    database_name = getattr(database, "name", None)
    if not isinstance(database_name, str) or not database_name:
        raise ApplySafetyError("invalid_database", "The explicit database has no usable name.")
    if not hasattr(database, "list_collection_names"):
        raise ApplySafetyError(
            "invalid_database",
            "The explicit database cannot enumerate collection presence.",
        )
    names = tuple(sorted(database.list_collection_names()))
    documents: dict[str, tuple[dict[str, Any], ...]] = {}
    indexes: dict[str, tuple[dict[str, Any], ...]] = {}
    total_rows = 0
    captured_canonical_bytes = 0
    for collection_name in LEGACY_COLLECTIONS:
        if collection_name not in names:
            documents[collection_name] = ()
            indexes[collection_name] = ()
            continue
        collection = database[collection_name]
        count = int(collection.count_documents({}, maxTimeMS=READ_OPERATION_MAX_TIME_MS))
        if not 0 <= count <= MAX_DOCUMENTS_PER_COLLECTION:
            raise ApplySafetyError(
                "document_limit_exceeded",
                f"Legacy collection {collection_name} exceeds the safe document limit.",
            )
        cursor = collection.find({})
        max_time_ms = getattr(cursor, "max_time_ms", None)
        if callable(max_time_ms):
            cursor = max_time_ms(READ_OPERATION_MAX_TIME_MS)
        if hasattr(cursor, "limit"):
            cursor = cursor.limit(MAX_DOCUMENTS_PER_COLLECTION + 1)
        rows: list[dict[str, Any]] = []
        try:
            for document in cursor:
                if len(rows) >= MAX_DOCUMENTS_PER_COLLECTION:
                    raise ApplySafetyError(
                        "document_limit_exceeded",
                        f"Legacy collection {collection_name} changed beyond the safe limit.",
                    )
                if not isinstance(document, Mapping):
                    raise ApplySafetyError(
                        "invalid_legacy_document",
                        f"Legacy collection {collection_name} returned a non-document value.",
                    )
                row = dict(document)
                captured_canonical_bytes += len(_legacy_canonical_json(row).encode("utf-8"))
                if captured_canonical_bytes > MAX_TOTAL_CANONICAL_BYTES:
                    raise ApplySafetyError(
                        "byte_limit_exceeded",
                        "Legacy target data exceeds the safe canonical byte limit.",
                    )
                rows.append(row)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        if len(rows) != count:
            raise ApplySafetyError(
                "concurrent_collection_drift",
                f"Legacy collection {collection_name} changed during one snapshot.",
            )
        total_rows += len(rows)
        if total_rows > len(LEGACY_COLLECTIONS) * MAX_DOCUMENTS_PER_COLLECTION:
            raise ApplySafetyError("document_limit_exceeded", "Legacy snapshot is too large.")
        documents[collection_name] = tuple(rows)
        indexes[collection_name] = _index_rows(collection, collection_name)
    return _snapshot_from_documents(
        database_name=database_name,
        all_collection_names=names,
        documents=documents,
        indexes=indexes,
        read_operations=(
            "list_collection_names",
            "count_documents",
            "find_complete_documents",
            "list_indexes",
        ),
    )


def compare_legacy_snapshots(
    expected: LegacySnapshot,
    before: LegacySnapshot,
    after: LegacySnapshot,
    *,
    require_catalog_absent: bool,
) -> LegacySnapshotComparison:
    """Compare ZIP compatibility and target stability using two explicit reads."""
    if before.database_name != after.database_name:
        raise ApplySafetyError(
            "database_changed",
            "The two target snapshots refer to different databases.",
        )
    expected_collections = {item.collection: item for item in expected.collections}
    before_collections = {item.collection: item for item in before.collections}
    after_collections = {item.collection: item for item in after.collections}
    expected_counts = {name: item.count for name, item in expected_collections.items()}
    before_counts = {name: item.count for name, item in before_collections.items()}
    after_counts = {name: item.count for name, item in after_collections.items()}
    expected_documents = {
        name: item.documents_sha256 for name, item in expected_collections.items()
    }
    before_documents = {name: item.documents_sha256 for name, item in before_collections.items()}
    after_documents = {name: item.documents_sha256 for name, item in after_collections.items()}
    before_bson_documents = {
        name: item.bson_documents_sha256 for name, item in before_collections.items()
    }
    after_bson_documents = {
        name: item.bson_documents_sha256 for name, item in after_collections.items()
    }
    counts_match = expected_counts == before_counts == after_counts
    fingerprints_match = expected_documents == before_documents == after_documents
    indexes_stable = before.legacy_indexes_sha256 == after.legacy_indexes_sha256
    legacy_presence_expected = {item.collection: item.present for item in expected.collections}
    legacy_presence_before = {item.collection: item.present for item in before.collections}
    legacy_presence_after = {item.collection: item.present for item in after.collections}
    legacy_presence_matches = (
        legacy_presence_expected == legacy_presence_before == legacy_presence_after
    )
    live_drift = not all(
        (
            before.collection_counts_sha256 == after.collection_counts_sha256,
            before.collection_documents_sha256 == after.collection_documents_sha256,
            before_bson_documents == after_bson_documents,
            indexes_stable,
            legacy_presence_before == legacy_presence_after,
        )
    )
    sources_absent = not before.sources_collection_present and not after.sources_collection_present
    references_absent = (
        not before.references_collection_present and not after.references_collection_present
    )
    manifest_absent = (
        not before.manifest_collection_present and not after.manifest_collection_present
    )
    snapshot_drift = not counts_match or not fingerprints_match or not legacy_presence_matches
    unexpected_before = before.unexpected_collection_names
    unexpected_after = after.unexpected_collection_names
    if unexpected_before or unexpected_after:
        snapshot_drift = True
        live_drift = live_drift or unexpected_before != unexpected_after
    if require_catalog_absent and (
        not sources_absent or not references_absent or not manifest_absent
    ):
        snapshot_drift = True
    writes_attempted = before.writes_attempted + after.writes_attempted
    details: list[str] = []
    if not counts_match:
        details.append("Legacy collection counts differ from the authoritative ZIP.")
    if not fingerprints_match:
        details.append("Legacy collection fingerprints differ from the authoritative ZIP.")
    if not legacy_presence_matches:
        details.append("Legacy collection presence differs from the authoritative ZIP.")
    if live_drift:
        details.append("Legacy target state changed between the two read-only snapshots.")
    if require_catalog_absent and not sources_absent:
        details.append("A sources collection is physically present before first apply.")
    if require_catalog_absent and not references_absent:
        details.append("A references collection is physically present before first apply.")
    if require_catalog_absent and not manifest_absent:
        details.append("A migration manifest collection is physically present before first apply.")
    if writes_attempted:
        details.append("Snapshot evidence reports an unexpected write attempt.")
    if unexpected_before or unexpected_after:
        details.append("The isolated target contains an unexpected collection.")
    return LegacySnapshotComparison(
        database_name=before.database_name,
        expected_zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        expected_aggregate_sha256=expected.aggregate_sha256,
        before_aggregate_sha256=before.aggregate_sha256,
        after_aggregate_sha256=after.aggregate_sha256,
        before_indexes_sha256=before.legacy_indexes_sha256,
        after_indexes_sha256=after.legacy_indexes_sha256,
        snapshot_drift=snapshot_drift,
        live_database_drift=live_drift,
        writes_attempted=writes_attempted,
        counts_match=counts_match,
        fingerprints_match=fingerprints_match,
        legacy_indexes_stable=indexes_stable,
        sources_collection_absent=sources_absent,
        references_collection_absent=references_absent,
        manifest_collection_absent=manifest_absent,
        catalog_absence_required=require_catalog_absent,
        drift_details=tuple(details),
    )


def preflight_legacy_database(
    export: LoadedLegacyExport,
    database: Any,
    *,
    require_catalog_absent: bool,
) -> LegacySnapshotComparison:
    """Perform the bounded expected/before/after read-only target comparison."""
    expected = legacy_snapshot_from_export(export)
    before = capture_legacy_snapshot(database)
    after = capture_legacy_snapshot(database)
    return compare_legacy_snapshots(
        expected,
        before,
        after,
        require_catalog_absent=require_catalog_absent,
    )


def manifest_invariant_hashes(snapshot: LegacySnapshot) -> ManifestInvariantHashes:
    """Convert a bounded target snapshot to the hashes stored in the manifest."""
    return ManifestInvariantHashes(
        collections_sha256=sha256_digest(
            {
                "counts": snapshot.collection_counts_sha256,
                "documents": snapshot.collection_documents_sha256,
                "bson_documents": snapshot.live_bson_documents_sha256,
            }
        ),
        indexes_sha256=snapshot.legacy_indexes_sha256,
        aggregate_sha256=snapshot.aggregate_sha256,
    )


def require_successful_legacy_preflight(
    comparison: LegacySnapshotComparison,
) -> LegacySnapshotComparison:
    """Fail closed by checking each required flag instead of a shorthand alone."""
    if comparison.snapshot_drift:
        raise ApplySafetyError("snapshot_drift", "The isolated target differs from the ZIP.")
    if comparison.live_database_drift:
        raise ApplySafetyError(
            "live_database_drift",
            "The isolated target changed during preflight.",
        )
    if comparison.writes_attempted != 0:
        raise ApplySafetyError(
            "preflight_write_detected",
            "A read-only preflight reported an unexpected write.",
        )
    if comparison.catalog_absence_required and not comparison.sources_collection_absent:
        raise ApplySafetyError(
            "sources_collection_present",
            "First apply requires the sources collection to be physically absent.",
        )
    if comparison.catalog_absence_required and not comparison.references_collection_absent:
        raise ApplySafetyError(
            "references_collection_present",
            "First apply requires the references collection to be physically absent.",
        )
    if comparison.catalog_absence_required and not comparison.manifest_collection_absent:
        raise ApplySafetyError(
            "manifest_collection_present",
            "First apply requires the migration manifest collection to be physically absent.",
        )
    if not comparison.counts_match or not comparison.fingerprints_match:
        raise ApplySafetyError(
            "legacy_snapshot_mismatch",
            "Legacy target invariants do not match the authoritative ZIP.",
        )
    if not comparison.legacy_indexes_stable:
        raise ApplySafetyError(
            "legacy_index_drift",
            "Legacy index definitions changed during preflight.",
        )
    return comparison


__all__ = [
    "AUTHORITATIVE_EXPECTED_COUNTS",
    "AUTHORITATIVE_PLAN_SEMANTIC_SHA256",
    "AUTHORITATIVE_PLANNER_VERSION",
    "AUTHORITATIVE_ZIP_SHA256",
    "ApplyAuthorization",
    "ApplySafetyError",
    "CATALOG_COLLECTIONS",
    "FORBIDDEN_TARGET_DATABASES",
    "ISOLATED_TARGET_PREFIXES",
    "LEGACY_COLLECTIONS",
    "LegacyCollectionSnapshot",
    "LegacySnapshot",
    "LegacySnapshotComparison",
    "PlanPreflight",
    "PRODUCTION_CONFIRMATION_PHRASE",
    "PRODUCTION_TARGET_DATABASE",
    "ProductionBackupEvidence",
    "capture_legacy_snapshot",
    "compare_legacy_snapshots",
    "legacy_snapshot_from_export",
    "legacy_snapshot_from_documents",
    "manifest_invariant_hashes",
    "preflight_legacy_database",
    "require_successful_legacy_preflight",
    "validate_apply_authorization",
    "validate_authoritative_inputs",
    "validate_authoritative_plan",
]

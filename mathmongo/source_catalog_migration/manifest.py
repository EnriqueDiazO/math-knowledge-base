"""Prepared-manifest contracts and race-safe persistence for S1C2A."""

from __future__ import annotations

import re
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any
from typing import Literal
from uuid import UUID
from uuid import uuid4

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import field_validator
from pydantic import model_validator
from pymongo.errors import DuplicateKeyError

from mathmongo.source_catalog.models import new_reference_id
from mathmongo.source_catalog.models import new_source_id
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.models import PLANNER_VERSION

MANIFEST_SCHEMA_VERSION = 1
MIGRATION_TYPE = "legacy_source_catalog_bootstrap"
MANIFEST_COLLECTION = "source_catalog_migration_manifest"
MANIFEST_KEY_PREFIX = "source_catalog_manifest_"
MAX_MANIFESTS_PER_TARGET = 16
MAX_MANIFEST_ERRORS = 20
MAX_ERROR_MESSAGE_LENGTH = 320
MAX_ERROR_CODE_LENGTH = 80
MAX_CANDIDATES_PER_KIND = 10_000
MAX_EVIDENCE_SUMMARIES = 10_000

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")
_MONGO_URI_RE = re.compile(r"mongodb(?:\+srv)?://[^\s]+", re.IGNORECASE)
_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|credential|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)
_POSIX_PATH_RE = re.compile(r"(?<![\w.-])/(?:[^\s:/]+/)+[^\s,;:]+")
_WINDOWS_PATH_RE = re.compile(r"(?i)\b[A-Z]:\\(?:[^\s\\]+\\)*[^\s,;:]*")


class ManifestPersistenceError(RuntimeError):
    """Base class for controlled manifest persistence failures."""


class ManifestCompatibilityError(ManifestPersistenceError):
    """An existing stable manifest is incompatible with the requested bootstrap."""

    def __init__(self, issues: Iterable[str]) -> None:
        """Retain bounded compatibility issue codes."""
        self.issues = tuple(dict.fromkeys(str(issue) for issue in issues))[:32]
        super().__init__("Incompatible prepared manifest: " + ", ".join(self.issues))


class ManifestConcurrentUpdateError(ManifestPersistenceError):
    """A compare-and-set update lost a race and must be retried from a fresh read."""


class ManifestState(str, Enum):
    """Durable bootstrap state; failed is resumable and blocked is closed."""

    PREPARED = "prepared"
    APPLYING_INDEXES = "applying_indexes"
    APPLYING_SOURCES = "applying_sources"
    APPLYING_REFERENCES = "applying_references"
    VERIFYING = "verifying"
    APPLIED = "applied"
    FAILED = "failed"
    BLOCKED = "blocked"


class ManifestModel(BaseModel):
    """Strict immutable base for manifest payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def utc_now_milliseconds(clock: Callable[[], datetime] | None = None) -> datetime:
    """Return aware UTC time truncated to MongoDB's millisecond precision."""
    value = (clock or (lambda: datetime.now(timezone.utc)))()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("manifest clock must return a timezone-aware datetime")
    value = value.astimezone(timezone.utc)
    return value.replace(microsecond=(value.microsecond // 1_000) * 1_000)


def _validate_sha256(value: Any, field_name: str) -> str:
    text = str(value or "")
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _validate_prefixed_uuid4(value: Any, prefix: str, field_name: str) -> str:
    text = str(value or "")
    expected = f"{prefix}_"
    if not text.startswith(expected):
        raise ValueError(f"{field_name} must start with {expected!r}")
    suffix = text[len(expected) :]
    try:
        parsed = UUID(suffix)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain a UUID v4") from exc
    if parsed.version != 4 or str(parsed) != suffix:
        raise ValueError(f"{field_name} must contain a canonical lowercase UUID v4")
    return text


def new_migration_id() -> str:
    """Allocate one canonical migration identifier."""
    return f"mig_{uuid4()}"


class ManifestExpectedCounts(ManifestModel):
    """Approved S1C1 cardinalities recorded before final ID allocation."""

    concepts: int
    source_candidates: int
    concepts_with_reference: int
    concepts_without_reference: int
    reference_candidates: int
    bindings: int
    conflicts: int
    review_items: int
    weak_suggestions: int

    @field_validator("*")
    @classmethod
    def counts_are_nonnegative_integers(cls, value: Any) -> int:
        """Reject booleans, coercions, and negative manifest counts."""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("manifest counts must be non-negative integers")
        return value


class ManifestIndexStatus(ManifestModel):
    """Bounded summary of the explicit Source Catalog index plan and result."""

    expected: int = 0
    applied: int = 0
    already_present: int = 0
    missing: int = 0
    conflicts: tuple[str, ...] = ()
    expected_sha256: str | None = None
    final_sha256: str | None = None

    @field_validator("expected", "applied", "already_present", "missing")
    @classmethod
    def index_counts_are_nonnegative(cls, value: Any) -> int:
        """Keep every index counter bounded and non-negative."""
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_024:
            raise ValueError("index counts must be integers between 0 and 1024")
        return value

    @field_validator("conflicts")
    @classmethod
    def conflicts_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject unbounded or verbose index conflict details."""
        if len(value) > 128 or any(not item or len(item) > 160 for item in value):
            raise ValueError("index conflicts exceed manifest limits")
        if len(value) != len(set(value)):
            raise ValueError("index conflicts must use unique stable names")
        return value

    @field_validator("expected_sha256", "final_sha256")
    @classmethod
    def optional_hashes_are_sha256(cls, value: str | None, info: Any) -> str | None:
        """Validate optional index-state hashes."""
        return None if value is None else _validate_sha256(value, info.field_name)

    @model_validator(mode="after")
    def index_states_cover_the_plan(self) -> ManifestIndexStatus:
        """Require disjoint state counters to account for every expected index."""
        observed = self.applied + self.already_present + self.missing + len(self.conflicts)
        if self.expected and observed != self.expected:
            raise ValueError("index state counters must cover every expected index")
        return self


class ManifestInvariantHashes(ManifestModel):
    """Hashes proving legacy collections and indexes before or after apply."""

    collections_sha256: str
    indexes_sha256: str
    aggregate_sha256: str

    @field_validator("*")
    @classmethod
    def invariant_hashes_are_sha256(cls, value: Any, info: Any) -> str:
        """Validate every invariant digest."""
        return _validate_sha256(value, info.field_name)


class ManifestBackupEvidence(ManifestModel):
    """Path-free immutable identity of the pre-production MathV0 backup."""

    file_name: str
    sha256: str
    size_bytes: int
    exported_at: datetime
    completed_at: datetime
    write_freeze_at: datetime
    format_name: str
    format_version: str
    collection_counts: dict[str, int]
    legacy_aggregate_sha256: str
    media_aggregate_sha256: str
    media_file_count: int
    file_mode: str
    parent_mode: str

    @field_validator("file_name")
    @classmethod
    def file_name_is_path_free(cls, value: str) -> str:
        """Prevent HOME or other absolute path disclosure in the manifest."""
        if not value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("manifest backup evidence requires a safe basename")
        return value

    @field_validator("sha256", "legacy_aggregate_sha256", "media_aggregate_sha256")
    @classmethod
    def backup_hashes_are_sha256(cls, value: Any, info: Any) -> str:
        """Validate immutable backup digests."""
        return _validate_sha256(value, info.field_name)

    @field_validator("size_bytes")
    @classmethod
    def backup_size_is_positive(cls, value: Any) -> int:
        """Reject empty or invalid backup sizes."""
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("manifest backup size must be a positive integer")
        return value

    @field_validator("media_file_count")
    @classmethod
    def media_count_is_bounded(cls, value: Any) -> int:
        """Retain a bounded physical-media inventory count."""
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
            raise ValueError("manifest backup media count is invalid")
        return value

    @field_validator("exported_at", "completed_at", "write_freeze_at")
    @classmethod
    def backup_timestamps_are_utc(cls, value: datetime) -> datetime:
        """Retain UTC millisecond timestamps compatible with BSON."""
        return utc_now_milliseconds(lambda: value)

    @field_validator("collection_counts")
    @classmethod
    def backup_counts_are_bounded(cls, value: dict[str, int]) -> dict[str, int]:
        """Keep the compact legacy count proof deterministic."""
        if len(value) > 64 or any(
            not name or isinstance(count, bool) or not isinstance(count, int) or count < 0
            for name, count in value.items()
        ):
            raise ValueError("manifest backup collection counts are invalid")
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def backup_time_order_is_valid(self) -> ManifestBackupEvidence:
        """Require the backup snapshot to begin after the write freeze."""
        if self.exported_at < self.write_freeze_at or self.completed_at < self.exported_at:
            raise ValueError("manifest backup timestamps are not ordered")
        return self


class ReferenceEvidenceSummary(ManifestModel):
    """Non-raw evidence retained when Reference cannot represent legacy shape."""

    reference_candidate_key: str
    bibliographic_fingerprint: str
    raw_variant_count: int
    field_names: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @field_validator("bibliographic_fingerprint")
    @classmethod
    def bibliography_hash_is_sha256(cls, value: Any) -> str:
        """Require a complete bibliographic fingerprint."""
        return _validate_sha256(value, "bibliographic_fingerprint")

    @field_validator("raw_variant_count")
    @classmethod
    def raw_variant_count_is_bounded(cls, value: Any) -> int:
        """Bound the diagnostic count without storing the variants."""
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
            raise ValueError("raw_variant_count must be an integer between 0 and 10000")
        return value

    @field_validator("field_names", "limitations")
    @classmethod
    def summaries_are_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Limit evidence summaries to short nonempty labels."""
        if len(value) > 128 or any(not item or len(item) > 160 for item in value):
            raise ValueError("reference evidence summary exceeds manifest limits")
        return value


class ManifestError(ManifestModel):
    """One safe, bounded diagnostic retained for resumable failures."""

    code: str
    message: str
    occurred_at: datetime
    state: ManifestState
    attempt: int

    @field_validator("code")
    @classmethod
    def code_is_safe(cls, value: str) -> str:
        """Require a compact machine-readable error code."""
        if not _ERROR_CODE_RE.fullmatch(value):
            raise ValueError("manifest error code is invalid")
        return value

    @field_validator("message")
    @classmethod
    def message_is_bounded(cls, value: str) -> str:
        """Reject multiline or oversized stored diagnostics."""
        if not value or len(value) > MAX_ERROR_MESSAGE_LENGTH or "\n" in value:
            raise ValueError("manifest error message is invalid")
        return value

    @field_validator("occurred_at")
    @classmethod
    def occurred_at_is_utc_milliseconds(cls, value: datetime) -> datetime:
        """Normalize the diagnostic timestamp to the manifest clock contract."""
        return utc_now_milliseconds(lambda: value)

    @field_validator("attempt")
    @classmethod
    def attempt_is_nonnegative(cls, value: Any) -> int:
        """Reject invalid attempt numbers."""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("manifest error attempt must be non-negative")
        return value


class FinalIdAllocation(ManifestModel):
    """Complete one-time UUID allocation used to build a prepared manifest."""

    migration_id: str
    created_at: datetime
    source_id_map: dict[str, str]
    reference_id_map: dict[str, str]

    @field_validator("migration_id")
    @classmethod
    def migration_id_is_uuid4(cls, value: Any) -> str:
        """Validate the migration UUID."""
        return _validate_prefixed_uuid4(value, "mig", "migration_id")

    @field_validator("created_at")
    @classmethod
    def created_at_is_utc_milliseconds(cls, value: datetime) -> datetime:
        """Normalize the allocation timestamp once."""
        return utc_now_milliseconds(lambda: value)

    @field_validator("source_id_map", "reference_id_map")
    @classmethod
    def maps_are_bounded(cls, value: dict[str, str]) -> dict[str, str]:
        """Reject empty candidate keys and unbounded maps."""
        if len(value) > MAX_CANDIDATES_PER_KIND or any(not key for key in value):
            raise ValueError("final ID map exceeds manifest limits")
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def ids_are_canonical_and_unique(self) -> FinalIdAllocation:
        """Validate every final ID and prevent two candidates sharing one ID."""
        for value in self.source_id_map.values():
            _validate_prefixed_uuid4(value, "src", "source_id_map value")
        for value in self.reference_id_map.values():
            _validate_prefixed_uuid4(value, "ref", "reference_id_map value")
        if len(set(self.source_id_map.values())) != len(self.source_id_map):
            raise ValueError("source_id_map values must be unique")
        if len(set(self.reference_id_map.values())) != len(self.reference_id_map):
            raise ValueError("reference_id_map values must be unique")
        return self


class MigrationManifest(ManifestModel):
    """Durable authority for one isolated legacy Source Catalog bootstrap."""

    manifest_schema_version: Literal[1] = MANIFEST_SCHEMA_VERSION
    manifest_key: str
    migration_id: str
    migration_type: Literal["legacy_source_catalog_bootstrap"] = MIGRATION_TYPE
    target_database: str
    zip_sha256: str
    plan_semantic_sha256: str
    planner_version: str = PLANNER_VERSION
    decisions_sha256: str
    production_backup_evidence: ManifestBackupEvidence | None = None
    source_id_map: dict[str, str]
    reference_id_map: dict[str, str]
    source_entity_hashes: dict[str, str]
    reference_entity_hashes: dict[str, str]
    reference_evidence_hashes: dict[str, str]
    reference_evidence_summaries: tuple[ReferenceEvidenceSummary, ...] = ()
    expected_counts: ManifestExpectedCounts
    state: ManifestState = ManifestState.PREPARED
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_updated_at: datetime
    sources_created: int = 0
    sources_identical: int = 0
    references_created: int = 0
    references_identical: int = 0
    indexes_status: ManifestIndexStatus
    errors: tuple[ManifestError, ...] = ()
    invariant_hashes_before: ManifestInvariantHashes
    invariant_hashes_after: ManifestInvariantHashes | None = None
    attempts: int = 0
    resume_count: int = 0
    revision: int = 0

    @field_validator("migration_id")
    @classmethod
    def migration_id_is_uuid4(cls, value: Any) -> str:
        """Validate the durable migration UUID."""
        return _validate_prefixed_uuid4(value, "mig", "migration_id")

    @field_validator(
        "zip_sha256",
        "plan_semantic_sha256",
        "decisions_sha256",
    )
    @classmethod
    def identity_hashes_are_sha256(cls, value: Any, info: Any) -> str:
        """Validate immutable manifest identity hashes."""
        return _validate_sha256(value, info.field_name)

    @field_validator(
        "source_entity_hashes",
        "reference_entity_hashes",
        "reference_evidence_hashes",
    )
    @classmethod
    def hash_maps_are_bounded(cls, value: dict[str, str], info: Any) -> dict[str, str]:
        """Validate candidate-keyed entity and evidence digests."""
        if len(value) > MAX_CANDIDATES_PER_KIND or any(not key for key in value):
            raise ValueError(f"{info.field_name} exceeds manifest limits")
        return {
            key: _validate_sha256(digest, f"{info.field_name} value")
            for key, digest in sorted(value.items())
        }

    @field_validator("created_at", "started_at", "completed_at", "last_updated_at")
    @classmethod
    def timestamps_are_utc_milliseconds(cls, value: datetime | None) -> datetime | None:
        """Normalize every manifest timestamp to aware UTC milliseconds."""
        return None if value is None else utc_now_milliseconds(lambda: value)

    @field_validator(
        "sources_created",
        "sources_identical",
        "references_created",
        "references_identical",
        "attempts",
        "resume_count",
        "revision",
    )
    @classmethod
    def progress_is_nonnegative(cls, value: Any) -> int:
        """Reject booleans, coercions, and negative progress counters."""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("manifest progress counters must be non-negative integers")
        return value

    @field_validator("errors")
    @classmethod
    def errors_are_bounded(cls, value: tuple[ManifestError, ...]) -> tuple[ManifestError, ...]:
        """Bound persisted failure history."""
        if len(value) > MAX_MANIFEST_ERRORS:
            raise ValueError("manifest error history exceeds its limit")
        return value

    @field_validator("reference_evidence_summaries")
    @classmethod
    def evidence_is_bounded(
        cls, value: tuple[ReferenceEvidenceSummary, ...]
    ) -> tuple[ReferenceEvidenceSummary, ...]:
        """Bound and deterministically order non-raw evidence summaries."""
        if len(value) > MAX_EVIDENCE_SUMMARIES:
            raise ValueError("reference evidence summaries exceed their limit")
        keys = [item.reference_candidate_key for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("reference evidence summary keys must be unique")
        return tuple(sorted(value, key=lambda item: item.reference_candidate_key))

    @model_validator(mode="after")
    def validate_prepared_authority(self) -> MigrationManifest:
        """Prove stable identity, complete maps, hashes, and coherent timestamps."""
        expected_key = stable_manifest_key(
            migration_type=self.migration_type,
            target_database=self.target_database,
            zip_sha256=self.zip_sha256,
            plan_semantic_sha256=self.plan_semantic_sha256,
            manifest_schema_version=self.manifest_schema_version,
        )
        if self.manifest_key != expected_key:
            raise ValueError("manifest_key does not match its stable identity")
        allocation = FinalIdAllocation(
            migration_id=self.migration_id,
            created_at=self.created_at,
            source_id_map=self.source_id_map,
            reference_id_map=self.reference_id_map,
        )
        object.__setattr__(self, "source_id_map", allocation.source_id_map)
        object.__setattr__(self, "reference_id_map", allocation.reference_id_map)
        source_keys = set(self.source_id_map)
        reference_keys = set(self.reference_id_map)
        if source_keys != set(self.source_entity_hashes):
            raise ValueError("source entity hashes must cover the source ID map exactly")
        if reference_keys != set(self.reference_entity_hashes):
            raise ValueError("reference entity hashes must cover the reference ID map exactly")
        if reference_keys != set(self.reference_evidence_hashes):
            raise ValueError("reference evidence hashes must cover the reference ID map exactly")
        summary_keys = {item.reference_candidate_key for item in self.reference_evidence_summaries}
        if not summary_keys <= reference_keys:
            raise ValueError("reference evidence summaries contain an unknown candidate key")
        if len(source_keys) != self.expected_counts.source_candidates:
            raise ValueError("source ID map count differs from expected_counts")
        if len(reference_keys) != self.expected_counts.reference_candidates:
            raise ValueError("reference ID map count differs from expected_counts")
        if self.indexes_status.expected <= 0 or self.indexes_status.expected_sha256 is None:
            raise ValueError("manifest requires a complete expected index plan")
        if self.state == ManifestState.PREPARED and (
            self.indexes_status.applied
            or self.indexes_status.already_present
            or self.indexes_status.missing != self.indexes_status.expected
            or self.indexes_status.conflicts
            or self.indexes_status.final_sha256 is not None
        ):
            raise ValueError("prepared manifest requires an untouched missing index plan")
        source_progress = self.sources_created + self.sources_identical
        reference_progress = self.references_created + self.references_identical
        if source_progress > self.expected_counts.source_candidates:
            raise ValueError("Source progress exceeds expected_counts")
        if reference_progress > self.expected_counts.reference_candidates:
            raise ValueError("Reference progress exceeds expected_counts")
        if self.last_updated_at < self.created_at:
            raise ValueError("last_updated_at cannot be earlier than created_at")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at cannot be earlier than created_at")
        if self.completed_at is not None:
            lower_bound = self.started_at or self.created_at
            if self.completed_at < lower_bound:
                raise ValueError("completed_at cannot precede the manifest start")
        if self.state == ManifestState.APPLIED and self.completed_at is None:
            raise ValueError("applied manifest requires completed_at")
        if self.state == ManifestState.APPLIED and (
            self.invariant_hashes_before is None or self.invariant_hashes_after is None
        ):
            raise ValueError("applied manifest requires before and after invariant hashes")
        if self.state == ManifestState.APPLIED and (
            self.indexes_status.missing or self.indexes_status.conflicts
        ):
            raise ValueError("applied manifest cannot retain missing or conflicting indexes")
        if self.state == ManifestState.APPLIED and (
            self.indexes_status.expected <= 0
            or self.indexes_status.applied + self.indexes_status.already_present
            != self.indexes_status.expected
            or self.indexes_status.expected_sha256 is None
            or self.indexes_status.final_sha256 is None
        ):
            raise ValueError("applied manifest requires a complete hashed index status")
        if self.state == ManifestState.APPLIED and (
            source_progress != self.expected_counts.source_candidates
            or reference_progress != self.expected_counts.reference_candidates
        ):
            raise ValueError("applied manifest requires complete Source and Reference progress")
        return self


class ManifestInsertResult(ManifestModel):
    """Outcome of racing to establish the one prepared manifest."""

    manifest: MigrationManifest
    created: bool


def stable_manifest_key(
    *,
    migration_type: str,
    target_database: str,
    zip_sha256: str,
    plan_semantic_sha256: str,
    manifest_schema_version: int = MANIFEST_SCHEMA_VERSION,
) -> str:
    """Derive the stable key without decisions, UUIDs, timestamps, or paths."""
    if not migration_type or not target_database:
        raise ValueError("migration_type and target_database are required")
    _validate_sha256(zip_sha256, "zip_sha256")
    _validate_sha256(plan_semantic_sha256, "plan_semantic_sha256")
    if manifest_schema_version != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported manifest schema version")
    digest = sha256_digest(
        {
            "manifest_schema_version": manifest_schema_version,
            "migration_type": migration_type,
            "target_database": target_database,
            "zip_sha256": zip_sha256,
            "plan_semantic_sha256": plan_semantic_sha256,
        }
    )
    return f"{MANIFEST_KEY_PREFIX}{digest}"


def allocate_final_ids(
    source_candidate_keys: Iterable[str],
    reference_candidate_keys: Iterable[str],
    *,
    source_id_factory: Callable[[], str] = new_source_id,
    reference_id_factory: Callable[[], str] = new_reference_id,
    migration_id_factory: Callable[[], str] = new_migration_id,
    clock: Callable[[], datetime] | None = None,
) -> FinalIdAllocation:
    """Allocate the full final-ID map once before any catalog persistence."""
    source_keys = tuple(source_candidate_keys)
    reference_keys = tuple(reference_candidate_keys)
    if len(source_keys) != len(set(source_keys)) or any(not key for key in source_keys):
        raise ValueError("source candidate keys must be unique and nonempty")
    if len(reference_keys) != len(set(reference_keys)) or any(not key for key in reference_keys):
        raise ValueError("reference candidate keys must be unique and nonempty")
    if len(source_keys) > MAX_CANDIDATES_PER_KIND or len(reference_keys) > MAX_CANDIDATES_PER_KIND:
        raise ValueError("candidate count exceeds manifest allocation limits")
    return FinalIdAllocation(
        migration_id=migration_id_factory(),
        created_at=utc_now_milliseconds(clock),
        source_id_map={key: source_id_factory() for key in sorted(source_keys)},
        reference_id_map={key: reference_id_factory() for key in sorted(reference_keys)},
    )


def allocate_prepared_manifest(
    *,
    target_database: str,
    zip_sha256: str,
    plan_semantic_sha256: str,
    decisions_sha256: str,
    expected_counts: ManifestExpectedCounts,
    source_candidate_keys: Iterable[str],
    reference_candidate_keys: Iterable[str],
    source_entity_hashes: Mapping[str, str],
    reference_entity_hashes: Mapping[str, str],
    reference_evidence_hashes: Mapping[str, str],
    invariant_hashes_before: ManifestInvariantHashes,
    indexes_status: ManifestIndexStatus,
    reference_evidence_summaries: Iterable[ReferenceEvidenceSummary] = (),
    planner_version: str = PLANNER_VERSION,
    production_backup_evidence: ManifestBackupEvidence | None = None,
    source_id_factory: Callable[[], str] = new_source_id,
    reference_id_factory: Callable[[], str] = new_reference_id,
    migration_id_factory: Callable[[], str] = new_migration_id,
    clock: Callable[[], datetime] | None = None,
) -> MigrationManifest:
    """Build one complete prepared manifest from a single final-ID allocation."""
    allocation = allocate_final_ids(
        source_candidate_keys,
        reference_candidate_keys,
        source_id_factory=source_id_factory,
        reference_id_factory=reference_id_factory,
        migration_id_factory=migration_id_factory,
        clock=clock,
    )
    return build_prepared_manifest_from_allocation(
        allocation=allocation,
        target_database=target_database,
        zip_sha256=zip_sha256,
        plan_semantic_sha256=plan_semantic_sha256,
        decisions_sha256=decisions_sha256,
        expected_counts=expected_counts,
        source_entity_hashes=source_entity_hashes,
        reference_entity_hashes=reference_entity_hashes,
        reference_evidence_hashes=reference_evidence_hashes,
        reference_evidence_summaries=reference_evidence_summaries,
        planner_version=planner_version,
        production_backup_evidence=production_backup_evidence,
        indexes_status=indexes_status,
        invariant_hashes_before=invariant_hashes_before,
    )


def build_prepared_manifest_from_allocation(
    *,
    allocation: FinalIdAllocation,
    target_database: str,
    zip_sha256: str,
    plan_semantic_sha256: str,
    decisions_sha256: str,
    expected_counts: ManifestExpectedCounts,
    source_entity_hashes: Mapping[str, str],
    reference_entity_hashes: Mapping[str, str],
    reference_evidence_hashes: Mapping[str, str],
    invariant_hashes_before: ManifestInvariantHashes,
    indexes_status: ManifestIndexStatus,
    reference_evidence_summaries: Iterable[ReferenceEvidenceSummary] = (),
    planner_version: str = PLANNER_VERSION,
    production_backup_evidence: ManifestBackupEvidence | None = None,
) -> MigrationManifest:
    """Persist hashes built from an already allocated map without regenerating IDs."""
    return MigrationManifest(
        manifest_key=stable_manifest_key(
            migration_type=MIGRATION_TYPE,
            target_database=target_database,
            zip_sha256=zip_sha256,
            plan_semantic_sha256=plan_semantic_sha256,
        ),
        migration_id=allocation.migration_id,
        target_database=target_database,
        zip_sha256=zip_sha256,
        plan_semantic_sha256=plan_semantic_sha256,
        planner_version=planner_version,
        decisions_sha256=decisions_sha256,
        production_backup_evidence=production_backup_evidence,
        source_id_map=allocation.source_id_map,
        reference_id_map=allocation.reference_id_map,
        source_entity_hashes=dict(source_entity_hashes),
        reference_entity_hashes=dict(reference_entity_hashes),
        reference_evidence_hashes=dict(reference_evidence_hashes),
        reference_evidence_summaries=tuple(reference_evidence_summaries),
        expected_counts=expected_counts,
        created_at=allocation.created_at,
        last_updated_at=allocation.created_at,
        indexes_status=indexes_status,
        invariant_hashes_before=invariant_hashes_before,
    )


def manifest_compatibility_issues(
    existing: MigrationManifest,
    requested: MigrationManifest,
) -> tuple[str, ...]:
    """Compare external authority while allowing the race winner's UUID map."""
    issues: list[str] = []
    fields = (
        "manifest_schema_version",
        "manifest_key",
        "migration_type",
        "target_database",
        "zip_sha256",
        "plan_semantic_sha256",
        "planner_version",
        "decisions_sha256",
        "production_backup_evidence",
        "expected_counts",
        "reference_evidence_hashes",
        "invariant_hashes_before",
    )
    for field_name in fields:
        if getattr(existing, field_name) != getattr(requested, field_name):
            issues.append(field_name)
    if set(existing.source_id_map) != set(requested.source_id_map):
        issues.append("source_candidate_keys")
    if set(existing.reference_id_map) != set(requested.reference_id_map):
        issues.append("reference_candidate_keys")
    return tuple(issues)


def bounded_safe_error(
    error: BaseException | str,
    *,
    code: str,
    state: ManifestState,
    attempt: int,
    occurred_at: datetime | None = None,
) -> ManifestError:
    """Redact credentials, URIs, paths, controls, and excessive error text."""
    if not _ERROR_CODE_RE.fullmatch(code):
        raise ValueError("manifest error code is invalid")
    text = " ".join(str(error).split()) or "Operation failed without diagnostic text."
    text = _MONGO_URI_RE.sub("<redacted-mongo-uri>", text)
    text = _SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    text = _WINDOWS_PATH_RE.sub("<redacted-path>", text)
    text = _POSIX_PATH_RE.sub("<redacted-path>", text)
    if len(text) > MAX_ERROR_MESSAGE_LENGTH:
        text = text[: MAX_ERROR_MESSAGE_LENGTH - 3].rstrip() + "..."
    return ManifestError(
        code=code,
        message=text,
        occurred_at=occurred_at or utc_now_milliseconds(),
        state=state,
        attempt=attempt,
    )


_NEXT_STATE = {
    ManifestState.PREPARED: ManifestState.APPLYING_INDEXES,
    ManifestState.APPLYING_INDEXES: ManifestState.APPLYING_SOURCES,
    ManifestState.APPLYING_SOURCES: ManifestState.APPLYING_REFERENCES,
    ManifestState.APPLYING_REFERENCES: ManifestState.VERIFYING,
    ManifestState.VERIFYING: ManifestState.APPLIED,
}


def state_transition_allowed(current: ManifestState, requested: ManifestState) -> bool:
    """Return whether a CAS update may move to the requested durable state."""
    if current in {ManifestState.APPLIED, ManifestState.BLOCKED}:
        return False
    if current == requested:
        return True
    if requested == ManifestState.BLOCKED:
        return True
    if requested == ManifestState.FAILED:
        return True
    if current == ManifestState.FAILED:
        return requested == ManifestState.APPLYING_INDEXES
    return _NEXT_STATE.get(current) == requested


def _mongo_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _mongo_value(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _mongo_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mongo_value(item) for item in value]
    return value


def _mongo_document(manifest: MigrationManifest) -> dict[str, Any]:
    document = _mongo_value(manifest)
    document["_id"] = manifest.manifest_key
    return document


def _hydrate_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, Mapping):
        return {str(key): _hydrate_datetime(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_hydrate_datetime(item) for item in value]
    return value


def _manifest_model(document: Mapping[str, Any] | None) -> MigrationManifest | None:
    if document is None:
        return None
    payload = _hydrate_datetime(dict(document))
    mongo_id = payload.pop("_id", None)
    if mongo_id is not None and payload.get("manifest_key") != mongo_id:
        raise ManifestCompatibilityError(("manifest_key",))
    return MigrationManifest.model_validate(payload)


class ManifestStore:
    """Race-safe persistence boundary for one explicit target database."""

    _MUTABLE_FIELDS = frozenset(
        {
            "state",
            "started_at",
            "completed_at",
            "sources_created",
            "sources_identical",
            "references_created",
            "references_identical",
            "indexes_status",
            "invariant_hashes_before",
            "invariant_hashes_after",
        }
    )

    def __init__(
        self,
        database: Any,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Retain an explicit database without touching a collection."""
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ManifestStore requires an explicit MongoDB database")
        self.database = database
        self.clock = clock

    def _collection_exists(self) -> bool:
        if not hasattr(self.database, "list_collection_names"):
            return True
        return MANIFEST_COLLECTION in self.database.list_collection_names()

    @property
    def _collection(self) -> Any:
        return self.database[MANIFEST_COLLECTION]

    def get(self, manifest_key: str) -> MigrationManifest | None:
        """Load one manifest without materializing an absent collection."""
        if not self._collection_exists():
            return None
        return _manifest_model(self._collection.find_one({"_id": manifest_key}))

    def find_for_target(
        self,
        target_database: str,
        *,
        migration_type: str = MIGRATION_TYPE,
    ) -> tuple[MigrationManifest, ...]:
        """Return a bounded deterministic set of manifests for one target."""
        if not self._collection_exists():
            return ()
        cursor = self._collection.find(
            {
                "target_database": target_database,
                "migration_type": migration_type,
            }
        )
        if hasattr(cursor, "limit"):
            cursor = cursor.limit(MAX_MANIFESTS_PER_TARGET + 1)
        values: list[MigrationManifest] = []
        try:
            for document in cursor:
                if len(values) >= MAX_MANIFESTS_PER_TARGET:
                    raise ManifestCompatibilityError(("too_many_target_manifests",))
                model = _manifest_model(document)
                if model is not None:
                    values.append(model)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        return tuple(sorted(values, key=lambda item: item.manifest_key))

    def insert_prepared_if_absent(
        self,
        requested: MigrationManifest,
    ) -> ManifestInsertResult:
        """Insert a complete prepared manifest or load the compatible race winner."""
        if requested.state != ManifestState.PREPARED or requested.revision != 0:
            raise ValueError("only a revision-zero prepared manifest may be inserted")
        try:
            self._collection.insert_one(_mongo_document(requested))
        except DuplicateKeyError as exc:
            try:
                winner = self.get(requested.manifest_key)
            except ManifestCompatibilityError:
                raise
            except (TypeError, ValueError) as hydration_error:
                raise ManifestCompatibilityError(("malformed_race_winner",)) from hydration_error
            if winner is None:
                raise ManifestConcurrentUpdateError(
                    "manifest duplicate race did not expose a winner"
                ) from exc
            issues = manifest_compatibility_issues(winner, requested)
            if issues:
                raise ManifestCompatibilityError(issues) from exc
            return ManifestInsertResult(manifest=winner, created=False)
        return ManifestInsertResult(manifest=requested, created=True)

    def update_cas(
        self,
        manifest_key: str,
        *,
        expected_revision: int,
        allowed_states: Iterable[ManifestState],
        changes: Mapping[str, Any] | None = None,
        attempts_increment: int = 0,
        resume_count_increment: int = 0,
    ) -> MigrationManifest:
        """Apply one validated field-level compare-and-set update."""
        if isinstance(expected_revision, bool) or expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer")
        states = tuple(dict.fromkeys(ManifestState(state) for state in allowed_states))
        if not states:
            raise ValueError("allowed_states cannot be empty")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (attempts_increment, resume_count_increment)
        ):
            raise ValueError("manifest increments must be non-negative integers")
        changes = dict(changes or {})
        unsupported = set(changes) - self._MUTABLE_FIELDS
        if unsupported:
            raise ValueError(f"immutable or unsupported manifest fields: {sorted(unsupported)}")
        current = self.get(manifest_key)
        if current is None:
            raise ManifestConcurrentUpdateError("manifest disappeared before CAS update")
        if current.revision != expected_revision or current.state not in states:
            raise ManifestConcurrentUpdateError("manifest revision or state changed")
        for field_name in ("started_at", "completed_at"):
            if (
                getattr(current, field_name) is not None
                and field_name in changes
                and changes[field_name] != getattr(current, field_name)
            ):
                raise ValueError(f"{field_name} is set-once and cannot be changed")
        requested_state = ManifestState(changes.get("state", current.state))
        if not state_transition_allowed(current.state, requested_state):
            raise ValueError(
                f"invalid manifest transition: {current.state.value} -> {requested_state.value}"
            )
        timestamp = utc_now_milliseconds(self.clock)
        candidate_payload = current.model_dump(mode="python")
        candidate_payload.update(changes)
        candidate_payload.update(
            {
                "state": requested_state,
                "attempts": current.attempts + attempts_increment,
                "resume_count": current.resume_count + resume_count_increment,
                "last_updated_at": timestamp,
                "revision": current.revision + 1,
            }
        )
        candidate = MigrationManifest.model_validate(candidate_payload)
        set_fields = {
            key: _mongo_value(getattr(candidate, key))
            for key in (
                *changes,
                "state",
                "attempts",
                "resume_count",
                "last_updated_at",
                "revision",
            )
        }
        result = self._collection.update_one(
            {
                "_id": manifest_key,
                "revision": expected_revision,
                "state": {"$in": [state.value for state in states]},
            },
            {"$set": set_fields},
        )
        if not getattr(result, "matched_count", 0):
            raise ManifestConcurrentUpdateError("manifest CAS update lost a concurrent race")
        updated = self.get(manifest_key)
        if updated is None:
            raise ManifestConcurrentUpdateError("manifest disappeared after CAS update")
        return updated

    def append_error_cas(
        self,
        manifest_key: str,
        *,
        expected_revision: int,
        allowed_states: Iterable[ManifestState],
        error: ManifestError,
        target_state: ManifestState = ManifestState.FAILED,
    ) -> MigrationManifest:
        """Append one safe bounded error with the same revision discipline."""
        states = tuple(dict.fromkeys(ManifestState(state) for state in allowed_states))
        current = self.get(manifest_key)
        if current is None or current.revision != expected_revision or current.state not in states:
            raise ManifestConcurrentUpdateError("manifest changed before error append")
        if not state_transition_allowed(current.state, target_state):
            raise ValueError("invalid state transition while appending manifest error")
        errors = (*current.errors, error)[-MAX_MANIFEST_ERRORS:]
        timestamp = utc_now_milliseconds(self.clock)
        candidate_payload = current.model_dump(mode="python")
        candidate_payload.update(
            {
                "state": target_state,
                "errors": errors,
                "last_updated_at": timestamp,
                "revision": current.revision + 1,
            }
        )
        candidate = MigrationManifest.model_validate(candidate_payload)
        result = self._collection.update_one(
            {
                "_id": manifest_key,
                "revision": expected_revision,
                "state": {"$in": [state.value for state in states]},
            },
            {
                "$set": {
                    "state": candidate.state.value,
                    "errors": _mongo_value(candidate.errors),
                    "last_updated_at": candidate.last_updated_at,
                    "revision": candidate.revision,
                }
            },
        )
        if not getattr(result, "matched_count", 0):
            raise ManifestConcurrentUpdateError("manifest error append lost a concurrent race")
        updated = self.get(manifest_key)
        if updated is None:
            raise ManifestConcurrentUpdateError("manifest disappeared after error append")
        return updated


__all__ = [
    "FinalIdAllocation",
    "MANIFEST_COLLECTION",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_MANIFEST_ERRORS",
    "MIGRATION_TYPE",
    "ManifestCompatibilityError",
    "ManifestBackupEvidence",
    "ManifestConcurrentUpdateError",
    "ManifestError",
    "ManifestExpectedCounts",
    "ManifestIndexStatus",
    "ManifestInsertResult",
    "ManifestInvariantHashes",
    "ManifestPersistenceError",
    "ManifestState",
    "ManifestStore",
    "MigrationManifest",
    "ReferenceEvidenceSummary",
    "allocate_final_ids",
    "allocate_prepared_manifest",
    "build_prepared_manifest_from_allocation",
    "bounded_safe_error",
    "manifest_compatibility_issues",
    "new_migration_id",
    "stable_manifest_key",
    "state_transition_allowed",
    "utc_now_milliseconds",
]

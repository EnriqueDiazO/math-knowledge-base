"""Idempotent, resumable Source Catalog bootstrap for an isolated legacy copy."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.indexes import SOURCE_CATALOG_INDEXES
from mathmongo.source_catalog.indexes import IndexPlan
from mathmongo.source_catalog.indexes import IndexPlanConflictError
from mathmongo.source_catalog.indexes import IndexState
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_catalog.models import ImportMethod
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import ReferenceProvenance
from mathmongo.source_catalog.models import ReferenceStatus
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceLegacy
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.models import SourceType
from mathmongo.source_catalog.models import new_reference_id
from mathmongo.source_catalog.models import new_source_id
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_catalog.service import SourceCatalogService
from mathmongo.source_catalog_migration.apply_result import ApplyOutcome
from mathmongo.source_catalog_migration.apply_result import ApplyResult
from mathmongo.source_catalog_migration.apply_result import IndexApplyResult
from mathmongo.source_catalog_migration.apply_result import safe_apply_diagnostic
from mathmongo.source_catalog_migration.apply_safety import ApplyAuthorization
from mathmongo.source_catalog_migration.apply_safety import ApplySafetyError
from mathmongo.source_catalog_migration.apply_safety import LegacySnapshot
from mathmongo.source_catalog_migration.apply_safety import PlanPreflight
from mathmongo.source_catalog_migration.apply_safety import capture_legacy_snapshot
from mathmongo.source_catalog_migration.apply_safety import compare_legacy_snapshots
from mathmongo.source_catalog_migration.apply_safety import legacy_snapshot_from_export
from mathmongo.source_catalog_migration.apply_safety import manifest_invariant_hashes
from mathmongo.source_catalog_migration.apply_safety import require_successful_legacy_preflight
from mathmongo.source_catalog_migration.apply_safety import validate_apply_authorization
from mathmongo.source_catalog_migration.apply_safety import validate_authoritative_inputs
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.decisions import DecisionSet
from mathmongo.source_catalog_migration.decisions import ValidatedDecisions
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.manifest import MAX_MANIFESTS_PER_TARGET
from mathmongo.source_catalog_migration.manifest import MIGRATION_TYPE
from mathmongo.source_catalog_migration.manifest import FinalIdAllocation
from mathmongo.source_catalog_migration.manifest import ManifestCompatibilityError
from mathmongo.source_catalog_migration.manifest import ManifestConcurrentUpdateError
from mathmongo.source_catalog_migration.manifest import ManifestIndexStatus
from mathmongo.source_catalog_migration.manifest import ManifestInvariantHashes
from mathmongo.source_catalog_migration.manifest import ManifestState
from mathmongo.source_catalog_migration.manifest import ManifestStore
from mathmongo.source_catalog_migration.manifest import MigrationManifest
from mathmongo.source_catalog_migration.manifest import ReferenceEvidenceSummary
from mathmongo.source_catalog_migration.manifest import allocate_final_ids
from mathmongo.source_catalog_migration.manifest import bounded_safe_error
from mathmongo.source_catalog_migration.manifest import build_prepared_manifest_from_allocation
from mathmongo.source_catalog_migration.manifest import manifest_compatibility_issues
from mathmongo.source_catalog_migration.manifest import new_migration_id
from mathmongo.source_catalog_migration.manifest import stable_manifest_key
from mathmongo.source_catalog_migration.manifest import utc_now_milliseconds
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.models import ReferenceCandidate
from mathmongo.source_catalog_migration.models import ReviewStatus
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport

Checkpoint = Callable[[str, int | None], None]


class BootstrapError(RuntimeError):
    """Controlled engine error with a stable safe code and outcome."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        outcome: ApplyOutcome = ApplyOutcome.FAILED,
    ) -> None:
        """Retain a stable code without embedding entity data."""
        self.code = code
        self.outcome = outcome
        super().__init__(message)


class BootstrapBlockedError(BootstrapError):
    """Closed safety or consistency failure that must not be overwritten."""

    def __init__(self, code: str, message: str) -> None:
        """Build a non-resumable consistency failure."""
        super().__init__(code, message, outcome=ApplyOutcome.BLOCKED)


class BootstrapConflictError(BootstrapError):
    """Duplicate or index conflict requiring an operator decision."""

    def __init__(self, code: str, message: str) -> None:
        """Build a conflict requiring explicit operator review."""
        super().__init__(code, message, outcome=ApplyOutcome.CONFLICT)


class BootstrapIndexConflictError(BootstrapConflictError):
    """Index conflict carrying already-persisted bounded evidence."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        manifest: MigrationManifest,
        indexes: IndexApplyResult,
    ) -> None:
        """Retain safe summaries so the public result matches the manifest."""
        super().__init__(code, message)
        self.manifest = manifest
        self.indexes = indexes


class BootstrapIndexApplyError(BootstrapError):
    """Transient index failure carrying already-persisted bounded evidence."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        manifest: MigrationManifest,
        indexes: IndexApplyResult,
    ) -> None:
        """Retain safe index progress for failure reporting and resume."""
        super().__init__(code, message)
        self.manifest = manifest
        self.indexes = indexes


@dataclass(frozen=True, slots=True)
class ExpectedCatalog:
    """Complete deterministic S1A entities derived from one durable allocation."""

    sources: Mapping[str, Source]
    references: Mapping[str, Reference]
    source_entity_hashes: Mapping[str, str]
    reference_entity_hashes: Mapping[str, str]
    reference_evidence_hashes: Mapping[str, str]
    reference_evidence_summaries: tuple[ReferenceEvidenceSummary, ...]


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """Candidate keys already present with byte-semantically identical models."""

    source_keys: frozenset[str]
    reference_keys: frozenset[str]


def _entity_hash(entity: Source | Reference) -> str:
    return sha256_digest(entity.model_dump(mode="json"))


def source_from_candidate(
    candidate: Any,
    *,
    source_id: str,
    migration_id: str,
    timestamp: datetime,
) -> Source:
    """Convert one S1C1 candidate without beautifying its exact legacy name."""
    return Source(
        source_id=source_id,
        name=candidate.exact_string,
        aliases=[],
        source_type=SourceType.OTHER,
        status=SourceStatus.ACTIVE,
        legacy=SourceLegacy(
            source_strings=list(candidate.legacy_source_strings),
            migration_batch_id=migration_id,
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _non_locator_warnings(candidate: ReferenceCandidate) -> list[str]:
    return [warning for warning in candidate.warnings if not warning.startswith("locator_")]


def reference_from_candidate(
    candidate: ReferenceCandidate,
    *,
    reference_id: str,
    source_id_map: Mapping[str, str],
    timestamp: datetime,
) -> Reference:
    """Convert accepted bibliography while excluding concept-specific locators."""
    bibliography = candidate.proposed_bibliography
    status = (
        ReferenceStatus.ACTIVE
        if candidate.classification == ReviewStatus.SAFE_EXACT
        else ReferenceStatus.NEEDS_REVIEW
    )
    return Reference(
        reference_id=reference_id,
        source_ids=[source_id_map[key] for key in candidate.source_candidate_keys],
        reference_type=bibliography.get("reference_type", "misc"),
        bibtex={"key": bibliography.get("citekey")},
        authors=bibliography.get("authors") or [],
        title=bibliography.get("title"),
        year=bibliography.get("year"),
        year_raw=bibliography.get("year_raw"),
        journal=bibliography.get("journal"),
        publisher=bibliography.get("publisher"),
        volume=bibliography.get("volume"),
        number=bibliography.get("number"),
        edition=bibliography.get("edition"),
        isbn=bibliography.get("isbn") or [],
        doi=bibliography.get("doi"),
        url=bibliography.get("url"),
        language=bibliography.get("language"),
        notes=bibliography.get("notes"),
        provenance=ReferenceProvenance(
            import_method=ImportMethod.LEGACY,
            imported_at=timestamp,
            warnings=_non_locator_warnings(candidate),
        ),
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _reference_evidence_payload(candidate: ReferenceCandidate) -> dict[str, Any]:
    """Return complete in-memory evidence; only its digest reaches MongoDB."""
    return {
        "reference_candidate_key": candidate.reference_candidate_key,
        "bibliographic_fingerprint": candidate.bibliographic_fingerprint,
        "grouping_rules": candidate.grouping_rules,
        "legacy_keys": candidate.legacy_keys,
        "normalized_bibliography": candidate.normalized_bibliography,
        "proposed_bibliography": candidate.proposed_bibliography,
        "raw_variants": candidate.raw_variants,
        "unknown_fields": candidate.unknown_fields,
        "locator_variants": candidate.locator_variants,
        "locator_statistics": candidate.locator_statistics,
        "warnings": candidate.warnings,
    }


def _reference_evidence_summary(candidate: ReferenceCandidate) -> ReferenceEvidenceSummary:
    field_names = tuple(sorted({str(key) for row in candidate.raw_variants for key in row}))
    limitations = [
        "raw_variants_represented_by_hash_only",
        "legacy_field_aliases_not_added_to_s1a_schema",
    ]
    if candidate.locator_variants or candidate.locator_statistics.concepts_with_locator:
        limitations.append("concept_locators_excluded_from_reference")
    if candidate.unknown_fields:
        limitations.append("unknown_legacy_fields_represented_by_hash_only")
    return ReferenceEvidenceSummary(
        reference_candidate_key=candidate.reference_candidate_key,
        bibliographic_fingerprint=candidate.bibliographic_fingerprint,
        raw_variant_count=candidate.raw_variant_count,
        field_names=field_names,
        limitations=tuple(limitations),
    )


def build_expected_catalog(
    plan: MigrationPlan,
    allocation: FinalIdAllocation,
) -> ExpectedCatalog:
    """Build all 16 Sources and 20 References from one persisted UUID map."""
    source_candidates = {
        candidate.source_candidate_key: candidate for candidate in plan.source_candidates
    }
    reference_candidates = {
        candidate.reference_candidate_key: candidate for candidate in plan.reference_candidates
    }
    if set(source_candidates) != set(allocation.source_id_map):
        raise BootstrapBlockedError(
            "source_map_mismatch",
            "The final Source ID map does not cover the plan exactly.",
        )
    if set(reference_candidates) != set(allocation.reference_id_map):
        raise BootstrapBlockedError(
            "reference_map_mismatch",
            "The final Reference ID map does not cover the plan exactly.",
        )

    sources = {
        key: source_from_candidate(
            source_candidates[key],
            source_id=allocation.source_id_map[key],
            migration_id=allocation.migration_id,
            timestamp=allocation.created_at,
        )
        for key in sorted(source_candidates)
    }
    references = {
        key: reference_from_candidate(
            reference_candidates[key],
            reference_id=allocation.reference_id_map[key],
            source_id_map=allocation.source_id_map,
            timestamp=allocation.created_at,
        )
        for key in sorted(reference_candidates)
    }
    evidence_hashes = {
        key: sha256_digest(_reference_evidence_payload(reference_candidates[key]))
        for key in sorted(reference_candidates)
    }
    return ExpectedCatalog(
        sources=sources,
        references=references,
        source_entity_hashes={key: _entity_hash(value) for key, value in sources.items()},
        reference_entity_hashes={key: _entity_hash(value) for key, value in references.items()},
        reference_evidence_hashes=evidence_hashes,
        reference_evidence_summaries=tuple(
            _reference_evidence_summary(reference_candidates[key])
            for key in sorted(reference_candidates)
        ),
    )


def _allocation_from_manifest(manifest: MigrationManifest) -> FinalIdAllocation:
    return FinalIdAllocation(
        migration_id=manifest.migration_id,
        created_at=manifest.created_at,
        source_id_map=manifest.source_id_map,
        reference_id_map=manifest.reference_id_map,
    )


def _invariant_dict(value: ManifestInvariantHashes | None) -> dict[str, str]:
    return value.model_dump(mode="json") if value is not None else {}


def _index_state_payload(plan: IndexPlan) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "collection": status.spec.collection,
            "name": status.spec.name,
            "keys": status.spec.keys,
            "unique": status.spec.unique,
            "state": status.state.value,
            "detail": status.detail,
        }
        for status in sorted(
            plan.statuses,
            key=lambda item: (item.spec.collection, item.spec.name),
        )
    )


def _expected_index_hash() -> str:
    return sha256_digest(
        [
            {
                "collection": spec.collection,
                "name": spec.name,
                "keys": spec.keys,
                "unique": spec.unique,
            }
            for spec in sorted(
                SOURCE_CATALOG_INDEXES,
                key=lambda item: (item.collection, item.name),
            )
        ]
    )


def _index_result(initial: IndexPlan, final: IndexPlan) -> IndexApplyResult:
    initial_missing = {spec.name for spec in initial.missing}
    final_present = {spec.name for spec in final.present}
    return IndexApplyResult(
        planned=tuple(spec.name for spec in SOURCE_CATALOG_INDEXES),
        applied=tuple(
            spec.name
            for spec in SOURCE_CATALOG_INDEXES
            if spec.name in initial_missing & final_present
        ),
        already_present=tuple(spec.name for spec in initial.present),
        conflicts=tuple(item.spec.name for item in final.conflicts),
        final_state_sha256=sha256_digest(_index_state_payload(final)),
    )


def _manifest_index_status(initial: IndexPlan, final: IndexPlan) -> ManifestIndexStatus:
    initial_missing = {spec.name for spec in initial.missing}
    final_present = {spec.name for spec in final.present}
    return ManifestIndexStatus(
        expected=len(SOURCE_CATALOG_INDEXES),
        applied=len(initial_missing & final_present),
        already_present=len(initial.present),
        missing=len(final.missing),
        conflicts=tuple(item.spec.name for item in final.conflicts),
        expected_sha256=_expected_index_hash(),
        final_sha256=sha256_digest(_index_state_payload(final)),
    )


def _prepared_index_status() -> ManifestIndexStatus:
    return ManifestIndexStatus(
        expected=len(SOURCE_CATALOG_INDEXES),
        missing=len(SOURCE_CATALOG_INDEXES),
        expected_sha256=_expected_index_hash(),
    )


def _manifest_is_compatible(
    manifest: MigrationManifest,
    requested: MigrationManifest,
) -> tuple[str, ...]:
    issues = list(manifest_compatibility_issues(manifest, requested))
    for field_name in (
        "source_entity_hashes",
        "reference_entity_hashes",
        "reference_evidence_summaries",
    ):
        if getattr(manifest, field_name) != getattr(requested, field_name):
            issues.append(field_name)
    return tuple(dict.fromkeys(issues))


class BootstrapEngine:
    """Apply one authoritative S1C1 plan to a strictly isolated target copy."""

    def __init__(
        self,
        database: Any,
        *,
        clock: Callable[[], datetime] | None = None,
        source_id_factory: Callable[[], str] = new_source_id,
        reference_id_factory: Callable[[], str] = new_reference_id,
        migration_id_factory: Callable[[], str] = new_migration_id,
        manifest_store: ManifestStore | None = None,
        source_repository: SourceRepository | None = None,
        reference_repository: ReferenceRepository | None = None,
        service: SourceCatalogService | None = None,
        index_manager: SourceCatalogIndexManager | None = None,
        checkpoint: Checkpoint | None = None,
    ) -> None:
        """Bind collaborators without reading, indexing, or persisting anything."""
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("BootstrapEngine requires one explicit target database")
        self.database = database
        self.clock = clock
        self.source_id_factory = source_id_factory
        self.reference_id_factory = reference_id_factory
        self.migration_id_factory = migration_id_factory
        self.manifests = manifest_store or ManifestStore(database, clock=clock)
        self.sources = source_repository or SourceRepository(database)
        self.references = reference_repository or ReferenceRepository(database)
        self.service = service or SourceCatalogService(
            database,
            source_repository=self.sources,
            reference_repository=self.references,
        )
        self.indexes = index_manager or SourceCatalogIndexManager(database)
        collaborators = (self.manifests, self.sources, self.references, self.service, self.indexes)
        if any(getattr(item, "database", None) is not database for item in collaborators):
            raise ValueError("Every BootstrapEngine collaborator must use the target database")
        if (
            self.service.sources is not self.sources
            or self.service.references is not self.references
        ):
            raise ValueError("BootstrapEngine service must use the engine repositories")
        self.checkpoint = checkpoint

    def _checkpoint(self, label: str, ordinal: int | None = None) -> None:
        if self.checkpoint is not None:
            self.checkpoint(label, ordinal)

    def _result(
        self,
        *,
        outcome: ApplyOutcome,
        authorization: ApplyAuthorization,
        preflight: PlanPreflight | None,
        manifest: MigrationManifest | None = None,
        expected_sources: int = 16,
        expected_references: int = 20,
        sources_created: int = 0,
        sources_identical: int = 0,
        references_created: int = 0,
        references_identical: int = 0,
        indexes: IndexApplyResult | None = None,
        invariant_before: ManifestInvariantHashes | None = None,
        invariant_after: ManifestInvariantHashes | None = None,
        invariants_passed: bool = False,
        errors: Iterable[Any] = (),
        next_action: str,
    ) -> ApplyResult:
        return ApplyResult(
            outcome=outcome,
            target_database=authorization.target_database,
            migration_id=manifest.migration_id if manifest is not None else None,
            zip_sha256=(
                preflight.zip_sha256 if preflight is not None else authorization.expected_zip_sha
            ),
            plan_semantic_sha256=(
                preflight.plan_semantic_sha256
                if preflight is not None
                else authorization.expected_plan_sha
            ),
            decisions_sha256=(
                preflight.decisions_sha256
                if preflight is not None
                else (manifest.decisions_sha256 if manifest is not None else None)
            ),
            expected_sources=expected_sources,
            sources_created=sources_created,
            sources_identical=sources_identical,
            expected_references=expected_references,
            references_created=references_created,
            references_identical=references_identical,
            indexes=indexes or IndexApplyResult(),
            manifest_state=manifest.state.value if manifest is not None else None,
            invariant_hashes_before=_invariant_dict(invariant_before),
            invariant_hashes_after=_invariant_dict(invariant_after),
            invariants_passed=invariants_passed,
            errors=tuple(errors),
            next_action=next_action,
        )

    def _catalog_ids(self, collection_name: str, id_field: str, limit: int) -> tuple[str, ...]:
        if collection_name not in self.database.list_collection_names():
            return ()
        cursor = self.database[collection_name].find({}, {"_id": 0, id_field: 1})
        if hasattr(cursor, "limit"):
            cursor = cursor.limit(limit + 1)
        values: list[str] = []
        try:
            for document in cursor:
                if len(values) >= limit:
                    raise BootstrapBlockedError(
                        "catalog_cardinality_mismatch",
                        f"The {collection_name} collection exceeds the prepared manifest.",
                    )
                value = document.get(id_field)
                if not isinstance(value, str) or not value:
                    raise BootstrapBlockedError(
                        "malformed_catalog_entity",
                        f"The {collection_name} collection contains a malformed identity.",
                    )
                values.append(value)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        if len(values) != len(set(values)):
            raise BootstrapBlockedError(
                "duplicate_catalog_identity",
                f"The {collection_name} collection contains duplicate domain IDs.",
            )
        return tuple(values)

    def _reconcile(self, manifest: MigrationManifest, expected: ExpectedCatalog) -> Reconciliation:
        source_by_id = {value: key for key, value in manifest.source_id_map.items()}
        reference_by_id = {value: key for key, value in manifest.reference_id_map.items()}
        observed_source_ids = self._catalog_ids("sources", "source_id", len(source_by_id))
        observed_reference_ids = self._catalog_ids(
            "references", "reference_id", len(reference_by_id)
        )
        unexpected_sources = set(observed_source_ids) - set(source_by_id)
        unexpected_references = set(observed_reference_ids) - set(reference_by_id)
        if unexpected_sources or unexpected_references:
            raise BootstrapBlockedError(
                "unexpected_catalog_entity",
                "The isolated catalog contains IDs outside the prepared manifest.",
            )

        source_keys: set[str] = set()
        for source_id in observed_source_ids:
            key = source_by_id[source_id]
            try:
                stored = self.sources.get_by_id(source_id)
            except Exception as exc:
                raise BootstrapBlockedError(
                    "malformed_source",
                    "An existing Source cannot be validated against the manifest.",
                ) from exc
            if stored is None or _entity_hash(stored) != expected.source_entity_hashes[key]:
                raise BootstrapBlockedError(
                    "source_content_mismatch",
                    "An existing Source has the prepared ID but different content.",
                )
            source_keys.add(key)

        reference_keys: set[str] = set()
        for reference_id in observed_reference_ids:
            key = reference_by_id[reference_id]
            try:
                stored = self.references.get_by_id(reference_id)
            except Exception as exc:
                raise BootstrapBlockedError(
                    "malformed_reference",
                    "An existing Reference cannot be validated against the manifest.",
                ) from exc
            if stored is None or _entity_hash(stored) != expected.reference_entity_hashes[key]:
                raise BootstrapBlockedError(
                    "reference_content_mismatch",
                    "An existing Reference has the prepared ID but different content.",
                )
            reference_keys.add(key)
        return Reconciliation(frozenset(source_keys), frozenset(reference_keys))

    def _cas(
        self,
        manifest: MigrationManifest,
        *,
        state: ManifestState | None = None,
        changes: Mapping[str, Any] | None = None,
        attempts_increment: int = 0,
        resume_count_increment: int = 0,
    ) -> MigrationManifest:
        payload = dict(changes or {})
        if state is not None:
            payload["state"] = state
        return self.manifests.update_cas(
            manifest.manifest_key,
            expected_revision=manifest.revision,
            allowed_states=(manifest.state,),
            changes=payload,
            attempts_increment=attempts_increment,
            resume_count_increment=resume_count_increment,
        )

    def _record_failure(
        self,
        manifest: MigrationManifest,
        error: BaseException,
        *,
        target_state: ManifestState,
        code: str,
    ) -> MigrationManifest:
        latest = self.manifests.get(manifest.manifest_key) or manifest
        if latest.state in {ManifestState.APPLIED, ManifestState.BLOCKED}:
            return latest
        diagnostic = bounded_safe_error(
            error,
            code=code,
            state=latest.state,
            attempt=latest.attempts,
            occurred_at=utc_now_milliseconds(self.clock),
        )
        try:
            return self.manifests.append_error_cas(
                latest.manifest_key,
                expected_revision=latest.revision,
                allowed_states=(latest.state,),
                error=diagnostic,
                target_state=target_state,
            )
        except ManifestConcurrentUpdateError:
            return self.manifests.get(latest.manifest_key) or latest

    @staticmethod
    def _requested_manifest(
        *,
        allocation: FinalIdAllocation,
        authorization: ApplyAuthorization,
        preflight: PlanPreflight,
        expected: ExpectedCatalog,
        invariant_before: ManifestInvariantHashes,
    ) -> MigrationManifest:
        return build_prepared_manifest_from_allocation(
            allocation=allocation,
            target_database=authorization.target_database,
            zip_sha256=preflight.zip_sha256,
            plan_semantic_sha256=preflight.plan_semantic_sha256,
            decisions_sha256=preflight.decisions_sha256,
            expected_counts=preflight.expected_counts,
            source_entity_hashes=expected.source_entity_hashes,
            reference_entity_hashes=expected.reference_entity_hashes,
            reference_evidence_hashes=expected.reference_evidence_hashes,
            reference_evidence_summaries=expected.reference_evidence_summaries,
            planner_version=preflight.planner_version,
            indexes_status=_prepared_index_status(),
            invariant_hashes_before=invariant_before,
        )

    def _resolve_existing(
        self,
        *,
        authorization: ApplyAuthorization,
        plan: MigrationPlan,
        preflight: PlanPreflight,
    ) -> tuple[MigrationManifest | None, ExpectedCatalog | None]:
        if MANIFEST_COLLECTION in self.database.list_collection_names():
            cursor = self.database[MANIFEST_COLLECTION].find(
                {},
                {"_id": 1, "target_database": 1, "migration_type": 1},
            )
            if hasattr(cursor, "limit"):
                cursor = cursor.limit(MAX_MANIFESTS_PER_TARGET + 1)
            metadata: list[Mapping[str, Any]] = []
            try:
                for document in cursor:
                    if len(metadata) >= MAX_MANIFESTS_PER_TARGET:
                        raise BootstrapBlockedError(
                            "too_many_manifests",
                            "The target manifest collection exceeds its safety limit.",
                        )
                    if not isinstance(document, Mapping):
                        raise BootstrapBlockedError(
                            "malformed_manifest",
                            "The target migration manifest is not a document.",
                        )
                    metadata.append(document)
            finally:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()
            if any(
                row.get("target_database") != authorization.target_database
                or row.get("migration_type") != MIGRATION_TYPE
                for row in metadata
            ):
                raise BootstrapBlockedError(
                    "foreign_manifest",
                    "The isolated target contains an incompatible migration manifest.",
                )
        try:
            manifests = self.manifests.find_for_target(authorization.target_database)
        except Exception as exc:
            raise BootstrapBlockedError(
                "malformed_manifest",
                "The target migration manifest cannot be validated.",
            ) from exc
        if len(manifests) > 1:
            raise BootstrapBlockedError(
                "multiple_target_manifests",
                "The target contains more than one bootstrap manifest.",
            )
        if not manifests:
            return None, None
        manifest = manifests[0]
        expected_key = stable_manifest_key(
            migration_type=MIGRATION_TYPE,
            target_database=authorization.target_database,
            zip_sha256=preflight.zip_sha256,
            plan_semantic_sha256=preflight.plan_semantic_sha256,
        )
        if manifest.manifest_key != expected_key:
            raise BootstrapBlockedError(
                "incompatible_manifest_identity",
                "The target manifest belongs to another ZIP or semantic plan.",
            )
        allocation = _allocation_from_manifest(manifest)
        expected = build_expected_catalog(plan, allocation)
        requested = self._requested_manifest(
            allocation=allocation,
            authorization=authorization,
            preflight=preflight,
            expected=expected,
            invariant_before=manifest.invariant_hashes_before,
        )
        issues = _manifest_is_compatible(manifest, requested)
        if issues:
            raise BootstrapBlockedError(
                "incompatible_manifest",
                "The existing manifest is incompatible with the requested bootstrap: "
                + ", ".join(issues),
            )
        if (
            manifest.indexes_status.expected != len(SOURCE_CATALOG_INDEXES)
            or manifest.indexes_status.expected_sha256 != _expected_index_hash()
        ):
            raise BootstrapBlockedError(
                "incompatible_index_manifest",
                "The existing manifest does not contain the approved index plan.",
            )
        return manifest, expected

    def _preflight_target(
        self,
        export: LoadedLegacyExport,
        *,
        require_catalog_absent: bool,
    ) -> tuple[LegacySnapshot, ManifestInvariantHashes]:
        expected_snapshot = legacy_snapshot_from_export(export)
        before = capture_legacy_snapshot(self.database)
        after = capture_legacy_snapshot(self.database)
        comparison = compare_legacy_snapshots(
            expected_snapshot,
            before,
            after,
            require_catalog_absent=require_catalog_absent,
        )
        require_successful_legacy_preflight(comparison)
        return before, manifest_invariant_hashes(before)

    def _apply_indexes(
        self,
        manifest: MigrationManifest,
    ) -> tuple[MigrationManifest, IndexApplyResult]:
        initial = self.indexes.plan()
        if initial.conflicts:
            status = _manifest_index_status(initial, initial)
            manifest = self._cas(manifest, changes={"indexes_status": status})
            raise BootstrapIndexConflictError(
                "index_conflict",
                "Source Catalog index definitions conflict with the approved stable names.",
                manifest=manifest,
                indexes=_index_result(initial, initial),
            )
        try:
            final = self.indexes.apply()
        except IndexPlanConflictError as exc:
            observed = self.indexes.plan()
            status = _manifest_index_status(initial, observed)
            manifest = self._cas(manifest, changes={"indexes_status": status})
            raise BootstrapIndexConflictError(
                "index_conflict_race",
                "Source Catalog indexes became conflicting during explicit apply.",
                manifest=manifest,
                indexes=_index_result(initial, observed),
            ) from exc
        except Exception as exc:
            observed = self.indexes.plan()
            if observed.conflicts:
                status = _manifest_index_status(initial, observed)
                manifest = self._cas(manifest, changes={"indexes_status": status})
                raise BootstrapIndexConflictError(
                    "index_conflict_race",
                    "Source Catalog indexes became conflicting during explicit apply.",
                    manifest=manifest,
                    indexes=_index_result(initial, observed),
                ) from exc
            status = _manifest_index_status(initial, observed)
            manifest = self._cas(manifest, changes={"indexes_status": status})
            raise BootstrapIndexApplyError(
                "index_apply_failed",
                "Source Catalog index apply failed and retained resumable progress.",
                manifest=manifest,
                indexes=_index_result(initial, observed),
            ) from exc
        if final.conflicts or final.missing:
            status = _manifest_index_status(initial, final)
            manifest = self._cas(manifest, changes={"indexes_status": status})
            raise BootstrapIndexConflictError(
                "index_verification_failed",
                "Source Catalog indexes are not complete after explicit apply.",
                manifest=manifest,
                indexes=_index_result(initial, final),
            )
        summary = _manifest_index_status(initial, final)
        manifest = self._cas(manifest, changes={"indexes_status": summary})
        self._checkpoint("indexes_applied")
        return manifest, _index_result(initial, final)

    def _insert_sources(
        self,
        manifest: MigrationManifest,
        expected: ExpectedCatalog,
        reconciliation: Reconciliation,
    ) -> tuple[MigrationManifest, int, int]:
        created = 0
        identical = len(reconciliation.source_keys)
        confirmed = manifest.sources_created + manifest.sources_identical
        if confirmed > len(reconciliation.source_keys):
            raise BootstrapBlockedError(
                "confirmed_source_missing",
                "A Source previously confirmed by the manifest is missing.",
            )
        cumulative_created = manifest.sources_created
        cumulative_identical = max(identical - cumulative_created, 0)
        manifest = self._cas(
            manifest,
            changes={
                "sources_created": cumulative_created,
                "sources_identical": cumulative_identical,
            },
        )
        for ordinal, key in enumerate(sorted(expected.sources), start=1):
            if key in reconciliation.source_keys:
                continue
            candidate = expected.sources[key]
            raced = self.sources.get_by_id(candidate.source_id)
            if raced is not None:
                if _entity_hash(raced) != expected.source_entity_hashes[key]:
                    raise BootstrapBlockedError(
                        "source_content_mismatch",
                        "A concurrent Source has the prepared ID but different content.",
                    )
                identical += 1
                cumulative_identical += 1
                manifest = self._cas(
                    manifest,
                    changes={
                        "sources_created": cumulative_created,
                        "sources_identical": cumulative_identical,
                    },
                )
                self._checkpoint("source_confirmed", ordinal)
                continue
            duplicates = self.service.detect_source_duplicates(candidate)
            raced_after_detection = any(
                match.entity_id == candidate.source_id for match in duplicates
            )
            duplicates = [match for match in duplicates if match.entity_id != candidate.source_id]
            if duplicates:
                raise BootstrapConflictError(
                    "source_duplicate_conflict",
                    "Unexpected Source duplicate evidence blocks automatic bootstrap.",
                )
            if raced_after_detection:
                raced = self.sources.get_by_id(candidate.source_id)
                if raced is None or _entity_hash(raced) != expected.source_entity_hashes[key]:
                    raise BootstrapBlockedError(
                        "source_content_mismatch",
                        "A concurrent Source has the prepared ID but different content.",
                    )
                identical += 1
                cumulative_identical += 1
                manifest = self._cas(
                    manifest,
                    changes={
                        "sources_created": cumulative_created,
                        "sources_identical": cumulative_identical,
                    },
                )
                self._checkpoint("source_confirmed", ordinal)
                continue
            result = self.service.create_source(candidate, allow_duplicate=True)
            post_insert_duplicates = [
                match for match in result.duplicates if match.entity_id != candidate.source_id
            ]
            stored = (
                result.value if result.persisted else self.sources.get_by_id(candidate.source_id)
            )
            if stored is None or _entity_hash(stored) != expected.source_entity_hashes[key]:
                raise BootstrapError(
                    "source_insert_failed",
                    "A Source could not be persisted and verified.",
                )
            if result.persisted:
                created += 1
                cumulative_created += 1
            else:
                identical += 1
                cumulative_identical += 1
            manifest = self._cas(
                manifest,
                changes={
                    "sources_created": cumulative_created,
                    "sources_identical": cumulative_identical,
                },
            )
            if post_insert_duplicates:
                raise BootstrapConflictError(
                    "source_duplicate_race",
                    "Concurrent Source duplicate evidence blocks automatic bootstrap.",
                )
            self._checkpoint("source_confirmed", ordinal)
        self._checkpoint("sources_complete")
        return manifest, created, identical

    def _insert_references(
        self,
        manifest: MigrationManifest,
        expected: ExpectedCatalog,
        reconciliation: Reconciliation,
    ) -> tuple[MigrationManifest, int, int]:
        created = 0
        identical = len(reconciliation.reference_keys)
        confirmed = manifest.references_created + manifest.references_identical
        if confirmed > len(reconciliation.reference_keys):
            raise BootstrapBlockedError(
                "confirmed_reference_missing",
                "A Reference previously confirmed by the manifest is missing.",
            )
        cumulative_created = manifest.references_created
        cumulative_identical = max(identical - cumulative_created, 0)
        manifest = self._cas(
            manifest,
            changes={
                "references_created": cumulative_created,
                "references_identical": cumulative_identical,
            },
        )
        blocking_classes = {
            DuplicateClassification.EXACT,
            DuplicateClassification.STRONG,
            DuplicateClassification.POSSIBLE,
        }
        for ordinal, key in enumerate(sorted(expected.references), start=1):
            if key in reconciliation.reference_keys:
                continue
            candidate = expected.references[key]
            raced = self.references.get_by_id(candidate.reference_id)
            if raced is not None:
                if _entity_hash(raced) != expected.reference_entity_hashes[key]:
                    raise BootstrapBlockedError(
                        "reference_content_mismatch",
                        "A concurrent Reference has the prepared ID but different content.",
                    )
                identical += 1
                cumulative_identical += 1
                manifest = self._cas(
                    manifest,
                    changes={
                        "references_created": cumulative_created,
                        "references_identical": cumulative_identical,
                    },
                )
                self._checkpoint("reference_confirmed", ordinal)
                continue
            duplicates = self.service.detect_reference_duplicates(
                candidate,
                import_context=manifest.migration_id,
            )
            raced_after_detection = any(
                match.entity_id == candidate.reference_id for match in duplicates
            )
            duplicates = [
                match for match in duplicates if match.entity_id != candidate.reference_id
            ]
            if any(match.classification in blocking_classes for match in duplicates):
                raise BootstrapConflictError(
                    "reference_duplicate_conflict",
                    "Unexpected exact, strong, or possible Reference duplicate evidence blocks apply.",
                )
            if raced_after_detection:
                raced = self.references.get_by_id(candidate.reference_id)
                if raced is None or _entity_hash(raced) != expected.reference_entity_hashes[key]:
                    raise BootstrapBlockedError(
                        "reference_content_mismatch",
                        "A concurrent Reference has the prepared ID but different content.",
                    )
                identical += 1
                cumulative_identical += 1
                manifest = self._cas(
                    manifest,
                    changes={
                        "references_created": cumulative_created,
                        "references_identical": cumulative_identical,
                    },
                )
                self._checkpoint("reference_confirmed", ordinal)
                continue
            result = self.service.create_reference(
                candidate,
                allow_duplicate=True,
                import_context=manifest.migration_id,
            )
            post_insert_duplicates = [
                match
                for match in result.duplicates
                if match.entity_id != candidate.reference_id
                and match.classification in blocking_classes
            ]
            stored = (
                result.value
                if result.persisted
                else self.references.get_by_id(candidate.reference_id)
            )
            if stored is None or _entity_hash(stored) != expected.reference_entity_hashes[key]:
                raise BootstrapError(
                    "reference_insert_failed",
                    "A Reference could not be persisted and verified.",
                )
            if result.persisted:
                created += 1
                cumulative_created += 1
            else:
                identical += 1
                cumulative_identical += 1
            manifest = self._cas(
                manifest,
                changes={
                    "references_created": cumulative_created,
                    "references_identical": cumulative_identical,
                },
            )
            if post_insert_duplicates:
                raise BootstrapConflictError(
                    "reference_duplicate_race",
                    "Concurrent exact, strong, or possible Reference evidence blocks apply.",
                )
            self._checkpoint("reference_confirmed", ordinal)
        self._checkpoint("references_complete")
        return manifest, created, identical

    def _verify_indexes_read_only(self) -> IndexApplyResult:
        final = self.indexes.plan()
        result = _index_result(final, final)
        if (
            final.conflicts
            or final.missing
            or any(item.state != IndexState.PRESENT for item in final.statuses)
        ):
            raise BootstrapConflictError(
                "index_state_mismatch",
                "The final Source Catalog index state is incomplete or conflicting.",
            )
        return result

    def apply(
        self,
        *,
        export: LoadedLegacyExport,
        plan: MigrationPlan,
        decisions: DecisionSet | ValidatedDecisions | Mapping[str, Any],
        authorization: ApplyAuthorization,
    ) -> ApplyResult:
        """Run or resume the closed S1C2A state machine without destructive rollback."""
        preflight: PlanPreflight | None = None
        manifest: MigrationManifest | None = None
        invariant_before: ManifestInvariantHashes | None = None
        invariant_after: ManifestInvariantHashes | None = None
        index_result = IndexApplyResult()
        sources_created = sources_identical = 0
        references_created = references_identical = 0
        resumed = False
        try:
            validate_apply_authorization(authorization)
            preflight = validate_authoritative_inputs(export, plan, decisions)
            database_name = getattr(self.database, "name", None)
            if database_name != authorization.target_database:
                raise BootstrapBlockedError(
                    "database_handle_mismatch",
                    "The explicit database handle does not match the authorized target.",
                )

            manifest, expected = self._resolve_existing(
                authorization=authorization,
                plan=plan,
                preflight=preflight,
            )
            if manifest is not None and manifest.state == ManifestState.BLOCKED:
                return self._result(
                    outcome=ApplyOutcome.BLOCKED,
                    authorization=authorization,
                    preflight=preflight,
                    manifest=manifest,
                    errors=("The durable manifest is blocked and cannot be resumed.",),
                    next_action="Inspect the bounded manifest diagnostics; use a new isolated target.",
                )

            _before_snapshot, observed_invariant = self._preflight_target(
                export,
                require_catalog_absent=manifest is None,
            )
            invariant_before = (
                manifest.invariant_hashes_before
                if manifest is not None and manifest.invariant_hashes_before is not None
                else observed_invariant
            )
            if (
                manifest is not None
                and manifest.invariant_hashes_before is not None
                and manifest.invariant_hashes_before != observed_invariant
            ):
                raise BootstrapBlockedError(
                    "legacy_invariant_mismatch",
                    "Legacy target invariants differ from the prepared manifest.",
                )

            if manifest is None:
                allocation = allocate_final_ids(
                    preflight.source_candidate_keys,
                    preflight.reference_candidate_keys,
                    source_id_factory=self.source_id_factory,
                    reference_id_factory=self.reference_id_factory,
                    migration_id_factory=self.migration_id_factory,
                    clock=self.clock,
                )
                expected = build_expected_catalog(plan, allocation)
                requested = self._requested_manifest(
                    allocation=allocation,
                    authorization=authorization,
                    preflight=preflight,
                    expected=expected,
                    invariant_before=invariant_before,
                )
                try:
                    inserted = self.manifests.insert_prepared_if_absent(requested)
                except ManifestCompatibilityError as exc:
                    raise BootstrapBlockedError(
                        "manifest_race_incompatible",
                        "The manifest race winner is incompatible with this apply.",
                    ) from exc
                manifest = inserted.manifest
                resumed = not inserted.created
                if not inserted.created:
                    expected = build_expected_catalog(plan, _allocation_from_manifest(manifest))
                    winner = self._requested_manifest(
                        allocation=_allocation_from_manifest(manifest),
                        authorization=authorization,
                        preflight=preflight,
                        expected=expected,
                        invariant_before=manifest.invariant_hashes_before,
                    )
                    issues = _manifest_is_compatible(manifest, winner)
                    if issues:
                        raise BootstrapBlockedError(
                            "manifest_race_incompatible",
                            "The manifest race winner is incompatible with this apply.",
                        )
                if (
                    manifest.indexes_status.expected != len(SOURCE_CATALOG_INDEXES)
                    or manifest.indexes_status.expected_sha256 != _expected_index_hash()
                ):
                    raise BootstrapBlockedError(
                        "manifest_race_index_plan_mismatch",
                        "The manifest race winner does not contain the approved index plan.",
                    )
                if manifest.state == ManifestState.BLOCKED:
                    return self._result(
                        outcome=ApplyOutcome.BLOCKED,
                        authorization=authorization,
                        preflight=preflight,
                        manifest=manifest,
                        invariant_before=invariant_before,
                        errors=("The manifest race winner is durably blocked.",),
                        next_action=(
                            "Inspect the bounded manifest diagnostics; use a new isolated target."
                        ),
                    )
                self._checkpoint("manifest_prepared")
            else:
                resumed = True
            assert manifest is not None and expected is not None

            reconciliation = self._reconcile(manifest, expected)
            if manifest.state == ManifestState.APPLIED:
                if len(reconciliation.source_keys) != len(expected.sources) or len(
                    reconciliation.reference_keys
                ) != len(expected.references):
                    raise BootstrapBlockedError(
                        "applied_catalog_incomplete",
                        "The applied manifest no longer has its complete expected catalog.",
                    )
                index_result = self._verify_indexes_read_only()
                durable_indexes = manifest.indexes_status
                if (
                    durable_indexes.expected != len(SOURCE_CATALOG_INDEXES)
                    or durable_indexes.applied + durable_indexes.already_present
                    != len(SOURCE_CATALOG_INDEXES)
                    or durable_indexes.expected_sha256 != _expected_index_hash()
                    or durable_indexes.final_sha256 != index_result.final_state_sha256
                ):
                    raise BootstrapBlockedError(
                        "applied_index_manifest_mismatch",
                        "The applied manifest index evidence is incomplete or inconsistent.",
                    )
                after_snapshot = capture_legacy_snapshot(self.database)
                invariant_after = manifest_invariant_hashes(after_snapshot)
                if (
                    manifest.invariant_hashes_after is not None
                    and invariant_after != manifest.invariant_hashes_after
                ):
                    raise BootstrapBlockedError(
                        "applied_invariant_mismatch",
                        "The applied target legacy invariants changed.",
                    )
                return self._result(
                    outcome=ApplyOutcome.ALREADY_APPLIED,
                    authorization=authorization,
                    preflight=preflight,
                    manifest=manifest,
                    sources_identical=len(expected.sources),
                    references_identical=len(expected.references),
                    indexes=index_result,
                    invariant_before=invariant_before,
                    invariant_after=invariant_after,
                    invariants_passed=True,
                    next_action="No action is required; the catalog is already applied and identical.",
                )

            started_at = manifest.started_at or utc_now_milliseconds(self.clock)
            first_state = (
                ManifestState.APPLYING_INDEXES
                if manifest.state in {ManifestState.PREPARED, ManifestState.FAILED}
                else manifest.state
            )
            manifest = self._cas(
                manifest,
                state=first_state,
                changes={"started_at": started_at},
                attempts_increment=1,
                resume_count_increment=int(resumed),
            )
            manifest, index_result = self._apply_indexes(manifest)

            if manifest.state in {
                ManifestState.PREPARED,
                ManifestState.FAILED,
                ManifestState.APPLYING_INDEXES,
            }:
                manifest = self._cas(manifest, state=ManifestState.APPLYING_SOURCES)
            manifest, sources_created, sources_identical = self._insert_sources(
                manifest,
                expected,
                reconciliation,
            )

            if manifest.state != ManifestState.VERIFYING:
                manifest = self._cas(manifest, state=ManifestState.APPLYING_REFERENCES)
            manifest, references_created, references_identical = self._insert_references(
                manifest,
                expected,
                reconciliation,
            )
            manifest = self._cas(manifest, state=ManifestState.VERIFYING)

            final_reconciliation = self._reconcile(manifest, expected)
            if len(final_reconciliation.source_keys) != len(expected.sources) or len(
                final_reconciliation.reference_keys
            ) != len(expected.references):
                raise BootstrapError(
                    "catalog_verification_incomplete",
                    "Final Source Catalog verification found missing entities.",
                )
            index_result = self._verify_indexes_read_only()
            expected_snapshot = legacy_snapshot_from_export(export)
            after_one = capture_legacy_snapshot(self.database)
            after_two = capture_legacy_snapshot(self.database)
            require_successful_legacy_preflight(
                compare_legacy_snapshots(
                    expected_snapshot,
                    after_one,
                    after_two,
                    require_catalog_absent=False,
                )
            )
            invariant_after = manifest_invariant_hashes(after_two)
            if invariant_after != invariant_before:
                raise BootstrapBlockedError(
                    "legacy_changed_during_apply",
                    "Legacy collections or indexes changed during Source Catalog apply.",
                )
            closing_reconciliation = self._reconcile(manifest, expected)
            if len(closing_reconciliation.source_keys) != len(expected.sources) or len(
                closing_reconciliation.reference_keys
            ) != len(expected.references):
                raise BootstrapBlockedError(
                    "catalog_changed_during_verification",
                    "The Source Catalog changed during final verification.",
                )
            self._checkpoint("verification_complete")
            completed_at = manifest.completed_at or utc_now_milliseconds(self.clock)
            manifest = self._cas(
                manifest,
                state=ManifestState.APPLIED,
                changes={
                    "completed_at": completed_at,
                    "invariant_hashes_after": invariant_after,
                },
            )
            outcome = (
                ApplyOutcome.IDENTICAL
                if resumed
                and not sources_created
                and not references_created
                and sources_identical == len(expected.sources)
                and references_identical == len(expected.references)
                else (ApplyOutcome.RESUMED if resumed else ApplyOutcome.APPLIED)
            )
            return self._result(
                outcome=outcome,
                authorization=authorization,
                preflight=preflight,
                manifest=manifest,
                expected_sources=len(expected.sources),
                expected_references=len(expected.references),
                sources_created=sources_created,
                sources_identical=sources_identical,
                references_created=references_created,
                references_identical=references_identical,
                indexes=index_result,
                invariant_before=invariant_before,
                invariant_after=invariant_after,
                invariants_passed=True,
                next_action="Proceed to S1C2B validation only in a disposable isolated harness.",
            )
        except ManifestConcurrentUpdateError as exc:
            if manifest is not None:
                manifest = self.manifests.get(manifest.manifest_key) or manifest
                sources_created = manifest.sources_created
                sources_identical = manifest.sources_identical
                references_created = manifest.references_created
                references_identical = manifest.references_identical
            return self._result(
                outcome=ApplyOutcome.FAILED,
                authorization=authorization,
                preflight=preflight,
                manifest=manifest,
                sources_created=sources_created,
                sources_identical=sources_identical,
                references_created=references_created,
                references_identical=references_identical,
                indexes=index_result,
                invariant_before=invariant_before,
                invariant_after=invariant_after,
                errors=(safe_apply_diagnostic(exc),),
                next_action=(
                    "Another isolated apply advanced the manifest; rerun to reconcile its state."
                ),
            )
        except (ApplySafetyError, BootstrapError) as exc:
            if isinstance(exc, (BootstrapIndexApplyError, BootstrapIndexConflictError)):
                manifest = exc.manifest
                index_result = exc.indexes
            outcome = exc.outcome if isinstance(exc, BootstrapError) else ApplyOutcome.BLOCKED
            code = exc.code if hasattr(exc, "code") else "apply_safety"
            if manifest is not None and manifest.state not in {
                ManifestState.APPLIED,
                ManifestState.BLOCKED,
            }:
                target_state = (
                    ManifestState.BLOCKED
                    if outcome in {ApplyOutcome.BLOCKED, ApplyOutcome.CONFLICT}
                    else ManifestState.FAILED
                )
                manifest = self._record_failure(
                    manifest,
                    exc,
                    target_state=target_state,
                    code=str(code),
                )
            if manifest is not None:
                sources_created = manifest.sources_created
                sources_identical = manifest.sources_identical
                references_created = manifest.references_created
                references_identical = manifest.references_identical
            return self._result(
                outcome=outcome,
                authorization=authorization,
                preflight=preflight,
                manifest=manifest,
                sources_created=sources_created,
                sources_identical=sources_identical,
                references_created=references_created,
                references_identical=references_identical,
                indexes=index_result,
                invariant_before=invariant_before,
                invariant_after=invariant_after,
                errors=(safe_apply_diagnostic(exc),),
                next_action=(
                    "Inspect the bounded manifest diagnostics and use a new isolated target."
                    if outcome in {ApplyOutcome.BLOCKED, ApplyOutcome.CONFLICT}
                    else "Fix the transient cause and rerun the same command to resume."
                ),
            )
        except Exception as exc:
            if manifest is not None:
                manifest = self._record_failure(
                    manifest,
                    exc,
                    target_state=ManifestState.FAILED,
                    code="unexpected_apply_failure",
                )
                sources_created = manifest.sources_created
                sources_identical = manifest.sources_identical
                references_created = manifest.references_created
                references_identical = manifest.references_identical
            return self._result(
                outcome=ApplyOutcome.FAILED,
                authorization=authorization,
                preflight=preflight,
                manifest=manifest,
                sources_created=sources_created,
                sources_identical=sources_identical,
                references_created=references_created,
                references_identical=references_identical,
                indexes=index_result,
                invariant_before=invariant_before,
                invariant_after=invariant_after,
                errors=(safe_apply_diagnostic(exc),),
                next_action="Fix the transient cause and rerun the same command to resume.",
            )


__all__ = [
    "BootstrapBlockedError",
    "BootstrapConflictError",
    "BootstrapEngine",
    "BootstrapError",
    "BootstrapIndexConflictError",
    "BootstrapIndexApplyError",
    "ExpectedCatalog",
    "Reconciliation",
    "build_expected_catalog",
    "reference_from_candidate",
    "source_from_candidate",
]

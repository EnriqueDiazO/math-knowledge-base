"""Typed, immutable contracts for the read-only S1C1 migration planner."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

SCHEMA_VERSION = 1
PLANNER_VERSION = "s1c1-v1"
PLANNER_NAMESPACE = "mathmongo.source-catalog-migration"


class PlannerModel(BaseModel):
    """Strict immutable base used by every public planner result."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ReviewStatus(str, Enum):
    """Human-review state for one candidate or binding."""

    SAFE_EXACT = "safe_exact"
    SAFE_STRONG = "safe_strong"
    REVIEW_REQUIRED = "review_required"
    METADATA_CONFLICT = "metadata_conflict"
    INSUFFICIENT_IDENTITY = "insufficient_identity"
    MISSING_REFERENCE = "missing_reference"


class ArchiveMember(PlannerModel):
    """Bounded central-directory metadata for one validated ZIP member."""

    name: str
    size_bytes: int
    compressed_size_bytes: int
    compression_ratio: float
    crc32: str
    is_directory: bool = False


class ZipSafetyReport(PlannerModel):
    """Result of validating every archive member before reading payloads."""

    validated: bool
    member_count: int
    file_count: int
    total_uncompressed_bytes: int
    total_compressed_bytes: int
    maximum_compression_ratio: float
    base_directory: str
    unexpected_members: tuple[str, ...] = ()
    suspicious_empty_members: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class InputSnapshot(PlannerModel):
    """Stable identity and declared inventory of the authoritative export."""

    filename: str
    sha256: str
    size_bytes: int
    modified_at: datetime
    exported_at: datetime | None = None
    database_name: str
    counts: dict[str, int]
    format_name: str
    format_version: str
    format_version_source: str
    members: tuple[ArchiveMember, ...]


class LegacyKey(PlannerModel):
    """Exact historical concept identity; never normalized or rewritten."""

    id: str
    source: str


class LegacyLocator(PlannerModel):
    """Concept-specific location metadata excluded from bibliography identity."""

    pages_raw: Any = None
    chapter_raw: Any = None
    section_raw: Any = None
    equation_raw: Any = None
    theorem_raw: Any = None
    notes_raw: Any = None
    raw_alias_values: dict[str, Any] = Field(default_factory=dict)
    present_fields: tuple[str, ...] = ()
    null_fields: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()


class LocatorStatistics(PlannerModel):
    """Bounded aggregate of locator use for a Source or Reference candidate."""

    concepts_with_locator: int = 0
    pages_present: int = 0
    chapter_present: int = 0
    section_present: int = 0
    equation_present: int = 0
    theorem_present: int = 0
    notes_present: int = 0
    variant_count: int = 0


class SourceCandidate(PlannerModel):
    """One exact legacy Source string proposed for later S1C2 bootstrap."""

    source_candidate_key: str
    exact_string: str
    normalized_string: str
    concept_count: int
    concepts_with_reference: int
    concepts_without_reference: int
    reference_candidate_keys: tuple[str, ...] = ()
    locator_statistics: LocatorStatistics = Field(default_factory=LocatorStatistics)
    suggested_source_type: str = "other"
    suggested_display_name: str
    legacy_source_strings: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    review_status: ReviewStatus = ReviewStatus.SAFE_EXACT


class ReferenceCandidate(PlannerModel):
    """A deterministic candidate group; it is not a persisted Reference."""

    reference_candidate_key: str
    classification: ReviewStatus
    grouping_rules: tuple[str, ...]
    concept_count: int
    source_candidate_keys: tuple[str, ...]
    legacy_keys: tuple[LegacyKey, ...]
    bibliographic_fingerprint: str
    normalized_bibliography: dict[str, Any]
    proposed_bibliography: dict[str, Any]
    raw_variants: tuple[dict[str, Any], ...]
    raw_variant_count: int
    unknown_fields: tuple[str, ...] = ()
    normalized_doi: str | None = None
    normalized_isbns: tuple[str, ...] = ()
    normalized_citekeys: tuple[str, ...] = ()
    matching_fields: tuple[str, ...] = ()
    contradictory_fields: tuple[str, ...] = ()
    locator_variants: tuple[LegacyLocator, ...] = ()
    locator_statistics: LocatorStatistics = Field(default_factory=LocatorStatistics)
    warnings: tuple[str, ...] = ()


class ConceptBinding(PlannerModel):
    """Read-only proposal binding exactly one legacy concept to candidates."""

    binding_candidate_key: str
    legacy_key: LegacyKey
    source_candidate_key: str
    reference_candidate_key: str | None = None
    locator: LegacyLocator = Field(default_factory=LegacyLocator)
    flags: tuple[str, ...] = ()
    review_status: ReviewStatus


class Conflict(PlannerModel):
    """Contradictory metadata that prevented an automatic candidate fusion."""

    conflict_key: str
    conflict_type: str
    reference_candidate_keys: tuple[str, ...]
    source_candidate_keys: tuple[str, ...]
    concept_count: int
    matching_fields: tuple[str, ...] = ()
    contradictory_fields: tuple[str, ...] = ()
    normalized_doi: str | None = None
    normalized_isbns: tuple[str, ...] = ()
    normalized_citekeys: tuple[str, ...] = ()
    raw_variant_summaries: tuple[str, ...] = ()
    locator_variants: tuple[LegacyLocator, ...] = ()


class ReviewItem(PlannerModel):
    """Bounded human decision queue item; no decision is applied in S1C1."""

    review_key: str
    candidate_key: str
    problem_type: str
    source_candidate_keys: tuple[str, ...]
    concept_count: int
    matching_fields: tuple[str, ...] = ()
    contradictory_fields: tuple[str, ...] = ()
    normalized_doi: str | None = None
    normalized_isbns: tuple[str, ...] = ()
    normalized_citekeys: tuple[str, ...] = ()
    raw_variant_summaries: tuple[str, ...] = ()
    locator_variants: tuple[LegacyLocator, ...] = ()
    possible_actions: tuple[str, ...] = (
        "accept_as_one_reference",
        "keep_separate",
        "choose_canonical_metadata",
        "defer",
    )


class WeakReferenceSuggestion(PlannerModel):
    """Non-merging warning that two candidates share weak title evidence."""

    suggestion_key: str
    reference_candidate_keys: tuple[str, str]
    reason: str = "weak_title_similarity"
    source_candidate_keys: tuple[str, ...]
    concept_count: int
    title_similarity_key: str
    warning: str = "Suggestion only; S1C1 did not merge these Reference candidates."


class ConsumerInventory(PlannerModel):
    """Read-only count and legacy-identity usage for one coupled collection."""

    collection: str
    document_count: int
    legacy_key_usages: int = 0
    id_at_source_usages: int = 0
    warnings: tuple[str, ...] = ()


class CoupledCollections(PlannerModel):
    """Inventory of collections S1C1 and S1C2 must not modify."""

    consumers: tuple[ConsumerInventory, ...]
    concept_counterparts_in_latex_documents: int
    orphan_latex_documents: int
    relations: int
    knowledge_graph_maps: int
    media_assets: int
    latex_notes: int
    bootstrap_collections_allowed: tuple[str, ...] = (
        "sources",
        "references",
        "source_catalog_migration_manifest",
    )
    collections_unchanged_by_s1c2: tuple[str, ...] = (
        "concepts",
        "latex_documents",
        "relations",
        "knowledge_graph_maps",
        "media_assets",
        "latex_notes",
    )


class PlanSummary(PlannerModel):
    """Top-level deterministic counts for status and dry-run reporting."""

    concept_count: int
    source_candidate_count: int
    embedded_reference_count: int
    missing_reference_count: int
    reference_candidate_count: int
    binding_count: int
    conflict_count: int
    review_item_count: int
    weak_suggestion_count: int = 0


class PlanInvariants(PlannerModel):
    """Machine-readable proof obligations checked before returning a plan."""

    expected_concepts: int | None = None
    expected_sources: int | None = None
    expected_with_reference: int | None = None
    expected_without_reference: int | None = None
    concept_count_matches: bool
    source_count_matches: bool
    reference_partition_matches: bool
    binding_count_matches: bool
    unique_legacy_keys: bool
    unique_binding_keys: bool
    no_concepts_lost: bool
    no_concepts_duplicated: bool
    locators_excluded_from_bibliographic_fingerprints: bool
    metadata_conflicts_not_merged: bool
    no_final_domain_ids: bool
    zip_unchanged: bool

    @property
    def passed(self) -> bool:
        """Return whether every mandatory proof obligation passed."""
        return all(
            (
                self.concept_count_matches,
                self.source_count_matches,
                self.reference_partition_matches,
                self.binding_count_matches,
                self.unique_legacy_keys,
                self.unique_binding_keys,
                self.no_concepts_lost,
                self.no_concepts_duplicated,
                self.locators_excluded_from_bibliographic_fingerprints,
                self.metadata_conflicts_not_merged,
                self.no_final_domain_ids,
                self.zip_unchanged,
            )
        )


class CollectionState(PlannerModel):
    """Deterministic live collection state captured before or after comparison."""

    collection_names: tuple[str, ...]
    counts: dict[str, int]
    fingerprints: dict[str, str]
    indexes: dict[str, tuple[dict[str, Any], ...]]
    indexes_fingerprint: str


class LiveComparison(PlannerModel):
    """Read-only comparison between the ZIP plan and explicit live MathV0."""

    database_name: str
    uri_redacted: str
    before: CollectionState
    after: CollectionState
    read_operations: tuple[str, ...]
    writes_attempted: int
    live_database_drift: bool
    snapshot_drift: bool
    sources_collection_absent: bool
    references_collection_absent: bool
    concept_count_expected: int
    concept_count_live: int
    concept_keys_match: bool
    source_counts_match: bool
    reference_partition_matches: bool
    reference_fingerprints_match: bool
    consumer_counts_match: bool
    drift_details: tuple[str, ...] = ()

    @property
    def successful(self) -> bool:
        """Concurrent live drift makes the comparison itself unsuccessful."""
        return not self.live_database_drift and self.writes_attempted == 0


class StatusReport(PlannerModel):
    """ZIP identity and inventory returned by the non-planning status command."""

    schema_version: int = SCHEMA_VERSION
    planner_version: str = PLANNER_VERSION
    input_snapshot: InputSnapshot
    zip_safety: ZipSafetyReport
    summary: PlanSummary
    coupled_collections: CoupledCollections
    ready_to_plan: bool
    issues: tuple[str, ...] = ()


class MigrationPlan(PlannerModel):
    """Complete deterministic S1C1 dry-run plan; it contains no final IDs."""

    schema_version: int = SCHEMA_VERSION
    planner_version: str = PLANNER_VERSION
    input_snapshot: InputSnapshot
    summary: PlanSummary
    source_candidates: tuple[SourceCandidate, ...]
    reference_candidates: tuple[ReferenceCandidate, ...]
    concept_bindings: tuple[ConceptBinding, ...]
    review_items: tuple[ReviewItem, ...]
    weak_reference_suggestions: tuple[WeakReferenceSuggestion, ...] = ()
    conflicts: tuple[Conflict, ...]
    coupled_collections: CoupledCollections
    invariants: PlanInvariants
    live_comparison: LiveComparison | None = None
    generated_at: datetime
    semantic_sha256: str = ""


__all__ = [
    "ArchiveMember",
    "CollectionState",
    "ConceptBinding",
    "Conflict",
    "ConsumerInventory",
    "CoupledCollections",
    "InputSnapshot",
    "LegacyKey",
    "LegacyLocator",
    "LiveComparison",
    "LocatorStatistics",
    "MigrationPlan",
    "PLANNER_NAMESPACE",
    "PLANNER_VERSION",
    "PlanInvariants",
    "PlanSummary",
    "ReferenceCandidate",
    "ReviewItem",
    "ReviewStatus",
    "SCHEMA_VERSION",
    "SourceCandidate",
    "StatusReport",
    "WeakReferenceSuggestion",
    "ZipSafetyReport",
]

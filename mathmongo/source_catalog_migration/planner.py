"""S1C1 orchestration: inventory, candidates, bindings, and invariants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any

from mathmongo.source_catalog_migration.canonical import candidate_key
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.inventory import LegacyInventory
from mathmongo.source_catalog_migration.inventory import build_inventory
from mathmongo.source_catalog_migration.inventory import has_embedded_reference
from mathmongo.source_catalog_migration.locator import extract_locator
from mathmongo.source_catalog_migration.models import ConceptBinding
from mathmongo.source_catalog_migration.models import LegacyKey
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.models import PlanInvariants
from mathmongo.source_catalog_migration.models import PlanSummary
from mathmongo.source_catalog_migration.models import ReviewStatus
from mathmongo.source_catalog_migration.models import StatusReport
from mathmongo.source_catalog_migration.reference_planner import ReferencePlanningResult
from mathmongo.source_catalog_migration.reference_planner import plan_references
from mathmongo.source_catalog_migration.source_planner import plan_source_keys
from mathmongo.source_catalog_migration.source_planner import plan_sources
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport

_FINAL_ID_RE = re.compile(
    r"\b(?:src|ref)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

AUTHORITATIVE_SNAPSHOT_COUNTS = {
    "backlog_items": 3,
    "concepts": 186,
    "deliverables": 2,
    "knowledge_graph_maps": 2,
    "latex_documents": 187,
    "latex_notes": 34,
    "media_assets": 10,
    "relations": 136,
    "weekly_reviews": 0,
    "worklog_entries": 5,
}


class PlanInvariantError(ValueError):
    """A dry-run proof obligation failed and the planner stopped closed."""


@dataclass(frozen=True, slots=True)
class SnapshotExpectations:
    """Explicit supplied-snapshot facts, never general MathMongo defaults."""

    concept_count: int | None = None
    source_count: int | None = None
    with_reference: int | None = None
    without_reference: int | None = None
    collection_counts: dict[str, int] | None = None


AUTHORITATIVE_EXPECTATIONS = SnapshotExpectations(
    concept_count=186,
    source_count=16,
    with_reference=145,
    without_reference=41,
    collection_counts=AUTHORITATIVE_SNAPSHOT_COUNTS,
)


def authoritative_expectations(database_name: str) -> SnapshotExpectations:
    """Apply supplied-ZIP invariants only when the operator labels it MathV0."""
    return AUTHORITATIVE_EXPECTATIONS if database_name == "MathV0" else SnapshotExpectations()


def expectation_issues(
    inventory: LegacyInventory,
    expectations: SnapshotExpectations,
) -> tuple[str, ...]:
    """Return deterministic supplied-snapshot mismatches without altering data."""
    issues: list[str] = []
    expected_values = (
        ("concepts", expectations.concept_count, len(inventory.concepts)),
        ("Source candidates", expectations.source_count, len(inventory.source_counts)),
        (
            "concepts with Reference",
            expectations.with_reference,
            inventory.concepts_with_reference,
        ),
        (
            "concepts without Reference",
            expectations.without_reference,
            inventory.concepts_without_reference,
        ),
    )
    for label, expected, actual in expected_values:
        if expected is not None and expected != actual:
            issues.append(f"Expected {expected} {label}, found {actual}.")
    if expectations.collection_counts is not None:
        if dict(expectations.collection_counts) != inventory.collection_counts:
            issues.append("Collection counts do not match the supplied MathV0 snapshot.")
    return tuple(issues)


def _observation_flags(
    references: ReferencePlanningResult,
) -> dict[tuple[str, str], tuple[str, ...]]:
    return {
        (item.legacy_key.id, item.legacy_key.source): item.flags for item in references.observations
    }


def _bindings(
    inventory: LegacyInventory,
    source_keys: dict[str, str],
    references: ReferencePlanningResult,
) -> tuple[ConceptBinding, ...]:
    candidate_models = {
        candidate.reference_candidate_key: candidate for candidate in references.candidates
    }
    observation_flags = _observation_flags(references)
    bindings: list[ConceptBinding] = []
    for concept in inventory.concepts:
        legacy_key = LegacyKey(id=str(concept.get("id")), source=str(concept.get("source")))
        raw_key = (legacy_key.id, legacy_key.source)
        reference_key = references.candidate_by_legacy_key.get(raw_key)
        raw_reference = concept.get("referencia")
        locator = extract_locator(raw_reference if isinstance(raw_reference, dict) else None)
        flags = set(locator.flags)
        flags.update(observation_flags.get(raw_key, ()))
        if reference_key is None:
            if "referencia" not in concept:
                flags.add("missing_reference")
            elif concept.get("referencia") is None:
                flags.add("null_reference")
            elif not has_embedded_reference(concept):
                flags.add("empty_reference")
            review_status = ReviewStatus.MISSING_REFERENCE
        else:
            candidate = candidate_models[reference_key]
            review_status = candidate.classification
            if locator.flags and review_status in {
                ReviewStatus.SAFE_EXACT,
                ReviewStatus.SAFE_STRONG,
            }:
                review_status = ReviewStatus.REVIEW_REQUIRED
        binding_content = {
            "legacy_key": legacy_key.model_dump(mode="json"),
            "source_candidate_key": source_keys[legacy_key.source],
            "reference_candidate_key": reference_key,
            "locator": locator.model_dump(mode="json"),
        }
        bindings.append(
            ConceptBinding(
                binding_candidate_key=candidate_key("binding_candidate", binding_content),
                legacy_key=legacy_key,
                source_candidate_key=source_keys[legacy_key.source],
                reference_candidate_key=reference_key,
                locator=locator,
                flags=tuple(sorted(flags)),
                review_status=review_status,
            )
        )
    return tuple(sorted(bindings, key=lambda item: (item.legacy_key.source, item.legacy_key.id)))


def _no_final_ids(value: Any) -> bool:
    return not bool(_FINAL_ID_RE.search(str(value)))


def _invariants(
    inventory: LegacyInventory,
    bindings: tuple[ConceptBinding, ...],
    references: ReferencePlanningResult,
    expectations: SnapshotExpectations,
) -> PlanInvariants:
    legacy_keys = [(item.id, item.source) for item in inventory.legacy_keys]
    binding_legacy_keys = [(item.legacy_key.id, item.legacy_key.source) for item in bindings]
    binding_keys = [item.binding_candidate_key for item in bindings]
    locators_excluded = all(
        not {
            "paginas",
            "pages",
            "pagina",
            "capitulo",
            "chapter",
            "seccion",
            "section",
            "ecuacion",
            "equation",
            "teorema",
            "theorem",
        }
        & set(candidate.normalized_bibliography)
        for candidate in references.candidates
    )
    candidate_payload = [candidate.model_dump(mode="json") for candidate in references.candidates]
    return PlanInvariants(
        expected_concepts=expectations.concept_count,
        expected_sources=expectations.source_count,
        expected_with_reference=expectations.with_reference,
        expected_without_reference=expectations.without_reference,
        concept_count_matches=(
            expectations.concept_count is None
            or len(inventory.concepts) == expectations.concept_count
        ),
        source_count_matches=(
            expectations.source_count is None
            or len(inventory.source_counts) == expectations.source_count
        ),
        reference_partition_matches=(
            inventory.concepts_with_reference + inventory.concepts_without_reference
            == len(inventory.concepts)
            and sum(item.reference_candidate_key is not None for item in bindings)
            == inventory.concepts_with_reference
            and sum(item.reference_candidate_key is None for item in bindings)
            == inventory.concepts_without_reference
            and (
                expectations.with_reference is None
                or inventory.concepts_with_reference == expectations.with_reference
            )
            and (
                expectations.without_reference is None
                or inventory.concepts_without_reference == expectations.without_reference
            )
        ),
        binding_count_matches=len(bindings) == len(inventory.concepts),
        unique_legacy_keys=len(legacy_keys) == len(set(legacy_keys)),
        unique_binding_keys=len(binding_keys) == len(set(binding_keys)),
        no_concepts_lost=set(binding_legacy_keys) == set(legacy_keys),
        no_concepts_duplicated=len(binding_legacy_keys) == len(set(binding_legacy_keys)),
        locators_excluded_from_bibliographic_fingerprints=locators_excluded,
        metadata_conflicts_not_merged=references.conflict_safety_passed
        and all(len(conflict.reference_candidate_keys) >= 2 for conflict in references.conflicts),
        no_final_domain_ids=_no_final_ids(candidate_payload),
        zip_unchanged=True,
    )


def semantic_plan_payload(plan: MigrationPlan) -> dict[str, Any]:
    """Return semantic plan data excluding volatile/non-authoritative metadata."""
    payload = plan.model_dump(mode="json")
    payload.pop("generated_at", None)
    payload.pop("semantic_sha256", None)
    payload.pop("live_comparison", None)
    return payload


def build_plan(
    export: LoadedLegacyExport,
    *,
    expectations: SnapshotExpectations | None = None,
    generated_at: datetime | None = None,
) -> MigrationPlan:
    """Build a complete dry-run plan without filesystem or MongoDB writes."""
    inventory = build_inventory(export)
    expectations = expectations or SnapshotExpectations()
    source_keys = plan_source_keys(inventory)
    references = plan_references(inventory, source_keys)
    sources = plan_sources(
        inventory,
        references,
        source_keys=source_keys,
    )
    bindings = _bindings(inventory, source_keys, references)
    summary = PlanSummary(
        concept_count=len(inventory.concepts),
        source_candidate_count=len(sources),
        embedded_reference_count=inventory.concepts_with_reference,
        missing_reference_count=inventory.concepts_without_reference,
        reference_candidate_count=len(references.candidates),
        binding_count=len(bindings),
        conflict_count=len(references.conflicts),
        review_item_count=len(references.review_items),
        weak_suggestion_count=len(references.weak_suggestions),
    )
    invariants = _invariants(inventory, bindings, references, expectations)
    plan = MigrationPlan(
        input_snapshot=export.input_snapshot,
        summary=summary,
        source_candidates=sources,
        reference_candidates=references.candidates,
        concept_bindings=bindings,
        review_items=references.review_items,
        weak_reference_suggestions=references.weak_suggestions,
        conflicts=references.conflicts,
        coupled_collections=inventory.coupled_collections,
        invariants=invariants,
        generated_at=(generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc),
    )
    return plan.model_copy(update={"semantic_sha256": sha256_digest(semantic_plan_payload(plan))})


def validate_plan(
    plan: MigrationPlan,
    inventory: LegacyInventory,
    expectations: SnapshotExpectations,
) -> None:
    """Fail closed before dry-run output if any supplied-snapshot invariant failed."""
    issues = list(expectation_issues(inventory, expectations))
    if not plan.invariants.passed:
        failed = [
            name
            for name, value in plan.invariants.model_dump(mode="python").items()
            if isinstance(value, bool) and not value
        ]
        issues.append("Failed plan invariants: " + ", ".join(failed))
    if issues:
        raise PlanInvariantError(" ".join(issues))


def build_status(
    export: LoadedLegacyExport,
    *,
    expectations: SnapshotExpectations | None = None,
) -> StatusReport:
    """Return status without exposing full candidate or binding payloads."""
    inventory = build_inventory(export)
    expectations = expectations or SnapshotExpectations()
    plan = build_plan(export, expectations=expectations)
    issues = expectation_issues(inventory, expectations)
    return StatusReport(
        input_snapshot=export.input_snapshot,
        zip_safety=export.zip_safety,
        summary=plan.summary,
        coupled_collections=inventory.coupled_collections,
        ready_to_plan=not issues and plan.invariants.passed,
        issues=issues,
    )


__all__ = [
    "AUTHORITATIVE_EXPECTATIONS",
    "AUTHORITATIVE_SNAPSHOT_COUNTS",
    "PlanInvariantError",
    "SnapshotExpectations",
    "authoritative_expectations",
    "build_plan",
    "build_status",
    "expectation_issues",
    "semantic_plan_payload",
    "validate_plan",
]

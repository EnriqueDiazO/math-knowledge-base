"""Deterministic Source candidates derived only from exact concept.source strings."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

from mathmongo.source_catalog.normalization import clean_text
from mathmongo.source_catalog.normalization import normalize_source_name
from mathmongo.source_catalog_migration.canonical import candidate_key
from mathmongo.source_catalog_migration.inventory import LegacyInventory
from mathmongo.source_catalog_migration.locator import locator_statistics
from mathmongo.source_catalog_migration.models import ReviewStatus
from mathmongo.source_catalog_migration.models import SourceCandidate
from mathmongo.source_catalog_migration.reference_planner import ReferencePlanningResult


def source_candidate_key(exact_string: str) -> str:
    """Return a full namespaced digest without cleaning the legacy string."""
    return candidate_key("source_candidate", {"exact_string": exact_string})


def plan_source_keys(inventory: LegacyInventory) -> dict[str, str]:
    """Build exact-string candidate keys without grouping similar names."""
    return {exact: source_candidate_key(exact) for exact in sorted(inventory.source_counts)}


def plan_sources(
    inventory: LegacyInventory,
    references: ReferencePlanningResult,
    *,
    source_keys: Mapping[str, str] | None = None,
) -> tuple[SourceCandidate, ...]:
    """Create one Source candidate per exact string and attach read-only counts."""
    source_keys = dict(source_keys or plan_source_keys(inventory))
    normalized_groups: dict[str, list[str]] = defaultdict(list)
    for exact in sorted(inventory.source_counts):
        normalized_groups[normalize_source_name(exact)].append(exact)

    references_by_source: dict[str, set[str]] = defaultdict(set)
    locators_by_source: dict[str, list] = defaultdict(list)
    for observation in references.observations:
        references_by_source[observation.legacy_key.source].add(
            references.candidate_by_legacy_key[
                (observation.legacy_key.id, observation.legacy_key.source)
            ]
        )
        locators_by_source[observation.legacy_key.source].append(observation.locator)

    candidates: list[SourceCandidate] = []
    for exact in sorted(inventory.source_counts):
        normalized = normalize_source_name(exact)
        warnings: list[str] = []
        review_status = ReviewStatus.SAFE_EXACT
        if exact != clean_text(exact):
            warnings.append(
                "Exact legacy string contains outer or repeated whitespace and must be reviewed."
            )
            review_status = ReviewStatus.REVIEW_REQUIRED
        if not normalized:
            warnings.append("Exact legacy string is blank after comparison normalization.")
            review_status = ReviewStatus.REVIEW_REQUIRED
        collisions = [value for value in normalized_groups[normalized] if value != exact]
        if collisions:
            warnings.append(
                "Another exact Source string has the same normalized form; no candidates were merged."
            )
            review_status = ReviewStatus.REVIEW_REQUIRED
        with_reference, without_reference = inventory.source_reference_counts[exact]
        candidates.append(
            SourceCandidate(
                source_candidate_key=source_keys[exact],
                exact_string=exact,
                normalized_string=normalized,
                concept_count=inventory.source_counts[exact],
                concepts_with_reference=with_reference,
                concepts_without_reference=without_reference,
                reference_candidate_keys=tuple(sorted(references_by_source[exact])),
                locator_statistics=locator_statistics(locators_by_source[exact]),
                suggested_source_type="other",
                suggested_display_name=exact,
                legacy_source_strings=(exact,),
                warnings=tuple(warnings),
                review_status=review_status,
            )
        )
    return tuple(sorted(candidates, key=lambda item: item.source_candidate_key))


__all__ = ["plan_source_keys", "plan_sources", "source_candidate_key"]

"""Pure orchestration for safe multi-step Source Catalog UI writes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.service import CatalogResult
from mathmongo.source_catalog.service import CatalogResultStatus
from mathmongo.source_catalog.service import SourceCatalogService


@dataclass(frozen=True, slots=True)
class ReferenceSavePlan:
    """One selected create-or-associate action after Source creation."""

    label: str
    candidate: Reference | Mapping[str, Any] | None = None
    existing_reference_id: str | None = None
    allow_duplicate: bool = False

    def __post_init__(self) -> None:
        """Reject ambiguous create/associate plans before any write."""
        has_candidate = self.candidate is not None
        has_existing = bool(self.existing_reference_id)
        if has_candidate == has_existing:
            raise ValueError("Reference plan requires exactly one candidate or existing ID.")


@dataclass(frozen=True, slots=True)
class ReferenceSaveOutcome:
    """Typed result for one optional Reference action."""

    label: str
    action: str
    result: CatalogResult[Reference]


@dataclass(frozen=True, slots=True)
class AddSourceOutcome:
    """Safe partial outcome that never rolls back an already-created Source."""

    source_result: CatalogResult[Source]
    references: tuple[ReferenceSaveOutcome, ...] = ()

    @property
    def source_created(self) -> bool:
        """Return whether this workflow persisted the Source."""
        return self.source_result.persisted and self.source_result.value is not None

    @property
    def partial(self) -> bool:
        """Return whether Source persisted but at least one Reference did not."""
        return self.source_created and any(not item.result.persisted for item in self.references)


def duplicate_confirmation_required(matches: list[DuplicateMatch]) -> bool:
    """Require confirmation for exact/strong/possible, never weak-only warnings."""
    return any(
        match.classification
        in {
            DuplicateClassification.EXACT,
            DuplicateClassification.STRONG,
            DuplicateClassification.POSSIBLE,
        }
        for match in matches
    )


def allow_source_creation(
    matches: list[DuplicateMatch],
    *,
    confirmed: bool,
) -> bool:
    """Allow weak-only candidates automatically and stronger evidence explicitly."""
    return confirmed or not duplicate_confirmation_required(matches)


def execute_add_source(
    service: SourceCatalogService,
    source: Source | Mapping[str, Any],
    reference_plans: list[ReferenceSavePlan] | tuple[ReferenceSavePlan, ...] = (),
    *,
    allow_duplicate_source: bool = False,
) -> AddSourceOutcome:
    """Create Source first, then selected References without destructive rollback."""
    source_result = service.create_source(source, allow_duplicate=allow_duplicate_source)
    if not source_result.persisted or source_result.value is None:
        return AddSourceOutcome(source_result=source_result)

    outcomes = execute_reference_plans(
        service,
        source_result.value.source_id,
        reference_plans,
    )
    return AddSourceOutcome(source_result=source_result, references=outcomes)


def execute_reference_plans(
    service: SourceCatalogService,
    source_id: str,
    reference_plans: list[ReferenceSavePlan] | tuple[ReferenceSavePlan, ...],
) -> tuple[ReferenceSaveOutcome, ...]:
    """Execute selected create/associate actions for one existing Source."""
    outcomes: list[ReferenceSaveOutcome] = []
    for plan in reference_plans:
        if plan.existing_reference_id:
            result = service.associate_reference(plan.existing_reference_id, source_id)
            outcomes.append(ReferenceSaveOutcome(plan.label, "associate", result))
            continue

        candidate = (
            plan.candidate
            if isinstance(plan.candidate, Reference)
            else Reference.model_validate(plan.candidate)
        )
        data = candidate.model_dump(mode="python")
        data["source_ids"] = list(dict.fromkeys([*candidate.source_ids, source_id]))
        result = service.create_reference(
            data,
            allow_duplicate=plan.allow_duplicate,
            import_context="add-source",
        )
        outcomes.append(ReferenceSaveOutcome(plan.label, "create", result))

    return tuple(outcomes)


def outcome_status(outcome: AddSourceOutcome) -> CatalogResultStatus:
    """Summarize a multi-step outcome without hiding partial failures."""
    if not outcome.source_created:
        return outcome.source_result.status
    if outcome.partial:
        return CatalogResultStatus.WARNING
    if any(item.result.status == CatalogResultStatus.WARNING for item in outcome.references):
        return CatalogResultStatus.WARNING
    return CatalogResultStatus.SUCCESS


__all__ = [
    "AddSourceOutcome",
    "ReferenceSaveOutcome",
    "ReferenceSavePlan",
    "allow_source_creation",
    "duplicate_confirmation_required",
    "execute_add_source",
    "execute_reference_plans",
    "outcome_status",
]

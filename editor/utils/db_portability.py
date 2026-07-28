"""Structured, reusable database portability diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from typing import Literal

LegacyConceptIssueCause = Literal["absent", "ambiguous"]


@dataclass(frozen=True, slots=True)
class PortabilityIssue:
    """One exact legacy-Concept portability failure."""

    collection: str
    evidence_link_id: str
    concept_legacy_id: str
    concept_legacy_source: str
    cause: LegacyConceptIssueCause
    matching_concepts: int

    @property
    def legacy_identity(self) -> tuple[str, str]:
        """Return the exact legacy Concept identity tuple."""
        return (self.concept_legacy_id, self.concept_legacy_source)


class PortabilityValidationError(ValueError):
    """Strict validation error retaining every structured portability issue."""

    def __init__(self, issues: Iterable[PortabilityIssue], *, context: str) -> None:
        """Build a ValueError without discarding its structured issues."""
        self.issues = tuple(issues)
        if not self.issues:
            raise ValueError("PortabilityValidationError requires at least one issue")
        first = self.issues[0]
        suffix = "" if len(self.issues) == 1 else f"; {len(self.issues)} issues found"
        super().__init__(
            "Concept Evidence Link points to a legacy Concept "
            f"{first.cause} in {context} "
            f"({first.matching_concepts} matching Concepts){suffix}"
        )


def _field(document: Mapping[str, Any] | Any, name: str) -> Any:
    if isinstance(document, Mapping):
        return document.get(name)
    return getattr(document, name, None)


def legacy_concept_portability_issues(
    evidence_links: Iterable[Mapping[str, Any] | Any],
    *,
    count_matching_concepts: Callable[[str, str], int],
) -> tuple[PortabilityIssue, ...]:
    """Return absent/ambiguous legacy-Concept identities without mutating data."""
    issues: list[PortabilityIssue] = []
    for link in evidence_links:
        evidence_link_id = _field(link, "evidence_link_id")
        concept_legacy_id = _field(link, "concept_legacy_id")
        concept_legacy_source = _field(link, "concept_legacy_source")
        if not all(
            isinstance(value, str) and value
            for value in (
                evidence_link_id,
                concept_legacy_id,
                concept_legacy_source,
            )
        ):
            # Model/schema validation owns malformed records. This validator
            # diagnoses only fully specified legacy identities.
            continue
        matching_concepts = int(
            count_matching_concepts(concept_legacy_id, concept_legacy_source)
        )
        if matching_concepts < 0:
            raise ValueError("Legacy Concept match count cannot be negative")
        if matching_concepts == 1:
            continue
        issues.append(
            PortabilityIssue(
                collection="concept_evidence_links",
                evidence_link_id=evidence_link_id,
                concept_legacy_id=concept_legacy_id,
                concept_legacy_source=concept_legacy_source,
                cause="absent" if matching_concepts == 0 else "ambiguous",
                matching_concepts=matching_concepts,
            )
        )
    return tuple(issues)


__all__ = [
    "LegacyConceptIssueCause",
    "PortabilityIssue",
    "PortabilityValidationError",
    "legacy_concept_portability_issues",
]

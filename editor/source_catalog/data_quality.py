"""Bounded, Source-local quality diagnostics composed from S1A services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import safe_error_message
from mathmongo.source_catalog.duplicates import DuplicateEvidenceType
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.legacy_repository import LegacyConceptRepository
from mathmongo.source_catalog.models import ReferenceStatus
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.quality import incomplete_reference_fields

QUALITY_REFERENCE_LIMIT = 100


@dataclass(frozen=True, slots=True)
class SourceQualitySummary:
    """Basic, bounded quality indicators for one selected Source."""

    reference_count: int
    source_duplicates: tuple[DuplicateMatch, ...]
    incomplete_reference_ids: tuple[str, ...]
    repeated_doi_reference_ids: tuple[str, ...]
    repeated_isbn_reference_ids: tuple[str, ...]
    repeated_citekey_reference_ids: tuple[str, ...]
    archived_associated_reference_ids: tuple[str, ...]
    shared_reference_ids: tuple[str, ...]
    legacy_concept_count: int
    legacy_without_reference_count: int
    exact_name_not_declared_count: int
    reference_scan_truncated: bool


def _source_name_only(source: Source) -> Source:
    data = source.model_dump(mode="python")
    data["legacy"] = {"source_strings": [], "migration_batch_id": None}
    return Source.model_validate(data)


def _duplicate_evidence_ids(
    matches: list[DuplicateMatch],
    evidence_type: DuplicateEvidenceType,
) -> set[str]:
    return {
        match.entity_id
        for match in matches
        if any(item.evidence_type == evidence_type for item in match.evidence)
    }


def inspect_source_quality(
    context: CatalogUIContext,
    source: Source,
) -> SourceQualitySummary:
    """Compute diagnostics through repositories/services with a hard reference limit."""
    page = context.reference_repository.list_quality_candidates(
        source_id=source.source_id,
        page_size=QUALITY_REFERENCE_LIMIT,
    )
    reference_count = page.total
    source_duplicates = tuple(
        context.service.detect_source_duplicates(
            source,
            exclude_source_id=source.source_id,
        )
    )
    incomplete: list[str] = []
    repeated_doi: set[str] = set()
    repeated_isbn: set[str] = set()
    repeated_key: set[str] = set()
    archived: list[str] = []
    shared: list[str] = []
    for reference in page.items:
        if incomplete_reference_fields(reference):
            incomplete.append(reference.reference_id)
        if reference.status == ReferenceStatus.ARCHIVED:
            archived.append(reference.reference_id)
        if len(reference.source_ids) > 1:
            shared.append(reference.reference_id)
        matches = context.service.detect_reference_duplicates(
            reference,
            exclude_reference_id=reference.reference_id,
        )
        if _duplicate_evidence_ids(matches, DuplicateEvidenceType.DOI):
            repeated_doi.add(reference.reference_id)
        if _duplicate_evidence_ids(matches, DuplicateEvidenceType.ISBN):
            repeated_isbn.add(reference.reference_id)
        if _duplicate_evidence_ids(matches, DuplicateEvidenceType.BIBTEX_KEY):
            repeated_key.add(reference.reference_id)

    legacy = LegacyConceptRepository(context.database)
    legacy_count = legacy.count(source)
    legacy_without_reference = legacy.count(source, has_reference=False)
    exact_name_not_declared = 0
    if source.name not in source.legacy.source_strings:
        exact_name_not_declared = legacy.count(_source_name_only(source))

    return SourceQualitySummary(
        reference_count=reference_count,
        source_duplicates=source_duplicates,
        incomplete_reference_ids=tuple(incomplete),
        repeated_doi_reference_ids=tuple(sorted(repeated_doi)),
        repeated_isbn_reference_ids=tuple(sorted(repeated_isbn)),
        repeated_citekey_reference_ids=tuple(sorted(repeated_key)),
        archived_associated_reference_ids=tuple(archived),
        shared_reference_ids=tuple(shared),
        legacy_concept_count=legacy_count,
        legacy_without_reference_count=legacy_without_reference,
        exact_name_not_declared_count=exact_name_not_declared,
        reference_scan_truncated=reference_count > len(page.items),
    )


def render_data_quality(ui: Any, context: CatalogUIContext, source: Source) -> None:
    """Render bounded diagnostics without global analytics or writes."""
    ui.subheader("Data Quality")
    try:
        summary = inspect_source_quality(context, source)
    except Exception as exc:
        ui.error(f"Database error reading quality indicators: {safe_error_message(exc)}")
        return
    columns = ui.columns(4)
    columns[0].metric("References", summary.reference_count)
    columns[1].metric("Legacy concepts", summary.legacy_concept_count)
    columns[2].metric("Incomplete references", len(summary.incomplete_reference_ids))
    columns[3].metric("Possible Source duplicates", len(summary.source_duplicates))
    ui.write(
        {
            "source_without_references": summary.reference_count == 0,
            "repeated_doi": len(summary.repeated_doi_reference_ids),
            "repeated_isbn": len(summary.repeated_isbn_reference_ids),
            "repeated_citekey": len(summary.repeated_citekey_reference_ids),
            "archived_still_associated": len(summary.archived_associated_reference_ids),
            "shared_references": len(summary.shared_reference_ids),
            "legacy_without_reference": summary.legacy_without_reference_count,
            "exact_name_not_in_legacy_strings": summary.exact_name_not_declared_count,
        }
    )
    ui.write(
        {
            "source_duplicate_ids": [match.entity_id for match in summary.source_duplicates],
            "incomplete_reference_ids": summary.incomplete_reference_ids,
            "repeated_doi_reference_ids": summary.repeated_doi_reference_ids,
            "repeated_isbn_reference_ids": summary.repeated_isbn_reference_ids,
            "repeated_citekey_reference_ids": summary.repeated_citekey_reference_ids,
            "archived_associated_reference_ids": (summary.archived_associated_reference_ids),
        }
    )
    if summary.reference_scan_truncated:
        ui.warning(
            f"Los diagnósticos de detalle están limitados a {QUALITY_REFERENCE_LIMIT} References; "
            "el conteo total sigue siendo server-side."
        )


__all__ = [
    "QUALITY_REFERENCE_LIMIT",
    "SourceQualitySummary",
    "incomplete_reference_fields",
    "inspect_source_quality",
    "render_data_quality",
]

"""Typed, non-persisting Source Catalog quality diagnostics."""

from __future__ import annotations

from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import ReferenceType


def incomplete_reference_fields(reference: Reference) -> tuple[str, ...]:
    """Return non-blocking, type-aware bibliographic completeness warnings."""
    if reference.reference_type == ReferenceType.BOOK:
        expected = {
            "authors": bool(reference.authors),
            "title": bool(reference.title),
            "year": reference.year is not None or bool(reference.year_raw),
            "publisher": bool(reference.publisher),
        }
    elif reference.reference_type == ReferenceType.ARTICLE:
        expected = {
            "authors": bool(reference.authors),
            "title": bool(reference.title),
            "year": reference.year is not None or bool(reference.year_raw),
            "journal": bool(reference.journal),
        }
    elif reference.reference_type == ReferenceType.WEB:
        expected = {
            "title": bool(reference.title),
            "url": bool(reference.url),
            "accessed_at": reference.accessed_at is not None,
        }
    else:
        expected = {"title": bool(reference.title)}
    return tuple(field_name for field_name, populated in expected.items() if not populated)


__all__ = ["incomplete_reference_fields"]

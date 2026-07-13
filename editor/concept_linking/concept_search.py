"""Bounded projected read-only search for legacy concept metadata."""

from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any

from editor.concept_linking.view_models import ConceptSummary
from editor.reading_annotations.concept_picker import MAX_CONCEPT_PAGE
from editor.reading_annotations.concept_picker import MAX_CONCEPT_QUERY_LENGTH
from editor.reading_annotations.concept_picker import legacy_identity_text

MAX_QUERY_LENGTH = MAX_CONCEPT_QUERY_LENGTH
MAX_PAGE = MAX_CONCEPT_PAGE
MAX_PAGE_SIZE = 24
MAX_BATCH_SIZE = 100
DEFAULT_PAGE_SIZE = 12
CONCEPT_PROJECTION = {
    "_id": 0,
    "id": 1,
    "source": 1,
    "titulo": 1,
    "title": 1,
    "nombre": 1,
    "name": 1,
    "tipo": 1,
    "type": 1,
    "categorias": 1,
    "categories": 1,
    "tags": 1,
}
_SEARCH_FIELDS = (
    "id",
    "source",
    "titulo",
    "title",
    "nombre",
    "name",
    "tipo",
    "type",
    "categorias",
    "categories",
    "tags",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _values(*values: object) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = (value,)
        else:
            try:
                candidates = tuple(value)  # type: ignore[arg-type]
            except TypeError:
                candidates = (value,)
        for candidate in candidates:
            text = _text(candidate)
            folded = text.casefold()
            if text and folded not in seen:
                seen.add(folded)
                result.append(text)
    return tuple(result)


def concept_from_document(document: Mapping[str, Any]) -> ConceptSummary | None:
    """Build a safe card summary from a projected legacy document."""
    concept_id = legacy_identity_text(document.get("id"))
    concept_source = legacy_identity_text(document.get("source"))
    if concept_id is None or concept_source is None:
        return None
    title = _text(
        document.get("titulo")
        or document.get("title")
        or document.get("nombre")
        or document.get("name")
    )
    return ConceptSummary(
        concept_id=concept_id,
        concept_source=concept_source,
        title=title,
        concept_type=_text(document.get("tipo") or document.get("type")),
        categories=_values(document.get("categorias"), document.get("categories")),
        tags=_values(document.get("tags")),
    )


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= MAX_PAGE:
        raise ValueError(f"page must be between 1 and {MAX_PAGE}")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ValueError("page_size must be a positive integer")
    return page, min(page_size, MAX_PAGE_SIZE)


def search_concepts(
    database: Any,
    query: str,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[ConceptSummary, ...]:
    """Search all safe metadata fields using escaped regex and server-side bounds."""
    if database is None or not hasattr(database, "__getitem__"):
        raise ValueError("An explicit database is required")
    page, page_size = _pagination(page, page_size)
    value = _text(query)
    if not value:
        return ()
    if len(value) > MAX_QUERY_LENGTH:
        raise ValueError(f"La búsqueda no puede exceder {MAX_QUERY_LENGTH} caracteres")
    pattern = {"$regex": re.escape(value), "$options": "i"}
    selector = {"$or": [{field: pattern} for field in _SEARCH_FIELDS]}
    cursor = database["concepts"].find(selector, dict(CONCEPT_PROJECTION))
    if hasattr(cursor, "sort"):
        cursor = cursor.sort([("source", 1), ("id", 1)])
    if hasattr(cursor, "skip"):
        cursor = cursor.skip((page - 1) * page_size)
    if hasattr(cursor, "limit"):
        cursor = cursor.limit(page_size)
    items: list[ConceptSummary] = []
    for raw in cursor:
        if isinstance(raw, Mapping) and (item := concept_from_document(raw)) is not None:
            items.append(item)
        if len(items) >= page_size:
            break
    return tuple(items)


def get_concept(database: Any, concept_id: str, concept_source: str) -> ConceptSummary | None:
    """Resolve one exact composite identity with the same safe projection."""
    if database is None or not hasattr(database, "__getitem__"):
        raise ValueError("An explicit database is required")
    raw = database["concepts"].find_one(
        {"id": concept_id, "source": concept_source},
        dict(CONCEPT_PROJECTION),
    )
    if not isinstance(raw, Mapping):
        return None
    item = concept_from_document(raw)
    if item is None or item.identity != (concept_id, concept_source):
        return None
    return item


def get_concepts(
    database: Any,
    identities: Iterable[tuple[str, str]],
    *,
    limit: int = MAX_PAGE_SIZE,
) -> tuple[ConceptSummary, ...]:
    """Resolve a bounded ordered identity set without a collection scan."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    limit = min(limit, MAX_BATCH_SIZE)
    ordered = tuple(dict.fromkeys(identities))[:limit]
    if not ordered:
        return ()
    selector = {
        "$or": [
            {"id": concept_id, "source": concept_source} for concept_id, concept_source in ordered
        ]
    }
    cursor = database["concepts"].find(selector, dict(CONCEPT_PROJECTION))
    if hasattr(cursor, "limit"):
        cursor = cursor.limit(limit)
    found: dict[tuple[str, str], ConceptSummary] = {}
    for raw in cursor:
        if isinstance(raw, Mapping) and (item := concept_from_document(raw)) is not None:
            found[item.identity] = item
        if len(found) >= limit:
            break
    return tuple(found[identity] for identity in ordered if identity in found)


def with_evidence_counts(
    concepts: Iterable[ConceptSummary], evidence_repository: Any
) -> tuple[ConceptSummary, ...]:
    """Attach optional bounded counts through the existing read-only repository."""
    from dataclasses import replace

    result: list[ConceptSummary] = []
    for concept in tuple(concepts)[:MAX_PAGE_SIZE]:
        try:
            count = int(
                evidence_repository.count_by_concept(
                    concept.concept_id,
                    concept.concept_source,
                    status=None,
                )
            )
        except Exception:
            count = None
        result.append(replace(concept, evidence_count=count))
    return tuple(result)


__all__ = [
    "CONCEPT_PROJECTION",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE",
    "MAX_PAGE_SIZE",
    "MAX_BATCH_SIZE",
    "MAX_QUERY_LENGTH",
    "concept_from_document",
    "get_concept",
    "get_concepts",
    "search_concepts",
    "with_evidence_counts",
]

"""Read-only projected access to exact legacy concept identities."""

# ruff: noqa: D101

from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from editor.concept_linking.concept_search import CONCEPT_PROJECTION
from editor.concept_linking.concept_search import concept_from_document
from editor.concept_linking.view_models import ConceptSummary

MAX_CONCEPT_QUERY_LENGTH = 160
MAX_CONCEPT_SEARCH_LIMIT = 50
DEFAULT_CONCEPT_SEARCH_LIMIT = 20
MAX_CONCEPT_SEARCH_PAGE = 100_000
SEARCH_FIELDS = (
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


@dataclass(frozen=True, slots=True)
class ConceptSearchPage:
    items: tuple[ConceptSummary, ...]
    page: int
    page_size: int
    has_more: bool


def _bounded_text(value: str | None, *, maximum: int, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError("concept query is required")
        return None
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("concept query is invalid")
    text = value.strip()
    if required and not text:
        raise ValueError("concept query cannot be empty")
    if len(text) > maximum:
        raise ValueError(f"concept query cannot exceed {maximum} characters")
    return text or None


def search_legacy_concepts(
    database: Any,
    query: str,
    *,
    source: str | None = None,
    concept_type: str | None = None,
    category: str | None = None,
    page: int = 1,
    limit: int = DEFAULT_CONCEPT_SEARCH_LIMIT,
) -> ConceptSearchPage:
    """Search approved metadata only, with an escaped regex and stable order."""
    if database is None or not hasattr(database, "__getitem__"):
        raise ValueError("an explicit database is required")
    if (
        isinstance(page, bool)
        or not isinstance(page, int)
        or not 1 <= page <= MAX_CONCEPT_SEARCH_PAGE
    ):
        raise ValueError("page is invalid")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_CONCEPT_SEARCH_LIMIT
    ):
        raise ValueError(f"limit must be between 1 and {MAX_CONCEPT_SEARCH_LIMIT}")
    value = _bounded_text(query, maximum=MAX_CONCEPT_QUERY_LENGTH, required=True)
    source_value = _bounded_text(source, maximum=1_000)
    type_value = _bounded_text(concept_type, maximum=160)
    category_value = _bounded_text(category, maximum=160)
    pattern = {"$regex": re.escape(value or ""), "$options": "i"}
    clauses: list[dict[str, Any]] = [{"$or": [{field: pattern} for field in SEARCH_FIELDS]}]
    if source_value is not None:
        clauses.append({"source": source_value})
    if type_value is not None:
        clauses.append({"$or": [{"tipo": type_value}, {"type": type_value}]})
    if category_value is not None:
        clauses.append({"$or": [{"categorias": category_value}, {"categories": category_value}]})
    selector: dict[str, Any] = clauses[0] if len(clauses) == 1 else {"$and": clauses}
    cursor = database["concepts"].find(selector, dict(CONCEPT_PROJECTION))
    if hasattr(cursor, "sort"):
        cursor = cursor.sort([("source", 1), ("id", 1)])
    if hasattr(cursor, "skip"):
        cursor = cursor.skip((page - 1) * limit)
    if hasattr(cursor, "limit"):
        cursor = cursor.limit(limit + 1)
    items: list[ConceptSummary] = []
    seen: set[tuple[str, str]] = set()
    for raw in cursor:
        item = concept_from_document(raw) if isinstance(raw, Mapping) else None
        if item is None or item.identity in seen:
            continue
        seen.add(item.identity)
        items.append(item)
        if len(items) > limit:
            break
    return ConceptSearchPage(tuple(items[:limit]), page, limit, len(items) > limit)


def get_legacy_concept(
    database: Any,
    concept_id: str,
    concept_source: str,
) -> ConceptSummary | None:
    """Resolve one opaque composite identity without normalization."""
    if database is None or not hasattr(database, "__getitem__"):
        raise ValueError("an explicit database is required")
    if not isinstance(concept_id, str) or not concept_id.strip() or len(concept_id) > 500:
        raise ValueError("concept_id is invalid")
    if (
        not isinstance(concept_source, str)
        or not concept_source.strip()
        or len(concept_source) > 1_000
    ):
        raise ValueError("concept_source is invalid")
    raw = database["concepts"].find_one(
        {"id": concept_id, "source": concept_source},
        dict(CONCEPT_PROJECTION),
    )
    item = concept_from_document(raw) if isinstance(raw, Mapping) else None
    return item if item is not None and item.identity == (concept_id, concept_source) else None


def get_legacy_concepts(
    database: Any,
    identities: Iterable[tuple[str, str]],
    *,
    limit: int = 100,
) -> dict[tuple[str, str], ConceptSummary]:
    """Resolve a bounded identity set in one projected query."""
    ordered = tuple(dict.fromkeys(identities))[: max(1, min(limit, 100))]
    if not ordered:
        return {}
    cursor = database["concepts"].find(
        {"$or": [{"id": item[0], "source": item[1]} for item in ordered]},
        dict(CONCEPT_PROJECTION),
    )
    if hasattr(cursor, "limit"):
        cursor = cursor.limit(len(ordered))
    found: dict[tuple[str, str], ConceptSummary] = {}
    for raw in cursor:
        item = concept_from_document(raw) if isinstance(raw, Mapping) else None
        if item is not None and item.identity in ordered:
            found.setdefault(item.identity, item)
    return found


__all__ = [
    "ConceptSearchPage",
    "DEFAULT_CONCEPT_SEARCH_LIMIT",
    "MAX_CONCEPT_QUERY_LENGTH",
    "MAX_CONCEPT_SEARCH_LIMIT",
    "get_legacy_concept",
    "get_legacy_concepts",
    "search_legacy_concepts",
]

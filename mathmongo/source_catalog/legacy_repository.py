"""Bounded, read-only access to legacy concepts associated with a Source."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mathmongo.source_catalog.models import Source

MAX_LEGACY_PAGE_SIZE = 100
MAX_LEGACY_SEARCH_LENGTH = 200

_LEGACY_PROJECTION = {
    "_id": 0,
    "id": 1,
    "titulo": 1,
    "tipo": 1,
    "categorias": 1,
    "referencia.paginas": 1,
    "referencia.pages": 1,
    "referencia.pagina": 1,
    "referencia.capitulo": 1,
    "referencia.chapter": 1,
    "referencia.seccion": 1,
    "referencia.section": 1,
    "referencia.tipo_referencia": 1,
    "referencia.fuente": 1,
    "ultima_actualizacion": 1,
    "source": 1,
}
_LEGACY_SORT = [
    ("ultima_actualizacion", -1),
    ("source", 1),
    ("id", 1),
]


@dataclass(frozen=True, slots=True)
class LegacyConceptSummary:
    """Projected, presentation-safe metadata for one legacy concept."""

    id: str
    title: str
    type: str
    categories: tuple[str, ...]
    has_reference: bool
    pages: str | None
    chapter: str | None
    section: str | None
    updated_at: datetime | None
    source: str


@dataclass(frozen=True, slots=True)
class LegacyConceptPage:
    """One bounded page and its server-side total."""

    items: tuple[LegacyConceptSummary, ...]
    page: int
    page_size: int
    total: int
    exact_source_values: tuple[str, ...]

    @property
    def pages(self) -> int:
        """Return the number of non-empty pages represented by the total."""
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


def legacy_source_values(source: Source | Mapping[str, Any]) -> tuple[str, ...]:
    """Return Source.name plus exact legacy strings, preserving value and order."""
    model = source if isinstance(source, Source) else Source.model_validate(source)
    return tuple(dict.fromkeys((model.name, *model.legacy.source_strings)))


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ValueError("page_size must be a positive integer")
    return page, min(page_size, MAX_LEGACY_PAGE_SIZE)


def _search_pattern(search: str | None) -> str | None:
    if search is None:
        return None
    if not isinstance(search, str):
        raise TypeError("search must be text")
    value = search.strip()
    if not value:
        return None
    if len(value) > MAX_LEGACY_SEARCH_LENGTH:
        raise ValueError(f"search cannot exceed {MAX_LEGACY_SEARCH_LENGTH} characters")
    return re.escape(value)


def _query(
    source: Source | Mapping[str, Any],
    *,
    concept_type: str | None,
    has_reference: bool | None,
    search: str | None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    if has_reference is not None and not isinstance(has_reference, bool):
        raise TypeError("has_reference must be bool or None")

    exact_values = legacy_source_values(source)
    clauses: list[dict[str, Any]] = [{"source": {"$in": list(exact_values)}}]

    type_value = str(concept_type).strip() if concept_type is not None else ""
    if type_value:
        clauses.append({"tipo": type_value})

    if has_reference is True:
        clauses.append({"referencia": {"$exists": True, "$nin": [None, {}]}})
    elif has_reference is False:
        clauses.append(
            {
                "$or": [
                    {"referencia": {"$exists": False}},
                    {"referencia": None},
                    {"referencia": {}},
                ]
            }
        )

    escaped = _search_pattern(search)
    if escaped is not None:
        regex = {"$regex": escaped, "$options": "i"}
        clauses.append(
            {
                "$or": [
                    {"id": regex},
                    {"titulo": regex},
                    {"tipo": regex},
                    {"categorias": regex},
                ]
            }
        )

    query = clauses[0] if len(clauses) == 1 else {"$and": clauses}
    return query, exact_values


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _summary(document: Mapping[str, Any]) -> LegacyConceptSummary:
    raw_categories = document.get("categorias")
    if raw_categories is None:
        categories: tuple[str, ...] = ()
    elif isinstance(raw_categories, str):
        categories = (raw_categories,)
    else:
        try:
            categories = tuple(str(value) for value in raw_categories)
        except TypeError:
            categories = (str(raw_categories),)

    raw_reference = document.get("referencia")
    reference = raw_reference if isinstance(raw_reference, Mapping) else {}
    updated_at = document.get("ultima_actualizacion")
    return LegacyConceptSummary(
        id=_text(document.get("id")),
        title=_text(document.get("titulo")),
        type=_text(document.get("tipo")),
        categories=categories,
        has_reference=bool(raw_reference),
        pages=_optional_text(
            reference.get("paginas", reference.get("pages", reference.get("pagina")))
        ),
        chapter=_optional_text(reference.get("capitulo", reference.get("chapter"))),
        section=_optional_text(reference.get("seccion", reference.get("section"))),
        updated_at=updated_at if isinstance(updated_at, datetime) else None,
        source=_text(document.get("source")),
    )


class LegacyConceptRepository:
    """Read legacy concept projections from one explicitly supplied database."""

    COLLECTION = "concepts"

    def __init__(self, database: Any) -> None:
        """Retain an explicit database without touching any collection."""
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("LegacyConceptRepository requires an explicit MongoDB database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def count(
        self,
        source: Source | Mapping[str, Any],
        *,
        concept_type: str | None = None,
        has_reference: bool | None = None,
        search: str | None = None,
    ) -> int:
        """Count exact legacy matches with optional bounded filters."""
        query, _exact_values = _query(
            source,
            concept_type=concept_type,
            has_reference=has_reference,
            search=search,
        )
        return int(self._collection.count_documents(query))

    def list(
        self,
        source: Source | Mapping[str, Any],
        *,
        page: int = 1,
        page_size: int = 25,
        concept_type: str | None = None,
        has_reference: bool | None = None,
        search: str | None = None,
    ) -> LegacyConceptPage:
        """Return a projected, stably sorted server-side page of exact matches."""
        page, page_size = _pagination(page, page_size)
        query, exact_values = _query(
            source,
            concept_type=concept_type,
            has_reference=has_reference,
            search=search,
        )
        total = int(self._collection.count_documents(query))
        cursor = (
            self._collection.find(query, dict(_LEGACY_PROJECTION))
            .sort(list(_LEGACY_SORT))
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return LegacyConceptPage(
            items=tuple(_summary(document) for document in cursor),
            page=page,
            page_size=page_size,
            total=total,
            exact_source_values=exact_values,
        )

    def list_types(self, source: Source | Mapping[str, Any]) -> tuple[str, ...]:
        """Return distinct non-empty concept types for the exact Source values."""
        query, _exact_values = _query(
            source,
            concept_type=None,
            has_reference=None,
            search=None,
        )
        values = self._collection.distinct("tipo", query)
        return tuple(sorted({str(value) for value in values if str(value).strip()}))


__all__ = [
    "LegacyConceptPage",
    "LegacyConceptRepository",
    "LegacyConceptSummary",
    "MAX_LEGACY_PAGE_SIZE",
    "MAX_LEGACY_SEARCH_LENGTH",
    "legacy_source_values",
]

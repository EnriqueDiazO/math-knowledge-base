"""Bounded, projected picker for read-only legacy concept identities."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from editor.reading_annotations.state import select_concept
from editor.reading_annotations.state import state_key
from editor.source_catalog.shared import safe_error_message

MAX_CONCEPT_QUERY_LENGTH = 120
MAX_CONCEPT_CHOICES = 50
MAX_CONCEPT_PAGE = 10_000
_IDENTITY_SEPARATOR = "\x1f"
_PROJECTION = {
    "_id": 0,
    "id": 1,
    "source": 1,
    "titulo": 1,
    "title": 1,
    "nombre": 1,
    "name": 1,
    "tipo": 1,
    "categorias": 1,
    "tags": 1,
}


@dataclass(frozen=True, slots=True)
class LegacyConceptChoice:
    """Presentation-safe metadata for a legacy concept composite identity."""

    concept_id: str
    concept_source: str
    title: str
    category: str
    tags: tuple[str, ...]

    @property
    def identity(self) -> str:
        """Return a session-safe encoding of the composite legacy identity."""
        return f"{self.concept_id}{_IDENTITY_SEPARATOR}{self.concept_source}"

    @property
    def label(self) -> str:
        """Return a compact human-readable selector label."""
        title = f" · {self.title}" if self.title else ""
        category = f" · {self.category}" if self.category else ""
        return f"{_text(self.concept_id)} [{_text(self.concept_source)}]{title}{category}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    else:
        try:
            values = tuple(value)
        except TypeError:
            values = (value,)
    return tuple(dict.fromkeys(text for item in values if (text := _text(item))))


def _identity_text(value: Any) -> str | None:
    """Preserve an exact legacy string while rejecting unusable identities."""
    if value is None:
        return None
    text = str(value)
    if not text.strip() or _IDENTITY_SEPARATOR in text:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        return None
    return text


def _choice(document: Mapping[str, Any]) -> LegacyConceptChoice | None:
    concept_id = _identity_text(document.get("id"))
    source = _identity_text(document.get("source"))
    if concept_id is None or source is None:
        return None
    return LegacyConceptChoice(
        concept_id=concept_id,
        concept_source=source,
        title=_text(
            document.get("titulo")
            or document.get("title")
            or document.get("nombre")
            or document.get("name")
        ),
        category=_text(document.get("tipo")),
        tags=_values(document.get("categorias") or document.get("tags")),
    )


def find_legacy_concepts(
    database: Any,
    *,
    search: str | None = None,
    legacy_source: str | None = None,
    page: int = 1,
    limit: int = 25,
) -> tuple[LegacyConceptChoice, ...]:
    """Search projected metadata only with escaped regex and a hard result bound."""
    if database is None or not hasattr(database, "__getitem__"):
        raise ValueError("An explicit database is required")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1 or page > MAX_CONCEPT_PAGE:
        raise ValueError(f"page must be between 1 and {MAX_CONCEPT_PAGE}")
    limit = min(limit, MAX_CONCEPT_CHOICES)
    search_value = _text(search)
    source_value = _text(legacy_source)
    if len(search_value) > MAX_CONCEPT_QUERY_LENGTH:
        raise ValueError(f"Concept search cannot exceed {MAX_CONCEPT_QUERY_LENGTH} characters")
    if len(source_value) > MAX_CONCEPT_QUERY_LENGTH:
        raise ValueError(
            f"Legacy source filter cannot exceed {MAX_CONCEPT_QUERY_LENGTH} characters"
        )
    clauses: list[dict[str, Any]] = []
    if search_value:
        pattern = {"$regex": re.escape(search_value), "$options": "i"}
        clauses.append(
            {
                "$or": [
                    {"id": pattern},
                    {"titulo": pattern},
                    {"title": pattern},
                    {"nombre": pattern},
                    {"name": pattern},
                ]
            }
        )
    if source_value:
        clauses.append({"source": {"$regex": re.escape(source_value), "$options": "i"}})
    query: dict[str, Any]
    if not clauses:
        query = {}
    elif len(clauses) == 1:
        query = clauses[0]
    else:
        query = {"$and": clauses}
    cursor = database["concepts"].find(query, dict(_PROJECTION))
    if hasattr(cursor, "sort"):
        cursor = cursor.sort([("source", 1), ("id", 1)])
    if hasattr(cursor, "skip"):
        cursor = cursor.skip((page - 1) * limit)
    if hasattr(cursor, "limit"):
        cursor = cursor.limit(limit)
    choices: list[LegacyConceptChoice] = []
    for document in cursor:
        if isinstance(document, Mapping) and (item := _choice(document)) is not None:
            choices.append(item)
        if len(choices) >= limit:
            break
    return tuple(choices)


def render_concept_picker(
    ui: Any,
    database: Any,
    *,
    subject_key: str,
) -> LegacyConceptChoice | None:
    """Render concept search without retaining query results or DB handles in session."""
    search = ui.text_input(
        "Concept id or title",
        key=state_key("concept_search", subject_key),
    )
    legacy_source = ui.text_input(
        "Legacy concept source",
        key=state_key("concept_source", subject_key),
    )
    page = int(
        ui.number_input(
            "Concept results page",
            min_value=1,
            max_value=MAX_CONCEPT_PAGE,
            value=1,
            step=1,
            key=state_key("concept_page", subject_key),
            width="stretch",
        )
    )
    try:
        choices = find_legacy_concepts(
            database,
            search=search,
            legacy_source=legacy_source,
            page=page,
        )
    except Exception as exc:
        ui.error(f"Could not search concepts: {safe_error_message(exc)}")
        return None
    labels = {item.identity: item.label for item in choices}
    identity = ui.selectbox(
        "Legacy concept",
        options=("", *labels),
        format_func=lambda value: "Select a concept" if not value else labels.get(value, value),
        key=state_key("concept_choice", subject_key),
    )
    selected = next((item for item in choices if item.identity == identity), None)
    if selected is None:
        select_concept(ui.session_state, None, None)
        if not choices:
            ui.caption("No matching legacy concepts.")
        return None
    select_concept(
        ui.session_state,
        selected.concept_id,
        selected.concept_source,
    )
    ui.write(
        {
            "concept_legacy_id": selected.concept_id,
            "concept_legacy_source": selected.concept_source,
            "title": selected.title,
            "category": selected.category,
            "tags": selected.tags,
        }
    )
    return selected


__all__ = [
    "LegacyConceptChoice",
    "MAX_CONCEPT_CHOICES",
    "MAX_CONCEPT_PAGE",
    "MAX_CONCEPT_QUERY_LENGTH",
    "find_legacy_concepts",
    "render_concept_picker",
]

"""Pure session-state lifecycle for the S4 Notes & Evidence panel."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from editor.reading_space.state import SELECTED_DOCUMENT_ID
from editor.reading_space.state import SELECTED_SOURCE_ID
from editor.reading_space.state import queue_workspace_tab
from editor.reading_space.state import select_document
from editor.reading_space.state import select_source
from editor.reading_space.state import state_key as reading_space_key

SESSION_PREFIX = "reading_annotations_"

ACTIVE_CONTEXT = f"{SESSION_PREFIX}active_context"
SELECTED_ANNOTATION_ID = f"{SESSION_PREFIX}selected_annotation_id"
SELECTED_NOTE_ID = f"{SESSION_PREFIX}selected_note_id"
SELECTED_CONCEPT_IDENTITY = f"{SESSION_PREFIX}selected_concept_identity"
PENDING_PAGE_SUGGESTION = f"{SESSION_PREFIX}pending_page_suggestion"
PENDING_DRAFT_CLEARS = f"{SESSION_PREFIX}pending_draft_clears"
PENDING_DRAFT_VALUES = f"{SESSION_PREFIX}pending_draft_values"


def state_key(name: str, *parts: object) -> str:
    """Build a stable key from logical IDs, never paths, bytes, or DB objects."""
    suffix = "_".join(str(part) for part in parts if part is not None and str(part))
    return f"{SESSION_PREFIX}{name}" + (f"_{suffix}" if suffix else "")


def _logical_context(
    *,
    connection_label: str,
    database_name: str,
    database_token: str,
    source_id: str,
    document_id: str,
    user_scope: str,
) -> tuple[str, str, str, str, str, str]:
    return (
        connection_label,
        database_name,
        database_token,
        source_id,
        document_id,
        user_scope,
    )


def clear_annotation_state(state: MutableMapping[str, Any]) -> None:
    """Discard S4-only widget and selection state."""
    for key in tuple(state):
        if str(key).startswith(SESSION_PREFIX):
            state.pop(key, None)


def queue_draft_clear(
    state: MutableMapping[str, Any],
    *,
    form_key: str,
    document_id: str,
) -> None:
    """Queue one form cleanup for the next rerun, before widgets exist."""
    pending = state.get(PENDING_DRAFT_CLEARS)
    values = (
        {
            (str(item[0]), str(item[1]))
            for item in pending or ()
            if isinstance(item, (list, tuple)) and len(item) == 2
        }
        if isinstance(pending, (list, tuple, set))
        else set()
    )
    values.add((form_key, document_id))
    state[PENDING_DRAFT_CLEARS] = sorted(values)


def apply_pending_draft_clears(
    state: MutableMapping[str, Any],
) -> tuple[tuple[str, str], ...]:
    """Clear queued form widgets safely before Streamlit instantiates them."""
    pending = state.pop(PENDING_DRAFT_CLEARS, ())
    if not isinstance(pending, (list, tuple, set)):
        return ()
    targets = tuple(
        (str(item[0]), str(item[1]))
        for item in pending
        if isinstance(item, (list, tuple))
        and len(item) == 2
        and isinstance(item[0], str)
        and item[0]
        and isinstance(item[1], str)
        and item[1]
    )
    for form_key, document_id in targets:
        prefix = state_key(form_key)
        suffix = f"_{document_id}"
        for key in tuple(state):
            text = str(key)
            if text.startswith(prefix) and text.endswith(suffix):
                state.pop(key, None)
    return targets


def queue_draft_values(
    state: MutableMapping[str, Any],
    values: dict[str, str | int | bool | None],
) -> None:
    """Queue bounded scalar widget defaults for application before the next rerun."""
    pending = state.get(PENDING_DRAFT_VALUES)
    merged = dict(pending) if isinstance(pending, dict) else {}
    for key, value in values.items():
        if str(key).startswith(SESSION_PREFIX) and (
            value is None or isinstance(value, (str, int, bool))
        ):
            merged[str(key)] = value
    state[PENDING_DRAFT_VALUES] = merged


def apply_pending_draft_values(state: MutableMapping[str, Any]) -> tuple[str, ...]:
    """Apply queued scalar form values before their widgets are instantiated."""
    pending = state.pop(PENDING_DRAFT_VALUES, None)
    if not isinstance(pending, dict):
        return ()
    applied: list[str] = []
    for key, value in pending.items():
        if str(key).startswith(SESSION_PREFIX) and (
            value is None or isinstance(value, (str, int, bool))
        ):
            state[str(key)] = value
            applied.append(str(key))
    return tuple(applied)


def sync_database_context(
    state: MutableMapping[str, Any],
    *,
    connection_label: str,
    database_name: str,
    database: object,
) -> bool:
    """Clear S4 state immediately when the active database endpoint changes."""
    prefix = (connection_label, database_name, f"object:{id(database):x}")
    previous = state.get(ACTIVE_CONTEXT)
    if isinstance(previous, (list, tuple)) and tuple(previous[:3]) == prefix:
        return False
    clear_annotation_state(state)
    state[ACTIVE_CONTEXT] = (*prefix, None, None, None)
    return previous is not None


def suggested_current_page(
    state: MutableMapping[str, Any],
    *,
    document_id: str,
    persisted_page: int | None,
) -> int | None:
    """Prefer the live S3 page widget, falling back to persisted reading state."""
    widget_page = state.get(reading_space_key("current_page", document_id))
    for value in (widget_page, persisted_page):
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
            return value
    return None


def sync_context(
    state: MutableMapping[str, Any],
    *,
    connection_label: str,
    database_name: str,
    database: object,
    source_id: str,
    document_id: str,
    user_scope: str = "local",
) -> bool:
    """Clear S4 state when its database, Source, Document, or scope changes."""
    identity = _logical_context(
        connection_label=connection_label,
        database_name=database_name,
        database_token=f"object:{id(database):x}",
        source_id=source_id,
        document_id=document_id,
        user_scope=user_scope,
    )
    previous = state.get(ACTIVE_CONTEXT)
    if previous == identity:
        return False
    clear_annotation_state(state)
    state[ACTIVE_CONTEXT] = identity
    return previous is not None


def select_annotation(state: MutableMapping[str, Any], annotation_id: str | None) -> bool:
    """Select one annotation and invalidate concept controls bound to another."""
    previous = state.get(SELECTED_ANNOTATION_ID)
    if previous == annotation_id:
        return False
    state.pop(SELECTED_CONCEPT_IDENTITY, None)
    state.pop(SELECTED_NOTE_ID, None)
    if annotation_id is None:
        state.pop(SELECTED_ANNOTATION_ID, None)
    else:
        state[SELECTED_ANNOTATION_ID] = annotation_id
    return True


def select_note(state: MutableMapping[str, Any], note_id: str | None) -> bool:
    """Select one note and invalidate concept controls bound to another."""
    previous = state.get(SELECTED_NOTE_ID)
    if previous == note_id:
        return False
    state.pop(SELECTED_CONCEPT_IDENTITY, None)
    state.pop(SELECTED_ANNOTATION_ID, None)
    if note_id is None:
        state.pop(SELECTED_NOTE_ID, None)
    else:
        state[SELECTED_NOTE_ID] = note_id
    return True


def select_concept(
    state: MutableMapping[str, Any],
    concept_id: str | None,
    concept_source: str | None,
) -> bool:
    """Select one legacy concept by its immutable composite identity."""
    identity = (
        (concept_id, concept_source)
        if isinstance(concept_id, str) and isinstance(concept_source, str)
        else None
    )
    previous = state.get(SELECTED_CONCEPT_IDENTITY)
    if previous == identity:
        return False
    if identity is None:
        state.pop(SELECTED_CONCEPT_IDENTITY, None)
    else:
        state[SELECTED_CONCEPT_IDENTITY] = identity
    return True


def open_document_at_page(
    state: MutableMapping[str, Any],
    *,
    source_id: str,
    document_id: str,
    page_number: int | None,
) -> None:
    """Navigate through logical Reading Space IDs and optionally suggest a page."""
    select_source(state, source_id)
    select_document(state, document_id)
    state[SELECTED_SOURCE_ID] = source_id
    state[SELECTED_DOCUMENT_ID] = document_id
    queue_workspace_tab(state, "Workspace")
    if isinstance(page_number, int) and not isinstance(page_number, bool) and page_number >= 1:
        state[PENDING_PAGE_SUGGESTION] = {
            "document_id": document_id,
            "page_number": page_number,
        }


def apply_pending_page_suggestion(
    state: MutableMapping[str, Any],
    *,
    total_pages: int | None = None,
) -> tuple[str, int] | None:
    """Apply a queued S3 page before its number_input is instantiated."""
    pending = state.pop(PENDING_PAGE_SUGGESTION, None)
    if not isinstance(pending, dict):
        return None
    document_id = pending.get("document_id")
    page_number = pending.get("page_number")
    if (
        not isinstance(document_id, str)
        or not document_id
        or isinstance(page_number, bool)
        or not isinstance(page_number, int)
        or page_number < 1
        or state.get(SELECTED_DOCUMENT_ID) != document_id
    ):
        return None
    if isinstance(total_pages, int) and not isinstance(total_pages, bool) and total_pages >= 1:
        page_number = min(page_number, total_pages)
    state[reading_space_key("current_page", document_id)] = page_number
    return document_id, page_number


__all__ = [
    "ACTIVE_CONTEXT",
    "PENDING_DRAFT_CLEARS",
    "PENDING_DRAFT_VALUES",
    "PENDING_PAGE_SUGGESTION",
    "SELECTED_ANNOTATION_ID",
    "SELECTED_CONCEPT_IDENTITY",
    "SELECTED_NOTE_ID",
    "SESSION_PREFIX",
    "clear_annotation_state",
    "apply_pending_draft_clears",
    "apply_pending_draft_values",
    "apply_pending_page_suggestion",
    "open_document_at_page",
    "queue_draft_clear",
    "queue_draft_values",
    "select_annotation",
    "select_concept",
    "select_note",
    "state_key",
    "suggested_current_page",
    "sync_database_context",
    "sync_context",
]

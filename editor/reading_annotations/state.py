"""Pure session-state lifecycle for the S4 Notes & Evidence panel."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from editor.reading_space.state import SELECTED_DOCUMENT_ID
from editor.reading_space.state import SELECTED_SOURCE_ID
from editor.reading_space.state import select_document
from editor.reading_space.state import select_source
from editor.reading_space.state import state_key as reading_space_key

SESSION_PREFIX = "reading_annotations_"

ACTIVE_CONTEXT = f"{SESSION_PREFIX}active_context"
SELECTED_ANNOTATION_ID = f"{SESSION_PREFIX}selected_annotation_id"
SELECTED_NOTE_ID = f"{SESSION_PREFIX}selected_note_id"
SELECTED_CONCEPT_IDENTITY = f"{SESSION_PREFIX}selected_concept_identity"
PENDING_PAGE_SUGGESTION = f"{SESSION_PREFIX}pending_page_suggestion"


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
    "PENDING_PAGE_SUGGESTION",
    "SELECTED_ANNOTATION_ID",
    "SELECTED_CONCEPT_IDENTITY",
    "SELECTED_NOTE_ID",
    "SESSION_PREFIX",
    "clear_annotation_state",
    "apply_pending_page_suggestion",
    "open_document_at_page",
    "select_annotation",
    "select_concept",
    "select_note",
    "state_key",
    "sync_context",
]

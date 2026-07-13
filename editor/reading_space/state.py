"""Pure navigation and session-state lifecycle helpers for Reading Space."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from editor.pdf_preview import clear_pdf_preview

SESSION_PREFIX = "reading_space_"
READING_SPACE_NAV_LABEL = "📖 Reading Space"
PDF_PREVIEW_NAMESPACE = "reading_space"

ACTIVE_DATABASE_IDENTITY = f"{SESSION_PREFIX}active_database_identity"
ACTIVE_USER_SCOPE = f"{SESSION_PREFIX}active_user_scope"
PENDING_NAVIGATION = f"{SESSION_PREFIX}pending_navigation"
PENDING_TARGET = f"{SESSION_PREFIX}pending_target"
SELECTED_SOURCE_ID = f"{SESSION_PREFIX}selected_source_id"
SELECTED_DOCUMENT_ID = f"{SESSION_PREFIX}selected_document_id"
READER_SUBJECT = f"{SESSION_PREFIX}reader_subject"
CONFIRMED_WEB_DOCUMENT_ID = f"{SESSION_PREFIX}confirmed_web_document_id"
APPLIED_FILTER_SOURCE_ID = f"{SESSION_PREFIX}applied_filter_source_id"
PENDING_DOCUMENT_WIDGET_CLEARS = f"{SESSION_PREFIX}pending_document_widget_clears"
PENDING_CURRENT_PAGE_WIDGET_CLEARS = f"{SESSION_PREFIX}pending_current_page_widget_clears"
PENDING_CURRENT_PAGE_VALUE = f"{SESSION_PREFIX}pending_current_page_value"
PENDING_WORKSPACE_TAB = f"{SESSION_PREFIX}pending_workspace_tab"
WORKSPACE_TAB = f"{SESSION_PREFIX}workspace_tabs"
WORKSPACE_FOCUS = f"{SESSION_PREFIX}workspace_focus"
WORKSPACE_TABS = (
    "Workspace",
    "Documents",
    "Recent",
    "Notes",
    "Concepts",
    "Page Map",
    "Maintenance",
)

DOCUMENT_WIDGET_NAMES = frozenset(
    {
        "complete",
        "current_page",
        "defer",
        "open",
        "open_recent",
        "reader_completed",
        "reader_deferred",
        "reader_open_pdf",
        "reader_reset",
        "register_web_open",
        "reset",
        "page_next",
        "page_previous",
        "quick_annotation_focus",
        "quick_note_focus",
        "save_page",
        "set_book_page_one",
        "source_entrypoint",
    }
)


def state_key(name: str, *parts: object) -> str:
    """Build a stable Reading Space key from logical, non-secret parts."""
    suffix = "_".join(str(part) for part in parts if part is not None and str(part))
    return f"{SESSION_PREFIX}{name}" + (f"_{suffix}" if suffix else "")


def database_identity(
    connection_label: str,
    database_name: str,
    *,
    database: object | None = None,
) -> str:
    """Return an endpoint-sensitive identity without retaining a database object."""
    endpoint = f"\x1fobject:{id(database):x}" if database is not None else ""
    return f"{connection_label}\x1f{database_name}{endpoint}"


def clear_reader_preview(state: MutableMapping[str, Any]) -> None:
    """Discard the one transient Reading Space PDF and its logical subject."""
    clear_pdf_preview(state, PDF_PREVIEW_NAMESPACE)
    state.pop(READER_SUBJECT, None)
    for key in tuple(state):
        if str(key).startswith(f"{SESSION_PREFIX}pdf_preview_"):
            state.pop(key, None)


def clear_document_widgets(state: MutableMapping[str, Any], document_id: str | None) -> None:
    """Remove every widget value bound to one Document identity."""
    if not isinstance(document_id, str) or not document_id:
        return
    state.pop(WORKSPACE_FOCUS, None)
    for name in DOCUMENT_WIDGET_NAMES:
        state.pop(state_key(name, document_id), None)
    suffix = f"_{document_id}"
    for key in tuple(state):
        text = str(key)
        if text.startswith(f"{SESSION_PREFIX}page_map_") and text.endswith(suffix):
            state.pop(key, None)


def queue_document_widget_clear(
    state: MutableMapping[str, Any],
    document_id: str,
) -> None:
    """Queue a widget cleanup for the next rerun, before widgets are instantiated."""
    pending = state.get(PENDING_DOCUMENT_WIDGET_CLEARS)
    document_ids = set(pending) if isinstance(pending, (list, tuple, set)) else set()
    document_ids.add(document_id)
    state[PENDING_DOCUMENT_WIDGET_CLEARS] = sorted(document_ids)


def queue_current_page_widget_clear(
    state: MutableMapping[str, Any],
    document_id: str,
) -> None:
    """Queue only a Current page widget reset while preserving an open viewer."""
    pending = state.get(PENDING_CURRENT_PAGE_WIDGET_CLEARS)
    document_ids = set(pending) if isinstance(pending, (list, tuple, set)) else set()
    document_ids.add(document_id)
    state[PENDING_CURRENT_PAGE_WIDGET_CLEARS] = sorted(document_ids)


def queue_current_page_value(
    state: MutableMapping[str, Any],
    *,
    document_id: str,
    page_number: int,
) -> None:
    """Queue a manual PDF page value for application before its widget exists."""
    if (
        not isinstance(document_id, str)
        or not document_id
        or isinstance(page_number, bool)
        or not isinstance(page_number, int)
        or page_number < 1
    ):
        return
    state[PENDING_CURRENT_PAGE_VALUE] = {
        "document_id": document_id,
        "page_number": page_number,
    }


def apply_pending_current_page_value(
    state: MutableMapping[str, Any],
) -> tuple[str, int] | None:
    """Apply one queued manual page without persisting S3 reading state."""
    pending = state.pop(PENDING_CURRENT_PAGE_VALUE, None)
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
    state[state_key("current_page", document_id)] = page_number
    return document_id, page_number


def queue_workspace_tab(state: MutableMapping[str, Any], tab_name: str) -> None:
    """Queue one approved top-level Reading Space tab for the next rerun."""
    if tab_name in WORKSPACE_TABS:
        state[PENDING_WORKSPACE_TAB] = tab_name


def apply_pending_workspace_tab(state: MutableMapping[str, Any]) -> str | None:
    """Apply a queued tab choice before ``st.tabs`` creates its widget."""
    pending = state.pop(PENDING_WORKSPACE_TAB, None)
    if pending not in WORKSPACE_TABS:
        return None
    state[WORKSPACE_TAB] = pending
    return str(pending)


def migrate_legacy_workspace_tab(state: MutableMapping[str, Any]) -> bool:
    """Map the former Evidence label before Streamlit instantiates the tabs widget."""
    changed = False
    if state.get(WORKSPACE_TAB) == "Evidence":
        state[WORKSPACE_TAB] = "Concepts"
        changed = True
    if state.get(PENDING_WORKSPACE_TAB) == "Evidence":
        state[PENDING_WORKSPACE_TAB] = "Concepts"
        changed = True
    return changed


def apply_pending_document_widget_clears(state: MutableMapping[str, Any]) -> tuple[str, ...]:
    """Apply queued post-action widget cleanup at the start of a page render."""
    pending = state.pop(PENDING_DOCUMENT_WIDGET_CLEARS, ())
    if not isinstance(pending, (list, tuple, set)):
        return ()
    document_ids = tuple(value for value in pending if isinstance(value, str) and value)
    for document_id in document_ids:
        clear_document_widgets(state, document_id)
    return document_ids


def apply_pending_current_page_widget_clears(
    state: MutableMapping[str, Any],
) -> tuple[str, ...]:
    """Apply queued Reset cleanups before Current page widgets are instantiated."""
    pending = state.pop(PENDING_CURRENT_PAGE_WIDGET_CLEARS, ())
    if not isinstance(pending, (list, tuple, set)):
        return ()
    document_ids = tuple(value for value in pending if isinstance(value, str) and value)
    for document_id in document_ids:
        state.pop(state_key("current_page", document_id), None)
    return document_ids


def clear_reading_space_state(state: MutableMapping[str, Any]) -> None:
    """Clear Reading Space state without touching unrelated application flows."""
    clear_reader_preview(state)
    for key in tuple(state):
        if str(key).startswith(SESSION_PREFIX):
            state.pop(key, None)


def sync_database_state(
    state: MutableMapping[str, Any],
    *,
    connection_label: str,
    database_name: str,
    database: object | None = None,
) -> bool:
    """Invalidate Reading Space state when the active database endpoint changes."""
    identity = database_identity(
        connection_label,
        database_name,
        database=database,
    )
    previous = state.get(ACTIVE_DATABASE_IDENTITY)
    if previous == identity:
        return False
    clear_reading_space_state(state)
    state[ACTIVE_DATABASE_IDENTITY] = identity
    return previous is not None


def sync_user_scope(state: MutableMapping[str, Any], user_scope: str) -> bool:
    """Clear selection and the PDF when the local reading scope changes."""
    previous = state.get(ACTIVE_USER_SCOPE)
    if previous == user_scope:
        return False
    queue_document_widget_clear_for_selected(state)
    clear_reader_preview(state)
    for key in (SELECTED_SOURCE_ID, SELECTED_DOCUMENT_ID, CONFIRMED_WEB_DOCUMENT_ID):
        state.pop(key, None)
    state[ACTIVE_USER_SCOPE] = user_scope
    queue_workspace_tab(state, "Documents")
    return previous is not None


def select_source(state: MutableMapping[str, Any], source_id: str | None) -> bool:
    """Select one Source and invalidate any Document from a different Source."""
    previous = state.get(SELECTED_SOURCE_ID)
    if previous == source_id:
        return False
    queue_document_widget_clear_for_selected(state)
    clear_reader_preview(state)
    state.pop(SELECTED_DOCUMENT_ID, None)
    state.pop(CONFIRMED_WEB_DOCUMENT_ID, None)
    queue_workspace_tab(state, "Documents")
    if source_id is None:
        state.pop(SELECTED_SOURCE_ID, None)
    else:
        state[SELECTED_SOURCE_ID] = source_id
    return True


def select_document(state: MutableMapping[str, Any], document_id: str | None) -> bool:
    """Select one Document and invalidate stale viewer/external-link state."""
    previous = state.get(SELECTED_DOCUMENT_ID)
    if previous == document_id:
        return False
    if isinstance(previous, str):
        queue_document_widget_clear(state, previous)
    clear_reader_preview(state)
    state.pop(CONFIRMED_WEB_DOCUMENT_ID, None)
    if document_id is None:
        state.pop(SELECTED_DOCUMENT_ID, None)
        queue_workspace_tab(state, "Documents")
    else:
        state[SELECTED_DOCUMENT_ID] = document_id
        queue_workspace_tab(state, "Workspace")
    return True


def queue_document_widget_clear_for_selected(state: MutableMapping[str, Any]) -> None:
    """Queue cleanup for the currently selected Document, if any."""
    selected = state.get(SELECTED_DOCUMENT_ID)
    if isinstance(selected, str):
        queue_document_widget_clear(state, selected)


def sync_source_filter(state: MutableMapping[str, Any], source_id: str | None) -> bool:
    """Invalidate the reader only when the Source filter widget actually changes."""
    if APPLIED_FILTER_SOURCE_ID not in state:
        state[APPLIED_FILTER_SOURCE_ID] = source_id
        return False
    previous = state.get(APPLIED_FILTER_SOURCE_ID)
    if previous == source_id:
        return False
    state[APPLIED_FILTER_SOURCE_ID] = source_id
    select_source(state, source_id)
    return True


def add_reading_space_navigation(options: list[str] | tuple[str, ...]) -> list[str]:
    """Insert Reading Space once next to Source Catalog administration."""
    result = [option for option in options if option != READING_SPACE_NAV_LABEL]
    anchor = "✏️ Edit / Analyze Source"
    try:
        insert_at = result.index(anchor) + 1
    except ValueError:
        try:
            insert_at = result.index("🏠 Dashboard") + 1
        except ValueError:
            insert_at = 0
    result.insert(insert_at, READING_SPACE_NAV_LABEL)
    return result


def request_reading_space_navigation(
    state: MutableMapping[str, Any],
    *,
    source_id: str,
    document_id: str,
    kind: str,
    user_scope: str = "local",
) -> None:
    """Queue a database-local Document target for the next application rerun."""
    state[PENDING_NAVIGATION] = READING_SPACE_NAV_LABEL
    state[PENDING_TARGET] = {
        "source_id": source_id,
        "document_id": document_id,
        "kind": kind,
        "user_scope": user_scope,
    }


def apply_pending_navigation(
    state: MutableMapping[str, Any],
    options: list[str] | tuple[str, ...],
    *,
    navigation_key: str,
) -> str | None:
    """Apply queued Reading Space navigation before the sidebar widget exists."""
    pending = state.pop(PENDING_NAVIGATION, None)
    if pending not in options:
        if pending is not None:
            state.pop(PENDING_TARGET, None)
        return None
    state[navigation_key] = pending
    return str(pending)


def consume_pending_target(state: MutableMapping[str, Any]) -> dict[str, str] | None:
    """Consume one validated logical handoff from Source Documents."""
    value = state.pop(PENDING_TARGET, None)
    if not isinstance(value, dict):
        return None
    required = ("source_id", "document_id", "kind", "user_scope")
    if any(not isinstance(value.get(field), str) or not value[field] for field in required):
        return None
    if value["kind"] not in {"pdf", "web"}:
        return None
    return {field: value[field] for field in required}


__all__ = [
    "ACTIVE_DATABASE_IDENTITY",
    "ACTIVE_USER_SCOPE",
    "APPLIED_FILTER_SOURCE_ID",
    "CONFIRMED_WEB_DOCUMENT_ID",
    "PDF_PREVIEW_NAMESPACE",
    "PENDING_DOCUMENT_WIDGET_CLEARS",
    "PENDING_CURRENT_PAGE_WIDGET_CLEARS",
    "PENDING_CURRENT_PAGE_VALUE",
    "PENDING_NAVIGATION",
    "PENDING_TARGET",
    "PENDING_WORKSPACE_TAB",
    "READER_SUBJECT",
    "READING_SPACE_NAV_LABEL",
    "SELECTED_DOCUMENT_ID",
    "SELECTED_SOURCE_ID",
    "SESSION_PREFIX",
    "WORKSPACE_FOCUS",
    "WORKSPACE_TAB",
    "WORKSPACE_TABS",
    "add_reading_space_navigation",
    "apply_pending_navigation",
    "apply_pending_document_widget_clears",
    "apply_pending_current_page_widget_clears",
    "apply_pending_current_page_value",
    "apply_pending_workspace_tab",
    "clear_document_widgets",
    "clear_reader_preview",
    "clear_reading_space_state",
    "consume_pending_target",
    "database_identity",
    "migrate_legacy_workspace_tab",
    "request_reading_space_navigation",
    "queue_document_widget_clear",
    "queue_document_widget_clear_for_selected",
    "queue_current_page_widget_clear",
    "queue_current_page_value",
    "queue_workspace_tab",
    "select_document",
    "select_source",
    "state_key",
    "sync_database_state",
    "sync_source_filter",
    "sync_user_scope",
]

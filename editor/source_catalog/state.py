"""Pure, namespaced session-state helpers for Source Catalog pages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from typing import Any

SESSION_PREFIX = "source_catalog_"
ADD_SOURCE_NAV_LABEL = "➕ Add Source"
EDIT_SOURCE_NAV_LABEL = "✏️ Edit / Analyze Source"

ACTIVE_DATABASE_IDENTITY = f"{SESSION_PREFIX}active_database_identity"
NAVIGATION_WIDGET = f"{SESSION_PREFIX}navigation"
PENDING_NAVIGATION = f"{SESSION_PREFIX}pending_navigation"
SELECTED_SOURCE_ID = f"{SESSION_PREFIX}selected_source_id"
PENDING_LEGACY_CONCEPT = f"{SESSION_PREFIX}pending_legacy_concept"
FLASH_MESSAGE = f"{SESSION_PREFIX}flash_message"


def draft_fingerprint(value: Any) -> str:
    """Hash editable draft content for decision-specific widget keys."""
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="json")
    else:
        payload = value

    def scrub(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                str(key): scrub(nested)
                for key, nested in item.items()
                if key
                not in {
                    "source_id",
                    "reference_id",
                    "created_at",
                    "updated_at",
                    "archived_at",
                    "imported_at",
                    "raw",
                }
            }
        if isinstance(item, (list, tuple)):
            return [scrub(nested) for nested in item]
        return item

    encoded = json.dumps(
        scrub(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def state_key(name: str, *parts: object) -> str:
    """Build a stable S1B-only key from safe logical parts."""
    suffix = "_".join(str(part) for part in parts if part is not None and str(part))
    return f"{SESSION_PREFIX}{name}" + (f"_{suffix}" if suffix else "")


def database_identity(
    connection_label: str,
    database_name: str,
    *,
    database: object | None = None,
) -> str:
    """Return a non-display runtime identity used only to invalidate S1B state."""
    endpoint_token = f"\x1fobject:{id(database):x}" if database is not None else ""
    return f"{connection_label}\x1f{database_name}{endpoint_token}"


def sync_database_state(
    state: MutableMapping[str, Any],
    *,
    connection_label: str,
    database_name: str,
    database: object | None = None,
) -> bool:
    """Clear only S1B state when the real active database changes."""
    identity = database_identity(
        connection_label,
        database_name,
        database=database,
    )
    previous = state.get(ACTIVE_DATABASE_IDENTITY)
    if previous == identity:
        return False
    for key in tuple(state):
        if str(key).startswith(SESSION_PREFIX):
            state.pop(key, None)
    state[ACTIVE_DATABASE_IDENTITY] = identity
    return previous is not None


def add_source_catalog_navigation(options: list[str] | tuple[str, ...]) -> list[str]:
    """Insert both S1B pages once while preserving every existing option."""
    result = [
        option for option in options if option not in {ADD_SOURCE_NAV_LABEL, EDIT_SOURCE_NAV_LABEL}
    ]
    try:
        insert_at = result.index("🏠 Dashboard") + 1
    except ValueError:
        insert_at = 0
    result[insert_at:insert_at] = [ADD_SOURCE_NAV_LABEL, EDIT_SOURCE_NAV_LABEL]
    return result


def request_navigation(
    state: MutableMapping[str, Any],
    page: str,
    *,
    source_id: str | None = None,
) -> None:
    """Queue navigation for application before the sidebar widget is built."""
    state[PENDING_NAVIGATION] = page
    if source_id is not None:
        state[SELECTED_SOURCE_ID] = source_id


def apply_pending_navigation(
    state: MutableMapping[str, Any],
    options: list[str] | tuple[str, ...],
) -> str | None:
    """Apply a queued page to the namespaced widget state exactly once."""
    pending = state.pop(PENDING_NAVIGATION, None)
    if pending not in options:
        return None
    state[NAVIGATION_WIDGET] = pending
    return str(pending)


def queue_legacy_concept_open(
    state: MutableMapping[str, Any],
    *,
    concept_id: str,
    source: str,
) -> None:
    """Queue the existing Edit Concept page with an exact legacy identity."""
    state[PENDING_LEGACY_CONCEPT] = {"id": concept_id, "source": source}
    request_navigation(state, "✏️ Edit Concept")


def consume_legacy_concept_open(state: MutableMapping[str, Any]) -> dict[str, str] | None:
    """Consume a queued exact legacy concept identity."""
    value = state.pop(PENDING_LEGACY_CONCEPT, None)
    if not isinstance(value, dict):
        return None
    concept_id = value.get("id")
    source = value.get("source")
    if not isinstance(concept_id, str) or not isinstance(source, str):
        return None
    return {"id": concept_id, "source": source}


def begin_operation(
    state: MutableMapping[str, Any],
    operation: str,
    token: str,
) -> bool:
    """Claim a write token once to protect against rerun double-submit."""
    active_key = state_key("operation_active", operation)
    completed_key = state_key("operation_completed", operation)
    if state.get(active_key) == token or state.get(completed_key) == token:
        return False
    state[active_key] = token
    return True


def finish_operation(
    state: MutableMapping[str, Any],
    operation: str,
    token: str,
    *,
    succeeded: bool,
) -> None:
    """Release a write token and remember only successful completion."""
    active_key = state_key("operation_active", operation)
    completed_key = state_key("operation_completed", operation)
    if state.get(active_key) == token:
        state.pop(active_key, None)
    if succeeded:
        state[completed_key] = token


def clear_completed_operation(state: MutableMapping[str, Any], operation: str) -> None:
    """Allow a distinct later operation after form state changes."""
    state.pop(state_key("operation_completed", operation), None)


def clear_state_group(state: MutableMapping[str, Any], group: str) -> None:
    """Clear one namespaced UI workflow without touching other S1B pages."""
    prefix = state_key(group)
    for key in tuple(state):
        if str(key).startswith(prefix):
            state.pop(key, None)


def set_flash(
    state: MutableMapping[str, Any],
    level: str,
    message: str,
) -> None:
    """Store one post-rerun message without retaining exceptions."""
    state[FLASH_MESSAGE] = {"level": level, "message": message}


def consume_flash(state: MutableMapping[str, Any]) -> dict[str, str] | None:
    """Consume one namespaced post-rerun message."""
    value = state.pop(FLASH_MESSAGE, None)
    if not isinstance(value, dict):
        return None
    level = value.get("level")
    message = value.get("message")
    if not isinstance(level, str) or not isinstance(message, str):
        return None
    return {"level": level, "message": message}


__all__ = [
    "ACTIVE_DATABASE_IDENTITY",
    "ADD_SOURCE_NAV_LABEL",
    "EDIT_SOURCE_NAV_LABEL",
    "FLASH_MESSAGE",
    "NAVIGATION_WIDGET",
    "PENDING_LEGACY_CONCEPT",
    "PENDING_NAVIGATION",
    "SELECTED_SOURCE_ID",
    "SESSION_PREFIX",
    "add_source_catalog_navigation",
    "apply_pending_navigation",
    "begin_operation",
    "clear_completed_operation",
    "clear_state_group",
    "consume_flash",
    "consume_legacy_concept_open",
    "database_identity",
    "draft_fingerprint",
    "finish_operation",
    "queue_legacy_concept_open",
    "request_navigation",
    "set_flash",
    "state_key",
    "sync_database_state",
]

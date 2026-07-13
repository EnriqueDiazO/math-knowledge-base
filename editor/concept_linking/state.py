"""Pure session-state lifecycle for the guided concept-linking wizard."""

# ruff: noqa: D103

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from editor.concept_linking.view_models import ConceptLinkingContext

SESSION_PREFIX = "concept_linking_"
ACTIVE_CONTEXT = f"{SESSION_PREFIX}context"
ACTIVE = f"{SESSION_PREFIX}active"
STEP = f"{SESSION_PREFIX}step"
DOCUMENT_ID = f"{SESSION_PREFIX}document_id"
PDF_PAGE = f"{SESSION_PREFIX}pdf_page"
SELECTED_CONCEPT_KEY = f"{SESSION_PREFIX}selected_concept_key"
MODE = f"{SESSION_PREFIX}mode"
TARGET_KIND = f"{SESSION_PREFIX}target_kind"
TARGET_ID = f"{SESSION_PREFIX}target_id"
LINK_TYPE = f"{SESSION_PREFIX}link_type"
COMMENT = f"{SESSION_PREFIX}comment"
SEARCH_QUERY = f"{SESSION_PREFIX}search_query"
PARTIAL_TARGET_KIND = f"{SESSION_PREFIX}partial_target_kind"
PARTIAL_TARGET_ID = f"{SESSION_PREFIX}partial_target_id"
PARTIAL_MESSAGE = f"{SESSION_PREFIX}partial_message"
LAST_RESULT = f"{SESSION_PREFIX}last_result"
DUPLICATE_LINK_ID = f"{SESSION_PREFIX}duplicate_link_id"
RECENT_CONCEPTS = f"{SESSION_PREFIX}recent_concepts"
_IDENTITY_SEPARATOR = "\x1f"
_MAX_RECENT = 12


def state_key(name: str, *parts: object) -> str:
    """Return a stable namespaced widget key."""
    suffix = "_".join(str(part) for part in parts if part is not None and str(part))
    return f"{SESSION_PREFIX}{name}" + (f"_{suffix}" if suffix else "")


def encode_concept_identity(concept_id: str, concept_source: str) -> str:
    """Encode the exact legacy composite identity without storing a document."""
    if _IDENTITY_SEPARATOR in concept_id or _IDENTITY_SEPARATOR in concept_source:
        raise ValueError("Legacy concept identity contains an unsupported control character")
    return f"{concept_id}{_IDENTITY_SEPARATOR}{concept_source}"


def decode_concept_identity(value: object) -> tuple[str, str] | None:
    """Decode a session-safe legacy identity."""
    if not isinstance(value, str) or value.count(_IDENTITY_SEPARATOR) != 1:
        return None
    concept_id, concept_source = value.split(_IDENTITY_SEPARATOR, 1)
    if not concept_id or not concept_source:
        return None
    return concept_id, concept_source


def _context_identity(
    *,
    connection_label: str,
    database_name: str,
    database: object | None,
    user_scope: str,
    source_id: str | None,
    document_id: str | None,
) -> str:
    endpoint = f"object:{id(database):x}" if database is not None else "none"
    return _IDENTITY_SEPARATOR.join(
        (
            connection_label,
            database_name,
            endpoint,
            user_scope,
            source_id or "",
            document_id or "",
        )
    )


def clear_wizard(state: MutableMapping[str, Any], *, keep_result: bool = False) -> None:
    """Clear only the active wizard draft, preserving unrelated reading drafts."""
    preserved = {ACTIVE_CONTEXT, RECENT_CONCEPTS}
    if keep_result:
        preserved.add(LAST_RESULT)
    for key in tuple(state):
        if str(key).startswith(SESSION_PREFIX) and key not in preserved:
            state.pop(key, None)


def clear_all(state: MutableMapping[str, Any]) -> None:
    """Clear the complete S4.3 namespace and nothing else."""
    for key in tuple(state):
        if str(key).startswith(SESSION_PREFIX):
            state.pop(key, None)


def sync_context(
    state: MutableMapping[str, Any],
    *,
    connection_label: str,
    database_name: str,
    database: object | None,
    user_scope: str,
    source_id: str | None,
    document_id: str | None,
) -> bool:
    """Invalidate S4.3 state after a database, scope, Source, or Document change."""
    identity = _context_identity(
        connection_label=connection_label,
        database_name=database_name,
        database=database,
        user_scope=user_scope,
        source_id=source_id,
        document_id=document_id,
    )
    previous = state.get(ACTIVE_CONTEXT)
    if previous == identity:
        return False
    clear_all(state)
    state[ACTIVE_CONTEXT] = identity
    return previous is not None


def start_wizard(
    state: MutableMapping[str, Any],
    context: ConceptLinkingContext,
    *,
    target_kind: str | None = None,
    target_id: str | None = None,
    pdf_page: int | None = None,
) -> None:
    """Capture the logical Document/page and optional pending evidence target."""
    clear_wizard(state)
    state[ACTIVE] = True
    state[STEP] = 1
    state[DOCUMENT_ID] = context.document_id
    state[PDF_PAGE] = pdf_page if pdf_page is not None else context.pdf_page
    if target_kind in {"annotation", "note"} and isinstance(target_id, str) and target_id:
        state[MODE] = target_kind
        state[TARGET_KIND] = target_kind
        state[TARGET_ID] = target_id


def cancel_wizard(state: MutableMapping[str, Any]) -> None:
    """Cancel without touching Quick Annotation/Reading Note state."""
    clear_wizard(state)


def select_concept(
    state: MutableMapping[str, Any],
    concept_id: str,
    concept_source: str,
) -> bool:
    """Select a concept and clear relationship fields from an incompatible draft."""
    encoded = encode_concept_identity(concept_id, concept_source)
    if state.get(SELECTED_CONCEPT_KEY) == encoded:
        return False
    state[SELECTED_CONCEPT_KEY] = encoded
    state[STEP] = max(int(state.get(STEP, 1)), 2)
    for key in (
        LINK_TYPE,
        COMMENT,
        PARTIAL_TARGET_KIND,
        PARTIAL_TARGET_ID,
        PARTIAL_MESSAGE,
        DUPLICATE_LINK_ID,
    ):
        state.pop(key, None)
    return True


def change_concept(state: MutableMapping[str, Any]) -> None:
    """Return to search while retaining a deliberately preselected evidence target."""
    for key in (SELECTED_CONCEPT_KEY, LINK_TYPE, COMMENT, DUPLICATE_LINK_ID):
        state.pop(key, None)
    state[STEP] = 1


def remember_concept(state: MutableMapping[str, Any], concept_id: str, concept_source: str) -> None:
    """Keep a bounded list of primitive identities for quick access."""
    encoded = encode_concept_identity(concept_id, concept_source)
    existing = state.get(RECENT_CONCEPTS, ())
    values = [encoded]
    if isinstance(existing, (list, tuple)):
        values.extend(item for item in existing if isinstance(item, str) and item != encoded)
    state[RECENT_CONCEPTS] = values[:_MAX_RECENT]


def recent_identities(state: MutableMapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return decoded recent identities without exposing invalid session payloads."""
    raw = state.get(RECENT_CONCEPTS, ())
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(item for value in raw if (item := decode_concept_identity(value)) is not None)


def record_partial(
    state: MutableMapping[str, Any], *, target_kind: str, target_id: str, message: str
) -> None:
    """Retain a successfully created target when the subsequent link fails."""
    state[PARTIAL_TARGET_KIND] = target_kind
    state[PARTIAL_TARGET_ID] = target_id
    state[PARTIAL_MESSAGE] = message
    state[TARGET_KIND] = target_kind
    state[TARGET_ID] = target_id


def clear_partial(state: MutableMapping[str, Any]) -> None:
    for key in (PARTIAL_TARGET_KIND, PARTIAL_TARGET_ID, PARTIAL_MESSAGE):
        state.pop(key, None)


__all__ = [
    "ACTIVE",
    "ACTIVE_CONTEXT",
    "COMMENT",
    "DOCUMENT_ID",
    "DUPLICATE_LINK_ID",
    "LAST_RESULT",
    "LINK_TYPE",
    "MODE",
    "PARTIAL_MESSAGE",
    "PARTIAL_TARGET_ID",
    "PARTIAL_TARGET_KIND",
    "PDF_PAGE",
    "RECENT_CONCEPTS",
    "SEARCH_QUERY",
    "SELECTED_CONCEPT_KEY",
    "SESSION_PREFIX",
    "STEP",
    "TARGET_ID",
    "TARGET_KIND",
    "cancel_wizard",
    "change_concept",
    "clear_all",
    "clear_partial",
    "clear_wizard",
    "decode_concept_identity",
    "encode_concept_identity",
    "recent_identities",
    "record_partial",
    "remember_concept",
    "select_concept",
    "start_wizard",
    "state_key",
    "sync_context",
]

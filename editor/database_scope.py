"""Pure session-state isolation helpers for database-bound editor workflows."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from typing import Any

DOCUMENT_BUILDER_PREFIX = "document_builder_"
DOCUMENT_BUILDER_WIDGET_PREFIX = "doc_"
DOCUMENT_BUILDER_SCOPE_KEY = f"{DOCUMENT_BUILDER_PREFIX}active_database_scope"
KNOWLEDGE_GRAPH_PREFIX = "knowledge_graph_"
KNOWLEDGE_GRAPH_WIDGET_PREFIX = "kg_"
KNOWLEDGE_GRAPH_SCOPE_KEY = f"{KNOWLEDGE_GRAPH_PREFIX}active_database_scope"
KNOWLEDGE_GRAPH_LOADED_MAP_KEY = f"{KNOWLEDGE_GRAPH_PREFIX}loaded_map_identity"


def database_scope_token(connection_label: str, database_name: str) -> str:
    """Return a stable opaque token for one connection label and real database."""
    payload = json.dumps(
        [str(connection_label), str(database_name)],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def sync_document_builder_scope(
    state: MutableMapping[str, Any],
    scope_token: str,
) -> bool:
    """Invalidate all Builder state before a different database can use it."""
    previous = state.get(DOCUMENT_BUILDER_SCOPE_KEY)
    if previous == scope_token:
        return False
    for key in tuple(state):
        if str(key).startswith((DOCUMENT_BUILDER_PREFIX, DOCUMENT_BUILDER_WIDGET_PREFIX)):
            state.pop(key, None)
    state[DOCUMENT_BUILDER_SCOPE_KEY] = scope_token
    return previous is not None


def sync_knowledge_graph_scope(
    state: MutableMapping[str, Any],
    scope_token: str,
) -> bool:
    """Invalidate all graph and map state before a different database uses it."""
    previous = state.get(KNOWLEDGE_GRAPH_SCOPE_KEY)
    if previous == scope_token:
        return False
    for key in tuple(state):
        if str(key).startswith((KNOWLEDGE_GRAPH_PREFIX, KNOWLEDGE_GRAPH_WIDGET_PREFIX)):
            state.pop(key, None)
    state[KNOWLEDGE_GRAPH_SCOPE_KEY] = scope_token
    return previous is not None


def knowledge_map_session_identity(
    scope_token: str,
    map_id: object,
    map_uid: object | None,
) -> str:
    """Bind a loaded map identity to its database, Mongo id, and portable uid."""
    payload = json.dumps(
        [str(scope_token), str(map_id), str(map_uid or "")],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def mark_knowledge_map_loaded(
    state: MutableMapping[str, Any],
    scope_token: str,
    map_id: object,
    map_uid: object | None,
) -> str:
    """Record that map state was freshly loaded from the active database."""
    identity = knowledge_map_session_identity(scope_token, map_id, map_uid)
    state[KNOWLEDGE_GRAPH_LOADED_MAP_KEY] = identity
    return identity


def knowledge_map_is_loaded(
    state: MutableMapping[str, Any],
    scope_token: str,
    map_id: object,
    map_uid: object | None,
) -> bool:
    """Return whether pending map actions belong to the active database map."""
    expected = knowledge_map_session_identity(scope_token, map_id, map_uid)
    return state.get(KNOWLEDGE_GRAPH_LOADED_MAP_KEY) == expected


__all__ = [
    "DOCUMENT_BUILDER_SCOPE_KEY",
    "KNOWLEDGE_GRAPH_LOADED_MAP_KEY",
    "KNOWLEDGE_GRAPH_SCOPE_KEY",
    "database_scope_token",
    "knowledge_map_is_loaded",
    "knowledge_map_session_identity",
    "mark_knowledge_map_loaded",
    "sync_document_builder_scope",
    "sync_knowledge_graph_scope",
]

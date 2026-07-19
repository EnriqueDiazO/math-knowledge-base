"""Pure session-state isolation helpers for database-bound editor workflows."""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from typing import Any

DOCUMENT_BUILDER_PREFIX = "document_builder_"
DOCUMENT_BUILDER_WIDGET_PREFIX = "doc_"
DOCUMENT_BUILDER_SCOPE_KEY = f"{DOCUMENT_BUILDER_PREFIX}active_database_scope"


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


__all__ = [
    "DOCUMENT_BUILDER_SCOPE_KEY",
    "database_scope_token",
    "sync_document_builder_scope",
]

"""Narrow persistence boundary for structured settings on existing Diario notes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import settings_persistence_set


def persist_diary_note_update(
    collection: Any,
    original_note: Mapping[str, Any],
    *,
    ordinary_fields: Mapping[str, Any] | None = None,
    settings: DiaryNoteSettings | None = None,
) -> Any | None:
    """Update exactly one note with ordinary fields plus a minimal settings diff.

    Passing no changed fields performs no Mongo operation.  This boundary only
    supports ``update_one`` with ``$set``; bulk updates and document replacement
    are intentionally outside the feature's API.
    """
    set_fields = dict(ordinary_fields or {})
    if settings is not None:
        set_fields.update(settings_persistence_set(original_note, settings))
    if not set_fields:
        return None
    return collection.update_one(
        {"_id": original_note.get("_id")},
        {"$set": set_fields},
    )


__all__ = ["persist_diary_note_update"]

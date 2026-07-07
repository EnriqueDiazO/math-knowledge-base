"""Persistence adapter for Cornell notes stored in latex_notes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import CornellDocument
from editor.cornell.models import build_cornell_math_v1_payload

NORMAL_NOTE_FIELDS = (
    "title",
    "date",
    "project",
    "context",
    "tags",
    "image_ids",
    "created_at",
    "updated_at",
)


def is_cornell_note(note: Mapping[str, Any] | None) -> bool:
    """Return True when a latex_notes document uses the Cornell v1 format."""
    return isinstance(note, Mapping) and note.get("note_format") == CORNELL_NOTE_FORMAT


def _validate_note_format(metadata: Mapping[str, Any]) -> None:
    note_format = metadata.get("note_format")
    if note_format is not None and note_format != CORNELL_NOTE_FORMAT:
        raise ValueError(f"Unsupported Cornell note_format: {note_format!r}")


def build_cornell_note_document(
    metadata: Mapping[str, Any],
    document: CornellDocument,
) -> dict[str, Any]:
    """Build a latex_notes-compatible Cornell document without trusting latex_body input."""
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping")
    if not isinstance(document, CornellDocument):
        raise ValueError("document must be a CornellDocument")
    _validate_note_format(metadata)

    note = {
        field: deepcopy(metadata[field])
        for field in NORMAL_NOTE_FIELDS
        if field in metadata
    }
    note.update(build_cornell_math_v1_payload(document))
    return note


def extract_cornell_document(note: Mapping[str, Any]) -> CornellDocument:
    """Extract the canonical CornellDocument from a persisted Cornell note."""
    if not isinstance(note, Mapping):
        raise ValueError("note must be a mapping")
    if "note_format" in note and note.get("note_format") != CORNELL_NOTE_FORMAT:
        raise ValueError(f"Unsupported note_format: {note.get('note_format')!r}")
    if not is_cornell_note(note):
        raise ValueError("note is not a cornell_math_v1 note")
    cornell = note.get("cornell")
    if not isinstance(cornell, Mapping):
        raise ValueError("cornell must be a mapping")
    return CornellDocument.from_dict(cornell)

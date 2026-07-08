"""Persistence adapter for CPI notes stored in latex_notes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from editor.cpi.media import cpi_document_image_ids
from editor.cpi.models import CPI_NOTE_FORMAT
from editor.cpi.models import CpiDocument
from editor.cpi.models import build_cpi_v1_payload

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


def is_cpi_note(note: Mapping[str, Any] | None) -> bool:
    """Return True when a latex_notes document uses the CPI v1 format."""
    return isinstance(note, Mapping) and note.get("note_format") == CPI_NOTE_FORMAT


def _validate_note_format(metadata: Mapping[str, Any]) -> None:
    note_format = metadata.get("note_format")
    if note_format is not None and note_format != CPI_NOTE_FORMAT:
        raise ValueError(f"Unsupported CPI note_format: {note_format!r}")


def build_cpi_note_document(
    metadata: Mapping[str, Any],
    document: CpiDocument,
) -> dict[str, Any]:
    """Build a latex_notes-compatible CPI document without trusting latex_body input."""
    if not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping")
    if not isinstance(document, CpiDocument):
        raise ValueError("document must be a CpiDocument")
    _validate_note_format(metadata)

    note = {
        field: deepcopy(metadata[field])
        for field in NORMAL_NOTE_FIELDS
        if field in metadata
    }
    note["image_ids"] = list(cpi_document_image_ids(document))
    note.update(build_cpi_v1_payload(document))
    return note


def extract_cpi_document(note: Mapping[str, Any]) -> CpiDocument:
    """Extract the canonical CpiDocument from a persisted CPI note."""
    if not isinstance(note, Mapping):
        raise ValueError("note must be a mapping")
    if "note_format" in note and note.get("note_format") != CPI_NOTE_FORMAT:
        raise ValueError(f"Unsupported note_format: {note.get('note_format')!r}")
    if not is_cpi_note(note):
        raise ValueError("note is not a cpi_v1 note")
    cpi = note.get("cpi")
    if not isinstance(cpi, Mapping):
        raise ValueError("cpi must be a mapping")
    return CpiDocument.from_dict(cpi)

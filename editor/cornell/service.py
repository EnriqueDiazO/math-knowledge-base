"""CRUD service layer for Cornell notes stored in latex_notes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import CornellDocument
from editor.cornell.models import build_cornell_math_v1_payload
from editor.cornell.persistence import build_cornell_note_document
from editor.cornell.persistence import extract_cornell_document


def _canonical_note(note: Mapping[str, Any], document: CornellDocument) -> dict[str, Any]:
    canonical = deepcopy(dict(note))
    canonical.update(build_cornell_math_v1_payload(document))
    return canonical


def _cornell_query(query: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not query:
        return {"note_format": CORNELL_NOTE_FORMAT}
    return {"$and": [{"note_format": CORNELL_NOTE_FORMAT}, deepcopy(dict(query))]}


def create_cornell_note(db: Any, metadata: Mapping[str, Any], document: CornellDocument) -> Any:
    """Create a Cornell note using MathMongo's existing latex_notes CRUD."""
    note = build_cornell_note_document(metadata, document)
    return db.create_notebook_note(note)


def get_cornell_note(db: Any, note_id: Any) -> dict[str, Any] | None:
    """Return one Cornell note with canonical latex_body regenerated from cornell.pages."""
    note = db.get_notebook_note_by_id(note_id)
    if note is None:
        return None
    document = extract_cornell_document(note)
    return _canonical_note(note, document)


def update_cornell_note(
    db: Any,
    note_id: Any,
    metadata: Mapping[str, Any],
    document: CornellDocument,
) -> Any:
    """Update an existing Cornell note without converting legacy notes."""
    existing = db.get_notebook_note_by_id(note_id)
    if existing is None:
        return None
    extract_cornell_document(existing)
    note = build_cornell_note_document(metadata, document)
    return db.update_notebook_note(note_id, note)


def delete_cornell_note(db: Any, note_id: Any) -> Any:
    """Delete an existing Cornell note without deleting legacy notes."""
    existing = db.get_notebook_note_by_id(note_id)
    if existing is None:
        return None
    extract_cornell_document(existing)
    return db.delete_notebook_note(note_id)


def list_cornell_notes(
    db: Any,
    query: Mapping[str, Any] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List Cornell notes through MathMongo's existing query/list method."""
    notes = db.get_notebook_notes(query=_cornell_query(query), limit=limit)
    result = []
    for note in notes:
        document = extract_cornell_document(note)
        result.append(_canonical_note(note, document))
    return result

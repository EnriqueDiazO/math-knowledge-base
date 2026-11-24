"""CRUD service layer for CPI notes stored in latex_notes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from editor.cpi.media import cpi_document_image_ids
from editor.cpi.models import CPI_NOTE_FORMAT
from editor.cpi.models import CpiDocument
from editor.cpi.models import build_cpi_v1_payload
from editor.cpi.persistence import build_cpi_note_document
from editor.cpi.persistence import extract_cpi_document
from editor.notebook_lifecycle import delete_note_record
from editor.notebook_lifecycle import duplicate_note_record
from editor.structured_note_persistence import update_structured_note


def _canonical_note(note: Mapping[str, Any], document: CpiDocument) -> dict[str, Any]:
    canonical = deepcopy(dict(note))
    canonical.update(build_cpi_v1_payload(document))
    return canonical


def _cpi_query(query: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not query:
        return {"note_format": CPI_NOTE_FORMAT}
    return {"$and": [{"note_format": CPI_NOTE_FORMAT}, deepcopy(dict(query))]}


def create_cpi_note(
    db: Any,
    metadata: Mapping[str, Any],
    document: CpiDocument,
    *,
    note_id=None,
    creation_fingerprint=None,
) -> Any:
    """Create a CPI note using MathMongo's existing latex_notes CRUD."""
    note = build_cpi_note_document(metadata, document)
    if note_id is not None:
        note["_id"] = note_id
    if creation_fingerprint is not None:
        note["study_create_fingerprint"] = creation_fingerprint
    return db.create_notebook_note(note)


def get_cpi_note(db: Any, note_id: Any) -> dict[str, Any] | None:
    """Return one CPI note with canonical latex_body regenerated from cpi.pages."""
    note = db.get_notebook_note_by_id(note_id)
    if note is None:
        return None
    document = extract_cpi_document(note)
    return _canonical_note(note, document)


def update_cpi_note(
    db: Any,
    note_id: Any,
    metadata: Mapping[str, Any],
    document: CpiDocument,
    *,
    expected_snapshot: Mapping[str, Any] | None = None,
    page_origins=None,
    operation_fingerprint=None,
) -> Any:
    """Update an existing CPI note without converting other note formats."""
    existing = (
        deepcopy(dict(expected_snapshot))
        if expected_snapshot is not None
        else db.get_notebook_note_by_id(note_id)
    )
    if existing is None:
        return None
    if str(existing["_id"]) != str(note_id):
        raise ValueError("The observed note identity does not match the requested edit")
    previous = extract_cpi_document(existing)
    safe_metadata = deepcopy(dict(metadata))
    if existing.get("seed_id") and "seed_id" not in safe_metadata:
        safe_metadata["seed_id"] = existing["seed_id"]
    note = build_cpi_note_document(safe_metadata, document)
    return update_structured_note(
        db,
        existing,
        note,
        build_cpi_v1_payload(previous),
        "cpi",
        page_origins=page_origins,
        operation_fingerprint=operation_fingerprint,
    )


def delete_cpi_note(db: Any, note_id: Any, *, expected_snapshot=None) -> Any:
    """Delete only the observed CPI note, retaining shared resources and other formats."""
    existing = deepcopy(dict(expected_snapshot)) if expected_snapshot is not None else db.get_notebook_note_by_id(note_id)
    if existing is None:
        return None
    document = extract_cpi_document(existing)
    if str(existing["_id"]) != str(note_id):
        raise ValueError("The observed note identity does not match deletion")
    return delete_note_record(db, existing, asset_ids=cpi_document_image_ids(document))


def duplicate_cpi_note(
    db: Any,
    note_id: Any,
    metadata_overrides: Mapping[str, Any] | None = None,
    *, expected_snapshot=None, target_id=None, creation_fingerprint=None,
) -> Any:
    """Copy exact stored source and extensions, with optional idempotent HTTP identity."""
    existing = deepcopy(dict(expected_snapshot)) if expected_snapshot is not None else db.get_notebook_note_by_id(note_id)
    if existing is None:
        return None
    document = extract_cpi_document(existing)
    if str(existing["_id"]) != str(note_id):
        raise ValueError("The observed note identity does not match duplication")
    return duplicate_note_record(db, existing, metadata_overrides, target_id=target_id,
                                 fingerprint=creation_fingerprint, asset_ids=cpi_document_image_ids(document))


def list_cpi_notes(
    db: Any,
    query: Mapping[str, Any] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List CPI notes through MathMongo's existing query/list method."""
    notes = db.get_notebook_notes(query=_cpi_query(query), limit=limit)
    result = []
    for note in notes:
        document = extract_cpi_document(note)
        result.append(_canonical_note(note, document))
    return result

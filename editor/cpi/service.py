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
from editor.utils.media_assets import attach_media_assets_to_note
from editor.utils.media_assets import detach_media_assets_from_note_record


def _canonical_note(note: Mapping[str, Any], document: CpiDocument) -> dict[str, Any]:
    canonical = deepcopy(dict(note))
    canonical.update(build_cpi_v1_payload(document))
    return canonical


def _cpi_query(query: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not query:
        return {"note_format": CPI_NOTE_FORMAT}
    return {"$and": [{"note_format": CPI_NOTE_FORMAT}, deepcopy(dict(query))]}


def create_cpi_note(db: Any, metadata: Mapping[str, Any], document: CpiDocument) -> Any:
    """Create a CPI note using MathMongo's existing latex_notes CRUD."""
    note = build_cpi_note_document(metadata, document)
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
) -> Any:
    """Update an existing CPI note without converting other note formats."""
    existing = db.get_notebook_note_by_id(note_id)
    if existing is None:
        return None
    extract_cpi_document(existing)
    note = build_cpi_note_document(metadata, document)
    return db.update_notebook_note(note_id, note)


def delete_cpi_note(db: Any, note_id: Any) -> Any:
    """Delete an existing CPI note without deleting other note formats."""
    existing = db.get_notebook_note_by_id(note_id)
    if existing is None:
        return None
    document = extract_cpi_document(existing)
    result = db.delete_notebook_note(note_id)
    if int(getattr(result, "deleted_count", 0) or 0) == 1:
        detach_media_assets_from_note_record(
            db,
            note_id=str(note_id),
            asset_ids=cpi_document_image_ids(document),
        )
    return result


def duplicate_cpi_note(
    db: Any,
    note_id: Any,
    metadata_overrides: Mapping[str, Any] | None = None,
) -> Any:
    """Duplicate a CPI note while sharing portable media references safely."""
    existing = get_cpi_note(db, note_id)
    if existing is None:
        return None
    document = extract_cpi_document(existing)
    metadata = {
        field: deepcopy(existing[field])
        for field in ("title", "date", "project", "context", "tags")
        if field in existing
    }
    metadata["title"] = f"Copia de {metadata.get('title') or 'Nota CPI'}"
    metadata.update(deepcopy(dict(metadata_overrides or {})))
    result = create_cpi_note(db, metadata, document)
    inserted_id = getattr(result, "inserted_id", None)
    if inserted_id is not None:
        attach_media_assets_to_note(
            db,
            note_id=str(inserted_id),
            asset_ids=cpi_document_image_ids(document),
        )
    return result


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

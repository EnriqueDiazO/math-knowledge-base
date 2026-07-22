"""CRUD service layer for Cornell notes stored in latex_notes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from editor.cornell.media import cornell_document_image_ids
from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import build_cornell_math_v1_payload
from editor.cornell.persistence import build_cornell_note_document
from editor.cornell.persistence import extract_cornell_document
from editor.utils.media_assets import attach_media_assets_to_note
from editor.utils.media_assets import detach_media_assets_from_note_record
from editor.utils.media_assets import media_collection
from editor.utils.media_assets import save_media_asset


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
    document = extract_cornell_document(existing)
    result = db.delete_notebook_note(note_id)
    if int(getattr(result, "deleted_count", 0) or 0) == 1:
        detach_media_assets_from_note_record(
            db,
            note_id=str(note_id),
            asset_ids=cornell_document_image_ids(document),
        )
    return result


def duplicate_cornell_note(
    db: Any,
    note_id: Any,
    metadata_overrides: Mapping[str, Any] | None = None,
) -> Any:
    """Duplicate a Cornell note while sharing portable media references safely."""
    existing = get_cornell_note(db, note_id)
    if existing is None:
        return None
    document = extract_cornell_document(existing)
    metadata = {
        field: deepcopy(existing[field])
        for field in ("title", "date", "project", "context", "tags")
        if field in existing
    }
    metadata["title"] = f"Copia de {metadata.get('title') or 'Nota Cornell'}"
    metadata.update(deepcopy(dict(metadata_overrides or {})))
    result = create_cornell_note(db, metadata, document)
    inserted_id = getattr(result, "inserted_id", None)
    if inserted_id is not None:
        attach_media_assets_to_note(
            db,
            note_id=str(inserted_id),
            asset_ids=cornell_document_image_ids(document),
        )
    return result


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


def get_cornell_assets_by_ids(db: Any, image_ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    """Return media_assets documents for the given image_ids, preserving requested order."""
    clean_ids = [str(asset_id) for asset_id in image_ids if str(asset_id or "").strip()]
    if not clean_ids:
        return []
    assets = list(media_collection(db).find({"asset_id": {"$in": clean_ids}}))
    by_id = {str(asset.get("asset_id")): dict(asset) for asset in assets if asset.get("asset_id")}
    return [by_id[asset_id] for asset_id in clean_ids if asset_id in by_id]


def upload_cornell_region_image(
    db: Any,
    *,
    note_id: Any | None,
    filename: str,
    data: bytes,
    mime_type: str | None = None,
    tags: list[str] | None = None,
    description: str = "",
) -> dict[str, Any]:
    """Upload one Cornell image through the existing media_assets subsystem."""
    return save_media_asset(
        db,
        filename=filename,
        data=data,
        mime_type=mime_type,
        note_id=str(note_id) if note_id else None,
        tags=tags,
        description=description,
    )


def upload_cornell_watermark_image(
    db: Any,
    *,
    note_id: Any | None,
    filename: str,
    data: bytes,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Upload one optional Cornell watermark image through media_assets."""
    return save_media_asset(
        db,
        filename=filename,
        data=data,
        mime_type=mime_type,
        note_id=str(note_id) if note_id else None,
        tags=["cornell", "watermark"],
        description="Cornell watermark",
    )


def _region_with_image_ids(region: CornellRegion, image_ids: tuple[str, ...]) -> CornellRegion:
    return CornellRegion(
        heading=region.heading,
        latex=region.latex,
        image_ids=image_ids,
    )


def _page_with_region(page: CornellPage, region_name: str, region: CornellRegion) -> CornellPage:
    regions = {
        "cue": page.cue,
        "main": page.main,
        "summary": page.summary,
    }
    if region_name not in regions:
        raise ValueError(f"Unknown Cornell region: {region_name!r}")
    regions[region_name] = region
    return CornellPage(
        page_id=page.page_id,
        order=page.order,
        cue=regions["cue"],
        main=regions["main"],
        summary=regions["summary"],
        source_refs=page.source_refs,
    )


def update_cornell_region_image_ids(
    document: CornellDocument,
    *,
    page_index: int,
    region_name: str,
    image_ids: tuple[str, ...],
) -> CornellDocument:
    """Return a document with one region's image_ids replaced."""
    pages = list(document.ordered_pages())
    if not pages:
        raise ValueError("CornellDocument must contain at least one page")
    safe_index = min(max(page_index, 0), len(pages) - 1)
    page = pages[safe_index]
    region = getattr(page, region_name, None)
    if not isinstance(region, CornellRegion):
        raise ValueError(f"Unknown Cornell region: {region_name!r}")
    pages[safe_index] = _page_with_region(page, region_name, _region_with_image_ids(region, image_ids))
    return CornellDocument(
        schema_version=document.schema_version,
        template_id=document.template_id,
        pages=tuple(pages),
        attribution=document.attribution,
        watermark=document.watermark,
    )


def add_cornell_region_image(
    document: CornellDocument,
    *,
    page_index: int,
    region_name: str,
    asset_id: str,
) -> CornellDocument:
    """Associate an image asset with one Cornell region without duplicating IDs."""
    pages = document.ordered_pages()
    if not pages:
        raise ValueError("CornellDocument must contain at least one page")
    safe_index = min(max(page_index, 0), len(pages) - 1)
    region = getattr(pages[safe_index], region_name, None)
    if not isinstance(region, CornellRegion):
        raise ValueError(f"Unknown Cornell region: {region_name!r}")
    clean_id = str(asset_id or "").strip()
    if not clean_id:
        raise ValueError("asset_id cannot be empty")
    image_ids = list(region.image_ids)
    if clean_id not in image_ids:
        image_ids.append(clean_id)
    return update_cornell_region_image_ids(
        document,
        page_index=safe_index,
        region_name=region_name,
        image_ids=tuple(image_ids),
    )


def remove_cornell_region_image(
    document: CornellDocument,
    *,
    page_index: int,
    region_name: str,
    asset_id: str,
) -> CornellDocument:
    """Remove an image association from one Cornell region without deleting the asset."""
    pages = document.ordered_pages()
    if not pages:
        raise ValueError("CornellDocument must contain at least one page")
    safe_index = min(max(page_index, 0), len(pages) - 1)
    region = getattr(pages[safe_index], region_name, None)
    if not isinstance(region, CornellRegion):
        raise ValueError(f"Unknown Cornell region: {region_name!r}")
    clean_id = str(asset_id or "").strip()
    image_ids = tuple(image_id for image_id in region.image_ids if image_id != clean_id)
    return update_cornell_region_image_ids(
        document,
        page_index=safe_index,
        region_name=region_name,
        image_ids=image_ids,
    )

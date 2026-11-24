"""Canonical note copying and conditional deletion shared by academic formats."""

from copy import deepcopy

from pymongo.errors import DuplicateKeyError
from pymongo.results import InsertOneResult

from editor.utils.media_assets import attach_media_assets_to_note
from editor.utils.media_assets import detach_media_assets_from_note_record


def duplicate_note_record(
    db, original, metadata=None, *, target_id=None, fingerprint=None, asset_ids=()
):
    """Copy stored LaTeX/extensions verbatim; never regenerate a historical projection."""
    candidate = deepcopy(dict(original))
    for key in (
        "_id",
        "created_at",
        "updated_at",
        "seed_id",
        "study_create_fingerprint",
        "study_update_fingerprint",
        "study_copy_fingerprint",
        "study_copy_source",
    ):
        candidate.pop(key, None)
    candidate["title"] = "Copia de " + str(original.get("title") or "Nota")
    candidate.update(deepcopy(dict(metadata or {})))
    if target_id is not None:
        candidate["_id"] = target_id
        candidate["study_copy_source"] = str(original["_id"])
        candidate["study_copy_fingerprint"] = fingerprint
    try:
        result = db.create_notebook_note(candidate)
    except DuplicateKeyError:
        existing = db.get_notebook_note_by_id(target_id) if target_id is not None else None
        if existing is None or existing.get("study_copy_fingerprint") != fingerprint:
            raise
        result = InsertOneResult(existing["_id"], acknowledged=True)
    if getattr(result, "acknowledged", True):
        attach_media_assets_to_note(db, note_id=str(result.inserted_id), asset_ids=asset_ids)
    return result


def delete_note_record(db, original, *, asset_ids=None):
    """Delete only the observed note; cleanup is retryable and never purges asset bytes."""
    conditional = getattr(type(db), "delete_notebook_note_from_snapshot", None)
    result = (
        conditional(db, original)
        if callable(conditional)
        else db.delete_notebook_note(original["_id"])
    )
    if not getattr(result, "acknowledged", True):
        raise RuntimeError("The note deletion was not acknowledged")
    current = db.get_notebook_note_by_id(original["_id"])
    if current is not None:
        if current["_id"] == original["_id"]:
            raise ValueError("The observed note changed before deletion")
        # An ObjectId and a string may share their printable key in legacy data.
        # Its asset registry key is shared too; keep that remaining reference.
        return result
    detach_media_assets_from_note_record(db, note_id=str(original["_id"]), asset_ids=asset_ids)
    return result

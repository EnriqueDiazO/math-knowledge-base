from __future__ import annotations

import json
import logging
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict
from typing import TYPE_CHECKING

from bson import ObjectId
from bson.errors import InvalidId

from mathkb_config import DATA_DIR
from mathkb_config import IMPORT_COLLECTIONS
from mathkb_config import IMPORT_TIMEOUT_SECONDS
from mathkb_config import MEDIA_ASSETS_COLLECTION
from mathkb_config import MEDIA_ROOT
from mathmongo.paths import validate_mutable_path

if TYPE_CHECKING:
    from mathdatabase.mathmongo import MathMongo

logger = logging.getLogger(__name__)

DEFAULT_IMPORT_COLLECTIONS = list(IMPORT_COLLECTIONS)


def _raise_if_timed_out(started_at: float, timeout_seconds: int, operation: str) -> None:
    elapsed = time.monotonic() - started_at
    if elapsed > timeout_seconds:
        raise TimeoutError(
            f"Database import timed out after {timeout_seconds} seconds while {operation}. "
            "You can increase IMPORT_TIMEOUT_SECONDS."
        )


def _restore_mongo_id(doc: dict) -> dict:
    """Restore ObjectId values exported as strings for top-level document IDs."""
    if not isinstance(doc, dict):
        return doc

    doc = dict(doc)
    raw_id = doc.get("_id")
    if isinstance(raw_id, str):
        try:
            doc["_id"] = ObjectId(raw_id)
        except InvalidId:
            pass
    return doc

_DATETIME_FIELDS_BY_COLLECTION = {
    "concepts": (
        "fecha_creacion",
        "ultima_actualizacion",
    ),
    "latex_documents": (
        "fecha_creacion",
        "ultima_actualizacion",
    ),
    "worklog_entries": (
        "created_at",
        "updated_at",
    ),
    "backlog_items": (
        "created_at",
        "updated_at",
    ),
    "weekly_reviews": (
        "created_at",
        "updated_at",
    ),
    "deliverables": (
        "created_at",
        "updated_at",
    ),
    "latex_notes": (
        "created_at",
        "updated_at",
    ),
    "knowledge_graph_maps": (
        "created_at",
        "updated_at",
    ),
    MEDIA_ASSETS_COLLECTION: (
        "created_at",
        "updated_at",
    ),
}


_OBJECT_ID_FIELDS_BY_COLLECTION = {
    "worklog_entries": (
        "deliverable_id",
    ),
}


_OBJECT_ID_LIST_FIELDS_BY_COLLECTION = {
    "backlog_items": (
        "linked_worklog_ids",
        "linked_note_ids",
    ),
    "deliverables": (
        "linked_worklog_ids",
        "linked_note_ids",
    ),
}


def _restore_iso_datetime(
    value,
    *,
    collection_name: str,
    field_name: str,
):
    """Restore an ISO 8601 string exported from a MongoDB datetime."""
    if value is None or isinstance(value, datetime):
        return value

    if not isinstance(value, str):
        return value

    normalized = value.strip()

    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid ISO datetime in "
            f"{collection_name}.{field_name}: {value!r}"
        ) from exc


def _restore_object_id(value):
    """Restore an ObjectId exported as a string."""
    if value is None or isinstance(value, ObjectId):
        return value

    if not isinstance(value, str):
        return value

    try:
        return ObjectId(value)
    except InvalidId:
        return value


def _restore_mongo_types(doc: dict, collection_name: str) -> dict:
    """Restore MongoDB-specific types lost during JSON export."""
    doc = _restore_mongo_id(doc)

    if not isinstance(doc, dict):
        return doc

    for field_name in _DATETIME_FIELDS_BY_COLLECTION.get(
        collection_name,
        (),
    ):
        if field_name in doc:
            doc[field_name] = _restore_iso_datetime(
                doc[field_name],
                collection_name=collection_name,
                field_name=field_name,
            )

    for field_name in _OBJECT_ID_FIELDS_BY_COLLECTION.get(
        collection_name,
        (),
    ):
        if field_name in doc:
            doc[field_name] = _restore_object_id(
                doc[field_name]
            )

    for field_name in _OBJECT_ID_LIST_FIELDS_BY_COLLECTION.get(
        collection_name,
        (),
    ):
        values = doc.get(field_name)

        if isinstance(values, list):
            doc[field_name] = [
                _restore_object_id(value)
                for value in values
            ]

    return doc


def _safe_media_member_path(base_dir: str, member_name: str) -> Path | None:
    prefix = f"{base_dir}/{MEDIA_ROOT.as_posix()}/"
    if not member_name.startswith(prefix) or member_name.endswith("/"):
        return None
    rel_path = Path(member_name[len(base_dir) + 1 :])
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"Unsafe media path in export ZIP: {member_name}")
    return rel_path


def _same_bytes(path: Path, data: bytes) -> bool:
    return path.exists() and path.read_bytes() == data


def _unique_import_destination(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    stamp = int(time.time())
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}_imported_{stamp}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not allocate a unique import path for {path}")


def _remap_media_paths_in_value(value, path_remap: dict[str, str]):
    if not path_remap:
        return value
    if isinstance(value, str):
        text = value
        for old_path, new_path in path_remap.items():
            text = text.replace(old_path, new_path)
        return text
    if isinstance(value, list):
        return [_remap_media_paths_in_value(item, path_remap) for item in value]
    if isinstance(value, dict):
        return {key: _remap_media_paths_in_value(item, path_remap) for key, item in value.items()}
    return value


def inspect_export_zip(zip_path: Path) -> Dict:
    """
    Inspect a Math Knowledge Base export ZIP.

    Returns a dict with:
    - base_name
    - metadata
    - collections: {collection_name: count}
    """
    started_at = time.monotonic()
    logger.info("Inspecting database import ZIP: path=%s timeout=%ss", zip_path, IMPORT_TIMEOUT_SECONDS)
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Uploaded file is not a valid ZIP archive")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # Detect base directory
        base_dirs = {p.split("/")[0] for p in names if "/" in p}
        if len(base_dirs) != 1:
            raise ValueError("Invalid export format: ambiguous base directory")

        base_name = base_dirs.pop()

        metadata_path = f"{base_name}/metadata.json"
        if metadata_path not in names:
            raise ValueError("metadata.json not found in export")

        metadata = json.loads(zf.read(metadata_path).decode("utf-8"))

        collections = {}
        for name in names:
            _raise_if_timed_out(started_at, IMPORT_TIMEOUT_SECONDS, f"inspecting {name}")
            if name.startswith(f"{base_name}/") and name.endswith(".json"):
                coll = Path(name).stem
                if coll == "metadata":
                    continue
                docs = json.loads(zf.read(name).decode("utf-8"))
                collections[coll] = len(docs)
                logger.info("ZIP collection found: %s (%s documents)", coll, len(docs))

    duration = time.monotonic() - started_at
    logger.info("ZIP inspection completed: path=%s duration=%.2fs", zip_path, duration)
    return {
        "base_name": base_name,
        "metadata": metadata,
        "collections": collections,
        "duration_seconds": round(duration, 3),
    }


def import_zip_into_database(zip_path: Path, mongo: MathMongo) -> None:
    """Import a validated export ZIP into an existing MongoDB database.

    Assumes:
    - zip_path has been validated with inspect_export_zip
    - mongo points to a NEW database
    """
    started_at = time.monotonic()
    db = mongo.db
    logger.info(
        "Starting database import: zip=%s db=%s timeout=%ss",
        zip_path,
        getattr(db, "name", "<unknown>"),
        IMPORT_TIMEOUT_SECONDS,
    )

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            base_dirs = {p.split("/")[0] for p in names if "/" in p}
            if len(base_dirs) != 1:
                raise ValueError("Invalid export format: ambiguous base directory")
            base_dir = base_dirs.pop()

            path_remap: dict[str, str] = {}
            for name in names:
                rel_path = _safe_media_member_path(base_dir, name)
                if rel_path is None:
                    continue
                _raise_if_timed_out(started_at, IMPORT_TIMEOUT_SECONDS, f"restoring {rel_path}")
                data = zf.read(name)
                destination = validate_mutable_path(
                    DATA_DIR / rel_path,
                    allowed_root=DATA_DIR,
                )
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                destination.parent.chmod(0o700)
                if destination.exists() and not _same_bytes(destination, data):
                    destination = _unique_import_destination(destination)
                    path_remap[rel_path.as_posix()] = destination.relative_to(DATA_DIR).as_posix()
                destination = validate_mutable_path(destination, allowed_root=DATA_DIR)
                destination.write_bytes(data)
                logger.info("Restored media file: %s", destination)

            imported_collections = set()
            imported_counts = {}
            existing_collections = set(db.list_collection_names())
            for name in names:
                _raise_if_timed_out(started_at, IMPORT_TIMEOUT_SECONDS, f"reading {name}")
                if not name.startswith(f"{base_dir}/") or not name.endswith(".json"):
                    continue

                coll = Path(name).stem
                if coll == "metadata":
                    continue

                collection_started_at = time.monotonic()
                docs = json.loads(zf.read(name).decode("utf-8"))
                imported_collections.add(coll)
                if coll not in existing_collections:
                    db.create_collection(coll)
                    existing_collections.add(coll)

                for idx, doc in enumerate(docs, start=1):
                    if idx == 1 or idx % 100 == 0:
                        _raise_if_timed_out(
                            started_at,
                            IMPORT_TIMEOUT_SECONDS,
                            f"importing {coll}",
                        )
                    doc = _restore_mongo_types(doc, coll)
                    if (
                        coll == MEDIA_ASSETS_COLLECTION
                        and isinstance(doc, dict)
                        and doc.get("path") in path_remap
                    ):
                        doc["path"] = path_remap[doc["path"]]
                        doc["filename"] = Path(doc["path"]).name
                    if isinstance(doc, dict) and path_remap:
                        doc = _remap_media_paths_in_value(doc, path_remap)
                    if isinstance(doc, dict) and "_id" in doc:
                        db[coll].replace_one({"_id": doc["_id"]}, doc, upsert=True)
                    else:
                        db[coll].insert_one(doc)
                imported_counts[coll] = len(docs)
                logger.info(
                    "Imported collection %s: %s documents in %.2fs",
                    coll,
                    len(docs),
                    time.monotonic() - collection_started_at,
                )

            for coll in set(IMPORT_COLLECTIONS) - imported_collections:
                _raise_if_timed_out(started_at, IMPORT_TIMEOUT_SECONDS, f"creating {coll}")
                if coll not in existing_collections:
                    db.create_collection(coll)
                    existing_collections.add(coll)
                    logger.info("Created expected empty collection: %s", coll)

        logger.info(
            "Database import completed: zip=%s db=%s collections=%s duration=%.2fs",
            zip_path,
            getattr(db, "name", "<unknown>"),
            imported_counts,
            time.monotonic() - started_at,
        )
    except Exception:
        logger.exception(
            "Database import failed after %.2fs",
            time.monotonic() - started_at,
        )
        raise

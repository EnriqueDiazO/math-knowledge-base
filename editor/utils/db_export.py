import json
import logging
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path

from bson import ObjectId

from mathkb_config import EXPORT_COLLECTIONS
from mathkb_config import EXPORT_TIMEOUT_SECONDS
from mathkb_config import MEDIA_ROOT
from mathkb_config import PROJECT_ROOT


logger = logging.getLogger(__name__)

DEFAULT_EXPORT_COLLECTIONS = list(EXPORT_COLLECTIONS)


def _raise_if_timed_out(started_at: float, timeout_seconds: int, operation: str) -> None:
    elapsed = time.monotonic() - started_at
    if elapsed > timeout_seconds:
        raise TimeoutError(
            f"Database export timed out after {timeout_seconds} seconds while {operation}. "
            "You can increase EXPORT_TIMEOUT_SECONDS."
        )


def mongo_to_json_safe(obj):
    """
    Recursively convert MongoDB-specific types into JSON-serializable forms.

    - ObjectId   -> str
    - datetime   -> ISO 8601 string
    - dict/list  -> recursively processed
    """
    if isinstance(obj, dict):
        return {k: mongo_to_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [mongo_to_json_safe(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, ObjectId):
        return str(obj)
    else:
        return obj


def export_database_to_zip(mongo, out_dir: Path) -> Path:
    """
    Export the entire MongoDB database to a ZIP archive of JSON files.

    - Read-only
    - No schema assumptions
    - JSON-safe normalization (ObjectId, datetime, nested structures)

    Returns the path to the generated ZIP file.
    """
    started_at = time.monotonic()
    db = mongo.db

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = f"mathkb_export_{timestamp}"

    export_dir = out_dir / base_name
    export_dir.mkdir(parents=True, exist_ok=True)
    collections_dir = export_dir / "collections"
    collections_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Starting database export: db=%s out_dir=%s timeout=%ss",
        getattr(db, "name", "<unknown>"),
        out_dir,
        EXPORT_TIMEOUT_SECONDS,
    )

    metadata = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "timeout_seconds": EXPORT_TIMEOUT_SECONDS,
        "collections": {},
        "media_files": {},
    }

    try:
        # Export existing collections plus expected empty collections.
        collection_names = sorted(set(db.list_collection_names()) | set(EXPORT_COLLECTIONS))
        logger.info("Collections scheduled for export: %s", ", ".join(collection_names))
        for collection_name in collection_names:
            _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, f"reading {collection_name}")
            collection_started_at = time.monotonic()
            cursor = db[collection_name].find({}).max_time_ms(EXPORT_TIMEOUT_SECONDS * 1000)
            raw_docs = list(cursor)
            metadata["collections"][collection_name] = len(raw_docs)

            # Normalize documents to JSON-safe structures.
            docs = [mongo_to_json_safe(doc) for doc in raw_docs]

            with open(collections_dir / f"{collection_name}.json", "w", encoding="utf-8") as f:
                json.dump(docs, f, ensure_ascii=False, indent=2)
            logger.info(
                "Exported collection %s: %s documents in %.2fs",
                collection_name,
                len(raw_docs),
                time.monotonic() - collection_started_at,
            )

        _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, "copying media files")
        media_source = PROJECT_ROOT / MEDIA_ROOT
        media_export_dir = export_dir / MEDIA_ROOT
        if media_source.exists():
            shutil.copytree(media_source, media_export_dir, dirs_exist_ok=True)
            for media_file in media_export_dir.rglob("*"):
                if media_file.is_file():
                    rel_path = media_file.relative_to(export_dir).as_posix()
                    metadata["media_files"][rel_path] = media_file.stat().st_size
            logger.info(
                "Exported media directory %s with %s files",
                media_source,
                len(metadata["media_files"]),
            )

        _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, "writing metadata")
        metadata["duration_seconds"] = round(time.monotonic() - started_at, 3)
        with open(export_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, "creating ZIP archive")
        zip_path = out_dir / f"{base_name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in export_dir.rglob("*"):
                _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, f"zipping {path.name}")
                arcname = f"{base_name}/{path.relative_to(export_dir).as_posix()}"
                zf.write(path, arcname=arcname)

        logger.info(
            "Database export completed: zip=%s duration=%.2fs",
            zip_path,
            time.monotonic() - started_at,
        )
        return zip_path
    except Exception:
        logger.exception(
            "Database export failed after %.2fs",
            time.monotonic() - started_at,
        )
        raise

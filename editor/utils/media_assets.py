from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId

from mathkb_config import ALLOWED_IMAGE_EXTENSIONS
from mathkb_config import MAX_IMAGE_UPLOAD_BYTES
from mathkb_config import MEDIA_ASSETS_COLLECTION
from mathkb_config import MEDIA_IMAGES_DIR
from mathkb_config import MEDIA_ROOT
from mathkb_config import PROJECT_ROOT


LOCAL_MEDIA_ROOT = PROJECT_ROOT / MEDIA_ROOT
LOCAL_MEDIA_IMAGES_DIR = PROJECT_ROOT / MEDIA_IMAGES_DIR
LATEX_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
HEAVY_TIKZ_DRAW_THRESHOLD = 500
HEAVY_TIKZ_CONTROLS_THRESHOLD = 800
HEAVY_TIKZ_LINE_THRESHOLD = 1200


def concept_media_key(concept_id: str, source: str) -> str:
    return f"{concept_id}@{source}"


def note_media_key(note_id: str) -> str:
    return str(note_id or "").strip()


def ensure_media_dirs() -> None:
    LOCAL_MEDIA_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def mongo_database(db):
    return db if hasattr(db, "list_collection_names") else getattr(db, "db", db)


def media_collection(db):
    return mongo_database(db)[MEDIA_ASSETS_COLLECTION]


def _note_filter(note_id: str) -> dict:
    text_id = note_media_key(note_id)
    try:
        object_id = ObjectId(text_id)
    except (InvalidId, TypeError):
        return {"_id": text_id}
    return {"$or": [{"_id": object_id}, {"_id": text_id}]}


def relative_media_path(path: str | Path) -> str:
    return Path(path).as_posix().lstrip("/")


def _slug(value: str, fallback: str = "image") -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_value = re.sub(r"[^a-z0-9._ -]+", "_", ascii_value)
    ascii_value = re.sub(r"[\s-]+", "_", ascii_value)
    ascii_value = re.sub(r"_+", "_", ascii_value).strip("._ ")
    return ascii_value or fallback


def safe_media_filename(original_filename: str, asset_id: str) -> str:
    original = Path(original_filename or "image")
    suffix = original.suffix.lower()
    stem = _slug(original.stem, "image")
    return f"{stem}_{asset_id[:8]}{suffix}"


def validate_image_upload(filename: str, data: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(ALLOWED_IMAGE_EXTENSIONS)
        raise ValueError(f"Unsupported image extension {suffix!r}. Allowed: {allowed}.")
    if not data:
        raise ValueError("Image file is empty.")
    if len(data) > MAX_IMAGE_UPLOAD_BYTES:
        raise ValueError(
            f"Image is too large ({len(data)} bytes). "
            f"Maximum allowed size is {MAX_IMAGE_UPLOAD_BYTES} bytes."
        )
    return suffix


def _unique_destination(filename: str) -> Path:
    ensure_media_dirs()
    candidate = LOCAL_MEDIA_IMAGES_DIR / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(1, 1000):
        next_candidate = candidate.with_name(f"{stem}_{index}{suffix}")
        if not next_candidate.exists():
            return next_candidate
    raise FileExistsError(f"Could not allocate a unique media filename for {filename}.")


def save_media_asset(
    db,
    *,
    filename: str,
    data: bytes,
    mime_type: str | None = None,
    concept_id: str | None = None,
    source: str | None = None,
    note_id: str | None = None,
    tags: list[str] | None = None,
    description: str = "",
) -> dict:
    validate_image_upload(filename, data)
    asset_id = str(uuid4())
    safe_name = safe_media_filename(filename, asset_id)
    destination = _unique_destination(safe_name)
    destination.write_bytes(data)

    relative_path = relative_media_path(destination.relative_to(PROJECT_ROOT))
    now = datetime.utcnow()
    concept_key = concept_media_key(concept_id, source) if concept_id and source else None
    note_key = note_media_key(note_id) if note_id else None
    doc = {
        "asset_id": asset_id,
        "filename": destination.name,
        "original_filename": filename,
        "mime_type": mime_type or mimetypes.guess_type(destination.name)[0] or "application/octet-stream",
        "storage_type": "local",
        "path": relative_path,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "created_at": now,
        "updated_at": now,
        "concept_ids": [concept_key] if concept_key else [],
        "note_ids": [note_key] if note_key else [],
        "tags": tags or [],
        "description": description.strip(),
    }
    try:
        inserted = False
        mongo_db = mongo_database(db)
        media_col = media_collection(db)
        media_col.insert_one(doc)
        inserted = True
        if concept_key:
            mongo_db["concepts"].update_one(
                {"id": concept_id, "source": source},
                {"$addToSet": {"image_ids": asset_id}},
            )
        if note_key:
            mongo_db["latex_notes"].update_one(
                _note_filter(note_key),
                {"$addToSet": {"image_ids": asset_id}},
            )
    except Exception:
        if inserted:
            media_collection(db).delete_one({"asset_id": asset_id})
        if destination.exists():
            destination.unlink()
        raise
    return doc


def get_concept_media_assets(db, concept_id: str, source: str) -> list[dict]:
    mongo_db = mongo_database(db)
    concept = mongo_db["concepts"].find_one({"id": concept_id, "source": source}, {"image_ids": 1})
    image_ids = [i for i in (concept or {}).get("image_ids", []) if isinstance(i, str)]
    concept_key = concept_media_key(concept_id, source)
    query = {
        "$or": [
            {"concept_ids": concept_key},
            {"asset_id": {"$in": image_ids}},
        ]
    }
    return list(media_collection(db).find(query).sort("created_at", -1))


def get_note_media_assets(db, note_id: str) -> list[dict]:
    note_key = note_media_key(note_id)
    if not note_key:
        return []
    mongo_db = mongo_database(db)
    note = mongo_db["latex_notes"].find_one(_note_filter(note_key), {"image_ids": 1})
    image_ids = [i for i in (note or {}).get("image_ids", []) if isinstance(i, str)]
    or_terms: list[dict] = [{"note_ids": note_key}]
    if image_ids:
        or_terms.append({"asset_id": {"$in": image_ids}})
    return list(media_collection(db).find({"$or": or_terms}).sort("created_at", -1))


def _delete_local_asset_file(asset: dict) -> None:
    rel_path = asset.get("path") or ""
    target = PROJECT_ROOT / rel_path
    if not Path(rel_path).is_absolute() and ".." not in Path(rel_path).parts and target.exists():
        target.unlink()


def detach_media_asset_from_concept(
    db,
    *,
    asset_id: str,
    concept_id: str,
    source: str,
    delete_if_unreferenced: bool = False,
) -> bool:
    concept_key = concept_media_key(concept_id, source)
    mongo_db = mongo_database(db)
    mongo_db["concepts"].update_one(
        {"id": concept_id, "source": source},
        {"$pull": {"image_ids": asset_id}},
    )
    media_collection(db).update_one(
        {"asset_id": asset_id},
        {"$pull": {"concept_ids": concept_key}, "$set": {"updated_at": datetime.utcnow()}},
    )
    asset = media_collection(db).find_one({"asset_id": asset_id})
    if not asset:
        return False
    still_referenced = bool(asset.get("concept_ids") or asset.get("note_ids"))
    if delete_if_unreferenced and not still_referenced:
        _delete_local_asset_file(asset)
        media_collection(db).delete_one({"asset_id": asset_id})
        return True
    return False


def detach_media_asset_from_note(
    db,
    *,
    asset_id: str,
    note_id: str,
    delete_if_unreferenced: bool = False,
) -> bool:
    note_key = note_media_key(note_id)
    mongo_db = mongo_database(db)
    mongo_db["latex_notes"].update_one(
        _note_filter(note_key),
        {"$pull": {"image_ids": asset_id}},
    )
    media_collection(db).update_one(
        {"asset_id": asset_id},
        {"$pull": {"note_ids": note_key}, "$set": {"updated_at": datetime.utcnow()}},
    )
    asset = media_collection(db).find_one({"asset_id": asset_id})
    if not asset:
        return False
    still_referenced = bool(asset.get("concept_ids") or asset.get("note_ids"))
    if delete_if_unreferenced and not still_referenced:
        _delete_local_asset_file(asset)
        media_collection(db).delete_one({"asset_id": asset_id})
        return True
    return False


def media_path_exists(asset: dict) -> bool:
    rel_path = asset.get("path") or ""
    if Path(rel_path).is_absolute() or ".." in Path(rel_path).parts:
        return False
    return (PROJECT_ROOT / rel_path).exists()


def latex_includegraphics_snippet(
    asset: dict,
    *,
    caption: str = "",
    width: str = r"\textwidth",
) -> str:
    path = relative_media_path(asset.get("path") or "")
    label_stem = _slug(Path(path).stem, "image")
    lines = [
        r"\begin{figure}[ht]",
        r"\centering",
        rf"\includegraphics[width={width}]{{{path}}}",
    ]
    if caption.strip():
        lines.append(r"\caption{" + caption.strip() + "}")
    lines.extend([rf"\label{{fig:{label_stem}}}", r"\end{figure}"])
    return "\n".join(lines)


def html_image_snippet(asset: dict, *, alt: str = "") -> str:
    path = relative_media_path(asset.get("path") or "")
    alt_text = (alt or asset.get("description") or asset.get("filename") or "image").replace('"', "&quot;")
    return f'<img src="{path}" alt="{alt_text}" style="max-width: 100%; height: auto;">'


def markdown_image_snippet(asset: dict, *, alt: str = "") -> str:
    path = relative_media_path(asset.get("path") or "")
    alt_text = (alt or asset.get("description") or asset.get("filename") or "image").replace("]", "\\]")
    return f"![{alt_text}]({path})"


def copy_media_tree_for_latex(destination_dir: str | Path) -> None:
    source = LOCAL_MEDIA_ROOT
    if not source.exists():
        return
    destination_root = Path(destination_dir).resolve()
    templates_root = (PROJECT_ROOT / "templates_latex").resolve()
    if destination_root == templates_root or templates_root in destination_root.parents:
        raise ValueError(
            "Refusing to copy media into templates_latex. "
            "Use a temporary/build directory for LaTeX compilation."
        )
    destination = destination_root / MEDIA_ROOT
    shutil.copytree(source, destination, dirs_exist_ok=True)


def detect_heavy_tikz(latex: str) -> list[str]:
    text = latex or ""
    warnings = []
    draw_count = len(re.findall(r"\\draw\b", text))
    controls_count = text.count(".. controls")
    tikz_line_count = sum(1 for line in text.splitlines() if "\\draw" in line or "tikzpicture" in line)
    if draw_count >= HEAVY_TIKZ_DRAW_THRESHOLD:
        warnings.append(
            f"TikZ has {draw_count} draw commands; consider replacing the figure with an image asset."
        )
    if controls_count >= HEAVY_TIKZ_CONTROLS_THRESHOLD:
        warnings.append(
            f"TikZ has {controls_count} Bezier control segments; rasterizing to PNG/PDF may compile faster."
        )
    if tikz_line_count >= HEAVY_TIKZ_LINE_THRESHOLD:
        warnings.append(
            f"TikZ-like content spans {tikz_line_count} lines; heavy figures can exceed LaTeX timeouts."
        )
    return warnings

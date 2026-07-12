"""Central configuration for Math Knowledge Base / MathMongo."""

from __future__ import annotations

import os
from pathlib import Path

from mathmongo.paths import get_backups_dir
from mathmongo.paths import get_data_dir
from mathmongo.paths import get_exports_dir
from mathmongo.paths import get_graph_runtime_dir
from mathmongo.paths import get_legacy_project_root
from mathmongo.paths import get_logs_dir
from mathmongo.paths import get_media_dir
from mathmongo.paths import get_resource_root
from mathmongo.paths import get_runtime_dir


def _timeout_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer number of seconds; got {raw_value!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero; got {value}")
    return value


PDF_COMPILE_TIMEOUT_SECONDS = _timeout_from_env("PDF_COMPILE_TIMEOUT_SECONDS", 300)
LATEX_MAX_PASSES = _timeout_from_env("LATEX_MAX_PASSES", 4)
EXPORT_TIMEOUT_SECONDS = _timeout_from_env("EXPORT_TIMEOUT_SECONDS", 300)
IMPORT_TIMEOUT_SECONDS = _timeout_from_env("IMPORT_TIMEOUT_SECONDS", 300)
LATEX_LINTER_TIMEOUT_SECONDS = _timeout_from_env("LATEX_LINTER_TIMEOUT_SECONDS", 60)
MAX_IMAGE_UPLOAD_BYTES = _timeout_from_env("MAX_IMAGE_UPLOAD_BYTES", 10 * 1024 * 1024)

PROJECT_ROOT = get_resource_root()
LEGACY_PROJECT_ROOT = get_legacy_project_root()
DATA_DIR = get_data_dir()
RUNTIME_DIR = get_runtime_dir()
GRAPH_RUNTIME_DIR = get_graph_runtime_dir()
GRAPH_EXPORT_DIR = get_exports_dir() / "knowledge_graphs"
CLEANUP_BACKUP_DIR = get_backups_dir() / "cleanup"
CLEANUP_LOG_DIR = get_logs_dir()
CLEANUP_LOG_FILE = CLEANUP_LOG_DIR / "cleanup_exports.log"
MEDIA_ROOT = Path(os.getenv("MATHKB_MEDIA_ROOT", "media"))
MEDIA_IMAGES_DIR = MEDIA_ROOT / "images"
LOCAL_MEDIA_ROOT = get_media_dir()
LOCAL_MEDIA_IMAGES_DIR = LOCAL_MEDIA_ROOT / "images"
MEDIA_ASSETS_COLLECTION = "media_assets"
ALLOWED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg", ".pdf")

EXPORT_CLEANUP_DIRS = (
    get_exports_dir(),
    get_data_dir() / "projects",
)
GRAPH_CLEANUP_DIRS = (
    GRAPH_RUNTIME_DIR,
    GRAPH_EXPORT_DIR,
)
ALLOWED_CLEANUP_DIRS = EXPORT_CLEANUP_DIRS + GRAPH_CLEANUP_DIRS

CORE_COLLECTIONS = (
    "concepts",
    "relations",
    "latex_documents",
)

CUADERNO_COLLECTIONS = (
    "latex_notes",
    "worklog_entries",
    "backlog_items",
    "weekly_reviews",
    "deliverables",
)

GRAPH_COLLECTIONS = ("knowledge_graph_maps",)

MEDIA_COLLECTIONS = (MEDIA_ASSETS_COLLECTION,)

SOURCE_CATALOG_COLLECTIONS = (
    "sources",
    "references",
    "source_catalog_migration_manifest",
)

# Source Documents are portable domain data, but they are deliberately not part
# of the guarded Source Catalog migration collection set.
SOURCE_DOCUMENT_COLLECTIONS = ("source_documents",)
PORTABLE_EXTENDED_JSON_COLLECTIONS = (
    *SOURCE_CATALOG_COLLECTIONS,
    *SOURCE_DOCUMENT_COLLECTIONS,
)

EXPORT_COLLECTIONS = CORE_COLLECTIONS + GRAPH_COLLECTIONS + MEDIA_COLLECTIONS + CUADERNO_COLLECTIONS
IMPORT_COLLECTIONS = EXPORT_COLLECTIONS

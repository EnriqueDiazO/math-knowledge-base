"""Central configuration for Math Knowledge Base / MathMongo."""

from __future__ import annotations

import os
from pathlib import Path


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

PROJECT_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"
GRAPH_RUNTIME_DIR = RUNTIME_DIR / "knowledge_graphs"
GRAPH_EXPORT_DIR = PROJECT_ROOT / "exports" / "knowledge_graphs"
CLEANUP_BACKUP_DIR = RUNTIME_DIR / "cleanup_backups"
CLEANUP_LOG_DIR = RUNTIME_DIR / "logs"
CLEANUP_LOG_FILE = CLEANUP_LOG_DIR / "cleanup_exports.log"
MEDIA_ROOT = Path(os.getenv("MATHKB_MEDIA_ROOT", "media"))
MEDIA_IMAGES_DIR = MEDIA_ROOT / "images"
MEDIA_ASSETS_COLLECTION = "media_assets"
ALLOWED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg", ".pdf")

EXPORT_CLEANUP_DIRS = (
    PROJECT_ROOT / "exportados",
    PROJECT_ROOT / "exported",
    PROJECT_ROOT / "exported_notes",
    Path.home() / "math_knowledge_pdfs",
)
GRAPH_CLEANUP_DIRS = (
    GRAPH_RUNTIME_DIR,
    GRAPH_EXPORT_DIR,
)
ALLOWED_CLEANUP_DIRS = tuple(
    path.resolve() for path in EXPORT_CLEANUP_DIRS + GRAPH_CLEANUP_DIRS
)

for _generated_dir in (
    RUNTIME_DIR,
    GRAPH_RUNTIME_DIR,
    GRAPH_EXPORT_DIR,
    CLEANUP_BACKUP_DIR,
    CLEANUP_LOG_DIR,
):
    _generated_dir.mkdir(parents=True, exist_ok=True)

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

GRAPH_COLLECTIONS = (
    "knowledge_graph_maps",
)

MEDIA_COLLECTIONS = (
    MEDIA_ASSETS_COLLECTION,
)

EXPORT_COLLECTIONS = CORE_COLLECTIONS + GRAPH_COLLECTIONS + MEDIA_COLLECTIONS + CUADERNO_COLLECTIONS
IMPORT_COLLECTIONS = EXPORT_COLLECTIONS

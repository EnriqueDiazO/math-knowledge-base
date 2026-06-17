"""Safe cleanup helpers for generated export and graph files."""

from __future__ import annotations

import os
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any

from mathkb_config import ALLOWED_CLEANUP_DIRS
from mathkb_config import CLEANUP_BACKUP_DIR
from mathkb_config import CLEANUP_LOG_FILE
from mathkb_config import EXPORT_CLEANUP_DIRS
from mathkb_config import GRAPH_RUNTIME_DIR
from mathkb_config import PROJECT_ROOT


TEMP_FILE_SUFFIXES = {
    ".aux",
    ".log",
    ".out",
    ".toc",
    ".fls",
    ".fdb_latexmk",
    ".synctex.gz",
    ".tmp",
    ".bak",
}
TEMP_DIR_NAMES = {"_build", "__pycache__"}
EXPORT_FILE_SUFFIXES = {".pdf", ".html", ".json", ".zip", ".tex"}
PRESERVED_FILENAMES = {".gitkeep"}
LEGACY_ROOT_GRAPH_PATTERNS = (
    "knowledge_graph_saved_*.html",
    "knowledge_graph_state_*.json",
    "knowledge_graph_current_*.html",
    "knowledge_graph.html",
    "relation_preview_graph.html",
    "relation_preview.json",
)


def _resolve_path(path: Path | str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _allowed_roots() -> tuple[Path, ...]:
    return tuple(_resolve_path(path) for path in ALLOWED_CLEANUP_DIRS)


def _allowed_root_for_path(path: Path | str) -> Path | None:
    resolved = _resolve_path(path)
    for root in _allowed_roots():
        if resolved == root or resolved.is_relative_to(root):
            return root
    return None


def validate_cleanup_path(path: Path | str) -> bool:
    """Return True only for root directories explicitly allowed for cleanup."""
    return _resolve_path(path) in _allowed_roots()


def _validate_cleanup_target(path: Path | str) -> tuple[Path | None, str | None]:
    resolved = _resolve_path(path)
    root = _allowed_root_for_path(resolved)
    if root is None:
        return None, f"Ruta no permitida: {resolved}"
    if resolved == root:
        return None, f"No se permite borrar la carpeta raíz protegida: {resolved}"
    return root, None


def _iter_directory(path: Path):
    if not path.exists() or not path.is_dir():
        return
    for root, dirnames, filenames in os.walk(path, followlinks=False):
        root_path = Path(root)
        for dirname in dirnames:
            yield root_path / dirname
        for filename in filenames:
            yield root_path / filename


def _path_size(path: Path) -> int:
    try:
        if path.is_dir() and not path.is_symlink():
            return sum(_path_size(child) for child in path.iterdir())
        return path.lstat().st_size
    except OSError:
        return 0


def _path_counts(path: Path) -> tuple[int, int, int]:
    files = 0
    dirs = 0
    size = 0
    try:
        if path.is_dir() and not path.is_symlink():
            dirs += 1
            for child in path.iterdir():
                child_files, child_dirs, child_size = _path_counts(child)
                files += child_files
                dirs += child_dirs
                size += child_size
        else:
            files += 1
            size += path.lstat().st_size
    except OSError:
        return files, dirs, size
    return files, dirs, size


def format_bytes(size: int | float | None) -> str:
    """Format a byte count for Streamlit tables and log messages."""
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _format_timestamp(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def get_directory_stats(path: Path | str) -> dict[str, Any]:
    """Return file counts, size, extensions, and preview data for one directory."""
    target = _resolve_path(path)
    stats: dict[str, Any] = {
        "path": str(target),
        "exists": target.exists(),
        "allowed": validate_cleanup_path(target),
        "files": 0,
        "subdirs": 0,
        "total_bytes": 0,
        "total_size": "0 B",
        "newest_mtime": None,
        "newest_file": "",
        "newest_modified": "",
        "extensions": {},
        "preview": [],
    }
    if not target.exists() or not target.is_dir():
        return stats

    extensions: Counter[str] = Counter()
    newest_mtime = 0.0
    newest_file = ""
    preview: list[str] = []

    for item in _iter_directory(target):
        try:
            stat = item.lstat()
        except OSError:
            continue
        relative = item.relative_to(target).as_posix()
        if item.is_dir() and not item.is_symlink():
            stats["subdirs"] += 1
            continue
        stats["files"] += 1
        stats["total_bytes"] += stat.st_size
        suffix = "".join(item.suffixes[-2:]).lower() if item.name.endswith(".synctex.gz") else item.suffix.lower()
        if suffix:
            extensions[suffix] += 1
        if stat.st_mtime > newest_mtime:
            newest_mtime = stat.st_mtime
            newest_file = relative
        if len(preview) < 20 and item.name not in PRESERVED_FILENAMES:
            preview.append(relative)

    stats["total_size"] = format_bytes(stats["total_bytes"])
    stats["newest_mtime"] = newest_mtime or None
    stats["newest_file"] = newest_file
    stats["newest_modified"] = _format_timestamp(newest_mtime)
    stats["extensions"] = dict(sorted(extensions.items()))
    stats["preview"] = preview
    return stats


def scan_cleanup_dirs(paths: list[Path] | tuple[Path, ...] | None = None) -> list[dict[str, Any]]:
    """Scan configured cleanup directories without deleting or moving files."""
    targets = list(paths or EXPORT_CLEANUP_DIRS)
    results = [get_directory_stats(path) for path in targets]
    for result in results:
        _log_cleanup_action(
            "scan",
            result["path"],
            {
                "deleted_files": 0,
                "deleted_dirs": 0,
                "bytes_freed": 0,
                "errors": [],
                "message": f"{result['files']} files | {result['total_size']}",
            },
        )
    return results


def _is_temp_file(path: Path) -> bool:
    lowered_name = path.name.lower()
    if lowered_name in PRESERVED_FILENAMES:
        return False
    if lowered_name.endswith("~"):
        return True
    if lowered_name.endswith(".synctex.gz"):
        return True
    return path.suffix.lower() in TEMP_FILE_SUFFIXES


def _is_export_file(path: Path) -> bool:
    if path.name in PRESERVED_FILENAMES:
        return False
    return path.suffix.lower() in EXPORT_FILE_SUFFIXES


def _collapse_nested_targets(paths: list[Path]) -> list[Path]:
    resolved_paths = sorted({_resolve_path(path) for path in paths}, key=lambda item: len(item.parts))
    collapsed: list[Path] = []
    for path in resolved_paths:
        if any(path != parent and path.is_relative_to(parent) for parent in collapsed):
            continue
        collapsed.append(path)
    return collapsed


def list_deletable_files(
    path: Path | str,
    mode: str,
    older_than_days: int | None = None,
) -> list[Path]:
    """List cleanup candidates for a safe root and mode."""
    root = _resolve_path(path)
    if not validate_cleanup_path(root) or not root.exists() or not root.is_dir():
        return []

    candidates: list[Path] = []
    if mode == "all":
        return [
            child
            for child in sorted(root.iterdir(), key=lambda item: item.name.lower())
            if child.name not in PRESERVED_FILENAMES
        ]

    cutoff = None
    if mode == "old_exports":
        days = int(older_than_days or 30)
        cutoff = time() - (days * 24 * 60 * 60)

    for current_root, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(current_root)
        if mode == "temp":
            matched_dirs = [dirname for dirname in dirnames if dirname in TEMP_DIR_NAMES]
            for dirname in matched_dirs:
                candidates.append(current / dirname)
                dirnames.remove(dirname)
            for filename in filenames:
                candidate = current / filename
                if _is_temp_file(candidate):
                    candidates.append(candidate)
        elif mode == "old_exports":
            for filename in filenames:
                candidate = current / filename
                if not _is_export_file(candidate):
                    continue
                try:
                    if cutoff is not None and candidate.lstat().st_mtime < cutoff:
                        candidates.append(candidate)
                except OSError:
                    continue
        else:
            raise ValueError(f"Modo de limpieza desconocido: {mode}")

    return _collapse_nested_targets(candidates)


def _backup_destination(path: Path, root: Path, backup_dir: Path) -> Path:
    relative = path.relative_to(root)
    destination = backup_dir / root.name / relative
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent
    for index in range(1, 1000):
        candidate = parent / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"No se pudo crear destino único para respaldo: {destination}")


def _new_backup_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = CLEANUP_BACKUP_DIR / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def delete_files_safely(
    files: list[Path],
    *,
    move_to_backup: bool = False,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    """Delete or move candidate paths after validating each target."""
    result: dict[str, Any] = {
        "deleted_files": 0,
        "deleted_dirs": 0,
        "moved_files": 0,
        "moved_dirs": 0,
        "bytes_freed": 0,
        "errors": [],
        "backup_dir": str(backup_dir) if backup_dir else "",
    }
    targets = _collapse_nested_targets(files)
    if move_to_backup and backup_dir is None:
        backup_dir = _new_backup_dir()
        result["backup_dir"] = str(backup_dir)

    for target in targets:
        root, error = _validate_cleanup_target(target)
        if error or root is None:
            result["errors"].append(error or f"Ruta no permitida: {target}")
            continue
        if not target.exists() and not target.is_symlink():
            continue

        files_count, dirs_count, bytes_count = _path_counts(target)
        try:
            if move_to_backup:
                assert backup_dir is not None
                destination = _backup_destination(target, root, backup_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(destination))
                result["moved_files"] += files_count
                result["moved_dirs"] += dirs_count
            elif target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
                result["deleted_files"] += files_count
                result["deleted_dirs"] += dirs_count
            else:
                target.unlink()
                result["deleted_files"] += files_count
            result["bytes_freed"] += bytes_count
        except Exception as exc:
            result["errors"].append(f"{target}: {exc}")

    action = "backup" if move_to_backup else "delete"
    _log_cleanup_action(action, f"{len(targets)} targets", result)
    return result


def empty_directory_contents_safely(
    path: Path | str,
    *,
    move_to_backup: bool = False,
) -> dict[str, Any]:
    """Remove contents inside an allowed cleanup root without removing the root."""
    root = _resolve_path(path)
    if not validate_cleanup_path(root):
        return {
            "deleted_files": 0,
            "deleted_dirs": 0,
            "moved_files": 0,
            "moved_dirs": 0,
            "bytes_freed": 0,
            "errors": [f"Ruta no permitida: {root}"],
            "backup_dir": "",
        }
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        return {
            "deleted_files": 0,
            "deleted_dirs": 0,
            "moved_files": 0,
            "moved_dirs": 0,
            "bytes_freed": 0,
            "errors": [],
            "backup_dir": "",
        }
    targets = [
        child
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower())
        if child.name not in PRESERVED_FILENAMES
    ]
    result = delete_files_safely(targets, move_to_backup=move_to_backup)
    root.mkdir(parents=True, exist_ok=True)
    return result


def cleanup_old_graph_runtime_files(max_age_hours: int = 24) -> dict[str, Any]:
    """Delete old generated graph runtime HTML/JSON files."""
    cutoff = time() - (int(max_age_hours) * 60 * 60)
    candidates = []
    if GRAPH_RUNTIME_DIR.exists():
        for item in GRAPH_RUNTIME_DIR.iterdir():
            if item.name in PRESERVED_FILENAMES or not item.is_file():
                continue
            if item.suffix.lower() not in {".html", ".json"}:
                continue
            try:
                if item.lstat().st_mtime < cutoff:
                    candidates.append(item)
            except OSError:
                continue
    return delete_files_safely(candidates)


def find_legacy_root_graph_files() -> list[Path]:
    """Find known graph artifacts that older versions wrote into PROJECT_ROOT."""
    files: list[Path] = []
    for pattern in LEGACY_ROOT_GRAPH_PATTERNS:
        for path in PROJECT_ROOT.glob(pattern):
            if path.is_file():
                files.append(path)
    return sorted(set(files), key=lambda item: item.name.lower())


def move_legacy_root_graph_files_to_runtime() -> dict[str, Any]:
    """Move legacy root graph artifacts into runtime/knowledge_graphs/legacy."""
    legacy_dir = GRAPH_RUNTIME_DIR / "legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "deleted_files": 0,
        "deleted_dirs": 0,
        "moved_files": 0,
        "moved_dirs": 0,
        "bytes_freed": 0,
        "errors": [],
        "backup_dir": str(legacy_dir),
    }
    for path in find_legacy_root_graph_files():
        try:
            size = path.lstat().st_size
            destination = legacy_dir / path.name
            if destination.exists():
                stem = path.stem
                suffix = path.suffix
                for index in range(1, 1000):
                    candidate = legacy_dir / f"{stem}_{index}{suffix}"
                    if not candidate.exists():
                        destination = candidate
                        break
            shutil.move(str(path), str(destination))
            result["moved_files"] += 1
            result["bytes_freed"] += size
        except Exception as exc:
            result["errors"].append(f"{path}: {exc}")
    _log_cleanup_action("move_legacy_graphs", str(PROJECT_ROOT), result)
    return result


def _log_cleanup_action(action: str, target: str, result: dict[str, Any]) -> None:
    try:
        CLEANUP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        deleted = result.get("deleted_files", 0)
        moved = result.get("moved_files", 0)
        dirs = result.get("deleted_dirs", 0) + result.get("moved_dirs", 0)
        size = format_bytes(result.get("bytes_freed", 0))
        errors = len(result.get("errors", []))
        message = result.get("message", "")
        line = (
            f"{timestamp} | {action} | {target} | files={deleted + moved} | "
            f"dirs={dirs} | size={size} | errors={errors}"
        )
        if message:
            line += f" | {message}"
        with CLEANUP_LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass

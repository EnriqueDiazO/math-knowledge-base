"""Explicit copy-only migration from historical MathMongo filesystem paths."""

# ruff: noqa: D101,D103

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path

from mathmongo.config import load_config
from mathmongo.paths import find_symlink_component
from mathmongo.paths import get_backups_dir
from mathmongo.paths import get_data_dir
from mathmongo.paths import get_exports_dir
from mathmongo.paths import get_home_dir
from mathmongo.paths import get_legacy_project_root
from mathmongo.paths import get_state_dir
from mathmongo.paths import validate_mutable_path

EXCLUDED_NAMES = {
    ".cache",
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "cache",
    "caches",
    "dist",
    "env",
    "mathdbmongo",
    "node_modules",
    "runtime",
    "venv",
}
EXCLUDED_SUFFIXES = {
    ".acn",
    ".acr",
    ".alg",
    ".aux",
    ".bak",
    ".bbl",
    ".bcf",
    ".blg",
    ".dvi",
    ".fdb_latexmk",
    ".fls",
    ".glg",
    ".glo",
    ".gls",
    ".idx",
    ".ilg",
    ".ind",
    ".ist",
    ".lof",
    ".log",
    ".lot",
    ".nav",
    ".out",
    ".pyc",
    ".run.xml",
    ".snm",
    ".swo",
    ".swp",
    ".synctex.gz",
    ".tmp",
    ".toc",
    ".vrb",
    ".xdv",
}


@dataclass
class MigrationRecord:
    source: str
    destination: str
    status: str
    size: int = 0
    sha256: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migration_roots(environment: Mapping[str, str] | None = None) -> list[tuple[Path, Path]]:
    """Return conservative persistent-data roots; regenerable runtime is omitted."""
    legacy = get_legacy_project_root(environment)
    home = get_home_dir(environment)
    config = load_config(environment)
    exports = get_exports_dir(environment, configured=config.export_directory)
    return [
        (legacy / "media", get_data_dir(environment) / "media"),
        (legacy / "exported_notes", exports / "legacy_notes"),
        (legacy / "exported", exports / "legacy_exported"),
        (legacy / "exportados", exports / "legacy_exportados"),
        (legacy / "data", get_data_dir(environment) / "projects" / "legacy_sources"),
        (legacy / "plantillas", get_data_dir(environment) / "user_templates" / "plantillas"),
        (legacy / "md_files", get_data_dir(environment) / "user_templates" / "md_files"),
        (legacy / "reports", get_state_dir(environment) / "reports" / "legacy"),
        (legacy / "quarto_book_build", exports / "quarto_legacy"),
        (legacy / "exports" / "knowledge_graphs", exports / "knowledge_graphs"),
        (legacy / "runtime" / "cornell_exports", get_data_dir(environment) / "projects" / "cornell"),
        (legacy / "runtime" / "cpi_exports", get_data_dir(environment) / "projects" / "cpi"),
        (legacy / "runtime" / "cleanup_backups", get_backups_dir(environment) / "cleanup_legacy"),
        (legacy / "runtime" / "knowledge_graphs" / "legacy", get_data_dir(environment) / "graphs" / "legacy"),
        (home / "math_knowledge_pdfs", exports / "legacy_concept_pdfs"),
        (home / "mathkb_backups", get_backups_dir(environment) / "legacy"),
    ]


def _excluded(relative: Path) -> bool:
    normalized_parts = tuple(part.casefold() for part in relative.parts)
    if any(part in EXCLUDED_NAMES for part in normalized_parts):
        return True
    if any("preview" in part for part in normalized_parts):
        return True
    if any(
        part.startswith(("cache-", "cache_"))
        or part.endswith(("-cache", "_cache", ".cache"))
        for part in normalized_parts
    ):
        return True
    filename = relative.name.casefold()
    if filename.endswith("~"):
        return True
    return any(filename.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)


def _destination_status(
    destination: Path,
    destination_root: Path,
    size: int,
    source_hash: str,
) -> str:
    try:
        destination = validate_mutable_path(destination, allowed_root=destination_root)
    except ValueError:
        return "conflict"
    if not destination.exists():
        return "copy"
    if destination.is_file() and destination.stat().st_size == size and _sha256(destination) == source_hash:
        return "verified"
    return "conflict"


def _inside_python_virtualenv(source: Path, source_root: Path) -> bool:
    directory = source.parent
    while source_root == directory or source_root in directory.parents:
        if (directory / "pyvenv.cfg").is_file():
            return True
        if directory == source_root:
            break
        directory = directory.parent
    return False


def _coalesce_destination_records(records: list[MigrationRecord]) -> list[MigrationRecord]:
    by_destination: dict[str, list[MigrationRecord]] = {}
    for record in records:
        by_destination.setdefault(record.destination, []).append(record)

    conflicting_destinations = {
        destination
        for destination, destination_records in by_destination.items()
        if len({(record.size, record.sha256) for record in destination_records}) > 1
    }
    emitted_destinations: set[str] = set()
    for record in records:
        if record.destination in conflicting_destinations:
            record.status = "conflict"
        elif record.destination in emitted_destinations:
            if record.status in {"copy", "verified"}:
                record.status = "duplicate"
        else:
            emitted_destinations.add(record.destination)
    return records


def plan_migration(environment: Mapping[str, str] | None = None) -> list[MigrationRecord]:
    records: list[MigrationRecord] = []
    for source_root, destination_root in migration_roots(environment):
        if find_symlink_component(source_root) is not None or not source_root.is_dir():
            continue
        for source in sorted(source_root.rglob("*")):
            if find_symlink_component(source) is not None or not source.is_file():
                continue
            relative = source.relative_to(source_root)
            if _excluded(relative) or _inside_python_virtualenv(source, source_root):
                continue
            destination = destination_root / relative
            size = source.stat().st_size
            source_hash = _sha256(source)
            status = _destination_status(destination, destination_root, size, source_hash)
            records.append(
                MigrationRecord(str(source), str(destination), status, size, source_hash)
            )
    legacy = get_legacy_project_root(environment)
    graph_destination = get_data_dir(environment) / "graphs" / "legacy"
    graph_patterns = (
        "knowledge_graph_saved_*.html",
        "knowledge_graph_state_*.json",
        "knowledge_graph_current_*.html",
        "knowledge_graph.html",
    )
    if find_symlink_component(legacy) is None:
        for pattern in graph_patterns:
            for source in sorted(legacy.glob(pattern)):
                if (
                    find_symlink_component(source) is not None
                    or not source.is_file()
                    or _excluded(Path(source.name))
                ):
                    continue
                destination = graph_destination / source.name
                size = source.stat().st_size
                source_hash = _sha256(source)
                status = _destination_status(destination, graph_destination, size, source_hash)
                records.append(MigrationRecord(str(source), str(destination), status, size, source_hash))
    return _coalesce_destination_records(records)


def _validated_destination(
    destination: Path,
    environment: Mapping[str, str] | None,
) -> Path:
    roots = (
        get_data_dir(environment),
        get_state_dir(environment),
        get_exports_dir(
            environment,
            configured=load_config(environment).export_directory,
        ),
    )
    for root in roots:
        if destination == root or destination.is_relative_to(root):
            return validate_mutable_path(destination, allowed_root=root)
    raise ValueError(f"Migration destination is outside controlled user roots: {destination}")


def migrate_copy(environment: Mapping[str, str] | None = None) -> tuple[list[MigrationRecord], Path]:
    """Copy new files, verify them, retain sources, and write a resumable manifest."""
    records = plan_migration(environment)
    state_dir = get_state_dir(environment)
    manifest_dir = validate_mutable_path(
        state_dir / "migrations",
        allowed_root=state_dir,
    )
    manifest = validate_mutable_path(
        manifest_dir / "xdg-migration-v1.json",
        allowed_root=manifest_dir,
    )
    for record in records:
        if record.status != "copy":
            continue
        source = Path(record.source)
        destination = _validated_destination(Path(record.destination), environment)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.parent.chmod(0o700)
        with source.open("rb") as source_handle, destination.open("xb") as destination_handle:
            shutil.copyfileobj(source_handle, destination_handle)
        shutil.copystat(source, destination, follow_symlinks=False)
        if destination.stat().st_size != record.size or _sha256(destination) != record.sha256:
            raise OSError(f"Verification failed after copying {source}")
        record.status = "copied"

    manifest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest_dir.chmod(0o700)
    manifest = validate_mutable_path(manifest, allowed_root=manifest_dir)
    payload = {
        "version": 1,
        "policy": "copy-verify-preserve-source",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "records": [asdict(record) for record in records],
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest.chmod(0o600)
    return records, manifest


def _print_records(records: list[MigrationRecord]) -> None:
    if not records:
        print("No se detectaron archivos históricos persistentes para migrar.")
        return
    for record in records:
        print(f"{record.status:9} {record.source} -> {record.destination}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migra archivos históricos a XDG sin borrarlos.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true", help="Mostrar el plan sin escribir.")
    action.add_argument("--copy", action="store_true", help="Copiar, verificar y conservar origen.")
    action.add_argument("--status", action="store_true", help="Mostrar estado sin escribir.")
    parser.add_argument("--legacy-root", help="Checkout histórico explícito que se debe inspeccionar.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    environment = None
    if args.legacy_root:
        import os

        environment = dict(os.environ)
        environment["MATHMONGO_LEGACY_ROOT"] = args.legacy_root
    try:
        if args.copy:
            records, manifest = migrate_copy(environment)
            _print_records(records)
            print(f"Manifest: {manifest}")
        else:
            _print_records(plan_migration(environment))
    except (OSError, ValueError) as exc:
        print(f"Error de migración: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

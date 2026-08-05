"""Verified, non-destructive backup helpers for MathMongo teaching releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps
from bson.json_util import loads as bson_json_loads

from editor.utils.db_export import export_database_to_zip
from editor.utils.db_import import import_zip_into_database
from editor.utils.db_import import inspect_export_zip
from mathmongo.config import AppConfig
from mathmongo.config import active_database_diagnostic
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error
from mathmongo.paths import get_backups_dir
from mathmongo.paths import validate_mutable_path

BACKUP_FORMAT = "mathmongo_verified_backup_v1"
MANIFEST_SUFFIX = ".manifest.json"
_SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
_SYSTEM_DATABASES = frozenset({"admin", "config", "local"})
_COLLECTION_OPTION_KEYS = (
    "validator",
    "validationAction",
    "validationLevel",
    "validationTimeoutMS",
)
_INDEX_OPTION_KEYS = (
    "unique",
    "sparse",
    "expireAfterSeconds",
    "partialFilterExpression",
    "collation",
    "hidden",
)


class BackupError(RuntimeError):
    """Raised when a backup cannot be proven complete or safe to restore."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_member_inventory(path: Path) -> dict[str, dict[str, int | str]]:
    inventory: dict[str, dict[str, int | str]] = {}
    with zipfile.ZipFile(path, "r") as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            data = archive.read(info)
            inventory[info.filename] = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
    return inventory


def _collection_options(raw: Mapping[str, Any]) -> dict[str, Any]:
    options = raw.get("options", {})
    if not isinstance(options, Mapping):
        return {}
    normalized = {key: options[key] for key in _COLLECTION_OPTION_KEYS if key in options}
    if "validator" in normalized:
        normalized.setdefault("validationAction", "error")
        normalized.setdefault("validationLevel", "strict")
    return normalized


def _index_spec(raw: Mapping[str, Any]) -> dict[str, Any]:
    key = raw.get("key", {})
    items = key.items() if isinstance(key, Mapping) else key
    return {
        "name": str(raw.get("name") or ""),
        "key": [[str(field), direction] for field, direction in items],
        "options": {key: raw[key] for key in _INDEX_OPTION_KEYS if key in raw},
    }


def database_structure(database: Any) -> dict[str, Any]:
    """Capture collection counts, index definitions and validators without writing."""
    try:
        collections = list(database.list_collections())
    except Exception as exc:
        raise BackupError(f"Could not inspect MongoDB collections: {exc}") from exc
    rows: dict[str, Any] = {}
    for raw in sorted(collections, key=lambda item: str(item.get("name") or "")):
        name = str(raw.get("name") or "")
        if not name or name.startswith("system."):
            continue
        collection = database[name]
        try:
            indexes = [_index_spec(item) for item in collection.list_indexes()]
            count = collection.count_documents({})
        except Exception as exc:
            raise BackupError(f"Could not inspect collection {name!r}: {exc}") from exc
        rows[name] = {
            "count": int(count),
            "options": _collection_options(raw),
            "indexes": sorted(indexes, key=lambda item: item["name"]),
        }
    return rows


def _restore_structure(
    source_structure: Mapping[str, Any],
    archive_counts: Mapping[str, Any],
) -> dict[str, Any]:
    """Represent empty project collections materialized by the portable importer."""
    restored = {str(name): value for name, value in source_structure.items()}
    for name, count in archive_counts.items():
        if name not in restored and count == 0:
            restored[str(name)] = {
                "count": 0,
                "options": {},
                "indexes": [{"name": "_id_", "key": [["_id", 1]], "options": {}}],
            }
    return restored


def _git_head() -> str:
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unavailable"
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "unavailable"


def _server_facts(client: Any) -> dict[str, str]:
    facts: dict[str, str] = {}
    try:
        build = client.admin.command("buildInfo")
        if build.get("version"):
            facts["mongodb_server"] = str(build["version"])
    except Exception:
        pass
    try:
        fcv = client.admin.command({"getParameter": 1, "featureCompatibilityVersion": 1})
        value = fcv.get("featureCompatibilityVersion", {})
        if isinstance(value, Mapping) and value.get("version"):
            facts["mongodb_fcv"] = str(value["version"])
    except Exception:
        pass
    return facts


def _manifest_path(archive_path: Path) -> Path:
    return archive_path.with_suffix(MANIFEST_SUFFIX)


def _write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    target = validate_mutable_path(path, allowed_root=path.parent)
    target.write_text(
        bson_json_dumps(manifest, json_options=CANONICAL_JSON_OPTIONS, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    target.chmod(0o600)


def _read_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = Path(path)
    try:
        payload = bson_json_loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise BackupError("Backup manifest could not be read.") from exc
    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        raise BackupError("Backup manifest has an unsupported format.")
    return manifest_path, payload


def create_verified_backup(
    mongo: Any,
    output_directory: str | Path,
    *,
    config: AppConfig | None = None,
) -> tuple[Path, Path]:
    """Export one database and write a separate manifest with structural proof."""
    database = getattr(mongo, "db", None)
    if database is None or not hasattr(database, "list_collections"):
        raise BackupError("Verified backup requires an explicit MongoDB database handle.")
    database_name = str(getattr(database, "name", "") or "")
    if not database_name:
        raise BackupError("Verified backup requires a named MongoDB database.")
    output_root = validate_mutable_path(output_directory)
    output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_root.chmod(0o700)

    before = database_structure(database)
    archive_path = export_database_to_zip(mongo, output_root)
    archive_path = validate_mutable_path(archive_path, allowed_root=output_root)
    after = database_structure(database)
    archive_inspection = inspect_export_zip(archive_path)
    archive_counts = archive_inspection.get("collections", {})
    live_counts = {name: item["count"] for name, item in after.items()}
    archive_has_live_counts = all(archive_counts.get(name) == count for name, count in live_counts.items())
    archive_only_counts_are_empty = all(
        count == 0 for name, count in archive_counts.items() if name not in live_counts
    )
    if before != after or not archive_has_live_counts or not archive_only_counts_are_empty:
        raise BackupError(
            "Backup source changed while exporting or the archive collection inventory is incomplete."
        )

    settings = config or resolve_config()
    client = getattr(mongo, "client", None)
    manifest = {
        "format": BACKUP_FORMAT,
        "source": {
            **active_database_diagnostic(settings),
            "database": database_name,
        },
        "toolchain": {
            "git_head": _git_head(),
            "python": platform.python_version(),
            "pymongo": _pymongo_version(),
            **(_server_facts(client) if client is not None else {}),
        },
        "archive": {
            "filename": archive_path.name,
            "sha256": _sha256_file(archive_path),
            "size_bytes": archive_path.stat().st_size,
            "members": _zip_member_inventory(archive_path),
        },
        "archive_collection_counts": archive_counts,
        "database_structure": after,
        "restore_structure": _restore_structure(after, archive_counts),
    }
    manifest_path = _manifest_path(archive_path)
    _write_manifest(manifest_path, manifest)
    return archive_path, manifest_path


def _pymongo_version() -> str:
    try:
        import pymongo

        return str(pymongo.version)
    except Exception:
        return "unavailable"


def verify_backup(manifest_path: str | Path) -> dict[str, Any]:
    """Verify archive bytes, member hashes and metadata without touching MongoDB."""
    path, manifest = _read_manifest(manifest_path)
    archive = manifest.get("archive")
    if not isinstance(archive, Mapping):
        raise BackupError("Backup manifest has no archive identity.")
    filename = archive.get("filename")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise BackupError("Backup manifest archive filename is unsafe.")
    archive_path = path.parent / filename
    if not archive_path.is_file() or archive_path.is_symlink():
        raise BackupError("Backup archive is missing or unsafe.")
    if archive.get("sha256") != _sha256_file(archive_path):
        raise BackupError("Backup archive SHA-256 does not match its manifest.")
    if archive.get("size_bytes") != archive_path.stat().st_size:
        raise BackupError("Backup archive size does not match its manifest.")
    members = archive.get("members")
    if not isinstance(members, Mapping) or _zip_member_inventory(archive_path) != dict(members):
        raise BackupError("Backup archive member inventory does not match its manifest.")
    inspection = inspect_export_zip(archive_path)
    expected_counts = manifest.get("archive_collection_counts")
    if not isinstance(expected_counts, Mapping):
        raise BackupError("Backup manifest has no archive collection inventory.")
    if inspection.get("collections") != expected_counts:
        raise BackupError("Backup archive collection counts do not match its structural manifest.")
    structure = manifest.get("database_structure")
    if not isinstance(structure, Mapping):
        raise BackupError("Backup manifest has no database structure.")
    return {
        "archive_path": archive_path,
        "database_name": manifest["source"]["database"],
        "collections": expected_counts,
        "members": len(members),
    }


def _validate_restore_target(source_database: str, target_database: str) -> str:
    target = str(target_database or "").strip()
    if not _SAFE_DATABASE_NAME.fullmatch(target):
        raise BackupError("Restore target database name is invalid.")
    if target.casefold() in _SYSTEM_DATABASES:
        raise BackupError("Restore target database is protected.")
    if target.casefold() == "mathv0":
        raise BackupError("Restore never targets MathV0; choose a new database name.")
    if target.casefold() == source_database.casefold():
        raise BackupError("Restore target must differ from the backup source database.")
    return target


def _apply_structure(database: Any, structure: Mapping[str, Any]) -> None:
    """Apply validators and indexes only after a new database received archive data."""
    for name, expected in structure.items():
        if not isinstance(name, str) or name.startswith("system.") or not isinstance(expected, Mapping):
            raise BackupError("Backup manifest declares an unsafe collection structure.")
        if name not in database.list_collection_names():
            database.create_collection(name)
        options = expected.get("options", {})
        if isinstance(options, Mapping) and options:
            database.command({"collMod": name, **dict(options)})
        for index in expected.get("indexes", []):
            if not isinstance(index, Mapping) or index.get("name") == "_id_":
                continue
            key = index.get("key")
            if not isinstance(key, list) or not key:
                raise BackupError("Backup manifest has an invalid index key.")
            options = index.get("options", {})
            database[name].create_index(
                [(str(field), direction) for field, direction in key],
                name=str(index.get("name") or ""),
                **(dict(options) if isinstance(options, Mapping) else {}),
            )


def compare_database_structure(database: Any, expected: Mapping[str, Any]) -> dict[str, Any]:
    """Return structural differences without modifying the inspected database."""
    observed = database_structure(database)
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    differences = {
        name: {"expected": expected[name], "observed": observed[name]}
        for name in sorted(set(expected) & set(observed))
        if expected[name] != observed[name]
    }
    return {"matches": not missing and not unexpected and not differences, "missing": missing, "unexpected": unexpected, "differences": differences}


def restore_to_new_database(
    manifest_path: str | Path,
    *,
    target_database: str,
    mongo_uri: str | None = None,
) -> dict[str, Any]:
    """Restore a verified archive only into a previously absent non-MathV0 database."""
    verification = verify_backup(manifest_path)
    _, manifest = _read_manifest(manifest_path)
    source = manifest["source"]
    source_database = str(source["database"])
    target = _validate_restore_target(source_database, target_database)
    settings = resolve_config()
    uri = mongo_uri or settings.mongo_uri
    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            if target in client.list_database_names():
                raise BackupError("Restore target database already exists.")
            target_handle = client[target]
            mongo = SimpleNamespace(db=target_handle, client=client)
            report = import_zip_into_database(verification["archive_path"], mongo, new_database=True)
            restore_structure = manifest.get("restore_structure", manifest["database_structure"])
            if not isinstance(restore_structure, Mapping):
                raise BackupError("Backup manifest has an invalid restore structure.")
            _apply_structure(target_handle, restore_structure)
            comparison = compare_database_structure(target_handle, restore_structure)
            if not comparison["matches"]:
                raise BackupError("Restored database does not match indexes or validators in the manifest.")
            return {
                "target_database": target,
                "imported_counts": dict(report.imported_counts),
                "structure_matches": True,
            }
        finally:
            client.close()
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(sanitize_mongo_error(exc, uri)) from exc


def backup_from_config(output_directory: str | Path | None = None) -> tuple[Path, Path]:
    """Create a backup of the explicitly configured database."""
    settings = resolve_config()
    uri = settings.mongo_uri
    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            return create_verified_backup(
                SimpleNamespace(db=client[settings.mongo_database], client=client),
                output_directory or get_backups_dir(),
                config=settings,
            )
        finally:
            client.close()
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError(sanitize_mongo_error(exc, uri)) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m mathmongo.backup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup", help="Create a verified backup of the configured database.")
    backup.add_argument("--output-dir", type=Path)
    verify = subparsers.add_parser("verify-backup", help="Verify a backup manifest and archive hashes.")
    verify.add_argument("manifest", type=Path)
    restore = subparsers.add_parser("restore-to-new-database", help="Restore only to a new non-MathV0 database.")
    restore.add_argument("manifest", type=Path)
    restore.add_argument("--target-database", required=True)
    restore.add_argument("--mongo-uri")
    doctor = subparsers.add_parser("doctor-backup", help="Summarize a verified backup without connecting to MongoDB.")
    doctor.add_argument("manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the verified backup commands with credential-safe errors."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "backup":
            archive, manifest = backup_from_config(args.output_dir)
            print(f"Backup: {archive}")
            print(f"Manifest: {manifest}")
        elif args.command in {"verify-backup", "doctor-backup"}:
            result = verify_backup(args.manifest)
            print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
        else:
            result = restore_to_new_database(
                args.manifest,
                target_database=args.target_database,
                mongo_uri=args.mongo_uri,
            )
            print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    except BackupError as exc:
        print(f"Backup error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())

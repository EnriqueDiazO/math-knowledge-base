"""Read-only diagnostics and explicit bootstrap for teaching-only MongoDB targets."""

from __future__ import annotations

import argparse
import json
import platform
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mathmongo.config import AppConfig
from mathmongo.config import active_database_diagnostic
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error
from mathmongo.paths import get_data_dir
from mathmongo.paths import get_media_dir
from mathmongo.paths import get_source_document_blobs_dir
from mathmongo.reading_space.indexes import ReadingSpaceIndexManager
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_documents.indexes import SOURCE_DOCUMENT_INDEXES
from mathmongo.source_documents.indexes import SourceDocumentIndexManager
from mathmongo.source_documents.models import SHA256_RE

PRODUCT_REQUIRED_COLLECTIONS = frozenset(
    {
        "latex_notes",
        "media_assets",
        "sources",
        "references",
        "source_documents",
        "document_reading_state",
    }
)
BOOTSTRAP_COLLECTIONS = ("sources", "references", "source_documents", "document_reading_state")
_SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,63}$")


class DoctorError(RuntimeError):
    """Raised when a diagnostic or bootstrap target is unsafe."""


def _safe_server_facts(client: Any) -> dict[str, str]:
    facts = {"python": platform.python_version()}
    try:
        import pymongo

        facts["pymongo"] = str(pymongo.version)
    except Exception:
        facts["pymongo"] = "unavailable"
    try:
        build = client.admin.command("buildInfo")
        facts["mongodb_server"] = str(build.get("version") or "unknown")
    except Exception:
        facts["mongodb_server"] = "unavailable"
    try:
        response = client.admin.command({"getParameter": 1, "featureCompatibilityVersion": 1})
        value = response.get("featureCompatibilityVersion", {})
        facts["mongodb_fcv"] = str(value.get("version") if isinstance(value, Mapping) else "unknown")
    except Exception:
        facts["mongodb_fcv"] = "unavailable"
    return facts


def _file_count(root: Path, suffix: str | None = None) -> int:
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and (suffix is None or path.suffix == suffix))


def _physical_pdf_blob_hashes(root: Path) -> set[str]:
    """Return canonical PDF blob hashes without opening the private files."""
    if not root.is_dir():
        return set()
    return {
        path.stem
        for path in root.rglob("*.pdf")
        if path.is_file() and SHA256_RE.fullmatch(path.stem)
    }


def _metadata_pdf_hashes(documents: Any | None) -> set[str]:
    """Read only PDF identities from metadata; tolerate incomplete legacy collections."""
    find = getattr(documents, "find", None)
    if not callable(find):
        return set()
    hashes: set[str] = set()
    for item in find({"kind": "pdf"}, {"pdf.versions.sha256": 1}):
        pdf = item.get("pdf") if isinstance(item, Mapping) else None
        versions = pdf.get("versions", ()) if isinstance(pdf, Mapping) else ()
        for version in versions:
            sha256 = version.get("sha256") if isinstance(version, Mapping) else None
            if isinstance(sha256, str) and SHA256_RE.fullmatch(sha256):
                hashes.add(sha256)
    return hashes


def _collection_indexes(database: Any, names: set[str]) -> dict[str, list[str]]:
    indexes: dict[str, list[str]] = {}
    for name in sorted(names):
        try:
            indexes[name] = sorted(str(item.get("name") or "") for item in database[name].list_indexes())
        except Exception:
            indexes[name] = []
    return indexes


def _source_document_index_plan(database: Any) -> dict[str, list[str]]:
    names = set(database.list_collection_names())
    existing = {
        str(item.get("name") or ""): item
        for item in (database["source_documents"].list_indexes() if "source_documents" in names else ())
    }
    present: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []
    for spec in SOURCE_DOCUMENT_INDEXES:
        candidate = existing.get(spec.name)
        if candidate is None:
            missing.append(spec.name)
            continue
        key = candidate.get("key", {})
        keys = tuple(key.items()) if hasattr(key, "items") else tuple(key)
        partial_filter = candidate.get("partialFilterExpression")
        if (
            tuple(keys) == spec.keys
            and bool(candidate.get("unique", False)) is spec.unique
            and partial_filter == spec.partial_filter
        ):
            present.append(spec.name)
        else:
            conflicts.append(spec.name)
    return {"present": present, "missing": missing, "conflicts": conflicts}


def doctor_report(
    database: Any,
    *,
    config: AppConfig,
    client: Any | None = None,
) -> dict[str, Any]:
    """Inspect availability without creating collections, files, indexes or validators."""
    names = set(database.list_collection_names())
    collection_rows = {
        name: {
            "count": int(database[name].count_documents({})),
            "validator_present": bool(item.get("options", {}).get("validator")),
        }
        for item in database.list_collections()
        if (name := str(item.get("name") or "")) and not name.startswith("system.")
    }
    source_plan = SourceCatalogIndexManager(database).plan()
    reading_plan = ReadingSpaceIndexManager(database).plan()
    documents = database["source_documents"] if "source_documents" in names else None
    pdf_metadata = int(documents.count_documents({"kind": "pdf"})) if documents is not None else 0
    physical_pdf_hashes = _physical_pdf_blob_hashes(get_source_document_blobs_dir())
    metadata_pdf_hashes = _metadata_pdf_hashes(documents)
    present_validators = sorted(
        name
        for name, row in collection_rows.items()
        if row["validator_present"]
    )
    report = {
        "identity": {**active_database_diagnostic(config), "database": str(database.name)},
        "server": _safe_server_facts(client) if client is not None else {},
        "collections": collection_rows,
        "required_collections": {
            "present": sorted(PRODUCT_REQUIRED_COLLECTIONS & names),
            "missing": sorted(PRODUCT_REQUIRED_COLLECTIONS - names),
        },
        "indexes": _collection_indexes(database, names),
        "validators": {
            "present": present_validators,
            "missing": [],
            "note": (
                "No MongoDB validator definition is maintained for the additive "
                "Source Catalog, Source Documents or Reading Space bootstrap."
            ),
        },
        "source_catalog": {
            "available": {"sources", "references"}.issubset(names),
            "missing_indexes": [spec.name for spec in source_plan.missing],
            "index_conflicts": [item.spec.name for item in source_plan.conflicts],
        },
        "source_documents": {
            "available": "source_documents" in names,
            "pdf_metadata": pdf_metadata,
            "physical_pdf_blobs": len(physical_pdf_hashes),
            "blobs_without_metadata": len(physical_pdf_hashes - metadata_pdf_hashes),
            "metadata_without_blobs": len(metadata_pdf_hashes - physical_pdf_hashes),
            "index_plan": _source_document_index_plan(database),
        },
        "reading_space": {
            "available": "document_reading_state" in names,
            "missing_indexes": [spec.name for spec in reading_plan.missing],
            "index_conflicts": [item.spec.name for item in reading_plan.conflicts],
        },
        "media": {
            "registered_assets": int(database["media_assets"].count_documents({}))
            if "media_assets" in names
            else 0,
            "physical_files": _file_count(get_media_dir()),
        },
        "xdg": {
            "data_root": str(get_data_dir()),
            "media_root": str(get_media_dir()),
            "source_blob_root": str(get_source_document_blobs_dir()),
        },
    }
    return report


def bootstrap_plan(database: Any) -> dict[str, Any]:
    """Return the known additive operations without performing them."""
    names = set(database.list_collection_names())
    source_plan = SourceCatalogIndexManager(database).plan()
    reading_plan = ReadingSpaceIndexManager(database).plan()
    document_plan = _source_document_index_plan(database)
    create_collections = [name for name in BOOTSTRAP_COLLECTIONS if name not in names]
    source_indexes = [spec.name for spec in source_plan.missing]
    source_index_operations = [
        {"action": "create_index", "collection": spec.collection, "index": spec.name}
        for spec in source_plan.missing
    ]
    document_indexes = document_plan["missing"]
    reading_indexes = [spec.name for spec in reading_plan.missing]
    return {
        "operations": (
            [{"action": "create_collection", "collection": name} for name in create_collections]
            + source_index_operations
            + [{"action": "create_index", "collection": "source_documents", "index": name} for name in document_indexes]
            + [{"action": "create_index", "collection": "document_reading_state", "index": name} for name in reading_indexes]
        ),
        "create_collections": create_collections,
        "source_catalog_indexes": source_indexes,
        "source_catalog_conflicts": [item.spec.name for item in source_plan.conflicts],
        "source_document_indexes": {**document_plan, "missing": document_indexes},
        "reading_space_indexes": reading_indexes,
        "reading_space_conflicts": [item.spec.name for item in reading_plan.conflicts],
    }


def _validate_bootstrap_target(database: Any, confirmed_database: str) -> str:
    name = str(getattr(database, "name", "") or "")
    if not _SAFE_DATABASE_NAME.fullmatch(name):
        raise DoctorError("Bootstrap target database name is invalid.")
    if name.casefold() == "mathv0":
        raise DoctorError("Bootstrap is intentionally blocked for MathV0 during this release preparation.")
    if confirmed_database != name:
        raise DoctorError("Bootstrap requires an exact --confirm-database value.")
    return name


def apply_bootstrap(database: Any, *, confirmed_database: str) -> dict[str, Any]:
    """Create only approved collections and indexes after an exact target confirmation."""
    _validate_bootstrap_target(database, confirmed_database)
    plan = bootstrap_plan(database)
    conflicts = (
        plan["source_catalog_conflicts"]
        + plan["source_document_indexes"]["conflicts"]
        + plan["reading_space_conflicts"]
    )
    if conflicts:
        raise DoctorError("Bootstrap found index conflicts: " + ", ".join(conflicts))
    for name in plan["create_collections"]:
        database.create_collection(name)
    SourceCatalogIndexManager(database).apply()
    SourceDocumentIndexManager(database).ensure()
    ReadingSpaceIndexManager(database).apply()
    return bootstrap_plan(database)


def doctor_from_config() -> dict[str, Any]:
    """Connect explicitly for a read-only report and close the client promptly."""
    settings = resolve_config()
    try:
        from pymongo import MongoClient

        client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            return doctor_report(client[settings.mongo_database], config=settings, client=client)
        finally:
            client.close()
    except DoctorError:
        raise
    except Exception as exc:
        raise DoctorError(sanitize_mongo_error(exc, settings.mongo_uri)) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m mathmongo.doctor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Read-only Source, PDF and Reading Space diagnostic.")
    bootstrap = subparsers.add_parser("bootstrap", help="Plan or apply additive structures to one explicit new target.")
    bootstrap.add_argument("--database", required=True)
    bootstrap.add_argument("--confirm-database", required=True)
    bootstrap.add_argument("--apply", action="store_true", help="Apply the displayed additive plan.")
    bootstrap.add_argument("--dry-run", action="store_true", help="Display the additive plan without writing (the default).")
    bootstrap.add_argument("--mongo-uri")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run diagnostic and bootstrap commands with safe messages."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor_from_config()
        else:
            settings = resolve_config(explicit={"mongo_database": args.database, "mongo_uri": args.mongo_uri})
            from pymongo import MongoClient

            client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
            try:
                database = client[settings.mongo_database]
                _validate_bootstrap_target(database, args.confirm_database)
                result = apply_bootstrap(database, confirmed_database=args.confirm_database) if args.apply else bootstrap_plan(database)
            finally:
                client.close()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except DoctorError as exc:
        print(f"Doctor error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Doctor error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

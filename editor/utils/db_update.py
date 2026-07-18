"""Plan and apply non-destructive updates to existing MathMongo databases."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from enum import Enum
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps
from bson.json_util import loads as bson_json_loads
from pymongo.errors import DuplicateKeyError

from editor.utils import db_import
from editor.utils.db_export import export_database_to_zip
from mathkb_config import DOCUMENT_PAGE_MAP_COLLECTIONS
from mathkb_config import MEDIA_ASSETS_COLLECTION
from mathkb_config import PORTABLE_EXTENDED_JSON_COLLECTIONS
from mathkb_config import READING_ANNOTATION_COLLECTIONS
from mathkb_config import SOURCE_CATALOG_COLLECTIONS
from mathmongo.document_page_maps.indexes import DocumentPageMapIndexManager
from mathmongo.document_page_maps.models import DocumentPageMap
from mathmongo.paths import get_backups_dir
from mathmongo.paths import validate_mutable_path
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import ReadingNote
from mathmongo.reading_space.indexes import ReadingSpaceIndexManager
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.manifest import MigrationManifest
from mathmongo.source_catalog_migration.zip_reader import FileIdentity
from mathmongo.source_catalog_migration.zip_reader import ZipSafetyLimits
from mathmongo.source_catalog_migration.zip_reader import ZipValidationError
from mathmongo.source_catalog_migration.zip_reader import _read_member
from mathmongo.source_catalog_migration.zip_reader import identify_input
from mathmongo.source_catalog_migration.zip_reader import verify_input_unchanged
from mathmongo.source_documents.indexes import SourceDocumentIndexManager
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.storage import PreparedPdf
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from schemas.schemas import ConceptoBase
from schemas.schemas import DocumentoLatex

PROTECTED_UPDATE_DATABASES = frozenset({"admin", "config", "local"})
GENERIC_COLLECTION_LABEL = "colección no administrada"
JSON_ENCODING = "json_utf8"
EXTENDED_JSON_ENCODING = db_import.CATALOG_EXTENDED_JSON_ENCODING
SUPPORTED_COLLECTION_ENCODINGS = frozenset({JSON_ENCODING, EXTENDED_JSON_ENCODING})

_SAFE_COLLECTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,119}$")
_SUPPORTED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

_PORTABLE_MODELS: dict[str, type[Any]] = {
    "sources": Source,
    "references": Reference,
    "source_documents": SourceDocument,
    "document_reading_state": DocumentReadingState,
    "document_page_maps": DocumentPageMap,
    "document_annotations": DocumentAnnotation,
    "reading_notes": ReadingNote,
    "concept_evidence_links": ConceptEvidenceLink,
}

# These are the identities already enforced by repositories or unique indexes.
# Collections without another declared unique contract retain MongoDB's `_id`.
_PRIMARY_IDENTITIES: dict[str, tuple[str, ...]] = {
    "concepts": ("id", "source"),
    "relations": ("desde", "hasta", "tipo"),
    "latex_documents": ("id", "source"),
    "media_assets": ("asset_id",),
    "sources": ("source_id",),
    "references": ("reference_id",),
    MANIFEST_COLLECTION: ("manifest_key",),
    "source_documents": ("document_id",),
    "document_reading_state": ("reading_state_id",),
    "document_page_maps": ("page_map_id",),
    "document_annotations": ("annotation_id",),
    "reading_notes": ("note_id",),
    "concept_evidence_links": ("evidence_link_id",),
    "weekly_reviews": ("iso_year", "iso_week"),
}

_KNOWN_COLLECTIONS = frozenset(
    {
        "concepts",
        "relations",
        "latex_documents",
        "knowledge_graph_maps",
        "media_assets",
        "latex_notes",
        "worklog_entries",
        "backlog_items",
        "weekly_reviews",
        "deliverables",
        *PORTABLE_EXTENDED_JSON_COLLECTIONS,
    }
)

_DEPENDENCY_ORDER = (
    "sources",
    "references",
    "concepts",
    "latex_documents",
    "media_assets",
    "source_documents",
    "document_reading_state",
    "document_page_maps",
    "document_annotations",
    "reading_notes",
    "concept_evidence_links",
    "relations",
    MANIFEST_COLLECTION,
)


class UpdateStrategy(str, Enum):
    """Supported non-deleting update policies."""

    SAFE_MERGE = "safe_merge"
    BACKUP_WINS = "backup_wins"
    KEEP_CURRENT = "keep_current"


class ConflictPolicy(str, Enum):
    """One explicit decision for one conflicting identity."""

    KEEP_CURRENT = "keep_current"
    USE_BACKUP = "use_backup"


class DocumentClassification(str, Enum):
    """Dry-run classification for one archive document."""

    IDENTICAL = "identical"
    INSERT = "insert"
    CONFLICT = "conflict"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class UpdateIssue:
    collection: str
    token: str
    reason: str


@dataclass(frozen=True, slots=True)
class DocumentAction:
    collection: str
    classification: DocumentClassification
    token: str
    identity_query: Mapping[str, Any] = field(repr=False)
    match_query: Mapping[str, Any] = field(repr=False)
    incoming: Mapping[str, Any] = field(repr=False)
    existing: Mapping[str, Any] | None = field(default=None, repr=False)
    managed: bool = True
    replace_allowed: bool = True


@dataclass(frozen=True, slots=True)
class CollectionUpdatePlan:
    name: str
    current_documents: int
    backup_documents: int
    identical: int
    new: int
    conflicts: int
    invalid: int
    managed: bool
    proposed_action: str


@dataclass(frozen=True, slots=True)
class BlobUpdatePlan:
    prepared: PreparedPdf = field(repr=False)
    exists: bool


@dataclass(frozen=True, slots=True)
class MediaUpdatePlan:
    relative_path: Path
    destination: Path = field(repr=False)
    data: bytes = field(repr=False)
    exists: bool


@dataclass(frozen=True, slots=True)
class DatabaseUpdatePlan:
    """Immutable result of validating and comparing one update archive."""

    target_database: str
    strategy: UpdateStrategy
    archive_sha256: str
    archive_database: str | None
    collection_plans: tuple[CollectionUpdatePlan, ...]
    actions: tuple[DocumentAction, ...] = field(repr=False)
    blocking_issues: tuple[UpdateIssue, ...]
    warnings: tuple[str, ...]
    blob_plans: tuple[BlobUpdatePlan, ...] = field(repr=False)
    media_plans: tuple[MediaUpdatePlan, ...] = field(repr=False)
    fingerprint: str
    analyzed_at: datetime

    @property
    def conflicts(self) -> tuple[DocumentAction, ...]:
        """Return document actions that require an explicit conflict policy."""
        return tuple(
            action
            for action in self.actions
            if action.classification is DocumentClassification.CONFLICT
        )

    @property
    def can_apply(self) -> bool:
        """Report whether validation found no blocking issue."""
        return not self.blocking_issues

    @property
    def totals(self) -> dict[str, int]:
        """Aggregate per-collection and portable-file plan counts."""
        return {
            "current": sum(item.current_documents for item in self.collection_plans),
            "backup": sum(item.backup_documents for item in self.collection_plans),
            "identical": sum(item.identical for item in self.collection_plans),
            "new": sum(item.new for item in self.collection_plans),
            "conflicts": sum(item.conflicts for item in self.collection_plans),
            "invalid": sum(item.invalid for item in self.collection_plans),
            "blobs_new": sum(not item.exists for item in self.blob_plans),
            "blobs_existing": sum(item.exists for item in self.blob_plans),
            "media_new": sum(not item.exists for item in self.media_plans),
            "media_existing": sum(item.exists for item in self.media_plans),
        }


@dataclass(frozen=True, slots=True)
class AppliedOperation:
    kind: str
    collection: str | None = None
    query: Mapping[str, Any] | None = field(default=None, repr=False)
    before: Mapping[str, Any] | None = field(default=None, repr=False)
    after: Mapping[str, Any] | None = field(default=None, repr=False)
    path: Path | None = field(default=None, repr=False)
    data: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class DatabaseUpdateReport:
    """Summary of a fully applied and post-validated database update."""

    target_database: str
    backup_path: Path
    inserted: int
    identical: int
    conflicts_preserved: int
    replaced: int
    blobs_created: int
    blobs_identical: int
    media_created: int
    media_identical: int
    unmanaged_collections: tuple[str, ...]
    operations: tuple[AppliedOperation, ...] = field(repr=False)


class StaleUpdatePlanError(RuntimeError):
    """The archive or destination changed after the dry-run."""


class DatabaseUpdateApplyError(RuntimeError):
    """An apply failed after a validated backup was created."""

    def __init__(
        self,
        message: str,
        *,
        target_database: str,
        backup_path: Path,
        operations: tuple[AppliedOperation, ...],
    ) -> None:
        """Attach the validated backup and operation journal to the failure."""
        super().__init__(message)
        self.target_database = target_database
        self.backup_path = backup_path
        self.operations = operations


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """Summary of an explicit operation-journal recovery."""

    target_database: str
    backup_path: Path
    reverted_operations: int


@dataclass(slots=True)
class ExistingDatabaseTarget:
    """Bind an existing PyMongo database without causing constructor writes."""

    client: Any
    db: Any

    def ensure_indexes(self, collection_names: set[str] | None = None) -> None:
        """Reuse the application's approved core index manager after apply."""
        from mathdatabase.mathmongo import MathMongo

        adapter = object.__new__(MathMongo)
        adapter.client = self.client
        adapter.db = self.db
        adapter.concepts = self.db["concepts"]
        adapter.relations = self.db["relations"]
        adapter.latex_documents = self.db["latex_documents"]
        adapter.knowledge_graph_maps = self.db["knowledge_graph_maps"]
        adapter.media_assets = self.db[MEDIA_ASSETS_COLLECTION]
        if collection_names is None:
            adapter.ensure_indexes()
            return
        selected = set(collection_names)
        approved_ensure = adapter._ensure_index

        def ensure_selected(collection: Any, *args: Any, **kwargs: Any) -> str:
            if getattr(collection, "name", None) in selected:
                return approved_ensure(collection, *args, **kwargs)
            return str(getattr(collection, "name", ""))

        adapter._ensure_index = ensure_selected
        adapter.ensure_indexes()


@dataclass(frozen=True, slots=True)
class _LoadedArchive:
    identity: FileIdentity
    base_dir: str
    metadata: Mapping[str, Any]
    encodings: Mapping[str, str]
    collections: Mapping[str, tuple[Any, ...]]
    media: Mapping[Path, bytes]
    blobs: Mapping[str, bytes]


@dataclass(slots=True)
class _Candidate:
    collection: str
    document: dict[str, Any]
    managed: bool
    primary_query: dict[str, Any] | None
    unique_queries: list[dict[str, Any]]
    token: str
    invalid_reason: str | None = None


def validate_database_name(name: object, *, update: bool) -> str:
    """Validate one explicit MongoDB target without applying create-mode policy."""
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("Database name must be explicit and cannot have surrounding spaces")
    if "\x00" in name or any(char in name for char in ("/", "\\", ".", " ")):
        raise ValueError("Database name contains unsafe characters")
    if len(name.encode("utf-8")) > 63:
        raise ValueError("Database name is too long")
    protected = PROTECTED_UPDATE_DATABASES if update else PROTECTED_UPDATE_DATABASES | {"mathmongo"}
    if name.casefold() in protected:
        raise ValueError("The selected MongoDB database is protected")
    if name.casefold() == "mathv0" and name != "MathV0":
        raise ValueError("MathV0 must use its exact case-sensitive name")
    return name


def bind_existing_database(mongo: Any, database_name: str) -> ExistingDatabaseTarget:
    """Return a side-effect-free target for a database verified to exist."""
    name = validate_database_name(database_name, update=True)
    client = getattr(mongo, "client", None)
    if client is None or not hasattr(client, "list_database_names"):
        raise ValueError("The active connection cannot enumerate MongoDB databases")
    if name not in client.list_database_names():
        raise ValueError("Update mode requires an existing destination database")
    return ExistingDatabaseTarget(client=client, db=client[name])


def _validate_collection_name(name: object) -> str:
    if not isinstance(name, str) or not _SAFE_COLLECTION_RE.fullmatch(name):
        raise ValueError("Archive contains an unsafe collection name")
    if name.startswith("system") or "$" in name or "\x00" in name:
        raise ValueError("Archive contains a protected collection name")
    return name


def _member_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name:
        raise ZipValidationError("unsafe_path", "ZIP member has an unsafe path", member=name)
    if name.startswith("/") or _WINDOWS_DRIVE_RE.match(name):
        raise ZipValidationError("absolute_path", "ZIP member is absolute", member=name)
    path = PurePosixPath(name)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ZipValidationError(
            "path_traversal",
            "ZIP member contains an unsafe path component",
            member=name,
        )
    expected = path.as_posix() + ("/" if name.endswith("/") else "")
    if expected != name:
        raise ZipValidationError("unsafe_path", "ZIP member path is not canonical", member=name)
    return path


def _member_kind(info: zipfile.ZipInfo) -> str:
    mode = (info.external_attr >> 16) & 0xFFFF
    if stat.S_IFMT(mode) == 0:
        return "directory" if info.is_dir() else "regular"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "regular"
    return "nonregular"


def _validate_dynamic_members(infos: list[zipfile.ZipInfo]) -> str:
    limits = ZipSafetyLimits()
    if not infos:
        raise ZipValidationError("empty_archive", "ZIP archive has no members")
    if len(infos) > limits.max_members:
        raise ZipValidationError("member_limit", "ZIP archive exceeds its member limit")

    raw_names: set[str] = set()
    normalized_names: set[str] = set()
    paths: list[PurePosixPath] = []
    total_size = 0
    for info in infos:
        path = _member_path(info.filename)
        normalized = unicodedata.normalize("NFC", info.filename)
        if info.filename in raw_names or normalized in normalized_names:
            raise ZipValidationError(
                "duplicate_member",
                "ZIP archive contains a duplicate member",
                member=info.filename,
            )
        raw_names.add(info.filename)
        normalized_names.add(normalized)
        paths.append(path)
        if info.flag_bits & 0x1:
            raise ZipValidationError(
                "encrypted_member",
                "Encrypted ZIP members are not supported",
                member=info.filename,
            )
        if info.compress_type not in _SUPPORTED_COMPRESSION:
            raise ZipValidationError(
                "unsupported_compression",
                "ZIP member uses unsupported compression",
                member=info.filename,
            )
        kind = _member_kind(info)
        if kind not in {"regular", "directory"} or (kind == "directory") != info.is_dir():
            raise ZipValidationError(
                "nonregular_member",
                "ZIP members must be regular files or directories",
                member=info.filename,
            )
        if info.file_size > limits.max_member_bytes:
            raise ZipValidationError(
                "member_size_limit",
                "ZIP member exceeds its size limit",
                member=info.filename,
            )
        total_size += info.file_size
        if total_size > limits.max_total_bytes:
            raise ZipValidationError("total_size_limit", "ZIP archive exceeds its size limit")
        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > float(limits.max_compression_ratio):
            raise ZipValidationError(
                "compression_ratio_limit",
                "ZIP member has an anomalous compression ratio",
                member=info.filename,
            )
        if not info.is_dir() and info.file_size == 0:
            raise ZipValidationError(
                "empty_regular_member",
                "ZIP archive contains an empty regular member",
                member=info.filename,
            )

    roots = {path.parts[0] for path in paths}
    if len(roots) != 1:
        raise ZipValidationError("ambiguous_root", "ZIP archive must have one base directory")
    root = next(iter(roots))
    regular_parts = {
        path.parts for info, path in zip(infos, paths, strict=True) if not info.is_dir()
    }
    for path in paths:
        for length in range(1, len(path.parts)):
            if path.parts[:length] in regular_parts:
                raise ZipValidationError(
                    "member_path_collision",
                    "A regular ZIP member is an ancestor of another member",
                    member=path.as_posix(),
                )

    for info, path in zip(infos, paths, strict=True):
        relative = path.parts[1:]
        allowed = False
        if info.is_dir():
            allowed = (
                not relative
                or relative == ("collections",)
                or (relative and relative[0] in {"media", "source_documents"})
            )
        else:
            if relative == ("metadata.json",):
                allowed = True
            elif len(relative) == 2 and relative[0] == "collections":
                allowed = relative[1].endswith(".json")
            elif len(relative) == 1 and relative[0].endswith(".json"):
                allowed = relative[0] != "metadata.json"
            elif relative and relative[0] == "media":
                allowed = True
            elif relative and relative[0] == "source_documents":
                allowed = (
                    db_import._source_document_blob_logical_path(root, info.filename) is not None
                )
        if not allowed:
            raise ZipValidationError(
                "unexpected_member",
                "ZIP archive contains an unexpected member",
                member=info.filename,
            )
    return root


def _collection_members(names: list[str], *, base_dir: str) -> dict[str, str]:
    modern_prefix = f"{base_dir}/collections/"
    historical_prefix = f"{base_dir}/"
    modern: dict[str, str] = {}
    historical: dict[str, str] = {}
    for member_name in names:
        if not member_name.endswith(".json"):
            continue
        if member_name.startswith(modern_prefix):
            relative = member_name[len(modern_prefix) :]
            target = modern
        elif member_name.startswith(historical_prefix):
            relative = member_name[len(historical_prefix) :]
            if relative == "metadata.json":
                continue
            target = historical
        else:
            continue
        if not relative or "/" in relative:
            if member_name.startswith(modern_prefix):
                raise ValueError("Archive contains a nested collection member")
            continue
        collection = _validate_collection_name(relative[:-5])
        if collection in target:
            raise ValueError("Archive contains duplicate collection identities")
        target[collection] = member_name
    if modern and historical:
        raise ValueError("Archive mixes modern and historical collection layouts")
    return modern or historical


def _read_exact_member(zf: zipfile.ZipFile, member_name: str) -> bytes:
    try:
        info = zf.getinfo(member_name)
    except KeyError as exc:
        raise ValueError("Archive member is missing") from exc
    data, _digest = _read_member(zf, info)
    return data


def _parse_metadata(
    metadata: Any,
    *,
    collection_members: Mapping[str, str],
) -> tuple[dict[str, int], dict[str, str]]:
    if not isinstance(metadata, dict):
        raise ValueError("metadata.json must contain an object")
    declared = metadata.get("collections")
    if not isinstance(declared, dict):
        raise ValueError("metadata.collections must contain an object")
    counts: dict[str, int] = {}
    for raw_name, count in declared.items():
        name = _validate_collection_name(raw_name)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("metadata collection counts must be non-negative integers")
        counts[name] = count
    if set(counts) != set(collection_members):
        raise ValueError("metadata collection inventory does not match archive members")

    raw_encodings = metadata.get("collection_encodings", {})
    if not isinstance(raw_encodings, dict):
        raise ValueError("metadata.collection_encodings must contain an object")
    encodings: dict[str, str] = {}
    for raw_name, raw_encoding in raw_encodings.items():
        name = _validate_collection_name(raw_name)
        if name not in collection_members:
            raise ValueError("metadata declares an encoding for an absent collection")
        if raw_encoding not in SUPPORTED_COLLECTION_ENCODINGS:
            raise ValueError("metadata declares an unsupported collection encoding")
        encodings[name] = str(raw_encoding)
    for name in collection_members:
        if name not in _KNOWN_COLLECTIONS and name not in encodings:
            raise ValueError("Generic collections require an explicit JSON encoding")
    return counts, encodings


def _decode_collection(data: bytes, *, collection: str, encoding: str) -> tuple[Any, ...]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Collection {collection} is not valid UTF-8") from exc
    try:
        if encoding == EXTENDED_JSON_ENCODING:
            payload = bson_json_loads(text, json_options=db_import._CATALOG_JSON_OPTIONS)
        else:
            payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Collection {collection} is not valid JSON or Extended JSON") from exc
    if not isinstance(payload, list):
        raise ValueError(f"Collection {collection} must contain a JSON array")
    return tuple(payload)


def _load_archive(zip_path: Path) -> _LoadedArchive:
    path = Path(zip_path).expanduser().absolute()
    identity = identify_input(path)
    with zipfile.ZipFile(path, "r") as zf:
        infos = zf.infolist()
        base_dir = _validate_dynamic_members(infos)
        corrupt = zf.testzip()
        if corrupt is not None:
            raise ZipValidationError("crc_mismatch", "ZIP member failed its CRC check")
        names = zf.namelist()
        metadata_name = f"{base_dir}/metadata.json"
        if metadata_name not in names:
            raise ValueError("metadata.json not found in archive")
        try:
            metadata = json.loads(_read_exact_member(zf, metadata_name).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("metadata.json is not valid UTF-8 JSON") from exc
        members = _collection_members(names, base_dir=base_dir)
        declared_counts, encodings = _parse_metadata(metadata, collection_members=members)
        collections: dict[str, tuple[Any, ...]] = {}
        for collection, member_name in members.items():
            encoding = encodings.get(collection, JSON_ENCODING)
            documents = _decode_collection(
                _read_exact_member(zf, member_name),
                collection=collection,
                encoding=encoding,
            )
            if len(documents) != declared_counts[collection]:
                raise ValueError("metadata count does not match a collection file")
            collections[collection] = documents

        media: dict[Path, bytes] = {}
        for member_name in names:
            relative = db_import._safe_media_member_path(base_dir, member_name)
            if relative is not None:
                media[relative] = _read_exact_member(zf, member_name)
        _validate_media_inventory(metadata.get("media_files"), media)

        blobs: dict[str, bytes] = {}
        for member_name in names:
            logical = db_import._source_document_blob_logical_path(base_dir, member_name)
            if logical is not None:
                blobs[logical] = _read_exact_member(zf, member_name)
        _validate_blob_inventory(metadata.get("source_document_blobs", {}), blobs)
    verify_input_unchanged(path, identity)
    return _LoadedArchive(
        identity=identity,
        base_dir=base_dir,
        metadata=metadata,
        encodings=encodings,
        collections=collections,
        media=media,
        blobs=blobs,
    )


def _validate_media_inventory(raw_inventory: Any, media: Mapping[Path, bytes]) -> None:
    if raw_inventory is None:
        if media:
            raise ValueError("Archive media files require a declared inventory")
        return
    if not isinstance(raw_inventory, dict):
        raise ValueError("metadata.media_files must contain an object")
    observed = {path.as_posix(): data for path, data in media.items()}
    if set(raw_inventory) != set(observed):
        raise ValueError("metadata media inventory does not match archive members")
    for name, declared in raw_inventory.items():
        data = observed[name]
        if isinstance(declared, bool):
            raise ValueError("metadata media inventory has an invalid size")
        if isinstance(declared, int):
            expected_size = declared
            expected_sha = None
        elif isinstance(declared, dict) and set(declared) == {"size_bytes", "sha256"}:
            expected_size = declared.get("size_bytes")
            expected_sha = declared.get("sha256")
        else:
            raise ValueError("metadata media inventory has an invalid entry")
        if not isinstance(expected_size, int) or expected_size < 0 or len(data) != expected_size:
            raise ValueError("metadata media size does not match archive bytes")
        if expected_sha is not None and (
            not isinstance(expected_sha, str) or hashlib.sha256(data).hexdigest() != expected_sha
        ):
            raise ValueError("metadata media SHA-256 does not match archive bytes")


def _validate_blob_inventory(raw_inventory: Any, blobs: Mapping[str, bytes]) -> None:
    if not isinstance(raw_inventory, dict):
        raise ValueError("metadata.source_document_blobs must contain an object")
    if set(raw_inventory) != set(blobs):
        raise ValueError("metadata blob inventory does not match archive members")
    for logical_path, data in blobs.items():
        identity = raw_inventory[logical_path]
        if not isinstance(identity, dict) or set(identity) != {"sha256", "size_bytes"}:
            raise ValueError("metadata blob inventory has an invalid entry")
        digest = hashlib.sha256(data).hexdigest()
        if identity.get("sha256") != digest or identity.get("size_bytes") != len(data):
            raise ValueError("metadata blob identity does not match archive bytes")
        prepared = SourceDocumentBlobStore.prepare_pdf(data)
        if prepared.logical_path != logical_path:
            raise ValueError("Blob path does not match its SHA-256")


def inspect_update_archive(zip_path: Path) -> dict[str, Any]:
    """Inspect dynamic collection inventory without reading or writing MongoDB."""
    loaded = _load_archive(zip_path)
    return {
        "base_name": loaded.base_dir,
        "metadata": dict(loaded.metadata),
        "collections": {name: len(items) for name, items in loaded.collections.items()},
        "unmanaged_collections": sorted(set(loaded.collections) - _KNOWN_COLLECTIONS),
        "archive_sha256": loaded.identity.sha256,
    }


def _canonical(value: Any) -> str:
    return bson_json_dumps(
        value,
        json_options=CANONICAL_JSON_OPTIONS,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _token(collection: str, query: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(f"{collection}:{_canonical(query)}".encode()).hexdigest()
    return digest[:16]


def _nested_value(document: Mapping[str, Any], dotted_name: str) -> Any:
    value: Any = document
    for part in dotted_name.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _query(document: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any] | None:
    values = {name: _nested_value(document, name) for name in fields}
    if any(
        value is None or (isinstance(value, str) and not value.strip()) for value in values.values()
    ):
        return None
    return values


def _identity_queries(collection: str, document: Mapping[str, Any]) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    primary_fields = _PRIMARY_IDENTITIES.get(collection, ("_id",))
    primary = _query(document, primary_fields)
    if primary is not None:
        queries.append(primary)
    storage = _query(document, ("_id",))
    if storage is not None and storage != primary:
        queries.append(storage)
    if collection == "source_documents":
        model = SourceDocument.model_validate(
            {key: value for key, value in document.items() if key != "_id"}
        )
        if model.kind == DocumentKind.PDF:
            assert model.pdf is not None
            queries.append(
                {
                    "source_id": model.source_id,
                    "kind": DocumentKind.PDF.value,
                    "pdf.versions.sha256": model.pdf.current_version.sha256,
                }
            )
        else:
            assert model.web is not None
            queries.append(
                {
                    "source_id": model.source_id,
                    "kind": DocumentKind.WEB.value,
                    "web.url_normalized": model.web.url_normalized,
                }
            )
    elif collection == "document_reading_state":
        alternate = _query(document, ("user_scope", "document_id"))
        if alternate is not None:
            queries.append(alternate)
    elif collection == "document_page_maps" and document.get("status") == "active":
        alternate = _query(document, ("user_scope", "document_id", "status"))
        if alternate is not None:
            queries.append(alternate)
    elif collection == "concept_evidence_links":
        queries.append(db_import._evidence_identity_query(dict(document)))
    return queries


def _validate_document(
    collection: str,
    raw_document: Any,
    *,
    encoding: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw_document, dict):
        return None, "Collection entries must be JSON objects"
    document = (
        dict(raw_document)
        if encoding == EXTENDED_JSON_ENCODING
        else db_import._restore_mongo_types(dict(raw_document), collection)
    )
    payload = {key: value for key, value in document.items() if key != "_id"}
    try:
        if collection == MANIFEST_COLLECTION:
            validated = MigrationManifest.model_validate(payload).model_dump(mode="python")
            if document.get("_id") != validated.get("manifest_key"):
                return document, "Manifest _id must equal manifest_key"
        elif collection in _PORTABLE_MODELS:
            validated = (
                _PORTABLE_MODELS[collection].model_validate(payload).model_dump(mode="python")
            )
            if (
                collection == "document_annotations"
                and payload.get("schema_version") in {1, 2}
                and "visual_anchor" not in payload
            ):
                validated.pop("visual_anchor", None)
            if encoding == EXTENDED_JSON_ENCODING and not db_import._catalog_documents_identical(
                payload,
                validated,
            ):
                return document, "Portable document is not canonical"
        elif collection == "concepts":
            ConceptoBase.model_validate(payload)
        elif collection == "latex_documents":
            DocumentoLatex.model_validate(payload)
        elif collection == "relations":
            for field_name in ("desde", "hasta", "tipo"):
                value = document.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    return document, f"Relation requires {field_name}"
        elif collection == MEDIA_ASSETS_COLLECTION:
            if not isinstance(document.get("asset_id"), str) or not document["asset_id"].strip():
                return document, "Media asset requires asset_id"
    except (TypeError, ValueError):
        return document, "Document does not satisfy its managed collection contract"
    return document, None


def _count_documents(database: Any, collection: str, existing_names: set[str]) -> int:
    if collection not in existing_names:
        return 0
    return int(database[collection].count_documents({}))


def _find_matches(database: Any, collection: str, query: Mapping[str, Any]) -> tuple[dict, ...]:
    return db_import._find_at_most_two(database[collection], dict(query))


def _build_candidates(
    loaded: _LoadedArchive,
) -> tuple[dict[str, list[_Candidate]], list[UpdateIssue]]:
    candidates: dict[str, list[_Candidate]] = {}
    issues: list[UpdateIssue] = []
    for collection, raw_documents in loaded.collections.items():
        managed = collection in _KNOWN_COLLECTIONS
        collection_candidates: list[_Candidate] = []
        for ordinal, raw_document in enumerate(raw_documents, start=1):
            document, invalid_reason = _validate_document(
                collection,
                raw_document,
                encoding=loaded.encodings.get(collection, JSON_ENCODING),
            )
            fallback = {"entry": ordinal}
            if document is None:
                candidate = _Candidate(
                    collection,
                    {},
                    managed,
                    None,
                    [],
                    _token(collection, fallback),
                    invalid_reason,
                )
                collection_candidates.append(candidate)
                continue
            queries = _identity_queries(collection, document)
            primary = queries[0] if queries else None
            if primary is None:
                invalid_reason = invalid_reason or (
                    "Generic collection has no safe _id identity"
                    if not managed
                    else "Document is missing its managed stable identity"
                )
            candidate = _Candidate(
                collection,
                document,
                managed,
                primary,
                queries,
                _token(collection, primary or fallback),
                invalid_reason,
            )
            collection_candidates.append(candidate)
        candidates[collection] = collection_candidates

        identities: dict[str, list[_Candidate]] = {}
        for candidate in collection_candidates:
            for query in candidate.unique_queries:
                key = _canonical(query)
                identities.setdefault(key, []).append(candidate)
        for duplicates in identities.values():
            if len(duplicates) < 2:
                continue
            for candidate in duplicates:
                candidate.invalid_reason = "Archive contains a duplicate stable identity"

        for candidate in collection_candidates:
            if candidate.invalid_reason:
                issues.append(UpdateIssue(collection, candidate.token, candidate.invalid_reason))
    return candidates, issues


def _candidate_action(
    database: Any,
    candidate: _Candidate,
    *,
    existing_names: set[str],
) -> tuple[DocumentAction, UpdateIssue | None]:
    assert candidate.primary_query is not None
    if candidate.collection not in existing_names:
        return (
            DocumentAction(
                candidate.collection,
                DocumentClassification.INSERT,
                candidate.token,
                candidate.primary_query,
                candidate.primary_query,
                candidate.document,
                managed=candidate.managed,
            ),
            None,
        )

    matches_by_query: list[tuple[dict[str, Any], tuple[dict, ...]]] = []
    for query in candidate.unique_queries:
        matches = _find_matches(database, candidate.collection, query)
        if len(matches) > 1:
            return (
                DocumentAction(
                    candidate.collection,
                    DocumentClassification.INVALID,
                    candidate.token,
                    candidate.primary_query,
                    query,
                    candidate.document,
                    managed=candidate.managed,
                    replace_allowed=False,
                ),
                UpdateIssue(
                    candidate.collection,
                    candidate.token,
                    "Destination contains duplicate documents for a stable identity",
                ),
            )
        matches_by_query.append((query, matches))

    distinct_matches = {
        _content_hash(document)
        for _query_value, matches in matches_by_query
        for document in matches
    }
    if len(distinct_matches) > 1:
        return (
            DocumentAction(
                candidate.collection,
                DocumentClassification.INVALID,
                candidate.token,
                candidate.primary_query,
                candidate.primary_query,
                candidate.document,
                managed=candidate.managed,
                replace_allowed=False,
            ),
            UpdateIssue(
                candidate.collection,
                candidate.token,
                "Archive identity collides with multiple destination documents",
            ),
        )

    primary_matches = matches_by_query[0][1]
    existing = primary_matches[0] if primary_matches else None
    match_query = candidate.primary_query
    if existing is None:
        alternate_matches = [
            (query, matches[0]) for query, matches in matches_by_query[1:] if matches
        ]
        if alternate_matches:
            match_query, existing = alternate_matches[0]

    incoming_id = candidate.document.get("_id")
    existing_id = existing.get("_id") if existing is not None else None
    replace_allowed = existing is None or incoming_id in {None, existing_id}

    if existing is None:
        classification = DocumentClassification.INSERT
    elif db_import._catalog_documents_identical(existing, candidate.document):
        classification = DocumentClassification.IDENTICAL
    else:
        classification = DocumentClassification.CONFLICT
    return (
        DocumentAction(
            candidate.collection,
            classification,
            candidate.token,
            candidate.primary_query,
            match_query,
            candidate.document,
            existing,
            candidate.managed,
            replace_allowed,
        ),
        None,
    )


def _endpoint_query(value: Any) -> dict[str, str] | None:
    if not isinstance(value, str) or "@" not in value:
        return None
    concept_id, source = value.rsplit("@", 1)
    if not concept_id or not source:
        return None
    return {"id": concept_id, "source": source}


def _relationship_issues(
    database: Any,
    candidates: Mapping[str, list[_Candidate]],
    *,
    existing_names: set[str],
) -> list[UpdateIssue]:
    issues: list[UpdateIssue] = []
    valid_docs = {
        name: [candidate.document for candidate in items if not candidate.invalid_reason]
        for name, items in candidates.items()
    }

    incoming_sources = {
        item.get("source_id") for item in valid_docs.get("sources", []) if item.get("source_id")
    }
    incoming_references = {
        item.get("reference_id"): item
        for item in valid_docs.get("references", [])
        if item.get("reference_id")
    }
    for reference in valid_docs.get("references", []):
        token = _token("references", {"reference_id": reference.get("reference_id")})
        for source_id in reference.get("source_ids", []):
            if source_id in incoming_sources:
                continue
            matches = (
                _find_matches(database, "sources", {"source_id": source_id})
                if "sources" in existing_names
                else ()
            )
            if len(matches) != 1:
                issues.append(
                    UpdateIssue(
                        "references",
                        token,
                        "Reference points to a Source absent from archive and destination",
                    )
                )
    for document in valid_docs.get("source_documents", []):
        token = _token("source_documents", {"document_id": document.get("document_id")})
        source_id = document.get("source_id")
        if source_id not in incoming_sources:
            matches = (
                _find_matches(database, "sources", {"source_id": source_id})
                if "sources" in existing_names
                else ()
            )
            if len(matches) != 1:
                issues.append(
                    UpdateIssue(
                        "source_documents",
                        token,
                        "Source Document points to a Source absent from archive and destination",
                    )
                )
        reference_id = document.get("reference_id")
        if reference_id is not None:
            reference = incoming_references.get(reference_id)
            if reference is None and "references" in existing_names:
                matches = _find_matches(database, "references", {"reference_id": reference_id})
                reference = matches[0] if len(matches) == 1 else None
            if reference is None or source_id not in reference.get("source_ids", []):
                issues.append(
                    UpdateIssue(
                        "source_documents",
                        token,
                        "Source Document Reference is absent or belongs to another Source",
                    )
                )

    incoming_concepts = {
        _canonical({"id": item.get("id"), "source": item.get("source")})
        for item in valid_docs.get("concepts", [])
    }
    for relation in valid_docs.get("relations", []):
        token = _token(
            "relations",
            {name: relation.get(name) for name in ("desde", "hasta", "tipo")},
        )
        for endpoint in (relation.get("desde"), relation.get("hasta")):
            query = _endpoint_query(endpoint)
            if query is None:
                issues.append(UpdateIssue("relations", token, "Relation endpoint is invalid"))
                continue
            if _canonical(query) in incoming_concepts:
                continue
            matches = (
                _find_matches(database, "concepts", query) if "concepts" in existing_names else ()
            )
            if len(matches) != 1:
                issues.append(
                    UpdateIssue(
                        "relations",
                        token,
                        "Relation points to a Concept absent from archive and destination",
                    )
                )

    report = db_import.DatabaseImportReport()
    try:
        db_import._preflight_reading_state_relationships(
            valid_docs.get("document_reading_state", []),
            source_documents=valid_docs.get("source_documents", []),
            db=database,
            report=report,
        )
        db_import._preflight_page_map_relationships(
            valid_docs.get("document_page_maps", []),
            source_documents=valid_docs.get("source_documents", []),
            db=database,
            report=report,
        )
        db_import._preflight_reading_annotation_relationships(
            raw_annotations=valid_docs.get("document_annotations", []),
            raw_notes=valid_docs.get("reading_notes", []),
            raw_evidence_links=valid_docs.get("concept_evidence_links", []),
            sources=valid_docs.get("sources", []),
            references=valid_docs.get("references", []),
            source_documents=valid_docs.get("source_documents", []),
            legacy_concepts=valid_docs.get("concepts", []),
            db=database,
            report=report,
        )
    except (TypeError, ValueError) as exc:
        issues.append(UpdateIssue("portable", "validation", str(exc)))
    for conflict in report.catalog_conflicts:
        if conflict.reason.startswith("destination contains a different"):
            continue
        issues.append(
            UpdateIssue(
                conflict.collection,
                _token(conflict.collection, {"domain": conflict.domain_id}),
                conflict.reason,
            )
        )
    return issues


def _read_regular_file(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise ValueError("Update destination is not a regular file")
        data = bytearray()
        while len(data) < observed.st_size:
            chunk = os.read(descriptor, min(1024 * 1024, observed.st_size - len(data)))
            if not chunk:
                raise ValueError("Update destination changed while it was read")
            data.extend(chunk)
        after = os.fstat(descriptor)
        if (observed.st_dev, observed.st_ino, observed.st_size, observed.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("Update destination changed while it was read")
        return bytes(data)
    finally:
        os.close(descriptor)


def _plan_files(
    loaded: _LoadedArchive,
    *,
    blob_store: SourceDocumentBlobStore,
    data_root: Path,
    source_documents: list[dict[str, Any]],
) -> tuple[list[BlobUpdatePlan], list[MediaUpdatePlan], list[UpdateIssue]]:
    issues: list[UpdateIssue] = []
    referenced: dict[str, Any] = {}
    for raw_document in source_documents:
        document = SourceDocument.model_validate(
            {key: value for key, value in raw_document.items() if key != "_id"}
        )
        if document.kind != DocumentKind.PDF:
            continue
        assert document.pdf is not None
        version = document.pdf.current_version
        referenced[version.logical_path] = version
    if set(referenced) != set(loaded.blobs):
        issues.append(
            UpdateIssue(
                "source_documents",
                "blob-inventory",
                "Source Document blobs are missing or unreferenced",
            )
        )

    blob_plans: list[BlobUpdatePlan] = []
    for logical_path, version in sorted(referenced.items()):
        data = loaded.blobs.get(logical_path)
        if data is None:
            continue
        prepared = SourceDocumentBlobStore.prepare_pdf(data)
        if (
            prepared.sha256 != version.sha256
            or prepared.size_bytes != version.size_bytes
            or prepared.logical_path != version.logical_path
        ):
            issues.append(
                UpdateIssue(
                    "source_documents",
                    prepared.sha256[:16],
                    "PDF blob does not match Source Document version metadata",
                )
            )
            continue
        try:
            existing = blob_store.read_version(version)
        except FileNotFoundError:
            exists = False
        except Exception:
            issues.append(
                UpdateIssue(
                    "source_documents",
                    prepared.sha256[:16],
                    "Canonical PDF blob destination conflicts",
                )
            )
            continue
        else:
            exists = True
            if existing != data:
                issues.append(
                    UpdateIssue(
                        "source_documents",
                        prepared.sha256[:16],
                        "Canonical PDF blob destination has different bytes",
                    )
                )
                continue
        blob_plans.append(BlobUpdatePlan(prepared, exists))

    media_plans: list[MediaUpdatePlan] = []
    for relative_path, data in sorted(loaded.media.items(), key=lambda item: item[0].as_posix()):
        destination = validate_mutable_path(
            data_root / relative_path,
            allowed_root=data_root,
        )
        if destination.exists() or destination.is_symlink():
            try:
                existing_data = _read_regular_file(destination)
            except (OSError, ValueError):
                issues.append(
                    UpdateIssue(
                        "media",
                        _token("media", {"path": relative_path.as_posix()}),
                        "Media destination is unsafe",
                    )
                )
                continue
            if existing_data != data:
                issues.append(
                    UpdateIssue(
                        "media",
                        _token("media", {"path": relative_path.as_posix()}),
                        "Media destination contains different bytes",
                    )
                )
                continue
            exists = True
        else:
            exists = False
        media_plans.append(MediaUpdatePlan(relative_path, destination, data, exists))
    return blob_plans, media_plans, issues


def _proposed_action(strategy: UpdateStrategy, *, conflicts: int, invalid: int) -> str:
    if invalid:
        return "Bloqueada hasta resolver datos inválidos"
    if conflicts and strategy is UpdateStrategy.BACKUP_WINS:
        return "Insertar nuevos y aplicar decisiones de conflicto"
    if conflicts:
        return "Insertar nuevos y conservar conflictos"
    return "Insertar nuevos y omitir idénticos"


def _plan_fingerprint(
    *,
    target_database: str,
    strategy: UpdateStrategy,
    archive_sha256: str,
    collection_plans: list[CollectionUpdatePlan],
    actions: list[DocumentAction],
    issues: list[UpdateIssue],
    blob_plans: list[BlobUpdatePlan],
    media_plans: list[MediaUpdatePlan],
) -> str:
    payload = {
        "target": target_database,
        "strategy": strategy.value,
        "archive": archive_sha256,
        "collections": [
            {
                "name": item.name,
                "current": item.current_documents,
                "backup": item.backup_documents,
                "identical": item.identical,
                "new": item.new,
                "conflicts": item.conflicts,
                "invalid": item.invalid,
            }
            for item in collection_plans
        ],
        "actions": [
            {
                "collection": item.collection,
                "classification": item.classification.value,
                "token": item.token,
                "incoming": _content_hash(item.incoming),
                "existing": _content_hash(item.existing) if item.existing is not None else None,
                "replace_allowed": item.replace_allowed,
            }
            for item in actions
        ],
        "issues": [(item.collection, item.token, item.reason) for item in issues],
        "blobs": [(item.prepared.sha256, item.exists) for item in blob_plans],
        "media": [(item.relative_path.as_posix(), item.exists) for item in media_plans],
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _managed_index_issues(database: Any, collection_names: set[str]) -> list[UpdateIssue]:
    """Inspect the index managers that expose read-only plans before any write."""
    source_catalog = collection_names & set(SOURCE_CATALOG_COLLECTIONS)
    reading_annotations = collection_names & set(READING_ANNOTATION_COLLECTIONS)
    plans = []
    if source_catalog:
        plans.append(SourceCatalogIndexManager(database).plan(source_catalog))
    if "document_reading_state" in collection_names:
        plans.append(ReadingSpaceIndexManager(database).plan())
    if collection_names & set(DOCUMENT_PAGE_MAP_COLLECTIONS):
        plans.append(DocumentPageMapIndexManager(database).plan())
    if reading_annotations:
        plans.append(ReadingAnnotationIndexManager(database).plan(reading_annotations))
    issues: list[UpdateIssue] = []
    for plan in plans:
        for conflict in plan.conflicts:
            spec = conflict.spec
            token = hashlib.sha256(f"index:{spec.collection}:{spec.name}".encode()).hexdigest()[:16]
            reason = f"Managed index conflict: {spec.name}"
            if conflict.detail:
                reason = f"{reason} ({conflict.detail})"
            issues.append(UpdateIssue(spec.collection, token, reason))
    return issues


def analyze_database_update(
    zip_path: Path,
    mongo: Any,
    *,
    strategy: UpdateStrategy | str = UpdateStrategy.SAFE_MERGE,
    source_document_blob_store: SourceDocumentBlobStore | None = None,
    data_root: Path | None = None,
) -> DatabaseUpdatePlan:
    """Build a complete read-only update plan for one existing database."""
    selected_strategy = UpdateStrategy(strategy)
    database = mongo.db
    target = validate_database_name(getattr(database, "name", None), update=True)
    client = getattr(mongo, "client", None)
    if client is not None and hasattr(client, "list_database_names"):
        if target not in client.list_database_names():
            raise ValueError("Update mode requires an existing destination database")
    loaded = _load_archive(zip_path)
    existing_names = set(database.list_collection_names())
    candidates, issues = _build_candidates(loaded)
    actions: list[DocumentAction] = []
    for collection_candidates in candidates.values():
        for candidate in collection_candidates:
            if candidate.invalid_reason or candidate.primary_query is None:
                actions.append(
                    DocumentAction(
                        candidate.collection,
                        DocumentClassification.INVALID,
                        candidate.token,
                        candidate.primary_query or {},
                        candidate.primary_query or {},
                        candidate.document,
                        managed=candidate.managed,
                        replace_allowed=False,
                    )
                )
                continue
            action, issue = _candidate_action(
                database,
                candidate,
                existing_names=existing_names,
            )
            actions.append(action)
            if issue is not None:
                issues.append(issue)

    issues.extend(_relationship_issues(database, candidates, existing_names=existing_names))
    issues.extend(_managed_index_issues(database, set(loaded.collections)))
    issue_keys = {(item.collection, item.token, item.reason) for item in issues}
    issues = [UpdateIssue(*values) for values in sorted(issue_keys)]

    valid_source_documents = [
        candidate.document
        for candidate in candidates.get("source_documents", [])
        if not candidate.invalid_reason
    ]
    root = validate_mutable_path(data_root or db_import.DATA_DIR)
    blob_store = source_document_blob_store or SourceDocumentBlobStore(root)
    blob_plans, media_plans, file_issues = _plan_files(
        loaded,
        blob_store=blob_store,
        data_root=root,
        source_documents=valid_source_documents,
    )
    issues.extend(file_issues)

    collection_plans: list[CollectionUpdatePlan] = []
    for collection in sorted(loaded.collections):
        collection_actions = [item for item in actions if item.collection == collection]
        counts = {
            classification: sum(
                item.classification is classification for item in collection_actions
            )
            for classification in DocumentClassification
        }
        invalid_tokens = {item.token for item in issues if item.collection == collection}
        invalid = max(counts[DocumentClassification.INVALID], len(invalid_tokens))
        managed = collection in _KNOWN_COLLECTIONS
        collection_plans.append(
            CollectionUpdatePlan(
                name=collection,
                current_documents=_count_documents(database, collection, existing_names),
                backup_documents=len(loaded.collections[collection]),
                identical=counts[DocumentClassification.IDENTICAL],
                new=counts[DocumentClassification.INSERT],
                conflicts=counts[DocumentClassification.CONFLICT],
                invalid=invalid,
                managed=managed,
                proposed_action=_proposed_action(
                    selected_strategy,
                    conflicts=counts[DocumentClassification.CONFLICT],
                    invalid=invalid,
                ),
            )
        )

    warnings = tuple(
        f"{name}: {GENERIC_COLLECTION_LABEL}; no se crearán índices"
        for name in sorted(set(loaded.collections) - _KNOWN_COLLECTIONS)
    )
    fingerprint = _plan_fingerprint(
        target_database=target,
        strategy=selected_strategy,
        archive_sha256=loaded.identity.sha256,
        collection_plans=collection_plans,
        actions=actions,
        issues=issues,
        blob_plans=blob_plans,
        media_plans=media_plans,
    )
    archive_database = loaded.metadata.get("database_name")
    return DatabaseUpdatePlan(
        target_database=target,
        strategy=selected_strategy,
        archive_sha256=loaded.identity.sha256,
        archive_database=archive_database if isinstance(archive_database, str) else None,
        collection_plans=tuple(collection_plans),
        actions=tuple(actions),
        blocking_issues=tuple(issues),
        warnings=warnings,
        blob_plans=tuple(blob_plans),
        media_plans=tuple(media_plans),
        fingerprint=fingerprint,
        analyzed_at=datetime.now(timezone.utc),
    )


def _ordered_collection_names(names: set[str]) -> list[str]:
    rank = {name: index for index, name in enumerate(_DEPENDENCY_ORDER)}
    return sorted(names, key=lambda name: (rank.get(name, len(rank)), name))


def _open_update_directory(directory: Path, *, data_root: Path, create: bool) -> int:
    """Open one XDG descendant through anchored, no-follow directory descriptors."""
    root = validate_mutable_path(data_root)
    target = validate_mutable_path(directory, allowed_root=root)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(target.anchor, flags)
    current_path = Path(target.anchor)
    try:
        for part in target.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
            current_path /= part
            if create and (current_path == root or current_path.is_relative_to(root)):
                os.fchmod(descriptor, 0o700)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _verify_pinned_media_destination(
    destination: Path,
    *,
    data_root: Path,
    pinned_parent: int,
    expected_identity: tuple[int, int],
    data: bytes,
) -> None:
    current_parent = _open_update_directory(
        destination.parent,
        data_root=data_root,
        create=False,
    )
    try:
        pinned = os.fstat(pinned_parent)
        current = os.fstat(current_parent)
        if (pinned.st_dev, pinned.st_ino) != (current.st_dev, current.st_ino):
            raise FileExistsError("Media destination parent changed during update")
        identity = db_import._matching_file_identity_at(
            current_parent,
            destination.name,
            data,
        )
        if identity != expected_identity:
            raise FileExistsError("Media destination changed during update")
    finally:
        os.close(current_parent)


def _write_atomic_new_file(
    plan: MediaUpdatePlan,
    *,
    data_root: Path,
) -> bool:
    """Publish one immutable media file without following mutable path components."""
    root = validate_mutable_path(data_root)
    destination = validate_mutable_path(plan.destination, allowed_root=root)
    parent_descriptor = _open_update_directory(
        destination.parent,
        data_root=root,
        create=True,
    )
    staged_descriptor: int | None = None
    try:
        existing_identity = db_import._matching_file_identity_at(
            parent_descriptor,
            destination.name,
            plan.data,
        )
        if existing_identity is not None:
            _verify_pinned_media_destination(
                destination,
                data_root=root,
                pinned_parent=parent_descriptor,
                expected_identity=existing_identity,
                data=plan.data,
            )
            return False
        try:
            os.stat(destination.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("Media destination changed after dry-run")

        temporary_flag = getattr(os, "O_TMPFILE", 0)
        if not temporary_flag:
            raise OSError("This platform cannot stage media through anonymous files")
        staged_descriptor = os.open(
            ".",
            os.O_RDWR | temporary_flag | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=parent_descriptor,
        )
        view = memoryview(plan.data)
        written = 0
        while written < len(view):
            count = os.write(staged_descriptor, view[written:])
            if count <= 0:
                raise OSError("Could not stage media update")
            written += count
        os.fchmod(staged_descriptor, 0o600)
        os.fsync(staged_descriptor)
        staged = os.fstat(staged_descriptor)
        expected_identity = (staged.st_dev, staged.st_ino)
        created = True

        current_parent = _open_update_directory(
            destination.parent,
            data_root=root,
            create=False,
        )
        try:
            pinned = os.fstat(parent_descriptor)
            current = os.fstat(current_parent)
            if (pinned.st_dev, pinned.st_ino) != (current.st_dev, current.st_ino):
                raise FileExistsError("Media destination parent changed before publication")
            try:
                os.link(
                    f"/proc/self/fd/{staged_descriptor}",
                    destination.name,
                    dst_dir_fd=current_parent,
                    follow_symlinks=True,
                )
            except FileExistsError as exc:
                existing_identity = db_import._matching_file_identity_at(
                    current_parent,
                    destination.name,
                    plan.data,
                )
                if existing_identity is None:
                    raise FileExistsError("Concurrent media update conflicted") from exc
                expected_identity = existing_identity
                created = False
            os.fsync(current_parent)
        finally:
            os.close(current_parent)

        _verify_pinned_media_destination(
            destination,
            data_root=root,
            pinned_parent=parent_descriptor,
            expected_identity=expected_identity,
            data=plan.data,
        )
        return created
    finally:
        if staged_descriptor is not None:
            os.close(staged_descriptor)
        os.close(parent_descriptor)


def _delete_created_file(path: Path, data: bytes, *, data_root: Path) -> None:
    """Delete an unchanged update-created file through its anchored parent."""
    root = validate_mutable_path(data_root)
    target = validate_mutable_path(path, allowed_root=root)
    parent_descriptor = _open_update_directory(
        target.parent,
        data_root=root,
        create=False,
    )
    try:
        identity = db_import._matching_file_identity_at(
            parent_descriptor,
            target.name,
            data,
        )
        if identity is None:
            try:
                os.stat(target.name, dir_fd=parent_descriptor, follow_symlinks=False)
            except FileNotFoundError:
                return
            raise RuntimeError("Recovery file changed after the failed update")
        os.unlink(target.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _create_preupdate_backup(
    mongo: Any,
    *,
    backup_root: Path,
    blob_store: SourceDocumentBlobStore,
) -> Path:
    root = validate_mutable_path(backup_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    database_name = validate_database_name(getattr(mongo.db, "name", None), update=True)
    directory = validate_mutable_path(
        root / "database-updates" / database_name / f"{timestamp}-{uuid4().hex[:8]}",
        allowed_root=root,
    )
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    directory.chmod(0o700)
    backup_path = export_database_to_zip(
        mongo,
        directory,
        source_document_blob_store=blob_store,
        include_all_collections=True,
    )
    inspection = inspect_update_archive(backup_path)
    if inspection["metadata"].get("database_name") != database_name:
        raise RuntimeError("Pre-update backup identifies another database")
    observed_counts = inspection["collections"]
    for collection in mongo.db.list_collection_names():
        if observed_counts.get(collection) != mongo.db[collection].count_documents({}):
            raise RuntimeError("Pre-update backup validation found an incomplete collection")
    return backup_path


def _validate_conflict_policies(
    plan: DatabaseUpdatePlan,
    policies: Mapping[str, ConflictPolicy | str],
) -> dict[str, ConflictPolicy]:
    expected = {action.token for action in plan.conflicts}
    if set(policies) != expected:
        raise ValueError("Every conflict requires one explicit policy")
    normalized = {token: ConflictPolicy(value) for token, value in policies.items()}
    for action in plan.conflicts:
        policy = normalized[action.token]
        if policy is ConflictPolicy.USE_BACKUP and plan.strategy is not UpdateStrategy.BACKUP_WINS:
            raise ValueError("Only the advanced strategy can replace a conflict")
        if policy is ConflictPolicy.USE_BACKUP and not action.replace_allowed:
            raise ValueError("This conflict cannot safely replace its MongoDB identity")
    return normalized


def _current_match(database: Any, action: DocumentAction) -> dict[str, Any] | None:
    matches = _find_matches(database, action.collection, action.match_query)
    if len(matches) > 1:
        raise StaleUpdatePlanError("Destination identity became ambiguous after dry-run")
    return matches[0] if matches else None


def _apply_known_indexes(mongo: Any, collection_names: set[str]) -> None:
    database = mongo.db
    if "source_documents" in collection_names:
        SourceDocumentIndexManager(database).ensure()
    source_catalog = collection_names & set(SOURCE_CATALOG_COLLECTIONS)
    if source_catalog:
        SourceCatalogIndexManager(database).apply(source_catalog)
    if "document_reading_state" in collection_names:
        ReadingSpaceIndexManager(database).apply()
    if collection_names & set(DOCUMENT_PAGE_MAP_COLLECTIONS):
        DocumentPageMapIndexManager(database).apply()
    reading_annotations = collection_names & set(READING_ANNOTATION_COLLECTIONS)
    if reading_annotations:
        ReadingAnnotationIndexManager(database).apply(reading_annotations)
    core_collections = collection_names & {
        "concepts",
        "relations",
        "latex_documents",
        "knowledge_graph_maps",
        "media_assets",
    }
    if core_collections:
        ExistingDatabaseTarget(client=getattr(mongo, "client", None), db=database).ensure_indexes(
            core_collections
        )


def apply_database_update(
    zip_path: Path,
    mongo: Any,
    expected_plan: DatabaseUpdatePlan,
    *,
    conflict_policies: Mapping[str, ConflictPolicy | str],
    backup_root: Path | None = None,
    source_document_blob_store: SourceDocumentBlobStore | None = None,
    data_root: Path | None = None,
) -> DatabaseUpdateReport:
    """Back up and apply one previously analyzed, non-deleting update plan."""
    root = validate_mutable_path(data_root or db_import.DATA_DIR)
    blob_store = source_document_blob_store or SourceDocumentBlobStore(root)
    current_plan = analyze_database_update(
        zip_path,
        mongo,
        strategy=expected_plan.strategy,
        source_document_blob_store=blob_store,
        data_root=root,
    )
    if current_plan.fingerprint != expected_plan.fingerprint:
        raise StaleUpdatePlanError("Archive or destination changed after dry-run; analyze again")
    if not current_plan.can_apply:
        raise ValueError("Update plan contains blocking validation errors")
    policies = _validate_conflict_policies(current_plan, conflict_policies)

    backup_path = _create_preupdate_backup(
        mongo,
        backup_root=backup_root or get_backups_dir(),
        blob_store=blob_store,
    )
    database = mongo.db
    operations: list[AppliedOperation] = []
    inserted = replaced = blobs_created = media_created = 0
    try:
        for blob_plan in current_plan.blob_plans:
            published = blob_store.publish(blob_plan.prepared)
            if published.created:
                blobs_created += 1
                operations.append(
                    AppliedOperation(
                        "blob_created",
                        path=blob_store.path_for_sha(blob_plan.prepared.sha256),
                        data=blob_plan.prepared.data,
                    )
                )

        for media_plan in current_plan.media_plans:
            if _write_atomic_new_file(media_plan, data_root=root):
                media_created += 1
                operations.append(
                    AppliedOperation(
                        "media_created",
                        path=media_plan.destination,
                        data=media_plan.data,
                    )
                )

        existing_names = set(database.list_collection_names())
        archive_collections = {item.name for item in current_plan.collection_plans}
        for collection in _ordered_collection_names(archive_collections):
            if collection not in existing_names:
                database.create_collection(collection)
                existing_names.add(collection)
                operations.append(AppliedOperation("collection_created", collection=collection))

        actions_by_collection: dict[str, list[DocumentAction]] = {}
        for action in current_plan.actions:
            actions_by_collection.setdefault(action.collection, []).append(action)
        for collection in _ordered_collection_names(set(actions_by_collection)):
            for action in actions_by_collection[collection]:
                if action.classification is DocumentClassification.INVALID:
                    raise RuntimeError("Invalid action reached update apply")
                current = _current_match(database, action)
                if action.classification is DocumentClassification.IDENTICAL:
                    if current is None or not db_import._catalog_documents_identical(
                        current,
                        dict(action.incoming),
                    ):
                        raise StaleUpdatePlanError("Identical document changed after dry-run")
                    continue
                if action.classification is DocumentClassification.INSERT:
                    if current is not None:
                        raise StaleUpdatePlanError("Insert identity appeared after dry-run")
                    try:
                        database[collection].insert_one(dict(action.incoming))
                    except DuplicateKeyError as exc:
                        raise StaleUpdatePlanError(
                            "A unique identity appeared while applying the update"
                        ) from exc
                    inserted += 1
                    operations.append(
                        AppliedOperation(
                            "document_inserted",
                            collection=collection,
                            query=dict(action.identity_query),
                            after=dict(action.incoming),
                        )
                    )
                    continue

                assert action.classification is DocumentClassification.CONFLICT
                if (
                    current is None
                    or action.existing is None
                    or not db_import._catalog_documents_identical(
                        current,
                        dict(action.existing),
                    )
                ):
                    raise StaleUpdatePlanError("Conflict changed after dry-run")
                if policies[action.token] is ConflictPolicy.KEEP_CURRENT:
                    continue
                replacement = dict(action.incoming)
                if "_id" not in replacement and "_id" in current:
                    replacement["_id"] = current["_id"]
                result = database[collection].replace_one(
                    dict(current),
                    replacement,
                    upsert=False,
                )
                if getattr(result, "matched_count", 1) != 1:
                    raise StaleUpdatePlanError("Conflict disappeared while applying the update")
                replaced += 1
                operations.append(
                    AppliedOperation(
                        "document_replaced",
                        collection=collection,
                        query={"_id": replacement.get("_id")}
                        if replacement.get("_id") is not None
                        else dict(action.identity_query),
                        before=dict(current),
                        after=replacement,
                    )
                )

        _apply_known_indexes(mongo, archive_collections)
        final_plan = analyze_database_update(
            zip_path,
            mongo,
            strategy=current_plan.strategy,
            source_document_blob_store=blob_store,
            data_root=root,
        )
        if final_plan.blocking_issues or any(item.new for item in final_plan.collection_plans):
            raise RuntimeError("Post-update validation did not reach a stable state")
        for original in current_plan.conflicts:
            matching = next(
                (
                    item
                    for item in final_plan.actions
                    if item.collection == original.collection and item.token == original.token
                ),
                None,
            )
            expected = (
                DocumentClassification.IDENTICAL
                if policies[original.token] is ConflictPolicy.USE_BACKUP
                else DocumentClassification.CONFLICT
            )
            if matching is None or matching.classification is not expected:
                raise RuntimeError("Post-update conflict policy validation failed")
    except Exception as exc:
        raise DatabaseUpdateApplyError(
            f"Update stopped after {len(operations)} completed operations. "
            "Use the validated backup and explicit recovery option before retrying.",
            target_database=current_plan.target_database,
            backup_path=backup_path,
            operations=tuple(operations),
        ) from exc

    conflicts_preserved = sum(policy is ConflictPolicy.KEEP_CURRENT for policy in policies.values())
    unmanaged = tuple(item.name for item in current_plan.collection_plans if not item.managed)
    return DatabaseUpdateReport(
        target_database=current_plan.target_database,
        backup_path=backup_path,
        inserted=inserted,
        identical=current_plan.totals["identical"],
        conflicts_preserved=conflicts_preserved,
        replaced=replaced,
        blobs_created=blobs_created,
        blobs_identical=len(current_plan.blob_plans) - blobs_created,
        media_created=media_created,
        media_identical=len(current_plan.media_plans) - media_created,
        unmanaged_collections=unmanaged,
        operations=tuple(operations),
    )


def restore_failed_update(
    failure: DatabaseUpdateApplyError,
    mongo: Any,
    *,
    confirmation: str,
    data_root: Path | None = None,
) -> RecoveryReport:
    """Explicitly undo the operation journal after validating its pre-update backup."""
    database_name = validate_database_name(getattr(mongo.db, "name", None), update=True)
    if database_name != failure.target_database or confirmation != database_name:
        raise ValueError("Recovery requires the exact destination database name")
    inspection = inspect_update_archive(failure.backup_path)
    if inspection["metadata"].get("database_name") != database_name:
        raise ValueError("Recovery backup does not belong to the destination database")

    reverted = 0
    database = mongo.db
    root = validate_mutable_path(data_root or db_import.DATA_DIR)
    for operation in reversed(failure.operations):
        if operation.kind in {"blob_created", "media_created"}:
            assert operation.path is not None and operation.data is not None
            _delete_created_file(operation.path, operation.data, data_root=root)
            reverted += 1
        elif operation.kind == "document_inserted":
            assert operation.collection and operation.query and operation.after
            current = database[operation.collection].find_one(dict(operation.query))
            if current is not None:
                if not db_import._catalog_documents_identical(current, dict(operation.after)):
                    raise RuntimeError("Inserted recovery document changed after failure")
                database[operation.collection].delete_one({"_id": current["_id"]})
            reverted += 1
        elif operation.kind == "document_replaced":
            assert operation.collection and operation.query and operation.before and operation.after
            current = database[operation.collection].find_one(dict(operation.query))
            if current is None or not db_import._catalog_documents_identical(
                current,
                dict(operation.after),
            ):
                raise RuntimeError("Replaced recovery document changed after failure")
            database[operation.collection].replace_one(
                dict(operation.query),
                dict(operation.before),
                upsert=False,
            )
            reverted += 1
        elif operation.kind == "collection_created":
            assert operation.collection
            if operation.collection in database.list_collection_names():
                if database[operation.collection].count_documents({}) != 0:
                    raise RuntimeError("Created recovery collection is no longer empty")
                database.drop_collection(operation.collection)
            reverted += 1
    return RecoveryReport(database_name, failure.backup_path, reverted)


__all__ = [
    "ConflictPolicy",
    "DatabaseUpdateApplyError",
    "DatabaseUpdatePlan",
    "DatabaseUpdateReport",
    "DocumentClassification",
    "ExistingDatabaseTarget",
    "GENERIC_COLLECTION_LABEL",
    "RecoveryReport",
    "StaleUpdatePlanError",
    "UpdateStrategy",
    "analyze_database_update",
    "apply_database_update",
    "bind_existing_database",
    "inspect_update_archive",
    "restore_failed_update",
    "validate_database_name",
]

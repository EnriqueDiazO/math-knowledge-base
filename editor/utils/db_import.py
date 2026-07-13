"""Conservative portable and historical MathMongo database import helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import stat
import time
import unicodedata
import zipfile
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps
from bson.json_util import loads as bson_json_loads
from pymongo.errors import DuplicateKeyError

from mathkb_config import DATA_DIR
from mathkb_config import IMPORT_COLLECTIONS
from mathkb_config import IMPORT_TIMEOUT_SECONDS
from mathkb_config import MEDIA_ASSETS_COLLECTION
from mathkb_config import MEDIA_ROOT
from mathkb_config import PORTABLE_EXTENDED_JSON_COLLECTIONS
from mathkb_config import READING_ANNOTATION_COLLECTIONS
from mathkb_config import SOURCE_CATALOG_COLLECTIONS
from mathmongo.paths import validate_mutable_path
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import ReadingNote
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.manifest import MigrationManifest
from mathmongo.source_catalog_migration.zip_reader import ZipSafetyLimits
from mathmongo.source_catalog_migration.zip_reader import ZipValidationError
from mathmongo.source_catalog_migration.zip_reader import _read_member
from mathmongo.source_catalog_migration.zip_reader import _validate_members
from mathmongo.source_documents.indexes import SourceDocumentIndexManager
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.storage import PreparedPdf
from mathmongo.source_documents.storage import SourceDocumentBlobStore

if TYPE_CHECKING:
    from mathdatabase.mathmongo import MathMongo

logger = logging.getLogger(__name__)

DEFAULT_IMPORT_COLLECTIONS = list(IMPORT_COLLECTIONS)

_CATALOG_ID_FIELDS = {
    "sources": "source_id",
    "references": "reference_id",
    MANIFEST_COLLECTION: "manifest_key",
}
_PORTABLE_ID_FIELDS = {
    **_CATALOG_ID_FIELDS,
    "source_documents": "document_id",
    "document_reading_state": "reading_state_id",
    "document_annotations": "annotation_id",
    "reading_notes": "note_id",
    "concept_evidence_links": "evidence_link_id",
}
_PORTABLE_IMPORT_ORDER = (
    "sources",
    "references",
    "source_documents",
    "document_reading_state",
    "document_annotations",
    "reading_notes",
    "concept_evidence_links",
    MANIFEST_COLLECTION,
)
CATALOG_EXTENDED_JSON_ENCODING = "mongodb_extended_json_v2_canonical"
_CATALOG_JSON_OPTIONS = CANONICAL_JSON_OPTIONS.with_options(
    tz_aware=True,
    tzinfo=timezone.utc,
)


@dataclass(frozen=True)
class CatalogImportConflict:
    """A Source Catalog document that cannot be imported safely."""

    collection: str
    domain_id: str
    reason: str


@dataclass
class DatabaseImportReport:
    """Structured import outcome, including non-destructive catalog decisions."""

    imported_counts: dict[str, int] = field(default_factory=dict)
    catalog_inserted: dict[str, int] = field(default_factory=dict)
    catalog_identical: dict[str, int] = field(default_factory=dict)
    catalog_conflicts: list[CatalogImportConflict] = field(default_factory=list)
    legacy_inserted: dict[str, int] = field(default_factory=dict)
    legacy_identical: dict[str, int] = field(default_factory=dict)
    source_document_blobs_created: int = 0
    source_document_blobs_identical: int = 0


@dataclass(frozen=True)
class _MediaRestorePlan:
    relative_path: Path
    destination: Path
    data: bytes


@dataclass(frozen=True)
class _SourceDocumentBlobPlan:
    prepared: PreparedPdf


class CatalogImportConflictError(RuntimeError):
    """Raised before importing when catalog IDs contain different data."""

    def __init__(self, report: DatabaseImportReport) -> None:
        """Retain the structured report and expose a safe conflict summary."""
        self.report = report
        summary = ", ".join(
            f"{item.collection}:{item.domain_id}" for item in report.catalog_conflicts
        )
        super().__init__(f"Source Catalog import conflicts require review: {summary}")


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
    "sources": (
        "created_at",
        "updated_at",
        "archived_at",
    ),
    "references": (
        "created_at",
        "updated_at",
        "archived_at",
        "accessed_at",
    ),
    "document_reading_state": (
        "last_opened_at",
        "first_opened_at",
        "completed_at",
        "created_at",
        "updated_at",
    ),
    "document_annotations": (
        "created_at",
        "updated_at",
        "archived_at",
    ),
    "reading_notes": (
        "created_at",
        "updated_at",
        "archived_at",
    ),
    "concept_evidence_links": (
        "created_at",
        "updated_at",
        "archived_at",
    ),
    MANIFEST_COLLECTION: (
        "created_at",
        "started_at",
        "completed_at",
        "last_updated_at",
    ),
}


_NESTED_DATETIME_FIELDS_BY_COLLECTION = {
    "references": (("provenance", "imported_at"),),
}


_OBJECT_ID_FIELDS_BY_COLLECTION = {
    "worklog_entries": ("deliverable_id",),
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
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid ISO datetime in {collection_name}.{field_name}: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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
            doc[field_name] = _restore_object_id(doc[field_name])

    for field_name in _OBJECT_ID_LIST_FIELDS_BY_COLLECTION.get(
        collection_name,
        (),
    ):
        values = doc.get(field_name)

        if isinstance(values, list):
            doc[field_name] = [_restore_object_id(value) for value in values]

    for path in _NESTED_DATETIME_FIELDS_BY_COLLECTION.get(collection_name, ()):
        parent: Any = doc
        for part in path[:-1]:
            if not isinstance(parent, dict):
                break
            parent = parent.get(part)
        else:
            field_name = path[-1]
            if isinstance(parent, dict) and field_name in parent:
                parent[field_name] = _restore_iso_datetime(
                    parent[field_name],
                    collection_name=collection_name,
                    field_name=".".join(path),
                )

    if collection_name == MANIFEST_COLLECTION:
        errors = doc.get("errors")
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, dict) and "occurred_at" in error:
                    error["occurred_at"] = _restore_iso_datetime(
                        error["occurred_at"],
                        collection_name=collection_name,
                        field_name="errors.occurred_at",
                    )
        backup_evidence = doc.get("production_backup_evidence")
        if isinstance(backup_evidence, dict):
            for field_name in ("exported_at", "completed_at", "write_freeze_at"):
                if field_name in backup_evidence:
                    backup_evidence[field_name] = _restore_iso_datetime(
                        backup_evidence[field_name],
                        collection_name=collection_name,
                        field_name=f"production_backup_evidence.{field_name}",
                    )

    return doc


def _safe_media_member_path(base_dir: str, member_name: str) -> Path | None:
    prefix = f"{base_dir}/{MEDIA_ROOT.as_posix()}/"
    if not member_name.startswith(prefix) or member_name.endswith("/"):
        return None
    rel_path = Path(member_name[len(base_dir) + 1 :])
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError(f"Unsafe media path in export ZIP: {member_name}")
    return rel_path


_SOURCE_DOCUMENT_BLOB_RE = re.compile(
    r"^source_documents/blobs/sha256/([0-9a-f]{2})/([0-9a-f]{64})\.pdf$"
)
_SUPPORTED_ZIP_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})


def _source_document_blob_logical_path(base_dir: str, member_name: str) -> str | None:
    """Return one exact content-addressed blob path from a portable ZIP member."""
    prefix = f"{base_dir}/"
    if not member_name.startswith(prefix):
        return None
    relative = member_name[len(prefix) :]
    match = _SOURCE_DOCUMENT_BLOB_RE.fullmatch(relative)
    if match is None:
        return None
    shard, digest = match.groups()
    if shard != digest[:2]:
        raise ValueError("Source Document blob shard does not match its SHA-256")
    return relative


def _is_portable_extension_zip_member(base_dir: str, member_name: str) -> bool:
    """Identify portable members unknown to the frozen legacy ZIP validator."""
    return member_name in {
        f"{base_dir}/collections/source_documents.json",
        f"{base_dir}/collections/document_reading_state.json",
        *(f"{base_dir}/collections/{name}.json" for name in READING_ANNOTATION_COLLECTIONS),
    } or member_name.startswith(f"{base_dir}/source_documents/")


def _zip_member_kind(info: zipfile.ZipInfo) -> str:
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


def _validate_portable_extension_zip_members(
    infos: list[zipfile.ZipInfo],
    *,
    base_dir: str,
    limits: ZipSafetyLimits,
) -> tuple[zipfile.ZipInfo, ...]:
    """Validate S2-S4 members before excluding them from the legacy validator."""
    if len(infos) > limits.max_members:
        raise ZipValidationError("member_limit", "ZIP archive exceeds its member limit")
    if sum(info.file_size for info in infos) > limits.max_total_bytes:
        raise ZipValidationError("total_size_limit", "ZIP archive exceeds its total size limit")

    selected: list[zipfile.ZipInfo] = []
    for info in infos:
        if not _is_portable_extension_zip_member(base_dir, info.filename):
            continue
        selected.append(info)
        is_collection = info.filename in {
            f"{base_dir}/collections/source_documents.json",
            f"{base_dir}/collections/document_reading_state.json",
            *(f"{base_dir}/collections/{name}.json" for name in READING_ANNOTATION_COLLECTIONS),
        }
        logical_path = _source_document_blob_logical_path(base_dir, info.filename)
        if not is_collection and logical_path is None:
            raise ZipValidationError(
                "unexpected_member",
                "ZIP archive contains an invalid portable extension member",
                member=info.filename,
            )
        path = PurePosixPath(info.filename)
        if path.as_posix() != info.filename or any(part in {"", ".", ".."} for part in path.parts):
            raise ZipValidationError(
                "unsafe_path",
                "Source Document ZIP member path is not canonical",
                member=info.filename,
            )
        if info.flag_bits & 0x1:
            raise ZipValidationError(
                "encrypted_member",
                "Encrypted ZIP members are not supported",
                member=info.filename,
            )
        if info.compress_type not in _SUPPORTED_ZIP_COMPRESSION:
            raise ZipValidationError(
                "unsupported_compression",
                "ZIP member uses an unsupported compression method",
                member=info.filename,
            )
        if _zip_member_kind(info) != "regular" or info.is_dir():
            raise ZipValidationError(
                "nonregular_member",
                "Portable extension ZIP members must be regular files",
                member=info.filename,
            )
        if info.file_size <= 0:
            raise ZipValidationError(
                "empty_regular_member",
                "ZIP archive contains an empty portable extension member",
                member=info.filename,
            )
        if info.file_size > limits.max_member_bytes:
            raise ZipValidationError(
                "member_size_limit",
                "ZIP member exceeds its size limit",
                member=info.filename,
            )
        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > float(limits.max_compression_ratio):
            raise ZipValidationError(
                "compression_ratio_limit",
                "ZIP member has an anomalous compression ratio",
                member=info.filename,
            )
    return tuple(selected)


def _descriptor_has_bytes(descriptor: int, data: bytes) -> bool:
    """Compare stable regular-file bytes through an already anchored descriptor."""
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        return False
    content = bytearray()
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > len(data):
            return False
    after = os.fstat(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    return identity_before == identity_after and bytes(content) == data


def _same_bytes(path: Path, data: bytes) -> bool:
    """Compare one regular file through a stable no-follow descriptor."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ValueError(f"Could not safely inspect import destination {path}") from exc
    try:
        return _descriptor_has_bytes(descriptor, data)
    finally:
        os.close(descriptor)


def _matching_file_identity_at(
    parent_descriptor: int,
    name: str,
    data: bytes,
) -> tuple[int, int] | None:
    """Return one direct child's inode only when its anchored bytes are exact."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"Could not safely inspect import destination {name}") from exc
    try:
        opened = os.fstat(descriptor)
        if not _descriptor_has_bytes(descriptor, data):
            return None
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        identity = (opened.st_dev, opened.st_ino)
        return identity if (named.st_dev, named.st_ino) == identity else None
    finally:
        os.close(descriptor)


def _same_bytes_at(parent_descriptor: int, name: str, data: bytes) -> bool:
    return _matching_file_identity_at(parent_descriptor, name, data) is not None


def _reusable_import_destination(path: Path, data: bytes) -> Path | None:
    """Find a bounded historical remap with the same immutable bytes."""
    if not path.parent.is_dir():
        return None
    stem = path.stem
    suffix = path.suffix
    prefix = f"{stem}_imported_"
    names: list[str] = []
    with os.scandir(path.parent) as entries:
        for ordinal, entry in enumerate(entries, start=1):
            if ordinal > 10_000:
                raise FileExistsError(f"Too many files while resolving import path for {path}")
            if entry.name.startswith(prefix) and entry.name.endswith(suffix):
                names.append(entry.name)
                if len(names) > 1_000:
                    raise FileExistsError(f"Too many collision paths for {path}")
    for name in sorted(names):
        candidate = validate_mutable_path(path.with_name(name), allowed_root=DATA_DIR)
        if _same_bytes(candidate, data):
            return candidate
    return None


def _content_addressed_import_destination(path: Path, data: bytes) -> Path:
    """Choose a stable collision path and reuse an identical prior import."""
    reusable = _reusable_import_destination(path, data)
    if reusable is not None:
        return reusable
    stem = path.stem
    suffix = path.suffix
    digest = hashlib.sha256(data).hexdigest()[:16]
    for index in range(1000):
        discriminator = "" if index == 0 else f"_{index}"
        candidate = path.with_name(f"{stem}_imported_{digest}{discriminator}{suffix}")
        candidate = validate_mutable_path(candidate, allowed_root=DATA_DIR)
        if not candidate.exists() or _same_bytes(candidate, data):
            return candidate
    raise FileExistsError(f"Could not allocate a unique import path for {path}")


def _open_private_import_directory(directory: Path, *, create: bool = True) -> int:
    """Open a DATA_DIR descendant through anchored no-follow dirfds."""
    data_root = validate_mutable_path(DATA_DIR)
    directory = validate_mutable_path(directory, allowed_root=data_root)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    current_descriptor = os.open(directory.anchor, directory_flags)
    current_path = Path(directory.anchor)
    try:
        for part in directory.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(
                part,
                directory_flags,
                dir_fd=current_descriptor,
            )
            os.close(current_descriptor)
            current_descriptor = next_descriptor
            current_path /= part
            if create and (current_path == data_root or current_path.is_relative_to(data_root)):
                current_mode = stat.S_IMODE(os.fstat(current_descriptor).st_mode)
                if current_mode != 0o700:
                    os.fchmod(current_descriptor, 0o700)
        return current_descriptor
    except Exception:
        os.close(current_descriptor)
        raise


def _require_current_media_destination(
    path: Path,
    pinned_parent_descriptor: int,
    expected_identity: tuple[int, int],
    data: bytes,
) -> None:
    """Reopen lexical parent and prove exact name, inode, and bytes before success."""
    try:
        current_parent_descriptor = _open_private_import_directory(
            path.parent,
            create=False,
        )
    except Exception as exc:
        raise FileExistsError(
            f"Import destination parent is no longer reachable: {path.parent}"
        ) from exc
    try:
        pinned_parent = os.fstat(pinned_parent_descriptor)
        current_parent = os.fstat(current_parent_descriptor)
        if (pinned_parent.st_dev, pinned_parent.st_ino) != (
            current_parent.st_dev,
            current_parent.st_ino,
        ):
            raise FileExistsError(
                f"Import destination parent changed before completion: {path.parent}"
            )
        current_identity = _matching_file_identity_at(
            current_parent_descriptor,
            path.name,
            data,
        )
        if current_identity != expected_identity:
            raise FileExistsError(
                f"Import destination identity or bytes changed before completion: {path}"
            )
    finally:
        os.close(current_parent_descriptor)

    try:
        final_parent_descriptor = _open_private_import_directory(
            path.parent,
            create=False,
        )
    except Exception as exc:
        raise FileExistsError(
            f"Import destination parent moved at completion: {path.parent}"
        ) from exc
    try:
        pinned_parent = os.fstat(pinned_parent_descriptor)
        final_parent = os.fstat(final_parent_descriptor)
        if (pinned_parent.st_dev, pinned_parent.st_ino) != (
            final_parent.st_dev,
            final_parent.st_ino,
        ):
            raise FileExistsError(f"Import destination parent changed at completion: {path.parent}")
        final_identity = _matching_file_identity_at(
            final_parent_descriptor,
            path.name,
            data,
        )
        if final_identity != expected_identity:
            raise FileExistsError(
                f"Import destination identity or bytes changed at completion: {path}"
            )
    finally:
        os.close(final_parent_descriptor)


def _write_media_file_exclusive(path: Path, data: bytes) -> bool:
    """Stage anonymously, then publish without overwrite in the validated parent."""
    path = validate_mutable_path(path, allowed_root=DATA_DIR)
    parent_descriptor = _open_private_import_directory(path.parent)
    descriptor: int | None = None
    try:
        existing_identity = _matching_file_identity_at(
            parent_descriptor,
            path.name,
            data,
        )
        if existing_identity is not None:
            _require_current_media_destination(
                path,
                parent_descriptor,
                existing_identity,
                data,
            )
            return False
        temporary_flag = getattr(os, "O_TMPFILE", 0)
        if not temporary_flag:
            raise OSError("This platform cannot stage media through anonymous files")
        try:
            descriptor = os.open(
                ".",
                os.O_RDWR | temporary_flag | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise OSError(
                f"The destination filesystem cannot stage media safely: {path.parent}"
            ) from exc

        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError(f"Could not complete media restore for {path}")
            written += count
        os.fchmod(descriptor, 0o600)
        staged_stat = os.fstat(descriptor)
        staged_identity = (staged_stat.st_dev, staged_stat.st_ino)
        published = True
        expected_final_identity = staged_identity

        try:
            current_parent_descriptor = _open_private_import_directory(
                path.parent,
                create=False,
            )
        except Exception as exc:
            raise FileExistsError(
                f"Import destination parent moved during creation: {path.parent}"
            ) from exc
        try:
            pinned_parent = os.fstat(parent_descriptor)
            current_parent = os.fstat(current_parent_descriptor)
            if (pinned_parent.st_dev, pinned_parent.st_ino) != (
                current_parent.st_dev,
                current_parent.st_ino,
            ):
                raise FileExistsError(
                    f"Import destination parent changed during creation: {path.parent}"
                )
            try:
                os.link(
                    f"/proc/self/fd/{descriptor}",
                    path.name,
                    dst_dir_fd=current_parent_descriptor,
                    follow_symlinks=True,
                )
            except FileExistsError as exc:
                existing_identity = _matching_file_identity_at(
                    current_parent_descriptor,
                    path.name,
                    data,
                )
                if existing_identity is not None:
                    expected_final_identity = existing_identity
                    published = False
                else:
                    raise FileExistsError(
                        f"Import destination changed before publication: {path}"
                    ) from exc
        finally:
            os.close(current_parent_descriptor)

        _require_current_media_destination(
            path,
            parent_descriptor,
            expected_final_identity,
            data,
        )
        return published
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_descriptor)


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


def _catalog_comparable(value):
    """Canonicalize exact BSON type/value identity, including int32 versus int64."""
    return json.loads(
        bson_json_dumps(
            value,
            json_options=CANONICAL_JSON_OPTIONS,
            ensure_ascii=False,
        )
    )


def _catalog_documents_identical(existing: dict, incoming: dict) -> bool:
    return _catalog_comparable(existing) == _catalog_comparable(incoming)


def _find_at_most_two(collection, query: dict) -> tuple[dict, ...]:
    """Expose duplicate destination identities without an unbounded query."""
    cursor = collection.find(query)
    max_time_ms = getattr(cursor, "max_time_ms", None)
    if callable(max_time_ms):
        cursor = max_time_ms(IMPORT_TIMEOUT_SECONDS * 1000)
    limit = getattr(cursor, "limit", None)
    if callable(limit):
        cursor = limit(2)
    matches: list[dict] = []
    try:
        for document in cursor:
            if not isinstance(document, dict):
                raise ValueError("MongoDB returned a non-document import identity match")
            matches.append(document)
            if len(matches) == 2:
                break
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()
    return tuple(matches)


def _catalog_member_names(
    names: list[str],
    *,
    base_dir: str,
) -> dict[str, str]:
    return {
        collection_name: member_name
        for collection_name, member_name in _collection_member_names(
            names,
            base_dir=base_dir,
        ).items()
        if collection_name in SOURCE_CATALOG_COLLECTIONS
    }


def _portable_member_names(
    names: list[str],
    *,
    base_dir: str,
) -> dict[str, str]:
    return {
        collection_name: member_name
        for collection_name, member_name in _collection_member_names(
            names,
            base_dir=base_dir,
        ).items()
        if collection_name in PORTABLE_EXTENDED_JSON_COLLECTIONS
    }


def _collection_member_names(
    names: list[str],
    *,
    base_dir: str,
) -> dict[str, str]:
    """Require one exact non-nested member for each collection stem."""
    if len(names) != len(set(names)):
        raise ValueError("Export ZIP contains duplicate member names")
    modern_prefix = f"{base_dir}/collections/"
    legacy_prefix = f"{base_dir}/"
    modern_members: dict[str, str] = {}
    legacy_members: dict[str, str] = {}
    allowed_collections = set(IMPORT_COLLECTIONS) | set(PORTABLE_EXTENDED_JSON_COLLECTIONS)
    for name in names:
        if not name.endswith(".json"):
            continue
        if name.startswith(modern_prefix):
            relative = name[len(modern_prefix) :]
            target = modern_members
        elif name.startswith(legacy_prefix):
            relative = name[len(legacy_prefix) :]
            if relative == "metadata.json":
                continue
            target = legacy_members
        else:
            continue
        if not relative or "/" in relative or "\\" in relative:
            if name.startswith(modern_prefix):
                raise ValueError("Export ZIP contains a nested or ambiguous collection member")
            continue
        collection_name = relative[:-5]
        if not collection_name or collection_name in target:
            raise ValueError("Export ZIP contains duplicate collection identities")
        if collection_name not in allowed_collections:
            raise ValueError(f"Export ZIP contains unsupported collection {collection_name!r}")
        target[collection_name] = name
    if modern_members and legacy_members:
        raise ValueError("Export ZIP mixes modern and historical collection layouts")
    return modern_members or legacy_members


def _collection_encodings(metadata: Any) -> dict[str, str]:
    """Validate optional per-collection codecs without breaking historical ZIPs."""
    if not isinstance(metadata, dict):
        raise ValueError("metadata.json must contain an object")
    raw = metadata.get("collection_encodings", {})
    if not isinstance(raw, dict):
        raise ValueError("metadata.collection_encodings must contain an object")
    encodings: dict[str, str] = {}
    for collection_name, encoding in raw.items():
        if collection_name not in PORTABLE_EXTENDED_JSON_COLLECTIONS:
            raise ValueError("metadata declares an encoding for an unsupported collection")
        if encoding != CATALOG_EXTENDED_JSON_ENCODING:
            raise ValueError("metadata declares an unsupported collection encoding")
        encodings[str(collection_name)] = str(encoding)
    return encodings


def _validate_zip_safety(zf: zipfile.ZipFile, *, expected_base: str) -> None:
    """Apply S1C1 checks plus the separately bounded S2-S4 member namespace."""
    infos = zf.infolist()
    raw_names: set[str] = set()
    normalized_names: set[str] = set()
    for info in infos:
        normalized_name = unicodedata.normalize("NFC", info.filename)
        if info.filename in raw_names or normalized_name in normalized_names:
            raise ZipValidationError(
                "duplicate_member",
                "ZIP archive contains a duplicate member",
                member=info.filename,
            )
        raw_names.add(info.filename)
        normalized_names.add(normalized_name)
    limits = ZipSafetyLimits()
    portable_extension_infos = _validate_portable_extension_zip_members(
        infos,
        base_dir=expected_base,
        limits=limits,
    )
    excluded = {id(info) for info in portable_extension_infos}
    legacy_infos = [info for info in infos if id(info) not in excluded]
    base, _members, _report = _validate_members(legacy_infos, limits)
    if base != expected_base:
        raise ZipValidationError("ambiguous_root", "ZIP base directory changed")
    corrupt_member = zf.testzip()
    if corrupt_member is not None:
        raise ZipValidationError(
            "crc_mismatch",
            "ZIP member failed its CRC check",
            member=corrupt_member,
        )


def _read_zip_member(zf: zipfile.ZipFile, member_name: str) -> bytes:
    """Read exactly one already-bounded member through the streaming guard."""
    try:
        info = zf.getinfo(member_name)
    except KeyError as exc:
        raise ValueError(f"ZIP member is missing: {member_name}") from exc
    data, _sha256 = _read_member(zf, info)
    return data


def _read_collection_documents(
    zf: zipfile.ZipFile,
    member_name: str,
    *,
    collection_name: str,
    encodings: dict[str, str],
) -> list[Any]:
    """Decode one collection using its explicit codec or the historical JSON fallback."""
    data = _read_zip_member(zf, member_name).decode("utf-8")
    if encodings.get(collection_name) == CATALOG_EXTENDED_JSON_ENCODING:
        payload = bson_json_loads(data, json_options=_CATALOG_JSON_OPTIONS)
    else:
        payload = json.loads(data)
    if not isinstance(payload, list):
        raise ValueError(f"Collection {collection_name} must contain a JSON array")
    return payload


def _validate_import_metadata(
    zf: zipfile.ZipFile,
    names: list[str],
    *,
    base_dir: str,
    metadata: Any,
    collection_members: dict[str, str],
    encodings: dict[str, str],
) -> dict[str, int]:
    """Bind declared collection/media inventory to exact physical ZIP members."""
    if not isinstance(metadata, dict):
        raise ValueError("metadata.json must contain an object")
    format_declared = "format" in metadata or "format_version" in metadata
    if format_declared:
        if (
            metadata.get("format") != "mathkb_legacy_export"
            or str(metadata.get("format_version")) != "1"
        ):
            raise ValueError("metadata declares an unsupported export format or version")
        if (
            not isinstance(metadata.get("database_name"), str)
            or not metadata["database_name"].strip()
        ):
            raise ValueError("versioned metadata requires a database_name")
        if "media_files" not in metadata:
            raise ValueError("versioned metadata requires an exact media inventory")
        portable_members = set(collection_members) & set(PORTABLE_EXTENDED_JSON_COLLECTIONS)
        if set(encodings) != portable_members:
            raise ValueError(
                "versioned portable collections require canonical Extended JSON encodings"
            )
    declared_collections = metadata.get("collections")
    if not isinstance(declared_collections, dict) or any(
        not isinstance(name, str)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count < 0
        for name, count in declared_collections.items()
    ):
        raise ValueError("metadata.collections must contain non-negative integer counts")
    if set(encodings) - set(collection_members):
        raise ValueError("metadata declares an encoding for an absent collection")

    actual_collections: dict[str, int] = {}
    for collection_name, member_name in collection_members.items():
        actual_collections[collection_name] = len(
            _read_collection_documents(
                zf,
                member_name,
                collection_name=collection_name,
                encodings=encodings,
            )
        )
    if declared_collections != actual_collections:
        raise ValueError("metadata collection inventory does not match physical ZIP members")

    actual_media: dict[str, int] = {}
    for member_name in names:
        relative_path = _safe_media_member_path(base_dir, member_name)
        if relative_path is not None:
            relative_name = relative_path.as_posix()
            if relative_name in actual_media:
                raise ValueError("ZIP contains duplicate normalized media paths")
            actual_media[relative_name] = zf.getinfo(member_name).file_size
    if "media_files" in metadata:
        declared_media = metadata["media_files"]
        if not isinstance(declared_media, dict) or any(
            not isinstance(name, str)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            for name, size in declared_media.items()
        ):
            raise ValueError("metadata.media_files must contain non-negative integer sizes")
        if declared_media != actual_media:
            raise ValueError("metadata media inventory does not match physical ZIP members")

    actual_source_document_blobs: dict[str, dict[str, Any]] = {}
    for member_name in names:
        logical_path = _source_document_blob_logical_path(base_dir, member_name)
        if logical_path is None:
            continue
        info = zf.getinfo(member_name)
        data = _read_zip_member(zf, member_name)
        prepared = SourceDocumentBlobStore.prepare_pdf(data)
        if prepared.logical_path != logical_path:
            raise ValueError("Physical Source Document blob path does not match its PDF bytes")
        actual_source_document_blobs[logical_path] = {
            "sha256": prepared.sha256,
            "size_bytes": info.file_size,
        }
    if "source_documents" in collection_members and format_declared:
        if "source_document_blobs" not in metadata:
            raise ValueError("versioned Source Documents require an exact blob inventory")
    declared_blobs = metadata.get("source_document_blobs", {})
    if not isinstance(declared_blobs, dict):
        raise ValueError("metadata.source_document_blobs must contain an object")
    normalized_blobs: dict[str, dict[str, Any]] = {}
    for logical_path, identity in declared_blobs.items():
        if (
            not isinstance(logical_path, str)
            or _SOURCE_DOCUMENT_BLOB_RE.fullmatch(logical_path) is None
            or not isinstance(identity, dict)
            or set(identity) != {"sha256", "size_bytes"}
            or not isinstance(identity.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", identity["sha256"])
            or isinstance(identity.get("size_bytes"), bool)
            or not isinstance(identity.get("size_bytes"), int)
            or identity["size_bytes"] <= 0
        ):
            raise ValueError("metadata Source Document blob inventory is invalid")
        match = _SOURCE_DOCUMENT_BLOB_RE.fullmatch(logical_path)
        assert match is not None
        shard, path_sha = match.groups()
        if shard != path_sha[:2] or identity["sha256"] != path_sha:
            raise ValueError("metadata Source Document blob identity is not canonical")
        normalized_blobs[logical_path] = dict(identity)
    if normalized_blobs != actual_source_document_blobs:
        raise ValueError(
            "metadata Source Document blob inventory does not match physical ZIP members"
        )
    return actual_collections


def _load_legacy_documents(
    zf: zipfile.ZipFile,
    collection_members: dict[str, str],
    *,
    encodings: dict[str, str],
) -> dict[str, list[dict]]:
    """Decode every non-catalog collection before any filesystem or DB mutation."""
    collections: dict[str, list[dict]] = {}
    for collection_name, member_name in collection_members.items():
        if collection_name in PORTABLE_EXTENDED_JSON_COLLECTIONS:
            continue
        raw_documents = _read_collection_documents(
            zf,
            member_name,
            collection_name=collection_name,
            encodings=encodings,
        )
        documents: list[dict] = []
        for raw_document in raw_documents:
            document = _restore_mongo_types(raw_document, collection_name)
            if not isinstance(document, dict):
                raise ValueError(f"Legacy collection {collection_name} must contain JSON objects")
            documents.append(document)
        collections[collection_name] = documents
    return collections


def _preferred_existing_media_destination(
    db,
    media_documents: list[dict],
    *,
    original_relative_path: str,
    data: bytes,
) -> Path | None:
    """Reuse the remap already persisted for the same media-asset identity."""
    for document in media_documents:
        if document.get("path") != original_relative_path or "_id" not in document:
            continue
        existing = db[MEDIA_ASSETS_COLLECTION].find_one({"_id": document["_id"]})
        if not isinstance(existing, dict):
            continue
        existing_path = existing.get("path")
        if not isinstance(existing_path, str) or existing_path == original_relative_path:
            continue
        candidate = validate_mutable_path(DATA_DIR / existing_path, allowed_root=DATA_DIR)
        if _same_bytes(candidate, data):
            return candidate
    return None


def _plan_media_restores(
    zf: zipfile.ZipFile,
    names: list[str],
    *,
    base_dir: str,
    db,
    legacy_documents: dict[str, list[dict]],
    started_at: float,
) -> tuple[list[_MediaRestorePlan], dict[str, str]]:
    """Plan stable media destinations without creating directories or files."""
    plans: list[_MediaRestorePlan] = []
    path_remap: dict[str, str] = {}
    media_documents = legacy_documents.get(MEDIA_ASSETS_COLLECTION, [])
    for member_name in names:
        relative_path = _safe_media_member_path(base_dir, member_name)
        if relative_path is None:
            continue
        _raise_if_timed_out(
            started_at,
            IMPORT_TIMEOUT_SECONDS,
            f"planning media restore {relative_path}",
        )
        data = _read_zip_member(zf, member_name)
        destination = validate_mutable_path(
            DATA_DIR / relative_path,
            allowed_root=DATA_DIR,
        )
        if not _same_bytes(destination, data):
            original_relative_path = relative_path.as_posix()
            reusable = _preferred_existing_media_destination(
                db,
                media_documents,
                original_relative_path=original_relative_path,
                data=data,
            ) or _reusable_import_destination(destination, data)
            if reusable is not None:
                destination = reusable
                path_remap[original_relative_path] = destination.relative_to(DATA_DIR).as_posix()
            elif destination.exists():
                destination = _content_addressed_import_destination(destination, data)
                path_remap[original_relative_path] = destination.relative_to(DATA_DIR).as_posix()
        plans.append(
            _MediaRestorePlan(
                relative_path=relative_path,
                destination=destination,
                data=data,
            )
        )
    return plans, path_remap


def _prepare_legacy_import(
    legacy_documents: dict[str, list[dict]],
    *,
    path_remap: dict[str, str],
    db,
    report: DatabaseImportReport,
) -> dict[str, list[dict]]:
    """Preflight all remapped legacy documents before writing media or MongoDB."""
    pending: dict[str, list[dict]] = {}
    for collection_name, raw_documents in legacy_documents.items():
        documents: list[dict] = []
        seen: dict[Any, dict] = {}
        for raw_document in raw_documents:
            original_media_path = (
                raw_document.get("path") if collection_name == MEDIA_ASSETS_COLLECTION else None
            )
            document = _remap_media_paths_in_value(raw_document, path_remap)
            if isinstance(original_media_path, str) and original_media_path in path_remap:
                document["filename"] = Path(document["path"]).name

            storage_id = document.get("_id")
            if storage_id is not None:
                previous = seen.get(storage_id)
                if previous is not None:
                    reason = (
                        "duplicate identical legacy _id in archive"
                        if _catalog_documents_identical(previous, document)
                        else "duplicate legacy _id with different data in archive"
                    )
                    report.catalog_conflicts.append(
                        CatalogImportConflict(collection_name, str(storage_id), reason)
                    )
                    continue
                seen[storage_id] = document
                existing = db[collection_name].find_one({"_id": storage_id})
                if existing is not None and not _catalog_documents_identical(
                    existing,
                    document,
                ):
                    report.catalog_conflicts.append(
                        CatalogImportConflict(
                            collection_name,
                            str(storage_id),
                            "destination contains different legacy data for the same _id",
                        )
                    )
                    continue
            documents.append(document)
        pending[collection_name] = documents
    return pending


def _require_existing_documents_are_archive_subset(
    db,
    archive_documents: dict[str, list[dict]],
) -> None:
    """Allow a versioned same-name restore only into an empty or partial exact restore."""
    for collection_name in db.list_collection_names():
        incoming = archive_documents.get(collection_name)
        if incoming is None:
            raise ValueError("Same-name MathV0 restore found a collection absent from the archive")
        cursor = db[collection_name].find({})
        max_time_ms = getattr(cursor, "max_time_ms", None)
        if callable(max_time_ms):
            cursor = max_time_ms(IMPORT_TIMEOUT_SECONDS * 1000)
        limit = getattr(cursor, "limit", None)
        if callable(limit):
            cursor = limit(len(incoming) + 1)
        remaining = list(incoming)
        try:
            for existing in cursor:
                if not isinstance(existing, dict):
                    raise ValueError("Same-name MathV0 restore read a non-document value")
                match = next(
                    (
                        index
                        for index, candidate in enumerate(remaining)
                        if _catalog_documents_identical(existing, candidate)
                    ),
                    None,
                )
                if match is None:
                    raise ValueError(
                        "Same-name MathV0 restore found data not identical to the archive"
                    )
                remaining.pop(match)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()


def _validate_portable_manifest(document: dict) -> dict:
    """Validate imported manifest authority without rewriting its original target."""
    payload = {key: value for key, value in document.items() if key != "_id"}
    try:
        manifest = MigrationManifest.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("The imported Source Catalog manifest is invalid") from exc
    if document.get("_id") != manifest.manifest_key:
        raise ValueError("The imported manifest _id must equal manifest_key")
    return manifest.model_dump(mode="python")


def _prepare_catalog_import(
    zf: zipfile.ZipFile,
    names: list[str],
    *,
    base_dir: str,
    db,
    report: DatabaseImportReport,
    started_at: float,
    encodings: dict[str, str],
    legacy_concepts: list[dict],
) -> dict[str, list[dict]]:
    """Preflight catalog documents without modifying the destination database."""
    pending: dict[str, list[dict]] = {}
    member_names = _portable_member_names(
        names,
        base_dir=base_dir,
    )
    for collection_name in _PORTABLE_IMPORT_ORDER:
        member_name = member_names.get(collection_name)
        if member_name is None:
            continue
        raw_documents = _read_collection_documents(
            zf,
            member_name,
            collection_name=collection_name,
            encodings=encodings,
        )

        id_field = _PORTABLE_ID_FIELDS[collection_name]
        seen: dict[str, dict] = {}
        seen_storage_ids: dict[Any, str] = {}
        collection_pending: list[dict] = []
        for index, raw_document in enumerate(raw_documents, start=1):
            if index == 1 or index % 100 == 0:
                _raise_if_timed_out(
                    started_at,
                    IMPORT_TIMEOUT_SECONDS,
                    f"preflighting {collection_name}",
                )
            if not isinstance(raw_document, dict):
                report.catalog_conflicts.append(
                    CatalogImportConflict(
                        collection_name,
                        f"<entry:{index}>",
                        "expected a JSON object",
                    )
                )
                continue
            document = (
                dict(raw_document)
                if encodings.get(collection_name) == CATALOG_EXTENDED_JSON_ENCODING
                else _restore_mongo_types(raw_document, collection_name)
            )
            domain_id = document.get(id_field)
            if not isinstance(domain_id, str) or not domain_id.strip():
                report.catalog_conflicts.append(
                    CatalogImportConflict(
                        collection_name,
                        f"<entry:{index}>",
                        f"missing {id_field}",
                    )
                )
                continue

            if collection_name == MANIFEST_COLLECTION:
                try:
                    validated_payload = _validate_portable_manifest(document)
                except ValueError as exc:
                    report.catalog_conflicts.append(
                        CatalogImportConflict(collection_name, domain_id, str(exc))
                    )
                    continue
                portable_payload = {key: value for key, value in document.items() if key != "_id"}
                if encodings.get(
                    collection_name
                ) == CATALOG_EXTENDED_JSON_ENCODING and not _catalog_documents_identical(
                    portable_payload,
                    validated_payload,
                ):
                    report.catalog_conflicts.append(
                        CatalogImportConflict(
                            collection_name,
                            domain_id,
                            "non-canonical portable manifest document",
                        )
                    )
                    continue
            elif collection_name in {
                "sources",
                "references",
                "source_documents",
                "document_reading_state",
                "document_annotations",
                "reading_notes",
                "concept_evidence_links",
            }:
                model = {
                    "sources": Source,
                    "references": Reference,
                    "source_documents": SourceDocument,
                    "document_reading_state": DocumentReadingState,
                    "document_annotations": DocumentAnnotation,
                    "reading_notes": ReadingNote,
                    "concept_evidence_links": ConceptEvidenceLink,
                }[collection_name]
                portable_payload = {key: value for key, value in document.items() if key != "_id"}
                try:
                    validated_payload = model.model_validate(portable_payload).model_dump(
                        mode="python"
                    )
                except (TypeError, ValueError):
                    report.catalog_conflicts.append(
                        CatalogImportConflict(
                            collection_name,
                            domain_id,
                            f"invalid portable {collection_name.rstrip('s')} document",
                        )
                    )
                    continue
                if encodings.get(
                    collection_name
                ) == CATALOG_EXTENDED_JSON_ENCODING and not _catalog_documents_identical(
                    portable_payload,
                    validated_payload,
                ):
                    report.catalog_conflicts.append(
                        CatalogImportConflict(
                            collection_name,
                            domain_id,
                            f"non-canonical portable {collection_name.rstrip('s')} document",
                        )
                    )
                    continue

            previous = seen.get(domain_id)
            if previous is not None:
                reason = (
                    "duplicate identical domain ID in archive"
                    if _catalog_documents_identical(previous, document)
                    else "duplicate domain ID with different data in archive"
                )
                report.catalog_conflicts.append(
                    CatalogImportConflict(collection_name, domain_id, reason)
                )
                continue
            seen[domain_id] = document

            storage_id = document.get("_id")
            if storage_id is not None:
                previous_domain_id = seen_storage_ids.get(storage_id)
                if previous_domain_id is not None and previous_domain_id != domain_id:
                    report.catalog_conflicts.append(
                        CatalogImportConflict(
                            collection_name,
                            domain_id,
                            "duplicate MongoDB _id assigned to different domain IDs in archive",
                        )
                    )
                    continue
                seen_storage_ids[storage_id] = domain_id

            domain_matches = _find_at_most_two(
                db[collection_name],
                {id_field: domain_id},
            )
            if len(domain_matches) > 1:
                report.catalog_conflicts.append(
                    CatalogImportConflict(
                        collection_name,
                        domain_id,
                        "destination contains duplicate documents for the same domain ID",
                    )
                )
                continue
            existing = domain_matches[0] if domain_matches else None
            if existing is None:
                if storage_id is not None:
                    storage_matches = _find_at_most_two(
                        db[collection_name],
                        {"_id": storage_id},
                    )
                    if len(storage_matches) != 0:
                        report.catalog_conflicts.append(
                            CatalogImportConflict(
                                collection_name,
                                domain_id,
                                "destination MongoDB _id belongs to a different domain ID",
                            )
                        )
                        continue
            elif _catalog_documents_identical(existing, document):
                pass
            else:
                report.catalog_conflicts.append(
                    CatalogImportConflict(
                        collection_name,
                        domain_id,
                        "destination contains different data for the same domain ID",
                    )
                )
                continue
            collection_pending.append(document)
        pending[collection_name] = collection_pending

    available_source_ids = set()
    for document in pending.get("sources", []):
        source_id = document.get("source_id")
        if isinstance(source_id, str):
            available_source_ids.add(source_id)
    for reference in pending.get("references", []):
        reference_id = str(reference.get("reference_id") or "<reference>")
        source_ids = reference.get("source_ids")
        if not isinstance(source_ids, list) or not all(
            isinstance(source_id, str) and source_id for source_id in source_ids
        ):
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "references",
                    reference_id,
                    "source_ids must be a list of nonempty Source IDs",
                )
            )
            continue
        for source_id in source_ids:
            if source_id in available_source_ids:
                continue
            source_matches = _find_at_most_two(
                db["sources"],
                {"source_id": source_id},
            )
            if len(source_matches) != 1:
                report.catalog_conflicts.append(
                    CatalogImportConflict(
                        "references",
                        reference_id,
                        "Reference points to a Source ID absent from archive and destination",
                    )
                )
    for document in pending.get("source_documents", []):
        document_id = str(document.get("document_id") or "<document>")
        source_id = document.get("source_id")
        if not isinstance(source_id, str):
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "source_documents",
                    document_id,
                    "Source Document requires a Source ID",
                )
            )
            continue
        if source_id not in available_source_ids:
            source_matches = _find_at_most_two(db["sources"], {"source_id": source_id})
            if len(source_matches) != 1:
                report.catalog_conflicts.append(
                    CatalogImportConflict(
                        "source_documents",
                        document_id,
                        "Source Document points to a Source ID absent from archive and destination",
                    )
                )
                continue
        reference_id = document.get("reference_id")
        if reference_id is None:
            continue
        incoming_reference = next(
            (
                item
                for item in pending.get("references", [])
                if item.get("reference_id") == reference_id
            ),
            None,
        )
        if incoming_reference is None:
            reference_matches = _find_at_most_two(
                db["references"],
                {"reference_id": reference_id},
            )
            incoming_reference = reference_matches[0] if len(reference_matches) == 1 else None
        if incoming_reference is None or source_id not in incoming_reference.get("source_ids", []):
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "source_documents",
                    document_id,
                    "Source Document Reference is absent or does not belong to its Source",
                )
            )
    _preflight_source_document_identities(
        pending.get("source_documents", []),
        db=db,
        report=report,
    )
    _preflight_reading_state_relationships(
        pending.get("document_reading_state", []),
        source_documents=pending.get("source_documents", []),
        db=db,
        report=report,
    )
    _preflight_reading_annotation_relationships(
        raw_annotations=pending.get("document_annotations", []),
        raw_notes=pending.get("reading_notes", []),
        raw_evidence_links=pending.get("concept_evidence_links", []),
        sources=pending.get("sources", []),
        references=pending.get("references", []),
        source_documents=pending.get("source_documents", []),
        legacy_concepts=legacy_concepts,
        db=db,
        report=report,
    )
    return pending


def _reading_state_identity_query(document: dict) -> dict[str, str]:
    """Return the immutable S3 identity query for one validated state."""
    return {
        "user_scope": str(document["user_scope"]),
        "document_id": str(document["document_id"]),
    }


def _preflight_reading_state_relationships(
    raw_states: list[dict],
    *,
    source_documents: list[dict],
    db,
    report: DatabaseImportReport,
) -> None:
    """Validate S3 foreign keys and unique identities before any import write."""
    incoming_documents = {
        str(document["document_id"]): document
        for document in source_documents
        if isinstance(document.get("document_id"), str)
    }
    seen_identities: dict[tuple[str, str], str] = {}
    for raw_state in raw_states:
        payload = {key: value for key, value in raw_state.items() if key != "_id"}
        state = DocumentReadingState.model_validate(payload)
        identity = (state.user_scope, state.document_id)
        previous = seen_identities.get(identity)
        if previous is not None and previous != state.reading_state_id:
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "document_reading_state",
                    state.reading_state_id,
                    "archive contains different reading-state IDs for one user/document identity",
                )
            )
            continue
        seen_identities[identity] = state.reading_state_id

        source_document = incoming_documents.get(state.document_id)
        if source_document is None:
            document_matches = _find_at_most_two(
                db["source_documents"],
                {"document_id": state.document_id},
            )
            source_document = document_matches[0] if len(document_matches) == 1 else None
        if source_document is None:
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "document_reading_state",
                    state.reading_state_id,
                    "Reading state points to a Source Document absent from archive and destination",
                )
            )
            continue
        if source_document.get("source_id") != state.source_id:
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "document_reading_state",
                    state.reading_state_id,
                    "Reading state Source does not match its Source Document",
                )
            )
            continue
        if (
            state.reference_id is not None
            and source_document.get("reference_id") != state.reference_id
        ):
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "document_reading_state",
                    state.reading_state_id,
                    "Reading state Reference does not match its Source Document",
                )
            )
            continue

        destination_matches = _find_at_most_two(
            db["document_reading_state"],
            _reading_state_identity_query(raw_state),
        )
        if len(destination_matches) > 1 or (
            len(destination_matches) == 1
            and destination_matches[0].get("reading_state_id") != state.reading_state_id
        ):
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "document_reading_state",
                    state.reading_state_id,
                    "destination contains a different reading-state ID for the same identity",
                )
            )


def _evidence_identity_query(document: dict) -> dict[str, object]:
    """Return the exact S4 evidence identity used for conflict detection."""
    payload = {key: value for key, value in document.items() if key != "_id"}
    link = ConceptEvidenceLink.model_validate(payload)
    return {
        "concept_legacy_source": link.concept_legacy_source,
        "concept_legacy_id": link.concept_legacy_id,
        "source_id": link.source_id,
        "reference_id": link.reference_id,
        "document_id": link.document_id,
        "annotation_id": link.annotation_id,
        "note_id": link.note_id,
        "page_number": link.page_number,
        "link_type": link.link_type.value,
    }


def _preflight_reading_annotation_relationships(
    *,
    raw_annotations: list[dict],
    raw_notes: list[dict],
    raw_evidence_links: list[dict],
    sources: list[dict],
    references: list[dict],
    source_documents: list[dict],
    legacy_concepts: list[dict],
    db,
    report: DatabaseImportReport,
) -> None:
    """Validate every S4 foreign key and exact evidence identity before writes."""
    incoming_sources = {
        str(document["source_id"]): document
        for document in sources
        if isinstance(document.get("source_id"), str)
    }
    incoming_references = {
        str(document["reference_id"]): document
        for document in references
        if isinstance(document.get("reference_id"), str)
    }
    incoming_documents = {
        str(document["document_id"]): document
        for document in source_documents
        if isinstance(document.get("document_id"), str)
    }
    incoming_annotations = {
        str(document["annotation_id"]): document
        for document in raw_annotations
        if isinstance(document.get("annotation_id"), str)
    }
    incoming_notes = {
        str(document["note_id"]): document
        for document in raw_notes
        if isinstance(document.get("note_id"), str)
    }

    def resolve(
        collection_name: str,
        id_field: str,
        domain_id: str,
        incoming: dict[str, dict],
    ) -> dict | None:
        document = incoming.get(domain_id)
        if document is not None:
            return document
        matches = _find_at_most_two(db[collection_name], {id_field: domain_id})
        return matches[0] if len(matches) == 1 else None

    def add_conflict(collection: str, domain_id: str, reason: str) -> None:
        report.catalog_conflicts.append(CatalogImportConflict(collection, domain_id, reason))

    def source_exists(collection: str, domain_id: str, source_id: str) -> bool:
        if resolve("sources", "source_id", source_id, incoming_sources) is not None:
            return True
        add_conflict(collection, domain_id, "Source is absent from archive and destination")
        return False

    def reference_matches_source(
        collection: str,
        domain_id: str,
        source_id: str,
        reference_id: str | None,
    ) -> bool:
        if reference_id is None:
            return True
        reference = resolve(
            "references",
            "reference_id",
            reference_id,
            incoming_references,
        )
        if reference is not None and source_id in reference.get("source_ids", []):
            return True
        add_conflict(
            collection,
            domain_id,
            "Reference is absent or does not belong to the S4 record's Source",
        )
        return False

    for raw_annotation in raw_annotations:
        payload = {key: value for key, value in raw_annotation.items() if key != "_id"}
        annotation = DocumentAnnotation.model_validate(payload)
        source_exists(
            "document_annotations",
            annotation.annotation_id,
            annotation.source_id,
        )
        source_document = resolve(
            "source_documents",
            "document_id",
            annotation.document_id,
            incoming_documents,
        )
        if source_document is None:
            add_conflict(
                "document_annotations",
                annotation.annotation_id,
                "Annotation points to a Source Document absent from archive and destination",
            )
            continue
        if source_document.get("source_id") != annotation.source_id:
            add_conflict(
                "document_annotations",
                annotation.annotation_id,
                "Annotation Source does not match its Source Document",
            )
        if (
            annotation.reference_id is not None
            and source_document.get("reference_id") != annotation.reference_id
        ):
            add_conflict(
                "document_annotations",
                annotation.annotation_id,
                "Annotation Reference does not match its Source Document",
            )
        reference_matches_source(
            "document_annotations",
            annotation.annotation_id,
            annotation.source_id,
            annotation.reference_id,
        )

    for raw_note in raw_notes:
        payload = {key: value for key, value in raw_note.items() if key != "_id"}
        note = ReadingNote.model_validate(payload)
        source_exists("reading_notes", note.note_id, note.source_id)
        if note.document_id is not None:
            source_document = resolve(
                "source_documents",
                "document_id",
                note.document_id,
                incoming_documents,
            )
            if source_document is None:
                add_conflict(
                    "reading_notes",
                    note.note_id,
                    "Reading Note points to a Source Document absent from archive and destination",
                )
            elif source_document.get("source_id") != note.source_id:
                add_conflict(
                    "reading_notes",
                    note.note_id,
                    "Reading Note Source does not match its Source Document",
                )
        reference_matches_source(
            "reading_notes",
            note.note_id,
            note.source_id,
            note.reference_id,
        )

    incoming_concept_counts: dict[tuple[str, str], int] = {}
    for concept in legacy_concepts:
        if concept.get("id") is None or concept.get("source") is None:
            continue
        key = (str(concept["id"]), str(concept["source"]))
        incoming_concept_counts[key] = incoming_concept_counts.get(key, 0) + 1

    seen_evidence_identities: dict[tuple[tuple[str, object], ...], str] = {}
    for raw_link in raw_evidence_links:
        payload = {key: value for key, value in raw_link.items() if key != "_id"}
        link = ConceptEvidenceLink.model_validate(payload)
        source_exists("concept_evidence_links", link.evidence_link_id, link.source_id)
        reference_matches_source(
            "concept_evidence_links",
            link.evidence_link_id,
            link.source_id,
            link.reference_id,
        )

        concept_key = (link.concept_legacy_id, link.concept_legacy_source)
        incoming_count = incoming_concept_counts.get(concept_key, 0)
        destination_concepts = _find_at_most_two(
            db["concepts"],
            {"id": concept_key[0], "source": concept_key[1]},
        )
        if incoming_count > 1 or (incoming_count == 0 and len(destination_concepts) != 1):
            add_conflict(
                "concept_evidence_links",
                link.evidence_link_id,
                "Legacy Concept is absent or ambiguous in archive and destination",
            )

        target_source_id: str | None = None
        target_reference_id: str | None = None
        target_document_id: str | None = None
        if link.annotation_id is not None:
            raw_target = resolve(
                "document_annotations",
                "annotation_id",
                link.annotation_id,
                incoming_annotations,
            )
            if raw_target is None:
                add_conflict(
                    "concept_evidence_links",
                    link.evidence_link_id,
                    "Evidence points to an Annotation absent from archive and destination",
                )
            else:
                target_source_id = raw_target.get("source_id")
                target_reference_id = raw_target.get("reference_id")
                target_document_id = raw_target.get("document_id")
        elif link.note_id is not None:
            raw_target = resolve(
                "reading_notes",
                "note_id",
                link.note_id,
                incoming_notes,
            )
            if raw_target is None:
                add_conflict(
                    "concept_evidence_links",
                    link.evidence_link_id,
                    "Evidence points to a Reading Note absent from archive and destination",
                )
            else:
                target_source_id = raw_target.get("source_id")
                target_reference_id = raw_target.get("reference_id")
                target_document_id = raw_target.get("document_id")
        elif link.document_id is not None:
            raw_target = resolve(
                "source_documents",
                "document_id",
                link.document_id,
                incoming_documents,
            )
            if raw_target is None:
                add_conflict(
                    "concept_evidence_links",
                    link.evidence_link_id,
                    "Evidence points to a Source Document absent from archive and destination",
                )
            else:
                target_source_id = raw_target.get("source_id")
                target_reference_id = raw_target.get("reference_id")
                target_document_id = raw_target.get("document_id")
        if target_source_id is not None and target_source_id != link.source_id:
            add_conflict(
                "concept_evidence_links",
                link.evidence_link_id,
                "Evidence Source does not match its target",
            )
        if link.reference_id is not None and link.reference_id != target_reference_id:
            add_conflict(
                "concept_evidence_links",
                link.evidence_link_id,
                "Evidence Reference does not match its target",
            )
        if target_document_id is not None:
            target_document = resolve(
                "source_documents",
                "document_id",
                target_document_id,
                incoming_documents,
            )
            if target_document is None:
                add_conflict(
                    "concept_evidence_links",
                    link.evidence_link_id,
                    "Evidence target's Source Document is absent from archive and destination",
                )
            elif target_document.get("source_id") != link.source_id:
                add_conflict(
                    "concept_evidence_links",
                    link.evidence_link_id,
                    "Evidence target's Source Document does not belong to its Source",
                )

        identity_query = _evidence_identity_query(raw_link)
        identity = tuple(sorted(identity_query.items()))
        previous = seen_evidence_identities.get(identity)
        if previous is not None and previous != link.evidence_link_id:
            add_conflict(
                "concept_evidence_links",
                link.evidence_link_id,
                "archive contains different evidence-link IDs for one exact identity",
            )
        seen_evidence_identities[identity] = link.evidence_link_id
        destination_matches = _find_at_most_two(
            db["concept_evidence_links"],
            identity_query,
        )
        if len(destination_matches) > 1 or (
            len(destination_matches) == 1
            and destination_matches[0].get("evidence_link_id") != link.evidence_link_id
        ):
            add_conflict(
                "concept_evidence_links",
                link.evidence_link_id,
                "destination contains a different evidence-link ID for the same exact identity",
            )


def _source_document_identity(
    document: SourceDocument,
) -> tuple[tuple[str, str, str], dict[str, Any]]:
    if document.pdf is not None:
        sha256 = document.pdf.current_version.sha256
        return (
            (document.source_id, "pdf", sha256),
            {
                "source_id": document.source_id,
                "kind": "pdf",
                "pdf.versions.sha256": sha256,
            },
        )
    assert document.web is not None
    normalized_url = document.web.url_normalized
    return (
        (document.source_id, "web", normalized_url),
        {
            "source_id": document.source_id,
            "kind": "web",
            "web.url_normalized": normalized_url,
        },
    )


def _preflight_source_document_identities(
    raw_documents: list[dict],
    *,
    db,
    report: DatabaseImportReport,
) -> None:
    """Enforce the same PDF/web identities as the S2 service and indexes."""
    seen: dict[tuple[str, str, str], str] = {}
    for raw_document in raw_documents:
        payload = {key: value for key, value in raw_document.items() if key != "_id"}
        document = SourceDocument.model_validate(payload)
        identity, query = _source_document_identity(document)
        previous = seen.get(identity)
        if previous is not None and previous != document.document_id:
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "source_documents",
                    document.document_id,
                    "archive contains different document IDs for one Source Document identity",
                )
            )
            continue
        seen[identity] = document.document_id

        destination_matches = _find_at_most_two(db["source_documents"], query)
        if len(destination_matches) > 1 or (
            len(destination_matches) == 1
            and destination_matches[0].get("document_id") != document.document_id
        ):
            report.catalog_conflicts.append(
                CatalogImportConflict(
                    "source_documents",
                    document.document_id,
                    "destination contains a different document ID for the same identity",
                )
            )


def _plan_source_document_blobs(
    zf: zipfile.ZipFile,
    *,
    base_dir: str,
    portable_documents: dict[str, list[dict]],
    blob_store: SourceDocumentBlobStore,
) -> list[_SourceDocumentBlobPlan]:
    """Bind every PDF model to one exact member and preflight its destination."""
    referenced: dict[str, Any] = {}
    for raw_document in portable_documents.get("source_documents", []):
        payload = {key: value for key, value in raw_document.items() if key != "_id"}
        document = SourceDocument.model_validate(payload)
        if document.kind != DocumentKind.PDF:
            continue
        assert document.pdf is not None
        version = document.pdf.current_version
        existing = referenced.get(version.logical_path)
        if existing is not None and (
            existing.sha256 != version.sha256 or existing.size_bytes != version.size_bytes
        ):
            raise ValueError("Source Document blob path has conflicting version metadata")
        referenced.setdefault(version.logical_path, version)

    plans: list[_SourceDocumentBlobPlan] = []
    for logical_path, version in sorted(referenced.items()):
        member_name = f"{base_dir}/{logical_path}"
        try:
            data = _read_zip_member(zf, member_name)
        except ValueError as exc:
            raise ValueError("Source Document PDF blob is missing from the archive") from exc
        prepared = blob_store.prepare_pdf(data)
        if (
            prepared.logical_path != version.logical_path
            or prepared.sha256 != version.sha256
            or prepared.size_bytes != version.size_bytes
        ):
            raise ValueError("Source Document PDF blob does not match version metadata")
        try:
            existing_data = blob_store.read_version(version)
        except FileNotFoundError:
            pass
        except Exception as exc:
            raise ValueError("Canonical Source Document blob destination conflicts") from exc
        else:
            if existing_data != data:
                raise ValueError("Canonical Source Document blob destination has different bytes")
        plans.append(_SourceDocumentBlobPlan(prepared))

    physical_paths = {
        logical_path
        for member_name in zf.namelist()
        if (logical_path := _source_document_blob_logical_path(base_dir, member_name)) is not None
    }
    if physical_paths != set(referenced):
        raise ValueError("Source Document archive contains missing or unreferenced PDF blobs")
    return plans


def inspect_export_zip(zip_path: Path) -> dict:
    """Inspect a Math Knowledge Base export ZIP.

    Returns a dict with:
    - base_name
    - metadata
    - collections: {collection_name: count}
    """
    started_at = time.monotonic()
    logger.info(
        "Inspecting database import ZIP: path=%s timeout=%ss", zip_path, IMPORT_TIMEOUT_SECONDS
    )
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Uploaded file is not a valid ZIP archive")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # Detect base directory
        base_dirs = {p.split("/")[0] for p in names if "/" in p}
        if len(base_dirs) != 1:
            raise ValueError("Invalid export format: ambiguous base directory")

        base_name = base_dirs.pop()
        _collection_member_names(names, base_dir=base_name)
        _validate_zip_safety(zf, expected_base=base_name)

        metadata_path = f"{base_name}/metadata.json"
        if metadata_path not in names:
            raise ValueError("metadata.json not found in export")

        metadata = json.loads(_read_zip_member(zf, metadata_path).decode("utf-8"))
        encodings = _collection_encodings(metadata)
        collection_members = _collection_member_names(names, base_dir=base_name)
        collections = _validate_import_metadata(
            zf,
            names,
            base_dir=base_name,
            metadata=metadata,
            collection_members=collection_members,
            encodings=encodings,
        )
        for coll, name in collection_members.items():
            _raise_if_timed_out(started_at, IMPORT_TIMEOUT_SECONDS, f"inspecting {name}")
            logger.info("ZIP collection found: %s (%s documents)", coll, collections[coll])

    duration = time.monotonic() - started_at
    logger.info("ZIP inspection completed: path=%s duration=%.2fs", zip_path, duration)
    return {
        "base_name": base_name,
        "metadata": metadata,
        "collections": collections,
        "duration_seconds": round(duration, 3),
    }


def import_zip_into_database(
    zip_path: Path,
    mongo: MathMongo,
    *,
    source_document_blob_store: SourceDocumentBlobStore | None = None,
) -> DatabaseImportReport:
    """Import a validated export ZIP into an existing MongoDB database.

    Assumes:
    - zip_path has been validated with inspect_export_zip
    - mongo points to a NEW database
    """
    started_at = time.monotonic()
    db = mongo.db
    database_name = getattr(db, "name", None)
    if not isinstance(database_name, str) or not database_name:
        raise ValueError("Database import requires an explicit target name")
    folded_name = database_name.casefold()
    if folded_name in {"admin", "config", "local", "mathmongo"}:
        raise ValueError("Database import refuses protected MongoDB targets")
    initial_collections = tuple(db.list_collection_names())
    if folded_name == "mathv0" and database_name != "MathV0":
        raise ValueError("Database import can restore only the exact case-sensitive MathV0 name")
    report = DatabaseImportReport()
    logger.info(
        "Starting database import: zip=%s db=%s timeout=%ss",
        zip_path,
        database_name,
        IMPORT_TIMEOUT_SECONDS,
    )

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

            base_dirs = {p.split("/")[0] for p in names if "/" in p}
            if len(base_dirs) != 1:
                raise ValueError("Invalid export format: ambiguous base directory")
            base_dir = base_dirs.pop()
            _collection_member_names(names, base_dir=base_dir)
            _validate_zip_safety(zf, expected_base=base_dir)
            metadata_name = f"{base_dir}/metadata.json"
            if metadata_name not in names:
                raise ValueError("metadata.json not found in export")
            metadata = json.loads(_read_zip_member(zf, metadata_name).decode("utf-8"))
            encodings = _collection_encodings(metadata)
            collection_members = _collection_member_names(names, base_dir=base_dir)
            validated_counts = _validate_import_metadata(
                zf,
                names,
                base_dir=base_dir,
                metadata=metadata,
                collection_members=collection_members,
                encodings=encodings,
            )
            versioned_export = "format" in metadata or "format_version" in metadata
            if (
                database_name == "MathV0"
                and versioned_export
                and metadata.get("database_name") != "MathV0"
            ):
                raise ValueError(
                    "A versioned same-name MathV0 restore requires MathV0 archive metadata"
                )
            if database_name == "MathV0" and not versioned_export and initial_collections:
                raise ValueError(
                    "An unversioned same-name MathV0 restore requires a physically empty target"
                )

            legacy_documents = _load_legacy_documents(
                zf,
                collection_members,
                encodings=encodings,
            )
            catalog_pending = _prepare_catalog_import(
                zf,
                names,
                base_dir=base_dir,
                db=db,
                report=report,
                started_at=started_at,
                encodings=encodings,
                legacy_concepts=legacy_documents.get("concepts", []),
            )
            if report.catalog_conflicts:
                raise CatalogImportConflictError(report)

            blob_store = source_document_blob_store or SourceDocumentBlobStore(DATA_DIR)
            source_document_blob_plans = _plan_source_document_blobs(
                zf,
                base_dir=base_dir,
                portable_documents=catalog_pending,
                blob_store=blob_store,
            )

            media_plans, path_remap = _plan_media_restores(
                zf,
                names,
                base_dir=base_dir,
                db=db,
                legacy_documents=legacy_documents,
                started_at=started_at,
            )
            legacy_pending = _prepare_legacy_import(
                legacy_documents,
                path_remap=path_remap,
                db=db,
                report=report,
            )
            if report.catalog_conflicts:
                raise CatalogImportConflictError(report)
            if database_name == "MathV0" and versioned_export:
                _require_existing_documents_are_archive_subset(
                    db,
                    {**legacy_pending, **catalog_pending},
                )

            if "source_documents" in collection_members:
                # Database import bypasses SourceDocumentService. Establish its
                # unique concurrency barriers before publishing any PDF blob.
                SourceDocumentIndexManager(db).ensure()

            for blob_plan in source_document_blob_plans:
                _raise_if_timed_out(
                    started_at,
                    IMPORT_TIMEOUT_SECONDS,
                    "restoring Source Document PDF blob",
                )
                publish_result = blob_store.publish(blob_plan.prepared)
                if publish_result.created:
                    report.source_document_blobs_created += 1
                else:
                    report.source_document_blobs_identical += 1

            for media_plan in media_plans:
                _raise_if_timed_out(
                    started_at,
                    IMPORT_TIMEOUT_SECONDS,
                    f"restoring {media_plan.relative_path}",
                )
                if _write_media_file_exclusive(media_plan.destination, media_plan.data):
                    logger.info("Restored media file: %s", media_plan.destination)

            imported_collections = set()
            imported_counts = {}
            existing_collections = set(db.list_collection_names())
            ordered_collections = [
                collection_name
                for collection_name in collection_members
                if collection_name not in PORTABLE_EXTENDED_JSON_COLLECTIONS
            ]
            ordered_collections.extend(
                collection_name
                for collection_name in _PORTABLE_IMPORT_ORDER
                if collection_name in collection_members
            )
            for coll in ordered_collections:
                name = collection_members[coll]
                _raise_if_timed_out(started_at, IMPORT_TIMEOUT_SECONDS, f"reading {name}")

                collection_started_at = time.monotonic()
                imported_collections.add(coll)
                if coll not in existing_collections:
                    db.create_collection(coll)
                    existing_collections.add(coll)

                if coll in PORTABLE_EXTENDED_JSON_COLLECTIONS:
                    docs = catalog_pending.get(coll, [])
                    id_field = _PORTABLE_ID_FIELDS[coll]
                    for document in docs:
                        domain_id = document[id_field]
                        if coll == "document_reading_state":
                            identity_matches = _find_at_most_two(
                                db[coll],
                                _reading_state_identity_query(document),
                            )
                            if len(identity_matches) > 1 or (
                                len(identity_matches) == 1
                                and identity_matches[0].get(id_field) != domain_id
                            ):
                                report.catalog_conflicts.append(
                                    CatalogImportConflict(
                                        coll,
                                        domain_id,
                                        "destination reading-state identity changed after preflight",
                                    )
                                )
                                raise CatalogImportConflictError(report)
                        elif coll == "concept_evidence_links":
                            identity_matches = _find_at_most_two(
                                db[coll],
                                _evidence_identity_query(document),
                            )
                            if len(identity_matches) > 1 or (
                                len(identity_matches) == 1
                                and identity_matches[0].get(id_field) != domain_id
                            ):
                                report.catalog_conflicts.append(
                                    CatalogImportConflict(
                                        coll,
                                        domain_id,
                                        "destination evidence identity changed after preflight",
                                    )
                                )
                                raise CatalogImportConflictError(report)
                        domain_matches = _find_at_most_two(
                            db[coll],
                            {id_field: domain_id},
                        )
                        if len(domain_matches) > 1:
                            report.catalog_conflicts.append(
                                CatalogImportConflict(
                                    coll,
                                    domain_id,
                                    "destination gained duplicate domain IDs after preflight",
                                )
                            )
                            raise CatalogImportConflictError(report)
                        existing = domain_matches[0] if domain_matches else None
                        if existing is not None:
                            if _catalog_documents_identical(existing, document):
                                report.catalog_identical[coll] = (
                                    report.catalog_identical.get(coll, 0) + 1
                                )
                                continue
                            report.catalog_conflicts.append(
                                CatalogImportConflict(
                                    coll,
                                    domain_id,
                                    "destination changed after catalog preflight",
                                )
                            )
                            raise CatalogImportConflictError(report)
                        storage_id = document.get("_id")
                        if storage_id is not None:
                            storage_matches = _find_at_most_two(
                                db[coll],
                                {"_id": storage_id},
                            )
                            if storage_matches:
                                report.catalog_conflicts.append(
                                    CatalogImportConflict(
                                        coll,
                                        domain_id,
                                        "destination MongoDB _id changed after catalog preflight",
                                    )
                                )
                                raise CatalogImportConflictError(report)
                        try:
                            db[coll].insert_one(document)
                        except DuplicateKeyError as exc:
                            domain_matches = _find_at_most_two(
                                db[coll],
                                {id_field: domain_id},
                            )
                            if len(domain_matches) == 1 and _catalog_documents_identical(
                                domain_matches[0], document
                            ):
                                report.catalog_identical[coll] = (
                                    report.catalog_identical.get(coll, 0) + 1
                                )
                                continue
                            report.catalog_conflicts.append(
                                CatalogImportConflict(
                                    coll,
                                    domain_id,
                                    "concurrent insert produced different data",
                                )
                            )
                            raise CatalogImportConflictError(report) from exc
                        inserted_matches = _find_at_most_two(
                            db[coll],
                            {id_field: domain_id},
                        )
                        if len(inserted_matches) != 1 or not _catalog_documents_identical(
                            inserted_matches[0],
                            document,
                        ):
                            report.catalog_conflicts.append(
                                CatalogImportConflict(
                                    coll,
                                    domain_id,
                                    "concurrent insert produced duplicate domain IDs",
                                )
                            )
                            raise CatalogImportConflictError(report)
                        if coll == "document_reading_state":
                            identity_matches = _find_at_most_two(
                                db[coll],
                                _reading_state_identity_query(document),
                            )
                            if (
                                len(identity_matches) != 1
                                or identity_matches[0].get(id_field) != domain_id
                            ):
                                report.catalog_conflicts.append(
                                    CatalogImportConflict(
                                        coll,
                                        domain_id,
                                        "concurrent insert produced duplicate reading-state identities",
                                    )
                                )
                                raise CatalogImportConflictError(report)
                        elif coll == "concept_evidence_links":
                            identity_matches = _find_at_most_two(
                                db[coll],
                                _evidence_identity_query(document),
                            )
                            if (
                                len(identity_matches) != 1
                                or identity_matches[0].get(id_field) != domain_id
                            ):
                                report.catalog_conflicts.append(
                                    CatalogImportConflict(
                                        coll,
                                        domain_id,
                                        "concurrent insert produced duplicate evidence identities",
                                    )
                                )
                                raise CatalogImportConflictError(report)
                        report.catalog_inserted[coll] = report.catalog_inserted.get(coll, 0) + 1
                    imported_counts[coll] = validated_counts[coll]
                    report.imported_counts[coll] = validated_counts[coll]
                    logger.info(
                        "Imported catalog collection %s: inserted=%s identical=%s",
                        coll,
                        report.catalog_inserted.get(coll, 0),
                        report.catalog_identical.get(coll, 0),
                    )
                    continue

                docs = legacy_pending.get(coll, [])
                for idx, doc in enumerate(docs, start=1):
                    if idx == 1 or idx % 100 == 0:
                        _raise_if_timed_out(
                            started_at,
                            IMPORT_TIMEOUT_SECONDS,
                            f"importing {coll}",
                        )
                    if "_id" in doc:
                        existing = db[coll].find_one({"_id": doc["_id"]})
                        if existing is not None:
                            if _catalog_documents_identical(existing, doc):
                                report.legacy_identical[coll] = (
                                    report.legacy_identical.get(coll, 0) + 1
                                )
                                continue
                            report.catalog_conflicts.append(
                                CatalogImportConflict(
                                    coll,
                                    str(doc["_id"]),
                                    "destination contains different legacy data for the same _id",
                                )
                            )
                            raise CatalogImportConflictError(report)
                        db[coll].insert_one(doc)
                        report.legacy_inserted[coll] = report.legacy_inserted.get(coll, 0) + 1
                    else:
                        db[coll].insert_one(doc)
                        report.legacy_inserted[coll] = report.legacy_inserted.get(coll, 0) + 1
                imported_counts[coll] = len(legacy_documents.get(coll, []))
                report.imported_counts[coll] = len(legacy_documents.get(coll, []))
                logger.info(
                    "Imported collection %s: %s documents in %.2fs",
                    coll,
                    len(docs),
                    time.monotonic() - collection_started_at,
                )

            required_empty_collections = (
                set(IMPORT_COLLECTIONS)
                - imported_collections
                - set(PORTABLE_EXTENDED_JSON_COLLECTIONS)
            )
            for coll in required_empty_collections:
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
        return report
    except Exception:
        logger.exception(
            "Database import failed after %.2fs",
            time.monotonic() - started_at,
        )
        raise

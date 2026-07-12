"""Portable, bounded MongoDB export helpers for MathMongo backups."""

import hashlib
import json
import logging
import os
import stat
import time
import zipfile
from datetime import datetime
from datetime import timezone
from pathlib import Path

from bson import ObjectId
from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps

from mathkb_config import EXPORT_COLLECTIONS
from mathkb_config import EXPORT_TIMEOUT_SECONDS
from mathkb_config import LEGACY_PROJECT_ROOT
from mathkb_config import LOCAL_MEDIA_ROOT
from mathkb_config import MEDIA_ROOT
from mathkb_config import SOURCE_CATALOG_COLLECTIONS
from mathmongo.paths import find_symlink_component
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_COLLECTIONS = list(EXPORT_COLLECTIONS)
CATALOG_EXTENDED_JSON_ENCODING = "mongodb_extended_json_v2_canonical"


def _raise_if_timed_out(started_at: float, timeout_seconds: int, operation: str) -> None:
    elapsed = time.monotonic() - started_at
    if elapsed > timeout_seconds:
        raise TimeoutError(
            f"Database export timed out after {timeout_seconds} seconds while {operation}. "
            "You can increase EXPORT_TIMEOUT_SECONDS."
        )


def mongo_to_json_safe(obj):
    """Recursively convert MongoDB-specific types into JSON-serializable forms.

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


def _open_private_output_directory(directory: Path, *, create: bool = True) -> int:
    """Open an output directory through anchored no-follow dirfds."""
    directory = validate_mutable_path(directory)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    current_descriptor = os.open(directory.anchor, flags)
    current_path = Path(directory.anchor)
    try:
        for part in directory.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(part, flags, dir_fd=current_descriptor)
            os.close(current_descriptor)
            current_descriptor = next_descriptor
            current_path /= part
        if create:
            current_mode = stat.S_IMODE(os.fstat(current_descriptor).st_mode)
            if current_mode != 0o700:
                os.fchmod(current_descriptor, 0o700)
        return current_descriptor
    except Exception:
        os.close(current_descriptor)
        raise


def _read_stable_media_file(path: Path) -> bytes:
    """Read one regular media file without following its leaf symlink."""
    if find_symlink_component(path) is not None:
        raise ValueError(f"Refusing symlinked media during export: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Refusing non-regular media during export: {path}")
        data = bytearray()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or len(data) != before.st_size:
            raise ValueError(f"Media changed during export: {path}")
        return bytes(data)
    finally:
        os.close(descriptor)


def _media_payloads() -> dict[str, bytes]:
    """Merge legacy then XDG media into an in-memory portable inventory."""
    payloads: dict[str, bytes] = {}
    for source_root in (LEGACY_PROJECT_ROOT / MEDIA_ROOT, LOCAL_MEDIA_ROOT):
        if find_symlink_component(source_root) is not None or not source_root.is_dir():
            continue
        for source in sorted(source_root.rglob("*")):
            if source.is_symlink() or not source.is_file():
                continue
            relative_name = (MEDIA_ROOT / source.relative_to(source_root)).as_posix()
            payloads[relative_name] = _read_stable_media_file(source)
    return payloads


def _publish_anonymous_zip(
    descriptor: int,
    output_directory_descriptor: int,
    file_name: str,
) -> None:
    """Materialize a complete anonymous ZIP without replacing any pathname."""
    os.fchmod(descriptor, 0o600)
    os.fsync(descriptor)
    try:
        os.link(
            f"/proc/self/fd/{descriptor}",
            file_name,
            dst_dir_fd=output_directory_descriptor,
            follow_symlinks=True,
        )
    except FileExistsError as exc:
        raise FileExistsError(
            f"Refusing to replace an existing database export: {file_name}"
        ) from exc


def _stable_descriptor_identity(descriptor: int) -> tuple[tuple[int, ...], str]:
    """Hash a regular descriptor while proving its bytes and metadata stayed stable."""
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise OSError("Database export staging descriptor is not a regular file")
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_uid,
        before.st_gid,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        stat.S_IMODE(before.st_mode),
    )
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        chunk = os.pread(descriptor, min(1024 * 1024, before.st_size - offset), offset)
        if not chunk:
            raise OSError("Database export staging file changed during verification")
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_uid,
        after.st_gid,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        stat.S_IMODE(after.st_mode),
    )
    if identity_after != identity_before:
        raise OSError("Database export staging file changed during verification")
    return identity_before, digest.hexdigest()


def _identity_unchanged_across_publication(
    before_link: tuple[int, ...],
    after_link: tuple[int, ...],
) -> bool:
    """Ignore only ctime, which legitimately changes when O_TMPFILE gains a hardlink."""
    stable_fields = (0, 1, 2, 3, 4, 5, 7)
    return all(before_link[index] == after_link[index] for index in stable_fields)


def export_database_to_zip(mongo, out_dir: Path) -> Path:
    """Export the entire MongoDB database to a ZIP archive of JSON files.

    - Read-only
    - No schema assumptions
    - JSON-safe normalization (ObjectId, datetime, nested structures)

    Returns the path to the generated ZIP file.
    """
    out_dir = validate_mutable_path(resolve_home_path(out_dir))
    output_directory_descriptor = _open_private_output_directory(out_dir)
    started_at = time.monotonic()
    db = mongo.db
    exported_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = f"mathkb_export_{timestamp}"
    zip_name = f"{base_name}.zip"
    zip_path = validate_mutable_path(out_dir / zip_name, allowed_root=out_dir)
    logger.info(
        "Starting database export: db=%s out_dir=%s timeout=%ss",
        getattr(db, "name", "<unknown>"),
        out_dir,
        EXPORT_TIMEOUT_SECONDS,
    )

    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": getattr(db, "name", None),
        "exported_at": exported_at.isoformat().replace("+00:00", "Z"),
        "timeout_seconds": EXPORT_TIMEOUT_SECONDS,
        "collections": {},
        "collection_encodings": {},
        "media_files": {},
    }

    anonymous_descriptor: int | None = None
    try:
        # Historical collections keep their existing backup behavior. Source
        # Catalog collections are optional and are exported only after they
        # have actually been created in the selected database.
        existing_collection_names = set(db.list_collection_names())
        always_exported = set(EXPORT_COLLECTIONS)
        optional_catalog = existing_collection_names & set(SOURCE_CATALOG_COLLECTIONS)
        collection_names = sorted(always_exported | optional_catalog)
        logger.info("Collections scheduled for export: %s", ", ".join(collection_names))
        collection_payloads: dict[str, str] = {}
        for collection_name in collection_names:
            _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, f"reading {collection_name}")
            collection_started_at = time.monotonic()
            cursor = db[collection_name].find({}).max_time_ms(EXPORT_TIMEOUT_SECONDS * 1000)
            raw_docs = list(cursor)
            metadata["collections"][collection_name] = len(raw_docs)

            if collection_name in SOURCE_CATALOG_COLLECTIONS:
                collection_payloads[collection_name] = bson_json_dumps(
                    raw_docs,
                    json_options=CANONICAL_JSON_OPTIONS,
                    ensure_ascii=False,
                    indent=2,
                )
                metadata["collection_encodings"][collection_name] = CATALOG_EXTENDED_JSON_ENCODING
            else:
                docs = [mongo_to_json_safe(doc) for doc in raw_docs]
                collection_payloads[collection_name] = json.dumps(
                    docs,
                    ensure_ascii=False,
                    indent=2,
                )
            logger.info(
                "Exported collection %s: %s documents in %.2fs",
                collection_name,
                len(raw_docs),
                time.monotonic() - collection_started_at,
            )

        _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, "copying media files")
        media_payloads = _media_payloads()
        metadata["media_files"] = {name: len(data) for name, data in sorted(media_payloads.items())}
        if media_payloads:
            logger.info(
                "Prepared portable media inventory with %s files",
                len(media_payloads),
            )

        _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, "writing metadata")
        metadata["snapshot_completed_at"] = (
            datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        )
        metadata["duration_seconds"] = round(time.monotonic() - started_at, 3)
        _raise_if_timed_out(started_at, EXPORT_TIMEOUT_SECONDS, "creating ZIP archive")
        temporary_flag = getattr(os, "O_TMPFILE", 0)
        if not temporary_flag:
            raise OSError("This platform cannot stage backups through anonymous files")
        anonymous_descriptor = os.open(
            ".",
            os.O_RDWR | temporary_flag | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=output_directory_descriptor,
        )
        with os.fdopen(os.dup(anonymous_descriptor), "w+b") as handle:
            with zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as archive:
                for collection_name, payload in sorted(collection_payloads.items()):
                    _raise_if_timed_out(
                        started_at,
                        EXPORT_TIMEOUT_SECONDS,
                        f"zipping {collection_name}",
                    )
                    archive.writestr(
                        f"{base_name}/collections/{collection_name}.json",
                        payload,
                    )
                for relative_name, payload in sorted(media_payloads.items()):
                    _raise_if_timed_out(
                        started_at,
                        EXPORT_TIMEOUT_SECONDS,
                        f"zipping {Path(relative_name).name}",
                    )
                    archive.writestr(f"{base_name}/{relative_name}", payload)
                archive.writestr(
                    f"{base_name}/metadata.json",
                    json.dumps(metadata, ensure_ascii=False, indent=2),
                )
            handle.flush()
            os.fsync(handle.fileno())

        expected_zip_identity, expected_zip_sha256 = _stable_descriptor_identity(
            anonymous_descriptor
        )

        current_output_descriptor = _open_private_output_directory(out_dir, create=False)
        try:
            pinned_output = os.fstat(output_directory_descriptor)
            current_output = os.fstat(current_output_descriptor)
            if (pinned_output.st_dev, pinned_output.st_ino) != (
                current_output.st_dev,
                current_output.st_ino,
            ):
                raise FileExistsError("Backup output directory changed before publication")
            _publish_anonymous_zip(
                anonymous_descriptor,
                current_output_descriptor,
                zip_name,
            )
        finally:
            os.close(current_output_descriptor)

        final_output_descriptor = _open_private_output_directory(out_dir, create=False)
        try:
            final_output = os.fstat(final_output_descriptor)
            if (pinned_output.st_dev, pinned_output.st_ino) != (
                final_output.st_dev,
                final_output.st_ino,
            ):
                raise FileExistsError("Backup output directory changed after publication")
            final_stat = os.stat(
                zip_name,
                dir_fd=final_output_descriptor,
                follow_symlinks=False,
            )
            final_identity = (
                final_stat.st_dev,
                final_stat.st_ino,
                final_stat.st_uid,
                final_stat.st_gid,
                final_stat.st_size,
                final_stat.st_mtime_ns,
                final_stat.st_ctime_ns,
                stat.S_IMODE(final_stat.st_mode),
            )
            observed_zip_identity, observed_zip_sha256 = _stable_descriptor_identity(
                anonymous_descriptor
            )
            if (
                final_identity != observed_zip_identity
                or not _identity_unchanged_across_publication(
                    expected_zip_identity,
                    observed_zip_identity,
                )
                or observed_zip_sha256 != expected_zip_sha256
            ):
                raise FileExistsError("Published backup identity changed")
        finally:
            os.close(final_output_descriptor)

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
    finally:
        if anonymous_descriptor is not None:
            os.close(anonymous_descriptor)
        os.close(output_directory_descriptor)

"""Fresh private backup validation for the explicit MathV0 production gate."""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from mathmongo.paths import validate_mutable_path
from mathmongo.source_catalog_migration.apply_safety import PRODUCTION_TARGET_DATABASE
from mathmongo.source_catalog_migration.apply_safety import ApplyAuthorization
from mathmongo.source_catalog_migration.apply_safety import ApplySafetyError
from mathmongo.source_catalog_migration.apply_safety import ProductionBackupEvidence
from mathmongo.source_catalog_migration.apply_safety import legacy_snapshot_from_documents
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_SNAPSHOT_COUNTS
from mathmongo.source_catalog_migration.zip_reader import ZipSafetyLimits
from mathmongo.source_catalog_migration.zip_reader import ZipValidationError
from mathmongo.source_catalog_migration.zip_reader import _json_payload
from mathmongo.source_catalog_migration.zip_reader import _layout_kind
from mathmongo.source_catalog_migration.zip_reader import _read_member
from mathmongo.source_catalog_migration.zip_reader import _validate_members
from mathmongo.source_catalog_migration.zip_reader import _validate_metadata

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_FILE_MODE = 0o600
_EXPECTED_DIRECTORY_MODE = 0o700
MAX_PRODUCTION_BACKUP_AGE = timedelta(hours=24)
MAX_PRODUCTION_BACKUP_BYTES = 512 * 1024 * 1024
AUTHORITATIVE_LEGACY_BACKUP_AGGREGATE_SHA256 = (
    "fcc4d833f6e35146d7a673cfc352f157f026e43373b0a46b1fe21fa9c6f34636"
)
AUTHORITATIVE_BACKUP_MEDIA_AGGREGATE_SHA256 = (
    "dd4c7eda2d9b269aa84a77b29dfc0fe6cd51cc5751b9d781c49250d1123851b9"
)
AUTHORITATIVE_BACKUP_MEDIA_FILE_COUNT = 15


class ProductionBackupRevalidationError(ApplySafetyError):
    """A mandatory engine-side backup reread failed before MongoDB writes."""


class ProductionBackupValidationError(ApplySafetyError):
    """A backup archive failed its single-descriptor structural validation."""


def _read_one_stable_file(
    descriptor: int,
    before: os.stat_result,
) -> tuple[bytes, str]:
    """Hash and capture exactly the bytes later parsed from one anchored FD."""
    fd_before = os.fstat(descriptor)
    if fd_before.st_size <= 0 or fd_before.st_size > MAX_PRODUCTION_BACKUP_BYTES:
        raise ProductionBackupValidationError(
            "backup_size_invalid",
            "The backup size is outside the production validation limit.",
        )
    digest = hashlib.sha256()
    content = bytearray()
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, fd_before.st_size + 1))
        if not chunk:
            break
        content.extend(chunk)
        digest.update(chunk)
        if len(content) > fd_before.st_size:
            raise ProductionBackupValidationError(
                "backup_changed",
                "The backup grew while it was being read.",
            )
    fd_after = os.fstat(descriptor)
    identity_fd = (
        fd_before.st_dev,
        fd_before.st_ino,
        fd_before.st_uid,
        fd_before.st_gid,
        fd_before.st_size,
        fd_before.st_mtime_ns,
        fd_before.st_ctime_ns,
        stat.S_IMODE(fd_before.st_mode),
    )
    identity_after = (
        fd_after.st_dev,
        fd_after.st_ino,
        fd_after.st_uid,
        fd_after.st_gid,
        fd_after.st_size,
        fd_after.st_mtime_ns,
        fd_after.st_ctime_ns,
        stat.S_IMODE(fd_after.st_mode),
    )
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
    if identity_fd != identity_before:
        raise ProductionBackupValidationError(
            "backup_changed",
            "The backup identity changed before its stable read began.",
        )
    if len(content) != fd_before.st_size or identity_after != identity_fd:
        raise ProductionBackupValidationError(
            "backup_changed",
            "The backup changed during its single-descriptor read.",
        )
    return bytes(content), digest.hexdigest()


def _open_directory_chain(directory: Path) -> tuple[list[int], tuple[str, ...]]:
    """Anchor every absolute directory component with O_NOFOLLOW."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptors = [os.open(directory.anchor, flags)]
    parts = directory.parts[1:]
    try:
        for part in parts:
            descriptors.append(os.open(part, flags, dir_fd=descriptors[-1]))
    except Exception:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise
    return descriptors, parts


def _verify_directory_chain(descriptors: list[int], parts: tuple[str, ...]) -> None:
    """Require every lexical component to retain the anchored directory inode."""
    for index, part in enumerate(parts):
        named = os.stat(part, dir_fd=descriptors[index], follow_symlinks=False)
        anchored = os.fstat(descriptors[index + 1])
        if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != (
            anchored.st_dev,
            anchored.st_ino,
        ):
            raise ProductionBackupValidationError(
                "backup_changed",
                "The backup directory chain changed or acquired a symlink.",
            )


@contextmanager
def _stable_backup_capture(
    path: Path,
    before: os.stat_result,
    parent_before: os.stat_result,
) -> Iterator[tuple[bytes, str]]:
    """Keep the no-follow directory/file chain anchored through ZIP parsing."""
    descriptors: list[int] = []
    file_descriptor: int | None = None
    try:
        descriptors, parts = _open_directory_chain(path.parent)
        parent_fd_stat = os.fstat(descriptors[-1])
        if (
            parent_fd_stat.st_dev,
            parent_fd_stat.st_ino,
            parent_fd_stat.st_uid,
            parent_fd_stat.st_gid,
            parent_fd_stat.st_mtime_ns,
            parent_fd_stat.st_ctime_ns,
            stat.S_IMODE(parent_fd_stat.st_mode),
        ) != (
            parent_before.st_dev,
            parent_before.st_ino,
            parent_before.st_uid,
            parent_before.st_gid,
            parent_before.st_mtime_ns,
            parent_before.st_ctime_ns,
            stat.S_IMODE(parent_before.st_mode),
        ):
            raise ProductionBackupValidationError(
                "backup_changed",
                "The backup directory changed before its anchored read.",
            )
        file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        file_descriptor = os.open(path.name, file_flags, dir_fd=descriptors[-1])
        data, digest = _read_one_stable_file(file_descriptor, before)
        yield data, digest
        named_file = os.stat(
            path.name,
            dir_fd=descriptors[-1],
            follow_symlinks=False,
        )
        anchored_file = os.fstat(file_descriptor)
        final_file_identity = (
            named_file.st_dev,
            named_file.st_ino,
            named_file.st_uid,
            named_file.st_gid,
            named_file.st_size,
            named_file.st_mtime_ns,
            named_file.st_ctime_ns,
            stat.S_IMODE(named_file.st_mode),
        )
        anchored_file_identity = (
            anchored_file.st_dev,
            anchored_file.st_ino,
            anchored_file.st_uid,
            anchored_file.st_gid,
            anchored_file.st_size,
            anchored_file.st_mtime_ns,
            anchored_file.st_ctime_ns,
            stat.S_IMODE(anchored_file.st_mode),
        )
        original_file_identity = (
            before.st_dev,
            before.st_ino,
            before.st_uid,
            before.st_gid,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            stat.S_IMODE(before.st_mode),
        )
        if (
            not stat.S_ISREG(named_file.st_mode)
            or final_file_identity != anchored_file_identity
            or anchored_file_identity != original_file_identity
        ):
            raise ProductionBackupValidationError(
                "backup_changed",
                "The backup filename changed during ZIP parsing.",
            )
        _verify_directory_chain(descriptors, parts)
        final_parent = os.fstat(descriptors[-1])
        if (
            final_parent.st_dev,
            final_parent.st_ino,
            final_parent.st_uid,
            final_parent.st_gid,
            final_parent.st_mtime_ns,
            final_parent.st_ctime_ns,
            stat.S_IMODE(final_parent.st_mode),
        ) != (
            parent_before.st_dev,
            parent_before.st_ino,
            parent_before.st_uid,
            parent_before.st_gid,
            parent_before.st_mtime_ns,
            parent_before.st_ctime_ns,
            stat.S_IMODE(parent_before.st_mode),
        ):
            raise ProductionBackupValidationError(
                "backup_changed",
                "The private backup directory changed during ZIP parsing.",
            )
    except ProductionBackupValidationError:
        raise
    except OSError as exc:
        raise ProductionBackupValidationError(
            "backup_open_failed",
            "The backup could not be anchored through its no-follow path boundary.",
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _parse_backup_bytes(
    data: bytes,
) -> tuple[dict[str, Any], dict[str, tuple[dict, ...]], str, int]:
    """Apply the S1C1 ZIP/member/metadata checks to the exact captured bytes."""
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            base, _members, _safety = _validate_members(infos, ZipSafetyLimits())
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise ZipValidationError(
                    "crc_mismatch",
                    "Backup member failed its CRC check",
                    member=corrupt_member,
                )
            info_by_name = {info.filename: info for info in infos}
            metadata_name = f"{base}/metadata.json"
            metadata_info = info_by_name.get(metadata_name)
            if metadata_info is None:
                raise ZipValidationError("missing_metadata", "metadata.json is missing")
            metadata_data, _metadata_sha = _read_member(archive, metadata_info)
            metadata_raw = _json_payload(metadata_data, member=metadata_name)
            collections: dict[str, tuple[dict, ...]] = {}
            media_sizes: dict[str, int] = {}
            media_rows: list[dict[str, Any]] = []
            for info in infos:
                relative = PurePosixPath(info.filename).parts[1:]
                kind = _layout_kind(relative)
                if kind == "collection" and not info.is_dir():
                    payload_data, _payload_sha = _read_member(archive, info)
                    payload = _json_payload(payload_data, member=info.filename)
                    if not isinstance(payload, list) or not all(
                        isinstance(document, dict) for document in payload
                    ):
                        raise ZipValidationError(
                            "invalid_collection",
                            "Backup collection JSON must contain an array of objects",
                            member=info.filename,
                        )
                    collections[PurePosixPath(info.filename).stem] = tuple(payload)
                elif kind == "media" and not info.is_dir():
                    relative_name = PurePosixPath(*relative).as_posix()
                    _media_data, media_sha256 = _read_member(archive, info)
                    media_sizes[relative_name] = info.file_size
                    media_rows.append(
                        {
                            "name": relative_name,
                            "size_bytes": info.file_size,
                            "sha256": media_sha256,
                        }
                    )
            metadata = _validate_metadata(metadata_raw, collections, media_sizes)
            ordered_media = sorted(media_rows, key=lambda row: row["name"])
            return metadata, collections, sha256_digest(ordered_media), len(ordered_media)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise ProductionBackupValidationError(
            "backup_archive_invalid",
            "The backup ZIP failed closed structural validation.",
        ) from exc


def _aware_utc(value: Any, *, field_name: str) -> datetime:
    """Parse a required ISO timestamp and reject ambiguous local wall time."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ApplySafetyError(
                "invalid_backup_metadata",
                f"Backup metadata field {field_name} is not a valid timestamp.",
            ) from exc
    else:
        raise ApplySafetyError(
            "invalid_backup_metadata",
            f"Backup metadata field {field_name} is required.",
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ApplySafetyError(
            "invalid_backup_metadata",
            f"Backup metadata field {field_name} must include a timezone.",
        )
    return parsed.astimezone(timezone.utc)


def parse_write_freeze_at(value: str | datetime) -> datetime:
    """Parse the operator's explicit write-freeze timestamp."""
    return _aware_utc(value, field_name="write_freeze_at")


def validate_production_backup(
    backup_path: str | Path,
    *,
    backup_sha: str,
    confirm_backup_sha: str,
    write_freeze_at: datetime,
    clock: Any | None = None,
    require_fresh: bool = True,
    _expected_legacy_aggregate_sha256: str = AUTHORITATIVE_LEGACY_BACKUP_AGGREGATE_SHA256,
    _expected_media_aggregate_sha256: str = AUTHORITATIVE_BACKUP_MEDIA_AGGREGATE_SHA256,
    _expected_media_file_count: int = AUTHORITATIVE_BACKUP_MEDIA_FILE_COUNT,
) -> ProductionBackupEvidence:
    """Read and authenticate a stable post-freeze, pre-apply MathV0 export."""
    if not _SHA256_RE.fullmatch(str(backup_sha or "")) or not _SHA256_RE.fullmatch(
        str(confirm_backup_sha or "")
    ):
        raise ApplySafetyError(
            "invalid_backup_hash",
            "Both backup hash assertions must be complete lowercase SHA-256 digests.",
        )
    if backup_sha != confirm_backup_sha:
        raise ApplySafetyError(
            "backup_confirmation_mismatch",
            "The backup SHA-256 confirmation does not match.",
        )
    if write_freeze_at.tzinfo is None or write_freeze_at.utcoffset() is None:
        raise ApplySafetyError(
            "invalid_write_freeze",
            "The write-freeze timestamp must include a timezone.",
        )
    freeze = write_freeze_at.astimezone(timezone.utc)
    validated_at = (clock or (lambda: datetime.now(timezone.utc)))()
    if validated_at.tzinfo is None or validated_at.utcoffset() is None:
        raise ValueError("backup validation clock must return timezone-aware time")
    validated_at = validated_at.astimezone(timezone.utc)
    if freeze > validated_at:
        raise ApplySafetyError(
            "future_write_freeze",
            "The write-freeze timestamp cannot be in the future.",
        )

    try:
        path = validate_mutable_path(backup_path)
        before = path.lstat()
        parent_before = path.parent.stat()
    except (OSError, ValueError) as exc:
        raise ApplySafetyError(
            "invalid_backup_path",
            "The backup path is unavailable or inside a forbidden mutable tree.",
        ) from exc
    if not stat.S_ISREG(before.st_mode):
        raise ApplySafetyError("backup_not_regular", "The backup must be a regular file.")
    if any(part in {"site-packages", "dist-packages"} for part in path.parts):
        raise ApplySafetyError(
            "backup_inside_site_packages",
            "The backup must remain outside installed Python package trees.",
        )
    if before.st_uid != os.geteuid() or parent_before.st_uid != os.geteuid():
        raise ApplySafetyError(
            "backup_owner_mismatch",
            "The backup file and directory must be owned by the current operator.",
        )
    file_mode = stat.S_IMODE(before.st_mode)
    parent_mode = stat.S_IMODE(parent_before.st_mode)
    if file_mode != _EXPECTED_FILE_MODE or parent_mode != _EXPECTED_DIRECTORY_MODE:
        raise ApplySafetyError(
            "backup_permissions_not_private",
            "The backup requires a 0600 file inside a 0700 directory.",
        )

    with _stable_backup_capture(path, before, parent_before) as (data, observed_sha):
        if observed_sha != backup_sha:
            raise ApplySafetyError(
                "backup_hash_mismatch",
                "The backup bytes do not match the confirmed SHA-256 digest.",
            )
        metadata, collections, media_aggregate_sha256, media_file_count = _parse_backup_bytes(data)
    if metadata.get("database_name") != PRODUCTION_TARGET_DATABASE:
        raise ApplySafetyError(
            "backup_database_mismatch",
            "The backup metadata does not identify MathV0.",
        )
    if (
        metadata.get("format") != "mathkb_legacy_export"
        or str(metadata.get("format_version")) != "1"
    ):
        raise ApplySafetyError(
            "backup_format_mismatch",
            "The backup does not use the approved MathMongo export format.",
        )

    counts = dict(metadata["collections"])
    expected_counts = dict(AUTHORITATIVE_SNAPSHOT_COUNTS)
    if counts != expected_counts:
        raise ApplySafetyError(
            "backup_counts_mismatch",
            "The backup legacy collection counts are not authoritative.",
        )
    forbidden = {"sources", "references", MANIFEST_COLLECTION}
    if forbidden & set(collections):
        raise ApplySafetyError(
            "backup_catalog_present",
            "The pre-apply backup must not contain Source Catalog collections.",
        )
    legacy_snapshot = legacy_snapshot_from_documents(
        collections,
        database_name=PRODUCTION_TARGET_DATABASE,
    )
    if legacy_snapshot.aggregate_sha256 != _expected_legacy_aggregate_sha256:
        raise ApplySafetyError(
            "backup_fingerprint_mismatch",
            "The backup legacy fingerprints do not match the authoritative snapshot.",
        )
    if (
        media_aggregate_sha256 != _expected_media_aggregate_sha256
        or media_file_count != _expected_media_file_count
    ):
        raise ApplySafetyError(
            "backup_media_mismatch",
            "The backup physical-media inventory does not match the authoritative export.",
        )

    exported_at = _aware_utc(metadata.get("exported_at"), field_name="exported_at")
    completed_at = _aware_utc(
        metadata.get("snapshot_completed_at"),
        field_name="snapshot_completed_at",
    )
    modified_at = datetime.fromtimestamp(before.st_mtime_ns / 1_000_000_000, timezone.utc)
    if exported_at < freeze or completed_at < exported_at:
        raise ApplySafetyError(
            "backup_precedes_write_freeze",
            "The backup was not created entirely after the confirmed write freeze.",
        )
    if completed_at > validated_at or modified_at < completed_at or modified_at > validated_at:
        raise ApplySafetyError(
            "backup_time_order_invalid",
            "The backup timestamps do not precede the production apply validation.",
        )
    fresh = validated_at - completed_at <= MAX_PRODUCTION_BACKUP_AGE
    if require_fresh and not fresh:
        raise ApplySafetyError(
            "backup_not_fresh",
            "The pre-apply backup is older than the guarded production window.",
        )

    with _stable_backup_capture(path, before, parent_before) as (
        _final_data,
        final_sha,
    ):
        if final_sha != backup_sha:
            raise ApplySafetyError(
                "backup_changed",
                "The backup bytes changed before validation completed.",
            )
    after = before

    return ProductionBackupEvidence(
        database_name=PRODUCTION_TARGET_DATABASE,
        file_name=path.name,
        sha256=backup_sha,
        size_bytes=after.st_size,
        exported_at=exported_at,
        completed_at=completed_at,
        write_freeze_at=freeze,
        validated_at=validated_at,
        format_name="mathkb_legacy_export",
        format_version="1",
        collection_counts=counts,
        legacy_aggregate_sha256=legacy_snapshot.aggregate_sha256,
        media_aggregate_sha256=media_aggregate_sha256,
        media_file_count=media_file_count,
        file_mode=f"{file_mode:04o}",
        parent_mode=f"{parent_mode:04o}",
        fresh=fresh,
    )


def revalidate_production_authorization(
    authorization: ApplyAuthorization,
) -> ApplyAuthorization:
    """Re-read backup bytes inside the engine before any production write."""
    if authorization.target_database != PRODUCTION_TARGET_DATABASE:
        return authorization
    assert authorization.production_backup_path is not None
    assert authorization.production_backup_sha is not None
    assert authorization.confirm_production_backup_sha is not None
    assert authorization.write_freeze_at is not None
    try:
        observed = validate_production_backup(
            authorization.production_backup_path,
            backup_sha=authorization.production_backup_sha,
            confirm_backup_sha=authorization.confirm_production_backup_sha,
            write_freeze_at=authorization.write_freeze_at,
            require_fresh=False,
        )
    except Exception as exc:
        raise ProductionBackupRevalidationError(
            str(getattr(exc, "code", "backup_revalidation_failed")),
            "The production backup failed mandatory engine-side revalidation.",
        ) from exc
    expected = authorization.production_backup
    if (
        expected is None
        or observed.validated_at < expected.validated_at
        or observed.model_dump(exclude={"validated_at", "fresh"})
        != expected.model_dump(exclude={"validated_at", "fresh"})
    ):
        raise ProductionBackupRevalidationError(
            "backup_revalidation_mismatch",
            "The production backup evidence changed before the write boundary.",
        )
    return authorization.model_copy(update={"production_backup": observed})


__all__ = [
    "MAX_PRODUCTION_BACKUP_AGE",
    "ProductionBackupRevalidationError",
    "parse_write_freeze_at",
    "revalidate_production_authorization",
    "validate_production_backup",
]

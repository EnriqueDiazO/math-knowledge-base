"""Safe, bounded reader for unversioned legacy MathMongo export archives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from mathmongo.source_catalog_migration.models import ArchiveMember
from mathmongo.source_catalog_migration.models import InputSnapshot
from mathmongo.source_catalog_migration.models import ZipSafetyReport

DEFAULT_MAX_MEMBERS = 1_000
DEFAULT_MAX_MEMBER_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 100.0

HARD_MAX_MEMBERS = 10_000
HARD_MAX_MEMBER_BYTES = 256 * 1024 * 1024
HARD_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
HARD_MAX_COMPRESSION_RATIO = 200.0

_ALLOWED_COLLECTIONS = frozenset(
    {
        "backlog_items",
        "concepts",
        "deliverables",
        "knowledge_graph_maps",
        "latex_documents",
        "latex_notes",
        "media_assets",
        "references",
        "relations",
        "sources",
        "source_catalog_migration_manifest",
        "weekly_reviews",
        "worklog_entries",
    }
)
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SUPPORTED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})


class ZipValidationError(ValueError):
    """Raised before planning when an archive fails closed validation."""

    def __init__(self, code: str, message: str, *, member: str | None = None) -> None:
        """Retain a stable diagnostic code without exposing member payloads."""
        self.code = code
        self.member = member
        suffix = f" ({member})" if member else ""
        super().__init__(f"{message}{suffix}")


class InputChangedError(ZipValidationError):
    """The authoritative archive changed while it was being inspected."""

    def __init__(self) -> None:
        """Use a stable error that callers can map to a closed failure."""
        super().__init__("input_changed", "Input ZIP changed during inspection")


@dataclass(frozen=True, slots=True)
class ZipSafetyLimits:
    """Configurable limits bounded by hard S1C1 ceilings."""

    max_members: int = DEFAULT_MAX_MEMBERS
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO

    def __post_init__(self) -> None:
        """Reject booleans, non-positive limits, and unsafe ceiling increases."""
        integer_limits = (
            ("max_members", self.max_members, HARD_MAX_MEMBERS),
            ("max_member_bytes", self.max_member_bytes, HARD_MAX_MEMBER_BYTES),
            ("max_total_bytes", self.max_total_bytes, HARD_MAX_TOTAL_BYTES),
        )
        for name, value, maximum in integer_limits:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}")
        ratio = self.max_compression_ratio
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
            raise TypeError("max_compression_ratio must be numeric")
        if not 1 <= float(ratio) <= HARD_MAX_COMPRESSION_RATIO:
            raise ValueError(
                f"max_compression_ratio must be between 1 and {HARD_MAX_COMPRESSION_RATIO:g}"
            )


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """Filesystem and content identity used for the pre/post input guard."""

    device: int
    inode: int
    size_bytes: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class LoadedLegacyExport:
    """Validated JSON collections and bounded metadata held only in memory."""

    input_snapshot: InputSnapshot
    zip_safety: ZipSafetyReport
    metadata: dict[str, Any]
    collections: dict[str, tuple[dict[str, Any], ...]]
    member_sha256: dict[str, str]
    input_identity: FileIdentity


def _descriptor_identity(value: os.stat_result) -> tuple[int, ...]:
    """Return the immutable and change-detecting fields used by the input guard."""
    return (
        value.st_dev,
        value.st_ino,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        stat.S_IMODE(value.st_mode),
    )


def _hash_stable_descriptor(descriptor: int) -> tuple[os.stat_result, str]:
    """Hash one anchored regular descriptor without changing its file offset."""
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ZipValidationError("input_not_regular", "Input ZIP must be a regular file")
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        chunk = os.pread(descriptor, min(1024 * 1024, before.st_size - offset), offset)
        if not chunk:
            raise InputChangedError()
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    if _descriptor_identity(after) != _descriptor_identity(before):
        raise InputChangedError()
    return after, digest.hexdigest()


def _open_input_directory_chain(directory: Path) -> tuple[list[int], tuple[str, ...]]:
    """Anchor every absolute parent component without following symlinks."""
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


def _verify_input_directory_chain(descriptors: list[int], parts: tuple[str, ...]) -> None:
    """Require every lexical directory name to retain its anchored inode."""
    for index, part in enumerate(parts):
        named = os.stat(part, dir_fd=descriptors[index], follow_symlinks=False)
        anchored = os.fstat(descriptors[index + 1])
        if not stat.S_ISDIR(named.st_mode) or (named.st_dev, named.st_ino) != (
            anchored.st_dev,
            anchored.st_ino,
        ):
            raise InputChangedError()


@contextmanager
def _anchored_input(path: Path) -> Iterator[tuple[int, FileIdentity]]:
    """Keep the exact descriptor that was hashed anchored through ZIP parsing."""
    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    try:
        directory_descriptors, parts = _open_input_directory_chain(path.parent)
        parent_before = os.fstat(directory_descriptors[-1])
        named_before = os.stat(
            path.name,
            dir_fd=directory_descriptors[-1],
            follow_symlinks=False,
        )
        if stat.S_ISLNK(named_before.st_mode):
            raise ZipValidationError("input_symlink", "Input ZIP must not be a symbolic link")
        if not stat.S_ISREG(named_before.st_mode):
            raise ZipValidationError("input_not_regular", "Input ZIP must be a regular file")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        file_descriptor = os.open(path.name, flags, dir_fd=directory_descriptors[-1])
        anchored_before, digest = _hash_stable_descriptor(file_descriptor)
        if _descriptor_identity(anchored_before) != _descriptor_identity(named_before):
            raise InputChangedError()
        identity = FileIdentity(
            device=anchored_before.st_dev,
            inode=anchored_before.st_ino,
            size_bytes=anchored_before.st_size,
            modified_ns=anchored_before.st_mtime_ns,
            sha256=digest,
        )
        try:
            yield file_descriptor, identity
        finally:
            anchored_after, final_digest = _hash_stable_descriptor(file_descriptor)
            try:
                named_after = os.stat(
                    path.name,
                    dir_fd=directory_descriptors[-1],
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise InputChangedError() from exc
            if (
                final_digest != digest
                or _descriptor_identity(anchored_after) != _descriptor_identity(anchored_before)
                or _descriptor_identity(named_after) != _descriptor_identity(anchored_before)
            ):
                raise InputChangedError()
            parent_after = os.fstat(directory_descriptors[-1])
            parent_fields = (
                "st_dev",
                "st_ino",
                "st_uid",
                "st_gid",
                "st_mtime_ns",
                "st_ctime_ns",
                "st_mode",
            )
            if any(
                getattr(parent_after, field) != getattr(parent_before, field)
                for field in parent_fields
            ):
                raise InputChangedError()
            _verify_input_directory_chain(directory_descriptors, parts)
    except (InputChangedError, ZipValidationError):
        raise
    except OSError as exc:
        raise ZipValidationError("input_unreadable", "Input ZIP is not readable") from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)


def identify_input(path: str | os.PathLike[str]) -> FileIdentity:
    """Return a regular, non-symlink file identity and complete SHA-256."""
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = path.absolute()
    with _anchored_input(path) as (_descriptor, identity):
        return identity


def verify_input_unchanged(
    path: str | os.PathLike[str],
    expected: FileIdentity,
) -> None:
    """Fail if path identity, metadata, or content differs from the initial read."""
    current = identify_input(path)
    if current != expected:
        raise InputChangedError()


def _member_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name:
        raise ZipValidationError("unsafe_path", "ZIP member has an empty or NUL name")
    if "\\" in name:
        raise ZipValidationError(
            "unsafe_path", "ZIP member uses a non-portable backslash", member=name
        )
    if name.startswith("/") or _WINDOWS_DRIVE_RE.match(name):
        raise ZipValidationError("absolute_path", "ZIP member is absolute", member=name)
    path = PurePosixPath(name)
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ZipValidationError(
            "path_traversal", "ZIP member contains an unsafe path component", member=name
        )
    expected = path.as_posix() + ("/" if name.endswith("/") else "")
    if expected != name:
        raise ZipValidationError("unsafe_path", "ZIP member path is not canonical", member=name)
    return path


def _unix_kind(info: zipfile.ZipInfo) -> str:
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


def _layout_kind(relative_parts: tuple[str, ...]) -> str | None:
    if relative_parts == ("metadata.json",):
        return "metadata"
    if (
        len(relative_parts) == 2
        and relative_parts[0] == "collections"
        and relative_parts[1].endswith(".json")
        and relative_parts[1][:-5] in _ALLOWED_COLLECTIONS
    ):
        return "collection"
    if (
        len(relative_parts) == 1
        and relative_parts[0].endswith(".json")
        and relative_parts[0][:-5] in _ALLOWED_COLLECTIONS
    ):
        return "collection"
    if relative_parts and relative_parts[0] == "media":
        return "media"
    return None


def _validate_members(
    infos: list[zipfile.ZipInfo],
    limits: ZipSafetyLimits,
) -> tuple[str, tuple[ArchiveMember, ...], ZipSafetyReport]:
    if not infos:
        raise ZipValidationError("empty_archive", "ZIP archive has no members")
    if len(infos) > limits.max_members:
        raise ZipValidationError("member_limit", "ZIP archive exceeds its member limit")

    raw_names: set[str] = set()
    normalized_names: set[str] = set()
    logical_names: set[str] = set()
    paths: list[PurePosixPath] = []
    members: list[ArchiveMember] = []
    total_size = 0
    total_compressed = 0
    maximum_ratio = 0.0
    suspicious_empty: list[str] = []
    collection_identities: set[str] = set()
    collection_layouts: set[str] = set()

    for info in infos:
        path = _member_path(info.filename)
        normalized_name = unicodedata.normalize("NFC", info.filename)
        logical_name = path.as_posix()
        if (
            info.filename in raw_names
            or normalized_name in normalized_names
            or logical_name in logical_names
        ):
            raise ZipValidationError(
                "duplicate_member", "ZIP archive contains a duplicate member", member=info.filename
            )
        raw_names.add(info.filename)
        normalized_names.add(normalized_name)
        logical_names.add(logical_name)
        paths.append(path)

        relative_parts = path.parts[1:]
        if _layout_kind(relative_parts) == "collection":
            collection_name = PurePosixPath(relative_parts[-1]).stem
            if collection_name in collection_identities:
                raise ZipValidationError(
                    "duplicate_collection",
                    "ZIP archive contains duplicate collection identities",
                    member=info.filename,
                )
            collection_identities.add(collection_name)
            collection_layouts.add("modern" if relative_parts[0] == "collections" else "historical")

        if info.flag_bits & 0x1:
            raise ZipValidationError(
                "encrypted_member", "Encrypted ZIP members are not supported", member=info.filename
            )
        if info.compress_type not in _SUPPORTED_COMPRESSION:
            raise ZipValidationError(
                "unsupported_compression",
                "ZIP member uses an unsupported compression method",
                member=info.filename,
            )
        kind = _unix_kind(info)
        if kind == "symlink":
            raise ZipValidationError(
                "symlink_member", "ZIP symlinks are forbidden", member=info.filename
            )
        if kind == "nonregular":
            raise ZipValidationError(
                "nonregular_member",
                "ZIP hardlinks and other non-regular members are forbidden",
                member=info.filename,
            )
        if (kind == "directory") != info.is_dir():
            raise ZipValidationError(
                "member_type_mismatch", "ZIP member type is inconsistent", member=info.filename
            )
        if info.file_size > limits.max_member_bytes:
            raise ZipValidationError(
                "member_size_limit", "ZIP member exceeds its size limit", member=info.filename
            )
        total_size += info.file_size
        total_compressed += info.compress_size
        if total_size > limits.max_total_bytes:
            raise ZipValidationError("total_size_limit", "ZIP archive exceeds its total size limit")
        ratio = info.file_size / max(info.compress_size, 1)
        maximum_ratio = max(maximum_ratio, ratio)
        if ratio > float(limits.max_compression_ratio):
            raise ZipValidationError(
                "compression_ratio_limit",
                "ZIP member has an anomalous compression ratio",
                member=info.filename,
            )
        if not info.is_dir() and info.file_size == 0:
            suspicious_empty.append(info.filename)
        members.append(
            ArchiveMember(
                name=info.filename,
                size_bytes=info.file_size,
                compressed_size_bytes=info.compress_size,
                compression_ratio=round(ratio, 6),
                crc32=f"{info.CRC:08x}",
                is_directory=info.is_dir(),
            )
        )

    if suspicious_empty:
        raise ZipValidationError(
            "empty_regular_member",
            "ZIP archive contains a suspicious empty regular member",
            member=suspicious_empty[0],
        )
    if len(collection_layouts) > 1:
        raise ZipValidationError(
            "mixed_collection_layout",
            "ZIP archive mixes modern and historical collection layouts",
        )
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
    roots = {path.parts[0] for path in paths}
    if len(roots) != 1:
        raise ZipValidationError("ambiguous_root", "ZIP archive must have one base directory")
    base_directory = next(iter(roots))
    unexpected: list[str] = []
    for info, path in zip(infos, paths, strict=True):
        relative = path.parts[1:]
        expected_directory = info.is_dir() and (
            not relative
            or relative == ("collections",)
            or bool(relative and relative[0] == "media")
        )
        if not expected_directory and _layout_kind(relative) is None:
            unexpected.append(info.filename)
    if unexpected:
        raise ZipValidationError(
            "unexpected_member", "ZIP archive contains an unexpected member", member=unexpected[0]
        )

    report = ZipSafetyReport(
        validated=True,
        member_count=len(infos),
        file_count=sum(not info.is_dir() for info in infos),
        total_uncompressed_bytes=total_size,
        total_compressed_bytes=total_compressed,
        maximum_compression_ratio=round(maximum_ratio, 6),
        base_directory=base_directory,
        unexpected_members=(),
        suspicious_empty_members=(),
    )
    return base_directory, tuple(members), report


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[bytes, str]:
    digest = hashlib.sha256()
    data = bytearray()
    with zf.open(info, "r") as handle:
        while True:
            chunk = handle.read(min(1024 * 1024, info.file_size + 1))
            if not chunk:
                break
            data.extend(chunk)
            digest.update(chunk)
            if len(data) > info.file_size:
                raise ZipValidationError(
                    "member_size_changed",
                    "ZIP member expanded beyond its declared size",
                    member=info.filename,
                )
    if len(data) != info.file_size:
        raise ZipValidationError(
            "member_size_mismatch", "ZIP member size is inconsistent", member=info.filename
        )
    return bytes(data), digest.hexdigest()


def _json_payload(data: bytes, *, member: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ZipValidationError("invalid_utf8", "JSON member is not UTF-8", member=member) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ZipValidationError("invalid_json", "JSON member is invalid", member=member) from exc


def _parse_exported_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ZipValidationError("invalid_metadata", "metadata.exported_at is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_metadata(
    metadata: Any,
    collections: dict[str, tuple[dict[str, Any], ...]],
    media_sizes: dict[str, int],
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ZipValidationError("invalid_metadata", "metadata.json must contain an object")
    declared_counts = metadata.get("collections")
    if not isinstance(declared_counts, dict):
        raise ZipValidationError("invalid_metadata", "metadata.collections must be an object")
    normalized_counts: dict[str, int] = {}
    for name, value in declared_counts.items():
        if name not in _ALLOWED_COLLECTIONS:
            raise ZipValidationError(
                "unexpected_collection",
                "metadata declares an unsupported collection",
                member=str(name),
            )
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ZipValidationError("invalid_metadata", "metadata collection count is invalid")
        normalized_counts[str(name)] = value
    actual_counts = {name: len(documents) for name, documents in collections.items()}
    if normalized_counts != actual_counts:
        raise ZipValidationError(
            "collection_count_mismatch",
            "Declared collection counts do not match collection members",
        )
    declared_media = metadata.get("media_files", {})
    if not isinstance(declared_media, dict):
        raise ZipValidationError("invalid_metadata", "metadata.media_files must be an object")
    normalized_media: dict[str, int] = {}
    for name, value in declared_media.items():
        if not isinstance(name, str) or not name.startswith("media/"):
            raise ZipValidationError("invalid_metadata", "metadata contains an unsafe media name")
        _member_path(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ZipValidationError("invalid_metadata", "metadata media size is invalid")
        normalized_media[name] = value
    if normalized_media != media_sizes:
        raise ZipValidationError(
            "media_size_mismatch", "Declared media files do not match ZIP media members"
        )
    result = dict(metadata)
    result["collections"] = normalized_counts
    result["media_files"] = normalized_media
    return result


def read_legacy_export(
    input_zip: str | os.PathLike[str],
    *,
    database_name: str = "MathV0",
    limits: ZipSafetyLimits | None = None,
    fail_on_input_change: bool = True,
) -> LoadedLegacyExport:
    """Validate and read one export without extraction or filesystem writes."""
    del fail_on_input_change  # S1C1 always fails closed; retained as an explicit CLI contract.
    path = Path(input_zip).expanduser()
    if not path.is_absolute():
        path = path.absolute()
    limits = limits or ZipSafetyLimits()

    try:
        with _anchored_input(path) as (descriptor, initial):
            with os.fdopen(os.dup(descriptor), "rb") as handle:
                with zipfile.ZipFile(handle, "r") as zf:
                    infos = zf.infolist()
                    base, members, safety = _validate_members(infos, limits)
                    corrupt_member = zf.testzip()
                    if corrupt_member is not None:
                        raise ZipValidationError(
                            "crc_mismatch",
                            "ZIP member failed its CRC check",
                            member=corrupt_member,
                        )
                    info_by_name = {info.filename: info for info in infos}
                    metadata_name = f"{base}/metadata.json"
                    metadata_info = info_by_name.get(metadata_name)
                    if metadata_info is None:
                        raise ZipValidationError("missing_metadata", "metadata.json is missing")

                    member_sha256: dict[str, str] = {}
                    metadata_data, metadata_sha = _read_member(zf, metadata_info)
                    member_sha256[metadata_name] = metadata_sha
                    metadata_raw = _json_payload(metadata_data, member=metadata_name)
                    collections: dict[str, tuple[dict[str, Any], ...]] = {}
                    media_sizes: dict[str, int] = {}
                    for info in infos:
                        relative = PurePosixPath(info.filename).parts[1:]
                        kind = _layout_kind(relative)
                        if kind == "collection" and not info.is_dir():
                            data, digest = _read_member(zf, info)
                            member_sha256[info.filename] = digest
                            payload = _json_payload(data, member=info.filename)
                            if not isinstance(payload, list):
                                raise ZipValidationError(
                                    "invalid_collection",
                                    "Collection JSON must contain an array",
                                    member=info.filename,
                                )
                            if not all(isinstance(document, dict) for document in payload):
                                raise ZipValidationError(
                                    "invalid_collection",
                                    "Collection JSON entries must be objects",
                                    member=info.filename,
                                )
                            collections[PurePosixPath(info.filename).stem] = tuple(payload)
                        elif kind == "media" and not info.is_dir():
                            relative_name = PurePosixPath(*relative).as_posix()
                            media_sizes[relative_name] = info.file_size
                    metadata = _validate_metadata(metadata_raw, collections, media_sizes)
    except zipfile.BadZipFile as exc:
        raise ZipValidationError("bad_zip", "ZIP archive is corrupt") from exc

    exported_at = _parse_exported_at(metadata.get("exported_at"))
    declared_format = metadata.get("format") or metadata.get("format_name")
    declared_version = metadata.get("format_version") or metadata.get("schema_version")
    format_name = str(declared_format) if declared_format else "mathkb_legacy_export"
    format_version = str(declared_version) if declared_version is not None else "unversioned"
    format_source = (
        "declared_metadata" if declared_format or declared_version else "layout_inference"
    )
    snapshot = InputSnapshot(
        filename=path.name,
        sha256=initial.sha256,
        size_bytes=initial.size_bytes,
        modified_at=datetime.fromtimestamp(initial.modified_ns / 1_000_000_000, timezone.utc),
        exported_at=exported_at,
        database_name=database_name,
        counts=dict(metadata["collections"]),
        format_name=format_name,
        format_version=format_version,
        format_version_source=format_source,
        members=members,
    )
    return LoadedLegacyExport(
        input_snapshot=snapshot,
        zip_safety=safety,
        metadata=metadata,
        collections=collections,
        member_sha256=member_sha256,
        input_identity=initial,
    )


@contextmanager
def private_temporary_workspace(*, parent: Path | None = None) -> Iterator[Path]:
    """Create a private external workspace and always remove it after use/error."""
    directory = Path(tempfile.mkdtemp(prefix="mathmongo-s1c1-", dir=parent))
    directory.chmod(0o700)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=False)


__all__ = [
    "DEFAULT_MAX_COMPRESSION_RATIO",
    "DEFAULT_MAX_MEMBER_BYTES",
    "DEFAULT_MAX_MEMBERS",
    "DEFAULT_MAX_TOTAL_BYTES",
    "FileIdentity",
    "HARD_MAX_COMPRESSION_RATIO",
    "HARD_MAX_MEMBER_BYTES",
    "HARD_MAX_MEMBERS",
    "HARD_MAX_TOTAL_BYTES",
    "InputChangedError",
    "LoadedLegacyExport",
    "ZipSafetyLimits",
    "ZipValidationError",
    "identify_input",
    "private_temporary_workspace",
    "read_legacy_export",
    "verify_input_unchanged",
]

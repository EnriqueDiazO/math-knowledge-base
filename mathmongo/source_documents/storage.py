"""Private content-addressed storage for Source PDF blobs."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from mathmongo.paths import find_symlink_component
from mathmongo.paths import get_data_dir
from mathmongo.paths import get_source_document_blobs_dir
from mathmongo.paths import get_source_documents_dir
from mathmongo.paths import validate_mutable_path
from mathmongo.source_documents.models import MAX_SOURCE_PDF_UPLOAD_BYTES
from mathmongo.source_documents.models import PDF_MIME_TYPE
from mathmongo.source_documents.models import SHA256_RE
from mathmongo.source_documents.models import PdfVersion

PDF_HEADER = b"%PDF-"


class BlobStorageError(RuntimeError):
    """Base class for safe PDF storage failures."""


class BlobValidationError(BlobStorageError):
    """Uploaded or stored bytes are not a supported PDF."""


class BlobConflictError(BlobStorageError):
    """The canonical SHA path exists with an incompatible identity or payload."""


@dataclass(frozen=True, slots=True)
class PreparedPdf:
    data: bytes
    sha256: str
    size_bytes: int
    logical_path: str


@dataclass(frozen=True, slots=True)
class BlobPublishResult:
    logical_path: str
    sha256: str
    size_bytes: int
    created: bool


@dataclass(frozen=True, slots=True)
class BlobInspection:
    ok: bool
    issues: tuple[str, ...]
    sha256: str | None = None
    size_bytes: int | None = None


class SourceDocumentBlobStore:
    """Store immutable PDF blobs beneath one explicit XDG data root."""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.data_root = validate_mutable_path(data_root or get_data_dir())
        self.documents_root = validate_mutable_path(
            get_source_documents_dir()
            if data_root is None
            else self.data_root / "source_documents",
            allowed_root=self.data_root,
        )
        self.blob_root = (
            get_source_document_blobs_dir()
            if data_root is None
            else self.documents_root / "blobs" / "sha256"
        )

    @staticmethod
    def prepare_pdf(data: bytes, *, max_bytes: int = MAX_SOURCE_PDF_UPLOAD_BYTES) -> PreparedPdf:
        """Validate bounded PDF bytes and derive their canonical identity."""
        if not isinstance(data, bytes):
            raise BlobValidationError("PDF payload must be bytes")
        if not data:
            raise BlobValidationError("PDF payload cannot be empty")
        if len(data) > max_bytes:
            raise BlobValidationError(f"PDF payload exceeds the {max_bytes}-byte limit")
        if not data.startswith(PDF_HEADER):
            raise BlobValidationError("PDF payload does not have a valid %PDF- header")
        digest = hashlib.sha256(data).hexdigest()
        logical_path = f"source_documents/blobs/sha256/{digest[:2]}/{digest}.pdf"
        return PreparedPdf(data, digest, len(data), logical_path)

    def path_for_sha(self, sha256: str) -> Path:
        """Derive a controlled absolute path solely from a canonical SHA-256."""
        if not SHA256_RE.fullmatch(str(sha256 or "")):
            raise BlobValidationError("Invalid canonical PDF SHA-256")
        try:
            return validate_mutable_path(
                self.blob_root / sha256[:2] / f"{sha256}.pdf",
                allowed_root=self.documents_root,
            )
        except (OSError, ValueError) as exc:
            raise BlobConflictError("Source document storage path is unsafe") from exc

    def path_for_version(self, version: PdfVersion) -> Path:
        """Resolve a validated version without trusting its logical path as an absolute path."""
        expected = f"source_documents/blobs/sha256/{version.sha256[:2]}/{version.sha256}.pdf"
        if version.logical_path != expected:
            raise BlobValidationError("PDF version logical path is not canonical")
        return self.path_for_sha(version.sha256)

    def _ensure_private_directories(self, shard: Path) -> None:
        current = self.documents_root
        for directory in (current, current / "blobs", self.blob_root, shard):
            try:
                validate_mutable_path(directory, allowed_root=self.data_root)
            except (OSError, ValueError) as exc:
                raise BlobConflictError("Source document storage directory is unsafe") from exc
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if directory.is_symlink() or not directory.is_dir():
                raise BlobConflictError("Source document storage contains an unsafe directory")
            directory.chmod(0o700)

    @staticmethod
    def _read_stable(path: Path, *, max_bytes: int) -> tuple[bytes, os.stat_result]:
        if find_symlink_component(path) is not None:
            raise BlobConflictError("Source PDF blob path contains a symbolic link")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise BlobConflictError("Source PDF blob cannot be opened safely") from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise BlobConflictError("Source PDF blob is not a regular file")
            if before.st_size <= 0 or before.st_size > max_bytes:
                raise BlobValidationError("Stored PDF blob has an invalid size")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise BlobConflictError("Stored PDF blob changed during reading")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise BlobConflictError("Stored PDF blob grew during reading")
            after = os.fstat(descriptor)
            identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, field) != getattr(after, field) for field in identity):
                raise BlobConflictError("Stored PDF blob changed during reading")
            return b"".join(chunks), after
        finally:
            os.close(descriptor)

    def publish(self, prepared: PreparedPdf) -> BlobPublishResult:
        """Publish once without overwrite, returning identical for a matching existing blob."""
        expected = self.prepare_pdf(prepared.data)
        if expected != prepared:
            raise BlobValidationError("Prepared PDF identity does not match its bytes")
        destination = self.path_for_sha(prepared.sha256)
        self._ensure_private_directories(destination.parent)

        if destination.exists() or destination.is_symlink():
            data, observed = self._read_stable(
                destination,
                max_bytes=MAX_SOURCE_PDF_UPLOAD_BYTES,
            )
            if data != prepared.data or stat.S_IMODE(observed.st_mode) != 0o600:
                raise BlobConflictError("Canonical PDF blob path contains incompatible data")
            return BlobPublishResult(
                prepared.logical_path,
                prepared.sha256,
                prepared.size_bytes,
                False,
            )

        temporary = destination.parent / f".pending-{uuid4().hex}"
        descriptor: int | None = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temporary, flags, 0o600)
            view = memoryview(prepared.data)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError("Could not complete Source PDF blob staging")
                written += count
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = None
            try:
                os.link(temporary, destination, follow_symlinks=False)
                created = True
            except FileExistsError as exc:
                data, observed = self._read_stable(
                    destination,
                    max_bytes=MAX_SOURCE_PDF_UPLOAD_BYTES,
                )
                if data != prepared.data or stat.S_IMODE(observed.st_mode) != 0o600:
                    raise BlobConflictError("Concurrent PDF blob publication conflicted") from exc
                created = False
            directory_descriptor = os.open(
                destination.parent,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

        return BlobPublishResult(
            prepared.logical_path,
            prepared.sha256,
            prepared.size_bytes,
            created,
        )

    def read_version(self, version: PdfVersion) -> bytes:
        """Read and verify one stored version before handing bytes to a viewer or export."""
        path = self.path_for_version(version)
        data, observed = self._read_stable(path, max_bytes=MAX_SOURCE_PDF_UPLOAD_BYTES)
        if stat.S_IMODE(observed.st_mode) != 0o600:
            raise BlobConflictError("Stored PDF blob permissions are not 0600")
        if len(data) != version.size_bytes or not data.startswith(PDF_HEADER):
            raise BlobValidationError("Stored PDF blob size or header is invalid")
        if hashlib.sha256(data).hexdigest() != version.sha256:
            raise BlobConflictError("Stored PDF blob SHA-256 does not match metadata")
        return data

    def _controlled_directory_issues(self, path: Path) -> tuple[str, ...]:
        """Check private controlled directories without exposing their absolute names."""
        for directory in (
            self.documents_root,
            self.documents_root / "blobs",
            self.blob_root,
            path.parent,
        ):
            try:
                if find_symlink_component(directory) is not None:
                    return ("directory_symlink",)
                observed = directory.stat(follow_symlinks=False)
            except FileNotFoundError:
                return ("blob_missing",)
            except OSError:
                return ("directory_unreadable",)
            if not stat.S_ISDIR(observed.st_mode):
                return ("directory_not_directory",)
            if stat.S_IMODE(observed.st_mode) != 0o700:
                return ("directory_permissions",)
        return ()

    def inspect_version(self, version: PdfVersion) -> BlobInspection:
        """Return bounded integrity diagnostics without raising or exposing absolute paths."""
        try:
            path = self.path_for_version(version)
            directory_issues = self._controlled_directory_issues(path)
            if directory_issues:
                return BlobInspection(False, directory_issues)
            data = self.read_version(version)
        except FileNotFoundError:
            return BlobInspection(False, ("blob_missing",))
        except BlobStorageError as exc:
            return BlobInspection(False, (type(exc).__name__,))
        except ValueError:
            return BlobInspection(False, ("unsafe_blob_path",))
        except OSError:
            return BlobInspection(False, ("blob_unreadable",))
        return BlobInspection(
            True,
            (),
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )


def pdf_version_from_prepared(
    prepared: PreparedPdf,
    *,
    original_filename: str,
    version_id: str | None = None,
    created_at: object | None = None,
) -> PdfVersion:
    """Build canonical version metadata from validated bytes."""
    values = {
        "sha256": prepared.sha256,
        "size_bytes": prepared.size_bytes,
        "mime_type": PDF_MIME_TYPE,
        "logical_path": prepared.logical_path,
        "original_filename": original_filename,
    }
    if version_id is not None:
        values["version_id"] = version_id
    if created_at is not None:
        values["created_at"] = created_at
    return PdfVersion.model_validate(values)

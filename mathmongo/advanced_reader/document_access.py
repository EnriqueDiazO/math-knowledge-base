"""Safe orchestration and verified descriptor access for S2 PDF blobs."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.document_page_maps.service import PageMapOperationStatus
from mathmongo.paths import find_symlink_component
from mathmongo.reading_space.service import ReaderContext
from mathmongo.reading_space.service import ReadingOperationStatus
from mathmongo.source_documents.models import PDF_MIME_TYPE
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import PdfVersion
from mathmongo.source_documents.models import validate_document_id
from mathmongo.source_documents.storage import BlobStorageError

VERIFY_CHUNK_BYTES = 1024 * 1024
STREAM_CHUNK_BYTES = 256 * 1024


class AdvancedReaderError(RuntimeError):
    """A bounded public API failure with no underlying path or URI."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.public_message = message
        self.status_code = status_code
        self.headers = headers or {}
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ResolvedPdfDocument:
    context: ReaderContext
    version: PdfVersion


def _same_file_identity(before: os.stat_result, after: os.stat_result) -> bool:
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    return all(getattr(before, field) == getattr(after, field) for field in fields)


class VerifiedPdfHandle:
    """One already-hashed immutable descriptor, streamed in bounded chunks."""

    def __init__(
        self,
        descriptor: int,
        *,
        observed: os.stat_result,
        version: PdfVersion,
    ) -> None:
        self._descriptor = descriptor
        self._observed = observed
        self._closed = False
        self.size = version.size_bytes
        self.sha256 = version.sha256
        self.mime_type = PDF_MIME_TYPE
        self.original_filename = version.original_filename

    @classmethod
    def open(
        cls, dependencies: AdvancedReaderDependencies, version: PdfVersion
    ) -> VerifiedPdfHandle:
        """Resolve only through S2 storage, then verify header, size, mode and SHA."""
        storage = dependencies.document_service.storage
        descriptor: int | None = None
        try:
            path = storage.path_for_version(version)
            expected = storage.path_for_sha(version.sha256)
            lexical_path = Path(os.path.abspath(path))
            lexical_root = Path(os.path.abspath(storage.documents_root))
            if path != expected or not lexical_path.is_relative_to(lexical_root):
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                )
            if find_symlink_component(lexical_path) is not None:
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                )
            for directory in (
                storage.documents_root,
                storage.documents_root / "blobs",
                storage.blob_root,
                lexical_path.parent,
            ):
                observed_directory = directory.stat(follow_symlinks=False)
                if (
                    not stat.S_ISDIR(observed_directory.st_mode)
                    or stat.S_IMODE(observed_directory.st_mode) != 0o700
                ):
                    raise AdvancedReaderError(
                        "integrity_error",
                        "PDF integrity verification failed.",
                        status_code=409,
                    )
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(lexical_path, flags)
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600:
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                )
            if before.st_size != version.size_bytes or before.st_size <= 0:
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                )
            if os.pread(descriptor, 5, 0) != b"%PDF-":
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                )
            digest = hashlib.sha256()
            offset = 0
            while offset < before.st_size:
                chunk = os.pread(
                    descriptor,
                    min(VERIFY_CHUNK_BYTES, before.st_size - offset),
                    offset,
                )
                if not chunk:
                    raise AdvancedReaderError(
                        "integrity_error",
                        "PDF integrity verification failed.",
                        status_code=409,
                    )
                digest.update(chunk)
                offset += len(chunk)
            if os.pread(descriptor, 1, before.st_size):
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                )
            after = os.fstat(descriptor)
            if not _same_file_identity(before, after) or digest.hexdigest() != version.sha256:
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                )
            result = cls(descriptor, observed=after, version=version)
            descriptor = None
            return result
        except FileNotFoundError as exc:
            raise AdvancedReaderError(
                "blob_missing",
                "The PDF blob is unavailable.",
                status_code=404,
            ) from exc
        except AdvancedReaderError:
            raise
        except (BlobStorageError, OSError, ValueError) as exc:
            raise AdvancedReaderError(
                "integrity_error",
                "PDF integrity verification failed.",
                status_code=409,
            ) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def close(self) -> None:
        if not self._closed:
            os.close(self._descriptor)
            self._closed = True

    def iter_bytes(self, start: int, length: int):
        """Yield exactly one interval and close the descriptor on every exit path."""
        remaining = length
        offset = start
        try:
            while remaining:
                chunk = os.pread(
                    self._descriptor,
                    min(STREAM_CHUNK_BYTES, remaining),
                    offset,
                )
                if not chunk:
                    raise RuntimeError("Verified PDF changed during streaming")
                yield chunk
                offset += len(chunk)
                remaining -= len(chunk)
            after = os.fstat(self._descriptor)
            if not _same_file_identity(self._observed, after):
                raise RuntimeError("Verified PDF changed during streaming")
        finally:
            self.close()


class DocumentAccessService:
    """Translate existing S2/S3/Page Map results into the S5A boundary."""

    def __init__(self, dependencies: AdvancedReaderDependencies) -> None:
        self.dependencies = dependencies

    @staticmethod
    def _validated_document_id(document_id: str) -> str:
        try:
            return validate_document_id(document_id)
        except (TypeError, ValueError) as exc:
            raise AdvancedReaderError(
                "invalid_document_id",
                "The Document identifier is invalid.",
                status_code=422,
            ) from exc

    def resolve_pdf(
        self,
        document_id: str,
        *,
        inspect_integrity: bool,
    ) -> ResolvedPdfDocument:
        identifier = self._validated_document_id(document_id)
        result = self.dependencies.reading_service.get_reader_context(identifier)
        if result.status == ReadingOperationStatus.NOT_FOUND:
            raise AdvancedReaderError(
                "document_not_found",
                "The requested Document does not exist.",
                status_code=404,
            )
        if result.status == ReadingOperationStatus.ARCHIVED:
            raise AdvancedReaderError(
                "document_archived",
                "Archived Documents cannot be opened in the Advanced Reader.",
                status_code=409,
            )
        if result.status == ReadingOperationStatus.ERROR:
            raise AdvancedReaderError(
                "database_unavailable",
                "The configured database is unavailable.",
                status_code=503,
            )
        if not result.completed or result.value is None:
            raise AdvancedReaderError(
                "integrity_error",
                "Document associations could not be verified.",
                status_code=409,
            )
        context = result.value
        document = context.document
        if document.status == DocumentStatus.ARCHIVED:
            raise AdvancedReaderError(
                "document_archived",
                "Archived Documents cannot be opened in the Advanced Reader.",
                status_code=409,
            )
        if document.kind != DocumentKind.PDF or document.pdf is None:
            raise AdvancedReaderError(
                "document_not_pdf",
                "The Advanced Reader supports PDF Documents only.",
                status_code=415,
            )
        version = document.pdf.current_version
        if inspect_integrity:
            try:
                inspection = self.dependencies.document_service.inspect_document_integrity(
                    identifier
                )
            except Exception as exc:
                raise AdvancedReaderError(
                    "integrity_error",
                    "PDF integrity verification failed.",
                    status_code=409,
                ) from exc
            if not inspection.ok:
                code = "blob_missing" if "blob_missing" in inspection.issues else "integrity_error"
                status_code = 404 if code == "blob_missing" else 409
                message = (
                    "The PDF blob is unavailable."
                    if code == "blob_missing"
                    else "PDF integrity verification failed."
                )
                raise AdvancedReaderError(code, message, status_code=status_code)
        return ResolvedPdfDocument(context, version)

    def open_verified_pdf(self, resolved: ResolvedPdfDocument) -> VerifiedPdfHandle:
        return VerifiedPdfHandle.open(self.dependencies, resolved.version)

    def page_label(self, document_id: str, pdf_page: int) -> tuple[str | None, str]:
        if isinstance(pdf_page, bool) or not isinstance(pdf_page, int) or pdf_page < 1:
            raise AdvancedReaderError(
                "page_invalid",
                "PDF page must be an integer greater than or equal to 1.",
                status_code=422,
            )
        result = self.dependencies.page_map_service.compute_page_label(document_id, pdf_page)
        if result.status == PageMapOperationStatus.SUCCESS and result.value is not None:
            label = result.value.book_page_label
            if label:
                return label, f"Book page {label} · PDF page {pdf_page}"
        return None, f"PDF page {pdf_page}"


__all__ = [
    "AdvancedReaderError",
    "DocumentAccessService",
    "ResolvedPdfDocument",
    "VerifiedPdfHandle",
]

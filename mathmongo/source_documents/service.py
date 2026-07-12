"""Application service for Source-associated PDF and web documents."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import ValidationError

from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceRights
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.models import normalize_web_url
from mathmongo.source_documents.repository import SourceDocumentPage
from mathmongo.source_documents.repository import SourceDocumentRepository
from mathmongo.source_documents.repository import SourceDocumentRepositoryConflictError
from mathmongo.source_documents.storage import BlobStorageError
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared


class DocumentOperationStatus(str, Enum):
    CREATED = "created"
    IDENTICAL = "identical"
    CONFLICT = "conflict"
    PARTIAL = "partial"
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DocumentOperationResult:
    status: DocumentOperationStatus
    value: SourceDocument | None = None
    message: str = ""
    metadata_persisted: bool = False
    blob_created: bool = False

    @property
    def completed(self) -> bool:
        return self.status in {
            DocumentOperationStatus.CREATED,
            DocumentOperationStatus.IDENTICAL,
            DocumentOperationStatus.SUCCESS,
        }


@dataclass(frozen=True, slots=True)
class DocumentIntegrityInspection:
    document_id: str
    ok: bool
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DocumentPdfPayload:
    document: SourceDocument
    pdf_bytes: bytes
    file_name: str
    sha256: str


def _rights(value: SourceRights | Mapping[str, Any] | None) -> SourceRights:
    if value is None:
        return SourceRights()
    return value if isinstance(value, SourceRights) else SourceRights.model_validate(value)


def _semantic_metadata(document: SourceDocument) -> dict[str, Any]:
    return {
        "source_id": document.source_id,
        "reference_id": document.reference_id,
        "kind": document.kind.value,
        "title": document.title,
        "description": document.description,
        "language": document.language,
        "tags": document.tags,
        "rights": document.rights.model_dump(mode="json"),
    }


class SourceDocumentService:
    """Coordinate validated metadata with immutable XDG PDF blobs."""

    def __init__(
        self,
        database: Any,
        *,
        documents: SourceDocumentRepository | None = None,
        storage: SourceDocumentBlobStore | None = None,
        sources: SourceRepository | None = None,
        references: ReferenceRepository | None = None,
    ) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("SourceDocumentService requires an explicit database")
        self.database = database
        self.documents = documents or SourceDocumentRepository(database)
        self.storage = storage or SourceDocumentBlobStore()
        self.sources = sources or SourceRepository(database)
        self.references = references or ReferenceRepository(database)

    def _source(self, source_id: str) -> Source | None:
        return self.sources.get_by_id(source_id)

    def _reference(self, reference_id: str | None, source_id: str) -> Reference | None:
        if reference_id is None:
            return None
        reference = self.references.get_by_id(reference_id)
        if reference is None:
            raise ValueError("Reference does not exist")
        if source_id not in reference.source_ids:
            raise ValueError("Reference is not associated with the selected Source")
        return reference

    @staticmethod
    def _same_pdf_request(
        existing: SourceDocument,
        candidate: SourceDocument,
    ) -> bool:
        if existing.pdf is None or candidate.pdf is None:
            return False
        return (
            _semantic_metadata(existing) == _semantic_metadata(candidate)
            and existing.pdf.current_version.sha256 == candidate.pdf.current_version.sha256
            and existing.pdf.current_version.original_filename
            == candidate.pdf.current_version.original_filename
        )

    @staticmethod
    def _same_web_request(existing: SourceDocument, candidate: SourceDocument) -> bool:
        if existing.web is None or candidate.web is None:
            return False
        return (
            _semantic_metadata(existing) == _semantic_metadata(candidate)
            and existing.web.url_normalized == candidate.web.url_normalized
        )

    def create_pdf_document(
        self,
        *,
        source_id: str,
        pdf_bytes: bytes,
        original_filename: str,
        title: str,
        description: str = "",
        language: str | None = None,
        tags: Iterable[str] = (),
        rights: SourceRights | Mapping[str, Any] | None = None,
        reference_id: str | None = None,
        document_id: str | None = None,
        version_id: str | None = None,
    ) -> DocumentOperationResult:
        """Validate, deduplicate, publish a PDF blob, then insert its MongoDB metadata."""
        try:
            if self._source(source_id) is None:
                return DocumentOperationResult(
                    DocumentOperationStatus.NOT_FOUND,
                    message="Source does not exist.",
                )
            self._reference(reference_id, source_id)
            prepared = self.storage.prepare_pdf(pdf_bytes)
            version = pdf_version_from_prepared(
                prepared,
                original_filename=original_filename,
                version_id=version_id,
            )
            values: dict[str, Any] = {
                "source_id": source_id,
                "reference_id": reference_id,
                "kind": DocumentKind.PDF,
                "title": title,
                "description": description,
                "language": language,
                "tags": list(tags),
                "rights": _rights(rights),
                "pdf": PdfDocument(versions=[version], current_version_id=version.version_id),
            }
            if document_id is not None:
                values["document_id"] = document_id
            candidate = SourceDocument.model_validate(values)

            if document_id is not None:
                by_id = self.documents.get_by_id(document_id)
                if by_id is not None:
                    if self._same_pdf_request(by_id, candidate):
                        return DocumentOperationResult(
                            DocumentOperationStatus.IDENTICAL,
                            by_id,
                            "An identical PDF Document already exists.",
                        )
                    return DocumentOperationResult(
                        DocumentOperationStatus.CONFLICT,
                        by_id,
                        "The document_id already contains different metadata.",
                    )

            matches = self.documents.find_pdf_identity(source_id, prepared.sha256)
            if len(matches) > 1:
                return DocumentOperationResult(
                    DocumentOperationStatus.CONFLICT,
                    message="The destination contains duplicate PDF Document identities.",
                )
            if matches:
                existing = matches[0]
                status = (
                    DocumentOperationStatus.IDENTICAL
                    if self._same_pdf_request(existing, candidate)
                    else DocumentOperationStatus.CONFLICT
                )
                return DocumentOperationResult(
                    status,
                    existing,
                    (
                        "An identical PDF Document already exists."
                        if status == DocumentOperationStatus.IDENTICAL
                        else "This Source already has the same PDF with different metadata."
                    ),
                )

            self.documents.ensure_indexes()
            published = self.storage.publish(prepared)
            try:
                stored = self.documents.insert(candidate)
            except SourceDocumentRepositoryConflictError:
                concurrent = self.documents.find_pdf_identity(source_id, prepared.sha256)
                if len(concurrent) == 1 and self._same_pdf_request(concurrent[0], candidate):
                    return DocumentOperationResult(
                        DocumentOperationStatus.IDENTICAL,
                        concurrent[0],
                        "A concurrent identical PDF Document was retained.",
                        blob_created=published.created,
                    )
                return DocumentOperationResult(
                    DocumentOperationStatus.PARTIAL
                    if published.created
                    else DocumentOperationStatus.CONFLICT,
                    message="PDF blob was retained but metadata conflicted.",
                    blob_created=published.created,
                )
            except Exception:
                return DocumentOperationResult(
                    DocumentOperationStatus.PARTIAL
                    if published.created
                    else DocumentOperationStatus.ERROR,
                    message=(
                        "PDF blob was published, but metadata could not be persisted."
                        if published.created
                        else "PDF metadata could not be persisted."
                    ),
                    blob_created=published.created,
                )
        except (BlobStorageError, ValidationError, ValueError) as exc:
            return DocumentOperationResult(DocumentOperationStatus.ERROR, message=str(exc))
        except Exception:
            return DocumentOperationResult(
                DocumentOperationStatus.ERROR,
                message="Unexpected database or storage error.",
            )
        return DocumentOperationResult(
            DocumentOperationStatus.CREATED,
            stored,
            "PDF Document created.",
            metadata_persisted=True,
            blob_created=published.created,
        )

    def create_web_document(
        self,
        *,
        source_id: str,
        url_raw: str,
        title: str,
        description: str = "",
        language: str | None = None,
        tags: Iterable[str] = (),
        rights: SourceRights | Mapping[str, Any] | None = None,
        reference_id: str | None = None,
        document_id: str | None = None,
    ) -> DocumentOperationResult:
        """Create URL metadata without making an HTTP request."""
        try:
            if self._source(source_id) is None:
                return DocumentOperationResult(
                    DocumentOperationStatus.NOT_FOUND,
                    message="Source does not exist.",
                )
            self._reference(reference_id, source_id)
            web = WebDocument(url_raw=url_raw, url_normalized=normalize_web_url(url_raw))
            values: dict[str, Any] = {
                "source_id": source_id,
                "reference_id": reference_id,
                "kind": DocumentKind.WEB,
                "title": title,
                "description": description,
                "language": language,
                "tags": list(tags),
                "rights": _rights(rights),
                "web": web,
            }
            if document_id is not None:
                values["document_id"] = document_id
            candidate = SourceDocument.model_validate(values)
            if document_id is not None:
                by_id = self.documents.get_by_id(document_id)
                if by_id is not None:
                    if self._same_web_request(by_id, candidate):
                        return DocumentOperationResult(
                            DocumentOperationStatus.IDENTICAL,
                            by_id,
                            "An identical web Document already exists.",
                        )
                    return DocumentOperationResult(
                        DocumentOperationStatus.CONFLICT,
                        by_id,
                        "The document_id already contains different metadata.",
                    )
            matches = self.documents.find_web_identity(source_id, web.url_normalized)
            if len(matches) > 1:
                return DocumentOperationResult(
                    DocumentOperationStatus.CONFLICT,
                    message="The destination contains duplicate web Document identities.",
                )
            if matches:
                existing = matches[0]
                status = (
                    DocumentOperationStatus.IDENTICAL
                    if self._same_web_request(existing, candidate)
                    else DocumentOperationStatus.CONFLICT
                )
                return DocumentOperationResult(
                    status,
                    existing,
                    (
                        "An identical web Document already exists."
                        if status == DocumentOperationStatus.IDENTICAL
                        else "This Source already has the URL with different metadata."
                    ),
                )
            self.documents.ensure_indexes()
            try:
                stored = self.documents.insert(candidate)
            except SourceDocumentRepositoryConflictError:
                concurrent = self.documents.find_web_identity(source_id, web.url_normalized)
                if len(concurrent) == 1 and self._same_web_request(concurrent[0], candidate):
                    return DocumentOperationResult(
                        DocumentOperationStatus.IDENTICAL,
                        concurrent[0],
                        "A concurrent identical web Document was retained.",
                    )
                return DocumentOperationResult(
                    DocumentOperationStatus.CONFLICT,
                    message="Concurrent web Document metadata conflicted.",
                )
        except (ValidationError, ValueError) as exc:
            return DocumentOperationResult(DocumentOperationStatus.ERROR, message=str(exc))
        except Exception:
            return DocumentOperationResult(
                DocumentOperationStatus.ERROR,
                message="Unexpected database error.",
            )
        return DocumentOperationResult(
            DocumentOperationStatus.CREATED,
            stored,
            "Web Document created.",
            metadata_persisted=True,
        )

    def list_source_documents(
        self,
        source_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        status: DocumentStatus | str | None = None,
        kind: DocumentKind | str | None = None,
    ) -> SourceDocumentPage:
        return self.documents.list(
            source_id,
            page=page,
            page_size=page_size,
            status=status,
            kind=kind,
        )

    def update_document_metadata(
        self,
        document_id: str,
        changes: Mapping[str, Any],
    ) -> DocumentOperationResult:
        current = self.documents.get_by_id(document_id)
        if current is None:
            return DocumentOperationResult(DocumentOperationStatus.NOT_FOUND, message="Not found.")
        try:
            if "reference_id" in changes:
                self._reference(changes.get("reference_id"), current.source_id)
            updated = self.documents.update_metadata(document_id, changes)
        except (ValidationError, ValueError) as exc:
            return DocumentOperationResult(DocumentOperationStatus.ERROR, current, str(exc))
        except SourceDocumentRepositoryConflictError as exc:
            return DocumentOperationResult(DocumentOperationStatus.CONFLICT, current, str(exc))
        except Exception:
            return DocumentOperationResult(
                DocumentOperationStatus.ERROR,
                current,
                "Unexpected database error.",
            )
        if updated is None:
            return DocumentOperationResult(DocumentOperationStatus.NOT_FOUND, message="Not found.")
        return DocumentOperationResult(
            DocumentOperationStatus.SUCCESS,
            updated,
            "Document metadata updated.",
            metadata_persisted=True,
        )

    def archive_document(self, document_id: str) -> DocumentOperationResult:
        return self._change_status(document_id, archive=True)

    def reactivate_document(self, document_id: str) -> DocumentOperationResult:
        return self._change_status(document_id, archive=False)

    def _change_status(self, document_id: str, *, archive: bool) -> DocumentOperationResult:
        current = self.documents.get_by_id(document_id)
        if current is None:
            return DocumentOperationResult(DocumentOperationStatus.NOT_FOUND, message="Not found.")
        already_matches = (
            current.status == DocumentStatus.ARCHIVED
            if archive
            else current.status == DocumentStatus.ACTIVE
        )
        if already_matches:
            return DocumentOperationResult(
                DocumentOperationStatus.IDENTICAL,
                current,
                "Document status already matched.",
            )
        try:
            value = (
                self.documents.archive(document_id)
                if archive
                else self.documents.reactivate(document_id)
            )
        except Exception:
            return DocumentOperationResult(
                DocumentOperationStatus.ERROR,
                current,
                "Unexpected database error.",
            )
        if value is None:
            return DocumentOperationResult(DocumentOperationStatus.NOT_FOUND, message="Not found.")
        return DocumentOperationResult(
            DocumentOperationStatus.SUCCESS,
            value,
            "Document status updated.",
            metadata_persisted=True,
        )

    def inspect_document_integrity(self, document_id: str) -> DocumentIntegrityInspection:
        issues: list[str] = []
        try:
            document = self.documents.get_by_id(document_id)
        except Exception:
            return DocumentIntegrityInspection(document_id, False, ("metadata_invalid",))
        if document is None:
            return DocumentIntegrityInspection(document_id, False, ("document_missing",))
        try:
            if self._source(document.source_id) is None:
                issues.append("source_missing")
        except Exception:
            issues.append("source_invalid")
        if document.reference_id is not None:
            try:
                self._reference(document.reference_id, document.source_id)
            except ValueError as exc:
                issues.append(
                    "reference_missing"
                    if "does not exist" in str(exc)
                    else "reference_not_associated"
                )
            except Exception:
                issues.append("reference_invalid")
        if document.kind == DocumentKind.PDF and document.pdf is not None:
            blob = self.storage.inspect_version(document.pdf.current_version)
            issues.extend(blob.issues)
        elif document.kind == DocumentKind.WEB and document.web is not None:
            try:
                if normalize_web_url(document.web.url_raw) != document.web.url_normalized:
                    issues.append("web_url_not_canonical")
            except ValueError:
                issues.append("web_url_invalid")
        else:
            issues.append("kind_payload_mismatch")
        return DocumentIntegrityInspection(document_id, not issues, tuple(dict.fromkeys(issues)))

    def read_pdf_document(self, document_id: str) -> DocumentPdfPayload:
        document = self.documents.get_by_id(document_id)
        if document is None:
            raise FileNotFoundError("Source PDF Document metadata was not found")
        if document.kind != DocumentKind.PDF or document.pdf is None:
            raise ValueError("Selected Source Document is not a PDF")
        version = document.pdf.current_version
        data = self.storage.read_version(version)
        return DocumentPdfPayload(
            document,
            data,
            version.original_filename,
            version.sha256,
        )


__all__ = [
    "DocumentIntegrityInspection",
    "DocumentOperationResult",
    "DocumentOperationStatus",
    "DocumentPdfPayload",
    "SourceDocumentService",
]

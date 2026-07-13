"""Application service for persistent Source Document reading state."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from enum import Enum
from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import ValidationError

from mathmongo.reading_space.errors import ReadingSpaceIndexConflictError
from mathmongo.reading_space.errors import ReadingStateConflictError
from mathmongo.reading_space.errors import ReadingStateRepositoryError
from mathmongo.reading_space.indexes import ReadingSpaceIndexManager
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.reading_space.models import ReadingDocumentFilters
from mathmongo.reading_space.models import ReadingStatus
from mathmongo.reading_space.models import utc_now
from mathmongo.reading_space.models import validate_user_scope
from mathmongo.reading_space.repository import ReadableDocumentItem
from mathmongo.reading_space.repository import ReadableDocumentPage
from mathmongo.reading_space.repository import ReadableDocumentRepository
from mathmongo.reading_space.repository import ReadingStateRepository
from mathmongo.reading_space.repository import SourceSummaryCounts
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.repository import SourceDocumentRepository
from mathmongo.source_documents.service import DocumentIntegrityInspection
from mathmongo.source_documents.service import DocumentPdfPayload
from mathmongo.source_documents.service import SourceDocumentService

T = TypeVar("T")


class ReadingOperationStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ARCHIVED = "archived"
    INTEGRITY_ERROR = "integrity_error"
    INVALID_STATE = "invalid_state"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ReadingServiceResult(Generic[T]):
    status: ReadingOperationStatus
    value: T | None = None
    message: str = ""

    @property
    def completed(self) -> bool:
        return self.status == ReadingOperationStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class ReaderContext:
    document: SourceDocument
    source: Source
    reference: Reference | None
    reading_state: DocumentReadingState | None
    effective_status: ReadingStatus
    pdf_payload: DocumentPdfPayload | None = None
    integrity: DocumentIntegrityInspection | None = None
    openable: bool = True


@dataclass(frozen=True, slots=True)
class RecentDocumentItem:
    document: SourceDocument
    state: DocumentReadingState
    source: Source
    reference: Reference | None
    openable: bool

    @property
    def archived(self) -> bool:
        return self.document.status == DocumentStatus.ARCHIVED


@dataclass(frozen=True, slots=True)
class RecentDocumentPage:
    items: tuple[RecentDocumentItem, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


@dataclass(frozen=True, slots=True)
class SourceReadingSummary:
    source: Source
    total_documents: int
    pdf_documents: int
    web_documents: int
    unread: int
    in_progress: int
    completed: int
    deferred: int
    last_opened_at: datetime | None


class ReadingSpaceService:
    """Coordinate S2 Documents with isolated, explicitly indexed reading state."""

    def __init__(
        self,
        database: Any,
        *,
        states: ReadingStateRepository | None = None,
        readable_documents: ReadableDocumentRepository | None = None,
        documents: SourceDocumentRepository | None = None,
        document_service: SourceDocumentService | None = None,
        sources: SourceRepository | None = None,
        references: ReferenceRepository | None = None,
        index_manager: ReadingSpaceIndexManager | None = None,
    ) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReadingSpaceService requires an explicit database")
        self.database = database
        self.states = states if states is not None else ReadingStateRepository(database)
        self.readable_documents = (
            readable_documents
            if readable_documents is not None
            else ReadableDocumentRepository(database)
        )
        self.documents = documents if documents is not None else SourceDocumentRepository(database)
        self.sources = sources if sources is not None else SourceRepository(database)
        self.references = references if references is not None else ReferenceRepository(database)
        self.document_service = (
            document_service
            if document_service is not None
            else SourceDocumentService(
                database,
                documents=self.documents,
                sources=self.sources,
                references=self.references,
            )
        )
        self.index_manager = (
            index_manager if index_manager is not None else ReadingSpaceIndexManager(database)
        )

    def _write_gate(self) -> ReadingServiceResult[None] | None:
        try:
            plan = self.index_manager.plan()
        except ReadingSpaceIndexConflictError as exc:
            return ReadingServiceResult(ReadingOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not inspect Reading Space indexes.",
            )
        if plan.conflicts:
            return ReadingServiceResult(
                ReadingOperationStatus.CONFLICT,
                message="Reading Space index definitions conflict with the approved plan.",
            )
        if plan.missing:
            return ReadingServiceResult(
                ReadingOperationStatus.INVALID_STATE,
                message="Initialize the approved Reading Space indexes before writing.",
            )
        return None

    def _catalog_context(
        self,
        document: SourceDocument,
    ) -> ReadingServiceResult[tuple[Source, Reference | None]]:
        try:
            source = self.sources.get_by_id(document.source_id)
            if source is None:
                return ReadingServiceResult(
                    ReadingOperationStatus.NOT_FOUND,
                    message="The Source associated with this Document does not exist.",
                )
            reference: Reference | None = None
            if document.reference_id is not None:
                reference = self.references.get_by_id(document.reference_id)
                if reference is None:
                    return ReadingServiceResult(
                        ReadingOperationStatus.INVALID_STATE,
                        message="The Reference associated with this Document does not exist.",
                    )
                if document.source_id not in reference.source_ids:
                    return ReadingServiceResult(
                        ReadingOperationStatus.CONFLICT,
                        message="The Document Reference is not associated with its Source.",
                    )
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not validate the Document catalog associations.",
            )
        return ReadingServiceResult(ReadingOperationStatus.SUCCESS, (source, reference))

    def _document_context(
        self,
        document_id: str,
        *,
        user_scope: str,
        strict_state_association: bool,
    ) -> ReadingServiceResult[ReaderContext]:
        try:
            scope = validate_user_scope(user_scope)
            document = self.documents.get_by_id(document_id)
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not load the Source Document.",
            )
        if document is None:
            return ReadingServiceResult(
                ReadingOperationStatus.NOT_FOUND,
                message="Source Document not found.",
            )
        catalog = self._catalog_context(document)
        if not catalog.completed or catalog.value is None:
            return ReadingServiceResult(catalog.status, message=catalog.message)
        source, reference = catalog.value
        try:
            state = self.states.get_by_document(document_id, user_scope=scope)
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not load the Document reading state.",
            )
        if state is not None:
            if state.source_id != document.source_id:
                return ReadingServiceResult(
                    ReadingOperationStatus.CONFLICT,
                    message="Reading state source_id does not match the Source Document.",
                )
            if (
                strict_state_association
                and state.reference_id is not None
                and state.reference_id != document.reference_id
            ):
                return ReadingServiceResult(
                    ReadingOperationStatus.CONFLICT,
                    message="Reading state reference_id does not match the Source Document.",
                )
        context = ReaderContext(
            document=document,
            source=source,
            reference=reference,
            reading_state=state,
            effective_status=state.status if state is not None else ReadingStatus.UNREAD,
            openable=document.status == DocumentStatus.ACTIVE,
        )
        if document.status == DocumentStatus.ARCHIVED:
            return ReadingServiceResult(
                ReadingOperationStatus.ARCHIVED,
                context,
                "Archived Documents cannot be opened normally.",
            )
        return ReadingServiceResult(ReadingOperationStatus.SUCCESS, context)

    def get_reader_context(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[ReaderContext]:
        """Return metadata-only reader context without loading PDF bytes or writing state."""
        return self._document_context(
            document_id,
            user_scope=user_scope,
            strict_state_association=True,
        )

    def open_document(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[ReaderContext]:
        gate = self._write_gate()
        if gate is not None:
            return ReadingServiceResult(gate.status, message=gate.message)
        base = self._document_context(
            document_id,
            user_scope=user_scope,
            strict_state_association=False,
        )
        if not base.completed or base.value is None:
            return base
        context = base.value
        inspection: DocumentIntegrityInspection | None = None
        pdf_payload: DocumentPdfPayload | None = None
        if context.document.kind == DocumentKind.PDF:
            try:
                inspection = self.document_service.inspect_document_integrity(document_id)
                if not inspection.ok:
                    return ReadingServiceResult(
                        ReadingOperationStatus.INTEGRITY_ERROR,
                        replace(context, integrity=inspection, openable=False),
                        "PDF integrity verification failed.",
                    )
                pdf_payload = self.document_service.read_pdf_document(document_id)
            except Exception:
                return ReadingServiceResult(
                    ReadingOperationStatus.INTEGRITY_ERROR,
                    message="The verified PDF blob could not be read safely.",
                )
        try:
            state = self.states.mark_opened(
                document_id=document_id,
                source_id=context.document.source_id,
                reference_id=context.document.reference_id,
                user_scope=user_scope,
            )
        except ReadingStateConflictError as exc:
            return ReadingServiceResult(ReadingOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingStateRepositoryError:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not persist the Document opening.",
            )
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Unexpected reading-state persistence error.",
            )
        return ReadingServiceResult(
            ReadingOperationStatus.SUCCESS,
            ReaderContext(
                document=context.document,
                source=context.source,
                reference=context.reference,
                reading_state=state,
                effective_status=state.status,
                pdf_payload=pdf_payload,
                integrity=inspection,
                openable=True,
            ),
            "Document opened.",
        )

    def list_readable_documents(
        self,
        *,
        filters: ReadingDocumentFilters | dict[str, Any] | None = None,
        user_scope: str = "local",
        page: int = 1,
        page_size: int = 50,
    ) -> ReadingServiceResult[ReadableDocumentPage]:
        try:
            result = self.readable_documents.list(
                filters=filters,
                user_scope=user_scope,
                page=page,
                page_size=page_size,
            )
            source_cache: dict[str, Source | None] = {}
            reference_cache: dict[str, Reference | None] = {}
            enriched: list[ReadableDocumentItem] = []
            for item in result.items:
                document = item.document
                if document.source_id not in source_cache:
                    source_cache[document.source_id] = self.sources.get_by_id(document.source_id)
                reference = None
                if document.reference_id is not None:
                    if document.reference_id not in reference_cache:
                        reference_cache[document.reference_id] = self.references.get_by_id(
                            document.reference_id
                        )
                    reference = reference_cache[document.reference_id]
                enriched.append(
                    ReadableDocumentItem(
                        document=document,
                        state=item.state,
                        source=source_cache[document.source_id],
                        reference=reference,
                    )
                )
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not list readable Documents.",
            )
        return ReadingServiceResult(
            ReadingOperationStatus.SUCCESS,
            ReadableDocumentPage(tuple(enriched), result.page, result.page_size, result.total),
        )

    def list_recent_documents(
        self,
        *,
        user_scope: str = "local",
        page: int = 1,
        page_size: int = 20,
    ) -> ReadingServiceResult[RecentDocumentPage]:
        try:
            documents_page = self.readable_documents.list_recent(
                user_scope=user_scope,
                page=page,
                page_size=page_size,
            )
            items: list[RecentDocumentItem] = []
            for item in documents_page.items:
                document = item.document
                state = item.state
                if state is None:
                    continue
                catalog = self._catalog_context(document)
                if not catalog.completed or catalog.value is None:
                    continue
                source, reference = catalog.value
                items.append(
                    RecentDocumentItem(
                        document=document,
                        state=state,
                        source=source,
                        reference=reference,
                        openable=document.status == DocumentStatus.ACTIVE,
                    )
                )
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not list recent Documents.",
            )
        return ReadingServiceResult(
            ReadingOperationStatus.SUCCESS,
            RecentDocumentPage(
                tuple(items),
                documents_page.page,
                documents_page.page_size,
                documents_page.total,
            ),
        )

    def _active_document_for_update(
        self,
        document_id: str,
        *,
        user_scope: str,
    ) -> ReadingServiceResult[ReaderContext]:
        gate = self._write_gate()
        if gate is not None:
            return ReadingServiceResult(gate.status, message=gate.message)
        return self._document_context(
            document_id,
            user_scope=user_scope,
            strict_state_association=True,
        )

    def update_current_page(
        self,
        document_id: str,
        current_page: int,
        *,
        user_scope: str = "local",
        total_pages: int | None = None,
    ) -> ReadingServiceResult[DocumentReadingState]:
        context = self._active_document_for_update(document_id, user_scope=user_scope)
        if not context.completed:
            return ReadingServiceResult(context.status, message=context.message)
        if context.value is None or context.value.document.kind != DocumentKind.PDF:
            return ReadingServiceResult(
                ReadingOperationStatus.INVALID_STATE,
                message="Current page is available only for PDF Documents.",
            )
        try:
            state = self.states.update_current_page(
                document_id,
                current_page,
                user_scope=user_scope,
                total_pages=total_pages,
            )
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingStateConflictError as exc:
            return ReadingServiceResult(ReadingOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not update the current page.",
            )
        if state is None:
            assert context.value is not None
            document = context.value.document
            try:
                state = self.states.upsert_for_document(
                    DocumentReadingState(
                        document_id=document.document_id,
                        source_id=document.source_id,
                        reference_id=document.reference_id,
                        user_scope=user_scope,
                        status=ReadingStatus.IN_PROGRESS,
                        current_page=current_page,
                        total_pages=total_pages,
                    )
                )
            except (ValidationError, ValueError) as exc:
                return ReadingServiceResult(
                    ReadingOperationStatus.INVALID_STATE,
                    message=str(exc),
                )
            except ReadingStateConflictError as exc:
                return ReadingServiceResult(ReadingOperationStatus.CONFLICT, message=str(exc))
            except Exception:
                return ReadingServiceResult(
                    ReadingOperationStatus.ERROR,
                    message="Could not create the current-page reading state.",
                )
        return ReadingServiceResult(ReadingOperationStatus.SUCCESS, state, "Current page saved.")

    def update_status(
        self,
        document_id: str,
        status: ReadingStatus | str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[DocumentReadingState]:
        context = self._active_document_for_update(document_id, user_scope=user_scope)
        if not context.completed:
            return ReadingServiceResult(context.status, message=context.message)
        try:
            next_status = ReadingStatus(status)
            state = self.states.update_status(
                document_id,
                next_status,
                user_scope=user_scope,
            )
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingStateConflictError as exc:
            return ReadingServiceResult(ReadingOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not update the reading status.",
            )
        if state is None:
            assert context.value is not None
            document = context.value.document
            timestamp = utc_now()
            try:
                state = self.states.upsert_for_document(
                    DocumentReadingState(
                        document_id=document.document_id,
                        source_id=document.source_id,
                        reference_id=document.reference_id,
                        user_scope=user_scope,
                        status=next_status,
                        completed_at=(
                            timestamp if next_status == ReadingStatus.COMPLETED else None
                        ),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            except (ValidationError, ValueError) as exc:
                return ReadingServiceResult(
                    ReadingOperationStatus.INVALID_STATE,
                    message=str(exc),
                )
            except ReadingStateConflictError as exc:
                return ReadingServiceResult(ReadingOperationStatus.CONFLICT, message=str(exc))
            except Exception:
                return ReadingServiceResult(
                    ReadingOperationStatus.ERROR,
                    message="Could not create the reading status.",
                )
        return ReadingServiceResult(ReadingOperationStatus.SUCCESS, state, "Reading status saved.")

    def mark_completed(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[DocumentReadingState]:
        return self.update_status(document_id, ReadingStatus.COMPLETED, user_scope=user_scope)

    def mark_deferred(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[DocumentReadingState]:
        return self.update_status(document_id, ReadingStatus.DEFERRED, user_scope=user_scope)

    def reset_reading_state(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[None]:
        gate = self._write_gate()
        if gate is not None:
            return ReadingServiceResult(gate.status, message=gate.message)
        try:
            validate_user_scope(user_scope)
            document = self.documents.get_by_id(document_id)
            if document is None:
                return ReadingServiceResult(
                    ReadingOperationStatus.NOT_FOUND,
                    message="Source Document not found.",
                )
            self.states.clear_state_for_document(document_id, user_scope=user_scope)
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not reset the reading state.",
            )
        return ReadingServiceResult(
            ReadingOperationStatus.SUCCESS,
            message="Reading state reset to unread.",
        )

    def get_source_reading_summary(
        self,
        source_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[SourceReadingSummary]:
        try:
            source = self.sources.get_by_id(source_id)
            if source is None:
                return ReadingServiceResult(
                    ReadingOperationStatus.NOT_FOUND,
                    message="Source not found.",
                )
            counts: SourceSummaryCounts = self.readable_documents.source_summary(
                source_id,
                user_scope=user_scope,
            )
        except (ValidationError, ValueError) as exc:
            return ReadingServiceResult(ReadingOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return ReadingServiceResult(
                ReadingOperationStatus.ERROR,
                message="Could not calculate the Source reading summary.",
            )
        return ReadingServiceResult(
            ReadingOperationStatus.SUCCESS,
            SourceReadingSummary(
                source=source,
                total_documents=counts.total_documents,
                pdf_documents=counts.pdf_documents,
                web_documents=counts.web_documents,
                unread=counts.unread,
                in_progress=counts.in_progress,
                completed=counts.completed,
                deferred=counts.deferred,
                last_opened_at=counts.last_opened_at,
            ),
        )


__all__ = [
    "ReaderContext",
    "ReadingOperationStatus",
    "ReadingServiceResult",
    "ReadingSpaceService",
    "RecentDocumentItem",
    "RecentDocumentPage",
    "SourceReadingSummary",
]

"""Validated application service for S4 reading annotations and evidence."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import ValidationError

from mathmongo.reading_annotations.errors import ReadingAnnotationConflictError
from mathmongo.reading_annotations.errors import ReadingAnnotationIndexConflictError
from mathmongo.reading_annotations.errors import ReadingAnnotationRepositoryError
from mathmongo.reading_annotations.indexes import LEGACY_READING_ANNOTATION_INDEXES
from mathmongo.reading_annotations.indexes import READING_ANNOTATION_INDEXES
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
from mathmongo.reading_annotations.models import VISUAL_ANNOTATION_COLORS
from mathmongo.reading_annotations.models import AnnotationKind
from mathmongo.reading_annotations.models import AnnotationStatus
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import EvidenceLinkType
from mathmongo.reading_annotations.models import NormalizedVisualRect
from mathmongo.reading_annotations.models import ReadingNote
from mathmongo.reading_annotations.models import ReadingNoteStatus
from mathmongo.reading_annotations.models import ReadingNoteType
from mathmongo.reading_annotations.models import VisualAnnotationAnchor
from mathmongo.reading_annotations.models import normalize_visual_quote_text
from mathmongo.reading_annotations.models import validate_annotation_id
from mathmongo.reading_annotations.models import validate_evidence_link_id
from mathmongo.reading_annotations.models import visual_text_sha256
from mathmongo.reading_annotations.repository import AnnotationPage
from mathmongo.reading_annotations.repository import AnnotationRepository
from mathmongo.reading_annotations.repository import ConceptEvidencePage
from mathmongo.reading_annotations.repository import ConceptEvidenceRepository
from mathmongo.reading_annotations.repository import ReadingNotePage
from mathmongo.reading_annotations.repository import ReadingNoteRepository
from mathmongo.reading_space.repository import ReadingStateRepository
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.repository import SourceDocumentRepository
from mathmongo.source_documents.service import SourceDocumentService

T = TypeVar("T")


class ReadingAnnotationOperationStatus(str, Enum):
    SUCCESS = "success"
    IDENTICAL = "identical"
    NOT_FOUND = "not_found"
    ARCHIVED = "archived"
    INVALID_STATE = "invalid_state"
    CONFLICT = "conflict"
    BLOCKED = "blocked"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ReadingAnnotationServiceResult(Generic[T]):
    status: ReadingAnnotationOperationStatus
    value: T | None = None
    message: str = ""

    @property
    def completed(self) -> bool:
        return self.status in {
            ReadingAnnotationOperationStatus.SUCCESS,
            ReadingAnnotationOperationStatus.IDENTICAL,
        }


class ReadingAnnotationService:
    """Coordinate S4 writes without mutating S1, S2, S3, or legacy concepts."""

    def __init__(
        self,
        database: Any,
        *,
        annotations: AnnotationRepository | None = None,
        notes: ReadingNoteRepository | None = None,
        evidence: ConceptEvidenceRepository | None = None,
        documents: SourceDocumentRepository | None = None,
        sources: SourceRepository | None = None,
        references: ReferenceRepository | None = None,
        index_manager: ReadingAnnotationIndexManager | None = None,
        document_service: SourceDocumentService | None = None,
        reading_states: ReadingStateRepository | None = None,
    ) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReadingAnnotationService requires an explicit database")
        self.database = database
        self.annotations = annotations or AnnotationRepository(database)
        self.notes = notes or ReadingNoteRepository(database)
        self.evidence = evidence or ConceptEvidenceRepository(database)
        self.documents = documents or SourceDocumentRepository(database)
        self.sources = sources or SourceRepository(database)
        self.references = references or ReferenceRepository(database)
        self.index_manager = index_manager or ReadingAnnotationIndexManager(database)
        self.reading_states = reading_states or ReadingStateRepository(database)
        # Keep the S4 service constructor filesystem-lazy. Advanced Reader injects its
        # existing S2 service; other callers only construct one when a visual write
        # actually requires blob-integrity inspection.
        self.document_service = document_service

    @staticmethod
    def _result(
        status: ReadingAnnotationOperationStatus,
        value: T | None = None,
        message: str = "",
    ) -> ReadingAnnotationServiceResult[T]:
        return ReadingAnnotationServiceResult(status, value, message)

    def _write_gate(
        self,
        *,
        visual: bool = False,
    ) -> ReadingAnnotationServiceResult[None] | None:
        try:
            plan = self.index_manager.plan()
        except ReadingAnnotationIndexConflictError as exc:
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not inspect Notes & Evidence indexes.",
            )
        required = READING_ANNOTATION_INDEXES if visual else LEGACY_READING_ANNOTATION_INDEXES
        required_identities = {(item.collection, item.name) for item in required}
        conflicts = tuple(
            item
            for item in plan.conflicts
            if (item.spec.collection, item.spec.name) in required_identities
        )
        missing = tuple(
            item for item in plan.missing if (item.collection, item.name) in required_identities
        )
        if conflicts:
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                message="Notes & Evidence index definitions conflict with the approved plan.",
            )
        if missing:
            return self._result(
                ReadingAnnotationOperationStatus.INVALID_STATE,
                message="Initialize the approved Notes & Evidence indexes before writing.",
            )
        return None

    def visual_indexes_ready(self) -> bool:
        """Inspect the full S5B index plan without installing anything."""
        try:
            return self.index_manager.plan().initialized
        except Exception:
            return False

    def _source(self, source_id: str) -> ReadingAnnotationServiceResult[Source]:
        try:
            source = self.sources.get_by_id(source_id)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not validate the Source.",
            )
        if source is None:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND,
                message="Source not found.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, source)

    def _document(
        self,
        document_id: str,
        *,
        require_active: bool,
    ) -> ReadingAnnotationServiceResult[SourceDocument]:
        try:
            document = self.documents.get_by_id(document_id)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not load the Source Document.",
            )
        if document is None:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND,
                message="Source Document not found.",
            )
        source = self._source(document.source_id)
        if not source.completed:
            return self._result(source.status, message=source.message)
        reference = self._reference(document.source_id, document.reference_id)
        if not reference.completed:
            return self._result(reference.status, message=reference.message)
        if require_active and document.status == DocumentStatus.ARCHIVED:
            return self._result(
                ReadingAnnotationOperationStatus.ARCHIVED,
                document,
                "Archived Documents cannot receive new reading work.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, document)

    def _reference(
        self,
        source_id: str,
        reference_id: str | None,
    ) -> ReadingAnnotationServiceResult[Reference | None]:
        if reference_id is None:
            return self._result(ReadingAnnotationOperationStatus.SUCCESS, None)
        try:
            reference = self.references.get_by_id(reference_id)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not validate the Reference.",
            )
        if reference is None:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND,
                message="Reference not found.",
            )
        if source_id not in reference.source_ids:
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                message="Reference is not associated with the selected Source.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, reference)

    def _annotation_associations(
        self,
        annotation: DocumentAnnotation,
        *,
        require_active_document: bool,
    ) -> ReadingAnnotationServiceResult[SourceDocument]:
        document = self._document(
            annotation.document_id,
            require_active=require_active_document,
        )
        if not document.completed or document.value is None:
            return self._result(document.status, document.value, document.message)
        if document.value.source_id != annotation.source_id:
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                message="Annotation Source does not match its Source Document.",
            )
        if annotation.reference_id not in {None, document.value.reference_id}:
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                message="Annotation Reference does not match its Source Document.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, document.value)

    def _note_associations(
        self,
        *,
        source_id: str,
        document_id: str | None,
        reference_id: str | None,
        require_active_document: bool,
    ) -> ReadingAnnotationServiceResult[SourceDocument | None]:
        source = self._source(source_id)
        if not source.completed:
            return self._result(source.status, message=source.message)
        document_value: SourceDocument | None = None
        if document_id is not None:
            document = self._document(
                document_id,
                require_active=require_active_document,
            )
            if not document.completed or document.value is None:
                return self._result(document.status, document.value, document.message)
            if document.value.source_id != source_id:
                return self._result(
                    ReadingAnnotationOperationStatus.CONFLICT,
                    message="Reading Note Source does not match the Source Document.",
                )
            document_value = document.value
        reference = self._reference(source_id, reference_id)
        if not reference.completed:
            return self._result(reference.status, message=reference.message)
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, document_value)

    @staticmethod
    def _scope_is_local(user_scope: str) -> ReadingAnnotationServiceResult[None] | None:
        if user_scope != "local":
            return ReadingAnnotationServiceResult(
                ReadingAnnotationOperationStatus.INVALID_STATE,
                message="S4 currently supports only user_scope='local'.",
            )
        return None

    def create_annotation(
        self,
        document_id: str,
        *,
        kind: AnnotationKind | str,
        body: str = "",
        page_number: int | None = None,
        page_label: str | None = None,
        quote_text: str | None = None,
        color_label: str | None = None,
        tags: tuple[str, ...] | list[str] = (),
        reference_id: str | None = None,
        user_scope: str = "local",
        annotation_id: str | None = None,
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        gate = self._write_gate() or self._scope_is_local(user_scope)
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        document_result = self._document(document_id, require_active=True)
        if not document_result.completed or document_result.value is None:
            return self._result(
                document_result.status,
                document_result.value,
                document_result.message,
            )
        document = document_result.value
        if reference_id is not None and reference_id != document.reference_id:
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                message="Annotation Reference must match the Source Document or remain empty.",
            )
        reference = self._reference(document.source_id, reference_id)
        if not reference.completed:
            return self._result(reference.status, message=reference.message)
        values: dict[str, Any] = {
            "document_id": document.document_id,
            "source_id": document.source_id,
            "reference_id": reference_id,
            "user_scope": user_scope,
            "kind": kind,
            "page_number": page_number,
            "page_label": page_label,
            "quote_text": quote_text,
            "body": body,
            "color_label": color_label,
            "tags": list(tags),
        }
        if annotation_id is not None:
            values["annotation_id"] = annotation_id
        try:
            return self._result(
                ReadingAnnotationOperationStatus.SUCCESS,
                self.annotations.insert(DocumentAnnotation.model_validate(values)),
                "Annotation created.",
            )
        except ReadingAnnotationConflictError as exc:
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingAnnotationRepositoryError:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not persist the Annotation.",
            )
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Unexpected Annotation persistence error.",
            )

    def get_annotation(
        self,
        annotation_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        try:
            item = self.annotations.get_by_id(annotation_id)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not load the Annotation.",
            )
        if item is None or item.user_scope != user_scope:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND, message="Annotation not found."
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, item)

    def list_document_annotations(
        self,
        document_id: str,
        *,
        status: AnnotationStatus | str | None = AnnotationStatus.ACTIVE,
        kind: AnnotationKind | str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[AnnotationPage]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        context = self._document(document_id, require_active=False)
        if not context.completed:
            return self._result(context.status, message=context.message)
        try:
            value = (
                self.annotations.search(
                    search,
                    document_id=document_id,
                    user_scope=user_scope,
                    status=status,
                    kind=kind,
                    page=page,
                    page_size=page_size,
                )
                if search and search.strip()
                else self.annotations.list_by_document(
                    document_id,
                    user_scope=user_scope,
                    status=status,
                    kind=kind,
                    page=page,
                    page_size=page_size,
                )
            )
            return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not list Annotations."
            )

    def list_source_annotations(
        self,
        source_id: str,
        *,
        status: AnnotationStatus | str | None = AnnotationStatus.ACTIVE,
        kind: AnnotationKind | str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[AnnotationPage]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        source = self._source(source_id)
        if not source.completed:
            return self._result(source.status, message=source.message)
        try:
            value = (
                self.annotations.search(
                    search,
                    source_id=source_id,
                    user_scope=user_scope,
                    status=status,
                    kind=kind,
                    page=page,
                    page_size=page_size,
                )
                if search and search.strip()
                else self.annotations.list_by_source(
                    source_id,
                    user_scope=user_scope,
                    status=status,
                    kind=kind,
                    page=page,
                    page_size=page_size,
                )
            )
            return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not list Annotations."
            )

    def search_annotations(
        self, query: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[AnnotationPage]:
        scope = self._scope_is_local(str(kwargs.get("user_scope", "local")))
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        try:
            value = self.annotations.search(query, **kwargs)
            return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not search Annotations."
            )

    def update_annotation(
        self,
        annotation_id: str,
        *,
        kind: AnnotationKind | str,
        body: str,
        page_number: int | None = None,
        page_label: str | None = None,
        quote_text: str | None = None,
        color_label: str | None = None,
        tags: tuple[str, ...] | list[str] = (),
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        current = self.get_annotation(annotation_id, user_scope=user_scope)
        if not current.completed or current.value is None:
            return current
        if current.value.visual_anchor is not None:
            visual_gate = self._write_gate(visual=True)
            if visual_gate is not None:
                return self._result(visual_gate.status, message=visual_gate.message)
            return self._result(
                ReadingAnnotationOperationStatus.INVALID_STATE,
                current.value,
                "Visual Annotations require the presentation-only update operation.",
            )
        if current.value.status == AnnotationStatus.ARCHIVED:
            return self._result(
                ReadingAnnotationOperationStatus.ARCHIVED,
                current.value,
                "Archived Annotations cannot be edited.",
            )
        associations = self._annotation_associations(
            current.value,
            require_active_document=True,
        )
        if not associations.completed:
            return self._result(associations.status, message=associations.message)
        try:
            updated = self.annotations.update_content(
                annotation_id,
                kind=kind,
                page_number=page_number,
                page_label=page_label,
                quote_text=quote_text,
                body=body,
                color_label=color_label,
                tags=tags,
            )
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingAnnotationConflictError as exc:
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not update the Annotation."
            )
        if updated is None:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND, message="Annotation not found."
            )
        return self._result(
            ReadingAnnotationOperationStatus.SUCCESS, updated, "Annotation updated."
        )

    def _annotation_lifecycle(
        self,
        annotation_id: str,
        *,
        reactivate: bool,
        user_scope: str,
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        current = self.get_annotation(annotation_id, user_scope=user_scope)
        if not current.completed or current.value is None:
            return current
        if current.value.visual_anchor is not None:
            visual_gate = self._write_gate(visual=True)
            if visual_gate is not None:
                return self._result(visual_gate.status, message=visual_gate.message)
        if reactivate:
            associations = self._annotation_associations(
                current.value,
                require_active_document=True,
            )
            if not associations.completed:
                return self._result(associations.status, message=associations.message)
        try:
            value = (
                self.annotations.reactivate(annotation_id)
                if reactivate
                else self.annotations.archive(annotation_id)
            )
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not update Annotation status.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)

    def archive_annotation(
        self, annotation_id: str, *, user_scope: str = "local"
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        return self._annotation_lifecycle(annotation_id, reactivate=False, user_scope=user_scope)

    def reactivate_annotation(
        self, annotation_id: str, *, user_scope: str = "local"
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        return self._annotation_lifecycle(annotation_id, reactivate=True, user_scope=user_scope)

    def _validated_visual_document(
        self,
        document_id: str,
        *,
        version_id: str,
        document_sha256: str,
        pdf_page: int,
        user_scope: str,
    ) -> ReadingAnnotationServiceResult[SourceDocument]:
        document_result = self._document(document_id, require_active=True)
        if not document_result.completed or document_result.value is None:
            return self._result(
                document_result.status,
                document_result.value,
                document_result.message,
            )
        document = document_result.value
        if document.kind != DocumentKind.PDF or document.pdf is None:
            return self._result(
                ReadingAnnotationOperationStatus.INVALID_STATE,
                message="Visual annotations require a PDF Source Document.",
            )
        current_version = document.pdf.current_version
        if current_version.version_id != version_id:
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                message="The visual annotation version is not the current PDF version.",
            )
        if current_version.sha256 != document_sha256:
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                message="The visual annotation SHA does not match the current PDF version.",
            )
        try:
            reading_state = self.reading_states.get_by_document(
                document_id,
                user_scope=user_scope,
            )
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not validate the persisted PDF page range.",
            )
        if (
            reading_state is not None
            and reading_state.total_pages is not None
            and pdf_page > reading_state.total_pages
        ):
            return self._result(
                ReadingAnnotationOperationStatus.INVALID_STATE,
                message="pdf_page exceeds the persisted PDF total_pages.",
            )
        try:
            document_service = self.document_service
            if document_service is None:
                document_service = SourceDocumentService(
                    self.database,
                    documents=self.documents,
                    sources=self.sources,
                    references=self.references,
                )
                self.document_service = document_service
            inspection = document_service.inspect_document_integrity(document_id)
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not validate Source PDF integrity.",
            )
        if not inspection.ok:
            return self._result(
                ReadingAnnotationOperationStatus.BLOCKED,
                message="Source PDF integrity validation failed.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, document)

    @staticmethod
    def _same_visual_create_request(
        existing: DocumentAnnotation,
        candidate: DocumentAnnotation,
    ) -> bool:
        fields = (
            "schema_version",
            "annotation_id",
            "document_id",
            "source_id",
            "reference_id",
            "user_scope",
            "kind",
            "page_number",
            "quote_text",
            "body",
            "color_label",
            "tags",
            "visual_anchor",
        )
        return all(getattr(existing, field) == getattr(candidate, field) for field in fields)

    def create_visual_annotation(
        self,
        *,
        annotation_id: str,
        document_id: str,
        version_id: str,
        document_sha256: str,
        pdf_page: int,
        kind: AnnotationKind | str,
        quote_text: str,
        rects: list[NormalizedVisualRect | Mapping[str, Any]]
        | tuple[NormalizedVisualRect | Mapping[str, Any], ...],
        capture_rotation: int,
        color_label: str = "yellow",
        body: str = "",
        tags: tuple[str, ...] | list[str] = (),
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        gate = self._write_gate(visual=True)
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        try:
            validate_annotation_id(annotation_id)
            normalized_quote = normalize_visual_quote_text(quote_text)
            anchor = VisualAnnotationAnchor(
                version_id=version_id,
                document_sha256=document_sha256,
                pdf_page=pdf_page,
                capture_rotation=capture_rotation,
                rects=rects,
                text_sha256=visual_text_sha256(normalized_quote),
            )
            if color_label not in VISUAL_ANNOTATION_COLORS:
                raise ValueError("color_label is not in the approved visual annotation palette")
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))

        document_result = self._validated_visual_document(
            document_id,
            version_id=anchor.version_id,
            document_sha256=anchor.document_sha256,
            pdf_page=anchor.pdf_page,
            user_scope=user_scope,
        )
        if not document_result.completed or document_result.value is None:
            return self._result(document_result.status, message=document_result.message)
        document = document_result.value
        try:
            candidate = DocumentAnnotation(
                schema_version=2,
                annotation_id=annotation_id,
                document_id=document.document_id,
                source_id=document.source_id,
                reference_id=document.reference_id,
                user_scope=user_scope,
                kind=kind,
                page_number=pdf_page,
                quote_text=normalized_quote,
                body=body,
                color_label=color_label,
                tags=list(tags),
                visual_anchor=anchor,
            )
            existing = self.annotations.get_by_id(annotation_id)
            if existing is not None:
                if self._same_visual_create_request(existing, candidate):
                    return self._result(
                        ReadingAnnotationOperationStatus.IDENTICAL,
                        existing,
                        "An identical visual Annotation already exists.",
                    )
                return self._result(
                    ReadingAnnotationOperationStatus.CONFLICT,
                    existing,
                    "The annotation_id already contains different content.",
                )
            stored = self.annotations.insert(candidate)
            return self._result(
                ReadingAnnotationOperationStatus.SUCCESS,
                stored,
                "Visual Annotation created.",
            )
        except ReadingAnnotationConflictError:
            try:
                concurrent = self.annotations.get_by_id(annotation_id)
            except Exception:
                concurrent = None
            if concurrent is not None and self._same_visual_create_request(concurrent, candidate):
                return self._result(
                    ReadingAnnotationOperationStatus.IDENTICAL,
                    concurrent,
                    "A concurrent identical visual Annotation was retained.",
                )
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                concurrent,
                "The annotation_id conflicts with persisted content.",
            )
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingAnnotationRepositoryError:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not persist the visual Annotation.",
            )
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Unexpected visual Annotation persistence error.",
            )

    def get_visual_annotation(
        self,
        annotation_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        try:
            item = self.annotations.get_visual_by_annotation_id(annotation_id)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not load the visual Annotation.",
            )
        if item is None or item.user_scope != user_scope:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND,
                message="Visual Annotation not found.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, item)

    def list_visual_annotations(
        self,
        document_id: str,
        *,
        pdf_page: int | None = None,
        status: AnnotationStatus | str | None = AnnotationStatus.ACTIVE,
        kind: AnnotationKind | str | None = None,
        page: int = 1,
        page_size: int = 50,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[AnnotationPage]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        context = self._document(document_id, require_active=False)
        if not context.completed:
            return self._result(context.status, message=context.message)
        try:
            value = (
                self.annotations.list_visual_by_page(
                    document_id,
                    pdf_page,
                    user_scope=user_scope,
                    status=status,
                    kind=kind,
                    page=page,
                    page_size=page_size,
                )
                if pdf_page is not None
                else self.annotations.list_visual_by_document(
                    document_id,
                    user_scope=user_scope,
                    status=status,
                    kind=kind,
                    page=page,
                    page_size=page_size,
                )
            )
            return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not list visual Annotations.",
            )

    def update_visual_annotation_presentation(
        self,
        annotation_id: str,
        *,
        kind: AnnotationKind | str,
        color_label: str,
        body: str,
        tags: tuple[str, ...] | list[str] = (),
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        gate = self._write_gate(visual=True)
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        current = self.get_visual_annotation(annotation_id, user_scope=user_scope)
        if not current.completed or current.value is None:
            return current
        if current.value.status == AnnotationStatus.ARCHIVED:
            return self._result(
                ReadingAnnotationOperationStatus.ARCHIVED,
                current.value,
                "Archived visual Annotations cannot be edited.",
            )
        associations = self._annotation_associations(
            current.value,
            require_active_document=True,
        )
        if not associations.completed:
            return self._result(associations.status, message=associations.message)
        try:
            if color_label not in VISUAL_ANNOTATION_COLORS:
                raise ValueError("color_label is not in the approved visual annotation palette")
            updated = self.annotations.update_visual_presentation(
                annotation_id,
                kind=kind,
                color_label=color_label,
                body=body,
                tags=tags,
            )
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingAnnotationConflictError as exc:
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not update the visual Annotation.",
            )
        if updated is None:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND,
                message="Visual Annotation not found.",
            )
        return self._result(
            ReadingAnnotationOperationStatus.SUCCESS,
            updated,
            "Visual Annotation updated.",
        )

    def _visual_annotation_lifecycle(
        self,
        annotation_id: str,
        *,
        reactivate: bool,
        user_scope: str,
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        gate = self._write_gate(visual=True)
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        current = self.get_visual_annotation(annotation_id, user_scope=user_scope)
        if not current.completed or current.value is None:
            return current
        if reactivate:
            associations = self._annotation_associations(
                current.value,
                require_active_document=True,
            )
            if not associations.completed:
                return self._result(associations.status, message=associations.message)
        try:
            value = (
                self.annotations.reactivate(annotation_id)
                if reactivate
                else self.annotations.archive(annotation_id)
            )
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not update visual Annotation status.",
            )
        if value is None:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND,
                message="Visual Annotation not found.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)

    def archive_visual_annotation(
        self,
        annotation_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        return self._visual_annotation_lifecycle(
            annotation_id,
            reactivate=False,
            user_scope=user_scope,
        )

    def reactivate_visual_annotation(
        self,
        annotation_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[DocumentAnnotation]:
        return self._visual_annotation_lifecycle(
            annotation_id,
            reactivate=True,
            user_scope=user_scope,
        )

    def create_note(
        self,
        *,
        source_id: str,
        title: str,
        body: str,
        note_type: ReadingNoteType | str = ReadingNoteType.GENERAL,
        document_id: str | None = None,
        reference_id: str | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
        tags: tuple[str, ...] | list[str] = (),
        user_scope: str = "local",
        note_id: str | None = None,
    ) -> ReadingAnnotationServiceResult[ReadingNote]:
        gate = self._write_gate() or self._scope_is_local(user_scope)
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        associations = self._note_associations(
            source_id=source_id,
            document_id=document_id,
            reference_id=reference_id,
            require_active_document=True,
        )
        if not associations.completed:
            return self._result(associations.status, message=associations.message)
        values: dict[str, Any] = {
            "document_id": document_id,
            "source_id": source_id,
            "reference_id": reference_id,
            "user_scope": user_scope,
            "title": title,
            "body": body,
            "note_type": note_type,
            "page_start": page_start,
            "page_end": page_end,
            "tags": list(tags),
        }
        if note_id is not None:
            values["note_id"] = note_id
        try:
            value = self.notes.insert(ReadingNote.model_validate(values))
            return self._result(
                ReadingAnnotationOperationStatus.SUCCESS, value, "Reading Note created."
            )
        except ReadingAnnotationConflictError as exc:
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not persist the Reading Note.",
            )

    def get_note(
        self, note_id: str, *, user_scope: str = "local"
    ) -> ReadingAnnotationServiceResult[ReadingNote]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        try:
            item = self.notes.get_by_id(note_id)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not load the Reading Note."
            )
        if item is None or item.user_scope != user_scope:
            return self._result(
                ReadingAnnotationOperationStatus.NOT_FOUND, message="Reading Note not found."
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, item)

    def _list_notes(
        self,
        *,
        document_id: str | None = None,
        source_id: str | None = None,
        status: ReadingNoteStatus | str | None,
        note_type: ReadingNoteType | str | None,
        search: str | None,
        page: int,
        page_size: int,
        user_scope: str,
        source_only: bool = False,
    ) -> ReadingAnnotationServiceResult[ReadingNotePage]:
        scope = self._scope_is_local(user_scope)
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        try:
            if search and search.strip():
                value = self.notes.search(
                    search,
                    document_id=document_id,
                    source_id=source_id,
                    user_scope=user_scope,
                    source_only=source_only,
                    status=status,
                    note_type=note_type,
                    page=page,
                    page_size=page_size,
                )
            elif document_id is not None:
                value = self.notes.list_by_document(
                    document_id,
                    user_scope=user_scope,
                    status=status,
                    note_type=note_type,
                    page=page,
                    page_size=page_size,
                )
            else:
                value = self.notes.list_by_source(
                    str(source_id),
                    user_scope=user_scope,
                    source_only=source_only,
                    status=status,
                    note_type=note_type,
                    page=page,
                    page_size=page_size,
                )
            return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not list Reading Notes."
            )

    def list_document_notes(
        self,
        document_id: str,
        *,
        status: ReadingNoteStatus | str | None = ReadingNoteStatus.ACTIVE,
        note_type: ReadingNoteType | str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[ReadingNotePage]:
        context = self._document(document_id, require_active=False)
        if not context.completed:
            return self._result(context.status, message=context.message)
        return self._list_notes(
            document_id=document_id,
            status=status,
            note_type=note_type,
            search=search,
            page=page,
            page_size=page_size,
            user_scope=user_scope,
        )

    def list_source_notes(
        self,
        source_id: str,
        *,
        status: ReadingNoteStatus | str | None = ReadingNoteStatus.ACTIVE,
        note_type: ReadingNoteType | str | None = None,
        search: str | None = None,
        source_only: bool = False,
        page: int = 1,
        page_size: int = 50,
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[ReadingNotePage]:
        source = self._source(source_id)
        if not source.completed:
            return self._result(source.status, message=source.message)
        return self._list_notes(
            source_id=source_id,
            source_only=source_only,
            status=status,
            note_type=note_type,
            search=search,
            page=page,
            page_size=page_size,
            user_scope=user_scope,
        )

    def search_notes(
        self, query: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ReadingNotePage]:
        scope = self._scope_is_local(str(kwargs.get("user_scope", "local")))
        if scope is not None:
            return self._result(scope.status, message=scope.message)
        try:
            return self._result(
                ReadingAnnotationOperationStatus.SUCCESS, self.notes.search(query, **kwargs)
            )
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not search Reading Notes."
            )

    def update_note(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        note_type: ReadingNoteType | str,
        document_id: str | None = None,
        reference_id: str | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
        tags: tuple[str, ...] | list[str] = (),
        user_scope: str = "local",
    ) -> ReadingAnnotationServiceResult[ReadingNote]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        current = self.get_note(note_id, user_scope=user_scope)
        if not current.completed or current.value is None:
            return current
        if current.value.status == ReadingNoteStatus.ARCHIVED:
            return self._result(
                ReadingAnnotationOperationStatus.ARCHIVED,
                current.value,
                "Archived Reading Notes cannot be edited.",
            )
        associations = self._note_associations(
            source_id=current.value.source_id,
            document_id=document_id,
            reference_id=reference_id,
            require_active_document=True,
        )
        if not associations.completed:
            return self._result(associations.status, message=associations.message)
        try:
            value = self.notes.update_content(
                note_id,
                title=title,
                body=body,
                note_type=note_type,
                document_id=document_id,
                page_start=page_start,
                page_end=page_end,
                reference_id=reference_id,
                tags=tags,
            )
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except ReadingAnnotationConflictError as exc:
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not update the Reading Note."
            )
        return self._result(
            ReadingAnnotationOperationStatus.SUCCESS, value, "Reading Note updated."
        )

    def _note_lifecycle(
        self, note_id: str, *, reactivate: bool, user_scope: str
    ) -> ReadingAnnotationServiceResult[ReadingNote]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        current = self.get_note(note_id, user_scope=user_scope)
        if not current.completed or current.value is None:
            return current
        if reactivate:
            associations = self._note_associations(
                source_id=current.value.source_id,
                document_id=current.value.document_id,
                reference_id=current.value.reference_id,
                require_active_document=True,
            )
            if not associations.completed:
                return self._result(associations.status, message=associations.message)
        try:
            value = self.notes.reactivate(note_id) if reactivate else self.notes.archive(note_id)
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not update Reading Note status.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)

    def archive_note(
        self, note_id: str, *, user_scope: str = "local"
    ) -> ReadingAnnotationServiceResult[ReadingNote]:
        return self._note_lifecycle(note_id, reactivate=False, user_scope=user_scope)

    def reactivate_note(
        self, note_id: str, *, user_scope: str = "local"
    ) -> ReadingAnnotationServiceResult[ReadingNote]:
        return self._note_lifecycle(note_id, reactivate=True, user_scope=user_scope)

    def _concept_exists(self, concept_id: str, concept_source: str) -> bool:
        """Read the immutable legacy composite identity with an exact query."""
        cursor = self.database["concepts"].find(
            {"id": concept_id, "source": concept_source},
            {"_id": 1},
        )
        if hasattr(cursor, "limit"):
            cursor = cursor.limit(2)
        return sum(1 for _item in cursor) == 1

    def _evidence_target(
        self,
        *,
        source_id: str,
        reference_id: str | None,
        document_id: str | None,
        annotation_id: str | None,
        note_id: str | None,
        page_number: int | None,
    ) -> ReadingAnnotationServiceResult[None]:
        reference = self._reference(source_id, reference_id)
        if not reference.completed:
            return self._result(reference.status, message=reference.message)
        if annotation_id is not None:
            annotation = self.get_annotation(annotation_id)
            if not annotation.completed or annotation.value is None:
                return self._result(
                    ReadingAnnotationOperationStatus.BLOCKED,
                    message="Evidence Annotation target does not exist.",
                )
            if annotation.value.status == AnnotationStatus.ARCHIVED:
                return self._result(
                    ReadingAnnotationOperationStatus.ARCHIVED,
                    message="Evidence Annotation target is archived.",
                )
            associations = self._annotation_associations(
                annotation.value,
                require_active_document=True,
            )
            if not associations.completed:
                return self._result(associations.status, message=associations.message)
            if annotation.value.source_id != source_id or reference_id not in {
                None,
                annotation.value.reference_id,
            }:
                return self._result(
                    ReadingAnnotationOperationStatus.CONFLICT,
                    message="Evidence associations do not match the Annotation.",
                )
        elif note_id is not None:
            note = self.get_note(note_id)
            if not note.completed or note.value is None:
                return self._result(
                    ReadingAnnotationOperationStatus.BLOCKED,
                    message="Evidence Reading Note target does not exist.",
                )
            if note.value.status == ReadingNoteStatus.ARCHIVED:
                return self._result(
                    ReadingAnnotationOperationStatus.ARCHIVED,
                    message="Evidence Reading Note target is archived.",
                )
            associations = self._note_associations(
                source_id=note.value.source_id,
                document_id=note.value.document_id,
                reference_id=note.value.reference_id,
                require_active_document=True,
            )
            if not associations.completed:
                return self._result(associations.status, message=associations.message)
            if note.value.source_id != source_id or reference_id not in {
                None,
                note.value.reference_id,
            }:
                return self._result(
                    ReadingAnnotationOperationStatus.CONFLICT,
                    message="Evidence associations do not match the Reading Note.",
                )
        elif document_id is not None and page_number is not None:
            document = self._document(document_id, require_active=True)
            if not document.completed or document.value is None:
                return self._result(document.status, message=document.message)
            if document.value.source_id != source_id or reference_id not in {
                None,
                document.value.reference_id,
            }:
                return self._result(
                    ReadingAnnotationOperationStatus.CONFLICT,
                    message="Evidence associations do not match the Source Document.",
                )
        else:
            return self._result(
                ReadingAnnotationOperationStatus.INVALID_STATE,
                message="Evidence requires exactly one valid target.",
            )
        return self._result(ReadingAnnotationOperationStatus.SUCCESS)

    def create_concept_evidence_link(
        self,
        *,
        concept_legacy_id: str,
        concept_legacy_source: str,
        source_id: str,
        link_type: EvidenceLinkType | str,
        reference_id: str | None = None,
        document_id: str | None = None,
        annotation_id: str | None = None,
        note_id: str | None = None,
        page_number: int | None = None,
        comment: str | None = None,
        evidence_link_id: str | None = None,
    ) -> ReadingAnnotationServiceResult[ConceptEvidenceLink]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        values: dict[str, Any] = {
            "concept_legacy_id": concept_legacy_id,
            "concept_legacy_source": concept_legacy_source,
            "source_id": source_id,
            "reference_id": reference_id,
            "document_id": document_id,
            "annotation_id": annotation_id,
            "note_id": note_id,
            "page_number": page_number,
            "link_type": link_type,
            "comment": comment,
        }
        if evidence_link_id is not None:
            values["evidence_link_id"] = evidence_link_id
        try:
            candidate = ConceptEvidenceLink.model_validate(values)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        try:
            existing_id = self.evidence.get_by_id(candidate.evidence_link_id)
        except Exception:
            existing_id = None
        if existing_id is not None:
            comparable = (
                "concept_legacy_id",
                "concept_legacy_source",
                "source_id",
                "reference_id",
                "document_id",
                "annotation_id",
                "note_id",
                "page_number",
                "link_type",
                "comment",
                "status",
            )
            if all(
                getattr(existing_id, field) == getattr(candidate, field) for field in comparable
            ):
                return self._result(
                    ReadingAnnotationOperationStatus.IDENTICAL,
                    existing_id,
                    "Concept evidence was already linked.",
                )
            return self._result(
                ReadingAnnotationOperationStatus.CONFLICT,
                existing_id,
                "Concept evidence identity conflicts with persisted content.",
            )
        source = self._source(candidate.source_id)
        if not source.completed:
            return self._result(source.status, message=source.message)
        try:
            if not self._concept_exists(
                candidate.concept_legacy_id,
                candidate.concept_legacy_source,
            ):
                return self._result(
                    ReadingAnnotationOperationStatus.BLOCKED,
                    message="Legacy concept does not exist.",
                )
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not validate the legacy concept.",
            )
        target = self._evidence_target(
            source_id=candidate.source_id,
            reference_id=candidate.reference_id,
            document_id=candidate.document_id,
            annotation_id=candidate.annotation_id,
            note_id=candidate.note_id,
            page_number=candidate.page_number,
        )
        if not target.completed:
            return self._result(target.status, message=target.message)
        try:
            if self.evidence.find_exact(candidate) is not None:
                return self._result(
                    ReadingAnnotationOperationStatus.CONFLICT,
                    message="An exact concept evidence link already exists.",
                )
            value = self.evidence.insert(candidate)
            return self._result(
                ReadingAnnotationOperationStatus.SUCCESS, value, "Concept evidence linked."
            )
        except ReadingAnnotationConflictError as exc:
            try:
                concurrent = self.evidence.get_by_id(candidate.evidence_link_id)
            except Exception:
                concurrent = None
            if concurrent is not None and all(
                getattr(concurrent, field) == getattr(candidate, field)
                for field in (
                    "concept_legacy_id",
                    "concept_legacy_source",
                    "source_id",
                    "reference_id",
                    "document_id",
                    "annotation_id",
                    "note_id",
                    "page_number",
                    "link_type",
                    "comment",
                    "status",
                )
            ):
                return self._result(ReadingAnnotationOperationStatus.IDENTICAL, concurrent)
            return self._result(ReadingAnnotationOperationStatus.CONFLICT, message=str(exc))
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not persist concept evidence.",
            )

    def _list_evidence(
        self, method: str, *args: Any, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ConceptEvidencePage]:
        try:
            return self._result(
                ReadingAnnotationOperationStatus.SUCCESS,
                getattr(self.evidence, method)(*args, **kwargs),
            )
        except (ValidationError, ValueError, TypeError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR, message="Could not list concept evidence."
            )

    def list_concept_evidence(
        self, concept_legacy_id: str, concept_legacy_source: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ConceptEvidencePage]:
        return self._list_evidence(
            "list_by_concept", concept_legacy_id, concept_legacy_source, **kwargs
        )

    def list_document_evidence(
        self, document_id: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ConceptEvidencePage]:
        context = self._document(document_id, require_active=False)
        if not context.completed:
            return self._result(context.status, message=context.message)
        return self._list_evidence("list_by_document", document_id, **kwargs)

    def list_annotation_evidence(
        self, annotation_id: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ConceptEvidencePage]:
        annotation = self.get_annotation(annotation_id)
        if not annotation.completed:
            return self._result(annotation.status, message=annotation.message)
        return self._list_evidence("list_by_annotation", annotation_id, **kwargs)

    def list_note_evidence(
        self, note_id: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ConceptEvidencePage]:
        note = self.get_note(note_id)
        if not note.completed:
            return self._result(note.status, message=note.message)
        return self._list_evidence("list_by_note", note_id, **kwargs)

    def list_source_evidence(
        self, source_id: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ConceptEvidencePage]:
        source = self._source(source_id)
        if not source.completed:
            return self._result(source.status, message=source.message)
        return self._list_evidence("list_by_source", source_id, **kwargs)

    def search_evidence(
        self, query: str, **kwargs: Any
    ) -> ReadingAnnotationServiceResult[ConceptEvidencePage]:
        return self._list_evidence("search", query, **kwargs)

    def _evidence_lifecycle(
        self, evidence_link_id: str, *, reactivate: bool
    ) -> ReadingAnnotationServiceResult[ConceptEvidenceLink]:
        gate = self._write_gate()
        if gate is not None:
            return self._result(gate.status, message=gate.message)
        try:
            validate_evidence_link_id(evidence_link_id)
            current = self.evidence.get_by_id(evidence_link_id)
            if current is None:
                return self._result(
                    ReadingAnnotationOperationStatus.NOT_FOUND,
                    message="Concept evidence link not found.",
                )
            if reactivate:
                if not self._concept_exists(
                    current.concept_legacy_id, current.concept_legacy_source
                ):
                    return self._result(
                        ReadingAnnotationOperationStatus.BLOCKED,
                        message="Legacy concept no longer exists.",
                    )
                target = self._evidence_target(
                    source_id=current.source_id,
                    reference_id=current.reference_id,
                    document_id=current.document_id,
                    annotation_id=current.annotation_id,
                    note_id=current.note_id,
                    page_number=current.page_number,
                )
                if not target.completed:
                    return self._result(target.status, message=target.message)
            value = (
                self.evidence.reactivate(evidence_link_id)
                if reactivate
                else self.evidence.archive(evidence_link_id)
            )
            return self._result(ReadingAnnotationOperationStatus.SUCCESS, value)
        except (ValidationError, ValueError) as exc:
            return self._result(ReadingAnnotationOperationStatus.INVALID_STATE, message=str(exc))
        except Exception:
            return self._result(
                ReadingAnnotationOperationStatus.ERROR,
                message="Could not update concept evidence status.",
            )

    def archive_evidence_link(
        self, evidence_link_id: str
    ) -> ReadingAnnotationServiceResult[ConceptEvidenceLink]:
        return self._evidence_lifecycle(evidence_link_id, reactivate=False)

    def reactivate_evidence_link(
        self, evidence_link_id: str
    ) -> ReadingAnnotationServiceResult[ConceptEvidenceLink]:
        return self._evidence_lifecycle(evidence_link_id, reactivate=True)


__all__ = [
    "ReadingAnnotationOperationStatus",
    "ReadingAnnotationService",
    "ReadingAnnotationServiceResult",
]

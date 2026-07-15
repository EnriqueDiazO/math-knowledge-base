"""Same-origin S5C routes for guided visual concept linking."""

# ruff: noqa: D103

from __future__ import annotations

from collections import OrderedDict
from typing import Annotated
from typing import Any
from typing import Literal

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import Response

from mathmongo.advanced_reader.concept_evidence import VisualConceptEvidenceRepository
from mathmongo.advanced_reader.concept_evidence import concept_payload
from mathmongo.advanced_reader.concept_evidence import create_visual_concept_evidence
from mathmongo.advanced_reader.concept_evidence import evidence_payload
from mathmongo.advanced_reader.concept_evidence import resolve_concepts_for_links
from mathmongo.advanced_reader.concept_schemas import ConceptDetailResponse
from mathmongo.advanced_reader.concept_schemas import ConceptEvidenceCreate
from mathmongo.advanced_reader.concept_schemas import ConceptEvidenceLifecycle
from mathmongo.advanced_reader.concept_schemas import ConceptEvidenceListResponse
from mathmongo.advanced_reader.concept_schemas import ConceptEvidenceWriteResponse
from mathmongo.advanced_reader.concept_schemas import ConceptSearchResponse
from mathmongo.advanced_reader.concept_schemas import DocumentConceptGroupResponse
from mathmongo.advanced_reader.concept_schemas import DocumentConceptSummaryResponse
from mathmongo.advanced_reader.concept_schemas import UnlinkedVisualAnnotationListResponse
from mathmongo.advanced_reader.concept_schemas import UnlinkedVisualAnnotationResponse
from mathmongo.advanced_reader.concept_search import get_legacy_concept
from mathmongo.advanced_reader.concept_search import search_legacy_concepts
from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.advanced_reader.document_access import DocumentAccessService
from mathmongo.reading_annotations.models import EvidenceLinkStatus
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
from mathmongo.reading_annotations.service import ReadingAnnotationService


def _dependencies(request: Request) -> AdvancedReaderDependencies:
    return request.app.state.advanced_reader_dependencies


def _service(dependencies: AdvancedReaderDependencies) -> ReadingAnnotationService:
    if dependencies.annotation_service is None:
        raise AdvancedReaderError(
            "concept_linking_not_ready",
            "Initialize Notes & Evidence in Maintenance before linking concepts.",
            status_code=409,
        )
    return dependencies.annotation_service


def _operation_error(
    status: ReadingAnnotationOperationStatus,
    message: str,
    *,
    lifecycle: bool = False,
) -> AdvancedReaderError:
    folded = message.casefold()
    if status == ReadingAnnotationOperationStatus.NOT_FOUND:
        return AdvancedReaderError(
            "evidence_not_found" if lifecycle else "annotation_not_found",
            "The requested evidence target does not exist.",
            status_code=404,
        )
    if status == ReadingAnnotationOperationStatus.ARCHIVED:
        return AdvancedReaderError(
            "annotation_archived",
            "Reactivate the visual Annotation before linking or reactivating evidence.",
            status_code=409,
        )
    if status == ReadingAnnotationOperationStatus.CONFLICT:
        return AdvancedReaderError(
            "evidence_conflict",
            "The concept evidence conflicts with persisted state.",
            status_code=409,
        )
    if status == ReadingAnnotationOperationStatus.BLOCKED:
        if "concept" in folded:
            return AdvancedReaderError(
                "concept_not_found",
                "The exact legacy concept does not exist.",
                status_code=404,
            )
        if "version" in folded:
            return AdvancedReaderError(
                "annotation_version_mismatch",
                "The visual mark belongs to another PDF version.",
                status_code=409,
            )
        return AdvancedReaderError(
            "annotation_not_visual",
            "The Annotation cannot receive visual concept evidence.",
            status_code=409,
        )
    if status == ReadingAnnotationOperationStatus.INVALID_STATE:
        if "visual" in folded and "not" in folded:
            return AdvancedReaderError(
                "annotation_not_visual",
                "The Annotation has no persistent visual anchor.",
                status_code=409,
            )
        return AdvancedReaderError(
            "concept_linking_not_ready",
            "Initialize Notes & Evidence in Maintenance before linking concepts.",
            status_code=409,
        )
    return AdvancedReaderError(
        "internal_error",
        "The concept evidence operation could not be completed.",
        status_code=503,
    )


def _book_label(access: DocumentAccessService, document_id: str, pdf_page: int) -> str | None:
    try:
        return access.page_label(document_id, pdf_page)[0]
    except Exception:
        return None


def _annotation_context(
    dependencies: AdvancedReaderDependencies,
    annotation_id: str,
) -> tuple[ReadingAnnotationService, DocumentAccessService, Any, Any]:
    service = _service(dependencies)
    result = service.get_visual_annotation(annotation_id)
    if not result.completed or result.value is None:
        raise _operation_error(result.status, result.message)
    access = DocumentAccessService(dependencies)
    resolved = access.resolve_pdf(result.value.document_id, inspect_integrity=False)
    return service, access, resolved, result.value


def build_concept_router() -> APIRouter:
    router = APIRouter()

    @router.get("/concepts/search", response_model=ConceptSearchResponse)
    def concept_search(
        request: Request,
        q: Annotated[str, Query(min_length=1, max_length=160)],
        source: Annotated[str | None, Query(max_length=1_000)] = None,
        concept_type: Annotated[str | None, Query(max_length=160)] = None,
        category: Annotated[str | None, Query(max_length=160)] = None,
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> ConceptSearchResponse:
        dependencies = _dependencies(request)
        service = _service(dependencies)
        try:
            result = search_legacy_concepts(
                service.database,
                q,
                source=source,
                concept_type=concept_type,
                category=category,
                page=page,
                limit=limit,
            )
        except ValueError as exc:
            raise AdvancedReaderError(
                "concept_query_invalid",
                "The concept search parameters are invalid.",
                status_code=422,
            ) from exc
        return ConceptSearchResponse(
            items=[concept_payload(item, item.identity) for item in result.items],
            page=result.page,
            page_size=result.page_size,
            has_more=result.has_more,
        )

    @router.get("/concepts/detail", response_model=ConceptDetailResponse)
    def concept_detail(
        request: Request,
        concept_id: Annotated[str, Query(min_length=1, max_length=500)],
        concept_source: Annotated[str, Query(min_length=1, max_length=1_000)],
    ) -> ConceptDetailResponse:
        service = _service(_dependencies(request))
        try:
            concept = get_legacy_concept(service.database, concept_id, concept_source)
        except ValueError as exc:
            raise AdvancedReaderError(
                "concept_query_invalid",
                "The legacy concept identity is invalid.",
                status_code=422,
            ) from exc
        if concept is None:
            raise AdvancedReaderError(
                "concept_not_found",
                "The exact legacy concept does not exist.",
                status_code=404,
            )
        base = concept_payload(concept, concept.identity)
        return ConceptDetailResponse(**base.model_dump(), description=None)

    @router.get(
        "/visual-annotations/{annotation_id}/concept-evidence",
        response_model=ConceptEvidenceListResponse,
    )
    def annotation_evidence(
        annotation_id: str,
        request: Request,
        status: Literal["active", "archived", "all"] = "active",
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
    ) -> ConceptEvidenceListResponse:
        dependencies = _dependencies(request)
        service, access, resolved, annotation = _annotation_context(dependencies, annotation_id)
        result = service.list_annotation_evidence(
            annotation_id,
            status=None if status == "all" else EvidenceLinkStatus(status),
            page=page,
            page_size=limit,
        )
        if not result.completed or result.value is None:
            raise _operation_error(result.status, result.message)
        links = result.value.items
        concepts = resolve_concepts_for_links(service.database, links)
        exact = (
            annotation.visual_anchor is not None
            and annotation.visual_anchor.version_id == resolved.version.version_id
            and annotation.visual_anchor.document_sha256 == resolved.version.sha256
        )
        label = _book_label(access, annotation.document_id, annotation.page_number or 1)
        return ConceptEvidenceListResponse(
            items=[
                evidence_payload(
                    link,
                    concepts.get((link.concept_legacy_id, link.concept_legacy_source)),
                    annotation=annotation,
                    visual_status="exact" if exact else "version_mismatch",
                    book_page_label=label,
                )
                for link in links
            ],
            page=result.value.page,
            page_size=result.value.page_size,
            total=result.value.total,
            pages=result.value.pages,
        )

    @router.post(
        "/visual-annotations/{annotation_id}/concept-evidence",
        response_model=ConceptEvidenceWriteResponse,
    )
    def create_annotation_evidence(
        annotation_id: str,
        payload: ConceptEvidenceCreate,
        request: Request,
        response: Response,
    ) -> ConceptEvidenceWriteResponse:
        dependencies = _dependencies(request)
        service, access, resolved, annotation = _annotation_context(dependencies, annotation_id)
        result = create_visual_concept_evidence(
            service,
            annotation,
            current_version_id=resolved.version.version_id,
            current_document_sha256=resolved.version.sha256,
            evidence_link_id=payload.evidence_link_id,
            concept_legacy_id=payload.concept_legacy_id,
            concept_legacy_source=payload.concept_legacy_source,
            link_type=payload.link_type.value,
            comment=payload.comment,
        )
        if not result.completed or result.value is None:
            raise _operation_error(result.status, result.message)
        concept = get_legacy_concept(
            service.database,
            result.value.concept_legacy_id,
            result.value.concept_legacy_source,
        )
        exact_result = result.status == ReadingAnnotationOperationStatus.IDENTICAL
        response.status_code = 200 if exact_result else 201
        response.headers["X-Write-Result"] = result.status.value
        return ConceptEvidenceWriteResponse(
            result="identical" if exact_result else "success",
            item=evidence_payload(
                result.value,
                concept,
                annotation=annotation,
                visual_status="exact",
                book_page_label=_book_label(
                    access,
                    annotation.document_id,
                    annotation.page_number or 1,
                ),
            ),
        )

    def lifecycle_response(
        evidence_link_id: str,
        request: Request,
        *,
        reactivate: bool,
    ) -> ConceptEvidenceWriteResponse:
        dependencies = _dependencies(request)
        service = _service(dependencies)
        result = (
            service.reactivate_evidence_link(evidence_link_id)
            if reactivate
            else service.archive_evidence_link(evidence_link_id)
        )
        if not result.completed or result.value is None:
            raise _operation_error(result.status, result.message, lifecycle=True)
        link = result.value
        annotation = None
        access = None
        visual_status = "exact"
        label = None
        if link.annotation_id is not None:
            _, access, resolved, annotation = _annotation_context(dependencies, link.annotation_id)
            anchor = annotation.visual_anchor
            visual_status = (
                "exact"
                if anchor is not None
                and anchor.version_id == resolved.version.version_id
                and anchor.document_sha256 == resolved.version.sha256
                else "version_mismatch"
            )
            label = _book_label(access, annotation.document_id, annotation.page_number or 1)
        concept = get_legacy_concept(
            service.database,
            link.concept_legacy_id,
            link.concept_legacy_source,
        )
        return ConceptEvidenceWriteResponse(
            result="identical"
            if result.status == ReadingAnnotationOperationStatus.IDENTICAL
            else "success",
            item=evidence_payload(
                link,
                concept,
                annotation=annotation,
                visual_status=visual_status,
                book_page_label=label,
            ),
        )

    @router.post(
        "/concept-evidence/{evidence_link_id}/archive",
        response_model=ConceptEvidenceWriteResponse,
    )
    def archive_evidence(
        evidence_link_id: str,
        payload: ConceptEvidenceLifecycle,
        request: Request,
    ) -> ConceptEvidenceWriteResponse:
        del payload
        return lifecycle_response(evidence_link_id, request, reactivate=False)

    @router.post(
        "/concept-evidence/{evidence_link_id}/reactivate",
        response_model=ConceptEvidenceWriteResponse,
    )
    def reactivate_evidence(
        evidence_link_id: str,
        payload: ConceptEvidenceLifecycle,
        request: Request,
    ) -> ConceptEvidenceWriteResponse:
        del payload
        return lifecycle_response(evidence_link_id, request, reactivate=True)

    @router.get(
        "/documents/{document_id}/visual-concept-evidence",
        response_model=DocumentConceptSummaryResponse,
    )
    def document_visual_evidence(
        document_id: str,
        request: Request,
        pdf_page: Annotated[int | None, Query(ge=1)] = None,
        concept_id: Annotated[str | None, Query(max_length=500)] = None,
        concept_source: Annotated[str | None, Query(max_length=1_000)] = None,
        status: Literal["active", "archived", "all"] = "active",
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
    ) -> DocumentConceptSummaryResponse:
        dependencies = _dependencies(request)
        service = _service(dependencies)
        access = DocumentAccessService(dependencies)
        resolved = access.resolve_pdf(document_id, inspect_integrity=False)
        repository = VisualConceptEvidenceRepository(service.database)
        records = repository.list_visual_evidence_by_document(
            document_id,
            pdf_page=pdf_page,
            concept_id=concept_id,
            concept_source=concept_source,
            status=None if status == "all" else EvidenceLinkStatus(status),
            page=page,
            page_size=limit,
        )
        links = tuple(item.link for item in records.items)
        concepts = resolve_concepts_for_links(service.database, links)
        labels = {
            value: _book_label(access, document_id, value)
            for value in {item.pdf_page for item in records.items}
        }
        grouped: OrderedDict[tuple[str, str], list[Any]] = OrderedDict()
        for item in records.items:
            identity = (item.link.concept_legacy_id, item.link.concept_legacy_source)
            grouped.setdefault(identity, []).append(item)
        groups: list[DocumentConceptGroupResponse] = []
        for identity, items in grouped.items():
            evidence = [
                evidence_payload(
                    item.link,
                    concepts.get(identity),
                    annotation=item,
                    visual_status=(
                        "exact"
                        if item.version_id == resolved.version.version_id
                        and item.document_sha256 == resolved.version.sha256
                        else "version_mismatch"
                    ),
                    book_page_label=labels[item.pdf_page],
                )
                for item in items
            ]
            groups.append(
                DocumentConceptGroupResponse(
                    concept=concept_payload(concepts.get(identity), identity),
                    highlight_count=sum(item.annotation_kind == "highlight" for item in items),
                    underline_count=sum(item.annotation_kind == "underline" for item in items),
                    pages=sorted({item.pdf_page for item in items}),
                    link_types=list(dict.fromkeys(item.link.link_type for item in items)),
                    evidence=evidence,
                )
            )
        return DocumentConceptSummaryResponse(
            items=groups,
            page=records.page,
            page_size=records.page_size,
            total=records.total,
            pages=records.pages,
        )

    @router.get(
        "/documents/{document_id}/unlinked-visual-annotations",
        response_model=UnlinkedVisualAnnotationListResponse,
    )
    def unlinked_visual_annotations(
        document_id: str,
        request: Request,
        pdf_page: Annotated[int | None, Query(ge=1)] = None,
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
    ) -> UnlinkedVisualAnnotationListResponse:
        dependencies = _dependencies(request)
        service = _service(dependencies)
        access = DocumentAccessService(dependencies)
        access.resolve_pdf(document_id, inspect_integrity=False)
        records = VisualConceptEvidenceRepository(
            service.database
        ).list_unlinked_visual_annotations(
            document_id,
            pdf_page=pdf_page,
            page=page,
            page_size=limit,
        )
        labels = {
            value: _book_label(access, document_id, value)
            for value in {item.pdf_page for item in records.items}
        }
        return UnlinkedVisualAnnotationListResponse(
            items=[
                UnlinkedVisualAnnotationResponse(
                    annotation_id=item.annotation_id,
                    kind=item.kind,
                    pdf_page=item.pdf_page,
                    book_page_label=labels[item.pdf_page] or item.page_label,
                    quote_text=item.quote_text,
                    color_label=item.color_label,
                )
                for item in records.items
            ],
            page=records.page,
            page_size=records.page_size,
            total=records.total,
            pages=records.pages,
        )

    return router


__all__ = ["build_concept_router"]

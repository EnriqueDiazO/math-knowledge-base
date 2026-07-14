"""Same-origin FastAPI routes for metadata, media, state, and Page Map."""

# ruff: noqa: D103

from __future__ import annotations

from typing import Annotated
from typing import Any
from typing import Literal

from fastapi import APIRouter
from fastapi import Header
from fastapi import Query
from fastapi import Request
from fastapi.responses import Response
from fastapi.responses import StreamingResponse

from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.advanced_reader.document_access import DocumentAccessService
from mathmongo.advanced_reader.range_requests import RangeErrorCode
from mathmongo.advanced_reader.range_requests import RangeRequestError
from mathmongo.advanced_reader.range_requests import parse_range_header
from mathmongo.advanced_reader.schemas import DocumentMetadataResponse
from mathmongo.advanced_reader.schemas import HealthResponse
from mathmongo.advanced_reader.schemas import PageLabelResponse
from mathmongo.advanced_reader.schemas import ReaderCapabilities
from mathmongo.advanced_reader.schemas import ReadingPageUpdate
from mathmongo.advanced_reader.schemas import ReadingStateResponse
from mathmongo.advanced_reader.schemas import ReadingStateSummary
from mathmongo.advanced_reader.schemas import ReferenceSummary
from mathmongo.advanced_reader.schemas import SourceSummary
from mathmongo.advanced_reader.schemas import VersionSummary
from mathmongo.advanced_reader.schemas import VisualAnchorResponse
from mathmongo.advanced_reader.schemas import VisualAnnotationCreate
from mathmongo.advanced_reader.schemas import VisualAnnotationLifecycle
from mathmongo.advanced_reader.schemas import VisualAnnotationListResponse
from mathmongo.advanced_reader.schemas import VisualAnnotationResponse
from mathmongo.advanced_reader.schemas import VisualAnnotationUpdate
from mathmongo.advanced_reader.security import sanitized_inline_filename
from mathmongo.reading_annotations.models import AnnotationStatus
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_space.service import ReadingOperationStatus

API_PREFIX = "/api/advanced-reader"


def _dependencies(request: Request) -> AdvancedReaderDependencies:
    return request.app.state.advanced_reader_dependencies


def _reading_state_payload(document_id: str, context: Any) -> ReadingStateResponse:
    state = context.reading_state
    return ReadingStateResponse(
        document_id=document_id,
        status=str(context.effective_status.value),
        current_page=getattr(state, "current_page", None),
        total_pages=getattr(state, "total_pages", None),
        last_opened_at=getattr(state, "last_opened_at", None),
    )


def _media_headers(version: Any) -> dict[str, str]:
    filename = sanitized_inline_filename(version.original_filename)
    return {
        "Accept-Ranges": "bytes",
        "ETag": f'"{version.sha256}"',
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
    }


def _annotation_service(dependencies: AdvancedReaderDependencies) -> ReadingAnnotationService:
    service = dependencies.annotation_service
    if service is None:
        raise AdvancedReaderError(
            "visual_annotations_unavailable",
            "Visual annotations are unavailable in this reader process.",
            status_code=503,
        )
    return service


def _visual_operation_error(status: ReadingAnnotationOperationStatus) -> AdvancedReaderError:
    if status == ReadingAnnotationOperationStatus.NOT_FOUND:
        return AdvancedReaderError(
            "visual_annotation_not_found",
            "The requested visual annotation does not exist.",
            status_code=404,
        )
    if status == ReadingAnnotationOperationStatus.ARCHIVED:
        return AdvancedReaderError(
            "visual_annotation_archived",
            "Archived visual annotations cannot be edited.",
            status_code=409,
        )
    if status == ReadingAnnotationOperationStatus.INVALID_STATE:
        return AdvancedReaderError(
            "visual_annotations_not_ready",
            "Initialize Notes & Evidence in Maintenance before saving visual marks.",
            status_code=409,
        )
    if status == ReadingAnnotationOperationStatus.CONFLICT:
        return AdvancedReaderError(
            "visual_annotation_conflict",
            "The visual annotation conflicts with persisted state.",
            status_code=409,
        )
    if status == ReadingAnnotationOperationStatus.BLOCKED:
        return AdvancedReaderError(
            "integrity_error",
            "PDF integrity validation blocked the visual annotation operation.",
            status_code=409,
        )
    return AdvancedReaderError(
        "database_unavailable",
        "The visual annotation operation could not be completed.",
        status_code=503,
    )


def _visual_response(
    annotation: DocumentAnnotation,
    *,
    current_version_id: str,
    current_document_sha256: str,
    page_label: str | None,
) -> VisualAnnotationResponse:
    anchor = annotation.visual_anchor
    if anchor is None:
        raise AdvancedReaderError(
            "invalid_visual_annotation",
            "The stored annotation has no visual anchor.",
            status_code=409,
        )
    exact = (
        anchor.version_id == current_version_id
        and anchor.document_sha256 == current_document_sha256
    )
    return VisualAnnotationResponse(
        annotation_id=annotation.annotation_id,
        document_id=annotation.document_id,
        kind=annotation.kind.value,
        status=annotation.status.value,
        pdf_page=anchor.pdf_page,
        page_label=annotation.page_label or page_label,
        quote_text=annotation.quote_text or "",
        body=annotation.body,
        color_label=annotation.color_label,
        tags=list(annotation.tags),
        visual_status="exact" if exact else "version_mismatch",
        visual_anchor=VisualAnchorResponse(
            version_id=anchor.version_id,
            document_sha256=anchor.document_sha256,
            coordinate_space=anchor.coordinate_space,
            capture_rotation=anchor.capture_rotation,
            rects=list(anchor.rects),
        ),
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
        archived_at=annotation.archived_at,
    )


def _optional_visual_page_label(
    access: DocumentAccessService,
    document_id: str,
    pdf_page: int,
) -> str | None:
    """Treat Book page metadata as optional after a visual write/read succeeds."""
    try:
        return access.page_label(document_id, pdf_page)[0]
    except Exception:
        return None


def build_api_router() -> APIRouter:
    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health", response_model=HealthResponse)
    def health(request: Request) -> HealthResponse:
        dependencies = _dependencies(request)
        try:
            available = bool(dependencies.health_check())
        except Exception:
            available = False
        if not available:
            raise AdvancedReaderError(
                "database_unavailable",
                "The configured database is unavailable.",
                status_code=503,
            )
        return HealthResponse(
            database=dependencies.database_name,
            frontend_ready=dependencies.frontend_ready,
        )

    @router.get("/documents/{document_id}", response_model=DocumentMetadataResponse)
    def document_metadata(document_id: str, request: Request) -> DocumentMetadataResponse:
        dependencies = _dependencies(request)
        access = DocumentAccessService(dependencies)
        resolved = access.resolve_pdf(document_id, inspect_integrity=True)
        context = resolved.context
        state = context.reading_state
        current_page = getattr(state, "current_page", None) or 1
        book_label, display_label = access.page_label(document_id, current_page)
        reference = context.reference
        visual_writes_ready = dependencies.visual_annotation_writes_ready
        return DocumentMetadataResponse(
            document_id=document_id,
            title=context.document.title,
            status=context.document.status.value,
            source=SourceSummary(
                source_id=context.source.source_id,
                name=context.source.name,
            ),
            reference=(
                ReferenceSummary(
                    reference_id=reference.reference_id,
                    title=reference.title or reference.reference_id,
                )
                if reference is not None
                else None
            ),
            version=VersionSummary(
                version_id=resolved.version.version_id,
                sha256=resolved.version.sha256,
                size_bytes=resolved.version.size_bytes,
                original_filename=resolved.version.original_filename,
            ),
            reading_state=ReadingStateSummary(
                status=context.effective_status.value,
                current_page=getattr(state, "current_page", None),
                total_pages=getattr(state, "total_pages", None),
                last_opened_at=getattr(state, "last_opened_at", None),
            ),
            page_label=PageLabelResponse(
                pdf_page=current_page,
                book_page_label=book_label,
                display_label=display_label,
            ),
            capabilities=ReaderCapabilities(
                persistent_highlights=visual_writes_ready,
                persistent_underlines=visual_writes_ready,
                visual_annotation_editing=visual_writes_ready,
                visual_annotation_archiving=visual_writes_ready,
            ),
        )

    def pdf_response(
        document_id: str,
        request: Request,
        range_header: str | None,
        *,
        head_only: bool,
    ) -> Response:
        dependencies = _dependencies(request)
        access = DocumentAccessService(dependencies)
        resolved = access.resolve_pdf(document_id, inspect_integrity=False)
        handle = access.open_verified_pdf(resolved)
        headers = _media_headers(resolved.version)
        start = 0
        length = handle.size
        status_code = 200
        if range_header:
            try:
                requested = parse_range_header(range_header, handle.size)
            except RangeRequestError as exc:
                handle.close()
                code = exc.code.value
                message = (
                    "Multiple byte ranges are not supported."
                    if exc.code == RangeErrorCode.MULTIPLE
                    else "The requested byte range is invalid."
                )
                raise AdvancedReaderError(
                    code,
                    message,
                    status_code=416,
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Range": f"bytes */{resolved.version.size_bytes}",
                    },
                ) from exc
            start = requested.start
            length = requested.length
            status_code = 206
            headers["Content-Range"] = requested.content_range
        headers["Content-Length"] = str(length)
        if head_only:
            handle.close()
            return Response(
                status_code=status_code,
                media_type="application/pdf",
                headers=headers,
            )
        return StreamingResponse(
            handle.iter_bytes(start, length),
            status_code=status_code,
            media_type="application/pdf",
            headers=headers,
        )

    @router.get("/documents/{document_id}/pdf")
    def pdf_stream(
        document_id: str,
        request: Request,
        range_header: str | None = Header(default=None, alias="Range"),
    ) -> Response:
        return pdf_response(
            document_id,
            request,
            range_header,
            head_only=False,
        )

    @router.head("/documents/{document_id}/pdf")
    def pdf_head(
        document_id: str,
        request: Request,
        range_header: str | None = Header(default=None, alias="Range"),
    ) -> Response:
        return pdf_response(
            document_id,
            request,
            range_header,
            head_only=True,
        )

    @router.get(
        "/documents/{document_id}/reading-state",
        response_model=ReadingStateResponse,
    )
    def reading_state(document_id: str, request: Request) -> ReadingStateResponse:
        access = DocumentAccessService(_dependencies(request))
        resolved = access.resolve_pdf(document_id, inspect_integrity=False)
        return _reading_state_payload(document_id, resolved.context)

    @router.put(
        "/documents/{document_id}/reading-state/page",
        response_model=ReadingStateResponse,
    )
    def update_reading_page(
        document_id: str,
        request: Request,
        payload: ReadingPageUpdate,
    ) -> ReadingStateResponse:
        dependencies = _dependencies(request)
        access = DocumentAccessService(dependencies)
        resolved = access.resolve_pdf(document_id, inspect_integrity=False)
        known_total = getattr(resolved.context.reading_state, "total_pages", None)
        if isinstance(known_total, int) and payload.pdf_page > known_total:
            raise AdvancedReaderError(
                "page_invalid",
                "PDF page exceeds the known page count.",
                status_code=422,
            )
        result = dependencies.reading_service.update_current_page(
            document_id,
            payload.pdf_page,
        )
        if result.status == ReadingOperationStatus.NOT_FOUND:
            raise AdvancedReaderError(
                "document_not_found",
                "The requested Document does not exist.",
                status_code=404,
            )
        if result.status == ReadingOperationStatus.ARCHIVED:
            raise AdvancedReaderError(
                "document_archived",
                "Archived Documents cannot be updated.",
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
                "internal_error",
                "The reading position could not be saved.",
                status_code=409,
            )
        state = result.value
        return ReadingStateResponse(
            document_id=resolved.context.document.document_id,
            status=state.status.value,
            current_page=state.current_page,
            total_pages=state.total_pages,
            last_opened_at=state.last_opened_at,
        )

    @router.get(
        "/documents/{document_id}/page-label",
        response_model=PageLabelResponse,
    )
    def page_label(document_id: str, pdf_page: str, request: Request) -> PageLabelResponse:
        access = DocumentAccessService(_dependencies(request))
        access.resolve_pdf(document_id, inspect_integrity=False)
        if not pdf_page.isascii() or not pdf_page.isdecimal():
            raise AdvancedReaderError(
                "page_invalid",
                "PDF page must be an integer greater than or equal to 1.",
                status_code=422,
            )
        page = int(pdf_page)
        book_label, display_label = access.page_label(document_id, page)
        return PageLabelResponse(
            pdf_page=page,
            book_page_label=book_label,
            display_label=display_label,
        )

    @router.get(
        "/documents/{document_id}/visual-annotations",
        response_model=VisualAnnotationListResponse,
    )
    def list_visual_annotations(
        document_id: str,
        request: Request,
        pdf_page: Annotated[int | None, Query(strict=False, ge=1)] = None,
        status: Literal["active", "archived", "all"] = "active",
        page: Annotated[int, Query(strict=False, ge=1, le=100_000)] = 1,
        limit: Annotated[int, Query(strict=False, ge=1, le=100)] = 50,
    ) -> VisualAnnotationListResponse:
        dependencies = _dependencies(request)
        access = DocumentAccessService(dependencies)
        resolved = access.resolve_pdf(document_id, inspect_integrity=False)
        result = _annotation_service(dependencies).list_visual_annotations(
            document_id,
            pdf_page=pdf_page,
            status=None if status == "all" else AnnotationStatus(status),
            page=page,
            page_size=limit,
        )
        if not result.completed or result.value is None:
            raise _visual_operation_error(result.status)
        labels: dict[int, str | None] = {}
        items: list[VisualAnnotationResponse] = []
        for annotation in result.value.items:
            annotation_page = annotation.page_number or 1
            if annotation_page not in labels:
                labels[annotation_page] = _optional_visual_page_label(
                    access,
                    document_id,
                    annotation_page,
                )
            items.append(
                _visual_response(
                    annotation,
                    current_version_id=resolved.version.version_id,
                    current_document_sha256=resolved.version.sha256,
                    page_label=labels[annotation_page],
                )
            )
        return VisualAnnotationListResponse(
            items=items,
            page=result.value.page,
            page_size=result.value.page_size,
            total=result.value.total,
            pages=result.value.pages,
        )

    @router.post(
        "/documents/{document_id}/visual-annotations",
        response_model=VisualAnnotationResponse,
    )
    def create_visual_annotation(
        document_id: str,
        payload: VisualAnnotationCreate,
        request: Request,
        response: Response,
    ) -> VisualAnnotationResponse:
        dependencies = _dependencies(request)
        access = DocumentAccessService(dependencies)
        resolved = access.resolve_pdf(document_id, inspect_integrity=False)
        known_total = getattr(resolved.context.reading_state, "total_pages", None)
        if isinstance(known_total, int) and payload.pdf_page > known_total:
            raise AdvancedReaderError(
                "page_invalid",
                "PDF page exceeds the known page count.",
                status_code=422,
            )
        result = _annotation_service(dependencies).create_visual_annotation(
            annotation_id=payload.annotation_id,
            document_id=document_id,
            version_id=payload.version_id,
            document_sha256=payload.document_sha256,
            pdf_page=payload.pdf_page,
            kind=payload.kind,
            quote_text=payload.quote_text,
            rects=payload.rects,
            capture_rotation=payload.capture_rotation,
            color_label=payload.color_label,
            body=payload.body,
            tags=payload.tags,
        )
        if not result.completed or result.value is None:
            raise _visual_operation_error(result.status)
        response.status_code = (
            200 if result.status == ReadingAnnotationOperationStatus.IDENTICAL else 201
        )
        response.headers["X-Write-Result"] = result.status.value
        book_label = _optional_visual_page_label(access, document_id, payload.pdf_page)
        return _visual_response(
            result.value,
            current_version_id=resolved.version.version_id,
            current_document_sha256=resolved.version.sha256,
            page_label=book_label,
        )

    def resolve_visual_annotation(
        annotation_id: str,
        request: Request,
    ) -> tuple[
        ReadingAnnotationService,
        DocumentAccessService,
        Any,
        DocumentAnnotation,
    ]:
        dependencies = _dependencies(request)
        service = _annotation_service(dependencies)
        result = service.get_visual_annotation(annotation_id)
        if not result.completed or result.value is None:
            raise _visual_operation_error(result.status)
        access = DocumentAccessService(dependencies)
        resolved = access.resolve_pdf(result.value.document_id, inspect_integrity=False)
        return service, access, resolved, result.value

    @router.get(
        "/visual-annotations/{annotation_id}",
        response_model=VisualAnnotationResponse,
    )
    def get_visual_annotation(
        annotation_id: str,
        request: Request,
    ) -> VisualAnnotationResponse:
        _, access, resolved, annotation = resolve_visual_annotation(annotation_id, request)
        label = _optional_visual_page_label(
            access,
            annotation.document_id,
            annotation.page_number or 1,
        )
        return _visual_response(
            annotation,
            current_version_id=resolved.version.version_id,
            current_document_sha256=resolved.version.sha256,
            page_label=label,
        )

    @router.patch(
        "/visual-annotations/{annotation_id}",
        response_model=VisualAnnotationResponse,
    )
    def update_visual_annotation(
        annotation_id: str,
        payload: VisualAnnotationUpdate,
        request: Request,
    ) -> VisualAnnotationResponse:
        service, access, resolved, current = resolve_visual_annotation(annotation_id, request)
        result = service.update_visual_annotation_presentation(
            annotation_id,
            kind=payload.kind if payload.kind is not None else current.kind,
            color_label=(
                payload.color_label
                if payload.color_label is not None
                else (current.color_label or "yellow")
            ),
            body=payload.body if payload.body is not None else current.body,
            tags=payload.tags if payload.tags is not None else current.tags,
        )
        if not result.completed or result.value is None:
            raise _visual_operation_error(result.status)
        label = _optional_visual_page_label(
            access,
            current.document_id,
            current.page_number or 1,
        )
        return _visual_response(
            result.value,
            current_version_id=resolved.version.version_id,
            current_document_sha256=resolved.version.sha256,
            page_label=label,
        )

    def visual_lifecycle_response(
        annotation_id: str,
        request: Request,
        *,
        reactivate: bool,
    ) -> VisualAnnotationResponse:
        service, access, resolved, current = resolve_visual_annotation(annotation_id, request)
        result = (
            service.reactivate_visual_annotation(annotation_id)
            if reactivate
            else service.archive_visual_annotation(annotation_id)
        )
        if not result.completed or result.value is None:
            raise _visual_operation_error(result.status)
        label = _optional_visual_page_label(
            access,
            current.document_id,
            current.page_number or 1,
        )
        return _visual_response(
            result.value,
            current_version_id=resolved.version.version_id,
            current_document_sha256=resolved.version.sha256,
            page_label=label,
        )

    @router.post(
        "/visual-annotations/{annotation_id}/archive",
        response_model=VisualAnnotationResponse,
    )
    def archive_visual_annotation(
        annotation_id: str,
        payload: VisualAnnotationLifecycle,
        request: Request,
    ) -> VisualAnnotationResponse:
        del payload
        return visual_lifecycle_response(annotation_id, request, reactivate=False)

    @router.post(
        "/visual-annotations/{annotation_id}/reactivate",
        response_model=VisualAnnotationResponse,
    )
    def reactivate_visual_annotation(
        annotation_id: str,
        payload: VisualAnnotationLifecycle,
        request: Request,
    ) -> VisualAnnotationResponse:
        del payload
        return visual_lifecycle_response(annotation_id, request, reactivate=True)

    return router


__all__ = ["API_PREFIX", "build_api_router"]

"""Same-origin FastAPI routes for metadata, media, state, and Page Map."""

# ruff: noqa: D103

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi import Header
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
from mathmongo.advanced_reader.schemas import ReadingPageUpdate
from mathmongo.advanced_reader.schemas import ReadingStateResponse
from mathmongo.advanced_reader.schemas import ReadingStateSummary
from mathmongo.advanced_reader.schemas import ReferenceSummary
from mathmongo.advanced_reader.schemas import SourceSummary
from mathmongo.advanced_reader.schemas import VersionSummary
from mathmongo.advanced_reader.security import sanitized_inline_filename
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

    return router


__all__ = ["API_PREFIX", "build_api_router"]

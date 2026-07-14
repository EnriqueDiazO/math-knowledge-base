"""FastAPI application factory for one isolated loopback reader process."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.advanced_reader.routes import build_api_router
from mathmongo.advanced_reader.schemas import ApiErrorDetail
from mathmongo.advanced_reader.schemas import ApiErrorResponse
from mathmongo.advanced_reader.security import LOOPBACK_HOSTS
from mathmongo.advanced_reader.security import SECURITY_HEADERS
from mathmongo.advanced_reader.security import redacted_request_path

LOGGER = logging.getLogger("mathmongo.advanced_reader")
MAX_VISUAL_ANNOTATION_REQUEST_BYTES = 64 * 1024


def _is_visual_annotation_write(request: Request) -> bool:
    path = request.url.path
    if request.method == "PATCH":
        return path.startswith("/api/advanced-reader/visual-annotations/")
    if request.method != "POST":
        return False
    return path.startswith("/api/advanced-reader/visual-annotations/") or path.endswith(
        "/visual-annotations"
    )


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else uuid4().hex


def _error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = ApiErrorResponse(
        error=ApiErrorDetail(
            code=code,
            message=message,
            request_id=_request_id(request),
        )
    )
    return JSONResponse(
        payload.model_dump(mode="json"),
        status_code=status_code,
        headers=headers,
    )


def _host_is_loopback(host_header: str) -> bool:
    if not host_header or host_header != host_header.strip():
        return False
    try:
        parsed = urlsplit(f"//{host_header}")
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        return False
    return bool(
        hostname
        and hostname.casefold() in LOOPBACK_HOSTS
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _same_origin(request: Request, origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
        host = parsed.hostname.casefold() if parsed.hostname else ""
        request_host = urlsplit(f"//{request.headers.get('host', '')}")
        origin_port = parsed.port or (80 if parsed.scheme == "http" else None)
        request_port = request_host.port or 80
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and host in LOOPBACK_HOSTS
        and host == (request_host.hostname or "").casefold()
        and origin_port == request_port
        and not parsed.username
        and not parsed.password
        and not parsed.path.strip("/")
        and not parsed.query
        and not parsed.fragment
    )


def create_app(dependencies: AdvancedReaderDependencies) -> FastAPI:
    """Create an app from explicit services without connecting or writing."""
    if not isinstance(dependencies, AdvancedReaderDependencies):
        raise ValueError("create_app requires explicit Advanced Reader dependencies")
    app = FastAPI(
        title="MathMongo Advanced Reader",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.advanced_reader_dependencies = dependencies

    @app.exception_handler(AdvancedReaderError)
    async def advanced_reader_error(request: Request, error: AdvancedReaderError) -> JSONResponse:
        return _error_response(
            request,
            code=error.code,
            message=error.public_message,
            status_code=error.status_code,
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _error: RequestValidationError) -> JSONResponse:
        visual_annotation_request = "/visual-annotations" in request.url.path
        return _error_response(
            request,
            code="invalid_visual_annotation" if visual_annotation_request else "page_invalid",
            message=(
                "The visual annotation request is invalid."
                if visual_annotation_request
                else "PDF page must be an integer greater than or equal to 1."
            ),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, _error: Exception) -> JSONResponse:
        LOGGER.error(
            "request_id=%s status=500 path=%s",
            _request_id(request),
            redacted_request_path(request.url.path),
        )
        return _error_response(
            request,
            code="internal_error",
            message="The Advanced Reader could not complete the request.",
            status_code=500,
        )

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        started = time.monotonic()
        request.state.request_id = uuid4().hex
        try:
            host_header = request.headers.get("host", "")
            if not _host_is_loopback(host_header):
                response = _error_response(
                    request,
                    code="internal_error",
                    message="The request host is not permitted.",
                    status_code=400,
                )
            else:
                origin = request.headers.get("origin")
                fetch_site = request.headers.get("sec-fetch-site", "none").casefold()
                if request.method in {"PUT", "POST", "PATCH", "DELETE"}:
                    if fetch_site not in {"none", "same-origin"} or (
                        origin and not _same_origin(request, origin)
                    ):
                        response = _error_response(
                            request,
                            code="internal_error",
                            message="Cross-origin state changes are not permitted.",
                            status_code=403,
                        )
                    elif _is_visual_annotation_write(request) and (
                        (origin is None and fetch_site != "same-origin")
                        or request.headers.get("content-type", "")
                        .partition(";")[0]
                        .strip()
                        .casefold()
                        != "application/json"
                    ):
                        message = (
                            "Visual annotation writes require same-origin request metadata."
                            if origin is None and fetch_site != "same-origin"
                            else "Visual annotation writes require an application/json body."
                        )
                        response = _error_response(
                            request,
                            code=(
                                "same_origin_required"
                                if origin is None and fetch_site != "same-origin"
                                else "json_required"
                            ),
                            message=message,
                            status_code=403
                            if origin is None and fetch_site != "same-origin"
                            else 415,
                        )
                    else:
                        if _is_visual_annotation_write(request):
                            raw_length = request.headers.get("content-length")
                            try:
                                declared_length = (
                                    int(raw_length) if raw_length is not None else None
                                )
                            except ValueError:
                                declared_length = -1
                            if declared_length is not None and (
                                declared_length < 0
                                or declared_length > MAX_VISUAL_ANNOTATION_REQUEST_BYTES
                            ):
                                response = _error_response(
                                    request,
                                    code="request_too_large",
                                    message="The visual annotation request exceeds the permitted size.",
                                    status_code=413,
                                )
                            else:
                                body = await request.body()
                                if (
                                    declared_length is not None and declared_length != len(body)
                                ) or len(body) > MAX_VISUAL_ANNOTATION_REQUEST_BYTES:
                                    response = _error_response(
                                        request,
                                        code="request_too_large",
                                        message=(
                                            "The visual annotation request exceeds the permitted size."
                                        ),
                                        status_code=413,
                                    )
                                else:
                                    response = await call_next(request)
                        else:
                            response = await call_next(request)
                else:
                    response = await call_next(request)
        except Exception:
            LOGGER.error(
                "request_id=%s status=500 path=%s",
                request.state.request_id,
                redacted_request_path(request.url.path),
            )
            response = _error_response(
                request,
                code="internal_error",
                message="The Advanced Reader could not complete the request.",
                status_code=500,
            )
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, private"
        elif request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        duration_ms = (time.monotonic() - started) * 1000
        LOGGER.info(
            "request_id=%s method=%s status=%s path=%s duration_ms=%.1f",
            request.state.request_id,
            request.method,
            response.status_code,
            redacted_request_path(request.url.path),
            duration_ms,
        )
        return response

    app.include_router(build_api_router())

    def serve_index(request: Request) -> FileResponse:
        index = dependencies.frontend_root / "index.html"
        if not dependencies.frontend_ready or not index.is_file():
            raise AdvancedReaderError(
                "frontend_not_built",
                "The Advanced Reader frontend has not been built.",
                status_code=503,
            )
        return FileResponse(index, media_type="text/html")

    app.add_api_route("/", serve_index, methods=["GET"], include_in_schema=False)
    app.add_api_route("/reader", serve_index, methods=["GET"], include_in_schema=False)

    def serve_favicon(request: Request) -> FileResponse:
        favicon = dependencies.frontend_root / "favicon.svg"
        if not dependencies.frontend_ready or not favicon.is_file():
            raise AdvancedReaderError(
                "frontend_not_built",
                "The Advanced Reader frontend has not been built.",
                status_code=503,
            )
        return FileResponse(favicon, media_type="image/svg+xml")

    app.add_api_route(
        "/favicon.svg",
        serve_favicon,
        methods=["GET"],
        include_in_schema=False,
    )
    app.mount(
        "/assets",
        StaticFiles(directory=Path(dependencies.frontend_root) / "assets", check_dir=False),
        name="advanced-reader-assets",
    )
    return app


__all__ = ["MAX_VISUAL_ANNOTATION_REQUEST_BYTES", "create_app"]

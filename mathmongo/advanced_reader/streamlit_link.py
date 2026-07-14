"""Safe, side-effect-free link helpers for the optional advanced reader."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler
from urllib.request import ProxyHandler
from urllib.request import Request
from urllib.request import build_opener

from mathmongo.advanced_reader.security import validate_public_url
from mathmongo.config import DEFAULT_ADVANCED_READER_PUBLIC_URL
from mathmongo.config import resolve_config
from mathmongo.source_documents.models import validate_document_id

ADVANCED_READER_URL_ENV = "MATHMONGO_ADVANCED_READER_URL"
DEFAULT_ADVANCED_READER_URL = DEFAULT_ADVANCED_READER_PUBLIC_URL
ADVANCED_READER_HEALTH_PATH = "/api/advanced-reader/health"
ADVANCED_READER_DOCUMENT_PATH = "/api/advanced-reader/documents"
ADVANCED_READER_PATH = "/reader"
DEFAULT_HEALTH_TIMEOUT_SECONDS = 0.35
MAX_HEALTH_TIMEOUT_SECONDS = 2.0
MAX_HEALTH_RESPONSE_BYTES = 4 * 1024
MAX_METADATA_RESPONSE_BYTES = 32 * 1024


class AdvancedReaderHealthStatus(str, Enum):
    """Bounded health outcomes understood by the Streamlit presentation layer."""

    AVAILABLE = "available"
    NOT_STARTED = "not_started"
    TIMEOUT = "timeout"
    INVALID = "invalid"


class AdvancedReaderDocumentStatus(str, Enum):
    """Document-specific outcomes used to gate the Streamlit reader link."""

    READY = "ready"
    NOT_STARTED = "not_started"
    DATABASE_MISMATCH = "database_mismatch"
    DOCUMENT_NOT_FOUND = "document_not_found"
    NOT_PDF = "not_pdf"
    INTEGRITY_ERROR = "integrity_error"
    TIMEOUT = "timeout"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class AdvancedReaderHealth:
    """Typed result from one loopback-only reader health probe."""

    status: AdvancedReaderHealthStatus
    base_url: str | None = None
    health_url: str | None = None
    database: str | None = None

    @property
    def available(self) -> bool:
        """Return whether the fixed health endpoint accepted the probe."""
        return self.status == AdvancedReaderHealthStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class AdvancedReaderDocumentReadiness:
    """Bounded readiness result for one Document in the active database."""

    status: AdvancedReaderDocumentStatus
    base_url: str | None = None
    metadata_url: str | None = None
    database: str | None = None

    @property
    def ready(self) -> bool:
        """Return whether the Document passed every remote readiness check."""
        return self.status == AdvancedReaderDocumentStatus.READY


def _loopback_base_url(value: object) -> str:
    """Validate and canonicalize one root-level loopback HTTP base URL."""
    if not isinstance(value, str):
        raise ValueError("Advanced reader base URL must be text")
    return validate_public_url(value)


def get_advanced_reader_base_url(
    environment: Mapping[str, str] | None = None,
) -> str:
    """Resolve the optional environment override without performing I/O."""
    env = os.environ if environment is None else environment
    configured = str(env.get(ADVANCED_READER_URL_ENV, "") or "").strip()
    if not configured and environment is None:
        configured = resolve_config(environment=env).advanced_reader_public_url
    return _loopback_base_url(configured or DEFAULT_ADVANCED_READER_URL)


def build_advanced_reader_url(
    document_id: str,
    *,
    base_url: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Build a reader URL whose only query parameter is ``document_id``."""
    canonical_document_id = validate_document_id(document_id)
    resolved_base = (
        _loopback_base_url(base_url)
        if base_url is not None
        else get_advanced_reader_base_url(environment)
    )
    query = urlencode({"document_id": canonical_document_id})
    return f"{resolved_base}{ADVANCED_READER_PATH}?{query}"


def _health_url(base_url: str) -> str:
    return f"{base_url}{ADVANCED_READER_HEALTH_PATH}"


def _metadata_url(base_url: str, document_id: str) -> str:
    return f"{base_url}{ADVANCED_READER_DOCUMENT_PATH}/{document_id}"


def _database_name(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("The active database name is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("The active database name is invalid") from exc
    if len(encoded) > 64 or "\x00" in value:
        raise ValueError("The active database name is invalid")
    return value


def _timeout_seconds(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("Health timeout must be a positive number")
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Health timeout must be a positive number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Health timeout must be a positive finite number")
    return min(timeout, MAX_HEALTH_TIMEOUT_SECONDS)


def _timed_out(error: BaseException) -> bool:
    if isinstance(error, TimeoutError):
        return True
    reason = getattr(error, "reason", None)
    return isinstance(reason, TimeoutError)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _bounded_json_payload(response: Any, *, maximum: int) -> dict[str, Any] | None:
    headers = getattr(response, "headers", None)
    declared_length = headers.get("Content-Length") if hasattr(headers, "get") else None
    if declared_length not in (None, ""):
        try:
            parsed_length = int(declared_length)
        except (TypeError, ValueError):
            return None
        if parsed_length < 0 or parsed_length > maximum:
            return None
    read = getattr(response, "read", None)
    if not callable(read):
        return None
    try:
        body = read(maximum + 1)
    except Exception:
        return None
    if not isinstance(body, bytes) or len(body) > maximum:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _health_response_status(
    response: Any,
    http_status: object,
) -> tuple[AdvancedReaderHealthStatus, str | None]:
    if not isinstance(http_status, int) or not 200 <= http_status < 300:
        return AdvancedReaderHealthStatus.NOT_STARTED, None
    payload = _bounded_json_payload(response, maximum=MAX_HEALTH_RESPONSE_BYTES)
    if payload is None:
        return AdvancedReaderHealthStatus.INVALID, None
    if payload.get("status") != "ok" or payload.get("service") != "mathmongo-advanced-reader":
        return AdvancedReaderHealthStatus.INVALID, None
    database = payload.get("database")
    try:
        database = _database_name(database)
    except ValueError:
        return AdvancedReaderHealthStatus.INVALID, None
    return (
        (
            AdvancedReaderHealthStatus.AVAILABLE
            if payload.get("frontend_ready") is True
            else AdvancedReaderHealthStatus.NOT_STARTED
        ),
        database,
    )


def _metadata_response_status(
    response: Any,
    http_status: object,
    *,
    document_id: str,
) -> AdvancedReaderDocumentStatus:
    if not isinstance(http_status, int) or not 200 <= http_status < 300:
        return AdvancedReaderDocumentStatus.INVALID
    payload = _bounded_json_payload(response, maximum=MAX_METADATA_RESPONSE_BYTES)
    if payload is None or payload.get("document_id") != document_id:
        return AdvancedReaderDocumentStatus.INVALID
    if payload.get("kind") != "pdf":
        return AdvancedReaderDocumentStatus.NOT_PDF
    if payload.get("integrity") != "ok":
        return AdvancedReaderDocumentStatus.INTEGRITY_ERROR
    return AdvancedReaderDocumentStatus.READY


def _metadata_http_error_status(error: HTTPError) -> AdvancedReaderDocumentStatus:
    payload = _bounded_json_payload(error, maximum=MAX_METADATA_RESPONSE_BYTES)
    detail = payload.get("error") if isinstance(payload, dict) else None
    code = detail.get("code") if isinstance(detail, dict) else None
    if code == "document_not_found":
        return AdvancedReaderDocumentStatus.DOCUMENT_NOT_FOUND
    if code == "document_not_pdf" or (code is None and error.code == 415):
        return AdvancedReaderDocumentStatus.NOT_PDF
    if code in {"blob_missing", "integrity_error"}:
        return AdvancedReaderDocumentStatus.INTEGRITY_ERROR
    return AdvancedReaderDocumentStatus.INVALID


def probe_advanced_reader(
    *,
    base_url: str | None = None,
    environment: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_HEALTH_TIMEOUT_SECONDS,
    opener: Callable[..., Any] | None = None,
) -> AdvancedReaderHealth:
    """Probe the fixed health endpoint once with a short, capped timeout."""
    try:
        resolved_base = (
            _loopback_base_url(base_url)
            if base_url is not None
            else get_advanced_reader_base_url(environment)
        )
        timeout = _timeout_seconds(timeout_seconds)
    except (TypeError, ValueError):
        return AdvancedReaderHealth(AdvancedReaderHealthStatus.INVALID)

    health_url = _health_url(resolved_base)
    request = Request(
        health_url,
        headers={"Accept": "application/json", "Connection": "close"},
        method="GET",
    )
    response: Any | None = None
    try:
        open_request = opener
        if open_request is None:
            open_request = build_opener(ProxyHandler({}), _NoRedirectHandler()).open
        response = open_request(request, timeout=timeout)
        status = getattr(response, "status", None)
        if status is None and callable(getattr(response, "getcode", None)):
            status = response.getcode()
        outcome, database = _health_response_status(response, status)
    except HTTPError as exc:
        outcome = AdvancedReaderHealthStatus.NOT_STARTED
        database = None
        if callable(getattr(exc, "close", None)):
            exc.close()
    except TimeoutError:
        outcome = AdvancedReaderHealthStatus.TIMEOUT
        database = None
    except URLError as exc:
        outcome = (
            AdvancedReaderHealthStatus.TIMEOUT
            if _timed_out(exc)
            else AdvancedReaderHealthStatus.NOT_STARTED
        )
        database = None
    except (ConnectionError, OSError):
        outcome = AdvancedReaderHealthStatus.NOT_STARTED
        database = None
    except Exception:
        outcome = AdvancedReaderHealthStatus.INVALID
        database = None
    finally:
        if response is not None and callable(getattr(response, "close", None)):
            response.close()
    return AdvancedReaderHealth(outcome, resolved_base, health_url, database)


def probe_advanced_reader_document(
    document_id: str,
    database_name: str,
    *,
    base_url: str | None = None,
    environment: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_HEALTH_TIMEOUT_SECONDS,
    opener: Callable[..., Any] | None = None,
) -> AdvancedReaderDocumentReadiness:
    """Check health, exact database identity, and one PDF metadata endpoint."""
    try:
        canonical_document_id = validate_document_id(document_id)
        expected_database = _database_name(database_name)
        resolved_base = (
            _loopback_base_url(base_url)
            if base_url is not None
            else get_advanced_reader_base_url(environment)
        )
        timeout = _timeout_seconds(timeout_seconds)
    except (TypeError, ValueError):
        return AdvancedReaderDocumentReadiness(AdvancedReaderDocumentStatus.INVALID)

    health = probe_advanced_reader(
        base_url=resolved_base,
        timeout_seconds=timeout,
        opener=opener,
    )
    metadata_url = _metadata_url(resolved_base, canonical_document_id)
    health_status = {
        AdvancedReaderHealthStatus.NOT_STARTED: AdvancedReaderDocumentStatus.NOT_STARTED,
        AdvancedReaderHealthStatus.TIMEOUT: AdvancedReaderDocumentStatus.TIMEOUT,
        AdvancedReaderHealthStatus.INVALID: AdvancedReaderDocumentStatus.INVALID,
    }.get(health.status)
    if health_status is not None:
        return AdvancedReaderDocumentReadiness(
            health_status,
            resolved_base,
            metadata_url,
            health.database,
        )
    if health.database != expected_database:
        return AdvancedReaderDocumentReadiness(
            AdvancedReaderDocumentStatus.DATABASE_MISMATCH,
            resolved_base,
            metadata_url,
            health.database,
        )

    request = Request(
        metadata_url,
        headers={"Accept": "application/json", "Connection": "close"},
        method="GET",
    )
    response: Any | None = None
    try:
        open_request = opener
        if open_request is None:
            open_request = build_opener(ProxyHandler({}), _NoRedirectHandler()).open
        response = open_request(request, timeout=timeout)
        status = getattr(response, "status", None)
        if status is None and callable(getattr(response, "getcode", None)):
            status = response.getcode()
        outcome = _metadata_response_status(
            response,
            status,
            document_id=canonical_document_id,
        )
    except HTTPError as exc:
        outcome = _metadata_http_error_status(exc)
        if callable(getattr(exc, "close", None)):
            exc.close()
    except TimeoutError:
        outcome = AdvancedReaderDocumentStatus.TIMEOUT
    except URLError as exc:
        outcome = (
            AdvancedReaderDocumentStatus.TIMEOUT
            if _timed_out(exc)
            else AdvancedReaderDocumentStatus.NOT_STARTED
        )
    except (ConnectionError, OSError):
        outcome = AdvancedReaderDocumentStatus.NOT_STARTED
    except Exception:
        outcome = AdvancedReaderDocumentStatus.INVALID
    finally:
        if response is not None and callable(getattr(response, "close", None)):
            response.close()
    return AdvancedReaderDocumentReadiness(
        outcome,
        resolved_base,
        metadata_url,
        health.database,
    )


__all__ = [
    "ADVANCED_READER_HEALTH_PATH",
    "ADVANCED_READER_DOCUMENT_PATH",
    "ADVANCED_READER_PATH",
    "ADVANCED_READER_URL_ENV",
    "DEFAULT_ADVANCED_READER_URL",
    "MAX_HEALTH_RESPONSE_BYTES",
    "MAX_METADATA_RESPONSE_BYTES",
    "AdvancedReaderDocumentReadiness",
    "AdvancedReaderDocumentStatus",
    "AdvancedReaderHealth",
    "AdvancedReaderHealthStatus",
    "build_advanced_reader_url",
    "get_advanced_reader_base_url",
    "probe_advanced_reader",
    "probe_advanced_reader_document",
]

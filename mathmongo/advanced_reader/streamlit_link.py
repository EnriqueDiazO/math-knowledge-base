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
ADVANCED_READER_PATH = "/reader"
DEFAULT_HEALTH_TIMEOUT_SECONDS = 0.35
MAX_HEALTH_TIMEOUT_SECONDS = 2.0
MAX_HEALTH_RESPONSE_BYTES = 4 * 1024


class AdvancedReaderHealthStatus(str, Enum):
    """Bounded health outcomes understood by the Streamlit presentation layer."""

    AVAILABLE = "available"
    NOT_STARTED = "not_started"
    TIMEOUT = "timeout"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class AdvancedReaderHealth:
    """Typed result from one loopback-only reader health probe."""

    status: AdvancedReaderHealthStatus
    base_url: str | None = None
    health_url: str | None = None

    @property
    def available(self) -> bool:
        """Return whether the fixed health endpoint accepted the probe."""
        return self.status == AdvancedReaderHealthStatus.AVAILABLE


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


def _health_response_status(response: Any, http_status: object) -> AdvancedReaderHealthStatus:
    if not isinstance(http_status, int) or not 200 <= http_status < 300:
        return AdvancedReaderHealthStatus.NOT_STARTED
    headers = getattr(response, "headers", None)
    declared_length = headers.get("Content-Length") if hasattr(headers, "get") else None
    if declared_length not in (None, ""):
        try:
            if int(declared_length) > MAX_HEALTH_RESPONSE_BYTES:
                return AdvancedReaderHealthStatus.INVALID
        except (TypeError, ValueError):
            return AdvancedReaderHealthStatus.INVALID
    read = getattr(response, "read", None)
    if not callable(read):
        return AdvancedReaderHealthStatus.INVALID
    try:
        body = read(MAX_HEALTH_RESPONSE_BYTES + 1)
    except Exception:
        return AdvancedReaderHealthStatus.INVALID
    if not isinstance(body, bytes) or len(body) > MAX_HEALTH_RESPONSE_BYTES:
        return AdvancedReaderHealthStatus.INVALID
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return AdvancedReaderHealthStatus.INVALID
    if not isinstance(payload, dict):
        return AdvancedReaderHealthStatus.INVALID
    if payload.get("status") != "ok" or payload.get("service") != "mathmongo-advanced-reader":
        return AdvancedReaderHealthStatus.INVALID
    return (
        AdvancedReaderHealthStatus.AVAILABLE
        if payload.get("frontend_ready") is True
        else AdvancedReaderHealthStatus.NOT_STARTED
    )


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
        outcome = _health_response_status(response, status)
    except HTTPError as exc:
        outcome = AdvancedReaderHealthStatus.NOT_STARTED
        if callable(getattr(exc, "close", None)):
            exc.close()
    except TimeoutError:
        outcome = AdvancedReaderHealthStatus.TIMEOUT
    except URLError as exc:
        outcome = (
            AdvancedReaderHealthStatus.TIMEOUT
            if _timed_out(exc)
            else AdvancedReaderHealthStatus.NOT_STARTED
        )
    except (ConnectionError, OSError):
        outcome = AdvancedReaderHealthStatus.NOT_STARTED
    except Exception:
        outcome = AdvancedReaderHealthStatus.INVALID
    finally:
        if response is not None and callable(getattr(response, "close", None)):
            response.close()
    return AdvancedReaderHealth(outcome, resolved_base, health_url)


__all__ = [
    "ADVANCED_READER_HEALTH_PATH",
    "ADVANCED_READER_PATH",
    "ADVANCED_READER_URL_ENV",
    "DEFAULT_ADVANCED_READER_URL",
    "MAX_HEALTH_RESPONSE_BYTES",
    "AdvancedReaderHealth",
    "AdvancedReaderHealthStatus",
    "build_advanced_reader_url",
    "get_advanced_reader_base_url",
    "probe_advanced_reader",
]

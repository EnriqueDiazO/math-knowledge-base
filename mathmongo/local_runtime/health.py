"""Direct loopback health probes with no proxy or remote-network fallback."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from http.client import HTTPException
from typing import Any

from mathmongo.advanced_reader.security import validate_loopback_host
from mathmongo.local_runtime.models import AdvancedReaderHealth
from mathmongo.local_runtime.models import validate_database_name
from mathmongo.local_runtime.models import validate_port

MAX_HEALTH_BODY_BYTES = 64 * 1024


def loopback_url(host: str, port: int) -> str:
    """Build a credential-free HTTP base URL from validated loopback values."""
    bind_host = validate_loopback_host(host)
    bind_port = validate_port(port)
    display_host = f"[{bind_host}]" if bind_host == "::1" else bind_host
    return f"http://{display_host}:{bind_port}"


def _get_local(
    host: str,
    port: int,
    path: str,
    *,
    timeout: float,
) -> tuple[int, bytes] | None:
    """Read one bounded response directly from a validated loopback socket."""
    bind_host = validate_loopback_host(host)
    bind_port = validate_port(port)
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("health path must be absolute and local")
    connection = HTTPConnection(bind_host, bind_port, timeout=timeout)
    try:
        connection.request(
            "GET",
            path,
            headers={"Accept": "application/json", "Connection": "close"},
        )
        response = connection.getresponse()
        body = response.read(MAX_HEALTH_BODY_BYTES + 1)
        if len(body) > MAX_HEALTH_BODY_BYTES:
            return None
        return response.status, body
    except (HTTPException, OSError, TimeoutError, ValueError):
        return None
    finally:
        connection.close()


def _bounded_text(value: Any, *, maximum: int = 80) -> str | None:
    if not isinstance(value, str):
        return None
    if value != value.strip():
        return None
    if not value or len(value) > maximum or any(ord(char) < 32 for char in value):
        return None
    return value


def probe_advanced_reader(
    host: str,
    port: int,
    *,
    timeout: float = 0.75,
) -> AdvancedReaderHealth | None:
    """Return a strict Advanced Reader health snapshot, or ``None`` on ambiguity."""
    response = _get_local(
        host,
        port,
        "/api/advanced-reader/health",
        timeout=timeout,
    )
    if response is None or response[0] != 200:
        return None
    try:
        payload = json.loads(response[1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("frontend_ready"), bool):
        return None
    status = _bounded_text(payload.get("status"))
    service = _bounded_text(payload.get("service"))
    database_raw = _bounded_text(payload.get("database"), maximum=64)
    if status is None or service is None or database_raw is None:
        return None
    try:
        database = validate_database_name(database_raw)
    except Exception:
        return None
    if database != database_raw:
        return None
    return AdvancedReaderHealth(
        status=status,
        service=service,
        database=database,
        frontend_ready=payload["frontend_ready"],
    )


def probe_streamlit(
    host: str,
    port: int,
    *,
    timeout: float = 0.75,
) -> bool:
    """Return whether the loopback listener exposes Streamlit's bounded health response."""
    response = _get_local(host, port, "/_stcore/health", timeout=timeout)
    if response is None or response[0] != 200:
        return False
    return response[1].strip().lower() in {b"ok", b"healthy"}


__all__ = [
    "MAX_HEALTH_BODY_BYTES",
    "loopback_url",
    "probe_advanced_reader",
    "probe_streamlit",
]

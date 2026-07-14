"""Loopback, response-header, and output-sanitization policy."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from urllib.parse import SplitResult
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DOCUMENT_ID_IN_PATH = re.compile(
    r"doc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "style-src-elem 'self'",
        "style-src-attr 'unsafe-inline'",
        "connect-src 'self'",
        "worker-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "form-action 'none'",
        "frame-src 'none'",
        "manifest-src 'none'",
    )
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), microphone=(), "
        "payment=(), usb=(), clipboard-read=(), clipboard-write=()"
    ),
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def validate_loopback_host(host: str) -> str:
    """Accept only the three explicit local bind identities used by S5A."""
    value = str(host or "").strip().casefold()
    if value == "localhost":
        return value
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("Advanced Reader host must be a loopback address") from exc
    if not parsed.is_loopback or value not in {"127.0.0.1", "::1"}:
        raise ValueError("Advanced Reader host must be 127.0.0.1, ::1, or localhost")
    return value


def validate_public_url(value: str) -> str:
    """Validate a path-free, credential-free HTTP loopback base URL."""
    try:
        parsed = urlsplit(str(value or "").strip())
        host = validate_loopback_host(parsed.hostname or "")
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("Advanced Reader URL must be a valid loopback HTTP URL") from exc
    if (
        parsed.scheme.casefold() != "http"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Advanced Reader URL must be a path-free loopback HTTP URL")
    display_host = f"[{host}]" if host == "::1" else host
    netloc = display_host if port is None else f"{display_host}:{port}"
    return urlunsplit(SplitResult("http", netloc, "", "", ""))


def sanitized_inline_filename(value: str) -> str:
    """Return a short ASCII PDF leaf safe for Content-Disposition."""
    normalized = unicodedata.normalize("NFKD", str(value or "document.pdf"))
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace("\\", "_").replace("/", "_")
    ascii_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", ascii_name).strip(" ._")
    stem = ascii_name[:-4] if ascii_name.casefold().endswith(".pdf") else ascii_name
    stem = stem.rstrip(" ._")[:116] or "document"
    return f"{stem}.pdf"


def redacted_request_path(path: str) -> str:
    """Shorten logical Document IDs before a path reaches local logs."""

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        return f"doc_…{value[-8:]}"

    return DOCUMENT_ID_IN_PATH.sub(replace, path)


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "LOOPBACK_HOSTS",
    "SECURITY_HEADERS",
    "redacted_request_path",
    "sanitized_inline_filename",
    "validate_loopback_host",
    "validate_public_url",
]

"""Fixed-provider HTTPS transport with bounded reads and no document uploads."""

from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime
from datetime import timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler
from urllib.request import Request
from urllib.request import build_opener

MAX_RESPONSE_BYTES = 1_048_576
PROVIDER_HOSTS = frozenset({"api.crossref.org", "api.datacite.org", "openlibrary.org"})


class MetadataLookupError(Exception):
    """A public status without exposing response bodies, proxy URLs or credentials."""

    def __init__(self, status: str, *, retry_after: float | None = None):
        """Retain the distinction between absence, rate limiting and an outage."""
        super().__init__(status)
        self.status = status
        self.retry_after = retry_after


def allowed_url(url: str) -> bool:
    """Allow only the documented read-only API endpoints, including edition redirects."""
    try:
        parsed = urlsplit(url)
        invalid = (
            parsed.scheme != "https"
            or parsed.hostname not in PROVIDER_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port
            or parsed.fragment
        )
    except (ValueError, TypeError):
        return False
    if invalid:
        return False
    if any(segment in {".", ".."} for segment in unquote(parsed.path).split("/")):
        return False
    if parsed.hostname == "api.crossref.org":
        return parsed.path.startswith("/works/")
    if parsed.hostname == "api.datacite.org":
        return parsed.path.startswith("/dois/")
    return bool(
        re.fullmatch(
            r"/(?:isbn/[0-9X]{10,13}|books/OL[0-9]+M|authors/OL[0-9]+A)\.json|/search\.json",
            parsed.path,
        )
    )


def retry_delay(value: str | None, now: datetime | None = None) -> float | None:
    """Honor both Retry-After forms without sleeping indefinitely in the UI."""
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0.0, min(86400.0, seconds)) if math.isfinite(seconds) else None
    except ValueError:
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return max(
                0.0, min(86400.0, (stamp - (now or datetime.now(timezone.utc))).total_seconds())
            )
        except (ValueError, TypeError, OverflowError):
            return None


class ProviderRedirects(HTTPRedirectHandler):
    """Follow Open Library's edition redirect, never a metadata-supplied URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Require the same provider and a documented endpoint after redirect."""
        if not allowed_url(newurl) or urlsplit(newurl).hostname != urlsplit(req.full_url).hostname:
            raise MetadataLookupError("unavailable")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicMetadataHTTP:
    """One GET with an application identity, bounded body and deadline."""

    def __init__(self, *, contact: str = "", clock=time.monotonic):
        """Contact is optional explicit configuration, never read from user documents."""
        if any(char in contact for char in "\r\n") or len(contact) > 200:
            raise ValueError("Invalid metadata contact configuration")
        self.user_agent = "MathMongo/0.13.0 (metadata lookup)" + (
            f" ({contact})" if contact else ""
        )
        self.clock = clock
        self.opener = build_opener(ProviderRedirects())

    def get(self, url: str, *, deadline: float) -> dict:
        """Return JSON data only; never execute remote HTML, JS, TeX or links."""
        if not allowed_url(url):
            raise MetadataLookupError("invalid")
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise MetadataLookupError("unavailable")
        request = Request(
            url, headers={"User-Agent": self.user_agent, "Accept": "application/json"}
        )
        try:
            with self.opener.open(request, timeout=min(5.0, remaining)) as response:
                if "json" not in response.headers.get("Content-Type", "").casefold():
                    raise MetadataLookupError("unavailable")
                body = bytearray()
                while True:
                    if self.clock() >= deadline:
                        raise MetadataLookupError("unavailable")
                    chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - len(body)))
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise MetadataLookupError("unavailable")
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise MetadataLookupError("unavailable")
                return result
        except HTTPError as exc:
            try:
                if exc.code == 404:
                    raise MetadataLookupError("not_found") from None
                if exc.code == 429:
                    raise MetadataLookupError(
                        "rate_limited", retry_after=retry_delay(exc.headers.get("Retry-After"))
                    ) from None
                raise MetadataLookupError("unavailable") from None
            finally:
                exc.close()
        except (URLError, OSError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            raise MetadataLookupError("unavailable") from None

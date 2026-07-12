"""Pure normalization helpers for the Source catalog domain.

The functions in this module do not inspect MongoDB or the filesystem.  They
produce comparison keys only; callers must never interpret a normalized match
as permission to merge records automatically.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

_WHITESPACE_RE = re.compile(r"\s+")
_DOI_PREFIX_RE = re.compile(
    r"^(?:(?:https?://)?(?:dx\.)?doi\.org/|doi\s*:\s*|urn\s*:\s*doi\s*:\s*)",
    re.IGNORECASE,
)
_ISBN_PREFIX_RE = re.compile(r"^isbn(?:-1[03])?\s*:\s*", re.IGNORECASE)
_ISBN_SEPARATORS_RE = re.compile(r"[\s\-\u00ad\u058a\u2010-\u2015\u2212\ufe58\ufe63\uff0d]+")
INVALID_ISBN_WARNING_PREFIX = "Invalid legacy ISBN retained for review:"
MAX_DUPLICATE_REGEX_CHARACTERS = 200


def _latin_equivalents() -> dict[str, tuple[str, ...]]:
    """Build small Latin accent classes for bounded warning-only queries."""
    values: dict[str, set[str]] = {
        chr(code): {chr(code)} for code in range(ord("a"), ord("z") + 1)
    }
    for codepoint in range(0x00C0, 0x0250):
        character = chr(codepoint)
        decomposed = unicodedata.normalize("NFKD", character)
        base = "".join(
            item for item in decomposed if not unicodedata.combining(item)
        ).casefold()
        if len(base) == 1 and base in values and character.isalpha():
            values[base].add(character.casefold())
    return {
        base: tuple(sorted(characters))
        for base, characters in values.items()
    }


_LATIN_EQUIVALENTS = _latin_equivalents()


def clean_text(value: Any) -> str:
    """Return NFKC text with outer and repeated whitespace removed."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return _WHITESPACE_RE.sub(" ", text.strip())


def normalize_source_name(value: Any) -> str:
    """Normalize a Source name for exact catalog lookup."""
    return clean_text(value).casefold()


def normalize_alias(value: Any) -> str:
    """Normalize a Source alias using the same identity rules as names."""
    return normalize_source_name(value)


def normalize_doi(value: Any) -> str | None:
    """Return a DOI comparison key without protocol, host, or ``doi:``."""
    text = clean_text(value)
    if not text:
        return None
    previous = None
    while text != previous:
        previous = text
        text = _DOI_PREFIX_RE.sub("", text, count=1).strip()
    return text.casefold() or None


def normalize_isbn(value: Any) -> str | None:
    """Return an ISBN comparison value while retaining invalid characters.

    Only the conventional ISBN prefix, whitespace, and dash variants are
    removed.  An invalid historical value therefore remains diagnosable
    instead of being converted into a misleading valid-looking identifier.
    """
    text = clean_text(value)
    if not text:
        return None
    text = _ISBN_PREFIX_RE.sub("", text, count=1)
    normalized = _ISBN_SEPARATORS_RE.sub("", text).upper()
    return normalized or None


def is_valid_isbn10(value: Any) -> bool:
    """Validate an ISBN-10 checksum."""
    normalized = normalize_isbn(value)
    if normalized is None or not re.fullmatch(r"\d{9}[\dX]", normalized):
        return False
    digits = [int(char) for char in normalized[:9]]
    check = 10 if normalized[-1] == "X" else int(normalized[-1])
    return sum((10 - index) * digit for index, digit in enumerate((*digits, check))) % 11 == 0


def is_valid_isbn13(value: Any) -> bool:
    """Validate an ISBN-13 checksum."""
    normalized = normalize_isbn(value)
    if normalized is None or not re.fullmatch(r"\d{13}", normalized):
        return False
    digits = [int(char) for char in normalized]
    weighted = sum(digit * (1 if index % 2 == 0 else 3) for index, digit in enumerate(digits[:12]))
    expected = (10 - weighted % 10) % 10
    return digits[-1] == expected


def is_valid_isbn(value: Any) -> bool:
    """Return whether *value* is a checksum-valid ISBN-10 or ISBN-13."""
    return is_valid_isbn10(value) or is_valid_isbn13(value)


@dataclass(frozen=True, slots=True)
class ISBNAnalysis:
    """Pure diagnostic result for one original ISBN value."""

    original: str
    normalized: str | None
    valid: bool
    kind: str | None
    warning: str | None


def analyze_isbn(value: Any) -> ISBNAnalysis:
    """Normalize and validate an ISBN without rejecting legacy input."""
    original = "" if value is None else str(value)
    normalized = normalize_isbn(original)
    valid10 = is_valid_isbn10(normalized)
    valid13 = is_valid_isbn13(normalized)
    valid = valid10 or valid13
    kind = "isbn10" if valid10 else "isbn13" if valid13 else None
    warning = None if valid else f"{INVALID_ISBN_WARNING_PREFIX} {original!r}"
    return ISBNAnalysis(
        original=original,
        normalized=normalized,
        valid=valid,
        kind=kind,
        warning=warning,
    )


def normalize_bibtex_key(value: Any) -> str | None:
    """Return a comparison-only BibTeX key, preserving the raw key elsewhere."""
    text = clean_text(value)
    return text.casefold() or None


def normalize_url(value: Any) -> str | None:
    """Normalize an URL's scheme and host without fetching it."""
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text
    if not parsed.scheme or not parsed.netloc:
        return text

    scheme = parsed.scheme.casefold()
    hostname = parsed.hostname
    if not hostname:
        return text
    host = hostname.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return text
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    netloc = f"{userinfo}{host}"
    return urlunsplit((scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def normalize_author(value: Any) -> str:
    """Return an author comparison string from text or structured metadata."""
    if isinstance(value, Mapping):
        literal = clean_text(value.get("literal"))
        if literal:
            return literal.casefold()
        family = clean_text(value.get("family"))
        given = clean_text(value.get("given"))
        return clean_text(", ".join(part for part in (family, given) if part)).casefold()
    return clean_text(value).casefold()


def normalize_authors(values: Iterable[Any] | Any) -> tuple[str, ...]:
    """Normalize authors in order and remove duplicate comparison values."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes, Mapping)):
        iterable: Iterable[Any] = (values,)
    else:
        try:
            iterable = tuple(values)
        except TypeError:
            iterable = (values,)
    result: list[str] = []
    seen: set[str] = set()
    for value in iterable:
        normalized = normalize_author(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def normalize_title(value: Any) -> str:
    """Return a title comparison value without destructive punctuation rules."""
    return clean_text(value).casefold()


def suggestion_key(value: Any) -> str:
    """Return an accent/punctuation-insensitive key for warnings only."""
    normalized = unicodedata.normalize("NFKD", normalize_title(value))
    parts: list[str] = []
    pending_space = False
    for char in normalized:
        if unicodedata.combining(char):
            continue
        if char.isalnum():
            if pending_space and parts:
                parts.append(" ")
            parts.append(char)
            pending_space = False
        else:
            pending_space = True
    return "".join(parts).strip()


def suggestion_regex_pattern(
    value: Any,
    *,
    max_characters: int = MAX_DUPLICATE_REGEX_CHARACTERS,
) -> str | None:
    """Return a bounded, escaped regex for warning-only suggestion lookup.

    The resulting query tolerates Latin accents and punctuation only. Final
    duplicate classification must still compare ``suggestion_key`` values;
    this pattern merely obtains a bounded server-side candidate set.
    """
    if isinstance(max_characters, bool) or not isinstance(max_characters, int):
        raise TypeError("max_characters must be an integer")
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    key = suggestion_key(value)
    if not key:
        return None
    truncated = len(key) > max_characters
    bounded = key[:max_characters].rstrip()
    pieces: list[str] = []
    for character in bounded:
        if character == " ":
            if not pieces or pieces[-1] != r"[\W_]+":
                pieces.append(r"[\W_]+")
            continue
        equivalents = _LATIN_EQUIVALENTS.get(character)
        if equivalents:
            pieces.append("[" + "".join(re.escape(item) for item in equivalents) + "]")
        else:
            pieces.append(re.escape(character))
    if not pieces:
        return None
    prefix = r"^[\W_]*"
    suffix = "" if truncated else r"[\W_]*$"
    return prefix + "".join(pieces) + suffix


def url_regex_pattern(
    value: Any,
    *,
    max_characters: int = MAX_DUPLICATE_REGEX_CHARACTERS,
) -> str | None:
    """Return a bounded exact-identity URL regex without exposing raw regex."""
    if isinstance(max_characters, bool) or not isinstance(max_characters, int):
        raise TypeError("max_characters must be an integer")
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    normalized = normalize_url(value)
    if not normalized:
        return None
    if len(normalized) > max_characters:
        return "^" + re.escape(normalized[:max_characters])
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        return "^" + re.escape(normalized) + "$"
    if not parsed.scheme or not parsed.netloc:
        return "^" + re.escape(normalized) + "$"
    default_port = "443" if parsed.scheme == "https" else "80" if parsed.scheme == "http" else None
    port_pattern = f"(?::{default_port})?" if default_port and parsed.port is None else ""
    suffix = urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))
    return (
        "^"
        + re.escape(f"{parsed.scheme}://{parsed.netloc}")
        + port_pattern
        + re.escape(suffix)
        + "$"
    )


def author_title_year_fingerprint(
    authors: Iterable[Any] | Any,
    title: Any,
    year: Any,
) -> str | None:
    """Build a stable SHA-256 fingerprint when all three signals exist."""
    normalized_authors = normalize_authors(authors)
    normalized_title = normalize_title(title)
    normalized_year = clean_text(year).casefold()
    if not normalized_authors or not normalized_title or not normalized_year:
        return None
    payload = "\x1f".join(("\x1e".join(normalized_authors), normalized_title, normalized_year))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "INVALID_ISBN_WARNING_PREFIX",
    "ISBNAnalysis",
    "MAX_DUPLICATE_REGEX_CHARACTERS",
    "analyze_isbn",
    "author_title_year_fingerprint",
    "clean_text",
    "is_valid_isbn",
    "is_valid_isbn10",
    "is_valid_isbn13",
    "normalize_alias",
    "normalize_author",
    "normalize_authors",
    "normalize_bibtex_key",
    "normalize_doi",
    "normalize_isbn",
    "normalize_source_name",
    "normalize_title",
    "normalize_url",
    "suggestion_key",
    "suggestion_regex_pattern",
    "url_regex_pattern",
]

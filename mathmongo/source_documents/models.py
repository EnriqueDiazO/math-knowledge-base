"""Strict domain contracts for Source-associated PDF and web documents."""

# ruff: noqa: D101,D102

from __future__ import annotations

import re
from datetime import datetime
from datetime import timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any
from typing import Literal
from urllib.parse import SplitResult
from urllib.parse import urlsplit
from urllib.parse import urlunsplit
from uuid import UUID
from uuid import uuid4

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from mathmongo.source_catalog.models import SourceRights
from mathmongo.source_catalog.models import validate_reference_id
from mathmongo.source_catalog.models import validate_source_id

SOURCE_DOCUMENT_SCHEMA_VERSION = 1
PDF_MIME_TYPE = "application/pdf"
MAX_SOURCE_PDF_UPLOAD_BYTES = 50 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def utc_now() -> datetime:
    """Return an aware UTC timestamp for BSON persistence."""
    return datetime.now(timezone.utc)


def _domain_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def new_document_id() -> str:
    """Return a stable ``doc_<uuid4>`` domain identifier."""
    return _domain_id("doc")


def new_version_id() -> str:
    """Return a stable ``dver_<uuid4>`` version identifier."""
    return _domain_id("dver")


def _validate_id(value: Any, prefix: str) -> str:
    text = str(value or "")
    marker = f"{prefix}_"
    if not text.startswith(marker):
        raise ValueError(f"identifier must start with {marker!r}")
    suffix = text[len(marker) :]
    try:
        parsed = UUID(suffix)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"identifier must contain a UUID v4 after {marker!r}") from exc
    if parsed.version != 4 or str(parsed) != suffix:
        raise ValueError(f"identifier must contain a canonical lowercase UUID v4 after {marker!r}")
    return text


def validate_document_id(value: Any) -> str:
    """Validate a Source document identifier."""
    return _validate_id(value, "doc")


def validate_version_id(value: Any) -> str:
    """Validate a Source document version identifier."""
    return _validate_id(value, "dver")


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _dedupe_tags(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean_text(item)
        folded = text.casefold()
        if text and folded not in seen:
            seen.add(folded)
            result.append(text)
    return result


def normalize_web_url(value: Any) -> str:
    """Normalize an HTTP(S) URL without performing a network request."""
    raw = str(value or "").strip()
    if not raw or any(character.isspace() or ord(character) < 32 for character in raw):
        raise ValueError("web URL cannot be empty or contain whitespace/control characters")
    parsed = urlsplit(raw)
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"}:
        raise ValueError("web URL scheme must be http or https")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("web URL requires a host and cannot contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("web URL contains an invalid port") from exc
    host = parsed.hostname.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    normalized = SplitResult(
        scheme=scheme,
        netloc=netloc,
        path=parsed.path or "/",
        query=parsed.query,
        fragment="",
    )
    return urlunsplit(normalized)


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DocumentKind(str, Enum):
    PDF = "pdf"
    WEB = "web"


class DocumentStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PdfVersion(DocumentModel):
    version_id: str = Field(default_factory=new_version_id, frozen=True)
    version_number: Literal[1] = 1
    sha256: str
    size_bytes: int = Field(gt=0, le=MAX_SOURCE_PDF_UPLOAD_BYTES)
    mime_type: Literal[PDF_MIME_TYPE] = PDF_MIME_TYPE
    logical_path: str
    original_filename: str
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("version_id")
    @classmethod
    def version_id_is_uuid4(cls, value: Any) -> str:
        return validate_version_id(value)

    @field_validator("sha256")
    @classmethod
    def sha_is_canonical(cls, value: Any) -> str:
        text = str(value or "")
        if not SHA256_RE.fullmatch(text):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return text

    @field_validator("original_filename", mode="before")
    @classmethod
    def filename_is_leaf(cls, value: Any) -> str:
        text = _clean_text(value)
        if (
            not text
            or len(text) > 255
            or PurePosixPath(text).name != text
            or "\\" in text
            or not text.casefold().endswith(".pdf")
        ):
            raise ValueError(
                "original_filename must be a PDF leaf filename of at most 255 characters"
            )
        return text

    @field_validator("created_at")
    @classmethod
    def timestamp_is_aware(cls, value: datetime) -> datetime:
        return _aware_utc(value, "created_at")

    @model_validator(mode="after")
    def logical_path_matches_sha(self) -> PdfVersion:
        expected = f"source_documents/blobs/sha256/{self.sha256[:2]}/{self.sha256}.pdf"
        path = PurePosixPath(self.logical_path)
        if path.is_absolute() or path.as_posix() != expected:
            raise ValueError("logical_path must be the canonical content-addressed PDF path")
        return self


class PdfDocument(DocumentModel):
    versions: list[PdfVersion]
    current_version_id: str

    @model_validator(mode="after")
    def one_initial_version_is_current(self) -> PdfDocument:
        if len(self.versions) != 1 or self.versions[0].version_number != 1:
            raise ValueError("S2 PDF documents require exactly versions[0] with version_number=1")
        validate_version_id(self.current_version_id)
        if self.current_version_id != self.versions[0].version_id:
            raise ValueError("current_version_id must identify versions[0]")
        return self

    @property
    def current_version(self) -> PdfVersion:
        return self.versions[0]


class WebDocument(DocumentModel):
    url_raw: str
    url_normalized: str = ""

    @model_validator(mode="after")
    def derive_normalized_url(self) -> WebDocument:
        raw = str(self.url_raw or "").strip()
        normalized = normalize_web_url(raw)
        if self.url_normalized and self.url_normalized != normalized:
            raise ValueError("url_normalized does not match url_raw")
        object.__setattr__(self, "url_raw", raw)
        object.__setattr__(self, "url_normalized", normalized)
        return self


class SourceDocument(DocumentModel):
    schema_version: Literal[SOURCE_DOCUMENT_SCHEMA_VERSION] = SOURCE_DOCUMENT_SCHEMA_VERSION
    document_id: str = Field(default_factory=new_document_id, frozen=True)
    source_id: str
    reference_id: str | None = None
    kind: DocumentKind
    title: str
    description: str = ""
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: DocumentStatus = DocumentStatus.ACTIVE
    rights: SourceRights = Field(default_factory=SourceRights)
    pdf: PdfDocument | None = None
    web: WebDocument | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @field_validator("document_id")
    @classmethod
    def document_id_is_uuid4(cls, value: Any) -> str:
        return validate_document_id(value)

    @field_validator("source_id")
    @classmethod
    def source_id_is_valid(cls, value: Any) -> str:
        return validate_source_id(value)

    @field_validator("reference_id")
    @classmethod
    def reference_id_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_reference_id(value)

    @field_validator("title", mode="before")
    @classmethod
    def title_is_nonempty(cls, value: Any) -> str:
        text = _clean_text(value)
        if not text:
            raise ValueError("title cannot be empty")
        return text

    @field_validator("description", mode="before")
    @classmethod
    def description_is_clean(cls, value: Any) -> str:
        return _clean_text(value)

    @field_validator("language", mode="before")
    @classmethod
    def language_is_optional_clean_text(cls, value: Any) -> str | None:
        return _clean_text(value) or None

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_unique(cls, value: Any) -> list[str]:
        return _dedupe_tags(value)

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def validate_document(self) -> SourceDocument:
        if self.kind == DocumentKind.PDF and (self.pdf is None or self.web is not None):
            raise ValueError("PDF documents require pdf and forbid web")
        if self.kind == DocumentKind.WEB and (self.web is None or self.pdf is not None):
            raise ValueError("web documents require web and forbid pdf")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        archived_at = self.archived_at
        if self.status == DocumentStatus.ARCHIVED and archived_at is None:
            archived_at = self.updated_at
        if self.status == DocumentStatus.ACTIVE and archived_at is not None:
            raise ValueError("active document cannot have archived_at")
        object.__setattr__(self, "archived_at", archived_at)
        return self

    def archived(self, *, at: datetime | None = None) -> SourceDocument:
        if self.status == DocumentStatus.ARCHIVED:
            return self
        timestamp = at or utc_now()
        data = self.model_dump(mode="python")
        data.update(
            {
                "status": DocumentStatus.ARCHIVED,
                "updated_at": timestamp,
                "archived_at": timestamp,
            }
        )
        return SourceDocument.model_validate(data)

    def reactivated(self, *, at: datetime | None = None) -> SourceDocument:
        if self.status == DocumentStatus.ACTIVE and self.archived_at is None:
            return self
        data = self.model_dump(mode="python")
        data.update(
            {
                "status": DocumentStatus.ACTIVE,
                "updated_at": at or utc_now(),
                "archived_at": None,
            }
        )
        return SourceDocument.model_validate(data)

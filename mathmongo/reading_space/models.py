"""Strict persistent contracts for per-document reading state."""

# ruff: noqa: D101,D102

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any
from typing import Literal
from uuid import UUID
from uuid import uuid4

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from mathmongo.source_catalog.models import validate_reference_id
from mathmongo.source_catalog.models import validate_source_id
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import validate_document_id

READING_STATE_SCHEMA_VERSION = 1
LOCAL_USER_SCOPE = "local"
MAX_READING_TAGS = 50
MAX_READING_TAG_CHARS = 100
MAX_USER_SCOPE_CHARS = 128
MAX_TITLE_QUERY_CHARS = 200


def utc_now() -> datetime:
    """Return an aware UTC timestamp for BSON persistence."""
    return datetime.now(timezone.utc)


def new_reading_state_id() -> str:
    """Return a stable ``read_<uuid4>`` identifier."""
    return f"read_{uuid4()}"


def validate_reading_state_id(value: Any) -> str:
    """Validate a canonical lowercase UUID-v4 reading-state identifier."""
    text = str(value or "")
    marker = "read_"
    if not text.startswith(marker):
        raise ValueError("reading_state_id must start with 'read_'")
    suffix = text[len(marker) :]
    try:
        parsed = UUID(suffix)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("reading_state_id must contain a UUID v4 after 'read_'") from exc
    if parsed.version != 4 or str(parsed) != suffix:
        raise ValueError("reading_state_id must contain a canonical lowercase UUID v4")
    return text


def validate_user_scope(value: Any) -> str:
    """Validate one bounded opaque user scope; S3 uses ``local``."""
    text = " ".join(str(value or "").strip().split())
    if not text or len(text) > MAX_USER_SCOPE_CHARS:
        raise ValueError(f"user_scope must contain 1 to {MAX_USER_SCOPE_CHARS} characters")
    if any(ord(character) < 32 for character in text):
        raise ValueError("user_scope cannot contain control characters")
    return text


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _reading_tags(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean_text(item)
        if not text:
            continue
        if len(text) > MAX_READING_TAG_CHARS:
            raise ValueError(f"reading tags cannot exceed {MAX_READING_TAG_CHARS} characters")
        folded = text.casefold()
        if folded not in seen:
            seen.add(folded)
            result.append(text)
    if len(result) > MAX_READING_TAGS:
        raise ValueError(f"reading state cannot contain more than {MAX_READING_TAGS} tags")
    return result


class ReadingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ReadingStatus(str, Enum):
    UNREAD = "unread"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"


class ReadingSort(str, Enum):
    RECENT = "recent"
    TITLE = "title"
    SOURCE = "source"
    STATUS = "status"


class DocumentReadingState(ReadingModel):
    schema_version: Literal[READING_STATE_SCHEMA_VERSION] = READING_STATE_SCHEMA_VERSION
    reading_state_id: str = Field(default_factory=new_reading_state_id, frozen=True)
    document_id: str = Field(frozen=True)
    source_id: str = Field(frozen=True)
    reference_id: str | None = None
    user_scope: str = Field(default=LOCAL_USER_SCOPE, frozen=True)
    status: ReadingStatus = ReadingStatus.UNREAD
    current_page: int | None = Field(default=None, ge=1)
    total_pages: int | None = Field(default=None, ge=1)
    last_opened_at: datetime | None = None
    first_opened_at: datetime | None = None
    completed_at: datetime | None = None
    open_count: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("reading_state_id")
    @classmethod
    def reading_state_id_is_uuid4(cls, value: Any) -> str:
        return validate_reading_state_id(value)

    @field_validator("document_id")
    @classmethod
    def document_id_is_valid(cls, value: Any) -> str:
        return validate_document_id(value)

    @field_validator("source_id")
    @classmethod
    def source_id_is_valid(cls, value: Any) -> str:
        return validate_source_id(value)

    @field_validator("reference_id")
    @classmethod
    def reference_id_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_reference_id(value)

    @field_validator("user_scope", mode="before")
    @classmethod
    def user_scope_is_bounded(cls, value: Any) -> str:
        return validate_user_scope(value)

    @field_validator("current_page", "total_pages", "open_count", mode="before")
    @classmethod
    def integers_are_strict(cls, value: Any) -> Any:
        if value is not None and type(value) is not int:
            raise ValueError("reading counters and pages must be strict integers")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_clean_and_unique(cls, value: Any) -> list[str]:
        return _reading_tags(value)

    @field_validator(
        "last_opened_at",
        "first_opened_at",
        "completed_at",
        "created_at",
        "updated_at",
    )
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def state_is_consistent(self) -> DocumentReadingState:
        if (
            self.current_page is not None
            and self.total_pages is not None
            and self.current_page > self.total_pages
        ):
            raise ValueError("current_page cannot exceed total_pages")
        if self.completed_at is not None and self.status != ReadingStatus.COMPLETED:
            raise ValueError("completed_at is only allowed when status is completed")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if (
            self.first_opened_at is not None
            and self.last_opened_at is not None
            and self.last_opened_at < self.first_opened_at
        ):
            raise ValueError("last_opened_at cannot be earlier than first_opened_at")
        return self


class ReadingDocumentFilters(ReadingModel):
    source_id: str | None = None
    reference_id: str | None = None
    kind: DocumentKind | None = None
    document_status: DocumentStatus | None = None
    reading_status: ReadingStatus | None = None
    tags: list[str] = Field(default_factory=list)
    title_query: str = ""
    order: ReadingSort = ReadingSort.RECENT

    @field_validator("source_id")
    @classmethod
    def source_filter_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_source_id(value)

    @field_validator("reference_id")
    @classmethod
    def reference_filter_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_reference_id(value)

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_clean_and_unique(cls, value: Any) -> list[str]:
        return _reading_tags(value)

    @field_validator("title_query", mode="before")
    @classmethod
    def title_query_is_bounded(cls, value: Any) -> str:
        text = _clean_text(value)
        if len(text) > MAX_TITLE_QUERY_CHARS:
            raise ValueError(f"title_query cannot exceed {MAX_TITLE_QUERY_CHARS} characters")
        return text


__all__ = [
    "DocumentReadingState",
    "LOCAL_USER_SCOPE",
    "READING_STATE_SCHEMA_VERSION",
    "ReadingDocumentFilters",
    "ReadingSort",
    "ReadingStatus",
    "new_reading_state_id",
    "utc_now",
    "validate_reading_state_id",
    "validate_user_scope",
]

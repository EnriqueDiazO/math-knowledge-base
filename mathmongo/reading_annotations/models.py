"""Strict S4 contracts for annotations, reading notes, and concept evidence."""

# ruff: noqa: D101,D102,D103

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
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

from mathmongo.reading_space.models import LOCAL_USER_SCOPE
from mathmongo.source_catalog.models import validate_reference_id
from mathmongo.source_catalog.models import validate_source_id
from mathmongo.source_documents.models import validate_document_id
from mathmongo.source_documents.models import validate_version_id

READING_ANNOTATION_SCHEMA_VERSION = 1
VISUAL_ANNOTATION_SCHEMA_VERSION = 2
VISUAL_ANCHOR_SCHEMA_VERSION = 1
MAX_ANNOTATION_TAGS = 50
MAX_ANNOTATION_TAG_CHARS = 100
MAX_BODY_CHARS = 100_000
MAX_QUOTE_CHARS = 20_000
MAX_TITLE_CHARS = 500
MAX_SHORT_TEXT_CHARS = 500
MAX_CONCEPT_ID_CHARS = 500
MAX_CONCEPT_SOURCE_CHARS = 1_000
MAX_SEARCH_QUERY_CHARS = 200
MAX_VISUAL_QUOTE_CHARS = 4_096
MAX_VISUAL_RECTS = 64
VISUAL_RECT_BOUNDARY_TOLERANCE = 1e-9
VISUAL_ANNOTATION_COLORS = frozenset({"yellow", "green", "blue", "pink", "purple"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HTML_MARKUP_RE = re.compile(
    r"<!--[\s\S]*?-->|<!DOCTYPE\s+[^>]*>|</?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*)?/?>",
    flags=re.IGNORECASE,
)


def utc_now() -> datetime:
    """Return an aware UTC timestamp for BSON persistence."""
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def new_annotation_id() -> str:
    return _new_id("ann")


def new_note_id() -> str:
    return _new_id("note")


def new_evidence_link_id() -> str:
    return _new_id("ev")


def _validate_id(value: Any, prefix: str, field_name: str) -> str:
    text = str(value or "")
    marker = f"{prefix}_"
    if not text.startswith(marker):
        raise ValueError(f"{field_name} must start with {marker!r}")
    suffix = text[len(marker) :]
    try:
        parsed = UUID(suffix)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain a UUID v4 after {marker!r}") from exc
    if parsed.version != 4 or str(parsed) != suffix:
        raise ValueError(f"{field_name} must contain a canonical lowercase UUID v4")
    return text


def validate_annotation_id(value: Any) -> str:
    return _validate_id(value, "ann", "annotation_id")


def validate_note_id(value: Any) -> str:
    return _validate_id(value, "note", "note_id")


def validate_evidence_link_id(value: Any) -> str:
    return _validate_id(value, "ev", "evidence_link_id")


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _text(value: Any, *, required: bool, maximum: int, field_name: str) -> str:
    if isinstance(value, bytes):
        raise ValueError(f"{field_name} must be text, not bytes")
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field_name} cannot be empty")
    if len(text) > maximum:
        raise ValueError(f"{field_name} cannot exceed {maximum} characters")
    if any(character == "\x00" for character in text):
        raise ValueError(f"{field_name} cannot contain NUL characters")
    return text


def _optional_text(value: Any, *, maximum: int, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, required=False, maximum=maximum, field_name=field_name) or None


def _legacy_identity_text(value: Any, *, maximum: int, field_name: str) -> str:
    """Validate one opaque legacy identity without normalizing exact whitespace."""
    if isinstance(value, bytes):
        raise ValueError(f"{field_name} must be text, not bytes")
    text = str(value) if value is not None else ""
    if not text.strip():
        raise ValueError(f"{field_name} cannot be empty")
    if len(text) > maximum:
        raise ValueError(f"{field_name} cannot exceed {maximum} characters")
    if "\x00" in text:
        raise ValueError(f"{field_name} cannot contain NUL characters")
    return text


def _tags(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _text(
            item,
            required=False,
            maximum=MAX_ANNOTATION_TAG_CHARS,
            field_name="tag",
        )
        folded = text.casefold()
        if text and folded not in seen:
            seen.add(folded)
            result.append(text)
    if len(result) > MAX_ANNOTATION_TAGS:
        raise ValueError(f"tags cannot contain more than {MAX_ANNOTATION_TAGS} values")
    return result


def _strict_page(value: Any) -> Any:
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError("page values must be strict integers")
    return value


class ReadingAnnotationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AnnotationKind(str, Enum):
    HIGHLIGHT = "highlight"
    UNDERLINE = "underline"
    COMMENT = "comment"
    BOOKMARK = "bookmark"
    QUESTION = "question"


class AnnotationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReadingNoteType(str, Enum):
    SUMMARY = "summary"
    IDEA = "idea"
    PROOF = "proof"
    DEFINITION = "definition"
    QUESTION = "question"
    TODO = "todo"
    BIBLIOGRAPHY = "bibliography"
    GENERAL = "general"


class ReadingNoteStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class EvidenceLinkType(str, Enum):
    DEFINITION_SOURCE = "definition_source"
    THEOREM_SOURCE = "theorem_source"
    PROOF_SOURCE = "proof_source"
    EXAMPLE_SOURCE = "example_source"
    MOTIVATION = "motivation"
    CITATION = "citation"
    QUESTION = "question"
    RELATED_CONTEXT = "related_context"


class EvidenceLinkStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


def normalize_visual_quote_text(value: Any) -> str:
    """Normalize the one persisted visual quote before hashing it."""
    if not isinstance(value, str):
        raise ValueError("visual quote_text must be Unicode text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("visual quote_text must contain valid Unicode") from exc
    if "\x00" in value:
        raise ValueError("visual quote_text cannot contain NUL characters")
    if HTML_MARKUP_RE.search(value):
        raise ValueError("visual quote_text must be plain text without HTML markup")
    normalized = re.sub(r"\s+", " ", value, flags=re.UNICODE).strip()
    if not normalized:
        raise ValueError("visual quote_text cannot be empty")
    if len(normalized) > MAX_VISUAL_QUOTE_CHARS:
        raise ValueError(f"visual quote_text cannot exceed {MAX_VISUAL_QUOTE_CHARS} characters")
    return normalized


def visual_text_sha256(value: Any) -> str:
    """Hash the canonical UTF-8 representation of one visual quote."""
    normalized = normalize_visual_quote_text(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class NormalizedVisualRect(ReadingAnnotationModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x: float
    y: float
    width: float
    height: float

    @field_validator("x", "y", "width", "height", mode="before")
    @classmethod
    def coordinates_are_finite_numbers(cls, value: Any, info: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{info.field_name} must be a finite number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{info.field_name} must be finite")
        return number

    @model_validator(mode="after")
    def rectangle_is_normalized(self) -> NormalizedVisualRect:
        if not 0 <= self.x <= 1 or not 0 <= self.y <= 1:
            raise ValueError("visual rectangle x and y must be between 0 and 1")
        if not 0 < self.width <= 1 or not 0 < self.height <= 1:
            raise ValueError(
                "visual rectangle width and height must be greater than 0 and at most 1"
            )
        if self.x + self.width > 1 + VISUAL_RECT_BOUNDARY_TOLERANCE:
            raise ValueError("visual rectangle exceeds the horizontal page boundary")
        if self.y + self.height > 1 + VISUAL_RECT_BOUNDARY_TOLERANCE:
            raise ValueError("visual rectangle exceeds the vertical page boundary")
        return self


class VisualAnnotationAnchor(ReadingAnnotationModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    anchor_schema_version: Literal[1] = VISUAL_ANCHOR_SCHEMA_VERSION
    version_id: str
    document_sha256: str
    pdf_page: int = Field(ge=1)
    coordinate_space: Literal["normalized_unrotated_crop_box"] = "normalized_unrotated_crop_box"
    capture_rotation: Literal[0, 90, 180, 270]
    rects: tuple[NormalizedVisualRect, ...]
    text_sha256: str
    created_from: Literal["pdfjs_text_selection"] = "pdfjs_text_selection"

    @field_validator("anchor_schema_version", mode="before")
    @classmethod
    def anchor_version_is_exact(cls, value: Any) -> int:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value != VISUAL_ANCHOR_SCHEMA_VERSION
        ):
            raise ValueError("anchor_schema_version must be exactly 1")
        return value

    @field_validator("version_id")
    @classmethod
    def version_id_is_valid(cls, value: Any) -> str:
        return validate_version_id(value)

    @field_validator("document_sha256", "text_sha256")
    @classmethod
    def hashes_are_canonical(cls, value: Any, info: Any) -> str:
        text = str(value or "")
        if not SHA256_RE.fullmatch(text):
            raise ValueError(f"{info.field_name} must be 64 lowercase hexadecimal characters")
        return text

    @field_validator("pdf_page", mode="before")
    @classmethod
    def pdf_page_is_strict(cls, value: Any) -> Any:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("pdf_page must be a strict integer")
        return value

    @field_validator("capture_rotation", mode="before")
    @classmethod
    def rotation_is_strict(cls, value: Any) -> Any:
        if not isinstance(value, int) or isinstance(value, bool) or value not in {0, 90, 180, 270}:
            raise ValueError("capture_rotation must be 0, 90, 180, or 270")
        return value

    @field_validator("rects", mode="before")
    @classmethod
    def rectangles_are_bounded(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise ValueError("rects must be a list or tuple")
        if not 1 <= len(value) <= MAX_VISUAL_RECTS:
            raise ValueError(f"rects must contain between 1 and {MAX_VISUAL_RECTS} rectangles")
        return value


class DocumentAnnotation(ReadingAnnotationModel):
    schema_version: Literal[1, 2] = READING_ANNOTATION_SCHEMA_VERSION
    annotation_id: str = Field(default_factory=new_annotation_id, frozen=True)
    document_id: str = Field(frozen=True)
    source_id: str = Field(frozen=True)
    reference_id: str | None = Field(default=None, frozen=True)
    user_scope: Literal[LOCAL_USER_SCOPE] = Field(default=LOCAL_USER_SCOPE, frozen=True)
    kind: AnnotationKind
    status: AnnotationStatus = AnnotationStatus.ACTIVE
    page_number: int | None = Field(default=None, ge=1)
    page_label: str | None = None
    quote_text: str | None = None
    body: str = ""
    color_label: str | None = None
    tags: list[str] = Field(default_factory=list)
    visual_anchor: VisualAnnotationAnchor | None = Field(default=None, frozen=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def visual_quote_is_normalized_before_generic_bounds(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        if value.get("schema_version", READING_ANNOTATION_SCHEMA_VERSION) != 2:
            return value
        if value.get("visual_anchor") is None:
            return value
        normalized = dict(value)
        normalized["quote_text"] = normalize_visual_quote_text(value.get("quote_text"))
        return normalized

    @field_validator("annotation_id")
    @classmethod
    def annotation_id_is_valid(cls, value: Any) -> str:
        return validate_annotation_id(value)

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_exact(cls, value: Any) -> int:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value
            not in {
                READING_ANNOTATION_SCHEMA_VERSION,
                VISUAL_ANNOTATION_SCHEMA_VERSION,
            }
        ):
            raise ValueError("schema_version must be exactly 1 or 2")
        return value

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

    @field_validator("page_number", mode="before")
    @classmethod
    def page_is_strict(cls, value: Any) -> Any:
        return _strict_page(value)

    @field_validator("page_label", "color_label", mode="before")
    @classmethod
    def short_text_is_bounded(cls, value: Any, info: Any) -> str | None:
        return _optional_text(value, maximum=MAX_SHORT_TEXT_CHARS, field_name=info.field_name)

    @field_validator("quote_text", mode="before")
    @classmethod
    def quote_is_bounded(cls, value: Any) -> str | None:
        return _optional_text(value, maximum=MAX_QUOTE_CHARS, field_name="quote_text")

    @field_validator("body", mode="before")
    @classmethod
    def body_is_bounded(cls, value: Any) -> str:
        return _text(value, required=False, maximum=MAX_BODY_CHARS, field_name="body")

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_bounded(cls, value: Any) -> list[str]:
        return _tags(value)

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def annotation_is_consistent(self) -> DocumentAnnotation:
        if self.schema_version == READING_ANNOTATION_SCHEMA_VERSION:
            if self.visual_anchor is not None:
                raise ValueError("schema_version=1 annotations cannot contain visual_anchor")
        elif self.visual_anchor is not None:
            if self.kind not in {AnnotationKind.HIGHLIGHT, AnnotationKind.UNDERLINE}:
                raise ValueError("visual annotations must be highlights or underlines")
            if self.page_number is None or self.page_number != self.visual_anchor.pdf_page:
                raise ValueError("visual annotation page_number must match visual_anchor.pdf_page")
            if not isinstance(self.quote_text, str) or not self.quote_text.strip():
                raise ValueError("visual quote_text cannot be empty")
            normalized_quote = normalize_visual_quote_text(self.quote_text)
            if visual_text_sha256(normalized_quote) != self.visual_anchor.text_sha256:
                raise ValueError("visual annotation quote_text does not match text_sha256")
            color_label = self.color_label or "yellow"
            if color_label not in VISUAL_ANNOTATION_COLORS:
                raise ValueError("visual annotation color_label is not in the approved palette")
            object.__setattr__(self, "quote_text", normalized_quote)
            object.__setattr__(self, "color_label", color_label)
        if self.kind in {AnnotationKind.COMMENT, AnnotationKind.QUESTION} and not self.body:
            raise ValueError("body is required for comment and question annotations")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        archived_at = self.archived_at
        if self.status == AnnotationStatus.ARCHIVED and archived_at is None:
            archived_at = self.updated_at
        if self.status == AnnotationStatus.ACTIVE and archived_at is not None:
            raise ValueError("active annotation cannot have archived_at")
        if archived_at is not None and not self.created_at <= archived_at <= self.updated_at:
            raise ValueError("annotation archived_at must be between created_at and updated_at")
        object.__setattr__(self, "archived_at", archived_at)
        return self


class ReadingNote(ReadingAnnotationModel):
    schema_version: Literal[READING_ANNOTATION_SCHEMA_VERSION] = READING_ANNOTATION_SCHEMA_VERSION
    note_id: str = Field(default_factory=new_note_id, frozen=True)
    document_id: str | None = Field(default=None, frozen=True)
    source_id: str = Field(frozen=True)
    reference_id: str | None = Field(default=None, frozen=True)
    user_scope: Literal[LOCAL_USER_SCOPE] = Field(default=LOCAL_USER_SCOPE, frozen=True)
    title: str
    body: str
    note_type: ReadingNoteType = ReadingNoteType.GENERAL
    status: ReadingNoteStatus = ReadingNoteStatus.ACTIVE
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @field_validator("note_id")
    @classmethod
    def note_id_is_valid(cls, value: Any) -> str:
        return validate_note_id(value)

    @field_validator("document_id")
    @classmethod
    def document_id_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_document_id(value)

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
    def title_is_required(cls, value: Any) -> str:
        return _text(value, required=True, maximum=MAX_TITLE_CHARS, field_name="title")

    @field_validator("body", mode="before")
    @classmethod
    def body_is_required(cls, value: Any) -> str:
        return _text(value, required=True, maximum=MAX_BODY_CHARS, field_name="body")

    @field_validator("page_start", "page_end", mode="before")
    @classmethod
    def pages_are_strict(cls, value: Any) -> Any:
        return _strict_page(value)

    @field_validator("tags", mode="before")
    @classmethod
    def tags_are_bounded(cls, value: Any) -> list[str]:
        return _tags(value)

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def note_is_consistent(self) -> ReadingNote:
        if self.page_end is not None and self.page_start is None:
            raise ValueError("page_start is required when page_end is provided")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_start > self.page_end
        ):
            raise ValueError("page_start cannot exceed page_end")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        archived_at = self.archived_at
        if self.status == ReadingNoteStatus.ARCHIVED and archived_at is None:
            archived_at = self.updated_at
        if self.status == ReadingNoteStatus.ACTIVE and archived_at is not None:
            raise ValueError("active reading note cannot have archived_at")
        if archived_at is not None and not self.created_at <= archived_at <= self.updated_at:
            raise ValueError("reading note archived_at must be between created_at and updated_at")
        object.__setattr__(self, "archived_at", archived_at)
        return self


class ConceptEvidenceLink(ReadingAnnotationModel):
    schema_version: Literal[READING_ANNOTATION_SCHEMA_VERSION] = READING_ANNOTATION_SCHEMA_VERSION
    evidence_link_id: str = Field(default_factory=new_evidence_link_id, frozen=True)
    concept_legacy_id: str
    concept_legacy_source: str
    source_id: str = Field(frozen=True)
    reference_id: str | None = Field(default=None, frozen=True)
    document_id: str | None = Field(default=None, frozen=True)
    annotation_id: str | None = Field(default=None, frozen=True)
    note_id: str | None = Field(default=None, frozen=True)
    page_number: int | None = Field(default=None, ge=1, frozen=True)
    link_type: EvidenceLinkType
    status: EvidenceLinkStatus = EvidenceLinkStatus.ACTIVE
    comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @field_validator("evidence_link_id")
    @classmethod
    def evidence_link_id_is_valid(cls, value: Any) -> str:
        return validate_evidence_link_id(value)

    @field_validator("concept_legacy_id", mode="before")
    @classmethod
    def concept_id_is_bounded(cls, value: Any) -> str:
        return _legacy_identity_text(
            value,
            maximum=MAX_CONCEPT_ID_CHARS,
            field_name="concept_legacy_id",
        )

    @field_validator("concept_legacy_source", mode="before")
    @classmethod
    def concept_source_is_bounded(cls, value: Any) -> str:
        return _legacy_identity_text(
            value,
            maximum=MAX_CONCEPT_SOURCE_CHARS,
            field_name="concept_legacy_source",
        )

    @field_validator("source_id")
    @classmethod
    def source_id_is_valid(cls, value: Any) -> str:
        return validate_source_id(value)

    @field_validator("reference_id")
    @classmethod
    def reference_id_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_reference_id(value)

    @field_validator("document_id")
    @classmethod
    def document_id_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_document_id(value)

    @field_validator("annotation_id")
    @classmethod
    def annotation_id_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_annotation_id(value)

    @field_validator("note_id")
    @classmethod
    def note_id_is_valid(cls, value: Any) -> str | None:
        return None if value is None else validate_note_id(value)

    @field_validator("page_number", mode="before")
    @classmethod
    def page_is_strict(cls, value: Any) -> Any:
        return _strict_page(value)

    @field_validator("comment", mode="before")
    @classmethod
    def comment_is_bounded(cls, value: Any) -> str | None:
        return _optional_text(value, maximum=MAX_BODY_CHARS, field_name="comment")

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def evidence_is_consistent(self) -> ConceptEvidenceLink:
        indirect_targets = int(self.annotation_id is not None) + int(self.note_id is not None)
        direct_target = self.document_id is not None or self.page_number is not None
        if indirect_targets:
            if indirect_targets != 1 or direct_target:
                raise ValueError(
                    "evidence requires exactly one target: annotation_id, note_id, or "
                    "document_id with page_number"
                )
        elif self.document_id is None or self.page_number is None:
            raise ValueError("direct evidence requires both document_id and page_number")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        archived_at = self.archived_at
        if self.status == EvidenceLinkStatus.ARCHIVED and archived_at is None:
            archived_at = self.updated_at
        if self.status == EvidenceLinkStatus.ACTIVE and archived_at is not None:
            raise ValueError("active evidence link cannot have archived_at")
        if archived_at is not None and not self.created_at <= archived_at <= self.updated_at:
            raise ValueError("evidence archived_at must be between created_at and updated_at")
        object.__setattr__(self, "archived_at", archived_at)
        return self


__all__ = [
    "AnnotationKind",
    "AnnotationStatus",
    "ConceptEvidenceLink",
    "DocumentAnnotation",
    "EvidenceLinkStatus",
    "EvidenceLinkType",
    "LOCAL_USER_SCOPE",
    "MAX_SEARCH_QUERY_CHARS",
    "MAX_VISUAL_QUOTE_CHARS",
    "MAX_VISUAL_RECTS",
    "NormalizedVisualRect",
    "READING_ANNOTATION_SCHEMA_VERSION",
    "ReadingNote",
    "ReadingNoteStatus",
    "ReadingNoteType",
    "VISUAL_ANCHOR_SCHEMA_VERSION",
    "VISUAL_ANNOTATION_COLORS",
    "VISUAL_ANNOTATION_SCHEMA_VERSION",
    "VisualAnnotationAnchor",
    "new_annotation_id",
    "new_evidence_link_id",
    "new_note_id",
    "normalize_visual_quote_text",
    "utc_now",
    "validate_annotation_id",
    "validate_evidence_link_id",
    "validate_note_id",
    "visual_text_sha256",
]

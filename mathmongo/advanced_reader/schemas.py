"""Bounded HTTP transport schemas for the isolated Advanced Reader."""

# ruff: noqa: D101,D102

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from mathmongo.reading_annotations.models import MAX_ANNOTATION_TAG_CHARS
from mathmongo.reading_annotations.models import MAX_ANNOTATION_TAGS
from mathmongo.reading_annotations.models import MAX_BODY_CHARS
from mathmongo.reading_annotations.models import MAX_VISUAL_QUOTE_CHARS
from mathmongo.reading_annotations.models import NormalizedVisualRect
from mathmongo.reading_annotations.models import normalize_visual_quote_text
from mathmongo.reading_annotations.models import validate_annotation_id
from mathmongo.source_documents.models import SHA256_RE
from mathmongo.source_documents.models import validate_version_id


class TransportModel(BaseModel):
    """Reject transport fields that are not part of the public contract."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(TransportModel):
    status: Literal["ok"] = "ok"
    service: Literal["mathmongo-advanced-reader"] = "mathmongo-advanced-reader"
    database: str
    frontend_ready: bool


class ApiErrorDetail(TransportModel):
    code: str
    message: str
    request_id: str


class ApiErrorResponse(TransportModel):
    error: ApiErrorDetail


class SourceSummary(TransportModel):
    source_id: str
    name: str


class ReferenceSummary(TransportModel):
    reference_id: str
    title: str


class VersionSummary(TransportModel):
    version_id: str
    sha256: str
    size_bytes: int
    original_filename: str


class ReadingStateSummary(TransportModel):
    status: str
    current_page: int | None = None
    total_pages: int | None = None
    last_opened_at: datetime | None = None


class PageLabelResponse(TransportModel):
    pdf_page: int
    book_page_label: str | None = None
    display_label: str


class ReaderCapabilities(TransportModel):
    page_navigation: Literal[True] = True
    thumbnails: Literal[True] = True
    zoom: Literal[True] = True
    rotate: Literal[True] = True
    text_search: Literal[True] = True
    text_selection: Literal[True] = True
    temporary_selection_geometry: Literal[True] = True
    persistent_highlights: bool = False
    persistent_underlines: bool = False
    visual_annotation_editing: bool = False
    visual_annotation_archiving: bool = False
    concept_linking: Literal[False] = False


class DocumentMetadataResponse(TransportModel):
    document_id: str
    title: str
    kind: Literal["pdf"] = "pdf"
    status: str
    source: SourceSummary
    reference: ReferenceSummary | None = None
    version: VersionSummary
    reading_state: ReadingStateSummary
    page_label: PageLabelResponse
    integrity: Literal["ok"] = "ok"
    capabilities: ReaderCapabilities = Field(default_factory=ReaderCapabilities)


class ReadingStateResponse(TransportModel):
    document_id: str
    status: str
    current_page: int | None = None
    total_pages: int | None = None
    last_opened_at: datetime | None = None


class ReadingPageUpdate(TransportModel):
    pdf_page: Annotated[int, Field(strict=True, ge=1)]


VisualKind = Literal["highlight", "underline"]
VisualColor = Literal["yellow", "green", "blue", "pink", "purple"]
VisualCompatibility = Literal["exact", "version_mismatch", "invalid_geometry", "logical_only"]


class VisualAnnotationCreate(TransportModel):
    annotation_id: str
    version_id: str
    document_sha256: str
    pdf_page: Annotated[int, Field(strict=True, ge=1)]
    kind: VisualKind
    quote_text: str
    rects: Annotated[list[NormalizedVisualRect], Field(min_length=1, max_length=64)]
    capture_rotation: Literal[0, 90, 180, 270]
    color_label: VisualColor = "yellow"
    body: Annotated[str, Field(max_length=MAX_BODY_CHARS)] = ""
    tags: Annotated[list[str], Field(max_length=MAX_ANNOTATION_TAGS)] = Field(default_factory=list)

    @field_validator("annotation_id")
    @classmethod
    def annotation_identity_is_valid(cls, value: str) -> str:
        return validate_annotation_id(value)

    @field_validator("version_id")
    @classmethod
    def version_identity_is_valid(cls, value: str) -> str:
        return validate_version_id(value)

    @field_validator("document_sha256")
    @classmethod
    def document_hash_is_canonical(cls, value: str) -> str:
        if not SHA256_RE.fullmatch(value):
            raise ValueError("document_sha256 must be lowercase SHA-256")
        return value

    @field_validator("capture_rotation", mode="before")
    @classmethod
    def capture_rotation_is_a_strict_integer(cls, value: object) -> object:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("capture_rotation must be a strict integer")
        return value

    @field_validator("quote_text")
    @classmethod
    def quote_is_normalized_and_bounded(cls, value: str) -> str:
        normalized = normalize_visual_quote_text(value)
        if len(normalized) > MAX_VISUAL_QUOTE_CHARS:
            raise ValueError("quote_text is too long")
        return normalized

    @field_validator("body")
    @classmethod
    def body_has_no_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("body cannot contain NUL characters")
        return value

    @field_validator("tags")
    @classmethod
    def tags_are_bounded(cls, value: list[str]) -> list[str]:
        if any(
            not isinstance(tag, str)
            or not tag.strip()
            or len(tag.strip()) > MAX_ANNOTATION_TAG_CHARS
            or "\x00" in tag
            for tag in value
        ):
            raise ValueError("tags contain an invalid value")
        return value


class VisualAnnotationUpdate(TransportModel):
    kind: VisualKind | None = None
    color_label: VisualColor | None = None
    body: Annotated[str, Field(max_length=MAX_BODY_CHARS)] | None = None
    tags: Annotated[list[str], Field(max_length=MAX_ANNOTATION_TAGS)] | None = None

    @field_validator("body")
    @classmethod
    def body_has_no_nul(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("body cannot contain NUL characters")
        return value

    @field_validator("tags")
    @classmethod
    def tags_are_bounded(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(
            not isinstance(tag, str)
            or not tag.strip()
            or len(tag.strip()) > MAX_ANNOTATION_TAG_CHARS
            or "\x00" in tag
            for tag in value
        ):
            raise ValueError("tags contain an invalid value")
        return value

    @model_validator(mode="after")
    def contains_one_edit(self) -> VisualAnnotationUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one presentation field is required")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("presentation fields cannot be null")
        return self


class VisualAnnotationLifecycle(TransportModel):
    """Require one valid, field-free JSON object for lifecycle writes."""


class VisualAnchorResponse(TransportModel):
    version_id: str
    document_sha256: str
    coordinate_space: Literal["normalized_unrotated_crop_box"]
    capture_rotation: Literal[0, 90, 180, 270]
    rects: list[NormalizedVisualRect]


class VisualAnnotationResponse(TransportModel):
    annotation_id: str
    document_id: str
    kind: VisualKind
    status: Literal["active", "archived"]
    pdf_page: int
    page_label: str | None = None
    quote_text: str
    body: str
    color_label: str | None = None
    tags: list[str]
    visual_status: VisualCompatibility
    visual_anchor: VisualAnchorResponse
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class VisualAnnotationListResponse(TransportModel):
    items: list[VisualAnnotationResponse]
    page: int
    page_size: int
    total: int
    pages: int


__all__ = [
    "ApiErrorDetail",
    "ApiErrorResponse",
    "DocumentMetadataResponse",
    "HealthResponse",
    "PageLabelResponse",
    "ReaderCapabilities",
    "ReadingPageUpdate",
    "ReadingStateResponse",
    "ReadingStateSummary",
    "ReferenceSummary",
    "SourceSummary",
    "VersionSummary",
    "VisualAnchorResponse",
    "VisualAnnotationCreate",
    "VisualAnnotationListResponse",
    "VisualAnnotationLifecycle",
    "VisualAnnotationResponse",
    "VisualAnnotationUpdate",
]

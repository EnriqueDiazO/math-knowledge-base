"""Bounded HTTP transport schemas for the isolated Advanced Reader."""

# ruff: noqa: D101

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


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
    persistent_highlights: Literal[False] = False
    persistent_underlines: Literal[False] = False
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
]

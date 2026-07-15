"""Bounded transport contracts for S5C visual concept linking."""

# ruff: noqa: D101,D102

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from typing import Literal

from pydantic import Field
from pydantic import field_validator

from mathmongo.advanced_reader.schemas import TransportModel
from mathmongo.reading_annotations.models import MAX_BODY_CHARS
from mathmongo.reading_annotations.models import EvidenceLinkType
from mathmongo.reading_annotations.models import validate_evidence_link_id


class ConceptSummaryResponse(TransportModel):
    concept_legacy_id: str
    concept_legacy_source: str
    title: str
    concept_type: str
    categories: list[str]
    tags: list[str]
    evidence_count: int | None = None
    evidence_in_document_count: int | None = None
    warning: Literal["concept_not_found"] | None = None


class ConceptSearchResponse(TransportModel):
    items: list[ConceptSummaryResponse]
    page: int
    page_size: int
    has_more: bool


class ConceptDetailResponse(ConceptSummaryResponse):
    description: str | None = None


class ConceptEvidenceCreate(TransportModel):
    evidence_link_id: str
    concept_legacy_id: Annotated[str, Field(min_length=1, max_length=500)]
    concept_legacy_source: Annotated[str, Field(min_length=1, max_length=1_000)]
    link_type: EvidenceLinkType
    comment: Annotated[str | None, Field(max_length=MAX_BODY_CHARS)] = None

    @field_validator("evidence_link_id")
    @classmethod
    def evidence_identity_is_valid(cls, value: str) -> str:
        return validate_evidence_link_id(value)

    @field_validator("concept_legacy_id", "concept_legacy_source")
    @classmethod
    def legacy_identity_is_exact_and_safe(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("legacy concept identity is invalid")
        return value

    @field_validator("comment")
    @classmethod
    def comment_has_no_nul(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("comment cannot contain NUL characters")
        return value


class ConceptEvidenceLifecycle(TransportModel):
    """Require an explicit field-free JSON object for lifecycle changes."""


class AnnotationEvidenceContext(TransportModel):
    annotation_id: str
    kind: Literal["highlight", "underline"]
    status: Literal["active", "archived"]
    visual_status: Literal["exact", "version_mismatch"]
    pdf_page: int
    book_page_label: str | None = None
    quote_text: str
    color_label: str | None = None
    annotation_comment: str


class ConceptEvidenceResponse(TransportModel):
    evidence_link_id: str
    concept: ConceptSummaryResponse
    link_type: EvidenceLinkType
    link_type_label: str
    comment: str | None = None
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    annotation: AnnotationEvidenceContext | None = None


class ConceptEvidenceListResponse(TransportModel):
    items: list[ConceptEvidenceResponse]
    page: int
    page_size: int
    total: int
    pages: int


class ConceptEvidenceWriteResponse(TransportModel):
    result: Literal["success", "identical"]
    item: ConceptEvidenceResponse


class DocumentConceptGroupResponse(TransportModel):
    concept: ConceptSummaryResponse
    highlight_count: int
    underline_count: int
    pages: list[int]
    link_types: list[EvidenceLinkType]
    evidence: list[ConceptEvidenceResponse]


class DocumentConceptSummaryResponse(TransportModel):
    items: list[DocumentConceptGroupResponse]
    page: int
    page_size: int
    total: int
    pages: int


class UnlinkedVisualAnnotationResponse(TransportModel):
    annotation_id: str
    kind: Literal["highlight", "underline"]
    pdf_page: int
    book_page_label: str | None = None
    quote_text: str
    color_label: str | None = None


class UnlinkedVisualAnnotationListResponse(TransportModel):
    items: list[UnlinkedVisualAnnotationResponse]
    page: int
    page_size: int
    total: int
    pages: int


__all__ = [
    "AnnotationEvidenceContext",
    "ConceptDetailResponse",
    "ConceptEvidenceCreate",
    "ConceptEvidenceLifecycle",
    "ConceptEvidenceListResponse",
    "ConceptEvidenceResponse",
    "ConceptEvidenceWriteResponse",
    "ConceptSearchResponse",
    "ConceptSummaryResponse",
    "DocumentConceptGroupResponse",
    "DocumentConceptSummaryResponse",
    "UnlinkedVisualAnnotationListResponse",
    "UnlinkedVisualAnnotationResponse",
]

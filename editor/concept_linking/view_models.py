"""Ephemeral presentation models for guided concept linking."""

# ruff: noqa: D101,D102

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class ConceptLinkingContext:
    """Human-readable reading context captured when the wizard starts."""

    database_name: str
    document_id: str
    document_title: str
    document_kind: str
    source_id: str
    source_name: str
    reference_id: str | None
    reference_title: str | None
    pdf_page: int | None
    book_page_label: str | None
    reading_status: str
    web_url: str | None = None
    page_map_warning: str | None = None

    @property
    def is_pdf(self) -> bool:
        return self.document_kind == "pdf"

    @property
    def action_label(self) -> str:
        return (
            "+ Asociar concepto a esta página"
            if self.is_pdf
            else "+ Asociar concepto a este recurso"
        )

    @property
    def location_label(self) -> str:
        if not self.is_pdf:
            if not self.web_url:
                return "Recurso web"
            try:
                domain = urlsplit(self.web_url).hostname
            except ValueError:
                domain = None
            return f"Recurso web · {domain}" if domain else "Recurso web"
        if self.pdf_page is None:
            return "Página PDF no disponible"
        if self.book_page_label:
            return f"Book page {self.book_page_label} · PDF page {self.pdf_page}"
        return f"PDF page {self.pdf_page}"


@dataclass(frozen=True, slots=True)
class ConceptSummary:
    """Small projected legacy concept suitable for cards and session identities."""

    concept_id: str
    concept_source: str
    title: str
    concept_type: str
    categories: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    evidence_count: int | None = None
    document_evidence_count: int = 0
    page_evidence_count: int = 0

    @property
    def identity(self) -> tuple[str, str]:
        return self.concept_id, self.concept_source

    @property
    def display_title(self) -> str:
        return self.title or "Concepto sin título"

    @property
    def topics(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.categories, *self.tags)))


@dataclass(frozen=True, slots=True)
class EvidenceView:
    """Resolved display metadata for one existing ConceptEvidenceLink."""

    evidence_link_id: str
    concept: ConceptSummary
    link_type: str
    link_type_label: str
    origin_kind: str
    origin_label: str
    source_id: str
    reference_id: str | None
    document_id: str | None
    annotation_id: str | None
    note_id: str | None
    pdf_page: int | None
    pdf_page_end: int | None
    book_page_label: str | None
    excerpt: str
    comment: str
    status: str

    @property
    def location_label(self) -> str:
        if self.pdf_page is None:
            return "Sin página"
        if self.book_page_label:
            return f"Book page {self.book_page_label} · PDF page {self.pdf_page}"
        return f"PDF page {self.pdf_page}"


@dataclass(frozen=True, slots=True)
class UnlinkedItem:
    """Presentation-only Annotation or ReadingNote without concept evidence."""

    target_kind: str
    target_id: str
    item_type: str
    title: str
    excerpt: str
    pdf_page: int | None
    book_page_label: str | None
    tags: tuple[str, ...]
    status: str

    @property
    def location_label(self) -> str:
        if self.pdf_page is None:
            return "Sin página"
        if self.book_page_label:
            return f"Book page {self.book_page_label} · PDF page {self.pdf_page}"
        return f"PDF page {self.pdf_page}"


__all__ = [
    "ConceptLinkingContext",
    "ConceptSummary",
    "EvidenceView",
    "UnlinkedItem",
]

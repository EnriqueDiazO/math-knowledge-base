"""S5C read models and service composition for visual concept evidence."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any

from editor.concept_linking.concept_cards import LINK_TYPE_LABELS
from editor.concept_linking.view_models import ConceptSummary
from mathmongo.advanced_reader.concept_schemas import AnnotationEvidenceContext
from mathmongo.advanced_reader.concept_schemas import ConceptEvidenceResponse
from mathmongo.advanced_reader.concept_schemas import ConceptSummaryResponse
from mathmongo.advanced_reader.concept_search import get_legacy_concepts
from mathmongo.reading_annotations.indexes import CONCEPT_EVIDENCE_LINKS_COLLECTION
from mathmongo.reading_annotations.indexes import DOCUMENT_ANNOTATIONS_COLLECTION
from mathmongo.reading_annotations.models import AnnotationStatus
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import EvidenceLinkStatus
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_annotations.service import ReadingAnnotationServiceResult

MAX_VISUAL_EVIDENCE_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class VisualEvidenceRecord:
    link: ConceptEvidenceLink
    annotation_id: str
    document_id: str
    annotation_kind: str
    annotation_status: str
    pdf_page: int
    page_label: str | None
    quote_text: str
    color_label: str | None
    annotation_comment: str
    version_id: str
    document_sha256: str


@dataclass(frozen=True, slots=True)
class VisualEvidencePage:
    items: tuple[VisualEvidenceRecord, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


@dataclass(frozen=True, slots=True)
class UnlinkedVisualRecord:
    annotation_id: str
    kind: str
    pdf_page: int
    page_label: str | None
    quote_text: str
    color_label: str | None


@dataclass(frozen=True, slots=True)
class UnlinkedVisualPage:
    items: tuple[UnlinkedVisualRecord, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100_000:
        raise ValueError("page is invalid")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= MAX_VISUAL_EVIDENCE_PAGE_SIZE
    ):
        raise ValueError(f"page_size must be between 1 and {MAX_VISUAL_EVIDENCE_PAGE_SIZE}")
    return page, page_size


class VisualConceptEvidenceRepository:
    """Bounded read-only joins over authoritative annotations and evidence links."""

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("an explicit database is required")
        self.database = database

    def list_visual_evidence_by_document(
        self,
        document_id: str,
        *,
        pdf_page: int | None = None,
        concept_id: str | None = None,
        concept_source: str | None = None,
        status: EvidenceLinkStatus | str | None = EvidenceLinkStatus.ACTIVE,
        page: int = 1,
        page_size: int = 25,
    ) -> VisualEvidencePage:
        page, page_size = _pagination(page, page_size)
        initial: dict[str, Any] = {"annotation_id": {"$ne": None}}
        if status is not None:
            initial["status"] = EvidenceLinkStatus(status).value
        if concept_id is not None:
            initial["concept_legacy_id"] = concept_id
        if concept_source is not None:
            initial["concept_legacy_source"] = concept_source
        target: dict[str, Any] = {
            "_annotation.document_id": document_id,
            "_annotation.visual_anchor": {"$ne": None},
        }
        if pdf_page is not None:
            target["_annotation.page_number"] = pdf_page
        pipeline = [
            {"$match": initial},
            {
                "$lookup": {
                    "from": DOCUMENT_ANNOTATIONS_COLLECTION,
                    "localField": "annotation_id",
                    "foreignField": "annotation_id",
                    "as": "_annotation",
                }
            },
            {"$unwind": "$_annotation"},
            {"$match": target},
            {
                "$sort": {
                    "_annotation.page_number": 1,
                    "concept_legacy_source": 1,
                    "concept_legacy_id": 1,
                    "evidence_link_id": 1,
                }
            },
            {
                "$facet": {
                    "items": [
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                        {"$unset": ["_id", "_annotation.visual_anchor.rects"]},
                    ],
                    "total": [{"$count": "value"}],
                }
            },
        ]
        rows = list(self.database[CONCEPT_EVIDENCE_LINKS_COLLECTION].aggregate(pipeline))
        facet = rows[0] if rows else {"items": [], "total": []}
        total_rows = facet.get("total", [])
        total = int(total_rows[0].get("value", 0)) if total_rows else 0
        items: list[VisualEvidenceRecord] = []
        for raw in facet.get("items", []):
            annotation = raw.get("_annotation", {})
            anchor = annotation.get("visual_anchor", {})
            link_values = {key: value for key, value in raw.items() if key != "_annotation"}
            for field in ("created_at", "updated_at", "archived_at"):
                timestamp = link_values.get(field)
                if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
                    link_values[field] = timestamp.replace(tzinfo=timezone.utc)
            try:
                link = ConceptEvidenceLink.model_validate(link_values)
                items.append(
                    VisualEvidenceRecord(
                        link=link,
                        annotation_id=str(annotation["annotation_id"]),
                        document_id=str(annotation["document_id"]),
                        annotation_kind=str(annotation["kind"]),
                        annotation_status=str(annotation["status"]),
                        pdf_page=int(annotation["page_number"]),
                        page_label=annotation.get("page_label"),
                        quote_text=str(annotation.get("quote_text") or ""),
                        color_label=annotation.get("color_label"),
                        annotation_comment=str(annotation.get("body") or ""),
                        version_id=str(anchor.get("version_id") or ""),
                        document_sha256=str(anchor.get("document_sha256") or ""),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return VisualEvidencePage(tuple(items), page, page_size, total)

    def list_visual_evidence_by_page(
        self, document_id: str, pdf_page: int, **kwargs: Any
    ) -> VisualEvidencePage:
        return self.list_visual_evidence_by_document(
            document_id,
            pdf_page=pdf_page,
            **kwargs,
        )

    def list_unlinked_visual_annotations(
        self,
        document_id: str,
        *,
        pdf_page: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> UnlinkedVisualPage:
        page, page_size = _pagination(page, page_size)
        selector: dict[str, Any] = {
            "document_id": document_id,
            "status": AnnotationStatus.ACTIVE.value,
            "visual_anchor": {"$ne": None},
        }
        if pdf_page is not None:
            selector["page_number"] = pdf_page
        pipeline = [
            {"$match": selector},
            {
                "$lookup": {
                    "from": CONCEPT_EVIDENCE_LINKS_COLLECTION,
                    "localField": "annotation_id",
                    "foreignField": "annotation_id",
                    "as": "_links",
                }
            },
            {"$match": {"_links": {"$not": {"$elemMatch": {"status": "active"}}}}},
            {"$sort": {"page_number": 1, "annotation_id": 1}},
            {
                "$facet": {
                    "items": [
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                        {
                            "$project": {
                                "_id": 0,
                                "annotation_id": 1,
                                "kind": 1,
                                "page_number": 1,
                                "page_label": 1,
                                "quote_text": 1,
                                "color_label": 1,
                            }
                        },
                    ],
                    "total": [{"$count": "value"}],
                }
            },
        ]
        rows = list(self.database[DOCUMENT_ANNOTATIONS_COLLECTION].aggregate(pipeline))
        facet = rows[0] if rows else {"items": [], "total": []}
        total_rows = facet.get("total", [])
        total = int(total_rows[0].get("value", 0)) if total_rows else 0
        items: list[UnlinkedVisualRecord] = []
        for raw in facet.get("items", []):
            try:
                items.append(
                    UnlinkedVisualRecord(
                        annotation_id=str(raw["annotation_id"]),
                        kind=str(raw["kind"]),
                        pdf_page=int(raw["page_number"]),
                        page_label=raw.get("page_label"),
                        quote_text=str(raw.get("quote_text") or ""),
                        color_label=raw.get("color_label"),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return UnlinkedVisualPage(tuple(items), page, page_size, total)


def concept_payload(
    concept: ConceptSummary | None,
    identity: tuple[str, str],
    *,
    evidence_count: int | None = None,
    evidence_in_document_count: int | None = None,
) -> ConceptSummaryResponse:
    if concept is None:
        return ConceptSummaryResponse(
            concept_legacy_id=identity[0],
            concept_legacy_source=identity[1],
            title="Concepto no disponible",
            concept_type="",
            categories=[],
            tags=[],
            evidence_count=evidence_count,
            evidence_in_document_count=evidence_in_document_count,
            warning="concept_not_found",
        )
    return ConceptSummaryResponse(
        concept_legacy_id=concept.concept_id,
        concept_legacy_source=concept.concept_source,
        title=concept.display_title,
        concept_type=concept.concept_type,
        categories=list(concept.categories),
        tags=list(concept.tags),
        evidence_count=evidence_count if evidence_count is not None else concept.evidence_count,
        evidence_in_document_count=evidence_in_document_count,
    )


def evidence_payload(
    link: ConceptEvidenceLink,
    concept: ConceptSummary | None,
    *,
    annotation: DocumentAnnotation | VisualEvidenceRecord | None = None,
    visual_status: str = "exact",
    book_page_label: str | None = None,
) -> ConceptEvidenceResponse:
    context: AnnotationEvidenceContext | None = None
    if isinstance(annotation, DocumentAnnotation) and annotation.visual_anchor is not None:
        context = AnnotationEvidenceContext(
            annotation_id=annotation.annotation_id,
            kind=annotation.kind.value,
            status=annotation.status.value,
            visual_status=visual_status,
            pdf_page=annotation.visual_anchor.pdf_page,
            book_page_label=book_page_label or annotation.page_label,
            quote_text=annotation.quote_text or "",
            color_label=annotation.color_label,
            annotation_comment=annotation.body,
        )
    elif isinstance(annotation, VisualEvidenceRecord):
        context = AnnotationEvidenceContext(
            annotation_id=annotation.annotation_id,
            kind=annotation.annotation_kind,
            status=annotation.annotation_status,
            visual_status=visual_status,
            pdf_page=annotation.pdf_page,
            book_page_label=book_page_label or annotation.page_label,
            quote_text=annotation.quote_text,
            color_label=annotation.color_label,
            annotation_comment=annotation.annotation_comment,
        )
    identity = (link.concept_legacy_id, link.concept_legacy_source)
    return ConceptEvidenceResponse(
        evidence_link_id=link.evidence_link_id,
        concept=concept_payload(concept, identity),
        link_type=link.link_type,
        link_type_label=LINK_TYPE_LABELS[link.link_type.value],
        comment=link.comment,
        status=link.status.value,
        created_at=link.created_at,
        updated_at=link.updated_at,
        archived_at=link.archived_at,
        annotation=context,
    )


def resolve_concepts_for_links(
    database: Any,
    links: tuple[ConceptEvidenceLink, ...],
) -> dict[tuple[str, str], ConceptSummary]:
    return get_legacy_concepts(
        database,
        ((item.concept_legacy_id, item.concept_legacy_source) for item in links),
        limit=max(1, len(links)),
    )


def create_visual_concept_evidence(
    service: ReadingAnnotationService,
    annotation: DocumentAnnotation,
    *,
    current_version_id: str,
    current_document_sha256: str,
    evidence_link_id: str,
    concept_legacy_id: str,
    concept_legacy_source: str,
    link_type: str,
    comment: str | None,
) -> ReadingAnnotationServiceResult[ConceptEvidenceLink]:
    """Validate visual eligibility, then delegate the one authoritative write."""
    if annotation.status != AnnotationStatus.ACTIVE:
        return ReadingAnnotationServiceResult(
            ReadingAnnotationOperationStatus.ARCHIVED,
            message="Visual Annotation is archived.",
        )
    anchor = annotation.visual_anchor
    if anchor is None:
        return ReadingAnnotationServiceResult(
            ReadingAnnotationOperationStatus.INVALID_STATE,
            message="Annotation is not visual.",
        )
    if anchor.version_id != current_version_id or anchor.document_sha256 != current_document_sha256:
        return ReadingAnnotationServiceResult(
            ReadingAnnotationOperationStatus.BLOCKED,
            message="Visual Annotation belongs to another PDF version.",
        )
    return service.create_concept_evidence_link(
        evidence_link_id=evidence_link_id,
        concept_legacy_id=concept_legacy_id,
        concept_legacy_source=concept_legacy_source,
        source_id=annotation.source_id,
        reference_id=annotation.reference_id,
        annotation_id=annotation.annotation_id,
        link_type=link_type,
        comment=comment,
    )


__all__ = [
    "MAX_VISUAL_EVIDENCE_PAGE_SIZE",
    "UnlinkedVisualPage",
    "UnlinkedVisualRecord",
    "VisualConceptEvidenceRepository",
    "VisualEvidencePage",
    "VisualEvidenceRecord",
    "concept_payload",
    "create_visual_concept_evidence",
    "evidence_payload",
    "resolve_concepts_for_links",
]

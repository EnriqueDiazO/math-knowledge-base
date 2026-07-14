"""Focused S5B model, repository, index, and service tests."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError
from source_catalog_migration_fakes import FakeDatabase

from mathmongo.reading_annotations.indexes import CONCEPT_EVIDENCE_LINKS_COLLECTION
from mathmongo.reading_annotations.indexes import DOCUMENT_ANNOTATIONS_COLLECTION
from mathmongo.reading_annotations.indexes import LEGACY_READING_ANNOTATION_INDEXES
from mathmongo.reading_annotations.indexes import READING_ANNOTATION_INDEXES
from mathmongo.reading_annotations.indexes import READING_NOTES_COLLECTION
from mathmongo.reading_annotations.indexes import VISUAL_ANNOTATION_INDEXES
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
from mathmongo.reading_annotations.models import AnnotationKind
from mathmongo.reading_annotations.models import AnnotationStatus
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import NormalizedVisualRect
from mathmongo.reading_annotations.models import VisualAnnotationAnchor
from mathmongo.reading_annotations.models import visual_text_sha256
from mathmongo.reading_annotations.repository import AnnotationRepository
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import PdfVersion
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.service import DocumentIntegrityInspection

PDF_BYTES = b"%PDF-1.7\nS5B\n%%EOF\n"
ANNOTATION_A = "ann_00000000-0000-4000-8000-000000000501"
ANNOTATION_B = "ann_00000000-0000-4000-8000-000000000502"
S4_COLLECTIONS = (
    DOCUMENT_ANNOTATIONS_COLLECTION,
    READING_NOTES_COLLECTION,
    CONCEPT_EVIDENCE_LINKS_COLLECTION,
)


def _pdf(
    source: Source,
    *,
    reference_id: str | None = None,
    status: str = "active",
) -> SourceDocument:
    digest = hashlib.sha256(PDF_BYTES).hexdigest()
    version = PdfVersion(
        sha256=digest,
        size_bytes=len(PDF_BYTES),
        logical_path=f"source_documents/blobs/sha256/{digest[:2]}/{digest}.pdf",
        original_filename="visual.pdf",
    )
    return SourceDocument(
        source_id=source.source_id,
        reference_id=reference_id,
        kind="pdf",
        title="Visual PDF",
        status=status,
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def _web(source: Source) -> SourceDocument:
    return SourceDocument(
        source_id=source.source_id,
        kind="web",
        title="Web",
        web=WebDocument(url_raw="https://example.test/visual"),
    )


def _database(
    *,
    ready: bool = True,
    total_pages: int | None = None,
) -> tuple[FakeDatabase, Source, Reference, SourceDocument, SourceDocument, SourceDocument]:
    source = Source(name="S5B Source")
    reference = Reference(source_ids=[source.source_id], title="S5B Reference")
    pdf = _pdf(source, reference_id=reference.reference_id)
    archived_pdf = _pdf(source, status="archived")
    web = _web(source)
    collections: dict[str, list[dict[str, Any]]] = {
        "sources": [source.model_dump(mode="python")],
        "references": [reference.model_dump(mode="python")],
        "source_documents": [
            pdf.model_dump(mode="python"),
            archived_pdf.model_dump(mode="python"),
            web.model_dump(mode="python"),
        ],
    }
    if total_pages is not None:
        state = DocumentReadingState(
            document_id=pdf.document_id,
            source_id=source.source_id,
            reference_id=reference.reference_id,
            current_page=1,
            total_pages=total_pages,
        )
        collections["document_reading_state"] = [state.model_dump(mode="python")]
    database = FakeDatabase(
        "s5b-core",
        collections,
        allowed_document_writes=S4_COLLECTIONS,
        allowed_index_writes=S4_COLLECTIONS,
    )
    if ready:
        ReadingAnnotationIndexManager(database).apply()
    return database, source, reference, pdf, archived_pdf, web


@dataclass
class _IntegrityService:
    ok: bool = True

    def __post_init__(self) -> None:
        self.calls: list[str] = []

    def inspect_document_integrity(self, document_id: str) -> DocumentIntegrityInspection:
        self.calls.append(document_id)
        issues = () if self.ok else ("sha256_mismatch",)
        return DocumentIntegrityInspection(document_id, self.ok, issues)


def _service(
    database: FakeDatabase,
    *,
    integrity_ok: bool = True,
) -> tuple[ReadingAnnotationService, _IntegrityService]:
    integrity = _IntegrityService(integrity_ok)
    service = ReadingAnnotationService(database, document_service=integrity)  # type: ignore[arg-type]
    return service, integrity


def _create_values(
    document: SourceDocument,
    *,
    annotation_id: str = ANNOTATION_A,
    pdf_page: int = 2,
) -> dict[str, Any]:
    assert document.pdf is not None
    version = document.pdf.current_version
    return {
        "annotation_id": annotation_id,
        "document_id": document.document_id,
        "version_id": version.version_id,
        "document_sha256": version.sha256,
        "pdf_page": pdf_page,
        "kind": "highlight",
        "quote_text": "  Selected\n mathematical\ttext  ",
        "rects": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.04}],
        "capture_rotation": 90,
        "color_label": "yellow",
        "body": "",
        "tags": ["Topology"],
    }


def _anchor(*, pdf_page: int = 2, quote: str = "Selected text") -> VisualAnnotationAnchor:
    version = PdfVersion(
        sha256="a" * 64,
        size_bytes=1,
        logical_path=f"source_documents/blobs/sha256/aa/{'a' * 64}.pdf",
        original_filename="x.pdf",
    )
    return VisualAnnotationAnchor(
        version_id=version.version_id,
        document_sha256="a" * 64,
        pdf_page=pdf_page,
        capture_rotation=0,
        rects=[{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}],
        text_sha256=visual_text_sha256(quote),
    )


def test_visual_models_normalize_hash_and_keep_anchor_immutable() -> None:
    source = Source(name="Visual models")
    document = _pdf(source)
    anchor = _anchor(quote="Selected text")
    annotation = DocumentAnnotation(
        schema_version=2,
        document_id=document.document_id,
        source_id=source.source_id,
        kind="highlight",
        page_number=2,
        quote_text="  Selected\n text ",
        visual_anchor=anchor,
    )

    assert annotation.quote_text == "Selected text"
    assert annotation.color_label == "yellow"
    assert annotation.visual_anchor == anchor
    assert visual_text_sha256("x < y > z") == hashlib.sha256(b"x < y > z").hexdigest()
    whitespace_heavy = DocumentAnnotation.model_validate(
        {
            **annotation.model_dump(mode="python"),
            "quote_text": f"Selected{' ' * 30_000}text",
        }
    )
    assert whitespace_heavy.quote_text == "Selected text"
    assert anchor.coordinate_space == "normalized_unrotated_crop_box"
    assert anchor.created_from == "pdfjs_text_selection"
    assert isinstance(anchor.rects, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        anchor.pdf_page = 3
    with pytest.raises(ValidationError, match="frozen"):
        annotation.visual_anchor = _anchor(pdf_page=3)
    with pytest.raises(ValidationError, match="schema_version=1"):
        DocumentAnnotation(
            document_id=document.document_id,
            source_id=source.source_id,
            kind="highlight",
            page_number=2,
            quote_text="Selected text",
            visual_anchor=anchor,
        )


@pytest.mark.parametrize(
    "values",
    [
        {"x": float("nan"), "y": 0.1, "width": 0.2, "height": 0.2},
        {"x": 0.1, "y": float("inf"), "width": 0.2, "height": 0.2},
        {"x": -0.01, "y": 0.1, "width": 0.2, "height": 0.2},
        {"x": 0.1, "y": 0.1, "width": 0, "height": 0.2},
        {"x": 0.9, "y": 0.1, "width": 0.2, "height": 0.2},
        {"x": True, "y": 0.1, "width": 0.2, "height": 0.2},
        {"x": "0.1", "y": 0.1, "width": 0.2, "height": 0.2},
        {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2, "extra": 1},
    ],
)
def test_normalized_rect_rejects_non_finite_out_of_bounds_and_extra(
    values: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        NormalizedVisualRect.model_validate(values)


@pytest.mark.parametrize(
    "patch",
    [
        {"version_id": "bad"},
        {"document_sha256": "A" * 64},
        {"text_sha256": "g" * 64},
        {"pdf_page": True},
        {"capture_rotation": 45},
        {"rects": []},
        {"rects": [{"x": 0, "y": 0, "width": 0.1, "height": 0.1}] * 65},
        {"coordinate_space": "viewport"},
        {"created_from": "manual"},
        {"unexpected": True},
    ],
)
def test_visual_anchor_is_closed_and_strict(patch: dict[str, Any]) -> None:
    values = _anchor().model_dump(mode="python")
    values.update(patch)
    with pytest.raises(ValidationError):
        VisualAnnotationAnchor.model_validate(values)


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"kind": "comment", "body": "comment"}, "highlights or underlines"),
        ({"page_number": 3}, "page_number"),
        ({"quote_text": ""}, "cannot be empty"),
        ({"quote_text": "other"}, "text_sha256"),
        ({"quote_text": "<script>alert(1)</script>"}, "plain text"),
        ({"color_label": "url(evil)"}, "palette"),
    ],
)
def test_document_annotation_rejects_invalid_visual_combinations(
    patch: dict[str, Any],
    message: str,
) -> None:
    source = Source(name="Visual combinations")
    document = _pdf(source)
    values: dict[str, Any] = {
        "schema_version": 2,
        "document_id": document.document_id,
        "source_id": source.source_id,
        "kind": "highlight",
        "page_number": 2,
        "quote_text": "Selected text",
        "visual_anchor": _anchor(),
    }
    values.update(patch)
    with pytest.raises(ValidationError, match=message):
        DocumentAnnotation.model_validate(values)


def test_visual_indexes_are_explicit_and_legacy_writes_remain_available() -> None:
    database, _, _, pdf, _, _ = _database(ready=False)
    manager = ReadingAnnotationIndexManager(database)
    service, _ = _service(database)

    assert len(READING_ANNOTATION_INDEXES) == 21
    assert [(item.name, item.keys) for item in VISUAL_ANNOTATION_INDEXES] == [
        (
            "document_annotations_document_page_status",
            (("document_id", 1), ("page_number", 1), ("status", 1), ("updated_at", -1)),
        ),
        (
            "document_annotations_visual_version_sha",
            (("visual_anchor.version_id", 1), ("visual_anchor.document_sha256", 1)),
        ),
    ]
    assert not service.visual_indexes_ready()
    assert not database.write_events

    for spec in LEGACY_READING_ANNOTATION_INDEXES:
        database[spec.collection].create_index(
            list(spec.keys),
            name=spec.name,
            unique=spec.unique,
        )
    logical = service.create_annotation(pdf.document_id, kind="bookmark")
    visual = service.create_visual_annotation(**_create_values(pdf))

    assert logical.completed and logical.value is not None
    assert logical.value.schema_version == 1 and logical.value.visual_anchor is None
    assert visual.status == ReadingAnnotationOperationStatus.INVALID_STATE
    assert not service.visual_indexes_ready()
    assert {item.name for item in manager.plan().missing} == {
        "document_annotations_document_page_status",
        "document_annotations_visual_version_sha",
    }


def test_repository_visual_queries_are_bounded_filtered_and_stable() -> None:
    database, source, _, pdf, _, _ = _database()
    repository = AnnotationRepository(database)
    assert pdf.pdf is not None
    version = pdf.pdf.current_version

    logical = repository.insert(
        DocumentAnnotation(
            document_id=pdf.document_id,
            source_id=source.source_id,
            kind="highlight",
            page_number=2,
            quote_text="logical",
        )
    )
    for annotation_id, page, kind, status in (
        (ANNOTATION_A, 2, "highlight", "active"),
        (ANNOTATION_B, 3, "underline", "archived"),
    ):
        quote = f"visual {page}"
        repository.insert(
            DocumentAnnotation(
                schema_version=2,
                annotation_id=annotation_id,
                document_id=pdf.document_id,
                source_id=source.source_id,
                kind=kind,
                status=status,
                page_number=page,
                quote_text=quote,
                visual_anchor=VisualAnnotationAnchor(
                    version_id=version.version_id,
                    document_sha256=version.sha256,
                    pdf_page=page,
                    capture_rotation=0,
                    rects=[{"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}],
                    text_sha256=visual_text_sha256(quote),
                ),
            )
        )

    assert repository.get_visual_by_annotation_id(logical.annotation_id) is None
    assert repository.get_visual_by_annotation_id(ANNOTATION_A).annotation_id == ANNOTATION_A
    assert repository.list_visual_by_document(pdf.document_id).total == 1
    all_visual = repository.list_visual_by_document(pdf.document_id, status=None)
    archived = repository.list_visual_by_page(pdf.document_id, 3, status="archived")
    assert [item.annotation_id for item in all_visual.items] == [ANNOTATION_A, ANNOTATION_B]
    assert archived.total == 1 and archived.items[0].kind == AnnotationKind.UNDERLINE
    visual_find = next(
        event
        for event in reversed(database.read_events)
        if event.collection == DOCUMENT_ANNOTATIONS_COLLECTION and event.operation == "find"
    )
    assert visual_find.details["projection"]["visual_anchor"] == 1
    assert visual_find.details["query"]["visual_anchor"] == {"$exists": True, "$ne": None}


def test_service_visual_crud_is_idempotent_and_preserves_anchor() -> None:
    database, _, _, pdf, _, _ = _database(total_pages=5)
    service, integrity = _service(database)
    values = _create_values(pdf)

    created = service.create_visual_annotation(**values)
    identical = service.create_visual_annotation(
        **{**values, "quote_text": "Selected mathematical text"}
    )
    conflict = service.create_visual_annotation(**{**values, "body": "different"})

    assert created.status == ReadingAnnotationOperationStatus.SUCCESS
    assert created.value is not None and created.value.schema_version == 2
    assert created.value.quote_text == "Selected mathematical text"
    assert identical.status == ReadingAnnotationOperationStatus.IDENTICAL
    assert identical.completed and identical.value.annotation_id == ANNOTATION_A
    assert conflict.status == ReadingAnnotationOperationStatus.CONFLICT
    assert len(database[DOCUMENT_ANNOTATIONS_COLLECTION].documents) == 1
    assert integrity.calls == [pdf.document_id, pdf.document_id, pdf.document_id]

    anchor_before = created.value.visual_anchor
    updated = service.update_visual_annotation_presentation(
        ANNOTATION_A,
        kind="underline",
        color_label="pink",
        body="presentation",
        tags=["proof"],
    )
    forbidden_generic = service.update_annotation(
        ANNOTATION_A,
        kind="underline",
        body="presentation",
        page_number=2,
        quote_text="Selected mathematical text",
        color_label="pink",
        tags=["proof"],
    )
    invalid_kind = service.update_visual_annotation_presentation(
        ANNOTATION_A,
        kind="comment",
        color_label="yellow",
        body="comment",
    )

    assert updated.completed and updated.value is not None
    assert updated.value.kind == AnnotationKind.UNDERLINE
    assert updated.value.color_label == "pink" and updated.value.tags == ["proof"]
    assert updated.value.visual_anchor == anchor_before
    assert updated.value.page_number == 2
    assert updated.value.quote_text == "Selected mathematical text"
    assert forbidden_generic.status == ReadingAnnotationOperationStatus.INVALID_STATE
    assert invalid_kind.status == ReadingAnnotationOperationStatus.INVALID_STATE
    assert service.get_visual_annotation(ANNOTATION_A).value.visual_anchor == anchor_before
    assert service.list_visual_annotations(pdf.document_id, pdf_page=2).value.total == 1

    archived = service.archive_visual_annotation(ANNOTATION_A)
    edit_archived = service.update_visual_annotation_presentation(
        ANNOTATION_A,
        kind="highlight",
        color_label="blue",
        body="blocked",
    )
    reactivated = service.reactivate_visual_annotation(ANNOTATION_A)
    assert archived.value.status == AnnotationStatus.ARCHIVED
    assert edit_archived.status == ReadingAnnotationOperationStatus.ARCHIVED
    assert reactivated.value.status == AnnotationStatus.ACTIVE
    assert reactivated.value.visual_anchor == anchor_before


def test_visual_create_validates_document_version_integrity_and_known_page_range() -> None:
    database, _, _, pdf, archived_pdf, web = _database(total_pages=3)
    service, _ = _service(database)
    values = _create_values(pdf)

    assert service.create_visual_annotation(**{**values, "pdf_page": 4}).status == (
        ReadingAnnotationOperationStatus.INVALID_STATE
    )
    assert (
        service.create_visual_annotation(
            **{**values, "version_id": "dver_00000000-0000-4000-8000-000000000599"}
        ).status
        == ReadingAnnotationOperationStatus.CONFLICT
    )
    assert (
        service.create_visual_annotation(**{**values, "document_sha256": "f" * 64}).status
        == ReadingAnnotationOperationStatus.CONFLICT
    )
    assert (
        service.create_visual_annotation(
            **{**values, "annotation_id": ANNOTATION_B, "document_id": web.document_id}
        ).status
        == ReadingAnnotationOperationStatus.INVALID_STATE
    )
    assert (
        service.create_visual_annotation(
            **_create_values(archived_pdf, annotation_id=ANNOTATION_B)
        ).status
        == ReadingAnnotationOperationStatus.ARCHIVED
    )
    missing_document_id = _pdf(Source(name="Missing visual source")).document_id
    assert (
        service.create_visual_annotation(**{**values, "document_id": missing_document_id}).status
        == ReadingAnnotationOperationStatus.NOT_FOUND
    )
    assert (
        service.create_visual_annotation(**{**values, "body": "x" * 100_001}).status
        == ReadingAnnotationOperationStatus.INVALID_STATE
    )

    underline = service.create_visual_annotation(
        **{
            **values,
            "annotation_id": ANNOTATION_B,
            "kind": "underline",
            "pdf_page": 3,
        }
    )
    assert underline.completed and underline.value.kind == AnnotationKind.UNDERLINE

    damaged, _ = _service(database, integrity_ok=False)
    assert damaged.create_visual_annotation(**values).status == (
        ReadingAnnotationOperationStatus.BLOCKED
    )


def test_unknown_page_total_does_not_materialize_pdf_and_reactivation_allows_version_mismatch() -> (
    None
):
    database, _, _, pdf, _, _ = _database()
    service, integrity = _service(database)
    values = _create_values(pdf, pdf_page=999)
    created = service.create_visual_annotation(**values)
    archived = service.archive_visual_annotation(ANNOTATION_A)

    assert created.completed and archived.completed
    assert integrity.calls == [pdf.document_id]
    assert not any(event.collection == "document_reading_state" for event in database.write_events)

    assert pdf.pdf is not None
    replacement = PdfVersion(
        sha256="b" * 64,
        size_bytes=2,
        logical_path=f"source_documents/blobs/sha256/bb/{'b' * 64}.pdf",
        original_filename="replacement.pdf",
    )
    raw = next(
        item
        for item in database._documents["source_documents"]
        if item["document_id"] == pdf.document_id
    )
    raw["pdf"]["versions"] = [replacement.model_dump(mode="python")]
    raw["pdf"]["current_version_id"] = replacement.version_id

    reactivated = service.reactivate_visual_annotation(ANNOTATION_A)
    assert reactivated.completed and reactivated.value.status == AnnotationStatus.ACTIVE
    assert reactivated.value.visual_anchor.version_id == values["version_id"]


def test_visual_reads_remain_available_without_s5b_indexes() -> None:
    database, source, _, pdf, _, _ = _database(ready=False)
    assert pdf.pdf is not None
    quote = "read without indexes"
    annotation = DocumentAnnotation(
        schema_version=2,
        annotation_id=ANNOTATION_A,
        document_id=pdf.document_id,
        source_id=source.source_id,
        kind="highlight",
        page_number=1,
        quote_text=quote,
        visual_anchor=VisualAnnotationAnchor(
            version_id=pdf.pdf.current_version.version_id,
            document_sha256=pdf.pdf.current_version.sha256,
            pdf_page=1,
            capture_rotation=0,
            rects=[{"x": 0, "y": 0, "width": 0.1, "height": 0.1}],
            text_sha256=visual_text_sha256(quote),
        ),
    )
    database.seed_collection(
        DOCUMENT_ANNOTATIONS_COLLECTION,
        [annotation.model_dump(mode="python")],
    )
    service, _ = _service(database)

    assert service.get_visual_annotation(ANNOTATION_A).completed
    listed = service.list_visual_annotations(pdf.document_id, pdf_page=1)
    assert listed.completed and listed.value.total == 1
    assert not service.visual_indexes_ready()

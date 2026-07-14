"""Focused S4 domain, repository, index, and service tests."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import copy
import hashlib
from datetime import datetime
from datetime import timezone
from typing import Any

import pytest
from pydantic import ValidationError
from source_catalog_migration_fakes import FakeDatabase

from mathmongo.reading_annotations.indexes import CONCEPT_EVIDENCE_LINKS_COLLECTION
from mathmongo.reading_annotations.indexes import DOCUMENT_ANNOTATIONS_COLLECTION
from mathmongo.reading_annotations.indexes import READING_ANNOTATION_INDEXES
from mathmongo.reading_annotations.indexes import READING_NOTES_COLLECTION
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexState
from mathmongo.reading_annotations.models import AnnotationKind
from mathmongo.reading_annotations.models import AnnotationStatus
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import EvidenceLinkStatus
from mathmongo.reading_annotations.models import ReadingNote
from mathmongo.reading_annotations.models import ReadingNoteStatus
from mathmongo.reading_annotations.repository import AnnotationRepository
from mathmongo.reading_annotations.repository import ConceptEvidenceRepository
from mathmongo.reading_annotations.repository import ReadingNoteRepository
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import PdfVersion
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument

PDF_BYTES = b"%PDF-1.7\n%%EOF\n"
S4_COLLECTIONS = (
    DOCUMENT_ANNOTATIONS_COLLECTION,
    READING_NOTES_COLLECTION,
    CONCEPT_EVIDENCE_LINKS_COLLECTION,
)


def _web(source: Source, *, reference_id: str | None = None, status: str = "active"):
    return SourceDocument(
        source_id=source.source_id,
        reference_id=reference_id,
        kind="web",
        title="Web paper",
        status=status,
        web=WebDocument(url_raw="https://example.test/paper"),
    )


def _pdf(source: Source, *, reference_id: str | None = None, status: str = "active"):
    digest = hashlib.sha256(PDF_BYTES).hexdigest()
    version = PdfVersion(
        sha256=digest,
        size_bytes=len(PDF_BYTES),
        logical_path=f"source_documents/blobs/sha256/{digest[:2]}/{digest}.pdf",
        original_filename="paper.pdf",
    )
    return SourceDocument(
        source_id=source.source_id,
        reference_id=reference_id,
        kind="pdf",
        title="PDF paper",
        status=status,
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def _database(*, ready: bool = True):
    source = Source(name="S4 Source")
    other_source = Source(name="Other Source")
    reference = Reference(source_ids=[source.source_id], title="Reference")
    other_reference = Reference(source_ids=[other_source.source_id], title="Other")
    pdf = _pdf(source, reference_id=reference.reference_id)
    web = _web(source)
    archived = _web(source, status="archived")
    database = FakeDatabase(
        "s4-focused",
        {
            "sources": [
                source.model_dump(mode="python"),
                other_source.model_dump(mode="python"),
            ],
            "references": [
                reference.model_dump(mode="python"),
                other_reference.model_dump(mode="python"),
            ],
            "source_documents": [
                pdf.model_dump(mode="python"),
                web.model_dump(mode="python"),
                archived.model_dump(mode="python"),
            ],
            "concepts": [{"id": "compactness", "source": "Legacy Topology", "name": "Compactness"}],
        },
        allowed_document_writes=S4_COLLECTIONS,
        allowed_index_writes=S4_COLLECTIONS,
    )
    if ready:
        ReadingAnnotationIndexManager(database).apply()
    return database, source, other_source, reference, other_reference, pdf, web, archived


def test_strict_models_ids_utc_pages_extra_and_required_body() -> None:
    source = Source(name="Models")
    document = _web(source)
    annotation = DocumentAnnotation(
        document_id=document.document_id,
        source_id=source.source_id,
        kind="highlight",
        quote_text="manual quote",
        tags=["Topology", " topology ", "proof"],
    )
    note = ReadingNote(
        document_id=document.document_id,
        source_id=source.source_id,
        title="A note",
        body="Plain user text",
    )
    evidence = ConceptEvidenceLink(
        concept_legacy_id="c1",
        concept_legacy_source="legacy",
        source_id=source.source_id,
        annotation_id=annotation.annotation_id,
        link_type="definition_source",
    )

    assert annotation.annotation_id.startswith("ann_")
    assert note.note_id.startswith("note_")
    assert evidence.evidence_link_id.startswith("ev_")
    assert annotation.tags == ["Topology", "proof"]
    assert annotation.created_at.tzinfo == timezone.utc
    assert note.created_at.tzinfo == timezone.utc
    assert evidence.created_at.tzinfo == timezone.utc
    for model, values, identifier in (
        (
            DocumentAnnotation,
            {
                "document_id": document.document_id,
                "source_id": source.source_id,
                "kind": "highlight",
            },
            "annotation_id",
        ),
        (ReadingNote, {"source_id": source.source_id, "title": "x", "body": "y"}, "note_id"),
        (
            ConceptEvidenceLink,
            {
                "concept_legacy_id": "c",
                "concept_legacy_source": "s",
                "source_id": source.source_id,
                "document_id": document.document_id,
                "page_number": 1,
                "link_type": "citation",
            },
            "evidence_link_id",
        ),
    ):
        with pytest.raises(ValidationError):
            model.model_validate({**values, identifier: "bad"})
        with pytest.raises(ValidationError):
            model.model_validate({**values, "unexpected": True})
    with pytest.raises(ValidationError, match="strict integers"):
        DocumentAnnotation(
            document_id=document.document_id,
            source_id=source.source_id,
            kind="highlight",
            page_number=True,
        )
    with pytest.raises(ValidationError, match="body is required"):
        DocumentAnnotation(
            document_id=document.document_id,
            source_id=source.source_id,
            kind="comment",
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        ReadingNote(
            source_id=source.source_id,
            title="x",
            body="y",
            created_at=datetime(2026, 7, 12),
        )


def test_model_lifecycle_page_ranges_and_exact_evidence_target() -> None:
    source = Source(name="Consistency")
    document = _web(source)
    with pytest.raises(ValidationError, match="page_start"):
        ReadingNote(
            source_id=source.source_id,
            title="range",
            body="body",
            page_start=3,
            page_end=2,
        )
    with pytest.raises(ValidationError, match="exactly one target"):
        ConceptEvidenceLink(
            concept_legacy_id="c",
            concept_legacy_source="s",
            source_id=source.source_id,
            annotation_id=DocumentAnnotation(
                document_id=document.document_id,
                source_id=source.source_id,
                kind="highlight",
            ).annotation_id,
            document_id=document.document_id,
            page_number=1,
            link_type="citation",
        )
    with pytest.raises(ValidationError, match="both document_id and page_number"):
        ConceptEvidenceLink(
            concept_legacy_id="c",
            concept_legacy_source="s",
            source_id=source.source_id,
            document_id=document.document_id,
            link_type="citation",
        )
    timestamp = datetime.now(timezone.utc)
    archived = DocumentAnnotation(
        document_id=document.document_id,
        source_id=source.source_id,
        kind="bookmark",
        status="archived",
        created_at=timestamp,
        updated_at=timestamp,
    )
    assert archived.status == AnnotationStatus.ARCHIVED
    assert archived.archived_at == timestamp
    with pytest.raises(ValidationError, match="active annotation"):
        DocumentAnnotation(
            document_id=document.document_id,
            source_id=source.source_id,
            kind="bookmark",
            archived_at=timestamp,
        )


def test_repositories_and_index_manager_are_lazy_and_apply_explicitly() -> None:
    database, *_ = _database(ready=False)
    before = database.events
    annotations = AnnotationRepository(database)
    notes = ReadingNoteRepository(database)
    evidence = ConceptEvidenceRepository(database)
    manager = ReadingAnnotationIndexManager(database)
    service = ReadingAnnotationService(database)

    assert annotations.database is database
    assert notes.database is database
    assert evidence.database is database
    assert service.database is database
    assert database.events == before
    plan = manager.plan()
    assert len(plan.missing) == len(READING_ANNOTATION_INDEXES) == 21
    assert not database.write_events
    applied = manager.apply()
    assert applied.initialized
    assert all(item.state == ReadingAnnotationIndexState.PRESENT for item in manager.status())
    assert {item.spec.collection for item in applied.statuses} == set(S4_COLLECTIONS)


def test_annotation_repository_insert_get_page_search_update_and_lifecycle() -> None:
    database, source, _, _, _, pdf, _, _ = _database()
    repository = AnnotationRepository(database)
    first = repository.insert(
        DocumentAnnotation(
            document_id=pdf.document_id,
            source_id=source.source_id,
            kind="highlight",
            page_number=2,
            quote_text="A [literal] compactness quote",
            tags=["topology"],
        )
    )
    second = repository.insert(
        DocumentAnnotation(
            document_id=pdf.document_id,
            source_id=source.source_id,
            kind="comment",
            body="A comment",
        )
    )

    page = repository.list_by_document(pdf.document_id, page=1, page_size=1)
    searched = repository.search("[literal]", document_id=pdf.document_id)
    updated = repository.update_content(
        first.annotation_id,
        kind="underline",
        page_number=3,
        page_label="iii",
        quote_text="changed",
        body="",
        color_label="blue",
        tags=["analysis"],
    )
    archived = repository.archive(second.annotation_id)
    reactivated = repository.reactivate(second.annotation_id)

    assert repository.get_by_id(first.annotation_id).annotation_id == first.annotation_id
    assert page.total == 2 and page.pages == 2 and len(page.items) == 1
    assert searched.total == 1 and searched.items[0].annotation_id == first.annotation_id
    assert updated.kind == AnnotationKind.UNDERLINE and updated.tags == ["analysis"]
    assert archived.status == AnnotationStatus.ARCHIVED and archived.archived_at is not None
    assert reactivated.status == AnnotationStatus.ACTIVE and reactivated.archived_at is None
    assert repository.count_by_document(pdf.document_id) == 2
    assert not hasattr(repository, "delete") and not hasattr(repository, "delete_one")


def test_note_repository_insert_get_page_search_update_and_lifecycle() -> None:
    database, source, _, reference, _, pdf, _, _ = _database()
    repository = ReadingNoteRepository(database)
    first = repository.insert(
        ReadingNote(
            document_id=pdf.document_id,
            source_id=source.source_id,
            title="Compactness proof",
            body="A finite subcover argument",
            note_type="proof",
            tags=["topology"],
        )
    )
    repository.insert(
        ReadingNote(
            source_id=source.source_id,
            title="General idea",
            body="Source-only note",
        )
    )

    assert repository.list_by_document(pdf.document_id).total == 1
    assert repository.list_by_source(source.source_id, page_size=1).total == 2
    source_only = repository.list_by_source(
        source.source_id,
        source_only=True,
        page_size=1,
    )
    assert source_only.total == 1
    assert source_only.items[0].document_id is None
    assert (
        repository.search(
            "Source-only",
            source_id=source.source_id,
            source_only=True,
            page_size=1,
        ).total
        == 1
    )
    assert (
        repository.search("subcover", source_id=source.source_id).items[0].note_id == first.note_id
    )
    updated = repository.update_content(
        first.note_id,
        title="Updated",
        body="Updated body",
        note_type="summary",
        document_id=pdf.document_id,
        page_start=4,
        page_end=5,
        reference_id=reference.reference_id,
        tags=["review"],
    )
    assert updated.title == "Updated" and updated.tags == ["review"]
    assert repository.archive(first.note_id).status == ReadingNoteStatus.ARCHIVED
    assert repository.reactivate(first.note_id).status == ReadingNoteStatus.ACTIVE
    assert repository.count_by_source(source.source_id) == 2
    assert not hasattr(repository, "delete")


def test_evidence_repository_insert_lists_search_exact_and_lifecycle() -> None:
    database, source, _, _, _, pdf, _, _ = _database()
    repository = ConceptEvidenceRepository(database)
    annotation = DocumentAnnotation(
        document_id=pdf.document_id,
        source_id=source.source_id,
        kind="highlight",
    )
    AnnotationRepository(database).insert(annotation)
    note = ReadingNote(
        document_id=pdf.document_id,
        source_id=source.source_id,
        title="note",
        body="body",
    )
    ReadingNoteRepository(database).insert(note)
    links = (
        ConceptEvidenceLink(
            concept_legacy_id="compactness",
            concept_legacy_source="Legacy Topology",
            source_id=source.source_id,
            annotation_id=annotation.annotation_id,
            link_type="definition_source",
        ),
        ConceptEvidenceLink(
            concept_legacy_id="compactness",
            concept_legacy_source="Legacy Topology",
            source_id=source.source_id,
            note_id=note.note_id,
            link_type="proof_source",
        ),
        ConceptEvidenceLink(
            concept_legacy_id="compactness",
            concept_legacy_source="Legacy Topology",
            source_id=source.source_id,
            document_id=pdf.document_id,
            page_number=8,
            link_type="citation",
        ),
    )
    for link in links:
        repository.insert(link)

    assert (
        repository.get_by_id(links[0].evidence_link_id).evidence_link_id
        == links[0].evidence_link_id
    )
    assert repository.list_by_annotation(annotation.annotation_id).total == 1
    assert repository.list_by_note(note.note_id).total == 1
    assert repository.list_by_source(source.source_id, page_size=2).total == 3
    assert repository.list_by_concept("compactness", "Legacy Topology").total == 3
    assert repository.search("Topology").total == 3
    assert repository.find_exact(links[0]).evidence_link_id == links[0].evidence_link_id
    assert repository.archive(links[0].evidence_link_id).status == EvidenceLinkStatus.ARCHIVED
    assert repository.reactivate(links[0].evidence_link_id).status == EvidenceLinkStatus.ACTIVE
    assert repository.count_by_concept("compactness", "Legacy Topology") == 3
    assert not hasattr(repository, "delete")


class _AggregateCollection:
    def __init__(self, result: list[dict[str, Any]]) -> None:
        self.result = result
        self.pipeline: list[dict[str, Any]] | None = None

    def aggregate(self, pipeline: list[dict[str, Any]]):
        self.pipeline = copy.deepcopy(pipeline)
        return iter(copy.deepcopy(self.result))


class _AggregateDatabase:
    def __init__(self, collection: _AggregateCollection) -> None:
        self.collection = collection

    def __getitem__(self, _name: str):
        return self.collection


def test_evidence_document_list_joins_indirect_targets_before_server_pagination() -> None:
    source = Source(name="Join")
    document = _web(source)
    link = ConceptEvidenceLink(
        concept_legacy_id="c",
        concept_legacy_source="legacy",
        source_id=source.source_id,
        annotation_id=DocumentAnnotation(
            document_id=document.document_id,
            source_id=source.source_id,
            kind="highlight",
        ).annotation_id,
        link_type="citation",
    )
    collection = _AggregateCollection(
        [{"items": [link.model_dump(mode="python")], "total": [{"value": 3}]}]
    )
    page = ConceptEvidenceRepository(_AggregateDatabase(collection)).list_by_document(
        document.document_id,
        page=2,
        page_size=1,
    )

    assert page.total == 3 and page.pages == 3 and page.items == (link,)
    assert [stage["$lookup"]["from"] for stage in collection.pipeline if "$lookup" in stage] == [
        DOCUMENT_ANNOTATIONS_COLLECTION,
        READING_NOTES_COLLECTION,
    ]
    match = next(stage["$match"] for stage in collection.pipeline if "$match" in stage)
    assert {"_annotation.document_id": document.document_id} in match["$or"]
    facet = next(stage["$facet"] for stage in collection.pipeline if "$facet" in stage)
    assert {"$skip": 1} in facet["items"] and {"$limit": 1} in facet["items"]


def test_service_creates_pdf_web_annotations_and_document_and_source_notes() -> None:
    database, source, _, reference, _, pdf, web, _ = _database()
    service = ReadingAnnotationService(database)

    highlight = service.create_annotation(
        pdf.document_id,
        kind="highlight",
        page_number=4,
        quote_text="manual",
        reference_id=reference.reference_id,
    )
    comment = service.create_annotation(web.document_id, kind="comment", body="Web comment")
    document_note = service.create_note(
        source_id=source.source_id,
        document_id=pdf.document_id,
        reference_id=reference.reference_id,
        title="Proof",
        body="Details",
        note_type="proof",
        page_start=4,
    )
    source_note = service.create_note(
        source_id=source.source_id,
        title="General",
        body="Source overview",
    )

    assert highlight.completed and highlight.value.page_number == 4
    assert comment.completed and comment.value.page_number is None
    assert document_note.completed and document_note.value.document_id == pdf.document_id
    assert source_note.completed and source_note.value.document_id is None
    assert service.list_document_annotations(pdf.document_id, status=None).value.total == 1
    assert service.list_document_notes(pdf.document_id).value.total == 1
    assert service.list_source_notes(source.source_id).value.total == 2
    source_only_page = service.list_source_notes(
        source.source_id,
        source_only=True,
        page_size=1,
    ).value
    assert source_only_page.total == 1
    assert source_only_page.items[0].document_id is None
    assert database["concepts"].documents == [
        {"id": "compactness", "source": "Legacy Topology", "name": "Compactness"}
    ]


def test_service_creates_three_evidence_targets_and_blocks_exact_duplicate() -> None:
    database, source, _, _, _, pdf, _, _ = _database()
    service = ReadingAnnotationService(database)
    annotation = service.create_annotation(pdf.document_id, kind="underline", page_number=2).value
    note = service.create_note(
        source_id=source.source_id,
        document_id=pdf.document_id,
        title="N",
        body="B",
    ).value

    annotation_link = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        annotation_id=annotation.annotation_id,
        link_type="definition_source",
    )
    note_link = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        note_id=note.note_id,
        link_type="proof_source",
    )
    direct = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        document_id=pdf.document_id,
        page_number=9,
        link_type="citation",
    )
    duplicate = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        annotation_id=annotation.annotation_id,
        link_type="definition_source",
        comment="comment does not change exact identity",
    )

    assert annotation_link.completed and note_link.completed and direct.completed
    assert duplicate.status == ReadingAnnotationOperationStatus.CONFLICT
    assert service.list_annotation_evidence(annotation.annotation_id).value.total == 1
    assert service.list_note_evidence(note.note_id).value.total == 1
    assert service.list_concept_evidence("compactness", "Legacy Topology").value.total == 3


def test_service_blocks_missing_or_incompatible_associations_without_legacy_writes() -> None:
    database, source, other_source, reference, other_reference, pdf, _, archived = _database()
    service = ReadingAnnotationService(database)
    before_concepts = database["concepts"].documents
    missing_document = _web(source)

    assert service.create_annotation(missing_document.document_id, kind="highlight").status == (
        ReadingAnnotationOperationStatus.NOT_FOUND
    )
    assert service.create_annotation(archived.document_id, kind="highlight").status == (
        ReadingAnnotationOperationStatus.ARCHIVED
    )
    assert (
        service.create_annotation(
            pdf.document_id,
            kind="highlight",
            reference_id=other_reference.reference_id,
        ).status
        == ReadingAnnotationOperationStatus.CONFLICT
    )
    assert (
        service.create_note(
            source_id=source.source_id,
            document_id=pdf.document_id,
            reference_id=other_reference.reference_id,
            title="bad",
            body="bad",
        ).status
        == ReadingAnnotationOperationStatus.CONFLICT
    )
    assert (
        service.create_note(
            source_id=other_source.source_id,
            document_id=pdf.document_id,
            title="bad",
            body="bad",
        ).status
        == ReadingAnnotationOperationStatus.CONFLICT
    )
    assert (
        service.create_concept_evidence_link(
            concept_legacy_id="missing",
            concept_legacy_source="Legacy Topology",
            source_id=source.source_id,
            document_id=pdf.document_id,
            page_number=1,
            link_type="citation",
        ).status
        == ReadingAnnotationOperationStatus.BLOCKED
    )
    assert database["concepts"].documents == before_concepts
    assert reference.reference_id == pdf.reference_id


def test_service_blocks_incompatible_or_archived_evidence_targets() -> None:
    database, source, other_source, _, _, pdf, _, _ = _database()
    service = ReadingAnnotationService(database)
    annotation = service.create_annotation(pdf.document_id, kind="highlight").value
    note = service.create_note(
        source_id=source.source_id,
        document_id=pdf.document_id,
        title="note",
        body="body",
    ).value
    service.archive_annotation(annotation.annotation_id)

    archived_target = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        annotation_id=annotation.annotation_id,
        link_type="citation",
    )
    wrong_source = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=other_source.source_id,
        note_id=note.note_id,
        link_type="citation",
    )
    dangling = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        annotation_id=DocumentAnnotation(
            document_id=pdf.document_id,
            source_id=source.source_id,
            kind="highlight",
        ).annotation_id,
        link_type="citation",
    )

    assert archived_target.status == ReadingAnnotationOperationStatus.ARCHIVED
    assert wrong_source.status == ReadingAnnotationOperationStatus.CONFLICT
    assert dangling.status == ReadingAnnotationOperationStatus.BLOCKED


def test_service_updates_and_archives_reactivates_all_entities() -> None:
    database, source, _, _, _, pdf, _, _ = _database()
    service = ReadingAnnotationService(database)
    annotation = service.create_annotation(pdf.document_id, kind="highlight").value
    note = service.create_note(
        source_id=source.source_id,
        document_id=pdf.document_id,
        title="note",
        body="body",
    ).value
    link = service.create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        note_id=note.note_id,
        link_type="citation",
    ).value

    updated_annotation = service.update_annotation(
        annotation.annotation_id,
        kind="question",
        body="Why?",
        page_number=7,
        tags=["question"],
    )
    updated_note = service.update_note(
        note.note_id,
        title="updated",
        body="updated body",
        note_type="summary",
        document_id=pdf.document_id,
        page_start=7,
        tags=["summary"],
    )
    assert updated_annotation.value.body == "Why?"
    assert updated_note.value.title == "updated"
    assert (
        service.archive_annotation(annotation.annotation_id).value.status
        == AnnotationStatus.ARCHIVED
    )
    assert (
        service.reactivate_annotation(annotation.annotation_id).value.status
        == AnnotationStatus.ACTIVE
    )
    assert service.archive_note(note.note_id).value.status == ReadingNoteStatus.ARCHIVED
    assert service.reactivate_note(note.note_id).value.status == ReadingNoteStatus.ACTIVE
    assert (
        service.archive_evidence_link(link.evidence_link_id).value.status
        == EvidenceLinkStatus.ARCHIVED
    )
    assert (
        service.reactivate_evidence_link(link.evidence_link_id).value.status
        == EvidenceLinkStatus.ACTIVE
    )


def test_service_write_gate_scope_search_bounds_and_no_cross_collection_writes() -> None:
    database, source, _, _, _, pdf, _, _ = _database(ready=False)
    service = ReadingAnnotationService(database)
    before_sources = database["sources"].documents
    before_documents = database["source_documents"].documents
    before_concepts = database["concepts"].documents

    blocked = service.create_annotation(pdf.document_id, kind="highlight")
    assert blocked.status == ReadingAnnotationOperationStatus.INVALID_STATE
    ReadingAnnotationIndexManager(database).apply()
    assert (
        service.create_annotation(
            pdf.document_id,
            kind="highlight",
            user_scope="remote",
        ).status
        == ReadingAnnotationOperationStatus.INVALID_STATE
    )
    assert service.search_annotations("x" * 201).status == (
        ReadingAnnotationOperationStatus.INVALID_STATE
    )
    assert service.search_notes("x" * 201).status == ReadingAnnotationOperationStatus.INVALID_STATE
    assert service.search_evidence("x" * 201).status == (
        ReadingAnnotationOperationStatus.INVALID_STATE
    )
    assert database["sources"].documents == before_sources
    assert database["source_documents"].documents == before_documents
    assert database["concepts"].documents == before_concepts


def test_update_and_reactivate_revalidate_authoritative_associations_but_archive_cleans_up() -> (
    None
):
    database, source, _, reference, _, pdf, _, _ = _database()
    service = ReadingAnnotationService(database)
    annotation = service.create_annotation(
        pdf.document_id,
        kind="highlight",
        reference_id=reference.reference_id,
    ).value
    source_note = service.create_note(
        source_id=source.source_id,
        reference_id=reference.reference_id,
        title="source note",
        body="body",
    ).value

    database._documents["references"].clear()
    annotation_archive = service.archive_annotation(annotation.annotation_id)
    note_archive = service.archive_note(source_note.note_id)
    annotation_reactivate = service.reactivate_annotation(annotation.annotation_id)
    note_reactivate = service.reactivate_note(source_note.note_id)

    assert annotation_archive.completed and note_archive.completed
    assert annotation_reactivate.status == ReadingAnnotationOperationStatus.NOT_FOUND
    assert note_reactivate.status == ReadingAnnotationOperationStatus.NOT_FOUND

    database._documents["references"].append(reference.model_dump(mode="python"))
    service.reactivate_annotation(annotation.annotation_id)
    database._documents["source_documents"][0]["source_id"] = Source(name="Corrupt").source_id
    assert service.update_annotation(
        annotation.annotation_id,
        kind="highlight",
        body="",
    ).status in {
        ReadingAnnotationOperationStatus.NOT_FOUND,
        ReadingAnnotationOperationStatus.CONFLICT,
    }


def test_ambiguous_legacy_concept_blocks_evidence_without_writes() -> None:
    database, source, _, _, _, pdf, _, _ = _database()
    database._documents["concepts"].append(
        {"id": "compactness", "source": "Legacy Topology", "name": "Duplicate"}
    )
    result = ReadingAnnotationService(database).create_concept_evidence_link(
        concept_legacy_id="compactness",
        concept_legacy_source="Legacy Topology",
        source_id=source.source_id,
        document_id=pdf.document_id,
        page_number=1,
        link_type="citation",
    )

    assert result.status == ReadingAnnotationOperationStatus.BLOCKED
    assert database[CONCEPT_EVIDENCE_LINKS_COLLECTION].documents == []


def test_legacy_concept_composite_identity_preserves_exact_source_text() -> None:
    database, source, _, _, _, pdf, _, _ = _database()
    database._documents["concepts"].append(
        {"id": "spaced", "source": " Exact Legacy Source ", "name": "Exact"}
    )
    service = ReadingAnnotationService(database)
    exact = service.create_concept_evidence_link(
        concept_legacy_id="spaced",
        concept_legacy_source=" Exact Legacy Source ",
        source_id=source.source_id,
        document_id=pdf.document_id,
        page_number=3,
        link_type="citation",
    )
    normalized = service.create_concept_evidence_link(
        concept_legacy_id="spaced",
        concept_legacy_source="Exact Legacy Source",
        source_id=source.source_id,
        document_id=pdf.document_id,
        page_number=4,
        link_type="citation",
    )

    assert exact.completed
    assert exact.value.concept_legacy_source == " Exact Legacy Source "
    assert normalized.status == ReadingAnnotationOperationStatus.BLOCKED


def test_importing_s4_modules_has_no_database_or_filesystem_side_effects() -> None:
    import mathmongo.reading_annotations as package
    import mathmongo.reading_annotations.indexes as indexes
    import mathmongo.reading_annotations.models as models
    import mathmongo.reading_annotations.repository as repository
    import mathmongo.reading_annotations.service as service

    assert package.DocumentAnnotation is models.DocumentAnnotation
    assert indexes.DOCUMENT_ANNOTATIONS_COLLECTION == "document_annotations"
    assert repository.AnnotationRepository.COLLECTION == "document_annotations"
    assert service.ReadingAnnotationOperationStatus.SUCCESS.value == "success"

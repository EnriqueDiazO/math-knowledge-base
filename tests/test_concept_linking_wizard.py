"""Pure orchestration tests for the S4.3 guided-link save operation."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from editor.concept_linking.linking_wizard import save_guided_link
from editor.concept_linking.view_models import ConceptLinkingContext
from editor.concept_linking.view_models import ConceptSummary
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import ReadingNote

SOURCE_ID = "src_00000000-0000-4000-8000-000000000001"
REFERENCE_ID = "ref_00000000-0000-4000-8000-000000000002"
ALTERNATE_REFERENCE_ID = "ref_00000000-0000-4000-8000-000000000003"
PDF_DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000004"
WEB_DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000005"
EXISTING_ANNOTATION_ID = "ann_00000000-0000-4000-8000-000000000006"
NEW_ANNOTATION_ID = "ann_00000000-0000-4000-8000-000000000007"
EXISTING_NOTE_ID = "note_00000000-0000-4000-8000-000000000008"
NEW_NOTE_ID = "note_00000000-0000-4000-8000-000000000009"
SEEDED_EVIDENCE_ID = "ev_00000000-0000-4000-8000-000000000010"


class FakeResult:
    def __init__(self, value: Any = None, *, status: str = "success", message: str = "") -> None:
        self.value = value
        self.status = SimpleNamespace(value=status)
        self.message = message

    @property
    def completed(self) -> bool:
        return self.status.value == "success"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _exact_identity(link: ConceptEvidenceLink) -> tuple[object, ...]:
    return (
        link.concept_legacy_source,
        link.concept_legacy_id,
        link.source_id,
        link.reference_id,
        link.document_id,
        link.annotation_id,
        link.note_id,
        link.page_number,
        _enum_value(link.link_type),
    )


class FakeEvidenceRepository:
    def __init__(self) -> None:
        self.links: list[ConceptEvidenceLink] = []
        self.find_calls: list[ConceptEvidenceLink] = []

    def find_exact(self, candidate: ConceptEvidenceLink) -> ConceptEvidenceLink | None:
        self.find_calls.append(candidate)
        identity = _exact_identity(candidate)
        return next((item for item in self.links if _exact_identity(item) == identity), None)

    def seed(self, link: ConceptEvidenceLink) -> ConceptEvidenceLink:
        self.links.append(link)
        return link


class FakeService:
    """Small stateful S4 fake that records attempted and completed writes separately."""

    def __init__(self) -> None:
        self.evidence = FakeEvidenceRepository()
        self.annotations: dict[str, DocumentAnnotation] = {}
        self.notes: dict[str, ReadingNote] = {}
        self.annotation_get_calls: list[tuple[str, str]] = []
        self.note_get_calls: list[tuple[str, str]] = []
        self.annotation_create_calls: list[tuple[str, dict[str, Any]]] = []
        self.note_create_calls: list[dict[str, Any]] = []
        self.link_calls: list[dict[str, Any]] = []
        self.fail_link_attempts = 0
        self._evidence_sequence = 100

    def add_annotation(
        self,
        *,
        annotation_id: str = EXISTING_ANNOTATION_ID,
        document_id: str = PDF_DOCUMENT_ID,
        reference_id: str | None = REFERENCE_ID,
        page_number: int | None = 9,
    ) -> DocumentAnnotation:
        annotation = DocumentAnnotation(
            annotation_id=annotation_id,
            document_id=document_id,
            source_id=SOURCE_ID,
            reference_id=reference_id,
            kind="highlight",
            page_number=page_number,
            quote_text="Existing quotation",
        )
        self.annotations[annotation.annotation_id] = annotation
        return annotation

    def add_note(
        self,
        *,
        note_id: str = EXISTING_NOTE_ID,
        document_id: str | None = PDF_DOCUMENT_ID,
        reference_id: str | None = REFERENCE_ID,
        page_start: int | None = 9,
    ) -> ReadingNote:
        note = ReadingNote(
            note_id=note_id,
            document_id=document_id,
            source_id=SOURCE_ID,
            reference_id=reference_id,
            title="Existing note",
            body="Existing note body",
            note_type="idea",
            page_start=page_start,
        )
        self.notes[note.note_id] = note
        return note

    def get_annotation(self, annotation_id: str, *, user_scope: str) -> FakeResult:
        self.annotation_get_calls.append((annotation_id, user_scope))
        item = self.annotations.get(annotation_id)
        return FakeResult(item) if item is not None else FakeResult(status="not_found")

    def get_note(self, note_id: str, *, user_scope: str) -> FakeResult:
        self.note_get_calls.append((note_id, user_scope))
        item = self.notes.get(note_id)
        return FakeResult(item) if item is not None else FakeResult(status="not_found")

    def create_annotation(self, document_id: str, **kwargs: Any) -> FakeResult:
        self.annotation_create_calls.append((document_id, dict(kwargs)))
        annotation = DocumentAnnotation(
            annotation_id=NEW_ANNOTATION_ID,
            document_id=document_id,
            source_id=SOURCE_ID,
            reference_id=kwargs.get("reference_id"),
            user_scope=kwargs.get("user_scope", "local"),
            kind=kwargs["kind"],
            body=kwargs.get("body", ""),
            page_number=kwargs.get("page_number"),
            quote_text=kwargs.get("quote_text"),
            tags=kwargs.get("tags", ()),
        )
        self.annotations[annotation.annotation_id] = annotation
        return FakeResult(annotation)

    def create_note(self, **kwargs: Any) -> FakeResult:
        self.note_create_calls.append(dict(kwargs))
        note = ReadingNote(
            note_id=NEW_NOTE_ID,
            source_id=kwargs["source_id"],
            document_id=kwargs.get("document_id"),
            reference_id=kwargs.get("reference_id"),
            user_scope=kwargs.get("user_scope", "local"),
            title=kwargs["title"],
            body=kwargs["body"],
            note_type=kwargs["note_type"],
            page_start=kwargs.get("page_start"),
            page_end=kwargs.get("page_end"),
            tags=kwargs.get("tags", ()),
        )
        self.notes[note.note_id] = note
        return FakeResult(note)

    def create_concept_evidence_link(self, **kwargs: Any) -> FakeResult:
        self.link_calls.append(dict(kwargs))
        if self.fail_link_attempts:
            self.fail_link_attempts -= 1
            return FakeResult(status="error", message="injected link failure")
        evidence_id = f"ev_00000000-0000-4000-8000-{self._evidence_sequence:012d}"
        self._evidence_sequence += 1
        link = ConceptEvidenceLink(evidence_link_id=evidence_id, **kwargs)
        self.evidence.seed(link)
        return FakeResult(link)


@pytest.fixture
def concept() -> ConceptSummary:
    return ConceptSummary(
        concept_id="spherical-metric",
        concept_source=" Pommerenke1991 ",
        title="Métrica esférica",
        concept_type="definition",
        categories=("Análisis complejo",),
    )


def _context(*, kind: str = "pdf") -> ConceptLinkingContext:
    is_pdf = kind == "pdf"
    return ConceptLinkingContext(
        database_name="isolated_concept_linking",
        document_id=PDF_DOCUMENT_ID if is_pdf else WEB_DOCUMENT_ID,
        document_title="Boundary Behaviour of Conformal Maps",
        document_kind=kind,
        source_id=SOURCE_ID,
        source_name="Pommerenke1991BoundaryBehaviourConformalMaps",
        reference_id=REFERENCE_ID,
        reference_title="Boundary Behaviour of Conformal Maps",
        pdf_page=9 if is_pdf else None,
        book_page_label="1" if is_pdf else None,
        reading_status="in_progress",
        web_url=None if is_pdf else "https://example.test/resource",
    )


def _save_new_target(
    service: FakeService,
    concept: ConceptSummary,
    *,
    mode: str,
    context: ConceptLinkingContext | None = None,
):
    draft = (
        {
            "annotation_draft": {
                "kind": "highlight",
                "body": "A logical highlight",
                "page_number": 9,
                "quote_text": "spherical metric",
                "tags": ("metric", "boundary"),
            }
        }
        if mode == "annotation"
        else {
            "note_draft": {
                "title": "Métrica esférica",
                "body": "Esta nota explica la definición.",
                "note_type": "definition",
                "document_bound": True,
                "page_start": 9,
                "page_end": 10,
                "tags": ("metric",),
            }
        }
    )
    return save_guided_link(
        service,
        concept=concept,
        context=context or _context(),
        mode=mode,
        link_type="definition_source",
        comment="Es evidencia primaria.",
        **draft,
    )


def test_direct_page_saves_type_and_comment_without_creating_a_target(
    concept: ConceptSummary,
) -> None:
    service = FakeService()

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode="page",
        page_number=9,
        link_type="definition_source",
        comment="  Aquí se introduce la métrica.  ",
    )

    assert result.completed
    assert result.created_target is False
    assert result.target_kind is None and result.target_id is None
    assert service.annotation_create_calls == []
    assert service.note_create_calls == []
    assert len(service.link_calls) == len(service.evidence.links) == 1
    values = service.link_calls[0]
    assert values == {
        "concept_legacy_id": concept.concept_id,
        "concept_legacy_source": concept.concept_source,
        "source_id": SOURCE_ID,
        "reference_id": REFERENCE_ID,
        "document_id": PDF_DOCUMENT_ID,
        "annotation_id": None,
        "note_id": None,
        "page_number": 9,
        "link_type": "definition_source",
        "comment": "Aquí se introduce la métrica.",
    }


def test_existing_annotation_is_used_without_creating_or_filling_a_direct_target(
    concept: ConceptSummary,
) -> None:
    service = FakeService()
    annotation = service.add_annotation(reference_id=None)

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode="annotation",
        target_id=annotation.annotation_id,
        link_type="citation",
    )

    assert result.completed and not result.created_target
    assert result.target_kind == "annotation" and result.target_id == annotation.annotation_id
    assert service.annotation_get_calls == [(annotation.annotation_id, "local")]
    assert service.annotation_create_calls == []
    values = service.link_calls[0]
    assert values["annotation_id"] == annotation.annotation_id
    assert values["reference_id"] is None
    assert values["document_id"] is None
    assert values["note_id"] is None
    assert values["page_number"] is None


def test_new_annotation_is_saved_then_linked_with_its_generated_identity(
    concept: ConceptSummary,
) -> None:
    service = FakeService()

    result = _save_new_target(service, concept, mode="annotation")

    assert result.completed and result.created_target
    assert result.target_kind == "annotation" and result.target_id == NEW_ANNOTATION_ID
    assert len(service.annotation_create_calls) == 1
    document_id, draft = service.annotation_create_calls[0]
    assert document_id == PDF_DOCUMENT_ID
    assert draft["kind"] == "highlight"
    assert draft["page_number"] == 9
    assert draft["quote_text"] == "spherical metric"
    assert draft["tags"] == ("metric", "boundary")
    assert draft["reference_id"] == REFERENCE_ID
    assert draft["user_scope"] == "local"
    values = service.link_calls[0]
    assert values["annotation_id"] == NEW_ANNOTATION_ID
    assert values["reference_id"] == REFERENCE_ID
    assert values["document_id"] is None and values["page_number"] is None


def test_existing_note_uses_the_notes_reference_and_never_fills_document_target(
    concept: ConceptSummary,
) -> None:
    service = FakeService()
    note = service.add_note(reference_id=ALTERNATE_REFERENCE_ID)

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode="note",
        target_id=note.note_id,
        link_type="related_context",
        comment="Una explicación complementaria.",
    )

    assert result.completed and not result.created_target
    assert result.target_kind == "note" and result.target_id == note.note_id
    assert service.note_get_calls == [(note.note_id, "local")]
    assert service.note_create_calls == []
    values = service.link_calls[0]
    assert values["note_id"] == note.note_id
    assert values["reference_id"] == ALTERNATE_REFERENCE_ID
    assert values["document_id"] is None
    assert values["annotation_id"] is None
    assert values["page_number"] is None


def test_new_note_is_saved_then_linked_with_document_page_range(
    concept: ConceptSummary,
) -> None:
    service = FakeService()

    result = _save_new_target(service, concept, mode="note")

    assert result.completed and result.created_target
    assert result.target_kind == "note" and result.target_id == NEW_NOTE_ID
    assert len(service.note_create_calls) == 1
    draft = service.note_create_calls[0]
    assert draft["source_id"] == SOURCE_ID
    assert draft["document_id"] == PDF_DOCUMENT_ID
    assert draft["reference_id"] == REFERENCE_ID
    assert draft["title"] == "Métrica esférica"
    assert draft["body"] == "Esta nota explica la definición."
    assert draft["note_type"] == "definition"
    assert (draft["page_start"], draft["page_end"]) == (9, 10)
    assert draft["tags"] == ("metric",)
    assert draft["user_scope"] == "local"
    values = service.link_calls[0]
    assert values["note_id"] == NEW_NOTE_ID
    assert values["document_id"] is None and values["page_number"] is None


@pytest.mark.parametrize(
    ("mode", "target_id", "target_collection", "create_calls"),
    (
        ("annotation", NEW_ANNOTATION_ID, "annotations", "annotation_create_calls"),
        ("note", NEW_NOTE_ID, "notes", "note_create_calls"),
    ),
)
def test_partial_result_preserves_target_and_retry_links_without_recreating_it(
    concept: ConceptSummary,
    mode: str,
    target_id: str,
    target_collection: str,
    create_calls: str,
) -> None:
    service = FakeService()
    service.fail_link_attempts = 1

    partial = _save_new_target(service, concept, mode=mode)

    assert partial.status == "partial"
    assert partial.completed is False
    assert partial.created_target is True
    assert partial.target_kind == mode and partial.target_id == target_id
    assert target_id in getattr(service, target_collection)
    assert len(getattr(service, create_calls)) == 1
    assert len(service.link_calls) == 1
    assert service.evidence.links == []

    retried = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode=mode,
        target_id=partial.target_id,
        link_type="definition_source",
        comment="Es evidencia primaria.",
    )

    assert retried.completed
    assert retried.created_target is False
    assert retried.target_kind == mode and retried.target_id == target_id
    assert len(getattr(service, create_calls)) == 1
    assert len(service.link_calls) == 2
    assert len(service.evidence.links) == 1


def test_exact_duplicate_returns_existing_link_without_a_second_write(
    concept: ConceptSummary,
) -> None:
    service = FakeService()
    existing = service.evidence.seed(
        ConceptEvidenceLink(
            evidence_link_id=SEEDED_EVIDENCE_ID,
            concept_legacy_id=concept.concept_id,
            concept_legacy_source=concept.concept_source,
            source_id=SOURCE_ID,
            reference_id=REFERENCE_ID,
            document_id=PDF_DOCUMENT_ID,
            page_number=9,
            link_type="definition_source",
            comment="Original comment",
        )
    )

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode="page",
        page_number=9,
        link_type="definition_source",
        comment="A changed comment does not change exact identity.",
    )

    assert result.status == "duplicate"
    assert result.link is existing
    assert service.link_calls == []
    assert service.evidence.links == [existing]
    assert service.annotation_create_calls == [] and service.note_create_calls == []


def test_same_target_with_a_different_link_type_is_allowed(concept: ConceptSummary) -> None:
    service = FakeService()
    annotation = service.add_annotation()
    existing = service.evidence.seed(
        ConceptEvidenceLink(
            evidence_link_id=SEEDED_EVIDENCE_ID,
            concept_legacy_id=concept.concept_id,
            concept_legacy_source=concept.concept_source,
            source_id=SOURCE_ID,
            reference_id=REFERENCE_ID,
            annotation_id=annotation.annotation_id,
            link_type="definition_source",
        )
    )

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode="annotation",
        target_id=annotation.annotation_id,
        link_type="proof_source",
    )

    assert result.completed
    assert len(service.link_calls) == 1
    assert len(service.evidence.links) == 2
    assert service.evidence.links[0] is existing
    assert {_enum_value(item.link_type) for item in service.evidence.links} == {
        "definition_source",
        "proof_source",
    }


def test_direct_web_link_is_unsupported_and_performs_no_write(
    concept: ConceptSummary,
) -> None:
    service = FakeService()

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(kind="web"),
        mode="page",
        page_number=1,
        link_type="citation",
        comment="No synthetic web page may be persisted.",
    )

    assert result.status == "unsupported"
    assert service.link_calls == []
    assert service.evidence.find_calls == []
    assert service.annotation_create_calls == []
    assert service.note_create_calls == []


@pytest.mark.parametrize("mode", ("annotation", "note"))
def test_existing_indirect_web_targets_can_be_linked(
    concept: ConceptSummary,
    mode: str,
) -> None:
    service = FakeService()
    target = (
        service.add_annotation(document_id=WEB_DOCUMENT_ID, page_number=None)
        if mode == "annotation"
        else service.add_note(document_id=WEB_DOCUMENT_ID, page_start=None)
    )
    target_id = target.annotation_id if mode == "annotation" else target.note_id

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(kind="web"),
        mode=mode,
        target_id=target_id,
        link_type="citation",
    )

    assert result.completed
    assert result.target_kind == mode and result.target_id == target_id
    assert len(service.link_calls) == 1
    values = service.link_calls[0]
    assert values["document_id"] is None and values["page_number"] is None
    assert values[f"{mode}_id"] == target_id


@pytest.mark.parametrize("page_number", (None, 0, -1, True, "9"))
def test_invalid_direct_page_is_rejected_without_writes(
    concept: ConceptSummary,
    page_number: object,
) -> None:
    service = FakeService()

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode="page",
        page_number=page_number,  # type: ignore[arg-type]
        link_type="citation",
    )

    assert result.status == "invalid"
    assert service.link_calls == []
    assert service.evidence.find_calls == []


@pytest.mark.parametrize(
    ("mode", "link_type"),
    (("unknown", "citation"), ("page", "unknown")),
)
def test_invalid_mode_or_link_type_is_rejected_before_any_write(
    concept: ConceptSummary,
    mode: str,
    link_type: str,
) -> None:
    service = FakeService()

    result = save_guided_link(
        service,
        concept=concept,
        context=_context(),
        mode=mode,
        page_number=9,
        link_type=link_type,
    )

    assert result.status == "invalid"
    assert service.link_calls == []
    assert service.annotation_create_calls == [] and service.note_create_calls == []

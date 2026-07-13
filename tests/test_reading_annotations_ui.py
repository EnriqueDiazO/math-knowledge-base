"""Focused fake-render and static safety tests for the S4 Notes & Evidence UI."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

import ast
import inspect
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from editor.reading_annotations.annotation_panel import render_notes_and_evidence_panel
from editor.reading_annotations.concept_picker import find_legacy_concepts
from editor.reading_annotations.evidence_panel import evidence_rows
from editor.reading_annotations.forms import render_annotation_form
from editor.reading_annotations.forms import render_note_form
from editor.reading_annotations.navigation import render_open_document
from editor.reading_annotations.panel_utils import local_match
from editor.reading_annotations.state import ACTIVE_CONTEXT
from editor.reading_annotations.state import PENDING_PAGE_SUGGESTION
from editor.reading_annotations.state import SELECTED_ANNOTATION_ID
from editor.reading_annotations.state import SELECTED_CONCEPT_IDENTITY
from editor.reading_annotations.state import SELECTED_NOTE_ID
from editor.reading_annotations.state import SESSION_PREFIX
from editor.reading_annotations.state import apply_pending_page_suggestion
from editor.reading_annotations.state import state_key
from editor.reading_annotations.state import sync_context
from editor.reading_space import reader_page as reading_page_module
from editor.reading_space.reader_page import _render_reader_panel
from editor.reading_space.state import SELECTED_DOCUMENT_ID
from editor.reading_space.state import SELECTED_SOURCE_ID
from editor.reading_space.state import state_key as reading_space_key
from mathmongo.source_documents.models import DocumentKind

ROOT = Path(__file__).resolve().parents[1]


class FakeUI:
    def __init__(
        self,
        *,
        values: dict[str, Any] | None = None,
        clicked: set[str] | None = None,
        submitted: set[str] | None = None,
    ) -> None:
        self.values = dict(values or {})
        self.clicked = set(clicked or ())
        self.submitted = set(submitted or ())
        self.session_state: dict[str, Any] = {}
        self.messages: list[tuple[str, str]] = []
        self.labels: list[str] = []
        self.rows: list[list[dict[str, Any]]] = []
        self.reruns = 0

    def _message(self, level: str, value: object) -> None:
        self.messages.append((level, str(value)))

    def _value(self, key: str, default: Any) -> Any:
        value = self.values.get(key, self.session_state.get(key, default))
        self.session_state[key] = value
        return value

    def header(self, value: object) -> None:
        self._message("header", value)

    def subheader(self, value: object) -> None:
        self._message("subheader", value)

    def caption(self, value: object) -> None:
        self._message("caption", value)

    def info(self, value: object) -> None:
        self._message("info", value)

    def success(self, value: object) -> None:
        self._message("success", value)

    def warning(self, value: object) -> None:
        self._message("warning", value)

    def error(self, value: object) -> None:
        self._message("error", value)

    def write(self, value: object) -> None:
        self._message("write", value)

    def divider(self) -> None:
        return None

    def expander(self, *_args, **_kwargs):
        return nullcontext(self)

    def form(self, *_args, **_kwargs):
        return nullcontext(self)

    def text_input(self, label, *, key, value="", **_kwargs):
        self.labels.append(str(label))
        return self._value(key, value)

    def text_area(self, label, *, key, value="", **_kwargs):
        self.labels.append(str(label))
        return self._value(key, value)

    def selectbox(self, label, options, *, key, index=0, **_kwargs):
        self.labels.append(str(label))
        values = tuple(options)
        return self._value(key, values[index])

    def checkbox(self, label, *, key, value=False, **_kwargs):
        self.labels.append(str(label))
        return bool(self._value(key, value))

    def number_input(self, label, *, key, value=1, **_kwargs):
        self.labels.append(str(label))
        return self._value(key, value)

    def form_submit_button(self, label, *, key, disabled=False, **_kwargs):
        self.labels.append(str(label))
        assert key.startswith(SESSION_PREFIX)
        return not disabled and label in self.submitted

    def button(self, label, *, key, disabled=False, **_kwargs):
        self.labels.append(str(label))
        return not disabled and (label in self.clicked or key in self.clicked)

    def dataframe(self, rows, **_kwargs) -> None:
        self.rows.append(list(rows))

    def rerun(self) -> None:
        self.reruns += 1


class FakeCursor(list):
    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, limit: int):
        return FakeCursor(self[:limit])

    def skip(self, count: int):
        return FakeCursor(self[count:])


class FakeCollection:
    def __init__(self, documents: tuple[dict[str, Any], ...]) -> None:
        self.documents = documents
        self.queries: list[dict[str, Any]] = []
        self.projections: list[dict[str, Any]] = []

    def find(self, query, projection):
        self.queries.append(query)
        self.projections.append(projection)
        return FakeCursor(dict(document) for document in self.documents)


class FakeDatabase:
    def __init__(self) -> None:
        self.concepts = FakeCollection(
            (
                {
                    "_id": "must-not-render",
                    "id": "C-1",
                    "source": "Legacy Book",
                    "titulo": "Compactness",
                    "tipo": "definition",
                    "categorias": ["topology"],
                },
            )
        )

    def __getitem__(self, name: str):
        assert name == "concepts"
        return self.concepts


class FakeResult:
    def __init__(self, value: Any = None, status: str = "success", message: str = "") -> None:
        self.value = value
        self.status = SimpleNamespace(value=status)
        self.message = message

    @property
    def completed(self) -> bool:
        return self.status.value == "success"


class FakeIndexManager:
    def __init__(self, initialized: bool = True) -> None:
        self.initialized = initialized

    def status(self):
        return ()

    def plan(self):
        return SimpleNamespace(initialized=self.initialized, conflicts=(), missing=())

    def apply(self):
        raise AssertionError("initialized S4 indexes must not be applied")


def _annotation(*, status: str = "active", document_id: str = "doc-pdf") -> Any:
    return SimpleNamespace(
        annotation_id="ann-1",
        document_id=document_id,
        source_id="src-1",
        reference_id="ref-1",
        user_scope="local",
        kind=SimpleNamespace(value="highlight"),
        status=SimpleNamespace(value=status),
        page_number=7 if document_id == "doc-pdf" else None,
        page_label=None,
        quote_text="manual quote",
        body="plain annotation",
        color_label="yellow",
        tags=("topology",),
        updated_at=None,
    )


def _note(
    *,
    status: str = "active",
    document_id: str | None = "doc-pdf",
    note_id: str = "note-1",
) -> Any:
    return SimpleNamespace(
        note_id=note_id,
        document_id=document_id,
        source_id="src-1",
        reference_id="ref-1",
        user_scope="local",
        title="A reading note",
        body="plain note body",
        note_type=SimpleNamespace(value="idea"),
        status=SimpleNamespace(value=status),
        page_start=7 if document_id == "doc-pdf" else None,
        page_end=8 if document_id == "doc-pdf" else None,
        tags=("insight",),
        updated_at=None,
    )


def _evidence(*, status: str = "active", target: str = "annotation") -> Any:
    return SimpleNamespace(
        evidence_link_id="ev-1",
        concept_legacy_id="C-1",
        concept_legacy_source="Legacy Book",
        source_id="src-1",
        reference_id="ref-1",
        document_id=None,
        annotation_id="ann-1" if target == "annotation" else None,
        note_id="note-1" if target == "note" else None,
        page_number=None,
        link_type=SimpleNamespace(value="definition_source"),
        status=SimpleNamespace(value=status),
        comment="supports the definition",
    )


class FakeService:
    def __init__(
        self,
        *,
        annotations: tuple[Any, ...] = (),
        notes: tuple[Any, ...] = (),
        source_notes: tuple[Any, ...] | None = None,
        evidence: tuple[Any, ...] = (),
        document_evidence: tuple[Any, ...] | None = None,
    ) -> None:
        self.index_manager = FakeIndexManager()
        self.annotations = annotations
        self.notes = notes
        self.source_notes = notes if source_notes is None else source_notes
        self.evidence = evidence
        self.document_evidence = evidence if document_evidence is None else document_evidence
        self.calls: list[tuple[str, Any]] = []
        self.source_note_list_kwargs: dict[str, Any] = {}

    @staticmethod
    def _page(items):
        values = tuple(items)
        return SimpleNamespace(items=values, page=1, page_size=50, total=len(values))

    def create_annotation(self, document_id, **kwargs):
        self.calls.append(("create_annotation", (document_id, kwargs)))
        return FakeResult(_annotation(document_id=document_id))

    def list_document_annotations(self, _document_id, **_kwargs):
        return FakeResult(self._page(self.annotations))

    def get_annotation(self, annotation_id, **_kwargs):
        return FakeResult(
            next(item for item in self.annotations if item.annotation_id == annotation_id)
        )

    def update_annotation(self, annotation_id, **kwargs):
        self.calls.append(("update_annotation", (annotation_id, kwargs)))
        return FakeResult(_annotation())

    def archive_annotation(self, annotation_id, **_kwargs):
        self.calls.append(("archive_annotation", annotation_id))
        return FakeResult(_annotation(status="archived"))

    def reactivate_annotation(self, annotation_id, **_kwargs):
        self.calls.append(("reactivate_annotation", annotation_id))
        return FakeResult(_annotation())

    def create_note(self, **kwargs):
        self.calls.append(("create_note", kwargs))
        return FakeResult(_note(document_id=kwargs["document_id"]))

    def list_document_notes(self, _document_id, **_kwargs):
        return FakeResult(self._page(self.notes))

    def list_source_notes(self, _source_id, **kwargs):
        self.source_note_list_kwargs = kwargs
        return FakeResult(self._page(self.source_notes))

    def get_note(self, note_id, **_kwargs):
        return FakeResult(next(item for item in self.notes if item.note_id == note_id))

    def update_note(self, note_id, **kwargs):
        self.calls.append(("update_note", (note_id, kwargs)))
        return FakeResult(_note(document_id=kwargs["document_id"]))

    def archive_note(self, note_id, **_kwargs):
        self.calls.append(("archive_note", note_id))
        return FakeResult(_note(status="archived"))

    def reactivate_note(self, note_id, **_kwargs):
        self.calls.append(("reactivate_note", note_id))
        return FakeResult(_note())

    def create_concept_evidence_link(self, **kwargs):
        self.calls.append(("create_evidence", kwargs))
        return FakeResult(_evidence())

    def list_document_evidence(self, _document_id, **_kwargs):
        return FakeResult(self._page(self.document_evidence))

    def list_annotation_evidence(self, annotation_id, **_kwargs):
        return FakeResult(
            self._page(item for item in self.evidence if item.annotation_id == annotation_id)
        )

    def list_note_evidence(self, note_id, **_kwargs):
        return FakeResult(self._page(item for item in self.evidence if item.note_id == note_id))

    def archive_evidence_link(self, evidence_id):
        self.calls.append(("archive_evidence", evidence_id))
        return FakeResult(_evidence(status="archived"))

    def reactivate_evidence_link(self, evidence_id):
        self.calls.append(("reactivate_evidence", evidence_id))
        return FakeResult(_evidence())


class FakeReferenceRepository:
    def list(self, **_kwargs):
        reference = SimpleNamespace(
            reference_id="ref-1",
            title="Reference one",
            bibtex=SimpleNamespace(key="ref-key"),
        )
        return SimpleNamespace(items=(reference,), total=1)


def _context(database: FakeDatabase | None = None) -> Any:
    return SimpleNamespace(
        connection_label="isolated",
        database_name="isolated_s4_ui",
        database=database or FakeDatabase(),
        reference_repository=FakeReferenceRepository(),
    )


def _reader(*, kind: str = "pdf", page: int | None = 7) -> Any:
    document_id = "doc-pdf" if kind == "pdf" else "doc-web"
    return SimpleNamespace(
        document=SimpleNamespace(
            document_id=document_id,
            source_id="src-1",
            reference_id="ref-1",
            kind=SimpleNamespace(value=kind),
            status=SimpleNamespace(value="active"),
        ),
        reading_state=SimpleNamespace(current_page=page),
    )


def _render(ui: FakeUI, service: FakeService, *, kind: str = "pdf") -> None:
    render_notes_and_evidence_panel(
        _context(),
        _reader(kind=kind, page=7 if kind == "pdf" else None),
        ui=ui,
        service=service,
    )


def test_panel_appears_and_session_context_contains_only_scalar_identity() -> None:
    ui = FakeUI()
    service = FakeService()

    _render(ui, service)

    assert ("header", "Notes & Evidence") in ui.messages
    assert ui.session_state[ACTIVE_CONTEXT][1] == "isolated_s4_ui"
    assert all(str(key).startswith(SESSION_PREFIX) for key in ui.session_state)
    assert not any(isinstance(value, FakeDatabase) for value in ui.session_state.values())


def test_selected_reader_invokes_s4_panel_independently_of_s3_write_readiness(
    monkeypatch,
) -> None:
    ui = FakeUI()
    ui.session_state[SELECTED_DOCUMENT_ID] = "doc-pdf"
    reader = _reader()
    reader.document.kind = DocumentKind.PDF
    service = SimpleNamespace(get_reader_context=lambda *_args, **_kwargs: FakeResult(reader))
    calls: list[tuple[Any, Any]] = []
    monkeypatch.setattr(reading_page_module, "_render_pdf_reader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        reading_page_module,
        "_render_s4_panel",
        lambda context, value, **_kwargs: calls.append((context, value)),
    )
    context = _context()

    _render_reader_panel(ui, context, service, actions_enabled=False)

    assert calls == [(context, reader)]


def test_pdf_annotation_uses_s3_current_page_as_suggestion() -> None:
    ui = FakeUI(submitted={"Add Annotation"})
    service = FakeService()

    _render(ui, service, kind="pdf")

    call = next(value for name, value in service.calls if name == "create_annotation")
    assert call[1]["page_number"] == 7
    assert "Page number" in ui.labels


def test_web_annotation_and_note_render_without_page_controls() -> None:
    ui = FakeUI(submitted={"Add Annotation", "Add Reading Note"})
    service = FakeService()

    _render(ui, service, kind="web")

    annotation = next(value for name, value in service.calls if name == "create_annotation")
    note = next(value for name, value in service.calls if name == "create_note")
    assert annotation[1]["page_number"] is None
    assert note["page_start"] is None and note["page_end"] is None
    assert not any("Page " in label or "PDF page" in label for label in ui.labels)


def test_add_source_only_reading_note_uses_plain_text_values() -> None:
    document_id = "doc-pdf"
    ui = FakeUI(
        values={
            state_key("add_note", "title", document_id): "  Main idea  ",
            state_key("add_note", "body", document_id): "  User text  ",
            state_key("add_note", "link_document", document_id): False,
            state_key("add_note", "tags", document_id): "one, two",
        },
        submitted={"Add Reading Note"},
    )
    service = FakeService()

    _render(ui, service)

    call = next(value for name, value in service.calls if name == "create_note")
    assert call["title"] == "Main idea"
    assert call["body"] == "User text"
    assert call["document_id"] is None
    assert call["tags"] == ("one", "two")


def test_source_only_note_remains_visible_beside_current_document() -> None:
    source_only = _note(document_id=None, note_id="note-source-only")
    ui = FakeUI()
    bound_notes = tuple(_note(note_id=f"note-{index}") for index in range(50))
    service = FakeService(notes=bound_notes, source_notes=(source_only,))

    _render(ui, service)

    assert any(row.get("note_id") == "note-source-only" for table in ui.rows for row in table)
    assert service.source_note_list_kwargs["source_only"] is True


def test_uninitialized_s4_indexes_disable_add_forms_independently() -> None:
    ui = FakeUI(submitted={"Add Annotation", "Add Reading Note"})
    service = FakeService()
    service.index_manager = FakeIndexManager(initialized=False)

    _render(ui, service)

    assert service.calls == []


def test_edit_note_and_annotation_use_controlled_update_methods() -> None:
    ui = FakeUI(
        clicked={"Edit note", "Edit annotation"},
        submitted={"Save Reading Note", "Save Annotation"},
    )
    service = FakeService(annotations=(_annotation(),), notes=(_note(),))

    _render(ui, service)

    assert any(name == "update_annotation" for name, _value in service.calls)
    assert any(name == "update_note" for name, _value in service.calls)
    assert SELECTED_ANNOTATION_ID not in ui.session_state
    assert SELECTED_NOTE_ID not in ui.session_state


def test_archive_and_reactivate_annotation_and_note() -> None:
    active_ui = FakeUI(clicked={"Archive annotation", "Archive note"})
    active_service = FakeService(annotations=(_annotation(),), notes=(_note(),))
    _render(active_ui, active_service)

    archived_ui = FakeUI(clicked={"Reactivate annotation", "Reactivate note"})
    archived_service = FakeService(
        annotations=(_annotation(status="archived"),),
        notes=(_note(status="archived"),),
    )
    _render(archived_ui, archived_service)

    assert {name for name, _value in active_service.calls} >= {
        "archive_annotation",
        "archive_note",
    }
    assert {name for name, _value in archived_service.calls} >= {
        "reactivate_annotation",
        "reactivate_note",
    }


def test_link_annotation_to_concept_uses_exclusive_target() -> None:
    annotation = _annotation()
    identity = "C-1\x1fLegacy Book"
    ui = FakeUI(
        values={
            state_key("show_annotation_evidence", annotation.annotation_id): True,
            state_key("concept_choice", f"annotation_{annotation.annotation_id}"): identity,
        },
        submitted={"Link to Concept"},
    )
    service = FakeService(annotations=(annotation,))

    _render(ui, service)

    call = next(value for name, value in service.calls if name == "create_evidence")
    assert call["annotation_id"] == annotation.annotation_id
    assert call["note_id"] is None
    assert call["document_id"] is None
    assert call["page_number"] is None
    assert call["concept_legacy_id"] == "C-1"
    assert ui.session_state[SELECTED_CONCEPT_IDENTITY] == ("C-1", "Legacy Book")


def test_link_note_to_concept_never_fills_document_target() -> None:
    note = _note()
    identity = "C-1\x1fLegacy Book"
    ui = FakeUI(
        values={
            state_key("show_note_evidence", note.note_id): True,
            state_key("concept_choice", f"note_{note.note_id}"): identity,
        },
        submitted={"Link to Concept"},
    )
    service = FakeService(notes=(note,))

    _render(ui, service)

    call = next(value for name, value in service.calls if name == "create_evidence")
    assert call["note_id"] == note.note_id
    assert call["annotation_id"] is None
    assert call["document_id"] is None
    assert call["page_number"] is None


def test_evidence_list_is_metadata_only_and_archive_action_is_available() -> None:
    ui = FakeUI(clicked={"Archive evidence"})
    service = FakeService(evidence=(_evidence(),))

    _render(ui, service)

    row = evidence_rows((_evidence(),))[0]
    assert row["concept_id"] == "C-1"
    assert "pdf_bytes" not in row
    assert ("archive_evidence", "ev-1") in service.calls


def test_existing_evidence_can_be_shown_inside_annotation() -> None:
    ui = FakeUI(values={state_key("show_annotation_links", "ann-1"): True})
    service = FakeService(annotations=(_annotation(),), evidence=(_evidence(),))

    _render(ui, service)

    assert sum(row.get("evidence_link_id") == "ev-1" for table in ui.rows for row in table) >= 2


def test_source_only_note_evidence_has_archive_and_reactivate_actions() -> None:
    note = _note(document_id=None)
    active = _evidence(target="note")
    active_ui = FakeUI(
        values={state_key("show_note_links", note.note_id): True},
        clicked={state_key("archive_evidence", active.evidence_link_id)},
    )
    active_service = FakeService(
        notes=(),
        source_notes=(note,),
        evidence=(active,),
        document_evidence=(),
    )

    _render(active_ui, active_service)

    archived = _evidence(status="archived", target="note")
    archived_ui = FakeUI(
        values={state_key("show_note_links", note.note_id): True},
        clicked={state_key("reactivate_evidence", archived.evidence_link_id)},
    )
    archived_service = FakeService(
        notes=(),
        source_notes=(note,),
        evidence=(archived,),
        document_evidence=(),
    )

    _render(archived_ui, archived_service)

    assert ("archive_evidence", "ev-1") in active_service.calls
    assert ("reactivate_evidence", "ev-1") in archived_service.calls


def test_evidence_target_opens_annotation_document_and_page() -> None:
    ui = FakeUI(clicked={state_key("open_evidence_target", "ev-1")})
    service = FakeService(annotations=(_annotation(),), evidence=(_evidence(),))

    _render(ui, service)

    assert ui.session_state[SELECTED_ANNOTATION_ID] == "ann-1"
    assert ui.session_state[SELECTED_DOCUMENT_ID] == "doc-pdf"
    assert ui.session_state[PENDING_PAGE_SUGGESTION] == {
        "document_id": "doc-pdf",
        "page_number": 7,
    }
    assert apply_pending_page_suggestion(ui.session_state) == ("doc-pdf", 7)
    assert ui.session_state[reading_space_key("current_page", "doc-pdf")] == 7


def test_open_note_or_annotation_selects_document_and_suggests_page() -> None:
    ui = FakeUI(clicked={state_key("open_document", "note-1")})
    current_page_key = reading_space_key("current_page", "doc-pdf")
    ui.session_state[current_page_key] = 3

    assert render_open_document(
        ui,
        source_id="src-1",
        document_id="doc-pdf",
        page_number=11,
        subject_id="note-1",
    )

    assert ui.session_state[SELECTED_SOURCE_ID] == "src-1"
    assert ui.session_state[SELECTED_DOCUMENT_ID] == "doc-pdf"
    assert ui.session_state[current_page_key] == 3
    assert ui.session_state[PENDING_PAGE_SUGGESTION] == {
        "document_id": "doc-pdf",
        "page_number": 11,
    }
    assert ui.reruns == 1

    assert apply_pending_page_suggestion(ui.session_state) == ("doc-pdf", 11)
    assert ui.session_state[current_page_key] == 11
    assert PENDING_PAGE_SUGGESTION not in ui.session_state


def test_page_suggestion_is_applied_before_reading_space_widgets() -> None:
    source = inspect.getsource(reading_page_module._render_reader_panel)

    apply_position = source.index("apply_pending_page_suggestion(")
    page_widget_path = source.index("_render_pdf_reader(")
    assert apply_position < page_widget_path


def test_page_suggestion_is_clamped_to_reader_total_without_persisting() -> None:
    state: dict[str, Any] = {
        SELECTED_DOCUMENT_ID: "doc-pdf",
        PENDING_PAGE_SUGGESTION: {"document_id": "doc-pdf", "page_number": 99},
    }

    assert apply_pending_page_suggestion(state, total_pages=12) == ("doc-pdf", 12)
    assert state[reading_space_key("current_page", "doc-pdf")] == 12
    assert PENDING_PAGE_SUGGESTION not in state


def test_web_forms_cannot_manufacture_page_fields_from_session_values() -> None:
    ui = FakeUI(
        values={
            state_key("web_ann", "page", "doc-web"): 99,
            state_key("web_note", "page_start", "doc-web"): 99,
            state_key("web_note", "page_end", "doc-web"): 100,
        },
        submitted={"Add Annotation", "Add Reading Note"},
    )
    annotation = render_annotation_form(
        ui,
        document_id="doc-web",
        is_pdf=False,
        suggested_page=None,
        form_key="web_ann",
    )
    note = render_note_form(
        ui,
        source_id="src-1",
        document_id="doc-web",
        is_pdf=False,
        suggested_page=None,
        references=(),
        form_key="web_note",
    )

    assert annotation is not None and annotation.page_number is None
    assert note is not None and note.page_start is None and note.page_end is None


def test_metadata_filter_matches_text_tags_and_type_only() -> None:
    note = _note()
    assert local_match(note, query="INSIGHT", record_type="idea", required_type="all")
    assert local_match(note, query="note body", record_type="idea", required_type="idea")
    assert not local_match(note, query="", record_type="idea", required_type="proof")


def test_concept_search_escapes_regex_projects_metadata_and_is_bounded() -> None:
    database = FakeDatabase()

    choices = find_legacy_concepts(
        database,
        search="C.*",
        legacy_source="Legacy[",
        limit=500,
    )

    assert choices[0].concept_id == "C-1"
    query = database.concepts.queries[0]
    assert query["$and"][0]["$or"][0]["id"]["$regex"] == r"C\.\*"
    assert query["$and"][1]["source"]["$regex"] == r"Legacy\["
    assert database.concepts.projections[0]["_id"] == 0


def test_concept_picker_preserves_exact_legacy_identity_whitespace() -> None:
    database = FakeDatabase()
    database.concepts.documents = (
        {
            "id": "  C-legacy  ",
            "source": " Legacy Source ",
            "titulo": "Exact identity",
        },
    )

    choices = find_legacy_concepts(database)

    assert choices[0].concept_id == "  C-legacy  "
    assert choices[0].concept_source == " Legacy Source "
    assert choices[0].identity == "  C-legacy  \x1f Legacy Source "
    assert choices[0].label.startswith("C-legacy [Legacy Source]")


def test_context_change_clears_s4_state_for_same_database_name_different_endpoint() -> None:
    state: dict[str, Any] = {}
    first = FakeDatabase()
    second = FakeDatabase()
    sync_context(
        state,
        connection_label="one",
        database_name="shared",
        database=first,
        source_id="src-1",
        document_id="doc-1",
    )
    state[state_key("draft")] = "discard me"

    assert sync_context(
        state,
        connection_label="two",
        database_name="shared",
        database=second,
        source_id="src-1",
        document_id="doc-1",
    )
    assert state_key("draft") not in state
    assert isinstance(state[ACTIVE_CONTEXT][2], str)


def test_s4_ui_has_no_local_urls_network_pdfjs_or_executable_html() -> None:
    paths = sorted((ROOT / "editor" / "reading_annotations").glob("*.py"))
    forbidden_imports = {"aiohttp", "httpx", "requests", "urllib.request", "webbrowser"}
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_imports:
                        violations.append(f"{path.name}:{node.lineno}: {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module in forbidden_imports:
                violations.append(f"{path.name}:{node.lineno}: {node.module}")
            elif isinstance(node, ast.Attribute) and node.attr in {
                "as_uri",
                "html",
                "iframe",
                "markdown",
            }:
                violations.append(f"{path.name}:{node.lineno}: {node.attr}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value.casefold()
                if "file://" in text or "pdf.js" in text or "pdfjs" in text:
                    violations.append(f"{path.name}:{node.lineno}: forbidden content")
    assert paths
    assert violations == []


def test_all_explicit_s4_widget_keys_use_the_required_namespace() -> None:
    paths = sorted((ROOT / "editor" / "reading_annotations").glob("*.py"))
    violations: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", "")
            if name not in {
                "button",
                "checkbox",
                "form",
                "form_submit_button",
                "number_input",
                "selectbox",
                "text_area",
                "text_input",
            }:
                continue
            key = next((item.value for item in node.keywords if item.arg == "key"), None)
            if key is None:
                violations.append(f"{path.name}:{node.lineno}: missing key")
            elif not (
                (
                    isinstance(key, ast.Call)
                    and isinstance(key.func, ast.Name)
                    and key.func.id == "state_key"
                )
                or (isinstance(key, ast.Name) and key.id == "key")
            ):
                violations.append(f"{path.name}:{node.lineno}: key not namespaced")
    assert violations == []

"""Focused fake-render and static safety tests for the S3 Reading Space UI."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import ast
import hashlib
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import editor.reading_space.reader_page as reading_page_module
from editor.pdf_preview import PdfPreviewPayload
from editor.pdf_preview import get_pdf_preview
from editor.pdf_preview import store_pdf_preview
from editor.reading_space.document_picker import document_rows
from editor.reading_space.reader_page import _open_pdf
from editor.reading_space.reader_page import _render_pdf_reader
from editor.reading_space.reader_page import _render_reading_state_actions
from editor.reading_space.reader_page import _render_web_reader
from editor.reading_space.reader_page import render_reading_space_page
from editor.reading_space.source_entrypoints import render_reading_space_entrypoint
from editor.reading_space.state import ACTIVE_DATABASE_IDENTITY
from editor.reading_space.state import ACTIVE_USER_SCOPE
from editor.reading_space.state import CONFIRMED_WEB_DOCUMENT_ID
from editor.reading_space.state import PDF_PREVIEW_NAMESPACE
from editor.reading_space.state import PENDING_TARGET
from editor.reading_space.state import READER_SUBJECT
from editor.reading_space.state import READING_SPACE_NAV_LABEL
from editor.reading_space.state import SELECTED_DOCUMENT_ID
from editor.reading_space.state import SELECTED_SOURCE_ID
from editor.reading_space.state import add_reading_space_navigation
from editor.reading_space.state import apply_pending_current_page_widget_clears
from editor.reading_space.state import apply_pending_document_widget_clears
from editor.reading_space.state import apply_pending_navigation
from editor.reading_space.state import consume_pending_target
from editor.reading_space.state import request_reading_space_navigation
from editor.reading_space.state import select_document
from editor.reading_space.state import select_source
from editor.reading_space.state import state_key
from editor.reading_space.state import sync_database_state
from editor.reading_space.state import sync_user_scope
from mathmongo.reading_space.models import ReadingStatus
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.service import DocumentIntegrityInspection
from mathmongo.source_documents.service import DocumentPdfPayload
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared

ROOT = Path(__file__).resolve().parents[1]
VALID_PDF = b"%PDF-1.7\nreading space\n%%EOF\n"


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
        self.rows: list[list[dict[str, Any]]] = []
        self.pdf_calls: list[tuple[bytes, dict[str, Any]]] = []
        self.download_calls: list[dict[str, Any]] = []
        self.links: list[str] = []
        self.reruns = 0
        self.column_calls: list[tuple[Any, dict[str, Any]]] = []
        self.expanders: list[tuple[str, bool]] = []
        self.layout_events: list[tuple[str, Any]] = []

    def _message(self, level: str, value: object) -> None:
        self.messages.append((level, str(value)))

    def _value(self, key: str, default: Any) -> Any:
        value = self.values.get(key, self.session_state.get(key, default))
        self.session_state[key] = value
        return value

    def title(self, value: object) -> None:
        self._message("title", value)

    def subheader(self, value: object) -> None:
        self._message("subheader", value)

    def info(self, value: object) -> None:
        self._message("info", value)

    def success(self, value: object) -> None:
        self._message("success", value)

    def warning(self, value: object) -> None:
        self._message("warning", value)

    def error(self, value: object) -> None:
        self._message("error", value)

    def caption(self, value: object) -> None:
        self._message("caption", value)

    def write(self, value: object) -> None:
        self._message("write", value)

    def divider(self) -> None:
        return None

    def columns(self, spec: Any, **kwargs: Any):
        self.column_calls.append((spec, dict(kwargs)))
        count = spec if isinstance(spec, int) else len(spec)
        return [nullcontext(self) for _index in range(count)]

    def container(self, *, key: str | None = None, **_kwargs: Any):
        self.layout_events.append(("container", key))
        return nullcontext(self)

    def expander(self, label: str, *, expanded: bool = False, **_kwargs: Any):
        self.expanders.append((label, expanded))
        self.layout_events.append(("expander", label))
        return nullcontext(self)

    def form(self, *_args, **_kwargs):
        return nullcontext(self)

    def selectbox(self, _label, options, *, key, index=0, **_kwargs):
        return self._value(key, list(options)[index])

    def text_input(self, _label, *, key, value="", **_kwargs):
        return self._value(key, value)

    def checkbox(self, _label, *, key, value=False, **_kwargs):
        return bool(self._value(key, value))

    def number_input(self, _label, *, key, value=1, **_kwargs):
        return self._value(key, value)

    def form_submit_button(self, label, **_kwargs):
        return label in self.submitted

    def button(self, label, *, key, disabled=False, **_kwargs):
        return not disabled and (label in self.clicked or key in self.clicked)

    def dataframe(self, rows, **_kwargs) -> None:
        self.rows.append(list(rows))

    def link_button(self, _label, url, **_kwargs) -> None:
        self.links.append(str(url))

    def pdf(self, data: bytes, **kwargs) -> None:
        self.pdf_calls.append((data, kwargs))

    def download_button(self, _label, **kwargs) -> None:
        self.download_calls.append(kwargs)

    def rerun(self) -> None:
        self.reruns += 1


class FakeResult:
    def __init__(self, value: Any = None, *, status: str = "success", message: str = "") -> None:
        self.value = value
        self.status = SimpleNamespace(value=status)
        self.message = message

    @property
    def completed(self) -> bool:
        return self.status.value == "success"


class FakePage:
    def __init__(self, items: tuple[Any, ...]) -> None:
        self.items = items
        self.page = 1
        self.page_size = 20
        self.total = len(items)
        self.pages = 1 if items else 0


class FakeIndexManager:
    def status(self):
        return ()

    def plan(self):
        return SimpleNamespace(initialized=True, conflicts=(), missing=())

    def apply(self):
        raise AssertionError("initialized Reading Space must not apply indexes")


class FakeRepository:
    def __init__(self, items: tuple[Any, ...]) -> None:
        self.items = items

    def list(self, **_kwargs):
        return SimpleNamespace(items=self.items, total=len(self.items))

    def get_by_id(self, item_id: str):
        for item in self.items:
            if item_id in {getattr(item, "source_id", None), getattr(item, "reference_id", None)}:
                return item
        return None


def _pdf_document(source: Source) -> SourceDocument:
    prepared = SourceDocumentBlobStore.prepare_pdf(VALID_PDF)
    version = pdf_version_from_prepared(prepared, original_filename="reading.pdf")
    return SourceDocument(
        source_id=source.source_id,
        kind="pdf",
        title="PDF reading",
        tags=["analysis"],
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def _web_document(source: Source) -> SourceDocument:
    return SourceDocument(
        source_id=source.source_id,
        kind="web",
        title="Web reading",
        web={"url_raw": "https://example.test/reading"},
    )


def _reading(document: SourceDocument, *, status: str = "in_progress") -> SimpleNamespace:
    return SimpleNamespace(
        document_id=document.document_id,
        status=SimpleNamespace(value=status),
        current_page=3,
        total_pages=None,
        last_opened_at=None,
        open_count=1,
        tags=("priority", "review"),
    )


def _reader(document: SourceDocument, source: Source, *, opened: bool) -> SimpleNamespace:
    reading = _reading(document)
    pdf_payload = None
    if opened and document.pdf is not None:
        pdf_payload = DocumentPdfPayload(
            document,
            VALID_PDF,
            document.pdf.current_version.original_filename,
            document.pdf.current_version.sha256,
        )
    return SimpleNamespace(
        document=document,
        source=source,
        reference=None,
        reading_state=reading,
        effective_status=ReadingStatus.IN_PROGRESS,
        pdf_payload=pdf_payload,
        integrity=DocumentIntegrityInspection(document.document_id, True, ()),
        openable=True,
    )


class FakeService:
    def __init__(self, source: Source, documents: tuple[SourceDocument, ...]) -> None:
        self.source = source
        self.documents = documents
        self.index_manager = FakeIndexManager()
        self.open_calls: list[str] = []
        self.context_calls: list[str] = []
        self.page_updates: list[tuple[str, int]] = []
        self.completed: list[str] = []
        self.deferred: list[str] = []
        self.reset: list[str] = []
        self.list_calls: list[dict[str, Any]] = []

    def _document(self, document_id: str) -> SourceDocument:
        return next(item for item in self.documents if item.document_id == document_id)

    def _item(self, document: SourceDocument) -> SimpleNamespace:
        return SimpleNamespace(
            document=document,
            state=None,
            source=self.source,
            reference=None,
        )

    def open_document(self, document_id: str, *, user_scope: str):
        assert user_scope == "local"
        self.open_calls.append(document_id)
        return FakeResult(_reader(self._document(document_id), self.source, opened=True))

    def get_reader_context(self, document_id: str, *, user_scope: str):
        assert user_scope == "local"
        self.context_calls.append(document_id)
        return FakeResult(_reader(self._document(document_id), self.source, opened=False))

    def list_readable_documents(self, **kwargs):
        self.list_calls.append(kwargs)
        return FakeResult(FakePage(tuple(self._item(document) for document in self.documents)))

    def list_recent_documents(self, **_kwargs):
        return FakeResult(())

    def update_current_page(
        self,
        document_id: str,
        current_page: int,
        **_kwargs,
    ):
        self.page_updates.append((document_id, current_page))
        return FakeResult(_reading(self._document(document_id)))

    def mark_completed(self, document_id: str, **_kwargs):
        self.completed.append(document_id)
        return FakeResult(_reading(self._document(document_id), status="completed"))

    def mark_deferred(self, document_id: str, **_kwargs):
        self.deferred.append(document_id)
        return FakeResult(_reading(self._document(document_id), status="deferred"))

    def reset_reading_state(self, document_id: str, **_kwargs):
        self.reset.append(document_id)
        return FakeResult()

    def get_source_reading_summary(self, _source_id: str, **_kwargs):
        return FakeResult(
            SimpleNamespace(
                total_documents=len(self.documents),
                pdf_documents=sum(item.pdf is not None for item in self.documents),
                web_documents=sum(item.web is not None for item in self.documents),
                unread=len(self.documents),
                in_progress=0,
                completed=0,
                deferred=0,
                last_opened_at=None,
            )
        )


def _context(source: Source) -> SimpleNamespace:
    return SimpleNamespace(
        connection_label="isolated",
        database_name="isolated_s3_ui",
        database=object(),
        source_repository=FakeRepository((source,)),
        reference_repository=FakeRepository(()),
    )


def test_navigation_handoff_keeps_only_logical_target() -> None:
    existing = ["🏠 Dashboard", "➕ Add Source", "✏️ Edit / Analyze Source", "Settings"]
    options = add_reading_space_navigation(existing)
    state: dict[str, Any] = {}

    request_reading_space_navigation(
        state,
        source_id="src-logical",
        document_id="doc-logical",
        kind="pdf",
    )
    assert apply_pending_navigation(state, options, navigation_key="navigation") == (
        READING_SPACE_NAV_LABEL
    )
    assert state["navigation"] == READING_SPACE_NAV_LABEL
    assert consume_pending_target(state) == {
        "source_id": "src-logical",
        "document_id": "doc-logical",
        "kind": "pdf",
        "user_scope": "local",
    }
    assert options.index(READING_SPACE_NAV_LABEL) == options.index("✏️ Edit / Analyze Source") + 1


def test_database_and_document_changes_invalidate_only_reading_preview() -> None:
    filter_key = state_key("filter_title")
    state: dict[str, Any] = {ACTIVE_DATABASE_IDENTITY: "old", filter_key: "old database"}
    payload = PdfPreviewPayload(VALID_PDF, "sha", "reading.pdf", "context")
    store_pdf_preview(state, PDF_PREVIEW_NAMESPACE, payload)
    store_pdf_preview(state, "source_document", payload)
    state[READER_SUBJECT] = {"document_id": "old"}

    assert sync_database_state(state, connection_label="label", database_name="new")
    assert get_pdf_preview(state, PDF_PREVIEW_NAMESPACE, context_identity="context") is None
    assert get_pdf_preview(state, "source_document", context_identity="context") is payload
    assert filter_key not in state

    store_pdf_preview(state, PDF_PREVIEW_NAMESPACE, payload)
    state[SELECTED_DOCUMENT_ID] = "old"
    stale_page = state_key("current_page", "old")
    state[stale_page] = 19
    assert select_document(state, "new")
    assert get_pdf_preview(state, PDF_PREVIEW_NAMESPACE, context_identity="context") is None
    assert state[stale_page] == 19
    assert apply_pending_document_widget_clears(state) == ("old",)
    assert stale_page not in state


def test_document_bound_widgets_are_fresh_when_returning_to_a_document() -> None:
    source = Source(name="Widget lifecycle")
    first = _pdf_document(source)
    second = _web_document(source)
    state: dict[str, Any] = {
        SELECTED_SOURCE_ID: source.source_id,
        SELECTED_DOCUMENT_ID: first.document_id,
        state_key("current_page", first.document_id): 17,
        state_key("reader_completed", first.document_id): True,
    }

    assert select_document(state, second.document_id)
    assert apply_pending_document_widget_clears(state) == (first.document_id,)
    assert state_key("current_page", first.document_id) not in state
    assert state_key("reader_completed", first.document_id) not in state

    assert select_document(state, first.document_id)
    apply_pending_document_widget_clears(state)
    ui = FakeUI()
    ui.session_state = state
    service = FakeService(source, (first, second))
    _render_reading_state_actions(
        ui,
        service,
        _reader(first, source, opened=False),
        actions_enabled=True,
    )

    assert ui.session_state[state_key("current_page", first.document_id)] == 3


def test_source_change_queues_cleanup_for_the_selected_document() -> None:
    first_source = Source(name="First")
    second_source = Source(name="Second")
    document = _pdf_document(first_source)
    widget = state_key("current_page", document.document_id)
    state: dict[str, Any] = {
        SELECTED_SOURCE_ID: first_source.source_id,
        SELECTED_DOCUMENT_ID: document.document_id,
        widget: 11,
    }

    assert select_source(state, second_source.source_id)
    apply_pending_document_widget_clears(state)

    assert widget not in state
    assert SELECTED_DOCUMENT_ID not in state


def test_user_scope_change_clears_document_widgets_but_preserves_filters() -> None:
    source = Source(name="Scoped")
    document = _pdf_document(source)
    widget = state_key("current_page", document.document_id)
    filter_key = state_key("filter_title")
    state: dict[str, Any] = {
        ACTIVE_USER_SCOPE: "local",
        SELECTED_SOURCE_ID: source.source_id,
        SELECTED_DOCUMENT_ID: document.document_id,
        widget: 13,
        filter_key: "topology",
    }

    assert sync_user_scope(state, "another-local-scope")
    apply_pending_document_widget_clears(state)

    assert widget not in state
    assert SELECTED_SOURCE_ID not in state
    assert SELECTED_DOCUMENT_ID not in state
    assert state[filter_key] == "topology"


def test_source_documents_entrypoint_does_not_read_pdf_or_open_web() -> None:
    source = Source(name="Entrypoint")
    document = _web_document(source)
    ui = FakeUI(clicked={"Open in Reading Space"})

    assert render_reading_space_entrypoint(ui, document)
    assert ui.session_state[PENDING_TARGET]["document_id"] == document.document_id
    assert ui.pdf_calls == []
    assert ui.links == []


def test_metadata_rows_never_materialize_pdf_bytes() -> None:
    source = Source(name="Rows")
    document = _pdf_document(source)
    item = SimpleNamespace(
        document=document, state=_reading(document), source=source, reference=None
    )

    rows = document_rows((item,))

    assert rows[0]["title"] == "PDF reading"
    assert rows[0]["current_page"] == 3
    assert rows[0]["document_tags"] == "analysis"
    assert rows[0]["reading_tags"] == "priority, review"
    assert "pdf_bytes" not in rows[0]


def test_pdf_open_uses_exact_bytes_and_invalidates_by_full_identity() -> None:
    source = Source(name="PDF")
    document = _pdf_document(source)
    context = _context(source)
    service = FakeService(source, (document,))
    ui = FakeUI()

    reader = _open_pdf(ui, context, service, document.document_id)
    assert reader is not None
    _render_pdf_reader(ui, context, service, reader, actions_enabled=True)

    assert service.open_calls == [document.document_id]
    assert ui.pdf_calls[0][0] is reader.pdf_payload.pdf_bytes
    assert ui.pdf_calls[0][1]["height"] == 800
    assert ui.pdf_calls[0][1]["key"].startswith("reading_space_")
    assert ui.download_calls[0]["data"] is ui.pdf_calls[0][0]
    assert ui.download_calls[0]["key"].startswith("reading_space_")
    subject = ui.session_state[READER_SUBJECT]
    assert subject["document_id"] == document.document_id
    assert subject["version_id"] == document.pdf.current_version.version_id
    assert subject["sha256"] == hashlib.sha256(VALID_PDF).hexdigest()
    assert all(str(key).startswith("reading_space_") for key in ui.session_state)


def test_current_page_and_reading_status_actions_call_typed_service() -> None:
    source = Source(name="Actions")
    document = _pdf_document(source)
    service = FakeService(source, (document,))
    reader = _reader(document, source, opened=False)
    ui = FakeUI(
        values={state_key("current_page", document.document_id): 7},
        clicked={"Save current page", "Completed", "Deferred", "Reset"},
    )

    _render_reading_state_actions(ui, service, reader, actions_enabled=True)

    assert service.page_updates == [(document.document_id, 7)]
    assert service.completed == [document.document_id]
    assert service.deferred == [document.document_id]
    assert service.reset == [document.document_id]
    assert apply_pending_current_page_widget_clears(ui.session_state) == (document.document_id,)
    assert state_key("current_page", document.document_id) not in ui.session_state


def test_web_reader_requires_registration_before_external_link() -> None:
    source = Source(name="Web")
    document = _web_document(source)
    reader = _reader(document, source, opened=False)
    service = FakeService(source, (document,))
    initial = FakeUI(
        values={state_key("current_page", document.document_id): 9},
        clicked={"Save current page"},
    )

    _render_web_reader(initial, service, reader, actions_enabled=True)

    assert service.open_calls == []
    assert service.page_updates == []
    assert state_key("current_page", document.document_id) not in initial.session_state
    assert initial.links == []

    confirmed = FakeUI(clicked={"Register opening"})
    _render_web_reader(confirmed, service, reader, actions_enabled=True)

    assert service.open_calls == [document.document_id]
    assert confirmed.session_state[CONFIRMED_WEB_DOCUMENT_ID] == document.document_id
    assert confirmed.links == ["https://example.test/reading"]


def test_full_page_filters_and_lists_without_loading_pdf() -> None:
    source = Source(name="List only")
    document = _pdf_document(source)
    service = FakeService(source, (document,))
    ui = FakeUI()

    render_reading_space_page(
        _context(source),
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )

    assert service.open_calls == []
    assert service.context_calls == []
    assert ui.pdf_calls == []
    rendered = " ".join(message for _level, message in ui.messages)
    assert "Reading Space" in rendered
    assert "Recent Documents" in rendered
    assert any(row["document_id"] == document.document_id for table in ui.rows for row in table)
    assert not any(label in {"Change Document", "Recent Documents"} for label, _ in ui.expanders)
    assert ("container", state_key("workspace")) not in ui.layout_events


def test_selected_document_uses_split_workspace_and_compact_top_bar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Source(name="Workspace Source")
    document = _pdf_document(source)
    service = FakeService(source, (document,))
    ui = FakeUI()
    ui.session_state.update(
        {
            ACTIVE_USER_SCOPE: "local",
            SELECTED_DOCUMENT_ID: document.document_id,
        }
    )
    context = _context(source)
    context.database = {}
    s4_calls: list[str] = []
    monkeypatch.setattr(
        reading_page_module,
        "_render_s4_panel",
        lambda _context, reader, **_kwargs: s4_calls.append(reader.document.document_id),
    )

    render_reading_space_page(
        context,
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )

    assert service.context_calls == [document.document_id]
    assert ui.session_state[state_key("workspace_layout")] == "Split workspace"
    assert ([0.58, 0.42], {"gap": "large"}) in ui.column_calls
    workspace_expanders = [
        item for item in ui.expanders if item[0] in {"Change Document", "Recent Documents"}
    ]
    assert workspace_expanders == [("Change Document", False), ("Recent Documents", False)]
    assert ui.layout_events[0] == ("container", state_key("workspace"))
    assert s4_calls == [document.document_id]
    rendered = " ".join(message for _level, message in ui.messages)
    assert "Reading Workspace" in rendered
    assert "PDF reading" in rendered
    assert "Workspace Source" in rendered
    assert "Current page" in rendered
    assert "in_progress" in rendered


def test_selected_document_can_use_stacked_layout_without_split_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Source(name="Stacked Source")
    document = _web_document(source)
    service = FakeService(source, (document,))
    ui = FakeUI(values={state_key("workspace_layout"): "Stacked layout"})
    ui.session_state.update(
        {
            ACTIVE_USER_SCOPE: "local",
            SELECTED_DOCUMENT_ID: document.document_id,
        }
    )
    context = _context(source)
    context.database = {}
    s4_calls: list[str] = []
    monkeypatch.setattr(
        reading_page_module,
        "_render_s4_panel",
        lambda _context, reader, **_kwargs: s4_calls.append(reader.document.document_id),
    )

    render_reading_space_page(
        context,
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )

    assert service.context_calls == [document.document_id]
    assert ([0.58, 0.42], {"gap": "large"}) not in ui.column_calls
    assert ui.session_state[state_key("workspace_layout")] == "Stacked layout"
    assert s4_calls == [document.document_id]


def test_all_required_filters_are_typed_and_passed_to_the_service() -> None:
    source = Source(name="Filtered")
    document = _pdf_document(source)
    service = FakeService(source, (document,))
    ui = FakeUI(
        values={
            state_key("filter_source"): source.source_id,
            state_key("filter_kind"): "pdf",
            state_key("filter_document_status"): "active",
            state_key("filter_reading_status"): "in_progress",
            state_key("filter_order"): "title",
            state_key("filter_title"): "reading",
            state_key("filter_tags"): "analysis, topology",
        }
    )

    render_reading_space_page(
        _context(source),
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )

    filters = service.list_calls[0]["filters"]
    assert filters.source_id == source.source_id
    assert filters.kind.value == "pdf"
    assert filters.document_status.value == "active"
    assert filters.reading_status.value == "in_progress"
    assert filters.order.value == "title"
    assert filters.title_query == "reading"
    assert filters.tags == ["analysis", "topology"]


def test_incompatible_reference_filter_is_sanitized_before_widget_render() -> None:
    source = Source(name="Reference sanitizer")
    document = _web_document(source)
    service = FakeService(source, (document,))
    ui = FakeUI()
    ui.session_state[state_key("filter_source")] = source.source_id
    ui.session_state[state_key("filter_reference")] = "ref_not_available"

    render_reading_space_page(
        _context(source),
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )

    assert service.list_calls[0]["filters"].reference_id is None
    assert ui.session_state[state_key("filter_reference")] is None


def test_open_document_persists_when_all_source_filter_is_unchanged() -> None:
    source = Source(name="Persistent reader")
    document = _pdf_document(source)
    service = FakeService(source, (document,))
    ui = FakeUI(clicked={state_key("open", document.document_id)})
    context = _context(source)

    render_reading_space_page(
        context,
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )
    assert ui.session_state[SELECTED_DOCUMENT_ID] == document.document_id
    assert ui.pdf_calls == []
    assert ui.reruns == 1

    ui.clicked.clear()
    render_reading_space_page(
        context,
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )

    assert ui.session_state[SELECTED_DOCUMENT_ID] == document.document_id
    assert service.open_calls == [document.document_id]
    assert len(ui.pdf_calls) == 1

    render_reading_space_page(
        context,
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )
    assert len(ui.pdf_calls) == 2


def test_pending_pdf_target_opens_once_but_pending_web_only_selects() -> None:
    source = Source(name="Direct targets")
    pdf = _pdf_document(source)
    web = _web_document(source)
    context = _context(source)

    pdf_service = FakeService(source, (pdf, web))
    pdf_ui = FakeUI()
    request_reading_space_navigation(
        pdf_ui.session_state,
        source_id=source.source_id,
        document_id=pdf.document_id,
        kind="pdf",
    )
    render_reading_space_page(
        context,
        ui=pdf_ui,
        service=pdf_service,  # type: ignore[arg-type]
    )
    assert pdf_service.open_calls == [pdf.document_id]
    assert pdf_ui.pdf_calls

    web_service = FakeService(source, (pdf, web))
    web_ui = FakeUI()
    request_reading_space_navigation(
        web_ui.session_state,
        source_id=source.source_id,
        document_id=web.document_id,
        kind="web",
    )
    render_reading_space_page(
        context,
        ui=web_ui,
        service=web_service,  # type: ignore[arg-type]
    )
    assert web_service.open_calls == []
    assert web_ui.links == []
    assert web_ui.session_state[SELECTED_DOCUMENT_ID] == web.document_id


def test_recent_document_action_reopens_pdf() -> None:
    source = Source(name="Recent")
    document = _pdf_document(source)
    service = FakeService(source, (document,))
    recent = service._item(document)
    recent.state = _reading(document)
    service.list_recent_documents = lambda **_kwargs: FakeResult(FakePage((recent,)))
    ui = FakeUI(clicked={state_key("open_recent", document.document_id)})
    context = _context(source)

    render_reading_space_page(
        context,
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )

    assert service.open_calls == [document.document_id]
    assert ui.session_state[SELECTED_DOCUMENT_ID] == document.document_id
    assert ui.pdf_calls == []
    assert ui.reruns == 1

    ui.clicked.clear()
    render_reading_space_page(
        context,
        ui=ui,
        service=service,  # type: ignore[arg-type]
    )
    assert ui.pdf_calls


def test_reading_space_ui_has_no_local_url_network_or_s4_escape_hatch() -> None:
    paths = sorted((ROOT / "editor" / "reading_space").glob("*.py"))
    forbidden_imports = {
        "aiohttp",
        "httpx",
        "requests",
        "urllib.request",
        "webbrowser",
    }
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
            elif isinstance(node, ast.Attribute) and node.attr == "as_uri":
                violations.append(f"{path.name}:{node.lineno}: Path.as_uri")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"html", "iframe"}:
                    violations.append(f"{path.name}:{node.lineno}: {node.func.attr}")
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                compact = node.name.replace("_", "").casefold()
                if any(term in compact for term in ("annotation", "readingnote", "evidence")):
                    violations.append(f"{path.name}:{node.lineno}: {node.name}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "file://" in node.value.casefold():
                    violations.append(f"{path.name}:{node.lineno}: local URL")

    assert paths
    assert violations == []


def test_router_declares_reading_space_navigation_and_page() -> None:
    path = ROOT / "editor" / "editor_streamlit.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "add_reading_space_navigation" in calls
    assert "apply_pending_reading_navigation" in calls
    assert "render_reading_space_page" in calls

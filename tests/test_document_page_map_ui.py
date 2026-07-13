"""Focused fake-render regressions for the S4.2 Page Map UI."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

from editor.reading_space.page_map_panel import page_labeler
from editor.reading_space.page_map_panel import render_page_map_panel
from mathmongo.document_page_maps.models import DocumentPageMap
from mathmongo.document_page_maps.models import PageLabelRule
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import PdfVersion
from mathmongo.source_documents.models import SourceDocument


class Result:
    def __init__(self, value: Any = None, *, status: str = "success", message: str = ""):
        self.value = value
        self.status = SimpleNamespace(value=status)
        self.message = message

    @property
    def completed(self) -> bool:
        return self.status.value == "success"


class UI:
    def __init__(
        self,
        *,
        clicked: set[str] | None = None,
        submitted: set[str] | None = None,
        values: dict[str, Any] | None = None,
    ) -> None:
        self.clicked = set(clicked or ())
        self.submitted = set(submitted or ())
        self.values = dict(values or {})
        self.session_state: dict[str, Any] = {}
        self.messages: list[tuple[str, str]] = []
        self.expanders: list[tuple[str, bool]] = []
        self.rows: list[list[dict[str, Any]]] = []
        self.reruns = 0

    def _message(self, kind: str, value: object) -> None:
        self.messages.append((kind, str(value)))

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

    def expander(self, label: str, *, expanded: bool = False):
        self.expanders.append((label, expanded))
        return nullcontext(self)

    def form(self, *_args: Any, **_kwargs: Any):
        return nullcontext(self)

    def popover(self, *_args: Any, **_kwargs: Any):
        return nullcontext(self)

    def columns(self, spec: Any, **_kwargs: Any):
        count = spec if isinstance(spec, int) else len(spec)
        return [nullcontext(self) for _index in range(count)]

    def button(self, label: str, **kwargs: Any) -> bool:
        return not kwargs.get("disabled", False) and label in self.clicked

    def number_input(self, label: str, *, value: int, **_kwargs: Any) -> int:
        return int(self.values.get(label, value))

    def text_input(self, label: str, *, value: str = "", **_kwargs: Any) -> str:
        return str(self.values.get(label, value))

    def selectbox(self, label: str, *, options: Any, **_kwargs: Any) -> Any:
        return self.values.get(label, tuple(options)[0])

    def form_submit_button(self, label: str, **kwargs: Any) -> bool:
        return not kwargs.get("disabled", False) and label in self.submitted

    def dataframe(self, rows: Any, **_kwargs: Any) -> None:
        self.rows.append(list(rows))

    def rerun(self) -> None:
        self.reruns += 1


class Service:
    def __init__(self, current: Result, archived: tuple[Any, ...] = ()) -> None:
        self.current = current
        self.archived = archived
        self.calls: list[tuple[Any, ...]] = []

    def get_page_map(self, document_id: str, *, user_scope: str):
        self.calls.append(("get", document_id, user_scope))
        return self.current

    def list_page_maps(self, document_id: str, **kwargs: Any):
        self.calls.append(("list", document_id, kwargs))
        return Result(SimpleNamespace(items=self.archived))

    def set_quick_rule(self, document_id: str, **kwargs: Any):
        self.calls.append(("quick", document_id, kwargs))
        return Result(SimpleNamespace())

    def add_rule(self, document_id: str, **kwargs: Any):
        self.calls.append(("add", document_id, kwargs))
        return Result(SimpleNamespace())

    def upsert_override(self, document_id: str, **kwargs: Any):
        self.calls.append(("override", document_id, kwargs))
        return Result(SimpleNamespace())

    def archive_page_map(self, page_map_id: str):
        self.calls.append(("archive", page_map_id))
        return Result(SimpleNamespace())

    def reactivate_page_map(self, page_map_id: str):
        self.calls.append(("reactivate", page_map_id))
        return Result(SimpleNamespace())

    def reset_page_map(self, document_id: str, **kwargs: Any):
        self.calls.append(("reset", document_id, kwargs))
        return Result(SimpleNamespace())


def _document() -> SourceDocument:
    source = Source(name="Page Map UI")
    version = PdfVersion(
        sha256="a" * 64,
        size_bytes=42,
        logical_path=f"source_documents/blobs/sha256/aa/{'a' * 64}.pdf",
        original_filename="map.pdf",
    )
    return SourceDocument(
        source_id=source.source_id,
        kind="pdf",
        title="Mapped Reader",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def test_page_map_ui_surfaces_typed_load_errors_and_stops_forms() -> None:
    document = _document()
    service = Service(Result(status="conflict", message="Multiple active maps"))
    ui = UI()

    render_page_map_panel(
        ui,
        service,  # type: ignore[arg-type]
        document=document,
        current_pdf_page=9,
        book_page_label=None,
        actions_enabled=True,
    )

    assert ("error", "Multiple active maps") in ui.messages
    assert ui.expanders == []


def test_archived_maps_are_discoverable_after_session_restart() -> None:
    document = _document()
    archived = SimpleNamespace(page_map_id="pmap_archived")
    service = Service(Result(status="not_found"), archived=(archived,))
    ui = UI(clicked={"Reactivate Page Map pmap_archived"})

    render_page_map_panel(
        ui,
        service,  # type: ignore[arg-type]
        document=document,
        current_pdf_page=9,
        book_page_label=None,
        actions_enabled=True,
    )

    assert ("reactivate", "pmap_archived") in service.calls
    assert not ui.session_state


def test_page_map_forms_call_typed_rule_and_override_operations() -> None:
    document = _document()
    service = Service(Result(status="not_found"))
    ui = UI(
        clicked={"Set current PDF page as Book page 1"},
        submitted={"Add rule", "Save override"},
        values={
            "PDF start page": 9,
            "Book label style": "roman_lower",
            "Book label start": "1",
            "Book page label": "plate A",
        },
    )

    render_page_map_panel(
        ui,
        service,  # type: ignore[arg-type]
        document=document,
        current_pdf_page=9,
        book_page_label="i",
        actions_enabled=True,
    )

    names = [call[0] for call in service.calls]
    assert {"quick", "add", "override", "list"}.issubset(names)
    add = next(call for call in service.calls if call[0] == "add")
    assert add[2]["pdf_start_page"] == 9
    assert add[2]["label_style"] == "roman_lower"
    override = next(call for call in service.calls if call[0] == "override")
    assert override[2]["book_page_label"] == "plate A"


def test_active_page_map_archive_and_confirmed_reset_are_explicit() -> None:
    document = _document()
    page_map = SimpleNamespace(
        page_map_id="pmap_active",
        rules=(
            SimpleNamespace(
                pdf_start_page=9,
                pdf_end_page=None,
                label_start=1,
                label_style="arabic",
                label_prefix=None,
                rule_id="prule_active",
            ),
        ),
        manual_overrides=(),
    )
    service = Service(Result(page_map))
    ui = UI(
        clicked={"Archive Page Map", "Confirm reset"},
        values={"Type the Document ID to clear all rules and overrides": document.document_id},
    )

    render_page_map_panel(
        ui,
        service,  # type: ignore[arg-type]
        document=document,
        current_pdf_page=9,
        book_page_label="1",
        actions_enabled=True,
    )

    assert ("archive", "pmap_active") in service.calls
    assert (
        "reset",
        document.document_id,
        {"user_scope": "local"},
    ) in service.calls


def test_page_labeler_loads_one_map_and_caches_computation() -> None:
    document = _document()
    page_map = DocumentPageMap(
        document_id=document.document_id,
        source_id=document.source_id,
        rules=[PageLabelRule(pdf_start_page=9, label_start=1)],
    )
    service = Service(Result(page_map))
    resolve = page_labeler(service, document.document_id)  # type: ignore[arg-type]

    assert resolve(9) == "1"
    assert resolve(9) == "1"
    assert resolve(10) == "2"
    assert [call[0] for call in service.calls] == ["get"]

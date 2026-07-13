"""Focused UI/static regressions for the S4.2 transversal polish."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import render_catalog_status
from mathmongo.source_catalog.indexes import IndexPlan
from mathmongo.source_catalog.indexes import IndexSpec
from mathmongo.source_catalog.indexes import IndexState
from mathmongo.source_catalog.indexes import IndexStatus

ROOT = Path(__file__).resolve().parents[1]


class _Database:
    name = "isolated_polish"

    def __init__(self, *, collections_ready: bool) -> None:
        self.collections_ready = collections_ready

    def list_collection_names(self) -> list[str]:
        return ["sources", "references"] if self.collections_ready else []


class _IndexManager:
    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.apply_count = 0
        self.spec = IndexSpec(
            "sources",
            "sources_polish_test",
            (("source_id", 1),),
            True,
        )

    def status(self) -> tuple[IndexStatus, ...]:
        state = IndexState.PRESENT if self.ready else IndexState.MISSING
        return (IndexStatus(self.spec, state),)

    def plan(self) -> IndexPlan:
        return IndexPlan(self.status())

    def apply(self) -> IndexPlan:
        self.apply_count += 1
        self.ready = True
        return self.plan()


class _Scope(AbstractContextManager[None]):
    def __init__(self, ui: _UI, label: str) -> None:
        self.ui = ui
        self.label = label

    def __enter__(self) -> None:
        self.ui.scopes.append(self.label)

    def __exit__(self, *_args: object) -> None:
        self.ui.scopes.pop()


class _UI:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.scopes: list[str] = []
        self.messages: list[tuple[str | None, str, str]] = []
        self.dataframes: list[tuple[str | None, list[dict[str, Any]]]] = []
        self.expanders: list[tuple[str, bool]] = []
        self.form_submit_count = 0

    @property
    def scope(self) -> str | None:
        return self.scopes[-1] if self.scopes else None

    def _message(self, level: str, value: object) -> None:
        self.messages.append((self.scope, level, str(value)))

    def subheader(self, value: object) -> None:
        self._message("subheader", value)

    def success(self, value: object) -> None:
        self._message("success", value)

    def warning(self, value: object) -> None:
        self._message("warning", value)

    def error(self, value: object) -> None:
        self._message("error", value)

    def info(self, value: object) -> None:
        self._message("info", value)

    def caption(self, value: object) -> None:
        self._message("caption", value)

    def write(self, value: object) -> None:
        self._message("write", value)

    def dataframe(self, rows: list[dict[str, Any]], **_kwargs: Any) -> None:
        self.dataframes.append((self.scope, list(rows)))

    def expander(self, label: str, *, expanded: bool = False) -> _Scope:
        self.expanders.append((label, expanded))
        return _Scope(self, label)

    def form(self, *_args: Any, **_kwargs: Any) -> _Scope:
        return _Scope(self, "catalog initialization form")

    def text_input(self, _label: str, *, key: str) -> str:
        del key
        return ""

    def checkbox(self, _label: str, *, key: str) -> bool:
        del key
        return False

    def form_submit_button(self, _label: str, *, disabled: bool) -> bool:
        del disabled
        self.form_submit_count += 1
        return False


def _context(*, ready: bool) -> tuple[CatalogUIContext, _IndexManager]:
    database = _Database(collections_ready=ready)
    manager = _IndexManager(ready=ready)
    return (
        CatalogUIContext(
            connection_label="isolated",
            database_name=database.name,
            database=database,
            source_repository=None,  # type: ignore[arg-type]
            reference_repository=None,  # type: ignore[arg-type]
            service=None,  # type: ignore[arg-type]
            index_manager=manager,  # type: ignore[arg-type]
        ),
        manager,
    )


def test_catalog_normal_flow_is_compact_and_diagnostics_are_collapsed() -> None:
    context, manager = _context(ready=False)
    ui = _UI()

    snapshot = render_catalog_status(ui, context)

    assert snapshot is not None and not snapshot.initialized
    normal_messages = [text for scope, _level, text in ui.messages if scope is None]
    assert any(text.startswith("Catalog missing") for text in normal_messages)
    assert not any("Colecciones:" in text or text.startswith("Plan:") for text in normal_messages)
    assert ("Advanced catalog diagnostics", False) in ui.expanders
    assert ("Initialize catalog indexes", False) in ui.expanders
    assert ui.dataframes
    assert all(scope == "Advanced catalog diagnostics" for scope, _rows in ui.dataframes)
    assert ui.form_submit_count == 1
    assert manager.apply_count == 0


def test_catalog_ready_uses_one_normal_summary_and_keeps_index_rows_advanced() -> None:
    context, _manager = _context(ready=True)
    ui = _UI()

    snapshot = render_catalog_status(ui, context)

    assert snapshot is not None and snapshot.initialized
    normal_messages = [text for scope, _level, text in ui.messages if scope is None]
    assert any(text.startswith("Catalog ready") for text in normal_messages)
    assert all(scope == "Advanced catalog diagnostics" for scope, _rows in ui.dataframes)


def test_cuaderno_removes_only_the_exact_experimental_banner() -> None:
    source = (ROOT / "editor" / "cuaderno_page.py").read_text(encoding="utf-8")

    assert "Este módulo es experimental. En los siguientes MVP" not in source
    assert 'st.title("🧪 Cuaderno (Experimental)")' in source
    assert 'with st.expander("Instalación / Estado", expanded=False):' in source
    for collection in (
        "worklog_entries",
        "backlog_items",
        "weekly_reviews",
        "deliverables",
        "latex_notes",
    ):
        assert f'mongo_db["{collection}"]' in source

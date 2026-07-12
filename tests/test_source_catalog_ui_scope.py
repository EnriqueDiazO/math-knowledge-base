"""Static scope and read-only rendering checks for the S1B Source Catalog UI."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import ast
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any

from editor.source_catalog.shared import build_catalog_context
from editor.source_catalog.shared import inspect_catalog_status
from editor.source_catalog.shared import render_catalog_status
from editor.source_catalog.state import ADD_SOURCE_NAV_LABEL
from editor.source_catalog.state import EDIT_SOURCE_NAV_LABEL
from editor.source_catalog.state import NAVIGATION_WIDGET
from editor.source_catalog.state import add_source_catalog_navigation
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "editor" / "editor_streamlit.py"
S1B_MODULE_DIRS = (
    ROOT / "editor" / "source_catalog",
    ROOT / "mathmongo" / "source_catalog",
)

EXISTING_NAVIGATION = (
    "\U0001f3e0 Dashboard",
    "\u2795 Add Concept",
    "\u270f\ufe0f Edit Concept",
    "\U0001f4da Browse Concepts",
    "\U0001f517 Manage Relations",
    "\U0001f4ca Knowledge Graph",
    "\U0001f4c4 Document Builder",
    "\U0001f4e4 Export",
    "\U0001f4e6 Database Export",
    "\U0001f4e5 Database Import",
    "\U0001f9f9 Maintenance",
    "\u2699\ufe0f Settings",
)
OPTIONAL_EXISTING_NAVIGATION = (
    "\U0001f9ea Cuaderno",
    "\U0001f9fe Cornell",
)
FORBIDDEN_COLLECTION_NAMES = frozenset(
    {
        "annotation",
        "annotations",
        "concept_evidence_link",
        "concept_evidence_links",
        "reading_note",
        "reading_notes",
    }
)
FORBIDDEN_IMPLEMENTATION_NAMES = (
    "annotation",
    "conceptevidence",
    "readingnote",
)


def _literal_list_assignment(tree: ast.Module, name: str) -> tuple[str, ...]:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        values = tuple(
            item.value
            for item in node.value.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        )
        if len(values) == len(node.value.elts):
            return values
    raise AssertionError(f"No literal assignment found for {name}")


def _calls_in_body(node: ast.If) -> set[str]:
    calls: set[str] = set()
    for statement in node.body:
        for child in ast.walk(statement):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                calls.add(child.func.id)
    return calls


def _page_branch(tree: ast.Module, expected: str, *, symbolic: bool = False) -> ast.If:
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        comparison = node.test
        if not isinstance(comparison.left, ast.Name) or comparison.left.id != "page":
            continue
        if len(comparison.comparators) != 1:
            continue
        comparator = comparison.comparators[0]
        if symbolic and isinstance(comparator, ast.Name) and comparator.id == expected:
            return node
        if not symbolic and isinstance(comparator, ast.Constant) and comparator.value == expected:
            return node
    raise AssertionError(f"No router branch found for {expected}")


def _is_navigation_helper_assignment(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "nav_options" for target in node.targets
        )
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "add_source_catalog_navigation"
        and len(node.value.args) == 1
        and isinstance(node.value.args[0], ast.Name)
        and node.value.args[0].id == "nav_options"
    )


def _selectbox_uses_namespaced_key(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "selectbox":
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "key"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "NAVIGATION_WIDGET"
            ):
                return True
    return False


def _navigation_appends(tree: ast.Module) -> set[str]:
    appended: set[str] = set()
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr != "append"
            or not isinstance(node.func.value, ast.Name)
            or node.func.value.id != "nav_options"
            or len(node.args) != 1
        ):
            continue
        value = node.args[0]
        if isinstance(value, ast.Name):
            appended.add(value.id)
        elif isinstance(value, ast.Constant) and isinstance(value.value, str):
            appended.add(value.value)
    return appended


class _WriteSentinelCollection:
    def __init__(self, database: _ReadOnlyMathV0, name: str) -> None:
        self.database = database
        self.name = name

    def list_indexes(self):
        self.database.reads.append(f"{self.name}.list_indexes")
        return iter(())

    def _write(self, operation: str, *_args: Any, **_kwargs: Any) -> None:
        self.database.write_attempts.append(f"{self.name}.{operation}")
        raise AssertionError(f"unexpected Mongo write: {self.name}.{operation}")

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self._write("create_index", *args, **kwargs)

    def insert_one(self, *args: Any, **kwargs: Any) -> None:
        self._write("insert_one", *args, **kwargs)

    def update_one(self, *args: Any, **kwargs: Any) -> None:
        self._write("update_one", *args, **kwargs)

    def replace_one(self, *args: Any, **kwargs: Any) -> None:
        self._write("replace_one", *args, **kwargs)

    def delete_one(self, *args: Any, **kwargs: Any) -> None:
        self._write("delete_one", *args, **kwargs)


class _ReadOnlyMathV0:
    name = "MathV0"

    def __init__(self) -> None:
        self.reads: list[str] = []
        self.write_attempts: list[str] = []
        self.collections = {
            name: _WriteSentinelCollection(self, name) for name in ("sources", "references")
        }

    def __getitem__(self, name: str) -> _WriteSentinelCollection:
        self.reads.append(f"database[{name}]")
        return self.collections[name]

    def list_collection_names(self) -> list[str]:
        self.reads.append("database.list_collection_names")
        return list(self.collections)

    def _write(self, operation: str, *_args: Any, **_kwargs: Any) -> None:
        self.write_attempts.append(f"database.{operation}")
        raise AssertionError(f"unexpected Mongo write: database.{operation}")

    def create_collection(self, *args: Any, **kwargs: Any) -> None:
        self._write("create_collection", *args, **kwargs)

    def drop_collection(self, *args: Any, **kwargs: Any) -> None:
        self._write("drop_collection", *args, **kwargs)

    def command(self, *args: Any, **kwargs: Any) -> None:
        self._write("command", *args, **kwargs)


class _Connection:
    def __init__(self, database: _ReadOnlyMathV0) -> None:
        self.db = database


class _NoApplyIndexManager(SourceCatalogIndexManager):
    def __init__(self, database: _ReadOnlyMathV0) -> None:
        super().__init__(database)
        self.apply_attempts = 0

    def apply(self):
        self.apply_attempts += 1
        raise AssertionError("inspection/render without submit must not call apply")


class _ReadOnlyUI:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.messages: list[tuple[str, str]] = []
        self.form_submit_count = 0
        self.submit_disabled: bool | None = None

    def _message(self, level: str, value: object) -> None:
        self.messages.append((level, str(value)))

    def subheader(self, value: object) -> None:
        self._message("subheader", value)

    def error(self, value: object) -> None:
        self._message("error", value)

    def success(self, value: object) -> None:
        self._message("success", value)

    def warning(self, value: object) -> None:
        self._message("warning", value)

    def info(self, value: object) -> None:
        self._message("info", value)

    def caption(self, value: object) -> None:
        self._message("caption", value)

    def write(self, value: object) -> None:
        self._message("write", value)

    def dataframe(self, _rows: object, **_kwargs: Any) -> None:
        return None

    def expander(self, *_args: Any, **_kwargs: Any):
        return nullcontext(self)

    def form(self, *_args: Any, **_kwargs: Any):
        return nullcontext(self)

    def text_input(self, _label: str, *, key: str) -> str:
        del key
        return "MathV0"

    def checkbox(self, _label: str, *, key: str) -> bool:
        del key
        return True

    def form_submit_button(self, _label: str, *, disabled: bool) -> bool:
        self.form_submit_count += 1
        self.submit_disabled = disabled
        return False


def test_router_ast_preserves_existing_pages_and_routes_catalog_labels() -> None:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"), filename=str(ROUTER))

    assert _literal_list_assignment(tree, "nav_options") == EXISTING_NAVIGATION
    assert any(_is_navigation_helper_assignment(node) for node in tree.body)
    assert add_source_catalog_navigation(list(EXISTING_NAVIGATION)) == [
        EXISTING_NAVIGATION[0],
        ADD_SOURCE_NAV_LABEL,
        EDIT_SOURCE_NAV_LABEL,
        *EXISTING_NAVIGATION[1:],
    ]
    assert ADD_SOURCE_NAV_LABEL == "\u2795 Add Source"
    assert EDIT_SOURCE_NAV_LABEL == "\u270f\ufe0f Edit / Analyze Source"
    assert NAVIGATION_WIDGET == "source_catalog_navigation"
    assert _selectbox_uses_namespaced_key(tree)
    assert {*OPTIONAL_EXISTING_NAVIGATION, "CPI_NAV_LABEL"} <= _navigation_appends(tree)

    add_branch = _page_branch(tree, "ADD_SOURCE_NAV_LABEL", symbolic=True)
    edit_branch = _page_branch(tree, "EDIT_SOURCE_NAV_LABEL", symbolic=True)
    assert "render_add_source_page" in _calls_in_body(add_branch)
    assert "render_edit_source_page" in _calls_in_body(edit_branch)
    for existing_page in EXISTING_NAVIGATION:
        _page_branch(tree, existing_page)
    for optional_page in OPTIONAL_EXISTING_NAVIGATION:
        _page_branch(tree, optional_page)
    _page_branch(tree, "CPI")


def test_s1b_modules_do_not_define_or_access_out_of_scope_collections() -> None:
    violations: list[str] = []
    paths = sorted(path for directory in S1B_MODULE_DIRS for path in directory.glob("*.py"))

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.casefold() in FORBIDDEN_COLLECTION_NAMES:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.value!r}")
            elif isinstance(node, ast.Attribute):
                if node.attr.casefold() in FORBIDDEN_COLLECTION_NAMES:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: .{node.attr}")
            elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                compact_name = node.name.replace("_", "").casefold()
                if any(word in compact_name for word in FORBIDDEN_IMPLEMENTATION_NAMES):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.name}")

    assert paths
    assert violations == []


def test_mathv0_status_inspection_and_render_without_submit_are_read_only() -> None:
    database = _ReadOnlyMathV0()
    context = build_catalog_context("MathMongo (Current)", _Connection(database))
    index_manager = _NoApplyIndexManager(database)
    context = replace(context, index_manager=index_manager)
    ui = _ReadOnlyUI()

    inspected = inspect_catalog_status(context)
    rendered = render_catalog_status(ui, context)

    assert inspected.database_name == "MathV0"
    assert inspected.source_collection_exists is True
    assert inspected.reference_collection_exists is True
    assert inspected.plan.missing
    assert rendered is not None
    assert rendered.database_name == "MathV0"
    assert ui.form_submit_count == 1
    assert ui.submit_disabled is False
    assert index_manager.apply_attempts == 0
    assert database.write_attempts == []
    assert "database[sources]" in database.reads
    assert "database[references]" in database.reads
    assert "sources.list_indexes" in database.reads
    assert "references.list_indexes" in database.reads

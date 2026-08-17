"""Create/edit integration contracts for the shared LaTeX toolbar."""

# ruff: noqa: D103

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _module(path: str) -> ast.Module:
    return ast.parse((PROJECT_ROOT / path).read_text(encoding="utf-8"))


def _function(module: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _called_names(node: ast.AST) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }


def test_cuaderno_create_and_edit_both_use_shared_toolbar() -> None:
    module = _module("editor/cuaderno_page.py")

    assert "_render_latex_toolbar" in _called_names(_function(module, "_render_diary_new_note"))
    assert "_render_latex_toolbar" in _called_names(_function(module, "_render_note_editor"))
    assert "render_latex_toolbar" in _called_names(_function(module, "_render_latex_toolbar"))


def test_cornell_create_and_edit_converge_on_toolbar_enabled_editor() -> None:
    module = _module("editor/cornell/streamlit_page.py")

    assert "_render_current_note_editor" in _called_names(_function(module, "render_cornell_page"))
    assert "_render_current_note_editor" in _called_names(_function(module, "_render_edit_notes"))
    assert "_render_page_editor" in _called_names(_function(module, "_render_current_note_editor"))
    assert "render_latex_toolbar" in _called_names(_function(module, "_render_page_editor"))


def test_cpi_create_and_edit_converge_on_toolbar_enabled_editor() -> None:
    module = _module("editor/cpi/streamlit_page.py")

    assert "_render_current_note_editor" in _called_names(_function(module, "render_cpi_page"))
    assert "_render_current_note_editor" in _called_names(_function(module, "_render_edit_notes"))
    assert "_render_page_editor" in _called_names(_function(module, "_render_current_note_editor"))
    assert "_render_latex_tools" in _called_names(_function(module, "_render_page_editor"))
    assert "render_latex_toolbar" in _called_names(_function(module, "_render_latex_tools"))


def test_concepts_create_and_edit_have_distinct_instances_of_same_toolbar() -> None:
    module = _module("editor/editor_streamlit.py")
    calls = [
        call
        for call in ast.walk(module)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "render_latex_toolbar"
    ]
    prefixes = {
        keyword.value.value
        for call in calls
        for keyword in call.keywords
        if keyword.arg == "key_prefix" and isinstance(keyword.value, ast.Constant)
    }

    assert prefixes == {"concept_create_latex_tool", "concept_edit_latex_tool"}


def test_active_consumers_do_not_redeclare_canonical_snippets() -> None:
    for path in (
        "editor/cuaderno_page.py",
        "editor/cornell/streamlit_page.py",
        "editor/cpi/streamlit_page.py",
        "editor/editor_streamlit.py",
    ):
        source = (PROJECT_ROOT / path).read_text(encoding="utf-8")
        assert r"\begin{definition}" not in source
        assert "ValorLanguage" not in source

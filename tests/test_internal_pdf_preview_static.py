"""Static regression tests for internal previews of generated PDFs."""

# ruff: noqa: D103

from __future__ import annotations

import ast
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
P1_EXECUTABLE_MODULES = (
    ROOT / "editor/pdf_preview.py",
    ROOT / "editor/pdf_export.py",
    ROOT / "editor/editor_streamlit.py",
    ROOT / "editor/cornell/streamlit_page.py",
    ROOT / "editor/cpi/streamlit_page.py",
)
FORBIDDEN_MESSAGE_FRAGMENTS = (
    "nueva pestaña",
    "new tab",
)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _executable_string_nodes(tree: ast.AST) -> list[ast.Constant]:
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            docstrings.add(id(node.body[0].value))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_p1_executable_modules_do_not_open_local_pdf_urls() -> None:
    failures: list[str] = []
    for path in P1_EXECUTABLE_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(ROOT)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = [alias.name for alias in node.names]
                imported_from = node.module if isinstance(node, ast.ImportFrom) else None
                if imported_from == "webbrowser" or "webbrowser" in imported:
                    failures.append(f"{relative}:{node.lineno}: imports webbrowser")
                if "open_local_pdf" in imported:
                    failures.append(f"{relative}:{node.lineno}: imports open_local_pdf")

            if isinstance(node, ast.Attribute) and node.attr == "as_uri":
                failures.append(f"{relative}:{node.lineno}: references Path.as_uri")

            if isinstance(node, ast.Call):
                called = _qualified_name(node.func)
                if called in {
                    "webbrowser.open",
                    "webbrowser.open_new_tab",
                    "open_local_pdf",
                }:
                    failures.append(f"{relative}:{node.lineno}: calls {called}")

        for node in _executable_string_nodes(tree):
            lowered = node.value.casefold()
            if "file://" in lowered:
                failures.append(f"{relative}:{node.lineno}: contains a file URL")
            for fragment in FORBIDDEN_MESSAGE_FRAGMENTS:
                if fragment in lowered:
                    failures.append(
                        f"{relative}:{node.lineno}: contains obsolete browser message {fragment!r}"
                    )

    assert not failures, "\n".join(failures)


def test_streamlit_official_pdf_extra_is_declared_consistently() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)
    streamlit = project["tool"]["poetry"]["dependencies"]["streamlit"]

    assert streamlit == {"version": "^1.35", "extras": ["pdf"]}
    assert project["tool"]["poetry"]["dependencies"]["streamlit-pdf"] == ">=1.0.0,<2"

    active_requirements = {
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "streamlit[pdf]" in active_requirements
    assert "streamlit-pdf>=1.0.0,<2" in active_requirements
    assert "streamlit" not in active_requirements

"""Contracts for MathMongo's canonical LaTeX editing capabilities."""

# ruff: noqa: D103

from __future__ import annotations

import re
from pathlib import Path

import pytest

from editor.cornell.latex_compat import snippet_environment_names
from editor.cornell.latex_compat import supported_cornell_snippet_environments
from editor.latex_tools import CATEGORY_ORDER
from editor.latex_tools import LATEX_SURFACE_CONCEPTS
from editor.latex_tools import LATEX_SURFACE_CORNELL
from editor.latex_tools import LATEX_SURFACE_CPI
from editor.latex_tools import LATEX_SURFACE_CUADERNO
from editor.latex_tools import LATEX_SURFACES
from editor.latex_tools import LATEX_TOOLS
from editor.latex_tools import append_latex_snippet
from editor.latex_tools import apply_queued_latex_snippet
from editor.latex_tools import environment_pairs
from editor.latex_tools import latex_tool_by_id
from editor.latex_tools import latex_tool_groups
from editor.latex_tools import latex_tools_for_surface
from editor.latex_tools import queue_latex_snippet
from editor.ui.latex_toolbar import render_latex_toolbar

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_CATEGORY = "Bloques semánticos del cuaderno"


def test_registry_has_unique_stable_ids_and_complete_metadata() -> None:
    ids = [tool.id for tool in LATEX_TOOLS]

    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", tool.id) for tool in LATEX_TOOLS)
    assert all(tool.label.strip() for tool in LATEX_TOOLS)
    assert all(tool.help.strip() for tool in LATEX_TOOLS)
    assert all(tool.snippet.strip() for tool in LATEX_TOOLS)
    assert all(tool.category in CATEGORY_ORDER for tool in LATEX_TOOLS)
    assert all(tool.surfaces and tool.surfaces <= LATEX_SURFACES for tool in LATEX_TOOLS)


def test_every_environment_snippet_closes_in_reverse_nesting_order() -> None:
    for tool in LATEX_TOOLS:
        opened, closed = environment_pairs(tool.snippet)
        assert opened == tuple(reversed(closed)), tool.id


def test_common_tools_are_declared_for_all_four_consumers() -> None:
    general = [tool for tool in LATEX_TOOLS if tool.category != SEMANTIC_CATEGORY]

    assert general
    assert all(tool.surfaces == LATEX_SURFACES for tool in general)
    for surface in LATEX_SURFACES:
        exposed_ids = {tool.id for tool in latex_tools_for_surface(surface)}
        assert {tool.id for tool in general} <= exposed_ids


def test_semantic_blocks_remain_exclusive_to_cuaderno() -> None:
    semantic = [tool for tool in LATEX_TOOLS if tool.category == SEMANTIC_CATEGORY]

    assert {tool.id for tool in semantic} >= {
        "context",
        "reading",
        "exploration",
        "hypothesis",
        "connections",
        "reflection",
        "decision",
        "openquestions",
        "technical",
        "nextsteps",
        "checkpoint",
        "warningnote",
        "successnote",
        "errornote",
    }
    assert all(tool.surfaces == {LATEX_SURFACE_CUADERNO} for tool in semantic)
    for surface in (LATEX_SURFACE_CORNELL, LATEX_SURFACE_CPI, LATEX_SURFACE_CONCEPTS):
        assert not any(tool.category == SEMANTIC_CATEGORY for tool in latex_tools_for_surface(surface))


def test_surface_groups_follow_canonical_order_and_none_are_empty() -> None:
    for surface in LATEX_SURFACES:
        groups = latex_tool_groups(surface)
        titles = tuple(group.title for group in groups)

        assert all(group.tools for group in groups)
        assert titles == tuple(category for category in CATEGORY_ORDER if category in titles)
        assert len({tool.id for group in groups for tool in group.tools}) == sum(
            len(group.tools) for group in groups
        )


def test_registry_removes_known_obsolete_snippet_syntax() -> None:
    combined = "\n".join(tool.snippet for tool in LATEX_TOOLS)

    assert "ValorLanguage" not in combined
    assert r"\begin{dirtree}" not in combined
    assert latex_tool_by_id("dirtree").snippet.startswith(r"\dirtree{")
    for tool_id in (
        "definition",
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "example",
        "remark",
    ):
        assert re.search(r"\\begin\{[^}]+\}\{[^}]+\}", latex_tool_by_id(tool_id).snippet)


def test_declared_packages_exist_in_managed_latex_sources() -> None:
    sources = "\n".join(
        (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "templates_latex/miestilo.sty",
            "templates_latex/notes.sty",
            "templates_latex/notes.cls",
        )
    )
    declared: set[str] = set()
    for package_group in re.findall(
        r"\\(?:RequirePackage|usepackage)(?:\[[^]]*\])?\{([^}]+)\}",
        sources,
    ):
        declared.update(item.strip() for item in package_group.split(","))
    declared.update({"miestilo", "notes", "mathmongo-macros"})

    packages = {package for tool in LATEX_TOOLS for package in tool.packages}

    assert packages <= declared


def test_cornell_compatibility_covers_every_common_environment() -> None:
    declared = set(snippet_environment_names())
    supported = set(supported_cornell_snippet_environments())

    assert declared <= supported


@pytest.mark.parametrize(
    ("existing", "snippet", "expected"),
    [
        ("", "α", "α\n"),
        ("inicio", "β", "inicio\nβ\n"),
        ("línea 1\nlínea 2\n", r"\(x^2\)", "línea 1\nlínea 2\n\\(x^2\\)\n"),
        ("contenido matemático ∀ x", "", "contenido matemático ∀ x"),
    ],
)
def test_append_preserves_plain_text_unicode_and_multiline_content(
    existing: str,
    snippet: str,
    expected: str,
) -> None:
    assert append_latex_snippet(existing, snippet) == expected


def test_unknown_surface_and_tool_fail_explicitly() -> None:
    with pytest.raises(ValueError, match="Unknown LaTeX editing surface"):
        latex_tool_groups("unknown")
    with pytest.raises(KeyError):
        latex_tool_by_id("unknown")


def test_queued_insert_preserves_existing_content_and_clears_only_transient_flags() -> None:
    state = {
        "text": "Texto previo con Unicode: á, ∀ y x²",
        "unrelated": {"persist": True},
    }
    snippet = latex_tool_by_id("align").snippet

    queue_latex_snippet(
        state,
        snippet_key="pending_snippet",
        trigger_key="do_insert",
        snippet=snippet,
    )
    applied = apply_queued_latex_snippet(
        state,
        text_key="text",
        snippet_key="pending_snippet",
        trigger_key="do_insert",
    )

    assert applied is True
    assert state["text"].startswith("Texto previo con Unicode: á, ∀ y x²\n")
    assert state["text"].endswith(snippet)
    assert state["pending_snippet"] == ""
    assert state["do_insert"] is False
    assert state["unrelated"] == {"persist": True}
    assert apply_queued_latex_snippet(
        state,
        text_key="text",
        snippet_key="pending_snippet",
        trigger_key="do_insert",
    ) is False


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class _FakeUi:
    def __init__(self, clicked_suffix: str | None = None) -> None:
        self.clicked_suffix = clicked_suffix
        self.captions: list[str] = []
        self.buttons: list[dict[str, object]] = []

    def caption(self, value: str) -> None:
        self.captions.append(value)

    def container(self, **kwargs):
        assert kwargs == {"horizontal": True, "gap": "xsmall"}
        return _Context()

    def button(self, label: str, **kwargs) -> bool:
        self.buttons.append({"label": label, **kwargs})
        return bool(self.clicked_suffix and str(kwargs["key"]).endswith(self.clicked_suffix))


def test_toolbar_is_responsive_tooltip_enabled_and_dispatches_exact_snippet() -> None:
    ui = _FakeUi(clicked_suffix="_theorem")
    inserted: list[str] = []

    render_latex_toolbar(
        surface=LATEX_SURFACE_CORNELL,
        key_prefix="create_cornell",
        on_insert=inserted.append,
        ui=ui,
    )

    assert ui.captions == [group.title for group in latex_tool_groups(LATEX_SURFACE_CORNELL)]
    assert all(button["help"] for button in ui.buttons)
    assert all(button["type"] == "tertiary" for button in ui.buttons)
    assert all(button["width"] == "content" for button in ui.buttons)
    assert inserted == [latex_tool_by_id("theorem").snippet]

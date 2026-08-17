"""Reusable Streamlit renderer for the canonical MathMongo LaTeX tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from editor.latex_tools import latex_tool_groups


def render_latex_toolbar(
    *,
    surface: str,
    key_prefix: str,
    on_insert: Callable[[str], None],
    ui: Any | None = None,
) -> None:
    """Render a compact responsive toolbar and dispatch selected snippets."""
    if ui is None:
        import streamlit as st

        ui = st

    for group in latex_tool_groups(surface):
        ui.caption(group.title)
        with ui.container(horizontal=True, gap="xsmall"):
            for tool in group.tools:
                if ui.button(
                    tool.label,
                    key=f"{key_prefix}_{tool.id}",
                    help=tool.help,
                    icon=tool.icon,
                    type="tertiary",
                    width="content",
                ):
                    on_insert(tool.snippet)


__all__ = ["render_latex_toolbar"]

"""Notebook; extracted without import-time rendering."""

from __future__ import annotations

from editor.notebook_availability import _cuaderno_is_installed


def render(context):
    """Render only the selected page using its explicit application context."""
    db = context.db
    from editor.cuaderno_page import render_cuaderno
    render_cuaderno(db, _cuaderno_is_installed)

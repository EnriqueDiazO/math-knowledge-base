"""Cpi; extracted without import-time rendering."""

from __future__ import annotations


def render(context):
    """Render only the selected page using its explicit application context."""
    db = context.db
    from editor.cpi.streamlit_page import render_cpi_page
    render_cpi_page(db)

"""Cornell; extracted without import-time rendering."""

from __future__ import annotations


def render(context):
    """Render only the selected page using its explicit application context."""
    db = context.db
    from editor.cornell.streamlit_page import render_cornell_page
    render_cornell_page(db)

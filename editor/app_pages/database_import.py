"""Database import; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from editor.database_import_page import render_database_import_page


def render(context):
    """Render only the selected page using its explicit application context."""
    db = context.db
    render_database_import_page(st, db)

"""Study room; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st


def render(context):
    """Render only the selected page using its explicit application context."""
    active_database_scope = context.active_database_scope
    db = context.db
    if db is None or not active_database_scope:
        st.error('Selecciona una conexión y base para abrir la habitación.')
    else:
        from editor.knowledge_map import render_knowledge_map
        render_knowledge_map(db, active_database_scope, room_mode=True)

# Dashboard page

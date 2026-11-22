"""Documents; extracted without import-time rendering."""

from __future__ import annotations

from editor.document_builder import render_document_builder_page


def render(context):
    """Render only the selected page using its explicit application context."""
    active_database_name = context.active_database_name
    active_database_scope = context.active_database_scope
    current_db = context.current_db
    db = context.db
    render_document_builder_page(
        db,
        current_db,
        database_scope=active_database_scope,
        database_name=active_database_name,
    )

# Export page

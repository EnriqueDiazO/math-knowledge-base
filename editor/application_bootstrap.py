"""Build the active application context once before any page widgets exist."""

from __future__ import annotations

import streamlit as st

from editor.application_context import PageContext
from editor.connection_controls import render_connection_controls
from editor.connection_manager import DatabaseManager
from editor.database_connections import initialize_configured_connection
from editor.database_scope import database_scope_token
from editor.reading_space.state import sync_database_state as sync_reading_database_state
from editor.source_catalog.shared import build_catalog_context
from editor.source_catalog.shared import safe_error_message as safe_catalog_error
from editor.source_catalog.state import sync_database_state
from mathmongo.config import resolve_config


def prepare_application():
    """Select only the configured connection and invalidate context-bound state."""
    # Initialize database manager in session state
    if 'db_manager' not in st.session_state:
        st.session_state.db_manager = DatabaseManager()
        app_settings = resolve_config()
        initialize_configured_connection(st.session_state.db_manager, app_settings)
    current_db, current_database_label, active_theme = render_connection_controls(st.session_state.db_manager)
    db = st.session_state.db_manager.get_current_connection()
    catalog_context = None
    catalog_context_error = None
    active_database_scope = None
    active_database_name = None
    if db is not None:
        try:
            catalog_context = build_catalog_context(current_db or "<unlabeled connection>", db)
            active_database_name = catalog_context.database_name
            active_database_scope = database_scope_token(
                catalog_context.connection_label,
                catalog_context.database_name,
            )
            sync_database_state(
                st.session_state,
                connection_label=catalog_context.connection_label,
                database_name=catalog_context.database_name,
                database=catalog_context.database,
            )
            sync_reading_database_state(
                st.session_state,
                connection_label=catalog_context.connection_label,
                database_name=catalog_context.database_name,
                database=catalog_context.database,
            )
        except Exception as exc:
            catalog_context_error = safe_catalog_error(exc)

    return PageContext(db=db, current_db=current_db, current_database_label=current_database_label,
        catalog_context=catalog_context, catalog_context_error=catalog_context_error,
        active_database_scope=active_database_scope, active_database_name=active_database_name,
        active_theme=active_theme)

"""Connection and appearance controls; render only when explicitly composed."""

from __future__ import annotations

import streamlit as st

from editor.database_connections import active_database_display_label
from editor.reading_space.state import READING_SPACE_NAV_LABEL
from editor.source_catalog.state import NAVIGATION_WIDGET
from editor.study_navigation import ROOM_RETURN
from editor.study_navigation import STUDY_ROOM_NAV_LABEL
from editor.ui.theme import apply_mathmongo_theme
from editor.ui.theme import render_theme_control
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error


def render_connection_controls(manager):
    """Present the existing controls without importing the application entry."""
    st.sidebar.title(":material/functions: MathMongo")
    st.sidebar.caption("Cuaderno académico para lectura, escritura y conocimiento matemático.")
    st.sidebar.divider()

    # Database connection section
    st.sidebar.subheader("Conexión a la base")

    # Show current connection
    current_db = None
    for name, conn_info in manager.connections.items():
        if manager.get_current_connection() == conn_info['connection']:
            current_db = name
            break

    current_database_label = None
    if current_db:
        current_database_label = active_database_display_label(
            current_db,
            manager.get_current_connection(),
        )
        st.sidebar.caption(f"{current_database_label} · conectada")
    else:
        st.sidebar.warning("No hay una base conectada.", icon=":material/portable_wifi_off:")

    # Database switcher
    available_dbs = manager.list_connections()
    if available_dbs:
        selected_db = st.sidebar.selectbox(
            "Cambiar base activa",
            available_dbs,
            index=available_dbs.index(current_db) if current_db in available_dbs else 0,
            format_func=lambda connection_label: active_database_display_label(
                connection_label,
                manager.get_connection(connection_label),
            ),
        )

        if selected_db != current_db:
            if manager.set_current_connection(selected_db):
                selected_database_label = active_database_display_label(
                    selected_db,
                    manager.get_current_connection(),
                )
                st.sidebar.success(
                    f"Base activa: {selected_database_label}",
                    icon=":material/check_circle:",
                )
                st.rerun()

    # Secondary database actions
    with st.sidebar.expander("Administrar conexiones", expanded=False, icon=":material/settings:"):
        new_db_name = st.text_input("Etiqueta de conexión", placeholder="p. ej., base docente")
        new_db_uri = st.text_input(
            "MongoDB URI",
            value=resolve_config().mongo_uri,
            type="password",
        )
        new_db_collection = st.text_input("Nombre de la base", placeholder="p. ej., MathV0")

        if st.button("Añadir conexión", icon=":material/add:"):
            if new_db_name and new_db_uri and new_db_collection:
                if manager.add_connection(new_db_name, new_db_uri, new_db_collection):
                    st.success(f"Conexión añadida: {new_db_name}", icon=":material/check_circle:")
                    st.rerun()
            else:
                st.error("Completa los tres campos para añadir una conexión.")

    with st.sidebar.expander("Acciones de conexión", expanded=False, icon=":material/network_check:"):
        if st.button("Probar conexión", icon=":material/network_check:"):
            current_conn = manager.get_current_connection()
            if current_conn:
                try:
                    # Test connection by getting collection count
                    concept_count = current_conn.concepts.count_documents({})
                    st.sidebar.success(
                        f"Conexión disponible · {concept_count} conceptos.",
                        icon=":material/check_circle:",
                    )
                except Exception as e:
                    connection_info = manager.connections.get(current_db or "", {})
                    uri = str(connection_info.get("uri") or resolve_config().mongo_uri)
                    st.sidebar.error(f"No se pudo conectar: {sanitize_mongo_error(e, uri)}")
            else:
                st.sidebar.error("No hay una conexión activa.")

    with st.sidebar:
        st.divider()
        st.subheader("Tema")
        active_theme = render_theme_control(st, study_mode=(NAVIGATION_WIDGET not in st.session_state and st.query_params.get("study") == "1") or st.session_state.get(NAVIGATION_WIDGET) in {"🗺️ Grafo de conocimiento", STUDY_ROOM_NAV_LABEL} or (st.session_state.get(NAVIGATION_WIDGET) == READING_SPACE_NAV_LABEL and bool(st.session_state.get(ROOM_RETURN))))
    apply_mathmongo_theme(active_theme, st)
    st.sidebar.divider()


    return current_db, current_database_label, active_theme

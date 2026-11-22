"""Page registration and pending navigation; no page renders during import."""

from __future__ import annotations

from dataclasses import replace
from importlib import import_module

import streamlit as st

from editor.notebook_availability import _cuaderno_is_installed
from editor.reading_space.state import READING_SPACE_NAV_LABEL
from editor.reading_space.state import add_reading_space_navigation
from editor.reading_space.state import apply_pending_navigation as apply_pending_reading_navigation
from editor.source_catalog.state import ADD_SOURCE_NAV_LABEL
from editor.source_catalog.state import EDIT_SOURCE_NAV_LABEL
from editor.source_catalog.state import NAVIGATION_WIDGET
from editor.source_catalog.state import add_source_catalog_navigation
from editor.source_catalog.state import apply_pending_navigation
from editor.study_navigation import STUDY_ROOM_NAV_LABEL
from editor.study_navigation import add_study_room_navigation

PAGES = {
    '🏠 Inicio': 'home', '📄 Documentos': 'documents',
    '💡 Nuevo concepto': 'concept_create', '🖊️ Editar concepto': 'concept_edit',
    '🧠 Conceptos': 'concepts', '🕸️ Relaciones': 'relations',
    '🗺️ Grafo de conocimiento': 'knowledge_graph', '📤 Exportar': 'export',
    '💾 Exportar base': 'database_export', '📥 Importar base': 'database_import',
    '🧰 Mantenimiento': 'maintenance', '⚙️ Configuración': 'settings',
    'Diagnóstico': 'diagnosis', '📝 Cuaderno': 'notebook',
    '🟩 Cornell': 'cornell', '🟥 CPI': 'cpi',
    ADD_SOURCE_NAV_LABEL: 'source_create', EDIT_SOURCE_NAV_LABEL: 'source_edit',
    READING_SPACE_NAV_LABEL: 'reading', STUDY_ROOM_NAV_LABEL: 'study_room',
}


def select_page(context):
    """Apply pending widget state before creating the existing navigation control."""
    options = list(PAGES)[:13]
    if _cuaderno_is_installed(context.db):
        options[1:1] = ['📝 Cuaderno', '🟩 Cornell', '🟥 CPI']
    options = add_study_room_navigation(add_reading_space_navigation(add_source_catalog_navigation(options)))
    apply_pending_navigation(st.session_state, options)
    apply_pending_reading_navigation(st.session_state, options, navigation_key=NAVIGATION_WIDGET)
    if NAVIGATION_WIDGET not in st.session_state and st.query_params.get('study') == '1':
        st.session_state[NAVIGATION_WIDGET] = STUDY_ROOM_NAV_LABEL
    if st.session_state.get(NAVIGATION_WIDGET) not in options:
        st.session_state.pop(NAVIGATION_WIDGET, None)
    with st.sidebar:
        st.subheader('Navegación')
        page = st.selectbox('Navegación', options, key=NAVIGATION_WIDGET, label_visibility='collapsed')
    if page == STUDY_ROOM_NAV_LABEL and st.query_params.get('study') != '1':
        st.query_params['study'] = '1'
    elif page not in {STUDY_ROOM_NAV_LABEL, READING_SPACE_NAV_LABEL} and 'study' in st.query_params:
        del st.query_params['study']
    return page


def render_page(label, context):
    """Import only the active page and pass a complete context explicitly."""
    module = import_module('editor.app_pages.' + PAGES[label])
    module.render(replace(context, page='CPI' if label == '🟥 CPI' else label))

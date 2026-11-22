"""Streamlit CCv2 bridge: local rendering, explicit validated write intentions."""
from __future__ import annotations

import hashlib

import streamlit as st
from pymongo.errors import PyMongoError

from editor.source_catalog.lookup_ui import metadata_lookup
from editor.source_catalog.state import EDIT_SOURCE_NAV_LABEL
from editor.source_catalog.state import queue_legacy_concept_open
from editor.source_catalog.state import request_navigation
from editor.study_navigation import open_room_source
from mathmongo.bibliography_lookup.capture import ReferenceCapture
from mathmongo.knowledge_map.service import KnowledgeMapService
from mathmongo.knowledge_map.service import MapConflictError

# Manifest/build wiring was adapted from the official cookiecutter/v2 template.
_COMPONENT = st.components.v2.component(
    'mathmongo.knowledge_map', js='index-*.js', css='*.css',
    html='<div class="knowledge-map-root"></div>',
)


def render_knowledge_map(mongo, database_scope: str, *, room_mode: bool = False) -> None:
    """Keep per-database view state in the browser; never send Mongo credentials."""
    service = KnowledgeMapService(mongo)
    scope = hashlib.sha256(database_scope.encode()).hexdigest()[:32]
    if room_mode:
        scope += '_room'
    key = 'knowledge_map_' + scope
    result_key = key + '_result'

    def on_intent():
        payload = st.session_state[key].get('intent')
        if isinstance(payload, dict):
            st.session_state[result_key] = service.execute(payload)

    def on_bibliography():
        payload = st.session_state[key].get('bibliography')
        if isinstance(payload, dict):
            st.session_state[key + '_bibliography_result'] = ReferenceCapture(mongo.db, metadata_lookup()).execute(payload)

    def on_source():
        payload = st.session_state[key].get('open_source')
        if not open_room_source(st.session_state, mongo.db, payload):
            st.warning('La fuente o su pasaje ya no está disponible. Se conserva la habitación y el borrador.')

    def on_library():
        request_navigation(st.session_state, EDIT_SOURCE_NAV_LABEL)

    def on_open():
        payload = st.session_state[key].get('open_note')
        if isinstance(payload, dict) and isinstance(payload.get('key'), str):
            try:
                document = service.find(payload['key'])
            except MapConflictError:
                return
            if document is not None:
                queue_legacy_concept_open(st.session_state, concept_id=str(document['id']), source=document['source'])

    try:
        graph = service.graph(include_study=True) if room_mode else service.graph()
    except PyMongoError:
        st.error("No se pudo cargar el mapa. Revisa la conexión; los borradores se conservan en este navegador.")
        return
    _COMPONENT(key=key, data={**graph, 'scope': scope, 'roomMode': room_mode, 'result': st.session_state.get(result_key),
        'bibliography_result': st.session_state.get(key + '_bibliography_result')},
               on_intent_change=on_intent, on_open_note_change=on_open, on_bibliography_change=on_bibliography, on_open_source_change=on_source, on_open_library_change=on_library, height='content')

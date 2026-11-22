"""Reading; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from editor.reading_space.reader_page import render_reading_space_page
from editor.source_catalog.state import request_navigation
from editor.study_navigation import ROOM_RETURN
from editor.study_navigation import STUDY_ROOM_NAV_LABEL


def render(context):
    """Render only the selected page using its explicit application context."""
    catalog_context = context.catalog_context
    catalog_context_error = context.catalog_context_error
    if catalog_context is None:
        st.error(
            "Reading Space is unavailable for the selected connection: "
            f"{catalog_context_error or 'no active MongoDB database.'}"
        )
    else:
        if st.session_state.get(ROOM_RETURN) and st.button('Volver a la habitación de estudio', key='study_reader_return'):
            request_navigation(st.session_state, STUDY_ROOM_NAV_LABEL)
            st.rerun()
        render_reading_space_page(catalog_context)

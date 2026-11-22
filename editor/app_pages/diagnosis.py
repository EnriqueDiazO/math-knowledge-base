"""Diagnosis; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st


def render(context):
    """Render only the selected page using its explicit application context."""
    catalog_context = context.catalog_context
    if catalog_context is None:
        st.error('Conecta una biblioteca desde Ajustes para comprobar su estado.')
    else:
        from editor.reading_space.diagnostics import render_reading_diagnostics
        render_reading_diagnostics(catalog_context)

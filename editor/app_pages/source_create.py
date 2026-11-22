"""Source create; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from editor.source_catalog.add_source_page import render_add_source_page


def render(context):
    """Render only the selected page using its explicit application context."""
    catalog_context = context.catalog_context
    catalog_context_error = context.catalog_context_error
    if catalog_context is None:
        st.error(
            "Source Catalog is unavailable for the selected connection: "
            f"{catalog_context_error or 'no active MongoDB database.'}"
        )
    else:
        render_add_source_page(catalog_context)

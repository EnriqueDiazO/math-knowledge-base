"""MathMongo entry point: configuration, active context and selected page only."""

import sys
from pathlib import Path

# Streamlit also launches this file directly from an installed distribution.
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st

from editor.application_bootstrap import prepare_application
from editor.application_navigation import render_page
from editor.application_navigation import select_page

st.set_page_config(
    page_title="MathMongo · cuaderno académico",
    page_icon=":material/functions:",
    layout="wide",
    initial_sidebar_state="auto",
)

context = prepare_application()
selected_page = select_page(context)
render_page(selected_page, context)

st.divider()
st.caption("MathMongo · cuaderno académico")

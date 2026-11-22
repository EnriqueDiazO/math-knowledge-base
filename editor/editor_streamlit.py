"""MathMongo entry point: configuration, active context and selected page only."""

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

"""AppTest coverage for MathMongo's session-local visual theme control."""

from __future__ import annotations

import textwrap
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_theme_control_preserves_navigation_and_unsent_form_draft(tmp_path: Path) -> None:
    """Changing visual preference must not clear ordinary Streamlit widget state."""
    app_file = tmp_path / "theme_control_app.py"
    app_file.write_text(
        textwrap.dedent(
            """
            import streamlit as st

            from editor.ui.theme import apply_mathmongo_theme
            from editor.ui.theme import render_theme_control


            theme = render_theme_control(st)
            apply_mathmongo_theme(theme, st)
            page = st.selectbox("Navegación", ["🏠 Inicio", "➕ Add Source"], key="nav")
            with st.form("source_draft"):
                st.text_input("Name", key="source_name")
                st.text_area("Definition", key="source_definition")
                st.form_submit_button("Crear Source")
            st.caption(f"Página actual: {page}")
            """
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file)).run()

    assert not app.exception
    app.text_input[0].input("Borrador de teoría de grupos")
    theme_control = app.segmented_control[0]
    theme_control.set_value("dark")
    app.run()

    assert not app.exception
    assert app.session_state["mathmongo_ui_theme"] == "dark"
    assert app.selectbox[0].value == "🏠 Inicio"
    assert app.text_input[0].value == "Borrador de teoría de grupos"


def test_source_workflow_pages_do_not_render_dataframe_editors() -> None:
    """Source creation and editing must use vertical fields and summary cards."""
    for relative_path in (
        "editor/source_catalog/add_source_page.py",
        "editor/source_catalog/edit_source_page.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert ".dataframe(" not in source
        assert ".data_editor(" not in source
        assert ".table(" not in source

    add_source = (ROOT / "editor/source_catalog/add_source_page.py").read_text(encoding="utf-8")
    edit_source = (ROOT / "editor/source_catalog/edit_source_page.py").read_text(encoding="utf-8")
    assert "Vista previa" in add_source
    assert "Vista previa de cambios" in edit_source
    assert "with ui.form(" in add_source
    assert "with ui.form(" in edit_source

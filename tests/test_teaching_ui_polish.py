"""Static checks for the conservative teaching interface polish."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / ".streamlit" / "config.toml"
STREAMLIT_APP = ROOT / "editor" / "editor_streamlit.py"
CUADERNO = ROOT / "editor" / "cuaderno_page.py"
ADD_SOURCE = ROOT / "editor" / "source_catalog" / "add_source_page.py"
REFERENCE_FORM = ROOT / "editor" / "concept_reference_form.py"


def test_teaching_theme_declares_native_warm_light_and_dark_tokens() -> None:
    """Keep the shared Streamlit theme calm, native, and available in both modes."""
    theme = THEME.read_text(encoding="utf-8")

    assert 'base = "light"' in theme
    assert 'primaryColor = "#2F6F68"' in theme
    assert 'backgroundColor = "#F5F2EA"' in theme
    assert 'secondaryBackgroundColor = "#ECE7DC"' in theme
    assert 'textColor = "#17242A"' in theme
    assert 'backgroundColor = "#11191D"' in theme
    assert 'primaryColor = "#69AFA4"' in theme
    assert "#000000" not in theme
    assert "[theme.sidebar]" in theme
    assert "[theme.light]" in theme
    assert "[theme.dark]" in theme


def test_theme_control_and_navigation_are_rendered_in_the_sidebar() -> None:
    """Keep the complete visual preference control out of the page body."""
    app = STREAMLIT_APP.read_text(encoding="utf-8")

    assert 'with st.sidebar:\n    st.divider()\n    st.subheader("Tema")\n    active_theme = render_theme_control(st)' in app
    assert 'with st.sidebar:\n    st.subheader("Navegación")\n    selected_page = st.selectbox(' in app
    assert app.count("render_theme_control(st)") == 1


def test_chart_theming_uses_the_shared_plotly_helper() -> None:
    """Dashboard charts must not fall back to unthemed light/dark containers."""
    app = STREAMLIT_APP.read_text(encoding="utf-8")
    theme_module = (ROOT / "editor" / "ui" / "theme.py").read_text(encoding="utf-8")

    assert "def apply_chart_theme" in theme_module
    assert app.count("apply_chart_theme(") >= 4


def test_stale_or_destructive_teaching_copy_is_absent() -> None:
    """Keep legacy versioning and destructive teaching controls out of the UI."""
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (STREAMLIT_APP, CUADERNO, ADD_SOURCE)
    )

    for stale in (
        "Version 0.1.0b1",
        "Initial status: active",
        "make cuaderno-",
        "Clear All Data",
        "Confirm Clear All",
        "Cuaderno (Experimental)",
        "[MVP]",
    ):
        assert stale not in source


def test_main_interface_uses_native_containers_and_hides_technical_preview() -> None:
    """Use supported native grouping and collapsed technical information."""
    app = STREAMLIT_APP.read_text(encoding="utf-8")
    reference_form = REFERENCE_FORM.read_text(encoding="utf-8")

    assert "st.container(border=True)" in app
    assert "unsafe_allow_html=True" not in app
    assert 'with st.expander("Diagnóstico seguro", expanded=False' in app
    assert 'with ui.expander("Resultado normalizado", expanded=False):' in reference_form

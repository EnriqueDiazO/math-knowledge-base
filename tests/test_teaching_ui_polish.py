"""Static checks for the conservative teaching interface polish."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / ".streamlit" / "config.toml"
STREAMLIT_APP = ROOT / "editor" / "editor_streamlit.py"
CUADERNO = ROOT / "editor" / "cuaderno_page.py"
ADD_SOURCE = ROOT / "editor" / "source_catalog" / "add_source_page.py"
REFERENCE_FORM = ROOT / "editor" / "concept_reference_form.py"


def test_teaching_theme_uses_native_warm_light_tokens() -> None:
    """Keep the shared Streamlit theme calm, light, and native."""
    theme = THEME.read_text(encoding="utf-8")

    assert 'base = "light"' in theme
    assert 'primaryColor = "#176B63"' in theme
    assert 'backgroundColor = "#F8F6F1"' in theme
    assert "[theme.sidebar]" in theme
    assert 'base = "dark"' not in theme


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

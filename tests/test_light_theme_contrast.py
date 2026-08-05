"""Regression coverage for light-theme text legibility."""

from __future__ import annotations

from editor.ui.theme import THEME_TOKENS
from editor.ui.theme import apply_mathmongo_theme
from editor.ui.theme import plotly_layout


class _ThemeUi:
    """Minimal Streamlit facade that records injected CSS."""

    markup: str = ""

    def html(self, body: str) -> None:
        self.markup = body


def test_light_theme_uses_dark_text_for_supporting_ui_copy() -> None:
    """Labels must remain legible on MathMongo's warm light surfaces."""
    ui = _ThemeUi()

    apply_mathmongo_theme("light", ui)

    assert THEME_TOKENS["light"]["text"] == "#17242A"
    assert THEME_TOKENS["light"]["muted_text"] == "#28353B"
    assert '[data-testid="stWidgetLabel"]' in ui.markup
    assert '[data-testid="stMetricLabel"]' in ui.markup
    assert '[data-testid="stCaptionContainer"]' in ui.markup
    assert "opacity: 1 !important;" in ui.markup
    assert "#17242A" in ui.markup


def test_dark_theme_tokens_and_chart_layout_remain_unchanged() -> None:
    """Contrast work for light mode must not alter the approved dark palette."""
    ui = _ThemeUi()
    apply_mathmongo_theme("dark", ui)

    assert THEME_TOKENS["dark"] == {
        "primary": "#69AFA4",
        "primary_hover": "#82C4BA",
        "background": "#11191D",
        "surface": "#1D2A30",
        "panel": "#1D2A30",
        "secondary": "#182329",
        "input": "#213037",
        "table_header": "#26373E",
        "text": "#E7E4DA",
        "muted_text": "#A8B2B3",
        "border": "#34464D",
        "sidebar": "#152126",
        "sidebar_secondary": "#1B2A30",
        "success": "#203B2D",
        "warning": "#493E21",
        "error": "#482826",
        "info": "#223A48",
        "chart_grid": "#35434A",
    }
    assert plotly_layout("dark")["xaxis"] == {
        "gridcolor": "#35434A",
        "zerolinecolor": "#34464D",
    }
    assert '[data-testid="stMetricLabel"]' not in ui.markup
    assert "opacity: 1 !important;" not in ui.markup

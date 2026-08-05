"""Session-scoped, token-based theming for the MathMongo Streamlit UI."""

# ruff: noqa: UP031  # CSS braces make %-tokens clearer than escaping an f-string.

from __future__ import annotations

from typing import Any
from typing import Literal

ThemeName = Literal["light", "dark"]

THEME_STATE_KEY = "mathmongo_ui_theme"

THEME_TOKENS: dict[ThemeName, dict[str, str]] = {
    "light": {
        "primary": "#2F6F68",
        "primary_hover": "#255A55",
        "background": "#F5F2EA",
        "surface": "#FBF9F4",
        "panel": "#FBF9F4",
        "secondary": "#ECE7DC",
        "input": "#FFFDF8",
        "table_header": "#E4DED1",
        "text": "#243037",
        "muted_text": "#657177",
        "border": "#CFC8BA",
        "sidebar": "#E9E4D8",
        "sidebar_secondary": "#F0ECE2",
        "success": "#E4F0E6",
        "warning": "#F6EDC9",
        "error": "#F5DFDB",
        "info": "#DFEAF0",
        "chart_grid": "#D9D3C8",
    },
    "dark": {
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
    },
}


def normalize_theme(value: object) -> ThemeName:
    """Return a supported session theme without accepting arbitrary CSS values."""
    return "dark" if value == "dark" else "light"


def get_mathmongo_theme(ui: Any) -> ThemeName:
    """Read the session-local preference, defaulting to the warm light theme."""
    state = ui.session_state
    theme = normalize_theme(state.get(THEME_STATE_KEY))
    state.setdefault(THEME_STATE_KEY, theme)
    return theme


def render_theme_control(ui: Any) -> ThemeName:
    """Render the compact visible theme switch without touching application drafts."""
    current = get_mathmongo_theme(ui)
    choice = ui.segmented_control(
        "Tema",
        ("light", "dark"),
        format_func=lambda value: "☀️ Claro" if value == "light" else "🌙 Oscuro",
        key=THEME_STATE_KEY,
        required=True,
        width="stretch",
        label_visibility="collapsed",
        persist_state="session",
        help="El tema se conserva durante esta sesión y no modifica la base de datos.",
    )
    return normalize_theme(choice or current)


def apply_mathmongo_theme(theme: ThemeName, ui: Any) -> None:
    """Apply central, value-only CSS tokens for the active session theme.

    Streamlit's built-in light/dark themes remain declared in ``config.toml``.
    These stable accessibility and test-id selectors let the visible sidebar
    control apply its session preference immediately, without browser cookies,
    generated CSS hashes, or positional selectors.
    """
    tokens = THEME_TOKENS[normalize_theme(theme)]
    ui.html(
        """
<style id="mathmongo-session-theme">
:root {
  --primary-color: %(primary)s;
  --primary-hover-color: %(primary_hover)s;
  --background-color: %(background)s;
  --secondary-background-color: %(secondary)s;
  --text-color: %(text)s;
  --border-color: %(border)s;
  --mathmongo-panel: %(panel)s;
  --mathmongo-input: %(input)s;
  --mathmongo-muted: %(muted_text)s;
}
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
[data-testid="stMain"] {
  background-color: %(background)s !important;
  color: %(text)s !important;
}
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stToolbarActions"] {
  background-color: %(background)s !important;
  color: %(text)s !important;
}
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
  background-color: %(sidebar)s !important;
  color: %(text)s !important;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
  background-color: %(sidebar_secondary)s !important;
}
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stForm"],
[data-testid="stExpander"],
[data-testid="stMetric"] {
  background-color: %(panel)s;
  border-color: %(border)s !important;
  color: %(text)s !important;
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div {
  background-color: %(input)s !important;
  border-color: %(border)s !important;
  color: %(text)s !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
  color: %(muted_text)s !important;
}
[data-testid="stButton"] button,
[data-testid="stFormSubmitButton"] button {
  background-color: %(surface)s;
  border-color: %(border)s !important;
  color: %(text)s !important;
}
[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
  background-color: %(primary)s !important;
  border-color: %(primary)s !important;
  color: %(surface)s !important;
}
[data-testid="stButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover {
  border-color: %(primary_hover)s !important;
}
[data-testid="stSegmentedControl"] [role="radio"] {
  background-color: %(input)s !important;
  border-color: %(border)s !important;
  color: %(text)s !important;
}
[data-testid="stSegmentedControl"] [role="radio"][aria-checked="true"] {
  background-color: %(primary)s !important;
  border-color: %(primary)s !important;
  color: %(surface)s !important;
}
[data-baseweb="tab-list"] {
  background-color: %(secondary)s !important;
}
[data-baseweb="tab"] {
  color: %(muted_text)s !important;
}
[aria-selected="true"][data-baseweb="tab"] {
  color: %(primary)s !important;
}
[data-testid="stDataFrame"] {
  background-color: %(panel)s !important;
  border-color: %(border)s !important;
}
[data-testid="stAlert"] {
  background-color: %(secondary)s !important;
  border-color: %(border)s;
  color: %(text)s !important;
}
[data-testid="stCaptionContainer"],
[data-testid="stMarkdownContainer"] small {
  color: %(muted_text)s;
}
</style>
        """
        % tokens
    )


def plotly_layout(theme: ThemeName) -> dict[str, Any]:
    """Return readable, non-neon Plotly defaults for the Panorama charts."""
    tokens = THEME_TOKENS[normalize_theme(theme)]
    return {
        "paper_bgcolor": tokens["panel"],
        "plot_bgcolor": tokens["panel"],
        "font": {"color": tokens["text"]},
        "legend": {"font": {"color": tokens["text"]}},
        "hoverlabel": {
            "bgcolor": tokens["input"],
            "bordercolor": tokens["border"],
            "font": {"color": tokens["text"]},
        },
        "xaxis": {"gridcolor": tokens["chart_grid"], "zerolinecolor": tokens["border"]},
        "yaxis": {"gridcolor": tokens["chart_grid"], "zerolinecolor": tokens["border"]},
    }


def apply_chart_theme(fig: Any, theme: ThemeName) -> Any:
    """Apply MathMongo's readable Plotly layout and return the same figure."""
    fig.update_layout(**plotly_layout(theme))
    return fig


__all__ = [
    "THEME_STATE_KEY",
    "THEME_TOKENS",
    "ThemeName",
    "apply_chart_theme",
    "apply_mathmongo_theme",
    "get_mathmongo_theme",
    "normalize_theme",
    "plotly_layout",
    "render_theme_control",
]

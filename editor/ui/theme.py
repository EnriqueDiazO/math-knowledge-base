"""Session-scoped, token-based theming for the MathMongo Streamlit UI."""

# ruff: noqa: UP031  # CSS braces make %-tokens clearer than escaping an f-string.

from __future__ import annotations

from typing import Any
from typing import Literal

ThemeName = Literal["light", "dark"]

THEME_STATE_KEY = "mathmongo_ui_theme"

THEME_TOKENS: dict[ThemeName, dict[str, str]] = {
    "light": {
        "primary": "#176B63",
        "background": "#F4F1EA",
        "surface": "#FFFCF6",
        "secondary": "#EAE5DA",
        "text": "#202B2F",
        "muted_text": "#59666A",
        "border": "#D2CBC0",
        "sidebar": "#ECE8DE",
        "sidebar_secondary": "#E2DDD2",
        "chart_grid": "#D9D3C8",
    },
    "dark": {
        "primary": "#54A79D",
        "background": "#172126",
        "surface": "#202C32",
        "secondary": "#29363C",
        "text": "#E8EAE4",
        "muted_text": "#BAC4C2",
        "border": "#3B4B51",
        "sidebar": "#121B20",
        "sidebar_secondary": "#1B272C",
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
        persist_state="session",
        help="El tema se conserva durante esta sesión y no modifica la base de datos.",
    )
    return normalize_theme(choice or current)


def apply_mathmongo_theme(theme: ThemeName, ui: Any) -> None:
    """Apply central, value-only CSS tokens for the active session theme.

    Streamlit's built-in light/dark themes remain declared in ``config.toml``.
    These stable ``data-testid`` selectors let the visible sidebar control apply
    its session preference immediately, without browser cookies, DOM hashes, or
    positional selectors.
    """
    tokens = THEME_TOKENS[normalize_theme(theme)]
    ui.html(
        """
<style id="mathmongo-session-theme">
:root {
  --primary-color: %(primary)s;
  --background-color: %(background)s;
  --secondary-background-color: %(secondary)s;
  --text-color: %(text)s;
  --border-color: %(border)s;
}
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
[data-testid="stMain"] {
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
[data-testid="stForm"] {
  background-color: %(surface)s;
  border-color: %(border)s !important;
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div {
  background-color: %(surface)s !important;
  border-color: %(border)s !important;
  color: %(text)s !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {
  color: %(muted_text)s !important;
}
[data-testid="stButton"] button,
[data-testid="stFormSubmitButton"] button {
  border-color: %(border)s !important;
}
[data-testid="stAlert"] {
  border-color: %(border)s;
}
</style>
        """
        % tokens
    )


def plotly_layout(theme: ThemeName) -> dict[str, Any]:
    """Return readable, non-neon Plotly defaults for the Panorama charts."""
    tokens = THEME_TOKENS[normalize_theme(theme)]
    return {
        "paper_bgcolor": tokens["background"],
        "plot_bgcolor": tokens["secondary"],
        "font": {"color": tokens["text"]},
        "legend": {"font": {"color": tokens["text"]}},
        "xaxis": {"gridcolor": tokens["chart_grid"], "zerolinecolor": tokens["border"]},
        "yaxis": {"gridcolor": tokens["chart_grid"], "zerolinecolor": tokens["border"]},
    }


__all__ = [
    "THEME_STATE_KEY",
    "THEME_TOKENS",
    "ThemeName",
    "apply_mathmongo_theme",
    "get_mathmongo_theme",
    "normalize_theme",
    "plotly_layout",
    "render_theme_control",
]

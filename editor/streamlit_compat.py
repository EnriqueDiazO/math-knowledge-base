"""Small Streamlit API compatibility helpers used by note editors."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def _supports_width(widget: Callable[..., Any]) -> bool:
    """Return whether a Streamlit widget callable accepts the modern width argument."""
    try:
        return "width" in inspect.signature(widget).parameters
    except (TypeError, ValueError):
        return False


def stretch_button(container: Any, label: str, **kwargs: Any) -> bool:
    """Render a full-width button across supported Streamlit versions."""
    button = container.button
    if _supports_width(button):
        kwargs["width"] = "stretch"
    else:
        kwargs["use_container_width"] = True
    return bool(button(label, **kwargs))


__all__ = ["stretch_button"]

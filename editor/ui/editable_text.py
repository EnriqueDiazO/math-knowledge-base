"""Reusable plain-text editing helpers for long Streamlit fields."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from collections.abc import Sequence
from typing import Any

_RESIZABLE_TEXT_AREA_CSS = """
<style>
div[class*="st-key-mm_resizable_text_"] textarea {
    resize: vertical !important;
    overflow: auto !important;
}
</style>
"""


def _literal_pattern(search: str, *, case_sensitive: bool) -> re.Pattern[str] | None:
    """Build an escaped pattern so search text never gains regex semantics."""
    if not search:
        return None
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(re.escape(search), flags)


def count_literal_matches(text: str, search: str, *, case_sensitive: bool = False) -> int:
    """Count non-overlapping literal matches, protecting the empty-search case."""
    pattern = _literal_pattern(search, case_sensitive=case_sensitive)
    if pattern is None:
        return 0
    return sum(1 for _match in pattern.finditer(text))


def replace_first_literal(
    text: str,
    search: str,
    replacement: str,
    *,
    case_sensitive: bool = False,
) -> str:
    """Replace the first remaining literal match from the start of ``text``."""
    pattern = _literal_pattern(search, case_sensitive=case_sensitive)
    if pattern is None:
        return text
    match = pattern.search(text)
    if match is None:
        return text
    return f"{text[:match.start()]}{replacement}{text[match.end():]}"


def replace_all_literal(
    text: str,
    search: str,
    replacement: str,
    *,
    case_sensitive: bool = False,
) -> str:
    """Replace every non-overlapping literal match in ``text``."""
    pattern = _literal_pattern(search, case_sensitive=case_sensitive)
    if pattern is None:
        return text
    return pattern.sub(lambda _match: replacement, text)


def _control_key(field_key: str, suffix: str) -> str:
    return f"{field_key}__{suffix}"


def _scope_key(field_key: str) -> str:
    digest = hashlib.sha256(field_key.encode("utf-8")).hexdigest()[:16]
    return f"mm_resizable_text_{digest}"


def _call_change_callback(
    callback: Callable[..., Any] | None,
    callback_args: Sequence[Any],
    callback_kwargs: dict[str, Any],
) -> None:
    if callback is not None:
        callback(*callback_args, **callback_kwargs)


def _replace_from_session_state(
    field_key: str,
    search_key: str,
    replacement_key: str,
    case_sensitive_key: str,
    replace_all: bool,
    on_change: Callable[..., Any] | None,
    callback_args: Sequence[Any],
    callback_kwargs: dict[str, Any],
) -> None:
    """Update one widget value before its textarea is instantiated on the rerun."""
    import streamlit as st

    current = str(st.session_state.get(field_key) or "")
    search = str(st.session_state.get(search_key) or "")
    replacement = str(st.session_state.get(replacement_key) or "")
    case_sensitive = bool(st.session_state.get(case_sensitive_key, False))
    replace = replace_all_literal if replace_all else replace_first_literal
    updated = replace(
        current,
        search,
        replacement,
        case_sensitive=case_sensitive,
    )
    if updated == current:
        return
    st.session_state[field_key] = updated
    _call_change_callback(on_change, callback_args, callback_kwargs)


def _native_text_area(
    ui: Any,
    label: str,
    *,
    key: str,
    height: int | str | None,
    placeholder: str | None,
    help: str | None,
    disabled: bool,
    on_change: Callable[..., Any] | None,
    callback_args: Sequence[Any],
    callback_kwargs: dict[str, Any],
    label_visibility: str,
    width: str | int,
) -> str:
    widget_kwargs: dict[str, Any] = {
        "key": key,
        "height": height,
        "placeholder": placeholder,
        "help": help,
        "disabled": disabled,
        "label_visibility": label_visibility,
        "width": width,
    }
    if on_change is not None:
        widget_kwargs.update(
            on_change=on_change,
            args=tuple(callback_args),
            kwargs=callback_kwargs,
        )
    return str(ui.text_area(label, **widget_kwargs) or "")


def editable_text_area(
    label: str,
    value: str | None = "",
    *,
    key: str,
    height: int | str | None = None,
    placeholder: str | None = None,
    help: str | None = None,
    disabled: bool = False,
    searchable: bool = True,
    replaceable: bool = True,
    resizable: bool = True,
    on_change: Callable[..., Any] | None = None,
    args: Sequence[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    label_visibility: str = "visible",
    width: str | int = "stretch",
    ui: Any | None = None,
) -> str:
    """Render a resizable, searchable editor that still returns plain ``str``.

    Search and replacement controls use isolated keys derived from ``key``. The
    replacement callbacks update the textarea key before Streamlit recreates the
    widget, avoiding conflicting ``value`` and Session State sources.

    A searchable instance should not be placed inside ``st.form`` because its
    replacement actions are ordinary Streamlit buttons.
    """
    if ui is None:
        import streamlit as st

        ui = st

    field_key = str(key)
    initial_value = "" if value is None else str(value)
    if field_key not in ui.session_state:
        ui.session_state[field_key] = initial_value

    callback_args = tuple(args or ())
    callback_kwargs = dict(kwargs or {})
    enhanced_ui_available = all(
        hasattr(ui, name)
        for name in (
            "button",
            "caption",
            "checkbox",
            "container",
            "markdown",
            "popover",
            "text_input",
        )
    )
    if not searchable or not enhanced_ui_available:
        return _native_text_area(
            ui,
            label,
            key=field_key,
            height=height,
            placeholder=placeholder,
            help=help,
            disabled=disabled,
            on_change=on_change,
            callback_args=callback_args,
            callback_kwargs=callback_kwargs,
            label_visibility=label_visibility,
            width=width,
        )

    if resizable and hasattr(ui, "html"):
        ui.html(_RESIZABLE_TEXT_AREA_CSS)

    search_key = _control_key(field_key, "search")
    replacement_key = _control_key(field_key, "replacement")
    case_sensitive_key = _control_key(field_key, "case_sensitive")
    scope_key = _scope_key(field_key) if resizable else _control_key(field_key, "editor")

    with ui.container(key=scope_key):
        with ui.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            gap="small",
        ):
            if label_visibility == "visible":
                ui.markdown(f"**{label}**")
            with ui.popover(
                "Buscar y reemplazar" if replaceable else "Buscar",
                icon=":material/find_replace:" if replaceable else ":material/search:",
                type="tertiary",
                key=_control_key(field_key, "search_popover"),
            ):
                search = str(ui.text_input("Buscar", key=search_key) or "")
                if replaceable:
                    ui.text_input("Reemplazar por", key=replacement_key)
                case_sensitive = bool(
                    ui.checkbox(
                        "Distinguir mayúsculas y minúsculas",
                        key=case_sensitive_key,
                    )
                )
                match_count = count_literal_matches(
                    str(ui.session_state.get(field_key) or ""),
                    search,
                    case_sensitive=case_sensitive,
                )
                noun = "coincidencia" if match_count == 1 else "coincidencias"
                ui.caption(f"{match_count} {noun}")
                if replaceable:
                    with ui.container(horizontal=True, gap="small"):
                        ui.button(
                            "Reemplazar una",
                            key=_control_key(field_key, "replace_one"),
                            disabled=match_count == 0,
                            help="Reemplaza la primera coincidencia restante desde el inicio.",
                            on_click=_replace_from_session_state,
                            args=(
                                field_key,
                                search_key,
                                replacement_key,
                                case_sensitive_key,
                                False,
                                on_change,
                                callback_args,
                                callback_kwargs,
                            ),
                        )
                        ui.button(
                            "Reemplazar todas",
                            key=_control_key(field_key, "replace_all"),
                            disabled=match_count == 0,
                            on_click=_replace_from_session_state,
                            args=(
                                field_key,
                                search_key,
                                replacement_key,
                                case_sensitive_key,
                                True,
                                on_change,
                                callback_args,
                                callback_kwargs,
                            ),
                        )

        widget_label_visibility = "collapsed" if label_visibility == "visible" else label_visibility
        return _native_text_area(
            ui,
            label,
            key=field_key,
            height=height,
            placeholder=placeholder,
            help=help,
            disabled=disabled,
            on_change=on_change,
            callback_args=callback_args,
            callback_kwargs=callback_kwargs,
            label_visibility=widget_label_visibility,
            width=width,
        )


__all__ = [
    "count_literal_matches",
    "editable_text_area",
    "replace_all_literal",
    "replace_first_literal",
]

"""Coverage for the reusable plain-text editor and its replacement logic."""

# ruff: noqa: D103

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from editor.ui.editable_text import _RESIZABLE_TEXT_AREA_CSS
from editor.ui.editable_text import count_literal_matches
from editor.ui.editable_text import replace_all_literal
from editor.ui.editable_text import replace_first_literal


def test_replace_first_replaces_exactly_one_match() -> None:
    text = "Python Python Python"

    updated = replace_first_literal(text, "Python", "R", case_sensitive=True)

    assert updated == "R Python Python"
    assert count_literal_matches(updated, "Python", case_sensitive=True) == 2


def test_replace_all_replaces_every_match() -> None:
    assert (
        replace_all_literal(
            "Python Python Python",
            "Python",
            "R",
            case_sensitive=True,
        )
        == "R R R"
    )


def test_empty_search_never_changes_text() -> None:
    text = "Python"

    assert count_literal_matches(text, "") == 0
    assert replace_first_literal(text, "", "R") == text
    assert replace_all_literal(text, "", "R") == text


def test_missing_search_reports_zero_and_preserves_text() -> None:
    text = "Python"

    assert count_literal_matches(text, "Rust") == 0
    assert replace_first_literal(text, "Rust", "R") == text
    assert replace_all_literal(text, "Rust", "R") == text


def test_case_sensitive_option_controls_literal_matching() -> None:
    text = "Python python PYTHON"

    assert count_literal_matches(text, "Python", case_sensitive=True) == 1
    assert count_literal_matches(text, "Python", case_sensitive=False) == 3
    assert replace_all_literal(text, "Python", "R", case_sensitive=True) == "R python PYTHON"
    assert replace_all_literal(text, "Python", "R", case_sensitive=False) == "R R R"


def test_special_characters_remain_literal_and_uncorrupted() -> None:
    text = "α β ∫ ∑ ñ á é ¿ ? \\ $ { } α"
    replacement = r"\\$\1{nuevo}"

    updated = replace_all_literal(text, "α", replacement, case_sensitive=True)

    assert updated == rf"{replacement} β ∫ ∑ ñ á é ¿ ? \ $ {{ }} {replacement}"
    assert replace_all_literal(text, r"\ $ { }", "literal", case_sensitive=True) == (
        "α β ∫ ∑ ñ á é ¿ ? literal α"
    )


def test_resize_css_is_vertical_and_scoped_to_helper_textareas() -> None:
    assert "resize: vertical" in _RESIZABLE_TEXT_AREA_CSS
    assert "resize: both" not in _RESIZABLE_TEXT_AREA_CSS
    assert "overflow: auto" in _RESIZABLE_TEXT_AREA_CSS
    assert 'class*="st-key-mm_resizable_text_"' in _RESIZABLE_TEXT_AREA_CSS
    assert "textarea" in _RESIZABLE_TEXT_AREA_CSS


def test_widget_replacements_update_local_string_without_saving() -> None:
    app = AppTest.from_string(
        """
import streamlit as st

from editor.ui.editable_text import editable_text_area

st.session_state.setdefault("save_count", 0)
st.session_state.setdefault("dirty", False)

def mark_dirty():
    st.session_state["dirty"] = True

content = editable_text_area(
    "Contenido",
    key="content",
    height=180,
    on_change=mark_dirty,
)
st.session_state["returned_type"] = type(content).__name__
if st.button("Guardar", key="save"):
    st.session_state["save_count"] += 1
"""
    ).run()

    assert not app.exception
    app.text_area[0].input("Python Python Python").run()
    next(item for item in app.text_input if item.label == "Buscar").input("Python")
    next(item for item in app.text_input if item.label == "Reemplazar por").input("R")
    app.run()

    next(item for item in app.button if item.label == "Reemplazar una").click().run()
    assert not app.exception
    assert app.session_state["content"] == "R Python Python"
    assert app.session_state["save_count"] == 0
    assert app.session_state["dirty"] is True
    assert app.session_state["returned_type"] == "str"

    next(item for item in app.button if item.label == "Reemplazar todas").click().run()
    assert not app.exception
    assert app.session_state["content"] == "R R R"
    assert app.session_state["save_count"] == 0


def test_widget_auxiliary_keys_are_isolated_between_fields() -> None:
    app = AppTest.from_string(
        """
from editor.ui.editable_text import editable_text_area

editable_text_area("Primero", "Python", key="first_content")
editable_text_area("Segundo", "Python", key="second_content")
"""
    ).run()

    assert not app.exception
    input_keys = {item.key for item in app.text_input}
    assert input_keys == {
        "first_content__search",
        "first_content__replacement",
        "second_content__search",
        "second_content__replacement",
    }

    next(item for item in app.text_input if item.key == "first_content__search").input("Python")
    next(item for item in app.text_input if item.key == "first_content__replacement").input("R")
    app.run()
    next(item for item in app.button if item.key == "first_content__replace_all").click().run()

    assert app.session_state["first_content"] == "R"
    assert app.session_state["second_content"] == "Python"

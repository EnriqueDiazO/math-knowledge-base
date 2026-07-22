"""Regression coverage for Cornell/CPI on the declared Streamlit range."""

# ruff: noqa: D103

from __future__ import annotations

from streamlit.testing.v1 import AppTest

_APP_TEMPLATE = """
from editor.{note_type}.streamlit_page import render_{note_type}_page

class FakeDb:
    name = "streamlit-compat-test"

    def get_notebook_projects(self):
        return []

    def get_notebook_contexts(self):
        return []

render_{note_type}_page(FakeDb())
"""


def _button(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def test_cornell_editor_opens_and_page_reruns_do_not_raise() -> None:
    app = AppTest.from_string(_APP_TEMPLATE.format(note_type="cornell")).run()

    assert not app.exception
    for label in ("Añadir", "Anterior", "Siguiente", "Duplicar", "Eliminar"):
        _button(app, label).click().run()
        assert not app.exception


def test_cpi_editor_opens_and_page_reruns_do_not_raise() -> None:
    app = AppTest.from_string(_APP_TEMPLATE.format(note_type="cpi")).run()

    assert not app.exception
    for label in ("Añadir", "Anterior", "Siguiente", "Duplicar", "Eliminar"):
        _button(app, label).click().run()
        assert not app.exception

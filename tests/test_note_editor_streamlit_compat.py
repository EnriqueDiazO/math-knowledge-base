"""Regression coverage for Cornell/CPI on the declared Streamlit range."""

# ruff: noqa: D103

from __future__ import annotations

from streamlit.testing.v1 import AppTest

_APP_TEMPLATE = """
from types import SimpleNamespace

from editor.{note_type}.streamlit_page import render_{note_type}_page

class FakeDb:
    name = "streamlit-compat-test"

    def get_notebook_projects(self):
        return []

    def get_notebook_contexts(self):
        return []

    def create_notebook_note(self, note):
        self.note = note
        return SimpleNamespace(inserted_id="created-note")

    def get_notebook_note_by_id(self, note_id):
        return getattr(self, "note", None)

    def update_notebook_note(self, note_id, note):
        self.note = note
        return SimpleNamespace(matched_count=1)

render_{note_type}_page(FakeDb())
"""


def _button(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def _assert_no_duplicate_widget_default_warning(app: AppTest) -> None:
    warnings = [str(item.value) for item in app.warning]
    assert not any("created with a default value" in warning for warning in warnings)


def test_cornell_editor_opens_and_page_reruns_do_not_raise() -> None:
    app = AppTest.from_string(_APP_TEMPLATE.format(note_type="cornell")).run()

    assert not app.exception
    _assert_no_duplicate_widget_default_warning(app)
    for label in ("Añadir", "Anterior", "Siguiente", "Duplicar", "Eliminar"):
        _button(app, label).click().run()
        assert not app.exception
        _assert_no_duplicate_widget_default_warning(app)


def test_cpi_editor_opens_and_page_reruns_do_not_raise() -> None:
    app = AppTest.from_string(_APP_TEMPLATE.format(note_type="cpi")).run()

    assert not app.exception
    _assert_no_duplicate_widget_default_warning(app)
    for label in ("Añadir", "Anterior", "Siguiente", "Duplicar", "Eliminar"):
        _button(app, label).click().run()
        assert not app.exception
        _assert_no_duplicate_widget_default_warning(app)


def test_save_does_not_remove_branding_widget_state_mid_run() -> None:
    for note_type in ("cornell", "cpi"):
        app = AppTest.from_string(_APP_TEMPLATE.format(note_type=note_type)).run()

        _button(app, "Guardar").click().run()

        assert not app.exception
        _assert_no_duplicate_widget_default_warning(app)

"""Real Streamlit form-cycle coverage for explicit catalog initialization."""

from __future__ import annotations

import textwrap
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_catalog_index_form_submits_invalid_zero_and_valid_once(tmp_path: Path) -> None:
    """Exercise the real form protocol without MongoDB or the monolithic app."""
    app_file = tmp_path / "catalog_status_app.py"
    app_file.write_text(
        textwrap.dedent(
            """
            from types import SimpleNamespace

            import streamlit as st

            from editor.source_catalog.shared import render_catalog_status
            from mathmongo.source_catalog.indexes import IndexPlan
            from mathmongo.source_catalog.indexes import IndexSpec
            from mathmongo.source_catalog.indexes import IndexState
            from mathmongo.source_catalog.indexes import IndexStatus


            DATABASE_NAME = "isolated_streamlit_form_test"
            READY_KEY = "fake_catalog_ready"
            APPLY_COUNT_KEY = "fake_catalog_apply_count"


            class FakeDatabase:
                name = DATABASE_NAME

                def list_collection_names(self):
                    return []


            class FakeIndexManager:
                spec = IndexSpec(
                    "sources",
                    "sources_streamlit_form_test",
                    (("source_id", 1),),
                    True,
                )

                def status(self):
                    state = (
                        IndexState.PRESENT
                        if st.session_state.get(READY_KEY, False)
                        else IndexState.MISSING
                    )
                    return (IndexStatus(self.spec, state),)

                def plan(self):
                    return IndexPlan(self.status())

                def apply(self):
                    st.session_state[APPLY_COUNT_KEY] = (
                        st.session_state.get(APPLY_COUNT_KEY, 0) + 1
                    )
                    st.session_state[READY_KEY] = True
                    return self.plan()


            context = SimpleNamespace(
                connection_label="Fake isolated connection",
                database_name=DATABASE_NAME,
                database=FakeDatabase(),
                index_manager=FakeIndexManager(),
            )
            render_catalog_status(st, context)
            st.metric("Fake apply count", st.session_state.get(APPLY_COUNT_KEY, 0))
            """
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file)).run()
    submit = next(button for button in app.button if button.label == "Initialize catalog indexes")
    assert submit.disabled is False
    assert app.metric[0].value == "0"

    submit.click()
    app.run()

    assert app.metric[0].value == "0"
    assert any("Initialization was not executed" in item.value for item in app.warning)

    confirmation_text = next(
        item
        for item in app.text_input
        if item.label == "Escribe el nombre real de la base para confirmar"
    )
    confirmation_checkbox = next(
        item
        for item in app.checkbox
        if item.label.startswith("Confirmo aplicar el plan exclusivamente")
    )
    submit = next(button for button in app.button if button.label == "Initialize catalog indexes")
    confirmation_text.input("isolated_streamlit_form_test")
    confirmation_checkbox.check()
    submit.click()
    app.run()

    assert app.metric[0].value == "1"
    assert any("Índices del catálogo verificados" in item.value for item in app.success)

    app.run()

    assert app.metric[0].value == "1"
    submit = next(button for button in app.button if button.label == "Initialize catalog indexes")
    assert submit.disabled is True

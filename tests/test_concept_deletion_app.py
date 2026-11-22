"""Actual confirmation/rerun behavior using the shared deletion UI and owned DB."""

from pathlib import Path

from pymongo.errors import AutoReconnect
from streamlit.testing.v1 import AppTest

from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def _app(service, tmp_path: Path):
    first = service.execute(create(service))["key"]
    other = service.execute(create(service, titulo="Otro concepto"))["key"]
    first_doc = service.find(first)
    host, port = service.db.client.address
    script = tmp_path / "deletion.py"
    script.write_text(
        """import streamlit as st
from pymongo import MongoClient
from editor.ui.concept_deletion import render_concept_deletion, render_deletion_feedback
if 'database' not in st.session_state:
    st.session_state.database=MongoClient("""
        + repr(f"mongodb://{host}:{port}")
        + """)["""
        + repr(service.db.name)
        + """]
db=st.session_state.database
render_deletion_feedback(st,db)
concepts=list(db.concepts.find({}).sort('titulo',1))
if concepts:
    choices={str(item['_id']):item for item in concepts}
    selected=st.selectbox('Concepto',list(choices),format_func=lambda value:choices[value]['titulo'])
    render_concept_deletion(st,db,choices[selected],scope='isolated')
"""
    )
    return AppTest.from_file(str(script)).run(timeout=20), first_doc, service.find(other)


def test_confirmation_is_bound_to_the_selected_concept_not_a_global_armed_flag(service, tmp_path):
    app, first, other = _app(service, tmp_path)
    assert not app.exception
    app.button[0].click().run()
    assert any(button.label == "Confirmar eliminación" for button in app.button)
    app.selectbox[0].select(str(other["_id"])).run()
    assert not any(button.label == "Confirmar eliminación" for button in app.button)
    assert service.db.concepts.count_documents({}) == 2
    app.selectbox[0].select(str(first["_id"])).run()
    app.text_input[0].input(first["titulo"]).run()
    next(button for button in app.button if button.label == "Confirmar eliminación").click().run()
    assert not app.exception
    assert service.db.concepts.find_one({"_id": first["_id"]}) is None
    assert service.db.concepts.find_one({"_id": other["_id"]}) == other
    assert any("Concepto eliminado" in message.value for message in app.success)


def test_partial_recovery_remains_available_after_the_concept_row_disappeared(
    service, tmp_path, monkeypatch
):
    app, first, other = _app(service, tmp_path)
    app.button[0].click().run()
    app.text_input[0].input(first["titulo"]).run()
    collection_type = type(service.db.media_assets)
    original = collection_type.update_many

    def interrupted(collection, *args, **kwargs):
        if collection.name == "media_assets":
            raise AutoReconnect("Lost acknowledgement")
        return original(collection, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(collection_type, "update_many", interrupted)
        next(
            button for button in app.button if button.label == "Confirmar eliminación"
        ).click().run()
    assert service.db.concepts.find_one({"_id": first["_id"]}) is None
    assert not any("Concepto eliminado" in message.value for message in app.success)
    app.run()
    retry = next(
        button for button in app.button if button.label.startswith("Reintentar eliminación")
    )
    retry.click().run()
    assert not app.exception
    assert any("Concepto eliminado" in message.value for message in app.success)
    assert service.db.concepts.find_one({"_id": other["_id"]}) == other

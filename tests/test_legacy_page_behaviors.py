"""Behavioral contracts retained during migration, on an owned MongoDB library.

AppTest cannot drive ACE's JS transport. Only that widget port is replaced with
a native textarea; page logic, canonical services, MongoDB and reruns are real.
"""

import json
from datetime import datetime

import streamlit as st
from streamlit.testing.v1 import AppTest

from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def app_for(service, tmp_path, monkeypatch, page, section=None):
    """Use cached real context and private file roots, even in a direct pytest run."""
    for kind in ("DATA", "STATE", "CONFIG", "CACHE"):
        monkeypatch.setenv("XDG_" + kind + "_HOME", str(tmp_path / kind.lower()))
    if page in {"concept_create", "concept_edit"}:
        from importlib import import_module

        module = import_module("editor.app_pages." + page)

        def ace(value="", key=None, **_kwargs):
            return st.text_area("LaTeX de prueba", value=value, key=key)

        monkeypatch.setattr(module, "st_ace", ace)
    from editor import graph_page_helpers
    from visualizations import grafoconocimiento

    if hasattr(graph_page_helpers, "GRAPH_RUNTIME_DIR"):
        monkeypatch.setattr(graph_page_helpers, "GRAPH_RUNTIME_DIR", tmp_path / "graphs")
    if hasattr(grafoconocimiento, "GRAPH_RUNTIME_DIR"):
        monkeypatch.setattr(grafoconocimiento, "GRAPH_RUNTIME_DIR", tmp_path / "graphs")
    host, port = service.db.client.address
    script = tmp_path / (page + ".py")
    script.write_text(
        """import streamlit as st
from mathdatabase.mathmongo import MathMongo
from editor.application_context import PageContext
from editor.source_catalog.shared import build_catalog_context
from editor.database_scope import database_scope_token,sync_knowledge_graph_scope
from editor.app_pages."""
        + page
        + """ import render
if 'context' not in st.session_state:
    connection=MathMongo("""
        + repr(f"mongodb://{host}:{port}")
        + ""","""
        + repr(service.db.name)
        + """)
    scope=database_scope_token('Prueba aislada',connection.db.name)
    st.session_state.context=PageContext(db=connection,current_db='Prueba aislada',current_database_label=connection.db.name,
        catalog_context=build_catalog_context('Prueba aislada',connection),active_database_scope=scope,active_database_name=connection.db.name)
    sync_knowledge_graph_scope(st.session_state,scope)
"""
        + (
            "    st.session_state.knowledge_graph_section_request=" + repr(section) + "\n"
            if section
            else ""
        )
        + """
render(st.session_state.context)
"""
    )
    return AppTest.from_file(str(script)).run(timeout=30)


def input_named(app, label, value):
    """Change an actual widget without relying on its position in a large page."""
    next(widget for widget in app.text_input if widget.label == label).input(value)


def test_advanced_create_saves_managed_identity_and_duplicate_does_not_erase_it(
    service, tmp_path, monkeypatch
):
    """Verify advanced create saves managed identity and duplicate does not erase it."""
    app = app_for(service, tmp_path, monkeypatch, "concept_create")
    assert not app.exception
    next(widget for widget in app.selectbox if widget.label == "Source").select(
        service.test_source_id
    ).run()
    input_named(app, "ID", "definicion:legacy-behavior")
    input_named(app, "Title (Optional)", "Concepto del formulario conservado")
    next(widget for widget in app.text_area if widget.label == "LaTeX de prueba").input(
        r"Sea $G$ un grupo."
    ).run()
    next(widget for widget in app.button if widget.label == "💾 Save Concept").click().run(
        timeout=30
    )
    assert not app.exception
    stored = service.db.concepts.find_one({"id": "definicion:legacy-behavior"})
    assert stored is not None and stored["source_id"] == service.test_source_id
    identity = {"id": stored["id"], "source": stored["source"]}
    latex = service.db.latex_documents.find_one(identity)
    assert latex["contenido_latex"] == r"Sea $G$ un grupo."
    next(widget for widget in app.button if widget.label == "💾 Save Concept").click().run(
        timeout=30
    )
    assert service.db.concepts.find_one(identity) == stored
    assert service.db.latex_documents.find_one(identity) == latex
    assert app.error
    app.session_state.context.db.client.close()


def test_advanced_edit_keeps_identity_unknown_metadata_and_original_source(
    service, tmp_path, monkeypatch
):
    """Verify advanced edit keeps identity unknown metadata and original source."""
    key = service.execute(create(service))["key"]
    before = service.find(key)
    service.db.concepts.update_one(
        {"_id": before["_id"]}, {"$set": {"unknown_contract": ["retain"]}}
    )
    app = app_for(service, tmp_path, monkeypatch, "concept_edit")
    assert not app.exception
    input_named(app, "Title", "Nombre editado sin mover el concepto")
    next(widget for widget in app.text_area if widget.label == "LaTeX de prueba").input(
        r"Nuevo cuerpo $G\times G$."
    ).run()
    next(widget for widget in app.button if widget.label == "💾 Update Concept").click().run(
        timeout=30
    )
    assert not app.exception
    after = service.db.concepts.find_one({"_id": before["_id"]})
    assert after["titulo"] == "Nombre editado sin mover el concepto"
    assert (
        after["id"] == before["id"]
        and after["source"] == before["source"]
        and after["source_id"] == before["source_id"]
    )
    assert after["unknown_contract"] == ["retain"]
    assert service.latex(after)["contenido_latex"] == r"Nuevo cuerpo $G\times G$."
    assert any("actualizado correctamente" in message.value for message in app.success)
    app.session_state.context.db.client.close()


def test_saved_map_duplicate_does_not_duplicate_canonical_concepts(service, tmp_path, monkeypatch):
    """Verify saved map duplicate does not duplicate canonical concepts."""
    key = service.execute(create(service))["key"]
    original = {
        "name": "Mapa conservado",
        "description": "Una vista, sin copias semánticas",
        "graph_state": {
            "nodes": [
                {"id": key, "label": "Grupo", "tipo": "definicion", "source": "Álgebra de prueba"}
            ],
            "edges": [],
        },
        "filters": {
            "sources": ["Álgebra de prueba"],
            "concept_types": ["definicion"],
            "relation_types": [],
        },
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "unknown_view_field": "retain",
    }
    service.db.knowledge_graph_maps.insert_one(original)
    app = app_for(service, tmp_path, monkeypatch, "knowledge_graph", section="📚 Mapas guardados")
    assert not app.exception
    next(widget for widget in app.button if widget.label == "Duplicar").click().run(timeout=30)
    assert not app.exception
    copies = list(service.db.knowledge_graph_maps.find({}))
    assert len(copies) == 2
    assert service.db.concepts.count_documents({}) == 1
    assert copies[0]["graph_state"] == copies[1]["graph_state"]
    assert copies[0]["name"] != copies[1]["name"]
    app.session_state.context.db.client.close()


def map_document(service):
    """Persist a complete legacy view with independent semantic records."""
    first = service.execute(create(service))["key"]
    other = service.execute(create(service, titulo="Otra idea"))["key"]
    service.execute(
        {
            "operation_id": __import__("uuid").uuid4().__str__(),
            "action": "connect",
            "key": first,
            "target": other,
        }
    )
    state = {
        "nodes": [
            {
                "id": key,
                "concept_id": service.find(key)["id"],
                "label": service.find(key)["titulo"],
                "type": "definicion",
                "tipo": "definicion",
                "source": "Álgebra de prueba",
            }
            for key in (first, other)
        ],
        "edges": [
            {"from": first, "to": other, "label": "requiere_concepto", "tipo": "requiere_concepto"}
        ],
    }
    document = {
        "name": "Mapa conservado",
        "description": "Descripción original",
        "graph_state": state,
        "filters": {
            "sources": ["Álgebra de prueba"],
            "concept_types": ["definicion"],
            "relation_types": ["requiere_concepto"],
            "max_depth": 3,
        },
        "tags": ["estudio"],
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "unknown_view_field": "retain",
    }
    service.db.knowledge_graph_maps.insert_one(document)
    return document


def test_edit_saved_map_preserves_unknown_fields_and_semantic_records(
    service, tmp_path, monkeypatch
):
    """Verify edit saved map preserves unknown fields and semantic records."""
    before = map_document(service)
    app = app_for(service, tmp_path, monkeypatch, "knowledge_graph", section="✏️ Editar mapa")
    assert not app.exception
    input_named(app, "Nombre del mapa", "Nombre nuevo de la misma vista")
    next(widget for widget in app.button if widget.label == "💾 Guardar mapa").click().run(
        timeout=30
    )
    assert not app.exception
    after = service.db.knowledge_graph_maps.find_one({"_id": before["_id"]})
    assert after["name"] == "Nombre nuevo de la misma vista"
    assert after["unknown_view_field"] == "retain"
    assert {node["id"] for node in after["graph_state"]["nodes"]} == {
        node["id"] for node in before["graph_state"]["nodes"]
    }
    assert (
        service.db.concepts.count_documents({}) == 2
        and service.db.relations.count_documents({}) == 1
    )
    app.session_state.context.db.client.close()


def test_generated_map_can_be_saved_without_copying_concepts(service, tmp_path, monkeypatch):
    """Verify generated map can be saved without copying concepts."""
    before = map_document(service)
    service.db.knowledge_graph_maps.delete_one({"_id": before["_id"]})
    app = app_for(service, tmp_path, monkeypatch, "knowledge_graph", section="📊 Nuevo mapa")
    assert not app.exception
    next(widget for widget in app.button if widget.label == "🔍 Generate Graph").click().run(
        timeout=30
    )
    assert not app.exception
    # The compatibility renderer exports JSON through its clipboard control.
    # AppTest cannot run that iframe: supply the same documented user input.
    next(
        widget for widget in app.text_area if widget.label == "Estado JSON actual del grafo"
    ).input(json.dumps(before["graph_state"]))
    input_named(app, "Nombre del mapa", "Vista generada")
    next(widget for widget in app.button if widget.label == "💾 Guardar mapa generado").click().run(
        timeout=30
    )
    assert not app.exception
    stored = service.db.knowledge_graph_maps.find_one({"name": "Vista generada"})
    assert stored is not None, (
        [message.value for message in app.error],
        [message.value for message in app.warning],
    )
    assert len(stored["graph_state"]["nodes"]) == 2
    assert service.db.concepts.count_documents({}) == 2
    app.session_state.context.db.client.close()


def test_import_map_validates_endpoints_then_preserves_original_state(
    service, tmp_path, monkeypatch
):
    """Verify import map validates endpoints then preserves original state."""
    before = map_document(service)
    app = app_for(
        service, tmp_path, monkeypatch, "knowledge_graph", section="📤 Exportar / importar"
    )
    assert not app.exception
    invalid = {
        "nodes": before["graph_state"]["nodes"],
        "edges": [{"from": "missing", "to": "also-missing"}],
    }
    next(widget for widget in app.text_area if widget.label == "Estado JSON").input(
        json.dumps(invalid)
    )
    input_named(app, "Nombre del mapa importado", "Estado importado")
    next(widget for widget in app.button if widget.label == "📥 Importar estado JSON").click().run(
        timeout=30
    )
    assert not app.exception
    assert service.db.knowledge_graph_maps.count_documents({"name": "Estado importado"}) == 0
    next(widget for widget in app.text_area if widget.label == "Estado JSON").input(
        json.dumps(before["graph_state"])
    )
    input_named(app, "Nombre del mapa importado", "Estado importado")
    next(widget for widget in app.button if widget.label == "📥 Importar estado JSON").click().run(
        timeout=30
    )
    assert not app.exception
    imported = service.db.knowledge_graph_maps.find_one({"name": "Estado importado"})
    assert imported is not None, (
        [message.value for message in app.error],
        [message.value for message in app.warning],
    )
    assert imported["graph_state"] == before["graph_state"]
    assert (
        service.db.concepts.count_documents({}) == 2
        and service.db.relations.count_documents({}) == 1
    )
    app.session_state.context.db.client.close()

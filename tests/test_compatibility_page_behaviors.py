"""Behavioral checks for retained pages against owned MongoDB, never a user's library."""

import json
from importlib import import_module
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from editor.application_context import PageContext
from mathdatabase.mathmongo import MathMongo
from mathmongo.source_catalog.models import Source
from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def run_page(context, slug):
    """AppTest executes real selected-page rendering with an explicit test context."""
    from importlib import import_module

    import_module("editor.app_pages." + slug).render(context)


@pytest.fixture
def pages(service, monkeypatch, tmp_path):
    """Bind real Mongo and temporary filesystem roots without an initializing constructor."""
    for kind in ("CONFIG", "DATA", "CACHE", "STATE"):
        monkeypatch.setenv(f"XDG_{kind}_HOME", str(tmp_path / kind.lower()))
    second = Source(name="Otra fuente temporal")
    service.db.sources.insert_one(second.model_dump(mode="python"))
    first_key = service.execute(create(service, titulo="Concepto A", categorias=["álgebra"]))["key"]
    second_key = service.execute(
        create(
            service,
            titulo="Concepto B",
            source_id=second.source_id,
            tipo="teorema",
            categorias=["lógica"],
        )
    )["key"]
    first, other = service.find(first_key), service.find(second_key)
    mongo = MathMongo.from_database(service.db)
    relation = mongo.add_relation(
        desde_id=first["id"],
        desde_source=first["source"],
        hasta_id=other["id"],
        hasta_source=other["source"],
        tipo="requiere_concepto",
        descripcion="Conservar",
    )
    assert relation is not None
    context = PageContext(
        db=mongo,
        current_db=service.db.name,
        current_database_label=service.db.name,
        active_database_scope=service.db.name,
        active_database_name=service.db.name,
        active_theme="dark",
    )

    def opening(slug, **state):
        app = AppTest.from_function(run_page, args=(context, slug), default_timeout=25)
        for key, value in state.items():
            app.session_state[key] = value
        return app.run()

    return opening, mongo, first, other


def test_home_statistics_and_source_filter_are_read_only(pages):
    """Counters, chart data and source filtering reflect real records without rewriting them."""
    opening, mongo, first, other = pages
    before = list(mongo.concepts.find())
    app = opening("home")
    assert not app.exception
    assert [metric.value for metric in app.metric[:3]] == ["2", "1", "2"]
    assert any("Concepto A" in item.value for item in app.markdown)
    app.toggle(key="qs_all_sources").set_value(False).run()
    app.multiselect(key="qs_selected_sources").set_value([first["source"]]).run()
    assert not app.exception
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert figure["data"][0]["x"] == ["definicion"]
    assert list(mongo.concepts.find()) == before
    assert mongo.relations.count_documents({}) == 1


def test_home_empty_library_has_zero_counters_and_no_fabricated_recent_documents(pages):
    """An empty prepared library remains readable without inserting placeholders."""
    opening, mongo, _first, _other = pages
    mongo.concepts.delete_many({})
    mongo.relations.delete_many({})
    app = opening("home")
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["0", "0", "0", "0"]
    assert any("Aún no hay conceptos" in item.value for item in app.info)
    assert mongo.concepts.count_documents({}) == 0


def test_relation_creation_rejects_self_link_then_persists_direction_and_description(pages):
    """The retained relation workflow changes only its explicit endpoint/type selection."""
    opening, mongo, first, other = pages
    app = opening("relations")
    assert not app.exception
    app.button(key="add_rel_btn").click().run()
    assert mongo.relations.count_documents({}) == 1
    assert any("itself" in message.value for message in app.error)
    options = app.selectbox(key="hasta_select").options
    different = (
        next(label for label in options if "Concepto A" in label)
        if "Concepto B" in app.selectbox(key="desde_select").value
        else next(label for label in options if "Concepto B" in label)
    )
    app.selectbox(key="hasta_select").select(different)
    app.selectbox(key="new_rel_type").select("implica")
    app.text_area(key="new_rel_desc").set_value("Justificación explícita")
    app.button(key="add_rel_btn").click().run()
    assert not app.exception
    stored = mongo.relations.find_one({"tipo": "implica"})
    assert stored and stored["descripcion"] == "Justificación explícita"
    assert stored["desde"] != stored["hasta"]
    assert mongo.relations.count_documents({}) == 2


def test_relation_delete_confirmation_cannot_move_to_a_filtered_row(pages):
    """Changing the type filter may not transfer an armed deletion to a different relation."""
    opening, mongo, first, other = pages
    mongo.add_relation(
        desde_id=first["id"],
        desde_source=first["source"],
        hasta_id=other["id"],
        hasta_source=other["source"],
        tipo="implica",
        descripcion="No borrar",
    )
    app = opening("relations")
    first_delete = next(button for button in app.button if button.label == "🗑️ Delete")
    first_delete.click().run()
    assert any(button.label == "❌ Confirm Delete" for button in app.button)
    app.selectbox(key="edit_type_filter").select("implica").run()
    assert not app.exception
    assert not any(button.label == "❌ Confirm Delete" for button in app.button)
    assert mongo.relations.count_documents({}) == 2


def test_relation_update_and_explicit_delete_keep_concepts_and_latex(pages):
    """A confirmed relation edit/delete changes only that relation, retaining its endpoints."""
    opening, mongo, _first, _other = pages
    before_concepts = list(mongo.concepts.find())
    before_latex = list(mongo.latex_documents.find())
    original = mongo.relations.find_one({})
    app = opening("relations")
    editor = next(item for item in app.text_area if item.label == "Description")
    editor.set_value("Descripción corregida")
    next(button for button in app.button if button.label == "💾 Update Relation").click().run()
    assert not app.exception
    assert mongo.relations.find_one({"_id": original["_id"]})["descripcion"] == "Descripción corregida"
    next(button for button in app.button if button.label == "🗑️ Delete").click().run()
    assert mongo.relations.count_documents({}) == 1
    next(button for button in app.button if button.label == "❌ Confirm Delete").click().run()
    assert not app.exception and mongo.relations.count_documents({}) == 0
    assert list(mongo.concepts.find()) == before_concepts
    assert list(mongo.latex_documents.find()) == before_latex


def test_legacy_bulk_export_uses_the_selected_database(pages, monkeypatch, tmp_path):
    """The bulk adapter must pass a Database, not a client's unrelated namespace."""
    opening, mongo, first, _other = pages
    module = import_module("editor.app_pages.export")
    monkeypatch.setattr(module, "get_exports_dir", lambda **_kw: tmp_path)
    observed = []
    canonical = module.ExportadorLatex.exportar_todos_de_source

    def export(exporter, database, source, salida=None):
        assert database.name == mongo.db.name
        # Keep the canonical query and per-concept rendering; bypass only TeX execution here.
        observed.append(source)
        return canonical(exporter, database, source, salida)

    monkeypatch.setattr(module.ExportadorLatex, "exportar_todos_de_source", export)

    def write(exporter, concept, body, salida=None, **_options):
        assert body and concept["source"] in {first["source"], "Otra fuente temporal"}
        target = Path(salida)
        target.mkdir(parents=True, exist_ok=True)
        (target / (concept["titulo"] + ".tex")).write_text(body)

    monkeypatch.setattr(module.ExportadorLatex, "exportar_concepto", write)
    app = opening("export")
    next(button for button in app.button if button.label == "🔄 Export All Sources").click().run()
    assert not app.exception
    assert not app.error
    assert set(observed) == {first["source"], "Otra fuente temporal"}
    assert len(list(tmp_path.rglob("*.tex"))) == 2
    assert mongo.concepts.count_documents({}) == 2


def test_map_generation_save_duplicate_and_filtered_navigation_preserve_concepts(pages):
    """Retained saved maps preserve their graph state and never replace source concepts."""
    from editor.graph_page_helpers import _build_knowledge_graph_state_from_filters

    opening, mongo, first, other = pages
    concepts = list(mongo.concepts.find())
    app = opening("knowledge_graph", knowledge_graph_section="📊 Nuevo mapa")
    assert not app.exception
    app.radio(key="knowledge_graph_section").set_value("📊 Nuevo mapa").run()
    app.button(key="kg_generate_graph").click().run()
    assert app.session_state["knowledge_graph_new_stats"]["nodes"] == 2
    assert app.session_state["knowledge_graph_new_stats"]["edges"] == 1
    graph = _build_knowledge_graph_state_from_filters(
        mongo, [first["source"], other["source"]], ["requiere_concepto"], []
    )
    app.text_input(key="kg_new_map_name").set_value("Mapa comprobable")
    app.text_area(key="kg_new_graph_state_json").set_value(json.dumps(graph, ensure_ascii=False))
    next(
        button for button in app.button if button.label == "💾 Guardar mapa generado"
    ).click().run()
    assert not app.exception and not app.error
    saved = mongo.db.knowledge_graph_maps.find_one({})
    assert saved["name"] == "Mapa comprobable" and saved["graph_state"] == graph
    app.radio(key="knowledge_graph_section").set_value("📚 Mapas guardados").run()
    app.button(key="kg_duplicate_map").click().run()
    assert mongo.db.knowledge_graph_maps.count_documents({}) == 2
    app.run()
    app.button(key="kg_view_map").click().run()
    assert not app.exception and not app.error
    assert next(metric for metric in app.metric if metric.label == "Nodos").value == "2"
    app.text_input(key="kg_maps_search").set_value("No existe este mapa").run()
    assert any("No hay mapas que coincidan" in item.value for item in app.info)
    assert mongo.db.knowledge_graph_maps.count_documents({}) == 2
    assert list(mongo.concepts.find()) == concepts


def test_maintenance_requires_confirmation_and_backs_up_only_owned_temporary_files(
    pages, monkeypatch, tmp_path
):
    """The existing cleanup activity previews and backs up files without touching notes or source."""
    from editor import maintenance_page as page
    from editor.utils import cleanup_exports as cleanup

    opening, mongo, _first, _other = pages
    exports = tmp_path / "exports"
    exports.mkdir()
    protected = exports / "source.tex"
    protected.write_text("LaTeX conservado")
    temporary = exports / "owned.aux"
    temporary.write_bytes(b"temporary compilation data")
    outside = tmp_path / "outside.txt"
    outside.write_text("No tocar")
    backup = tmp_path / "backups"
    log = tmp_path / "cleanup.log"
    for module in (page, cleanup):
        monkeypatch.setattr(module, "EXPORT_CLEANUP_DIRS", (exports,))
        monkeypatch.setattr(module, "CLEANUP_BACKUP_DIR", backup)
        monkeypatch.setattr(module, "CLEANUP_LOG_FILE", log)
    monkeypatch.setattr(page, "GRAPH_CLEANUP_DIRS", ())
    monkeypatch.setattr(page, "find_legacy_root_graph_files", lambda: [])
    monkeypatch.setattr(cleanup, "ALLOWED_CLEANUP_DIRS", (exports,))
    before = list(mongo.concepts.find())
    app = opening("maintenance")
    app.button(key="cleanup_scan_dirs").click().run()
    assert not app.exception
    app.button(key="cleanup_delete_temp").click().run()
    assert temporary.exists() and any("confirmación" in item.value for item in app.error)
    app.checkbox(key="cleanup_confirm_temp").set_value(True)
    app.button(key="cleanup_delete_temp").click().run()
    assert not app.exception and not app.error
    assert not temporary.exists() and any(
        p.read_bytes() == b"temporary compilation data" for p in backup.rglob("owned.aux")
    )
    assert protected.read_text() == "LaTeX conservado" and outside.read_text() == "No tocar"
    assert list(mongo.concepts.find()) == before


def test_concept_browsing_filters_and_empty_export_selection_are_read_only(pages):
    """Browsing and requesting export without a selection cannot remove or edit concepts."""
    opening, mongo, first, _other = pages
    before = list(mongo.concepts.find())
    app = opening("concepts")
    assert not app.exception
    selector = next(item for item in app.selectbox if item.label == "Source")
    selector.select(first["source"]).run()
    assert any("Results (1 concepts)" in item.value for item in app.subheader)
    next(
        button for button in app.button if button.label == "🚀 Export selected concepts to Quarto"
    ).click().run()
    assert any("select at least one concept" in item.value for item in app.warning)
    assert list(mongo.concepts.find()) == before

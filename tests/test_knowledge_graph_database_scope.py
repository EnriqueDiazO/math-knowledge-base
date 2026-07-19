"""Database-scope regressions for Knowledge Graph and saved maps."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path

from editor.database_scope import KNOWLEDGE_GRAPH_LOADED_MAP_KEY
from editor.database_scope import KNOWLEDGE_GRAPH_SCOPE_KEY
from editor.database_scope import database_scope_token
from editor.database_scope import knowledge_map_is_loaded
from editor.database_scope import knowledge_map_session_identity
from editor.database_scope import mark_knowledge_map_loaded
from editor.database_scope import sync_knowledge_graph_scope

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = ROOT / "editor" / "editor_streamlit.py"


class _WriteSpyCollection:
    def __init__(self) -> None:
        self.writes: list[tuple[str, object]] = []

    def insert_one(self, document):
        self.writes.append(("insert_one", document))

    def update_one(self, query, update):
        self.writes.append(("update_one", (query, update)))

    def delete_one(self, query):
        self.writes.append(("delete_one", query))


def _graph_state(scope: str) -> dict[str, object]:
    return {
        KNOWLEDGE_GRAPH_SCOPE_KEY: scope,
        KNOWLEDGE_GRAPH_LOADED_MAP_KEY: "old-map-identity",
        "knowledge_graph_section": "✏️ Editar mapa",
        "knowledge_graph_section_request": "✏️ Editar mapa",
        "knowledge_graph_active_mode": "edit",
        "knowledge_graph_active_map_id": "same-object-id",
        "knowledge_graph_editing_map_id": "same-object-id",
        "knowledge_graph_edit_graph_state": {
            "nodes": [{"id": "X@S", "x": 10, "y": 20}],
            "edges": [{"from": "X@S", "to": "Y@S"}],
        },
        "knowledge_graph_edit_sync_settings": {"auto_sync": True},
        "knowledge_graph_edit_dirty": True,
        "knowledge_graph_render_version": 7,
        "knowledge_graph_remove_pending": {"node_ids": ["X@S"]},
        "knowledge_graph_new_html": "<html>A</html>",
        "knowledge_graph_new_stats": {"nodes": 99, "edges": 88},
        "knowledge_graph_message": ("success", "saved in A"),
        "knowledge_graph_repair_state": {"pending": True},
        "knowledge_graph_save_state": {"pending": True},
        "knowledge_graph_preview": "preview A",
        "knowledge_graph_export": "export A",
        "kg_new_sources": ["S"],
        "kg_new_concept_types": ["teorema"],
        "kg_new_relation_types": ["implica"],
        "kg_new_max_depth": 5,
        "kg_new_graph_state_json": '{"nodes": [{"id": "X@S"}]}',
        "kg_edit_form_state_same-object-id": {"name": "A"},
        "kg_edit_name_widget_same-object-id": "A",
        "kg_edit_graph_state_json_widget_same-object-id": "positions from A",
        "kg_show_edit_state_json_same-object-id": True,
        "kg_saved_selected_map": "Map A",
        "kg_export_selected_map": "Map A",
        "kg_import_state_json": "state A",
        "document_builder_items": ["unrelated@builder"],
        "unrelated_state": "preserved",
    }


def test_switch_clears_all_graph_map_form_preview_and_widget_state() -> None:
    scope_a = database_scope_token("connection-a", "database-a")
    scope_b = database_scope_token("connection-b", "database-b")
    state = _graph_state(scope_a)

    changed = sync_knowledge_graph_scope(state, scope_b)

    assert changed is True
    assert state == {
        KNOWLEDGE_GRAPH_SCOPE_KEY: scope_b,
        "document_builder_items": ["unrelated@builder"],
        "unrelated_state": "preserved",
    }


def test_same_scope_preserves_current_graph_editor_state() -> None:
    scope = database_scope_token("connection-a", "database-a")
    state = _graph_state(scope)

    changed = sync_knowledge_graph_scope(state, scope)

    assert changed is False
    assert state["knowledge_graph_edit_dirty"] is True
    assert state["knowledge_graph_new_html"] == "<html>A</html>"


def test_returning_to_database_does_not_restore_cleared_graph_state() -> None:
    scope_a = database_scope_token("connection-a", "database-a")
    scope_b = database_scope_token("connection-b", "database-b")
    state = _graph_state(scope_a)

    sync_knowledge_graph_scope(state, scope_b)
    sync_knowledge_graph_scope(state, scope_a)

    assert state.get("knowledge_graph_edit_graph_state") is None
    assert state.get("knowledge_graph_new_html") is None
    assert state[KNOWLEDGE_GRAPH_SCOPE_KEY] == scope_a


def test_map_session_identity_includes_scope_object_id_and_map_uid() -> None:
    scope_a = database_scope_token("connection-a", "shared")
    scope_b = database_scope_token("connection-b", "shared")
    baseline = knowledge_map_session_identity(scope_a, "same-id", "same-uid")

    assert baseline == knowledge_map_session_identity(scope_a, "same-id", "same-uid")
    assert baseline != knowledge_map_session_identity(scope_b, "same-id", "same-uid")
    assert baseline != knowledge_map_session_identity(scope_a, "other-id", "same-uid")
    assert baseline != knowledge_map_session_identity(scope_a, "same-id", "other-uid")


def test_same_map_ids_in_second_database_are_not_ready_until_reloaded() -> None:
    scope_a = database_scope_token("connection-a", "shared")
    scope_b = database_scope_token("connection-b", "shared")
    state: dict[str, object] = {KNOWLEDGE_GRAPH_SCOPE_KEY: scope_a}
    mark_knowledge_map_loaded(state, scope_a, "same-id", "same-uid")

    sync_knowledge_graph_scope(state, scope_b)

    assert knowledge_map_is_loaded(state, scope_b, "same-id", "same-uid") is False
    mark_knowledge_map_loaded(state, scope_b, "same-id", "same-uid")
    assert knowledge_map_is_loaded(state, scope_b, "same-id", "same-uid") is True
    assert knowledge_map_is_loaded(state, scope_a, "same-id", "same-uid") is False


def test_switch_is_pure_session_cleanup_with_no_mongodb_writes() -> None:
    scope_a = database_scope_token("connection-a", "database-a")
    scope_b = database_scope_token("connection-b", "database-b")
    state = _graph_state(scope_a)
    maps = _WriteSpyCollection()
    sources = _WriteSpyCollection()
    concepts = _WriteSpyCollection()
    relations = _WriteSpyCollection()

    sync_knowledge_graph_scope(state, scope_b)

    assert maps.writes == []
    assert sources.writes == []
    assert concepts.writes == []
    assert relations.writes == []


def test_graph_scope_sync_precedes_reads_and_map_identity_guards_writes() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    branch = source[source.index('elif page == "📊 Knowledge Graph":'):]

    assert branch.index("sync_knowledge_graph_scope(") < branch.index(
        'maps_col = db.db["knowledge_graph_maps"]'
    )
    assert "knowledge_map_session_identity(" in branch
    assert "mark_knowledge_map_loaded(" in branch
    assert "knowledge_map_is_loaded(" in branch
    assert branch.count("if not map_state_ready:") >= 4

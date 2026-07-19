"""Database-scope regressions for the read-only Document Builder."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path

from editor.database_scope import DOCUMENT_BUILDER_SCOPE_KEY
from editor.database_scope import database_scope_token
from editor.database_scope import sync_document_builder_scope
from editor.document_builder import _concepts_for_keys

ROOT = Path(__file__).resolve().parents[1]
BUILDER_SOURCE = ROOT / "editor" / "document_builder.py"
APP_SOURCE = ROOT / "editor" / "editor_streamlit.py"


class _ReadOnlyCollection:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.queries: list[dict] = []

    def find_one(self, query: dict, *_args, **_kwargs):
        self.queries.append(query)
        return next(
            (
                dict(document)
                for document in self.documents
                if all(document.get(key) == value for key, value in query.items())
            ),
            None,
        )

    def __getattr__(self, name: str):
        if name.startswith(("insert", "update", "delete", "replace", "bulk")):
            raise AssertionError(f"Document Builder attempted MongoDB write: {name}")
        raise AttributeError(name)


class _ReadOnlyDatabase:
    def __init__(self, concepts: list[dict], latex_documents: list[dict]) -> None:
        self.concepts = _ReadOnlyCollection(concepts)
        self.latex_documents = _ReadOnlyCollection(latex_documents)


def _populated_builder_state(scope: str) -> dict[str, object]:
    return {
        DOCUMENT_BUILDER_SCOPE_KEY: scope,
        "document_builder_items": ["X@S"],
        "document_builder_validation_results": [{"concept_id": "X", "source": "S"}],
        "document_builder_validation_filter": "error",
        "document_builder_source": "S",
        "document_builder_types": ["teorema"],
        "document_builder_search": "needle",
        "document_builder_available_select": ["X@S"],
        "document_builder_output_dir": "/tmp/generated",
        "document_builder_export_only_valid": True,
        "document_builder_generated_document": {"master": "a.tex"},
        "document_builder_preview": ["X@S"],
        "document_builder_error": "old error",
        "document_builder_message": "old message",
        "document_builder_pending_export": True,
        "doc_up_X@S_0": True,
        "unrelated_state": "preserved",
    }


def test_scope_token_includes_connection_and_real_database_name() -> None:
    first = database_scope_token("connection-a", "shared")
    same = database_scope_token("connection-a", "shared")
    other_connection = database_scope_token("connection-b", "shared")
    other_database = database_scope_token("connection-a", "other")

    assert first == same
    assert len({first, other_connection, other_database}) == 3


def test_switch_clears_every_builder_selection_result_and_widget_key() -> None:
    scope_a = database_scope_token("connection-a", "database-a")
    scope_b = database_scope_token("connection-b", "database-b")
    state = _populated_builder_state(scope_a)

    changed = sync_document_builder_scope(state, scope_b)

    assert changed is True
    assert state == {
        DOCUMENT_BUILDER_SCOPE_KEY: scope_b,
        "unrelated_state": "preserved",
    }


def test_same_database_scope_keeps_builder_state() -> None:
    scope = database_scope_token("connection-a", "database-a")
    state = _populated_builder_state(scope)

    changed = sync_document_builder_scope(state, scope)

    assert changed is False
    assert state["document_builder_items"] == ["X@S"]


def test_returning_to_database_does_not_restore_cleared_state() -> None:
    scope_a = database_scope_token("connection-a", "database-a")
    scope_b = database_scope_token("connection-b", "database-b")
    state = _populated_builder_state(scope_a)

    sync_document_builder_scope(state, scope_b)
    sync_document_builder_scope(state, scope_a)

    assert state.get("document_builder_items") is None
    assert state[DOCUMENT_BUILDER_SCOPE_KEY] == scope_a


def test_same_identity_in_second_database_cannot_reinterpret_first_selection() -> None:
    scope_a = database_scope_token("connection-a", "shared")
    scope_b = database_scope_token("connection-b", "shared")
    state = _populated_builder_state(scope_a)
    database_b = _ReadOnlyDatabase(
        concepts=[{"id": "X", "source": "S", "titulo": "Different B content"}],
        latex_documents=[{"id": "X", "source": "S", "contenido_latex": "B"}],
    )

    sync_document_builder_scope(state, scope_b)
    selected = _concepts_for_keys(database_b, list(state.get("document_builder_items", [])))

    assert selected == []
    assert database_b.concepts.queries == []
    assert database_b.latex_documents.queries == []


def test_modern_and_legacy_concepts_resolve_read_only_inside_own_database() -> None:
    database = _ReadOnlyDatabase(
        concepts=[
            {"id": "modern", "source": "S", "source_id": "managed-source"},
            {"id": "legacy", "source": "Legacy Snapshot"},
        ],
        latex_documents=[
            {"id": "modern", "source": "S", "contenido_latex": "modern body"},
            {"id": "legacy", "source": "Legacy Snapshot", "contenido_latex": "legacy body"},
        ],
    )

    concepts = _concepts_for_keys(database, ["modern@S", "legacy@Legacy Snapshot"])

    assert [(item["id"], item["contenido_latex"]) for item in concepts] == [
        ("modern", "modern body"),
        ("legacy", "legacy body"),
    ]


def test_builder_sync_precedes_database_reads_and_context_is_visible() -> None:
    builder_source = BUILDER_SOURCE.read_text(encoding="utf-8")
    render_branch = builder_source[builder_source.index("def render_document_builder_page"):]
    app_source = APP_SOURCE.read_text(encoding="utf-8")

    assert render_branch.index("sync_document_builder_scope(") < render_branch.index(
        "db.concepts.distinct("
    )
    assert "database_scope=active_database_scope" in app_source
    assert "database_name=active_database_name" in app_source
    assert "Connection:" in render_branch
    assert "Database:" in render_branch

"""Focused tests for clear, read-only active database presentation."""

# ruff: noqa: D103

from __future__ import annotations

import inspect
from pathlib import Path

import editor.database_connections as database_connections

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_APP = ROOT / "editor" / "editor_streamlit.py"


class _ReadOnlyDatabase:
    def __init__(self, name: str, operations: list[str] | None = None) -> None:
        self._name = name
        self._operations = operations

    @property
    def name(self) -> str:
        if self._operations is not None:
            self._operations.append("database.name")
        return self._name

    def __getattr__(self, attribute: str):
        raise AssertionError(f"unexpected database access: {attribute}")


class _ReadOnlyConnection:
    def __init__(self, database: _ReadOnlyDatabase, operations: list[str] | None = None) -> None:
        self._database = database
        self._operations = operations

    @property
    def db(self) -> _ReadOnlyDatabase:
        if self._operations is not None:
            self._operations.append("connection.db")
        return self._database

    def __getattr__(self, attribute: str):
        raise AssertionError(f"unexpected connection access: {attribute}")


def _display(alias: str, database_name: str) -> str:
    connection = _ReadOnlyConnection(_ReadOnlyDatabase(database_name))
    return database_connections.active_database_display_label(alias, connection)


def _app_branch(start_marker: str, end_marker: str) -> str:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_configured_mathv0_name_is_visible_without_hardcoding() -> None:
    assert _display("MathMongo (Current)", "MathV0") == "MathV0 — MathMongo (Current)"


def test_configured_mathmongo_name_is_visible() -> None:
    assert _display("MathMongo (Current)", "mathmongo") == (
        "mathmongo — MathMongo (Current)"
    )


def test_generic_alias_never_hides_the_real_database_name() -> None:
    rendered = _display("MathMongo (Current)", "research_database")

    assert rendered.startswith("research_database — ")
    assert "MathMongo (Current)" in rendered


def test_switcher_options_identify_each_real_database() -> None:
    labels = {
        _display("Local", "algebra"),
        _display("Remote", "geometry"),
    }

    assert labels == {"algebra — Local", "geometry — Remote"}
    switcher = _app_branch("# Database switcher", "# Add new database connection")
    assert "format_func=lambda connection_label: active_database_display_label(" in switcher


def test_current_database_card_uses_the_clear_display_label() -> None:
    branch = _app_branch("# Show current connection", "# Database switcher")

    assert "{current_database_card_label}" in branch
    assert "{current_db}<br>" not in branch


def test_add_concept_message_uses_the_clear_display_label() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")

    assert 'Adding concept to: **{current_database_label}**' in source
    assert 'Adding concept to: **{current_db}**' not in source


def test_same_alias_with_different_databases_remains_distinguishable() -> None:
    first = _display("Shared alias", "database_a")
    second = _display("Shared alias", "database_b")

    assert first != second
    assert first.startswith("database_a")
    assert second.startswith("database_b")


def test_same_database_on_different_connections_retains_safe_aliases() -> None:
    first = _display("Primary cluster", "shared_database")
    second = _display("Replica cluster", "shared_database")

    assert first == "shared_database — Primary cluster"
    assert second == "shared_database — Replica cluster"
    assert first != second


def test_uri_shaped_alias_is_not_exposed() -> None:
    rendered = _display("mongodb://alice:secret@localhost:27017", "safe_database")

    assert rendered == "safe_database"
    assert "alice" not in rendered
    assert "secret" not in rendered
    assert "mongodb://" not in rendered


def test_labels_follow_the_new_active_connection_after_rerun() -> None:
    before = _display("Current", "database_a")
    after = _display("Current", "database_b")
    switcher = _app_branch("# Database switcher", "# Add new database connection")

    assert before == "database_a — Current"
    assert after == "database_b — Current"
    assert before != after
    assert "st.rerun()" in switcher


def test_production_label_helper_does_not_hardcode_mathv0() -> None:
    source = inspect.getsource(database_connections)

    assert '"MathV0"' not in source
    assert "'MathV0'" not in source


def test_label_resolution_only_reads_connection_database_name() -> None:
    operations: list[str] = []
    database = _ReadOnlyDatabase("read_only", operations)
    connection = _ReadOnlyConnection(database, operations)

    rendered = database_connections.active_database_display_label("Friendly", connection)

    assert rendered == "read_only — Friendly"
    assert operations == ["connection.db", "database.name"]

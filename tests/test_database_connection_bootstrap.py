"""Focused tests for configured-only Streamlit database bootstrap."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from editor.database_connections import CONFIGURED_CONNECTION_LABEL
from editor.database_connections import initialize_configured_connection

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_APP = ROOT / "editor" / "editor_streamlit.py"


class _ManagerSpy:
    def __init__(self) -> None:
        self.added: list[tuple[str, str, str]] = []
        self.selected: list[str] = []

    def add_connection(self, label: str, uri: str, database: str) -> bool:
        self.added.append((label, uri, database))
        return True

    def set_current_connection(self, label: str) -> bool:
        self.selected.append(label)
        return True


def _bootstrap_branch() -> str:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    start = source.index("# Initialize database manager in session state")
    end = source.index("# Database connection sidebar", start)
    return source[start:end]


def test_configured_database_is_the_only_automatic_connection() -> None:
    manager = _ManagerSpy()
    settings = SimpleNamespace(mongo_uri="mongodb://test.invalid", mongo_database="fresh_a")

    initialized = initialize_configured_connection(manager, settings)

    assert initialized is True
    assert manager.added == [
        (CONFIGURED_CONNECTION_LABEL, "mongodb://test.invalid", "fresh_a")
    ]
    assert manager.selected == [CONFIGURED_CONNECTION_LABEL]


def test_mathv0_is_opened_only_when_it_is_the_configured_database() -> None:
    manager = _ManagerSpy()
    settings = SimpleNamespace(mongo_uri="mongodb://test.invalid", mongo_database="MathV0")

    initialize_configured_connection(manager, settings)

    assert [database for _label, _uri, database in manager.added] == ["MathV0"]


def test_changing_configuration_does_not_retain_a_literal_connection() -> None:
    first = _ManagerSpy()
    second = _ManagerSpy()

    initialize_configured_connection(
        first,
        SimpleNamespace(mongo_uri="mongodb://one.invalid", mongo_database="fresh_one"),
    )
    initialize_configured_connection(
        second,
        SimpleNamespace(mongo_uri="mongodb://two.invalid", mongo_database="fresh_two"),
    )

    assert [item[2] for item in first.added] == ["fresh_one"]
    assert [item[2] for item in second.added] == ["fresh_two"]


def test_streamlit_bootstrap_has_no_implicit_mathv0_connection() -> None:
    branch = _bootstrap_branch()

    assert '"MathV0"' not in branch
    assert "initialize_configured_connection(" in branch
    assert branch.count("add_connection(") == 0


def test_additional_connections_remain_an_explicit_sidebar_action() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    start = source.index("# Add new database connection")
    end = source.index("# Test database connection", start)
    branch = source[start:end]

    assert 'st.button("Add Connection")' in branch
    assert "db_manager.add_connection(" in branch

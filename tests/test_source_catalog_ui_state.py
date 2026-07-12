"""Pure and fake-render tests for Source Catalog UI state and safety."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import build_catalog_context
from editor.source_catalog.shared import initialize_catalog_indexes
from editor.source_catalog.shared import render_active_database
from editor.source_catalog.shared import render_catalog_result
from editor.source_catalog.shared import render_catalog_status
from editor.source_catalog.shared import safe_error_message
from editor.source_catalog.state import ACTIVE_DATABASE_IDENTITY
from editor.source_catalog.state import ADD_SOURCE_NAV_LABEL
from editor.source_catalog.state import EDIT_SOURCE_NAV_LABEL
from editor.source_catalog.state import NAVIGATION_WIDGET
from editor.source_catalog.state import add_source_catalog_navigation
from editor.source_catalog.state import apply_pending_navigation
from editor.source_catalog.state import begin_operation
from editor.source_catalog.state import draft_fingerprint
from editor.source_catalog.state import finish_operation
from editor.source_catalog.state import request_navigation
from editor.source_catalog.state import state_key
from editor.source_catalog.state import sync_database_state
from mathmongo.source_catalog.indexes import IndexPlan
from mathmongo.source_catalog.indexes import IndexSpec
from mathmongo.source_catalog.indexes import IndexState
from mathmongo.source_catalog.indexes import IndexStatus
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.service import CatalogResult
from mathmongo.source_catalog.service import CatalogResultStatus


class _Collection:
    def list_indexes(self):
        return iter(())


class _Database:
    def __init__(self, name: str) -> None:
        self.name = name
        self.accessed: list[str] = []
        self.list_collection_names_count = 0

    def __getitem__(self, name: str) -> _Collection:
        self.accessed.append(name)
        return _Collection()

    def list_collection_names(self) -> list[str]:
        self.list_collection_names_count += 1
        return []


class _Connection:
    def __init__(self, database: _Database) -> None:
        self.db = database


class _IndexManager:
    def __init__(self, database: _Database) -> None:
        self.database = database
        self.apply_count = 0
        self.plan_count = 0
        self.status_count = 0
        self.ready = False
        self.conflict = False
        self.spec = IndexSpec("sources", "sources_test", (("source_id", 1),), True)

    def status(self) -> tuple[IndexStatus, ...]:
        self.status_count += 1
        if self.conflict:
            state = IndexState.CONFLICT
        else:
            state = IndexState.PRESENT if self.ready else IndexState.MISSING
        return (IndexStatus(self.spec, state),)

    def plan(self) -> IndexPlan:
        self.plan_count += 1
        return IndexPlan(self.status())

    def apply(self) -> IndexPlan:
        self.apply_count += 1
        self.ready = True
        return self.plan()


class _UI:
    def __init__(
        self,
        *,
        database_name: str = "isolated",
        click: bool = False,
        confirmation_text: str | None = None,
        confirmed: bool = True,
    ) -> None:
        self.session_state: dict[str, Any] = {}
        self.database_name = database_name
        self.click = click
        self.confirmation_text = database_name if confirmation_text is None else confirmation_text
        self.confirmed = confirmed
        self.messages: list[tuple[str, str]] = []
        self.dataframes: list[list[dict[str, str]]] = []
        self.disabled: bool | None = None
        self.disabled_history: list[bool] = []
        self.form_count = 0
        self.form_submit_count = 0
        self.regular_button_count = 0

    def _message(self, level: str, value: object) -> None:
        self.messages.append((level, str(value)))

    def info(self, value: object) -> None:
        self._message("info", value)

    def caption(self, value: object) -> None:
        self._message("caption", value)

    def subheader(self, value: object) -> None:
        self._message("subheader", value)

    def success(self, value: object) -> None:
        self._message("success", value)

    def warning(self, value: object) -> None:
        self._message("warning", value)

    def error(self, value: object) -> None:
        self._message("error", value)

    def write(self, value: object) -> None:
        self._message("write", value)

    def dataframe(self, rows: list[dict[str, str]], **_kwargs) -> None:
        self.dataframes.append(rows)

    def expander(self, *_args, **_kwargs):
        return nullcontext(self)

    def form(self, *_args, **_kwargs):
        self.form_count += 1
        return nullcontext(self)

    def text_input(self, _label: str, *, key: str) -> str:
        del key
        return self.confirmation_text

    def checkbox(self, _label: str, *, key: str) -> bool:
        del key
        return self.confirmed

    def button(self, _label: str, *, key: str, disabled: bool) -> bool:
        del key
        self.regular_button_count += 1
        self.disabled = disabled
        self.disabled_history.append(disabled)
        return self.click and not disabled

    def form_submit_button(self, _label: str, *, disabled: bool) -> bool:
        self.form_submit_count += 1
        self.disabled = disabled
        self.disabled_history.append(disabled)
        return self.click and not disabled


def _context(
    database: _Database,
    manager: _IndexManager,
    *,
    connection_label: str = "Friendly label",
) -> CatalogUIContext:
    return CatalogUIContext(
        connection_label=connection_label,
        database_name=database.name,
        database=database,
        source_repository=None,  # type: ignore[arg-type]
        reference_repository=None,  # type: ignore[arg-type]
        service=None,  # type: ignore[arg-type]
        index_manager=manager,  # type: ignore[arg-type]
    )


def test_navigation_adds_catalog_pages_without_removing_existing_pages() -> None:
    existing = ["🏠 Dashboard", "➕ Add Concept", "✏️ Edit Concept", "⚙️ Settings"]

    result = add_source_catalog_navigation(existing)

    assert result == [
        "🏠 Dashboard",
        ADD_SOURCE_NAV_LABEL,
        EDIT_SOURCE_NAV_LABEL,
        "➕ Add Concept",
        "✏️ Edit Concept",
        "⚙️ Settings",
    ]
    assert add_source_catalog_navigation(result) == result


def test_database_change_clears_only_namespaced_state() -> None:
    state = {
        ACTIVE_DATABASE_IDENTITY: "label\x1fdb-a",
        state_key("preview"): {"candidate": 1},
        "cornell_document": "keep",
    }

    changed = sync_database_state(state, connection_label="label", database_name="db-b")

    assert changed is True
    assert state[ACTIVE_DATABASE_IDENTITY] == "label\x1fdb-b"
    assert state["cornell_document"] == "keep"
    assert state_key("preview") not in state


def test_replaced_endpoint_with_same_label_and_name_clears_catalog_state() -> None:
    first_database = object()
    replacement_database = object()
    state: dict[str, Any] = {}
    sync_database_state(
        state,
        connection_label="same label",
        database_name="same_database",
        database=first_database,
    )
    state[state_key("preview")] = "endpoint-specific"

    changed = sync_database_state(
        state,
        connection_label="same label",
        database_name="same_database",
        database=replacement_database,
    )

    assert changed is True
    assert state_key("preview") not in state


def test_pending_navigation_applies_before_widget_creation() -> None:
    state: dict[str, Any] = {}
    options = ["🏠 Dashboard", EDIT_SOURCE_NAV_LABEL]
    request_navigation(state, EDIT_SOURCE_NAV_LABEL, source_id="src_test")

    applied = apply_pending_navigation(state, options)

    assert applied == EDIT_SOURCE_NAV_LABEL
    assert state[NAVIGATION_WIDGET] == EDIT_SOURCE_NAV_LABEL
    assert apply_pending_navigation(state, options) is None


def test_operation_token_prevents_double_submit_after_rerun() -> None:
    state: dict[str, Any] = {}

    assert begin_operation(state, "create", "token-1") is True
    assert begin_operation(state, "create", "token-1") is False
    finish_operation(state, "create", "token-1", succeeded=True)
    assert begin_operation(state, "create", "token-1") is False
    assert begin_operation(state, "create", "token-2") is True


def test_draft_fingerprint_changes_with_fields_but_never_contains_raw() -> None:
    first = Reference(
        title="First",
        bibtex={"raw": "@misc{private, note={secret body}}"},
    )
    same_fields_new_id = Reference(
        title="First",
        bibtex={"raw": "@misc{private, note={secret body}}"},
    )
    changed = Reference(
        title="Changed",
        bibtex={"raw": "@misc{private, note={secret body}}"},
    )

    first_digest = draft_fingerprint(first)

    assert first_digest == draft_fingerprint(same_fields_new_id)
    assert first_digest != draft_fingerprint(changed)
    assert "secret body" not in first_digest


def test_context_uses_real_database_name_and_one_database_identity() -> None:
    database = _Database("real_database")

    context = build_catalog_context("MathMongo (Current)", _Connection(database))

    assert context.database is database
    assert context.database_name == "real_database"
    assert context.service.database is database
    assert context.source_repository.database is database
    assert context.reference_repository.database is database
    assert context.index_manager.database is database
    assert database.accessed == []


def test_active_banner_distinguishes_label_from_real_database() -> None:
    database = _Database("MathV0")
    ui = _UI()
    render_active_database(ui, _context(database, _IndexManager(database)))

    rendered = " ".join(message for _level, message in ui.messages)
    assert "Base activa: **MathV0**" in rendered
    assert "Conexión: Friendly label" in rendered


def test_active_banner_sanitizes_connection_label_but_keeps_real_database_name() -> None:
    database = _Database("MathV0")
    ui = _UI()
    context = _context(
        database,
        _IndexManager(database),
        connection_label="mongodb://alice:secret@localhost/db token=private",
    )

    render_active_database(ui, context)

    rendered = " ".join(message for _level, message in ui.messages)
    assert "alice" not in rendered
    assert "secret" not in rendered
    assert "private" not in rendered
    assert "Base activa: **MathV0**" in rendered
    assert "Base MongoDB real: MathV0" in rendered


def test_index_status_and_plan_are_read_only_and_render_in_a_form() -> None:
    database = _Database("isolated")
    manager = _IndexManager(database)
    context = _context(database, manager)
    ui = _UI(database_name="isolated", click=False)

    render_catalog_status(ui, context)

    assert manager.apply_count == 0
    assert manager.status_count == 2
    assert manager.plan_count == 1
    assert database.list_collection_names_count == 1
    assert database.accessed == []
    assert ui.form_count == 1
    assert ui.form_submit_count == 1
    assert ui.regular_button_count == 0
    assert any(
        row["collection"] == "sources" and row["index"] == "sources_test"
        for dataframe in ui.dataframes
        for row in dataframe
    )


def test_confirmed_index_apply_is_one_shot_after_rerun() -> None:
    database = _Database("isolated")
    manager = _IndexManager(database)
    context = _context(database, manager)
    ui = _UI(database_name="isolated", click=True)

    render_catalog_status(ui, context)
    render_catalog_status(ui, context)

    assert manager.apply_count == 1
    assert ui.disabled_history == [False, True]


def test_index_apply_requires_exact_name_checkbox_missing_plan_and_no_conflict() -> None:
    database = _Database("isolated")
    manager = _IndexManager(database)
    context = _context(database, manager)

    wrong_name = _UI(click=True, confirmation_text="Friendly label")
    render_catalog_status(wrong_name, context)
    assert wrong_name.disabled is False
    assert any("not executed" in message for _level, message in wrong_name.messages)

    unchecked = _UI(click=True, confirmed=False)
    render_catalog_status(unchecked, context)
    assert unchecked.disabled is False
    assert any("not executed" in message for _level, message in unchecked.messages)

    manager.conflict = True
    conflict = _UI(click=True)
    render_catalog_status(conflict, context)
    assert conflict.disabled is True
    assert any(
        level == "error" and "revisión humana" in message for level, message in conflict.messages
    )
    assert manager.apply_count == 0


def test_index_apply_can_run_again_after_initialized_plan_later_becomes_missing() -> None:
    database = _Database("isolated")
    manager = _IndexManager(database)
    context = _context(database, manager)
    ui = _UI(click=True)

    render_catalog_status(ui, context)
    render_catalog_status(ui, context)
    manager.ready = False
    render_catalog_status(ui, context)

    assert manager.apply_count == 2


def test_index_initialization_requires_exact_real_database_name() -> None:
    database = _Database("real-name")
    manager = _IndexManager(database)
    context = _context(database, manager)

    try:
        initialize_catalog_indexes(context, confirmation_text="Friendly label", confirmed=True)
    except ValueError as exc:
        assert "exact real database name" in str(exc)
    else:
        raise AssertionError("wrong database label must not initialize indexes")
    assert manager.apply_count == 0


def test_safe_error_redacts_uri_credentials_and_validation_input() -> None:
    message = safe_error_message(
        "failed mongodb+srv://alice:secret@example.test/db password=hunter2, "
        '"api_key": "json-secret", authorization=Bearer auth-secret; token=abc123, '
        "input_value=@article{private body}, input_type=str"
    )

    assert "alice" not in message
    assert "secret" not in message
    assert "hunter2" not in message
    assert "abc123" not in message
    assert "json-secret" not in message
    assert "auth-secret" not in message
    assert "private body" not in message
    assert "<redacted MongoDB URI>" in message


def test_safe_error_redacts_internal_path_without_hiding_domain_ids() -> None:
    message = safe_error_message(
        "failure in /home/user/private/catalog/file.py, file:///usr/local/private.log, "
        r"C:\Users\alice\private.txt for source_id=src_keep_me"
    )

    assert "/home/user/private/catalog/file.py" not in message
    assert "file:///usr/local/private.log" not in message
    assert "Users" not in message
    assert "<redacted local path>" in message
    assert "source_id=src_keep_me" in message


def test_catalog_result_sanitizes_messages_warnings_errors_and_blockers() -> None:
    ui = _UI()
    render_catalog_result(
        ui,
        CatalogResult(
            CatalogResultStatus.BLOCKED,
            message="mongodb://user:password@localhost/private",
            warnings=("token=warning-secret",),
            errors=("/home/user/private/error.log",),
            blockers=("password=blocker-secret",),
        ),
        success="unused",
    )

    rendered = " ".join(message for _level, message in ui.messages)
    assert "user:password" not in rendered
    assert "warning-secret" not in rendered
    assert "/home/user" not in rendered
    assert "blocker-secret" not in rendered

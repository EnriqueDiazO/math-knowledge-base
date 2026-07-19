"""Persistent, scoped feedback contract for Edit Concept updates."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from editor.db.concept_edit_service import ConceptEditResult
from editor.db.concept_edit_service import ConceptEditStatus
from editor.edit_concept_feedback import FLASH_KEY
from editor.edit_concept_feedback import SCOPE_KEY
from editor.edit_concept_feedback import feedback_for_update_result
from editor.edit_concept_feedback import render_update_flash
from editor.edit_concept_feedback import safe_update_exception_message
from editor.edit_concept_feedback import store_update_success_flash
from editor.edit_concept_feedback import sync_update_feedback_scope

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "editor" / "editor_streamlit.py"
HELPER = ROOT / "editor" / "edit_concept_feedback.py"
CONCEPT_ID = "def_001"
SOURCE = "SourceTest"
DATABASE_SCOPE_A = "connection-a\x1fdatabase-a"
DATABASE_SCOPE_B = "connection-b\x1fdatabase-b"


class FakeUI:
    def __init__(self) -> None:
        self.successes: list[str] = []
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def success(self, message: str) -> None:
        self.successes.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


def _result(
    status: ConceptEditStatus,
    *,
    concept_matched: int = 0,
    concept_modified: int = 0,
    latex_matched: int = 0,
    latex_modified: int = 0,
) -> ConceptEditResult:
    return ConceptEditResult(
        status=status,
        message=f"service result: {status.value}",
        concept_matched_count=concept_matched,
        concept_modified_count=concept_modified,
        latex_matched_count=latex_matched,
        latex_modified_count=latex_modified,
    )


def _success_result(*, modified: bool = True) -> ConceptEditResult:
    return _result(
        ConceptEditStatus.SUCCESS,
        concept_matched=1,
        concept_modified=int(modified),
        latex_matched=1,
        latex_modified=int(modified),
    )


def _edit_concept_branch() -> str:
    source = APP.read_text(encoding="utf-8")
    start = source.index('elif page == "✏️ Edit Concept":')
    end = source.index('\nelif page == "📚 Browse Concepts":', start)
    return source[start:end]


def _ordinary_save_block() -> str:
    branch = _edit_concept_branch()
    start = branch.index('if st.button("💾 Update Concept"')
    end = branch.index("# PDF Generation Button for Edit Concept", start)
    return branch[start:end]


def test_success_is_stored_before_rerun_and_rendered_after_later_render() -> None:
    state: dict[str, Any] = {}
    sync_update_feedback_scope(state, DATABASE_SCOPE_A)

    stored = store_update_success_flash(
        state,
        _success_result(),
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )

    assert stored is True
    assert state[FLASH_KEY]["level"] == "success"
    # Simulate the save rerun and the form-reload rerun without consuming flash.
    assert sync_update_feedback_scope(state, DATABASE_SCOPE_A) is False
    assert FLASH_KEY in state
    assert sync_update_feedback_scope(state, DATABASE_SCOPE_A) is False
    assert FLASH_KEY in state
    ui = FakeUI()
    assert render_update_flash(
        ui,
        state,
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    ) is True
    assert ui.successes == [
        "Concepto actualizado correctamente: def_001 — SourceTest."
    ]


def test_success_message_names_the_updated_concept_and_source_snapshot() -> None:
    feedback = feedback_for_update_result(
        _success_result(),
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )

    assert feedback.level == "success"
    assert "actualizado correctamente" in feedback.message
    assert CONCEPT_ID in feedback.message
    assert SOURCE in feedback.message


def test_feedback_is_rendered_after_reload_gate_and_before_edit_form() -> None:
    branch = _edit_concept_branch()

    render_position = branch.index("render_update_flash(")
    reload_position = branch.index("# Force rerun to update all widgets")
    header_position = branch.index("# Display header")
    form_position = branch.index("# Basic information")

    assert reload_position < render_position < header_position < form_position


def test_flash_is_consumed_exactly_once() -> None:
    state: dict[str, Any] = {}
    sync_update_feedback_scope(state, DATABASE_SCOPE_A)
    store_update_success_flash(
        state,
        _success_result(),
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )
    ui = FakeUI()

    first = render_update_flash(
        ui,
        state,
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )
    second = render_update_flash(
        ui,
        state,
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )

    assert first is True
    assert second is False
    assert len(ui.successes) == 1
    assert FLASH_KEY not in state


def test_valid_noop_is_a_confirmed_success() -> None:
    result = _success_result(modified=False)

    feedback = feedback_for_update_result(
        result,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )

    assert result.concept_matched_count == 1
    assert result.latex_matched_count == 1
    assert feedback.level == "success"
    assert feedback.message == (
        "Concepto confirmado sin cambios: def_001 — SourceTest. "
        "El contenido persistido ya era idéntico."
    )


@pytest.mark.parametrize(
    ("status", "expected_level", "expected_text"),
    (
        (ConceptEditStatus.CONCEPT_NOT_FOUND, "error", "ya no existe"),
        (ConceptEditStatus.LATEX_NOT_FOUND, "error", "documento LaTeX"),
        (ConceptEditStatus.STALE_IDENTITY, "warning", "Recarga"),
        (
            ConceptEditStatus.FAILED_COMPENSATED,
            "error",
            "no quedó una actualización persistente",
        ),
        (
            ConceptEditStatus.PARTIAL_RECOVERY_REQUIRED,
            "error",
            "requiere recuperación",
        ),
    ),
)
def test_non_success_statuses_never_store_or_render_success(
    status: ConceptEditStatus,
    expected_level: str,
    expected_text: str,
) -> None:
    result = _result(status)
    feedback = feedback_for_update_result(
        result,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )
    state: dict[str, Any] = {SCOPE_KEY: DATABASE_SCOPE_A}

    stored = store_update_success_flash(
        state,
        result,
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )

    assert feedback.level == expected_level
    assert expected_text in feedback.message
    assert stored is False
    assert FLASH_KEY not in state


def test_unexpected_exception_has_safe_feedback_and_does_not_trigger_rerun() -> None:
    message = safe_update_exception_message(RuntimeError("mongodb://secret@example"))
    save_block = _ordinary_save_block()
    exception_block = save_block[save_block.index("except Exception") :]

    assert "secret" not in message
    assert "No se limpió el formulario" in message
    assert "safe_update_exception_message" in exception_block
    assert "st.rerun()" not in exception_block


def test_flash_for_another_concept_is_discarded_without_rendering() -> None:
    state: dict[str, Any] = {SCOPE_KEY: DATABASE_SCOPE_A}
    store_update_success_flash(
        state,
        _success_result(),
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )
    ui = FakeUI()

    rendered = render_update_flash(
        ui,
        state,
        database_scope=DATABASE_SCOPE_A,
        concept_id="def_002",
        source=SOURCE,
    )

    assert rendered is False
    assert ui.successes == []
    assert FLASH_KEY not in state


def test_flash_for_another_source_snapshot_is_not_misattributed() -> None:
    state: dict[str, Any] = {SCOPE_KEY: DATABASE_SCOPE_A}
    store_update_success_flash(
        state,
        _success_result(),
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )
    ui = FakeUI()

    rendered = render_update_flash(
        ui,
        state,
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source="OtherSource",
    )

    assert rendered is False
    assert ui.successes == []
    assert FLASH_KEY not in state


def test_database_change_discards_flash_before_any_render() -> None:
    state: dict[str, Any] = {}
    sync_update_feedback_scope(state, DATABASE_SCOPE_A)
    store_update_success_flash(
        state,
        _success_result(),
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )

    changed = sync_update_feedback_scope(state, DATABASE_SCOPE_B)

    assert changed is True
    assert state[SCOPE_KEY] == DATABASE_SCOPE_B
    assert FLASH_KEY not in state


def test_same_database_scope_keeps_pending_flash_across_reruns() -> None:
    state: dict[str, Any] = {}
    sync_update_feedback_scope(state, DATABASE_SCOPE_A)
    store_update_success_flash(
        state,
        _success_result(),
        database_scope=DATABASE_SCOPE_A,
        concept_id=CONCEPT_ID,
        source=SOURCE,
    )

    changed = sync_update_feedback_scope(state, DATABASE_SCOPE_A)

    assert changed is False
    assert FLASH_KEY in state


def test_update_integration_stores_flash_before_selection_cleanup_and_rerun() -> None:
    save_block = _ordinary_save_block()

    status_position = save_block.index(
        "feedback_for_update_result(",
        save_block.index("update_concept_fields_preserving_identity("),
    )
    store_position = save_block.index("store_update_success_flash(")
    cleanup_position = save_block.index(
        "st.session_state.pop(legacy_last_selected_key, None)"
    )
    rerun_position = save_block.index("st.rerun()", cleanup_position)

    assert status_position < store_position < cleanup_position < rerun_position
    assert "st.success(" not in save_block[store_position:rerun_position]


def test_update_feedback_change_does_not_expand_persistence_scope() -> None:
    helper_source = HELPER.read_text(encoding="utf-8")
    helper_tree = ast.parse(helper_source, filename=str(HELPER))
    save_block = _ordinary_save_block()

    for forbidden in (
        "insert_one(",
        "update_one(",
        "delete_one(",
        "db.sources",
        "db.relations",
        "db.media_assets",
        "db.concept_evidence_links",
    ):
        assert forbidden not in helper_source
        assert forbidden not in save_block
    assert all(
        not (isinstance(node, ast.ImportFrom) and "repository" in (node.module or ""))
        for node in ast.walk(helper_tree)
    )


def test_ordinary_update_payload_still_excludes_identity_fields() -> None:
    save_block = _ordinary_save_block()
    payload = save_block[
        save_block.index("concept_changes = {") : save_block.index(
            "# Add reference if provided"
        )
    ]

    assert '"id":' not in payload
    assert '"source":' not in payload
    assert '"source_id":' not in payload
    assert "concept_id=original_concept_id" in save_block
    assert "source=original_source" in save_block
    assert "expected_source_id=original_source_id" in save_block

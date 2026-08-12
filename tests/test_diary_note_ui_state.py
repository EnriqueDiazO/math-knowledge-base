"""State-contract tests for the shared Streamlit Diario settings editor."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path

from editor.diary_note_models import note_with_settings
from editor.diary_note_ui import add_manual_reference_state
from editor.diary_note_ui import clear_note_settings_state
from editor.diary_note_ui import initialize_note_settings_state
from editor.diary_note_ui import move_reference_state
from editor.diary_note_ui import remove_reference_state
from editor.diary_note_ui import settings_from_ui_state


def test_old_note_state_initialization_is_conservative_and_isolated() -> None:
    state: dict[str, object] = {"unrelated": "keep"}
    initialize_note_settings_state(
        state,
        prefix="editor_note_a",
        note={"_id": "a", "title": "A"},
        identity="a",
    )
    initialize_note_settings_state(
        state,
        prefix="editor_note_b",
        note={"_id": "b", "title": "B"},
        identity="b",
    )

    assert settings_from_ui_state(state, "editor_note_a").page_layout.enabled is False
    assert settings_from_ui_state(state, "editor_note_b").references == []
    assert state["unrelated"] == "keep"


def test_reference_widget_keys_follow_stable_id_during_reorder() -> None:
    state: dict[str, object] = {}
    prefix = "new_note"
    initialize_note_settings_state(
        state,
        prefix=prefix,
        note={},
        identity="new",
        new_note=True,
    )
    first_id = add_manual_reference_state(state, prefix)
    second_id = add_manual_reference_state(state, prefix)
    state[f"{prefix}_reference_{first_id}_title"] = "Primera"
    state[f"{prefix}_reference_{second_id}_title"] = "Segunda"

    move_reference_state(state, prefix, second_id, -1)
    settings = settings_from_ui_state(state, prefix)

    assert [reference.reference_id for reference in settings.references] == [
        second_id,
        first_id,
    ]
    assert [reference.title for reference in settings.references] == ["Segunda", "Primera"]


def test_explicit_reference_removal_does_not_touch_other_note_state() -> None:
    state: dict[str, object] = {"other_note_settings_value": 7}
    prefix = "edit_a"
    initialize_note_settings_state(
        state,
        prefix=prefix,
        note={},
        identity="a",
    )
    reference_id = add_manual_reference_state(state, prefix)

    remove_reference_state(state, prefix, reference_id)

    assert settings_from_ui_state(state, prefix).references == []
    assert state["other_note_settings_value"] == 7


def test_clear_removes_only_one_editor_draft() -> None:
    state: dict[str, object] = {}
    for prefix in ("new_a", "edit_b"):
        initialize_note_settings_state(
            state,
            prefix=prefix,
            note={},
            identity=prefix,
        )
    clear_note_settings_state(state, "new_a")

    assert not any(key.startswith("new_a_") for key in state)
    assert any(key.startswith("edit_b_") for key in state)


def test_references_order_and_toc_survive_reopen_from_persisted_note() -> None:
    state: dict[str, object] = {}
    prefix = "edit_original"
    initialize_note_settings_state(
        state,
        prefix=prefix,
        note={"_id": "original"},
        identity="original",
    )
    first_id = add_manual_reference_state(state, prefix)
    second_id = add_manual_reference_state(state, prefix)
    state[f"{prefix}_reference_{first_id}_title"] = "Primera"
    state[f"{prefix}_reference_{second_id}_title"] = "Segunda"
    move_reference_state(state, prefix, second_id, -1)
    state[f"{prefix}_settings_toc_show_table_of_contents"] = True
    persisted = note_with_settings(
        {"_id": "original"},
        settings_from_ui_state(state, prefix),
    )

    clear_note_settings_state(state, prefix)
    initialize_note_settings_state(
        state,
        prefix=prefix,
        note=persisted,
        identity="original-reopened",
    )
    reopened = settings_from_ui_state(state, prefix)

    assert [item.reference_id for item in reopened.references] == [second_id, first_id]
    assert [item.title for item in reopened.references] == ["Segunda", "Primera"]
    assert reopened.table_of_contents.show_table_of_contents is True


def test_new_and_edit_flows_use_the_shared_editor_and_narrow_persistence() -> None:
    source = Path("editor/cuaderno_page.py").read_text(encoding="utf-8")

    assert source.count("render_note_settings_editor(") == 2
    assert "persist_diary_note_update(" in source
    assert "doc.update(settings_document_fields(note_settings))" in source

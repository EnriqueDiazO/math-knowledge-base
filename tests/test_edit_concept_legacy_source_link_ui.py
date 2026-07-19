"""UI contract for the explicit legacy link action in Edit Concept."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path

from editor.source_catalog.state import ACTIVE_DATABASE_IDENTITY
from editor.source_catalog.state import state_key
from editor.source_catalog.state import sync_database_state

APP_PATH = Path(__file__).resolve().parents[1] / "editor" / "editor_streamlit.py"


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _branch(start_marker: str, end_marker: str) -> str:
    source = _app_source()
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _edit_branch() -> str:
    return _branch(
        'elif page == "✏️ Edit Concept":',
        '\nelif page == "📚 Browse Concepts":',
    )


def _add_concept_branch() -> str:
    return _branch(
        'elif page == "➕ Add Concept":',
        '\nelif page == "✏️ Edit Concept":',
    )


def _link_section() -> str:
    branch = _edit_branch()
    start = branch.index('st.subheader("🔗 Link to an existing managed Source")')
    end = branch.index("# Concept type (read-only", start)
    return branch[start:end]


def _ordinary_save_block() -> str:
    branch = _edit_branch()
    start = branch.index('if st.button("💾 Update Concept"')
    end = branch.index("# PDF Generation Button for Edit Concept", start)
    return branch[start:end]


def test_legacy_concept_gets_an_explicit_link_action_only_when_field_is_absent() -> None:
    branch = _edit_branch()

    assert 'original_source_id_present = "source_id" in selected_concept' in branch
    assert 'if not original_source_id_present:' in branch
    assert "Legacy concept — not linked to a managed Source." in branch
    assert "🔗 Link to an existing managed Source" in branch


def test_link_selector_lists_active_source_ids_from_the_active_catalog() -> None:
    section = _link_section()

    assert "catalog_context.source_repository" in section
    assert "load_active_sources(" in section
    assert "managed_source_ids = [source.source_id for source in" in section
    assert "options=managed_source_ids" in section
    assert "format_func=lambda value:" in section
    assert "resolve_active_source(" in section
    assert "selected_source_id" in section


def test_link_action_has_no_free_text_or_source_creation_path() -> None:
    section = _link_section()

    assert "st.text_input(" not in section
    assert "Custom" not in section
    assert "New source name" not in section
    assert "create_source(" not in section
    assert "insert_one(" not in section
    assert "update_one(" not in section


def test_empty_or_failed_catalog_blocks_linking_with_safe_messages() -> None:
    section = _link_section()

    assert "No hay Sources activas disponibles." in section
    assert "Crea primero una Source desde Add Source." in section
    assert "safe_catalog_error(exc)" in section
    assert "link_action_available = False" in section
    assert "disabled=not link_action_available" in section


def test_confirmation_shows_both_identities_and_non_move_warning() -> None:
    section = _link_section()

    assert "Historical Source snapshot" in section
    assert "Managed Source selected" in section
    assert "Target Managed Source ID" in section
    assert "original_source" in section
    assert "selected_source_preview.name" in section
    assert "selected_source_id" in section
    assert "La vinculación añadirá el Managed Source ID, pero no cambiará" in section
    assert "el snapshot histórico ni la clave id@source." in section
    assert "I confirm" in section
    assert "will not move the concept" in section


def test_link_button_is_distinct_from_ordinary_update_and_calls_only_service() -> None:
    section = _link_section()
    ordinary_save = _ordinary_save_block()

    assert "🔗 Link managed Source" in section
    assert "link_concept_to_existing_managed_source(" in section
    assert "link_concept_to_existing_managed_source(" not in ordinary_save
    assert "expected_source_id=original_source_id" in ordinary_save
    assert 'if st.button("💾 Update Concept"' not in section


def test_linked_or_explicit_null_concepts_cannot_change_or_repair_link() -> None:
    branch = _edit_branch()

    assert "if original_source_id_present:" in branch
    assert "Managed Source ID (immutable)" in branch
    assert "Repair link is outside this phase" in branch
    assert 'st.button("Change Source"' not in _link_section()
    assert 'st.button("Unlink"' not in _link_section()


def test_every_structured_failure_has_a_non_success_message() -> None:
    section = _link_section()
    required_failures = (
        "TARGET_NOT_FOUND",
        "TARGET_INACTIVE",
        "CONCEPT_NOT_FOUND",
        "LATEX_NOT_FOUND",
        "STALE_IDENTITY",
        "LINK_MISMATCH",
        "ALREADY_LINKED_TO_DIFFERENT_SOURCE",
        "FAILED_COMPENSATED",
        "PARTIAL_RECOVERY_REQUIRED",
    )

    for status in required_failures:
        assert f"ConceptSourceLinkStatus.{status}" in section
    assert "st.error(" in section
    assert "ConceptSourceLinkStatus.SUCCESS" in section
    assert "ConceptSourceLinkStatus.ALREADY_LINKED" in section


def test_success_clears_only_link_widgets_then_reruns_for_a_fresh_document() -> None:
    section = _link_section()

    assert "st.session_state.pop(link_source_selector_key, None)" in section
    assert "st.session_state.pop(link_confirmation_key, None)" in section
    assert "st.rerun()" in section
    assert "legacy_last_selected_key" not in section
    assert "st.session_state.clear(" not in section


def test_database_switch_clears_namespaced_link_state_and_preserves_unrelated_state() -> None:
    old_identity = "old database identity"
    link_key = state_key("legacy_link_target_source_id", "grupo")
    state = {
        ACTIVE_DATABASE_IDENTITY: old_identity,
        link_key: "src_old",
        "unrelated": "keep",
    }

    changed = sync_database_state(
        state,
        connection_label="Database B",
        database_name="temporary_b",
        database=object(),
    )

    assert changed
    assert link_key not in state
    assert state["unrelated"] == "keep"


def test_link_flow_is_absent_from_add_concept_and_other_source_pages() -> None:
    source = _app_source()
    edit_branch = _edit_branch()

    assert "link_concept_to_existing_managed_source(" not in _add_concept_branch()
    assert source.count('st.subheader("🔗 Link to an existing managed Source")') == 1
    assert source.count("link_concept_to_existing_managed_source(") == 1
    assert "render_add_source_page" not in edit_branch
    assert "render_edit_source_page" not in edit_branch

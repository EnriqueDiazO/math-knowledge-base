"""Streamlit Add Source page using only the S1A catalog facade."""

from __future__ import annotations

from typing import Any

from editor.source_catalog.bibtex_ui import render_bibtex_input
from editor.source_catalog.reference_actions import render_reference_save_plan
from editor.source_catalog.reference_form import ReferenceFormDraft
from editor.source_catalog.reference_form import render_reference_form
from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import render_active_database
from editor.source_catalog.shared import render_catalog_result
from editor.source_catalog.shared import render_catalog_status
from editor.source_catalog.shared import render_duplicate_preview
from editor.source_catalog.shared import safe_error_message
from editor.source_catalog.source_form import SourceFormDraft
from editor.source_catalog.source_form import render_source_form
from editor.source_catalog.state import EDIT_SOURCE_NAV_LABEL
from editor.source_catalog.state import SELECTED_SOURCE_ID
from editor.source_catalog.state import begin_operation
from editor.source_catalog.state import clear_state_group
from editor.source_catalog.state import draft_fingerprint
from editor.source_catalog.state import finish_operation
from editor.source_catalog.state import request_navigation
from editor.source_catalog.state import state_key
from editor.source_catalog.workflows import AddSourceOutcome
from editor.source_catalog.workflows import ReferenceSavePlan
from editor.source_catalog.workflows import allow_source_creation
from editor.source_catalog.workflows import duplicate_confirmation_required
from editor.source_catalog.workflows import execute_add_source
from mathmongo.source_catalog.models import Source

ADD_PREVIEW_KEY = state_key("add_preview")
RECENT_CREATED_SOURCE_ID = state_key("recent_created_source_id")
REFERENCE_MODES = ("None", "Manual", "Paste / Upload BibTeX")


def _show_form_errors(ui: Any, draft: SourceFormDraft | ReferenceFormDraft) -> None:
    for message in draft.errors:
        ui.error(f"Validation error: {safe_error_message(message)}")


def _manual_reference_plan(
    ui: Any,
    context: CatalogUIContext,
) -> tuple[list[ReferenceSavePlan], bool]:
    draft = render_reference_form(ui, key_prefix="add_manual_reference")
    if not draft.valid or draft.reference is None:
        _show_form_errors(ui, draft)
        return [], False
    try:
        duplicates = tuple(
            context.service.detect_reference_duplicates(
                draft.reference,
                import_context="add-source-manual",
            )
        )
    except Exception as exc:
        ui.error(f"Database error during duplicate preview: {safe_error_message(exc)}")
        return [], False
    render_duplicate_preview(ui, duplicates)
    plan, ready = render_reference_save_plan(
        ui,
        key_prefix="add_manual_reference",
        label="manual Reference",
        reference=draft.reference,
        duplicates=duplicates,
    )
    return ([plan] if plan else []), ready


def _bibtex_reference_plans(
    ui: Any,
    context: CatalogUIContext,
) -> tuple[list[ReferenceSavePlan], bool]:
    selection = render_bibtex_input(ui, context.service, key_prefix="add")
    if not selection.drafts:
        return [], False
    plans: list[ReferenceSavePlan] = []
    ready = True
    for draft in selection.drafts:
        if draft.reference is None:
            ready = False
            continue
        raw_hash = draft.reference.bibtex.raw_sha256 or "manual"
        plan, candidate_ready = render_reference_save_plan(
            ui,
            key_prefix=f"add_bibtex_{draft.entry_index}_{raw_hash[:12]}",
            label=f"BibTeX entry {draft.entry_index}",
            reference=draft.reference,
            duplicates=draft.duplicates,
            confirmed_duplicate=draft.allow_duplicate,
        )
        if plan:
            plans.append(plan)
        ready = ready and candidate_ready
    return plans, ready and len(plans) == len(selection.drafts)


def _render_outcome(ui: Any, outcome: AddSourceOutcome) -> None:
    render_catalog_result(ui, outcome.source_result, success="Source created successfully.")
    for item in outcome.references:
        render_catalog_result(
            ui,
            item.result,
            success=f"{item.label}: {item.action} completed.",
        )
    if outcome.partial:
        ui.warning(
            "Partial result: the Source was preserved, while at least one Reference action "
            "needs correction in Edit / Analyze Source. No rollback or unrelated deletion occurred."
        )


def render_add_source_page(
    context: CatalogUIContext,
    *,
    ui: Any | None = None,
) -> None:
    """Render Add Source with preview, confirmation, and partial-safe writes."""
    if ui is None:
        import streamlit as ui

    ui.title("➕ Add Source")
    render_active_database(ui, context)
    snapshot = render_catalog_status(ui, context)
    ui.divider()
    ui.subheader("A. Basic Information")
    ui.caption("Initial status: active")
    draft = render_source_form(ui, key_prefix="add_source")

    preview_clicked = ui.button(
        "Preview Source",
        key=state_key("add_preview_button"),
        disabled=not draft.valid,
    )
    if preview_clicked and draft.source is not None:
        ui.session_state[ADD_PREVIEW_KEY] = {
            "values": dict(draft.values),
            "source": draft.source,
        }
    elif not draft.valid:
        _show_form_errors(ui, draft)

    stored = ui.session_state.get(ADD_PREVIEW_KEY)
    source: Source | None = None
    if isinstance(stored, dict) and stored.get("values") == dict(draft.values):
        candidate = stored.get("source")
        source = candidate if isinstance(candidate, Source) else None
    elif stored is not None:
        ui.warning("Basic fields changed. Run Duplicate Preview again before saving.")

    source_duplicates: list[Any] = []
    source_confirmed = False
    if source is not None:
        ui.subheader("B. Duplicate Preview")
        ui.write(
            {
                "source_id_generated": source.source_id,
                "name": source.name,
                "type": source.source_type.value,
                "aliases": [alias.value for alias in source.aliases],
                "status": source.status.value,
            }
        )
        try:
            source_duplicates = context.service.detect_source_duplicates(source)
            render_duplicate_preview(ui, source_duplicates)
        except Exception as exc:
            ui.error(f"Database error during duplicate preview: {safe_error_message(exc)}")
            source = None
        if source is not None and duplicate_confirmation_required(source_duplicates):
            source_fingerprint = draft_fingerprint(source)
            source_confirmed = ui.checkbox(
                "I reviewed exact/strong/possible Source matches and want a separate Source",
                key=state_key("add_source_allow_duplicate", source_fingerprint),
            )

    ui.subheader("C. Optional References")
    reference_mode = ui.radio(
        "Reference input",
        REFERENCE_MODES,
        horizontal=True,
        key=state_key("add_reference_mode"),
    )
    plans: list[ReferenceSavePlan] = []
    references_ready = True
    if reference_mode == "Manual":
        plans, references_ready = _manual_reference_plan(ui, context)
    elif reference_mode == "Paste / Upload BibTeX":
        ui.subheader("D. BibTeX Preview")
        plans, references_ready = _bibtex_reference_plans(ui, context)

    ui.subheader("E. Save Workflow")
    if source is not None:
        ui.write(
            f"Summary: create Source `{source.source_id}` in `{context.database_name}` "
            f"and process {len(plans)} Reference action(s)."
        )
    source_ready = source is not None and allow_source_creation(
        source_duplicates,
        confirmed=source_confirmed,
    )
    catalog_ready = snapshot is not None and snapshot.initialized
    if not catalog_ready:
        ui.warning("Initialize or repair the catalog indexes explicitly before writing.")
    with ui.form(key=state_key("add_save_form")):
        final_confirmation = ui.checkbox(
            f"Confirm write exclusively to {context.database_name}",
            key=state_key("add_final_confirmation"),
        )
        submitted = ui.form_submit_button(
            "Create Source and selected References",
            disabled=not (source_ready and references_ready and catalog_ready),
        )
    save_clicked = submitted and final_confirmation
    if submitted and not final_confirmation:
        ui.warning("Nothing was written: confirm the real active database before submitting.")
    if save_clicked and source is not None:
        token = f"{context.database_name}:{source.source_id}"
        if not begin_operation(ui.session_state, "add_source", token):
            ui.info("This confirmed Source submission was already processed.")
            return
        succeeded = False
        try:
            outcome = execute_add_source(
                context.service,
                source,
                plans,
                allow_duplicate_source=bool(source_duplicates),
            )
            _render_outcome(ui, outcome)
            succeeded = outcome.source_created
            if outcome.source_created and outcome.source_result.value is not None:
                created_source_id = outcome.source_result.value.source_id
                ui.session_state[SELECTED_SOURCE_ID] = created_source_id
                clear_state_group(ui.session_state, "add")
                ui.session_state[RECENT_CREATED_SOURCE_ID] = created_source_id
        except Exception as exc:
            ui.error(f"Unexpected safe workflow error: {safe_error_message(exc)}")
        finally:
            finish_operation(
                ui.session_state,
                "add_source",
                token,
                succeeded=succeeded,
            )

    recent_source_id = ui.session_state.get(RECENT_CREATED_SOURCE_ID)
    if isinstance(recent_source_id, str) and ui.button(
        "Open newly created Source in Edit / Analyze Source",
        key=state_key("open_created", recent_source_id),
    ):
        request_navigation(
            ui.session_state,
            EDIT_SOURCE_NAV_LABEL,
            source_id=recent_source_id,
        )
        ui.rerun()


__all__ = [
    "ADD_PREVIEW_KEY",
    "RECENT_CREATED_SOURCE_ID",
    "REFERENCE_MODES",
    "render_add_source_page",
]

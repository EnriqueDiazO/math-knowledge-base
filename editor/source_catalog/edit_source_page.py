"""Streamlit Edit / Analyze Source page backed by the S1A facade."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from editor.source_catalog.bibtex_ui import render_bibtex_input
from editor.source_catalog.data_quality import incomplete_reference_fields
from editor.source_catalog.data_quality import render_data_quality
from editor.source_catalog.legacy_concepts import render_legacy_concepts
from editor.source_catalog.reference_actions import render_reference_save_plan
from editor.source_catalog.reference_form import render_reference_form
from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import render_active_database
from editor.source_catalog.shared import render_catalog_result
from editor.source_catalog.shared import render_catalog_status
from editor.source_catalog.shared import render_duplicate_preview
from editor.source_catalog.shared import safe_error_message
from editor.source_catalog.source_form import render_source_form
from editor.source_catalog.state import SELECTED_SOURCE_ID
from editor.source_catalog.state import begin_operation
from editor.source_catalog.state import clear_state_group
from editor.source_catalog.state import draft_fingerprint
from editor.source_catalog.state import finish_operation
from editor.source_catalog.state import state_key
from editor.source_catalog.workflows import ReferenceSavePlan
from editor.source_catalog.workflows import duplicate_confirmation_required
from editor.source_catalog.workflows import execute_reference_plans
from mathmongo.source_catalog.legacy_repository import LegacyConceptRepository
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import ReferenceStatus
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.models import SourceType

SOURCE_SECTIONS = (
    "Overview & Edit",
    "References",
    "Concepts — Legacy Read Only",
    "Data Quality",
    "Actions",
)
REFERENCE_UPDATE_FIELDS = (
    "reference_type",
    "bibtex",
    "authors",
    "title",
    "year",
    "year_raw",
    "journal",
    "publisher",
    "volume",
    "number",
    "edition",
    "isbn",
    "doi",
    "url",
    "accessed_at",
    "language",
    "notes",
    "provenance",
)


def _write_token(
    context: CatalogUIContext,
    action: str,
    entity_id: str,
    version: object,
) -> str:
    """Build a namespaced, database-bound token without retaining form bodies."""
    return f"{context.database_name}:{action}:{entity_id}:{version}"


def _execute_write_once(
    ui: Any,
    *,
    operation: str,
    token: str,
    action: Any,
    success: str,
) -> Any | None:
    """Execute and render one confirmed write at most once per stable token."""
    if not begin_operation(ui.session_state, operation, token):
        ui.info("This catalog operation was already processed.")
        return None
    succeeded = False
    try:
        result = action()
        render_catalog_result(ui, result, success=success)
        succeeded = bool(result.persisted)
        return result
    except Exception as exc:
        ui.error(f"Database error completing catalog action: {safe_error_message(exc)}")
        return None
    finally:
        finish_operation(
            ui.session_state,
            operation,
            token,
            succeeded=succeeded,
        )


def _reference_plan_digest(
    source_id: str,
    plans: list[ReferenceSavePlan],
) -> str:
    """Hash selected actions without putting BibTeX raw or generated IDs in state."""
    payload: list[dict[str, Any]] = []
    for plan in plans:
        if plan.existing_reference_id:
            payload.append(
                {
                    "label": plan.label,
                    "existing_reference_id": plan.existing_reference_id,
                }
            )
            continue
        candidate = (
            plan.candidate
            if isinstance(plan.candidate, Reference)
            else Reference.model_validate(plan.candidate)
        )
        data = candidate.model_dump(mode="json")
        for field_name in (
            "reference_id",
            "source_ids",
            "created_at",
            "updated_at",
            "archived_at",
        ):
            data.pop(field_name, None)
        bibtex = data.get("bibtex")
        if isinstance(bibtex, dict):
            bibtex.pop("raw", None)
        provenance = data.get("provenance")
        if isinstance(provenance, dict):
            provenance.pop("imported_at", None)
        payload.append(
            {
                "label": plan.label,
                "candidate": data,
                "allow_duplicate": plan.allow_duplicate,
            }
        )
    encoded = json.dumps(
        {"source_id": source_id, "plans": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _association_rows(context: CatalogUIContext, reference: Reference) -> list[dict[str, str]]:
    """Resolve every shared Source association without hiding missing records."""
    sources = context.source_repository.get_by_ids(reference.source_ids)
    by_id = {source.source_id: source for source in sources}
    rows: list[dict[str, str]] = []
    for source_id in reference.source_ids:
        source = by_id.get(source_id)
        rows.append(
            {
                "source_id": source_id,
                "name": source.name if source is not None else "<missing Source>",
                "status": source.status.value if source is not None else "missing",
            }
        )
    return rows


def _source_rows(items: tuple[Source, ...]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": item.source_id,
            "name": item.name,
            "type": item.source_type.value,
            "aliases": ", ".join(alias.value for alias in item.aliases),
            "tags": ", ".join(item.tags),
            "status": item.status.value,
            "updated_at": item.updated_at,
        }
        for item in items
    ]


def _reference_rows(items: tuple[Reference, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        authors = "; ".join(
            author.literal or " ".join(part for part in (author.given, author.family) if part)
            for author in item.authors
        )
        rows.append(
            {
                "reference_id": item.reference_id,
                "type": item.reference_type.value,
                "authors": authors,
                "title": item.title or "",
                "year": item.year if item.year is not None else item.year_raw or "",
                "DOI": item.doi or "",
                "ISBN": ", ".join(item.isbn),
                "citekey": item.bibtex.key or "",
                "status": item.status.value,
                "quality": ", ".join(incomplete_reference_fields(item)) or "complete",
                "associations": len(item.source_ids),
            }
        )
    return rows


def _render_source_search(ui: Any, context: CatalogUIContext) -> Source | None:
    ui.subheader("A. Search and Select")
    filters = ui.columns(4)
    with filters[0]:
        search = ui.text_input("Search", key=state_key("edit_search"))
    with filters[1]:
        status_label = ui.selectbox(
            "Status",
            ("All", "active", "archived"),
            key=state_key("edit_status_filter"),
        )
    with filters[2]:
        type_label = ui.selectbox(
            "Source type",
            ("All", *(item.value for item in SourceType)),
            key=state_key("edit_type_filter"),
        )
    with filters[3]:
        tag = ui.text_input("Tag", key=state_key("edit_tag_filter"))
    page_number = int(
        ui.number_input(
            "Source page",
            min_value=1,
            value=1,
            step=1,
            key=state_key("edit_source_page"),
        )
    )
    kwargs = {
        "page": page_number,
        "page_size": 20,
        "status": None if status_label == "All" else status_label,
        "source_type": None if type_label == "All" else type_label,
        "tag": tag.strip() or None,
    }
    try:
        page = (
            context.source_repository.search(search, **kwargs)
            if search.strip()
            else context.source_repository.list(**kwargs)
        )
    except Exception as exc:
        ui.error(f"Database error searching Sources: {safe_error_message(exc)}")
        return None
    ui.caption(f"{page.total} Sources · page {page.page} of {max(page.pages, 1)}")
    ui.dataframe(_source_rows(page.items), width="stretch", hide_index=True)
    for source in page.items:
        if ui.button(
            f"Select {source.name} ({source.source_id})",
            key=state_key("edit_select_source", source.source_id),
        ):
            ui.session_state[SELECTED_SOURCE_ID] = source.source_id
            ui.rerun()
    selected_id = ui.session_state.get(SELECTED_SOURCE_ID)
    if not isinstance(selected_id, str):
        return None
    try:
        selected = context.source_repository.get_by_id(selected_id)
    except Exception as exc:
        ui.error(f"Database error loading Source: {safe_error_message(exc)}")
        return None
    if selected is None:
        ui.session_state.pop(SELECTED_SOURCE_ID, None)
        ui.warning("The selected Source no longer exists in this database.")
    return selected


def _overview_counts(context: CatalogUIContext, source: Source) -> tuple[int, int]:
    references = context.reference_repository.count(source_id=source.source_id)
    concepts = LegacyConceptRepository(context.database).count(source)
    return references, concepts


def _render_overview_header(ui: Any, context: CatalogUIContext, source: Source) -> None:
    try:
        reference_count, concept_count = _overview_counts(context, source)
    except Exception as exc:
        ui.error(f"Database error reading overview counts: {safe_error_message(exc)}")
        reference_count, concept_count = 0, 0
    ui.subheader("B. Overview")
    ui.write(
        {
            "source_id": source.source_id,
            "name": source.name,
            "type": source.source_type.value,
            "language": source.language,
            "aliases": [alias.value for alias in source.aliases],
            "tags": source.tags,
            "description": source.description,
            "status": source.status.value,
            "rights_default": source.rights_default.model_dump(mode="json"),
            "created_at": source.created_at,
            "updated_at": source.updated_at,
            "references": reference_count,
            "legacy_concepts": concept_count,
        }
    )


def _render_source_editor(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    draft = render_source_form(
        ui,
        key_prefix=f"edit_source_{source.source_id}",
        initial=source,
    )
    if not draft.valid or draft.source is None:
        for error in draft.errors:
            ui.error(f"Validation error: {safe_error_message(error)}")
        return
    candidate = draft.source
    try:
        duplicates = context.service.detect_source_duplicates(
            candidate,
            exclude_source_id=source.source_id,
        )
    except Exception as exc:
        ui.error(f"Database error during duplicate preview: {safe_error_message(exc)}")
        return
    render_duplicate_preview(ui, duplicates)
    candidate_fingerprint = draft_fingerprint(candidate)
    preserve_old = False
    if candidate.name != source.name:
        preserve_old = ui.checkbox(
            "Preserve previous name as alias",
            value=True,
            key=state_key(
                "edit_preserve_name",
                source.source_id,
                candidate_fingerprint,
            ),
        )
    duplicate_confirmed = True
    if duplicate_confirmation_required(duplicates):
        duplicate_confirmed = ui.checkbox(
            "I reviewed exact/strong/possible Source matches",
            key=state_key(
                "edit_allow_source_duplicate",
                source.source_id,
                candidate_fingerprint,
            ),
        )
    if not writes_enabled:
        ui.warning("Read-only until the approved Source Catalog indexes are initialized.")
        return
    with ui.form(key=state_key("edit_source_save_form", source.source_id)):
        confirmed = ui.checkbox(
            f"Confirm updating {source.source_id} only in {context.database_name}",
            key=state_key("edit_source_save_confirm", source.source_id),
        )
        submitted = ui.form_submit_button(
            "Save Source changes",
            disabled=not duplicate_confirmed,
        )
    if not submitted:
        return
    if not confirmed:
        ui.warning("Confirm the Source update before saving.")
        return
    changes = {
        "name": candidate.name,
        "aliases": [alias.model_dump(mode="python") for alias in candidate.aliases],
        "source_type": candidate.source_type,
        "description": candidate.description,
        "language": candidate.language,
        "tags": candidate.tags,
        "rights_default": candidate.rights_default.model_dump(mode="python"),
    }
    token = _write_token(
        context,
        "edit_source",
        source.source_id,
        source.updated_at.isoformat(),
    )
    _execute_write_once(
        ui,
        operation=f"edit_source_{source.source_id}",
        token=token,
        action=lambda: context.service.update_source(
            source.source_id,
            changes,
            preserve_previous_name_as_alias=preserve_old,
            allow_duplicate=bool(duplicates),
        ),
        success="Source changes saved.",
    )


def _reference_changes(reference: Reference) -> dict[str, Any]:
    data = reference.model_dump(mode="python")
    return {field: data[field] for field in REFERENCE_UPDATE_FIELDS}


def _render_reference_editor(
    ui: Any,
    context: CatalogUIContext,
    reference: Reference,
    *,
    writes_enabled: bool,
) -> None:
    ui.warning(
        "This Reference is shared with multiple Sources. Edits affect all associations."
        if len(reference.source_ids) > 1
        else "Edits preserve the stable Reference ID and any BibTeX raw not explicitly replaced."
    )
    try:
        ui.write({"associations": _association_rows(context, reference)})
    except Exception as exc:
        ui.error(f"Database error resolving Source associations: {safe_error_message(exc)}")
        ui.write({"source_ids": reference.source_ids})
    draft = render_reference_form(
        ui,
        key_prefix=f"edit_reference_{reference.reference_id}",
        initial=reference,
        source_ids=reference.source_ids,
        reference_id=reference.reference_id,
    )
    if not draft.valid or draft.reference is None:
        for error in draft.errors:
            ui.error(f"Validation error: {safe_error_message(error)}")
        return
    try:
        duplicates = context.service.detect_reference_duplicates(
            draft.reference,
            exclude_reference_id=reference.reference_id,
        )
    except Exception as exc:
        ui.error(f"Database error during duplicate preview: {safe_error_message(exc)}")
        return
    render_duplicate_preview(ui, duplicates)
    candidate_fingerprint = draft_fingerprint(draft.reference)
    duplicate_confirmed = not duplicate_confirmation_required(duplicates) or ui.checkbox(
        "I reviewed exact/strong/possible Reference matches",
        key=state_key(
            "edit_reference_duplicate_confirm",
            reference.reference_id,
            candidate_fingerprint,
        ),
    )
    shared_confirmed = len(reference.source_ids) <= 1 or ui.checkbox(
        "I understand this edit affects every associated Source",
        key=state_key(
            "edit_reference_shared_confirm",
            reference.reference_id,
            candidate_fingerprint,
        ),
    )
    if not writes_enabled:
        ui.warning("Read-only until the approved Source Catalog indexes are initialized.")
        return
    with ui.form(key=state_key("edit_reference_save_form", reference.reference_id)):
        confirmed = ui.checkbox(
            f"Confirm Reference update in {context.database_name}",
            key=state_key("edit_reference_save_confirm", reference.reference_id),
        )
        submitted = ui.form_submit_button(
            "Save Reference changes",
            disabled=not (duplicate_confirmed and shared_confirmed),
        )
    if submitted:
        if not confirmed:
            ui.warning("Confirm the Reference update before saving.")
            return
        token = _write_token(
            context,
            "edit_reference",
            reference.reference_id,
            reference.updated_at.isoformat(),
        )
        _execute_write_once(
            ui,
            operation=f"edit_reference_{reference.reference_id}",
            token=token,
            action=lambda: context.service.update_reference(
                reference.reference_id,
                _reference_changes(draft.reference),
                allow_duplicate=bool(duplicates),
            ),
            success="Reference changes saved.",
        )


def _render_reference_actions(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    reference: Reference,
    *,
    writes_enabled: bool,
) -> None:
    if not writes_enabled:
        return
    shared_suffix = (
        f"; this affects all {len(reference.source_ids)} Source associations"
        if len(reference.source_ids) > 1
        else ""
    )
    if reference.status == ReferenceStatus.ARCHIVED:
        with ui.form(key=state_key("reactivate_reference_form", reference.reference_id)):
            confirmed = ui.checkbox(
                f"Confirm reactivation in {context.database_name}{shared_suffix}",
                key=state_key("reactivate_reference_confirm", reference.reference_id),
            )
            submitted = ui.form_submit_button(
                "Reactivate Reference",
            )
        if submitted:
            if not confirmed:
                ui.warning("Confirm Reference reactivation before continuing.")
                return
            token = _write_token(
                context,
                "reactivate_reference",
                reference.reference_id,
                reference.updated_at.isoformat(),
            )
            _execute_write_once(
                ui,
                operation=f"reactivate_reference_{reference.reference_id}",
                token=token,
                action=lambda: context.service.reactivate_reference(reference.reference_id),
                success="Reference reactivated.",
            )
    else:
        with ui.form(key=state_key("archive_reference_form", reference.reference_id)):
            confirmed = ui.checkbox(
                "Confirm archive (no physical deletion) only in "
                f"{context.database_name}{shared_suffix}",
                key=state_key("archive_reference_confirm", reference.reference_id),
            )
            submitted = ui.form_submit_button("Archive Reference")
        if submitted:
            if not confirmed:
                ui.warning("Confirm Reference archive before continuing.")
                return
            token = _write_token(
                context,
                "archive_reference",
                reference.reference_id,
                reference.updated_at.isoformat(),
            )
            _execute_write_once(
                ui,
                operation=f"archive_reference_{reference.reference_id}",
                token=token,
                action=lambda: context.service.archive_reference(reference.reference_id),
                success="Reference archived.",
            )

    with ui.form(
        key=state_key(
            "disassociate_reference_form",
            reference.reference_id,
            source.source_id,
        )
    ):
        confirmed = ui.checkbox(
            f"Confirm unlink from {source.source_id} only in "
            f"{context.database_name}; other associations remain",
            key=state_key(
                "disassociate_reference_confirm",
                reference.reference_id,
                source.source_id,
            ),
        )
        submitted = ui.form_submit_button("Unlink from this Source")
    if submitted:
        if not confirmed:
            ui.warning("Confirm the Reference unlink before continuing.")
            return
        token = _write_token(
            context,
            "disassociate_reference",
            reference.reference_id,
            f"{source.source_id}:{reference.updated_at.isoformat()}",
        )
        result = _execute_write_once(
            ui,
            operation=f"disassociate_reference_{reference.reference_id}_{source.source_id}",
            token=token,
            action=lambda: context.service.disassociate_reference(
                reference.reference_id,
                source.source_id,
            ),
            success="Reference unlinked from this Source.",
        )
        if result is not None and result.persisted:
            ui.session_state[state_key("detached_reference_id")] = reference.reference_id


def _render_detached_reference(
    ui: Any,
    context: CatalogUIContext,
    *,
    writes_enabled: bool,
) -> None:
    if not writes_enabled:
        return
    reference_id = ui.session_state.get(state_key("detached_reference_id"))
    if not isinstance(reference_id, str):
        return
    try:
        reference = context.reference_repository.get_by_id(reference_id)
    except Exception as exc:
        ui.error(f"Database error loading detached Reference: {safe_error_message(exc)}")
        return
    if reference is None:
        ui.session_state.pop(state_key("detached_reference_id"), None)
        return
    ui.subheader("Recently unlinked Reference")
    try:
        inspection = context.service.inspect_reference_deletion(reference.reference_id)
    except Exception as exc:
        ui.error(f"Database error inspecting Reference deletion: {safe_error_message(exc)}")
        return
    blockers = tuple(safe_error_message(value) for value in inspection.blockers)
    ui.write(
        {
            "database": context.database_name,
            "reference_id": reference.reference_id,
            "title": reference.title,
            "source_ids": reference.source_ids,
            "blockers": blockers,
            "consequence": "Permanent removal of this unused Reference only.",
        }
    )
    if not inspection.allowed:
        ui.warning("Physical deletion blocked: " + ", ".join(blockers))
        return
    with ui.form(key=state_key("delete_reference_form", reference.reference_id)):
        typed = ui.text_input(
            "Type the Reference ID to confirm physical deletion",
            key=state_key("delete_reference_typed", reference.reference_id),
        )
        confirmed = ui.checkbox(
            f"Confirm permanent deletion only in {context.database_name}",
            key=state_key("delete_reference_confirm", reference.reference_id),
        )
        submitted = ui.form_submit_button(
            "Physically delete unused Reference",
        )
    if submitted:
        if not confirmed or typed != reference.reference_id:
            ui.warning(
                "Physical deletion requires the confirmation checkbox and the exact Reference ID."
            )
            return
        token = _write_token(
            context,
            "delete_reference",
            reference.reference_id,
            reference.updated_at.isoformat(),
        )
        result = _execute_write_once(
            ui,
            operation=f"delete_reference_{reference.reference_id}",
            token=token,
            action=lambda: context.service.delete_reference_if_unused(reference.reference_id),
            success="Unused Reference physically deleted.",
        )
        if result is not None and result.persisted:
            ui.session_state.pop(state_key("detached_reference_id"), None)


def _render_add_reference(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    if not writes_enabled:
        ui.warning("Adding References is disabled until catalog indexes are initialized.")
        return
    if ui.checkbox(
        "Show Add Reference controls",
        key=state_key("edit_add_reference_open", source.source_id),
    ):
        mode = ui.radio(
            "New Reference input",
            ("Manual", "Paste / Upload BibTeX"),
            horizontal=True,
            key=state_key("edit_add_reference_mode", source.source_id),
        )
        plans: list[ReferenceSavePlan] = []
        ready = False
        if mode == "Manual":
            draft = render_reference_form(
                ui,
                key_prefix=f"edit_add_manual_{source.source_id}",
                source_ids=[source.source_id],
            )
            if draft.valid and draft.reference is not None:
                try:
                    duplicates = tuple(
                        context.service.detect_reference_duplicates(
                            draft.reference,
                            import_context="edit-source-manual",
                        )
                    )
                except Exception as exc:
                    ui.error("Database error during duplicate preview: " + safe_error_message(exc))
                    duplicates = ()
                    ready = False
                else:
                    render_duplicate_preview(ui, duplicates)
                    plan, ready = render_reference_save_plan(
                        ui,
                        key_prefix=f"edit_add_manual_{source.source_id}",
                        label="manual Reference",
                        reference=draft.reference,
                        duplicates=duplicates,
                    )
                    if plan:
                        plans.append(plan)
            else:
                for error in draft.errors:
                    ui.error(f"Validation error: {safe_error_message(error)}")
        else:
            selection = render_bibtex_input(
                ui,
                context.service,
                key_prefix=f"edit_add_{source.source_id}",
            )
            ready = bool(selection.drafts)
            for candidate in selection.drafts:
                if candidate.reference is None:
                    ready = False
                    continue
                raw_hash = candidate.reference.bibtex.raw_sha256 or "manual"
                plan, candidate_ready = render_reference_save_plan(
                    ui,
                    key_prefix=(
                        f"edit_add_bibtex_{source.source_id}_"
                        f"{candidate.entry_index}_{raw_hash[:12]}"
                    ),
                    label=f"BibTeX entry {candidate.entry_index}",
                    reference=candidate.reference,
                    duplicates=candidate.duplicates,
                    confirmed_duplicate=candidate.allow_duplicate,
                )
                ready = ready and candidate_ready
                if plan:
                    plans.append(plan)

        with ui.form(key=state_key("edit_add_reference_save_form", source.source_id)):
            confirmed = ui.checkbox(
                f"Confirm {len(plans)} Reference action(s) in {context.database_name}",
                key=state_key("edit_add_reference_confirm", source.source_id),
            )
            submitted = ui.form_submit_button(
                "Save selected Reference actions",
                disabled=not (ready and plans),
            )
        if submitted:
            if not confirmed:
                ui.warning("Confirm the Reference actions before saving.")
                return
            digest = _reference_plan_digest(source.source_id, plans)
            token = _write_token(
                context,
                "add_references",
                source.source_id,
                digest,
            )
            operation = f"add_references_{source.source_id}"
            if not begin_operation(ui.session_state, operation, token):
                ui.info("This Reference batch was already processed.")
                return
            persisted_any = False
            try:
                outcomes = execute_reference_plans(
                    context.service,
                    source.source_id,
                    plans,
                )
                for outcome in outcomes:
                    render_catalog_result(
                        ui,
                        outcome.result,
                        success=f"{outcome.label}: {outcome.action} completed.",
                    )
                persisted_any = any(item.result.persisted for item in outcomes)
                if outcomes and all(item.result.persisted for item in outcomes):
                    clear_state_group(ui.session_state, "edit_add")
                elif persisted_any:
                    ui.warning(
                        "Partial result: persisted actions were kept. Correct remaining "
                        "References from this Source before submitting a new batch."
                    )
            except Exception as exc:
                ui.error(f"Database error saving References: {safe_error_message(exc)}")
            finally:
                finish_operation(
                    ui.session_state,
                    operation,
                    token,
                    succeeded=persisted_any,
                )


def _render_references(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    ui.subheader("C. References")
    _render_add_reference(
        ui,
        context,
        source,
        writes_enabled=writes_enabled,
    )
    page_number = int(
        ui.number_input(
            "Reference page",
            min_value=1,
            value=1,
            step=1,
            key=state_key("edit_reference_page", source.source_id),
        )
    )
    try:
        page = context.reference_repository.list(
            source_id=source.source_id,
            page=page_number,
            page_size=10,
        )
    except Exception as exc:
        ui.error(f"Database error reading References: {safe_error_message(exc)}")
        return
    ui.caption(f"{page.total} References · page {page.page} of {max(page.pages, 1)}")
    ui.dataframe(_reference_rows(page.items), width="stretch", hide_index=True)
    editing_id = ui.session_state.get(state_key("editing_reference_id"))
    for reference in page.items:
        with ui.expander(
            f"{reference.title or reference.bibtex.key or reference.reference_id}",
            expanded=editing_id == reference.reference_id,
        ):
            try:
                associations = _association_rows(context, reference)
            except Exception as exc:
                ui.error("Database error resolving Source associations: " + safe_error_message(exc))
                associations = [
                    {"source_id": source_id, "name": "<unavailable>", "status": "unknown"}
                    for source_id in reference.source_ids
                ]
            ui.write(
                {
                    "reference_id": reference.reference_id,
                    "associations": associations,
                    "bibtex_key": reference.bibtex.key,
                    "bibtex_raw_sha256": reference.bibtex.raw_sha256,
                    "warnings": [
                        safe_error_message(warning) for warning in reference.provenance.warnings
                    ],
                }
            )
            if len(reference.source_ids) > 1:
                ui.warning("Shared Reference: edits affect every associated Source.")
            if ui.button(
                "Edit Reference",
                key=state_key("edit_reference_open", reference.reference_id),
            ):
                ui.session_state[state_key("editing_reference_id")] = reference.reference_id
                editing_id = reference.reference_id
            if editing_id == reference.reference_id:
                _render_reference_editor(
                    ui,
                    context,
                    reference,
                    writes_enabled=writes_enabled,
                )
            _render_reference_actions(
                ui,
                context,
                source,
                reference,
                writes_enabled=writes_enabled,
            )
    _render_detached_reference(ui, context, writes_enabled=writes_enabled)


def _render_source_actions(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    ui.subheader("F. Actions")
    if not writes_enabled:
        ui.warning("Source actions are read-only until catalog indexes are initialized.")
        return
    if source.status == SourceStatus.ARCHIVED:
        with ui.form(key=state_key("reactivate_source_form", source.source_id)):
            confirmed = ui.checkbox(
                f"Confirm reactivation only in {context.database_name}",
                key=state_key("reactivate_source_confirm", source.source_id),
            )
            submitted = ui.form_submit_button(
                "Reactivate Source",
            )
        if submitted:
            if not confirmed:
                ui.warning("Confirm Source reactivation before continuing.")
                return
            token = _write_token(
                context,
                "reactivate_source",
                source.source_id,
                source.updated_at.isoformat(),
            )
            _execute_write_once(
                ui,
                operation=f"reactivate_source_{source.source_id}",
                token=token,
                action=lambda: context.service.reactivate_source(source.source_id),
                success="Source reactivated.",
            )
    else:
        with ui.form(key=state_key("archive_source_form", source.source_id)):
            confirmed = ui.checkbox(
                f"Confirm archive as the normal removal action only in {context.database_name}",
                key=state_key("archive_source_confirm", source.source_id),
            )
            submitted = ui.form_submit_button("Archive Source")
        if submitted:
            if not confirmed:
                ui.warning("Confirm Source archive before continuing.")
                return
            token = _write_token(
                context,
                "archive_source",
                source.source_id,
                source.updated_at.isoformat(),
            )
            _execute_write_once(
                ui,
                operation=f"archive_source_{source.source_id}",
                token=token,
                action=lambda: context.service.archive_source(source.source_id),
                success="Source archived.",
            )

    if ui.button(
        "Inspect physical deletion",
        key=state_key("inspect_source_delete", source.source_id),
    ):
        ui.session_state[state_key("source_delete_inspected", source.source_id)] = True
    if not ui.session_state.get(state_key("source_delete_inspected", source.source_id)):
        return
    try:
        inspection = context.service.inspect_source_deletion(source.source_id)
        reference_count, concept_count = _overview_counts(context, source)
    except Exception as exc:
        ui.error(f"Database error inspecting deletion: {safe_error_message(exc)}")
        return
    blockers = tuple(safe_error_message(value) for value in inspection.blockers)
    ui.write(
        {
            "database": context.database_name,
            "source_id": source.source_id,
            "name": source.name,
            "references": reference_count,
            "legacy_concepts": concept_count,
            "blockers": blockers,
            "consequence": "Permanent removal of the unused Source catalog record only.",
        }
    )
    if not inspection.allowed:
        ui.error("Physical deletion blocked: " + ", ".join(blockers))
        return
    with ui.form(key=state_key("delete_source_form", source.source_id)):
        typed = ui.text_input(
            "Type the Source ID to confirm physical deletion",
            key=state_key("delete_source_typed", source.source_id),
        )
        confirmed = ui.checkbox(
            f"Confirm permanent deletion only in {context.database_name}",
            key=state_key("delete_source_confirm", source.source_id),
        )
        submitted = ui.form_submit_button(
            "Physically delete unused Source",
        )
    if submitted:
        if not confirmed or typed != source.source_id:
            ui.warning(
                "Physical deletion requires the confirmation checkbox and the exact Source ID."
            )
            return
        token = _write_token(
            context,
            "delete_source",
            source.source_id,
            source.updated_at.isoformat(),
        )
        result = _execute_write_once(
            ui,
            operation=f"delete_source_{source.source_id}",
            token=token,
            action=lambda: context.service.delete_source_if_unused(source.source_id),
            success="Unused Source physically deleted.",
        )
        if result is not None and result.persisted:
            ui.session_state.pop(SELECTED_SOURCE_ID, None)


def render_edit_source_page(
    context: CatalogUIContext,
    *,
    ui: Any | None = None,
) -> None:
    """Render bounded Source administration, References, legacy, and actions."""
    if ui is None:
        import streamlit as ui

    ui.title("✏️ Edit / Analyze Source")
    render_active_database(ui, context)
    status_snapshot = render_catalog_status(ui, context)
    writes_enabled = bool(status_snapshot is not None and status_snapshot.initialized)
    if not writes_enabled:
        ui.warning(
            "Catalog data writes are disabled until the approved index plan is initialized. "
            "Search, analysis, and legacy concepts remain read-only."
        )
    ui.divider()
    source = _render_source_search(ui, context)
    if source is None:
        ui.info("Select a Source to inspect or edit.")
        return
    _render_overview_header(ui, context, source)
    section = ui.selectbox(
        "Section",
        SOURCE_SECTIONS,
        key=state_key("edit_section", source.source_id),
    )
    if section == "Overview & Edit":
        _render_source_editor(
            ui,
            context,
            source,
            writes_enabled=writes_enabled,
        )
    elif section == "References":
        _render_references(
            ui,
            context,
            source,
            writes_enabled=writes_enabled,
        )
    elif section == "Concepts — Legacy Read Only":
        render_legacy_concepts(ui, context, source)
    elif section == "Data Quality":
        render_data_quality(ui, context, source)
    else:
        _render_source_actions(
            ui,
            context,
            source,
            writes_enabled=writes_enabled,
        )


__all__ = [
    "REFERENCE_UPDATE_FIELDS",
    "SOURCE_SECTIONS",
    "render_edit_source_page",
]

"""Streamlit Edit Source page backed by the S1A facade."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from editor.source_catalog.bibtex_ui import render_bibtex_input
from editor.source_catalog.data_quality import render_data_quality
from editor.source_catalog.document_ui import clear_source_document_preview
from editor.source_catalog.document_ui import render_source_documents
from editor.source_catalog.legacy_concepts import render_legacy_concepts
from editor.source_catalog.presentation import render_association_cards
from editor.source_catalog.presentation import render_change_cards
from editor.source_catalog.presentation import render_key_value_card
from editor.source_catalog.presentation import render_reference_summary_card
from editor.source_catalog.presentation import render_section_header
from editor.source_catalog.presentation import render_source_summary_card
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
    "Documents",
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
SOURCE_EDIT_PREVIEW_KEY = state_key("edit_source_preview")


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


def _render_source_search(ui: Any, context: CatalogUIContext) -> Source | None:
    render_section_header(ui, "Buscar y seleccionar")
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
    selected_id = ui.session_state.get(SELECTED_SOURCE_ID)
    visible_sources = list(page.items)
    if isinstance(selected_id, str) and selected_id not in {item.source_id for item in visible_sources}:
        try:
            retained = context.source_repository.get_by_id(selected_id)
        except Exception as exc:
            ui.error(f"Database error loading selected Source: {safe_error_message(exc)}")
            retained = None
        if retained is not None:
            visible_sources.insert(0, retained)

    source_by_id = {item.source_id: item for item in visible_sources}
    options = [None, *source_by_id]
    choice_key = state_key("edit_source_choice")
    current_choice = ui.session_state.get(choice_key)
    if current_choice not in options:
        ui.session_state.pop(choice_key, None)
    selected_id = ui.selectbox(
        "Source",
        options,
        index=options.index(selected_id) if selected_id in options else 0,
        format_func=lambda source_id: (
            "Selecciona una Source"
            if source_id is None
            else (
                f"{source_by_id[source_id].name} · "
                f"{source_by_id[source_id].source_type.value} · {source_id[:8]}"
            )
        ),
        key=choice_key,
    )
    if not isinstance(selected_id, str):
        return None
    previous_selected = ui.session_state.get(SELECTED_SOURCE_ID)
    if previous_selected != selected_id:
        clear_source_document_preview(ui.session_state)
        ui.session_state[SELECTED_SOURCE_ID] = selected_id
    try:
        selected = source_by_id.get(selected_id) or context.source_repository.get_by_id(selected_id)
    except Exception as exc:
        ui.error(f"Database error loading Source: {safe_error_message(exc)}")
        return None
    if selected is None:
        clear_source_document_preview(ui.session_state)
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
    render_section_header(ui, "Source seleccionada")
    render_source_summary_card(ui, source, title="Resumen")
    render_key_value_card(
        ui,
        "Actividad vinculada",
        (("References", reference_count), ("Conceptos heredados", concept_count)),
    )


def _source_changes(source: Source, candidate: Source) -> dict[str, tuple[object, object]]:
    """Return only Source fields whose user-visible values would change."""
    current_aliases = tuple(alias.value for alias in source.aliases)
    candidate_aliases = tuple(alias.value for alias in candidate.aliases)
    current_rights = source.rights_default.model_dump(mode="json")
    candidate_rights = candidate.rights_default.model_dump(mode="json")
    fields = (
        ("Nombre", source.name, candidate.name),
        ("Descripción", source.description, candidate.description),
        ("Tipo", source.source_type.value, candidate.source_type.value),
        ("Idioma", source.language, candidate.language),
        ("Aliases", current_aliases, candidate_aliases),
        ("Etiquetas", tuple(source.tags), tuple(candidate.tags)),
        ("Derechos predeterminados", current_rights, candidate_rights),
    )
    return {label: (before, after) for label, before, after in fields if before != after}


def _draft_values(draft: Any, candidate: Source) -> dict[str, Any]:
    """Use visible form values, with a model fallback for compatibility adapters."""
    values = getattr(draft, "values", None)
    if isinstance(values, dict):
        return dict(values)
    return candidate.model_dump(mode="json")


def _render_source_editor(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    if not writes_enabled:
        ui.warning("Read-only until the approved Source Catalog indexes are initialized.")
        return
    render_section_header(
        ui,
        "Editar Source",
        "Los campos permanecen como borrador local hasta que confirmes el guardado.",
    )
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
    draft_values = _draft_values(draft, candidate)
    reset_clicked = ui.button(
        "Restablecer",
        key=state_key("edit_source_reset", source.source_id),
    )
    if reset_clicked:
        clear_state_group(ui.session_state, f"edit_source_{source.source_id}")
        ui.session_state.pop(SOURCE_EDIT_PREVIEW_KEY, None)
        ui.rerun()

    preview_clicked = ui.button(
        "Vista previa de cambios",
        key=state_key("edit_source_preview_button", source.source_id),
    )
    if preview_clicked:
        ui.session_state[SOURCE_EDIT_PREVIEW_KEY] = {
            "source_id": source.source_id,
            "base_updated_at": source.updated_at.isoformat(),
            "values": draft_values,
            "candidate": candidate,
        }

    stored = ui.session_state.get(SOURCE_EDIT_PREVIEW_KEY)
    preview_candidate: Source | None = None
    if isinstance(stored, dict) and stored.get("source_id") == source.source_id:
        candidate_value = stored.get("candidate")
        if stored.get("values") == draft_values and isinstance(candidate_value, Source):
            preview_candidate = candidate_value
        else:
            ui.warning("Los campos cambiaron. Genera una nueva vista previa antes de guardar.")
    if preview_candidate is None:
        ui.info("Usa Vista previa de cambios para revisar y habilitar el guardado.")
        return

    changes = _source_changes(source, preview_candidate)
    render_change_cards(ui, changes)
    try:
        duplicates = context.service.detect_source_duplicates(
            preview_candidate,
            exclude_source_id=source.source_id,
        )
    except Exception as exc:
        ui.error(f"Database error during duplicate preview: {safe_error_message(exc)}")
        return
    render_section_header(ui, "Coincidencias")
    render_duplicate_preview(ui, duplicates)
    candidate_fingerprint = draft_fingerprint(preview_candidate)
    preserve_old = False
    if preview_candidate.name != source.name:
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
    render_section_header(ui, "Confirmar y guardar")
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
    repository = getattr(context, "source_repository", None)
    fresh_source = None
    if repository is not None and hasattr(repository, "get_by_id"):
        try:
            fresh_source = repository.get_by_id(source.source_id)
        except Exception as exc:
            ui.error(f"Database error checking Source freshness: {safe_error_message(exc)}")
            return
    preview_version = stored.get("base_updated_at") if isinstance(stored, dict) else None
    if fresh_source is not None and fresh_source.updated_at.isoformat() != preview_version:
        ui.warning("La Source cambió desde la vista previa. Revisa y confirma una nueva vista previa.")
        return
    changes = {
        "name": preview_candidate.name,
        "aliases": [alias.model_dump(mode="python") for alias in preview_candidate.aliases],
        "source_type": preview_candidate.source_type,
        "description": preview_candidate.description,
        "language": preview_candidate.language,
        "tags": preview_candidate.tags,
        "rights_default": preview_candidate.rights_default.model_dump(mode="python"),
    }
    token = _write_token(
        context,
        "edit_source",
        source.source_id,
        f"{source.updated_at.isoformat()}:{draft_fingerprint(preview_candidate)}",
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
        render_section_header(ui, "Sources asociadas")
        render_association_cards(ui, _association_rows(context, reference))
    except Exception as exc:
        ui.error(f"Database error resolving Source associations: {safe_error_message(exc)}")
        render_key_value_card(
            ui,
            "Asociaciones no disponibles",
            (("IDs de Source", reference.source_ids),),
        )
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
    render_section_header(ui, "Reference desvinculada recientemente")
    try:
        inspection = context.service.inspect_reference_deletion(reference.reference_id)
    except Exception as exc:
        ui.error(f"Database error inspecting Reference deletion: {safe_error_message(exc)}")
        return
    blockers = tuple(safe_error_message(value) for value in inspection.blockers)
    render_key_value_card(
        ui,
        "Revisión antes de borrado físico",
        (
            ("Base", context.database_name),
            ("ID de Reference", reference.reference_id),
            ("Título", reference.title),
            ("Sources asociadas", reference.source_ids),
            ("Bloqueos", blockers),
            ("Consecuencia", "Sólo elimina esta Reference sin uso."),
        ),
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
    render_section_header(ui, "References")
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
    editing_id = ui.session_state.get(state_key("editing_reference_id"))
    for reference in page.items:
        with ui.expander(
            f"{reference.title or reference.bibtex.key or reference.reference_id}",
            expanded=editing_id == reference.reference_id,
        ):
            render_reference_summary_card(ui, reference, title="Resumen de Reference")
            try:
                associations = _association_rows(context, reference)
            except Exception as exc:
                ui.error("Database error resolving Source associations: " + safe_error_message(exc))
                associations = [
                    {"source_id": source_id, "name": "<unavailable>", "status": "unknown"}
                    for source_id in reference.source_ids
                ]
            render_association_cards(ui, associations)
            render_key_value_card(
                ui,
                "Detalles técnicos",
                (
                    ("Clave BibTeX", reference.bibtex.key),
                    ("Huella del BibTeX preservado", reference.bibtex.raw_sha256),
                    (
                        "Advertencias",
                        [safe_error_message(warning) for warning in reference.provenance.warnings],
                    ),
                ),
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
    render_section_header(ui, "Acciones")
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
    render_key_value_card(
        ui,
        "Revisión antes de borrado físico",
        (
            ("Base", context.database_name),
            ("ID de Source", source.source_id),
            ("Nombre", source.name),
            ("References", reference_count),
            ("Conceptos heredados", concept_count),
            ("Bloqueos", blockers),
            ("Consecuencia", "Sólo elimina este registro de Source sin uso."),
        ),
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

    ui.title("✏️ Edit Source")
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
    elif section == "Documents":
        render_source_documents(
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

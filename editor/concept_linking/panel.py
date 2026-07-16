"""Top-level S4.3 panels embedded by Reading Space."""

from __future__ import annotations

from typing import Any

from editor.concept_linking.concept_cards import render_relationship_help
from editor.concept_linking.concept_search import get_concept
from editor.concept_linking.context import render_context_card
from editor.concept_linking.context import resolve_linking_context
from editor.concept_linking.document_concepts import render_document_concepts
from editor.concept_linking.document_concepts import render_known_concept_evidence
from editor.concept_linking.linking_wizard import render_linking_wizard
from editor.concept_linking.linking_wizard import suggestion_sections
from editor.concept_linking.page_concepts import render_page_concepts
from editor.concept_linking.page_concepts import resolve_document_evidence
from editor.concept_linking.state import ACTIVE
from editor.concept_linking.state import LAST_RESULT
from editor.concept_linking.state import SELECTED_CONCEPT_KEY
from editor.concept_linking.state import decode_concept_identity
from editor.concept_linking.state import recent_identities
from editor.concept_linking.state import start_wizard
from editor.concept_linking.state import state_key
from editor.concept_linking.state import sync_context
from editor.concept_linking.unlinked_items import find_unlinked_items
from editor.concept_linking.unlinked_items import render_unlinked_items
from editor.reading_space.state import queue_workspace_tab


def _sync(catalog_context: Any, reader: Any, ui: Any) -> None:
    document = reader.document
    sync_context(
        ui.session_state,
        connection_label=str(catalog_context.connection_label),
        database_name=str(catalog_context.database_name),
        database=catalog_context.database,
        user_scope="local",
        source_id=document.source_id,
        document_id=document.document_id,
    )


def _launch_button(ui: Any, context: Any, *, actions_enabled: bool, location: str) -> bool:
    valid_location = not context.is_pdf or isinstance(context.pdf_page, int)
    clicked = ui.button(
        context.action_label,
        key=state_key("launch", location, context.document_id),
        disabled=not valid_location,
        type="primary",
        width="stretch",
    )
    if not actions_enabled:
        ui.caption(
            "La búsqueda está disponible; inicializa Notes & Evidence en Maintenance "
            "para guardar asociaciones."
        )
    elif not valid_location:
        ui.caption("Selecciona una página PDF válida para asociar un concepto.")
    if clicked:
        start_wizard(ui.session_state, context)
        queue_workspace_tab(ui.session_state, "Conocimiento")
        ui.rerun()
    return bool(clicked)


def _resolved_state(
    catalog_context: Any,
    reader: Any,
    ui: Any,
    service: Any,
    *,
    page_map_service: Any | None,
    page_labeler: Any | None,
    evidence_page: int = 1,
) -> tuple[Any, tuple[Any, ...], tuple[Any, ...]]:
    context = resolve_linking_context(
        catalog_context,
        reader,
        session_state=ui.session_state,
        page_map_service=page_map_service,
    )
    evidence = resolve_document_evidence(
        catalog_context.database,
        service,
        document_id=context.document_id,
        status=None,
        page=evidence_page,
        page_size=100,
        page_labeler=page_labeler,
    )
    pending = find_unlinked_items(
        service,
        document_id=context.document_id,
        source_id=context.source_id,
        page_labeler=page_labeler,
    )
    return context, evidence, pending


def render_workspace_concept_panel(
    catalog_context: Any,
    reader: Any,
    *,
    ui: Any,
    service: Any,
    page_map_service: Any | None,
    page_labeler: Any | None,
    actions_enabled: bool,
    lifecycle_enabled: bool,
    legacy_panel: Any,
    focus: str | None = None,
) -> None:
    """Put concept context/actions before the existing Quick capture panel."""
    _sync(catalog_context, reader, ui)
    context, evidence, pending = _resolved_state(
        catalog_context,
        reader,
        ui,
        service,
        page_map_service=page_map_service,
        page_labeler=page_labeler,
    )
    render_context_card(ui, context)
    _launch_button(ui, context, actions_enabled=actions_enabled, location="workspace")
    if bool(ui.session_state.get(ACTIVE)):
        ui.info("Hay una asociación en curso en la pestaña Concepts.")
        if ui.button(
            "Continuar asociación",
            key=state_key("continue", context.document_id),
            width="content",
        ):
            queue_workspace_tab(ui.session_state, "Conocimiento")
            ui.rerun()
    render_page_concepts(
        ui,
        service,
        evidence,
        pdf_page=context.pdf_page,
        is_pdf=context.is_pdf,
        actions_enabled=actions_enabled,
        archive_enabled=lifecycle_enabled,
        compact=True,
    )
    render_unlinked_items(
        ui,
        pending,
        context=context,
        actions_enabled=actions_enabled,
        compact=True,
    )
    legacy_panel(
        catalog_context,
        reader,
        ui=ui,
        service=service,
        page_labeler=page_labeler,
        focus=focus,
    )


def render_concepts_tab(
    catalog_context: Any,
    reader: Any,
    *,
    ui: Any,
    service: Any,
    page_map_service: Any | None,
    page_labeler: Any | None,
    actions_enabled: bool,
    lifecycle_enabled: bool,
) -> None:
    """Render all S4.3 guided views for the selected Document."""
    _sync(catalog_context, reader, ui)
    ui.header("Concepts & Evidence")
    evidence_page = int(
        ui.number_input(
            "Página del resumen documental",
            min_value=1,
            max_value=10_000,
            value=1,
            step=1,
            key=state_key("document_evidence_page", reader.document.document_id),
            width="stretch",
        )
    )
    ui.caption("Cada página carga como máximo 100 asociaciones del Document.")
    context, evidence, pending = _resolved_state(
        catalog_context,
        reader,
        ui,
        service,
        page_map_service=page_map_service,
        page_labeler=page_labeler,
        evidence_page=evidence_page,
    )
    result_message = ui.session_state.pop(LAST_RESULT, None)
    if result_message:
        ui.success(str(result_message))
    render_context_card(ui, context)
    _launch_button(ui, context, actions_enabled=actions_enabled, location="tab")
    sections = suggestion_sections(
        catalog_context.database,
        service,
        document_evidence=evidence,
        current_page=context.pdf_page,
        is_pdf=context.is_pdf,
        recent=recent_identities(ui.session_state),
        source_id=context.source_id,
    )
    render_linking_wizard(
        ui,
        catalog_context.database,
        service,
        context=context,
        document_evidence=evidence,
        quick_sections=sections,
        actions_enabled=actions_enabled,
        page_labeler=page_labeler,
        archive_enabled=lifecycle_enabled,
    )
    render_page_concepts(
        ui,
        service,
        evidence,
        pdf_page=context.pdf_page,
        is_pdf=context.is_pdf,
        actions_enabled=actions_enabled,
        archive_enabled=lifecycle_enabled,
    )
    render_document_concepts(
        ui,
        service,
        evidence,
        context=context,
        actions_enabled=actions_enabled,
        archive_enabled=lifecycle_enabled,
    )
    render_unlinked_items(
        ui,
        pending,
        context=context,
        actions_enabled=actions_enabled,
    )
    selected = decode_concept_identity(ui.session_state.get(SELECTED_CONCEPT_KEY))
    if selected is not None:
        try:
            concept = get_concept(catalog_context.database, selected[0], selected[1])
        except Exception:
            concept = None
        if concept is not None:
            render_known_concept_evidence(
                ui,
                service,
                concept,
                current_document_id=context.document_id,
                current_source_id=context.source_id,
                page_labeler=page_labeler,
                page_map_service=page_map_service,
            )
    render_relationship_help(ui)


def render_knowledge_tab(
    catalog_context: Any,
    reader: Any,
    *,
    ui: Any,
    service: Any,
    page_map_service: Any | None,
    page_labeler: Any | None,
) -> None:
    """Render transversal concept review without a creation wizard or technical IDs."""
    _sync(catalog_context, reader, ui)
    ui.header("Conocimiento")
    ui.caption("Conceptos y evidencia vinculados a tu lectura.")
    context, evidence, pending = _resolved_state(
        catalog_context,
        reader,
        ui,
        service,
        page_map_service=page_map_service,
        page_labeler=page_labeler,
    )
    render_page_concepts(
        ui,
        service,
        evidence,
        pdf_page=context.pdf_page,
        is_pdf=context.is_pdf,
        actions_enabled=False,
        review_only=True,
    )
    render_document_concepts(
        ui,
        service,
        evidence,
        context=context,
        actions_enabled=False,
        review_only=True,
    )
    render_unlinked_items(
        ui,
        pending,
        context=context,
        actions_enabled=False,
        review_only=True,
    )


__all__ = [
    "render_concepts_tab",
    "render_knowledge_tab",
    "render_workspace_concept_panel",
]

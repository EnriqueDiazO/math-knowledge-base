"""Notes & Evidence panel integrated beside the S3 Document reader."""

from __future__ import annotations

from typing import Any

from editor.reading_annotations.evidence_panel import render_document_evidence
from editor.reading_annotations.evidence_panel import render_link_form
from editor.reading_annotations.evidence_panel import render_subject_evidence
from editor.reading_annotations.forms import ANNOTATION_KINDS
from editor.reading_annotations.forms import render_annotation_form
from editor.reading_annotations.navigation import render_open_document
from editor.reading_annotations.note_panel import render_note_panel
from editor.reading_annotations.panel_utils import enum_value
from editor.reading_annotations.panel_utils import local_match
from editor.reading_annotations.panel_utils import render_result
from editor.reading_annotations.panel_utils import result_items
from editor.reading_annotations.state import SELECTED_ANNOTATION_ID
from editor.reading_annotations.state import select_annotation
from editor.reading_annotations.state import state_key
from editor.reading_annotations.state import sync_context
from editor.source_catalog.shared import safe_error_message
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus


def _index_rows(statuses: Any) -> list[dict[str, str]]:
    return [
        {
            "collection": str(getattr(getattr(item, "spec", None), "collection", "")),
            "index": str(getattr(getattr(item, "spec", None), "name", "")),
            "state": enum_value(getattr(item, "state", "unknown")),
            "detail": str(getattr(item, "detail", "")),
        }
        for item in statuses
    ]


def _render_index_status(ui: Any, context: Any, service: Any) -> bool:
    """Inspect S4 indexes and apply only after an exact explicit confirmation."""
    manager = service.index_manager
    try:
        statuses = tuple(manager.status())
        plan = manager.plan()
    except Exception as exc:
        ui.error(f"Could not inspect Notes & Evidence indexes: {safe_error_message(exc)}")
        return False
    initialized = bool(getattr(plan, "initialized", False))
    conflicts = tuple(getattr(plan, "conflicts", ()))
    with ui.expander("Notes & Evidence index status", expanded=not initialized):
        if initialized:
            ui.success(f"Notes & Evidence initialized in {context.database_name}.")
        elif conflicts:
            ui.error("Notes & Evidence indexes have conflicts; no changes will be applied.")
        else:
            ui.info("Notes & Evidence is not initialized. Opening the panel creates no indexes.")
        ui.dataframe(_index_rows(statuses), width="stretch", hide_index=True)
        with ui.form(key=state_key("initialize_indexes_form")):
            confirmation = ui.text_input(
                "Type the real database name to initialize S4 indexes",
                key=state_key("initialize_indexes_database"),
            )
            confirmed = ui.checkbox(
                f"I confirm applying only S4 indexes in {context.database_name}",
                key=state_key("initialize_indexes_confirm"),
            )
            submitted = ui.form_submit_button(
                "Initialize Notes & Evidence indexes",
                key=state_key("initialize_indexes_submit"),
                disabled=initialized or bool(conflicts),
            )
        if submitted:
            if not confirmed or str(confirmation or "").strip() != context.database_name:
                ui.warning("Initialization requires the exact database name and confirmation.")
            else:
                try:
                    applied = manager.apply()
                except Exception as exc:
                    ui.error(f"Could not initialize S4 indexes: {safe_error_message(exc)}")
                else:
                    initialized = bool(getattr(applied, "initialized", True))
                    if initialized:
                        ui.success("Notes & Evidence indexes initialized.")
    return initialized


def annotation_rows(items: tuple[Any, ...] | list[Any]) -> list[dict[str, Any]]:
    """Return metadata-only annotation rows without interpreting quote/body."""
    return [
        {
            "kind": enum_value(item.kind),
            "status": enum_value(item.status),
            "page_number": item.page_number,
            "page_label": item.page_label,
            "tags": ", ".join(item.tags),
            "updated_at": item.updated_at,
            "annotation_id": item.annotation_id,
        }
        for item in items
    ]


def _render_annotations(
    ui: Any,
    database: Any,
    service: Any,
    *,
    document: Any,
    suggested_page: int | None,
    is_pdf: bool,
    actions_enabled: bool,
    archive_enabled: bool,
) -> None:
    document_id = document.document_id
    ui.subheader("Document Annotations")
    with ui.expander("Add Annotation", expanded=False):
        draft = render_annotation_form(
            ui,
            document_id=document_id,
            is_pdf=is_pdf,
            suggested_page=suggested_page,
            form_key="add_annotation",
            actions_enabled=actions_enabled,
        )
        if draft is not None:
            result = service.create_annotation(
                document_id,
                user_scope="local",
                kind=draft.kind,
                page_number=draft.page_number,
                page_label=draft.page_label,
                quote_text=draft.quote_text,
                body=draft.body,
                color_label=draft.color_label,
                tags=draft.tags,
            )
            if render_result(ui, result, success="Annotation added."):
                ui.rerun()

    query = ui.text_input(
        "Filter annotations by text or tags",
        key=state_key("annotation_filter", document_id),
    )
    kind_filter = ui.selectbox(
        "Filter annotations by kind",
        options=("all", *ANNOTATION_KINDS),
        key=state_key("annotation_kind_filter", document_id),
    )
    result = service.list_document_annotations(
        document_id,
        status=None,
        page=1,
        page_size=50,
        user_scope="local",
    )
    if not getattr(result, "completed", False):
        render_result(ui, result, success="Annotations loaded.")
        return
    items = tuple(
        item
        for item in result_items(result)
        if local_match(
            item,
            query=str(query or "")[:200],
            record_type=enum_value(item.kind),
            required_type=str(kind_filter),
        )
    )
    if not items:
        ui.caption("No annotations match this Document and filter.")
        return
    ui.dataframe(annotation_rows(items), width="stretch", hide_index=True)
    for item in items:
        status = enum_value(item.status)
        title = f"{enum_value(item.kind)} · page {item.page_number or 'general'} · {status}"
        with ui.expander(title, expanded=False):
            ui.write(
                {
                    "kind": enum_value(item.kind),
                    "page_number": item.page_number,
                    "page_label": item.page_label,
                    "quote_text": item.quote_text,
                    "body": item.body,
                    "color_label": item.color_label,
                    "tags": item.tags,
                    "status": status,
                }
            )
            render_open_document(
                ui,
                source_id=item.source_id,
                document_id=item.document_id,
                page_number=item.page_number,
                subject_id=item.annotation_id,
            )
            if status == "archived":
                if ui.button(
                    "Reactivate annotation",
                    key=state_key("reactivate_annotation", item.annotation_id),
                    disabled=not actions_enabled,
                ) and render_result(
                    ui,
                    service.reactivate_annotation(item.annotation_id, user_scope="local"),
                    success="Annotation reactivated.",
                ):
                    ui.rerun()
            else:
                if ui.button(
                    "Archive annotation",
                    key=state_key("archive_annotation", item.annotation_id),
                    disabled=not archive_enabled,
                ) and render_result(
                    ui,
                    service.archive_annotation(item.annotation_id, user_scope="local"),
                    success="Annotation archived.",
                ):
                    ui.rerun()
            if ui.button(
                "Edit annotation",
                key=state_key("edit_annotation", item.annotation_id),
                disabled=not actions_enabled or status == "archived",
            ):
                select_annotation(ui.session_state, item.annotation_id)
            if ui.session_state.get(SELECTED_ANNOTATION_ID) == item.annotation_id:
                draft = render_annotation_form(
                    ui,
                    document_id=document_id,
                    is_pdf=is_pdf,
                    suggested_page=item.page_number or suggested_page,
                    form_key=f"edit_annotation_{item.annotation_id}",
                    initial=item,
                    submit_label="Save Annotation",
                    actions_enabled=actions_enabled and status == "active",
                )
                if draft is not None:
                    updated = service.update_annotation(
                        item.annotation_id,
                        user_scope="local",
                        kind=draft.kind,
                        page_number=draft.page_number,
                        page_label=draft.page_label,
                        quote_text=draft.quote_text,
                        body=draft.body,
                        color_label=draft.color_label,
                        tags=draft.tags,
                    )
                    if render_result(ui, updated, success="Annotation updated."):
                        select_annotation(ui.session_state, None)
                        ui.rerun()
            show_evidence = ui.checkbox(
                "Link to Concept",
                key=state_key("show_annotation_evidence", item.annotation_id),
            )
            if show_evidence:
                render_link_form(
                    ui,
                    database,
                    service,
                    source_id=item.source_id,
                    reference_id=item.reference_id,
                    annotation_id=item.annotation_id,
                    actions_enabled=actions_enabled and status == "active",
                )
            if ui.checkbox(
                "Show existing evidence",
                key=state_key("show_annotation_links", item.annotation_id),
            ):
                render_subject_evidence(
                    ui,
                    service,
                    annotation_id=item.annotation_id,
                    note_id=None,
                )


def _references(context: Any, source_id: str) -> tuple[Any, ...]:
    try:
        page = context.reference_repository.list(source_id=source_id, page=1, page_size=100)
    except Exception:
        return ()
    return tuple(getattr(page, "items", ()))


def render_notes_and_evidence_panel(
    context: Any,
    reader: Any,
    *,
    ui: Any,
    service: Any | None = None,
) -> None:
    """Render the isolated S4 panel for one already-selected S3 ReaderContext."""
    if service is None:
        from mathmongo.reading_annotations.service import ReadingAnnotationService

        service = ReadingAnnotationService(context.database)
    document = reader.document
    sync_context(
        ui.session_state,
        connection_label=context.connection_label,
        database_name=context.database_name,
        database=context.database,
        source_id=document.source_id,
        document_id=document.document_id,
        user_scope="local",
    )
    ui.divider()
    ui.header("Notes & Evidence")
    s4_initialized = _render_index_status(ui, context, service)
    document_active = enum_value(document.status) == DocumentStatus.ACTIVE.value
    writable = s4_initialized and document_active
    if not s4_initialized:
        ui.caption(
            "Existing Notes & Evidence remain readable; writes require initialized S4 indexes."
        )
    elif not document_active:
        ui.caption(
            "The Document is archived. Document-bound creation/editing is blocked; safe lifecycle actions remain available."
        )
    is_pdf = enum_value(document.kind) == DocumentKind.PDF.value
    suggested_page = (
        getattr(getattr(reader, "reading_state", None), "current_page", None) if is_pdf else None
    )
    _render_annotations(
        ui,
        context.database,
        service,
        document=document,
        suggested_page=suggested_page,
        is_pdf=is_pdf,
        actions_enabled=writable,
        archive_enabled=s4_initialized,
    )
    render_note_panel(
        ui,
        context.database,
        service,
        document=document,
        references=_references(context, document.source_id),
        suggested_page=suggested_page,
        is_pdf=is_pdf,
        actions_enabled=s4_initialized,
        document_active=document_active,
    )
    render_document_evidence(
        ui,
        service,
        document_id=document.document_id,
        actions_enabled=s4_initialized,
    )


__all__ = ["annotation_rows", "render_notes_and_evidence_panel"]

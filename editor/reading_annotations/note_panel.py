"""Reading Note list, forms, lifecycle actions, and navigation."""

from __future__ import annotations

from typing import Any

from editor.reading_annotations.evidence_panel import render_link_form
from editor.reading_annotations.evidence_panel import render_subject_evidence
from editor.reading_annotations.forms import NOTE_TYPES
from editor.reading_annotations.forms import render_note_form
from editor.reading_annotations.navigation import render_open_document
from editor.reading_annotations.panel_utils import enum_value
from editor.reading_annotations.panel_utils import local_match
from editor.reading_annotations.panel_utils import render_result
from editor.reading_annotations.panel_utils import result_items
from editor.reading_annotations.state import SELECTED_NOTE_ID
from editor.reading_annotations.state import queue_draft_clear
from editor.reading_annotations.state import select_note
from editor.reading_annotations.state import state_key


def note_rows(items: tuple[Any, ...] | list[Any]) -> list[dict[str, Any]]:
    """Return compact metadata-only rows without rendering note text as markup."""
    return [
        {
            "title": item.title,
            "type": enum_value(item.note_type),
            "scope": "Document" if item.document_id is not None else "Source only",
            "pages": (
                f"{item.page_start}–{item.page_end}"
                if item.page_start is not None and item.page_end is not None
                else str(item.page_start or "")
            ),
            "status": enum_value(item.status),
            "tags": ", ".join(item.tags),
            "note_id": item.note_id,
        }
        for item in items
    ]


def render_note_panel(
    ui: Any,
    database: Any,
    service: Any,
    *,
    document: Any,
    references: tuple[Any, ...],
    suggested_page: int | None,
    is_pdf: bool,
    actions_enabled: bool,
    document_active: bool,
) -> None:
    """Render creation, editing, archive/reactivation, and evidence for notes."""
    document_id = document.document_id
    ui.subheader("Reading Notes")
    with ui.expander("Quick Reading Note", expanded=True):
        ui.caption("Capture a compact plain-text note for this Document or its Source.")
        draft = render_note_form(
            ui,
            source_id=document.source_id,
            document_id=document_id,
            is_pdf=is_pdf,
            suggested_page=suggested_page,
            references=references,
            form_key="quick_note",
            actions_enabled=actions_enabled,
            compact=True,
        )
        if draft is not None:
            result = service.create_note(
                source_id=document.source_id,
                document_id=draft.document_id,
                reference_id=draft.reference_id,
                user_scope="local",
                title=draft.title,
                body=draft.body,
                note_type=draft.note_type,
                page_start=draft.page_start,
                page_end=draft.page_end,
                tags=draft.tags,
            )
            if render_result(ui, result, success="Reading Note added."):
                queue_draft_clear(
                    ui.session_state,
                    form_key="quick_note",
                    document_id=document_id,
                )
                ui.rerun()

    query = ui.text_input(
        "Filter notes by title, text, or tags",
        key=state_key("note_filter", document_id),
    )
    type_filter = ui.selectbox(
        "Filter notes by type",
        options=("all", *NOTE_TYPES),
        key=state_key("note_type_filter", document_id),
    )
    result = service.list_document_notes(
        document_id,
        status=None,
        page=1,
        page_size=50,
        user_scope="local",
    )
    if not getattr(result, "completed", False):
        render_result(ui, result, success="Reading Notes loaded.")
        return
    source_result = service.list_source_notes(
        document.source_id,
        status=None,
        page=1,
        page_size=50,
        user_scope="local",
        source_only=True,
    )
    if not getattr(source_result, "completed", False):
        render_result(ui, source_result, success="Source Reading Notes loaded.")
        return
    combined = list(result_items(result))
    seen = {item.note_id for item in combined}
    combined.extend(item for item in result_items(source_result) if item.note_id not in seen)
    items = tuple(
        item
        for item in combined
        if local_match(
            item,
            query=str(query or "")[:200],
            record_type=enum_value(item.note_type),
            required_type=str(type_filter),
        )
    )
    if not items:
        ui.caption("No Reading Notes match this Document and filter.")
        return
    document_notes = tuple(item for item in items if item.document_id is not None)
    source_notes = tuple(item for item in items if item.document_id is None)
    for label, values in (
        ("Document Notes", document_notes),
        ("Source-only Notes", source_notes),
    ):
        if values:
            ui.caption(f"{label} · {len(values)}")
            ui.dataframe(note_rows(values), width="stretch", hide_index=True)
    for item in (*document_notes, *source_notes):
        status = enum_value(item.status)
        note_write_enabled = actions_enabled and (item.document_id is None or document_active)
        with ui.expander(f"{item.title} · {enum_value(item.note_type)} · {status}"):
            ui.write(
                {
                    "title": item.title,
                    "body": item.body,
                    "note_type": enum_value(item.note_type),
                    "page_start": item.page_start,
                    "page_end": item.page_end,
                    "tags": item.tags,
                    "reference_id": item.reference_id,
                    "status": status,
                }
            )
            render_open_document(
                ui,
                source_id=item.source_id,
                document_id=item.document_id,
                page_number=item.page_start,
                subject_id=item.note_id,
            )
            if status == "archived":
                if ui.button(
                    "Reactivate note",
                    key=state_key("reactivate_note", item.note_id),
                    disabled=not actions_enabled,
                ) and render_result(
                    ui,
                    service.reactivate_note(item.note_id, user_scope="local"),
                    success="Reading Note reactivated.",
                ):
                    ui.rerun()
            else:
                if ui.button(
                    "Archive note",
                    key=state_key("archive_note", item.note_id),
                    disabled=not actions_enabled,
                ) and render_result(
                    ui,
                    service.archive_note(item.note_id, user_scope="local"),
                    success="Reading Note archived.",
                ):
                    ui.rerun()
            if ui.button(
                "Edit note",
                key=state_key("edit_note", item.note_id),
                disabled=not note_write_enabled or status == "archived",
            ):
                select_note(ui.session_state, item.note_id)
            if ui.session_state.get(SELECTED_NOTE_ID) == item.note_id:
                draft = render_note_form(
                    ui,
                    source_id=item.source_id,
                    document_id=document_id,
                    is_pdf=is_pdf,
                    suggested_page=item.page_start or suggested_page,
                    references=references,
                    form_key=f"edit_note_{item.note_id}",
                    initial=item,
                    submit_label="Save Reading Note",
                    actions_enabled=note_write_enabled and status == "active",
                )
                if draft is not None:
                    updated = service.update_note(
                        item.note_id,
                        user_scope="local",
                        title=draft.title,
                        body=draft.body,
                        note_type=draft.note_type,
                        document_id=draft.document_id,
                        reference_id=draft.reference_id,
                        page_start=draft.page_start,
                        page_end=draft.page_end,
                        tags=draft.tags,
                    )
                    if render_result(ui, updated, success="Reading Note updated."):
                        queue_draft_clear(
                            ui.session_state,
                            form_key=f"edit_note_{item.note_id}",
                            document_id=document_id,
                        )
                        select_note(ui.session_state, None)
                        ui.rerun()
            show_evidence = ui.checkbox(
                "Link to Concept",
                key=state_key("show_note_evidence", item.note_id),
            )
            if show_evidence:
                render_link_form(
                    ui,
                    database,
                    service,
                    source_id=item.source_id,
                    reference_id=item.reference_id,
                    note_id=item.note_id,
                    actions_enabled=(note_write_enabled and status == "active"),
                )
            if ui.checkbox(
                "Show existing evidence",
                key=state_key("show_note_links", item.note_id),
            ):
                render_subject_evidence(
                    ui,
                    database,
                    service,
                    annotation_id=None,
                    note_id=item.note_id,
                    manage_lifecycle=item.document_id is None,
                    actions_enabled=actions_enabled,
                )


__all__ = ["note_rows", "render_note_panel"]

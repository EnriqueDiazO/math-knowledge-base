"""Bounded discovery and cards for Annotation/ReadingNote items without concepts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from editor.concept_linking.concept_cards import compact_text
from editor.concept_linking.state import start_wizard
from editor.concept_linking.state import state_key
from editor.concept_linking.view_models import ConceptLinkingContext
from editor.concept_linking.view_models import UnlinkedItem
from editor.reading_space.state import queue_workspace_tab

PageLabeler = Callable[[int], str | None]


def _items(result: Any) -> tuple[Any, ...]:
    if not bool(getattr(result, "completed", False)):
        return ()
    return tuple(getattr(getattr(result, "value", None), "items", ()))


def _has_evidence(service: Any, *, annotation_id: str | None, note_id: str | None) -> bool:
    try:
        if annotation_id:
            result = service.list_annotation_evidence(
                annotation_id, status=None, page=1, page_size=1
            )
        else:
            result = service.list_note_evidence(note_id, status=None, page=1, page_size=1)
    except Exception:
        return True
    if not bool(getattr(result, "completed", False)):
        return True
    return bool(getattr(getattr(result, "value", None), "total", 0))


def _book_page(page_labeler: PageLabeler | None, page: int | None) -> str | None:
    if page_labeler is None or not isinstance(page, int):
        return None
    try:
        return page_labeler(page)
    except Exception:
        return None


def find_unlinked_items(
    service: Any,
    *,
    document_id: str,
    source_id: str | None = None,
    page_labeler: PageLabeler | None = None,
    limit: int = 50,
) -> tuple[UnlinkedItem, ...]:
    """Inspect a bounded active working set through existing repositories/services."""
    size = max(1, min(int(limit), 50))
    try:
        annotations = _items(
            service.list_document_annotations(
                document_id,
                status="active",
                page=1,
                page_size=size,
                user_scope="local",
            )
        )
        notes = _items(
            service.list_document_notes(
                document_id,
                status="active",
                page=1,
                page_size=size,
                user_scope="local",
            )
        )
    except Exception:
        return ()
    source_notes: tuple[Any, ...] = ()
    if source_id and hasattr(service, "list_source_notes"):
        try:
            source_notes = _items(
                service.list_source_notes(
                    source_id,
                    status="active",
                    page=1,
                    page_size=size,
                    user_scope="local",
                    source_only=True,
                )
            )
        except Exception:
            source_notes = ()
    seen_note_ids = {item.note_id for item in notes}
    notes = (*notes, *(item for item in source_notes if item.note_id not in seen_note_ids))
    result: list[UnlinkedItem] = []
    for item in annotations:
        if _has_evidence(service, annotation_id=item.annotation_id, note_id=None):
            continue
        excerpt = compact_text(item.quote_text or item.body)
        result.append(
            UnlinkedItem(
                target_kind="annotation",
                target_id=item.annotation_id,
                item_type=str(getattr(item.kind, "value", item.kind)),
                title="Cita o anotación",
                excerpt=excerpt,
                pdf_page=item.page_number,
                book_page_label=_book_page(page_labeler, item.page_number),
                tags=tuple(item.tags),
                status=str(getattr(item.status, "value", item.status)),
            )
        )
    for item in notes:
        if _has_evidence(service, annotation_id=None, note_id=item.note_id):
            continue
        result.append(
            UnlinkedItem(
                target_kind="note",
                target_id=item.note_id,
                item_type=str(getattr(item.note_type, "value", item.note_type)),
                title=compact_text(item.title, limit=100) or "Nota de lectura",
                excerpt=compact_text(item.body),
                pdf_page=item.page_start,
                book_page_label=_book_page(page_labeler, item.page_start),
                tags=tuple(item.tags),
                status=str(getattr(item.status, "value", item.status)),
            )
        )
    result.sort(
        key=lambda item: (
            item.pdf_page is None,
            item.pdf_page or 0,
            item.target_kind,
            item.target_id,
        )
    )
    return tuple(result[:size])


def render_unlinked_items(
    ui: Any,
    items: tuple[UnlinkedItem, ...],
    *,
    context: ConceptLinkingContext,
    actions_enabled: bool,
    compact: bool = False,
) -> None:
    """Render grouped pending cards and launch a pre-targeted wizard."""
    ui.subheader("Pendientes de vincular")
    if not items:
        ui.caption("No hay anotaciones ni notas activas pendientes.")
        return
    visible = items[:3] if compact else items
    last_location: str | None = None
    for item in visible:
        if item.location_label != last_location:
            ui.caption(item.location_label)
            last_location = item.location_label
        with ui.container(border=True):
            ui.write(f"[{item.item_type}] {item.title}")
            if item.excerpt:
                ui.write(item.excerpt)
            if item.tags:
                ui.caption(f"Tags: {', '.join(item.tags[:5])}")
            ui.caption("Sin concepto asociado")
            clicked = ui.button(
                "Asociar concepto",
                key=state_key("link_pending", item.target_kind, item.target_id),
                disabled=not actions_enabled,
                width="content",
            )
        if clicked:
            start_wizard(
                ui.session_state,
                context,
                target_kind=item.target_kind,
                target_id=item.target_id,
                pdf_page=item.pdf_page,
            )
            queue_workspace_tab(ui.session_state, "Concepts")
            ui.rerun()
    if compact and len(items) > len(visible):
        ui.caption(f"{len(items) - len(visible)} pendientes más en la pestaña Concepts.")


__all__ = ["find_unlinked_items", "render_unlinked_items"]

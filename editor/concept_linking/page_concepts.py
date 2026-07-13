"""Resolve and render concept evidence for the current PDF page or web resource."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from editor.concept_linking.concept_cards import compact_text
from editor.concept_linking.concept_cards import human_link_type
from editor.concept_linking.concept_search import MAX_BATCH_SIZE
from editor.concept_linking.concept_search import get_concepts
from editor.concept_linking.navigation import open_evidence
from editor.concept_linking.state import state_key
from editor.concept_linking.view_models import ConceptSummary
from editor.concept_linking.view_models import EvidenceView

PageLabeler = Callable[[int], str | None]


def _status(value: object) -> str:
    return str(getattr(value, "value", value or ""))


def _items(result: Any) -> tuple[Any, ...]:
    if not bool(getattr(result, "completed", False)):
        return ()
    return tuple(getattr(getattr(result, "value", None), "items", ()))


def _target(service: Any, item: Any, cache: dict[tuple[str, str], Any]) -> Any | None:
    if item.annotation_id:
        identity = ("annotation", item.annotation_id)
        getter = service.get_annotation
    elif item.note_id:
        identity = ("note", item.note_id)
        getter = service.get_note
    else:
        return None
    if identity not in cache:
        try:
            result = getter(identity[1], user_scope="local")
        except Exception:
            result = None
        cache[identity] = (
            getattr(result, "value", None) if bool(getattr(result, "completed", False)) else None
        )
    return cache[identity]


def resolve_document_evidence(
    database: Any,
    service: Any,
    *,
    document_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 100,
    page_labeler: PageLabeler | None = None,
) -> tuple[EvidenceView, ...]:
    """Resolve one bounded server-side page of evidence into presentation metadata."""
    try:
        listed = service.list_document_evidence(
            document_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    except Exception:
        return ()
    links = _items(listed)
    identities = tuple(
        dict.fromkeys((item.concept_legacy_id, item.concept_legacy_source) for item in links)
    )
    try:
        concepts = {
            item.identity: item
            for item in get_concepts(
                database,
                identities,
                limit=min(page_size, MAX_BATCH_SIZE),
            )
        }
    except Exception:
        concepts = {}
    target_cache: dict[tuple[str, str], Any] = {}
    views: list[EvidenceView] = []
    for item in links:
        identity = (item.concept_legacy_id, item.concept_legacy_source)
        concept = concepts.get(identity) or ConceptSummary(
            concept_id=identity[0],
            concept_source=identity[1],
            title="Concepto no disponible",
            concept_type="",
        )
        target = _target(service, item, target_cache)
        if item.annotation_id:
            origin_kind = "annotation"
            origin_label = "Cita o anotación"
            pdf_page = getattr(target, "page_number", None)
            pdf_page_end = pdf_page
            excerpt = compact_text(
                getattr(target, "quote_text", None) or getattr(target, "body", None)
            )
            resolved_document_id = getattr(target, "document_id", None)
        elif item.note_id:
            origin_kind = "note"
            origin_label = "Nota de lectura"
            pdf_page = getattr(target, "page_start", None)
            pdf_page_end = getattr(target, "page_end", None) or pdf_page
            title = compact_text(getattr(target, "title", None), limit=80)
            body = compact_text(getattr(target, "body", None))
            excerpt = f"{title}: {body}" if title and body else title or body
            resolved_document_id = getattr(target, "document_id", None)
        else:
            origin_kind = "page"
            origin_label = "Página directa"
            pdf_page = item.page_number
            pdf_page_end = pdf_page
            excerpt = ""
            resolved_document_id = item.document_id
        book_page = None
        if isinstance(pdf_page, int) and page_labeler is not None:
            try:
                book_page = page_labeler(pdf_page)
            except Exception:
                book_page = None
        views.append(
            EvidenceView(
                evidence_link_id=item.evidence_link_id,
                concept=concept,
                link_type=_status(item.link_type),
                link_type_label=human_link_type(item.link_type),
                origin_kind=origin_kind,
                origin_label=origin_label,
                source_id=item.source_id,
                reference_id=item.reference_id,
                document_id=resolved_document_id,
                annotation_id=item.annotation_id,
                note_id=item.note_id,
                pdf_page=pdf_page,
                pdf_page_end=pdf_page_end,
                book_page_label=book_page,
                excerpt=excerpt,
                comment=compact_text(item.comment),
                status=_status(item.status),
            )
        )
    document_counts: dict[tuple[str, str], int] = {}
    for view in views:
        document_counts[view.concept.identity] = document_counts.get(view.concept.identity, 0) + 1
    return tuple(
        replace(
            view,
            concept=replace(
                view.concept,
                document_evidence_count=document_counts[view.concept.identity],
            ),
        )
        for view in views
    )


def evidence_for_page(
    evidence: tuple[EvidenceView, ...], pdf_page: int | None
) -> tuple[EvidenceView, ...]:
    """Filter direct/Annotation pages and ReadingNote ranges in memory."""
    if pdf_page is None:
        return evidence
    return tuple(
        item
        for item in evidence
        if item.pdf_page is not None
        and item.pdf_page <= pdf_page <= (item.pdf_page_end or item.pdf_page)
    )


def render_evidence_card(
    ui: Any,
    service: Any,
    item: EvidenceView,
    *,
    actions_enabled: bool,
    archive_enabled: bool | None = None,
    card_key: str,
) -> None:
    """Render one evidence relation without technical identities in the main card."""
    with ui.container(border=True):
        ui.subheader(item.concept.display_title)
        concept_type = f" · {item.concept.concept_type}" if item.concept.concept_type else ""
        ui.caption(f"{item.link_type_label}{concept_type}")
        ui.caption(f"Origen: {item.origin_label} · {item.location_label}")
        if item.excerpt:
            ui.write(item.excerpt)
        if item.comment:
            ui.caption(f"¿Por qué es relevante? {item.comment}")
        ui.caption(f"Estado: {item.status}")
        open_clicked = ui.button(
            "Abrir evidencia",
            key=state_key("open_evidence", card_key),
            width="content",
        )
        if item.status == "archived":
            lifecycle_clicked = ui.button(
                "Reactivar",
                key=state_key("reactivate_evidence", card_key),
                disabled=not actions_enabled,
                width="content",
            )
        else:
            lifecycle_clicked = ui.button(
                "Archivar",
                key=state_key("archive_evidence", card_key),
                disabled=not (actions_enabled if archive_enabled is None else archive_enabled),
                width="content",
            )
        with ui.expander("Detalles técnicos", expanded=False):
            ui.write(
                {
                    "evidence_link_id": item.evidence_link_id,
                    "annotation_id": item.annotation_id,
                    "note_id": item.note_id,
                    "document_id": item.document_id,
                    "concept_legacy_id": item.concept.concept_id,
                    "concept_legacy_source": item.concept.concept_source,
                }
            )
    if open_clicked:
        open_evidence(ui, item)
    if not lifecycle_clicked:
        return
    try:
        result = (
            service.reactivate_evidence_link(item.evidence_link_id)
            if item.status == "archived"
            else service.archive_evidence_link(item.evidence_link_id)
        )
    except Exception:
        result = None
    if bool(getattr(result, "completed", False)):
        ui.success("Evidencia reactivada." if item.status == "archived" else "Evidencia archivada.")
        ui.rerun()
    else:
        ui.error("No se pudo actualizar el estado de la evidencia.")


def render_page_concepts(
    ui: Any,
    service: Any,
    evidence: tuple[EvidenceView, ...],
    *,
    pdf_page: int | None,
    is_pdf: bool,
    actions_enabled: bool,
    archive_enabled: bool | None = None,
    compact: bool = False,
) -> tuple[EvidenceView, ...]:
    """Render the visible current-page/resource concept group."""
    current = evidence_for_page(evidence, pdf_page) if is_pdf else evidence
    ui.subheader("Conceptos en esta página" if is_pdf else "Conceptos en este recurso")
    if not current:
        ui.caption("Todavía no hay conceptos asociados aquí.")
        return ()
    limit = 3 if compact else len(current)
    for item in current[:limit]:
        render_evidence_card(
            ui,
            service,
            item,
            actions_enabled=actions_enabled,
            archive_enabled=archive_enabled,
            card_key=item.evidence_link_id,
        )
    if compact and len(current) > limit:
        ui.caption(f"{len(current) - limit} asociaciones más en la pestaña Concepts.")
    return current


__all__ = [
    "PageLabeler",
    "evidence_for_page",
    "render_evidence_card",
    "render_page_concepts",
    "resolve_document_evidence",
]

"""Document-wide and selected-concept evidence summaries."""

# ruff: noqa: D101,D102

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from editor.concept_linking.concept_cards import compact_text
from editor.concept_linking.concept_cards import human_link_type
from editor.concept_linking.page_concepts import render_evidence_card
from editor.concept_linking.state import select_concept
from editor.concept_linking.state import start_wizard
from editor.concept_linking.state import state_key
from editor.concept_linking.view_models import ConceptLinkingContext
from editor.concept_linking.view_models import ConceptSummary
from editor.concept_linking.view_models import EvidenceView
from editor.reading_space.state import queue_workspace_tab


@dataclass(frozen=True, slots=True)
class DocumentConceptGroup:
    concept: ConceptSummary
    evidence: tuple[EvidenceView, ...]

    @property
    def pages(self) -> tuple[str, ...]:
        values: list[str] = []
        for item in self.evidence:
            label = item.location_label
            if label != "Sin página" and label not in values:
                values.append(label)
        return tuple(values)

    @property
    def link_types(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.link_type_label for item in self.evidence))


def group_document_evidence(
    evidence: tuple[EvidenceView, ...],
) -> tuple[DocumentConceptGroup, ...]:
    """Group a bounded evidence page by exact legacy concept identity."""
    grouped: dict[tuple[str, str], list[EvidenceView]] = {}
    order: list[tuple[str, str]] = []
    for item in evidence:
        identity = item.concept.identity
        if identity not in grouped:
            grouped[identity] = []
            order.append(identity)
        grouped[identity].append(item)
    return tuple(
        DocumentConceptGroup(grouped[identity][0].concept, tuple(grouped[identity]))
        for identity in order
    )


def render_document_concepts(
    ui: Any,
    service: Any,
    evidence: tuple[EvidenceView, ...],
    *,
    context: ConceptLinkingContext,
    actions_enabled: bool,
    archive_enabled: bool | None = None,
    review_only: bool = False,
) -> tuple[DocumentConceptGroup, ...]:
    """Render document concepts as grouped cards rather than a technical table."""
    ui.subheader("Conceptos del documento")
    groups = group_document_evidence(evidence)
    if not groups:
        ui.caption("Este documento todavía no tiene evidencia conceptual.")
        return ()
    for group in groups:
        with ui.container(border=True):
            ui.subheader(group.concept.display_title)
            count = len(group.evidence)
            ui.caption(f"{count} {'evidencia' if count == 1 else 'evidencias'}")
            if group.pages:
                ui.caption(f"Páginas: {'; '.join(group.pages[:6])}")
            ui.caption(f"Tipos: {', '.join(group.link_types)}")
            additional = False
            if not review_only:
                additional = ui.button(
                    "Crear evidencia adicional",
                    key=state_key(
                        "additional_evidence",
                        group.concept.concept_source,
                        group.concept.concept_id,
                    ),
                    disabled=not actions_enabled,
                    width="content",
                )
            with ui.expander("Expandir evidencias", expanded=False):
                for item in group.evidence:
                    render_evidence_card(
                        ui,
                        service,
                        item,
                        actions_enabled=actions_enabled,
                        archive_enabled=archive_enabled,
                        card_key=f"document_{item.evidence_link_id}",
                        review_only=review_only,
                    )
        if additional:
            start_wizard(ui.session_state, context)
            select_concept(
                ui.session_state,
                group.concept.concept_id,
                group.concept.concept_source,
            )
            queue_workspace_tab(ui.session_state, "Conocimiento")
            ui.rerun()
    return groups


def _target_context(
    service: Any,
    item: Any,
    cache: dict[tuple[str, str], Any],
) -> tuple[str | None, int | None, int | None, str]:
    if item.annotation_id:
        identity = ("annotation", item.annotation_id)
        if identity not in cache:
            try:
                result = service.get_annotation(item.annotation_id, user_scope="local")
            except Exception:
                result = None
            cache[identity] = (
                getattr(result, "value", None)
                if bool(getattr(result, "completed", False))
                else None
            )
        target = cache[identity]
        page = getattr(target, "page_number", None)
        return (
            getattr(target, "document_id", None),
            page,
            page,
            "Cita o anotación",
        )
    if item.note_id:
        identity = ("note", item.note_id)
        if identity not in cache:
            try:
                result = service.get_note(item.note_id, user_scope="local")
            except Exception:
                result = None
            cache[identity] = (
                getattr(result, "value", None)
                if bool(getattr(result, "completed", False))
                else None
            )
        target = cache[identity]
        return (
            getattr(target, "document_id", None),
            getattr(target, "page_start", None),
            getattr(target, "page_end", None),
            "Nota de lectura",
        )
    return item.document_id, item.page_number, item.page_number, "Página directa"


def _repository_get(repository: Any, identity: str | None) -> Any | None:
    if not identity:
        return None
    try:
        return repository.get_by_id(identity)
    except Exception:
        return None


def render_known_concept_evidence(
    ui: Any,
    service: Any,
    concept: ConceptSummary,
    *,
    current_document_id: str,
    current_source_id: str,
    page_labeler: Any | None = None,
    page_map_service: Any | None = None,
) -> None:
    """Render one paginated cross-document read-only evidence view."""
    ui.subheader("Evidencias conocidas")
    page = int(
        ui.number_input(
            "Página de evidencias",
            min_value=1,
            max_value=10_000,
            value=1,
            step=1,
            key=state_key("known_evidence_page", concept.concept_source, concept.concept_id),
            width="stretch",
        )
    )
    try:
        result = service.list_concept_evidence(
            concept.concept_id,
            concept.concept_source,
            status=None,
            page=page,
            page_size=20,
        )
    except Exception:
        result = None
    if not bool(getattr(result, "completed", False)):
        ui.warning("No se pudieron cargar las evidencias conocidas.")
        return
    value = getattr(result, "value", None)
    items = tuple(getattr(value, "items", ()))
    total = int(getattr(value, "total", len(items)) or 0)
    if not items:
        ui.caption("Este concepto todavía no tiene evidencias documentales.")
        return
    groups: dict[str, list[tuple[Any, str | None, int | None, int | None, str]]] = {
        "En el documento actual": [],
        "En la Source actual": [],
        "En otros Documents": [],
    }
    target_cache: dict[tuple[str, str], Any] = {}
    metadata_cache: dict[tuple[str, str], Any] = {}

    def metadata(kind: str, repository: Any, identity: str | None) -> Any | None:
        if not identity:
            return None
        key = (kind, identity)
        if key not in metadata_cache:
            metadata_cache[key] = _repository_get(repository, identity)
        return metadata_cache[key]

    def book_label(document_id: str | None, page_number: int) -> str | None:
        if document_id == current_document_id and page_labeler is not None:
            try:
                return page_labeler(page_number)
            except Exception:
                return None
        if not document_id or page_map_service is None:
            return None
        try:
            result = page_map_service.compute_page_label(
                document_id,
                page_number,
                user_scope="local",
            )
        except Exception:
            return None
        if not bool(getattr(result, "completed", False)):
            return None
        return getattr(getattr(result, "value", None), "book_page_label", None)

    for item in items:
        document_id, pdf_page, pdf_page_end, origin = _target_context(
            service,
            item,
            target_cache,
        )
        if document_id == current_document_id:
            group = "En el documento actual"
        elif item.source_id == current_source_id:
            group = "En la Source actual"
        else:
            group = "En otros Documents"
        groups[group].append((item, document_id, pdf_page, pdf_page_end, origin))
    ui.caption(f"{total} evidencias · página {page} de {getattr(value, 'pages', 0) or 1}")
    for heading, entries in groups.items():
        if not entries:
            continue
        ui.write(heading)
        for item, document_id, pdf_page, pdf_page_end, origin in entries:
            document = metadata("document", service.documents, document_id)
            source = metadata("source", service.sources, item.source_id)
            reference = metadata("reference", service.references, item.reference_id)
            with ui.container(border=True):
                ui.write(getattr(document, "title", None) or "Documento no disponible")
                ui.caption(f"Source: {getattr(source, 'name', None) or 'Source no disponible'}")
                ui.caption(
                    f"Reference: {getattr(reference, 'title', None) or 'Sin Reference asociada'}"
                )
                if isinstance(pdf_page, int):
                    book_page = book_label(document_id, pdf_page)
                    location = (
                        f"Book page {book_page} · PDF page {pdf_page}"
                        if book_page
                        else f"PDF page {pdf_page}"
                    )
                    if isinstance(pdf_page_end, int) and pdf_page_end != pdf_page:
                        end_book = book_label(document_id, pdf_page_end)
                        end_location = (
                            f"Book page {end_book} · PDF page {pdf_page_end}"
                            if end_book
                            else f"PDF page {pdf_page_end}"
                        )
                        location = f"{location} – {end_location}"
                else:
                    location = "Sin página"
                ui.caption(
                    f"{origin} · {location} · {human_link_type(item.link_type)} · "
                    f"{getattr(item.status, 'value', item.status)}"
                )
                if item.comment:
                    ui.caption(f"Comentario: {compact_text(item.comment)}")


__all__ = [
    "DocumentConceptGroup",
    "group_document_evidence",
    "render_document_concepts",
    "render_known_concept_evidence",
]

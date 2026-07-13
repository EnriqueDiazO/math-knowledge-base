"""Four-stage Streamlit wizard composed exclusively from existing S4 services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from typing import Any

from editor.concept_linking.concept_cards import LINK_TYPE_HELP
from editor.concept_linking.concept_cards import LINK_TYPE_LABELS
from editor.concept_linking.concept_cards import compact_text
from editor.concept_linking.concept_cards import human_link_type
from editor.concept_linking.concept_cards import render_concept_cards
from editor.concept_linking.concept_cards import render_selected_concept
from editor.concept_linking.concept_search import get_concept
from editor.concept_linking.concept_search import get_concepts
from editor.concept_linking.concept_search import search_concepts
from editor.concept_linking.concept_search import with_evidence_counts
from editor.concept_linking.page_concepts import evidence_for_page
from editor.concept_linking.page_concepts import render_evidence_card
from editor.concept_linking.state import ACTIVE
from editor.concept_linking.state import COMMENT
from editor.concept_linking.state import DUPLICATE_LINK_ID
from editor.concept_linking.state import LAST_RESULT
from editor.concept_linking.state import LINK_TYPE
from editor.concept_linking.state import MODE
from editor.concept_linking.state import PARTIAL_MESSAGE
from editor.concept_linking.state import PARTIAL_TARGET_ID
from editor.concept_linking.state import PARTIAL_TARGET_KIND
from editor.concept_linking.state import PDF_PAGE
from editor.concept_linking.state import SEARCH_QUERY
from editor.concept_linking.state import SELECTED_CONCEPT_KEY
from editor.concept_linking.state import TARGET_ID
from editor.concept_linking.state import TARGET_KIND
from editor.concept_linking.state import cancel_wizard
from editor.concept_linking.state import clear_partial
from editor.concept_linking.state import decode_concept_identity
from editor.concept_linking.state import record_partial
from editor.concept_linking.state import remember_concept
from editor.concept_linking.state import state_key
from editor.concept_linking.view_models import ConceptLinkingContext
from editor.concept_linking.view_models import ConceptSummary
from editor.concept_linking.view_models import EvidenceView
from editor.source_catalog.shared import safe_error_message
from mathmongo.reading_annotations.models import ConceptEvidenceLink

_ANNOTATION_KINDS = ("highlight", "underline", "comment", "bookmark", "question")
_NOTE_TYPES = (
    "summary",
    "idea",
    "proof",
    "definition",
    "question",
    "todo",
    "bibliography",
    "general",
)
_MODES = ("page", "annotation", "note")
_MODE_LABELS = {
    "page": "Asociar directamente con esta página",
    "annotation": "Asociar mediante una cita o anotación",
    "note": "Asociar mediante una Reading Note",
}


@dataclass(frozen=True, slots=True)
class GuidedLinkResult:
    """Typed UI composition result, never persisted as a second evidence model."""

    status: str
    message: str
    link: Any | None = None
    target_kind: str | None = None
    target_id: str | None = None
    created_target: bool = False

    @property
    def completed(self) -> bool:
        """Return whether the composed operation fully succeeded."""
        return self.status == "success"


def _result_status(result: Any) -> str:
    return str(getattr(getattr(result, "status", None), "value", getattr(result, "status", "")))


def _result_value(result: Any) -> Any | None:
    return getattr(result, "value", None) if bool(getattr(result, "completed", False)) else None


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value or ""))


def _exact_link(service: Any, values: Mapping[str, Any]) -> Any | None:
    """Use the existing repository's exact identity query before a confirmed write."""
    try:
        candidate = ConceptEvidenceLink.model_validate(dict(values))
        return service.evidence.find_exact(candidate)
    except Exception:
        return None


def _link_values(
    *,
    concept: ConceptSummary,
    context: ConceptLinkingContext,
    link_type: str,
    comment: str | None,
    document_id: str | None = None,
    annotation_id: str | None = None,
    note_id: str | None = None,
    page_number: int | None = None,
    reference_id: str | None = None,
) -> dict[str, Any]:
    return {
        "concept_legacy_id": concept.concept_id,
        "concept_legacy_source": concept.concept_source,
        "source_id": context.source_id,
        "reference_id": reference_id,
        "document_id": document_id,
        "annotation_id": annotation_id,
        "note_id": note_id,
        "page_number": page_number,
        "link_type": link_type,
        "comment": comment,
    }


def _create_link(
    service: Any,
    values: dict[str, Any],
    *,
    created_target: bool,
    target_kind: str | None,
    target_id: str | None,
) -> GuidedLinkResult:
    exact = _exact_link(service, values)
    if exact is not None:
        return GuidedLinkResult(
            "duplicate",
            "Este concepto ya está asociado con esta evidencia.",
            exact,
            target_kind,
            target_id,
            created_target,
        )
    try:
        result = service.create_concept_evidence_link(**values)
    except Exception:
        result = None
    if bool(getattr(result, "completed", False)):
        return GuidedLinkResult(
            "success",
            "Evidencia guardada.",
            getattr(result, "value", None),
            target_kind,
            target_id,
            created_target,
        )
    if _result_status(result) == "conflict":
        exact = _exact_link(service, values)
        if exact is not None:
            return GuidedLinkResult(
                "duplicate",
                "Este concepto ya está asociado con esta evidencia.",
                exact,
                target_kind,
                target_id,
                created_target,
            )
    if created_target and target_kind and target_id:
        noun = "anotación" if target_kind == "annotation" else "nota"
        return GuidedLinkResult(
            "partial",
            f"La {noun} se guardó, pero no se pudo crear el vínculo conceptual.",
            target_kind=target_kind,
            target_id=target_id,
            created_target=True,
        )
    return GuidedLinkResult("error", "No se pudo guardar la asociación conceptual.")


def save_guided_link(
    service: Any,
    *,
    concept: ConceptSummary,
    context: ConceptLinkingContext,
    mode: str,
    link_type: str,
    comment: str | None = None,
    page_number: int | None = None,
    target_id: str | None = None,
    annotation_draft: Mapping[str, Any] | None = None,
    note_draft: Mapping[str, Any] | None = None,
) -> GuidedLinkResult:
    """Create one confirmed association and preserve a successful partial target."""
    if mode not in _MODES or link_type not in LINK_TYPE_LABELS:
        return GuidedLinkResult("invalid", "Completa el modo y el tipo de evidencia.")
    clean_comment = str(comment or "").strip() or None
    if mode == "page":
        if not context.is_pdf:
            return GuidedLinkResult(
                "unsupported",
                "El backend actual no admite un vínculo directo a un recurso web sin página.",
            )
        if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
            return GuidedLinkResult("invalid", "Selecciona una página PDF válida.")
        values = _link_values(
            concept=concept,
            context=context,
            link_type=link_type,
            comment=clean_comment,
            document_id=context.document_id,
            page_number=page_number,
            reference_id=context.reference_id,
        )
        return _create_link(
            service,
            values,
            created_target=False,
            target_kind=None,
            target_id=None,
        )

    created_target = False
    target: Any | None = None
    if mode == "annotation":
        if target_id:
            try:
                target = _result_value(service.get_annotation(target_id, user_scope="local"))
            except Exception:
                target = None
        else:
            draft = dict(annotation_draft or {})
            try:
                created = service.create_annotation(
                    context.document_id,
                    kind=draft.get("kind", "highlight"),
                    body=str(draft.get("body", "")),
                    page_number=draft.get("page_number"),
                    quote_text=str(draft.get("quote_text", "")).strip() or None,
                    tags=tuple(draft.get("tags", ())),
                    reference_id=context.reference_id,
                    user_scope="local",
                )
            except Exception:
                created = None
            target = _result_value(created)
            created_target = target is not None
        if target is None:
            return GuidedLinkResult("error", "No se pudo preparar la anotación.")
        values = _link_values(
            concept=concept,
            context=context,
            link_type=link_type,
            comment=clean_comment,
            annotation_id=target.annotation_id,
            reference_id=target.reference_id,
        )
        return _create_link(
            service,
            values,
            created_target=created_target,
            target_kind="annotation",
            target_id=target.annotation_id,
        )

    if target_id:
        try:
            target = _result_value(service.get_note(target_id, user_scope="local"))
        except Exception:
            target = None
    else:
        draft = dict(note_draft or {})
        document_bound = bool(draft.get("document_bound", True))
        note_page = draft.get("page_start") if document_bound else None
        note_page_end = draft.get("page_end") if document_bound else None
        try:
            created = service.create_note(
                source_id=context.source_id,
                title=str(draft.get("title", "")),
                body=str(draft.get("body", "")),
                note_type=draft.get("note_type", "general"),
                document_id=context.document_id if document_bound else None,
                reference_id=context.reference_id,
                page_start=note_page,
                page_end=note_page_end,
                tags=tuple(draft.get("tags", ())),
                user_scope="local",
            )
        except Exception:
            created = None
        target = _result_value(created)
        created_target = target is not None
    if target is None:
        return GuidedLinkResult("error", "No se pudo preparar la nota de lectura.")
    values = _link_values(
        concept=concept,
        context=context,
        link_type=link_type,
        comment=clean_comment,
        note_id=target.note_id,
        reference_id=target.reference_id,
    )
    return _create_link(
        service,
        values,
        created_target=created_target,
        target_kind="note",
        target_id=target.note_id,
    )


def _radio(ui: Any, label: str, options: tuple[Any, ...], *, key: str, **kwargs: Any) -> Any:
    if hasattr(ui, "radio"):
        return ui.radio(label, options=options, key=key, **kwargs)
    return ui.selectbox(label, options=options, key=key, **kwargs)


def _text_area(ui: Any, label: str, *, key: str, value: str = "", **kwargs: Any) -> str:
    renderer = getattr(ui, "text_area", ui.text_input)
    return str(renderer(label, key=key, value=value, **kwargs) or "")


def _parse_optional_page(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    return parsed if parsed >= 1 else None


def suggestion_sections(
    database: Any,
    service: Any,
    *,
    document_evidence: tuple[EvidenceView, ...],
    current_page: int | None,
    is_pdf: bool,
    recent: tuple[tuple[str, str], ...],
    source_id: str,
) -> tuple[tuple[str, tuple[ConceptSummary, ...]], ...]:
    """Build four deduplicated, bounded quick-access sections."""
    page_items = evidence_for_page(document_evidence, current_page) if is_pdf else document_evidence
    sources: list[tuple[str, tuple[tuple[str, str], ...]]] = [
        (
            "Conceptos vinculados en la página actual",
            tuple(item.concept.identity for item in page_items),
        ),
        (
            "Conceptos usados en este documento",
            tuple(item.concept.identity for item in document_evidence),
        ),
    ]
    try:
        source_result = service.list_source_evidence(source_id, status=None, page=1, page_size=50)
        source_links = tuple(
            getattr(getattr(source_result, "value", None), "items", ())
            if bool(getattr(source_result, "completed", False))
            else ()
        )
    except Exception:
        source_links = ()
    sources.extend(
        (
            (
                "Conceptos usados en esta Source",
                tuple(
                    (item.concept_legacy_id, item.concept_legacy_source) for item in source_links
                ),
            ),
            ("Conceptos recientes", recent),
        )
    )
    seen: set[tuple[str, str]] = set()
    sections: list[tuple[str, tuple[ConceptSummary, ...]]] = []
    remaining = 48
    for heading, identities in sources:
        unique = tuple(identity for identity in dict.fromkeys(identities) if identity not in seen)
        unique = unique[: min(12, remaining)]
        if not unique:
            continue
        seen.update(unique)
        remaining -= len(unique)
        try:
            concepts = get_concepts(database, unique, limit=max(1, len(unique)))
            concepts = with_evidence_counts(concepts, service.evidence)
        except Exception:
            concepts = ()
        if concepts:
            sections.append((heading, concepts))
        if remaining <= 0:
            break
    return tuple(sections)


def _selected_concept(
    ui: Any,
    database: Any,
    *,
    document_evidence: tuple[EvidenceView, ...],
    current_page: int | None,
    is_pdf: bool,
) -> ConceptSummary | None:
    identity = decode_concept_identity(ui.session_state.get(SELECTED_CONCEPT_KEY))
    if identity is None:
        return None
    try:
        concept = get_concept(database, identity[0], identity[1])
    except Exception:
        concept = None
    if concept is None:
        ui.warning("El concepto seleccionado ya no está disponible.")
        ui.session_state.pop(SELECTED_CONCEPT_KEY, None)
        return None
    document_count = sum(item.concept.identity == identity for item in document_evidence)
    page_count = sum(
        item.concept.identity == identity
        for item in (
            evidence_for_page(document_evidence, current_page) if is_pdf else document_evidence
        )
    )
    return replace(
        concept,
        document_evidence_count=document_count,
        page_evidence_count=page_count,
    )


def _render_stage_one(
    ui: Any,
    database: Any,
    service: Any,
    *,
    sections: tuple[tuple[str, tuple[ConceptSummary, ...]], ...],
    document_evidence: tuple[EvidenceView, ...],
    current_page: int | None,
    is_pdf: bool,
) -> ConceptSummary | None:
    ui.subheader("1. Concepto")
    concept = _selected_concept(
        ui,
        database,
        document_evidence=document_evidence,
        current_page=current_page,
        is_pdf=is_pdf,
    )
    if concept is not None:
        if render_selected_concept(ui, concept):
            return None
        return concept
    if sections:
        ui.caption("Accesos rápidos")
        for index, (heading, items) in enumerate(sections):
            with ui.expander(heading, expanded=index == 0):
                selected = render_concept_cards(
                    ui,
                    items,
                    section_key=f"suggestion_{index}",
                )
                if selected is not None:
                    return selected
    query = ui.text_input("Buscar concepto", key=SEARCH_QUERY)
    page = int(
        ui.number_input(
            "Página de resultados",
            min_value=1,
            max_value=10_000,
            value=1,
            step=1,
            key=state_key("search_page"),
            width="stretch",
        )
    )
    if not str(query or "").strip():
        ui.caption("Busca por nombre, ID, Source legacy, tipo, categoría o tag.")
        return None
    try:
        results = with_evidence_counts(
            search_concepts(database, str(query), page=page),
            service.evidence,
        )
    except Exception as exc:
        ui.error(compact_text(safe_error_message(exc), limit=160) or "No se pudo buscar conceptos.")
        return None
    return render_concept_cards(
        ui,
        results,
        section_key=f"search_{page}",
        empty_message="No se encontraron conceptos.",
    )


def _target_has_evidence(service: Any, *, kind: str, target_id: str) -> bool:
    try:
        result = (
            service.list_annotation_evidence(target_id, status=None, page=1, page_size=1)
            if kind == "annotation"
            else service.list_note_evidence(target_id, status=None, page=1, page_size=1)
        )
    except Exception:
        return True
    return bool(getattr(getattr(result, "value", None), "total", 0))


def _page_location(
    page: int | None,
    page_end: int | None,
    *,
    context: ConceptLinkingContext,
    page_labeler: Any | None,
) -> str:
    def label(value: int) -> str:
        book_page = None
        if page_labeler is not None:
            try:
                book_page = page_labeler(value)
            except Exception:
                book_page = None
        elif value == context.pdf_page:
            book_page = context.book_page_label
        return f"Book page {book_page} · PDF page {value}" if book_page else f"PDF page {value}"

    if not isinstance(page, int):
        return "Sin página"
    start = label(page)
    return (
        f"{start} – {label(page_end)}" if isinstance(page_end, int) and page_end != page else start
    )


def _render_target_card(
    ui: Any,
    service: Any,
    item: Any,
    *,
    context: ConceptLinkingContext,
    mode: str,
    page_labeler: Any | None,
    selectable: bool,
) -> bool:
    target_id = item.annotation_id if mode == "annotation" else item.note_id
    page = getattr(item, "page_number", None) or getattr(item, "page_start", None)
    page_end = getattr(item, "page_end", None)
    heading = (
        _enum_value(getattr(item, "kind", "")) or "Cita o anotación"
        if mode == "annotation"
        else compact_text(getattr(item, "title", None), limit=100) or "Nota de lectura"
    )
    status = _enum_value(getattr(item, "status", ""))
    tags = tuple(getattr(item, "tags", ()) or ())
    clicked = False
    with ui.container(border=True):
        ui.write(heading)
        if mode == "note":
            ui.caption(f"Tipo: {_enum_value(getattr(item, 'note_type', '')) or 'general'}")
        ui.caption(
            _page_location(
                page if isinstance(page, int) else None,
                page_end if isinstance(page_end, int) else None,
                context=context,
                page_labeler=page_labeler,
            )
        )
        if mode == "annotation":
            quote = compact_text(getattr(item, "quote_text", None))
            body = compact_text(getattr(item, "body", None))
            if quote:
                ui.write(f"“{quote}”")
            if body:
                ui.write(body)
        else:
            body = compact_text(getattr(item, "body", None))
            if body:
                ui.write(body)
        if tags:
            ui.caption(f"Tags: {', '.join(str(tag) for tag in tags[:5])}")
        ui.caption(f"Estado: {status or '—'}")
        linked = _target_has_evidence(service, kind=mode, target_id=target_id)
        ui.caption("Ya tiene evidencia conceptual" if linked else "Sin concepto asociado")
        if selectable:
            clicked = ui.button(
                "Usar esta anotación" if mode == "annotation" else "Usar esta nota",
                key=state_key("use_target", mode, target_id),
                disabled=status == "archived",
                width="content",
            )
            if status == "archived":
                ui.caption("Reactiva este elemento antes de usarlo como evidencia.")
        with ui.expander("Detalles técnicos", expanded=False):
            ui.caption(f"ID: {target_id}")
    return bool(clicked)


def _render_selected_target(
    ui: Any,
    service: Any,
    *,
    context: ConceptLinkingContext,
    mode: str,
    target_id: str,
    page_labeler: Any | None,
) -> bool:
    try:
        result = (
            service.get_annotation(target_id, user_scope="local")
            if mode == "annotation"
            else service.get_note(target_id, user_scope="local")
        )
    except Exception:
        result = None
    target = _result_value(result)
    if target is None:
        ui.warning("La evidencia seleccionada ya no está disponible.")
        return False
    ui.caption("Evidencia seleccionada")
    _render_target_card(
        ui,
        service,
        target,
        context=context,
        mode=mode,
        page_labeler=page_labeler,
        selectable=False,
    )
    return True


def _render_existing_targets(
    ui: Any,
    service: Any,
    *,
    context: ConceptLinkingContext,
    mode: str,
    page_labeler: Any | None,
) -> None:
    show_archived = False
    with ui.expander("Opciones avanzadas", expanded=False):
        show_archived = ui.checkbox(
            "Mostrar elementos archivados",
            key=state_key("show_archived", mode),
            value=False,
        )
        ui.caption("Los IDs internos permanecen ocultos fuera de Detalles técnicos.")
    status = None if show_archived else "active"
    page = int(
        ui.number_input(
            "Página de anotaciones" if mode == "annotation" else "Página de notas",
            min_value=1,
            max_value=10_000,
            value=1,
            step=1,
            key=state_key("existing_target_page", mode),
            width="stretch",
        )
    )
    try:
        result = (
            service.list_document_annotations(
                context.document_id,
                status=status,
                page=page,
                page_size=20,
                user_scope="local",
            )
            if mode == "annotation"
            else service.list_document_notes(
                context.document_id,
                status=status,
                page=page,
                page_size=20,
                user_scope="local",
            )
        )
    except Exception:
        result = None
    items = tuple(
        getattr(getattr(result, "value", None), "items", ())
        if bool(getattr(result, "completed", False))
        else ()
    )
    if not items:
        ui.caption("No hay elementos compatibles en este Document.")
        return
    for item in items:
        if _render_target_card(
            ui,
            service,
            item,
            context=context,
            mode=mode,
            page_labeler=page_labeler,
            selectable=True,
        ):
            target_id = item.annotation_id if mode == "annotation" else item.note_id
            ui.session_state[TARGET_KIND] = mode
            ui.session_state[TARGET_ID] = target_id


def _duplicate_evidence_view(
    service: Any,
    outcome: GuidedLinkResult,
    *,
    concept: ConceptSummary,
    context: ConceptLinkingContext,
    fallback_page: int | None,
) -> EvidenceView | None:
    """Resolve a duplicate into the same human card used by evidence summaries."""
    link = outcome.link
    evidence_link_id = getattr(link, "evidence_link_id", None)
    if not isinstance(evidence_link_id, str) or not evidence_link_id:
        return None
    annotation_id = getattr(link, "annotation_id", None)
    note_id = getattr(link, "note_id", None)
    document_id = getattr(link, "document_id", None)
    pdf_page = getattr(link, "page_number", None)
    pdf_page_end = pdf_page
    excerpt = ""
    if annotation_id:
        origin_kind = "annotation"
        origin_label = "Cita o anotación"
        try:
            target = _result_value(service.get_annotation(annotation_id, user_scope="local"))
        except Exception:
            target = None
        document_id = getattr(target, "document_id", None)
        pdf_page = getattr(target, "page_number", None)
        pdf_page_end = pdf_page
        excerpt = compact_text(getattr(target, "quote_text", None) or getattr(target, "body", None))
    elif note_id:
        origin_kind = "note"
        origin_label = "Nota de lectura"
        try:
            target = _result_value(service.get_note(note_id, user_scope="local"))
        except Exception:
            target = None
        document_id = getattr(target, "document_id", None)
        pdf_page = getattr(target, "page_start", None)
        pdf_page_end = getattr(target, "page_end", None) or pdf_page
        title = compact_text(getattr(target, "title", None), limit=80)
        body = compact_text(getattr(target, "body", None))
        excerpt = f"{title}: {body}" if title and body else title or body
    else:
        origin_kind = "page"
        origin_label = "Página directa"
        pdf_page = pdf_page if isinstance(pdf_page, int) else fallback_page
        pdf_page_end = pdf_page
    book_page = context.book_page_label if pdf_page == context.pdf_page else None
    return EvidenceView(
        evidence_link_id=evidence_link_id,
        concept=concept,
        link_type=_enum_value(getattr(link, "link_type", "")),
        link_type_label=human_link_type(getattr(link, "link_type", "")),
        origin_kind=origin_kind,
        origin_label=origin_label,
        source_id=str(getattr(link, "source_id", context.source_id)),
        reference_id=getattr(link, "reference_id", None),
        document_id=document_id,
        annotation_id=annotation_id,
        note_id=note_id,
        pdf_page=pdf_page if isinstance(pdf_page, int) else None,
        pdf_page_end=pdf_page_end if isinstance(pdf_page_end, int) else None,
        book_page_label=book_page,
        excerpt=excerpt,
        comment=compact_text(getattr(link, "comment", None)),
        status=_enum_value(getattr(link, "status", "active")) or "active",
    )


def _render_duplicate_result(
    ui: Any,
    service: Any,
    *,
    concept: ConceptSummary,
    context: ConceptLinkingContext,
    fallback_page: int | None,
    actions_enabled: bool,
    archive_enabled: bool | None,
    link: Any | None = None,
) -> bool:
    """Render a stored duplicate on every rerun so its actions remain interactive."""
    evidence_link_id = ui.session_state.get(DUPLICATE_LINK_ID)
    if link is None and isinstance(evidence_link_id, str):
        try:
            link = service.evidence.get_by_id(evidence_link_id)
        except Exception:
            link = None
    if link is None:
        if evidence_link_id is not None:
            ui.session_state.pop(DUPLICATE_LINK_ID, None)
        return False
    outcome = GuidedLinkResult(
        status="duplicate",
        message="Este concepto ya está asociado con esta evidencia.",
        link=link,
    )
    duplicate = _duplicate_evidence_view(
        service,
        outcome,
        concept=concept,
        context=context,
        fallback_page=fallback_page,
    )
    if duplicate is None:
        return False
    ui.warning(outcome.message)
    ui.caption("Vínculo existente")
    render_evidence_card(
        ui,
        service,
        duplicate,
        actions_enabled=actions_enabled,
        archive_enabled=archive_enabled,
        card_key=f"duplicate_{duplicate.evidence_link_id}",
    )
    return True


def _render_stage_two(
    ui: Any,
    service: Any,
    *,
    context: ConceptLinkingContext,
    effective_page: int | None,
    page_labeler: Any | None,
) -> tuple[str, str | None, dict[str, Any] | None, dict[str, Any] | None, bool]:
    ui.subheader("2. Evidencia")
    if context.is_pdf:
        mode = str(
            _radio(
                ui,
                "Tipo de evidencia",
                _MODES,
                key=MODE,
                format_func=lambda value: _MODE_LABELS[value],
                horizontal=True,
            )
        )
    else:
        ui.caption("Asociación directa con este recurso")
        ui.info(
            "El contrato actual exige una página para la evidencia directa. "
            "Para recursos web usa una Annotation o ReadingNote sin página."
        )
        mode = str(
            _radio(
                ui,
                "Tipo de evidencia",
                ("annotation", "note"),
                key=MODE,
                format_func=lambda value: _MODE_LABELS[value],
                horizontal=True,
            )
        )
    target_id = ui.session_state.get(TARGET_ID)
    target_kind = ui.session_state.get(TARGET_KIND)
    if target_kind != mode:
        target_id = None
        ui.session_state.pop(TARGET_ID, None)
        ui.session_state.pop(TARGET_KIND, None)
    if mode == "page":
        ui.caption("Este concepto aparece o se utiliza en la página actual.")
        return mode, None, None, None, isinstance(effective_page, int)
    use_mode = (
        "existing"
        if target_id
        else str(
            _radio(
                ui,
                "Evidencia disponible",
                ("existing", "new"),
                key=state_key("target_source", mode),
                format_func=lambda value: (
                    "Usar existente" if value == "existing" else "Crear nueva"
                ),
                horizontal=True,
            )
        )
    )
    if use_mode == "existing":
        if target_id:
            ui.success("Evidencia existente seleccionada.")
            target_available = _render_selected_target(
                ui,
                service,
                context=context,
                mode=mode,
                target_id=target_id,
                page_labeler=page_labeler,
            )
            if not target_available:
                ui.session_state.pop(TARGET_ID, None)
                ui.session_state.pop(TARGET_KIND, None)
                ui.rerun()
            if ui.button(
                "Cambiar evidencia",
                key=state_key("change_target", mode),
                width="content",
            ):
                ui.session_state.pop(TARGET_ID, None)
                ui.session_state.pop(TARGET_KIND, None)
                ui.rerun()
        if not target_id:
            _render_existing_targets(
                ui,
                service,
                context=context,
                mode=mode,
                page_labeler=page_labeler,
            )
            target_id = ui.session_state.get(TARGET_ID)
        return mode, target_id if isinstance(target_id, str) else None, None, None, bool(target_id)

    if mode == "annotation":
        kind = ui.selectbox(
            "Tipo de anotación",
            options=_ANNOTATION_KINDS,
            key=state_key("annotation_kind"),
        )
        quote = _text_area(ui, "Cita", key=state_key("annotation_quote"), height=100)
        body = _text_area(
            ui,
            "Nota sobre la cita (opcional)",
            key=state_key("annotation_body"),
            height=100,
        )
        tags = ui.text_input("Tags (separados por comas)", key=state_key("annotation_tags"))
        draft = {
            "kind": kind,
            "quote_text": quote,
            "body": body,
            "page_number": effective_page if context.is_pdf else None,
            "tags": tuple(value.strip() for value in str(tags).split(",") if value.strip()),
        }
        valid = bool(body.strip()) if kind in {"comment", "question"} else True
        return mode, None, draft, None, valid

    title = ui.text_input("Título", key=state_key("note_title"))
    note_type = ui.selectbox(
        "Tipo de nota",
        options=_NOTE_TYPES,
        key=state_key("note_type"),
    )
    body = _text_area(ui, "Nota", key=state_key("note_body"), height=150)
    end_page = (
        ui.text_input(
            "Página final (opcional)",
            key=state_key("note_page_end"),
            value="",
        )
        if context.is_pdf
        else ""
    )
    tags = ui.text_input("Tags (separados por comas)", key=state_key("note_tags"))
    document_bound = True
    without_pages = False
    with ui.expander("Opciones avanzadas", expanded=False):
        document_bound = not ui.checkbox(
            "Guardar como nota sólo de la Source",
            key=state_key("note_source_only"),
            value=False,
        )
        without_pages = ui.checkbox(
            "Asociar con el Document completo, sin páginas",
            key=state_key("note_without_pages"),
            value=False,
            disabled=not document_bound or not context.is_pdf,
        )
        ui.caption(
            "Una nota Source-only no tendrá página ni Document asociado; una nota de "
            "Document completo conserva el Document, pero no un rango."
        )
    draft = {
        "title": title,
        "note_type": note_type,
        "body": body,
        "page_start": (
            effective_page if context.is_pdf and document_bound and not without_pages else None
        ),
        "page_end": (
            _parse_optional_page(end_page) if document_bound and not without_pages else None
        ),
        "tags": tuple(value.strip() for value in str(tags).split(",") if value.strip()),
        "document_bound": document_bound,
    }
    return mode, None, None, draft, bool(str(title).strip() and body.strip())


def _render_context_summary(
    ui: Any,
    *,
    context: ConceptLinkingContext,
    concept: ConceptSummary,
    mode: str,
    link_type: str,
    effective_page: int | None,
) -> None:
    with ui.container(border=True):
        ui.subheader("Contexto de la asociación")
        ui.write(f"Concepto: {concept.display_title}")
        ui.caption(f"Documento: {context.document_title}")
        ui.caption(f"Source: {context.source_name}")
        ui.caption(
            f"Reference: {context.reference_title}"
            if context.reference_title
            else "Sin Reference asociada"
        )
        if context.is_pdf and effective_page:
            book = context.book_page_label if effective_page == context.pdf_page else None
            location = (
                f"Book page {book} · PDF page {effective_page}"
                if book
                else f"PDF page {effective_page}"
            )
            ui.caption(f"Ubicación: {location}")
        elif context.is_pdf:
            ui.caption("Ubicación: Sin página")
        else:
            ui.caption(f"Ubicación: {context.location_label}")
        ui.caption(f"Evidencia: {_MODE_LABELS[mode]}")
        ui.caption(f"Tipo: {LINK_TYPE_LABELS[link_type]}")


def _association_page(
    service: Any,
    *,
    mode: str,
    target_id: str | None,
    annotation_draft: Mapping[str, Any] | None,
    note_draft: Mapping[str, Any] | None,
    fallback: int | None,
) -> int | None:
    """Resolve the evidence page shown in confirmation from its actual target."""
    if mode == "page":
        return fallback
    if target_id:
        try:
            result = (
                service.get_annotation(target_id, user_scope="local")
                if mode == "annotation"
                else service.get_note(target_id, user_scope="local")
            )
        except Exception:
            result = None
        target = _result_value(result)
        page = (
            getattr(target, "page_number", None)
            if mode == "annotation"
            else getattr(target, "page_start", None)
        )
        return page if isinstance(page, int) and not isinstance(page, bool) else None
    draft = annotation_draft if mode == "annotation" else note_draft
    field = "page_number" if mode == "annotation" else "page_start"
    page = (draft or {}).get(field)
    return page if isinstance(page, int) and not isinstance(page, bool) else None


def render_linking_wizard(
    ui: Any,
    database: Any,
    service: Any,
    *,
    context: ConceptLinkingContext,
    document_evidence: tuple[EvidenceView, ...],
    quick_sections: tuple[tuple[str, tuple[ConceptSummary, ...]], ...],
    actions_enabled: bool,
    page_labeler: Any | None = None,
    archive_enabled: bool | None = None,
) -> None:
    """Render the four human stages and write only after explicit confirmation."""
    if not bool(ui.session_state.get(ACTIVE)):
        return
    if ui.session_state.get(PARTIAL_MESSAGE):
        ui.warning(str(ui.session_state[PARTIAL_MESSAGE]))
        ui.caption("El elemento permanece en Pendientes de vincular.")
    ui.header("Asociar concepto")
    ui.caption("1 Concepto → 2 Evidencia → 3 Contexto → 4 Confirmar")
    captured_page = ui.session_state.get(PDF_PAGE)
    effective_page = captured_page if isinstance(captured_page, int) else context.pdf_page
    if context.is_pdf and context.pdf_page != captured_page:
        ui.warning(
            f"La página actual cambió durante el wizard: se capturó PDF page "
            f"{captured_page or '—'} y ahora estás en PDF page {context.pdf_page or '—'}."
        )
        choices = tuple(
            value for value in (captured_page, context.pdf_page) if isinstance(value, int)
        )
        if choices:
            effective_page = int(
                _radio(
                    ui,
                    "Página para esta asociación",
                    tuple(dict.fromkeys(choices)),
                    key=state_key("page_choice"),
                    format_func=lambda value: (
                        f"Usar página capturada: PDF {value}"
                        if value == captured_page
                        else f"Actualizar al contexto actual: PDF {value}"
                    ),
                    horizontal=True,
                )
            )
    concept = _render_stage_one(
        ui,
        database,
        service,
        sections=quick_sections,
        document_evidence=document_evidence,
        current_page=effective_page,
        is_pdf=context.is_pdf,
    )
    if concept is None:
        if ui.button("Cancelar", key=state_key("cancel_search"), width="content"):
            cancel_wizard(ui.session_state)
            ui.rerun()
        return
    mode, target_id, annotation_draft, note_draft, target_ready = _render_stage_two(
        ui,
        service,
        context=context,
        effective_page=effective_page,
        page_labeler=page_labeler,
    )
    ui.subheader("3. Contexto")
    link_type = ui.selectbox(
        "Tipo de relación",
        options=("", *LINK_TYPE_LABELS),
        key=LINK_TYPE,
        format_func=lambda value: "Selecciona un tipo" if not value else LINK_TYPE_LABELS[value],
    )
    if link_type:
        ui.caption(LINK_TYPE_HELP[str(link_type)])
    comment = _text_area(
        ui,
        "¿Por qué esta evidencia es relevante?",
        key=COMMENT,
        height=100,
    )
    if link_type:
        summary_page = _association_page(
            service,
            mode=mode,
            target_id=target_id,
            annotation_draft=annotation_draft,
            note_draft=note_draft,
            fallback=effective_page,
        )
        _render_context_summary(
            ui,
            context=context,
            concept=concept,
            mode=mode,
            link_type=str(link_type),
            effective_page=summary_page,
        )
    ui.subheader("4. Confirmación")
    ready = bool(actions_enabled and target_ready and link_type)
    if not actions_enabled:
        ui.caption("Las escrituras se habilitan al inicializar Notes & Evidence en Maintenance.")
    elif not target_ready or not link_type:
        ui.caption("Completa la evidencia y el tipo de relación para revisar y guardar.")
    else:
        ui.success("Revisa el resumen anterior. Nada se ha guardado todavía.")
    retry = bool(ui.session_state.get(PARTIAL_TARGET_ID)) and ui.button(
        "Reintentar vínculo",
        key=state_key("retry_link"),
        disabled=not ready,
        width="content",
    )
    save = ui.button(
        "Guardar asociación",
        key=state_key("save_link"),
        disabled=not ready,
        type="primary",
        width="content",
    )
    cancel = ui.button("Cancelar", key=state_key("cancel_link"), width="content")
    if cancel:
        cancel_wizard(ui.session_state)
        ui.rerun()
        return
    stored_duplicate_id = ui.session_state.get(DUPLICATE_LINK_ID)
    duplicate_rendered = _render_duplicate_result(
        ui,
        service,
        concept=concept,
        context=context,
        fallback_page=effective_page,
        actions_enabled=actions_enabled,
        archive_enabled=archive_enabled,
    )
    if not (save or retry):
        return
    if retry:
        partial_kind = ui.session_state.get(PARTIAL_TARGET_KIND)
        partial_id = ui.session_state.get(PARTIAL_TARGET_ID)
        if partial_kind in {"annotation", "note"} and isinstance(partial_id, str):
            mode = partial_kind
            target_id = partial_id
            annotation_draft = None
            note_draft = None
    outcome = save_guided_link(
        service,
        concept=concept,
        context=context,
        mode=mode,
        link_type=str(link_type),
        comment=comment,
        page_number=effective_page,
        target_id=target_id,
        annotation_draft=annotation_draft,
        note_draft=note_draft,
    )
    if outcome.status == "success":
        remember_concept(ui.session_state, concept.concept_id, concept.concept_source)
        clear_partial(ui.session_state)
        ui.session_state[LAST_RESULT] = outcome.message
        cancel_wizard(ui.session_state)
        ui.session_state[LAST_RESULT] = outcome.message
        ui.success(outcome.message)
        ui.rerun()
    elif outcome.status == "duplicate":
        clear_partial(ui.session_state)
        evidence_link_id = getattr(outcome.link, "evidence_link_id", None)
        if isinstance(evidence_link_id, str) and evidence_link_id:
            ui.session_state[DUPLICATE_LINK_ID] = evidence_link_id
        already_rendered = duplicate_rendered and evidence_link_id == stored_duplicate_id
        rendered = already_rendered or _render_duplicate_result(
            ui,
            service,
            concept=concept,
            context=context,
            fallback_page=effective_page,
            actions_enabled=actions_enabled,
            archive_enabled=archive_enabled,
            link=outcome.link,
        )
        if not rendered:
            ui.warning(outcome.message)
            ui.caption("Puedes abrir la evidencia existente desde Conceptos en esta página.")
    elif outcome.status == "partial" and outcome.target_kind and outcome.target_id:
        record_partial(
            ui.session_state,
            target_kind=outcome.target_kind,
            target_id=outcome.target_id,
            message=outcome.message,
        )
        ui.warning(outcome.message)
        ui.rerun()
    else:
        ui.error(outcome.message)


__all__ = [
    "GuidedLinkResult",
    "render_linking_wizard",
    "save_guided_link",
    "suggestion_sections",
]

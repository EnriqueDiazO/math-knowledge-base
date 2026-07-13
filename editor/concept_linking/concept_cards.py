"""Human-facing cards and labels shared by the S4.3 views."""

# ruff: noqa: D103

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from editor.concept_linking.state import change_concept
from editor.concept_linking.state import select_concept
from editor.concept_linking.state import state_key
from editor.concept_linking.view_models import ConceptSummary

LINK_TYPE_LABELS = {
    "definition_source": "Fuente de definición",
    "theorem_source": "Fuente de teorema",
    "proof_source": "Fuente de prueba",
    "example_source": "Fuente de ejemplo",
    "motivation": "Motivación",
    "citation": "Cita",
    "question": "Pregunta",
    "related_context": "Contexto relacionado",
}
LINK_TYPE_HELP = {
    "definition_source": "El documento define o introduce formalmente el concepto.",
    "theorem_source": "El documento enuncia un resultado central sobre el concepto.",
    "proof_source": "La evidencia contiene parte de una demostración o justificación.",
    "example_source": "La evidencia presenta una instancia concreta del concepto.",
    "motivation": "La evidencia explica por qué el concepto resulta útil o natural.",
    "citation": "La evidencia registra una cita especialmente relevante.",
    "question": "La evidencia plantea una pregunta abierta o de lectura.",
    "related_context": "El contenido ayuda a comprender el concepto, aunque no lo defina.",
}


def compact_text(value: object, *, limit: int = 180) -> str:
    """Collapse whitespace and bound user text for a card preview."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)].rstrip()}…"


def human_link_type(value: object) -> str:
    key = str(getattr(value, "value", value or ""))
    return LINK_TYPE_LABELS.get(key, key.replace("_", " ").strip().capitalize())


def _concept_meta(concept: ConceptSummary) -> str:
    parts = [concept.concept_type] if concept.concept_type else []
    parts.extend(concept.topics[:3])
    return " · ".join(parts) or "Concepto matemático"


def render_concept_card(
    ui: Any,
    concept: ConceptSummary,
    *,
    card_key: str,
    button_label: str = "Seleccionar",
) -> bool:
    """Render one selectable concept without exposing technical IDs by default."""
    with ui.container(border=True):
        ui.subheader(concept.display_title)
        ui.caption(_concept_meta(concept))
        ui.caption(f"Source legacy: {concept.concept_source}")
        if concept.evidence_count is not None:
            noun = (
                "evidencia documental" if concept.evidence_count == 1 else "evidencias documentales"
            )
            ui.caption(f"{concept.evidence_count} {noun}")
        selected = ui.button(
            button_label,
            key=state_key("select_concept", card_key),
            width="content",
        )
        with ui.expander("Detalles del concepto", expanded=False):
            ui.caption(f"ID legacy: {concept.concept_id}")
            ui.caption(f"Source legacy: {concept.concept_source}")
            if concept.categories:
                ui.caption(f"Categorías: {', '.join(concept.categories)}")
            if concept.tags:
                ui.caption(f"Tags: {', '.join(concept.tags)}")
    if selected:
        select_concept(ui.session_state, concept.concept_id, concept.concept_source)
    return bool(selected)


def render_concept_cards(
    ui: Any,
    concepts: Iterable[ConceptSummary],
    *,
    section_key: str,
    empty_message: str = "No hay conceptos para mostrar.",
) -> ConceptSummary | None:
    """Render a bounded sequence and return the concept selected in this run."""
    items = tuple(concepts)
    if not items:
        ui.caption(empty_message)
        return None
    for index, concept in enumerate(items):
        if render_concept_card(
            ui,
            concept,
            card_key=f"{section_key}_{index}_{concept.concept_source}_{concept.concept_id}",
        ):
            return concept
    return None


def render_selected_concept(ui: Any, concept: ConceptSummary) -> bool:
    """Preview a chosen concept and allow an explicit return to search."""
    with ui.container(border=True):
        ui.subheader("Concepto seleccionado")
        ui.write(concept.display_title)
        ui.caption(_concept_meta(concept))
        ui.caption(f"Source legacy: {concept.concept_source}")
        if concept.document_evidence_count or concept.page_evidence_count:
            ui.caption(
                f"{concept.document_evidence_count} evidencias en este documento · "
                f"{concept.page_evidence_count} en esta página"
            )
        clicked = ui.button(
            "Cambiar concepto",
            key=state_key("change_concept"),
            width="content",
        )
        with ui.expander("Ver detalles", expanded=False):
            ui.caption(f"ID legacy: {concept.concept_id}")
            ui.caption(f"Source legacy: {concept.concept_source}")
            ui.caption(f"Tipo: {concept.concept_type or '—'}")
            ui.caption(f"Categorías: {', '.join(concept.categories) or '—'}")
            ui.caption(f"Tags: {', '.join(concept.tags) or '—'}")
    if clicked:
        change_concept(ui.session_state)
        ui.rerun()
    return bool(clicked)


def render_relationship_help(ui: Any) -> None:
    """Explain the persisted relationship using a collapsed human diagram."""
    with ui.expander("¿Cómo se relacionan conceptos y documentos?", expanded=False):
        diagram = (
            "Concepto\n"
            "   │\n"
            "   ▼\n"
            "ConceptEvidenceLink\n"
            "   │\n"
            "   ├── página del documento\n"
            "   ├── Annotation\n"
            "   └── ReadingNote"
        )
        if hasattr(ui, "code"):
            ui.code(diagram, language=None)
        else:
            ui.write(diagram)
        ui.caption(
            "La asociación no modifica el concepto ni el PDF. Guarda una referencia "
            "trazable entre el concepto y la evidencia encontrada durante la lectura."
        )


__all__ = [
    "LINK_TYPE_HELP",
    "LINK_TYPE_LABELS",
    "compact_text",
    "human_link_type",
    "render_concept_card",
    "render_concept_cards",
    "render_relationship_help",
    "render_selected_concept",
]

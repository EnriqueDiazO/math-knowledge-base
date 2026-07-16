"""Logical navigation from S4.3 cards without paths or browser side effects."""

from __future__ import annotations

from typing import Any

from editor.concept_linking.view_models import EvidenceView
from editor.reading_annotations.state import open_document_at_page
from editor.reading_annotations.state import select_annotation
from editor.reading_annotations.state import select_note
from editor.reading_space.state import queue_workspace_tab


def open_evidence(ui: Any, evidence: EvidenceView) -> bool:
    """Navigate to a logical target while preserving the selected Document."""
    if not evidence.document_id:
        if evidence.note_id:
            select_note(ui.session_state, evidence.note_id)
            queue_workspace_tab(ui.session_state, "Cuaderno")
            ui.rerun()
            return True
        ui.warning("Esta evidencia no está asociada con un Document.")
        return False
    open_document_at_page(
        ui.session_state,
        source_id=evidence.source_id,
        document_id=evidence.document_id,
        page_number=evidence.pdf_page,
    )
    if evidence.annotation_id:
        select_annotation(ui.session_state, evidence.annotation_id)
        queue_workspace_tab(ui.session_state, "Cuaderno")
    elif evidence.note_id:
        select_note(ui.session_state, evidence.note_id)
        queue_workspace_tab(ui.session_state, "Cuaderno")
    ui.rerun()
    return True


__all__ = ["open_evidence"]

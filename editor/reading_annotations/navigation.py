"""Navigation controls from S4 records back to the current Reading Space."""

from __future__ import annotations

from typing import Any

from editor.reading_annotations.state import open_document_at_page
from editor.reading_annotations.state import state_key


def render_open_document(
    ui: Any,
    *,
    source_id: str,
    document_id: str | None,
    page_number: int | None,
    subject_id: str,
    label: str = "Open in Reading Space",
) -> bool:
    """Render logical navigation without filesystem or browser URL handling."""
    if not document_id:
        return False
    clicked = ui.button(
        label,
        key=state_key("open_document", subject_id),
        width="content",
    )
    if not clicked:
        return False
    open_document_at_page(
        ui.session_state,
        source_id=source_id,
        document_id=document_id,
        page_number=page_number,
    )
    ui.rerun()
    return True


__all__ = ["render_open_document"]

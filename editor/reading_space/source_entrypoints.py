"""Small handoff control from Source Documents into Reading Space."""

from __future__ import annotations

from typing import Any

from editor.reading_space.state import request_reading_space_navigation
from editor.reading_space.state import state_key
from mathmongo.source_documents.models import SourceDocument


def render_reading_space_entrypoint(ui: Any, document: SourceDocument) -> bool:
    """Queue a logical target without loading PDF bytes or opening a web URL."""
    if not ui.button(
        "Open in Reading Space",
        key=state_key("source_entrypoint", document.document_id),
    ):
        return False
    request_reading_space_navigation(
        ui.session_state,
        source_id=document.source_id,
        document_id=document.document_id,
        kind=document.kind.value,
    )
    return True


__all__ = ["render_reading_space_entrypoint"]

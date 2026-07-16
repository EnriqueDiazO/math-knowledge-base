"""Recent reading history presentation without PDF materialization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from editor.reading_space.state import state_key


def render_recent_documents(
    ui: Any,
    page: Any,
    *,
    actions_enabled: bool,
    on_open: Callable[[Any], None],
) -> bool:
    """Render recent metadata and permit an explicit re-open of active Documents."""
    items = tuple(getattr(page, "items", ()))
    if not items:
        return False
    ui.subheader("Continuar leyendo")
    for item in items:
        document = item.document
        status = str(getattr(document.status, "value", document.status))
        reading = getattr(item, "state", None)
        with ui.container(border=True, key=state_key("recent_card", document.document_id)):
            ui.write(document.title)
            page_number = getattr(reading, "current_page", None)
            last_opened = getattr(reading, "last_opened_at", None)
            details = (
                "PDF" if str(getattr(document.kind, "value", document.kind)) == "pdf" else "Web"
            )
            if isinstance(page_number, int):
                details += f" · página {page_number}"
            if last_opened is not None:
                details += f" · {last_opened}"
            ui.caption(details)
            if status == "archived":
                ui.warning("Este documento está archivado; no se puede continuar.")
            if ui.button(
                "Continuar",
                key=state_key("open_recent", document.document_id),
                disabled=status == "archived" or not actions_enabled,
                type="primary",
            ):
                on_open(item)
    return True


__all__ = ["render_recent_documents"]

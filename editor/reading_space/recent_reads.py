"""Recent reading history presentation without PDF materialization."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from editor.reading_space.document_picker import document_rows
from editor.reading_space.state import state_key


def render_recent_documents(
    ui: Any,
    page: Any,
    *,
    actions_enabled: bool,
    on_open: Callable[[Any], None],
) -> None:
    """Render recent metadata and permit an explicit re-open of active Documents."""
    items = tuple(getattr(page, "items", ()))
    if not items:
        ui.info("No hay Documents abiertos recientemente para este user_scope.")
        return
    ui.dataframe(document_rows(items), width="stretch", hide_index=True)
    for item in items:
        document = item.document
        status = str(getattr(document.status, "value", document.status))
        if status == "archived":
            ui.warning(f"{document.title}: archived; la reapertura está bloqueada.")
        if ui.button(
            f"Open recent: {document.title}",
            key=state_key("open_recent", document.document_id),
            disabled=status == "archived" or not actions_enabled,
        ):
            on_open(item)


__all__ = ["render_recent_documents"]

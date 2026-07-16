"""Reading Space filter widgets and typed filter construction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from editor.reading_space.state import state_key
from mathmongo.reading_space.models import ReadingDocumentFilters
from mathmongo.reading_space.models import ReadingSort

Choice = tuple[str, str]


def _select_optional(
    ui: Any,
    label: str,
    choices: Sequence[Choice],
    *,
    key: str,
) -> str | None:
    ids: list[str | None] = [None, *(item[0] for item in choices)]
    labels = {item_id: item_label for item_id, item_label in choices}
    current = ui.session_state.get(key)
    if current not in ids:
        ui.session_state.pop(key, None)
        current = None
    index = ids.index(current) if current in ids else 0
    return ui.selectbox(
        label,
        ids,
        index=index,
        format_func=lambda value: "All" if value is None else labels[str(value)],
        key=key,
        width="stretch",
    )


def render_filters(
    ui: Any,
    *,
    sources: Sequence[Choice],
    references: Sequence[Choice],
) -> ReadingDocumentFilters:
    """Render a simple title search with the remaining filters collapsed."""
    title_query = ui.text_input(
        "Buscar documentos",
        key=state_key("filter_title"),
        placeholder="Título",
        width="stretch",
    )
    with ui.expander("Más filtros", expanded=False):
        source_id = _select_optional(
            ui,
            "Fuente",
            sources,
            key=state_key("filter_source"),
        )
        reference_id = _select_optional(
            ui,
            "Referencia",
            references,
            key=state_key("filter_reference"),
        )
        kind = ui.selectbox(
            "Formato",
            (None, "pdf", "web"),
            format_func=lambda value: "Todos" if value is None else str(value).upper(),
            key=state_key("filter_kind"),
            width="stretch",
        )
        document_status = ui.selectbox(
            "Estado del documento",
            (None, "active", "archived"),
            format_func=lambda value: "Todos" if value is None else str(value),
            key=state_key("filter_document_status"),
            width="stretch",
        )
        reading_status = ui.selectbox(
            "Estado de lectura",
            (None, "unread", "in_progress", "completed", "deferred"),
            format_func=lambda value: "Todos" if value is None else str(value),
            key=state_key("filter_reading_status"),
            width="stretch",
        )
        order = ui.selectbox(
            "Orden",
            tuple(item.value for item in ReadingSort),
            key=state_key("filter_order"),
            width="stretch",
        )
        tag_text = ui.text_input(
            "Etiquetas (separadas por comas)",
            key=state_key("filter_tags"),
            width="stretch",
        )
    tags = [part.strip() for part in str(tag_text or "").split(",") if part.strip()]
    return ReadingDocumentFilters(
        source_id=source_id,
        reference_id=reference_id,
        kind=kind,
        document_status=document_status,
        reading_status=reading_status,
        tags=tags,
        title_query=str(title_query or "").strip(),
        order=order,
    )


__all__ = ["Choice", "render_filters"]

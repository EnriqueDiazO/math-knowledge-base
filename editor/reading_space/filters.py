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
    """Render every required filter and return the core typed contract."""
    first_row = ui.columns(3)
    with first_row[0]:
        source_id = _select_optional(
            ui,
            "Source",
            sources,
            key=state_key("filter_source"),
        )
    with first_row[1]:
        reference_id = _select_optional(
            ui,
            "Reference",
            references,
            key=state_key("filter_reference"),
        )
    with first_row[2]:
        kind = ui.selectbox(
            "Type",
            (None, "pdf", "web"),
            format_func=lambda value: "All" if value is None else str(value).upper(),
            key=state_key("filter_kind"),
            width="stretch",
        )

    second_row = ui.columns(3)
    with second_row[0]:
        document_status = ui.selectbox(
            "Document status",
            (None, "active", "archived"),
            format_func=lambda value: "All" if value is None else str(value),
            key=state_key("filter_document_status"),
            width="stretch",
        )
    with second_row[1]:
        reading_status = ui.selectbox(
            "Reading status",
            (None, "unread", "in_progress", "completed", "deferred"),
            format_func=lambda value: "All" if value is None else str(value),
            key=state_key("filter_reading_status"),
            width="stretch",
        )
    with second_row[2]:
        order = ui.selectbox(
            "Order",
            tuple(item.value for item in ReadingSort),
            key=state_key("filter_order"),
            width="stretch",
        )

    third_row = ui.columns(2)
    with third_row[0]:
        title_query = ui.text_input(
            "Search title",
            key=state_key("filter_title"),
            width="stretch",
        )
    with third_row[1]:
        tag_text = ui.text_input(
            "Tags (comma separated)",
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

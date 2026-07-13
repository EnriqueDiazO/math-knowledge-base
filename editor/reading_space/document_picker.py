"""Metadata-only Document list and action controls for Reading Space."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from editor.reading_space.state import state_key


def _enum_value(value: Any, default: str = "") -> str:
    return str(getattr(value, "value", value) if value is not None else default)


def _item_parts(item: Any) -> tuple[Any, Any | None, Any | None, Any | None]:
    return (
        item.document,
        getattr(item, "state", None),
        getattr(item, "source", None),
        getattr(item, "reference", None),
    )


def _source_name(source: Any | None, source_id: str) -> str:
    return str(getattr(source, "name", None) or source_id)


def _reference_name(reference: Any | None, reference_id: str | None) -> str:
    if reference_id is None:
        return ""
    return str(
        getattr(reference, "title", None)
        or getattr(getattr(reference, "bibtex", None), "key", None)
        or reference_id
    )


def document_rows(items: tuple[Any, ...] | list[Any]) -> list[dict[str, Any]]:
    """Build display rows without accessing PDF storage."""
    rows: list[dict[str, Any]] = []
    for item in items:
        document, reading, source, reference = _item_parts(item)
        reading_tags = tuple(getattr(reading, "tags", ()) or ())
        rows.append(
            {
                "title": document.title,
                "source": _source_name(source, document.source_id),
                "reference": _reference_name(reference, document.reference_id),
                "kind": _enum_value(document.kind),
                "document_status": _enum_value(document.status),
                "reading_status": _enum_value(
                    getattr(reading, "status", None),
                    "unread",
                ),
                "last_opened_at": getattr(reading, "last_opened_at", None),
                "current_page": getattr(reading, "current_page", None),
                "document_tags": ", ".join(document.tags),
                "reading_tags": ", ".join(reading_tags),
                "document_id": document.document_id,
            }
        )
    return rows


def render_document_picker(
    ui: Any,
    page: Any,
    *,
    actions_enabled: bool,
    on_open: Callable[[Any], None],
    on_completed: Callable[[Any], None],
    on_deferred: Callable[[Any], None],
    on_reset: Callable[[Any], None],
) -> None:
    """Render a bounded page and delegate all writes to injected callbacks."""
    items = tuple(getattr(page, "items", ()))
    page_number = int(getattr(page, "page", 1))
    pages = int(getattr(page, "pages", 0))
    total = int(getattr(page, "total", len(items)))
    ui.caption(f"{total} Documents · página {page_number} de {max(pages, 1)}")
    ui.dataframe(document_rows(items), width="stretch", hide_index=True)
    for item in items:
        document, reading, source, reference = _item_parts(item)
        document_status = _enum_value(document.status)
        reading_status = _enum_value(getattr(reading, "status", None), "unread")
        with ui.expander(
            f"{document.title} · {_enum_value(document.kind)} · {reading_status}",
            expanded=False,
        ):
            ui.write(
                {
                    "document_id": document.document_id,
                    "source": _source_name(source, document.source_id),
                    "reference": _reference_name(reference, document.reference_id),
                    "document_status": document_status,
                    "reading_status": reading_status,
                    "last_opened_at": getattr(reading, "last_opened_at", None),
                    "current_page": getattr(reading, "current_page", None),
                    "document_tags": document.tags,
                    "reading_tags": tuple(getattr(reading, "tags", ()) or ()),
                }
            )
            archived = document_status == "archived"
            if archived:
                ui.warning("Este Document está archivado; la apertura normal está bloqueada.")
            if ui.button(
                "Open",
                key=state_key("open", document.document_id),
                disabled=archived or not actions_enabled,
            ):
                on_open(item)
            if ui.button(
                "Mark completed",
                key=state_key("complete", document.document_id),
                disabled=not actions_enabled,
            ):
                on_completed(item)
            if ui.button(
                "Mark deferred",
                key=state_key("defer", document.document_id),
                disabled=not actions_enabled,
            ):
                on_deferred(item)
            if ui.button(
                "Reset reading state",
                key=state_key("reset", document.document_id),
                disabled=not actions_enabled or reading is None,
            ):
                on_reset(item)


__all__ = ["document_rows", "render_document_picker"]

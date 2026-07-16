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


def _reading_label(value: str) -> str:
    return {
        "unread": "Sin comenzar",
        "in_progress": "En curso",
        "completed": "Completado",
        "deferred": "Pospuesto",
    }.get(value, value.replace("_", " ").capitalize())


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
    ui.caption(f"{total} documentos · página {page_number} de {max(pages, 1)}")
    for item in items:
        document, reading, source, reference = _item_parts(item)
        document_status = _enum_value(document.status)
        reading_status = _enum_value(getattr(reading, "status", None), "unread")
        with ui.container(border=True, key=state_key("library_card", document.document_id)):
            ui.subheader(document.title)
            source_label = _source_name(source, document.source_id)
            reference_label = _reference_name(reference, document.reference_id)
            ui.caption(f"{source_label}" + (f" · {reference_label}" if reference_label else ""))
            kind_label = "PDF" if _enum_value(document.kind) == "pdf" else "Web"
            reading_label = _reading_label(reading_status)
            page = getattr(reading, "current_page", None)
            last_opened = getattr(reading, "last_opened_at", None)
            progress = f" · página {page}" if isinstance(page, int) else ""
            recent = f" · última lectura {last_opened}" if last_opened is not None else ""
            ui.caption(f"{kind_label} · {reading_label}{progress}{recent}")
            archived = document_status == "archived"
            if archived:
                ui.warning("Este documento está archivado; no se puede abrir.")
            if ui.button(
                "Continuar" if reading is not None else "Leer",
                key=state_key("open", document.document_id),
                disabled=archived or not actions_enabled,
                type="primary",
            ):
                on_open(item)
            with ui.expander("Más opciones", expanded=False):
                if ui.button(
                    "Marcar como completado",
                    key=state_key("complete", document.document_id),
                    disabled=not actions_enabled,
                ):
                    on_completed(item)
                if ui.button(
                    "Posponer",
                    key=state_key("defer", document.document_id),
                    disabled=not actions_enabled,
                ):
                    on_deferred(item)
                if ui.button(
                    "Reiniciar progreso",
                    key=state_key("reset", document.document_id),
                    disabled=not actions_enabled or reading is None,
                ):
                    on_reset(item)


__all__ = ["document_rows", "render_document_picker"]

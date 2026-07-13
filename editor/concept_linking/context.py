"""Resolve the current Reading Space context into human-facing metadata."""

from __future__ import annotations

from typing import Any

from editor.concept_linking.view_models import ConceptLinkingContext
from editor.reading_space.state import state_key as reading_state_key


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value or ""))


def _visible_reference(reader: Any) -> tuple[str | None, str | None]:
    reference = getattr(reader, "reference", None)
    if reference is None:
        return getattr(reader.document, "reference_id", None), None
    return (
        getattr(reference, "reference_id", None),
        str(getattr(reference, "title", None) or "Reference sin título"),
    )


def resolve_linking_context(
    catalog_context: Any,
    reader: Any,
    *,
    session_state: Any,
    page_map_service: Any | None = None,
) -> ConceptLinkingContext:
    """Resolve visible names and optional Page Map data without persisting anything."""
    document = reader.document
    kind = _enum_value(document.kind)
    source = getattr(reader, "source", None)
    source_name = str(getattr(source, "name", None) or "Source no disponible")
    reference_id, reference_title = _visible_reference(reader)
    pdf_page: int | None = None
    book_page: str | None = None
    page_map_warning: str | None = None
    if kind == "pdf":
        persisted = getattr(getattr(reader, "reading_state", None), "current_page", None)
        raw_page = session_state.get(
            reading_state_key("current_page", document.document_id), persisted or 1
        )
        if isinstance(raw_page, int) and not isinstance(raw_page, bool) and raw_page > 0:
            pdf_page = raw_page
        else:
            pdf_page = 1
        if page_map_service is not None:
            try:
                result = page_map_service.compute_page_label(
                    document.document_id,
                    pdf_page,
                    user_scope="local",
                )
                if bool(getattr(result, "completed", False)) and result.value is not None:
                    book_page = getattr(result.value, "book_page_label", None)
                else:
                    status = _enum_value(getattr(result, "status", ""))
                    if status not in {"", "success", "not_found"}:
                        page_map_warning = "No se pudo calcular Book page; se usará PDF page."
            except Exception:
                page_map_warning = "No se pudo calcular Book page; se usará PDF page."
    web = getattr(document, "web", None)
    web_url = str(getattr(web, "url_normalized", "") or "") or None
    return ConceptLinkingContext(
        database_name=str(catalog_context.database_name),
        document_id=document.document_id,
        document_title=str(document.title),
        document_kind=kind,
        source_id=document.source_id,
        source_name=source_name,
        reference_id=reference_id,
        reference_title=reference_title,
        pdf_page=pdf_page,
        book_page_label=book_page,
        reading_status=_enum_value(getattr(reader, "effective_status", "")),
        web_url=web_url,
        page_map_warning=page_map_warning,
    )


def render_context_card(ui: Any, context: ConceptLinkingContext) -> None:
    """Render visible context first and keep internal identifiers collapsed."""
    with ui.container(border=True):
        ui.subheader("Contexto actual")
        ui.write(context.document_title)
        ui.caption(f"Source: {context.source_name}")
        ui.caption(
            f"Reference: {context.reference_title}"
            if context.reference_title
            else "Sin Reference asociada"
        )
        ui.caption(f"Ubicación: {context.location_label}")
        ui.caption(f"Estado: {context.reading_status}")
        if context.page_map_warning:
            ui.warning(context.page_map_warning)
    with ui.expander("Detalles técnicos", expanded=False):
        ui.write(
            {
                "database_name": context.database_name,
                "document_id": context.document_id,
                "source_id": context.source_id,
                "reference_id": context.reference_id,
            }
        )


__all__ = ["render_context_card", "resolve_linking_context"]

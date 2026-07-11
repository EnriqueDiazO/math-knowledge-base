"""Streamlit UI for CPI notes."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_footer_text
from editor.cornell.ui_helpers import ALL_LABEL
from editor.cornell.ui_helpers import LATEX_SNIPPET_GROUPS
from editor.cornell.ui_helpers import NEW_PROJECT_LABEL
from editor.cornell.ui_helpers import NO_PROJECT_LABEL
from editor.cornell.ui_helpers import append_latex_snippet
from editor.cornell.ui_helpers import get_existing_note_contexts
from editor.cornell.ui_helpers import get_existing_note_projects
from editor.cornell.ui_helpers import normalize_project_name
from editor.cornell.ui_helpers import normalize_tags
from editor.cornell.ui_helpers import project_selector_choices
from editor.cornell.ui_helpers import resolve_project_choice
from editor.cpi.media import cpi_image_reference
from editor.cpi.models import CPI_NOTE_FORMAT
from editor.cpi.models import DEFAULT_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.persistence import build_cpi_note_document
from editor.cpi.persistence import extract_cpi_document
from editor.cpi.renderer import cpi_latex_full_log
from editor.cpi.renderer import render_cpi_document
from editor.cpi.service import create_cpi_note
from editor.cpi.service import delete_cpi_note
from editor.cpi.service import get_cpi_note
from editor.cpi.service import list_cpi_notes
from editor.cpi.service import update_cpi_note
from editor.note_export import export_note_project
from editor.pdf_preview import open_local_pdf
from editor.pdf_preview import prepare_stable_preview
from editor.utils.media_assets import ALLOWED_IMAGE_EXTENSIONS
from editor.utils.media_assets import media_collection
from editor.utils.media_assets import media_path_exists
from editor.utils.media_assets import save_media_asset
from mathkb_config import PROJECT_ROOT

SESSION_NOTE_ID = "cpi_note_id"
SESSION_DOCUMENT = "cpi_document"
SESSION_PAGE_INDEX = "cpi_page_index"
SESSION_METADATA = "cpi_metadata"
SESSION_DIRTY = "cpi_dirty"
SESSION_RENDERED_PAGE_NUMBER = "cpi_rendered_page_number"
SESSION_VIEW = "cpi_view_state"
SESSION_VIEW_SELECTOR = "cpi_view_selector"
SESSION_PENDING_VIEW = "cpi_pending_view"
SESSION_PENDING_NOTE_ID = "cpi_pending_note_id"
SESSION_PENDING_DELETE_NOTE_ID = "cpi_pending_delete_note_id"
SESSION_FLASH_MESSAGE = "cpi_flash_message"
SESSION_RENDER_DIAGNOSTICS = "cpi_render_diagnostics"
VIEW_NEW_NOTE = "Nueva nota"
VIEW_EXPLORE_NOTES = "Explorar notas"
VIEW_EDIT_NOTES = "Editar notas"
VIEW_OPTIONS = (VIEW_NEW_NOTE, VIEW_EXPLORE_NOTES, VIEW_EDIT_NOTES)
REGION_LABELS = {
    "comprehension": "Comprensión",
    "production": "Producción",
    "integration": "Integración",
}
IDENTITY_POSITION_LABELS = {
    "center": "Centro",
    "bottom_right": "Inferior derecha",
    "top_right": "Superior derecha",
}
WATERMARK_TYPE_LABELS = {
    "text": "Texto",
    "image": "Imagen",
}
FOOTER_MODE_LABELS = {
    "auto": "Automático",
    "custom": "Personalizado",
}


def make_blank_page(page_number: int = 1) -> CpiPage:
    """Create one blank CPI page for UI editing."""
    return CpiPage(
        page_number=page_number,
        comprehension=CpiRegion(heading="Comprensión", latex=""),
        production=CpiRegion(heading="Producción", latex=""),
        integration=CpiRegion(heading="Integración", latex=""),
    )


def make_blank_document() -> CpiDocument:
    """Create a minimal one-page CPI document."""
    return CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(make_blank_page(page_number=1),),
    )


def _document_with_normalized_pages(
    pages: tuple[CpiPage, ...] | list[CpiPage],
    *,
    schema_version: int,
    template_id: str,
    attribution: CornellAttribution | None = None,
    watermark: CornellWatermark | None = None,
) -> CpiDocument:
    normalized_pages = []
    for page_number, page in enumerate(pages, start=1):
        normalized_pages.append(
            CpiPage(
                page_number=page_number,
                comprehension=_region_from_session_value(page.comprehension, "Comprensión"),
                production=_region_from_session_value(page.production, "Producción"),
                integration=_region_from_session_value(page.integration, "Integración"),
            )
        )
    return CpiDocument(
        schema_version=schema_version,
        template_id=template_id,
        pages=tuple(normalized_pages),
        attribution=attribution or CornellAttribution(),
        watermark=watermark or CornellWatermark(),
    )


def _region_from_session_value(region: Any, default_heading: str) -> CpiRegion:
    return CpiRegion(
        heading=str(getattr(region, "heading", default_heading) or default_heading),
        latex=str(getattr(region, "latex", "") or ""),
        image_ids=tuple(getattr(region, "image_ids", ()) or ()),
    )


def normalize_page_numbers(document: CpiDocument) -> CpiDocument:
    """Return a document with page numbers normalized to 1..n."""
    return _document_with_normalized_pages(
        document.ordered_pages(),
        schema_version=document.schema_version,
        template_id=document.template_id,
        attribution=document.attribution,
        watermark=document.watermark,
    )


def replace_page(document: CpiDocument, page_index: int, page: CpiPage) -> CpiDocument:
    """Replace the ordered page at page_index and normalize page numbers."""
    pages = list(document.ordered_pages())
    if not pages:
        pages = [page]
    else:
        safe_index = min(max(page_index, 0), len(pages) - 1)
        pages[safe_index] = page
    return _document_with_normalized_pages(
        pages,
        schema_version=document.schema_version,
        template_id=document.template_id,
        attribution=document.attribution,
        watermark=document.watermark,
    )


def add_page(document: CpiDocument, selected_index: int | None = None) -> tuple[CpiDocument, int]:
    """Add a blank page after the selected page and return the new selected index."""
    pages = list(document.ordered_pages())
    insert_at = len(pages) if selected_index is None else min(max(selected_index + 1, 0), len(pages))
    pages.insert(insert_at, make_blank_page(page_number=insert_at + 1))
    new_document = _document_with_normalized_pages(
        pages,
        schema_version=document.schema_version,
        template_id=document.template_id,
        attribution=document.attribution,
        watermark=document.watermark,
    )
    return new_document, insert_at


def duplicate_page(document: CpiDocument, selected_index: int) -> tuple[CpiDocument, int]:
    """Duplicate the selected page."""
    pages = list(document.ordered_pages())
    if not pages:
        return make_blank_document(), 0
    safe_index = min(max(selected_index, 0), len(pages) - 1)
    source = pages[safe_index]
    duplicate = CpiPage(
        page_number=source.page_number + 1,
        comprehension=source.comprehension,
        production=source.production,
        integration=source.integration,
    )
    insert_at = safe_index + 1
    pages.insert(insert_at, duplicate)
    new_document = _document_with_normalized_pages(
        pages,
        schema_version=document.schema_version,
        template_id=document.template_id,
        attribution=document.attribution,
        watermark=document.watermark,
    )
    return new_document, insert_at


def delete_page(document: CpiDocument, selected_index: int) -> tuple[CpiDocument, int]:
    """Delete the selected page while keeping at least one editable page."""
    pages = list(document.ordered_pages())
    if len(pages) <= 1:
        return normalize_page_numbers(document), 0
    safe_index = min(max(selected_index, 0), len(pages) - 1)
    del pages[safe_index]
    new_index = min(safe_index, len(pages) - 1)
    new_document = _document_with_normalized_pages(
        pages,
        schema_version=document.schema_version,
        template_id=document.template_id,
        attribution=document.attribution,
        watermark=document.watermark,
    )
    return new_document, new_index


def valid_page_index(document: CpiDocument, selected_index: Any) -> int:
    """Clamp the selected page index to the document's available pages."""
    pages = document.ordered_pages()
    if not pages:
        return 0
    try:
        index = int(selected_index)
    except (TypeError, ValueError):
        index = 0
    return min(max(index, 0), len(pages) - 1)


def _metadata_from_note(note: dict[str, Any] | None = None) -> dict[str, Any]:
    today = date.today().isoformat()
    source = note or {}
    return {
        "title": source.get("title") or "Nueva nota CPI",
        "date": source.get("date") or today,
        "project": source.get("project") or "",
        "context": source.get("context") or "estudio",
        "tags": list(source.get("tags") or []),
    }


def normalize_cpi_view(view: Any) -> str:
    """Return a valid CPI navigation view."""
    return str(view) if view in VIEW_OPTIONS else VIEW_NEW_NOTE


def queue_cpi_navigation(
    state: dict[str, Any],
    *,
    view: str,
    note_id: Any | None = None,
) -> None:
    """Queue navigation without mutating the current radio widget key."""
    state[SESSION_PENDING_VIEW] = normalize_cpi_view(view)
    if note_id is not None:
        state[SESSION_PENDING_NOTE_ID] = str(note_id)


def apply_pending_view_state(state: dict[str, Any]) -> str:
    """Apply queued view before the navigation selector is instantiated."""
    pending_view = state.pop(SESSION_PENDING_VIEW, None)
    if pending_view is not None:
        view = normalize_cpi_view(pending_view)
        state[SESSION_VIEW] = view
        state[SESSION_VIEW_SELECTOR] = view
    return normalize_cpi_view(state.get(SESSION_VIEW))


def consume_pending_note_id(state: dict[str, Any]) -> str | None:
    """Return and clear the note id queued for opening/editing."""
    note_id = state.pop(SESSION_PENDING_NOTE_ID, None)
    return str(note_id) if note_id is not None else None


def request_cpi_note_delete(state: dict[str, Any], note_id: Any) -> None:
    """Mark a CPI note as pending deletion without touching storage."""
    state[SESSION_PENDING_DELETE_NOTE_ID] = str(note_id)


def cancel_cpi_note_delete(state: dict[str, Any], note_id: Any | None = None) -> None:
    """Clear pending delete confirmation, optionally only for a specific note."""
    pending_id = state.get(SESSION_PENDING_DELETE_NOTE_ID)
    if note_id is None or (pending_id is not None and str(pending_id) == str(note_id)):
        state.pop(SESSION_PENDING_DELETE_NOTE_ID, None)


def _same_note_id(left: Any, right: Any) -> bool:
    return left is not None and right is not None and str(left) == str(right)


def _set_flash_message(state: dict[str, Any], level: str, message: str) -> None:
    state[SESSION_FLASH_MESSAGE] = {"level": level, "message": message}


def _reset_page_widget_sync(state: dict[str, Any]) -> None:
    state.pop(SESSION_RENDERED_PAGE_NUMBER, None)


def apply_loaded_note_state(
    state: dict[str, Any],
    *,
    note_id: Any,
    note: dict[str, Any] | None,
    document: CpiDocument,
) -> None:
    """Replace the editable note state, clearing stale editor values."""
    normalized_document = normalize_page_numbers(document)
    metadata = _metadata_from_note(note)
    state[SESSION_NOTE_ID] = str(note_id) if note_id is not None else None
    state[SESSION_METADATA] = metadata
    state[SESSION_DOCUMENT] = normalized_document
    state[SESSION_PAGE_INDEX] = 0
    state[SESSION_DIRTY] = False
    state.pop(SESSION_RENDER_DIAGNOSTICS, None)

    pages = normalized_document.ordered_pages()
    first_page = pages[0] if pages else make_blank_page()
    state[SESSION_RENDERED_PAGE_NUMBER] = first_page.page_number
    state["cpi_title"] = metadata["title"]
    state["cpi_date"] = _safe_date(metadata["date"])
    state["cpi_project"] = metadata["project"]
    state.pop("cpi_project_choice", None)
    state.pop("cpi_project_new", None)
    state["cpi_context"] = metadata["context"]
    state["cpi_tags"] = ", ".join(metadata["tags"])
    state["cpi_comprehension_latex"] = first_page.comprehension.latex
    state["cpi_production_latex"] = first_page.production.latex
    state["cpi_integration_latex"] = first_page.integration.latex
    _sync_identity_state_values(state, normalized_document)


def clear_deleted_note_state(state: dict[str, Any], note_id: Any) -> None:
    """Clear editor/session state that points at a note deleted from storage."""
    cancel_cpi_note_delete(state, note_id)
    if _same_note_id(state.get(SESSION_PENDING_NOTE_ID), note_id):
        state.pop(SESSION_PENDING_NOTE_ID, None)
    if not _same_note_id(state.get(SESSION_NOTE_ID), note_id):
        return
    apply_loaded_note_state(
        state,
        note_id=None,
        note=None,
        document=make_blank_document(),
    )


def confirm_cpi_note_delete(state: dict[str, Any], db: Any, note_id: Any) -> str:
    """Delete exactly one CPI note and return deleted, missing, or failed."""
    result = delete_cpi_note(db, note_id)
    deleted_count = 0 if result is None else int(getattr(result, "deleted_count", 0) or 0)
    if deleted_count == 1:
        clear_deleted_note_state(state, note_id)
        _set_flash_message(state, "success", "Nota CPI borrada correctamente.")
        return "deleted"
    if deleted_count == 0:
        clear_deleted_note_state(state, note_id)
        _set_flash_message(state, "warning", "La nota ya no existe. La lista se actualizó.")
        return "missing"
    raise RuntimeError(f"La eliminación informó {deleted_count} documentos borrados; se esperaba exactamente 1.")


def _safe_date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return date.today()


def _ensure_state() -> None:
    import streamlit as st

    if SESSION_DOCUMENT not in st.session_state:
        st.session_state[SESSION_DOCUMENT] = make_blank_document()
    if SESSION_PAGE_INDEX not in st.session_state:
        st.session_state[SESSION_PAGE_INDEX] = 0
    if SESSION_METADATA not in st.session_state:
        st.session_state[SESSION_METADATA] = _metadata_from_note()
    if SESSION_NOTE_ID not in st.session_state:
        st.session_state[SESSION_NOTE_ID] = None
    if SESSION_DIRTY not in st.session_state:
        st.session_state[SESSION_DIRTY] = False
    if SESSION_VIEW not in st.session_state:
        st.session_state[SESSION_VIEW] = VIEW_NEW_NOTE


def _set_current_note(note_id: Any, note: dict[str, Any] | None, document: CpiDocument) -> None:
    import streamlit as st

    apply_loaded_note_state(
        st.session_state,
        note_id=note_id,
        note=note,
        document=document,
    )


def _sync_page_widget_state(page: CpiPage) -> None:
    import streamlit as st

    if st.session_state.get(SESSION_RENDERED_PAGE_NUMBER) == page.page_number:
        return
    st.session_state[SESSION_RENDERED_PAGE_NUMBER] = page.page_number
    st.session_state["cpi_comprehension_latex"] = page.comprehension.latex
    st.session_state["cpi_production_latex"] = page.production.latex
    st.session_state["cpi_integration_latex"] = page.integration.latex


def _position_label(position: str) -> str:
    return IDENTITY_POSITION_LABELS.get(position, IDENTITY_POSITION_LABELS["center"])


def _position_value(label: Any, *, default: str = "center") -> str:
    text = str(label or "")
    for value, display in IDENTITY_POSITION_LABELS.items():
        if text == display or text == value:
            return value
    return default


def _watermark_type_label(value: str) -> str:
    return WATERMARK_TYPE_LABELS.get(value, WATERMARK_TYPE_LABELS["text"])


def _watermark_type_value(label: Any) -> str:
    text = str(label or "")
    for value, display in WATERMARK_TYPE_LABELS.items():
        if text == display or text == value:
            return value
    return "text"


def _footer_mode_label(value: str) -> str:
    return FOOTER_MODE_LABELS.get(value, FOOTER_MODE_LABELS["auto"])


def _footer_mode_value(label: Any) -> str:
    text = str(label or "")
    for value, display in FOOTER_MODE_LABELS.items():
        if text == display or text == value:
            return value
    return "auto"


def _sync_identity_state_values(state: dict[str, Any], document: CpiDocument) -> None:
    attribution = document.attribution
    watermark = document.watermark
    state["cpi_attribution_enabled"] = attribution.enabled
    state["cpi_attribution_mode"] = _footer_mode_label(attribution.mode)
    state["cpi_attribution_text"] = attribution.text
    state["cpi_attribution_author"] = attribution.author
    state["cpi_attribution_course"] = attribution.course
    state["cpi_attribution_year"] = attribution.year
    state["cpi_attribution_position"] = _position_label(attribution.position)
    state["cpi_watermark_enabled"] = watermark.enabled
    state["cpi_watermark_type"] = _watermark_type_label(watermark.type)
    state["cpi_watermark_text"] = watermark.text
    state["cpi_watermark_image_id"] = watermark.image_id
    state["cpi_watermark_opacity"] = watermark.opacity
    state["cpi_watermark_scale"] = watermark.scale
    state["cpi_watermark_position"] = _position_label(watermark.position)


def _ensure_identity_widget_state(document: CpiDocument) -> None:
    import streamlit as st

    defaults: dict[str, Any] = {}
    _sync_identity_state_values(defaults, document)
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _document_with_identity_from_inputs(document: CpiDocument) -> CpiDocument:
    import streamlit as st

    attribution = CornellAttribution(
        enabled=bool(st.session_state.get("cpi_attribution_enabled", document.attribution.enabled)),
        mode=_footer_mode_value(st.session_state.get("cpi_attribution_mode")),
        text=str(st.session_state.get("cpi_attribution_text", document.attribution.text) or ""),
        author=str(st.session_state.get("cpi_attribution_author", document.attribution.author) or ""),
        course=str(st.session_state.get("cpi_attribution_course", document.attribution.course) or ""),
        year=str(st.session_state.get("cpi_attribution_year", document.attribution.year) or ""),
        position=_position_value(
            st.session_state.get("cpi_attribution_position"),
            default=document.attribution.position,
        ),
    )
    watermark = CornellWatermark(
        enabled=bool(st.session_state.get("cpi_watermark_enabled", document.watermark.enabled)),
        type=_watermark_type_value(st.session_state.get("cpi_watermark_type")),
        text=str(st.session_state.get("cpi_watermark_text", document.watermark.text) or ""),
        image_id=str(st.session_state.get("cpi_watermark_image_id", document.watermark.image_id) or ""),
        opacity=float(st.session_state.get("cpi_watermark_opacity", document.watermark.opacity)),
        scale=float(st.session_state.get("cpi_watermark_scale", document.watermark.scale)),
        position=_position_value(
            st.session_state.get("cpi_watermark_position"),
            default=document.watermark.position,
        ),
    )
    return CpiDocument(
        schema_version=document.schema_version,
        template_id=document.template_id,
        pages=document.pages,
        attribution=attribution,
        watermark=watermark,
    )


def _current_page_from_inputs(page: CpiPage) -> CpiPage:
    import streamlit as st

    return CpiPage(
        page_number=page.page_number,
        comprehension=CpiRegion(
            heading=page.comprehension.heading or "Comprensión",
            latex=st.session_state.get("cpi_comprehension_latex", page.comprehension.latex),
            image_ids=page.comprehension.image_ids,
        ),
        production=CpiRegion(
            heading=page.production.heading or "Producción",
            latex=st.session_state.get("cpi_production_latex", page.production.latex),
            image_ids=page.production.image_ids,
        ),
        integration=CpiRegion(
            heading=page.integration.heading or "Integración",
            latex=st.session_state.get("cpi_integration_latex", page.integration.latex),
            image_ids=page.integration.image_ids,
        ),
    )


def _document_from_inputs() -> CpiDocument:
    import streamlit as st

    document = st.session_state[SESSION_DOCUMENT]
    pages = document.ordered_pages()
    if not pages:
        return make_blank_document()
    page_index = valid_page_index(document, st.session_state.get(SESSION_PAGE_INDEX))
    current_page = _current_page_from_inputs(pages[page_index])
    return _document_with_identity_from_inputs(replace_page(document, page_index, current_page))


def _metadata_from_inputs() -> dict[str, Any]:
    import streamlit as st

    project_choice = st.session_state.get("cpi_project_choice", NO_PROJECT_LABEL)
    project_new = st.session_state.get("cpi_project_new", "")
    return {
        "title": st.session_state.get("cpi_title") or "Nueva nota CPI",
        "date": st.session_state.get("cpi_date", date.today()).isoformat(),
        "project": resolve_project_choice(project_choice, project_new),
        "context": st.session_state.get("cpi_context") or "estudio",
        "tags": normalize_tags(st.session_state.get("cpi_tags", "")),
    }


def _mark_dirty() -> None:
    import streamlit as st

    st.session_state[SESSION_DIRTY] = True
    st.session_state.pop(SESSION_RENDER_DIAGNOSTICS, None)


def _sync_view_from_selector() -> None:
    import streamlit as st

    st.session_state[SESSION_VIEW] = normalize_cpi_view(st.session_state.get(SESSION_VIEW_SELECTOR))


def _request_navigation(view: str, note_id: Any | None = None) -> None:
    import streamlit as st

    queue_cpi_navigation(st.session_state, view=view, note_id=note_id)


def _apply_pending_navigation(db: Any) -> None:
    import streamlit as st

    note_id = consume_pending_note_id(st.session_state)
    if note_id is not None:
        try:
            opened = get_cpi_note(db, note_id)
            if opened is None:
                st.warning("La nota seleccionada ya no existe.")
            else:
                _set_current_note(note_id, opened, extract_cpi_document(opened))
        except Exception as exc:
            st.error(f"No se pudo abrir como CPI: {exc}")
    apply_pending_view_state(st.session_state)


def _render_navigation() -> str:
    import streamlit as st

    st.subheader("CPI")
    current_view = normalize_cpi_view(st.session_state.get(SESSION_VIEW))
    if st.session_state.get(SESSION_VIEW_SELECTOR) not in VIEW_OPTIONS:
        st.session_state[SESSION_VIEW_SELECTOR] = current_view
    view = st.radio(
        "Vista",
        options=VIEW_OPTIONS,
        key=SESSION_VIEW_SELECTOR,
        on_change=_sync_view_from_selector,
    )
    st.session_state[SESSION_VIEW] = normalize_cpi_view(view)
    if st.button("Nueva nota CPI", use_container_width=True):
        _set_current_note(None, None, make_blank_document())
        _request_navigation(VIEW_NEW_NOTE)
        st.rerun()
    return normalize_cpi_view(view)


def _cpi_page_count(note: dict[str, Any]) -> int:
    pages = ((note.get("cpi") or {}).get("pages") or []) if isinstance(note, dict) else []
    return len(pages)


def _filter_cpi_notes_for_explorer(
    notes: list[dict[str, Any]],
    *,
    text: str = "",
    project: str = ALL_LABEL,
    context: str = ALL_LABEL,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    text_q = (text or "").strip().lower()
    filtered = []
    for note in notes:
        if note.get("note_format") != CPI_NOTE_FORMAT:
            continue
        note_project = normalize_project_name(str(note.get("project") or ""))
        if project not in (ALL_LABEL, None):
            if project == NO_PROJECT_LABEL and note_project:
                continue
            if project != NO_PROJECT_LABEL and note_project != normalize_project_name(project):
                continue
        if context != ALL_LABEL and (note.get("context") or "") != context:
            continue
        note_date = str(note.get("date") or "")
        if start_date and note_date < start_date.strftime("%Y-%m-%d"):
            continue
        if end_date and note_date > end_date.strftime("%Y-%m-%d"):
            continue
        if text_q:
            haystack = "\n".join(
                [
                    str(note.get("title") or ""),
                    str(note.get("latex_body") or ""),
                    str(note.get("project") or ""),
                    str(note.get("context") or ""),
                ]
            ).lower()
            if text_q not in haystack:
                continue
        filtered.append(note)
    return filtered


def _render_flash_message() -> None:
    import streamlit as st

    flash = st.session_state.pop(SESSION_FLASH_MESSAGE, None)
    if not isinstance(flash, dict):
        return
    message = str(flash.get("message") or "")
    if not message:
        return
    level = str(flash.get("level") or "info")
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.info(message)


def _render_note_browser(
    db: Any,
    *,
    title: str,
    key_prefix: str,
    action_label: str,
    destination_view: str,
    allow_delete: bool = False,
) -> None:
    import streamlit as st

    st.subheader(title)
    _render_flash_message()
    try:
        notes = list_cpi_notes(db, limit=500)
    except Exception as exc:
        st.error(f"No se pudieron listar las notas CPI: {exc}")
        return

    if not notes:
        st.caption("No hay notas CPI todavía.")
        return

    projects = sorted({note.get("project") or NO_PROJECT_LABEL for note in notes}, key=str.lower)
    contexts = sorted({note.get("context") or "" for note in notes if note.get("context")}, key=str.lower)
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        text_q = st.text_input("Buscar", value="", key=f"{key_prefix}_text")
    with f2:
        project = st.selectbox(
            "Proyecto",
            options=[ALL_LABEL, NO_PROJECT_LABEL, *[p for p in projects if p != NO_PROJECT_LABEL]],
            key=f"{key_prefix}_project",
        )
    with f3:
        context = st.selectbox(
            "Contexto",
            options=[ALL_LABEL, *contexts],
            key=f"{key_prefix}_context",
        )

    use_date = st.checkbox("Filtrar por fecha", value=False, key=f"{key_prefix}_use_date")
    start_date = end_date = None
    if use_date:
        d1, d2 = st.columns(2)
        with d1:
            start_date = st.date_input("Desde", value=date.today(), key=f"{key_prefix}_start")
        with d2:
            end_date = st.date_input("Hasta", value=date.today(), key=f"{key_prefix}_end")

    filtered = _filter_cpi_notes_for_explorer(
        notes,
        text=text_q,
        project=project,
        context=context,
        start_date=start_date,
        end_date=end_date,
    )
    st.caption(f"Resultados: {len(filtered)}")
    for row_index, note in enumerate(filtered):
        raw_note_id = note.get("_id")
        note_id = str(raw_note_id) if raw_note_id is not None else ""
        row_key = note_id or f"missing_id_{row_index}"
        cols = st.columns([2, 1, 1, 1, 1, 0.8, 0.8] if allow_delete else [2, 1, 1, 1, 1, 0.8])
        cols[0].write(note.get("title") or "Sin título")
        cols[1].write(note.get("date") or "")
        cols[2].write(note.get("project") or "Sin proyecto")
        cols[3].write(note.get("context") or "")
        cols[4].write(f"{_cpi_page_count(note)} págs.")
        if cols[5].button(
            action_label,
            key=f"{key_prefix}_open_{row_key}",
            disabled=not note_id,
        ):
            _request_navigation(destination_view, note_id=note_id)
            st.rerun()
        if not allow_delete:
            continue

        if cols[6].button(
            "Borrar",
            key=f"{key_prefix}_delete_{row_key}",
            disabled=not note_id,
        ):
            request_cpi_note_delete(st.session_state, note_id)
            st.rerun()

        if not _same_note_id(st.session_state.get(SESSION_PENDING_DELETE_NOTE_ID), note_id):
            continue

        title_text = str(note.get("title") or "Sin título")
        project_text = str(note.get("project") or "").strip()
        st.warning("¿Seguro que deseas borrar esta nota?")
        st.markdown(f"**Título:** {title_text}")
        if project_text:
            st.markdown(f"**Proyecto:** {project_text}")
        confirm_cols = st.columns([1, 1.6, 3])
        if confirm_cols[0].button("Cancelar", key=f"{key_prefix}_cancel_delete_{note_id}"):
            cancel_cpi_note_delete(st.session_state, note_id)
            st.rerun()
        if confirm_cols[1].button(
            "Sí, borrar definitivamente",
            key=f"{key_prefix}_confirm_delete_{note_id}",
        ):
            try:
                confirm_cpi_note_delete(st.session_state, db, note_id)
            except Exception as exc:
                st.error(f"No se pudo borrar la nota CPI: {exc}")
            else:
                st.rerun()


def _render_explorer(db: Any) -> None:
    _render_note_browser(
        db,
        title="Explorar notas CPI",
        key_prefix="cpi_explore",
        action_label="Abrir",
        destination_view=VIEW_EDIT_NOTES,
    )


def _render_edit_note_picker(db: Any) -> None:
    _render_note_browser(
        db,
        title="Editar notas CPI",
        key_prefix="cpi_edit",
        action_label="Editar",
        destination_view=VIEW_EDIT_NOTES,
        allow_delete=True,
    )


def _render_page_controls() -> None:
    import streamlit as st

    document = _document_from_inputs()
    pages = document.ordered_pages()
    page_index = valid_page_index(document, st.session_state.get(SESSION_PAGE_INDEX))
    st.session_state[SESSION_DOCUMENT] = document
    st.session_state[SESSION_PAGE_INDEX] = page_index

    col_prev, col_count, col_next, col_add, col_dup, col_del = st.columns([1, 1.4, 1, 1, 1, 1])
    with col_prev:
        if st.button("Anterior", disabled=page_index <= 0, use_container_width=True):
            st.session_state[SESSION_PAGE_INDEX] = page_index - 1
            st.rerun()
    with col_count:
        st.markdown(f"**Página {page_index + 1} / {len(pages)}**")
    with col_next:
        if st.button("Siguiente", disabled=page_index >= len(pages) - 1, use_container_width=True):
            st.session_state[SESSION_PAGE_INDEX] = page_index + 1
            st.rerun()
    with col_add:
        if st.button("Añadir", use_container_width=True):
            st.session_state[SESSION_DOCUMENT], st.session_state[SESSION_PAGE_INDEX] = add_page(
                document,
                page_index,
            )
            _reset_page_widget_sync(st.session_state)
            _mark_dirty()
            st.rerun()
    with col_dup:
        if st.button("Duplicar", use_container_width=True):
            st.session_state[SESSION_DOCUMENT], st.session_state[SESSION_PAGE_INDEX] = duplicate_page(
                document,
                page_index,
            )
            _reset_page_widget_sync(st.session_state)
            _mark_dirty()
            st.rerun()
    with col_del:
        if st.button("Eliminar", disabled=len(pages) <= 1, use_container_width=True):
            st.session_state[SESSION_DOCUMENT], st.session_state[SESSION_PAGE_INDEX] = delete_page(
                document,
                page_index,
            )
            _reset_page_widget_sync(st.session_state)
            _mark_dirty()
            st.rerun()


def _render_metadata_editor(db: Any) -> None:
    import streamlit as st

    metadata = st.session_state[SESSION_METADATA]
    st.text_input("Título", value=metadata["title"], key="cpi_title", on_change=_mark_dirty)
    st.date_input(
        "Fecha",
        value=_safe_date(metadata["date"]),
        key="cpi_date",
        on_change=_mark_dirty,
    )
    projects = get_existing_note_projects(db)
    project_choices, project_index = project_selector_choices(projects, metadata["project"])
    project_choice = st.selectbox(
        "Proyecto (opcional)",
        options=project_choices,
        index=project_index,
        key="cpi_project_choice",
        on_change=_mark_dirty,
    )
    if project_choice == NEW_PROJECT_LABEL:
        st.text_input(
            "Proyecto nuevo",
            value=metadata["project"],
            key="cpi_project_new",
            on_change=_mark_dirty,
        )

    contexts = get_existing_note_contexts(db)
    context_index = contexts.index(metadata["context"]) if metadata["context"] in contexts else 0
    st.selectbox(
        "Contexto",
        options=contexts,
        index=context_index,
        key="cpi_context",
        on_change=_mark_dirty,
    )
    st.text_input(
        "Tags",
        value=", ".join(metadata["tags"]),
        key="cpi_tags",
        on_change=_mark_dirty,
    )


def _render_identity_editor(db: Any) -> None:
    import streamlit as st

    document = _document_from_inputs()
    _ensure_identity_widget_state(document)
    with st.expander("Identidad del material", expanded=False):
        st.checkbox(
            "Mostrar pie de página",
            key="cpi_attribution_enabled",
            on_change=_mark_dirty,
        )
        st.radio(
            "Modo del pie",
            options=tuple(FOOTER_MODE_LABELS.values()),
            horizontal=True,
            key="cpi_attribution_mode",
            on_change=_mark_dirty,
        )
        footer_mode = _footer_mode_value(st.session_state.get("cpi_attribution_mode"))
        if footer_mode == "auto":
            attr_author, attr_course, attr_year = st.columns([2, 2, 1])
            attr_author.text_input("Autor", key="cpi_attribution_author", on_change=_mark_dirty)
            attr_course.text_input("Curso", key="cpi_attribution_course", on_change=_mark_dirty)
            attr_year.text_input("Año", key="cpi_attribution_year", on_change=_mark_dirty)
        else:
            st.text_input(
                "Texto del pie",
                key="cpi_attribution_text",
                placeholder="© Enrique Díaz Ocampo · Material Docente",
                on_change=_mark_dirty,
            )
        st.selectbox(
            "Posición del pie",
            options=tuple(IDENTITY_POSITION_LABELS.values()),
            key="cpi_attribution_position",
            on_change=_mark_dirty,
        )
        footer_preview = build_footer_text(
            mode=footer_mode,
            text=str(st.session_state.get("cpi_attribution_text") or ""),
            author=str(st.session_state.get("cpi_attribution_author") or ""),
            course=str(st.session_state.get("cpi_attribution_course") or ""),
            year=str(st.session_state.get("cpi_attribution_year") or ""),
        )
        st.markdown("**Vista previa del pie:**")
        st.caption(footer_preview or "Sin pie de página")

        st.markdown("---")
        st.checkbox(
            "Mostrar marca de agua",
            key="cpi_watermark_enabled",
            on_change=_mark_dirty,
        )
        st.radio(
            "Tipo",
            options=tuple(WATERMARK_TYPE_LABELS.values()),
            horizontal=True,
            key="cpi_watermark_type",
            on_change=_mark_dirty,
        )
        watermark_type = _watermark_type_value(st.session_state.get("cpi_watermark_type"))
        if watermark_type == "text":
            st.text_input(
                "Texto de marca de agua",
                key="cpi_watermark_text",
                on_change=_mark_dirty,
            )
        else:
            uploaded = st.file_uploader(
                "Subir imagen",
                type=("png", "svg"),
                key="cpi_watermark_upload",
            )
            if st.button("Guardar imagen de marca", disabled=uploaded is None, key="cpi_watermark_save"):
                try:
                    asset = save_media_asset(
                        db,
                        note_id=str(st.session_state.get(SESSION_NOTE_ID) or "") or None,
                        filename=uploaded.name,
                        data=uploaded.getvalue(),
                        mime_type=getattr(uploaded, "type", None),
                        tags=["cpi", "watermark"],
                        description="CPI watermark",
                    )
                    st.session_state["cpi_watermark_image_id"] = asset["asset_id"]
                    _mark_dirty()
                    st.success("Imagen de marca asociada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar la imagen de marca: {exc}")
            image_id = str(st.session_state.get("cpi_watermark_image_id") or "")
            if image_id:
                try:
                    assets = list(media_collection(db).find({"asset_id": {"$in": [image_id]}}))
                except Exception as exc:
                    st.warning(f"No se pudo cargar la imagen de marca: {exc}")
                    assets = []
                if assets:
                    asset = assets[0]
                    st.caption(asset.get("original_filename") or asset.get("filename") or image_id)
                    if media_path_exists(asset):
                        st.image(str(PROJECT_ROOT / asset.get("path")), width=140)
                    if st.button("Quitar imagen de marca", key="cpi_watermark_remove"):
                        st.session_state["cpi_watermark_image_id"] = ""
                        _mark_dirty()
                        st.rerun()
                else:
                    st.warning(f"Asset de marca no encontrado: {image_id}")

        opacity_col, scale_col, position_col = st.columns(3)
        opacity_col.slider(
            "Opacidad",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            key="cpi_watermark_opacity",
            on_change=_mark_dirty,
        )
        scale_col.slider(
            "Tamaño",
            min_value=0.05,
            max_value=1.0,
            step=0.01,
            key="cpi_watermark_scale",
            on_change=_mark_dirty,
        )
        position_col.selectbox(
            "Posición",
            options=tuple(IDENTITY_POSITION_LABELS.values()),
            key="cpi_watermark_position",
            on_change=_mark_dirty,
        )


def _render_latex_tools() -> None:
    import streamlit as st

    with st.expander("Herramientas LaTeX", expanded=False):
        target = st.selectbox(
            "Insertar en",
            options=tuple(REGION_LABELS.values()),
            key="cpi_latex_insert_target",
        )
        target_key = {
            "Comprensión": "cpi_comprehension_latex",
            "Producción": "cpi_production_latex",
            "Integración": "cpi_integration_latex",
        }[target]
        cols = st.columns(4)
        for index, group in enumerate(LATEX_SNIPPET_GROUPS[:4]):
            with cols[index]:
                st.caption(group.title)
                for snippet in group.snippets:
                    if st.button(snippet.label, key=f"cpi_tool_{target_key}_{snippet.key}"):
                        st.session_state[target_key] = append_latex_snippet(
                            st.session_state.get(target_key, ""),
                            snippet.snippet,
                        )
                        _mark_dirty()
                        st.rerun()
        st.caption(LATEX_SNIPPET_GROUPS[4].title)
        semantic_cols = st.columns(5)
        for index, snippet in enumerate(LATEX_SNIPPET_GROUPS[4].snippets):
            with semantic_cols[index % len(semantic_cols)]:
                if st.button(snippet.label, key=f"cpi_tool_{target_key}_{snippet.key}"):
                    st.session_state[target_key] = append_latex_snippet(
                        st.session_state.get(target_key, ""),
                        snippet.snippet,
                    )
                    _mark_dirty()
                    st.rerun()


def _render_page_editor(db: Any, page: CpiPage, page_index: int) -> None:
    import streamlit as st

    _render_latex_tools()
    comprehension_col, production_col = st.columns(2)
    with comprehension_col:
        st.subheader("Comprensión")
        st.caption("Valor epistémico")
        st.text_area(
            "LaTeX Comprensión",
            value=page.comprehension.latex,
            height=280,
            key="cpi_comprehension_latex",
            on_change=_mark_dirty,
        )
        region_name = "comprehension"
        region = page.comprehension
        label = REGION_LABELS[region_name]
        latex_key = "cpi_comprehension_latex"
        safe_prefix = f"cpi_page_{page_index + 1}_{page.page_number}_{region_name}_media"
        with st.expander(f"{label} · Imágenes: {len(region.image_ids)}", expanded=False):
            uploaded = st.file_uploader(
                f"Subir imagen para {label}",
                type=[extension.lstrip(".") for extension in ALLOWED_IMAGE_EXTENSIONS],
                key=f"{safe_prefix}_upload",
            )
            description = st.text_input("Descripción", key=f"{safe_prefix}_description")
            tags = st.text_input("Tags", key=f"{safe_prefix}_tags")
            if st.button("Guardar imagen", key=f"{safe_prefix}_save", disabled=uploaded is None):
                try:
                    document = _document_from_inputs()
                    note_id = st.session_state.get(SESSION_NOTE_ID)
                    asset = save_media_asset(
                        db,
                        note_id=str(note_id) if note_id else None,
                        filename=uploaded.name,
                        data=uploaded.getvalue(),
                        mime_type=getattr(uploaded, "type", None),
                        tags=normalize_tags(tags),
                        description=description,
                    )
                    pages = document.ordered_pages()
                    safe_index = valid_page_index(document, page_index)
                    current_page = pages[safe_index]
                    image_ids = list(current_page.comprehension.image_ids)
                    if asset["asset_id"] not in image_ids:
                        image_ids.append(asset["asset_id"])
                    updated_page = CpiPage(
                        page_number=current_page.page_number,
                        comprehension=CpiRegion(
                            heading=current_page.comprehension.heading,
                            latex=current_page.comprehension.latex,
                            image_ids=tuple(image_ids),
                        ),
                        production=current_page.production,
                        integration=current_page.integration,
                    )
                    st.session_state[SESSION_DOCUMENT] = replace_page(
                        document,
                        safe_index,
                        updated_page,
                    )
                    _mark_dirty()
                    st.success(f"Imagen asociada a {label}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar la imagen: {exc}")
            clean_ids = [asset_id for asset_id in region.image_ids if str(asset_id or "").strip()]
            try:
                assets = (
                    list(media_collection(db).find({"asset_id": {"$in": clean_ids}}))
                    if clean_ids
                    else []
                )
            except Exception as exc:
                st.error(f"No se pudieron cargar las imágenes de {label}: {exc}")
                assets = []
            assets_by_id = {asset.get("asset_id"): asset for asset in assets}
            for asset_id in region.image_ids:
                asset = assets_by_id.get(asset_id)
                if not asset:
                    st.warning(f"Asset faltante en {label}: {asset_id}")
                    continue
                st.markdown(f"**{asset.get('original_filename') or asset.get('filename') or asset_id}**")
                if media_path_exists(asset):
                    st.image(str(PROJECT_ROOT / asset.get("path")), caption=asset.get("description") or "")
                else:
                    st.warning(f"Archivo faltante: {asset.get('path')}")
                ref = cpi_image_reference(asset_id)
                st.code(ref, language="latex")
                col_insert, col_remove = st.columns(2)
                if col_insert.button("Insertar referencia LaTeX", key=f"{safe_prefix}_insert_{asset_id}"):
                    st.session_state[latex_key] = append_latex_snippet(
                        st.session_state.get(latex_key, ""),
                        ref,
                    )
                    _mark_dirty()
                    st.rerun()
                if col_remove.button("Quitar asociación", key=f"{safe_prefix}_remove_{asset_id}"):
                    document = _document_from_inputs()
                    pages = document.ordered_pages()
                    safe_index = valid_page_index(document, page_index)
                    current_page = pages[safe_index]
                    updated_page = CpiPage(
                        page_number=current_page.page_number,
                        comprehension=CpiRegion(
                            heading=current_page.comprehension.heading,
                            latex=current_page.comprehension.latex,
                            image_ids=tuple(
                                image_id
                                for image_id in current_page.comprehension.image_ids
                                if image_id != asset_id
                            ),
                        ),
                        production=current_page.production,
                        integration=current_page.integration,
                    )
                    st.session_state[SESSION_DOCUMENT] = replace_page(
                        document,
                        safe_index,
                        updated_page,
                    )
                    _mark_dirty()
                    st.rerun()
    with production_col:
        st.subheader("Producción")
        st.caption("Valor pragmático")
        st.text_area(
            "LaTeX Producción",
            value=page.production.latex,
            height=280,
            key="cpi_production_latex",
            on_change=_mark_dirty,
        )
        region_name = "production"
        region = page.production
        label = REGION_LABELS[region_name]
        latex_key = "cpi_production_latex"
        safe_prefix = f"cpi_page_{page_index + 1}_{page.page_number}_{region_name}_media"
        with st.expander(f"{label} · Imágenes: {len(region.image_ids)}", expanded=False):
            uploaded = st.file_uploader(
                f"Subir imagen para {label}",
                type=[extension.lstrip(".") for extension in ALLOWED_IMAGE_EXTENSIONS],
                key=f"{safe_prefix}_upload",
            )
            description = st.text_input("Descripción", key=f"{safe_prefix}_description")
            tags = st.text_input("Tags", key=f"{safe_prefix}_tags")
            if st.button("Guardar imagen", key=f"{safe_prefix}_save", disabled=uploaded is None):
                try:
                    document = _document_from_inputs()
                    note_id = st.session_state.get(SESSION_NOTE_ID)
                    asset = save_media_asset(
                        db,
                        note_id=str(note_id) if note_id else None,
                        filename=uploaded.name,
                        data=uploaded.getvalue(),
                        mime_type=getattr(uploaded, "type", None),
                        tags=normalize_tags(tags),
                        description=description,
                    )
                    pages = document.ordered_pages()
                    safe_index = valid_page_index(document, page_index)
                    current_page = pages[safe_index]
                    image_ids = list(current_page.production.image_ids)
                    if asset["asset_id"] not in image_ids:
                        image_ids.append(asset["asset_id"])
                    updated_page = CpiPage(
                        page_number=current_page.page_number,
                        comprehension=current_page.comprehension,
                        production=CpiRegion(
                            heading=current_page.production.heading,
                            latex=current_page.production.latex,
                            image_ids=tuple(image_ids),
                        ),
                        integration=current_page.integration,
                    )
                    st.session_state[SESSION_DOCUMENT] = replace_page(
                        document,
                        safe_index,
                        updated_page,
                    )
                    _mark_dirty()
                    st.success(f"Imagen asociada a {label}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar la imagen: {exc}")
            clean_ids = [asset_id for asset_id in region.image_ids if str(asset_id or "").strip()]
            try:
                assets = (
                    list(media_collection(db).find({"asset_id": {"$in": clean_ids}}))
                    if clean_ids
                    else []
                )
            except Exception as exc:
                st.error(f"No se pudieron cargar las imágenes de {label}: {exc}")
                assets = []
            assets_by_id = {asset.get("asset_id"): asset for asset in assets}
            for asset_id in region.image_ids:
                asset = assets_by_id.get(asset_id)
                if not asset:
                    st.warning(f"Asset faltante en {label}: {asset_id}")
                    continue
                st.markdown(f"**{asset.get('original_filename') or asset.get('filename') or asset_id}**")
                if media_path_exists(asset):
                    st.image(str(PROJECT_ROOT / asset.get("path")), caption=asset.get("description") or "")
                else:
                    st.warning(f"Archivo faltante: {asset.get('path')}")
                ref = cpi_image_reference(asset_id)
                st.code(ref, language="latex")
                col_insert, col_remove = st.columns(2)
                if col_insert.button("Insertar referencia LaTeX", key=f"{safe_prefix}_insert_{asset_id}"):
                    st.session_state[latex_key] = append_latex_snippet(
                        st.session_state.get(latex_key, ""),
                        ref,
                    )
                    _mark_dirty()
                    st.rerun()
                if col_remove.button("Quitar asociación", key=f"{safe_prefix}_remove_{asset_id}"):
                    document = _document_from_inputs()
                    pages = document.ordered_pages()
                    safe_index = valid_page_index(document, page_index)
                    current_page = pages[safe_index]
                    updated_page = CpiPage(
                        page_number=current_page.page_number,
                        comprehension=current_page.comprehension,
                        production=CpiRegion(
                            heading=current_page.production.heading,
                            latex=current_page.production.latex,
                            image_ids=tuple(
                                image_id
                                for image_id in current_page.production.image_ids
                                if image_id != asset_id
                            ),
                        ),
                        integration=current_page.integration,
                    )
                    st.session_state[SESSION_DOCUMENT] = replace_page(
                        document,
                        safe_index,
                        updated_page,
                    )
                    _mark_dirty()
                    st.rerun()
    st.subheader("Integración")
    st.text_area(
        "LaTeX Integración",
        value=page.integration.latex,
        height=180,
        key="cpi_integration_latex",
        on_change=_mark_dirty,
    )
    region_name = "integration"
    region = page.integration
    label = REGION_LABELS[region_name]
    latex_key = "cpi_integration_latex"
    safe_prefix = f"cpi_page_{page_index + 1}_{page.page_number}_{region_name}_media"
    with st.expander(f"{label} · Imágenes: {len(region.image_ids)}", expanded=False):
        uploaded = st.file_uploader(
            f"Subir imagen para {label}",
            type=[extension.lstrip(".") for extension in ALLOWED_IMAGE_EXTENSIONS],
            key=f"{safe_prefix}_upload",
        )
        description = st.text_input("Descripción", key=f"{safe_prefix}_description")
        tags = st.text_input("Tags", key=f"{safe_prefix}_tags")
        if st.button("Guardar imagen", key=f"{safe_prefix}_save", disabled=uploaded is None):
            try:
                document = _document_from_inputs()
                note_id = st.session_state.get(SESSION_NOTE_ID)
                asset = save_media_asset(
                    db,
                    note_id=str(note_id) if note_id else None,
                    filename=uploaded.name,
                    data=uploaded.getvalue(),
                    mime_type=getattr(uploaded, "type", None),
                    tags=normalize_tags(tags),
                    description=description,
                )
                pages = document.ordered_pages()
                safe_index = valid_page_index(document, page_index)
                current_page = pages[safe_index]
                image_ids = list(current_page.integration.image_ids)
                if asset["asset_id"] not in image_ids:
                    image_ids.append(asset["asset_id"])
                updated_page = CpiPage(
                    page_number=current_page.page_number,
                    comprehension=current_page.comprehension,
                    production=current_page.production,
                    integration=CpiRegion(
                        heading=current_page.integration.heading,
                        latex=current_page.integration.latex,
                        image_ids=tuple(image_ids),
                    ),
                )
                st.session_state[SESSION_DOCUMENT] = replace_page(
                    document,
                    safe_index,
                    updated_page,
                )
                _mark_dirty()
                st.success(f"Imagen asociada a {label}.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo guardar la imagen: {exc}")
        clean_ids = [asset_id for asset_id in region.image_ids if str(asset_id or "").strip()]
        try:
            assets = (
                list(media_collection(db).find({"asset_id": {"$in": clean_ids}}))
                if clean_ids
                else []
            )
        except Exception as exc:
            st.error(f"No se pudieron cargar las imágenes de {label}: {exc}")
            assets = []
        assets_by_id = {asset.get("asset_id"): asset for asset in assets}
        for asset_id in region.image_ids:
            asset = assets_by_id.get(asset_id)
            if not asset:
                st.warning(f"Asset faltante en {label}: {asset_id}")
                continue
            st.markdown(f"**{asset.get('original_filename') or asset.get('filename') or asset_id}**")
            if media_path_exists(asset):
                st.image(str(PROJECT_ROOT / asset.get("path")), caption=asset.get("description") or "")
            else:
                st.warning(f"Archivo faltante: {asset.get('path')}")
            ref = cpi_image_reference(asset_id)
            st.code(ref, language="latex")
            col_insert, col_remove = st.columns(2)
            if col_insert.button("Insertar referencia LaTeX", key=f"{safe_prefix}_insert_{asset_id}"):
                st.session_state[latex_key] = append_latex_snippet(
                    st.session_state.get(latex_key, ""),
                    ref,
                )
                _mark_dirty()
                st.rerun()
            if col_remove.button("Quitar asociación", key=f"{safe_prefix}_remove_{asset_id}"):
                document = _document_from_inputs()
                pages = document.ordered_pages()
                safe_index = valid_page_index(document, page_index)
                current_page = pages[safe_index]
                updated_page = CpiPage(
                    page_number=current_page.page_number,
                    comprehension=current_page.comprehension,
                    production=current_page.production,
                    integration=CpiRegion(
                        heading=current_page.integration.heading,
                        latex=current_page.integration.latex,
                        image_ids=tuple(
                            image_id
                            for image_id in current_page.integration.image_ids
                            if image_id != asset_id
                        ),
                    ),
                )
                st.session_state[SESSION_DOCUMENT] = replace_page(
                    document,
                    safe_index,
                    updated_page,
                )
                _mark_dirty()
                st.rerun()


def _save_current_note(db: Any) -> None:
    import streamlit as st

    metadata = _metadata_from_inputs()
    document = _document_from_inputs()
    note_id = st.session_state[SESSION_NOTE_ID]
    if note_id:
        update_cpi_note(db, note_id, metadata, document)
        st.success("Nota CPI guardada.")
    else:
        result = create_cpi_note(db, metadata, document)
        inserted_id = getattr(result, "inserted_id", None)
        st.session_state[SESSION_NOTE_ID] = str(inserted_id) if inserted_id is not None else None
        st.success("Nota CPI creada.")
    st.session_state[SESSION_METADATA] = metadata
    st.session_state[SESSION_DOCUMENT] = document
    st.session_state[SESSION_DIRTY] = False


def _render_fit_report(diagnostics: dict[str, Any]) -> None:
    import streamlit as st

    report = diagnostics.get("fit_report") if isinstance(diagnostics, dict) else None
    if not isinstance(report, dict):
        return
    pages = report.get("pages")
    if not isinstance(pages, list) or not pages:
        return

    status_labels = {
        "FIT": "OK",
        "SCALED": "Ajustado",
        "OVERFLOW": "No cabe",
    }
    colors = {
        "FIT": ("#0f7b35", "#e8f5ec", "#b7dfc5"),
        "SCALED": ("#9a5b00", "#fff7e6", "#f3d18a"),
        "OVERFLOW": ("#b42318", "#fff1f0", "#f4b8b2"),
    }

    st.markdown("**Ajuste de página**")
    for page in pages:
        page_number = escape(str(page.get("page_number") or "pagina"))
        if len(pages) > 1:
            st.caption(f"Página {page_number}")
        regions = page.get("regions")
        if not isinstance(regions, list):
            continue
        for region in regions:
            if not isinstance(region, dict):
                continue
            status = str(region.get("status") or "FIT")
            label = escape(str(region.get("label") or region.get("region") or "Región"))
            scale = region.get("applied_scale", region.get("required_scale", 1.0))
            try:
                percent = int(round(float(scale) * 100))
            except (TypeError, ValueError):
                percent = 100
            color, background, border = colors.get(status, colors["FIT"])
            status_label = escape(status_labels.get(status, status))
            st.markdown(
                (
                    "<div style='display:grid;grid-template-columns:1fr 72px 96px;"
                    "gap:8px;align-items:center;border:1px solid "
                    f"{border};background:{background};color:{color};"
                    "border-radius:6px;padding:6px 8px;margin:4px 0;"
                    "font-size:0.9rem;line-height:1.2;'>"
                    f"<span>{label}</span>"
                    f"<span style='text-align:right;font-variant-numeric:tabular-nums;'>{percent} %</span>"
                    f"<strong style='text-align:right;'>{status_label}</strong>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _preview_pdf(db: Any) -> None:
    import streamlit as st

    document = _document_from_inputs()
    output_dir = PROJECT_ROOT / "runtime" / "cpi_streamlit_preview"
    preview_path = prepare_stable_preview(output_dir, "cpi_preview.pdf")
    output_name = preview_path.stem
    result = render_cpi_document(document, output_dir, str(output_name), db=db)
    st.session_state[SESSION_RENDER_DIAGNOSTICS] = result.diagnostics
    if not result.success:
        st.error(result.message or "No se pudo generar el PDF.")
        _render_fit_report(result.diagnostics)
        with st.expander("Ver log completo", expanded=False):
            st.code(cpi_latex_full_log(result), language="text")
        return
    if not Path(result.pdf_path).is_file():
        st.error("La compilación terminó sin producir el PDF esperado.")
        return
    if open_local_pdf(result.pdf_path):
        st.success(f"PDF generado. Se solicitó su apertura en una nueva pestaña: {result.pdf_path}")
    else:
        st.warning(f"PDF generado, pero el navegador no confirmó la solicitud de apertura: {result.pdf_path}")
    _render_fit_report(result.diagnostics)
    try:
        st.download_button(
            "Descargar PDF",
            data=Path(result.pdf_path).read_bytes(),
            file_name=Path(result.pdf_path).name,
            mime="application/pdf",
        )
    except OSError as exc:
        st.warning(f"PDF generado, pero no se pudo preparar la descarga: {exc}")


def _export_editable_project(db: Any) -> None:
    import streamlit as st

    document = _document_from_inputs()
    metadata = _metadata_from_inputs()
    note = build_cpi_note_document(metadata, document)
    output_root = PROJECT_ROOT / "runtime" / "cpi_exports"
    try:
        result = export_note_project(
            note,
            output_root,
            db=db,
        )
    except Exception as exc:
        st.error(f"No se pudo exportar el proyecto LaTeX: {exc}")
        return

    st.success(f"Proyecto exportado: {result.project_dir}")
    try:
        st.download_button(
            "Descargar ZIP",
            data=result.zip_path.read_bytes(),
            file_name=result.file_name,
            mime="application/zip",
            key="cpi_project_zip_download",
        )
    except OSError as exc:
        st.warning(f"Proyecto exportado, pero no se pudo preparar el ZIP: {exc}")


def _render_current_note_editor(db: Any) -> None:
    import streamlit as st

    note_id = st.session_state[SESSION_NOTE_ID]
    dirty = " · sin guardar" if st.session_state[SESSION_DIRTY] else ""
    st.caption(f"Nota actual: {note_id or 'nueva'}{dirty}")
    st.subheader("Metadata")
    _render_metadata_editor(db)
    _render_identity_editor(db)
    st.markdown("---")
    document = st.session_state[SESSION_DOCUMENT]
    pages = document.ordered_pages()
    if not pages:
        document = make_blank_document()
        st.session_state[SESSION_DOCUMENT] = document
        st.session_state[SESSION_PAGE_INDEX] = 0
        pages = document.ordered_pages()
    page_index = valid_page_index(document, st.session_state.get(SESSION_PAGE_INDEX))
    _sync_page_widget_state(pages[page_index])
    _render_page_controls()
    document = st.session_state[SESSION_DOCUMENT]
    pages = document.ordered_pages()
    page_index = valid_page_index(document, st.session_state.get(SESSION_PAGE_INDEX))
    _render_page_editor(db, pages[page_index], page_index)

    col_save, col_preview, col_export = st.columns(3)
    with col_save:
        if st.button("Guardar", type="primary", use_container_width=True):
            try:
                _save_current_note(db)
            except Exception as exc:
                st.error(f"No se pudo guardar: {exc}")
    with col_preview:
        if st.button("Vista previa PDF", use_container_width=True):
            _preview_pdf(db)
    with col_export:
        if st.button(
            "Exportar proyecto LaTeX editable",
            use_container_width=True,
            key="cpi_export_editable_project",
        ):
            _export_editable_project(db)


def _render_edit_notes(db: Any) -> None:
    import streamlit as st

    if not st.session_state.get(SESSION_NOTE_ID):
        _render_edit_note_picker(db)
        return

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Editar nota CPI")
    with right:
        if st.button("Volver al listado", use_container_width=True):
            _set_current_note(None, None, make_blank_document())
            _request_navigation(VIEW_EDIT_NOTES)
            st.rerun()
    _render_current_note_editor(db)


def render_cpi_page(db: Any) -> None:
    """Render the CPI Streamlit page."""
    import streamlit as st

    st.title("CPI")
    if db is None:
        st.error("No hay conexión activa a MongoDB.")
        return

    _ensure_state()
    _apply_pending_navigation(db)
    sidebar, editor = st.columns([1, 3])
    with sidebar:
        view = _render_navigation()

    with editor:
        if view == VIEW_EXPLORE_NOTES:
            _render_explorer(db)
            return
        if view == VIEW_EDIT_NOTES:
            _render_edit_notes(db)
            return
        _render_current_note_editor(db)

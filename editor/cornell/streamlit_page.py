"""Minimal Streamlit UI for Cornell math notes."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from editor.cornell.content_blocks import RegionSplitError
from editor.cornell.content_blocks import SplitProposal
from editor.cornell.content_blocks import apply_split_proposal
from editor.cornell.content_blocks import is_empty_cornell_page
from editor.cornell.content_blocks import split_region_to_fit
from editor.cornell.media import cornell_image_reference
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_footer_text
from editor.cornell.persistence import extract_cornell_document
from editor.cornell.project_export import export_cornell_project
from editor.cornell.renderer import cornell_latex_full_log
from editor.cornell.renderer import measure_cornell_page_fit
from editor.cornell.renderer import render_cornell_document
from editor.cornell.service import add_cornell_region_image
from editor.cornell.service import create_cornell_note
from editor.cornell.service import delete_cornell_note
from editor.cornell.service import get_cornell_assets_by_ids
from editor.cornell.service import get_cornell_note
from editor.cornell.service import list_cornell_notes
from editor.cornell.service import remove_cornell_region_image
from editor.cornell.service import update_cornell_note
from editor.cornell.service import upload_cornell_region_image
from editor.cornell.service import upload_cornell_watermark_image
from editor.cornell.ui_helpers import ALL_LABEL
from editor.cornell.ui_helpers import LATEX_SNIPPET_GROUPS
from editor.cornell.ui_helpers import NEW_PROJECT_LABEL
from editor.cornell.ui_helpers import NO_PROJECT_LABEL
from editor.cornell.ui_helpers import append_latex_snippet
from editor.cornell.ui_helpers import filter_cornell_notes_for_explorer
from editor.cornell.ui_helpers import get_existing_note_contexts
from editor.cornell.ui_helpers import get_existing_note_projects
from editor.cornell.ui_helpers import normalize_tags
from editor.cornell.ui_helpers import note_page_count
from editor.cornell.ui_helpers import project_selector_choices
from editor.cornell.ui_helpers import resolve_project_choice
from editor.pdf_preview import open_local_pdf
from editor.pdf_preview import prepare_stable_preview
from editor.utils.media_assets import ALLOWED_IMAGE_EXTENSIONS
from editor.utils.media_assets import media_path_exists
from editor.utils.media_assets import resolve_media_asset_path
from mathkb_config import RUNTIME_DIR

SESSION_NOTE_ID = "cornell_note_id"
SESSION_DOCUMENT = "cornell_document"
SESSION_PAGE_INDEX = "cornell_page_index"
SESSION_METADATA = "cornell_metadata"
SESSION_DIRTY = "cornell_dirty"
SESSION_RENDERED_PAGE_ID = "cornell_rendered_page_id"
SESSION_VIEW = "cornell_view_state"
SESSION_VIEW_SELECTOR = "cornell_view_selector"
SESSION_PENDING_VIEW = "cornell_pending_view"
SESSION_PENDING_NOTE_ID = "cornell_pending_note_id"
SESSION_PENDING_DELETE_NOTE_ID = "cornell_pending_delete_note_id"
SESSION_FLASH_MESSAGE = "cornell_flash_message"
SESSION_FIT_DIAGNOSTICS = "cornell_fit_diagnostics"
SESSION_SPLIT_PROPOSAL = "cornell_split_proposal"
SESSION_PENDING_LATEX_INSERT = "cornell_pending_latex_insert"
LEGACY_SESSION_VIEW = "cornell_view"
VIEW_NEW_NOTE = "Nueva nota"
VIEW_EXPLORE_NOTES = "Explorar notas"
VIEW_EDIT_NOTES = "Editar notas"
VIEW_OPTIONS = (VIEW_NEW_NOTE, VIEW_EXPLORE_NOTES, VIEW_EDIT_NOTES)
REGION_LABELS = {
    "cue": "Cue",
    "main": "Main",
    "summary": "Summary",
}
IDENTITY_POSITION_LABELS = {
    "center": "Centro",
    "bottom_right": "Inferior derecha",
    "top_right": "Superior derecha",
}
IDENTITY_POSITION_VALUES = tuple(IDENTITY_POSITION_LABELS)
WATERMARK_TYPE_LABELS = {
    "text": "Texto",
    "image": "Imagen",
}
WATERMARK_TYPE_VALUES = tuple(WATERMARK_TYPE_LABELS)
FOOTER_MODE_LABELS = {
    "auto": "Automático",
    "custom": "Personalizado",
}


def _new_page_id(existing_ids: set[str] | None = None) -> str:
    existing = existing_ids or set()
    while True:
        page_id = f"p_{uuid4().hex[:8]}"
        if page_id not in existing:
            return page_id


def make_blank_page(order: int = 1, page_id: str | None = None) -> CornellPage:
    """Create one blank Cornell page for UI editing."""
    return CornellPage(
        page_id=page_id or _new_page_id(),
        order=order,
        cue=CornellRegion(heading="Ideas principales", latex=""),
        main=CornellRegion(heading="Tema", latex=""),
        summary=CornellRegion(heading="Observaciones", latex=""),
    )


def make_blank_document() -> CornellDocument:
    """Create a minimal one-page Cornell document."""
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(make_blank_page(order=1),),
    )


def normalize_page_orders(document: CornellDocument) -> CornellDocument:
    """Return a document with page orders normalized to 1..n."""
    return _document_with_normalized_pages(
        document.ordered_pages(),
        schema_version=document.schema_version,
        template_id=document.template_id,
        attribution=document.attribution,
        watermark=document.watermark,
    )


def _document_with_normalized_pages(
    pages: tuple[CornellPage, ...] | list[CornellPage],
    *,
    schema_version: int,
    template_id: str,
    attribution: CornellAttribution | None = None,
    watermark: CornellWatermark | None = None,
) -> CornellDocument:
    normalized_pages = []
    for order, page in enumerate(pages, start=1):
        normalized_pages.append(
            CornellPage(
                page_id=page.page_id,
                order=order,
                cue=page.cue,
                main=page.main,
                summary=page.summary,
                source_refs=page.source_refs,
            )
        )
    return CornellDocument(
        schema_version=schema_version,
        template_id=template_id,
        pages=tuple(normalized_pages),
        attribution=attribution or CornellAttribution(),
        watermark=watermark or CornellWatermark(),
    )


def replace_page(document: CornellDocument, page_index: int, page: CornellPage) -> CornellDocument:
    """Replace the ordered page at page_index and normalize orders."""
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


def add_page(document: CornellDocument, selected_index: int | None = None) -> tuple[CornellDocument, int]:
    """Add a blank page after the selected page and return the new selected index."""
    pages = list(document.ordered_pages())
    insert_at = len(pages) if selected_index is None else min(max(selected_index + 1, 0), len(pages))
    existing_ids = {page.page_id for page in pages}
    pages.insert(insert_at, make_blank_page(order=insert_at + 1, page_id=_new_page_id(existing_ids)))
    new_document = _document_with_normalized_pages(
        pages,
        schema_version=document.schema_version,
        template_id=document.template_id,
        attribution=document.attribution,
        watermark=document.watermark,
    )
    return new_document, insert_at


def duplicate_page(document: CornellDocument, selected_index: int) -> tuple[CornellDocument, int]:
    """Duplicate the selected page with a fresh page_id."""
    pages = list(document.ordered_pages())
    if not pages:
        new_document = make_blank_document()
        return new_document, 0
    safe_index = min(max(selected_index, 0), len(pages) - 1)
    source = pages[safe_index]
    existing_ids = {page.page_id for page in pages}
    duplicate = CornellPage(
        page_id=_new_page_id(existing_ids),
        order=source.order + 1,
        cue=source.cue,
        main=source.main,
        summary=source.summary,
        source_refs=source.source_refs,
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


def delete_page(document: CornellDocument, selected_index: int) -> tuple[CornellDocument, int]:
    """Delete the selected page while keeping at least one editable page."""
    pages = list(document.ordered_pages())
    if len(pages) <= 1:
        return normalize_page_orders(document), 0
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


def _metadata_from_note(note: dict[str, Any] | None = None) -> dict[str, Any]:
    today = date.today().isoformat()
    source = note or {}
    return {
        "title": source.get("title") or "Nueva nota Cornell",
        "date": source.get("date") or today,
        "project": source.get("project") or "",
        "context": source.get("context") or "estudio",
        "tags": list(source.get("tags") or []),
        "image_ids": list(source.get("image_ids") or []),
    }


def normalize_cornell_view(view: Any) -> str:
    """Return a valid Cornell navigation view."""
    return str(view) if view in VIEW_OPTIONS else VIEW_NEW_NOTE


def queue_cornell_navigation(
    state: dict[str, Any],
    *,
    view: str,
    note_id: Any | None = None,
) -> None:
    """Queue navigation without mutating the current radio widget key."""
    state[SESSION_PENDING_VIEW] = normalize_cornell_view(view)
    if note_id is not None:
        state[SESSION_PENDING_NOTE_ID] = str(note_id)


def apply_pending_view_state(state: dict[str, Any]) -> str:
    """Apply queued view before the navigation selector is instantiated."""
    pending_view = state.pop(SESSION_PENDING_VIEW, None)
    if pending_view is not None:
        view = normalize_cornell_view(pending_view)
        state[SESSION_VIEW] = view
        state[SESSION_VIEW_SELECTOR] = view
    return normalize_cornell_view(state.get(SESSION_VIEW))


def consume_pending_note_id(state: dict[str, Any]) -> str | None:
    """Return and clear the note id queued for opening/editing."""
    note_id = state.pop(SESSION_PENDING_NOTE_ID, None)
    return str(note_id) if note_id is not None else None


def queue_latex_insert(state: dict[str, Any], *, latex_key: str, snippet: str) -> None:
    """Queue a LaTeX insert so widget state is updated before instantiation."""
    state[SESSION_PENDING_LATEX_INSERT] = {
        "latex_key": latex_key,
        "snippet": snippet,
    }


def apply_pending_latex_insert(state: dict[str, Any]) -> bool:
    """Apply a queued LaTeX insert before its text area widget is created."""
    pending = state.pop(SESSION_PENDING_LATEX_INSERT, None)
    if not isinstance(pending, dict):
        return False

    latex_key = pending.get("latex_key")
    snippet = pending.get("snippet")
    if not isinstance(latex_key, str) or not isinstance(snippet, str):
        return False

    state[latex_key] = append_latex_snippet(str(state.get(latex_key, "") or ""), snippet)
    return True


def request_cornell_note_delete(state: dict[str, Any], note_id: Any) -> None:
    """Mark a Cornell note as pending deletion without touching storage."""
    state[SESSION_PENDING_DELETE_NOTE_ID] = str(note_id)


def cancel_cornell_note_delete(state: dict[str, Any], note_id: Any | None = None) -> None:
    """Clear pending delete confirmation, optionally only for a specific note."""
    pending_id = state.get(SESSION_PENDING_DELETE_NOTE_ID)
    if note_id is None or (pending_id is not None and str(pending_id) == str(note_id)):
        state.pop(SESSION_PENDING_DELETE_NOTE_ID, None)


def _same_note_id(left: Any, right: Any) -> bool:
    return left is not None and right is not None and str(left) == str(right)


def clear_deleted_note_state(state: dict[str, Any], note_id: Any) -> None:
    """Clear editor/session state that points at a note deleted from storage."""
    cancel_cornell_note_delete(state, note_id)
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
    state.pop(SESSION_FIT_DIAGNOSTICS, None)
    state.pop(SESSION_SPLIT_PROPOSAL, None)


def _set_flash_message(state: dict[str, Any], level: str, message: str) -> None:
    state[SESSION_FLASH_MESSAGE] = {"level": level, "message": message}


def confirm_cornell_note_delete(state: dict[str, Any], db: Any, note_id: Any) -> str:
    """Delete exactly one Cornell note and return deleted, missing, or failed."""
    result = delete_cornell_note(db, note_id)
    deleted_count = 0 if result is None else int(getattr(result, "deleted_count", 0) or 0)
    if deleted_count == 1:
        clear_deleted_note_state(state, note_id)
        _set_flash_message(state, "success", "Nota Cornell borrada correctamente.")
        return "deleted"
    if deleted_count == 0:
        clear_deleted_note_state(state, note_id)
        _set_flash_message(state, "warning", "La nota ya no existe. La lista se actualizó.")
        return "missing"
    raise RuntimeError(f"La eliminación informó {deleted_count} documentos borrados; se esperaba exactamente 1.")


def valid_page_index(document: CornellDocument, selected_index: Any) -> int:
    """Clamp the selected page index to the document's available pages."""
    pages = document.ordered_pages()
    if not pages:
        return 0
    try:
        index = int(selected_index)
    except (TypeError, ValueError):
        index = 0
    return min(max(index, 0), len(pages) - 1)


def apply_loaded_note_state(
    state: dict[str, Any],
    *,
    note_id: Any,
    note: dict[str, Any] | None,
    document: CornellDocument,
) -> None:
    """Replace the editable note state, clearing stale editor values."""
    normalized_document = normalize_page_orders(document)
    metadata = _metadata_from_note(note)
    state[SESSION_NOTE_ID] = str(note_id) if note_id is not None else None
    state[SESSION_METADATA] = metadata
    state[SESSION_DOCUMENT] = normalized_document
    state[SESSION_PAGE_INDEX] = 0
    state[SESSION_DIRTY] = False

    pages = normalized_document.ordered_pages()
    first_page = pages[0] if pages else make_blank_page()
    state[SESSION_RENDERED_PAGE_ID] = first_page.page_id
    state["cornell_title"] = metadata["title"]
    state["cornell_date"] = _safe_date(metadata["date"])
    state["cornell_project"] = metadata["project"]
    state.pop("cornell_project_choice", None)
    state.pop("cornell_project_new", None)
    state["cornell_context"] = metadata["context"]
    state["cornell_tags"] = ", ".join(metadata["tags"])
    state["cornell_cue_heading"] = first_page.cue.heading
    state["cornell_cue_latex"] = first_page.cue.latex
    state["cornell_main_heading"] = first_page.main.heading
    state["cornell_main_latex"] = first_page.main.latex
    state["cornell_summary_heading"] = first_page.summary.heading
    state["cornell_summary_latex"] = first_page.summary.latex
    _sync_identity_state_values(state, normalized_document)


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
        st.session_state[SESSION_VIEW] = normalize_cornell_view(
            st.session_state.get(LEGACY_SESSION_VIEW, VIEW_NEW_NOTE)
        )


def _set_current_note(note_id: Any, note: dict[str, Any] | None, document: CornellDocument) -> None:
    import streamlit as st

    apply_loaded_note_state(
        st.session_state,
        note_id=note_id,
        note=note,
        document=document,
    )


def _sync_page_widget_state(page: CornellPage) -> None:
    import streamlit as st

    if st.session_state.get(SESSION_RENDERED_PAGE_ID) == page.page_id:
        return
    st.session_state[SESSION_RENDERED_PAGE_ID] = page.page_id
    st.session_state["cornell_cue_heading"] = page.cue.heading
    st.session_state["cornell_cue_latex"] = page.cue.latex
    st.session_state["cornell_main_heading"] = page.main.heading
    st.session_state["cornell_main_latex"] = page.main.latex
    st.session_state["cornell_summary_heading"] = page.summary.heading
    st.session_state["cornell_summary_latex"] = page.summary.latex


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


def _sync_identity_state_values(state: dict[str, Any], document: CornellDocument) -> None:
    attribution = document.attribution
    watermark = document.watermark
    state["cornell_attribution_enabled"] = attribution.enabled
    state["cornell_attribution_mode"] = _footer_mode_label(attribution.mode)
    state["cornell_attribution_text"] = attribution.text
    state["cornell_attribution_author"] = attribution.author
    state["cornell_attribution_course"] = attribution.course
    state["cornell_attribution_year"] = attribution.year
    state["cornell_attribution_position"] = _position_label(attribution.position)
    state["cornell_watermark_enabled"] = watermark.enabled
    state["cornell_watermark_type"] = _watermark_type_label(watermark.type)
    state["cornell_watermark_text"] = watermark.text
    state["cornell_watermark_image_id"] = watermark.image_id
    state["cornell_watermark_opacity"] = watermark.opacity
    state["cornell_watermark_scale"] = watermark.scale
    state["cornell_watermark_position"] = _position_label(watermark.position)


def _ensure_identity_widget_state(document: CornellDocument) -> None:
    import streamlit as st

    defaults: dict[str, Any] = {}
    _sync_identity_state_values(defaults, document)
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _document_with_identity_from_inputs(document: CornellDocument) -> CornellDocument:
    import streamlit as st

    attribution = CornellAttribution(
        enabled=bool(st.session_state.get("cornell_attribution_enabled", document.attribution.enabled)),
        mode=_footer_mode_value(st.session_state.get("cornell_attribution_mode")),
        text=str(st.session_state.get("cornell_attribution_text", document.attribution.text) or ""),
        author=str(st.session_state.get("cornell_attribution_author", document.attribution.author) or ""),
        course=str(st.session_state.get("cornell_attribution_course", document.attribution.course) or ""),
        year=str(st.session_state.get("cornell_attribution_year", document.attribution.year) or ""),
        position=_position_value(
            st.session_state.get("cornell_attribution_position"),
            default=document.attribution.position,
        ),
    )
    watermark = CornellWatermark(
        enabled=bool(st.session_state.get("cornell_watermark_enabled", document.watermark.enabled)),
        type=_watermark_type_value(st.session_state.get("cornell_watermark_type")),
        text=str(st.session_state.get("cornell_watermark_text", document.watermark.text) or ""),
        image_id=str(st.session_state.get("cornell_watermark_image_id", document.watermark.image_id) or ""),
        opacity=float(st.session_state.get("cornell_watermark_opacity", document.watermark.opacity)),
        scale=float(st.session_state.get("cornell_watermark_scale", document.watermark.scale)),
        position=_position_value(
            st.session_state.get("cornell_watermark_position"),
            default=document.watermark.position,
        ),
    )
    return CornellDocument(
        schema_version=document.schema_version,
        template_id=document.template_id,
        pages=document.pages,
        attribution=attribution,
        watermark=watermark,
    )


def _current_page_from_inputs(page: CornellPage) -> CornellPage:
    import streamlit as st

    return CornellPage(
        page_id=page.page_id,
        order=page.order,
        cue=CornellRegion(
            heading=st.session_state.get("cornell_cue_heading", page.cue.heading),
            latex=st.session_state.get("cornell_cue_latex", page.cue.latex),
            image_ids=page.cue.image_ids,
        ),
        main=CornellRegion(
            heading=st.session_state.get("cornell_main_heading", page.main.heading),
            latex=st.session_state.get("cornell_main_latex", page.main.latex),
            image_ids=page.main.image_ids,
        ),
        summary=CornellRegion(
            heading=st.session_state.get("cornell_summary_heading", page.summary.heading),
            latex=st.session_state.get("cornell_summary_latex", page.summary.latex),
            image_ids=page.summary.image_ids,
        ),
        source_refs=page.source_refs,
    )


def _document_from_inputs() -> CornellDocument:
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

    project_choice = st.session_state.get("cornell_project_choice", NO_PROJECT_LABEL)
    project_new = st.session_state.get("cornell_project_new", "")
    return {
        "title": st.session_state.get("cornell_title") or "Nueva nota Cornell",
        "date": st.session_state.get("cornell_date", date.today()).isoformat(),
        "project": resolve_project_choice(project_choice, project_new),
        "context": st.session_state.get("cornell_context") or "estudio",
        "tags": normalize_tags(st.session_state.get("cornell_tags", "")),
        "image_ids": list(st.session_state.get(SESSION_METADATA, {}).get("image_ids") or []),
    }


def _mark_dirty() -> None:
    import streamlit as st

    st.session_state[SESSION_DIRTY] = True
    st.session_state.pop(SESSION_FIT_DIAGNOSTICS, None)
    st.session_state.pop(SESSION_SPLIT_PROPOSAL, None)


def _sync_view_from_selector() -> None:
    import streamlit as st

    st.session_state[SESSION_VIEW] = normalize_cornell_view(st.session_state.get(SESSION_VIEW_SELECTOR))


def _request_navigation(view: str, note_id: Any | None = None) -> None:
    import streamlit as st

    queue_cornell_navigation(st.session_state, view=view, note_id=note_id)


def _apply_pending_navigation(db: Any) -> None:
    import streamlit as st

    note_id = consume_pending_note_id(st.session_state)
    if note_id is not None:
        try:
            opened = get_cornell_note(db, note_id)
            if opened is None:
                st.warning("La nota seleccionada ya no existe.")
            else:
                _set_current_note(note_id, opened, extract_cornell_document(opened))
        except Exception as exc:
            st.error(f"No se pudo abrir como Cornell: {exc}")
    apply_pending_view_state(st.session_state)


def _render_navigation() -> str:
    import streamlit as st

    st.subheader("Cornell")
    current_view = normalize_cornell_view(st.session_state.get(SESSION_VIEW))
    if st.session_state.get(SESSION_VIEW_SELECTOR) not in VIEW_OPTIONS:
        st.session_state[SESSION_VIEW_SELECTOR] = current_view
    view = st.radio(
        "Vista",
        options=VIEW_OPTIONS,
        key=SESSION_VIEW_SELECTOR,
        on_change=_sync_view_from_selector,
    )
    st.session_state[SESSION_VIEW] = normalize_cornell_view(view)
    if st.button("Nueva nota Cornell", width="stretch"):
        _set_current_note(None, None, make_blank_document())
        _request_navigation(VIEW_NEW_NOTE)
        st.rerun()
    return normalize_cornell_view(view)


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
    flash = st.session_state.pop(SESSION_FLASH_MESSAGE, None)
    if isinstance(flash, dict):
        message = str(flash.get("message") or "")
        if message:
            level = str(flash.get("level") or "info")
            if level == "success":
                st.success(message)
            elif level == "warning":
                st.warning(message)
            elif level == "error":
                st.error(message)
            else:
                st.info(message)

    try:
        notes = list_cornell_notes(db, limit=500)
    except Exception as exc:
        st.error(f"No se pudieron listar las notas Cornell: {exc}")
        return

    if not notes:
        st.caption("No hay notas Cornell todavía.")
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

    filtered = filter_cornell_notes_for_explorer(
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
        cols[4].write(f"{note_page_count(note)} págs.")
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
            request_cornell_note_delete(st.session_state, note_id)
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
            cancel_cornell_note_delete(st.session_state, note_id)
            st.rerun()
        if confirm_cols[1].button(
            "Sí, borrar definitivamente",
            key=f"{key_prefix}_confirm_delete_{note_id}",
        ):
            try:
                confirm_cornell_note_delete(st.session_state, db, note_id)
            except Exception as exc:
                st.error(f"No se pudo borrar la nota Cornell: {exc}")
            else:
                st.rerun()


def _render_explorer(db: Any) -> None:
    _render_note_browser(
        db,
        title="Explorar notas Cornell",
        key_prefix="cornell_explore",
        action_label="Abrir",
        destination_view=VIEW_EDIT_NOTES,
    )


def _render_edit_note_picker(db: Any) -> None:
    _render_note_browser(
        db,
        title="Editar notas Cornell",
        key_prefix="cornell_edit",
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
        if st.button("Anterior", disabled=page_index <= 0, width="stretch"):
            st.session_state[SESSION_PAGE_INDEX] = page_index - 1
            st.rerun()
    with col_count:
        st.markdown(f"**Página {page_index + 1} / {len(pages)}**")
    with col_next:
        if st.button("Siguiente", disabled=page_index >= len(pages) - 1, width="stretch"):
            st.session_state[SESSION_PAGE_INDEX] = page_index + 1
            st.rerun()
    with col_add:
        if st.button("Añadir", width="stretch"):
            st.session_state[SESSION_DOCUMENT], st.session_state[SESSION_PAGE_INDEX] = add_page(
                document,
                page_index,
            )
            _mark_dirty()
            st.rerun()
    with col_dup:
        if st.button("Duplicar", width="stretch"):
            st.session_state[SESSION_DOCUMENT], st.session_state[SESSION_PAGE_INDEX] = duplicate_page(
                document,
                page_index,
            )
            _mark_dirty()
            st.rerun()
    with col_del:
        if st.button("Eliminar", disabled=len(pages) <= 1, width="stretch"):
            st.session_state[SESSION_DOCUMENT], st.session_state[SESSION_PAGE_INDEX] = delete_page(
                document,
                page_index,
            )
            _mark_dirty()
            st.rerun()


def _render_metadata_editor(db: Any) -> None:
    import streamlit as st

    metadata = st.session_state[SESSION_METADATA]
    st.text_input("Título", value=metadata["title"], key="cornell_title", on_change=_mark_dirty)
    st.date_input(
        "Fecha",
        value=_safe_date(metadata["date"]),
        key="cornell_date",
        on_change=_mark_dirty,
    )
    projects = get_existing_note_projects(db)
    project_choices, project_index = project_selector_choices(projects, metadata["project"])
    project_choice = st.selectbox(
        "Proyecto (opcional)",
        options=project_choices,
        index=project_index,
        key="cornell_project_choice",
        on_change=_mark_dirty,
    )
    if project_choice == NEW_PROJECT_LABEL:
        st.text_input(
            "Proyecto nuevo",
            value=metadata["project"],
            key="cornell_project_new",
            on_change=_mark_dirty,
        )

    contexts = get_existing_note_contexts(db)
    context_index = contexts.index(metadata["context"]) if metadata["context"] in contexts else 0
    st.selectbox(
        "Contexto",
        options=contexts,
        index=context_index,
        key="cornell_context",
        on_change=_mark_dirty,
    )
    st.text_input(
        "Tags",
        value=", ".join(metadata["tags"]),
        key="cornell_tags",
        on_change=_mark_dirty,
    )


def _render_identity_editor(db: Any) -> None:
    import streamlit as st

    document = _document_from_inputs()
    _ensure_identity_widget_state(document)
    with st.expander("Identidad del material", expanded=False):
        st.checkbox(
            "Mostrar pie de página",
            key="cornell_attribution_enabled",
            on_change=_mark_dirty,
        )
        st.radio(
            "Modo del pie",
            options=tuple(FOOTER_MODE_LABELS.values()),
            horizontal=True,
            key="cornell_attribution_mode",
            on_change=_mark_dirty,
        )
        footer_mode = _footer_mode_value(st.session_state.get("cornell_attribution_mode"))
        if footer_mode == "auto":
            attr_author, attr_course, attr_year = st.columns([2, 2, 1])
            attr_author.text_input("Autor", key="cornell_attribution_author", on_change=_mark_dirty)
            attr_course.text_input("Curso", key="cornell_attribution_course", on_change=_mark_dirty)
            attr_year.text_input("Año", key="cornell_attribution_year", on_change=_mark_dirty)
        else:
            st.text_input(
                "Texto del pie",
                key="cornell_attribution_text",
                placeholder="© Enrique Díaz Ocampo · Material Docente",
                on_change=_mark_dirty,
            )
        st.selectbox(
            "Posición del pie",
            options=tuple(IDENTITY_POSITION_LABELS.values()),
            key="cornell_attribution_position",
            on_change=_mark_dirty,
        )
        footer_preview = build_footer_text(
            mode=footer_mode,
            text=str(st.session_state.get("cornell_attribution_text") or ""),
            author=str(st.session_state.get("cornell_attribution_author") or ""),
            course=str(st.session_state.get("cornell_attribution_course") or ""),
            year=str(st.session_state.get("cornell_attribution_year") or ""),
        )
        st.markdown("**Vista previa del pie:**")
        st.caption(footer_preview or "Sin pie de página")

        st.markdown("---")
        st.checkbox(
            "Mostrar marca de agua",
            key="cornell_watermark_enabled",
            on_change=_mark_dirty,
        )
        st.radio(
            "Tipo",
            options=tuple(WATERMARK_TYPE_LABELS.values()),
            horizontal=True,
            key="cornell_watermark_type",
            on_change=_mark_dirty,
        )
        watermark_type = _watermark_type_value(st.session_state.get("cornell_watermark_type"))
        if watermark_type == "text":
            st.text_input(
                "Texto de marca de agua",
                key="cornell_watermark_text",
                on_change=_mark_dirty,
            )
        else:
            uploaded = st.file_uploader(
                "Subir imagen",
                type=("png", "svg"),
                key="cornell_watermark_upload",
            )
            if st.button("Guardar imagen de marca", disabled=uploaded is None):
                try:
                    asset = upload_cornell_watermark_image(
                        db,
                        note_id=st.session_state.get(SESSION_NOTE_ID),
                        filename=uploaded.name,
                        data=uploaded.getvalue(),
                        mime_type=getattr(uploaded, "type", None),
                    )
                    st.session_state["cornell_watermark_image_id"] = asset["asset_id"]
                    _mark_dirty()
                    st.success("Imagen de marca asociada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar la imagen de marca: {exc}")
            image_id = str(st.session_state.get("cornell_watermark_image_id") or "")
            if image_id:
                try:
                    assets = get_cornell_assets_by_ids(db, (image_id,))
                except Exception as exc:
                    st.warning(f"No se pudo cargar la imagen de marca: {exc}")
                    assets = []
                if assets:
                    asset = assets[0]
                    st.caption(asset.get("original_filename") or asset.get("filename") or image_id)
                    if media_path_exists(asset):
                        st.image(str(resolve_media_asset_path(asset)), width=140)
                    if st.button("Quitar imagen de marca"):
                        st.session_state["cornell_watermark_image_id"] = ""
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
            key="cornell_watermark_opacity",
            on_change=_mark_dirty,
        )
        scale_col.slider(
            "Tamaño",
            min_value=0.05,
            max_value=1.0,
            step=0.01,
            key="cornell_watermark_scale",
            on_change=_mark_dirty,
        )
        position_col.selectbox(
            "Posición",
            options=tuple(IDENTITY_POSITION_LABELS.values()),
            key="cornell_watermark_position",
            on_change=_mark_dirty,
        )


def _render_region_media_manager(
    db: Any,
    *,
    page: CornellPage,
    page_index: int,
    region_name: str,
    region: CornellRegion,
    latex_key: str,
) -> None:
    import streamlit as st

    label = REGION_LABELS[region_name]
    safe_prefix = f"cornell_{page.page_id}_{region_name}_media"
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
                asset = upload_cornell_region_image(
                    db,
                    note_id=note_id,
                    filename=uploaded.name,
                    data=uploaded.getvalue(),
                    mime_type=getattr(uploaded, "type", None),
                    tags=normalize_tags(tags),
                    description=description,
                )
                st.session_state[SESSION_DOCUMENT] = add_cornell_region_image(
                    document,
                    page_index=page_index,
                    region_name=region_name,
                    asset_id=asset["asset_id"],
                )
                _mark_dirty()
                st.success(f"Imagen asociada a {label}.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo guardar la imagen: {exc}")

        try:
            assets = get_cornell_assets_by_ids(db, region.image_ids)
        except Exception as exc:
            st.error(f"No se pudieron cargar las imágenes de {label}: {exc}")
            return

        assets_by_id = {asset.get("asset_id"): asset for asset in assets}
        for asset_id in region.image_ids:
            asset = assets_by_id.get(asset_id)
            if not asset:
                st.warning(f"Asset faltante en {label}: {asset_id}")
                continue
            st.markdown(f"**{asset.get('original_filename') or asset.get('filename') or asset_id}**")
            if media_path_exists(asset):
                st.image(str(resolve_media_asset_path(asset)), caption=asset.get("description") or "")
            else:
                st.warning(f"Archivo faltante: {asset.get('path')}")
            ref = cornell_image_reference(asset_id)
            st.code(ref, language="latex")
            col_insert, col_remove = st.columns(2)
            if col_insert.button("Insertar referencia LaTeX", key=f"{safe_prefix}_insert_{asset_id}"):
                queue_latex_insert(st.session_state, latex_key=latex_key, snippet=ref)
                _mark_dirty()
                st.rerun()
            if col_remove.button("Quitar asociación", key=f"{safe_prefix}_remove_{asset_id}"):
                document = _document_from_inputs()
                st.session_state[SESSION_DOCUMENT] = remove_cornell_region_image(
                    document,
                    page_index=page_index,
                    region_name=region_name,
                    asset_id=asset_id,
                )
                _mark_dirty()
                st.rerun()


def _render_page_editor(db: Any, page: CornellPage, page_index: int) -> None:
    import streamlit as st

    apply_pending_latex_insert(st.session_state)

    with st.expander("Herramientas LaTeX", expanded=False):
        target = st.selectbox(
            "Insertar en",
            options=("Cue", "Main", "Summary"),
            key="cornell_latex_insert_target",
        )
        target_key = {
            "Cue": "cornell_cue_latex",
            "Main": "cornell_main_latex",
            "Summary": "cornell_summary_latex",
        }[target]
        cols = st.columns(4)
        for index, group in enumerate(LATEX_SNIPPET_GROUPS[:4]):
            with cols[index]:
                st.caption(group.title)
                for snippet in group.snippets:
                    if st.button(snippet.label, key=f"cornell_tool_{target}_{snippet.key}"):
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
                if st.button(snippet.label, key=f"cornell_tool_{target}_{snippet.key}"):
                    st.session_state[target_key] = append_latex_snippet(
                        st.session_state.get(target_key, ""),
                        snippet.snippet,
                    )
                    _mark_dirty()
                    st.rerun()

    left, main = st.columns([1, 2])
    with left:
        st.text_input(
            "Cue heading",
            value=page.cue.heading,
            key="cornell_cue_heading",
            on_change=_mark_dirty,
        )
        st.text_area(
            "Cue LaTeX",
            value=page.cue.latex,
            height=220,
            key="cornell_cue_latex",
            on_change=_mark_dirty,
        )
        _render_region_media_manager(
            db,
            page=page,
            page_index=page_index,
            region_name="cue",
            region=page.cue,
            latex_key="cornell_cue_latex",
        )
    with main:
        st.text_input(
            "Main heading",
            value=page.main.heading,
            key="cornell_main_heading",
            on_change=_mark_dirty,
        )
        st.text_area(
            "Main LaTeX",
            value=page.main.latex,
            height=320,
            key="cornell_main_latex",
            on_change=_mark_dirty,
        )
        _render_region_media_manager(
            db,
            page=page,
            page_index=page_index,
            region_name="main",
            region=page.main,
            latex_key="cornell_main_latex",
        )
    st.text_input(
        "Summary heading",
        value=page.summary.heading,
        key="cornell_summary_heading",
        on_change=_mark_dirty,
    )
    st.text_area(
        "Summary LaTeX",
        value=page.summary.latex,
        height=140,
        key="cornell_summary_latex",
        on_change=_mark_dirty,
    )
    _render_region_media_manager(
        db,
        page=page,
        page_index=page_index,
        region_name="summary",
        region=page.summary,
        latex_key="cornell_summary_latex",
    )


def _save_current_note(db: Any) -> None:
    import streamlit as st

    metadata = _metadata_from_inputs()
    document = _document_from_inputs()
    note_id = st.session_state[SESSION_NOTE_ID]
    if note_id:
        update_cornell_note(db, note_id, metadata, document)
        st.success("Nota Cornell guardada.")
    else:
        result = create_cornell_note(db, metadata, document)
        inserted_id = getattr(result, "inserted_id", None)
        st.session_state[SESSION_NOTE_ID] = str(inserted_id) if inserted_id is not None else None
        st.success("Nota Cornell creada.")
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
        page_id = escape(str(page.get("page_id") or "pagina"))
        if len(pages) > 1:
            st.caption(f"Página {page_id}")
        regions = page.get("regions")
        if not isinstance(regions, list):
            continue
        for region in regions:
            if not isinstance(region, dict):
                continue
            status = str(region.get("status") or "FIT")
            label = escape(str(region.get("label") or region.get("region") or "Region"))
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


def _first_overflow_region(diagnostics: dict[str, Any]) -> tuple[str, str] | None:
    report = diagnostics.get("fit_report") if isinstance(diagnostics, dict) else None
    if not isinstance(report, dict):
        return None
    pages = report.get("pages")
    if not isinstance(pages, list):
        return None
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("page_id") or "")
        regions = page.get("regions")
        if not page_id or not isinstance(regions, list):
            continue
        for region in regions:
            if isinstance(region, dict) and region.get("status") == "OVERFLOW":
                return page_id, str(region.get("region") or "")
    return None


def _page_index_by_id(document: CornellDocument, page_id: str) -> int | None:
    for index, page in enumerate(document.ordered_pages()):
        if page.page_id == page_id:
            return index
    return None


def _split_proposal_fit_engine(db: Any, output_dir: Path):
    counter = 0

    def fit_engine(page: CornellPage, region_name: str):
        nonlocal counter
        counter += 1
        page_report = measure_cornell_page_fit(
            page,
            output_dir,
            f"split_fit_{counter}_{page.page_id}",
            db=db,
        )
        fit = page_report.region_fit(region_name)
        if fit is None:
            raise RegionSplitError(f"No se pudo medir la región {region_name}.")
        return fit

    return fit_engine


def apply_split_proposal_to_state(
    state: dict[str, Any],
    document: CornellDocument,
    page_index: int,
    proposal: SplitProposal,
) -> CornellDocument:
    """Apply a split proposal to editable UI state without saving to MongoDB."""
    updated = apply_split_proposal(document, page_index, proposal)
    state[SESSION_DOCUMENT] = updated
    state[SESSION_PAGE_INDEX] = min(page_index + 1, len(updated.ordered_pages()) - 1)
    state[SESSION_DIRTY] = True
    state.pop(SESSION_FIT_DIAGNOSTICS, None)
    state.pop(SESSION_SPLIT_PROPOSAL, None)
    return updated


def _render_split_proposal(proposal: SplitProposal, page_index: int) -> None:
    import streamlit as st

    st.markdown("**Propuesta de división**")
    st.caption(
        "Página actual: "
        f"{proposal.current_fit.applied_scale:.0%} · "
        "Nueva página: "
        f"{proposal.moved_fit.applied_scale:.0%}"
    )
    left, right = st.columns(2)
    with left:
        st.caption("Contenido que queda")
        st.code(proposal.kept_latex, language="latex")
    with right:
        st.caption("Contenido que se mueve")
        st.code(proposal.moved_latex, language="latex")

    apply_col, cancel_col = st.columns(2)
    if apply_col.button("Aplicar división", type="primary", width="stretch"):
        document = _document_from_inputs()
        st.session_state[SESSION_DOCUMENT] = apply_split_proposal(
            document,
            page_index,
            proposal,
        )
        st.session_state[SESSION_PAGE_INDEX] = page_index + 1
        st.session_state.pop(SESSION_SPLIT_PROPOSAL, None)
        _mark_dirty()
        st.rerun()
    if cancel_col.button("Cancelar", width="stretch"):
        st.session_state.pop(SESSION_SPLIT_PROPOSAL, None)
        st.rerun()


def _render_overflow_split_controls(
    document: CornellDocument,
    diagnostics: dict[str, Any],
    db: Any,
) -> None:
    import streamlit as st

    overflow = _first_overflow_region(diagnostics)
    if overflow is None:
        return
    page_id, region_name = overflow
    page_index = _page_index_by_id(document, page_id)
    if page_index is None:
        st.warning("No se encontró la página con overflow en el editor actual.")
        return

    if not st.button("Dividir contenido en nueva página", width="stretch"):
        return

    pages = document.ordered_pages()
    page = pages[page_index]
    existing_ids = {candidate.page_id for candidate in pages}
    next_page = pages[page_index + 1] if page_index + 1 < len(pages) else None
    if next_page is not None and is_empty_cornell_page(next_page):
        target_page_id = next_page.page_id
    else:
        target_page_id = _new_page_id(existing_ids)
    output_dir = RUNTIME_DIR / "cornell" / "split"
    try:
        proposal = split_region_to_fit(
            page,
            region_name,
            _split_proposal_fit_engine(db, output_dir),
            new_page_id=target_page_id,
        )
    except (RegionSplitError, ValueError) as exc:
        st.error(str(exc))
        return

    apply_split_proposal_to_state(st.session_state, document, page_index, proposal)
    st.rerun()


def _preview_pdf(db: Any) -> None:
    import streamlit as st

    document = _document_from_inputs()
    output_dir = RUNTIME_DIR / "cornell_preview"
    try:
        preview_path = prepare_stable_preview(
            output_dir,
            "cornell_preview.pdf",
            allowed_root=RUNTIME_DIR,
        )
    except (OSError, ValueError) as exc:
        st.error(f"No se pudo preparar la vista previa PDF: {exc}")
        return
    output_name = preview_path.stem
    result = render_cornell_document(document, output_dir, str(output_name), db=db)
    st.session_state[SESSION_FIT_DIAGNOSTICS] = result.diagnostics
    _render_fit_report(result.diagnostics)
    if not result.success:
        st.error(result.message or "No se pudo generar el PDF.")
        with st.expander("Ver log completo", expanded=False):
            st.code(cornell_latex_full_log(result), language="text")
        return
    if not Path(result.pdf_path).is_file():
        st.error("La compilación terminó sin producir el PDF esperado.")
        return
    if open_local_pdf(result.pdf_path):
        st.success(f"PDF generado. Se solicitó su apertura en una nueva pestaña: {result.pdf_path}")
    else:
        st.warning(f"PDF generado, pero el navegador no confirmó la solicitud de apertura: {result.pdf_path}")
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
    output_root = RUNTIME_DIR / "cornell" / "editable_projects"
    try:
        result = export_cornell_project(
            document,
            metadata,
            output_root,
            allowed_root=RUNTIME_DIR,
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
            file_name=result.zip_path.name,
            mime="application/zip",
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
        if st.button("Guardar", type="primary", width="stretch"):
            try:
                _save_current_note(db)
            except Exception as exc:
                st.error(f"No se pudo guardar: {exc}")
    with col_preview:
        if st.button("Vista previa PDF", width="stretch"):
            _preview_pdf(db)
    with col_export:
        if st.button("Exportar proyecto LaTeX editable", width="stretch"):
            _export_editable_project(db)

    diagnostics = st.session_state.get(SESSION_FIT_DIAGNOSTICS)
    if isinstance(diagnostics, dict):
        _render_overflow_split_controls(_document_from_inputs(), diagnostics, db)


def _render_edit_notes(db: Any) -> None:
    import streamlit as st

    if not st.session_state.get(SESSION_NOTE_ID):
        _render_edit_note_picker(db)
        return

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Editar nota Cornell")
    with right:
        if st.button("Volver al listado", width="stretch"):
            _set_current_note(None, None, make_blank_document())
            _request_navigation(VIEW_EDIT_NOTES)
            st.rerun()
    _render_current_note_editor(db)


def render_cornell_page(db: Any) -> None:
    """Render the minimal Cornell Streamlit page."""
    import streamlit as st

    st.title("Cornell matemático")
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

"""Minimal Streamlit UI for Cornell math notes."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.persistence import extract_cornell_document
from editor.cornell.renderer import cornell_latex_full_log
from editor.cornell.renderer import render_cornell_document
from editor.cornell.service import create_cornell_note
from editor.cornell.service import get_cornell_note
from editor.cornell.service import list_cornell_notes
from editor.cornell.service import update_cornell_note
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
from mathkb_config import PROJECT_ROOT

SESSION_NOTE_ID = "cornell_note_id"
SESSION_DOCUMENT = "cornell_document"
SESSION_PAGE_INDEX = "cornell_page_index"
SESSION_METADATA = "cornell_metadata"
SESSION_DIRTY = "cornell_dirty"
SESSION_RENDERED_PAGE_ID = "cornell_rendered_page_id"
SESSION_VIEW = "cornell_view"


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
    )


def _document_with_normalized_pages(
    pages: tuple[CornellPage, ...] | list[CornellPage],
    *,
    schema_version: int,
    template_id: str,
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
        st.session_state[SESSION_VIEW] = "Nueva nota"


def _set_current_note(note_id: Any, note: dict[str, Any] | None, document: CornellDocument) -> None:
    import streamlit as st

    st.session_state[SESSION_NOTE_ID] = str(note_id) if note_id is not None else None
    st.session_state[SESSION_METADATA] = _metadata_from_note(note)
    st.session_state[SESSION_DOCUMENT] = normalize_page_orders(document)
    st.session_state[SESSION_PAGE_INDEX] = 0
    st.session_state[SESSION_DIRTY] = False
    st.session_state[SESSION_RENDERED_PAGE_ID] = None
    st.session_state["cornell_title"] = st.session_state[SESSION_METADATA]["title"]
    st.session_state["cornell_date"] = _safe_date(st.session_state[SESSION_METADATA]["date"])
    st.session_state["cornell_project"] = st.session_state[SESSION_METADATA]["project"]
    st.session_state.pop("cornell_project_choice", None)
    st.session_state.pop("cornell_project_new", None)
    st.session_state["cornell_context"] = st.session_state[SESSION_METADATA]["context"]
    st.session_state["cornell_tags"] = ", ".join(st.session_state[SESSION_METADATA]["tags"])


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
    page_index = min(max(st.session_state[SESSION_PAGE_INDEX], 0), len(pages) - 1)
    current_page = _current_page_from_inputs(pages[page_index])
    return replace_page(document, page_index, current_page)


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


def _render_navigation() -> str:
    import streamlit as st

    st.subheader("Cornell")
    view = st.radio(
        "Vista",
        options=("Nueva nota", "Explorar notas"),
        key=SESSION_VIEW,
    )
    if st.button("Nueva nota Cornell", use_container_width=True):
        _set_current_note(None, None, make_blank_document())
        st.session_state[SESSION_VIEW] = "Nueva nota"
        st.rerun()
    return view


def _render_explorer(db: Any) -> None:
    import streamlit as st

    st.subheader("Explorar notas Cornell")
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
        text_q = st.text_input("Buscar", value="", key="cornell_explore_text")
    with f2:
        project = st.selectbox(
            "Proyecto",
            options=[ALL_LABEL, NO_PROJECT_LABEL, *[p for p in projects if p != NO_PROJECT_LABEL]],
            key="cornell_explore_project",
        )
    with f3:
        context = st.selectbox(
            "Contexto",
            options=[ALL_LABEL, *contexts],
            key="cornell_explore_context",
        )

    use_date = st.checkbox("Filtrar por fecha", value=False, key="cornell_explore_use_date")
    start_date = end_date = None
    if use_date:
        d1, d2 = st.columns(2)
        with d1:
            start_date = st.date_input("Desde", value=date.today(), key="cornell_explore_start")
        with d2:
            end_date = st.date_input("Hasta", value=date.today(), key="cornell_explore_end")

    filtered = filter_cornell_notes_for_explorer(
        notes,
        text=text_q,
        project=project,
        context=context,
        start_date=start_date,
        end_date=end_date,
    )
    st.caption(f"Resultados: {len(filtered)}")
    for note in filtered:
        note_id = str(note.get("_id"))
        cols = st.columns([2, 1, 1, 1, 1, 0.8])
        cols[0].write(note.get("title") or "Sin título")
        cols[1].write(note.get("date") or "")
        cols[2].write(note.get("project") or "Sin proyecto")
        cols[3].write(note.get("context") or "")
        cols[4].write(f"{note_page_count(note)} págs.")
        if cols[5].button("Abrir", key=f"cornell_open_{note_id}"):
            try:
                opened = get_cornell_note(db, note_id)
                if opened is None:
                    st.warning("La nota seleccionada ya no existe.")
                    return
                _set_current_note(note_id, opened, extract_cornell_document(opened))
                st.session_state[SESSION_VIEW] = "Nueva nota"
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo abrir como Cornell: {exc}")


def _render_page_controls() -> None:
    import streamlit as st

    document = _document_from_inputs()
    pages = document.ordered_pages()
    page_index = min(max(st.session_state[SESSION_PAGE_INDEX], 0), len(pages) - 1)
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
            _mark_dirty()
            st.rerun()
    with col_dup:
        if st.button("Duplicar", use_container_width=True):
            st.session_state[SESSION_DOCUMENT], st.session_state[SESSION_PAGE_INDEX] = duplicate_page(
                document,
                page_index,
            )
            _mark_dirty()
            st.rerun()
    with col_del:
        if st.button("Eliminar", disabled=len(pages) <= 1, use_container_width=True):
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


def _render_page_editor(page: CornellPage) -> None:
    import streamlit as st

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


def _preview_pdf() -> None:
    import streamlit as st

    document = _document_from_inputs()
    output_dir = PROJECT_ROOT / "runtime" / "cornell_streamlit_preview"
    output_name = st.session_state[SESSION_NOTE_ID] or "cornell_preview"
    result = render_cornell_document(document, output_dir, str(output_name))
    if not result.success:
        st.error(result.message or "No se pudo generar el PDF.")
        with st.expander("Ver log completo", expanded=False):
            st.code(cornell_latex_full_log(result), language="text")
        return
    st.success(f"PDF generado: {result.pdf_path}")
    try:
        st.download_button(
            "Descargar PDF",
            data=Path(result.pdf_path).read_bytes(),
            file_name=Path(result.pdf_path).name,
            mime="application/pdf",
        )
    except OSError as exc:
        st.warning(f"PDF generado, pero no se pudo preparar la descarga: {exc}")


def render_cornell_page(db: Any) -> None:
    """Render the minimal Cornell Streamlit page."""
    import streamlit as st

    st.title("Cornell matemático")
    if db is None:
        st.error("No hay conexión activa a MongoDB.")
        return

    _ensure_state()
    sidebar, editor = st.columns([1, 3])
    with sidebar:
        view = _render_navigation()

    with editor:
        if view == "Explorar notas":
            _render_explorer(db)
            return

        note_id = st.session_state[SESSION_NOTE_ID]
        dirty = " · sin guardar" if st.session_state[SESSION_DIRTY] else ""
        st.caption(f"Nota actual: {note_id or 'nueva'}{dirty}")
        st.subheader("Metadata")
        _render_metadata_editor(db)
        st.markdown("---")
        document = st.session_state[SESSION_DOCUMENT]
        pages = document.ordered_pages()
        page_index = min(max(st.session_state[SESSION_PAGE_INDEX], 0), len(pages) - 1)
        _sync_page_widget_state(pages[page_index])
        _render_page_controls()
        document = st.session_state[SESSION_DOCUMENT]
        pages = document.ordered_pages()
        page_index = min(max(st.session_state[SESSION_PAGE_INDEX], 0), len(pages) - 1)
        _render_page_editor(pages[page_index])

        col_save, col_preview = st.columns(2)
        with col_save:
            if st.button("Guardar", type="primary", use_container_width=True):
                try:
                    _save_current_note(db)
                except Exception as exc:
                    st.error(f"No se pudo guardar: {exc}")
        with col_preview:
            if st.button("Vista previa PDF", use_container_width=True):
                _preview_pdf()

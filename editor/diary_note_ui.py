"""Shared Streamlit editor and testable state helpers for Diario note settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from editor.diary_note_models import KNOWN_HEADER_FOOTER_TOKENS
from editor.diary_note_models import AcademicMetadata
from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import FirstPageStyle
from editor.diary_note_models import HeaderFooterSettings
from editor.diary_note_models import ListOfFiguresSettings
from editor.diary_note_models import ListOfTablesSettings
from editor.diary_note_models import NoteReference
from editor.diary_note_models import NoteReferenceKind
from editor.diary_note_models import PageNumberPosition
from editor.diary_note_models import TableOfContentsSettings
from editor.diary_note_models import TocPosition
from editor.diary_note_models import move_reference
from editor.diary_note_models import note_reference_from_catalog
from editor.diary_note_models import resolve_tokens
from editor.diary_note_models import settings_from_note
from editor.diary_note_models import settings_warnings
from editor.diary_note_models import token_values
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.repository import ReferenceRepository

_ACADEMIC_FIELDS = (
    "institution",
    "program",
    "course_code",
    "course_name",
    "week",
    "session",
    "short_title",
    "topic",
    "objective",
    "linked_activity",
    "author",
    "version",
    "language",
    "pdf_subject",
)
_LAYOUT_FIELDS = (
    "enabled",
    "header_left",
    "header_center",
    "header_right",
    "footer_left",
    "footer_center",
    "footer_right",
    "first_page_style",
    "show_page_number",
    "page_number_position",
)
_TOC_FIELDS = (
    "show_table_of_contents",
    "toc_title",
    "toc_depth",
    "position",
)
_LIST_OF_FIGURES_FIELDS = (
    "show_list_of_figures",
    "title",
)
_LIST_OF_TABLES_FIELDS = (
    "show_list_of_tables",
    "title",
)
_REFERENCE_FIELDS = (
    "origin",
    "catalog_reference_id",
    "kind",
    "citation_key",
    "authors",
    "title",
    "year_or_date",
    "container_title",
    "publisher",
    "volume",
    "number",
    "pages",
    "edition",
    "doi",
    "url",
    "accessed_date",
    "language",
    "note",
)
_REFERENCE_KIND_LABELS = {
    NoteReferenceKind.BOOK.value: "Libro",
    NoteReferenceKind.CHAPTER.value: "Capítulo",
    NoteReferenceKind.ARTICLE.value: "Artículo",
    NoteReferenceKind.WEBSITE.value: "Sitio web",
    NoteReferenceKind.DOCUMENTATION.value: "Documentación",
    NoteReferenceKind.THESIS.value: "Tesis",
    NoteReferenceKind.DATASET.value: "Dataset",
    NoteReferenceKind.SOFTWARE.value: "Software",
    NoteReferenceKind.INSTITUTIONAL.value: "Material institucional",
    NoteReferenceKind.OTHER.value: "Otro",
}
_FIRST_PAGE_LABELS = {
    FirstPageStyle.SAME.value: "Mismo encabezado y pie",
    FirstPageStyle.PLAIN.value: "Estilo simple",
    FirstPageStyle.EMPTY.value: "Sin encabezado ni pie",
}
_PAGE_POSITION_LABELS = {
    PageNumberPosition.FOOTER_LEFT.value: "Pie izquierdo",
    PageNumberPosition.FOOTER_CENTER.value: "Pie central",
    PageNumberPosition.FOOTER_RIGHT.value: "Pie derecho",
}
_TOC_POSITION_LABELS = {
    TocPosition.AFTER_TITLE.value: "Después del título",
    TocPosition.AFTER_METADATA.value: "Después de los metadatos",
}
_TOC_DEPTH_LABELS = {
    0: "Capítulos",
    1: "Capítulos y secciones",
    2: "Capítulos, secciones y subsecciones",
}


def _state_key(prefix: str, field: str) -> str:
    return f"{prefix}_settings_{field}"


def _reference_key(prefix: str, reference_id: str, field: str) -> str:
    return f"{prefix}_reference_{reference_id}_{field}"


def _reference_ids_key(prefix: str) -> str:
    return _state_key(prefix, "reference_ids")


def _has_complete_note_settings_state(state: Any, prefix: str) -> bool:
    """Return whether every persisted-value key needed by the editor still exists.

    Streamlit removes widget-owned keys when the Edit view is no longer rendered,
    while our non-widget ``loaded_identity`` marker remains.  Reusing that marker
    alone would skip database reconstruction and recreate empty widgets when the
    same note is opened again.
    """
    required_keys = [
        *(_state_key(prefix, f"academic_{field}") for field in _ACADEMIC_FIELDS),
        _state_key(prefix, "academic_pdf_keywords"),
        *(_state_key(prefix, f"layout_{field}") for field in _LAYOUT_FIELDS),
        *(_state_key(prefix, f"toc_{field}") for field in _TOC_FIELDS),
        *(_state_key(prefix, f"lof_{field}") for field in _LIST_OF_FIGURES_FIELDS),
        *(_state_key(prefix, f"lot_{field}") for field in _LIST_OF_TABLES_FIELDS),
        _reference_ids_key(prefix),
    ]
    if any(key not in state for key in required_keys):
        return False
    reference_ids = state.get(_reference_ids_key(prefix))
    if not isinstance(reference_ids, list | tuple):
        return False
    for reference_id in reference_ids:
        reference_keys = [
            *(_reference_key(prefix, str(reference_id), field) for field in _REFERENCE_FIELDS),
            _reference_key(prefix, str(reference_id), "__extra__"),
        ]
        if any(key not in state for key in reference_keys):
            return False
    return True


def _set_reference_state(
    state: Any,
    prefix: str,
    reference: NoteReference,
) -> None:
    data = reference.model_dump(mode="json")
    known = {*_REFERENCE_FIELDS, "reference_id", "position"}
    state[_reference_key(prefix, reference.reference_id, "__extra__")] = {
        key: value for key, value in data.items() if key not in known
    }
    for field in _REFERENCE_FIELDS:
        state[_reference_key(prefix, reference.reference_id, field)] = data.get(field)


def initialize_note_settings_state(
    state: Any,
    *,
    prefix: str,
    note: Mapping[str, Any],
    identity: str,
    new_note: bool = False,
) -> None:
    """Load one note exactly once into note-scoped widget state."""
    loaded_key = _state_key(prefix, "loaded_identity")
    if state.get(loaded_key) == identity and _has_complete_note_settings_state(state, prefix):
        return
    clear_note_settings_state(state, prefix)
    settings = settings_from_note(note, new_note=new_note)
    state[loaded_key] = identity
    metadata = settings.academic_metadata.model_dump(mode="json")
    for field in _ACADEMIC_FIELDS:
        state[_state_key(prefix, f"academic_{field}")] = metadata[field]
    state[_state_key(prefix, "academic_pdf_keywords")] = ", ".join(metadata["pdf_keywords"])
    layout = settings.page_layout.model_dump(mode="json")
    for field in _LAYOUT_FIELDS:
        state[_state_key(prefix, f"layout_{field}")] = layout[field]
    toc = settings.table_of_contents.model_dump(mode="json")
    for field in _TOC_FIELDS:
        state[_state_key(prefix, f"toc_{field}")] = toc[field]
    list_of_figures = settings.list_of_figures.model_dump(mode="json")
    for field in _LIST_OF_FIGURES_FIELDS:
        state[_state_key(prefix, f"lof_{field}")] = list_of_figures[field]
    list_of_tables = settings.list_of_tables.model_dump(mode="json")
    for field in _LIST_OF_TABLES_FIELDS:
        state[_state_key(prefix, f"lot_{field}")] = list_of_tables[field]
    state[_reference_ids_key(prefix)] = [
        reference.reference_id for reference in settings.references
    ]
    for reference in settings.references:
        _set_reference_state(state, prefix, reference)


def clear_note_settings_state(state: Any, prefix: str) -> None:
    """Remove only widget/draft keys owned by one note editor."""
    owned_prefixes = (f"{prefix}_settings_", f"{prefix}_reference_")
    for key in tuple(state):
        if str(key).startswith(owned_prefixes):
            state.pop(key, None)


def settings_from_ui_state(state: Mapping[str, Any], prefix: str) -> DiaryNoteSettings:
    """Build validated persistent settings from the current widget values."""
    academic = {
        field: state.get(_state_key(prefix, f"academic_{field}"), "") for field in _ACADEMIC_FIELDS
    }
    academic["pdf_keywords"] = state.get(_state_key(prefix, "academic_pdf_keywords"), "")
    layout = {field: state.get(_state_key(prefix, f"layout_{field}")) for field in _LAYOUT_FIELDS}
    toc = {field: state.get(_state_key(prefix, f"toc_{field}")) for field in _TOC_FIELDS}
    list_of_figures = {
        field: state.get(_state_key(prefix, f"lof_{field}"))
        for field in _LIST_OF_FIGURES_FIELDS
    }
    list_of_tables = {
        field: state.get(_state_key(prefix, f"lot_{field}"))
        for field in _LIST_OF_TABLES_FIELDS
    }
    references: list[NoteReference] = []
    for position, reference_id in enumerate(state.get(_reference_ids_key(prefix), [])):
        preserved_extra = state.get(_reference_key(prefix, reference_id, "__extra__"), {})
        data = dict(preserved_extra) if isinstance(preserved_extra, Mapping) else {}
        data.update(
            {
                field: state.get(_reference_key(prefix, reference_id, field), "")
                for field in _REFERENCE_FIELDS
            }
        )
        data.update({"reference_id": reference_id, "position": position})
        references.append(NoteReference.model_validate(data))
    return DiaryNoteSettings(
        academic_metadata=AcademicMetadata.model_validate(academic),
        references=references,
        page_layout=HeaderFooterSettings.model_validate(layout),
        table_of_contents=TableOfContentsSettings.model_validate(toc),
        list_of_figures=ListOfFiguresSettings.model_validate(list_of_figures),
        list_of_tables=ListOfTablesSettings.model_validate(list_of_tables),
    )


def add_manual_reference_state(state: Any, prefix: str) -> str:
    """Append one empty draft and initialize its stable widget keys."""
    ids_key = _reference_ids_key(prefix)
    reference_ids = list(state.get(ids_key, []))
    reference = NoteReference(position=len(reference_ids))
    reference_ids.append(reference.reference_id)
    state[ids_key] = reference_ids
    _set_reference_state(state, prefix, reference)
    return reference.reference_id


def add_catalog_reference_state(
    state: Any,
    prefix: str,
    reference: Reference,
) -> str:
    """Append a catalog-linked snapshot without modifying the catalog Reference."""
    ids_key = _reference_ids_key(prefix)
    reference_ids = list(state.get(ids_key, []))
    snapshot = note_reference_from_catalog(reference, position=len(reference_ids))
    reference_ids.append(snapshot.reference_id)
    state[ids_key] = reference_ids
    _set_reference_state(state, prefix, snapshot)
    return snapshot.reference_id


def move_reference_state(state: Any, prefix: str, reference_id: str, offset: int) -> None:
    """Reorder stable IDs while retaining each reference's widget values."""
    settings = settings_from_ui_state(state, prefix)
    moved = move_reference(settings.references, reference_id, offset)
    state[_reference_ids_key(prefix)] = [item.reference_id for item in moved]


def remove_reference_state(state: Any, prefix: str, reference_id: str) -> None:
    """Explicitly remove one reference and only its owned widget state."""
    ids_key = _reference_ids_key(prefix)
    state[ids_key] = [item for item in state.get(ids_key, []) if item != reference_id]
    owned_prefix = f"{prefix}_reference_{reference_id}_"
    for key in tuple(state):
        if str(key).startswith(owned_prefix):
            state.pop(key, None)


def reset_page_layout_state(state: Any, prefix: str) -> None:
    """Restore metadata-derived page defaults without touching other note settings."""
    defaults = HeaderFooterSettings(enabled=True).model_dump(mode="json")
    for field in _LAYOUT_FIELDS:
        state[_state_key(prefix, f"layout_{field}")] = defaults[field]


def resolved_layout_preview(
    note: Mapping[str, Any],
    settings: DiaryNoteSettings,
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Resolve header/footer text for UI preview with exactly one example page number."""
    layout = settings.page_layout
    values = token_values(note, settings)
    resolved: dict[str, str] = {}
    warnings: list[str] = []
    for slot in (
        "header_left",
        "header_center",
        "header_right",
        "footer_left",
        "footer_center",
        "footer_right",
    ):
        text, token_warnings = resolve_tokens(getattr(layout, slot), values, page_value="1")
        resolved[slot] = text
        warnings.extend(token_warnings)
    if layout.show_page_number:
        page_slot = layout.page_number_position.value
        if "{page}" not in getattr(layout, page_slot):
            resolved[page_slot] = " · ".join(part for part in (resolved[page_slot], "1") if part)
    return resolved, tuple(dict.fromkeys(warnings))


def _catalog_references(database: Any) -> tuple[Reference, ...]:
    repository = ReferenceRepository(database)
    items: dict[str, Reference] = {}
    for status in ("active", "needs_review"):
        page = repository.list(page_size=100, status=status)
        items.update({item.reference_id: item for item in page.items})
    return tuple(
        sorted(
            items.values(),
            key=lambda item: (
                -(item.year or 0),
                (item.title or "").casefold(),
                item.reference_id,
            ),
        )
    )


def _catalog_label(reference: Reference) -> str:
    authors = "; ".join(
        author.literal or " ".join(part for part in (author.given, author.family) if part)
        for author in reference.authors
    )
    prefix = " · ".join(part for part in (str(reference.year or ""), authors) if part)
    return (
        f"{prefix} — {reference.title or reference.reference_id}"
        if prefix
        else (reference.title or reference.reference_id)
    )


def _render_academic_metadata(prefix: str) -> None:
    with st.expander("Metadatos académicos y PDF", expanded=False):
        st.caption(
            "Título, fecha, proyecto, contexto y tags se reutilizan desde los campos principales."
        )
        left, right = st.columns(2)
        with left:
            st.text_input("Institución", key=_state_key(prefix, "academic_institution"))
            st.text_input("Programa", key=_state_key(prefix, "academic_program"))
            st.text_input("Código de asignatura", key=_state_key(prefix, "academic_course_code"))
            st.text_input("Nombre de asignatura", key=_state_key(prefix, "academic_course_name"))
            st.text_input("Semana", key=_state_key(prefix, "academic_week"))
            st.text_input("Sesión", key=_state_key(prefix, "academic_session"))
            st.text_input("Título corto", key=_state_key(prefix, "academic_short_title"))
        with right:
            st.text_input("Tema", key=_state_key(prefix, "academic_topic"))
            st.text_area("Objetivo", key=_state_key(prefix, "academic_objective"), height=80)
            st.text_input("Actividad vinculada", key=_state_key(prefix, "academic_linked_activity"))
            st.text_input("Autoría", key=_state_key(prefix, "academic_author"))
            st.text_input("Versión", key=_state_key(prefix, "academic_version"))
            st.text_input("Idioma", key=_state_key(prefix, "academic_language"))
            st.text_input("Asunto del PDF", key=_state_key(prefix, "academic_pdf_subject"))
        st.text_input(
            "Palabras clave del PDF (separadas por comas)",
            key=_state_key(prefix, "academic_pdf_keywords"),
        )


def _render_page_layout(prefix: str, note: Mapping[str, Any]) -> None:
    with st.expander("Encabezado, pie y página de contenido", expanded=False):
        st.toggle("Usar encabezado y pie personalizados", key=_state_key(prefix, "layout_enabled"))
        st.caption(
            "Tokens disponibles: " + ", ".join(f"{{{item}}}" for item in KNOWN_HEADER_FOOTER_TOKENS)
        )
        header_columns = st.columns(3)
        footer_columns = st.columns(3)
        for column, field, label in zip(
            header_columns,
            ("header_left", "header_center", "header_right"),
            ("Encabezado izquierdo", "Encabezado central", "Encabezado derecho"),
            strict=True,
        ):
            with column:
                st.text_input(label, key=_state_key(prefix, f"layout_{field}"))
        for column, field, label in zip(
            footer_columns,
            ("footer_left", "footer_center", "footer_right"),
            ("Pie izquierdo", "Pie central", "Pie derecho"),
            strict=True,
        ):
            with column:
                st.text_input(label, key=_state_key(prefix, f"layout_{field}"))
        options = st.columns(3)
        with options[0]:
            st.selectbox(
                "Primera página",
                options=list(_FIRST_PAGE_LABELS),
                format_func=_FIRST_PAGE_LABELS.__getitem__,
                key=_state_key(prefix, "layout_first_page_style"),
            )
        with options[1]:
            st.toggle("Mostrar número de página", key=_state_key(prefix, "layout_show_page_number"))
        with options[2]:
            st.selectbox(
                "Ubicación del número",
                options=list(_PAGE_POSITION_LABELS),
                format_func=_PAGE_POSITION_LABELS.__getitem__,
                key=_state_key(prefix, "layout_page_number_position"),
            )
        st.button(
            "Restablecer encabezado y pie",
            key=_state_key(prefix, "layout_reset"),
            on_click=reset_page_layout_state,
            args=(st.session_state, prefix),
        )

        st.divider()
        st.markdown("**Página de contenido**")
        st.toggle(
            "Mostrar página de contenido",
            key=_state_key(prefix, "toc_show_table_of_contents"),
        )
        toc_columns = st.columns(3)
        with toc_columns[0]:
            st.text_input("Título del índice", key=_state_key(prefix, "toc_toc_title"))
        with toc_columns[1]:
            st.selectbox(
                "Profundidad",
                options=list(_TOC_DEPTH_LABELS),
                format_func=_TOC_DEPTH_LABELS.__getitem__,
                key=_state_key(prefix, "toc_toc_depth"),
            )
        with toc_columns[2]:
            st.selectbox(
                "Posición",
                options=list(_TOC_POSITION_LABELS),
                format_func=_TOC_POSITION_LABELS.__getitem__,
                key=_state_key(prefix, "toc_position"),
            )

        st.divider()
        st.markdown("**Índice de figuras**")
        st.toggle(
            "Mostrar índice de figuras",
            key=_state_key(prefix, "lof_show_list_of_figures"),
        )
        st.text_input("Título del índice", key=_state_key(prefix, "lof_title"))

        st.divider()
        st.markdown("**Índice de tablas**")
        st.toggle(
            "Mostrar índice de tablas",
            key=_state_key(prefix, "lot_show_list_of_tables"),
        )
        st.text_input("Título del índice", key=_state_key(prefix, "lot_title"))

        settings = settings_from_ui_state(st.session_state, prefix)
        preview, preview_warnings = resolved_layout_preview(note, settings)
        st.markdown("**Vista previa textual**")
        st.caption(
            "Encabezado: "
            + " | ".join(
                preview[field] or "—" for field in ("header_left", "header_center", "header_right")
            )
        )
        st.caption(
            "Pie: "
            + " | ".join(
                preview[field] or "—" for field in ("footer_left", "footer_center", "footer_right")
            )
        )
        for warning in preview_warnings:
            st.warning(warning)


def _render_reference_fields(prefix: str, reference_id: str, position: int, total: int) -> None:
    title = str(st.session_state.get(_reference_key(prefix, reference_id, "title")) or "")
    authors = str(st.session_state.get(_reference_key(prefix, reference_id, "authors")) or "")
    summary = title or authors or "Borrador sin título"
    with st.expander(f"{position + 1}. {summary}", expanded=not bool(title)):
        linked_id = st.session_state.get(
            _reference_key(prefix, reference_id, "catalog_reference_id")
        )
        if linked_id:
            st.caption(
                f"Vinculada al catálogo: `{linked_id}` · se guarda una instantánea editable."
            )
        basic = st.columns(2)
        with basic[0]:
            st.selectbox(
                "Tipo",
                options=list(_REFERENCE_KIND_LABELS),
                format_func=_REFERENCE_KIND_LABELS.__getitem__,
                key=_reference_key(prefix, reference_id, "kind"),
            )
            st.text_input(
                "Autoría o entidad responsable", key=_reference_key(prefix, reference_id, "authors")
            )
            st.text_input("Título", key=_reference_key(prefix, reference_id, "title"))
        with basic[1]:
            st.text_input("Año o fecha", key=_reference_key(prefix, reference_id, "year_or_date"))
            st.text_input(
                "Publicación contenedora",
                key=_reference_key(prefix, reference_id, "container_title"),
            )
            st.text_input(
                "Clave de cita (opcional)", key=_reference_key(prefix, reference_id, "citation_key")
            )
        show_advanced = st.toggle(
            "Mostrar campos bibliográficos avanzados",
            key=_reference_key(prefix, reference_id, "show_advanced"),
        )
        if show_advanced:
            advanced_left, advanced_right = st.columns(2)
            with advanced_left:
                st.text_input(
                    "Editorial o institución", key=_reference_key(prefix, reference_id, "publisher")
                )
                st.text_input("Volumen", key=_reference_key(prefix, reference_id, "volume"))
                st.text_input("Número", key=_reference_key(prefix, reference_id, "number"))
                st.text_input("Páginas", key=_reference_key(prefix, reference_id, "pages"))
                st.text_input("Edición", key=_reference_key(prefix, reference_id, "edition"))
            with advanced_right:
                st.text_input("DOI", key=_reference_key(prefix, reference_id, "doi"))
                st.text_input("URL", key=_reference_key(prefix, reference_id, "url"))
                st.text_input(
                    "Fecha de consulta", key=_reference_key(prefix, reference_id, "accessed_date")
                )
                st.text_input("Idioma", key=_reference_key(prefix, reference_id, "language"))
                st.text_area(
                    "Nota interna", key=_reference_key(prefix, reference_id, "note"), height=80
                )
        with st.container(horizontal=True):
            st.button(
                "Subir",
                disabled=position == 0,
                key=_reference_key(prefix, reference_id, "move_up"),
                on_click=move_reference_state,
                args=(st.session_state, prefix, reference_id, -1),
            )
            st.button(
                "Bajar",
                disabled=position >= total - 1,
                key=_reference_key(prefix, reference_id, "move_down"),
                on_click=move_reference_state,
                args=(st.session_state, prefix, reference_id, 1),
            )
            confirm_key = _reference_key(prefix, reference_id, "delete_confirm")
            st.checkbox("Confirmar eliminación", key=confirm_key)
            delete_clicked = st.button(
                "Eliminar",
                key=_reference_key(prefix, reference_id, "delete"),
            )
        if delete_clicked:
            if st.session_state.get(confirm_key):
                remove_reference_state(st.session_state, prefix, reference_id)
                st.rerun()
            else:
                st.warning("Confirma la eliminación de esta referencia.")


def _render_references(database: Any, prefix: str) -> None:
    with st.expander("Referencias bibliográficas", expanded=False):
        st.caption(
            "Las referencias se guardan con la nota. Las que no tengan título permanecen como "
            "borradores y se omiten al exportar."
        )
        with st.container(horizontal=True):
            if st.button(
                "Agregar referencia manual", key=_state_key(prefix, "reference_add_manual")
            ):
                add_manual_reference_state(st.session_state, prefix)
                st.rerun()
        try:
            catalog = _catalog_references(database)
        except Exception as exc:
            catalog = ()
            st.warning(f"No se pudo consultar el catálogo de referencias: {exc}")
        if catalog:
            catalog_by_id = {item.reference_id: item for item in catalog}
            catalog_columns = st.columns([4, 1])
            with catalog_columns[0]:
                selected_id = st.selectbox(
                    "Agregar desde el catálogo",
                    options=list(catalog_by_id),
                    format_func=lambda value: _catalog_label(catalog_by_id[value]),
                    key=_state_key(prefix, "reference_catalog_choice"),
                )
            with catalog_columns[1]:
                add_catalog = st.button(
                    "Agregar selección",
                    key=_state_key(prefix, "reference_add_catalog"),
                )
            if add_catalog:
                add_catalog_reference_state(
                    st.session_state,
                    prefix,
                    catalog_by_id[selected_id],
                )
                st.rerun()
        else:
            st.caption(
                "No hay referencias activas en el catálogo; puedes agregar referencias manuales."
            )

        reference_ids = list(st.session_state.get(_reference_ids_key(prefix), []))
        if not reference_ids:
            st.info("Aún no hay referencias bibliográficas en esta nota.")
        for position, reference_id in enumerate(reference_ids):
            _render_reference_fields(prefix, reference_id, position, len(reference_ids))


def render_note_settings_editor(
    database: Any,
    *,
    prefix: str,
    note: Mapping[str, Any],
    identity: str,
    new_note: bool = False,
) -> DiaryNoteSettings:
    """Render shared structured settings for both New and Edit note flows."""
    initialize_note_settings_state(
        st.session_state,
        prefix=prefix,
        note=note,
        identity=identity,
        new_note=new_note,
    )
    _render_academic_metadata(prefix)
    _render_page_layout(prefix, note)
    _render_references(database, prefix)
    settings = settings_from_ui_state(st.session_state, prefix)
    warnings = settings_warnings(settings)
    if warnings:
        with st.expander("Advertencias de metadatos y referencias", expanded=False):
            for warning in warnings:
                st.warning(warning)
    return settings


__all__ = [
    "add_catalog_reference_state",
    "add_manual_reference_state",
    "clear_note_settings_state",
    "initialize_note_settings_state",
    "move_reference_state",
    "remove_reference_state",
    "render_note_settings_editor",
    "reset_page_layout_state",
    "resolved_layout_preview",
    "settings_from_ui_state",
]

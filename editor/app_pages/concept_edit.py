"""Concept edit; extracted without import-time rendering."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from editor.ui.concept_deletion import render_concept_deletion
from streamlit_ace import st_ace

from editor.database_scope import database_scope_token
from editor.db.concept_edit_service import update_concept_fields_preserving_identity
from editor.db.concept_source_link_service import ConceptSourceLinkStatus
from editor.db.concept_source_link_service import link_concept_to_existing_managed_source
from editor.edit_concept_feedback import feedback_for_update_result
from editor.edit_concept_feedback import render_update_flash
from editor.edit_concept_feedback import safe_update_exception_message
from editor.edit_concept_feedback import store_update_success_flash
from editor.edit_concept_feedback import sync_update_feedback_scope
from editor.helpers.managed_source_selection import can_save_with_managed_source
from editor.helpers.managed_source_selection import load_active_sources
from editor.helpers.managed_source_selection import resolve_active_source
from editor.helpers.managed_source_selection import source_labels
from editor.helpers.tipo_aplicacion import TipoAplicacion
from editor.helpers.tipo_contexto import NivelContexto
from editor.helpers.tipo_formalidad import GradoFormalidad
from editor.helpers.tipo_presentacion import TipoPresentacion
from editor.helpers.tipo_referencia import TipoReferencia
from editor.helpers.tipo_simbolico import NivelSimbolico
from editor.helpers.tipo_titulo import TipoTitulo
from editor.latex_tools import LATEX_SURFACE_CONCEPTS
from editor.latex_tools import apply_queued_latex_snippet
from editor.latex_tools import queue_latex_snippet
from editor.pdf_preview import clear_pdf_preview
from editor.pdf_preview import pdf_preview_context
from editor.pdf_preview import render_pdf_preview
from editor.source_catalog.shared import safe_error_message as safe_catalog_error
from editor.source_catalog.state import consume_legacy_concept_open
from editor.source_catalog.state import state_key as source_catalog_state_key
from editor.ui.concept_media import _render_concept_media_manager
from editor.ui.concept_media import _render_tikz_weight_warnings
from editor.ui.concept_pdf import _generate_concept_pdf_preview
from editor.ui.editable_text import editable_text_area
from editor.ui.latex_toolbar import render_latex_toolbar
from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir


def render(context):
    """Render only the selected page using its explicit application context."""
    active_database_scope = context.active_database_scope
    catalog_context = context.catalog_context
    catalog_context_error = context.catalog_context_error
    current_database_label = context.current_database_label
    current_db = context.current_db
    db = context.db
    st.title("✏️ Edit Mathematical Concept")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    edit_feedback_database_scope = active_database_scope or database_scope_token(
        current_db or "<unlabeled connection>",
        current_database_label or "<unknown database>",
    )
    sync_update_feedback_scope(
        st.session_state,
        edit_feedback_database_scope,
    )
    st.info(f"📊 Editing concepts in: **{current_database_label}**")

    # Concept selection
    st.subheader("🔍 Select Concept to Edit")

    legacy_target = consume_legacy_concept_open(st.session_state)
    legacy_source_key = source_catalog_state_key("legacy_edit_filter_source")
    legacy_type_key = source_catalog_state_key("legacy_edit_filter_type")
    legacy_concept_key = source_catalog_state_key("legacy_edit_concept")
    legacy_last_selected_key = source_catalog_state_key("legacy_last_selected_concept")
    available_legacy_sources = [
        value
        for value in db.concepts.distinct("source")
        if isinstance(value, str) and value
    ]
    source_options = ["All", *available_legacy_sources]
    type_options = [
        "All",
        *[
            value
            for value in db.concepts.distinct("tipo")
            if isinstance(value, str) and value
        ],
    ]
    if legacy_target is not None:
        if legacy_target["source"] in available_legacy_sources:
            st.session_state[legacy_source_key] = legacy_target["source"]
            st.session_state[legacy_type_key] = "All"
            st.info(
                "Opened from Source Catalog using the exact legacy identity "
                f"`{legacy_target['id']}@{legacy_target['source']}`."
            )
        else:
            st.warning("The exact legacy Source is not available in the active database.")
    if st.session_state.get(legacy_source_key) not in source_options:
        st.session_state.pop(legacy_source_key, None)
    if st.session_state.get(legacy_type_key) not in type_options:
        st.session_state.pop(legacy_type_key, None)

    col1, col2 = st.columns(2)

    with col1:
        # Filter by source
        filter_source = st.selectbox(
            "Filter by Source",
            source_options,
            key=legacy_source_key,
        )

    with col2:
        # Filter by type
        filter_type = st.selectbox(
            "Filter by Type",
            type_options,
            key=legacy_type_key,
        )

    # Build query for concept selection
    query = {}
    if filter_source != "All":
        query["source"] = filter_source
    if filter_type != "All":
        query["tipo"] = filter_type

    # Get concepts for selection
    concepts = list(db.concepts.find(query).sort("fecha_creacion", -1))

    if not concepts:
        st.warning("⚠️ No concepts found with the selected filters.")
        st.stop()

    # Create concept options for selection
    concept_options = []
    concept_map = {}

    for concept in concepts:
        display_name = (
            f"{concept.get('titulo', concept['id'])} "
            f"({concept['tipo']} - {concept['source']}) · {concept['id']}"
        )
        concept_options.append(display_name)
        concept_map[display_name] = concept

    if legacy_target is not None:
        target_display = next(
            (
                display
                for display, concept in concept_map.items()
                if str(concept.get("id")) == legacy_target["id"]
                and concept.get("source") == legacy_target["source"]
            ),
            None,
        )
        if target_display is not None:
            st.session_state[legacy_concept_key] = target_display
        else:
            st.warning("The exact legacy concept was not found with the active filters.")
    if st.session_state.get(legacy_concept_key) not in concept_options:
        st.session_state.pop(legacy_concept_key, None)

    # Concept selector
    selected_concept_display = st.selectbox(
        "Choose Concept to Edit",
        concept_options,
        help="Select the concept you want to edit",
        key=legacy_concept_key,
    )
    # Handle concept selection and data loading
    if selected_concept_display:
        selected_concept = concept_map[selected_concept_display]
        original_concept_id = str(selected_concept["id"])
        original_source = str(selected_concept["source"])
        original_source_id_present = "source_id" in selected_concept
        original_source_id = selected_concept.get("source_id")

        # Check if concept has changed and update session state
        selected_concept_key = (
            original_concept_id,
            original_source,
        )
        if (
            st.session_state.get(legacy_last_selected_key) != selected_concept_key
        ):

            # IDs are only unique together with their exact legacy Source.
            st.session_state[legacy_last_selected_key] = selected_concept_key

            # Get LaTeX content from database
            latex_doc = db.latex_documents.find_one({
                "id": original_concept_id,
                "source": original_source,
            })
            current_latex = latex_doc['contenido_latex'] if latex_doc else ""

            # Update all form fields in session state
            st.session_state.pop("edit_id", None)
            st.session_state.pop("edit_source", None)
            st.session_state.edit_titulo = selected_concept.get("titulo", "")
            st.session_state.edit_tipo_titulo = selected_concept.get("tipo_titulo", "ninguno")
            st.session_state["edit_latex_text"] = current_latex
            # estado para remount del editor en Edit Concept
            # fuerza re-mount REAL cuando cambias de concepto (evita que ACE se quede pegado)
            st.session_state["edit_latex_editor_rev"] = st.session_state.get("edit_latex_editor_rev", 0) + 1
            st.session_state["edit_latex_insert"] = ""
            st.session_state["edit_insert_latex"] = False

            st.session_state.edit_comentario = selected_concept.get("comentario", "")
            st.session_state.edit_es_algoritmo = selected_concept.get("es_algoritmo", False)
            st.session_state.edit_categorias = selected_concept.get("categorias", [])
            st.session_state.edit_referencia = selected_concept.get("referencia", {})
            st.session_state.edit_pasos_algoritmo = selected_concept.get("pasos_algoritmo", [])
            st.session_state.edit_contexto_docente = selected_concept.get("contexto_docente", {})
            st.session_state.edit_metadatos_tecnicos = selected_concept.get("metadatos_tecnicos", {})

            # Initialize reference fields in session state
            ref = selected_concept.get("referencia", {})
            st.session_state.edit_ref_tipo = ref.get('tipo_referencia', 'libro')
            st.session_state.edit_ref_autor = ref.get('autor', '')
            st.session_state.edit_ref_fuente = ref.get('fuente', '')
            st.session_state.edit_ref_anio = ref.get('anio', 2024)
            st.session_state.edit_ref_tomo = ref.get('tomo', '')
            st.session_state.edit_ref_edicion = ref.get('edicion', '')
            st.session_state.edit_ref_paginas = ref.get('paginas', '')
            st.session_state.edit_ref_capitulo = ref.get('capitulo', '')
            st.session_state.edit_ref_seccion = ref.get('seccion', '')
            st.session_state.edit_ref_editorial = ref.get('editorial', '')
            st.session_state.edit_ref_doi = ref.get('doi', '')
            st.session_state.edit_ref_url = ref.get('url', '')
            st.session_state.edit_ref_issbn = ref.get('issbn', '')
            # Citekey can be stored either at concept-level (legacy) or inside referencia (preferred).
            st.session_state.edit_ref_citekey = (
                (selected_concept.get("citekey") or "")
                or (ref.get('citekey') or '')
            )

            # Initialize teaching context fields in session state
            context = selected_concept.get("contexto_docente", {})
            st.session_state.edit_nivel = context.get('nivel_contexto', 'introductorio')
            st.session_state.edit_formalidad = context.get('grado_formalidad', 'informal')

            # Initialize technical metadata fields in session state
            meta = selected_concept.get("metadatos_tecnicos", {})
            st.session_state.edit_notacion = meta.get('usa_notacion_formal', True)
            st.session_state.edit_demostracion = meta.get('incluye_demostracion', False)
            st.session_state.edit_operativa = meta.get('es_definicion_operativa', False)
            st.session_state.edit_fundamental = meta.get('es_concepto_fundamental', False)
            st.session_state.edit_previos = ', '.join(meta.get('requiere_conceptos_previos', [])) if meta.get('requiere_conceptos_previos') else ""
            st.session_state.edit_ejemplo = meta.get('incluye_ejemplo', False)
            st.session_state.edit_autocontenible = meta.get('es_autocontenible', True)
            st.session_state.edit_presentacion = meta.get('tipo_presentacion', 'expositivo')
            st.session_state.edit_simbolico = meta.get('nivel_simbolico', 'bajo')
            st.session_state.edit_aplicacion = meta.get('tipo_aplicacion') or []

            # Initialize algorithm fields in session state
            st.session_state.edit_algoritmo = selected_concept.get("es_algoritmo", False)
            st.session_state.edit_pasos = '\n'.join(selected_concept.get("pasos_algoritmo", [])) if selected_concept.get("pasos_algoritmo") else ""

            # Clear any pending LaTeX insertions
            st.session_state.edit_latex_insert = ""
            st.session_state.edit_insert_latex = False

            # Force rerun to update all widgets
            st.rerun()

        render_update_flash(
            st,
            st.session_state,
            database_scope=edit_feedback_database_scope,
            concept_id=original_concept_id,
            source=original_source,
        )

        # Display header
        st.markdown("---")
        st.subheader(f"✏️ Editing: {selected_concept.get('titulo', selected_concept['id'])}")

        # Basic information
        st.subheader("📋 Basic Information")

        col1, col2 = st.columns(2)
        with col1:
            st.caption("ID (immutable)")
            st.code(original_concept_id, language=None)
            st.caption("Source snapshot (immutable)")
            st.code(original_source, language=None)
            if original_source_id_present:
                st.caption("Managed Source ID (immutable)")
                st.code(
                    str(original_source_id) if original_source_id is not None else "null",
                    language=None,
                )
                if original_source_id is None:
                    st.warning(
                        "The Managed Source link field is present but invalid. "
                        "Repair link is outside this phase."
                    )
            else:
                st.info("Legacy concept — not linked to a managed Source.")

        with col2:
            titulo = st.text_input("Title", key="edit_titulo")
            tipo_titulo = st.selectbox(
                "Title Type",
                [t.value for t in TipoTitulo],
                key="edit_tipo_titulo",
            )

        if not original_source_id_present:
            st.markdown("---")
            st.subheader("🔗 Link to an existing managed Source")
            st.caption(
                "This is a separate, explicit action. It only adds a Managed Source ID; "
                "the ordinary Update Concept action remains unchanged."
            )

            link_source_selector_key = source_catalog_state_key(
                "legacy_link_target_source_id",
                original_concept_id,
                original_source,
            )
            link_confirmation_key = source_catalog_state_key(
                "legacy_link_confirmation",
                original_concept_id,
                original_source,
            )
            link_button_key = source_catalog_state_key(
                "legacy_link_submit",
                original_concept_id,
                original_source,
            )
            link_source_repository = None
            managed_sources = ()
            managed_source_labels = {}
            selected_source_id = None
            selected_source_preview = None
            link_action_available = False
            link_catalog_error = None

            if catalog_context is None:
                link_catalog_error = catalog_context_error or "no active Source Catalog"
            else:
                link_source_repository = catalog_context.source_repository
                try:
                    managed_sources = load_active_sources(link_source_repository)
                    managed_source_labels = source_labels(managed_sources)
                except Exception as exc:
                    link_catalog_error = safe_catalog_error(exc)

            if link_catalog_error is not None:
                st.error(
                    "No se pudieron cargar las Sources administradas: "
                    f"{link_catalog_error}"
                )
            elif not managed_sources:
                st.warning(
                    "No hay Sources activas disponibles. "
                    "Crea primero una Source desde Add Source."
                )
            else:
                managed_source_ids = [source.source_id for source in managed_sources]
                selected_source_id = st.selectbox(
                    "Managed Source",
                    options=managed_source_ids,
                    index=None,
                    placeholder="Select an active managed Source",
                    format_func=lambda value: managed_source_labels[value],
                    help="Only active Sources from the current database are listed.",
                    key=link_source_selector_key,
                )
                selected_source_preview = next(
                    (
                        candidate
                        for candidate in managed_sources
                        if candidate.source_id == selected_source_id
                    ),
                    None,
                )

                if selected_source_preview is not None:
                    st.markdown(f"**Historical Source snapshot:** `{original_source}`")
                    st.markdown(
                        "**Managed Source selected:** "
                        f"`{selected_source_preview.name}`"
                    )
                    st.markdown(f"**Target Managed Source ID:** `{selected_source_id}`")
                    if original_source != selected_source_preview.name:
                        st.warning(
                            "La vinculación añadirá el Managed Source ID, pero no cambiará "
                            "el snapshot histórico ni la clave id@source."
                        )

                    link_confirmed = st.checkbox(
                        f"I confirm historical snapshot `{original_source}`, managed Source "
                        f"`{selected_source_preview.name}`, and target Source ID "
                        f"`{selected_source_id}`; this action will not move the concept or "
                        "change its id@source key.",
                        key=link_confirmation_key,
                    )
                    link_action_available = bool(link_confirmed)

            if st.button(
                "🔗 Link managed Source",
                key=link_button_key,
                disabled=not link_action_available,
            ):
                rehydrated_source = None
                try:
                    rehydrated_source = resolve_active_source(
                        link_source_repository,
                        selected_source_id,
                    )
                except Exception as exc:
                    st.error(
                        "No se pudo revalidar la Source administrada: "
                        f"{safe_catalog_error(exc)}"
                    )

                if not can_save_with_managed_source(rehydrated_source):
                    st.error(
                        "The selected managed Source is no longer active or available. "
                        "Nothing was linked."
                    )
                else:
                    link_result = link_concept_to_existing_managed_source(
                        db,
                        concept_id=original_concept_id,
                        source=original_source,
                        expected_source_id=original_source_id,
                        target_source_id=rehydrated_source.source_id,
                    )
                    if link_result.status in {
                        ConceptSourceLinkStatus.SUCCESS,
                        ConceptSourceLinkStatus.ALREADY_LINKED,
                    }:
                        st.success(
                            "The concept is linked to the selected managed Source. "
                            "Its ID, historical Source snapshot, and id@source key are unchanged."
                        )
                        st.session_state.pop(link_source_selector_key, None)
                        st.session_state.pop(link_confirmation_key, None)
                        st.rerun()
                    elif link_result.status is ConceptSourceLinkStatus.TARGET_NOT_FOUND:
                        st.error("The selected managed Source no longer exists. Nothing was linked.")
                    elif link_result.status is ConceptSourceLinkStatus.TARGET_INACTIVE:
                        st.error("The selected managed Source is archived. Nothing was linked.")
                    elif link_result.status is ConceptSourceLinkStatus.CONCEPT_NOT_FOUND:
                        st.error("The original legacy concept no longer exists. Nothing was linked.")
                    elif link_result.status is ConceptSourceLinkStatus.LATEX_NOT_FOUND:
                        st.error("The matching LaTeX document is missing. Nothing was linked.")
                    elif link_result.status is ConceptSourceLinkStatus.STALE_IDENTITY:
                        st.error("The concept changed after it was loaded. Reload before retrying.")
                    elif link_result.status is ConceptSourceLinkStatus.LINK_MISMATCH:
                        st.error(
                            "Concept and LaTeX Source links do not match. "
                            "Repair link is outside this phase."
                        )
                    elif (
                        link_result.status
                        is ConceptSourceLinkStatus.ALREADY_LINKED_TO_DIFFERENT_SOURCE
                    ):
                        st.error(
                            "The concept is already linked to a different managed Source. "
                            "Change Source is outside this phase."
                        )
                    elif link_result.status is ConceptSourceLinkStatus.FAILED_COMPENSATED:
                        st.error(
                            "The link failed, but the added concept link was safely removed. "
                            "No complete link was reported."
                        )
                    elif (
                        link_result.status
                        is ConceptSourceLinkStatus.PARTIAL_RECOVERY_REQUIRED
                    ):
                        st.error(
                            "The link may be partial and requires recovery before retrying. "
                            f"Details: {link_result.message}"
                        )
                    else:
                        st.error(f"The Source link failed: {link_result.message}")

        # Concept type (read-only for now to avoid complications)
        st.info(f"**Concept Type:** {selected_concept['tipo']} (cannot be changed)")

        # Categories
        # Get all available categories from database
        categorias_db = db.concepts.distinct("categorias")
        categorias_db = [cat for cat in categorias_db if isinstance(cat, str)]

        # Combine predefined and database categories
        categorias_predefinidas = ["Algebra", "Analysis", "Topology", "Geometry", "Number Theory", "Combinatorics", "Logic", "Statistics", "Calculus"]
        all_categories = sorted(set(categorias_predefinidas + categorias_db))

        categorias = st.multiselect(
            "Categories",
            all_categories,
            key="edit_categorias",
        )

        # LaTeX content with helper toolbar
        st.subheader("Contenido LaTeX")

        st.session_state.setdefault("edit_latex_text", "")
        st.session_state.setdefault("edit_latex_editor_rev", 0)
        st.session_state.setdefault("edit_latex_insert", "")
        st.session_state.setdefault("edit_insert_latex", False)

        with st.expander("Herramientas LaTeX", expanded=False):
            render_latex_toolbar(
                surface=LATEX_SURFACE_CONCEPTS,
                key_prefix="concept_edit_latex_tool",
                on_insert=lambda snippet: queue_latex_snippet(
                    st.session_state,
                    snippet_key="edit_latex_insert",
                    trigger_key="edit_insert_latex",
                    snippet=snippet,
                ),
            )

        # -------------------------
        # LaTeX editor (ACE) - Edit Concept
        # -------------------------

        # Handle insertion (DEBE IR ANTES del st_ace)
        if apply_queued_latex_snippet(
            st.session_state,
            text_key="edit_latex_text",
            snippet_key="edit_latex_insert",
            trigger_key="edit_insert_latex",
        ):
            st.session_state["edit_latex_editor_rev"] += 1
            st.rerun()

        editor_seed = f"{original_concept_id}@{original_source}"
        contenido_latex = st_ace(
            value=st.session_state["edit_latex_text"],
            language="latex",
            theme="monokai",
            font_size=16,
            tab_size=2,
            height=800,        # aquí súbele para edición cómoda
            wrap=True,
            show_gutter=True,
            auto_update=True,
            key=f"edit_latex_editor__{editor_seed}__{st.session_state['edit_latex_editor_rev']}",
        )

        # Sincronizar el contenido del editor con el estado
        st.session_state["edit_latex_text"] = contenido_latex or ""
        contenido_latex = st.session_state["edit_latex_text"]  # este es el que se guarda
        _render_tikz_weight_warnings(contenido_latex)
        concept_media_assets = _render_concept_media_manager(
            db,
            original_concept_id,
            original_source,
            prefix="edit_concept",
            latex_insert_key="edit_latex_insert",
            insert_flag_key="edit_insert_latex",
        )

        ##----------------------------------------
        # Algorithm section
        st.subheader("⚙️ Algorithm Information")
        col1, col2 = st.columns(2)
        with col1:
            es_algoritmo = st.checkbox("Is this an algorithm?", key="edit_algoritmo")
        with col2:
            if es_algoritmo:
                pasos_algoritmo = editable_text_area("Algorithm Steps", key="edit_pasos")

        # Reference information
        st.subheader("📚 Reference Information")
        current_ref = st.session_state.edit_referencia

        with st.expander("Edit Reference", expanded=bool(current_ref)):
            col1, col2 = st.columns(2)
            with col1:
                ref_tipo = st.selectbox(
                    "Reference Type",
                    [t.value for t in TipoReferencia],
                    key="edit_ref_tipo"
                )
                ref_autor = st.text_input("Author", key="edit_ref_autor")
                ref_fuente = st.text_input("Source/Title", key="edit_ref_fuente")
                ref_anio = st.number_input("Year", min_value=1800, max_value=2030, key="edit_ref_anio")

            with col2:
                ref_tomo = st.text_input("Volume", key="edit_ref_tomo")
                ref_edicion = st.text_input("Edition", key="edit_ref_edicion")
                ref_paginas = st.text_input("Pages", key="edit_ref_paginas")
                ref_capitulo = st.text_input("Chapter", key="edit_ref_capitulo")

            ref_seccion = st.text_input("Section", key="edit_ref_seccion")
            ref_editorial = st.text_input("Publisher", key="edit_ref_editorial")
            ref_doi = st.text_input("DOI", key="edit_ref_doi")
            ref_url = st.text_input("URL", key="edit_ref_url")
            ref_issbn = st.text_input("ISBN", key="edit_ref_issbn")
            # Optional citekey used for bibliography export (Quarto/Pandoc).
            st.text_input("Citekey (opcional)", key="edit_ref_citekey")

        # Teaching context
        st.subheader("🎓 Teaching Context")
        current_context = st.session_state.edit_contexto_docente

        with st.expander("Edit Teaching Context", expanded=bool(current_context)):
            col1, col2 = st.columns(2)
            with col1:
                nivel_contexto = st.selectbox(
                    "Context Level",
                    [n.value for n in NivelContexto],
                    key="edit_nivel",
                )
            with col2:
                grado_formalidad = st.selectbox(
                    "Formality Degree",
                    [g.value for g in GradoFormalidad],
                    key="edit_formalidad",
                )

        # Technical metadata
        st.subheader("🔧 Technical Metadata")
        current_meta = st.session_state.edit_metadatos_tecnicos

        with st.expander("Edit Technical Metadata", expanded=bool(current_meta)):
            col1, col2 = st.columns(2)
            with col1:
                usa_notacion_formal = st.checkbox("Uses Formal Notation", key="edit_notacion")
                incluye_demostracion = st.checkbox("Includes Proof", key="edit_demostracion")
                es_definicion_operativa = st.checkbox("Is Operational Definition", key="edit_operativa")
                es_concepto_fundamental = st.checkbox("Is Fundamental Concept", key="edit_fundamental")

            with col2:
                requiere_conceptos_previos = st.text_area(
                    "Required Previous Concepts",
                    key="edit_previos"
                )
                incluye_ejemplo = st.checkbox("Includes Example", key="edit_ejemplo")
                es_autocontenible = st.checkbox("Is Self-Contained", key="edit_autocontenible")

            tipo_presentacion = st.selectbox(
                "Presentation Type",
                [t.value for t in TipoPresentacion],
                key="edit_presentacion"
            )
            nivel_simbolico = st.selectbox(
                "Symbolic Level",
                [n.value for n in NivelSimbolico],
                key="edit_simbolico"
            )
            tipo_aplicacion = st.multiselect(
                "Application Type",
                [t.value for t in TipoAplicacion],
                key="edit_aplicacion"
            )
        # Comment
        comentario = editable_text_area(
            "Comment",
            key="edit_comentario"
        )
        # Action buttons
        st.markdown("---")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 Update Concept", type="primary"):
                try:
                    # Identity fields are deliberately absent from ordinary edits.
                    concept_changes = {
                        "titulo": titulo if titulo else None,
                        "tipo_titulo": tipo_titulo,
                        "categorias": categorias,
                        "es_algoritmo": es_algoritmo,
                        "pasos_algoritmo": pasos_algoritmo.split('\n') if es_algoritmo and pasos_algoritmo else None,
                        "comentario": comentario if comentario else None,
                        "image_ids": [asset["asset_id"] for asset in concept_media_assets],
                        # Keep concept-level citekey for backward compatibility.
                        "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }

                    # Add reference if provided
                    if ref_autor or ref_fuente:
                        concept_changes["referencia"] = {
                            "tipo_referencia": ref_tipo,
                            "autor": ref_autor if ref_autor else None,
                            "fuente": ref_fuente if ref_fuente else None,
                            "anio": ref_anio if ref_anio else None,
                            "tomo": ref_tomo if ref_tomo else None,
                            "edicion": ref_edicion if ref_edicion else None,
                            "paginas": ref_paginas if ref_paginas else None,
                            "capitulo": ref_capitulo if ref_capitulo else None,
                            "seccion": ref_seccion if ref_seccion else None,
                            "editorial": ref_editorial if ref_editorial else None,
                            "doi": ref_doi if ref_doi else None,
                            "url": ref_url if ref_url else None,
                            "issbn": ref_issbn if ref_issbn else None,
                            # NEW: Persist citekey at reference-level (preferred).
                            "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                        }

                    # Add teaching context if provided
                    if nivel_contexto or grado_formalidad:
                        concept_changes["contexto_docente"] = {
                            "nivel_contexto": nivel_contexto,
                            "grado_formalidad": grado_formalidad
                        }

                    # Add technical metadata if provided
                    if usa_notacion_formal is not None or incluye_demostracion is not None:
                        concept_changes["metadatos_tecnicos"] = {
                            "usa_notacion_formal": usa_notacion_formal,
                            "incluye_demostracion": incluye_demostracion,
                            "es_definicion_operativa": es_definicion_operativa,
                            "es_concepto_fundamental": es_concepto_fundamental,
                            "requiere_conceptos_previos": [c.strip() for c in requiere_conceptos_previos.split(',')] if requiere_conceptos_previos else None,
                            "incluye_ejemplo": incluye_ejemplo,
                            "es_autocontenible": es_autocontenible,
                            "tipo_presentacion": tipo_presentacion,
                            "nivel_simbolico": nivel_simbolico,
                            "tipo_aplicacion": tipo_aplicacion if tipo_aplicacion else None
                        }

                    update_result = update_concept_fields_preserving_identity(
                        db,
                        concept_id=original_concept_id,
                        source=original_source,
                        expected_source_id=original_source_id,
                        changes=concept_changes,
                        contenido_latex=contenido_latex,
                        now=datetime.now(),
                    )

                    update_feedback = feedback_for_update_result(
                        update_result,
                        concept_id=original_concept_id,
                        source=original_source,
                    )
                    if update_feedback.level == "success":
                        store_update_success_flash(
                            st.session_state,
                            update_result,
                            database_scope=edit_feedback_database_scope,
                            concept_id=original_concept_id,
                            source=original_source,
                        )
                        st.session_state.pop(legacy_last_selected_key, None)
                        st.rerun()
                    elif update_feedback.level == "warning":
                        st.warning(update_feedback.message)
                    else:
                        st.error(update_feedback.message)

                except Exception as e:
                    st.error(safe_update_exception_message(e))

        # PDF Generation Button for Edit Concept
        st.markdown("---")
        st.subheader("📄 Generar PDF")
        edit_pdf_context = pdf_preview_context(
            "edit_concept",
            current_db,
            original_source,
            original_concept_id,
        )
        concept_pdf_root = get_exports_dir(
            configured=resolve_config().export_directory
        ) / "concepts"

        # Check if we have the minimum required data for PDF generation
        if original_concept_id and original_source and contenido_latex:
            if st.button(
                "📄 Generar vista previa PDF",
                key="edit_pdf_btn",
                type="secondary",
            ):
                # Build concept data for PDF generation
                pdf_concept_data = {
                    "id": original_concept_id,
                    "tipo": selected_concept['tipo'],
                    "titulo": titulo if titulo else original_concept_id,
                    "categorias": categorias,
                    "contenido_latex": contenido_latex,
                    "source": original_source,
                    "comentario": comentario if comentario else None
                }

                # Add reference if provided
                if ref_autor or ref_fuente:
                    pdf_concept_data["referencia"] = {
                        "tipo_referencia": ref_tipo,
                        "autor": ref_autor if ref_autor else None,
                        "fuente": ref_fuente if ref_fuente else None,
                        "anio": ref_anio if ref_anio else None,
                        "tomo": ref_tomo if ref_tomo else None,
                        "edicion": ref_edicion if ref_edicion else None,
                        "paginas": ref_paginas if ref_paginas else None,
                        "capitulo": ref_capitulo if ref_capitulo else None,
                        "seccion": ref_seccion if ref_seccion else None,
                        "editorial": ref_editorial if ref_editorial else None,
                        "doi": ref_doi if ref_doi else None,
                        "url": ref_url if ref_url else None,
                        "issbn": ref_issbn if ref_issbn else None,
                        # NEW: Persist citekey at reference-level too.
                        "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }

                _generate_concept_pdf_preview(
                    "edit_concept",
                    pdf_concept_data,
                    context_identity=edit_pdf_context,
                    allowed_root=concept_pdf_root,
                )
        else:
            clear_pdf_preview(st.session_state, "edit_concept")
            st.info("ℹ️ Complete los campos requeridos (ID, Source, LaTeX Content) para generar el PDF")

        render_pdf_preview(
            st,
            st.session_state,
            "edit_concept",
            context_identity=edit_pdf_context,
        )

        with col2:
            if st.button("🔄 Reset to Original"):
                st.rerun()

        with col3:
            render_concept_deletion(st, db.db, selected_concept, scope='edit')

# Browse Concepts page

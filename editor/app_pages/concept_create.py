"""Concept create; extracted without import-time rendering."""

from __future__ import annotations

from datetime import datetime

import streamlit as st
from streamlit_ace import st_ace

from editor.concept_reference_form import (
    apply_reference_to_state as apply_concept_reference_to_state,
)
from editor.concept_reference_form import concept_reference_has_content
from editor.concept_reference_form import render_concept_reference_form
from editor.concept_reference_form import state_key as concept_reference_state_key
from editor.concept_reference_form import sync_reference_scope as sync_concept_reference_scope
from editor.db.concept_repository import concept_exists
from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.helpers.concept_builders import build_concept_metadata
from editor.helpers.concept_reference_history import load_last_reference_by_source
from editor.helpers.managed_source_selection import can_save_with_managed_source
from editor.helpers.managed_source_selection import load_active_sources
from editor.helpers.managed_source_selection import resolve_active_source
from editor.helpers.managed_source_selection import source_labels
from editor.helpers.tipo_aplicacion import TipoAplicacion
from editor.helpers.tipo_contexto import NivelContexto
from editor.helpers.tipo_formalidad import GradoFormalidad
from editor.helpers.tipo_presentacion import TipoPresentacion
from editor.helpers.tipo_simbolico import NivelSimbolico
from editor.helpers.tipo_titulo import TipoTitulo
from editor.latex_tools import LATEX_SURFACE_CONCEPTS
from editor.latex_tools import apply_queued_latex_snippet
from editor.latex_tools import queue_latex_snippet
from editor.pdf_preview import clear_pdf_preview
from editor.pdf_preview import pdf_preview_context
from editor.pdf_preview import render_pdf_preview
from editor.source_catalog.shared import safe_error_message as safe_catalog_error
from editor.source_catalog.state import state_key as source_catalog_state_key
from editor.ui.concept_media import _render_concept_media_manager
from editor.ui.concept_media import _render_tikz_weight_warnings
from editor.ui.concept_pdf import _generate_concept_pdf_preview
from editor.ui.editable_text import editable_text_area
from editor.ui.latex_toolbar import render_latex_toolbar
from editor.validators.concept_validator import validate_new_concept_identity
from editor.validators.concept_validator import validate_semantic_duplicate
from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir
from schemas.schemas import ConceptoBase


def render(context):
    """Render only the selected page using its explicit application context."""
    active_database_scope = context.active_database_scope
    catalog_context = context.catalog_context
    catalog_context_error = context.catalog_context_error
    current_database_label = context.current_database_label
    current_db = context.current_db
    db = context.db
    st.title("➕ Add New Mathematical Concept")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    managed_source_repository = None
    managed_sources = ()
    managed_source_labels = {}
    managed_source_catalog_error = None
    if catalog_context is None:
        managed_source_catalog_error = catalog_context_error or "no active Source Catalog"
    else:
        managed_source_repository = catalog_context.source_repository
        try:
            managed_sources = load_active_sources(managed_source_repository)
            managed_source_labels = source_labels(managed_sources)
        except Exception as exc:
            managed_source_catalog_error = safe_catalog_error(exc)

    st.info(f"📊 Adding concept to: **{current_database_label}**")
    st.markdown("### 📘 Concept Type")
    # Concept type selection
    concept_type = st.selectbox(
        "Concept Type",
        ["definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"],
        help="Select the type of mathematical concept you want to add",
    )

    # Basic information
    st.subheader("📋 Basic Information")

    selected_source_id = None
    selected_source_preview = None
    source = None
    source_id = None
    source_selection_valid = False
    col1, col2 = st.columns(2)
    with col1:
        concept_id = st.text_input("ID", placeholder="e.g., def:grupo_001", help="Unique identifier for the concept")

        if managed_source_catalog_error is not None:
            st.error(
                "No se pudieron cargar las Sources administradas: "
                f"{managed_source_catalog_error}"
            )
        elif not managed_sources:
            st.warning(
                "No hay Sources disponibles. Crea primero una Source desde Add Source."
            )
        else:
            managed_source_ids = [source.source_id for source in managed_sources]
            selected_source_id = st.selectbox(
                "Source",
                options=managed_source_ids,
                index=None,
                placeholder="Select a managed Source",
                format_func=lambda value: managed_source_labels[value],
                help="Select an active Source managed from Add Source.",
                key=source_catalog_state_key("add_concept_source_id"),
            )
            selected_source_preview = next(
                (
                    candidate
                    for candidate in managed_sources
                    if candidate.source_id == selected_source_id
                ),
                None,
            )
            source_selection_valid = can_save_with_managed_source(
                selected_source_preview
            )
            if source_selection_valid:
                source = selected_source_preview.name
                source_id = selected_source_preview.source_id

        if source:
            try:
                docs = list(
                    db.concepts.find(
                        {"source": source},
                        {"id": 1, "titulo": 1, "_id": 0}
                    )
                )
                    # Normaliza y ordena por id
                items = sorted(
                        [
                            {"id": d.get("id", "").strip(),
                             "titulo": (d.get("titulo") or "").strip()}
                            for d in docs
                            if isinstance(d.get("id"), str)
                        ],
                        key=lambda x: x["id"]
                )
            except Exception:
                items = []

            st.markdown("#### Existing IDs for this source")
            if items:
                show_n = 50
                lines = []
                for it in items[-show_n:]:
                    if it["titulo"]:
                        lines.append(f"{it['id']}  —  {it['titulo']}")
                    else:
                        lines.append(f"{it['id']}")
                st.text_area(
                    "Existing IDs (latest 10)",
                    value="\n".join(lines),
                    height=220,
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                st.caption("No concepts yet for this source.")

    with col2:
        titulo = st.text_input("Title (Optional)", placeholder="e.g., Definition of Group")
        tipo_titulo = st.selectbox("Title Type", [t.value for t in TipoTitulo])

    # 1. Categorías base (predefinidas)
    categorias_base = [
    "Algebra", "Analysis", "Topology", "Geometry", "Number Theory",
    "Combinatorics", "Logic", "Statistics", "Calculus"]

    # 2. Categorías adicionales ya existentes en la base de datos
    categorias_db = db.concepts.distinct("categorias")
    categorias_db = [cat for cat in categorias_db if isinstance(cat, str)]

    # 3. Opcional: incluir categorías sugeridas por usuarios previos
    try:
        categorias_sugeridas = [doc["nombre"] for doc in db.categorias.find()]
    except Exception:
        categorias_sugeridas = []

    # 4. Combinar todas las categorías conocidas y eliminar duplicados
    categorias_existentes = sorted(set(categorias_base + categorias_db + categorias_sugeridas))

    # 🔒 Asegurar estado inicial
    if 'categorias_seleccionadas' not in st.session_state:
        st.session_state.categorias_seleccionadas = []

    # 5. Input para nueva categoría
    nueva_categoria = st.text_input("➕ Add New Category (Optional)", placeholder="e.g., Discrete Math")

    # 6. Agregar a lista si es nueva
    if nueva_categoria:
        nueva_categoria = nueva_categoria.strip()
        if nueva_categoria and nueva_categoria not in st.session_state.categorias_seleccionadas:
            st.session_state.categorias_seleccionadas.append(nueva_categoria)

    # ⚠️ Agregar seleccionadas a las opciones visibles
    categorias_existentes = sorted(set(categorias_base + categorias_db + categorias_sugeridas + st.session_state.categorias_seleccionadas))

    # 7. Mostrar multiselect
    st.session_state.categorias_seleccionadas = st.multiselect("Categories",
    options=categorias_existentes,
    default=st.session_state.categorias_seleccionadas,
    help="Select relevant mathematical categories")

    # 8. Resultado final para guardar
    categorias = st.session_state.categorias_seleccionadas

    # LaTeX content with helper toolbar
    st.subheader("Contenido LaTeX")

    st.session_state.setdefault("latex_text", "")
    st.session_state.setdefault("latex_editor_rev", 0)
    st.session_state.setdefault("latex_insert", "")
    st.session_state.setdefault("insert_latex", False)

    with st.expander("Herramientas LaTeX", expanded=False):
        render_latex_toolbar(
            surface=LATEX_SURFACE_CONCEPTS,
            key_prefix="concept_create_latex_tool",
            on_insert=lambda snippet: queue_latex_snippet(
                st.session_state,
                snippet_key="latex_insert",
                trigger_key="insert_latex",
                snippet=snippet,
            ),
        )

    # LaTeX text area
    # -------------------------
    # LaTeX editor (state real + remount para inserciones)
    # -------------------------
    # Handle insertion (DEBE IR ANTES del st_ace)
    if apply_queued_latex_snippet(
        st.session_state,
        text_key="latex_text",
        snippet_key="latex_insert",
        trigger_key="insert_latex",
    ):
        st.session_state["latex_editor_rev"] += 1
        st.rerun()

    contenido_latex = st_ace(
        value=st.session_state["latex_text"],
        language="latex",
        theme="monokai",
        font_size=16,
        tab_size=2,
        height=800,
        wrap=True,
        show_gutter=True,
        auto_update=True,
        key=f"latex_editor_{st.session_state['latex_editor_rev']}"
    )
    # Sincronizar el contenido del editor con el estado
    st.session_state["latex_text"] = contenido_latex or ""
    # Este es el contenido que usarás para guardar en DB
    contenido_latex = st.session_state["latex_text"]
    _render_tikz_weight_warnings(contenido_latex)
    concept_media_assets = _render_concept_media_manager(
        db,
        concept_id,
        source,
        prefix="add_concept",
        latex_insert_key="latex_insert",
        insert_flag_key="insert_latex",
    )
    ###----

    # Algorithm section

    st.subheader("⚙️ Algorithm Information")
    col1, col2 = st.columns(2)
    with col1:
        es_algoritmo = st.checkbox("Is this an algorithm?")
    with col2:
        if es_algoritmo:
            pasos_algoritmo = editable_text_area(
                "Algorithm Steps",
                key="add_concept_algorithm_steps",
                placeholder="Enter algorithm steps...",
            )

    st.subheader("📚 Reference Information")
    sync_concept_reference_scope(
        st.session_state,
        database_scope=active_database_scope,
        source_id=selected_source_id,
        concept_id=concept_id,
    )
    if st.button(
        "📋 Cargar referencia del concepto anterior",
        key=concept_reference_state_key("load_previous"),
    ):
        try:
            ref = load_last_reference_by_source(db, source)
            if not ref:
                st.warning(f"⚠️ No se encontró ninguna referencia previa para el source: {source!r}")
            else:
                apply_concept_reference_to_state(st.session_state, ref)
                st.session_state[concept_reference_state_key("notice")] = (
                    "Referencia cargada desde el último concepto de esta Source. "
                    "Revisa los campos antes de guardar."
                )
                st.rerun()
        except Exception as e:
            st.error(f"❌ Error cargando referencia previa: {e}")

    reference_data = render_concept_reference_form(
        st,
        database_scope=active_database_scope,
        source_id=selected_source_id,
        concept_id=concept_id,
    )
    ref_citekey = reference_data["citekey"]

    # Teaching context
    st.subheader("🎓 Teaching Context")
    with st.expander("Add Teaching Context", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            nivel_contexto = st.selectbox("Context Level", [n.value for n in NivelContexto])
        with col2:
            grado_formalidad = st.selectbox("Formality Degree", [g.value for g in GradoFormalidad])

    # Technical metadata
    st.subheader("🔧 Technical Metadata")
    with st.expander("Add Technical Metadata", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            usa_notacion_formal = st.checkbox("Uses Formal Notation", value=True)
            incluye_demostracion = st.checkbox("Includes Proof")
            es_definicion_operativa = st.checkbox("Is Operational Definition")
            es_concepto_fundamental = st.checkbox("Is Fundamental Concept")

        with col2:
            requiere_conceptos_previos = st.text_area("Required Previous Concepts", placeholder="Enter concepts separated by commas")
            incluye_ejemplo = st.checkbox("Includes Example")
            es_autocontenible = st.checkbox("Is Self-Contained", value=True)

        tipo_presentacion = st.selectbox("Presentation Type", [t.value for t in TipoPresentacion])
        nivel_simbolico = st.selectbox("Symbolic Level", [n.value for n in NivelSimbolico])
        tipo_aplicacion = st.multiselect("Application Type", [t.value for t in TipoAplicacion])

    # Comment
    comentario = editable_text_area(
        "Comment (Optional)",
        key="add_concept_comment",
        placeholder="Additional comments or notes...",
    )

    # Submit button
    if st.button(
        "💾 Save Concept",
        type="primary",
        disabled=not source_selection_valid,
    ):
        if managed_source_repository is None or not selected_source_id:
            st.error("❌ Select an active managed Source before saving.")
            st.stop()
        try:
            selected_source = resolve_active_source(
                managed_source_repository,
                selected_source_id,
            )
        except Exception as exc:
            st.error(
                "No se pudieron cargar las Sources administradas: "
                f"{safe_catalog_error(exc)}"
            )
            st.stop()
        if not can_save_with_managed_source(selected_source):
            st.error(
                "❌ The selected Source is no longer active or available. "
                "Choose another managed Source."
            )
            st.stop()
        source = selected_source.name
        source_id = selected_source.source_id

        # 1. Campos requeridos (primero)
        if not concept_id or not source or not contenido_latex:
            st.error("❌ Please fill in all required fields: ID, Source, and LaTeX Content")
            st.stop()
        # 2. Identidad lógica (id, source)
        errors = validate_new_concept_identity(db, concept_id, source)
        for err in errors:
            st.error(err)
        if errors:
            st.stop()

        # 3. Duplicado semántico
        errors = validate_semantic_duplicate(db, titulo, concept_type, source)
        for err in errors:
            st.error(err)
        if errors:
            st.stop()

        #if titulo and semantic_duplicate_exists(db, titulo, concept_type, source):

            #st.error("❌ Ya existe un concepto con el mismo TITULO y tipo desde este source.")
            #st.info("💡 Usa un ID distinto solo si el concepto es realmente diferente, o edita el existente.")
            #st.stop()
        # 4. Guardado
        try:
            # Build concept data
            concept_data = {
                "id": concept_id,
                "tipo": concept_type,
                "titulo": titulo if titulo else None,
                "tipo_titulo": tipo_titulo,
                "categorias": categorias,
                "contenido_latex": contenido_latex,
                "es_algoritmo": es_algoritmo,
                "pasos_algoritmo": pasos_algoritmo.split('\n') if es_algoritmo and pasos_algoritmo else None,
                "comentario": comentario if comentario else None,
                "source": source,
                "source_id": source_id,
                "image_ids": [asset["asset_id"] for asset in concept_media_assets],
                "fecha_creacion": datetime.now(),
                "ultima_actualizacion": datetime.now(),
                # Keep the legacy top-level construction input for exporter compatibility.
                # The validated authoritative value is concept.referencia.citekey.
                "citekey": ref_citekey if ref_citekey else None,
                }

            # Add reference if provided
            if concept_reference_has_content(reference_data):
                concept_data["referencia"] = reference_data

            # Add teaching context if provided
            if nivel_contexto or grado_formalidad:
                concept_data["contexto_docente"] = {
                    "nivel_contexto": nivel_contexto,
                    "grado_formalidad": grado_formalidad
                    }

                # Add technical metadata if provided
            if usa_notacion_formal is not None or incluye_demostracion is not None:
                concept_data["metadatos_tecnicos"] = {
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

                # Create concept object
            concepto = ConceptoBase(**concept_data)

                # Save to database
            if concept_exists(db, concepto.id, source):
                existing = db.concepts.find_one(
                        {"id": concepto.id, "source": source},
                        {"_id": 1, "id": 1, "source": 1, "titulo": 1, "fecha_creacion": 1, "ultima_actualizacion": 1},
                    )
                st.warning("⚠️ Este concepto ya existe. Usa ✏️ Edit Concept o cambia el ID.")
                if existing:
                    st.json(existing)
                st.stop()
            concepto_dict = build_concept_metadata(concepto)
            now = datetime.now()
            insert_concept_with_latex_atomic(
                    db,
                    concepto.id,
                    source,
                    concepto_dict,
                    contenido_latex,
                    now,
                )

            st.success(
                f"✅ Concept '{concept_id}' saved successfully to "
                f"{current_database_label}!"
            )
            st.balloons()

        except Exception as e:
            st.error(f"❌ Error saving concept: {e}")

    # PDF Generation Button
    st.markdown("---")
    st.subheader("📄 Generar PDF")
    add_pdf_context = pdf_preview_context(
        "add_concept",
        current_db,
        source,
        concept_id,
    )
    concept_pdf_root = get_exports_dir(
        configured=resolve_config().export_directory
    ) / "concepts"

    # Check if we have the minimum required data for PDF generation
    if concept_id and source and contenido_latex:
        if st.button("📄 Generar vista previa PDF", type="secondary"):
            # Build concept data for PDF generation
            pdf_concept_data = {
                "id": concept_id,
                "tipo": concept_type,
                "titulo": titulo if titulo else concept_id,
                "categorias": categorias,
                "contenido_latex": contenido_latex,
                "source": source,
                "comentario": comentario if comentario else None
            }

            # Add reference if provided
            if concept_reference_has_content(reference_data):
                pdf_concept_data["referencia"] = reference_data

            _generate_concept_pdf_preview(
                "add_concept",
                pdf_concept_data,
                context_identity=add_pdf_context,
                allowed_root=concept_pdf_root,
            )
    else:
        clear_pdf_preview(st.session_state, "add_concept")
        st.info("ℹ️ Complete los campos requeridos (ID, Source, LaTeX Content) para generar el PDF")

    render_pdf_preview(
        st,
        st.session_state,
        "add_concept",
        context_identity=add_pdf_context,
    )

# Edit Concept page

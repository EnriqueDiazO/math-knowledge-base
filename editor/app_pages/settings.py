"""Settings; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from editor.source_catalog.shared import render_catalog_status


def render(context):
    """Render only the selected page using its explicit application context."""
    catalog_context = context.catalog_context
    catalog_context_error = context.catalog_context_error
    current_database_label = context.current_database_label
    db = context.db
    st.title("Ajustes")

    st.subheader("Base activa")

    # Database status
    if db is None:
        st.error("No hay una conexión a la base.")
        st.stop()
    else:
        st.success(
            f"Conectada a: {current_database_label}",
            icon=":material/check_circle:",
        )

    # Database statistics
    st.subheader("Resumen")

    col1, col2 = st.columns(2)

    with col1:
        concept_count = db.concepts.count_documents({})
        st.metric("Conceptos", concept_count)

        relation_count = db.relations.count_documents({})
        st.metric("Relaciones", relation_count)

    with col2:
        source_count = len(db.concepts.distinct("source"))
        st.metric("Fuentes", source_count)

        category_count = len(db.concepts.distinct("categorias"))
        st.metric("Categorías", category_count)

    st.subheader("Protección de datos")
    st.info(
        "La release docente no ofrece borrado masivo ni reconstrucción de índices desde esta "
        "pantalla. Usa el respaldo verificado y el diagnóstico seguro antes de cualquier cambio.",
        icon=":material/shield:",
    )
    st.caption("Consulta `docs/BACKUP_AND_RECOVERY.md` y `docs/DOCTOR_AND_BOOTSTRAP.md`.")
    with st.expander("Diagnóstico seguro", expanded=False, icon=":material/diagnosis:"):
        st.caption(
            "Este comando inspecciona la base activa, los índices y las rutas XDG sin crear "
            "estructuras ni mostrar contenido privado."
        )
        st.code("python -m mathmongo.doctor doctor", language="bash")
    if catalog_context is not None:
        st.subheader("Diagnóstico del catálogo")
        render_catalog_status(
            st,
            catalog_context,
            allow_index_initialization=True,
        )
    elif catalog_context_error:
        st.warning(f"No se pudo inspeccionar el catálogo: {catalog_context_error}")

    # Application information
    st.subheader("Aplicación")
    st.write("**MathMongo** · cuaderno académico con LaTeX y almacenamiento MongoDB.")
    st.caption("Autor: Enrique Díaz Ocampo · Licencia MIT")

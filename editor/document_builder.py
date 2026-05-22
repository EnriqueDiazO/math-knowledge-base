from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from exporters_latex.concept_ordering import concept_key
from exporters_latex.concept_ordering import order_by_date
from exporters_latex.concept_ordering import order_by_graph
from exporters_latex.concept_ordering import order_by_title
from exporters_latex.concept_ordering import order_by_type
from exporters_latex.exportadorlatex import ExportadorLatex


CONCEPT_TYPES = [
    "definicion",
    "proposicion",
    "teorema",
    "lema",
    "corolario",
    "ejemplo",
    "nota",
]


def _builder_state_key(name: str) -> str:
    return f"document_builder_{name}"


def _display_label(concept: dict[str, Any]) -> str:
    title = concept.get("titulo") or concept.get("id") or "Sin titulo"
    return f"{title} ({concept.get('tipo', 'sin tipo')} - {concept.get('id')}@{concept.get('source')})"


def _load_concepts(db, source: str, selected_types: list[str], search: str) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"source": source}
    if selected_types:
        query["tipo"] = {"$in": selected_types}

    concepts = list(db.concepts.find(query).sort("titulo", 1))
    search_norm = search.strip().lower()
    if search_norm:
        filtered = []
        for concept in concepts:
            latex_doc = db.latex_documents.find_one(
                {"id": concept.get("id"), "source": concept.get("source")},
                {"contenido_latex": 1, "_id": 0},
            )
            haystack = " ".join(
                str(value or "")
                for value in (
                    concept.get("titulo"),
                    concept.get("id"),
                    concept.get("tipo"),
                    " ".join(concept.get("categorias") or []),
                    (latex_doc or {}).get("contenido_latex"),
                )
            ).lower()
            if search_norm in haystack:
                filtered.append(concept)
        concepts = filtered
    return concepts


def _attach_latex(db, concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for concept in concepts:
        doc = dict(concept)
        latex_doc = db.latex_documents.find_one(
            {"id": doc.get("id"), "source": doc.get("source")}
        )
        doc["contenido_latex"] = (latex_doc or {}).get("contenido_latex", "")
        enriched.append(doc)
    return enriched


def _concepts_for_keys(db, keys: list[str]) -> list[dict[str, Any]]:
    concepts = []
    for key in keys:
        if "@" not in key:
            continue
        concept_id, source = key.split("@", 1)
        concept = db.concepts.find_one({"id": concept_id, "source": source})
        if concept:
            concepts.append(concept)
    return _attach_latex(db, concepts)


def _move_item(items: list[str], index: int, delta: int) -> list[str]:
    target = index + delta
    if target < 0 or target >= len(items):
        return items
    items = list(items)
    items[index], items[target] = items[target], items[index]
    return items


def _relations_for_source(db, source: str) -> list[dict[str, Any]]:
    query = {
        "$or": [
            {"desde": {"$regex": f"@{source}$"}},
            {"hasta": {"$regex": f"@{source}$"}},
        ]
    }
    return list(db.relations.find(query))


def _set_order_from_concepts(concepts: list[dict[str, Any]]) -> None:
    st.session_state[_builder_state_key("items")] = [concept_key(c) for c in concepts]


def render_document_builder_page(db, current_db: str | None = None) -> None:
    st.title("📄 Document Builder")

    if db is None:
        st.error("No database connection. Please select a database in the sidebar.")
        st.stop()

    if current_db:
        st.info(f"Building document from: **{current_db}**")

    items_key = _builder_state_key("items")
    if items_key not in st.session_state:
        st.session_state[items_key] = []

    sources = list(db.concepts.distinct("source"))
    if not sources:
        st.warning("No sources found in the current database.")
        return

    controls_left, controls_right = st.columns([2, 1])
    with controls_left:
        source = st.selectbox("Source", sources, key=_builder_state_key("source"))
    with controls_right:
        output_dir = st.text_input(
            "Output directory",
            value="./exported",
            key=_builder_state_key("output_dir"),
        )

    filter_col1, filter_col2 = st.columns([2, 2])
    with filter_col1:
        selected_types = st.multiselect(
            "Concept types",
            CONCEPT_TYPES,
            default=[],
            key=_builder_state_key("types"),
        )
    with filter_col2:
        search = st.text_input(
            "Search title, id or tags",
            value="",
            key=_builder_state_key("search"),
        )

    available = _load_concepts(db, source, selected_types, search)
    available_by_key = {concept_key(c): c for c in available}

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Conceptos disponibles")
        options = list(available_by_key.keys())
        selected_to_add = st.multiselect(
            "Selecciona conceptos",
            options,
            format_func=lambda key: _display_label(available_by_key[key]),
            key=_builder_state_key("available_select"),
        )

        add_col1, add_col2 = st.columns(2)
        with add_col1:
            if st.button("Agregar seleccionados"):
                current = list(st.session_state[items_key])
                for key in selected_to_add:
                    if key not in current:
                        current.append(key)
                st.session_state[items_key] = current
                st.rerun()
        with add_col2:
            if st.button("Agregar filtrados"):
                current = list(st.session_state[items_key])
                for key in options:
                    if key not in current:
                        current.append(key)
                st.session_state[items_key] = current
                st.rerun()

        st.caption(f"{len(available)} conceptos disponibles con los filtros actuales.")

    with right:
        st.subheader("Documento actual")
        selected_keys = list(st.session_state[items_key])
        selected_concepts = _concepts_for_keys(db, selected_keys)
        selected_by_key = {concept_key(c): c for c in selected_concepts}

        if not selected_keys:
            st.info("Agrega conceptos para construir el documento.")
        else:
            for index, key in enumerate(selected_keys):
                concept = selected_by_key.get(key)
                label = _display_label(concept) if concept else key
                row = st.columns([6, 1, 1, 1, 1])
                row[0].write(f"{index + 1}. {label}")
                if row[1].button("↑", key=f"doc_up_{key}_{index}"):
                    st.session_state[items_key] = _move_item(selected_keys, index, -1)
                    st.rerun()
                if row[2].button("↓", key=f"doc_down_{key}_{index}"):
                    st.session_state[items_key] = _move_item(selected_keys, index, 1)
                    st.rerun()
                if row[3].button("Top", key=f"doc_top_{key}_{index}"):
                    new_items = list(selected_keys)
                    item = new_items.pop(index)
                    new_items.insert(0, item)
                    st.session_state[items_key] = new_items
                    st.rerun()
                if row[4].button("✕", key=f"doc_remove_{key}_{index}"):
                    new_items = list(selected_keys)
                    new_items.pop(index)
                    st.session_state[items_key] = new_items
                    st.rerun()

        clear_col, refresh_col = st.columns(2)
        with clear_col:
            if st.button("Limpiar documento"):
                st.session_state[items_key] = []
                st.rerun()
        with refresh_col:
            if st.button("Refrescar LaTeX"):
                st.rerun()

    st.markdown("---")
    st.subheader("Ordenamiento")
    order_cols = st.columns(4)
    selected_concepts = _concepts_for_keys(db, list(st.session_state[items_key]))

    if order_cols[0].button("Ordenar por tipo"):
        _set_order_from_concepts(order_by_type(selected_concepts))
        st.rerun()
    if order_cols[1].button("Ordenar por titulo"):
        _set_order_from_concepts(order_by_title(selected_concepts))
        st.rerun()
    if order_cols[2].button("Ordenar por fecha"):
        _set_order_from_concepts(order_by_date(selected_concepts))
        st.rerun()
    if order_cols[3].button("Ordenar por grafo"):
        ordered, warnings, _info = order_by_graph(
            selected_concepts,
            _relations_for_source(db, source),
        )
        _set_order_from_concepts(ordered)
        for warning in warnings:
            st.warning(warning)
        st.rerun()

    st.markdown("---")
    st.subheader("Estructura y exportacion")
    export_col1, export_col2, export_col3, export_col4 = st.columns(4)
    with export_col1:
        strict_order = st.checkbox(
            "Respetar orden manual estricto",
            value=True,
            key=_builder_state_key("strict_order"),
        )
    with export_col2:
        group_by_type = st.checkbox(
            "Agrupar por tipo",
            value=False,
            disabled=strict_order,
            key=_builder_state_key("group_by_type"),
        )
    with export_col3:
        compile_pdf = st.checkbox(
            "Generar PDF",
            value=True,
            key=_builder_state_key("compile_pdf"),
        )
    with export_col4:
        overwrite = st.checkbox(
            "Sobrescribir carpeta",
            value=False,
            key=_builder_state_key("overwrite"),
        )

    selected_concepts = _concepts_for_keys(db, list(st.session_state[items_key]))
    if selected_concepts:
        st.write("Vista previa:")
        for i, concept in enumerate(selected_concepts, start=1):
            missing = "  (sin contenido LaTeX)" if not concept.get("contenido_latex") else ""
            st.write(
                f"{i}. {concept.get('tipo', 'tipo')}: "
                f"{concept.get('titulo') or concept.get('id')}{missing}"
            )

    if st.button("Generar documento modular", type="primary"):
        if not selected_concepts:
            st.error("No hay conceptos seleccionados.")
            return

        exporter = ExportadorLatex()
        result = exporter.exportar_documento_unificado(
            source=source,
            conceptos=selected_concepts,
            salida=output_dir,
            titulo=source,
            agrupar_por_tipo=group_by_type,
            respetar_orden_manual=strict_order,
            compilar_pdf=compile_pdf,
            sobrescribir=overwrite,
        )

        for warning in result.warnings:
            st.warning(warning)
        for error in result.errors:
            st.error(error)

        if result.success:
            st.success("Documento generado correctamente.")
        else:
            st.warning("El documento .tex fue generado, pero la exportacion no termino completamente.")

        st.write(f"Master .tex: `{result.master_tex_path}`")
        st.write(f"Concepts dir: `{result.concepts_dir}`")
        if result.pdf_path:
            st.write(f"PDF: `{result.pdf_path}`")
        if result.latex_log_path:
            st.write(f"LaTeX log: `{result.latex_log_path}`")
        if result.probable_error_file:
            st.warning(f"Archivo probable con error: {result.probable_error_file}")
        if result.log_tail:
            with st.expander("Ultimas lineas del log"):
                st.code(result.log_tail)

        if result.master_tex_path.exists():
            st.download_button(
                "Descargar master .tex",
                data=result.master_tex_path.read_text(encoding="utf-8"),
                file_name=result.master_tex_path.name,
                mime="text/plain",
            )
        if result.pdf_path and Path(result.pdf_path).exists():
            st.download_button(
                "Descargar PDF",
                data=Path(result.pdf_path).read_bytes(),
                file_name=Path(result.pdf_path).name,
                mime="application/pdf",
            )

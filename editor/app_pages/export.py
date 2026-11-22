"""Export; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from exporters_latex.exportadorlatex import ExportadorLatex
from exporters_latex.latex_validation import validate_latex_fragment
from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


def render(context):
    """Render only the selected page using its explicit application context."""
    current_database_label = context.current_database_label
    db = context.db
    st.title("📤 Export Concepts")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Exporting from: **{current_database_label}**")

    st.subheader("📄 LaTeX/PDF Export")
    st.info("Para construir un unico PDF modular con varios conceptos, usa la pagina 📄 Document Builder.")

    # Export options
    col1, col2 = st.columns(2)

    with col1:
        export_source = st.selectbox("Select Source", [""] + list(db.concepts.distinct("source")))
        export_type = st.selectbox("Export Type", ["All", "definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"])

    with col2:
        export_format = st.selectbox("Export Format", ["PDF", "LaTeX"])
        output_dir = st.text_input(
            "Output Directory",
            value=str(get_exports_dir(configured=resolve_config().export_directory) / "concepts"),
        )

    val_exp_col1, val_exp_col2, val_exp_col3 = st.columns(3)
    with val_exp_col1:
        validate_latex_before_export = st.checkbox(
            "Validar LaTeX antes de exportar",
            value=True,
            key="export_validate_latex_before_export",
        )
    with val_exp_col2:
        apply_safe_fixes_export = st.checkbox(
            "Aplicar fixes seguros solo al export",
            value=False,
            key="export_apply_safe_fixes",
        )
    with val_exp_col3:
        export_even_with_errors = st.checkbox(
            "Exportar aunque haya errores",
            value=False,
            key="export_even_with_errors",
        )

    if st.button("📤 Export", type="primary"):
        if export_source:
            try:
                exportador = ExportadorLatex()
                resolved_output_dir = validate_mutable_path(resolve_home_path(output_dir))

                # Build query
                query = {"source": export_source}
                if export_type != "All":
                    query["tipo"] = export_type

                concepts = list(db.concepts.find(query))

                if concepts:
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    for i, concept in enumerate(concepts):
                        status_text.text(f"Exporting {concept['id']}...")

                        latex_doc = db.latex_documents.find_one({"id": concept['id'], "source": export_source})
                        if latex_doc:
                            contenido_latex = latex_doc['contenido_latex']
                            if validate_latex_before_export:
                                validation = validate_latex_fragment(
                                    contenido_latex,
                                    concept=concept,
                                    apply_fixes=apply_safe_fixes_export,
                                )
                                if validation.status == "error" and not export_even_with_errors:
                                    st.error(
                                        f"Skipping {concept['id']} due to LaTeX errors. "
                                        "Enable 'Exportar aunque haya errores' to force export."
                                    )
                                    if validation.unknown_commands:
                                        st.write(validation.unknown_commands)
                                    if validation.log_excerpt:
                                        with st.expander(f"LaTeX log: {concept['id']}"):
                                            st.code(validation.log_excerpt)
                                    progress_bar.progress((i + 1) / len(concepts))
                                    continue
                                if validation.status == "warning":
                                    st.warning(f"LaTeX warnings for {concept['id']}")
                                if apply_safe_fixes_export and validation.safe_fixes:
                                    contenido_latex = validation.corrected_latex_preview
                                    st.warning(
                                        f"Applied safe fixes only to exported file for {concept['id']}; "
                                        "MongoDB was not modified."
                                    )
                            exportador.exportar_concepto(
                                concept,
                                contenido_latex,
                                salida=str(resolved_output_dir),
                            )

                        progress_bar.progress((i + 1) / len(concepts))

                    status_text.text("✅ Export completed!")
                    st.success(f"✅ Exported {len(concepts)} concepts to {resolved_output_dir}")

                    # Show exported files
                    if resolved_output_dir.exists():
                        st.subheader("📁 Exported Files")
                        files = list(
                            resolved_output_dir.glob(
                                "*.pdf" if export_format == "PDF" else "*.tex"
                            )
                        )
                        for file in files:
                            st.write(f"• {file.name}")

                else:
                    st.warning("⚠️ No concepts found for the selected source and type.")

            except Exception as e:
                st.error(f"❌ Export failed: {e}")
        else:
            st.error("❌ Please select a source to export.")

    st.markdown("---")

    # Bulk operations
    st.subheader("🔄 Bulk Operations")

    if st.button("🔄 Export All Sources"):
        try:
            sources = db.concepts.distinct("source")
            exportador = ExportadorLatex()

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, source in enumerate(sources):
                status_text.text(f"Exporting source: {source}")
                concepts_root = get_exports_dir(
                    configured=resolve_config().export_directory
                ) / "concepts"
                bulk_dir = validate_mutable_path(
                    concepts_root / source,
                    allowed_root=concepts_root,
                )
                exportador.exportar_todos_de_source(db.client, source, salida=str(bulk_dir))
                progress_bar.progress((i + 1) / len(sources))

            status_text.text("✅ Bulk export completed!")
            st.success(f"✅ Exported all {len(sources)} sources")

        except Exception as e:
            st.error(f"❌ Bulk export failed: {e}")

# Maintenance page

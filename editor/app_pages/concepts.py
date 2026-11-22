"""Concepts; extracted without import-time rendering."""

from __future__ import annotations

import streamlit as st

from editor.ui.concept_deletion import render_concept_deletion
from editor.ui.concept_media import _render_media_asset_preview
from editor.utils.media_assets import get_concept_media_assets
from exporters_latex.exportadorlatex import ExportadorLatex
from exporters_latex.latex_compile import latex_timeout_message
from exporters_latex.latex_compile import output_tail
from exporters_latex.latex_compile import run_latex_until_stable
from mathkb_config import LATEX_MAX_PASSES
from mathkb_config import PDF_COMPILE_TIMEOUT_SECONDS
from mathkb_config import PROJECT_ROOT
from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir
from mathmongo.paths import get_latex_runtime_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


def render(context):
    """Render only the selected page using its explicit application context."""
    current_database_label = context.current_database_label
    db = context.db
    st.title("📚 Browse Mathematical Concepts")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Browsing concepts in: **{current_database_label}**")

    # Filters
    st.subheader("🔍 Filters")
    col1, col2, col3 = st.columns(3)

    with col1:
        filter_type = st.selectbox("Type", ["All"] + list(db.concepts.distinct("tipo")))

    with col2:
        filter_source = st.selectbox("Source", ["All"] + list(db.concepts.distinct("source")))

    with col3:
        search_term = st.text_input("Search", placeholder="Search by title or ID...")

    # Build query
    query = {}
    if filter_type != "All":
        query["tipo"] = filter_type
    if filter_source != "All":
        query["source"] = filter_source
    if search_term:
        query["$or"] = [
            {"titulo": {"$regex": search_term, "$options": "i"}},
            {"id": {"$regex": search_term, "$options": "i"}}
        ]

    # Execute query
    concepts = list(db.concepts.find(query).sort("fecha_creacion", -1))

    st.subheader(f"📊 Results ({len(concepts)} concepts)")

    # =========================
    # Quarto Book Export (NEW)
    # =========================
    st.markdown("---")
    st.subheader("📘 Export to Quarto Book")

    # Build list of selectable IDs
    concept_id_map = {
        f"{c.get('titulo', c['id'])} [{c['tipo']}]": c["id"]
        for c in concepts
    }

    selected_labels = st.multiselect(
        "Select concepts to export",
        options=list(concept_id_map.keys()),
    )


    build_dir = st.text_input(
        "Quarto build directory",
        value=str(get_exports_dir(configured=resolve_config().export_directory) / "quarto"),
    )


    force_build = st.checkbox(
        "Overwrite existing build directory",
        value=False,
    )

    # MVP-B: LaTeX preflight (pdflatex compile check) before export
    preflight_compile = st.checkbox(
        "Preflight LaTeX (pdflatex compile check) before export",
        value=True,
        help="Compiles each selected concept with pdflatex + miestilo.sty. Blocks export on fatal errors.",
    )

    if st.button("🚀 Export selected concepts to Quarto"):
        if not selected_labels:
            st.warning("Please select at least one concept.")
        else:
            try:
                from pathlib import Path

                from exporters_quarto.quarto_exporter import QuartoBookExporter
                from scripts.export_quarto_book import _write_book_quarto_yml
                build_path = validate_mutable_path(resolve_home_path(build_dir))
                selected_ids = {concept_id_map[label] for label in selected_labels}
                selected_concepts = []
                for c in concepts:
                    if c["id"] in selected_ids:
                        latex_doc = db.latex_documents.find_one({"id": c["id"], "source": c["source"]})
                        c2 = dict(c)  # copia para no mutar la lista base
                        c2["contenido_latex"] = (latex_doc or {}).get("contenido_latex", "")
                        selected_concepts.append(c2)

                # --- MVP-B: LaTeX preflight (pdflatex compile check) ---
                if preflight_compile:
                    import shutil
                    import tempfile

                    if not shutil.which("pdflatex"):
                        raise RuntimeError(
                            "pdflatex not found. Install TeX Live (texlive-latex-base) or disable the preflight checkbox."
                        )

                    style_dirs = [
                        build_path / "styles",
                        PROJECT_ROOT / "quarto_book" / "styles",
                        PROJECT_ROOT / "templates_latex",
                    ]

                    def _find_style_file(name: str) -> Path:
                        for style_dir in style_dirs:
                            candidate = style_dir / name
                            if candidate.exists():
                                return candidate
                        searched = ", ".join(str(path) for path in style_dirs)
                        raise FileNotFoundError(f"{name} not found in: {searched}")

                    miestilo_src = _find_style_file("miestilo.sty")
                    coloredtheorem_src = _find_style_file("coloredtheorem.sty")


                    failures: list[tuple[str, str, str]] = []
                    progress = st.progress(0, text="Preflight LaTeX: compiling selected concepts...")
                    total = max(1, len(selected_concepts))

                    for idx, c in enumerate(selected_concepts, start=1):
                        latex_body = (c.get("contenido_latex") or "").strip()
                        # Empty LaTeX content is treated as OK (non-blocking)
                        if not latex_body:
                            progress.progress(int(idx * 100 / total))
                            continue

                        latex_runtime = validate_mutable_path(get_latex_runtime_dir())
                        latex_runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
                        with tempfile.TemporaryDirectory(prefix="mkb_preflight_", dir=latex_runtime) as td:
                            td_path = Path(td)
                            shutil.copy2(miestilo_src, td_path / "miestilo.sty")
                            (td_path / "styles").mkdir(parents=True, exist_ok=True)
                            shutil.copy2(coloredtheorem_src, td_path / "styles" / "coloredtheorem.sty")

                            tex = (
                                "\\documentclass{article}\n"
                                "\\usepackage{miestilo}\n"
                                "\\begin{document}\n"
                                + latex_body
                                + "\n\\end{document}\n"
                            )
                            (td_path / "main.tex").write_text(tex, encoding="utf-8")


                            command = [
                                "pdflatex",
                                "-interaction=nonstopmode",
                                "-halt-on-error",
                                "-file-line-error",
                                "main.tex",
                            ]
                            key = f"{c.get('id')}@{c.get('source')}"
                            try:
                                compile_info = run_latex_until_stable(
                                    command,
                                    cwd=str(td_path),
                                    tex_file=td_path / "main.tex",
                                    pdf_path=td_path / "main.pdf",
                                    log_path=td_path / "main.log",
                                    timeout_seconds=PDF_COMPILE_TIMEOUT_SECONDS,
                                    max_passes=LATEX_MAX_PASSES,
                                )
                            except TimeoutError:
                                failures.append(
                                    (
                                        key,
                                        str(c.get("titulo") or ""),
                                        latex_timeout_message(
                                            td_path / "main.tex",
                                            command,
                                            PDF_COMPILE_TIMEOUT_SECONDS,
                                        ),
                                    )
                                )
                                progress.progress(int(idx * 100 / total))
                                continue

                            if compile_info["status"] == "failed":
                                tail = compile_info.get("log_excerpt") or output_tail(
                                    compile_info.get("stdout", ""),
                                    compile_info.get("stderr", ""),
                                    lines=80,
                                )
                                failures.append((key, str(c.get("titulo") or ""), tail))

                        progress.progress(int(idx * 100 / total))

                    progress.empty()
                    if failures:
                        st.error(
                            f"❌ LaTeX preflight failed for {len(failures)} concept(s). Export blocked."
                        )
                        for key, title, tail in failures:
                            with st.expander(f"Preflight error: {title or key}"):
                                st.code(tail)
                        st.stop()
                # --- end MVP-B ---

                template_dir = PROJECT_ROOT / "quarto_book"

                exporter = QuartoBookExporter(
                    template_dir=template_dir,
                    build_dir=build_path,
                    allowed_root=build_path.parent,
                )

                exporter.prepare_build(force=force_build)
                exporter.export_concepts(selected_concepts)

                _write_book_quarto_yml(build_path)

                st.success(f"Quarto book exported to: {build_path}")
                st.info("Next step: run `quarto render` inside that directory.")

            except Exception as e:
                st.error(f"Quarto export failed: {e}")
    if concepts:
        for concept in concepts:
            with st.expander(f"{concept.get('titulo', concept['id'])} ({concept['tipo']})"):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.write(f"**ID:** {concept['id']}")
                    st.write(f"**Source:** {concept['source']}")
                    st.write(f"**Categories:** {', '.join(concept.get('categorias', []))}")

                    if concept.get('comentario'):
                        st.write(f"**Comment:** {concept['comentario']}")

                    # Show LaTeX content
                    latex_doc = db.latex_documents.find_one({"id": concept['id'], "source": concept['source']})
                    if latex_doc:
                        st.subheader("LaTeX Content")
                        st.code(latex_doc['contenido_latex'], language="latex")
                    assets = get_concept_media_assets(db, concept["id"], concept["source"])
                    if assets:
                        st.subheader("Images")
                        for asset in assets:
                            _render_media_asset_preview(asset)

                with col2:
                    # Actions
                    if st.button("📤 Export PDF", key=f"export_{concept['id']}"):
                        try:
                            exportador = ExportadorLatex()
                            exportador.exportar_concepto(concept, latex_doc['contenido_latex'])
                            st.success("PDF exported successfully!")
                        except Exception as e:
                            st.error(f"Export failed: {e}")

                    if st.button("🔗 View Relations", key=f"relations_{concept['id']}"):
                        relations = db.get_relations(desde_id=concept['id'], desde_source=concept['source'])
                        if relations:
                            st.write("**Relations:**")
                            for rel in relations:
                                st.write(f"• {rel.tipo}: {rel.hasta_id}@{rel.hasta_source}")
                        else:
                            st.write("No relations found.")

                    render_concept_deletion(st, db.db, concept, scope='browse')
    else:
        st.info("No concepts found matching the criteria.")

# Manage Relations page

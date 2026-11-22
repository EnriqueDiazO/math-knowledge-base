"""Concept pdf; extracted without import-time rendering."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from editor.pdf_export import generar_pdf_desde_formulario
from editor.pdf_preview import PdfPreviewError
from editor.pdf_preview import generate_pdf_preview


def _concept_pdf_download_name(concept_data: dict) -> str:
    """Return a safe leaf filename without exposing an internal filesystem path."""
    concept_id = str(concept_data.get("id") or "concept")
    concept_type = str(concept_data.get("tipo") or "concept")
    safe_id = concept_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe_type = concept_type.replace("/", "_").replace("\\", "_").replace(":", "_")
    return f"{safe_id or 'concept'}_{safe_type or 'concept'}.pdf"


def _generate_concept_pdf_preview(
    namespace: str,
    concept_data: dict,
    *,
    context_identity: str,
    allowed_root: Path,
) -> None:
    """Generate, validate, and store one concept preview for internal rendering."""
    try:
        with st.spinner("🔄 Generando PDF..."):
            generate_pdf_preview(
                st.session_state,
                namespace,
                generator=lambda: generar_pdf_desde_formulario(concept_data),
                allowed_root=allowed_root,
                file_name=_concept_pdf_download_name(concept_data),
                context_identity=context_identity,
            )
        st.success("✅ PDF generado y disponible en la vista previa.")
    except PdfPreviewError as exc:
        st.error(f"❌ No se pudo preparar la vista previa PDF. {exc}")
    except Exception as exc:
        diagnostic = getattr(exc, "diagnostic", {})
        known_stages = {
            "Generar contenido LaTeX",
            "Preparar datos",
            "Escribir archivo TEX",
            "Analizar TEX con ChkTeX",
            "Ejecutar compilador LaTeX",
            "Verificar PDF generado",
            "Entregar PDF",
        }
        stage = diagnostic.get("stage") if isinstance(diagnostic, dict) else None
        safe_stage = stage if stage in known_stages else "Generar PDF"
        st.error(
            "❌ No se pudo generar el PDF. "
            f"Etapa: {safe_stage}. Revisa el contenido LaTeX y vuelve a intentarlo."
        )

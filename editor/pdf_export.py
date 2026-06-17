#!/usr/bin/env python3
"""
PDF Export Module for Math Knowledge Base
Generates PDF files from mathematical concepts using LaTeX compilation.
"""

import os
import shutil
import tempfile
import unicodedata
import webbrowser
from pathlib import Path
from typing import Dict, Optional
import streamlit as st

from exporters_latex.latex_compile import latex_failure_message
from exporters_latex.latex_compile import latex_warning_message
from exporters_latex.latex_compile import run_latex_until_stable
from editor.utils.media_assets import copy_media_tree_for_latex
from mathkb_config import LATEX_MAX_PASSES
from mathkb_config import PDF_COMPILE_TIMEOUT_SECONDS

# Valores constantes
PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPORTED_NOTES_DIR = PROJECT_ROOT / "exported_notes"
EXPORTED_NOTES_BUILD_DIR = EXPORTED_NOTES_DIR / "_build"
TEMPLATES_LATEX_DIR = PROJECT_ROOT / "templates_latex"

EXPORTED_NOTES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTED_NOTES_BUILD_DIR.mkdir(parents=True, exist_ok=True)

def generar_pdf_concepto(concepto: Dict, output_path: Optional[str] = None) -> str:
    """
    Generate a PDF file from a mathematical concept using the same style as ExportadorLatex.
    
    Args:
        concepto: Dictionary containing concept data (id, titulo, contenido_latex, etc.)
        output_path: Optional path for the output PDF. If None, uses a temporary file.
    
    Returns:
        Path to the generated PDF file.
    
    Raises:
        Exception: If LaTeX compilation fails.
    """
    
    with tempfile.TemporaryDirectory(prefix="mathkb_concept_pdf_") as temp_dir:
        temp_path = Path(temp_dir)

        # Copy style files (same as ExportadorLatex)
        _copiar_archivos_estilo(temp_path)
        copy_media_tree_for_latex(temp_path)
        
        # Generate LaTeX content
        latex_content = _generar_latex_content(concepto)
        
        # Write LaTeX file
        tex_file = temp_path / f"{concepto['id']}.tex"
        with open(tex_file, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        # Compile LaTeX to PDF. Each pass has its own timeout so references and
        # aux files can settle without giving a single runaway command forever.
        try:
            command = [
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory",
                str(temp_path),
                str(tex_file),
            ]
            pdf_file = temp_path / f"{concepto['id']}.pdf"
            compile_info = run_latex_until_stable(
                command,
                cwd=temp_path,
                tex_file=tex_file,
                pdf_path=pdf_file,
                log_path=tex_file.with_suffix(".log"),
                timeout_seconds=PDF_COMPILE_TIMEOUT_SECONDS,
                max_passes=LATEX_MAX_PASSES,
            )

            if compile_info["status"] == "failed":
                result = compile_info.get("result")
                raise RuntimeError(
                    latex_failure_message(
                        tex_file,
                        command,
                        compile_info.get("returncode"),
                        log_excerpt=compile_info.get("log_excerpt", ""),
                        stdout=getattr(result, "stdout", "") if result else "",
                        stderr=getattr(result, "stderr", "") if result else "",
                    )
                )
            if compile_info["status"] == "success_with_warnings":
                print(latex_warning_message(compile_info))
            else:
                print(
                    "✅ PDF generated successfully "
                    f"(return code: {compile_info.get('returncode')}, passes: {compile_info.get('passes')})"
                )

            if not pdf_file.exists():
                result = compile_info.get("result")
                raise RuntimeError(
                    latex_failure_message(
                        tex_file,
                        command,
                        compile_info.get("returncode"),
                        log_excerpt=compile_info.get("log_excerpt", ""),
                        stdout=result.stdout if result else "",
                        stderr=result.stderr if result else "",
                    )
                )
            
            # Copy to final destination
            if output_path is None:
                # Create a dedicated directory for generated PDFs
                pdf_dir = Path(os.path.expanduser("~/math_knowledge_pdfs"))
                pdf_dir.mkdir(exist_ok=True)
                
                # Ensure directory has correct permissions
                os.chmod(pdf_dir, 0o755)  # rwxr-xr-x
                
                # Use a descriptive filename
                safe_id = concepto['id'].replace('/', '_').replace('\\', '_').replace(':', '_')
                final_pdf = pdf_dir / f"{safe_id}_{concepto['tipo']}.pdf"
            else:
                final_pdf = Path(output_path)
            
            # Copy the PDF to the final location
            shutil.copy2(pdf_file, final_pdf)
            
            # Set readable permissions for the PDF file
            os.chmod(final_pdf, 0o644)  # rw-r--r--
            
            return str(final_pdf)
            
        except (TimeoutError, FileNotFoundError, PermissionError, OSError) as exc:
            raise RuntimeError(str(exc)) from exc




def _latex_escape_text(s: str) -> str:
    """Best-effort escape for LaTeX text fields (titles/metadata), not for LaTeX bodies."""
    if s is None:
        return ""
    # Keep this intentionally minimal; the body is trusted LaTeX authored by the user.
    return (
        s.replace("\\", r"\textbackslash{}")
         .replace("{", r"\{")
         .replace("}", r"\}")
    )


def _normalize_latex_unicode(latex: str) -> str:
    """Normalize combining accents so pdfLaTeX sees standard precomposed glyphs."""
    return unicodedata.normalize("NFC", latex or "")


def generar_tex_nota_latex(nota: Dict, template: str = "simple") -> str:
    """Generate a standalone LaTeX document for a diary note (latex_notes).

    Args:
        nota: Mongo document of latex_notes.
        template: "simple" (default) or "diario" (mdframed boxes inspired by diario.tex).
    """
    title = (nota.get("title") or "Nota").strip()
    fecha = (nota.get("date") or "").strip()
    project = (nota.get("project") or "").strip()
    context = (nota.get("context") or "").strip()
    tags = nota.get("tags") or []
    body = (nota.get("latex_body") or "").strip()

    # Common metadata block (optional)
    meta_lines = []
    if fecha:
        meta_lines.append(r"\textbf{Fecha:} " + _latex_escape_text(fecha) + r"\\")
    if project:
        meta_lines.append(r"\textbf{Proyecto:} " + _latex_escape_text(project) + r"\\")
    if context:
        meta_lines.append(r"\textbf{Contexto:} " + _latex_escape_text(context) + r"\\")
    if tags:
        meta_lines.append(r"\textbf{Tags:} " + _latex_escape_text(", ".join(tags)) + r"\\")

    # Template: "diario" (boxed / nicer layout)
    if template == "diario":
        latex_doc = r"""\documentclass[12pt,letterpaper]{notes}
\usepackage{graphicx}
\providecommand{\Inv}{\mathrm{Inv}}
\begin{document}

"""
        latex_doc += r"\notetitle{" + _latex_escape_text(title) + r"}" + "\n\n"

        if meta_lines:
            latex_doc += r"\begin{notemeta}" + "\n"
            latex_doc += "\n".join(meta_lines) + "\n"
            latex_doc += r"\end{notemeta}" + "\n\n"

        if body:
            pass
            #latex_doc += r"\begin{notebody}" + "\n"
            latex_doc += body + "\n"
            #latex_doc += r"\end{notebody}" + "\n\n"

        latex_doc += r"\end{document}" + "\n"
        return _normalize_latex_unicode(latex_doc)
    # Default: "simple" (uses existing style files)
    latex_doc = r"""\documentclass[12pt]{article}
\usepackage{miestilo}
\usepackage{coloredtheorem}
\usepackage{graphicx}
\providecommand{\Inv}{\mathrm{Inv}}
\begin{document}

"""
    latex_doc += r"\section*{" + _latex_escape_text(title) + r"}" + "\n\n"

    if meta_lines:
        latex_doc += r"\noindent\begin{flushleft}\small" + "\n"
        latex_doc += "\n".join(meta_lines) + "\n"
        latex_doc += r"\end{flushleft}\normalsize" + "\n\n"

    if body:
        latex_doc += body + "\n\n"

    latex_doc += r"\end{document}" + "\n"
    return _normalize_latex_unicode(latex_doc)


def generar_pdf_nota_latex_result(
    nota: Dict,
    output_path: Optional[str] = None,
    template: str = "diario",
) -> dict:
    """Generate a PDF from a diary note using pdflatex, reusing the concept export pipeline.

    Args:
        nota: Mongo document of latex_notes.
        output_path: Optional destination path.
        template: "simple" (default) or "diario".
    """
    # Compile into dedicated build directory to keep exported_notes/ clean
    temp_path = EXPORTED_NOTES_BUILD_DIR

    # Only copy style files for "simple"; the "diario" template is self-contained.
    if template == "simple":
        _copiar_archivos_estilo(temp_path)
    elif template == "diario":
        _copiar_archivos_estilo(temp_path)   # copia .sty base (miestilo, coloredtheorem, etc.)
        _copiar_archivos_notas(temp_path)    # copia notes.cls + notes.sty

    copy_media_tree_for_latex(temp_path)

    # Build LaTeX document
    latex_content = generar_tex_nota_latex(nota, template=template)

    # Build safe filename base
    raw_id = str(nota.get("_id") or nota.get("id") or "latex_note")
    safe_id = raw_id.replace("/", "_").replace("\\", "_").replace(":", "_")
    tex_file = temp_path / f"{safe_id}.tex"
    tex_file.write_text(latex_content, encoding="utf-8")

    # Compile
    command = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-output-directory",
        str(temp_path),
        str(tex_file),
    ]
    try:
        compile_info = run_latex_until_stable(
            command,
            cwd=temp_path,
            tex_file=tex_file,
            pdf_path=temp_path / f"{safe_id}.pdf",
            log_path=tex_file.with_suffix(".log"),
            timeout_seconds=PDF_COMPILE_TIMEOUT_SECONDS,
            max_passes=LATEX_MAX_PASSES,
        )
    except (TimeoutError, FileNotFoundError, PermissionError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc

    pdf_file = temp_path / f"{safe_id}.pdf"
    if compile_info["status"] == "failed":
        result = compile_info.get("result")
        raise RuntimeError(
            latex_failure_message(
                tex_file,
                command,
                compile_info.get("returncode"),
                log_excerpt=compile_info.get("log_excerpt", ""),
                stdout=getattr(result, "stdout", "") if result else "",
                stderr=getattr(result, "stderr", "") if result else "",
            )
        )

    # Copy to final destination
    if output_path is None:
        pdf_dir = EXPORTED_NOTES_DIR
        pdf_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(pdf_dir, 0o755)

        # Optional date prefix
        date_prefix = (nota.get("date") or "").replace("-", "")
        title = (nota.get("title") or "nota").strip().replace(" ", "_")
        title = "".join(ch for ch in title if ch.isalnum() or ch in ("_", "-", "."))
        suffix = f"{template}"  # distinguish outputs by template
        if date_prefix:
            final_pdf = pdf_dir / f"{date_prefix}_{title}_{safe_id}_{suffix}.pdf"
        else:
            final_pdf = pdf_dir / f"{title}_{safe_id}_{suffix}.pdf"
    else:
        final_pdf = Path(output_path)

    import shutil
    shutil.copy2(pdf_file, final_pdf)
    os.chmod(final_pdf, 0o644)
    compile_info["pdf_path"] = str(final_pdf)
    return compile_info


def generar_pdf_nota_latex(nota: Dict, output_path: Optional[str] = None, template: str = "diario") -> str:
    """Generate a PDF from a diary note and return only the final PDF path."""
    return generar_pdf_nota_latex_result(
        nota,
        output_path=output_path,
        template=template,
    )["pdf_path"]

def _generar_latex_content(concepto: Dict) -> str:
    """
    Generate LaTeX content for a mathematical concept using the same style as ExportadorLatex.
    
    Args:
        concepto: Dictionary containing concept data.
    
    Returns:
        Complete LaTeX document as string.
    """
    
    # Extract concept data
    concept_id = concepto.get('id', 'unknown')
    titulo = concepto.get('titulo', concept_id)
    contenido_latex = concepto.get('contenido_latex', '')
    source = concepto.get('source', '')
    
    # Build LaTeX document using the same style as ExportadorLatex
    latex_doc = r"""\documentclass[12pt]{article}
\usepackage{miestilo}
\usepackage{coloredtheorem}
\usepackage{graphicx}
\begin{document}

"""
    
    # --- título ---
    latex_doc += r"\section*{" + titulo + "}\n\n"
    
    # --- cuerpo principal ---
    if contenido_latex:
        latex_doc += contenido_latex + "\n\n"
    
    # --- comentario opcional ---
    comentario = concepto.get('comentario')
    if comentario:
        latex_doc += r"\section*{Comentario}" "\n" + comentario + "\n\n"
    
    # --- referencia bibliográfica opcional ---
    referencia = concepto.get('referencia')
    if referencia:
        latex_doc += r"\section*{Referencia}" "\n"
        linea1 = ", ".join(
            filter(None, (
                referencia.get("autor"),
                referencia.get("fuente"),
                f"({referencia.get('anio')})" if referencia.get("anio") else None,
            ))
        )
        latex_doc += linea1 + r"\\" "\n"
        
        linea2 = ", ".join(
            filter(None, (
                f"Tomo {referencia['tomo']}"       if referencia.get("tomo") else None,
                f"Ed. {referencia['edicion']}"    if referencia.get("edicion") else None,
                f"Cap. {referencia['capitulo']}"  if referencia.get("capitulo") else None,
                f"Sección {referencia['seccion']}"if referencia.get("seccion") else None,
                f"Pág. {referencia['paginas']}"   if referencia.get("paginas") else None,
                referencia.get("editorial"),
            ))
        )
        if linea2:
            latex_doc += linea2 + r"\\" "\n"
        if referencia.get("issbn"):
            latex_doc += f"ISSBN: {referencia['issbn']}\\\\\n"
        if referencia.get("doi"):
            latex_doc += f"DOI: {referencia['doi']}\\\\\n"
        if referencia.get("url"):
            latex_doc += r"\url{" + referencia["url"] + "}\\\\" "\n"
        latex_doc += "\n"
    
    # --- ID interno ---
    latex_doc += r"\textbf{ID del concepto:}~\verb|" + f"{concept_id}@{source}|" + "\n\n"
    
    latex_doc += r"\end{document}" "\n"
    
    return latex_doc


def _copiar_archivos_estilo(destino: Path) -> None:
    """
    Copy style files (miestilo.sty, coloredtheorem.sty) to the destination directory.
    Same as ExportadorLatex._copiar_plantillas method.
    """
    # Define style files to copy (same as ExportadorLatex)
    archivos_plantilla = ("miestilo.sty", "coloredtheorem.sty")
    
    # Templates directory (same as ExportadorLatex)
    templates_dir = Path(__file__).parent.parent / "templates_latex"
    
    for fname in archivos_plantilla:
        src = templates_dir / fname
        dst = destino / fname
        if not src.exists():
            print(f"⚠️  Plantilla no encontrada: {src}")
            continue
        if not dst.exists():
            import shutil
            shutil.copy2(src, dst)
            print(f"📄 Plantilla {fname} copiada a {destino}")


def _copiar_archivos_notas(destino: Path) -> None:
    """Copy notes.cls and notes.sty into the LaTeX build directory."""
    archivos = ("notes.cls", "notes.sty")
    templates_dir = Path(__file__).parent.parent / "templates_latex"
    import shutil

    for fname in archivos:
        src = templates_dir / fname
        dst = destino / fname
        if not src.exists():
            print(f"⚠️  Plantilla no encontrada: {src}")
            continue
        shutil.copy2(src, dst)
        print(f"📄 Plantilla {fname} copiada a {destino}")


def abrir_pdf_en_navegador(pdf_path: str) -> bool:
    """
    Open a PDF file in the default browser.
    
    Args:
        pdf_path: Path to the PDF file.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Convert to file URL
        pdf_url = f"file://{os.path.abspath(pdf_path)}"
        
        # Open in browser
        webbrowser.open_new_tab(pdf_url)
        return True
        
    except Exception as e:
        st.error(f"❌ Error opening PDF: {e}")
        return False


def generar_y_abrir_pdf_desde_formulario(concept_data: Dict) -> bool:
    """
    Generate PDF from form data and open it in browser.
    
    Args:
        concept_data: Dictionary containing concept data from form.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        with st.spinner("🔄 Generando PDF..."):
            # Generate PDF
            pdf_path = generar_pdf_concepto(concept_data)
            
            # Open in browser
            if abrir_pdf_en_navegador(pdf_path):
                st.success(f"✅ PDF generado y abierto: {pdf_path}")
                return True
            else:
                st.error("❌ Error al abrir el PDF en el navegador")
                return False
                
    except Exception as e:
        st.error(f"❌ Error generando PDF: {e}")
        return False

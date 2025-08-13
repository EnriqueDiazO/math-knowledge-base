#!/usr/bin/env python3
"""
PDF Export Module for Math Knowledge Base
Generates PDF files from mathematical concepts using LaTeX compilation.
"""

import os
import tempfile
import subprocess
import webbrowser
from pathlib import Path
from typing import Dict, Optional
import streamlit as st


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
    
    # Create a persistent temporary directory for LaTeX files
    temp_dir = Path(__file__).resolve().parent.parent / "templates_latex"
    temp_path = Path(temp_dir)
    
    try:
        # Copy style files (same as ExportadorLatex)
        _copiar_archivos_estilo(temp_path)
        
        # Generate LaTeX content
        latex_content = _generar_latex_content(concepto)
        
        # Write LaTeX file
        tex_file = temp_path / f"{concepto['id']}.tex"
        with open(tex_file, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        # Compile LaTeX to PDF
        try:
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', '-output-directory', str(temp_path), str(tex_file)],
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            # Check if PDF was actually generated despite warnings
            pdf_file = temp_path / f"{concepto['id']}.pdf"
            
            if not pdf_file.exists():
                print(f"❌ LaTeX compilation failed:")
                print(f"Return code: {result.returncode}")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                st.error(f"❌ LaTeX compilation failed:\n{result.stderr}")
                raise Exception(f"LaTeX compilation failed: {result.stderr}")
            else:
                print(f"✅ PDF generated successfully (return code: {result.returncode})")
                if result.stderr:
                    print(f"⚠️ Warnings: {result.stderr}")
            
            # Find the generated PDF
            pdf_file = temp_path / f"{concepto['id']}.pdf"
            
            if not pdf_file.exists():
                raise Exception("PDF file was not generated")
            
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
            import shutil
            shutil.copy2(pdf_file, final_pdf)
            
            # Set readable permissions for the PDF file
            os.chmod(final_pdf, 0o644)  # rw-r--r--
            
            return str(final_pdf)
            
        except subprocess.TimeoutExpired:
            raise Exception("LaTeX compilation timed out")
        except FileNotFoundError:
            raise Exception("pdflatex not found. Please install LaTeX distribution.")
    
    finally:
        # Clean up temporary directory (but keep the final PDF)
        import shutil
        try:
            #shutil.rmtree(temp_dir)
            #Extensiones a eliminar
            extensiones = [".tex",".out",".log",".aux",".pdf"]
            # Borrar los archivos de las extensiones en temp_dir
            for archivo in temp_dir.glob("*"):
                if archivo.suffix in extensiones and archivo.is_file():
                    archivo.unlink()
            print("Creación completa del PDF")

        except Exception as e:
            print(f"⚠️ Warning: Could not clean up temporary directory {temp_dir}: {e}")


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
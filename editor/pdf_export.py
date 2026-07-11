#!/usr/bin/env python3
"""
PDF Export Module for Math Knowledge Base
Generates PDF files from mathematical concepts using LaTeX compilation.
"""

import os
import hashlib
import re
import shutil
import tempfile
import traceback
import unicodedata
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional
import streamlit as st

from exporters_latex.latex_compile import latex_failure_message
from exporters_latex.latex_compile import latex_warning_message
from exporters_latex.latex_compile import run_latex_until_stable
from exporters_latex.latex_validation import run_chktex_analysis
from editor.utils.media_assets import copy_media_tree_for_latex
from editor.pdf_preview import open_local_pdf
from mathkb_config import LATEX_MAX_PASSES
from mathkb_config import PDF_COMPILE_TIMEOUT_SECONDS

# Valores constantes
PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXPORTED_NOTES_DIR = PROJECT_ROOT / "exported_notes"
EXPORTED_NOTES_BUILD_DIR = EXPORTED_NOTES_DIR / "_build"
TEMPLATES_LATEX_DIR = PROJECT_ROOT / "templates_latex"

EXPORTED_NOTES_DIR.mkdir(parents=True, exist_ok=True)
EXPORTED_NOTES_BUILD_DIR.mkdir(parents=True, exist_ok=True)


class PdfExportError(RuntimeError):
    """Error de exportación con diagnóstico estructurado para Streamlit."""

    def __init__(self, message: str, diagnostic: Optional[dict] = None):
        super().__init__(message)
        self.diagnostic = diagnostic or {}


def _tail_text(value: object, lines: int = 80, chars: int = 12000) -> str:
    text = str(value or "")
    if not text:
        return ""
    tail = "\n".join(text.splitlines()[-lines:])
    if len(tail) > chars:
        return tail[-chars:]
    return tail


def _first_latex_error_line(log_text: str) -> str:
    for line in (log_text or "").splitlines():
        clean = line.strip()
        if (
            clean.startswith("!")
            or "Emergency stop" in clean
            or "Fatal" in clean
            or "Error" in clean
        ):
            return clean
    return ""


def _latex_reported_line(log_text: str) -> int | None:
    lines = (log_text or "").splitlines()
    error_index = None
    for index, line in enumerate(lines):
        clean = line.strip()
        if clean.startswith("!") or "Emergency stop" in clean or "Fatal" in clean:
            error_index = index
            break

    search_ranges = []
    if error_index is not None:
        search_ranges.append(lines[error_index:])
    search_ranges.append(lines)

    for candidate_lines in search_ranges:
        for line in candidate_lines:
            match = re.match(r"l\.(\d+)\s+", line)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    return None
    return None


def _tex_context_for_line(tex_file: object, line_number: int | None, radius: int = 3) -> str:
    if not tex_file or not line_number:
        return ""
    path = Path(str(tex_file))
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return ""
    if line_number < 1 or line_number > len(lines):
        return ""
    start = max(1, line_number - radius)
    end = min(len(lines), line_number + radius)
    rendered = []
    for number in range(start, end + 1):
        marker = ">" if number == line_number else " "
        rendered.append(f"{marker} {number:4d} | {lines[number - 1]}")
    return "\n".join(rendered)


def _unicode_decode_diagnostic(exc: UnicodeDecodeError) -> dict:
    raw = exc.object if isinstance(exc.object, (bytes, bytearray)) else b""
    problem = bytes(raw[exc.start:exc.end]) if raw else b""
    left = max(0, exc.start - 24)
    right = min(len(raw), exc.end + 24) if raw else exc.end
    context = bytes(raw[left:right]) if raw else b""
    return {
        "encoding_attempted": exc.encoding,
        "decode_start": exc.start,
        "decode_end": exc.end,
        "decode_reason": exc.reason,
        "problematic_bytes": " ".join(f"0x{byte:02x}" for byte in problem),
        "byte_context_hex": " ".join(f"0x{byte:02x}" for byte in context),
    }


def _probable_cause(diagnostic: dict) -> str:
    if diagnostic.get("exception_type") == "UnicodeDecodeError" or diagnostic.get("decode_diagnostics"):
        return "Se encontró salida diagnóstica que no pudo interpretarse como UTF-8."
    if diagnostic.get("exception_type") == "FileNotFoundError":
        return "No se pudo iniciar el compilador o falta un archivo requerido."
    if diagnostic.get("stage") == "Verificar PDF generado":
        return "El proceso terminó, pero no se encontró el PDF esperado."
    if diagnostic.get("fatal_errors"):
        return "LaTeX reportó un error fatal durante la compilación."
    if diagnostic.get("returncode") not in (None, 0):
        return "El compilador LaTeX terminó con código de error."
    return "Ocurrió una excepción durante el flujo de exportación."


def _diagnostic_from_exception(
    exc: BaseException,
    *,
    stage: str,
    operation: str,
    **context: object,
) -> dict:
    diagnostic = {
        "stage": stage,
        "operation": operation,
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }
    for key, value in context.items():
        if value not in (None, "", [], {}):
            diagnostic[key] = value
    if isinstance(exc, UnicodeDecodeError):
        diagnostic.update(_unicode_decode_diagnostic(exc))
    diagnostic["probable_cause"] = _probable_cause(diagnostic)
    return diagnostic


def _decode_diagnostics_from_compile_info(compile_info: dict) -> list[dict]:
    diagnostics = []
    for key, label in (
        ("stdout_decode", "stdout"),
        ("stderr_decode", "stderr"),
        ("log_decode", "log"),
    ):
        item = compile_info.get(key)
        if isinstance(item, dict) and item.get("had_decode_error"):
            enriched = dict(item)
            enriched["stream"] = label
            diagnostics.append(enriched)
    return diagnostics


def _diagnostic_from_compile_info(
    compile_info: dict,
    *,
    stage: str,
    operation: str,
    message: str,
    **context: object,
) -> dict:
    log_text = compile_info.get("log_text") or ""
    latex_line = _latex_reported_line(log_text)
    tex_context = _tex_context_for_line(compile_info.get("tex_file"), latex_line)
    diagnostic = {
        "stage": stage,
        "operation": operation,
        "exception_type": "LaTeXCompilationError",
        "exception_message": message,
        "command": compile_info.get("command"),
        "cwd": compile_info.get("cwd"),
        "returncode": compile_info.get("returncode"),
        "tex_file": compile_info.get("tex_file"),
        "pdf_path": compile_info.get("pdf_path"),
        "log_path": compile_info.get("log_path"),
        "stdout": _tail_text(compile_info.get("stdout"), lines=80),
        "stderr": _tail_text(compile_info.get("stderr"), lines=80),
        "log_excerpt": compile_info.get("log_excerpt") or _tail_text(log_text, lines=80),
        "first_latex_error": _first_latex_error_line(log_text or compile_info.get("log_excerpt", "")),
        "latex_error_line": latex_line,
        "latex_error_context": tex_context,
        "warnings": compile_info.get("warnings") or [],
        "fatal_errors": compile_info.get("fatal_errors") or [],
        "undefined_references": compile_info.get("undefined_references") or [],
        "decode_diagnostics": _decode_diagnostics_from_compile_info(compile_info),
    }
    for key, value in context.items():
        if value not in (None, "", [], {}):
            diagnostic[key] = value
    diagnostic["probable_cause"] = _probable_cause(diagnostic)
    return diagnostic


def _raise_pdf_export_error(
    message: str,
    *,
    stage: str,
    operation: str,
    exc: BaseException,
    **context: object,
) -> None:
    raise PdfExportError(
        message,
        _diagnostic_from_exception(
            exc,
            stage=stage,
            operation=operation,
            **context,
        ),
    ) from exc


def render_pdf_export_error(
    error: BaseException,
    *,
    main_message: str = "❌ No se pudo generar el PDF.",
    fallback_stage: str = "Exportación PDF",
    fallback_operation: str = "Exportación",
) -> None:
    diagnostic = getattr(error, "diagnostic", None)
    if not isinstance(diagnostic, dict):
        diagnostic = _diagnostic_from_exception(
            error,
            stage=fallback_stage,
            operation=fallback_operation,
        )

    stage = diagnostic.get("stage") or fallback_stage
    cause = diagnostic.get("probable_cause") or _probable_cause(diagnostic)
    if diagnostic.get("chktex_result"):
        render_chktex_result(diagnostic.get("chktex_result"), expanded=False)
    st.error(f"{main_message}\n\n**Etapa:** {stage}\n\n**Causa probable:** {cause}")

    with st.expander("🔍 Detalles técnicos", expanded=False):
        fields = [
            ("Tipo de excepción", "exception_type"),
            ("Mensaje original", "exception_message"),
            ("Etapa", "stage"),
            ("Operación", "operation"),
            ("Archivo", "file"),
            ("Archivo TEX", "tex_file"),
            ("Archivo LOG", "log_path"),
            ("PDF esperado", "pdf_path"),
            ("Directorio temporal", "temp_dir"),
            ("Comando ejecutado", "command"),
            ("CWD", "cwd"),
            ("Código de retorno", "returncode"),
            ("Encoding intentado", "encoding_attempted"),
            ("Posición inicial", "decode_start"),
            ("Posición final", "decode_end"),
            ("Bytes problemáticos", "problematic_bytes"),
            ("Razón", "decode_reason"),
            ("Contexto de bytes", "byte_context_hex"),
            ("Primera línea LaTeX relevante", "first_latex_error"),
            ("Línea reportada por LaTeX", "latex_error_line"),
        ]
        for label, key in fields:
            value = diagnostic.get(key)
            if value not in (None, "", [], {}):
                st.write(f"**{label}:** `{value}`")

        decode_diagnostics = diagnostic.get("decode_diagnostics") or []
        if decode_diagnostics:
            st.write("**Problemas de encoding detectados:**")
            for item in decode_diagnostics:
                st.json(item)

        for label, key in (
            ("stdout", "stdout"),
            ("stderr", "stderr"),
            ("Últimas líneas del log", "log_excerpt"),
            ("Contexto de la línea reportada por LaTeX", "latex_error_context"),
            ("Errores fatales detectados", "fatal_errors"),
            ("Advertencias", "warnings"),
            ("Referencias indefinidas", "undefined_references"),
            ("Traceback", "traceback"),
        ):
            value = diagnostic.get(key)
            if value not in (None, "", [], {}):
                st.write(f"**{label}:**")
                if isinstance(value, list):
                    st.code("\n".join(str(item) for item in value), language="text")
                else:
                    st.code(str(value), language="text")


def _chktex_result_dict(result: object) -> dict:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    return asdict(result)


def render_chktex_result(result: object, *, expanded: bool = False) -> None:
    data = _chktex_result_dict(result)
    if not data:
        return

    if not data.get("tool_available"):
        st.warning(
            "⚠️ ChkTeX no está disponible.\n\n"
            "El análisis estático de LaTeX requiere ChkTeX.\n\n"
            "En Ubuntu/Debian puede instalarse con:\n\n"
            "```bash\nsudo apt install chktex\n```"
        )
        return

    issues = data.get("issues") or []
    if data.get("timed_out"):
        st.warning(f"⚠️ ChkTeX excedió el tiempo límite. {data.get('error') or ''}")
    elif data.get("error"):
        st.warning(f"⚠️ ChkTeX terminó con observaciones técnicas: {data.get('error')}")
    elif issues:
        st.warning(f"⚠️ ChkTeX encontró {len(issues)} posibles problemas.")
    else:
        st.success("✅ ChkTeX no encontró problemas.")

    st.caption(
        " · ".join(
            part
            for part in (
                "Herramienta: ChkTeX",
                data.get("version") or "",
                f"Archivo analizado: {data.get('tex_path')}" if data.get("tex_path") else "",
            )
            if part
        )
    )

    if not issues:
        return

    with st.expander("🔍 Análisis estático — ChkTeX", expanded=expanded):
        st.write(f"**Comando:** `{data.get('command')}`")
        if data.get("return_code") is not None:
            st.write(f"**Código de retorno:** `{data.get('return_code')}`")
        if data.get("duration") is not None:
            st.write(f"**Duración:** `{data.get('duration'):.3f}s`")

        for index, issue in enumerate(issues, start=1):
            warning = issue.get("warning_number") or "?"
            line = issue.get("line")
            column = issue.get("column")
            note_line = issue.get("note_line")
            st.markdown(f"**Problema {index} — Warning {warning}**")
            location = []
            if line:
                location.append(f"Línea del TEX generado: {line}")
            if column:
                location.append(f"columna {column}")
            if note_line:
                location.append(f"línea aproximada en la nota: {note_line}")
            if location:
                st.write(" · ".join(location))
            st.write("**Mensaje:**")
            st.write(issue.get("message") or "")

            context = issue.get("context") or []
            if context:
                rendered_context = []
                for row in context:
                    marker = ">" if row.get("is_target") else " "
                    rendered_context.append(
                        f"{marker} {int(row.get('line') or 0):4d} | {row.get('text') or ''}"
                    )
                st.code("\n".join(rendered_context), language="latex")

        decode_diagnostics = data.get("decode_diagnostics") or []
        if decode_diagnostics:
            st.write("**Diagnóstico de encoding de ChkTeX:**")
            for item in decode_diagnostics:
                st.json(item)


def _safe_filename_part(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    text = (
        text.replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )
    safe = "".join(ch for ch in text if ch.isalnum() or ch in ("_", "-", "."))
    return safe or fallback


def _safe_concept_id_part(value: object, fallback: str = "concept") -> str:
    text = str(value or "").strip()
    safe = text.replace("/", "_").replace("\\", "_").replace(":", "_")
    return safe or fallback


def _copy_pdf_to_final_path(pdf_file: Path, final_pdf: Path) -> None:
    final_pdf.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_file, final_pdf)
    os.chmod(final_pdf, 0o644)


def _generar_pdf_desde_latex_temporal(
    *,
    latex_content: str,
    safe_id: str,
    temp_prefix: str,
    final_pdf: Path,
    include_note_styles: bool = False,
    source_map: Optional[dict] = None,
) -> dict:
    temp_path = Path(tempfile.mkdtemp(prefix=temp_prefix))
    cleanup_temp = False
    try:
        try:
            _copiar_archivos_estilo(temp_path)
            if include_note_styles:
                _copiar_archivos_notas(temp_path)
            copy_media_tree_for_latex(temp_path)
        except Exception as exc:
            _raise_pdf_export_error(
                "No se pudo preparar el directorio temporal de exportación.",
                stage="Preparar datos",
                operation="Copiar estilos y media",
                exc=exc,
                temp_dir=str(temp_path),
            )

        tex_file = temp_path / f"{safe_id}.tex"
        try:
            tex_file.write_text(latex_content, encoding="utf-8")
        except Exception as exc:
            _raise_pdf_export_error(
                "No se pudo escribir el archivo TEX.",
                stage="Escribir archivo TEX",
                operation="Escritura de archivo de texto",
                exc=exc,
                file=str(tex_file),
                tex_file=str(tex_file),
                encoding_attempted="utf-8",
                temp_dir=str(temp_path),
            )

        chktex_result = None
        try:
            chktex_result = asdict(
                run_chktex_analysis(
                    tex_file,
                    latex_source=latex_content,
                    note_body_start_line=(source_map or {}).get("body_start_line"),
                )
            )
        except Exception as exc:
            chktex_result = {
                "tool_available": True,
                "issues": [],
                "error": str(exc),
                "tex_path": str(tex_file),
                "stage": "Analizar TEX con ChkTeX",
            }

        command = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-output-directory",
            str(temp_path),
            str(tex_file),
        ]
        pdf_file = temp_path / f"{safe_id}.pdf"
        log_file = tex_file.with_suffix(".log")
        try:
            compile_info = run_latex_until_stable(
                command,
                cwd=temp_path,
                tex_file=tex_file,
                pdf_path=pdf_file,
                log_path=log_file,
                timeout_seconds=PDF_COMPILE_TIMEOUT_SECONDS,
                max_passes=LATEX_MAX_PASSES,
            )
        except Exception as exc:
            _raise_pdf_export_error(
                "No se pudo ejecutar el compilador LaTeX.",
                stage="Ejecutar compilador LaTeX",
                operation="subprocess pdflatex",
                exc=exc,
                command=" ".join(command),
                cwd=str(temp_path),
                tex_file=str(tex_file),
                log_path=str(log_file),
                pdf_path=str(pdf_file),
                temp_dir=str(temp_path),
                chktex_result=chktex_result,
            )

        if compile_info["status"] == "failed":
            result = compile_info.get("result")
            message = latex_failure_message(
                tex_file,
                command,
                compile_info.get("returncode"),
                log_excerpt=compile_info.get("log_excerpt", ""),
                stdout=getattr(result, "stdout", "") if result else "",
                stderr=getattr(result, "stderr", "") if result else "",
            )
            raise PdfExportError(
                message,
                _diagnostic_from_compile_info(
                    compile_info,
                    stage="Ejecutar compilador LaTeX",
                    operation="Compilación LaTeX",
                    message=message,
                    temp_dir=str(temp_path),
                    chktex_result=chktex_result,
                ),
            )

        if not pdf_file.exists():
            message = "El proceso terminó, pero no se encontró el PDF esperado."
            raise PdfExportError(
                message,
                _diagnostic_from_compile_info(
                    compile_info,
                    stage="Verificar PDF generado",
                    operation="Comprobación de archivo PDF",
                    message=message,
                    temp_dir=str(temp_path),
                    expected_pdf=str(pdf_file),
                    chktex_result=chktex_result,
                ),
            )

        try:
            _copy_pdf_to_final_path(pdf_file, final_pdf)
        except Exception as exc:
            _raise_pdf_export_error(
                "No se pudo copiar el PDF al destino final.",
                stage="Entregar PDF",
                operation="Copiar PDF final",
                exc=exc,
                file=str(final_pdf),
                pdf_path=str(pdf_file),
                temp_dir=str(temp_path),
            )

        compile_info["pdf_path"] = str(final_pdf)
        compile_info["chktex"] = chktex_result
        cleanup_temp = True
        return compile_info
    finally:
        if cleanup_temp:
            shutil.rmtree(temp_path, ignore_errors=True)


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
    try:
        latex_content = _generar_latex_content(concepto)
        safe_id = _safe_concept_id_part(concepto.get("id"))
    except Exception as exc:
        _raise_pdf_export_error(
            "No se pudo generar el contenido LaTeX del concepto.",
            stage="Generar contenido LaTeX",
            operation="Construcción de documento LaTeX",
            exc=exc,
        )

    if output_path is None:
        pdf_dir = Path(os.path.expanduser("~/math_knowledge_pdfs"))
        pdf_dir.mkdir(exist_ok=True)
        os.chmod(pdf_dir, 0o755)
        final_pdf = pdf_dir / f"{safe_id}_{concepto['tipo']}.pdf"
    else:
        final_pdf = Path(output_path)

    compile_info = _generar_pdf_desde_latex_temporal(
        latex_content=latex_content,
        safe_id=safe_id,
        temp_prefix="mathkb_concept_pdf_",
        final_pdf=final_pdf,
    )

    if compile_info["status"] == "success_with_warnings":
        print(latex_warning_message(compile_info))
    else:
        print(
            "✅ PDF generated successfully "
            f"(return code: {compile_info.get('returncode')}, passes: {compile_info.get('passes')})"
        )

    return str(final_pdf)




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


def _format_pdf_section_value(value: object) -> str:
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(
            str(item).strip()
            for item in value
            if str(item).strip()
        )
    return str(value or "").strip()


def _render_note_pdf_extra_sections(sections: object) -> str:
    if not isinstance(sections, list):
        return ""

    rendered_sections = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = _format_pdf_section_value(section.get("title"))
        rows = section.get("rows") or []
        paragraphs = section.get("paragraphs") or []
        lines = []

        if title:
            lines.append(r"\section*{" + _latex_escape_text(title) + r"}")

        for row in rows:
            if isinstance(row, dict):
                label = _format_pdf_section_value(row.get("label"))
                value = _format_pdf_section_value(row.get("value"))
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                label = _format_pdf_section_value(row[0])
                value = _format_pdf_section_value(row[1])
            else:
                label = ""
                value = _format_pdf_section_value(row)

            if not value:
                continue
            if label:
                lines.append(
                    r"\noindent\textbf{"
                    + _latex_escape_text(label)
                    + r":} "
                    + _latex_escape_text(value)
                    + r"\\"
                )
            else:
                lines.append(r"\noindent " + _latex_escape_text(value) + r"\\")

        for paragraph in paragraphs:
            value = _format_pdf_section_value(paragraph)
            if value:
                lines.append(_latex_escape_text(value) + "\n")

        if len(lines) > 1:
            rendered_sections.append("\n".join(lines))

    return "\n\n".join(rendered_sections)


def _next_line_number(latex_doc: str) -> int:
    return latex_doc.count("\n") + 1


def generar_tex_nota_latex_info(nota: Dict, template: str = "simple") -> dict:
    """Generate a standalone diary-note LaTeX document and source map."""
    title = str(nota.get("title") or "Nota sin título").strip() or "Nota sin título"
    fecha_value = nota.get("date") or ""
    fecha = fecha_value.strftime("%Y-%m-%d") if hasattr(fecha_value, "strftime") else str(fecha_value).strip()
    project = str(nota.get("project") or "").strip()
    context = str(nota.get("context") or "").strip()
    tags = nota.get("tags") or []
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    body = str(nota.get("latex_body") or "")
    extra_sections = _render_note_pdf_extra_sections(nota.get("pdf_sections") or [])

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

    body_start_line = None
    body_line_count = body.count("\n") + 1 if body else 0

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
            body_start_line = _next_line_number(latex_doc)
            latex_doc += body + "\n"

        if extra_sections:
            latex_doc += extra_sections + "\n\n"

        latex_doc += r"\end{document}" + "\n"
        return {
            "latex": _normalize_latex_unicode(latex_doc),
            "source_map": {
                "body_start_line": body_start_line,
                "body_line_count": body_line_count,
                "template": template,
            },
        }

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
        body_start_line = _next_line_number(latex_doc)
        latex_doc += body + "\n\n"

    if extra_sections:
        latex_doc += extra_sections + "\n\n"

    latex_doc += r"\end{document}" + "\n"
    return {
        "latex": _normalize_latex_unicode(latex_doc),
        "source_map": {
            "body_start_line": body_start_line,
            "body_line_count": body_line_count,
            "template": template,
        },
    }


def generar_tex_nota_latex(nota: Dict, template: str = "simple") -> str:
    """Generate a standalone LaTeX document for a diary note (latex_notes).

    Args:
        nota: Mongo document of latex_notes.
        template: "simple" (default) or "diario" (mdframed boxes inspired by diario.tex).
    """
    return generar_tex_nota_latex_info(nota, template=template)["latex"]


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
    try:
        latex_info = generar_tex_nota_latex_info(nota, template=template)
        latex_content = latex_info["latex"]
        source_map = latex_info.get("source_map") or {}
        raw_id = str(nota.get("_id") or nota.get("id") or "latex_note")
        safe_id = _safe_filename_part(raw_id, "latex_note")
    except Exception as exc:
        _raise_pdf_export_error(
            "No se pudo generar el contenido LaTeX de la nota.",
            stage="Generar contenido LaTeX",
            operation="Construcción de documento LaTeX",
            exc=exc,
            note_id=str(nota.get("_id") or nota.get("id") or ""),
        )

    if output_path is None:
        pdf_dir = EXPORTED_NOTES_DIR
        pdf_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(pdf_dir, 0o755)

        date_prefix = str(nota.get("date") or "").replace("-", "")
        title = _safe_filename_part(nota.get("title"), "nota")
        suffix = f"{template}"
        if date_prefix:
            final_pdf = pdf_dir / f"{date_prefix}_{title}_{safe_id}_{suffix}.pdf"
        else:
            final_pdf = pdf_dir / f"{title}_{safe_id}_{suffix}.pdf"
    else:
        final_pdf = Path(output_path)

    return _generar_pdf_desde_latex_temporal(
        latex_content=latex_content,
        safe_id=safe_id,
        temp_prefix="mathkb_note_pdf_",
        final_pdf=final_pdf,
        include_note_styles=template == "diario",
        source_map=source_map,
    )


def generar_pdf_nota_latex(nota: Dict, output_path: Optional[str] = None, template: str = "diario") -> str:
    """Generate a PDF from a diary note and return only the final PDF path."""
    return generar_pdf_nota_latex_result(
        nota,
        output_path=output_path,
        template=template,
    )["pdf_path"]


def analizar_tex_nota_latex_con_chktex(nota: Dict, template: str = "diario") -> dict:
    """Generate the note TEX and analyze that exact source with ChkTeX."""
    latex_info = generar_tex_nota_latex_info(nota, template=template)
    latex_content = latex_info["latex"]
    source_map = latex_info.get("source_map") or {}
    raw_id = str(nota.get("_id") or nota.get("id") or "latex_note")
    digest = hashlib.sha256(latex_content.encode("utf-8")).hexdigest()[:12]
    safe_id = _safe_filename_part(f"{raw_id}_{digest}_chktex", "latex_note_chktex")
    EXPORTED_NOTES_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    tex_file = EXPORTED_NOTES_BUILD_DIR / f"{safe_id}.tex"
    tex_file.write_text(latex_content, encoding="utf-8")
    return asdict(
        run_chktex_analysis(
            tex_file,
            latex_source=latex_content,
            note_body_start_line=source_map.get("body_start_line"),
        )
    )


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
        return open_local_pdf(pdf_path)
        
    except Exception as e:
        st.error(f"❌ Error opening PDF: {e}")
        return False


def _generar_y_abrir_pdf(generar_pdf_path: Callable[[], str]) -> bool:
    try:
        with st.spinner("🔄 Generando PDF..."):
            pdf_path = generar_pdf_path()

            if abrir_pdf_en_navegador(pdf_path):
                st.success(f"✅ PDF generado y abierto: {pdf_path}")
                return True

            render_pdf_export_error(
                PdfExportError(
                    "El PDF fue generado, pero no se pudo abrir en el navegador.",
                    {
                        "stage": "Abrir o entregar PDF",
                        "operation": "Abrir PDF en navegador",
                        "file": pdf_path,
                        "pdf_path": pdf_path,
                        "probable_cause": "El navegador o el sistema no aceptó la apertura del archivo.",
                    },
                ),
                main_message="❌ PDF generado, pero no se pudo abrir.",
            )
            return False

    except Exception as e:
        render_pdf_export_error(e)
        return False


def generar_y_abrir_pdf_desde_formulario(concept_data: Dict) -> bool:
    """
    Generate PDF from form data and open it in browser.
    
    Args:
        concept_data: Dictionary containing concept data from form.
    
    Returns:
        True if successful, False otherwise.
    """
    return _generar_y_abrir_pdf(lambda: generar_pdf_concepto(concept_data))


def generar_y_abrir_pdf_nota_latex_desde_formulario(
    note_data: Dict,
    template: str = "diario",
) -> bool:
    """Generate and open a diary-note PDF from current Streamlit form values."""
    pdf_note = dict(note_data or {})
    pdf_note["title"] = str(pdf_note.get("title") or "Nota sin título").strip() or "Nota sin título"

    if not str(pdf_note.get("latex_body") or "").strip():
        st.warning("⚠️ El contenido LaTeX está vacío. Escribe contenido antes de generar el PDF.")
        return False

    return _generar_y_abrir_pdf(
        lambda: generar_pdf_nota_latex(
            pdf_note,
            template=template,
        )
    )

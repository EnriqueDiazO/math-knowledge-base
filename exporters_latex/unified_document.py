#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from exporters_latex.latex_compile import latex_failure_message
from exporters_latex.latex_compile import latex_warning_message
from exporters_latex.latex_compile import output_tail
from exporters_latex.latex_compile import run_latex_until_stable
from editor.utils.media_assets import copy_media_tree_for_latex
from mathkb_config import LATEX_MAX_PASSES
from mathkb_config import PDF_COMPILE_TIMEOUT_SECONDS


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATES_DIR = PROJECT_ROOT / "templates_latex"

TYPE_SECTION_TITLES = {
    "definicion": "Definiciones",
    "proposicion": "Proposiciones",
    "teorema": "Teoremas",
    "lema": "Lemas",
    "corolario": "Corolarios",
    "ejemplo": "Ejemplos",
    "nota": "Notas",
    "otro": "Otros",
}

TYPE_ORDER = [
    "definicion",
    "proposicion",
    "teorema",
    "lema",
    "corolario",
    "ejemplo",
    "nota",
    "otro",
]


@dataclass
class UnifiedExportResult:
    master_tex_path: Path
    pdf_path: Path | None
    concepts_dir: Path
    output_dir: Path
    warnings: list[str]
    errors: list[str]
    latex_log_path: Path | None
    success: bool
    log_tail: str = ""
    probable_error_file: str | None = None


def sanitize_filename(value: str, fallback: str = "documento") -> str:
    """Return a filesystem-safe ASCII slug."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.lower()
    ascii_value = re.sub(r"[^a-z0-9._ -]+", "_", ascii_value)
    ascii_value = re.sub(r"[\s-]+", "_", ascii_value)
    ascii_value = re.sub(r"_+", "_", ascii_value).strip("._ ")
    return ascii_value or fallback


def sanitize_source_name(value: str) -> str:
    """Keep source names readable while making them safe for paths."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(r"[^A-Za-z0-9._ -]+", "_", ascii_value)
    ascii_value = re.sub(r"[\s]+", "_", ascii_value)
    ascii_value = re.sub(r"_+", "_", ascii_value).strip("._ ")
    return ascii_value or "documento"


def latex_escape_text(value: Any) -> str:
    """Best-effort escape for LaTeX text fields, not for authored LaTeX bodies."""
    text = "" if value is None else str(value)
    return (
        text.replace("\\", r"\textbackslash{}")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("&", r"\&")
        .replace("%", r"\%")
        .replace("$", r"\$")
        .replace("#", r"\#")
        .replace("_", r"\_")
    )


def copy_latex_styles(destino: Path, templates_dir: Path = DEFAULT_TEMPLATES_DIR) -> list[str]:
    warnings: list[str] = []
    destino.mkdir(parents=True, exist_ok=True)
    for src in templates_dir.iterdir():
        if src.is_file() and src.suffix in {".sty", ".cls"}:
            dst = destino / src.name
            shutil.copy2(src, dst)

    for required in ("miestilo.sty", "coloredtheorem.sty"):
        if not (destino / required).exists():
            warnings.append(f"Style file not found: {templates_dir / required}")
    return warnings


def render_concept_fragment(concepto: dict, contenido_latex: str) -> str:
    """Render a partial LaTeX fragment using the current individual-export body."""
    concept_id = concepto.get("id", "")
    source = concepto.get("source", "")
    tipo = concepto.get("tipo", "")
    titulo = concepto.get("titulo") or concept_id or "Sin titulo"

    lines = [
        f"% Concept ID: {concept_id}",
        f"% Source: {source}",
        f"% Type: {tipo}",
        f"% Title: {titulo}",
        "",
        r"\section*{" + str(titulo) + "}",
        "",
    ]

    if contenido_latex:
        lines.extend([contenido_latex.strip(), ""])

    if concepto.get("comentario"):
        lines.extend([r"\section*{Comentario}", str(concepto["comentario"]), ""])

    ref = concepto.get("referencia")
    if isinstance(ref, dict) and ref:
        lines.append(r"\section*{Referencia}")
        linea1 = ", ".join(
            filter(
                None,
                (
                    ref.get("autor"),
                    ref.get("fuente"),
                    f"({ref.get('anio')})" if ref.get("anio") else None,
                ),
            )
        )
        if linea1:
            lines.append(linea1 + r"\\")

        linea2 = ", ".join(
            filter(
                None,
                (
                    f"Tomo {ref['tomo']}" if ref.get("tomo") else None,
                    f"Ed. {ref['edicion']}" if ref.get("edicion") else None,
                    f"Cap. {ref['capitulo']}" if ref.get("capitulo") else None,
                    f"Seccion {ref['seccion']}" if ref.get("seccion") else None,
                    f"Pag. {ref['paginas']}" if ref.get("paginas") else None,
                    ref.get("editorial"),
                ),
            )
        )
        if linea2:
            lines.append(linea2 + r"\\")
        if ref.get("issbn"):
            lines.append(f"ISSBN: {ref['issbn']}\\\\")
        if ref.get("doi"):
            lines.append(f"DOI: {ref['doi']}\\\\")
        if ref.get("url"):
            lines.append(r"\url{" + ref["url"] + r"}\\")
        lines.append("")

    if concept_id or source:
        lines.extend(
            [
                r"\textbf{ID del concepto:}~\verb|"
                + f"{concept_id}@{source}"
                + "|",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def make_unique_fragment_names(concepts: list[dict]) -> dict[str, str]:
    names: dict[str, str] = {}
    seen: set[str] = set()
    for index, concept in enumerate(concepts, start=1):
        key = concept_key(concept)
        title = concept.get("titulo") or concept.get("id") or "concepto"
        slug = sanitize_filename(str(title), fallback="concepto")
        base = f"{index:03d}_{slug}"
        name = base
        if name in seen:
            short_id = sanitize_filename(str(concept.get("id", "")), fallback="id")[:16]
            name = f"{base}_{short_id}"
        counter = 2
        while name in seen:
            name = f"{base}_{counter}"
            counter += 1
        seen.add(name)
        names[key] = name
    return names


def concept_key(concept: dict) -> str:
    return f"{concept.get('id')}@{concept.get('source')}"


def build_master_tex(
    title: str,
    fragment_records: list[dict],
    agrupar_por_tipo: bool = False,
    respetar_orden_manual: bool = True,
    include_toc: bool = True,
) -> str:
    lines = [
        r"\documentclass[12pt]{article}",
        "",
        r"\usepackage{miestilo}",
        r"\usepackage{coloredtheorem}",
        r"\usepackage{graphicx}",
        "",
        r"\title{" + latex_escape_text(title) + "}",
        r"\date{\today}",
        "",
        r"\begin{document}",
        "",
        r"\maketitle",
    ]
    if include_toc:
        lines.extend([r"\tableofcontents", ""])

    if agrupar_por_tipo and not respetar_orden_manual:
        for tipo in TYPE_ORDER:
            group = [r for r in fragment_records if (r["concept"].get("tipo") or "otro") == tipo]
            if not group:
                continue
            lines.extend([r"\section{" + TYPE_SECTION_TITLES.get(tipo, "Otros") + "}", ""])
            for record in group:
                lines.append(r"\input{" + record["input_path"] + "}")
            lines.append("")
        other = [
            r
            for r in fragment_records
            if (r["concept"].get("tipo") or "otro") not in TYPE_ORDER
        ]
        if other:
            lines.extend([r"\section{Otros}", ""])
            for record in other:
                lines.append(r"\input{" + record["input_path"] + "}")
            lines.append("")
    else:
        for record in fragment_records:
            lines.append(r"\input{" + record["input_path"] + "}")

    lines.extend(["", r"\end{document}", ""])
    return "\n".join(lines)


def read_log_tail(log_path: Path, lines: int = 60) -> str:
    if not log_path.exists():
        return ""
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def detect_probable_error_file(log_tail: str) -> str | None:
    matches = re.findall(r"\((concepts/[^()\s]+\.tex)", log_tail)
    if matches:
        return matches[-1]
    matches = re.findall(r"(concepts/[^:\s]+\.tex)", log_tail)
    if matches:
        return matches[-1]
    return None


def export_unified_document_with_inputs(
    source: str,
    concepts: list[dict],
    output_dir: str | Path = "./exported",
    title: str | None = None,
    agrupar_por_tipo: bool = False,
    respetar_orden_manual: bool = True,
    compile_pdf: bool = True,
    overwrite: bool = False,
    templates_dir: str | Path = DEFAULT_TEMPLATES_DIR,
) -> UnifiedExportResult:
    warnings: list[str] = []
    errors: list[str] = []
    if not concepts:
        safe_source = sanitize_source_name(source)
        output_path = Path(output_dir) / safe_source
        master_path = output_path / f"{safe_source}.tex"
        return UnifiedExportResult(
            master_tex_path=master_path,
            pdf_path=None,
            concepts_dir=output_path / "concepts",
            output_dir=output_path,
            warnings=[],
            errors=["No concepts selected."],
            latex_log_path=None,
            success=False,
        )

    safe_source = sanitize_source_name(source or title or "documento")
    base_output_path = Path(output_dir) / safe_source
    output_path = base_output_path
    if output_path.exists() and not overwrite:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(output_dir) / f"{safe_source}_{timestamp}"
        warnings.append(f"Output directory exists. Created timestamped directory: {output_path}")

    concepts_dir = output_path / "concepts"
    build_dir = output_path / "build"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    warnings.extend(copy_latex_styles(output_path, Path(templates_dir)))
    copy_media_tree_for_latex(output_path)

    fragment_names = make_unique_fragment_names(concepts)
    fragment_records: list[dict] = []

    for concept in concepts:
        key = concept_key(concept)
        contenido = concept.get("contenido_latex") or ""
        if not contenido.strip():
            warnings.append(f"Concept without LaTeX content: {key}")
        fragment_name = fragment_names[key]
        fragment_path = concepts_dir / f"{fragment_name}.tex"
        fragment_path.write_text(
            render_concept_fragment(concept, contenido),
            encoding="utf-8",
        )
        fragment_records.append(
            {
                "concept": concept,
                "fragment_path": fragment_path,
                "input_path": f"concepts/{fragment_name}",
            }
        )

    master_name = f"{safe_source}.tex"
    master_path = output_path / master_name
    master_path.write_text(
        build_master_tex(
            title=title or source or safe_source,
            fragment_records=fragment_records,
            agrupar_por_tipo=agrupar_por_tipo,
            respetar_orden_manual=respetar_orden_manual,
        ),
        encoding="utf-8",
    )

    pdf_path = output_path / f"{safe_source}.pdf"
    log_path = build_dir / f"{safe_source}.log"
    success = not errors
    log_tail = ""
    probable_error_file = None

    if compile_pdf and not errors:
        command = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-output-directory",
            str(build_dir),
            master_name,
        ]
        try:
            built_pdf = build_dir / f"{safe_source}.pdf"
            compile_info = run_latex_until_stable(
                command,
                cwd=str(output_path),
                tex_file=master_path,
                pdf_path=built_pdf,
                log_path=log_path,
                timeout_seconds=PDF_COMPILE_TIMEOUT_SECONDS,
                max_passes=LATEX_MAX_PASSES,
            )
            log_tail = compile_info.get("log_excerpt", "") or read_log_tail(log_path)
            probable_error_file = detect_probable_error_file(log_tail or compile_info.get("stdout", ""))
            if compile_info["status"] == "failed":
                result = compile_info.get("result")
                success = False
                errors.append(
                    latex_failure_message(
                        master_path,
                        command,
                        compile_info.get("returncode"),
                        log_excerpt=log_tail,
                        stdout=getattr(result, "stdout", "") if result else "",
                        stderr=getattr(result, "stderr", "") if result else "",
                    )
                )
            else:
                shutil.copy2(built_pdf, pdf_path)
                if compile_info["status"] == "success_with_warnings":
                    warnings.append(latex_warning_message(compile_info))
        except TimeoutError as exc:
            success = False
            errors.append(str(exc))
        except (FileNotFoundError, PermissionError, OSError) as exc:
            success = False
            errors.append(str(exc))

        if not log_tail:
            log_tail = read_log_tail(log_path)
            probable_error_file = detect_probable_error_file(log_tail)

    return UnifiedExportResult(
        master_tex_path=master_path,
        pdf_path=pdf_path if pdf_path.exists() else None,
        concepts_dir=concepts_dir,
        output_dir=output_path,
        warnings=warnings,
        errors=errors,
        latex_log_path=log_path if log_path.exists() else None,
        success=success and (not compile_pdf or pdf_path.exists()),
        log_tail=log_tail,
        probable_error_file=probable_error_file,
    )

"""Generate and validate the DI104-shaped Diario-note acceptance artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

from editor.diary_note_models import AcademicMetadata
from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import HeaderFooterSettings
from editor.diary_note_models import NoteReference
from editor.diary_note_models import NoteReferenceKind
from editor.diary_note_models import TableOfContentsSettings
from editor.diary_note_models import settings_document_fields
from editor.note_export import build_note_latex_bundle
from editor.note_export import export_note_pdf
from editor.note_export import export_note_tex

LOG_FAILURE_PATTERNS = (
    "Undefined control sequence",
    "LaTeX Error",
    "Emergency stop",
    "multiply defined",
    "undefined references",
    "Overfull \\hbox",
    "Overfull \\vbox",
    "Package fancyhdr Warning",
)


def acceptance_note() -> dict:
    """Return a synthetic note equivalent to the reference package's structure."""
    settings = DiaryNoteSettings(
        academic_metadata=AcademicMetadata(
            institution="Instituto de Ciencia & Tecnología",
            program="Programa de Ciencia de Datos 100% reproducible",
            course_code="DI104_S01",
            course_name="Programación orientada a objetos #1",
            week="Semana 1",
            session="Sesión inicial",
            short_title="Fundamentos de objetos",
            topic="Objetos, clases & modelo de ejecución",
            objective="Comprender identidad, estado y comportamiento con ejemplos á, é y ñ.",
            linked_activity="Actividad_DI104#1",
            author="Coordinación Académica",
            version="1.0",
            language="es-MX",
            pdf_subject="Nota teórica de programación & objetos",
            pdf_keywords=["Python", "POO", "bytecode", "objetos_datos"],
        ),
        page_layout=HeaderFooterSettings(
            enabled=True,
            header_left="{institution} · {course_code}",
            header_center="{program}",
            header_right="{week} · {short_title}",
            footer_left="{course_name}",
            footer_center="",
            footer_right="{author}",
            show_page_number=True,
        ),
        table_of_contents=TableOfContentsSettings(
            show_table_of_contents=True,
            toc_title="Contenido",
            toc_depth=2,
            position="after_metadata",
        ),
        references=[
            NoteReference(
                kind=NoteReferenceKind.BOOK,
                citation_key="lutz2021",
                authors="Lutz, Mark",
                title="Learning Python: edición práctica & completa",
                year_or_date="2021",
                publisher="O'Reilly Media",
                edition="5",
                language="en",
            ),
            NoteReference(
                kind=NoteReferenceKind.CHAPTER,
                citation_key="ramalho2022chapter",
                authors="Ramalho, Luciano",
                title="Data model & special methods",
                year_or_date="2022",
                container_title="Fluent Python",
                publisher="O'Reilly Media",
                pages="1--42",
                edition="2",
                doi="10.1234/python_chapter",
            ),
            NoteReference(
                kind=NoteReferenceKind.ARTICLE,
                citation_key="pythoninstitute2025",
                authors="Python Software Foundation",
                title="The Python execution model: 100% documented",
                year_or_date="2025",
                container_title="Python Language Reference",
                volume="3",
                number="14",
                pages="1--25",
                doi="10.5555/psf.execution_model",
            ),
            NoteReference(
                kind=NoteReferenceKind.WEBSITE,
                citation_key="pythonDataModel",
                authors="Python Software Foundation",
                title="Data model — objects, values & types #overview",
                year_or_date="2026",
                container_title="Python Documentation",
                url="https://docs.python.org/3/reference/datamodel.html?view=full_page&lang=es#objects-values-and-types",
                accessed_date="2026-08-12",
            ),
            NoteReference(
                kind=NoteReferenceKind.INSTITUTIONAL,
                citation_key="cocidDI104",
                authors="Coordinación de Ciencia & Datos",
                title="Lineamientos institucionales DI104_S01",
                year_or_date="2026",
                publisher="Instituto de Ciencia y Tecnología",
                url="https://example.edu/materiales/DI104_S01?version=1&format=pdf",
                accessed_date="2026-08-12",
            ),
            NoteReference(
                kind=NoteReferenceKind.SOFTWARE,
                citation_key="cpython2026",
                authors="Python Core Developers",
                title="CPython 3.14 — implementación de referencia",
                year_or_date="2026",
                publisher="Python Software Foundation",
                url="https://github.com/python/cpython/tree/3.14?tab=readme_ov_file#readme",
                accessed_date="2026-08-12",
            ),
            NoteReference(
                kind=NoteReferenceKind.OTHER,
                note="Borrador deliberadamente incompleto; no debe exportarse.",
            ),
        ],
    )
    body = r"""
\chapter{Fundamentos del modelo de objetos}
En Python, identidad, tipo y valor permiten razonar sobre el comportamiento de
los objetos. Esta página desarrolla el vocabulario base de la sesión.

\section{Identidad, estado y comportamiento}
La identidad permanece durante la vida del objeto; el estado puede cambiar y
el comportamiento se expresa mediante operaciones. El análisis distingue cada
dimensión para evitar confundir una referencia con el objeto referenciado.

\subsection{Ejemplo mínimo}
Dos nombres pueden designar el mismo objeto. La igualdad y la identidad son
preguntas diferentes y deben comprobarse con operaciones diferentes.

\clearpage
\chapter{Clases y protocolo de datos}
Una clase organiza construcción, representación y operaciones. Los métodos
especiales conectan objetos definidos por el usuario con el lenguaje.

\section{Creación e inicialización}
La creación reserva o produce la instancia; la inicialización establece su
estado inicial. La separación es útil al estudiar objetos inmutables.

\subsection{Representación segura}
Una representación debe facilitar diagnóstico sin confundir texto para humanos
con una forma inequívoca orientada a desarrollo.

\clearpage
\chapter{Ejecución, bytecode e importación}
El código fuente se compila a bytecode antes de ejecutarse. Los detalles de
cache e importación pertenecen a la implementación y no cambian el modelo
conceptual de nombre, objeto y alcance.

\section{Espacios de nombres}
La resolución de nombres consulta ámbitos definidos. Entenderlos permite
explicar cierres, módulos y atributos sin recurrir a reglas informales.

\subsection{Módulos como objetos}
Un módulo posee identidad y un espacio de nombres; importar enlaza nombres con
el módulo cargado de acuerdo con el sistema de importación.

\clearpage
\chapter*{Síntesis y preguntas abiertas}
\addcontentsline{toc}{chapter}{Síntesis y preguntas abiertas}
La síntesis no está numerada, pero se incorpora explícitamente al índice con el
mecanismo nativo de LaTeX. Quedan abiertas preguntas para la siguiente sesión.
"""
    return {
        "_id": "DI104_S01_acceptance",
        "title": "DI104: objetos, ejecución & configuración 100% segura #1",
        "date": "2026-08-12",
        "project": "Programación avanzada para Ciencia_de_Datos",
        "context": "estudio",
        "tags": ["Python", "POO", "DI104_S01"],
        "latex_body": body.strip() + "\n",
        "image_ids": [],
        **settings_document_fields(settings),
    }


def _run_pdflatex(project_dir: Path) -> tuple[subprocess.CompletedProcess[str], ...]:
    command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    return tuple(
        subprocess.run(
            command,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        for _ in range(2)
    )


def generate(output_dir: Path) -> dict[str, object]:
    """Write acceptance artifacts and validate a freshly extracted ZIP."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty evidence directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    note = acceptance_note()
    tex_export = export_note_tex(note)
    tex_path = output_dir / tex_export.file_name
    tex_path.write_text(tex_export.tex, encoding="utf-8")
    pdf_export = export_note_pdf(note, output_dir=output_dir)
    bundle = build_note_latex_bundle(note, diagnostics=pdf_export.diagnostics)
    zip_path = output_dir / bundle.download_filename
    zip_path.write_bytes(bundle.zip_bytes)

    extract_root = output_dir / "recompiled"
    extract_root.mkdir()
    with ZipFile(zip_path) as archive:
        archive.extractall(extract_root)
        project_name = archive.namelist()[0].split("/", 1)[0]
    project_dir = extract_root / project_name
    passes = _run_pdflatex(project_dir)
    if any(result.returncode != 0 for result in passes):
        details = "\n\n".join(result.stdout[-5000:] for result in passes)
        raise RuntimeError(f"pdflatex acceptance compilation failed:\n{details}")
    log_path = project_dir / "main.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    findings = [
        pattern for pattern in LOG_FAILURE_PATTERNS if pattern.casefold() in log_text.casefold()
    ]
    if findings:
        raise RuntimeError(f"LaTeX acceptance log contains forbidden findings: {findings}")
    toc_path = project_dir / "main.toc"
    toc_text = toc_path.read_text(encoding="utf-8")
    required_toc_titles = (
        "Fundamentos del modelo de objetos",
        "Identidad, estado y comportamiento",
        "Ejemplo mínimo",
        "Síntesis y preguntas abiertas",
        "Referencias",
    )
    if not all(title in toc_text for title in required_toc_titles):
        raise RuntimeError("The generated table of contents is missing required titles")
    report = {
        "tex": str(tex_path),
        "pdf": str(pdf_export.pdf_path),
        "zip": str(zip_path),
        "recompiled_pdf": str(project_dir / "main.pdf"),
        "recompiled_log": str(log_path),
        "recompiled_toc": str(toc_path),
        "pdflatex_return_codes": [result.returncode for result in passes],
        "pdflatex_passes": 2,
        "log_findings": findings,
        "generation_warnings": pdf_export.diagnostics.get("generation_warnings") or [],
    }
    report_path = output_dir / "validation.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    """Parse one output directory and print the machine-readable validation report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(generate(args.output_dir.expanduser().resolve()), ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""LaTeX regression coverage for structured Diario note settings."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from editor.diary_note_latex import latex_escape_text
from editor.diary_note_models import AcademicMetadata
from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import FirstPageStyle
from editor.diary_note_models import HeaderFooterSettings
from editor.diary_note_models import ListOfFiguresSettings
from editor.diary_note_models import ListOfTablesSettings
from editor.diary_note_models import NoteReference
from editor.diary_note_models import NoteReferenceKind
from editor.diary_note_models import TableOfContentsSettings
from editor.diary_note_models import TocPosition
from editor.diary_note_models import settings_document_fields
from editor.note_export import build_note_latex_bundle
from editor.note_export import export_note_pdf
from editor.pdf_export import generar_tex_nota_latex


def _structured_note() -> dict:
    settings = DiaryNoteSettings(
        academic_metadata=AcademicMetadata(
            institution="Instituto A & B",
            program="Programa 100% datos",
            course_code="DI_104#1",
            course_name="Programación $ avanzada",
            week="Semana 1",
            short_title="Objetos & clases",
            topic="Tema con {datos}",
            objective="Comprender á, é y ñ sin romper LaTeX.",
            author="Autora Institucional",
            pdf_keywords=["Python", "objetos_datos"],
        ),
        page_layout=HeaderFooterSettings(
            enabled=True,
            header_left="{institution} · {course_code}",
            header_right="{week} · {short_title}",
            footer_left="{course_name}",
            footer_right="{author}",
            first_page_style=FirstPageStyle.SAME,
            show_page_number=True,
        ),
        table_of_contents=TableOfContentsSettings(
            show_table_of_contents=True,
            toc_title="Contenido & guía",
            toc_depth=2,
            position=TocPosition.AFTER_METADATA,
        ),
        references=[
            NoteReference(
                kind=NoteReferenceKind.WEBSITE,
                citation_key="institucion2026",
                authors="Institución A & B",
                title="Guía 100% práctica #1",
                year_or_date="2026",
                publisher="Editorial_datos",
                url="https://example.test/guia_python?a=1&b=dos#seccion",
            ),
            NoteReference(
                kind=NoteReferenceKind.ARTICLE,
                citation_key="institucion2026",
                authors="García, Ana",
                title="Artículo sobre objetos",
                container_title="Revista Ñ",
                doi="10.1234/demo_test",
            ),
            NoteReference(),
        ],
    )
    return {
        "_id": "latex-structured",
        "title": "Título á, é, ñ & 100% _ # $ {seguro}",
        "date": "2026-08-12",
        "project": "Proyecto & pruebas",
        "context": "estudio",
        "tags": ["Python", "POO"],
        "latex_body": (
            "\\chapter{Fundamentos}\n"
            "Texto interior.\n"
            "\\section{Objetos}\n"
            "\\subsection{Identidad}\n"
            "Más contenido.\n"
        ),
        **settings_document_fields(settings),
    }


def _indexed_note() -> dict:
    note = _structured_note()
    note["list_of_figures"] = ListOfFiguresSettings(
        show_list_of_figures=True,
        title="Figuras & esquemas",
    ).model_dump(mode="json")
    note["list_of_tables"] = ListOfTablesSettings(
        show_list_of_tables=True,
        title="Tablas 100% útiles",
    ).model_dump(mode="json")
    note["latex_body"] = r"""
\chapter{Redes neuronales}
\section{Arquitectura}
\begin{figure}[htbp]
\centering
\rule{5cm}{3cm}
\caption{Arquitectura conceptual de una neurona artificial}
\label{fig:neurona}
\end{figure}

\begin{table}[htbp]
\centering
\begin{tabular}{cc}
A & B \\
1 & 2
\end{tabular}
\caption{Elementos de una neurona artificial}
\label{tab:elementos}
\end{table}

\section{Funciones de activación}
\begin{figure}[htbp]
\centering
\rule{5cm}{3cm}
\caption{Comparación de funciones de activación}
\label{fig:activaciones}
\end{figure}

\begin{table}[htbp]
\centering
\begin{tabular}{cc}
A & B \\
3 & 4
\end{tabular}
\caption{Comparación de funciones de activación}
\label{tab:activaciones}
\end{table}
""".strip()
    return note


def test_ordinary_text_escapes_every_latex_special_character() -> None:
    escaped = latex_escape_text("á é ñ & % _ # $ { } ~ ^ \\")

    assert escaped == (
        r"á é ñ \& \% \_ \# \$ \{ \} " r"\textasciitilde{} \textasciicircum{} \textbackslash{}"
    )


def test_diario_tex_renders_metadata_layout_toc_and_exportable_references_once() -> None:
    tex = generar_tex_nota_latex(_structured_note(), template="diario")

    assert tex.count(r"\hypersetup{") == 1
    assert r"pdftitle={Título á, é, ñ \& 100\% \_ \# \$ \{seguro\}}" in tex
    assert r"pdfauthor={Autora Institucional}" in tex
    assert r"pdfkeywords={Python, objetos\_datos}" in tex
    assert r"\usepackage{fancyhdr}" in tex
    assert r"\fancyhf{}" in tex
    assert r"\setlength{\headheight}{36pt}" in tex
    assert r"\thispagestyle{mathmongonote}" in tex
    assert tex.count(r"\tableofcontents") == 1
    assert tex.count(r"\renewcommand{\contentsname}{Contenido \& guía}") == 1
    assert r"\setcounter{tocdepth}{2}" in tex
    assert tex.index(r"\end{notemeta}") < tex.index(r"\tableofcontents")
    assert tex.count(r"\begin{thebibliography}{99}") == 1
    assert tex.count(r"\bibitem{") == 2
    assert r"\bibitem{institucion2026}" in tex
    assert r"\bibitem{institucion2026_2}" in tex
    assert "Borrador sin título" not in tex
    assert r"\addcontentsline{toc}{chapter}{Referencias}" in tex
    assert r"\chapter*{Referencias}" not in tex
    assert r"\url{https://example.test/guia_python?a=1&b=dos#seccion}" in tex


def test_toc_can_be_placed_after_title_and_old_note_keeps_features_disabled() -> None:
    note = _structured_note()
    note["table_of_contents"]["position"] = "after_title"
    tex = generar_tex_nota_latex(note, template="diario")
    assert tex.index(r"\tableofcontents") < tex.index(r"\begin{notemeta}")

    legacy = generar_tex_nota_latex(
        {"title": "Legacy & safe", "date": "2026-08-12", "latex_body": "Texto."},
        template="diario",
    )
    assert r"\notetitle{Legacy \& safe}" in legacy
    assert r"\usepackage{fancyhdr}" not in legacy
    assert r"\tableofcontents" not in legacy
    assert r"\listoffigures" not in legacy
    assert r"\listoftables" not in legacy
    assert r"\begin{thebibliography}" not in legacy


def test_figure_and_table_lists_are_independent_ordered_and_escaped_once() -> None:
    tex = generar_tex_nota_latex(_indexed_note(), template="diario")

    assert tex.count(r"\tableofcontents") == 1
    assert tex.count(r"\listoffigures") == 1
    assert tex.count(r"\listoftables") == 1
    assert tex.count(r"\renewcommand{\listfigurename}{Figuras \& esquemas}") == 1
    assert tex.count(r"\renewcommand{\listtablename}{Tablas 100\% útiles}") == 1
    assert tex.index(r"\end{notemeta}") < tex.index(r"\tableofcontents")
    assert tex.index(r"\tableofcontents") < tex.index(r"\listoffigures")
    assert tex.index(r"\listoffigures") < tex.index(r"\listoftables")
    assert tex.index(r"\listoftables") < tex.index(r"\chapter{Redes neuronales}")


def test_each_native_list_can_be_enabled_without_the_other_or_the_toc() -> None:
    note = _structured_note()
    note["table_of_contents"]["show_table_of_contents"] = False
    note["list_of_figures"] = {
        "show_list_of_figures": True,
        "title": "Sólo figuras",
    }

    figures_only = generar_tex_nota_latex(note, template="diario")

    assert r"\tableofcontents" not in figures_only
    assert figures_only.count(r"\listoffigures") == 1
    assert r"\listoftables" not in figures_only

    note["list_of_figures"]["show_list_of_figures"] = False
    note["list_of_tables"] = {
        "show_list_of_tables": True,
        "title": "Sólo tablas",
    }
    tables_only = generar_tex_nota_latex(note, template="diario")

    assert r"\tableofcontents" not in tables_only
    assert r"\listoffigures" not in tables_only
    assert tables_only.count(r"\listoftables") == 1


def test_page_number_is_emitted_once_per_style_and_first_page_modes_are_explicit() -> None:
    note = _structured_note()
    note["page_layout"]["header_left"] = "{page} / {page}"
    note["page_layout"]["footer_center"] = "{page}"
    tex = generar_tex_nota_latex(note, template="diario")

    main_style = tex.split(r"\fancypagestyle{mathmongonote}{%", 1)[1].split(
        r"\fancypagestyle{plain}{%", 1
    )[0]
    chapter_style = tex.split(r"\fancypagestyle{plain}{%", 1)[1].split(
        r"\fancypagestyle{mathmongofirstplain}{%", 1
    )[0]
    first_plain = tex.split(r"\fancypagestyle{mathmongofirstplain}{%", 1)[1].split(
        r"\pagestyle{mathmongonote}", 1
    )[0]
    assert main_style.count(r"\thepage") == 1
    assert chapter_style.count(r"\thepage") == 1
    assert first_plain.count(r"\thepage") == 1

    note["page_layout"]["first_page_style"] = "plain"
    plain_tex = generar_tex_nota_latex(note, template="diario")
    assert r"\thispagestyle{mathmongofirstplain}" in plain_tex
    note["page_layout"]["first_page_style"] = "empty"
    empty_tex = generar_tex_nota_latex(note, template="diario")
    assert r"\thispagestyle{empty}" in empty_tex

    note["page_layout"]["show_page_number"] = False
    no_page_tex = generar_tex_nota_latex(note, template="diario")
    assert r"\thepage" not in no_page_tex


def test_structured_diario_compiles_with_toc_in_multiple_passes(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for Diario structured export verification")

    result = export_note_pdf(_structured_note(), output_dir=tmp_path)
    log_text = str(result.diagnostics.get("log_text") or "")

    assert result.pdf_path.exists()
    assert result.pdf_path.parent == tmp_path
    assert int(result.diagnostics.get("passes") or 0) >= 2
    assert "Undefined control sequence" not in log_text
    assert "LaTeX Error" not in log_text
    assert "Emergency stop" not in log_text
    assert "undefined references" not in log_text.casefold()
    assert "multiply defined" not in log_text
    assert "Overfull \\hbox" not in log_text
    assert "Overfull \\vbox" not in log_text
    assert "Package fancyhdr Warning" not in log_text


def test_portable_zip_recompiles_toc_and_references_in_exactly_two_passes(
    tmp_path: Path,
) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for portable ZIP verification")
    bundle = build_note_latex_bundle(_structured_note())
    assert all(not name.startswith("/") and ".." not in Path(name).parts for name in bundle.entries)

    with ZipFile(BytesIO(bundle.zip_bytes)) as archive:
        archive.extractall(tmp_path)
        names = archive.namelist()
        root_name = names[0].split("/", 1)[0]
        source_metadata = archive.read(f"{root_name}/metadata/source.json").decode()
        readme = archive.read(f"{root_name}/README.md").decode()
        main_tex = archive.read(f"{root_name}/main.tex").decode()

    assert '"references"' in source_metadata
    assert "thebibliography" in main_tex
    assert "tableofcontents" in main_tex
    assert readme.count("pdflatex -interaction=nonstopmode main.tex") == 2
    project_dir = tmp_path / root_name
    command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    first = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)

    assert first.returncode == 0, first.stdout[-5000:]
    assert second.returncode == 0, second.stdout[-5000:]
    toc_text = (project_dir / "main.toc").read_text(encoding="utf-8")
    log_text = (project_dir / "main.log").read_text(encoding="utf-8", errors="replace")
    assert all(
        title in toc_text for title in ("Fundamentos", "Objetos", "Identidad", "Referencias")
    )
    assert "??" not in toc_text
    assert (project_dir / "main.pdf").exists()
    for pattern in (
        "Undefined control sequence",
        "LaTeX Error",
        "Emergency stop",
        "multiply defined",
        "undefined references",
        "Overfull \\hbox",
        "Overfull \\vbox",
        "Package fancyhdr Warning",
    ):
        assert pattern.casefold() not in log_text.casefold()


def test_portable_zip_builds_figure_and_table_indexes_in_exactly_two_passes(
    tmp_path: Path,
) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdftotext") is None:
        pytest.skip("pdflatex and pdftotext are required for native list verification")
    bundle = build_note_latex_bundle(_indexed_note())

    with ZipFile(BytesIO(bundle.zip_bytes)) as archive:
        archive.extractall(tmp_path)
        root_name = archive.namelist()[0].split("/", 1)[0]
        main_tex = archive.read(f"{root_name}/main.tex").decode()

    assert main_tex.count(r"\listoffigures") == 1
    assert main_tex.count(r"\listoftables") == 1
    project_dir = tmp_path / root_name
    command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    first = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)

    assert first.returncode == 0, first.stdout[-5000:]
    assert second.returncode == 0, second.stdout[-5000:]
    lof_path = project_dir / "main.lof"
    lot_path = project_dir / "main.lot"
    assert lof_path.exists()
    assert lot_path.exists()
    lof_text = lof_path.read_text(encoding="utf-8")
    lot_text = lot_path.read_text(encoding="utf-8")
    assert "Arquitectura conceptual de una neurona artificial" in lof_text
    assert "Comparación de funciones de activación" in lof_text
    assert "Elementos de una neurona artificial" in lot_text
    assert "Comparación de funciones de activación" in lot_text
    pdf_text = subprocess.run(
        ["pdftotext", "-layout", "main.pdf", "-"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "Figuras & esquemas" in pdf_text
    assert "Tablas 100 % útiles" in pdf_text
    assert "Arquitectura conceptual de una neurona artificial" in pdf_text
    assert "Elementos de una neurona artificial" in pdf_text
    assert "Tabla 1.1: Elementos de una neurona artificial" in pdf_text
    assert "Cuadro 1.1" not in pdf_text

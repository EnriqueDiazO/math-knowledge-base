"""Compatibility checks for the optional Diario academic color palette."""

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from editor.note_export import build_note_latex_bundle
from editor.note_export import export_note_pdf
from editor.pdf_export import generar_tex_nota_latex

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STYLE_PATH = PROJECT_ROOT / "templates_latex" / "miestilo.sty"
DI_COLORS = {
    "DIblue": "1F4E79",
    "DIteal": "0F6B78",
    "DIgreen": "3A7D44",
    "DIorange": "B45F06",
    "DIred": "9C2F2F",
    "DIgray": "4F5B66",
    "DIpurple": "665191",
    "DIlightblue": "EAF2F8",
    "DIlightgreen": "EDF7ED",
    "DIlightorange": "FFF4E5",
    "DIlightred": "FDECEC",
    "DIlightpurple": "F2EFF9",
}


def _palette_note() -> dict[str, object]:
    swatches = "\n".join(
        rf"\textcolor{{{name}}}{{{name}}}\par" for name in DI_COLORS
    )
    return {
        "_id": "di-palette-compatibility",
        "title": "Compatibilidad de paleta DI",
        "date": "2026-08-12",
        "latex_body": (
            r"\chapter{Paleta académica}" "\n"
            # A note-specific definition must remain authoritative.
            r"\definecolor{DIblue}{HTML}{123456}" "\n"
            + swatches
            + "\n"
            + r"\begin{tcolorbox}[colback=DIlightblue,colframe=DIblue]"
            + "Paleta disponible sin preámbulo adicional."
            + r"\end{tcolorbox}"
        ),
    }


def _compatibility_note() -> dict[str, object]:
    boxes = "\n".join(
        rf"\begin{{{name}}}Contenido de {name}.\end{{{name}}}"
        for name in (
            "learningobjectives",
            "precisionbox",
            "commonerror",
            "designchoice",
            "answerbox",
            "checkpoint",
        )
    )
    return {
        "_id": "di-body-compatibility",
        "title": "Compatibilidad del cuerpo DI",
        "date": "2026-08-12",
        "latex_body": (
            r"\chapter{Compatibilidad}" "\n"
            r"\begin{enumerate}\item Primero.\end{enumerate}" "\n"
            r"\begin{enumerate}[resume]\item Segundo.\end{enumerate}" "\n"
            r"\begin{table}[H]\centering Contenido.\end{table}" "\n"
            r"\begin{figure}[H]\centering Contenido.\end{figure}" "\n"
            r"\code{self} y \concept{objeto}." "\n"
            + boxes
            + "\n"
            r"\resizebox{0.98\textwidth}{!}{%" "\n"
            r"\begin{tikzpicture}[>=Latex,arrow/.style={->},card/.style={drop shadow}]"
            r'\node[card,rectangle split,rectangle split parts=2] (first) {"A"\nodepart{second}B};'
            r"\node[below=0.3cm of first] (second) {C};"
            r"\draw[arrow] (first) -- (second);"
            r"\end{tikzpicture}%" "\n"
            r"}"
        ),
    }


def test_di_palette_uses_non_overriding_defaults() -> None:
    """The shared palette must never replace a note-local color definition."""
    style = STYLE_PATH.read_text(encoding="utf-8")

    for name, html in DI_COLORS.items():
        assert rf"\providecolor{{{name}}}{{HTML}}{{{html}}}" in style
        assert rf"\definecolor{{{name}}}" not in style


def test_diario_adds_only_the_compatibility_features_used_by_the_body() -> None:
    """Known DI constructs receive a portable preamble without changing the body."""
    tex = generar_tex_nota_latex(_compatibility_note(), template="diario")

    assert tex.count(r"\usepackage{enumitem}") == 1
    assert tex.count(r"\usepackage{float}") == 1
    assert tex.count(r"\usetikzlibrary{") == 1
    assert tex.count(r'\AtBeginDocument{\shorthandoff{"<>}}') == 1
    assert r"arrows.meta,positioning,calc,fit,backgrounds" in tex
    assert r"matrix,shadows" in tex
    assert tex.count(r"\providecommand{\code}") == 1
    assert tex.count(r"\providecommand{\concept}") == 1
    for name in (
        "learningobjectives",
        "precisionbox",
        "commonerror",
        "designchoice",
        "answerbox",
        "checkpoint",
    ):
        assert tex.count(rf"\ProvideTColorBox{{{name}}}") == 1

    plain = generar_tex_nota_latex(
        {"title": "Legacy", "latex_body": "Texto sin extensiones."},
        template="diario",
    )
    assert r"\usepackage{enumitem}" not in plain
    assert r"\usepackage{float}" not in plain
    assert r"\usetikzlibrary{" not in plain
    assert r"\shorthandoff{<>}" not in plain
    assert r"\providecommand{\code}" not in plain
    assert r"\ProvideTColorBox" not in plain


def test_note_local_compatibility_definitions_remain_authoritative() -> None:
    """Body-local definitions suppress generated fallbacks with the same names."""
    note = {
        "title": "Definiciones locales",
        "latex_body": (
            r"\newcommand{\code}[1]{\emph{#1}}" "\n"
            r"\newtcolorbox{answerbox}{colback=white}" "\n"
            r"\code{local}\begin{answerbox}Local.\end{answerbox}"
        ),
    }

    tex = generar_tex_nota_latex(note, template="diario")

    assert r"\providecommand{\code}" not in tex
    assert r"\ProvideTColorBox{answerbox}" not in tex


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is required")
def test_portable_diario_bundle_compiles_palette_and_local_override(tmp_path: Path) -> None:
    """The real portable bundle must expose and compile every palette token."""
    bundle = build_note_latex_bundle(_palette_note())

    with ZipFile(BytesIO(bundle.zip_bytes)) as archive:
        root = archive.namelist()[0].split("/", 1)[0]
        bundled_style = archive.read(f"{root}/styles/miestilo.sty").decode("utf-8")
        archive.extractall(tmp_path)

    assert all(
        rf"\providecolor{{{name}}}{{HTML}}{{{html}}}" in bundled_style
        for name, html in DI_COLORS.items()
    )

    project_dir = tmp_path / root
    command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    first = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)

    assert first.returncode == 0, first.stdout[-5000:]
    assert second.returncode == 0, second.stdout[-5000:]
    assert (project_dir / "main.pdf").is_file()
    log_text = (project_dir / "main.log").read_text(encoding="utf-8", errors="replace")
    for pattern in ("Undefined color", "LaTeX Error", "Undefined control sequence"):
        assert pattern.casefold() not in log_text.casefold()


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is required")
def test_diario_pdf_compiles_known_di_body_extensions(tmp_path: Path) -> None:
    """The canonical PDF path must compile the constructs from the reported failure."""
    result = export_note_pdf(_compatibility_note(), output_dir=tmp_path)
    log_text = str(result.diagnostics.get("log_text") or "")

    assert result.pdf_path.is_file()
    for pattern in (
        "Something's wrong--perhaps a missing \\item",
        "Unknown float option",
        "Environment answerbox undefined",
        "Unknown operator",
        "Unknown arrow tip kind",
        "Undefined control sequence",
    ):
        assert pattern.casefold() not in log_text.casefold()

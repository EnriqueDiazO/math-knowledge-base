"""Real exporter compilation checks for representative canonical LaTeX tools."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from editor.latex_tools import latex_tool_by_id
from editor.note_export import export_note_pdf
from editor.pdf_export import generar_pdf_concepto


def _representative_body() -> str:
    tool_ids = (
        "theorem",
        "align_star",
        "cases",
        "pmatrix",
        "itemize",
        "booktabs",
        "listing_python",
        "algorithm",
        "tikzpicture",
        "dirtree",
        "pgfplots",
        "real_numbers",
        "osc_operator",
        "max_operator",
    )
    return "\n".join(latex_tool_by_id(tool_id).snippet for tool_id in tool_ids)


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is required")
def test_concept_exporter_compiles_representative_canonical_tools(tmp_path: Path) -> None:
    output = tmp_path / "concept_tools.pdf"

    generated = generar_pdf_concepto(
        {
            "id": "latex-tools-concept",
            "titulo": "Herramientas LaTeX",
            "tipo": "teorema",
            "source": "test",
            "contenido_latex": _representative_body(),
        },
        output_path=str(output),
    )

    assert Path(generated) == output
    assert output.is_file()
    assert output.stat().st_size > 0


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is required")
def test_cuaderno_exporter_compiles_representative_canonical_tools(tmp_path: Path) -> None:
    result = export_note_pdf(
        {
            "_id": "latex-tools-cuaderno",
            "title": "Herramientas LaTeX",
            "date": "2026-08-16",
            "project": "Pruebas",
            "context": "estudio",
            "tags": ["latex"],
            "latex_body": _representative_body(),
        },
        output_dir=tmp_path,
        template="diario",
    )

    assert result.pdf_path.is_file()
    assert result.pdf_path.stat().st_size > 0

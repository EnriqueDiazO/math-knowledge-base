"""Tests for unified latex_note export dispatch."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from editor import note_export
from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.persistence import build_cornell_note_document
from editor.cornell.renderer import CornellRenderResult


def sample_legacy_note(note_format: str | None = None) -> dict[str, Any]:
    note = {
        "_id": "legacy-1",
        "title": "Legacy note",
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "latex_body": r"\begin{equation}a+b=c\end{equation}",
    }
    if note_format is not None:
        note["note_format"] = note_format
    return note


def sample_cornell_document() -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CornellPage(
                page_id="p002",
                order=2,
                cue=CornellRegion(heading="Cue 2", latex="Segunda idea."),
                main=CornellRegion(
                    heading="Teorema",
                    latex="\\begin{theorem}{Titulo}\nContenido.\n\\end{theorem}",
                ),
                summary=CornellRegion(heading="Resumen 2", latex="Cierre 2."),
            ),
            CornellPage(
                page_id="p001",
                order=1,
                cue=CornellRegion(heading="Cue 1", latex="Primera idea."),
                main=CornellRegion(
                    heading="Definicion",
                    latex="\\begin{definition}{hola}\nhola\n\\end{definition}",
                ),
                summary=CornellRegion(heading="Resumen 1", latex="Cierre 1."),
            ),
        ),
    )


def sample_cornell_note() -> dict[str, Any]:
    note = build_cornell_note_document(
        {
            "_id": "cornell-1",
            "title": "Cornell Algebra",
            "date": "2026-07-07",
            "project": "Algebra",
            "context": "estudio",
            "tags": ["cornell"],
        },
        sample_cornell_document(),
    )
    note["_id"] = "cornell-1"
    return note


def pdfinfo_text(pdf_path: Path) -> str:
    return subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_export_note_tex_uses_legacy_exporter_for_missing_note_format(monkeypatch) -> None:
    calls = []

    def fake_legacy_tex(note: dict[str, Any], template: str = "diario") -> str:
        calls.append((note, template))
        return "LEGACY TEX"

    monkeypatch.setattr(note_export, "generar_tex_nota_latex", fake_legacy_tex)

    result = note_export.export_note_tex(sample_legacy_note())

    assert result.tex == "LEGACY TEX"
    assert result.note_format == "freeform"
    assert calls[0][1] == "diario"


def test_export_note_tex_uses_legacy_exporter_for_freeform(monkeypatch) -> None:
    monkeypatch.setattr(note_export, "generar_tex_nota_latex", lambda note, template="diario": "FREEFORM TEX")

    result = note_export.export_note_tex(sample_legacy_note("freeform"))

    assert result.tex == "FREEFORM TEX"
    assert result.note_format == "freeform"


def test_export_note_tex_uses_cornell_renderer_and_orders_pages() -> None:
    result = note_export.export_note_tex(sample_cornell_note())

    assert result.note_format == CORNELL_NOTE_FORMAT
    assert result.tex.index("Definicion") < result.tex.index("Teorema")
    assert result.tex.count(r"\null") == 2


def test_export_note_pdf_uses_cornell_renderer(monkeypatch, tmp_path: Path) -> None:
    calls = []
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"%PDF")

    def fake_render(document: CornellDocument, output_dir: Path, output_name: str) -> CornellRenderResult:
        calls.append((document, output_dir, output_name))
        return CornellRenderResult(
            success=True,
            status="success",
            tex_path=tmp_path / "fake.tex",
            pdf_path=pdf_path,
            log_path=tmp_path / "fake.log",
            diagnostics={"status": "success"},
        )

    monkeypatch.setattr(note_export, "render_cornell_document", fake_render)

    result = note_export.export_note_pdf(sample_cornell_note(), output_dir=tmp_path)

    assert result.note_format == CORNELL_NOTE_FORMAT
    assert result.pdf_path == pdf_path
    assert calls[0][0].ordered_pages()[0].page_id == "p001"


def test_export_note_unknown_format_fails_clearly() -> None:
    with pytest.raises(ValueError, match="Formato de nota desconocido"):
        note_export.export_note_tex({**sample_legacy_note(), "note_format": "mystery"})


def test_export_note_pdf_cornell_multipage_compiles_snippets(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for Cornell export PDF verification")

    result = note_export.export_note_pdf(sample_cornell_note(), output_dir=tmp_path)

    assert result.note_format == CORNELL_NOTE_FORMAT
    assert result.pdf_path.exists()
    assert "Pages:           2" in pdfinfo_text(result.pdf_path)

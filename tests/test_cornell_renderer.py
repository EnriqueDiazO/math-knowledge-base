"""Tests for the standalone Cornell MVP renderer."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from editor.cornell import renderer
from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import build_cornell_math_v1_payload
from editor.cornell.models import generate_latex_body


def sample_page() -> CornellPage:
    return CornellPage(
        page_id="p001",
        order=1,
        cue=CornellRegion(
            heading="Ideas principales",
            latex="Matrices con la misma forma.",
            image_ids=("cue-image",),
        ),
        main=CornellRegion(
            heading="Aritmética de matrices",
            latex=r"""
            \[
            A+B =
            \begin{pmatrix}
            1 & 2\\
            3 & 4
            \end{pmatrix}
            \]
            """,
        ),
        summary=CornellRegion(
            heading="Observaciones",
            latex="Revisar dimensiones antes de operar.",
        ),
    )


def sample_document() -> CornellDocument:
    second_page = CornellPage(
        page_id="p002",
        order=2,
        cue=CornellRegion(heading="Recordatorio", latex="Producto compatible."),
        main=CornellRegion(heading="Producto", latex=r"\[ (AB)_{ij}=\sum_k a_{ik}b_{kj} \]"),
        summary=CornellRegion(heading="Cierre", latex="Primero revisar dimensiones."),
    )
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(second_page, sample_page()),
    )


def test_cornell_page_model_creation() -> None:
    page = sample_page()

    assert page.page_id == "p001"
    assert page.order == 1
    assert page.cue.heading == "Ideas principales"
    assert page.cue.image_ids == ("cue-image",)


def test_cornell_page_requires_page_id() -> None:
    with pytest.raises(ValueError):
        CornellPage(
            page_id=" ",
            order=1,
            cue=CornellRegion(heading="Cue", latex="Cue body"),
            main=CornellRegion(heading="Main", latex="Main body"),
            summary=CornellRegion(heading="Summary", latex="Summary body"),
        )


def test_cornell_page_requires_positive_order() -> None:
    with pytest.raises(ValueError):
        CornellPage(
            page_id="p001",
            order=0,
            cue=CornellRegion(heading="Cue", latex="Cue body"),
            main=CornellRegion(heading="Main", latex="Main body"),
            summary=CornellRegion(heading="Summary", latex="Summary body"),
        )


def test_cornell_document_round_trip_to_dict_from_dict() -> None:
    document = sample_document()

    restored = CornellDocument.from_dict(document.to_dict())

    assert restored == CornellDocument.from_dict(restored.to_dict())
    assert restored.to_dict() == document.to_dict()


def test_cornell_document_rejects_duplicate_page_ids() -> None:
    with pytest.raises(ValueError):
        CornellDocument(
            schema_version=1,
            template_id=DEFAULT_TEMPLATE_ID,
            pages=(sample_page(), sample_page()),
        )


def test_cornell_document_rejects_duplicate_orders() -> None:
    with pytest.raises(ValueError):
        CornellDocument(
            schema_version=1,
            template_id=DEFAULT_TEMPLATE_ID,
            pages=(
                sample_page(),
                CornellPage(
                    page_id="p002",
                    order=1,
                    cue=CornellRegion(heading="Cue", latex="Cue body"),
                    main=CornellRegion(heading="Main", latex="Main body"),
                    summary=CornellRegion(heading="Summary", latex="Summary body"),
                ),
            ),
        )


def test_cornell_document_orders_pages_by_order() -> None:
    document = sample_document()

    assert [page.page_id for page in document.ordered_pages()] == ["p001", "p002"]
    assert [page["page_id"] for page in document.to_dict()["pages"]] == ["p001", "p002"]


def test_generate_latex_body_uses_ordered_regions() -> None:
    latex_body = generate_latex_body(sample_document())

    assert latex_body.index("Ideas principales") < latex_body.index("Aritmética de matrices")
    assert latex_body.index("Aritmética de matrices") < latex_body.index("Observaciones")
    assert latex_body.index("Observaciones") < latex_body.index("Recordatorio")
    assert r"\paragraph*{Producto}" in latex_body


def test_build_cornell_math_v1_payload_structure() -> None:
    payload = build_cornell_math_v1_payload(sample_document())

    assert payload["note_format"] == CORNELL_NOTE_FORMAT
    assert payload["cornell"]["schema_version"] == 1
    assert payload["cornell"]["template_id"] == DEFAULT_TEMPLATE_ID
    assert payload["cornell"]["pages"][0]["cue"]["heading"] == "Ideas principales"
    assert "latex_body" in payload


def test_generate_cornell_tex_contains_three_regions() -> None:
    tex = renderer.generate_cornell_tex(sample_page())

    assert "Ideas principales" in tex
    assert "Aritmética de matrices" in tex
    assert "Observaciones" in tex
    assert r"\begin{pmatrix}" in tex


def test_generate_cornell_tex_contains_expected_geometry() -> None:
    tex = renderer.generate_cornell_tex(sample_page())

    assert "paperwidth=8.5in,paperheight=11in,margin=0in" in tex
    assert "$(SW)+(0,2in)$" in tex
    assert "$(SW)+(2.4in,2in)$" in tex
    assert "$(NW)+(2.5in,0)$" in tex
    assert "$(NW)+(2.5in,-1.11in)$" in tex
    assert r"\includegraphics[width=6in]{cornell_assets/lineas.png}" in tex


def test_generate_cornell_tex_does_not_use_historical_three_pdf_pipeline() -> None:
    tex = renderer.generate_cornell_tex(sample_page())

    assert "Izquierda" not in tex
    assert "Derecha" not in tex
    assert "Abajo" not in tex
    assert r"\foreach" not in tex
    assert "page=\\p" not in tex


def test_write_cornell_tex_creates_debug_source(tmp_path: Path) -> None:
    tex_path = renderer.write_cornell_tex(sample_page(), tmp_path)

    assert tex_path.exists()
    assert tex_path.read_text(encoding="utf-8").startswith(
        "% Generated by MathMongo Cornell MVP renderer."
    )
    assert (tmp_path / "cornell_assets" / "lineas.png").exists()


def test_render_cornell_pdf_surfaces_compile_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run_latex_until_stable(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "status": "failed",
            "log_excerpt": "! Undefined control sequence.",
            "stderr": "",
        }

    monkeypatch.setattr(renderer, "run_latex_until_stable", fake_run_latex_until_stable)

    result = renderer.render_cornell_pdf(sample_page(), tmp_path)

    assert not result.success
    assert result.status == "failed"
    assert "! Undefined control sequence." in result.message
    assert result.tex_path.exists()


def test_render_cornell_pdf_has_single_letter_page(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for PDF geometry verification")

    result = renderer.render_cornell_pdf(sample_page(), tmp_path)

    assert result.success, result.message
    info = subprocess.run(
        ["pdfinfo", str(result.pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "Pages:           1" in info
    assert "Page size:       612 x 792 pts (letter)" in info

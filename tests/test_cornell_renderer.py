"""Tests for the standalone Cornell MVP renderer."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from editor.cornell import renderer
from editor.cornell.latex_compat import snippet_environment_names
from editor.cornell.latex_compat import supported_cornell_snippet_environments
from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import build_cornell_math_v1_payload
from editor.cornell.models import generate_latex_body
from editor.cornell.ui_helpers import LATEX_SNIPPET_GROUPS


def sample_page() -> CornellPage:
    return CornellPage(
        page_id="p001",
        order=1,
        cue=CornellRegion(
            heading="Ideas principales",
            latex="Matrices con la misma forma.",
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


def sample_three_page_document() -> CornellDocument:
    third_page = CornellPage(
        page_id="p003",
        order=3,
        cue=CornellRegion(heading="Comprobaciones", latex="Producto compatible."),
        main=CornellRegion(heading="Producto de matrices", latex=r"\[ (AB)_{ij}=\sum_k a_{ik}b_{kj} \]"),
        summary=CornellRegion(heading="Cierre", latex="El producto depende del orden."),
    )
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(third_page, sample_page(), sample_document().ordered_pages()[1]),
    )


def snippet_page(main_latex: str) -> CornellPage:
    return CornellPage(
        page_id="snippet",
        order=1,
        cue=CornellRegion(heading="Cue", latex="Texto de apoyo."),
        main=CornellRegion(heading="Snippets", latex=main_latex),
        summary=CornellRegion(heading="Summary", latex="Cierre."),
    )


def summary_layout_page(summary_latex: str) -> CornellPage:
    return CornellPage(
        page_id="summary-layout",
        order=1,
        cue=CornellRegion(heading="Cue", latex="Cue body"),
        main=CornellRegion(heading="Main", latex="Main body"),
        summary=CornellRegion(heading="Observaciones 2", latex=summary_latex),
    )


def pdfinfo_text(pdf_path: Path) -> str:
    return subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def pdf_page_text(pdf_path: Path, page_number: int) -> str:
    return subprocess.run(
        [
            "pdftotext",
            "-layout",
            "-f",
            str(page_number),
            "-l",
            str(page_number),
            str(pdf_path),
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_cornell_page_model_creation() -> None:
    page = sample_page()

    assert page.page_id == "p001"
    assert page.order == 1
    assert page.cue.heading == "Ideas principales"
    assert page.cue.image_ids == ()


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


def test_generate_cornell_tex_contains_snippet_compatibility_layer() -> None:
    tex = renderer.generate_cornell_tex(sample_page())

    assert "Cornell compatibility layer for snippets shared with Diario LaTeX" in tex
    assert r"\NewDocumentEnvironment{definition}{g}" in tex
    assert r"\NewDocumentEnvironment{theorem}{g}" in tex
    assert r"\NewDocumentEnvironment{dirtree}" in tex
    assert r"\RenewDocumentEnvironment{lstlisting}" in tex


def test_generate_cornell_tex_positions_summary_body_independently() -> None:
    tex = renderer.generate_cornell_tex(
        summary_layout_page(
            "\\begin{example}\n"
            "A poco no ocupa todo el espacio.\\\\\n"
            "Ejemplo en otra linea.\n"
            "\\end{example}"
        )
    )

    summary_heading_index = tex.index(r"\CornellSummaryHeading{Observaciones 2}")
    summary_body_anchor_index = tex.index(
        r"\node[anchor=north west, inner sep=0pt, align=left] at ($(SW)+(18mm,1.62in)$)"
    )
    summary_marker_index = tex.index("% Cornell source page=1 region=summary")

    assert summary_heading_index < summary_body_anchor_index
    assert summary_body_anchor_index < summary_marker_index
    assert r"\begin{minipage}[t]{7.55in}" in tex
    assert r"\raggedright" in tex
    assert r"\raggedleft" not in tex
    assert "anchor=north east" not in tex
    assert "align=right" not in tex
    assert "$(SW)+(8.3in,1.72in)$" not in tex
    assert tex.index(r"\begin{example}") > summary_marker_index
    assert "A poco no ocupa todo el espacio" in tex
    assert "Ejemplo en otra linea" in tex


def test_all_snippet_environments_are_supported_by_cornell_compat() -> None:
    offered_environments = set(snippet_environment_names())
    supported_environments = set(supported_cornell_snippet_environments())

    assert offered_environments <= supported_environments


def test_generate_cornell_tex_does_not_use_historical_three_pdf_pipeline() -> None:
    tex = renderer.generate_cornell_tex(sample_page())

    assert "Izquierda" not in tex
    assert "Derecha" not in tex
    assert "Abajo" not in tex
    assert r"\foreach" not in tex
    assert "page=\\p" not in tex


def test_generate_cornell_document_tex_renders_pages_by_order() -> None:
    tex = renderer.generate_cornell_document_tex(sample_three_page_document())

    assert tex.index("Aritmética de matrices") < tex.index("Producto")
    assert tex.index("Producto") < tex.index("Producto de matrices")


def test_generate_cornell_document_tex_contains_each_page_content() -> None:
    tex = renderer.generate_cornell_document_tex(sample_three_page_document())

    assert "Aritmética de matrices" in tex
    assert "Producto" in tex
    assert "Producto de matrices" in tex
    assert "Comprobaciones" in tex


def test_generate_cornell_document_tex_does_not_use_historical_pipeline() -> None:
    tex = renderer.generate_cornell_document_tex(sample_three_page_document())

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
    assert "Undefined control sequence." in result.message
    assert result.tex_path.exists()


def test_render_cornell_pdf_has_single_letter_page(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for PDF geometry verification")

    result = renderer.render_cornell_pdf(sample_page(), tmp_path)

    assert result.success, result.message
    info = pdfinfo_text(result.pdf_path)
    assert "Pages:           1" in info
    assert "Page size:       612 x 792 pts (letter)" in info


@pytest.mark.parametrize(
    ("snippet_name", "main_latex"),
    [
        (
            "definition",
            "\\begin{definition}{hola}\nhola\n\\end{definition}",
        ),
        (
            "theorem",
            "\\begin{theorem}{Titulo}\nhola\n\\end{theorem}",
        ),
        (
            "equation",
            "\\begin{equation}\na+b=c\n\\end{equation}",
        ),
        (
            "matrix",
            "\\[\n\\begin{pmatrix}\n1 & 2 \\\\\n3 & 4\n\\end{pmatrix}\n\\]",
        ),
    ],
)
def test_render_cornell_pdf_compiles_core_snippets(
    snippet_name: str,
    main_latex: str,
    tmp_path: Path,
) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for Cornell snippet compilation")

    result = renderer.render_cornell_pdf(snippet_page(main_latex), tmp_path / snippet_name)

    assert result.success, result.message


def test_render_cornell_pdf_compiles_every_shared_latex_snippet(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for Cornell snippet compilation")

    snippets = []
    for group in LATEX_SNIPPET_GROUPS:
        for snippet in group.snippets:
            snippets.append(f"% snippet {snippet.key}\n{snippet.snippet}")
    result = renderer.render_cornell_pdf(snippet_page("\n\n".join(snippets)), tmp_path)

    assert result.success, result.message


def test_cornell_compile_error_summary_uses_page_and_region(tmp_path: Path) -> None:
    tex_path = tmp_path / "cornell_preview.tex"
    tex_path.write_text(
        "\n".join(
            [
                r"\begin{document}",
                "% Cornell source page=1 region=main",
                r"\begin{unknown}",
                r"\end{document}",
            ]
        ),
        encoding="utf-8",
    )
    diagnostics = {
        "log_excerpt": "./cornell_preview.tex:3: LaTeX Error: Environment unknown undefined.",
        "log_text": "FULL LOG\n./cornell_preview.tex:3: LaTeX Error: Environment unknown undefined.",
    }

    summary = renderer.summarize_cornell_latex_failure(tex_path, diagnostics)
    result = renderer.CornellRenderResult(
        success=False,
        status="failed",
        tex_path=tex_path,
        pdf_path=tex_path.with_suffix(".pdf"),
        log_path=tex_path.with_suffix(".log"),
        message=summary,
        diagnostics=diagnostics,
    )

    assert summary == "Error LaTeX en pagina 1, region Main: Environment unknown undefined."
    assert renderer.cornell_latex_full_log(result).startswith("FULL LOG")


def test_render_cornell_document_one_page_has_one_pdf_page(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for PDF geometry verification")

    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(sample_page(),),
    )
    result = renderer.render_cornell_document(document, tmp_path, "one_page")

    assert result.success, result.message
    assert "Pages:           1" in pdfinfo_text(result.pdf_path)


def test_render_cornell_document_three_pages_has_three_pdf_pages(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for PDF geometry verification")

    result = renderer.render_cornell_document(sample_three_page_document(), tmp_path, "three_pages")

    assert result.success, result.message
    info = pdfinfo_text(result.pdf_path)
    assert "Pages:           3" in info
    assert "Page size:       612 x 792 pts (letter)" in info


def test_render_cornell_document_has_no_initial_or_final_blank_page(tmp_path: Path) -> None:
    if (
        shutil.which("pdflatex") is None
        or shutil.which("pdfinfo") is None
        or shutil.which("pdftotext") is None
    ):
        pytest.skip("pdflatex, pdfinfo, and pdftotext are required for PDF text verification")

    result = renderer.render_cornell_document(sample_three_page_document(), tmp_path, "no_blanks")

    assert result.success, result.message
    assert "Aritmética de matrices" in pdf_page_text(result.pdf_path, 1)
    assert "Producto de matrices" in pdf_page_text(result.pdf_path, 3)


def test_render_cornell_document_empty_document_returns_clear_error(tmp_path: Path) -> None:
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(),
    )

    result = renderer.render_cornell_document(document, tmp_path, "empty")

    assert not result.success
    assert result.status == "failed"
    assert "at least one page" in result.message

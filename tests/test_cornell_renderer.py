"""Tests for the standalone Cornell MVP renderer."""

# ruff: noqa: D103

from __future__ import annotations

import re
import shutil
import subprocess
import zlib
from pathlib import Path

import pytest

from editor.cornell import renderer
from editor.cornell.latex_compat import snippet_environment_names
from editor.cornell.latex_compat import supported_cornell_snippet_environments
from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_cornell_math_v1_payload
from editor.cornell.models import build_footer_text
from editor.cornell.models import generate_latex_body
from editor.cornell.ui_helpers import LATEX_SNIPPET_GROUPS

HREF_REGRESSION_URL = "https://www.r-project.org/"
HREF_REGRESSION_LATEX = rf"""
Texto con enlace: \href{{{HREF_REGRESSION_URL}}}{{\textbf{{proyecto oficial de R}}}}

\begin{{enumerate}}
    \item ¿Qué es \textbf{{R}}?
    \item ¿Qué es \textbf{{RStudio}}?
\end{{enumerate}}

Código inline: \texttt{{x <- c(10, 12, 9, 15)}}

Matemáticas: \(x^2 + y^2 = z^2\)

Caracteres españoles: á é í ó ú ñ ¿ ¡
"""
PDF_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)


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


def href_regression_page() -> CornellPage:
    return CornellPage(
        page_id="href-regression",
        order=1,
        cue=CornellRegion(heading="Cue", latex="Idea principal."),
        main=CornellRegion(heading="R y RStudio", latex=HREF_REGRESSION_LATEX),
        summary=CornellRegion(heading="Resumen", latex="Cierre con acentos: á é í ó ú ñ."),
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


def overlap_regression_page(repeat: int, page_id: str = "p001") -> CornellPage:
    repeated_text = " ".join(
        [
            "Sea una familia de objetos con una propiedad estable bajo las operaciones consideradas."
            for _ in range(repeat)
        ]
    )
    return CornellPage(
        page_id=page_id,
        order=1,
        cue=CornellRegion(
            heading="Ideas principales",
            latex="\\begin{itemize}\n"
            + "\n".join("\\item Punto de control" for _ in range(7))
            + "\n\\end{itemize}",
        ),
        main=CornellRegion(
            heading="Regresion Cornell",
            latex=rf"""
            \begin{{definition}}{{Espacio}}
            {repeated_text}
            \end{{definition}}
            \begin{{example}}{{Matrices}}
            {repeated_text}
            \end{{example}}
            \begin{{theorem}}{{Unicidad}}
            {repeated_text}
            \end{{theorem}}
            \begin{{definition}}{{Subespacio}}
            {repeated_text}
            \end{{definition}}
            \begin{{proposition}}{{Criterio}}
            {repeated_text}
            \end{{proposition}}
            """,
        ),
        summary=CornellRegion(
            heading="Observaciones",
            latex=r"""
            \begin{remark}{Control}
            El criterio reduce la verificacion a una sola expresion.
            \end{remark}
            \begin{itemize}
            \item Cuidar no vacuidad.
            \item Separar axiomas de consecuencias.
            \end{itemize}
            """,
        ),
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


def pdf_contains_uri(pdf_path: Path, uri: str) -> bool:
    raw = pdf_path.read_bytes()
    content = bytearray(raw)
    for match in PDF_STREAM_PATTERN.finditer(raw):
        stream = match.group(1).strip(b"\r\n")
        try:
            content.extend(zlib.decompress(stream))
        except zlib.error:
            continue
    return b"/Subtype/Link" in content and uri.encode("ascii") in content


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


def test_cornell_document_identity_round_trip_to_dict_from_dict() -> None:
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(sample_page(),),
        attribution=CornellAttribution(
            enabled=True,
            text="© 2026 Enrique Díaz Ocampo · Material docente",
            author="Enrique Díaz Ocampo",
            course="Álgebra",
            year="2026",
            position="bottom_right",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="text",
            text="COCID",
            opacity=0.05,
            scale=0.4,
            position="center",
        ),
    )

    restored = CornellDocument.from_dict(document.to_dict())

    assert restored == document
    assert restored.attribution.mode == "custom"
    assert restored.attribution.text.startswith("© 2026")
    assert restored.watermark.opacity == 0.05


def test_build_footer_text_auto_author_course_year() -> None:
    assert (
        build_footer_text(
            mode="auto",
            author="Enrique Díaz Ocampo",
            course="Python",
            year="2026",
        )
        == "© 2026 Enrique Díaz Ocampo · Python"
    )


@pytest.mark.parametrize(
    ("author", "course", "year", "expected"),
    [
        ("Enrique Díaz Ocampo", "", "2026", "© 2026 Enrique Díaz Ocampo"),
        ("Enrique Díaz Ocampo", "", "", "© Enrique Díaz Ocampo"),
        ("", "Python", "2026", "Python · 2026"),
        ("", "Python", "", "Python"),
        ("", "", "2026", "2026"),
        ("", "", "", ""),
    ],
)
def test_build_footer_text_auto_omits_empty_fields(
    author: str,
    course: str,
    year: str,
    expected: str,
) -> None:
    assert build_footer_text(mode="auto", author=author, course=course, year=year) == expected


def test_build_footer_text_custom_uses_literal_footer_text() -> None:
    assert (
        build_footer_text(
            mode="custom",
            text="© Enrique Díaz Ocampo · Material Docente",
            author="Otro",
            course="Python",
            year="2026",
        )
        == "© Enrique Díaz Ocampo · Material Docente"
    )


def test_cornell_document_legacy_attribution_without_mode_stays_custom() -> None:
    payload = sample_document().to_dict()
    payload["attribution"] = {
        "enabled": True,
        "text": "© Enrique Díaz Ocampo · Material Docente",
        "author": "Enrique Díaz Ocampo",
        "course": "Python",
        "year": "2026",
        "position": "bottom_right",
    }

    restored = CornellDocument.from_dict(payload)

    assert restored.attribution.mode == "custom"
    assert build_footer_text(restored.attribution) == "© Enrique Díaz Ocampo · Material Docente"


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


def test_generate_cornell_document_tex_contains_text_watermark_and_footer() -> None:
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(sample_page(),),
        attribution=CornellAttribution(
            enabled=True,
            mode="auto",
            text="© 2026 Enrique Díaz Ocampo · Material docente",
            author="Enrique Díaz Ocampo",
            course="Python",
            year="2026",
            position="bottom_right",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="text",
            text="COCID",
            opacity=0.05,
            scale=0.4,
            position="center",
        ),
    )

    tex = renderer.generate_cornell_document_tex(document)

    assert "COCID" in tex
    assert "opacity=0.05" in tex
    assert "scale=0.4" in tex
    assert r"($(SW)+(4.25in,5.5in)$)" in tex
    assert r"\scriptsize © 2026 Enrique Díaz Ocampo · Python" in tex
    assert r"($(SE)+(-.35in,.16in)$)" in tex


def test_generate_cornell_document_tex_disabled_identity_is_absent() -> None:
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(sample_page(),),
        attribution=CornellAttribution(enabled=False, text="NO FOOTER"),
        watermark=CornellWatermark(enabled=False, type="text", text="NO WATERMARK"),
    )

    tex = renderer.generate_cornell_document_tex(document)

    assert "NO FOOTER" not in tex
    assert "NO WATERMARK" not in tex
    assert "opacity=0.05" not in tex


def test_generate_cornell_tex_contains_snippet_compatibility_layer() -> None:
    tex = renderer.generate_cornell_tex(sample_page())

    assert "Cornell compatibility layer for snippets shared with Diario LaTeX" in tex
    assert r"\usepackage{hyperref}" in tex
    assert r"\NewDocumentEnvironment{definition}{g}" in tex
    assert r"\NewDocumentEnvironment{theorem}{g}" in tex
    assert r"\NewDocumentEnvironment{dirtree}" in tex
    assert r"\RenewDocumentEnvironment{lstlisting}" in tex


def test_generate_cornell_tex_isolates_summary_region() -> None:
    tex = renderer.generate_cornell_tex(
        summary_layout_page(
            "\\begin{example}\n"
            "A poco no ocupa todo el espacio.\\\\\n"
            "Ejemplo en otra linea.\n"
            "\\end{example}"
        )
    )

    summary_clip_index = tex.index(r"\clip ($(SW)+(0,2in)$) rectangle (SE);")
    summary_heading_index = tex.index(r"\CornellSummaryHeading{Observaciones 2}")
    summary_marker_index = tex.index("% Cornell source page=1 region=summary")

    assert summary_clip_index < summary_heading_index
    assert summary_heading_index < summary_marker_index
    assert r"\begin{minipage}[t]{8.5in}" in tex
    assert r"\begin{minipage}[t]{7.55in}" in tex
    assert r"\raggedright" in tex
    assert r"\raggedleft" not in tex
    assert "anchor=north east" not in tex
    assert "align=right" not in tex
    assert "align=left" not in tex
    assert "$(SW)+(8.3in,1.72in)$" not in tex
    assert "$(SW)+(18mm,1.62in)$" not in tex
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


def test_render_cornell_pdf_compiles_href_lists_utf8_and_math(tmp_path: Path) -> None:
    if (
        shutil.which("pdflatex") is None
        or shutil.which("pdftotext") is None
        or shutil.which("pdfinfo") is None
    ):
        pytest.skip("pdflatex, pdftotext, and pdfinfo are required for href regression verification")
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(href_regression_page(),),
    )

    result = renderer.render_cornell_document(document, tmp_path, "cornell_preview")

    assert result.success, result.message
    assert result.diagnostics["fit_report"]["pages"][0]["regions"]
    assert result.pdf_path.exists()
    assert "Pages:           1" in pdfinfo_text(result.pdf_path)
    assert pdf_contains_uri(result.pdf_path, HREF_REGRESSION_URL)
    log_text = result.log_path.read_text(encoding="utf-8")
    assert "Undefined control sequence" not in log_text

    fit_tex = tmp_path / "cornell_preview_fit.tex"
    assert fit_tex.exists()
    assert r"\usepackage{hyperref}" in fit_tex.read_text(encoding="utf-8")
    fit_log = fit_tex.with_suffix(".log").read_text(encoding="utf-8")
    assert "Undefined control sequence" not in fit_log

    text = pdf_page_text(result.pdf_path, 1)
    assert "proyecto oficial de R" in text
    assert "1. ¿Qué es R" in text
    assert "2. ¿Qué es RStudio" in text
    assert "x <- c(10, 12, 9, 15)" in text
    assert "x2 + y 2 = z 2" in text
    assert "á é í ó ú ñ ¿ ¡" in text


def test_render_cornell_pdf_measures_every_shared_latex_snippet_and_rejects_overflow(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for Cornell snippet compilation")

    snippets = []
    for group in LATEX_SNIPPET_GROUPS:
        for snippet in group.snippets:
            snippets.append(f"% snippet {snippet.key}\n{snippet.snippet}")
    result = renderer.render_cornell_pdf(snippet_page("\n\n".join(snippets)), tmp_path)

    assert not result.success
    assert result.status == "overflow"
    assert "Escala necesaria" in result.message
    assert result.diagnostics["overflow_regions"][0]["page_id"] == "snippet"
    assert result.diagnostics["overflow_regions"][0]["region"] == "main"


def test_render_cornell_pdf_scales_main_independently(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for Cornell fit verification")

    result = renderer.render_cornell_pdf(overlap_regression_page(6), tmp_path)

    assert result.success, result.message
    regions = {
        region["region"]: region
        for region in result.diagnostics["fit_report"]["pages"][0]["regions"]
    }
    assert regions["cue"]["status"] == "FIT"
    assert regions["main"]["status"] == "SCALED"
    assert 0.80 <= regions["main"]["applied_scale"] < 1.0
    assert regions["summary"]["status"] == "FIT"
    assert r"\begin{adjustbox}{scale=" in result.tex_path.read_text(encoding="utf-8")


def test_render_cornell_pdf_rejects_overflow_below_minimum(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for Cornell fit verification")

    result = renderer.render_cornell_pdf(overlap_regression_page(7, page_id="p_overflow"), tmp_path)

    assert not result.success
    assert result.status == "overflow"
    assert not result.pdf_path.exists()
    overflow = result.diagnostics["overflow_regions"][0]
    assert overflow["page_id"] == "p_overflow"
    assert overflow["region"] == "main"
    assert overflow["required_scale"] < overflow["min_region_scale"]


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

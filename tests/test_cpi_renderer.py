"""Tests for the CPI landscape-letter renderer."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest

from editor.cornell import media as cornell_media
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellWatermark
from editor.cpi import renderer
from editor.cpi.layout import OVERFLOW_STATUS
from editor.cpi.layout import SCALED_STATUS
from editor.cpi.models import DEFAULT_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion


def sample_page(page_number: int = 1) -> CpiPage:
    return CpiPage(
        page_number=page_number,
        comprehension=CpiRegion(heading="Comprensión", latex="Entendí la definición."),
        production=CpiRegion(heading="Producción", latex=r"\[ a^2+b^2=c^2 \]"),
        integration=CpiRegion(heading="Integración", latex="Usarlo en el siguiente ejercicio."),
    )


def sample_document() -> CpiDocument:
    return CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CpiPage(
                page_number=2,
                comprehension=CpiRegion(heading="Comprensión", latex="Segunda comprensión."),
                production=CpiRegion(heading="Producción", latex="Segunda producción."),
                integration=CpiRegion(heading="Integración", latex="Segunda integración."),
            ),
            sample_page(1),
        ),
    )


def pdfinfo_text(pdf_path: Path) -> str:
    return subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _long_text(sentences: int) -> str:
    return " ".join(
        "Sea una propiedad estable bajo suma y producto."
        for _ in range(sentences)
    )


def _page_with_regions(
    *,
    comprehension: str = "Breve comprensión.",
    production: str = r"\[ a+b=b+a \]",
    integration: str = "Breve integración.",
    comprehension_ids: tuple[str, ...] = (),
) -> CpiPage:
    return CpiPage(
        page_number=1,
        comprehension=CpiRegion(
            heading="Comprensión",
            latex=comprehension,
            image_ids=comprehension_ids,
        ),
        production=CpiRegion(heading="Producción", latex=production),
        integration=CpiRegion(heading="Integración", latex=integration),
    )


def _fit_regions(page: CpiPage, tmp_path: Path) -> dict[str, Any]:
    fit = renderer.measure_cpi_page_fit(page, tmp_path, f"fit_{page.page_number}_{abs(hash(page))}")
    return {region.region: region for region in fit.regions}


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _tiny_png_bytes() -> bytes:
    raw_scanline = b"\x00\xcc\xdd\xff"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw_scanline))
        + _png_chunk(b"IEND", b"")
    )


def _write_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asset_id: str,
    filename: str,
) -> dict[str, Any]:
    monkeypatch.setattr(cornell_media, "PROJECT_ROOT", tmp_path)
    media_dir = tmp_path / "media" / "images"
    media_dir.mkdir(parents=True, exist_ok=True)
    source = media_dir / filename
    source.write_bytes(_tiny_png_bytes())
    return {
        "asset_id": asset_id,
        "filename": filename,
        "original_filename": filename,
        "path": source.relative_to(tmp_path).as_posix(),
        "mime_type": "image/png",
    }


def test_measure_cpi_fit_short_content_uses_scale_one(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")

    regions = _fit_regions(sample_page(), tmp_path)

    assert {region.status for region in regions.values()} == {"FIT"}
    assert {region.applied_scale for region in regions.values()} == {1.0}


def test_measure_cpi_fit_scales_only_comprehension(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")

    regions = _fit_regions(
        _page_with_regions(comprehension=_long_text(55)),
        tmp_path,
    )

    assert regions["comprehension"].status == SCALED_STATUS
    assert 0.80 <= regions["comprehension"].applied_scale < 1.0
    assert regions["production"].applied_scale == 1.0
    assert regions["integration"].applied_scale == 1.0


def test_measure_cpi_fit_scales_only_production(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")

    regions = _fit_regions(
        _page_with_regions(production=_long_text(55)),
        tmp_path,
    )

    assert regions["production"].status == SCALED_STATUS
    assert 0.80 <= regions["production"].applied_scale < 1.0
    assert regions["comprehension"].applied_scale == 1.0
    assert regions["integration"].applied_scale == 1.0


def test_measure_cpi_fit_scales_only_integration(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")

    regions = _fit_regions(
        _page_with_regions(integration=_long_text(40)),
        tmp_path,
    )

    assert regions["integration"].status == SCALED_STATUS
    assert 0.80 <= regions["integration"].applied_scale < 1.0
    assert regions["comprehension"].applied_scale == 1.0
    assert regions["production"].applied_scale == 1.0


def test_measure_cpi_fit_uses_independent_scales_for_three_regions(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")

    regions = _fit_regions(
        _page_with_regions(
            comprehension=_long_text(55),
            production=_long_text(50),
            integration=_long_text(40),
        ),
        tmp_path,
    )

    scales = {
        "comprehension": regions["comprehension"].applied_scale,
        "production": regions["production"].applied_scale,
        "integration": regions["integration"].applied_scale,
    }
    assert all(0.80 <= scale < 1.0 for scale in scales.values())
    assert len({round(scale, 3) for scale in scales.values()}) == 3


def test_measure_cpi_fit_handles_equations_and_lists(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")
    latex = r"""
    \begin{itemize}
    \item Primer criterio de ajuste.
    \item Segundo criterio con una ecuación:
    \[
      \begin{pmatrix}1 & 2\\3 & 4\end{pmatrix}
    \]
    \end{itemize}
    \begin{align}
      f(x+y) &= f(x)+f(y)\\
      f(\lambda x) &= \lambda f(x)
    \end{align}
    """

    regions = _fit_regions(_page_with_regions(production=latex), tmp_path)

    assert regions["production"].status != OVERFLOW_STATUS


def test_measure_cpi_fit_handles_text_and_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")
    asset = _write_asset(tmp_path, monkeypatch, "img-comp", "Comp.png")
    page = _page_with_regions(
        comprehension=_long_text(12),
        comprehension_ids=("img-comp",),
    )

    fit = renderer.measure_cpi_page_fit(
        page,
        tmp_path / "fit",
        "text_image",
        assets_by_id={"img-comp": asset},
    )
    regions = {region.region: region for region in fit.regions}

    assert regions["comprehension"].status == SCALED_STATUS
    assert 0.80 <= regions["comprehension"].applied_scale < 1.0
    assert regions["production"].applied_scale == 1.0
    assert regions["integration"].applied_scale == 1.0


def test_measure_cpi_document_fit_is_independent_per_page(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")
    first = _page_with_regions(comprehension=_long_text(55))
    second = CpiPage(
        page_number=2,
        comprehension=CpiRegion(heading="Comprensión", latex="Breve."),
        production=CpiRegion(heading="Producción", latex=_long_text(55)),
        integration=CpiRegion(heading="Integración", latex=_long_text(40)),
    )
    document = CpiDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(first, second))

    result = renderer.render_cpi_document(document, tmp_path, "multipage_fit")

    assert result.success, result.message
    pages = result.diagnostics["fit_report"]["pages"]
    page_1 = {region["region"]: region for region in pages[0]["regions"]}
    page_2 = {region["region"]: region for region in pages[1]["regions"]}
    assert page_1["comprehension"]["status"] == SCALED_STATUS
    assert page_1["production"]["applied_scale"] == 1.0
    assert page_2["comprehension"]["applied_scale"] == 1.0
    assert page_2["production"]["status"] == SCALED_STATUS
    assert page_2["integration"]["status"] == SCALED_STATUS


def test_render_cpi_document_scales_regions_without_overflow(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for CPI PDF verification")
    page = _page_with_regions(
        comprehension=_long_text(55),
        production=_long_text(50),
        integration=_long_text(40),
    )
    document = CpiDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(page,))

    result = renderer.render_cpi_document(document, tmp_path, "scaled_regions")

    assert result.success, result.message
    assert result.status in {"success", "success_with_warnings"}
    assert "Pages:           1" in pdfinfo_text(result.pdf_path)
    source = result.tex_path.read_text(encoding="utf-8")
    assert source.count(r"\begin{adjustbox}{scale=") == 3


def test_render_cpi_document_rejects_overflow_below_minimum(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for CPI fit verification")
    page = _page_with_regions(comprehension=_long_text(70))
    document = CpiDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(page,))

    result = renderer.render_cpi_document(document, tmp_path, "overflow")

    assert not result.success
    assert result.status == "overflow"
    overflow = result.diagnostics["overflow_regions"][0]
    assert overflow["region"] == "comprehension"
    assert overflow["required_scale"] < overflow["min_region_scale"]


def test_generate_cpi_tex_contains_three_regions() -> None:
    tex = renderer.generate_cpi_tex(sample_page())

    assert "Entendí la definición." in tex
    assert r"\[ a^2+b^2=c^2 \]" in tex
    assert "Usarlo en el siguiente ejercicio." in tex
    assert "% CPI source page=1 region=comprehension" in tex
    assert "% CPI source page=1 region=production" in tex
    assert "% CPI source page=1 region=integration" in tex


def test_generate_cpi_tex_contains_expected_geometry() -> None:
    tex = renderer.generate_cpi_tex(sample_page())

    assert "letterpaper" in tex
    assert "landscape" in tex
    assert "margin=0pt" in tex
    assert r"\setlength{\alturaIntegracion}{2.40in}" in tex
    assert r"\setlength{\mitadPagina}{5.50in}" in tex
    assert r"($(SW)+(0,\alturaIntegracion)$) -- ($(SE)+(0,\alturaIntegracion)$)" in tex
    assert r"($(SW)+(\mitadPagina,\alturaIntegracion)$) -- ($(NW)+(\mitadPagina,0)$)" in tex
    assert "Zona de Comprensión" in tex
    assert "Zona de Producción" in tex
    assert "Zona de Integración" in tex


def test_generate_cpi_tex_contains_zone_title_colors() -> None:
    tex = renderer.generate_cpi_tex(sample_page())

    assert r"\definecolor{CPIComprehension}{HTML}{2E7D32}" in tex
    assert r"\definecolor{CPIProduction}{HTML}{C2185B}" in tex
    assert r"\definecolor{CPIIntegration}{HTML}{1565C0}" in tex
    assert r"{CPIComprehension}" in tex
    assert r"{CPIProduction}" in tex
    assert r"\CPIIntegrationTitle" in tex


def test_generate_cpi_tex_renders_region_images_without_mixing() -> None:
    page = CpiPage(
        page_number=1,
        comprehension=CpiRegion(heading="Comprensión", latex="C", image_ids=("img-comp",)),
        production=CpiRegion(heading="Producción", latex="P", image_ids=("img-prod",)),
        integration=CpiRegion(heading="Integración", latex="I", image_ids=("img-int",)),
    )
    tex = renderer.generate_cpi_document_tex(
        CpiDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(page,)),
        asset_paths_by_id={
            "img-comp": "cpi_assets/media/comp.png",
            "img-prod": "cpi_assets/media/prod.png",
            "img-int": "cpi_assets/media/int.png",
        },
    )

    comp_index = tex.index("% CPI source page=1 region=comprehension")
    prod_index = tex.index("% CPI source page=1 region=production")
    int_index = tex.index("% CPI source page=1 region=integration")
    assert comp_index < tex.index("cpi_assets/media/comp.png") < prod_index
    assert prod_index < tex.index("cpi_assets/media/prod.png") < int_index
    assert int_index < tex.index("cpi_assets/media/int.png")


def test_generate_cpi_document_tex_orders_pages() -> None:
    tex = renderer.generate_cpi_document_tex(sample_document())

    assert tex.index("Entendí la definición.") < tex.index("Segunda comprensión.")
    assert tex.count(r"\null") == 2


def test_generate_cpi_document_tex_contains_text_watermark_and_footer() -> None:
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(sample_page(),),
        attribution=CornellAttribution(
            enabled=True,
            mode="auto",
            author="Enrique Díaz Ocampo",
            course="Python",
            year="2026",
            position="bottom_right",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="text",
            text="COCID",
            opacity=0.08,
            scale=0.5,
            position="center",
        ),
    )

    tex = renderer.generate_cpi_document_tex(document)

    assert "COCID" in tex
    assert "© 2026 Enrique Díaz Ocampo · Python" in tex
    assert "opacity=0.08" in tex
    assert "scale=0.5" in tex
    assert "($(SW)+(5.50in,4.25in)$)" in tex
    assert tex.index("COCID") < tex.index("% CPI source page=1 region=comprehension")


def test_generate_cpi_document_tex_disabled_identity_is_absent() -> None:
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(sample_page(),),
        attribution=CornellAttribution(enabled=False, text="NO FOOTER"),
        watermark=CornellWatermark(enabled=False, type="text", text="NO WATERMARK"),
    )

    tex = renderer.generate_cpi_document_tex(document)

    assert "NO FOOTER" not in tex
    assert "NO WATERMARK" not in tex


def test_generate_cpi_document_tex_contains_image_watermark_path() -> None:
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(sample_page(),),
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id="watermark-logo",
            opacity=0.12,
            scale=0.35,
            position="top_right",
        ),
    )

    tex = renderer.generate_cpi_document_tex(
        document,
        asset_paths_by_id={"watermark-logo": "cpi_assets/media/logo.png"},
    )

    assert "cpi_assets/media/logo.png" in tex
    assert r"width=0.35\paperwidth" in tex
    assert "opacity=0.12" in tex


def test_render_cpi_document_compiles_landscape_letter_multipage(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for CPI PDF verification")

    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=sample_document().pages,
        attribution=CornellAttribution(
            enabled=True,
            mode="custom",
            text="Material CPI",
            position="center",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="text",
            text="CPI",
            opacity=0.04,
            scale=0.4,
            position="center",
        ),
    )

    result = renderer.render_cpi_document(document, tmp_path, "cpi_test")

    assert result.success, result.message
    assert result.pdf_path.exists()
    info = pdfinfo_text(result.pdf_path)
    assert "Pages:           2" in info
    assert "792 x 612 pts" in info

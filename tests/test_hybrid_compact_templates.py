"""Regression coverage for the opt-in compact Cornell and CPI templates."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from editor.cornell.layout import default_cornell_fit_report
from editor.cornell.models import DEFAULT_TEMPLATE_ID as CORNELL_DEFAULT_TEMPLATE_ID
from editor.cornell.models import HYBRID_COMPACT_TEMPLATE_ID as CORNELL_HYBRID_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import resolve_template_id as resolve_cornell_template_id
from editor.cornell.models import template_ids as cornell_template_ids
from editor.cornell.project_export import export_cornell_project
from editor.cornell.renderer import generate_cornell_document_tex
from editor.cornell.renderer import render_cornell_document
from editor.cpi.layout import default_cpi_fit_report
from editor.cpi.models import DEFAULT_TEMPLATE_ID as CPI_DEFAULT_TEMPLATE_ID
from editor.cpi.models import HYBRID_COMPACT_TEMPLATE_ID as CPI_HYBRID_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.models import resolve_template_id as resolve_cpi_template_id
from editor.cpi.models import template_ids as cpi_template_ids
from editor.cpi.project_export import export_cpi_project
from editor.cpi.renderer import generate_cpi_document_tex
from editor.cpi.renderer import render_cpi_document


def _cornell_document(template_id: str = CORNELL_HYBRID_TEMPLATE_ID) -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=template_id,
        pages=(
            CornellPage(
                page_id="hybrid-cornell-page",
                order=1,
                cue=CornellRegion(
                    heading="Preguntas clave",
                    latex=(
                        r"\begin{itemize}\item ¿Qué preserva la continuidad?"
                        r"\item ¿Cómo se interpreta $\nabla f$?\end{itemize}"
                    ),
                ),
                main=CornellRegion(
                    heading="Contenido principal",
                    latex=(
                        r"\begin{definition}[Continuidad] Una función preserva límites."
                        r"\end{definition}\[\int_0^1x^2\,dx=\frac13.\]"
                    ),
                ),
                summary=CornellRegion(
                    heading="Síntesis",
                    latex="La síntesis breve no reserva una franja fija.",
                ),
            ),
        ),
    )


def _cpi_document(template_id: str = CPI_HYBRID_TEMPLATE_ID) -> CpiDocument:
    return CpiDocument(
        schema_version=1,
        template_id=template_id,
        pages=(
            CpiPage(
                page_number=1,
                comprehension=CpiRegion(
                    heading="Comprensión",
                    latex=r"\textbf{Idea.} $\nabla f$ resume la variación local.",
                ),
                production=CpiRegion(
                    heading="Producción",
                    latex=r"Calcula $\sum_{i=1}^{n}i$ y explica el resultado.",
                ),
                integration=CpiRegion(
                    heading="Integración",
                    latex="Una integración breve conserva una altura natural.",
                ),
            ),
        ),
    )


def _compile_project_notas(project_dir: Path) -> None:
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "Notas.tex"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_compact_template_registries_are_opt_in_and_unknown_ids_fall_back_safely() -> None:
    """Keep the compact IDs opt-in and preserve persisted legacy values."""
    assert cornell_template_ids() == (CORNELL_DEFAULT_TEMPLATE_ID, CORNELL_HYBRID_TEMPLATE_ID)
    assert cpi_template_ids() == (CPI_DEFAULT_TEMPLATE_ID, CPI_HYBRID_TEMPLATE_ID)
    assert resolve_cornell_template_id("unknown") == CORNELL_DEFAULT_TEMPLATE_ID
    assert resolve_cpi_template_id("unknown") == CPI_DEFAULT_TEMPLATE_ID

    legacy_cornell = _cornell_document(template_id="legacy-cornell-template")
    legacy_cpi = _cpi_document(template_id="legacy-cpi-template")
    assert legacy_cornell.to_dict()["template_id"] == "legacy-cornell-template"
    assert legacy_cpi.to_dict()["template_id"] == "legacy-cpi-template"


def test_hybrid_templates_use_continuous_semantic_regions() -> None:
    """Use continuous, colour-coded sheets for Cornell and CPI."""
    cornell_tex = generate_cornell_document_tex(_cornell_document())
    cpi_tex = generate_cpi_document_tex(_cpi_document())

    assert "CornellHybridCard" not in cornell_tex
    assert "CornellHybridCue" in cornell_tex
    assert "CornellHybridSummarySoft" in cornell_tex
    assert r"\fill[CornellHybridCueSoft,opacity=.55]" in cornell_tex
    assert r"\fill[CornellHybridMainSoft,opacity=.30]" in cornell_tex
    assert r"\fill[CornellHybridSummarySoft,opacity=.65]" in cornell_tex
    assert r"\foreach \y in {2.35,2.70,...,10.55}" in cornell_tex
    assert r"\draw[line width=.65pt] ($(SW)+(0,2in)$)" in cornell_tex
    assert "lineas.png" not in cornell_tex
    assert "CPIHybridCard" not in cpi_tex
    assert "CPIHybridComprehensionSoft" in cpi_tex
    assert "CPIHybridIntegrationSoft" in cpi_tex
    assert r"\fill[CPIHybridComprehensionSoft,opacity=.62]" in cpi_tex
    assert r"\fill[CPIHybridProductionSoft,opacity=.50]" in cpi_tex
    assert r"\fill[CPIHybridIntegrationSoft,opacity=.75]" in cpi_tex
    assert r"\draw[line width=.65pt] ($(SW)+(0,2.4in)$)" in cpi_tex
    assert "Valor epistémico" in cpi_tex
    assert "Valor pragmático" in cpi_tex


def test_scaled_hybrid_region_keeps_its_paragraph_width() -> None:
    """Scaling a long hybrid region must not turn its paragraph into one wide box."""
    document = _cornell_document()
    base_report = default_cornell_fit_report(document)
    page_report = base_report.pages[0]
    scaled_regions = tuple(
        replace(region, applied_scale=0.84)
        if region.region == "main"
        else region
        for region in page_report.regions
    )
    fit_report = replace(base_report, pages=(replace(page_report, regions=scaled_regions),))

    tex = generate_cornell_document_tex(document, fit_report=fit_report)

    scaled_main = tex[tex.index(r"\begin{adjustbox}{scale=0.840000}") :]
    assert r"\begin{minipage}[t]{5.68in}" in scaled_main
    assert scaled_main.index(r"\begin{minipage}[t]{5.68in}") < scaled_main.index(
        r"% Cornell source page=1 region=main"
    )


def test_scaled_cpi_hybrid_region_keeps_its_paragraph_width() -> None:
    """Scaling a CPI region must retain its constrained paragraph width."""
    document = _cpi_document()
    base_report = default_cpi_fit_report(document)
    page_report = base_report.pages[0]
    scaled_regions = tuple(
        replace(region, applied_scale=0.84)
        if region.region == "production"
        else region
        for region in page_report.regions
    )
    fit_report = replace(base_report, pages=(replace(page_report, regions=scaled_regions),))

    tex = generate_cpi_document_tex(document, fit_report=fit_report)

    scaled_production = tex[tex.index(r"\begin{adjustbox}{scale=0.840000}") :]
    assert r"\begin{minipage}[t]{5.04in}" in scaled_production
    assert scaled_production.index(r"\begin{minipage}[t]{5.04in}") < scaled_production.index(
        r"% CPI source page=1 region=production"
    )


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is required for template rendering")
def test_hybrid_templates_render_and_export_the_same_tex_style(tmp_path: Path) -> None:
    """Compile previews and editable projects from the same compact renderer path."""
    cornell = _cornell_document()
    cpi = _cpi_document()

    cornell_render = render_cornell_document(cornell, tmp_path / "cornell_render", "hybrid")
    cpi_render = render_cpi_document(cpi, tmp_path / "cpi_render", "hybrid")
    assert cornell_render.success, cornell_render.message
    assert cpi_render.success, cpi_render.message
    assert "Overfull \\vbox" not in cornell_render.log_path.read_text(encoding="utf-8", errors="replace")
    assert "Overfull \\vbox" not in cpi_render.log_path.read_text(encoding="utf-8", errors="replace")

    cornell_project = export_cornell_project(cornell, {"title": "Cornell híbrido"}, tmp_path / "cornell_project")
    cpi_project = export_cpi_project(cpi, {"title": "CPI híbrido"}, tmp_path / "cpi_project")
    assert r"\fill[CornellHybridCueSoft,opacity=.55]" in (
        cornell_project.project_dir / "Notas.tex"
    ).read_text(encoding="utf-8")
    assert r"\fill[CPIHybridComprehensionSoft,opacity=.62]" in (
        cpi_project.project_dir / "Notas.tex"
    ).read_text(encoding="utf-8")
    _compile_project_notas(cornell_project.project_dir)
    _compile_project_notas(cpi_project.project_dir)

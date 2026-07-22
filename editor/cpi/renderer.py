"""Renderer for CPI landscape-letter notes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from string import Template
from textwrap import dedent
from typing import Any

from editor.cornell.latex_compat import cornell_latex_compat_preamble
from editor.cpi.identity import cpi_attribution_latex
from editor.cpi.identity import cpi_watermark_latex
from editor.cpi.layout import REGION_GEOMETRY
from editor.cpi.layout import CpiFitReport
from editor.cpi.layout import CpiLayoutError
from editor.cpi.layout import CpiPageFitReport
from editor.cpi.layout import cpi_region_box_latex
from editor.cpi.layout import default_cpi_fit_report
from editor.cpi.layout import measure_cpi_document_fit
from editor.cpi.media import latex_uses_svg_paths
from editor.cpi.media import prepare_cpi_image_assets
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from exporters_latex.latex_compile import run_latex_until_stable
from mathkb_config import PROJECT_ROOT

TEMPLATE_PATH = PROJECT_ROOT / "templates_latex" / "cpi_landscape_letter_v1.tex"
ASSETS_DIRNAME = "cpi_assets"
SOURCE_MARKER_PATTERN = re.compile(r"% CPI source page=(?P<page>\d+) region=(?P<region>\w+)")
LATEX_FILE_LINE_PATTERN = re.compile(r"(?P<file>[^\s:]+\.tex):(?P<line>\d+):")
LATEX_ERROR_PATTERN = re.compile(r"LaTeX Error:\s*(?P<message>.+)")
REGION_LABELS = {
    "comprehension": "Comprensión",
    "production": "Producción",
    "integration": "Integración",
}


@dataclass(frozen=True, slots=True)
class CpiRenderResult:
    """Result object returned by the CPI PDF renderer."""

    success: bool
    status: str
    tex_path: Path
    pdf_path: Path
    log_path: Path
    message: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _slugify_output_name(output_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(output_name).stem or output_name)
    return slug.strip("._") or "cpi_note"


def _escape_latex_text(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def _template_source() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"CPI template not found: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _template_variables(*, include_svg: bool, pages: str) -> dict[str, str]:
    return {
        "snippet_compat": cornell_latex_compat_preamble(),
        "svg_package": "\n\\usepackage{svg}" if include_svg else "",
        "pages": pages,
    }


def _latex_preamble(*, include_svg: bool = False) -> str:
    source = Template(_template_source()).substitute(
        _template_variables(include_svg=include_svg, pages="")
    )
    preamble, _separator, _tail = source.partition(r"\begin{document}")
    return preamble.strip()


def cpi_latex_preamble(*, include_svg: bool = False) -> str:
    """Return the standalone CPI LaTeX preamble used for fit measurement."""
    return _latex_preamble(include_svg=include_svg)


def _scaled_region_latex(region_box: str, scale: float) -> str:
    if scale >= 1.0:
        return region_box
    return dedent(
        rf"""
        \begin{{adjustbox}}{{scale={scale:.6f}}}
        {region_box}
        \end{{adjustbox}}
        """
    ).strip()


def _region_node_latex(
    *,
    page: CpiPage,
    region_name: str,
    page_number: int,
    fit_report: CpiFitReport,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    geometry = REGION_GEOMETRY[region_name]
    scale = fit_report.region_scale(page_number, region_name)
    region_box = cpi_region_box_latex(
        page,
        region_name,
        page_number=page_number,
        asset_paths_by_id=asset_paths_by_id,
    )
    region_content = _scaled_region_latex(region_box, scale)
    return dedent(
        rf"""
        \begin{{scope}}
          \clip {geometry.clip_top_left} rectangle {geometry.clip_bottom_right};
          \node[anchor=north west, inner sep=0pt] at {geometry.anchor} {{
            {region_content}
          }};
        \end{{scope}}
        """
    ).strip()


def _cpi_page_body(
    document: CpiDocument,
    page: CpiPage,
    *,
    page_number: int,
    fit_report: CpiFitReport,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    comprehension_heading = _escape_latex_text(page.comprehension.heading or "Comprensión")
    production_heading = _escape_latex_text(page.production.heading or "Producción")
    comprehension_node = _region_node_latex(
        page=page,
        region_name="comprehension",
        page_number=page_number,
        fit_report=fit_report,
        asset_paths_by_id=asset_paths_by_id,
    )
    production_node = _region_node_latex(
        page=page,
        region_name="production",
        page_number=page_number,
        fit_report=fit_report,
        asset_paths_by_id=asset_paths_by_id,
    )
    integration_node = _region_node_latex(
        page=page,
        region_name="integration",
        page_number=page_number,
        fit_report=fit_report,
        asset_paths_by_id=asset_paths_by_id,
    )
    return dedent(
        rf"""
        \null

        \begin{{tikzpicture}}[remember picture,overlay]
          \coordinate (SW) at (current page.south west);
          \coordinate (SE) at (current page.south east);
          \coordinate (NW) at (current page.north west);
          \coordinate (NE) at (current page.north east);

          {cpi_watermark_latex(
              document,
              asset_paths_by_id=asset_paths_by_id,
              page_number=page_number,
          )}

          \draw[line width=0.45pt] ($(SW)+(0,\alturaIntegracion)$) -- ($(SE)+(0,\alturaIntegracion)$);
          \draw[line width=0.45pt] ($(SW)+(\mitadPagina,\alturaIntegracion)$) -- ($(NW)+(\mitadPagina,0)$);

          \node[
            anchor=north,
            inner sep=0pt,
            text width=5.50in,
            align=center,
            yshift=-\bajadaTitulos
          ] at ($(NW)+(2.75in,0)$)
          {{\CPITopTitle{{Zona de {comprehension_heading}}}{{(valor epistémico)}}{{CPIComprehension}}}};

          \node[
            anchor=north,
            inner sep=0pt,
            text width=5.50in,
            align=center,
            yshift=-\bajadaTitulos
          ] at ($(NW)+(8.25in,0)$)
          {{\CPITopTitle{{Zona de {production_heading}}}{{(valor pragmático)}}{{CPIProduction}}}};

          \node[
            anchor=north,
            inner sep=0pt,
            align=center,
            yshift=-\bajadaIntegracion
          ] at ($(SW)+(5.50in,\alturaIntegracion)$)
          {{\CPIIntegrationTitle}};

          {comprehension_node}

          {production_node}

          {integration_node}

          {cpi_attribution_latex(document)}
        \end{{tikzpicture}}
        """
    ).strip() + "\n"


def generate_cpi_document_tex(
    document: CpiDocument,
    *,
    fit_report: CpiFitReport | None = None,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    """Generate a single LaTeX document for all CPI pages in order."""
    pages = document.ordered_pages()
    if not pages:
        raise ValueError("CpiDocument must contain at least one page")
    if fit_report is None:
        fit_report = default_cpi_fit_report(document)
    page_bodies = [
        _cpi_page_body(
            document,
            page,
            page_number=index,
            fit_report=fit_report,
            asset_paths_by_id=asset_paths_by_id,
        ).strip()
        for index, page in enumerate(pages, start=1)
    ]
    asset_paths = dict(asset_paths_by_id or {})
    return Template(_template_source()).substitute(
        _template_variables(
            include_svg=latex_uses_svg_paths(asset_paths),
            pages="\n\\clearpage\n".join(page_bodies),
        )
    )


def generate_cpi_tex(
    page: CpiPage,
    *,
    fit_report: CpiFitReport | None = None,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    """Generate the one-page LaTeX source for a CPI page."""
    document = CpiDocument(schema_version=1, template_id="source_generation", pages=(page,))
    return generate_cpi_document_tex(
        document,
        fit_report=fit_report,
        asset_paths_by_id=asset_paths_by_id,
    )


def _prepare_output_dir(output_dir: str | Path) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def write_cpi_document_tex(
    document: CpiDocument,
    output_dir: str | Path,
    output_name: str,
    *,
    fit_report: CpiFitReport | None = None,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> Path:
    """Write a complete CPI document source file."""
    output_path = _prepare_output_dir(output_dir)
    image_paths = prepare_cpi_image_assets(
        document,
        output_path,
        assets_dirname=ASSETS_DIRNAME,
        db=db,
        assets_by_id=assets_by_id,
    )
    tex_path = output_path / f"{_slugify_output_name(output_name)}.tex"
    tex_path.write_text(
        generate_cpi_document_tex(
            document,
            fit_report=fit_report,
            asset_paths_by_id=image_paths,
        ),
        encoding="utf-8",
    )
    return tex_path


def _line_number_from_diagnostics(diagnostics: Mapping[str, Any]) -> int | None:
    text = "\n".join(
        str(diagnostics.get(key) or "")
        for key in ("log_excerpt", "stderr", "stdout", "log_text")
    )
    file_line_match = LATEX_FILE_LINE_PATTERN.search(text)
    if file_line_match:
        return int(file_line_match.group("line"))
    line_match = re.search(r"\bl\.(?P<line>\d+)\b", text)
    if line_match:
        return int(line_match.group("line"))
    return None


def _latex_error_from_diagnostics(diagnostics: Mapping[str, Any]) -> str:
    text = "\n".join(
        str(diagnostics.get(key) or "")
        for key in ("log_excerpt", "stderr", "stdout", "log_text")
    )
    latex_match = LATEX_ERROR_PATTERN.search(text)
    if latex_match:
        return latex_match.group("message").strip()
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("!") and len(clean) > 1:
            return clean.lstrip("!").strip()
    return "PDF generation failed."


def _source_region_for_line(tex_path: Path, line_number: int | None) -> tuple[int, str] | None:
    if line_number is None or not tex_path.exists():
        return None
    source = tex_path.read_text(encoding="utf-8", errors="replace").splitlines()
    markers: list[tuple[int, int, str]] = []
    for index, line in enumerate(source, start=1):
        marker = SOURCE_MARKER_PATTERN.search(line)
        if marker:
            markers.append((index, int(marker.group("page")), marker.group("region")))
    selected = None
    for marker_line, page_number, region in markers:
        if marker_line <= line_number:
            selected = (page_number, region)
        else:
            break
    return selected


def summarize_cpi_latex_failure(tex_path: Path, diagnostics: Mapping[str, Any]) -> str:
    """Build a short, UI-friendly LaTeX failure summary for CPI PDFs."""
    error = _latex_error_from_diagnostics(diagnostics)
    region = _source_region_for_line(tex_path, _line_number_from_diagnostics(diagnostics))
    if region is None:
        return error
    page_number, region_name = region
    region_label = REGION_LABELS.get(region_name, region_name)
    return f"Error LaTeX en pagina {page_number}, region {region_label}: {error}"


def cpi_latex_full_log(result: CpiRenderResult) -> str:
    """Return the complete LaTeX log when available, falling back to diagnostics/message."""
    for key in ("log_text", "log_excerpt", "stderr", "stdout"):
        value = result.diagnostics.get(key)
        if value:
            return str(value)
    return result.message


def _fit_overflow_message(fit_report: CpiFitReport) -> str:
    overflow_regions = fit_report.overflow_regions()
    if not overflow_regions:
        return "El ajuste CPI no pudo completarse."
    page_report, region = overflow_regions[0]
    lines = [
        f"Página {page_report.page_number} · {region.label}",
        f"Escala necesaria: {region.required_scale:.2f}",
        f"Escala mínima: {fit_report.min_region_scale:.2f}",
    ]
    if len(overflow_regions) > 1:
        lines.append(f"Regiones con overflow: {len(overflow_regions)}")
    return "\n".join(lines)


def _fit_overflow_diagnostics(fit_report: CpiFitReport) -> dict[str, Any]:
    return {
        "fit_report": fit_report.to_dict(),
        "overflow_regions": [
            {
                "page_number": page.page_number,
                "region": region.region,
                "label": region.label,
                "required_scale": region.required_scale,
                "min_region_scale": fit_report.min_region_scale,
            }
            for page, region in fit_report.overflow_regions()
        ],
    }


def _remove_stale_pdf(pdf_path: Path) -> None:
    try:
        if pdf_path.exists():
            pdf_path.unlink()
    except OSError:
        pass


def _preflight_cpi_fit(
    document: CpiDocument,
    output_path: Path,
    output_name: str,
    *,
    asset_paths_by_id: Mapping[str, str],
) -> CpiFitReport:
    return measure_cpi_document_fit(
        document,
        output_path,
        output_name,
        latex_preamble=_latex_preamble(include_svg=latex_uses_svg_paths(dict(asset_paths_by_id))),
        asset_paths_by_id=asset_paths_by_id,
    )


def measure_cpi_page_fit(
    page: CpiPage,
    output_dir: str | Path,
    output_name: str,
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> CpiPageFitReport:
    """Measure all regions in one CPI page using the renderer preflight."""
    document = CpiDocument(schema_version=1, template_id="single_page_fit", pages=(page,))
    output_path = _prepare_output_dir(output_dir)
    image_paths = prepare_cpi_image_assets(
        document,
        output_path,
        assets_dirname=ASSETS_DIRNAME,
        db=db,
        assets_by_id=assets_by_id,
    )
    fit_report = _preflight_cpi_fit(
        document,
        output_path,
        output_name,
        asset_paths_by_id=image_paths,
    )
    return fit_report.pages[0]


def _compile_cpi_tex(tex_path: Path, output_path: Path) -> CpiRenderResult:
    pdf_path = tex_path.with_suffix(".pdf")
    log_path = tex_path.with_suffix(".log")
    command = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        tex_path.name,
    ]
    diagnostics = run_latex_until_stable(
        command,
        cwd=output_path,
        tex_file=tex_path.name,
        pdf_path=pdf_path,
        log_path=log_path,
    )
    status = str(diagnostics.get("status") or "failed")
    success = status in {"success", "success_with_warnings"}
    if success:
        message = "PDF generated successfully."
    else:
        message = summarize_cpi_latex_failure(tex_path, diagnostics)
    return CpiRenderResult(
        success=success,
        status=status,
        tex_path=tex_path,
        pdf_path=pdf_path,
        log_path=log_path,
        message=message,
        diagnostics=diagnostics,
    )


def render_cpi_document(
    document: CpiDocument,
    output_dir: str | Path,
    output_name: str,
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> CpiRenderResult:
    """Render all CPI pages into one LaTeX document and one PDF."""
    output_path = Path(output_dir)
    tex_path = output_path / f"{_slugify_output_name(output_name)}.tex"
    pdf_path = tex_path.with_suffix(".pdf")
    log_path = tex_path.with_suffix(".log")
    warnings: list[str] = []

    try:
        output_path = _prepare_output_dir(output_path)
        image_paths = prepare_cpi_image_assets(
            document,
            output_path,
            assets_dirname=ASSETS_DIRNAME,
            db=db,
            assets_by_id=assets_by_id,
            warnings=warnings,
        )
        fit_report = _preflight_cpi_fit(
            document,
            output_path,
            output_name,
            asset_paths_by_id=image_paths,
        )
        if fit_report.has_overflow:
            _remove_stale_pdf(pdf_path)
            return CpiRenderResult(
                success=False,
                status="overflow",
                tex_path=tex_path,
                pdf_path=pdf_path,
                log_path=log_path,
                message=_fit_overflow_message(fit_report),
                diagnostics={
                    **_fit_overflow_diagnostics(fit_report),
                    "warnings": warnings,
                },
            )
        tex_path.write_text(
            generate_cpi_document_tex(
                document,
                fit_report=fit_report,
                asset_paths_by_id=image_paths,
            ),
            encoding="utf-8",
        )
        result = _compile_cpi_tex(tex_path, output_path)
        result.diagnostics["fit_report"] = fit_report.to_dict()
        result.diagnostics["warnings"] = warnings
        return result
    except CpiLayoutError as exc:
        return CpiRenderResult(
            success=False,
            status="failed",
            tex_path=tex_path,
            pdf_path=pdf_path,
            log_path=log_path,
            message=str(exc),
            diagnostics={**exc.diagnostics, "warnings": warnings},
        )
    except Exception as exc:
        return CpiRenderResult(
            success=False,
            status="failed",
            tex_path=tex_path,
            pdf_path=pdf_path,
            log_path=log_path,
            message=str(exc),
            diagnostics={"exception_type": type(exc).__name__, "warnings": warnings},
        )

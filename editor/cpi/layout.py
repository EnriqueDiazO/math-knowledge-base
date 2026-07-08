"""Preflight layout measurement for CPI PDF regions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

from editor.cornell.layout import FIT_STATUS
from editor.cornell.layout import MIN_REGION_SCALE
from editor.cornell.layout import OVERFLOW_STATUS
from editor.cornell.layout import SCALE_EPSILON
from editor.cornell.layout import SCALED_STATUS
from editor.cornell.layout import _normalize_min_region_scale
from editor.cornell.layout import compute_region_fit
from editor.cornell.layout import point_value_from_sp
from editor.cpi.media import render_cpi_region_latex
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from exporters_latex.latex_compile import extract_latex_fatal_errors
from exporters_latex.latex_compile import output_tail
from exporters_latex.latex_compile import read_diagnostic_text
from exporters_latex.latex_compile import run_latex_command

REGION_ORDER = ("comprehension", "production", "integration")
REGION_LABELS = {
    "comprehension": "Comprensión",
    "production": "Producción",
    "integration": "Integración",
}
MEASURE_PATTERN = re.compile(
    r"CPI_FIT\s+"
    r"p=(?P<page_index>\d+)\s+"
    r"r=(?P<region>comprehension|production|integration)\s+"
    r"nw=(?P<natural_width_sp>\d+)\s+"
    r"nh=(?P<natural_height_sp>\d+)\s+"
    r"aw=(?P<available_width_sp>\d+)\s+"
    r"ah=(?P<available_height_sp>\d+)"
)


@dataclass(frozen=True, slots=True)
class CpiRegionGeometry:
    """Physical page rectangle and content anchor for a CPI region."""

    region: str
    clip_top_left: str
    clip_bottom_right: str
    anchor: str
    width: str
    available_width: str
    available_height: str
    footer_available_height: str | None = None


REGION_GEOMETRY: dict[str, CpiRegionGeometry] = {
    "comprehension": CpiRegionGeometry(
        region="comprehension",
        clip_top_left="(NW)",
        clip_bottom_right=r"($(SW)+(5.50in,\alturaIntegracion)$)",
        anchor=r"($(NW)+(0.20in,-0.72in)$)",
        width="5.12in",
        available_width="5.12in",
        available_height="5.38in",
    ),
    "production": CpiRegionGeometry(
        region="production",
        clip_top_left=r"($(NW)+(5.50in,0)$)",
        clip_bottom_right=r"($(SE)+(0,\alturaIntegracion)$)",
        anchor=r"($(NW)+(5.70in,-0.72in)$)",
        width="5.12in",
        available_width="5.12in",
        available_height="5.38in",
    ),
    "integration": CpiRegionGeometry(
        region="integration",
        clip_top_left=r"($(SW)+(0,\alturaIntegracion)$)",
        clip_bottom_right="(SE)",
        anchor=r"($(SW)+(0.25in,1.86in)$)",
        width="10.50in",
        available_width="10.50in",
        available_height="1.86in",
        footer_available_height="1.68in",
    ),
}


@dataclass(frozen=True, slots=True)
class CpiRegionFitResult:
    """Measured fit for one CPI region."""

    region: str
    natural_width: float
    natural_height: float
    available_width: float
    available_height: float
    required_scale: float
    applied_scale: float
    status: str

    @property
    def label(self) -> str:
        """Return a display label for this region."""
        return REGION_LABELS.get(self.region, self.region)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the fit result for UI diagnostics."""
        return {
            "region": self.region,
            "label": self.label,
            "natural_width": self.natural_width,
            "natural_height": self.natural_height,
            "available_width": self.available_width,
            "available_height": self.available_height,
            "required_scale": self.required_scale,
            "applied_scale": self.applied_scale,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class CpiPageFitReport:
    """Measured fit report for one CPI page."""

    page_number: int
    regions: tuple[CpiRegionFitResult, ...]

    @property
    def has_overflow(self) -> bool:
        """Return True when any region requires an unreadably small scale."""
        return any(region.status == OVERFLOW_STATUS for region in self.regions)

    def region_scale(self, region_name: str) -> float:
        """Return the applied scale for one region, defaulting to 1.0."""
        region_fit = self.region_fit(region_name)
        if region_fit is None:
            return 1.0
        return region_fit.applied_scale

    def region_fit(self, region_name: str) -> CpiRegionFitResult | None:
        """Return the measured fit for one region."""
        for region in self.regions:
            if region.region == region_name:
                return region
        return None

    def overflow_regions(self) -> tuple[CpiRegionFitResult, ...]:
        """Return all overflowing regions for this page."""
        return tuple(region for region in self.regions if region.status == OVERFLOW_STATUS)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this page report for UI diagnostics."""
        return {
            "page_number": self.page_number,
            "regions": [region.to_dict() for region in self.regions],
        }


@dataclass(frozen=True, slots=True)
class CpiFitReport:
    """Measured fit report for all pages in a CPI document."""

    pages: tuple[CpiPageFitReport, ...]
    min_region_scale: float

    @property
    def has_overflow(self) -> bool:
        """Return True when at least one page region cannot fit legibly."""
        return any(page.has_overflow for page in self.pages)

    def page_report(self, page_number: int) -> CpiPageFitReport | None:
        """Return a page report by one-based page number."""
        for page in self.pages:
            if page.page_number == page_number:
                return page
        return None

    def region_scale(self, page_number: int, region_name: str) -> float:
        """Return the applied scale for a page region, defaulting to 1.0."""
        page = self.page_report(page_number)
        if page is None:
            return 1.0
        return page.region_scale(region_name)

    def overflow_regions(self) -> tuple[tuple[CpiPageFitReport, CpiRegionFitResult], ...]:
        """Return all page/region pairs that overflow the minimum scale."""
        return tuple(
            (page, region)
            for page in self.pages
            for region in page.regions
            if region.status == OVERFLOW_STATUS
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this fit report for UI diagnostics."""
        return {
            "min_region_scale": self.min_region_scale,
            "pages": [page.to_dict() for page in self.pages],
        }


class CpiLayoutError(RuntimeError):
    """Raised when LaTeX preflight measurement cannot be completed."""

    def __init__(self, message: str, diagnostics: Mapping[str, Any] | None = None) -> None:
        """Store a user-facing message and structured diagnostics."""
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


def cpi_region_box_latex(
    page: CpiPage,
    region_name: str,
    *,
    page_number: int,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    """Return the natural-size LaTeX box used for one CPI region."""
    geometry = REGION_GEOMETRY[region_name]
    region = getattr(page, region_name)
    body = render_cpi_region_latex(
        region,
        region_name=region_name,
        asset_paths_by_id=asset_paths_by_id,
    )
    marker = f"% CPI source page={page_number} region={region_name}"
    return dedent(
        rf"""
        \begin{{CPIZoneBody}}{{{geometry.width}}}
          {marker}
          {body}
        \end{{CPIZoneBody}}
        """
    ).strip()


def _available_height(document: CpiDocument, geometry: CpiRegionGeometry) -> str:
    if (
        geometry.footer_available_height is not None
        and document.attribution.enabled
        and document.attribution.position in {"center", "bottom_right"}
    ):
        return geometry.footer_available_height
    return geometry.available_height


def _measurement_source(
    document: CpiDocument,
    pages: tuple[CpiPage, ...],
    *,
    latex_preamble: str,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    blocks = []
    for page_index, page in enumerate(pages, start=1):
        for region_name in REGION_ORDER:
            geometry = REGION_GEOMETRY[region_name]
            region_box = cpi_region_box_latex(
                page,
                region_name,
                page_number=page_index,
                asset_paths_by_id=asset_paths_by_id,
            )
            blocks.append(
                "\n".join(
                    [
                        r"\setbox\CPIMeasureBox=\hbox{%",
                        region_box + "%",
                        r"}%",
                        (
                            rf"\typeout{{CPI_FIT p={page_index} r={region_name} "
                            r"nw=\number\wd\CPIMeasureBox\space "
                            r"nh=\number\dimexpr\ht\CPIMeasureBox+\dp\CPIMeasureBox\relax\space "
                            rf"aw=\number\dimexpr{geometry.available_width}\relax\space "
                            rf"ah=\number\dimexpr{_available_height(document, geometry)}\relax}}"
                        ),
                    ]
                )
            )
    return (
        latex_preamble
        + "\n"
        + r"\newsavebox{\CPIMeasureBox}"
        + "\n\\begin{document}\n"
        + "\n\n".join(blocks)
        + "\n\\end{document}\n"
    )


def _parse_measurements(log_text: str) -> dict[tuple[int, str], dict[str, int]]:
    measurements: dict[tuple[int, str], dict[str, int]] = {}
    for match in MEASURE_PATTERN.finditer(log_text or ""):
        page_index = int(match.group("page_index"))
        region = match.group("region")
        measurements[(page_index, region)] = {
            "natural_width_sp": int(match.group("natural_width_sp")),
            "natural_height_sp": int(match.group("natural_height_sp")),
            "available_width_sp": int(match.group("available_width_sp")),
            "available_height_sp": int(match.group("available_height_sp")),
        }
    return measurements


def _cpi_region_fit_from_cornell(
    *,
    region: str,
    natural_width_sp: int,
    natural_height_sp: int,
    available_width_sp: int,
    available_height_sp: int,
    min_region_scale: float,
) -> CpiRegionFitResult:
    fit = compute_region_fit(
        region=region,
        natural_width_sp=natural_width_sp,
        natural_height_sp=natural_height_sp,
        available_width_sp=available_width_sp,
        available_height_sp=available_height_sp,
        min_region_scale=min_region_scale,
    )
    return CpiRegionFitResult(
        region=fit.region,
        natural_width=fit.natural_width,
        natural_height=fit.natural_height,
        available_width=fit.available_width,
        available_height=fit.available_height,
        required_scale=fit.required_scale,
        applied_scale=fit.applied_scale,
        status=fit.status,
    )


def measure_cpi_document_fit(
    document: CpiDocument,
    output_dir: str | Path,
    output_name: str,
    *,
    latex_preamble: str,
    asset_paths_by_id: Mapping[str, str] | None = None,
    min_region_scale: float | None = None,
) -> CpiFitReport:
    """Measure every CPI region with LaTeX before the final render."""
    pages = document.ordered_pages()
    if not pages:
        raise ValueError("CpiDocument must contain at least one page")

    min_scale = _normalize_min_region_scale(
        MIN_REGION_SCALE if min_region_scale is None else min_region_scale
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(output_name).stem or str(output_name)).strip("._")
    safe_name = safe_name or "cpi"
    tex_path = output_path / f"{safe_name}_fit.tex"
    log_path = tex_path.with_suffix(".log")
    tex_path.write_text(
        _measurement_source(
            document,
            pages,
            latex_preamble=latex_preamble,
            asset_paths_by_id=asset_paths_by_id,
        ),
        encoding="utf-8",
    )

    command = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        tex_path.name,
    ]
    try:
        result = run_latex_command(command, cwd=output_path, tex_file=tex_path.name)
    except Exception as exc:
        raise CpiLayoutError(
            f"No se pudo medir el ajuste CPI: {exc}",
            {
                "exception_type": type(exc).__name__,
                "tex_path": str(tex_path),
                "log_path": str(log_path),
            },
        ) from exc

    log_text, log_decode = read_diagnostic_text(log_path)
    if not log_text:
        log_text = "\n".join(part for part in (result.stdout or "", result.stderr or "") if part)
    fatal_errors = extract_latex_fatal_errors(log_text)
    if result.returncode not in (0, None) or fatal_errors:
        raise CpiLayoutError(
            "No se pudo medir el ajuste CPI.",
            {
                "returncode": result.returncode,
                "fatal_errors": fatal_errors,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "log_text": log_text,
                "log_excerpt": "\n".join(log_text.splitlines()[-80:]) or output_tail(result.stdout, result.stderr),
                "tex_path": str(tex_path),
                "log_path": str(log_path),
                "log_decode": log_decode,
            },
        )

    measurements = _parse_measurements(log_text)
    page_reports: list[CpiPageFitReport] = []
    missing: list[str] = []
    for page_index, page in enumerate(pages, start=1):
        region_reports: list[CpiRegionFitResult] = []
        for region_name in REGION_ORDER:
            values = measurements.get((page_index, region_name))
            if values is None:
                missing.append(f"pagina-{page.page_number}:{region_name}")
                continue
            region_reports.append(
                _cpi_region_fit_from_cornell(
                    region=region_name,
                    min_region_scale=min_scale,
                    **values,
                )
            )
        page_reports.append(
            CpiPageFitReport(
                page_number=page_index,
                regions=tuple(region_reports),
            )
        )

    if missing:
        raise CpiLayoutError(
            "No se pudo medir el ajuste CPI: faltan regiones en el log.",
            {
                "missing_regions": missing,
                "log_text": log_text,
                "log_excerpt": "\n".join(log_text.splitlines()[-80:]),
                "tex_path": str(tex_path),
                "log_path": str(log_path),
                "log_decode": log_decode,
            },
        )

    return CpiFitReport(
        pages=tuple(page_reports),
        min_region_scale=min_scale,
    )


def default_cpi_fit_report(document: CpiDocument) -> CpiFitReport:
    """Return a scale-1 report for source generation without preflight."""
    pages = []
    for page_index, _page in enumerate(document.ordered_pages(), start=1):
        regions = []
        for region_name in REGION_ORDER:
            regions.append(
                CpiRegionFitResult(
                    region=region_name,
                    natural_width=0.0,
                    natural_height=0.0,
                    available_width=0.0,
                    available_height=0.0,
                    required_scale=1.0,
                    applied_scale=1.0,
                    status=FIT_STATUS,
                )
            )
        pages.append(
            CpiPageFitReport(
                page_number=page_index,
                regions=tuple(regions),
            )
        )
    return CpiFitReport(pages=tuple(pages), min_region_scale=MIN_REGION_SCALE)


__all__ = [
    "CpiFitReport",
    "CpiLayoutError",
    "CpiPageFitReport",
    "CpiRegionFitResult",
    "FIT_STATUS",
    "MIN_REGION_SCALE",
    "OVERFLOW_STATUS",
    "REGION_GEOMETRY",
    "REGION_LABELS",
    "REGION_ORDER",
    "SCALED_STATUS",
    "SCALE_EPSILON",
    "cpi_region_box_latex",
    "default_cpi_fit_report",
    "measure_cpi_document_fit",
    "point_value_from_sp",
]

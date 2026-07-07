"""Preflight layout measurement for Cornell PDF regions."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

from editor.cornell.media import render_cornell_region_latex
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from exporters_latex.latex_compile import extract_latex_fatal_errors
from exporters_latex.latex_compile import output_tail
from exporters_latex.latex_compile import read_diagnostic_text
from exporters_latex.latex_compile import run_latex_command

DEFAULT_MIN_REGION_SCALE = 0.80
MIN_REGION_SCALE_ENV = "CORNELL_MIN_REGION_SCALE"


def _configured_min_region_scale() -> float:
    raw_value = os.getenv(MIN_REGION_SCALE_ENV)
    if raw_value is None:
        return DEFAULT_MIN_REGION_SCALE
    try:
        return _normalize_min_region_scale(float(raw_value))
    except (TypeError, ValueError):
        return DEFAULT_MIN_REGION_SCALE


def _normalize_min_region_scale(value: float) -> float:
    scale = float(value)
    if not 0 < scale <= 1:
        raise ValueError("min_region_scale must be greater than 0 and less than or equal to 1")
    return scale


MIN_REGION_SCALE = _configured_min_region_scale()

FIT_STATUS = "FIT"
SCALED_STATUS = "SCALED"
OVERFLOW_STATUS = "OVERFLOW"
REGION_ORDER = ("cue", "main", "summary")
REGION_LABELS = {"cue": "Cue", "main": "Main", "summary": "Summary"}
SCALE_EPSILON = 1e-6
SP_PER_PT = 65536

MEASURE_PATTERN = re.compile(
    r"CORNELL_FIT\s+"
    r"p=(?P<page_index>\d+)\s+"
    r"r=(?P<region>cue|main|summary)\s+"
    r"nw=(?P<natural_width_sp>\d+)\s+"
    r"nh=(?P<natural_height_sp>\d+)\s+"
    r"aw=(?P<available_width_sp>\d+)\s+"
    r"ah=(?P<available_height_sp>\d+)"
)


@dataclass(frozen=True, slots=True)
class RegionGeometry:
    """Physical page rectangle and content anchor for a Cornell region."""

    region: str
    clip_top_left: str
    clip_bottom_right: str
    anchor: str
    outer_width: str
    available_width: str
    available_height: str


REGION_GEOMETRY: dict[str, RegionGeometry] = {
    "cue": RegionGeometry(
        region="cue",
        clip_top_left="(NW)",
        clip_bottom_right=r"($(SW)+(2.4in,2in)$)",
        anchor="(NW)",
        outer_width="2.3in",
        available_width="2.4in",
        available_height="9in",
    ),
    "main": RegionGeometry(
        region="main",
        clip_top_left=r"($(NW)+(2.4in,0)$)",
        clip_bottom_right=r"($(SE)+(0,2in)$)",
        anchor=r"($(NW)+(2.5in,0)$)",
        outer_width="6in",
        available_width="6in",
        available_height="9in",
    ),
    "summary": RegionGeometry(
        region="summary",
        clip_top_left=r"($(SW)+(0,2in)$)",
        clip_bottom_right="(SE)",
        anchor=r"($(SW)+(0,2in)$)",
        outer_width="8.5in",
        available_width="8.5in",
        available_height="2in",
    ),
}


@dataclass(frozen=True, slots=True)
class RegionFitResult:
    """Measured fit for one Cornell region."""

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
class PageFitReport:
    """Measured fit report for one Cornell page."""

    page_id: str
    page_number: int
    regions: tuple[RegionFitResult, ...]

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

    def region_fit(self, region_name: str) -> RegionFitResult | None:
        """Return the measured fit for one region."""
        for region in self.regions:
            if region.region == region_name:
                return region
        return None

    def overflow_regions(self) -> tuple[RegionFitResult, ...]:
        """Return all overflowing regions for this page."""
        return tuple(region for region in self.regions if region.status == OVERFLOW_STATUS)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this page report for UI diagnostics."""
        return {
            "page_id": self.page_id,
            "page_number": self.page_number,
            "regions": [region.to_dict() for region in self.regions],
        }


@dataclass(frozen=True, slots=True)
class CornellFitReport:
    """Measured fit report for all pages in a Cornell document."""

    pages: tuple[PageFitReport, ...]
    min_region_scale: float

    @property
    def has_overflow(self) -> bool:
        """Return True when at least one page region cannot fit legibly."""
        return any(page.has_overflow for page in self.pages)

    def page_report(self, page_number: int) -> PageFitReport | None:
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

    def overflow_regions(self) -> tuple[tuple[PageFitReport, RegionFitResult], ...]:
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


class CornellLayoutError(RuntimeError):
    """Raised when LaTeX preflight measurement cannot be completed."""

    def __init__(self, message: str, diagnostics: Mapping[str, Any] | None = None) -> None:
        """Store a user-facing message and structured diagnostics."""
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


def escape_latex_text(value: str) -> str:
    """Escape plain heading text for LaTeX."""
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


def cornell_region_box_latex(
    page: CornellPage,
    region_name: str,
    *,
    page_number: int,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    """Return the natural-size LaTeX box used for one Cornell region."""
    if region_name == "cue":
        heading = escape_latex_text(page.cue.heading)
        body = render_cornell_region_latex(
            page.cue,
            region_name="cue",
            asset_paths_by_id=asset_paths_by_id,
        )
        return dedent(
            rf"""
            \begin{{minipage}}[t]{{2.3in}}
              \vspace{{5mm}}
              \hspace*{{4mm}}\begin{{minipage}}[t]{{2.05in}}
                {{\setlength{{\fboxrule}}{{1pt}}\setlength{{\fboxsep}}{{3pt}}%
                \fcolorbox{{gray}}{{white}}{{%
                  \begin{{minipage}}{{1.93in}}
                    \CornellCueHeading{{{heading}}}
                  \end{{minipage}}%
                }}}}
                \par\vspace{{4mm}}
                \CornellMainText
                % Cornell source page={page_number} region=cue
                {body}
              \end{{minipage}}
            \end{{minipage}}
            """
        ).strip()

    if region_name == "main":
        heading = escape_latex_text(page.main.heading)
        body = render_cornell_region_latex(
            page.main,
            region_name="main",
            asset_paths_by_id=asset_paths_by_id,
        )
        return dedent(
            rf"""
            \begin{{minipage}}[t]{{6in}}
              \vspace{{.2cm}}
              \hspace*{{4mm}}\begin{{minipage}}[t]{{5.52in}}
                \CornellMainHeading{{{heading}}}
                \CornellMainText
                % Cornell source page={page_number} region=main
                {body}
              \end{{minipage}}
            \end{{minipage}}
            """
        ).strip()

    if region_name == "summary":
        heading = escape_latex_text(page.summary.heading)
        body = render_cornell_region_latex(
            page.summary,
            region_name="summary",
            asset_paths_by_id=asset_paths_by_id,
        )
        return dedent(
            rf"""
            \begin{{minipage}}[t]{{8.5in}}
              \vspace{{4mm}}
              \hspace*{{18mm}}\begin{{minipage}}[t]{{7.43in}}
                \CornellSummaryHeading{{{heading}}}
              \end{{minipage}}
              \par\vspace{{1mm}}
              \hspace*{{18mm}}\begin{{minipage}}[t]{{7.55in}}
                \raggedright
                \CornellMainText
                % Cornell source page={page_number} region=summary
                {body}
              \end{{minipage}}
            \end{{minipage}}
            """
        ).strip()

    raise ValueError(f"Unknown Cornell region: {region_name!r}")


def point_value_from_sp(value: int) -> float:
    """Convert TeX scaled points to points."""
    return value / SP_PER_PT


def compute_region_fit(
    *,
    region: str,
    natural_width_sp: int,
    natural_height_sp: int,
    available_width_sp: int,
    available_height_sp: int,
    min_region_scale: float,
) -> RegionFitResult:
    """Compute the scale and status for one measured region."""
    width_scale = 1.0 if natural_width_sp <= 0 else available_width_sp / natural_width_sp
    height_scale = 1.0 if natural_height_sp <= 0 else available_height_sp / natural_height_sp
    required_scale = min(1.0, width_scale, height_scale)
    if required_scale >= 1.0 - SCALE_EPSILON:
        required_scale = 1.0
        applied_scale = 1.0
        status = FIT_STATUS
    elif required_scale + SCALE_EPSILON >= min_region_scale:
        applied_scale = required_scale
        status = SCALED_STATUS
    else:
        applied_scale = required_scale
        status = OVERFLOW_STATUS

    return RegionFitResult(
        region=region,
        natural_width=point_value_from_sp(natural_width_sp),
        natural_height=point_value_from_sp(natural_height_sp),
        available_width=point_value_from_sp(available_width_sp),
        available_height=point_value_from_sp(available_height_sp),
        required_scale=required_scale,
        applied_scale=applied_scale,
        status=status,
    )


def _measurement_source(
    pages: tuple[CornellPage, ...],
    *,
    latex_preamble: str,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    blocks = []
    for page_index, page in enumerate(pages, start=1):
        for region_name in REGION_ORDER:
            geometry = REGION_GEOMETRY[region_name]
            region_box = cornell_region_box_latex(
                page,
                region_name,
                page_number=page_index,
                asset_paths_by_id=asset_paths_by_id,
            )
            blocks.append(
                "\n".join(
                    [
                        r"\setbox\CornellMeasureBox=\hbox{%",
                        region_box + "%",
                        r"}%",
                        (
                            rf"\typeout{{CORNELL_FIT p={page_index} r={region_name} "
                            r"nw=\number\wd\CornellMeasureBox\space "
                            r"nh=\number\dimexpr\ht\CornellMeasureBox+\dp\CornellMeasureBox\relax\space "
                            rf"aw=\number\dimexpr{geometry.available_width}\relax\space "
                            rf"ah=\number\dimexpr{geometry.available_height}\relax}}"
                        ),
                    ]
                )
            )
    return (
        latex_preamble
        + "\n"
        + r"\newsavebox{\CornellMeasureBox}"
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


def measure_cornell_document_fit(
    document: CornellDocument,
    output_dir: str | Path,
    output_name: str,
    *,
    latex_preamble: str,
    asset_paths_by_id: Mapping[str, str] | None = None,
    min_region_scale: float | None = None,
) -> CornellFitReport:
    """Measure every Cornell region with LaTeX before the final render."""
    pages = document.ordered_pages()
    if not pages:
        raise ValueError("CornellDocument must contain at least one page")

    min_scale = _normalize_min_region_scale(
        MIN_REGION_SCALE if min_region_scale is None else min_region_scale
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(output_name).stem or str(output_name)).strip("._")
    safe_name = safe_name or "cornell"
    tex_path = output_path / f"{safe_name}_fit.tex"
    log_path = tex_path.with_suffix(".log")
    tex_path.write_text(
        _measurement_source(
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
        raise CornellLayoutError(
            f"No se pudo medir el ajuste Cornell: {exc}",
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
        raise CornellLayoutError(
            "No se pudo medir el ajuste Cornell.",
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
    page_reports: list[PageFitReport] = []
    missing: list[str] = []
    for page_index, page in enumerate(pages, start=1):
        region_reports: list[RegionFitResult] = []
        for region_name in REGION_ORDER:
            values = measurements.get((page_index, region_name))
            if values is None:
                missing.append(f"{page.page_id}:{region_name}")
                continue
            region_reports.append(
                compute_region_fit(
                    region=region_name,
                    min_region_scale=min_scale,
                    **values,
                )
            )
        page_reports.append(
            PageFitReport(
                page_id=page.page_id,
                page_number=page_index,
                regions=tuple(region_reports),
            )
        )

    if missing:
        raise CornellLayoutError(
            "No se pudo medir el ajuste Cornell: faltan regiones en el log.",
            {
                "missing_regions": missing,
                "log_text": log_text,
                "log_excerpt": "\n".join(log_text.splitlines()[-80:]),
                "tex_path": str(tex_path),
                "log_path": str(log_path),
                "log_decode": log_decode,
            },
        )

    return CornellFitReport(
        pages=tuple(page_reports),
        min_region_scale=min_scale,
    )


def default_cornell_fit_report(document: CornellDocument) -> CornellFitReport:
    """Return a scale-1 report for source generation without preflight."""
    pages = []
    for page_index, page in enumerate(document.ordered_pages(), start=1):
        regions = []
        for region_name in REGION_ORDER:
            regions.append(
                RegionFitResult(
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
            PageFitReport(
                page_id=page.page_id,
                page_number=page_index,
                regions=tuple(regions),
            )
        )
    return CornellFitReport(pages=tuple(pages), min_region_scale=MIN_REGION_SCALE)

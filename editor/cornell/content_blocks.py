"""Block-aware Cornell region splitting for LaTeX content."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from editor.cornell.layout import MIN_REGION_SCALE
from editor.cornell.layout import RegionFitResult
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion

REGION_NAMES = ("cue", "main", "summary")
DEFAULT_REGION_HEADINGS = {
    "cue": "Ideas principales",
    "main": "Tema",
    "summary": "Observaciones",
}
LATEX_MARKER_PATTERN = re.compile(
    r"\\(?P<kind>begin|end)\s*\{(?P<environment>[^{}]+)\}|"
    r"(?P<display_open>\\\[)|"
    r"(?P<display_close>\\\])"
)
FIT_EPSILON = 1e-6

RegionFitEngine = Callable[[CornellPage, str], RegionFitResult]


@dataclass(frozen=True, slots=True)
class LatexContentBlock:
    """One top-level block of LaTeX region content."""

    kind: str
    latex: str
    environment: str | None = None


@dataclass(frozen=True, slots=True)
class SplitProposal:
    """Proposed two-page split for one overflowing Cornell region."""

    region: str
    original_latex: str
    kept_latex: str
    moved_latex: str
    kept_blocks: tuple[LatexContentBlock, ...]
    moved_blocks: tuple[LatexContentBlock, ...]
    current_page: CornellPage
    new_page: CornellPage
    current_fit: RegionFitResult
    moved_fit: RegionFitResult

    @property
    def cut_after_block(self) -> int:
        """Return the one-based block count left on the current page."""
        return len(self.kept_blocks)


class RegionSplitError(RuntimeError):
    """Raised when a Cornell region cannot be split safely."""


def _validate_region_name(region_name: str) -> str:
    region = str(region_name or "").strip().lower()
    if region not in REGION_NAMES:
        raise ValueError(f"Unknown Cornell region: {region_name!r}")
    return region


def _append_text_block(blocks: list[LatexContentBlock], latex: str) -> None:
    if latex:
        blocks.append(LatexContentBlock(kind="text", latex=latex))


def _with_latex(block: LatexContentBlock, latex: str) -> LatexContentBlock:
    return LatexContentBlock(kind=block.kind, latex=latex, environment=block.environment)


def _merge_whitespace_blocks(blocks: list[LatexContentBlock]) -> tuple[LatexContentBlock, ...]:
    merged: list[LatexContentBlock] = []
    pending_whitespace = ""
    for block in blocks:
        if block.kind == "text" and not block.latex.strip():
            pending_whitespace += block.latex
            continue
        if pending_whitespace:
            block = _with_latex(block, pending_whitespace + block.latex)
            pending_whitespace = ""
        merged.append(block)

    if pending_whitespace:
        if merged:
            last = merged[-1]
            merged[-1] = _with_latex(last, last.latex + pending_whitespace)
        else:
            merged.append(LatexContentBlock(kind="text", latex=pending_whitespace))
    return tuple(merged)


def _find_environment_end(source: str, begin_match: re.Match[str]) -> int:
    stack = [begin_match.group("environment")]
    for match in LATEX_MARKER_PATTERN.finditer(source, begin_match.end()):
        kind = match.group("kind")
        if kind == "begin":
            stack.append(match.group("environment"))
            continue
        if kind != "end":
            continue
        environment = match.group("environment")
        if not stack or environment != stack[-1]:
            expected = stack[-1] if stack else "ninguno"
            raise ValueError(
                f"Entorno LaTeX desbalanceado: se esperaba \\end{{{expected}}}, "
                f"pero apareció \\end{{{environment}}}."
            )
        stack.pop()
        if not stack:
            return match.end()
    raise ValueError(f"Entorno LaTeX sin cierre: \\begin{{{begin_match.group('environment')}}}.")


def _find_display_math_end(source: str, open_match: re.Match[str]) -> int:
    depth = 1
    for match in LATEX_MARKER_PATTERN.finditer(source, open_match.end()):
        if match.group("display_open"):
            depth += 1
            continue
        if not match.group("display_close"):
            continue
        depth -= 1
        if depth == 0:
            return match.end()
    raise ValueError("Bloque LaTeX display math sin cierre: \\[.")


def parse_latex_blocks(source: str) -> tuple[LatexContentBlock, ...]:
    """Parse top-level LaTeX blocks without cutting inside environments."""
    latex = source or ""
    blocks: list[LatexContentBlock] = []
    position = 0
    while position < len(latex):
        next_match = None
        for match in LATEX_MARKER_PATTERN.finditer(latex, position):
            if match.group("kind") == "begin" or match.group("display_open"):
                next_match = match
                break
        if next_match is None:
            _append_text_block(blocks, latex[position:])
            break

        _append_text_block(blocks, latex[position : next_match.start()])
        if next_match.group("display_open"):
            end = _find_display_math_end(latex, next_match)
            blocks.append(
                LatexContentBlock(
                    kind="display_math",
                    latex=latex[next_match.start() : end],
                    environment="display_math",
                )
            )
            position = end
            continue

        end = _find_environment_end(latex, next_match)
        environment = next_match.group("environment")
        blocks.append(
            LatexContentBlock(
                kind="environment",
                latex=latex[next_match.start() : end],
                environment=environment,
            )
        )
        position = end
    return _merge_whitespace_blocks(blocks)


def reconstruct_latex(blocks: tuple[LatexContentBlock, ...] | list[LatexContentBlock]) -> str:
    """Rebuild LaTeX content from parsed blocks."""
    return "".join(block.latex for block in blocks)


def _region_with_latex(region: CornellRegion, latex: str, *, image_ids: tuple[str, ...]) -> CornellRegion:
    return CornellRegion(
        heading=region.heading,
        latex=latex,
        image_ids=image_ids,
    )


def _page_with_region_latex(
    page: CornellPage,
    region_name: str,
    latex: str,
    *,
    preserve_image_ids: bool,
) -> CornellPage:
    source_region = getattr(page, region_name)
    image_ids = source_region.image_ids if preserve_image_ids else ()
    regions = {
        "cue": page.cue,
        "main": page.main,
        "summary": page.summary,
    }
    regions[region_name] = _region_with_latex(source_region, latex, image_ids=image_ids)
    return CornellPage(
        page_id=page.page_id,
        order=page.order,
        cue=regions["cue"],
        main=regions["main"],
        summary=regions["summary"],
        source_refs=page.source_refs,
    )


def _new_page_for_split(
    page: CornellPage,
    region_name: str,
    latex: str,
    *,
    page_id: str | None = None,
) -> CornellPage:
    source_region = getattr(page, region_name)
    regions = {
        region: CornellRegion(heading=DEFAULT_REGION_HEADINGS[region], latex="")
        for region in REGION_NAMES
    }
    regions[region_name] = CornellRegion(heading=source_region.heading, latex=latex)
    return CornellPage(
        page_id=page_id or f"{page.page_id}_{region_name}_{uuid4().hex[:8]}",
        order=page.order + 1,
        cue=regions["cue"],
        main=regions["main"],
        summary=regions["summary"],
    )


def _fits_minimum(fit: RegionFitResult) -> bool:
    return fit.required_scale + FIT_EPSILON >= MIN_REGION_SCALE


def _block_label(block: LatexContentBlock, index: int) -> str:
    if block.environment:
        return f"bloque {index} ({block.environment})"
    return f"bloque {index} ({block.kind})"


def split_region_to_fit(
    page: CornellPage,
    region: str,
    fit_engine: RegionFitEngine,
    *,
    new_page_id: str | None = None,
) -> SplitProposal:
    """Split an overflowing region into two pages using real LaTeX fit checks."""
    region_name = _validate_region_name(region)
    original_region = getattr(page, region_name)
    blocks = parse_latex_blocks(original_region.latex)
    if len(blocks) < 2:
        raise RegionSplitError("No hay suficientes bloques completos para dividir la región.")

    for index, block in enumerate(blocks, start=1):
        block_page = _page_with_region_latex(
            page,
            region_name,
            block.latex,
            preserve_image_ids=False,
        )
        block_fit = fit_engine(block_page, region_name)
        if not _fits_minimum(block_fit):
            raise RegionSplitError(
                "Un solo bloque no cabe con escala mínima "
                f"{MIN_REGION_SCALE:.2f}: {_block_label(block, index)} "
                f"requiere {block_fit.required_scale:.2f}."
            )

    best: SplitProposal | None = None
    for cut_index in range(1, len(blocks)):
        kept_blocks = blocks[:cut_index]
        moved_blocks = blocks[cut_index:]
        kept_latex = reconstruct_latex(kept_blocks)
        moved_latex = reconstruct_latex(moved_blocks)
        current_page = _page_with_region_latex(
            page,
            region_name,
            kept_latex,
            preserve_image_ids=True,
        )
        current_fit = fit_engine(current_page, region_name)
        if not _fits_minimum(current_fit):
            break

        moved_page = _new_page_for_split(
            page,
            region_name,
            moved_latex,
            page_id=new_page_id,
        )
        moved_fit = fit_engine(moved_page, region_name)
        if not _fits_minimum(moved_fit):
            continue

        best = SplitProposal(
            region=region_name,
            original_latex=original_region.latex,
            kept_latex=kept_latex,
            moved_latex=moved_latex,
            kept_blocks=kept_blocks,
            moved_blocks=moved_blocks,
            current_page=current_page,
            new_page=moved_page,
            current_fit=current_fit,
            moved_fit=moved_fit,
        )

    if best is None:
        raise RegionSplitError(
            "No se encontró un corte que deje ambas páginas con escala mínima "
            f"{MIN_REGION_SCALE:.2f}."
        )
    return best


def _unique_page_id(desired: str, existing_ids: set[str]) -> str:
    if desired not in existing_ids:
        return desired
    stem = desired
    suffix = 2
    while f"{stem}_{suffix}" in existing_ids:
        suffix += 1
    return f"{stem}_{suffix}"


def is_empty_cornell_page(page: CornellPage) -> bool:
    """Return True when a page has no region body content or images."""
    return all(
        not region.latex.strip() and not region.image_ids
        for region in (page.cue, page.main, page.summary)
    )


def _new_page_with_identity(source: CornellPage, *, page_id: str, order: int) -> CornellPage:
    return CornellPage(
        page_id=page_id,
        order=order,
        cue=source.cue,
        main=source.main,
        summary=source.summary,
        source_refs=source.source_refs,
    )


def apply_split_proposal(
    document: CornellDocument,
    page_index: int,
    proposal: SplitProposal,
) -> CornellDocument:
    """Apply a split proposal after the selected page and normalize orders."""
    pages = list(document.ordered_pages())
    if not pages:
        raise ValueError("CornellDocument must contain at least one page")
    safe_index = min(max(page_index, 0), len(pages) - 1)
    pages[safe_index] = proposal.current_page
    next_index = safe_index + 1
    if next_index < len(pages) and is_empty_cornell_page(pages[next_index]):
        target = pages[next_index]
        pages[next_index] = _new_page_with_identity(
            proposal.new_page,
            page_id=target.page_id,
            order=target.order,
        )
    else:
        existing_ids = {page.page_id for page in pages}
        existing_ids.discard(proposal.current_page.page_id)
        new_page_id = _unique_page_id(proposal.new_page.page_id, existing_ids)
        pages.insert(
            next_index,
            _new_page_with_identity(
                proposal.new_page,
                page_id=new_page_id,
                order=proposal.new_page.order,
            ),
        )
    normalized_pages = [
        CornellPage(
            page_id=page.page_id,
            order=order,
            cue=page.cue,
            main=page.main,
            summary=page.summary,
            source_refs=page.source_refs,
        )
        for order, page in enumerate(pages, start=1)
    ]
    return CornellDocument(
        schema_version=document.schema_version,
        template_id=document.template_id,
        pages=tuple(normalized_pages),
        attribution=document.attribution,
        watermark=document.watermark,
    )

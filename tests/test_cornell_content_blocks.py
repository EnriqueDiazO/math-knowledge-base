"""Tests for block-aware Cornell region splitting."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from editor.cornell import renderer
from editor.cornell.content_blocks import RegionSplitError
from editor.cornell.content_blocks import apply_split_proposal
from editor.cornell.content_blocks import parse_latex_blocks
from editor.cornell.content_blocks import reconstruct_latex
from editor.cornell.content_blocks import split_region_to_fit
from editor.cornell.layout import MIN_REGION_SCALE
from editor.cornell.layout import RegionFitResult
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion


def mandatory_overflow_main_latex(repeat: int = 7) -> str:
    paragraph = " ".join(
        "Sea una familia de objetos con una propiedad estable bajo las operaciones consideradas."
        for _ in range(repeat)
    )
    return rf"""
\begin{{definition}}{{Espacio}}
{paragraph}
\end{{definition}}

\begin{{align}}
a_1 + a_2 &= b_1 + b_2\\
\phi(x+y) &= \phi(x)+\phi(y)
\end{{align}}

\begin{{example}}{{Matrices}}
{paragraph}
\end{{example}}

\begin{{theorem}}{{Unicidad}}
{paragraph}
\end{{theorem}}

\[
\begin{{pmatrix}}
1 & 0 & 2\\
0 & 1 & 3\\
4 & 5 & 6
\end{{pmatrix}}
\]

\begin{{definition}}{{Subespacio}}
{paragraph}
\end{{definition}}

\begin{{proposition}}{{Criterio}}
{paragraph}
\end{{proposition}}
"""


def mandatory_overflow_page(page_id: str = "p001") -> CornellPage:
    return CornellPage(
        page_id=page_id,
        order=1,
        cue=CornellRegion(heading="Ideas principales", latex="Idea principal."),
        main=CornellRegion(
            heading="Caso 69 por ciento",
            latex=mandatory_overflow_main_latex(),
        ),
        summary=CornellRegion(heading="Observaciones", latex="Resumen breve."),
    )


def second_page() -> CornellPage:
    return CornellPage(
        page_id="p002",
        order=2,
        cue=CornellRegion(heading="Cue 2", latex="Cue 2"),
        main=CornellRegion(heading="Main 2", latex="Main 2"),
        summary=CornellRegion(heading="Summary 2", latex="Summary 2"),
    )


def empty_page(page_id: str = "p_empty", order: int = 2) -> CornellPage:
    return CornellPage(
        page_id=page_id,
        order=order,
        cue=CornellRegion(heading="Ideas principales", latex=""),
        main=CornellRegion(heading="Tema", latex=""),
        summary=CornellRegion(heading="Observaciones", latex=""),
    )


def fake_fit(scale: float = 1.0) -> RegionFitResult:
    status = "FIT" if scale >= 1 else "SCALED"
    if scale < MIN_REGION_SCALE:
        status = "OVERFLOW"
    return RegionFitResult(
        region="main",
        natural_width=100,
        natural_height=100,
        available_width=100,
        available_height=100,
        required_scale=scale,
        applied_scale=scale,
        status=status,
    )


def always_fit_engine(page: CornellPage, region_name: str) -> RegionFitResult:
    return fake_fit(1.0)


def real_fit_engine(tmp_path: Path):
    counter = 0

    def fit(page: CornellPage, region_name: str) -> RegionFitResult:
        nonlocal counter
        counter += 1
        page_report = renderer.measure_cornell_page_fit(
            page,
            tmp_path,
            f"split_real_{counter}",
        )
        region_fit = page_report.region_fit(region_name)
        assert region_fit is not None
        return region_fit

    return fit


def test_parse_latex_blocks_keeps_nested_environment_whole() -> None:
    source = (
        "Intro\n"
        "\\begin{definition}{A}\n"
        "Texto.\n"
        "\\begin{proof}\n"
        "Prueba.\n"
        "\\end{proof}\n"
        "\\end{definition}\n"
        "Tail"
    )

    blocks = parse_latex_blocks(source)

    assert [block.kind for block in blocks] == ["text", "environment", "text"]
    assert blocks[1].environment == "definition"
    assert "\\begin{proof}" in blocks[1].latex
    assert "\\end{proof}" in blocks[1].latex


def test_parse_latex_blocks_does_not_cut_display_matrix() -> None:
    source = "Antes\n\\[\n\\begin{pmatrix}1 & 2\\\\3 & 4\\end{pmatrix}\n\\]\nDespues"

    blocks = parse_latex_blocks(source)

    assert [block.kind for block in blocks] == ["text", "display_math", "text"]
    assert "\\begin{pmatrix}" in blocks[1].latex
    assert "\\end{pmatrix}" in blocks[1].latex


def test_parse_latex_blocks_reconstructs_exact_original() -> None:
    source = mandatory_overflow_main_latex()

    blocks = parse_latex_blocks(source)

    assert reconstruct_latex(blocks) == source


def test_split_region_by_real_latex_fit(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for Cornell split fit verification")
    page = mandatory_overflow_page()
    full_fit = renderer.measure_cornell_page_fit(page, tmp_path, "mandatory_full").region_fit("main")
    assert full_fit is not None
    assert 0.65 <= full_fit.required_scale < MIN_REGION_SCALE

    proposal = split_region_to_fit(
        page,
        "main",
        real_fit_engine(tmp_path),
        new_page_id="p001_split",
    )

    assert proposal.current_fit.required_scale >= MIN_REGION_SCALE
    assert proposal.moved_fit.required_scale >= MIN_REGION_SCALE
    assert proposal.kept_latex + proposal.moved_latex == page.main.latex
    assert proposal.cut_after_block == 5
    assert proposal.kept_blocks[-1].kind == "display_math"
    assert proposal.moved_blocks[0].environment == "definition"


def test_apply_split_reuses_next_empty_page_and_normalizes_orders() -> None:
    page = mandatory_overflow_page()
    proposal = split_region_to_fit(page, "main", always_fit_engine, new_page_id="generated")
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(page, empty_page("p002", 2)),
    )

    updated = apply_split_proposal(document, 0, proposal)

    pages = updated.ordered_pages()
    assert [page.page_id for page in pages] == ["p001", "p002"]
    assert [page.order for page in pages] == [1, 2]
    assert pages[0].main.latex == proposal.kept_latex
    assert pages[1].main.latex == proposal.moved_latex
    assert pages[0].main.latex + pages[1].main.latex == proposal.original_latex
    assert pages[1].cue.latex == ""
    assert pages[1].summary.latex == ""


def test_apply_split_creates_new_page_when_next_page_is_not_empty() -> None:
    page = mandatory_overflow_page()
    proposal = split_region_to_fit(page, "main", always_fit_engine, new_page_id="p001_split")
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(page, second_page()),
    )

    updated = apply_split_proposal(document, 0, proposal)

    pages = updated.ordered_pages()
    assert [page.page_id for page in pages] == ["p001", "p001_split", "p002"]
    assert [page.order for page in pages] == [1, 2, 3]
    assert pages[0].main.latex == proposal.kept_latex
    assert pages[1].main.latex == proposal.moved_latex
    assert pages[0].main.latex + pages[1].main.latex == proposal.original_latex
    assert pages[1].cue.latex == ""
    assert pages[1].summary.latex == ""


def test_cancel_split_proposal_does_not_modify_document() -> None:
    page = mandatory_overflow_page()
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(page, second_page()),
    )
    before = document.to_dict()

    split_region_to_fit(page, "main", always_fit_engine, new_page_id="p001_split")

    assert document.to_dict() == before


def test_single_oversized_block_fails_clearly() -> None:
    page = CornellPage(
        page_id="too_big",
        order=1,
        cue=CornellRegion(heading="Cue", latex=""),
        main=CornellRegion(
            heading="Main",
            latex="\\begin{definition}{Gigante}\nMucho contenido.\n\\end{definition}\nTexto final.",
        ),
        summary=CornellRegion(heading="Summary", latex=""),
    )

    def fit_engine(candidate: CornellPage, region_name: str) -> RegionFitResult:
        if "Gigante" in candidate.main.latex:
            return fake_fit(0.60)
        return fake_fit(1.0)

    with pytest.raises(RegionSplitError, match="Un solo bloque no cabe"):
        split_region_to_fit(page, "main", fit_engine)

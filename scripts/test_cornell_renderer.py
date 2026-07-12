"""Manual smoke test for the Cornell MVP renderer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _page(
    *,
    page_id: str,
    order: int,
    cue_heading: str,
    main_heading: str,
    summary_heading: str,
    cue_latex: str,
    main_latex: str,
    summary_latex: str,
):
    from editor.cornell.models import CornellPage
    from editor.cornell.models import CornellRegion

    return CornellPage(
        page_id=page_id,
        order=order,
        cue=CornellRegion(heading=cue_heading, latex=cue_latex),
        main=CornellRegion(heading=main_heading, latex=main_latex),
        summary=CornellRegion(heading=summary_heading, latex=summary_latex),
    )


def main() -> int:
    """Render one hardcoded three-page Cornell document and print generated paths."""
    from editor.cornell.models import DEFAULT_TEMPLATE_ID
    from editor.cornell.models import CornellDocument
    from editor.cornell.models import build_cornell_math_v1_payload
    from editor.cornell.renderer import render_cornell_document
    from mathmongo.paths import get_cornell_runtime_dir

    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            _page(
                page_id="mvp_page_3",
                order=3,
                cue_heading="Comprobaciones",
                cue_latex="Producto compatible y matriz identidad.",
                main_heading="Producto de matrices",
                main_latex=r"""
                Para \(A\in M_{2\times 3}\) y \(B\in M_{3\times 2}\),
                \[
                  (AB)_{ij}=\sum_{k=1}^{3} a_{ik}b_{kj}.
                \]
                """,
                summary_heading="Cierre",
                summary_latex="El producto depende del orden de los factores.",
            ),
            _page(
                page_id="mvp_page_1",
                order=1,
                cue_heading="Ideas principales",
                cue_latex=(
                    "Operaciones definidas entrada por entrada.\\par\n"
                    "Verificar dimensiones antes de sumar o multiplicar."
                ),
                main_heading="Aritmética de matrices",
                main_latex=r"""
                Sean \(A,B \in M_{2\times 2}(\mathbb{R})\). La suma se define por
                \[
                  (A+B)_{ij}=a_{ij}+b_{ij}.
                \]
                Por ejemplo,
                \[
                \begin{pmatrix}
                1 & 2\\
                3 & 4
                \end{pmatrix}
                +
                \begin{pmatrix}
                5 & 6\\
                7 & 8
                \end{pmatrix}
                =
                \begin{pmatrix}
                6 & 8\\
                10 & 12
                \end{pmatrix}.
                \]
                """,
                summary_heading="Observaciones",
                summary_latex=(
                    "La suma requiere matrices del mismo tamaño. "
                    r"El producto \(AB\) exige compatibilidad entre columnas y filas."
                ),
            ),
            _page(
                page_id="mvp_page_2",
                order=2,
                cue_heading="Reglas",
                cue_latex="La suma es conmutativa; el producto no siempre lo es.",
                main_heading="Propiedades básicas",
                main_latex=r"""
                Si las operaciones están definidas,
                \[
                  A+B=B+A,\qquad A(BC)=(AB)C.
                \]
                """,
                summary_heading="Notas",
                summary_latex="La asociatividad permite agrupar productos de matrices.",
            ),
        ),
    )
    output_dir = get_cornell_runtime_dir() / "mvp"
    single_page_document = CornellDocument(
        schema_version=document.schema_version,
        template_id=document.template_id,
        pages=(document.ordered_pages()[0],),
    )
    single_result = render_cornell_document(single_page_document, output_dir, "cornell_mvp_manual")
    result = render_cornell_document(document, output_dir, "cornell_multipage_manual")
    persistible = build_cornell_math_v1_payload(document)
    print(f"SINGLE TEX: {single_result.tex_path}")
    print(f"SINGLE PDF: {single_result.pdf_path}")
    print(f"SINGLE LOG: {single_result.log_path}")
    print(f"SINGLE STATUS: {single_result.status}")
    print(f"TEX: {result.tex_path}")
    print(f"PDF: {result.pdf_path}")
    print(f"LOG: {result.log_path}")
    print(f"STATUS: {result.status}")
    print("PERSISTIBLE:")
    print(json.dumps(persistible, ensure_ascii=False, indent=2))
    if not single_result.success:
        print(single_result.message)
        return 1
    if not result.success:
        print(result.message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

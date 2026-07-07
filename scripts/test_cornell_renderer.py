"""Manual smoke test for the Cornell MVP renderer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Render one hardcoded Cornell page and print generated paths."""
    from editor.cornell.models import DEFAULT_TEMPLATE_ID
    from editor.cornell.models import CornellDocument
    from editor.cornell.models import CornellPage
    from editor.cornell.models import CornellRegion
    from editor.cornell.models import build_cornell_math_v1_payload
    from editor.cornell.renderer import render_cornell_pdf

    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CornellPage(
                page_id="mvp_manual",
                order=1,
                cue=CornellRegion(
                    heading="Ideas principales",
                    latex=(
                        "Operaciones definidas entrada por entrada.\\par\n"
                        "Verificar dimensiones antes de sumar o multiplicar."
                    ),
                ),
                main=CornellRegion(
                    heading="Aritmética de matrices",
                    latex=r"""
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
                ),
                summary=CornellRegion(
                    heading="Observaciones",
                    latex=(
                        "La suma requiere matrices del mismo tamaño. "
                        r"El producto \(AB\) exige compatibilidad entre columnas y filas."
                    ),
                ),
            ),
        ),
    )
    page = document.ordered_pages()[0]
    persistible = build_cornell_math_v1_payload(document)
    output_dir = PROJECT_ROOT / "runtime" / "cornell_mvp"
    result = render_cornell_pdf(page, output_dir)
    print(f"TEX: {result.tex_path}")
    print(f"PDF: {result.pdf_path}")
    print(f"LOG: {result.log_path}")
    print(f"STATUS: {result.status}")
    print("PERSISTIBLE:")
    print(json.dumps(persistible, ensure_ascii=False, indent=2))
    if not result.success:
        print(result.message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

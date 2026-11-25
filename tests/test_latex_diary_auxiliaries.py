"""Regression: real notes with lists and tcolorbox listings need only fixed writable auxiliaries."""

import pytest

from exporters_latex.sandbox import compile_document


@pytest.mark.parametrize(
    ("body", "auxiliary"),
    [
        (r"\listoffigures Texto.", "main.lof"),
        (r"\listoftables Texto.", "main.lot"),
        (
            "\\begin{algoritmo}[language=bash]{Comando}\npython --version\n\\end{algoritmo}",
            "main.listing",
        ),
    ],
)
def test_diary_auxiliaries_compile_without_general_writable_directories(body, auxiliary):
    """Preserve valid canonical source rather than deleting lists or replacing authored code."""
    source = r"\documentclass{notes}\begin{document}" + "\n" + body + "\n" + r"\end{document}"
    result = compile_document(source)
    assert result.status == "ready", result.diagnostic
    assert result.pdf.startswith(b"%PDF-")
    assert auxiliary in result.log
    assert "I can't write on file" not in result.log

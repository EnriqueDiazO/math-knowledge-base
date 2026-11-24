"""Compiler failures explain a corrective action and never imply failed storage."""

import pytest

from exporters_latex.compile_diagnostics import compilation_failure_message


@pytest.mark.parametrize(("log", "expected"), [
    ("! LaTeX Error: File `tikz-cd.sty' not found.", "Falta el paquete LaTeX «tikz-cd.sty»"),
    ("/inputs/main.tex:15: LaTeX Error: Environment concept undefined.", "El entorno «concept» no está definido"),
    ("! Undefined control sequence.\nl.9 \\unknownMacro", "comando LaTeX sin definir"),
    ("! Missing $ inserted.", "corrige la fuente"),
])
def test_failure_message_is_specific_and_preserves_document(log, expected):
    """Known diagnostics point to code/dependencies; every path preserves the source."""
    message = compilation_failure_message(log)
    assert expected in message
    assert "se conserva" in message
    assert "compilar" in message
    assert "/inputs" not in message

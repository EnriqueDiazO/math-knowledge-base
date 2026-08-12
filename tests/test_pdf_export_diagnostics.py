"""Regression coverage for user-facing PDF export diagnostics."""

from editor.pdf_export import _probable_cause


def test_fatal_latex_error_takes_priority_over_diagnostic_encoding() -> None:
    """An incidental log decoding issue must not hide the actionable LaTeX error."""
    cause = _probable_cause(
        {
            "exception_type": "LaTeXCompilationError",
            "returncode": 1,
            "first_latex_error": r"! Argument of \language@active@arg> has an extra }.",
            "fatal_errors": ["Runaway argument?"],
            "decode_diagnostics": [{"had_decode_error": True}],
        }
    )

    assert cause == (
        r"LaTeX reportó un error fatal: "
        r"! Argument of \language@active@arg> has an extra }."
    )
    assert "UTF-8" not in cause


def test_encoding_is_reported_when_it_is_the_only_known_failure() -> None:
    """A genuine standalone decoding failure retains its specific explanation."""
    cause = _probable_cause(
        {
            "exception_type": "UnicodeDecodeError",
            "decode_diagnostics": [{"had_decode_error": True}],
        }
    )

    assert cause == "Se encontró salida diagnóstica que no pudo interpretarse como UTF-8."

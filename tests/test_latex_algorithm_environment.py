"""Regression tests for the custom LaTeX algorithm environment."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from exporters_latex.exportadorlatex import ExportadorLatex

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates_latex"


def test_single_export_refreshes_stale_managed_styles(tmp_path: Path) -> None:
    """A single export replaces stale managed styles but leaves unrelated files."""
    templates = tmp_path / "templates"
    destination = tmp_path / "export"
    templates.mkdir()
    destination.mkdir()

    for name in ExportadorLatex._ARCHIVOS_PLANTILLA:
        (templates / name).write_text(f"current {name}\n", encoding="utf-8")
        (destination / name).write_text(f"stale {name}\n", encoding="utf-8")
    unrelated = destination / "custom.sty"
    unrelated.write_text("keep me\n", encoding="utf-8")

    ExportadorLatex(templates_dir=templates)._copiar_plantillas(str(destination))

    for name in ExportadorLatex._ARCHIVOS_PLANTILLA:
        assert (destination / name).read_bytes() == (templates / name).read_bytes()
    assert unrelated.read_text(encoding="utf-8") == "keep me\n"


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is required")
def test_algoritmo_compiles_without_breaking_theorem_environments(tmp_path: Path) -> None:
    """The algorithm listing and the established theorem aliases compile together."""
    for name in ("miestilo.sty", "coloredtheorem.sty"):
        shutil.copy2(TEMPLATES_DIR / name, tmp_path / name)

    tex_path = tmp_path / "algorithm.tex"
    tex_path.write_text(
        r"""\documentclass[12pt]{article}
\usepackage{miestilo}
\begin{document}
\begin{definition}
Una definición existente sigue disponible.
\end{definition}
\begin{theorem}
Un teorema existente sigue disponible.
\end{theorem}
\begin{algoritmo}[language=bash]{Versión local estática}
mkdocs build
echo '# Guía rápida' >> docs/guia.md
\end{algoritmo}
\end{document}
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert tex_path.with_suffix(".pdf").is_file()

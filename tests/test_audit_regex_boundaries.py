"""Verify bounded parsing cost while retaining valid Markdown, math and diagnostics."""

import re
import subprocess
import sys
from itertools import product

import pytest

from editor.cornell.renderer import LATEX_FILE_LINE_PATTERN as CORNELL_LOCATION
from editor.cpi.renderer import LATEX_FILE_LINE_PATTERN as CPI_LOCATION
from mathmongo.reading_annotations.models import normalize_visual_quote_text
from parsers.markdownparser import MarkdownParser


@pytest.mark.parametrize("module,operation", [
    ("diagnostics", "from editor.cpi.renderer import LATEX_FILE_LINE_PATTERN; assert LATEX_FILE_LINE_PATTERN.search('a'*500_000+':17:') is None"),
    ("title", "from parsers.markdownparser import MarkdownParser; p.write_text('#'+' '*100_000+'x'); assert MarkdownParser(out).parsear_md(str(p),guardar=False)['titulo']==''"),
    ("reference", "from parsers.markdownparser import MarkdownParser; p.write_text('**Referencia**:'+' '*100_000+'x'); assert MarkdownParser(out).parsear_md(str(p),guardar=False)['referencia']=={}"),
    ("markup", "from mathmongo.reading_annotations.models import normalize_visual_quote_text; assert normalize_visual_quote_text('<a'+' '*100_000)=='<a'"),
])
def test_adversarial_parsing_finishes_and_preserves_its_result(module, operation, tmp_path):
    """A malformed long token must not monopolize the caller while looking for a terminator."""
    program = "from pathlib import Path\n" + f"p=Path({str(tmp_path / 'input.md')!r});out=Path({str(tmp_path / 'out')!r})\n" + operation
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, timeout=5, check=True)
    assert result.returncode == 0


@pytest.mark.parametrize("text,expected", [("/tmp/note.tex:12: Error", ("/tmp/note.tex", "12")), ("prefix note.tex:3: Error", ("note.tex", "3")), (r"C:\notes\note.tex:4: Error", (r"\notes\note.tex", "4")), ("not-a-file:17:", None)])
def test_both_renderers_keep_file_and_line_diagnostics(text, expected):
    """The optimized candidate boundary retains paths and exact line numbers."""
    for pattern in (CORNELL_LOCATION, CPI_LOCATION):
        match = pattern.search(text)
        assert (match.groups() if match else None) == expected


@pytest.mark.parametrize("text", ["$x < y$", r"\alpha < \beta", "a <= b", "< 3", "n > 0", "<a", "<!DOCTYPE"])
def test_plain_math_and_incomplete_markup_remain_plain_text(text):
    """Mathematical comparisons and incomplete literal tags stay valid quote text."""
    assert normalize_visual_quote_text(text) == text


@pytest.mark.parametrize("text", ["<script>alert(1)</script>", "</div>", "<a href='x'>", "<a   >", "<!-- a < b -->", "<!DOCTYPE html>", "<!doctype >"])
def test_complete_markup_is_still_rejected(text):
    """Comments, doctypes and tags remain forbidden even when their whitespace varies."""
    with pytest.raises(ValueError, match="without HTML"):
        normalize_visual_quote_text(text)


def test_single_line_metadata_keeps_the_existing_matching_contract(tmp_path):
    """Terminator bounding preserves even the legacy whitespace/newline edge cases."""
    path = tmp_path / "input.md"
    parser = MarkdownParser(tmp_path / "out")
    for whitespace, tail in product((" ", "\t", "\n", " \n "), ("Título\n", "", " \n", "Título sin salto")):
        text = "#" + whitespace + tail
        expected = re.search(r"#\s+(.*?)\n", text)
        path.write_text(text)
        result = parser.parsear_md(str(path), guardar=False)
        assert result["titulo"] == (expected.group(1).strip() if expected else "")

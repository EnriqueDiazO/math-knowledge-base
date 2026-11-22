"""Regression checks for malformed legacy input and unsafe export paths."""

from __future__ import annotations

import pytest

from exporters_latex.exportar_qmd_desde_mongo import crear_qmd
from parsers.markdownparser import MarkdownParser
from parsers.yaml_latex_parser import YamlLatexParser


@pytest.mark.parametrize("reference, expected", [
    ("Author, 2026, Book", {"autor": "Author", "año": 2026, "obra": "Book"}),
    ("Author, 2026, Book, 1, 9, key", {"autor": "Author", "año": 2026, "obra": "Book",
                                    "capitulo": "1", "pagina": "9", "bibkey": "key"}),
])
def test_markdown_reference_handles_optional_fields(tmp_path, reference, expected):
    """Three required reference fields must not index absent optional fields."""
    source = tmp_path / "note.md"
    source.write_text(f"# Note\n\n**Referencia**: {reference}\n\n$$x=1$$\n")
    result = MarkdownParser(tmp_path / "output").parsear_md(str(source), guardar=False)
    assert result["referencia"] == expected
    assert result["contenido_latex"] == "x=1"


@pytest.mark.parametrize("latex", [r"\frac{a}{b}=\alpha^2", r"\begin{aligned}x&=1\\y&=2\end{aligned}"])
def test_short_reference_preserves_mathematics_and_bibtex(tmp_path, latex):
    """Keep display mathematics and the separate BibTeX block byte-for-byte."""
    source = tmp_path / "math.md"
    bibtex = "@book{key, title={Book}, year={2026}}"
    source.write_text(f"# Note\n\n**Referencia**: Author, 2026, Book\n\n$$\n{latex}\n$$\n\n```bibtex\n{bibtex}\n```\n")
    result = MarkdownParser(tmp_path / "output").parsear_md(str(source), guardar=False)
    assert result["contenido_latex"] == latex
    assert result["bibtex_entry"] == bibtex


def test_valid_yaml_metadata_keeps_mathematical_content(tmp_path):
    """A well-formed header retains the public (metadata, LaTeX) contract."""
    source = tmp_path / "math.tex"
    source.write_text("---\nid: def:one\nsource: Book\n---\n\\frac{1}{2}\n")
    assert YamlLatexParser.extraer_yaml_y_contenido(str(source)) == ({"id": "def:one", "source": "Book"}, r"\frac{1}{2}")


@pytest.mark.parametrize("kind", ["../../outside/escape", "absolute", "..", "x\\escape"])
def test_qmd_export_rejects_path_components_in_concept_type(tmp_path, kind):
    """A concept's category must not select an arbitrary filesystem directory."""
    if kind == "absolute":
        kind = str(tmp_path / "outside/escape")
    with pytest.raises(ValueError, match="tipo"):
        crear_qmd({"tipo": kind, "titulo": "Title"}, tmp_path / "output")
    assert list(tmp_path.rglob("*.qmd")) == []


@pytest.mark.parametrize("leaf", [False, True])
def test_qmd_export_rejects_symlinks_inside_the_output_root(tmp_path, leaf):
    """Validate the final output path, including directory and file symlinks."""
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if leaf:
        (output / "teoremas").mkdir()
        target = outside / "valuable.qmd"
        target.write_text("keep")
        (output / "teoremas/teorema-title.qmd").symlink_to(target)
    else:
        (output / "teoremas").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        crear_qmd({"tipo": "teorema", "titulo": "Title"}, output)
    assert not (outside / "teorema-title.qmd").exists()
    if leaf:
        assert target.read_text() == "keep"


def test_qmd_export_keeps_the_existing_valid_directory_and_filename(tmp_path):
    """Normal concept types retain the legacy published path convention."""
    result = crear_qmd({"tipo": ["teorema"], "titulo": "Title", "contenido_latex": "x=1"}, tmp_path / "output")
    assert result.relative_to(tmp_path).as_posix() == "output/teoremas/teorema-title.qmd"
    assert "x=1" in result.read_text()


@pytest.mark.parametrize("header", ["", "- item", "42"])
def test_yaml_parser_requires_a_mapping_before_ingestion(tmp_path, header):
    """Invalid metadata must fail at the parser boundary with a useful error."""
    source = tmp_path / "note.tex"
    source.write_text(f"---\n{header}\n---\nx=1\n")
    with pytest.raises(ValueError, match="YAML.*mapping"):
        YamlLatexParser.extraer_yaml_y_contenido(str(source))

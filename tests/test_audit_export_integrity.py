"""Verify private PDF publication and non-destructive QMD export identities."""

import os
import stat

import pytest

from editor import pdf_export
from exporters_latex.exportar_qmd_desde_mongo import crear_qmd


def test_pdf_export_is_private_even_in_a_shared_destination(tmp_path):
    """A shared parent or readable compiler output cannot expose the exported note."""
    source = tmp_path / "compiled.pdf"
    source.write_bytes(b"%PDF-1.4 private note")
    source.chmod(0o644)
    destination = tmp_path / "shared" / "note.pdf"
    pdf_export._copy_pdf_to_final_path(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_failed_pdf_publication_preserves_the_previous_export(tmp_path, monkeypatch):
    """A failed replacement leaves the prior PDF intact and removes its temporary file."""
    source = tmp_path / "compiled.pdf"
    source.write_bytes(b"new export")
    destination = tmp_path / "existing.pdf"
    destination.write_bytes(b"previous export")
    def fail(*_args):
        raise OSError("publication failure")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="publication failure"):
        pdf_export._copy_pdf_to_final_path(source, destination)
    assert destination.read_bytes() == b"previous export"
    assert {p.name for p in tmp_path.iterdir()} == {"compiled.pdf", "existing.pdf"}


@pytest.mark.parametrize("second", [{"id": "second", "source": "same"}, {"id": "first", "source": "another"}])
def test_equal_titles_keep_both_compound_concept_identities(tmp_path, second):
    """Neither another ID nor another source may overwrite an earlier concept's QMD."""
    common = {"tipo": "definicion", "titulo": "Título idéntico", "contenido_latex": r"x^2 + y^2"}
    first = crear_qmd({**common, "id": "first", "source": "same"}, tmp_path)
    original = first.read_bytes()
    other = crear_qmd({**common, **second, "contenido_latex": r"\alpha + \beta"}, tmp_path)
    assert first != other
    assert first.read_bytes() == original
    assert r"\alpha + \beta" in other.read_text()
    updated = crear_qmd({**common, **second, "contenido_latex": r"\gamma"}, tmp_path)
    assert updated == other
    assert r"\gamma" in other.read_text()
    assert first.read_bytes() == original


def test_legacy_export_without_provable_ownership_is_preserved(tmp_path):
    """An unmarked legacy file is retained while its replacement gets a stable identity path."""
    directory = tmp_path / "definicions"
    directory.mkdir()
    legacy = directory / "definicion-titulo.qmd"
    legacy.write_text("# Historic manually edited output")
    result = crear_qmd({"id": "one", "source": "source", "tipo": "definicion", "titulo": "Titulo", "contenido_latex": "x"}, tmp_path)
    assert result != legacy and result.is_file()
    assert legacy.read_text() == "# Historic manually edited output"

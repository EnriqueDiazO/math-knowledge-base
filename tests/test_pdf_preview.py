"""Tests for the shared local PDF preview lifecycle."""

# ruff: noqa: D103

from pathlib import Path

from editor.pdf_preview import open_local_pdf
from editor.pdf_preview import prepare_stable_preview


def test_prepare_stable_preview_removes_stale_pdf_and_auxiliaries(tmp_path: Path) -> None:
    preview_dir = tmp_path / "runtime with spaces"
    preview_dir.mkdir()
    for name in ("cornell_preview.pdf", "cornell_preview.aux", "cornell_preview.log"):
        (preview_dir / name).write_bytes(b"old")
    export = preview_dir / "user-export.zip"
    export.write_bytes(b"keep")

    result = prepare_stable_preview(preview_dir, "cornell_preview.pdf")

    assert result == preview_dir.resolve() / "cornell_preview.pdf"
    assert not result.exists()
    assert not (preview_dir / "cornell_preview.aux").exists()
    assert not (preview_dir / "cornell_preview.log").exists()
    assert export.exists()


def test_open_local_pdf_quotes_spaces_and_is_injectable(tmp_path: Path) -> None:
    pdf = tmp_path / "preview with spaces.pdf"
    pdf.write_bytes(b"%PDF")
    opened: list[str] = []

    assert open_local_pdf(pdf, opener=lambda uri: opened.append(uri) or True)
    assert opened == [pdf.resolve().as_uri()]
    assert "%20" in opened[0]


def test_open_local_pdf_does_not_open_missing_or_stale_pdf(tmp_path: Path) -> None:
    opened: list[str] = []

    assert not open_local_pdf(tmp_path / "missing.pdf", opener=lambda uri: opened.append(uri))
    assert opened == []


def test_preview_filename_cannot_escape_controlled_directory(tmp_path: Path) -> None:
    try:
        prepare_stable_preview(tmp_path, "../outside.pdf")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe preview filename was accepted")

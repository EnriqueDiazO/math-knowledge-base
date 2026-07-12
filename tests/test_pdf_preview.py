"""Tests for the shared local PDF preview lifecycle."""

# ruff: noqa: D103

from pathlib import Path

import pytest

from editor.pdf_preview import open_local_pdf
from editor.pdf_preview import prepare_stable_preview


def test_prepare_stable_preview_removes_stale_pdf_and_auxiliaries(tmp_path: Path) -> None:
    preview_dir = tmp_path / "runtime with spaces"
    preview_dir.mkdir()
    for name in (
        "cornell_preview.pdf",
        "cornell_preview.aux",
        "cornell_preview.log",
        "cornell_preview_fit.log",
    ):
        (preview_dir / name).write_bytes(b"old")
    export = preview_dir / "user-export.zip"
    export.write_bytes(b"keep")
    unrelated_log = preview_dir / "unrelated.log"
    unrelated_log.write_bytes(b"keep-log")

    result = prepare_stable_preview(
        preview_dir,
        "cornell_preview.pdf",
        allowed_root=tmp_path,
    )

    assert result == preview_dir.resolve() / "cornell_preview.pdf"
    assert not result.exists()
    assert not (preview_dir / "cornell_preview.aux").exists()
    assert not (preview_dir / "cornell_preview.log").exists()
    assert not (preview_dir / "cornell_preview_fit.log").exists()
    assert export.exists()
    assert unrelated_log.read_bytes() == b"keep-log"


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
    with pytest.raises(ValueError, match="plain PDF filename"):
        prepare_stable_preview(
            tmp_path,
            "../outside.pdf",
            allowed_root=tmp_path,
        )


def test_preview_directory_symlink_cannot_escape_allowed_root(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    outside = tmp_path / "outside"
    runtime.mkdir()
    outside.mkdir()
    unrelated = outside / "unrelated.log"
    unrelated.write_bytes(b"must survive")
    (runtime / "cornell_preview").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="Symbolic links"):
        prepare_stable_preview(
            runtime / "cornell_preview",
            "cornell_preview.pdf",
            allowed_root=runtime,
        )

    assert unrelated.read_bytes() == b"must survive"
    assert not (outside / "cornell_preview.pdf").exists()


def test_preview_rejects_a_symlink_ancestor_of_a_missing_allowed_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    allowed = alias / "runtime"

    with pytest.raises(ValueError, match="Symbolic links"):
        prepare_stable_preview(
            allowed / "cornell_preview",
            "cornell_preview.pdf",
            allowed_root=allowed,
        )

    assert not (outside / "runtime").exists()


def test_preview_rejects_the_installed_package_tree() -> None:
    project_root = Path(__file__).resolve().parents[1]
    preview = project_root / "templates_latex" / "forbidden_preview.pdf"

    with pytest.raises(ValueError, match="installed MathMongo package"):
        prepare_stable_preview(
            project_root / "templates_latex",
            preview.name,
            allowed_root=project_root,
        )

    assert not preview.exists()

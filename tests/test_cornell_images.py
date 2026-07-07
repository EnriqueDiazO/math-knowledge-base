"""Tests for Cornell region images backed by media_assets."""

# ruff: noqa: D103

from __future__ import annotations

import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Any

import pytest

from editor import note_export
from editor.cornell import media as cornell_media
from editor.cornell import renderer
from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.persistence import build_cornell_note_document
from editor.cornell.service import add_cornell_region_image
from editor.cornell.service import remove_cornell_region_image


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _tiny_png_bytes() -> bytes:
    raw_scanline = b"\x00\xcc\xdd\xff"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw_scanline))
        + _png_chunk(b"IEND", b"")
    )


def _write_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asset_id: str, filename: str = "Imagen Á.png") -> dict[str, Any]:
    monkeypatch.setattr(cornell_media, "PROJECT_ROOT", tmp_path)
    media_dir = tmp_path / "media" / "images"
    media_dir.mkdir(parents=True, exist_ok=True)
    source = media_dir / filename
    source.write_bytes(_tiny_png_bytes())
    return {
        "asset_id": asset_id,
        "filename": filename,
        "original_filename": filename,
        "path": source.relative_to(tmp_path).as_posix(),
        "mime_type": "image/png",
    }


def _document_with_images(
    *,
    cue_ids: tuple[str, ...] = (),
    main_ids: tuple[str, ...] = (),
    summary_ids: tuple[str, ...] = (),
    main_latex: str = "",
) -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CornellPage(
                page_id="p001",
                order=1,
                cue=CornellRegion(heading="Cue", latex="Cue body", image_ids=cue_ids),
                main=CornellRegion(heading="Main", latex=main_latex or "Main body", image_ids=main_ids),
                summary=CornellRegion(heading="Summary", latex="Summary body", image_ids=summary_ids),
            ),
        ),
    )


def pdfinfo_text(pdf_path: Path) -> str:
    return subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_image_ids_round_trip_by_region() -> None:
    document = _document_with_images(
        cue_ids=("cue-img",),
        main_ids=("main-img",),
        summary_ids=("summary-img",),
    )

    restored = CornellDocument.from_dict(document.to_dict())

    page = restored.ordered_pages()[0]
    assert page.cue.image_ids == ("cue-img",)
    assert page.main.image_ids == ("main-img",)
    assert page.summary.image_ids == ("summary-img",)


def test_region_images_render_with_resizebox_in_each_region() -> None:
    document = _document_with_images(
        cue_ids=("cue-img",),
        main_ids=("main-img",),
        summary_ids=("summary-img",),
    )
    tex = renderer.generate_cornell_document_tex(
        document,
        asset_paths_by_id={
            "cue-img": "cornell_assets/media/cue.png",
            "main-img": "cornell_assets/media/main.png",
            "summary-img": "cornell_assets/media/summary.png",
        },
    )

    assert r"\resizebox{1.9in}{!}{\includegraphics{cornell_assets/media/cue.png}}" in tex
    assert r"\resizebox{5.35in}{!}{\includegraphics{cornell_assets/media/main.png}}" in tex
    assert r"\resizebox{5.7in}{!}{\includegraphics{cornell_assets/media/summary.png}}" in tex


def test_multiple_images_and_same_image_used_in_two_regions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = _write_asset(tmp_path, monkeypatch, "shared-img")
    document = _document_with_images(cue_ids=("shared-img",), main_ids=("shared-img",))

    result = renderer.render_cornell_document(
        document,
        tmp_path / "out",
        "same_image",
        assets_by_id={"shared-img": asset},
    )

    tex = result.tex_path.read_text(encoding="utf-8")
    copied_files = list((tmp_path / "out" / "cornell_assets" / "media").iterdir())
    assert result.success, result.message
    assert len(copied_files) == 1
    assert tex.count(r"\resizebox") == 2


def test_inserted_stable_reference_replaces_without_duplicate_append() -> None:
    ref = cornell_media.cornell_image_reference("asset-1")
    document = _document_with_images(main_ids=("asset-1",), main_latex=f"Antes\n{ref}\nDespues")

    tex = renderer.generate_cornell_document_tex(
        document,
        asset_paths_by_id={"asset-1": "cornell_assets/media/asset.png"},
    )

    assert ref not in tex
    assert tex.count(r"\resizebox{5.35in}") == 1


def test_remove_region_image_does_not_delete_asset() -> None:
    document = _document_with_images(main_ids=("asset-1", "asset-2"))

    updated = remove_cornell_region_image(
        document,
        page_index=0,
        region_name="main",
        asset_id="asset-1",
    )

    assert updated.ordered_pages()[0].main.image_ids == ("asset-2",)


def test_add_region_image_avoids_duplicates() -> None:
    document = _document_with_images(cue_ids=("asset-1",))

    updated = add_cornell_region_image(
        document,
        page_index=0,
        region_name="cue",
        asset_id="asset-1",
    )

    assert updated.ordered_pages()[0].cue.image_ids == ("asset-1",)


def test_renderer_copies_asset_with_safe_filename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = _write_asset(tmp_path, monkeypatch, "asset-safe", filename="Mi imagen rara Á.png")
    document = _document_with_images(main_ids=("asset-safe",))

    result = renderer.render_cornell_document(
        document,
        tmp_path / "out",
        "safe_name",
        assets_by_id={"asset-safe": asset},
    )

    assert result.success, result.message
    tex = result.tex_path.read_text(encoding="utf-8")
    assert "mi_imagen_rara_a_asset-sa.png" in tex
    assert (tmp_path / "out" / "cornell_assets" / "media" / "mi_imagen_rara_a_asset-sa.png").exists()


def test_missing_asset_fails_clearly(tmp_path: Path) -> None:
    document = _document_with_images(summary_ids=("missing-asset",))

    result = renderer.render_cornell_document(document, tmp_path, "missing_asset")

    assert not result.success
    assert "Cornell image asset not found: missing-asset" in result.message


def test_pdf_with_image_compiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for image PDF verification")
    asset = _write_asset(tmp_path, monkeypatch, "main-img")
    document = _document_with_images(main_ids=("main-img",))

    result = renderer.render_cornell_document(
        document,
        tmp_path / "out",
        "image_pdf",
        assets_by_id={"main-img": asset},
    )

    assert result.success, result.message
    assert "Pages:           1" in pdfinfo_text(result.pdf_path)


def test_export_multipage_cornell_preserves_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for image PDF verification")
    asset = _write_asset(tmp_path, monkeypatch, "asset-export")
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            _document_with_images(cue_ids=("asset-export",)).ordered_pages()[0],
            CornellPage(
                page_id="p002",
                order=2,
                cue=CornellRegion(heading="Cue 2", latex="Cue 2"),
                main=CornellRegion(heading="Main 2", latex="Main 2", image_ids=("asset-export",)),
                summary=CornellRegion(heading="Summary 2", latex="Summary 2"),
            ),
        ),
    )
    note = build_cornell_note_document(
        {
            "_id": "cornell-images",
            "title": "Cornell images",
            "date": "2026-07-07",
            "project": "Cornell",
            "context": "debug",
        },
        document,
    )
    note["_id"] = "cornell-images"

    result = note_export.export_note_pdf(
        note,
        output_dir=tmp_path / "export",
        assets_by_id={"asset-export": asset},
    )

    assert result.note_format == CORNELL_NOTE_FORMAT
    assert "Pages:           2" in pdfinfo_text(result.pdf_path)
    assert result.render_result is not None
    assert result.render_result.tex_path.read_text(encoding="utf-8").count(r"\resizebox") == 2

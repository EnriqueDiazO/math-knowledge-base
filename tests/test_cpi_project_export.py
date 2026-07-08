"""Tests for editable CPI LaTeX project export."""

# ruff: noqa: D103

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest

from editor.cornell import media as cornell_media
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_footer_text
from editor.cpi.models import DEFAULT_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.project_export import export_cpi_project


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def _tiny_png_bytes() -> bytes:
    width = 20
    raw_scanline = b"\x00" + (b"\xcc\xdd\xff" * width)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, 1, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw_scanline))
        + _png_chunk(b"IEND", b"")
    )


def _write_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asset_id: str,
    filename: str,
) -> dict[str, Any]:
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


def metadata(title: str = "Álgebra CPI") -> dict[str, Any]:
    return {
        "title": title,
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "tags": ["cpi", "latex"],
    }


def one_page_document(
    *,
    comprehension_ids: tuple[str, ...] = (),
    production_ids: tuple[str, ...] = (),
    integration_ids: tuple[str, ...] = (),
    attribution: CornellAttribution | None = None,
    watermark: CornellWatermark | None = None,
) -> CpiDocument:
    return CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CpiPage(
                page_number=1,
                comprehension=CpiRegion(
                    heading="Comprensión",
                    latex="Entendí la definición.",
                    image_ids=comprehension_ids,
                ),
                production=CpiRegion(
                    heading="Producción",
                    latex=r"\[ a+b=b+a \]",
                    image_ids=production_ids,
                ),
                integration=CpiRegion(
                    heading="Integración",
                    latex="Usarlo en el siguiente ejercicio.",
                    image_ids=integration_ids,
                ),
            ),
        ),
        attribution=attribution or CornellAttribution(),
        watermark=watermark or CornellWatermark(),
    )


def multipage_document() -> CpiDocument:
    first = one_page_document().ordered_pages()[0]
    second = CpiPage(
        page_number=2,
        comprehension=CpiRegion(heading="Comprensión", latex="Segunda comprensión."),
        production=CpiRegion(heading="Producción", latex="Segunda producción."),
        integration=CpiRegion(heading="Integración", latex="Segunda integración."),
    )
    return CpiDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(second, first))


def long_text(sentences: int) -> str:
    return " ".join(
        "Sea una propiedad estable bajo suma y producto."
        for _ in range(sentences)
    )


def pdfinfo_text(pdf_path: Path) -> str:
    return subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def pdf_page_count(pdf_path: Path) -> int:
    for line in pdfinfo_text(pdf_path).splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", maxsplit=1)[1].strip())
    raise AssertionError(f"pdfinfo did not report a page count for {pdf_path}")


def compile_tex(project_dir: Path, filename: str) -> None:
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", filename],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )


def assert_no_absolute_paths(project_dir: Path, forbidden: str) -> None:
    for path in project_dir.rglob("*"):
        if path.suffix.lower() not in {".tex", ".md", ".json"}:
            continue
        assert forbidden not in path.read_text(encoding="utf-8")


def test_export_project_one_page_structure_and_metadata(tmp_path: Path) -> None:
    result = export_cpi_project(one_page_document(), metadata(), tmp_path)
    project_dir = result.project_dir

    assert project_dir.name == "Algebra_CPI"
    for filename in ("Notas.tex", "README.md", "metadata.json"):
        assert (project_dir / filename).exists()
    assert (project_dir / "templates" / "cpi_landscape_letter_v1.tex").exists()
    assert (project_dir / "images").is_dir()
    assert (project_dir / "contenido" / "pagina_001" / "comprension.tex").exists()
    assert (project_dir / "contenido" / "pagina_001" / "produccion.tex").exists()
    assert (project_dir / "contenido" / "pagina_001" / "integracion.tex").exists()

    notas = (project_dir / "Notas.tex").read_text(encoding="utf-8")
    assert "letterpaper" in notas
    assert "landscape" in notas
    assert "CPIComprehension" in notas
    assert "CPIProduction" in notas
    assert "CPIIntegration" in notas

    payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert payload["title"] == "Álgebra CPI"
    assert payload["note_format"] == "cpi_v1"
    assert payload["schema_version"] == 1
    assert payload["page_numbers"] == [1]
    assert payload["attribution"]["enabled"] is False
    assert payload["watermark"]["enabled"] is False


def test_export_project_copies_images_without_mixing_zones(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comp = _write_asset(tmp_path, monkeypatch, "img-comp", "Comprensión.png")
    prod = _write_asset(tmp_path, monkeypatch, "img-prod", "Producción.png")
    integ = _write_asset(tmp_path, monkeypatch, "img-int", "Integración.png")
    unused = _write_asset(tmp_path, monkeypatch, "unused", "Unused.png")

    result = export_cpi_project(
        one_page_document(
            comprehension_ids=("img-comp",),
            production_ids=("img-prod",),
            integration_ids=("img-int",),
        ),
        metadata("Con imagen"),
        tmp_path / "out",
        assets_by_id={
            "img-comp": comp,
            "img-prod": prod,
            "img-int": integ,
            "unused": unused,
        },
    )

    copied = sorted(path.name for path in (result.project_dir / "images").iterdir())
    assert len(copied) == 3
    assert all("unused" not in filename.lower() for filename in copied)

    page_dir = result.project_dir / "contenido" / "pagina_001"
    comprension = (page_dir / "comprension.tex").read_text(encoding="utf-8")
    produccion = (page_dir / "produccion.tex").read_text(encoding="utf-8")
    integracion = (page_dir / "integracion.tex").read_text(encoding="utf-8")
    assert "img-comp" in comprension
    assert "img-prod" not in comprension
    assert "img-int" not in comprension
    assert "img-prod" in produccion
    assert "img-comp" not in produccion
    assert "img-int" not in produccion
    assert "img-int" in integracion
    assert "img-comp" not in integracion
    assert "img-prod" not in integracion
    assert str(tmp_path) not in comprension + produccion + integracion


def test_export_project_zip_contains_complete_source_tree(tmp_path: Path) -> None:
    result = export_cpi_project(multipage_document(), metadata("Zip completo"), tmp_path)

    with zipfile.ZipFile(result.zip_path) as archive:
        names = set(archive.namelist())

    root = result.project_dir.name
    assert f"{root}/Notas.tex" in names
    assert f"{root}/contenido/pagina_001/comprension.tex" in names
    assert f"{root}/contenido/pagina_002/produccion.tex" in names
    assert f"{root}/templates/cpi_landscape_letter_v1.tex" in names
    assert f"{root}/metadata.json" in names


def test_export_project_preserves_identity_and_copies_watermark_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watermark_asset = _write_asset(tmp_path, monkeypatch, "watermark-logo", "Marca.png")
    attribution = CornellAttribution(
        enabled=True,
        mode="auto",
        author="Enrique Díaz Ocampo",
        course="Python",
        year="2026",
        position="bottom_right",
    )
    watermark = CornellWatermark(
        enabled=True,
        type="image",
        image_id="watermark-logo",
        opacity=0.12,
        scale=0.35,
        position="top_right",
    )

    result = export_cpi_project(
        one_page_document(attribution=attribution, watermark=watermark),
        metadata("Identidad CPI"),
        tmp_path / "out",
        assets_by_id={"watermark-logo": watermark_asset},
    )

    notas = (result.project_dir / "Notas.tex").read_text(encoding="utf-8")
    payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    copied = sorted(path.name for path in (result.project_dir / "images").iterdir())

    assert build_footer_text(attribution) in notas
    assert len(copied) == 1
    assert f"images/{copied[0]}" in notas
    assert payload["attribution"] == attribution.to_dict()
    assert payload["watermark"] == watermark.to_dict()
    assert_no_absolute_paths(result.project_dir, str(tmp_path))
    with zipfile.ZipFile(result.zip_path) as archive:
        names = set(archive.namelist())
    assert f"{result.project_dir.name}/images/{copied[0]}" in names


def test_export_project_has_no_absolute_paths_and_does_not_need_mongo(tmp_path: Path) -> None:
    class ExplodingDb:
        def __getitem__(self, key: str) -> object:
            raise AssertionError(f"Unexpected Mongo access: {key}")

    result = export_cpi_project(
        one_page_document(),
        metadata("Sin Mongo"),
        tmp_path,
        db=ExplodingDb(),
    )

    assert_no_absolute_paths(result.project_dir, str(tmp_path))


def test_export_project_compiles_multipage_landscape_letter(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for CPI project compilation")
    result = export_cpi_project(multipage_document(), metadata("Compilable"), tmp_path / "out")

    compile_tex(result.project_dir, "Notas.tex")

    assert pdf_page_count(result.project_dir / "Notas.pdf") == 2
    assert "792 x 612 pts" in pdfinfo_text(result.project_dir / "Notas.pdf")


def test_export_project_preserves_auto_fit_in_notas(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for CPI project compilation")
    page = CpiPage(
        page_number=1,
        comprehension=CpiRegion(heading="Comprensión", latex=long_text(55)),
        production=CpiRegion(heading="Producción", latex=long_text(50)),
        integration=CpiRegion(heading="Integración", latex=long_text(40)),
    )
    document = CpiDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(page,))

    result = export_cpi_project(document, metadata("Autoajuste"), tmp_path / "out")

    notas = (result.project_dir / "Notas.tex").read_text(encoding="utf-8")
    assert notas.count(r"\begin{adjustbox}{scale=") == 3

    compile_tex(result.project_dir, "Notas.tex")

    assert pdf_page_count(result.project_dir / "Notas.pdf") == 1

"""Tests for editable Cornell LaTeX project export."""

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
from editor.cornell.content_blocks import apply_split_proposal
from editor.cornell.content_blocks import split_region_to_fit
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_footer_text
from editor.cornell.project_export import _zip_project
from editor.cornell.project_export import export_cornell_project
from editor.cornell.renderer import generate_cornell_document_tex
from tests.test_cornell_content_blocks import always_fit_engine
from tests.test_cornell_content_blocks import mandatory_overflow_page
from tests.test_cornell_renderer import HREF_REGRESSION_LATEX
from tests.test_cornell_renderer import HREF_REGRESSION_URL
from tests.test_cornell_renderer import pdf_contains_uri


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


def _write_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    asset_id: str,
    filename: str = "Imagen Á.png",
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


def metadata(title: str = "Álgebra Cornell") -> dict[str, Any]:
    return {
        "title": title,
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "tags": ["cornell", "latex"],
    }


def one_page_document(main_latex: str | None = None, image_ids: tuple[str, ...] = ()) -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CornellPage(
                page_id="p001",
                order=1,
                cue=CornellRegion(heading="Cue 1", latex="Idea principal."),
                main=CornellRegion(
                    heading="Main 1",
                    latex=main_latex
                    or "\\begin{definition}{Grupo}\nUn grupo es un conjunto con una operacion.\n\\end{definition}",
                    image_ids=image_ids,
                ),
                summary=CornellRegion(
                    heading="Summary 1",
                    latex="\\begin{remark}{Nota}\nResumen.\n\\end{remark}",
                ),
            ),
        ),
    )


def multipage_document(image_ids: tuple[str, ...] = ()) -> CornellDocument:
    first = one_page_document(image_ids=image_ids).ordered_pages()[0]
    second = CornellPage(
        page_id="p002",
        order=2,
        cue=CornellRegion(heading="Cue 2", latex="Segunda idea."),
        main=CornellRegion(
            heading="Main 2",
            latex="\\begin{theorem}{T}\nSi $a=b$, entonces $b=a$.\n\\end{theorem}",
        ),
        summary=CornellRegion(heading="Summary 2", latex="Cierre."),
    )
    return CornellDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(second, first))


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


def compile_cornell_project(project_dir: Path) -> None:
    for filename in ("Izquierda.tex", "Derecha.tex", "Abajo.tex", "Notas.tex"):
        compile_tex(project_dir, filename)


def assert_no_absolute_paths(project_dir: Path, forbidden: str) -> None:
    for path in project_dir.rglob("*"):
        if path.suffix.lower() not in {".tex", ".md", ".json"}:
            continue
        assert forbidden not in path.read_text(encoding="utf-8")


def test_export_project_one_page_structure_and_metadata(tmp_path: Path) -> None:
    result = export_cornell_project(one_page_document(), metadata(), tmp_path)
    project_dir = result.project_dir

    assert project_dir.name == "Algebra_Cornell"
    for filename in (
        "Notas.tex",
        "Izquierda.tex",
        "Derecha.tex",
        "Abajo.tex",
        "A.tex",
        "B.tex",
        "C.tex",
        "README.md",
        "metadata.json",
    ):
        assert (project_dir / filename).exists()
    assert (project_dir / "images").is_dir()
    assert (project_dir / "images" / "lineas.png").exists()
    assert (project_dir / "contenido" / "pagina_001" / "izquierda.tex").exists()
    assert (project_dir / "contenido" / "pagina_001" / "derecha.tex").exists()
    assert (project_dir / "contenido" / "pagina_001" / "abajo.tex").exists()

    derecha_template = (project_dir / "B.tex").read_text(encoding="utf-8")
    assert r"\AddToHook{shipout/background}" in derecha_template
    assert "images/lineas.png" in derecha_template
    assert "opacity=0.2" in derecha_template
    assert "width=6in" in derecha_template

    payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert payload["title"] == "Álgebra Cornell"
    assert payload["note_format"] == "cornell_math_v1"
    assert payload["schema_version"] == 1
    assert payload["page_ids"] == ["p001"]
    assert payload["order"] == [{"page_id": "p001", "order": 1}]


def test_export_project_replaces_only_an_identifiable_cornell_project(tmp_path: Path) -> None:
    output_root = tmp_path / "projects"
    first = export_cornell_project(
        one_page_document(),
        metadata("Proyecto propio"),
        output_root,
        allowed_root=tmp_path,
    )
    stale = first.project_dir / "stale.tmp"
    stale.write_bytes(b"old")

    second = export_cornell_project(
        one_page_document(),
        metadata("Proyecto propio"),
        output_root,
        allowed_root=tmp_path,
    )

    assert second.project_dir == first.project_dir
    assert not stale.exists()
    assert json.loads(second.metadata_path.read_text(encoding="utf-8"))["note_format"] == (
        "cornell_math_v1"
    )


def test_export_project_preserves_unrelated_same_name_directory(tmp_path: Path) -> None:
    output_root = tmp_path / "projects"
    unrelated = output_root / "Proyecto_ajeno"
    unrelated.mkdir(parents=True)
    user_source = unrelated / "user_source.tex"
    user_source.write_bytes(b"must survive")

    with pytest.raises(FileExistsError, match="Refusing to replace"):
        export_cornell_project(
            one_page_document(),
            metadata("Proyecto ajeno"),
            output_root,
            allowed_root=tmp_path,
        )

    assert user_source.read_bytes() == b"must survive"
    assert not (unrelated / "metadata.json").exists()


def test_export_project_rejects_symlink_escape_from_allowed_root(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    outside = tmp_path / "outside"
    runtime.mkdir()
    outside.mkdir()
    marker = outside / "user_source.tex"
    marker.write_bytes(b"must survive")
    (runtime / "cornell").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="Symbolic links"):
        export_cornell_project(
            one_page_document(),
            metadata("Escape"),
            runtime / "cornell" / "editable_projects",
            allowed_root=runtime,
        )

    assert marker.read_bytes() == b"must survive"
    assert not (outside / "editable_projects").exists()


def test_export_project_rejects_the_installed_package_tree() -> None:
    project_root = Path(__file__).resolve().parents[1]
    forbidden = project_root / "templates_latex" / "Forbidden"

    with pytest.raises(ValueError, match="installed MathMongo package"):
        export_cornell_project(
            one_page_document(),
            metadata("Forbidden"),
            project_root / "templates_latex",
            allowed_root=project_root,
        )

    assert not forbidden.exists()


def test_export_project_masters_include_all_pages_in_order(tmp_path: Path) -> None:
    result = export_cornell_project(multipage_document(), metadata("Multipágina"), tmp_path)

    izquierda = (result.project_dir / "Izquierda.tex").read_text(encoding="utf-8")
    derecha = (result.project_dir / "Derecha.tex").read_text(encoding="utf-8")
    abajo = (result.project_dir / "Abajo.tex").read_text(encoding="utf-8")

    assert izquierda.index("pagina_001/izquierda.tex") < izquierda.index("pagina_002/izquierda.tex")
    assert r"\newpage" in izquierda
    assert "pagina_001/derecha.tex" in derecha
    assert "pagina_002/derecha.tex" in derecha
    assert "pagina_001/abajo.tex" in abajo
    assert "pagina_002/abajo.tex" in abajo
    assert "% \\input" not in izquierda


def test_export_project_copies_only_used_images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    used = _write_asset(tmp_path, monkeypatch, "used-img")
    unused = _write_asset(tmp_path, monkeypatch, "unused-img", filename="Unused.png")

    result = export_cornell_project(
        one_page_document(image_ids=("used-img",)),
        metadata("Con imagen"),
        tmp_path / "out",
        assets_by_id={"used-img": used, "unused-img": unused},
    )

    copied = sorted(path.name for path in (result.project_dir / "images").iterdir())
    assert "lineas.png" in copied
    content_images = [filename for filename in copied if filename != "lineas.png"]
    assert len(content_images) == 1
    assert content_images[0].startswith("imagen_a_used-img")
    assert all("unused" not in filename.lower() for filename in copied)
    derecha = (result.project_dir / "contenido" / "pagina_001" / "derecha.tex").read_text(
        encoding="utf-8"
    )
    assert "images/" in derecha
    assert str(tmp_path) not in derecha


def test_export_project_split_pages_preserve_overflow_division(tmp_path: Path) -> None:
    source = mandatory_overflow_page()
    proposal = split_region_to_fit(source, "main", always_fit_engine, new_page_id="p002")
    split_document = apply_split_proposal(
        CornellDocument(
            schema_version=1,
            template_id=DEFAULT_TEMPLATE_ID,
            pages=(source,),
        ),
        0,
        proposal,
    )

    result = export_cornell_project(split_document, metadata("Dividida"), tmp_path)

    page1 = (result.project_dir / "contenido" / "pagina_001" / "derecha.tex").read_text(
        encoding="utf-8"
    )
    page2 = (result.project_dir / "contenido" / "pagina_002" / "derecha.tex").read_text(
        encoding="utf-8"
    )
    assert "\\begin{proposition}" not in page1
    assert "\\begin{proposition}" in page2


def test_export_project_zip_contains_complete_source_tree(tmp_path: Path) -> None:
    result = export_cornell_project(multipage_document(), metadata("Zip completo"), tmp_path)

    with zipfile.ZipFile(result.zip_path) as archive:
        names = set(archive.namelist())

    root = result.project_dir.name
    assert f"{root}/Notas.tex" in names
    assert f"{root}/Izquierda.tex" in names
    assert f"{root}/Derecha.tex" in names
    assert f"{root}/Abajo.tex" in names
    assert f"{root}/contenido/pagina_001/izquierda.tex" in names
    assert f"{root}/contenido/pagina_002/derecha.tex" in names
    assert f"{root}/images/lineas.png" in names
    assert f"{root}/metadata.json" in names


def test_zip_project_rejects_existing_zip_leaf_symlink(tmp_path: Path) -> None:
    project_dir = tmp_path / "cornell-project"
    project_dir.mkdir()
    (project_dir / "source.tex").write_text("source", encoding="utf-8")
    outside = tmp_path / "user-file.zip"
    outside.write_bytes(b"must survive")
    zip_path = project_dir.with_suffix(".zip")
    zip_path.symlink_to(outside)

    with pytest.raises(ValueError, match="Symbolic links"):
        _zip_project(project_dir)

    assert zip_path.is_symlink()
    assert outside.read_bytes() == b"must survive"


def test_zip_project_rejects_symlinked_intermediate_directory(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    project_dir = real_parent / "cornell-project"
    project_dir.mkdir(parents=True)
    (project_dir / "source.tex").write_text("source", encoding="utf-8")
    alias = tmp_path / "parent-alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="Symbolic links"):
        _zip_project(alias / project_dir.name)

    assert not project_dir.with_suffix(".zip").exists()


@pytest.mark.parametrize("link_kind", ("file", "directory"))
def test_zip_project_rejects_symlinks_inside_project(
    tmp_path: Path,
    link_kind: str,
) -> None:
    project_dir = tmp_path / "cornell-project"
    project_dir.mkdir()
    (project_dir / "source.tex").write_text("source", encoding="utf-8")
    link = project_dir / "linked-user-content"
    if link_kind == "file":
        outside = tmp_path / "outside.tex"
        outside.write_text("private", encoding="utf-8")
        link.symlink_to(outside)
    else:
        outside = tmp_path / "outside-dir"
        outside.mkdir()
        (outside / "private.tex").write_text("private", encoding="utf-8")
        link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        _zip_project(project_dir)

    assert not project_dir.with_suffix(".zip").exists()


def test_export_project_includes_identity_watermark_image_in_notas_and_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _write_asset(tmp_path, monkeypatch, "wm-logo", filename="Logo COCID.png")
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=one_page_document().pages,
        attribution=CornellAttribution(
            enabled=True,
            text="© 2026 Enrique Díaz Ocampo · Material docente",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id="wm-logo",
            opacity=0.05,
            scale=0.4,
            position="center",
        ),
    )

    result = export_cornell_project(
        document,
        metadata("Con marca"),
        tmp_path / "out",
        assets_by_id={"wm-logo": asset},
    )

    notas = (result.project_dir / "Notas.tex").read_text(encoding="utf-8")
    assert "images/logo_cocid_wm-logo.png" in notas
    assert "opacity=0.05" in notas
    assert r"width=0.4\paperwidth" in notas
    assert "© 2026 Enrique Díaz Ocampo" in notas
    assert str(tmp_path) not in notas
    assert (result.project_dir / "images" / "logo_cocid_wm-logo.png").exists()
    payload = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert len(payload["assets"]) == 1
    assert payload["assets"][0]["asset_id"] == "wm-logo"
    assert payload["assets"][0]["roles"] == ["watermark"]
    assert len(payload["assets"][0]["sha256"]) == 64
    assert not Path(payload["assets"][0]["path"]).is_absolute()

    with zipfile.ZipFile(result.zip_path) as archive:
        names = set(archive.namelist())

    root = result.project_dir.name
    assert f"{root}/images/logo_cocid_wm-logo.png" in names


def test_export_project_missing_watermark_is_controlled(tmp_path: Path) -> None:
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=one_page_document().pages,
        watermark=CornellWatermark(enabled=True, type="image", image_id="missing-logo"),
    )

    result = export_cornell_project(document, metadata("Marca faltante"), tmp_path)

    assert result.warnings == ("Asset de marca de agua no encontrado: missing-logo",)
    assert "missing-logo" not in (result.project_dir / "Notas.tex").read_text(encoding="utf-8")


def test_footer_text_matches_preview_tex_and_project_export(tmp_path: Path) -> None:
    attribution = CornellAttribution(
        enabled=True,
        mode="auto",
        author="Enrique Díaz Ocampo",
        course="Python",
        year="2026",
    )
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=one_page_document().pages,
        attribution=attribution,
    )
    expected_footer = build_footer_text(attribution)

    preview_tex = generate_cornell_document_tex(document)
    result = export_cornell_project(document, metadata("Footer consistente"), tmp_path)
    notas_tex = (result.project_dir / "Notas.tex").read_text(encoding="utf-8")

    assert expected_footer == "© 2026 Enrique Díaz Ocampo · Python"
    assert expected_footer in preview_tex
    assert expected_footer in notas_tex


def test_export_project_has_no_absolute_paths_and_does_not_need_mongo(tmp_path: Path) -> None:
    class ExplodingDb:
        def __getitem__(self, key: str) -> object:
            raise AssertionError(f"Unexpected Mongo access: {key}")

    result = export_cornell_project(
        one_page_document(),
        metadata("Sin Mongo"),
        tmp_path,
        db=ExplodingDb(),
    )

    assert_no_absolute_paths(result.project_dir, str(tmp_path))


def test_export_project_compiles_one_page_without_blank_pages(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for Cornell project compilation")
    result = export_cornell_project(one_page_document(), metadata("Una pagina"), tmp_path / "out")

    compile_cornell_project(result.project_dir)

    assert pdf_page_count(result.project_dir / "Izquierda.pdf") == 1
    assert pdf_page_count(result.project_dir / "Derecha.pdf") == 1
    assert pdf_page_count(result.project_dir / "Abajo.pdf") == 1
    assert pdf_page_count(result.project_dir / "Notas.pdf") == 1


def test_export_project_compiles_href_lists_utf8_and_math(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for Cornell project compilation")
    result = export_cornell_project(
        one_page_document(main_latex=HREF_REGRESSION_LATEX),
        metadata("Href Cornell"),
        tmp_path / "out",
    )

    derecha_template = (result.project_dir / "B.tex").read_text(encoding="utf-8")
    assert r"\usepackage{hyperref}" in derecha_template

    compile_cornell_project(result.project_dir)

    assert pdf_page_count(result.project_dir / "Derecha.pdf") == 1
    assert pdf_contains_uri(result.project_dir / "Derecha.pdf", HREF_REGRESSION_URL)


def test_export_project_compiles_two_pages_without_blank_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdfinfo") is None:
        pytest.skip("pdflatex and pdfinfo are required for Cornell project compilation")
    asset = _write_asset(tmp_path, monkeypatch, "main-img")
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=multipage_document(image_ids=("main-img",)).pages,
        attribution=CornellAttribution(enabled=True, text="© 2026 Enrique Díaz Ocampo"),
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id="main-img",
            opacity=0.05,
            scale=0.4,
        ),
    )
    result = export_cornell_project(
        document,
        metadata("Compilable"),
        tmp_path / "out",
        assets_by_id={"main-img": asset},
    )

    compile_cornell_project(result.project_dir)

    assert pdf_page_count(result.project_dir / "Izquierda.pdf") == 2
    assert pdf_page_count(result.project_dir / "Derecha.pdf") == 2
    assert pdf_page_count(result.project_dir / "Abajo.pdf") == 2
    assert pdf_page_count(result.project_dir / "Notas.pdf") == 2
    derecha_log = (result.project_dir / "Derecha.log").read_text(encoding="utf-8")
    assert derecha_log.count("<use images/lineas.png>") == 2

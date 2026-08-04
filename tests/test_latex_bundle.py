"""Unit coverage for portable LaTeX project bundles."""

# ruff: noqa: D103

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile

from bson import ObjectId

from editor.latex_bundle import DOWNLOAD_HELP
from editor.latex_bundle import DOWNLOAD_LABEL
from editor.latex_bundle import build_latex_project_bundle
from editor.latex_bundle import latex_project_download_options
from editor.note_export import build_note_latex_bundle
from editor.pdf_export import generar_tex_nota_latex
from exporters_latex.unified_document import UnifiedExportResult
from exporters_latex.unified_document import build_unified_document_bundle


def _archive(result):
    return ZipFile(BytesIO(result.zip_bytes))


def _bundle(**overrides):
    defaults = {
        "main_tex": "\\documentclass{article}\n\\usepackage{mathmongo-macros}\n\\begin{document}\n\\includegraphics{media/images/a.png}\n\\end{document}\n",
        "raw_body": "\\includegraphics{media/images/a.png}\n",
        "metadata": {"title": "Árbol", "_id": ObjectId("64b64c7e6c8c222b8139de31"), "created_at": datetime(2026, 8, 4, 12, 30)},
        "project_styles": {"mathmongo-macros.sty": "\\RequirePackage{amsmath}\n\\providecommand{\\osc}{\\operatorname{osc}}\n\\providecommand{\\Max}{\\operatorname{Max}}\n"},
        "images": [{"data": b"png-one", "path": "media/images/a.png", "filename": "a.png", "asset_id": "one"}],
        "source_type": "freeform",
        "source_id": "nota-1",
        "title": "Árbol",
    }
    defaults.update(overrides)
    return build_latex_project_bundle(**defaults)


def test_bundle_contains_required_portable_project_files() -> None:
    result = _bundle()
    with _archive(result) as archive:
        names = archive.namelist()
        root = "Arbol_latex/"
        assert root + "main.tex" in names
        assert root + "content/body.tex" in names
        assert root + "README.md" in names
        assert root + "manifest.json" in names
        assert root + "metadata/source.json" in names
        assert root + "styles/mathmongo-macros.sty" in names
        assert root + "user_macros.tex" in names
        assert root + "images/a.png" in names
        assert archive.read(root + "content/body.tex").decode() == "\\includegraphics{media/images/a.png}\n"
        main_tex = archive.read(root + "main.tex").decode()
        assert "\\usepackage{styles/mathmongo-macros}" in main_tex
        assert "\\InputIfFileExists{user_macros.tex}{}{}" in main_tex
        assert "\\includegraphics{images/a.png}" in main_tex


def test_bundle_is_safe_deterministic_and_has_download_parameters() -> None:
    first = _bundle(project_styles={"../bad.sty": "no", "mathmongo-macros.sty": "ok"})
    second = _bundle(project_styles={"../bad.sty": "no", "mathmongo-macros.sty": "ok"})
    assert first.zip_bytes == second.zip_bytes
    assert first.entries == tuple(sorted(first.entries))
    assert all(".." not in name and not name.startswith("/") for name in first.entries)
    assert any("ruta insegura" in warning for warning in first.warnings)
    options = latex_project_download_options(first)
    assert DOWNLOAD_LABEL == "Descargar proyecto TEX (.zip)"
    assert options["data"] == first.zip_bytes
    assert options["file_name"].endswith("_latex.zip")
    assert options["mime"] == "application/zip"
    assert options["help"] == DOWNLOAD_HELP


def test_multiple_and_missing_assets_do_not_block_a_bundle() -> None:
    result = _bundle(
        images=[
            {"data": b"one", "path": "media/images/first.png", "filename": "misma imagen.png"},
            {"data": b"two", "path": "media/images/second.jpg", "filename": "misma imagen.png"},
            {"data": None, "path": "media/images/lost.jpeg", "filename": "lost.jpeg", "asset_id": "lost"},
        ],
    )
    with _archive(result) as archive:
        names = archive.namelist()
        assert "Arbol_latex/images/misma_imagen.png" in names
        assert "Arbol_latex/images/misma_imagen_2.png" in names
        manifest = json.loads(archive.read("Arbol_latex/manifest.json"))
        assert manifest["missing_assets"] == ["media/images/lost.jpeg"]
    assert result.missing_assets == ("media/images/lost.jpeg",)


def test_no_image_document_and_unicode_jpeg_asset_are_portable() -> None:
    empty_result = _bundle(images=[])
    with _archive(empty_result) as archive:
        assert not any(name.startswith("Arbol_latex/images/") for name in archive.namelist())
    image_result = _bundle(
        images=[
            {
                "data": b"jpeg-bytes",
                "path": "media/images/área foto.jpeg",
                "filename": "área foto.jpeg",
            },
            {
                "data": b"",
                "path": "media/images/vacía.png",
                "filename": "vacía.png",
            },
        ]
    )
    with _archive(image_result) as archive:
        assert "Arbol_latex/images/area_foto.jpeg" in archive.namelist()
        assert "Arbol_latex/images/vacia.png" not in archive.namelist()
    assert "media/images/vacía.png" in image_result.missing_assets


def test_diagnostics_and_unknown_commands_are_preserved_without_inventing_macros() -> None:
    result = _bundle(
        chktex_report={"issues": [{"message": "warning"}]},
        latex_log="! Undefined control sequence.\nl.42 \\UnknownMacro\n",
        compilation_summary={"status": "failed", "returncode": 1, "pdf_valid": False},
    )
    with _archive(result) as archive:
        undefined = archive.read("Arbol_latex/diagnostics/undefined-commands.txt").decode()
        style = archive.read("Arbol_latex/styles/mathmongo-macros.sty").decode()
        assert "\\UnknownMacro" in undefined
        assert "UnknownMacro" not in style
        assert "\\providecommand{\\osc}" in style
        assert "\\providecommand{\\Max}" in style
        assert "Arbol_latex/diagnostics/chktex.txt" in archive.namelist()
        assert "Arbol_latex/diagnostics/latex.log" in archive.namelist()
        assert "Arbol_latex/diagnostics/compilation-summary.txt" in archive.namelist()


def test_metadata_is_json_safe_and_excludes_mongo_secrets() -> None:
    result = _bundle(
        metadata={
            "_id": ObjectId("64b64c7e6c8c222b8139de31"),
            "updated_at": datetime(2026, 8, 4, 9, 0),
            "mongo_uri": "mongodb://user:password@example.test/db",
            "credentials": {"password": "do-not-export"},
            "temporary_file": "/tmp/should-not-appear.tex",
        }
    )
    with _archive(result) as archive:
        source = archive.read("Arbol_latex/metadata/source.json").decode()
        parsed = json.loads(source)
        assert parsed["_id"] == "64b64c7e6c8c222b8139de31"
        assert parsed["updated_at"] == "2026-08-04T09:00:00"
        assert "mongodb://" not in source
        assert "do-not-export" not in source
        assert "/tmp/" not in source


def test_note_bundle_uses_the_canonical_note_tex_and_note_specific_assets() -> None:
    note = {
        "_id": "note-assets",
        "title": "Nota con imagen",
        "date": "2026-08-04",
        "latex_body": "\\osc f + \\Max A\\n\\includegraphics{media/images/notebook.png}",
        "image_ids": ["image-1"],
    }
    canonical = generar_tex_nota_latex(note, template="diario")
    result = build_note_latex_bundle(
        note,
        assets_by_id={
            "image-1": {
                "asset_id": "image-1",
                "path": "media/images/notebook.png",
                "filename": "notebook.png",
                "data": b"image-bytes",
            }
        },
    )
    with _archive(result) as archive:
        main_tex = archive.read("Nota_con_imagen_latex/main.tex").decode()
        assert main_tex.replace("styles/", "") == canonical.replace(
            "media/images/notebook.png", "images/notebook.png"
        )
        assert "Nota_con_imagen_latex/images/notebook.png" in archive.namelist()
        assert "Nota_con_imagen_latex/styles/mathmongo-macros.sty" in archive.namelist()
        assert archive.read("Nota_con_imagen_latex/content/body.tex").decode() == note["latex_body"]


def test_failed_compilation_and_chktex_warning_still_produce_valid_zip() -> None:
    result = _bundle(
        chktex_report={"issues": ["warning"]},
        compilation_summary={"status": "failed", "returncode": 1, "first_latex_error": "Undefined control sequence"},
    )
    with _archive(result) as archive:
        assert archive.testzip() is None
        assert "Arbol_latex/main.tex" in archive.namelist()
        assert "Arbol_latex/diagnostics/chktex.txt" in archive.namelist()
        assert "Arbol_latex/diagnostics/compilation-summary.txt" in archive.namelist()


def test_unified_document_bundle_preserves_fragments_and_failed_log(tmp_path) -> None:
    output_dir = tmp_path / "unified"
    concepts_dir = output_dir / "concepts"
    image_dir = output_dir / "media" / "images"
    concepts_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    master = output_dir / "source.tex"
    master.write_text(
        "\\documentclass{article}\n\\usepackage{mathmongo-macros}\n"
        "\\begin{document}\n\\input{concepts/001_example}\n\\end{document}\n",
        encoding="utf-8",
    )
    (concepts_dir / "001_example.tex").write_text(
        "\\includegraphics{media/images/chart.png}\n", encoding="utf-8"
    )
    (image_dir / "chart.png").write_bytes(b"chart")
    (output_dir / "mathmongo-macros.sty").write_text("\\RequirePackage{amsmath}\n", encoding="utf-8")
    log_path = output_dir / "build.log"
    log_path.write_text("! Undefined control sequence.\nl.12 \\StillUnknown\n", encoding="utf-8")
    result = UnifiedExportResult(
        master_tex_path=master,
        pdf_path=None,
        concepts_dir=concepts_dir,
        output_dir=output_dir,
        warnings=[],
        errors=["LaTeX failed"],
        latex_log_path=log_path,
        success=False,
    )
    bundle = build_unified_document_bundle(result, source="source", title="Documento")
    with _archive(bundle) as archive:
        assert "Documento_latex/concepts/001_example.tex" in archive.namelist()
        assert "Documento_latex/images/chart.png" in archive.namelist()
        fragment = archive.read("Documento_latex/concepts/001_example.tex").decode()
        assert "\\includegraphics{images/chart.png}" in fragment
        assert "Documento_latex/diagnostics/latex.log" in archive.namelist()
        assert "\\StillUnknown" in archive.read(
            "Documento_latex/diagnostics/undefined-commands.txt"
        ).decode()

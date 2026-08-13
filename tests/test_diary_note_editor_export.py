"""Direct Diario editor export tests for unsaved snapshots and zero persistence."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import json
import shutil
import subprocess
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import pytest

from editor import diary_note_editor_export
from editor.diary_note_editor_export import build_diary_editor_export_note
from editor.diary_note_editor_export import prepare_diary_editor_pdf_download
from editor.diary_note_editor_export import prepare_diary_editor_zip_download
from editor.diary_note_models import AcademicMetadata
from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import HeaderFooterSettings
from editor.diary_note_models import ListOfFiguresSettings
from editor.diary_note_models import ListOfTablesSettings
from editor.diary_note_models import NoteReference
from editor.diary_note_models import TableOfContentsSettings


class _RecordingCollection:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = deepcopy(document)
        self.write_calls: list[object] = []

    def update_one(self, *args: object, **kwargs: object) -> None:
        self.write_calls.append((args, kwargs))
        raise AssertionError("Editor export must never call update_one")


def _legacy_note() -> dict[str, Any]:
    return {
        "_id": "editor-export-legacy",
        "title": "Título almacenado",
        "date": "2026-08-01",
        "project": "Proyecto almacenado",
        "context": "estudio",
        "tags": ["guardado"],
        "latex_body": r"\chapter{Cuerpo almacenado}",
        "image_ids": [],
        "unknown_historical_field": {"preserve": True},
    }


def _unsaved_snapshot() -> tuple[dict[str, Any], dict[str, Any], DiaryNoteSettings]:
    original = _legacy_note()
    current_form = {
        **original,
        "title": "Título actual sin guardar",
        "date": "2026-08-12",
        "project": "Proyecto actual",
        "context": "investigación",
        "tags": ["actual", "sin_guardar"],
        "latex_body": (
            r"\chapter{Capítulo actual}"
            "\n"
            r"MARCADOR ACTUAL NO GUARDADO."
            "\n"
            r"\section{Sección actual}"
            "\n"
            r"\begin{figure}[htbp]\centering\rule{5cm}{3cm}"
            "\n"
            r"\caption{Figura actual sin guardar}\end{figure}"
            "\n"
            r"\begin{table}[htbp]\centering\begin{tabular}{cc}A & B \\ 1 & 2\end{tabular}"
            "\n"
            r"\caption{Tabla actual sin guardar}\end{table}"
            "\n"
        ),
    }
    settings = DiaryNoteSettings(
        academic_metadata=AcademicMetadata(
            institution="Institución actual",
            program="Programa actual",
            course_code="CUR-9",
            course_name="Curso actual",
            week="Semana 9",
            session="Sesión actual",
            short_title="Corto actual",
            author="Autor actual",
        ),
        page_layout=HeaderFooterSettings(
            enabled=True,
            header_left="{institution} · {course_code}",
            header_right="{short_title}",
            footer_left="PIE ACTUAL",
            footer_right="{author}",
            show_page_number=True,
        ),
        table_of_contents=TableOfContentsSettings(
            show_table_of_contents=True,
            toc_title="Contenido actual",
            toc_depth=2,
            position="after_metadata",
        ),
        list_of_figures=ListOfFiguresSettings(
            show_list_of_figures=True,
            title="Figuras actuales",
        ),
        list_of_tables=ListOfTablesSettings(
            show_list_of_tables=True,
            title="Tablas actuales",
        ),
        references=[
            NoteReference(
                authors="Autora actual",
                title="Referencia actual exportable",
                year_or_date="2026",
            ),
            NoteReference(note="BORRADOR OMITIDO SIN TÍTULO"),
        ],
    )
    return original, current_form, settings


def test_pdf_action_uses_unsaved_values_without_mongodb_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original, current_form, settings = _unsaved_snapshot()
    collection = _RecordingCollection(original)
    captured: dict[str, Any] = {}

    def fake_export(note: dict[str, Any], **kwargs: Any) -> SimpleNamespace:
        captured.update(deepcopy(note))
        output_dir = Path(kwargs["output_dir"])
        pdf_path = output_dir / "draft.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n% unsaved draft\n")
        return SimpleNamespace(
            pdf_path=pdf_path,
            file_name="draft.pdf",
            diagnostics={"status": "success", "passes": 2},
        )

    monkeypatch.setattr(diary_note_editor_export, "export_note_pdf", fake_export)
    snapshot = build_diary_editor_export_note(current_form, settings)
    download = prepare_diary_editor_pdf_download(snapshot)

    assert download.data.startswith(b"%PDF")
    assert captured["title"] == "Título actual sin guardar"
    assert "MARCADOR ACTUAL NO GUARDADO" in captured["latex_body"]
    assert captured["academic_metadata"]["institution"] == "Institución actual"
    assert captured["table_of_contents"]["show_table_of_contents"] is True
    assert captured["list_of_figures"]["show_list_of_figures"] is True
    assert captured["list_of_tables"]["show_list_of_tables"] is True
    assert len(captured["references"]) == 2
    assert collection.write_calls == []
    assert collection.document == original


def test_zip_action_uses_unsaved_values_and_contains_portable_project() -> None:
    original, current_form, settings = _unsaved_snapshot()
    collection = _RecordingCollection(original)
    snapshot = build_diary_editor_export_note(current_form, settings)

    bundle = prepare_diary_editor_zip_download(snapshot)

    with ZipFile(BytesIO(bundle.zip_bytes)) as archive:
        names = archive.namelist()
        root = names[0].split("/", 1)[0]
        required = {
            f"{root}/main.tex",
            f"{root}/content/body.tex",
            f"{root}/styles/notes.cls",
            f"{root}/styles/notes.sty",
            f"{root}/styles/miestilo.sty",
            f"{root}/styles/mathmongo-macros.sty",
            f"{root}/README.md",
            f"{root}/metadata/source.json",
        }
        assert required <= set(names)
        main_tex = archive.read(f"{root}/main.tex").decode()
        body_tex = archive.read(f"{root}/content/body.tex").decode()
        metadata = json.loads(archive.read(f"{root}/metadata/source.json"))
    assert "Título actual sin guardar" in main_tex
    assert "Institución actual" in main_tex
    assert r"\tableofcontents" in main_tex
    assert main_tex.count(r"\listoffigures") == 1
    assert main_tex.count(r"\listoftables") == 1
    assert main_tex.count(r"\bibitem{") == 1
    assert "Referencia actual exportable" in main_tex
    assert "BORRADOR OMITIDO" not in main_tex
    assert "MARCADOR ACTUAL NO GUARDADO" in body_tex
    assert metadata["title"] == "Título actual sin guardar"
    assert collection.write_calls == []
    assert collection.document == original


def test_export_helpers_do_not_change_current_form_state_or_legacy_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original, current_form, settings = _unsaved_snapshot()
    form_state = {
        "loaded_identity": original["_id"],
        "diary_selected_mode": "edit",
        "institution_widget": "Institución actual",
        "show_list_of_figures_widget": True,
        "list_of_figures_title_widget": "Figuras actuales",
        "show_list_of_tables_widget": True,
        "list_of_tables_title_widget": "Tablas actuales",
        "reference_ids": [settings.references[0].reference_id],
    }
    before_state = deepcopy(form_state)
    before_original = deepcopy(original)

    def fake_export(note: dict[str, Any], **kwargs: Any) -> SimpleNamespace:
        pdf_path = Path(kwargs["output_dir"]) / "state.pdf"
        pdf_path.write_bytes(b"%PDF-state")
        return SimpleNamespace(
            pdf_path=pdf_path,
            file_name="state.pdf",
            diagnostics={"status": "success"},
        )

    monkeypatch.setattr(diary_note_editor_export, "export_note_pdf", fake_export)
    snapshot = build_diary_editor_export_note(current_form, settings)
    prepare_diary_editor_pdf_download(snapshot)
    prepare_diary_editor_zip_download(snapshot)

    assert form_state == before_state
    assert original == before_original
    assert not any(
        field in original
        for field in (
            "academic_metadata",
            "page_layout",
            "table_of_contents",
            "list_of_figures",
            "list_of_tables",
            "references",
        )
    )


def test_actual_editor_pdf_contains_layout_toc_and_only_exportable_references(
    tmp_path: Path,
) -> None:
    if shutil.which("pdflatex") is None or shutil.which("pdftotext") is None:
        pytest.skip("pdflatex and pdftotext are required for editor PDF verification")
    _, current_form, settings = _unsaved_snapshot()
    snapshot = build_diary_editor_export_note(current_form, settings)

    download = prepare_diary_editor_pdf_download(snapshot)
    pdf_path = tmp_path / download.file_name
    pdf_path.write_bytes(download.data)
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert int(download.diagnostics.get("passes") or 0) >= 2
    assert "Título actual sin guardar" in text
    assert "MARCADOR ACTUAL NO GUARDADO" in text
    assert "Institución actual" in text
    assert "PIE ACTUAL" in text
    assert "Contenido actual" in text
    assert "Figuras actuales" in text
    assert "Tablas actuales" in text
    assert "Figura actual sin guardar" in text
    assert "Tabla actual sin guardar" in text
    assert "Referencia actual exportable" in text
    assert "BORRADOR OMITIDO" not in text


def test_editor_zip_recompiles_unsaved_indexes_in_exactly_two_passes(tmp_path: Path) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is required for editor ZIP verification")
    original, current_form, settings = _unsaved_snapshot()
    collection = _RecordingCollection(original)
    snapshot = build_diary_editor_export_note(current_form, settings)
    bundle = prepare_diary_editor_zip_download(snapshot)

    with ZipFile(BytesIO(bundle.zip_bytes)) as archive:
        archive.extractall(tmp_path)
        root = archive.namelist()[0].split("/", 1)[0]
    project_dir = tmp_path / root
    command = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
    first = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=project_dir, capture_output=True, text=True, check=False)

    assert first.returncode == 0, first.stdout[-5000:]
    assert second.returncode == 0, second.stdout[-5000:]
    assert "Figura actual sin guardar" in (project_dir / "main.lof").read_text(encoding="utf-8")
    assert "Tabla actual sin guardar" in (project_dir / "main.lot").read_text(encoding="utf-8")
    assert collection.write_calls == []
    assert collection.document == original


@pytest.mark.parametrize("note_format", ["cornell_math_v1", "cpi_v1"])
def test_direct_diario_editor_export_rejects_specialized_note_formats(
    note_format: str,
) -> None:
    note = {**_legacy_note(), "note_format": note_format}

    with pytest.raises(ValueError, match="sólo admite notas Diario"):
        build_diary_editor_export_note(note, DiaryNoteSettings())


def test_export_boundary_has_no_persistence_api_and_save_keeps_minimal_diff() -> None:
    export_source = Path("editor/diary_note_editor_export.py").read_text(encoding="utf-8")
    editor_source = Path("editor/cuaderno_page.py").read_text(encoding="utf-8")

    assert "update_one" not in export_source
    assert '"$set"' not in export_source
    assert "persist_diary_note_update" not in export_source
    assert "prepare_diary_editor_pdf_download(" in editor_source
    assert "prepare_diary_editor_zip_download(" in editor_source
    assert editor_source.count("persist_diary_note_update(") == 1
    edit_source = editor_source.split("def _render_note_editor", 1)[1].split(
        "def _render_selected_note_panel", 1
    )[0]
    assert edit_source.index('"Guardar cambios"') < edit_source.index('"📄 Descargar PDF"')
    assert edit_source.index('"📄 Descargar PDF"') < edit_source.index('"📦 Exportar ZIP LaTeX"')
    assert edit_source.index('"📦 Exportar ZIP LaTeX"') < edit_source.index('"Cancelar"')

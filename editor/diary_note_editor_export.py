"""Side-effect-free export preparation for the current Diario editor draft."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import note_with_settings
from editor.latex_bundle import LatexBundleResult
from editor.note_export import build_note_latex_bundle
from editor.note_export import export_note_pdf
from editor.note_export import normalized_note_format


@dataclass(frozen=True, slots=True)
class DiaryEditorPdfDownload:
    """In-memory PDF download produced from one unsaved editor snapshot."""

    data: bytes
    file_name: str
    diagnostics: Mapping[str, Any]


def build_diary_editor_export_note(
    current_form_note: Mapping[str, Any],
    settings: DiaryNoteSettings,
) -> dict[str, Any]:
    """Overlay current structured settings without mutating or saving the note."""
    note = dict(current_form_note)
    if normalized_note_format(note) != "freeform":
        raise ValueError("La exportación directa de este editor sólo admite notas Diario.")
    return note_with_settings(note, settings)


def diary_editor_export_marker(note: Mapping[str, Any]) -> str:
    """Return a session-local marker that invalidates stale prepared downloads."""
    return hashlib.sha256(repr(dict(note)).encode("utf-8", errors="replace")).hexdigest()


def prepare_diary_editor_pdf_download(
    note: Mapping[str, Any],
    *,
    db: Any | None = None,
) -> DiaryEditorPdfDownload:
    """Compile a temporary PDF and retain only its bytes and diagnostics."""
    note_data = dict(note)
    if normalized_note_format(note_data) != "freeform":
        raise ValueError("La exportación directa de este editor sólo admite notas Diario.")
    with tempfile.TemporaryDirectory(prefix="mathmongo_diary_editor_pdf_") as temp_dir:
        result = export_note_pdf(note_data, db=db, output_dir=Path(temp_dir))
        data = result.pdf_path.read_bytes()
        return DiaryEditorPdfDownload(
            data=data,
            file_name=result.file_name,
            diagnostics=dict(result.diagnostics),
        )


def prepare_diary_editor_zip_download(
    note: Mapping[str, Any],
    *,
    db: Any | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> LatexBundleResult:
    """Build the canonical portable bundle from one unsaved editor snapshot."""
    note_data = dict(note)
    if normalized_note_format(note_data) != "freeform":
        raise ValueError("La exportación directa de este editor sólo admite notas Diario.")
    return build_note_latex_bundle(
        note_data,
        db=db,
        diagnostics=diagnostics,
    )


__all__ = [
    "DiaryEditorPdfDownload",
    "build_diary_editor_export_note",
    "diary_editor_export_marker",
    "prepare_diary_editor_pdf_download",
    "prepare_diary_editor_zip_download",
]

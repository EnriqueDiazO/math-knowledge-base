"""Dispatcher for exporting legacy Diario and Cornell latex_notes."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.persistence import extract_cornell_document
from editor.cornell.renderer import CornellRenderResult
from editor.cornell.renderer import generate_cornell_document_tex
from editor.cornell.renderer import render_cornell_document
from editor.cornell.renderer import write_cornell_document_tex
from editor.pdf_export import EXPORTED_NOTES_DIR
from editor.pdf_export import generar_pdf_nota_latex_result
from editor.pdf_export import generar_tex_nota_latex

LEGACY_NOTE_FORMATS = {None, "", "freeform"}


@dataclass(frozen=True, slots=True)
class NoteTexExport:
    """Generated TEX content ready for download."""

    tex: str
    file_name: str
    note_format: str


@dataclass(frozen=True, slots=True)
class NotePdfExport:
    """Generated PDF metadata ready for download."""

    pdf_path: Path
    file_name: str
    note_format: str
    diagnostics: dict[str, Any]
    render_result: CornellRenderResult | None = None


class NoteExportError(RuntimeError):
    """Raised when a latex_note cannot be exported by the dispatcher."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        """Store a short message and optional export diagnostics."""
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _safe_export_slug(value: object, fallback: str = "latex_note") -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", ascii_text).strip("._")
    return slug or fallback


def normalized_note_format(note: dict[str, Any]) -> str:
    """Return the effective note format used by export dispatch."""
    note_format = note.get("note_format")
    if note_format in LEGACY_NOTE_FORMATS:
        return "freeform"
    if note_format == CORNELL_NOTE_FORMAT:
        return CORNELL_NOTE_FORMAT
    raise ValueError(f"Formato de nota desconocido: {note_format!r}")


def note_format_badge(note: dict[str, Any]) -> str:
    """Return a compact UI badge for a latex_note document."""
    return "[Cornell]" if normalized_note_format(note) == CORNELL_NOTE_FORMAT else "[Diario]"


def note_export_basename(note: dict[str, Any]) -> str:
    """Build a safe export basename from note date, title, and id."""
    date_prefix = _safe_export_slug(str(note.get("date") or "").replace("-", ""), "")
    title = _safe_export_slug(note.get("title"), "nota")
    note_id = _safe_export_slug(note.get("_id") or note.get("id"), "note")
    parts = [part for part in (date_prefix, title, note_id) if part]
    return "_".join(parts) or "latex_note"


def export_note_tex(
    note: dict[str, Any],
    *,
    db: Any | None = None,
    assets_by_id: dict[str, dict[str, Any]] | None = None,
    output_dir: str | Path | None = None,
    template: str = "diario",
) -> NoteTexExport:
    """Export one latex_note as TEX, dispatching Cornell separately from legacy notes."""
    note_format = normalized_note_format(note)
    base_name = note_export_basename(note)
    if note_format == CORNELL_NOTE_FORMAT:
        document = extract_cornell_document(note)
        if db is not None or assets_by_id:
            tex_dir = Path(output_dir) if output_dir is not None else EXPORTED_NOTES_DIR / "cornell" / "_tex"
            tex_path = write_cornell_document_tex(
                document,
                tex_dir,
                f"{base_name}_cornell",
                db=db,
                assets_by_id=assets_by_id,
            )
            return NoteTexExport(
                tex=tex_path.read_text(encoding="utf-8"),
                file_name=tex_path.name,
                note_format=note_format,
            )
        return NoteTexExport(
            tex=generate_cornell_document_tex(document),
            file_name=f"{base_name}_cornell.tex",
            note_format=note_format,
        )
    return NoteTexExport(
        tex=generar_tex_nota_latex(note, template=template),
        file_name=f"{base_name}_{template}.tex",
        note_format=note_format,
    )


def export_note_pdf(
    note: dict[str, Any],
    *,
    db: Any | None = None,
    assets_by_id: dict[str, dict[str, Any]] | None = None,
    output_dir: str | Path | None = None,
    template: str = "diario",
) -> NotePdfExport:
    """Export one latex_note as PDF, dispatching Cornell separately from legacy notes."""
    note_format = normalized_note_format(note)
    base_name = note_export_basename(note)
    if note_format == CORNELL_NOTE_FORMAT:
        document = extract_cornell_document(note)
        cornell_output_dir = Path(output_dir) if output_dir is not None else EXPORTED_NOTES_DIR / "cornell"
        result = render_cornell_document(
            document,
            cornell_output_dir,
            f"{base_name}_cornell",
            db=db,
            assets_by_id=assets_by_id,
        )
        if not result.success:
            raise NoteExportError(result.message, dict(result.diagnostics))
        return NotePdfExport(
            pdf_path=result.pdf_path,
            file_name=result.pdf_path.name,
            note_format=note_format,
            diagnostics=dict(result.diagnostics),
            render_result=result,
        )

    pdf_result = generar_pdf_nota_latex_result(note, template=template)
    pdf_path = Path(pdf_result["pdf_path"])
    return NotePdfExport(
        pdf_path=pdf_path,
        file_name=pdf_path.name,
        note_format=note_format,
        diagnostics=pdf_result,
    )

"""Dispatcher for exporting legacy Diario and Cornell latex_notes."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.persistence import extract_cornell_document
from editor.cornell.project_export import CornellProjectExportResult
from editor.cornell.project_export import export_cornell_project
from editor.cornell.renderer import CornellRenderResult
from editor.cornell.renderer import generate_cornell_document_tex
from editor.cornell.renderer import render_cornell_document
from editor.cornell.renderer import write_cornell_document_tex
from editor.cpi.models import CPI_NOTE_FORMAT
from editor.cpi.persistence import extract_cpi_document
from editor.cpi.project_export import CpiProjectExportResult
from editor.cpi.project_export import export_cpi_project
from editor.cpi.renderer import CpiRenderResult
from editor.cpi.renderer import generate_cpi_document_tex
from editor.cpi.renderer import render_cpi_document
from editor.cpi.renderer import write_cpi_document_tex
from editor.latex_bundle import LatexBundleAsset
from editor.latex_bundle import LatexBundleResult
from editor.latex_bundle import build_latex_project_bundle
from editor.pdf_export import EXPORTED_NOTES_DIR
from editor.pdf_export import generar_pdf_nota_latex_result
from editor.pdf_export import generar_tex_nota_latex
from editor.utils.media_assets import get_note_media_assets
from editor.utils.media_assets import resolve_media_asset_path

LEGACY_NOTE_FORMATS = {None, "", "freeform"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_LATEX_DIR = PROJECT_ROOT / "templates_latex"


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
    render_result: CornellRenderResult | CpiRenderResult | None = None


@dataclass(frozen=True, slots=True)
class NoteProjectExport:
    """Generated editable LaTeX project metadata ready for download."""

    project_dir: Path
    zip_path: Path
    file_name: str
    note_format: str
    export_result: CornellProjectExportResult | CpiProjectExportResult
    warnings: tuple[str, ...] = ()


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
    if note_format == CPI_NOTE_FORMAT:
        return CPI_NOTE_FORMAT
    raise ValueError(f"Formato de nota desconocido: {note_format!r}")


def note_format_badge(note: dict[str, Any]) -> str:
    """Return a compact UI badge for a latex_note document."""
    note_format = normalized_note_format(note)
    if note_format == CORNELL_NOTE_FORMAT:
        return "[Cornell]"
    if note_format == CPI_NOTE_FORMAT:
        return "[CPI]"
    return "[Diario]"


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
    if note_format == CPI_NOTE_FORMAT:
        document = extract_cpi_document(note)
        if output_dir is not None or db is not None or assets_by_id:
            tex_dir = Path(output_dir) if output_dir is not None else EXPORTED_NOTES_DIR / "cpi" / "_tex"
            tex_path = write_cpi_document_tex(
                document,
                tex_dir,
                f"{base_name}_cpi",
                db=db,
                assets_by_id=assets_by_id,
            )
            return NoteTexExport(
                tex=tex_path.read_text(encoding="utf-8"),
                file_name=tex_path.name,
                note_format=note_format,
            )
        return NoteTexExport(
            tex=generate_cpi_document_tex(document),
            file_name=f"{base_name}_cpi.tex",
            note_format=note_format,
        )
    return NoteTexExport(
        tex=generar_tex_nota_latex(note, template=template),
        file_name=f"{base_name}_{template}.tex",
        note_format=note_format,
    )


def _note_bundle_styles(tex: str) -> dict[str, bytes]:
    """Load only project-owned styles referenced by a generated note TEX."""
    names = {"mathmongo-macros.sty"}
    if re.search(r"\\documentclass(?:\[[^\]]*\])?\{notes\}", tex):
        names.update({"notes.cls", "notes.sty", "miestilo.sty", "coloredtheorem.sty"})
    if re.search(r"\\usepackage(?:\[[^\]]*\])?\{miestilo\}", tex):
        names.update({"miestilo.sty", "coloredtheorem.sty"})
    if re.search(r"\\usepackage(?:\[[^\]]*\])?\{coloredtheorem\}", tex):
        names.add("coloredtheorem.sty")
    return {
        name: (TEMPLATES_LATEX_DIR / name).read_bytes()
        for name in sorted(names)
        if (TEMPLATES_LATEX_DIR / name).is_file()
    }


def _note_bundle_assets(
    note: Mapping[str, Any],
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[LatexBundleAsset]:
    """Materialize note-specific image bytes without coupling the ZIP builder to Mongo."""
    resolved_assets: dict[str, Mapping[str, Any]] = {}
    if assets_by_id:
        resolved_assets.update({str(key): value for key, value in assets_by_id.items()})
    note_id = str(note.get("_id") or note.get("id") or "")
    if db is not None and note_id:
        for asset in get_note_media_assets(db, note_id):
            asset_id = str(asset.get("asset_id") or asset.get("_id") or "")
            if asset_id:
                resolved_assets[asset_id] = asset
    ordered_ids = [str(asset_id) for asset_id in note.get("image_ids") or []]
    ordered_assets: list[Mapping[str, Any]] = [
        resolved_assets[asset_id] for asset_id in ordered_ids if asset_id in resolved_assets
    ]
    known_ids = {str(asset.get("asset_id") or asset.get("_id") or "") for asset in ordered_assets}
    ordered_assets.extend(
        asset for asset_id, asset in sorted(resolved_assets.items()) if asset_id not in known_ids
    )
    bundle_assets: list[LatexBundleAsset] = []
    for asset in ordered_assets:
        data = asset.get("data")
        if isinstance(data, bytearray):
            data = bytes(data)
        if not isinstance(data, bytes):
            try:
                path = resolve_media_asset_path(dict(asset))
                data = path.read_bytes() if path.is_file() and not path.is_symlink() else None
            except OSError:
                data = None
        bundle_assets.append(
            LatexBundleAsset(
                data=data,
                source_path=str(asset.get("path") or ""),
                filename=str(asset.get("filename") or asset.get("original_filename") or ""),
                mime_type=str(asset.get("mime_type") or "") or None,
                asset_id=str(asset.get("asset_id") or asset.get("_id") or "") or None,
                metadata={
                    key: value
                    for key, value in asset.items()
                    if key not in {"data", "path", "filename", "original_filename"}
                },
            )
        )
    for asset_id in ordered_ids:
        if asset_id not in resolved_assets:
            bundle_assets.append(
                LatexBundleAsset(data=None, asset_id=asset_id, filename=f"asset_{asset_id}")
            )
    return bundle_assets


def build_note_latex_bundle(
    note: Mapping[str, Any],
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    chktex_report: object | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    template: str = "diario",
) -> LatexBundleResult:
    """Return a portable note project independently from PDF compilation status."""
    note_data = dict(note)
    tex_export = export_note_tex(
        note_data,
        db=None,
        assets_by_id=None,
        template=template,
    )
    diagnostics_data = dict(diagnostics or {})
    latex_log = diagnostics_data.get("log_text") or diagnostics_data.get("log_excerpt")
    portable_metadata = {
        key: value
        for key, value in note_data.items()
        if key not in {"latex_body", "cornell_document", "cpi_document"}
    }
    return build_latex_project_bundle(
        main_tex=tex_export.tex,
        raw_body=str(note_data.get("latex_body") or ""),
        metadata=portable_metadata,
        project_styles=_note_bundle_styles(tex_export.tex),
        images=_note_bundle_assets(note_data, db=db, assets_by_id=assets_by_id),
        chktex_report=chktex_report or diagnostics_data.get("chktex"),
        latex_log=latex_log,
        compilation_summary=diagnostics_data or None,
        source_type=tex_export.note_format,
        source_id=str(note_data.get("_id") or note_data.get("id") or ""),
        title=str(note_data.get("title") or note_export_basename(note_data)),
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
    if note_format == CPI_NOTE_FORMAT:
        document = extract_cpi_document(note)
        cpi_output_dir = Path(output_dir) if output_dir is not None else EXPORTED_NOTES_DIR / "cpi"
        result = render_cpi_document(
            document,
            cpi_output_dir,
            f"{base_name}_cpi",
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

    output_path = None
    if output_dir is not None:
        output_path = str(Path(output_dir) / f"{base_name}_{template}.pdf")
    pdf_result = generar_pdf_nota_latex_result(
        note,
        output_path=output_path,
        template=template,
    )
    pdf_path = Path(pdf_result["pdf_path"])
    return NotePdfExport(
        pdf_path=pdf_path,
        file_name=pdf_path.name,
        note_format=note_format,
        diagnostics=pdf_result,
    )


def export_note_project(
    note: dict[str, Any],
    output_root: str | Path,
    *,
    allowed_root: str | Path | None = None,
    db: Any | None = None,
    assets_by_id: dict[str, dict[str, Any]] | None = None,
) -> NoteProjectExport:
    """Export one structured latex_note as an editable LaTeX project by note_format."""
    note_format = normalized_note_format(note)
    if note_format == CORNELL_NOTE_FORMAT:
        result = export_cornell_project(
            extract_cornell_document(note),
            note,
            output_root,
            allowed_root=allowed_root,
            db=db,
            assets_by_id=assets_by_id,
        )
    elif note_format == CPI_NOTE_FORMAT:
        result = export_cpi_project(
            extract_cpi_document(note),
            note,
            output_root,
            allowed_root=allowed_root,
            db=db,
            assets_by_id=assets_by_id,
        )
    else:
        raise ValueError("Solo Cornell y CPI tienen proyecto LaTeX editable.")
    return NoteProjectExport(
        project_dir=result.project_dir,
        zip_path=result.zip_path,
        file_name=result.zip_path.name,
        note_format=note_format,
        export_result=result,
        warnings=tuple(getattr(result, "warnings", ())),
    )

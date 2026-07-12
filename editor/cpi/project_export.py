"""Editable LaTeX project exporter for CPI notes."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

from editor.cornell.project_export import _prepare_owned_project_directory
from editor.cornell.project_export import _zip_project
from editor.cpi.layout import CpiFitReport
from editor.cpi.layout import measure_cpi_document_fit
from editor.cpi.media import _assets_by_id_from_db
from editor.cpi.media import _normalize_assets_by_id
from editor.cpi.media import _safe_asset_source_path
from editor.cpi.media import cpi_document_image_ids
from editor.cpi.media import latex_uses_svg_paths
from editor.cpi.media import render_cpi_region_latex
from editor.cpi.media import safe_cornell_asset_filename
from editor.cpi.models import CPI_NOTE_FORMAT
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.renderer import TEMPLATE_PATH
from editor.cpi.renderer import cpi_latex_preamble
from editor.cpi.renderer import generate_cpi_document_tex

CONTENT_FILENAMES = {
    "comprehension": "comprension.tex",
    "production": "produccion.tex",
    "integration": "integracion.tex",
}


@dataclass(frozen=True, slots=True)
class CpiProjectExportResult:
    """Filesystem paths for an exported editable CPI LaTeX project."""

    project_dir: Path
    zip_path: Path
    metadata_path: Path


def _resolve_project_images(
    document: CpiDocument,
    project_dir: Path,
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    images_dir = project_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    image_ids = cpi_document_image_ids(document)
    if not image_ids:
        return {}

    resolved_assets = _normalize_assets_by_id(assets_by_id)
    if db is not None:
        resolved_assets.update(_assets_by_id_from_db(db, image_ids))
    missing = [asset_id for asset_id in image_ids if asset_id not in resolved_assets]
    if missing:
        raise ValueError(f"CPI image asset not found: {', '.join(missing)}")

    latex_paths: dict[str, str] = {}
    used_names: set[str] = set()
    for asset_id in image_ids:
        asset = resolved_assets[asset_id]
        source = _safe_asset_source_path(asset)
        safe_name = safe_cornell_asset_filename(asset)
        if safe_name in used_names:
            stem = Path(safe_name).stem
            suffix = Path(safe_name).suffix
            safe_name = f"{stem}_{asset_id[:8]}{suffix}"
        used_names.add(safe_name)
        destination = images_dir / safe_name
        shutil.copyfile(source, destination)
        latex_paths[asset_id] = destination.relative_to(project_dir).as_posix()
    return latex_paths


def _write_template_reference(project_dir: Path) -> None:
    templates_dir = project_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE_PATH, templates_dir / TEMPLATE_PATH.name)


def _write_page_content(
    project_dir: Path,
    pages: tuple[CpiPage, ...],
    *,
    asset_paths_by_id: Mapping[str, str],
) -> None:
    content_dir = project_dir / "contenido"
    for index, page in enumerate(pages, start=1):
        page_dir = content_dir / f"pagina_{index:03d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        for region_name, filename in CONTENT_FILENAMES.items():
            region = getattr(page, region_name)
            body = render_cpi_region_latex(
                region,
                region_name=region_name,
                asset_paths_by_id=asset_paths_by_id,
            )
            (page_dir / filename).write_text(body.rstrip() + "\n", encoding="utf-8")


def _input_region(page_number: int, region_name: str) -> CpiRegion:
    return CpiRegion(
        heading={
            "comprehension": "Comprensión",
            "production": "Producción",
            "integration": "Integración",
        }[region_name],
        latex=rf"\input{{contenido/pagina_{page_number:03d}/{CONTENT_FILENAMES[region_name]}}}",
    )


def _project_input_document(document: CpiDocument) -> CpiDocument:
    pages = []
    for page_number, _page in enumerate(document.ordered_pages(), start=1):
        pages.append(
            CpiPage(
                page_number=page_number,
                comprehension=_input_region(page_number, "comprehension"),
                production=_input_region(page_number, "production"),
                integration=_input_region(page_number, "integration"),
            )
        )
    return CpiDocument(
        schema_version=document.schema_version,
        template_id=document.template_id,
        pages=tuple(pages),
        attribution=document.attribution,
        watermark=document.watermark,
    )


def _write_notas(
    project_dir: Path,
    document: CpiDocument,
    *,
    asset_paths_by_id: Mapping[str, str],
    fit_report: CpiFitReport | None = None,
) -> None:
    source = generate_cpi_document_tex(
        _project_input_document(document),
        fit_report=fit_report,
        asset_paths_by_id=asset_paths_by_id,
    )
    (project_dir / "Notas.tex").write_text(source, encoding="utf-8")


def _cleanup_fit_artifacts(project_dir: Path, output_name: str) -> None:
    safe_name = Path(output_name).stem or output_name
    safe_name = "".join(character if character.isalnum() or character in "_.-" else "_" for character in safe_name)
    safe_name = safe_name.strip("._") or "cpi"
    for suffix in (".tex", ".log", ".aux", ".pdf"):
        path = project_dir / f"{safe_name}_fit{suffix}"
        if path.exists():
            path.unlink()


def _measure_project_fit(
    project_dir: Path,
    document: CpiDocument,
    *,
    asset_paths_by_id: Mapping[str, str],
) -> CpiFitReport:
    output_name = "Notas"
    try:
        return measure_cpi_document_fit(
            _project_input_document(document),
            project_dir,
            output_name,
            latex_preamble=cpi_latex_preamble(
                include_svg=latex_uses_svg_paths(dict(asset_paths_by_id))
            ),
            asset_paths_by_id=asset_paths_by_id,
        )
    finally:
        _cleanup_fit_artifacts(project_dir, output_name)


def _metadata_payload(metadata: Mapping[str, Any], document: CpiDocument) -> dict[str, Any]:
    pages = document.ordered_pages()
    return {
        "title": str(metadata.get("title") or "Nueva nota CPI"),
        "date": str(metadata.get("date") or ""),
        "project": str(metadata.get("project") or ""),
        "context": str(metadata.get("context") or ""),
        "tags": list(metadata.get("tags") or []),
        "note_format": CPI_NOTE_FORMAT,
        "schema_version": document.schema_version,
        "template_id": document.template_id,
        "page_numbers": [page.page_number for page in pages],
        "regions": list(CONTENT_FILENAMES),
        "attribution": document.attribution.to_dict(),
        "watermark": document.watermark.to_dict(),
    }


def _write_metadata(project_dir: Path, metadata: Mapping[str, Any], document: CpiDocument) -> Path:
    metadata_path = project_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(_metadata_payload(metadata, document), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def _write_readme(project_dir: Path) -> None:
    (project_dir / "README.md").write_text(
        dedent(
            """
            # Proyecto CPI LaTeX editable

            Compila el documento final:

            ```bash
            pdflatex Notas.tex
            ```

            Edita los archivos en `contenido/pagina_NNN/` para modificar cada zona.
            El documento conserva la geometría CPI carta horizontal.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def export_cpi_project(
    document: CpiDocument,
    metadata: Mapping[str, Any],
    output_root: str | Path,
    *,
    allowed_root: str | Path | None = None,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> CpiProjectExportResult:
    """Export a CPI document as a standalone editable LaTeX project."""
    pages = document.ordered_pages()
    if not pages:
        raise ValueError("CpiDocument must contain at least one page")

    project_dir = _prepare_owned_project_directory(
        output_root,
        metadata.get("title") or "cpi_project",
        allowed_root=output_root if allowed_root is None else allowed_root,
        expected_note_format=CPI_NOTE_FORMAT,
    )
    metadata_path = _write_metadata(project_dir, metadata, document)

    asset_paths = _resolve_project_images(
        document,
        project_dir,
        db=db,
        assets_by_id=assets_by_id,
    )
    _write_template_reference(project_dir)
    _write_page_content(project_dir, pages, asset_paths_by_id=asset_paths)
    fit_report = _measure_project_fit(project_dir, document, asset_paths_by_id=asset_paths)
    if fit_report.has_overflow:
        overflow = fit_report.overflow_regions()[0]
        page, region = overflow
        raise ValueError(
            "El contenido CPI no cabe en el proyecto exportable: "
            f"pagina {page.page_number}, {region.label}, "
            f"escala necesaria {region.required_scale:.2f}, "
            f"escala minima {fit_report.min_region_scale:.2f}."
        )
    _write_notas(project_dir, document, asset_paths_by_id=asset_paths, fit_report=fit_report)
    _write_readme(project_dir)
    zip_path = _zip_project(project_dir)
    return CpiProjectExportResult(
        project_dir=project_dir,
        zip_path=zip_path,
        metadata_path=metadata_path,
    )


__all__ = [
    "CpiProjectExportResult",
    "export_cpi_project",
    "latex_uses_svg_paths",
]

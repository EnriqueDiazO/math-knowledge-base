"""Media asset helpers for CPI region images."""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from editor.cornell.media import _assets_by_id_from_db
from editor.cornell.media import _normalize_assets_by_id
from editor.cornell.media import _safe_asset_source_path
from editor.cornell.media import latex_image_include
from editor.cornell.media import latex_uses_svg_paths
from editor.cornell.media import safe_cornell_asset_filename
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiRegion

CPI_IMAGE_COMMAND = "cpiimage"
CPI_IMAGE_REF_PATTERN = re.compile(r"\\cpiimage\{(?P<asset_id>[^{}]+)\}")
CPI_LATEX_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".svg"}
REGION_IMAGE_WIDTHS = {
    "comprehension": "4.7in",
    "production": "4.7in",
    "integration": "9.8in",
}


def cpi_image_reference(asset_id: str) -> str:
    """Return the stable LaTeX reference stored in CPI region text."""
    clean = str(asset_id or "").strip()
    if not clean or any(character in clean for character in "{}\\"):
        raise ValueError("asset_id must be non-empty and must not contain braces or backslashes")
    return rf"\{CPI_IMAGE_COMMAND}{{{clean}}}"


def cpi_region_image_ids(document: CpiDocument) -> tuple[str, ...]:
    """Return unique associated image IDs from all CPI regions in page order."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for page in document.ordered_pages():
        for region in (page.comprehension, page.production, page.integration):
            for asset_id in region.image_ids:
                if asset_id not in seen:
                    image_ids.append(asset_id)
                    seen.add(asset_id)
    return tuple(image_ids)


def cpi_latex_image_refs(document: CpiDocument) -> tuple[str, ...]:
    """Return unique asset IDs referenced by stable CPI LaTeX image commands."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for page in document.ordered_pages():
        for latex in (page.comprehension.latex, page.production.latex, page.integration.latex):
            for match in CPI_IMAGE_REF_PATTERN.finditer(latex or ""):
                asset_id = match.group("asset_id").strip()
                if asset_id and asset_id not in seen:
                    image_ids.append(asset_id)
                    seen.add(asset_id)
    return tuple(image_ids)


def cpi_document_image_ids(document: CpiDocument) -> tuple[str, ...]:
    """Return all image asset IDs needed to render a CPI document."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for asset_id in (*cpi_region_image_ids(document), *cpi_latex_image_refs(document)):
        if asset_id not in seen:
            image_ids.append(asset_id)
            seen.add(asset_id)
    watermark = document.watermark
    if watermark.enabled and watermark.type == "image" and watermark.image_id:
        asset_id = watermark.image_id
        if asset_id not in seen:
            image_ids.append(asset_id)
            seen.add(asset_id)
    return tuple(image_ids)


def prepare_cpi_image_assets(
    document: CpiDocument,
    output_dir: str | Path,
    *,
    assets_dirname: str = "cpi_assets",
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Resolve and copy all CPI images, returning asset_id -> LaTeX path."""
    image_ids = cpi_document_image_ids(document)
    if not image_ids:
        return {}

    resolved_assets = _normalize_assets_by_id(assets_by_id)
    if db is not None:
        resolved_assets.update(_assets_by_id_from_db(db, image_ids))
    missing = [asset_id for asset_id in image_ids if asset_id not in resolved_assets]
    if missing:
        raise ValueError(f"CPI image asset not found: {', '.join(missing)}")

    output_path = Path(output_dir)
    media_dir = output_path / assets_dirname / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    latex_paths: dict[str, str] = {}
    used_names: set[str] = set()
    for asset_id in image_ids:
        asset = resolved_assets[asset_id]
        source_path = _safe_asset_source_path(asset, allowed_extensions=CPI_LATEX_IMAGE_EXTENSIONS)
        safe_name = safe_cornell_asset_filename(asset)
        if safe_name in used_names:
            stem = Path(safe_name).stem
            suffix = Path(safe_name).suffix
            safe_name = f"{stem}_{asset_id[:8]}{suffix}"
        used_names.add(safe_name)
        destination = media_dir / safe_name
        shutil.copyfile(source_path, destination)
        latex_paths[asset_id] = destination.relative_to(output_path).as_posix()
    return latex_paths


def cpi_image_box_latex(asset_path: str, *, region_name: str) -> str:
    """Return a bounded LaTeX image block for one CPI region."""
    max_width = REGION_IMAGE_WIDTHS.get(region_name, r"\linewidth")
    if str(asset_path).lower().endswith(".svg"):
        image = latex_image_include(asset_path, options=f"width={max_width}")
    else:
        image = rf"\resizebox{{{max_width}}}{{!}}{{\includegraphics{{{asset_path}}}}}"
    return "\n" + r"\begin{center}" "\n" + image + "\n" + r"\end{center}" "\n"


def render_cpi_region_latex(
    region: CpiRegion,
    *,
    region_name: str,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    """Resolve stable CPI image refs and append associated region images."""
    asset_paths = dict(asset_paths_by_id or {})
    referenced_ids: set[str] = set()

    def replace_reference(match: re.Match[str]) -> str:
        asset_id = match.group("asset_id").strip()
        referenced_ids.add(asset_id)
        if asset_id not in asset_paths:
            return cpi_image_reference(asset_id)
        return cpi_image_box_latex(asset_paths[asset_id], region_name=region_name)

    rendered = CPI_IMAGE_REF_PATTERN.sub(replace_reference, region.latex or "")
    for asset_id in region.image_ids:
        if asset_id in referenced_ids:
            continue
        if asset_id in asset_paths:
            rendered += cpi_image_box_latex(asset_paths[asset_id], region_name=region_name)
        else:
            rendered += "\n" + cpi_image_reference(asset_id) + "\n"
    return rendered


__all__ = [
    "CPI_IMAGE_COMMAND",
    "cpi_document_image_ids",
    "cpi_image_reference",
    "cpi_latex_image_refs",
    "cpi_region_image_ids",
    "latex_uses_svg_paths",
    "prepare_cpi_image_assets",
    "render_cpi_region_latex",
]

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
CPI_IMAGE_REF_PATTERN = re.compile(
    r"\\cpiimage(?:\[(?P<width_ratio>(?:0(?:\.\d+)?|1(?:\.0+)?))\])?"
    r"\{(?P<asset_id>[^{}]+)\}"
)
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


def cpi_content_image_ids(document: CpiDocument) -> tuple[str, ...]:
    """Return required region and inline image IDs, excluding optional branding."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for asset_id in (*cpi_region_image_ids(document), *cpi_latex_image_refs(document)):
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
    warnings: list[str] | None = None,
) -> dict[str, str]:
    """Resolve and copy all CPI images, returning asset_id -> LaTeX path."""
    content_ids = cpi_content_image_ids(document)
    watermark = document.watermark
    watermark_id = (
        watermark.image_id
        if watermark.enabled and watermark.type == "image" and watermark.image_id
        else ""
    )
    image_ids = tuple(dict.fromkeys((*content_ids, watermark_id))) if watermark_id else content_ids
    if not image_ids:
        if watermark.enabled and watermark.type == "image" and warnings is not None:
            warnings.append("La marca de agua está activa, pero no tiene un asset_id.")
        return {}

    resolved_assets = _normalize_assets_by_id(assets_by_id)
    if db is not None:
        resolved_assets.update(_assets_by_id_from_db(db, image_ids))
    missing_content = [asset_id for asset_id in content_ids if asset_id not in resolved_assets]
    if missing_content:
        raise ValueError(f"CPI image asset not found: {', '.join(missing_content)}")
    if watermark_id and watermark_id not in resolved_assets:
        if warnings is not None:
            warnings.append(f"Asset de marca de agua no encontrado: {watermark_id}")
        image_ids = tuple(asset_id for asset_id in image_ids if asset_id != watermark_id)

    output_path = Path(output_dir)
    media_dir = output_path / assets_dirname / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    latex_paths: dict[str, str] = {}
    used_names: set[str] = set()
    for asset_id in image_ids:
        asset = resolved_assets[asset_id]
        try:
            source_path = _safe_asset_source_path(
                asset,
                allowed_extensions=CPI_LATEX_IMAGE_EXTENSIONS,
            )
        except FileNotFoundError as exc:
            if asset_id != watermark_id:
                raise
            if warnings is not None:
                warnings.append(f"Marca de agua omitida: {exc}")
            continue
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


def cpi_image_box_latex(
    asset_path: str,
    *,
    region_name: str,
    width_ratio: float | None = None,
) -> str:
    """Return a bounded LaTeX image block for one CPI region."""
    if width_ratio is None:
        max_width = REGION_IMAGE_WIDTHS.get(region_name, r"\linewidth")
    else:
        if width_ratio <= 0.0 or width_ratio > 1.0:
            raise ValueError("CPI image width ratio must be greater than 0 and at most 1")
        max_width = f"{width_ratio:g}\\linewidth"
    if str(asset_path).lower().endswith(".svg"):
        image = latex_image_include(asset_path, options=f"width={max_width}")
    else:
        image = rf"\resizebox{{{max_width}}}{{!}}{{\includegraphics{{{asset_path}}}}}"
    if width_ratio is not None:
        return image
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
            return match.group(0)
        raw_width = match.group("width_ratio")
        return cpi_image_box_latex(
            asset_paths[asset_id],
            region_name=region_name,
            width_ratio=float(raw_width) if raw_width is not None else None,
        )

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
    "cpi_content_image_ids",
    "cpi_document_image_ids",
    "cpi_image_reference",
    "cpi_latex_image_refs",
    "cpi_region_image_ids",
    "latex_uses_svg_paths",
    "prepare_cpi_image_assets",
    "render_cpi_region_latex",
]

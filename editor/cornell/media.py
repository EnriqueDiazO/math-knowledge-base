"""Media asset helpers for Cornell region images."""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellRegion
from editor.utils.media_assets import LATEX_IMAGE_EXTENSIONS
from editor.utils.media_assets import media_collection
from editor.utils.media_assets import resolve_media_asset_path
from editor.utils.media_assets import safe_media_filename
from mathkb_config import PROJECT_ROOT
from mathmongo.paths import find_symlink_component

CORNELL_IMAGE_COMMAND = "cornellimage"
CORNELL_IMAGE_REF_PATTERN = re.compile(
    r"\\cornellimage(?:\[(?P<width_ratio>(?:0(?:\.\d+)?|1(?:\.0+)?))\])?"
    r"\{(?P<asset_id>[^{}]+)\}"
)
REGION_IMAGE_WIDTHS = {
    "cue": "1.9in",
    "main": "5.35in",
    "summary": "5.7in",
}
CORNELL_LATEX_IMAGE_EXTENSIONS = LATEX_IMAGE_EXTENSIONS | {".svg"}


def cornell_image_reference(asset_id: str) -> str:
    """Return the stable LaTeX reference stored in Cornell region text."""
    clean = str(asset_id or "").strip()
    if not clean or any(character in clean for character in "{}\\"):
        raise ValueError("asset_id must be non-empty and must not contain braces or backslashes")
    return rf"\{CORNELL_IMAGE_COMMAND}{{{clean}}}"


def cornell_region_image_ids(document: CornellDocument) -> tuple[str, ...]:
    """Return unique image_ids from all Cornell regions in page order."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for page in document.ordered_pages():
        for region in (page.cue, page.main, page.summary):
            for asset_id in region.image_ids:
                if asset_id not in seen:
                    image_ids.append(asset_id)
                    seen.add(asset_id)
    return tuple(image_ids)


def cornell_latex_image_refs(document: CornellDocument) -> tuple[str, ...]:
    """Return unique asset IDs referenced by stable Cornell LaTeX image commands."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for page in document.ordered_pages():
        for latex in (page.cue.latex, page.main.latex, page.summary.latex):
            for match in CORNELL_IMAGE_REF_PATTERN.finditer(latex or ""):
                asset_id = match.group("asset_id").strip()
                if asset_id and asset_id not in seen:
                    image_ids.append(asset_id)
                    seen.add(asset_id)
    return tuple(image_ids)


def cornell_document_image_ids(document: CornellDocument) -> tuple[str, ...]:
    """Return all image asset IDs needed to render a Cornell document."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for asset_id in (*cornell_region_image_ids(document), *cornell_latex_image_refs(document)):
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


def cornell_content_image_ids(document: CornellDocument) -> tuple[str, ...]:
    """Return required region and inline image IDs, excluding optional branding."""
    image_ids: list[str] = []
    seen: set[str] = set()
    for asset_id in (*cornell_region_image_ids(document), *cornell_latex_image_refs(document)):
        if asset_id not in seen:
            image_ids.append(asset_id)
            seen.add(asset_id)
    return tuple(image_ids)


def _assets_by_id_from_db(db: Any, image_ids: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    if not image_ids:
        return {}
    assets = media_collection(db).find({"asset_id": {"$in": list(image_ids)}})
    return {
        str(asset.get("asset_id")): dict(asset)
        for asset in assets
        if isinstance(asset, Mapping) and asset.get("asset_id")
    }


def _normalize_assets_by_id(assets_by_id: Mapping[str, Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if not assets_by_id:
        return {}
    return {str(asset_id): dict(asset) for asset_id, asset in assets_by_id.items()}


def _safe_asset_source_path(
    asset: Mapping[str, Any],
    *,
    allowed_extensions: set[str] | frozenset[str] | None = None,
) -> Path:
    raw_path = str(asset.get("path") or "")
    source_path = Path(raw_path)
    if not raw_path or (not source_path.is_absolute() and ".." in source_path.parts):
        raise ValueError(f"Cornell image asset has an unsafe path: {raw_path!r}")
    suffix = source_path.suffix.lower()
    safe_extensions = allowed_extensions or CORNELL_LATEX_IMAGE_EXTENSIONS
    if suffix not in safe_extensions:
        allowed = ", ".join(sorted(safe_extensions))
        raise ValueError(f"Cornell image asset extension {suffix!r} is not supported by LaTeX. Allowed: {allowed}.")
    absolute_path = resolve_media_asset_path({"path": raw_path})
    # Compatibility for callers/tests that explicitly provide a historical root.
    if not absolute_path.is_file():
        fallback = source_path if source_path.is_absolute() else PROJECT_ROOT / source_path
        if fallback.is_file():
            absolute_path = fallback
    if not absolute_path.is_file():
        raise FileNotFoundError(f"Cornell image asset file does not exist: {raw_path}")
    if find_symlink_component(absolute_path) is not None:
        raise ValueError(f"Cornell image asset cannot use a symbolic link: {raw_path!r}")
    return absolute_path


def safe_cornell_asset_filename(asset: Mapping[str, Any]) -> str:
    """Return a collision-resistant LaTeX-safe filename for a copied Cornell image."""
    asset_id = str(asset.get("asset_id") or "").strip()
    if not asset_id:
        raise ValueError("Cornell image asset is missing asset_id")
    filename = str(asset.get("filename") or asset.get("original_filename") or asset_id)
    return safe_media_filename(filename, asset_id)


def prepare_cornell_image_assets(
    document: CornellDocument,
    output_dir: str | Path,
    *,
    db: Any | None = None,
    assets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, str]:
    """Resolve and copy all Cornell images, returning asset_id -> LaTeX path."""
    content_ids = cornell_content_image_ids(document)
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
        raise ValueError(f"Cornell image asset not found: {', '.join(missing_content)}")
    if watermark_id and watermark_id not in resolved_assets:
        if warnings is not None:
            warnings.append(f"Asset de marca de agua no encontrado: {watermark_id}")
        image_ids = tuple(asset_id for asset_id in image_ids if asset_id != watermark_id)

    output_path = Path(output_dir)
    media_dir = output_path / "cornell_assets" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    latex_paths: dict[str, str] = {}
    used_names: set[str] = set()
    for asset_id in image_ids:
        asset = resolved_assets[asset_id]
        try:
            source_path = _safe_asset_source_path(asset)
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


def cornell_image_box_latex(
    asset_path: str,
    *,
    region_name: str,
    width_ratio: float | None = None,
) -> str:
    """Return a bounded LaTeX image block for one region."""
    if width_ratio is None:
        max_width = REGION_IMAGE_WIDTHS.get(region_name, r"\linewidth")
    else:
        if width_ratio <= 0.0 or width_ratio > 1.0:
            raise ValueError("Cornell image width ratio must be greater than 0 and at most 1")
        max_width = f"{width_ratio:g}\\linewidth"
    if str(asset_path).lower().endswith(".svg"):
        image = latex_image_include(asset_path, options=f"width={max_width}")
    else:
        image = rf"\resizebox{{{max_width}}}{{!}}{{\includegraphics{{{asset_path}}}}}"
    if width_ratio is not None:
        return image
    return "\n" + r"\begin{center}" "\n" + image + "\n" + r"\end{center}" "\n"


def latex_image_include(asset_path: str, *, options: str = "") -> str:
    """Return a LaTeX image command for PNG/JPG/PDF/SVG Cornell assets."""
    option_block = f"[{options}]" if options else ""
    if str(asset_path).lower().endswith(".svg"):
        svg_path = str(Path(asset_path).with_suffix(""))
        return rf"\includesvg{option_block}{{{svg_path}}}"
    return rf"\includegraphics{option_block}{{{asset_path}}}"


def latex_uses_svg_paths(paths: Mapping[str, str] | list[str] | tuple[str, ...]) -> bool:
    """Return True when any LaTeX image path needs the svg package."""
    values = paths.values() if isinstance(paths, Mapping) else paths
    return any(str(path).lower().endswith(".svg") for path in values)


def render_cornell_region_latex(
    region: CornellRegion,
    *,
    region_name: str,
    asset_paths_by_id: Mapping[str, str] | None = None,
) -> str:
    """Resolve stable Cornell image refs and append associated region images."""
    asset_paths = dict(asset_paths_by_id or {})
    referenced_ids: set[str] = set()

    def replace_reference(match: re.Match[str]) -> str:
        asset_id = match.group("asset_id").strip()
        referenced_ids.add(asset_id)
        if asset_id not in asset_paths:
            return match.group(0)
        raw_width = match.group("width_ratio")
        return cornell_image_box_latex(
            asset_paths[asset_id],
            region_name=region_name,
            width_ratio=float(raw_width) if raw_width is not None else None,
        )

    rendered = CORNELL_IMAGE_REF_PATTERN.sub(replace_reference, region.latex or "")
    for asset_id in region.image_ids:
        if asset_id in referenced_ids:
            continue
        if asset_id in asset_paths:
            rendered += cornell_image_box_latex(asset_paths[asset_id], region_name=region_name)
        else:
            rendered += "\n" + cornell_image_reference(asset_id) + "\n"
    return rendered

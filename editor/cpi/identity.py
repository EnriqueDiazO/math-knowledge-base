"""LaTeX helpers for optional CPI material identity."""

from __future__ import annotations

from collections.abc import Mapping
from textwrap import dedent

from editor.cornell.identity import escape_latex_text
from editor.cornell.media import latex_image_include
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_footer_text
from editor.cpi.models import CpiDocument

POSITION_ANCHORS = {
    "center": ("center", "($(SW)+(5.50in,4.25in)$)"),
    "bottom_right": ("south east", "($(SE)+(-.35in,.35in)$)"),
    "top_right": ("north east", "($(NE)+(-.35in,-.35in)$)"),
}
FOOTER_ANCHORS = {
    "center": ("south", "($(SW)+(5.50in,.16in)$)"),
    "bottom_right": ("south east", "($(SE)+(-.35in,.16in)$)"),
    "top_right": ("north east", "($(NE)+(-.35in,-.35in)$)"),
}


def _opacity(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _scale(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _watermark_text_latex(watermark: CornellWatermark, *, anchor: str, coordinate: str) -> str:
    text = escape_latex_text(watermark.text.strip())
    if not text:
        return ""
    return dedent(
        rf"""
        \node[
          anchor={anchor},
          inner sep=0pt,
          opacity={_opacity(watermark.opacity)},
          text=gray,
          scale={_scale(watermark.scale)}
        ] at {coordinate} {{\bfseries\fontsize{{42}}{{50}}\selectfont {text}}};
        """
    ).strip()


def _watermark_image_latex(
    watermark: CornellWatermark,
    *,
    anchor: str,
    coordinate: str,
    asset_paths_by_id: Mapping[str, str],
) -> str:
    asset_path = asset_paths_by_id.get(watermark.image_id)
    if not asset_path:
        return ""
    image = latex_image_include(asset_path, options=rf"width={_scale(watermark.scale)}\paperwidth")
    return dedent(
        rf"""
        \node[
          anchor={anchor},
          inner sep=0pt,
          opacity={_opacity(watermark.opacity)}
        ] at {coordinate} {{{image}}};
        """
    ).strip()


def cpi_watermark_latex(
    document: CpiDocument,
    *,
    asset_paths_by_id: Mapping[str, str] | None = None,
    page_number: int = 1,
) -> str:
    """Return a TikZ watermark node for a full CPI page."""
    watermark = document.watermark
    if not watermark.enabled or (not watermark.all_pages and page_number != 1):
        return ""
    anchor, coordinate = POSITION_ANCHORS[watermark.position]
    if watermark.type == "image":
        return _watermark_image_latex(
            watermark,
            anchor=anchor,
            coordinate=coordinate,
            asset_paths_by_id=dict(asset_paths_by_id or {}),
        )
    return _watermark_text_latex(watermark, anchor=anchor, coordinate=coordinate)


def cpi_attribution_latex(document: CpiDocument) -> str:
    """Return a TikZ footer attribution node for a full CPI page."""
    attribution = document.attribution
    if not attribution.enabled:
        return ""
    text = escape_latex_text(build_footer_text(attribution))
    if not text:
        return ""
    anchor, coordinate = FOOTER_ANCHORS[attribution.position]
    return dedent(
        rf"""
        \node[
          anchor={anchor},
          inner sep=0pt,
          opacity=.78,
          text=gray
        ] at {coordinate} {{\scriptsize {text}}};
        """
    ).strip()

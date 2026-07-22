"""Tests for compact CPI image references."""

from editor.cpi.media import render_cpi_region_latex
from editor.cpi.models import CpiRegion


def test_compact_cpi_reference_uses_relative_width() -> None:
    """An explicit ratio supports tutorial galleries without changing legacy images."""
    region = CpiRegion(
        heading="Producción",
        latex=r"\cpiimage[0.48]{asset-1}",
        image_ids=("asset-1",),
    )

    rendered = render_cpi_region_latex(
        region,
        region_name="production",
        asset_paths_by_id={"asset-1": "cpi_assets/media/asset.png"},
    )

    assert rendered == r"\resizebox{0.48\linewidth}{!}{\includegraphics{cpi_assets/media/asset.png}}"

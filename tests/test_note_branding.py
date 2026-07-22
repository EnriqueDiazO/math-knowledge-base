"""Portable branding contract, state, media, and renderer regression tests."""

# ruff: noqa: D103

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from editor.cornell import media as cornell_media
from editor.cornell.media import prepare_cornell_image_assets
from editor.cornell.models import DEFAULT_TEMPLATE_ID as CORNELL_TEMPLATE
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.renderer import generate_cornell_document_tex
from editor.cpi.media import prepare_cpi_image_assets
from editor.cpi.models import DEFAULT_TEMPLATE_ID as CPI_TEMPLATE
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.renderer import generate_cpi_document_tex
from editor.note_branding import DEFAULT_WATERMARK_OPACITY
from editor.note_branding import DEFAULT_WATERMARK_SCALE
from editor.note_branding import branding_key
from editor.note_branding import branding_widget_prefix
from editor.note_branding import normalize_watermark_upload
from editor.note_branding import pending_watermark_upload
from editor.note_branding import remove_watermark_state
from editor.note_branding import reset_watermark_state
from editor.note_branding import stage_watermark_upload
from editor.note_branding import sync_branding_state
from editor.note_branding import watermark_from_state


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (12, 8), (12, 70, 120, 80)).save(output, format="PNG")
    return output.getvalue()


def _cornell_document(watermark: CornellWatermark | None = None, *, pages: int = 1) -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=CORNELL_TEMPLATE,
        pages=tuple(
            CornellPage(
                page_id=f"p{index}",
                order=index,
                cue=CornellRegion(heading="Preguntas", latex="Cue"),
                main=CornellRegion(heading="Contenido", latex="Main"),
                summary=CornellRegion(heading="Resumen", latex="Summary"),
            )
            for index in range(1, pages + 1)
        ),
        watermark=watermark or CornellWatermark(),
    )


def _cpi_document(watermark: CornellWatermark | None = None, *, pages: int = 1) -> CpiDocument:
    return CpiDocument(
        schema_version=1,
        template_id=CPI_TEMPLATE,
        pages=tuple(
            CpiPage(
                page_number=index,
                comprehension=CpiRegion(heading="Comprensión", latex="C"),
                production=CpiRegion(heading="Producción", latex="P"),
                integration=CpiRegion(heading="Integración", latex="I"),
            )
            for index in range(1, pages + 1)
        ),
        watermark=watermark or CornellWatermark(),
    )


def test_legacy_notes_without_watermark_keep_disabled_safe_defaults() -> None:
    cornell_payload = _cornell_document().to_dict()
    cpi_payload = _cpi_document().to_dict()
    cornell_payload.pop("watermark")
    cpi_payload.pop("watermark")

    cornell = CornellDocument.from_dict(cornell_payload)
    cpi = CpiDocument.from_dict(cpi_payload)

    assert cornell.watermark == CornellWatermark()
    assert cpi.watermark == CornellWatermark()
    assert cornell.watermark.all_pages is True


@pytest.mark.parametrize("opacity", (0.0, 0.2, 1.0))
def test_watermark_accepts_valid_opacity_boundaries(opacity: float) -> None:
    assert CornellWatermark(opacity=opacity).opacity == opacity


@pytest.mark.parametrize("opacity", (-0.01, 1.01))
def test_watermark_rejects_invalid_opacity(opacity: float) -> None:
    with pytest.raises(ValueError, match="opacity"):
        CornellWatermark(opacity=opacity)


@pytest.mark.parametrize("scale", (0.05, 0.30, 0.90, 2.0))
def test_watermark_accepts_valid_size_boundaries(scale: float) -> None:
    assert CornellWatermark(scale=scale).scale == scale


@pytest.mark.parametrize("scale", (0.049, 2.01))
def test_watermark_rejects_invalid_size(scale: float) -> None:
    with pytest.raises(ValueError, match="scale"):
        CornellWatermark(scale=scale)


def test_empty_image_id_is_serializable_and_degrades_without_crashing(tmp_path: Path) -> None:
    watermark = CornellWatermark(enabled=True, type="image", image_id="")
    warnings: list[str] = []

    paths = prepare_cornell_image_assets(
        _cornell_document(watermark),
        tmp_path,
        warnings=warnings,
    )

    assert paths == {}
    assert warnings == ["La marca de agua está activa, pero no tiene un asset_id."]


def test_missing_watermark_asset_degrades_for_cornell_and_cpi(tmp_path: Path) -> None:
    watermark = CornellWatermark(enabled=True, type="image", image_id="missing-logo")
    cornell_warnings: list[str] = []
    cpi_warnings: list[str] = []

    assert prepare_cornell_image_assets(
        _cornell_document(watermark),
        tmp_path / "cornell",
        warnings=cornell_warnings,
    ) == {}
    assert prepare_cpi_image_assets(
        _cpi_document(watermark),
        tmp_path / "cpi",
        warnings=cpi_warnings,
    ) == {}
    assert cornell_warnings == ["Asset de marca de agua no encontrado: missing-logo"]
    assert cpi_warnings == ["Asset de marca de agua no encontrado: missing-logo"]


def test_all_pages_false_renders_watermark_only_on_first_page() -> None:
    watermark = CornellWatermark(
        enabled=True,
        type="image",
        image_id="logo",
        opacity=0.07,
        scale=0.70,
        all_pages=False,
    )

    cornell_tex = generate_cornell_document_tex(
        _cornell_document(watermark, pages=2),
        asset_paths_by_id={"logo": "assets/logo.png"},
    )
    cpi_tex = generate_cpi_document_tex(
        _cpi_document(watermark, pages=2),
        asset_paths_by_id={"logo": "assets/logo.png"},
    )

    assert cornell_tex.count("assets/logo.png") == 1
    assert cpi_tex.count("assets/logo.png") == 1
    assert "opacity=0.07" in cornell_tex
    assert r"width=0.7\paperwidth" in cpi_tex


def test_branding_widget_keys_are_scoped_by_format_note_and_field() -> None:
    keys = {
        branding_key(note_type, note_id, field)
        for note_type in ("cornell", "cpi")
        for note_id in ("note-a", "note-b")
        for field in ("enabled", "opacity", "scale")
    }

    assert len(keys) == 12
    assert branding_widget_prefix("cornell", "note-a") != branding_widget_prefix(
        "cornell", "note-b"
    )


def test_switching_notes_replaces_branding_state_without_contamination() -> None:
    state: dict[str, object] = {}
    first = CornellWatermark(enabled=True, type="text", text="FIRST")
    second = CornellWatermark(enabled=True, type="text", text="SECOND")

    sync_branding_state(state, note_type="cornell", note_id="first", watermark=first)
    sync_branding_state(state, note_type="cornell", note_id="second", watermark=second)

    assert all("branding" not in key or "cornell" in key for key in state)
    assert watermark_from_state(
        state,
        note_type="cornell",
        note_id="second",
        fallback=CornellWatermark(),
    ).text == "SECOND"
    assert not any(key.startswith(branding_widget_prefix("cornell", "first")) for key in state)


def test_upload_is_staged_in_memory_and_remove_does_not_touch_storage() -> None:
    state: dict[str, object] = {}

    staged = stage_watermark_upload(
        state,
        note_type="cornell",
        note_id="note-a",
        filename="logo.png",
        data=_png_bytes(),
        mime_type="image/png",
    )
    assert pending_watermark_upload(state, "cornell", "note-a") == staged

    remove_watermark_state(state, "cornell", "note-a")

    assert pending_watermark_upload(state, "cornell", "note-a") is None
    assert state[branding_key("cornell", "note-a", "enabled")] is False


def test_reset_restores_recommended_visual_values() -> None:
    state = {
        branding_key("cpi", "note-a", "opacity"): 0.19,
        branding_key("cpi", "note-a", "scale"): 0.88,
        branding_key("cpi", "note-a", "position"): "Superior derecha",
        branding_key("cpi", "note-a", "all_pages"): False,
    }

    reset_watermark_state(state, "cpi", "note-a")

    assert state[branding_key("cpi", "note-a", "opacity")] == DEFAULT_WATERMARK_OPACITY
    assert state[branding_key("cpi", "note-a", "scale")] == DEFAULT_WATERMARK_SCALE
    assert state[branding_key("cpi", "note-a", "position")] == "Centro"
    assert state[branding_key("cpi", "note-a", "all_pages")] is True


def test_webp_upload_normalizes_to_portable_png() -> None:
    output = io.BytesIO()
    try:
        Image.new("RGBA", (8, 8), (20, 30, 40, 60)).save(output, format="WEBP")
    except OSError:
        pytest.skip("Pillow was built without WebP support")

    normalized = normalize_watermark_upload("logo.webp", output.getvalue(), "image/webp")

    assert normalized["filename"] == "logo.png"
    assert normalized["mime_type"] == "image/png"
    assert bytes(normalized["data"]).startswith(b"\x89PNG\r\n\x1a\n")


def test_watermark_asset_path_with_spaces_is_copied_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cornell_media, "PROJECT_ROOT", tmp_path)
    source = tmp_path / "media" / "Logo COCID transparente.png"
    source.parent.mkdir()
    source.write_bytes(_png_bytes())
    watermark = CornellWatermark(enabled=True, type="image", image_id="logo-space")
    asset = {
        "asset_id": "logo-space",
        "filename": source.name,
        "path": source.relative_to(tmp_path).as_posix(),
        "mime_type": "image/png",
    }

    paths = prepare_cornell_image_assets(
        _cornell_document(watermark),
        tmp_path / "out",
        assets_by_id={"logo-space": asset},
    )

    assert paths["logo-space"].endswith("logo_cocid_transparente_logo-spa.png")
    assert (tmp_path / "out" / paths["logo-space"]).is_file()


def test_watermark_asset_rejects_parent_escape_and_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watermark = CornellWatermark(enabled=True, type="image", image_id="logo")
    document = _cornell_document(watermark)
    with pytest.raises(ValueError, match="unsafe path"):
        prepare_cornell_image_assets(
            document,
            tmp_path / "escape",
            assets_by_id={
                "logo": {
                    "asset_id": "logo",
                    "filename": "logo.png",
                    "path": "../logo.png",
                }
            },
        )

    monkeypatch.setattr(cornell_media, "PROJECT_ROOT", tmp_path)
    target = tmp_path / "target.png"
    target.write_bytes(_png_bytes())
    link = tmp_path / "logo.png"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        prepare_cornell_image_assets(
            document,
            tmp_path / "symlink",
            assets_by_id={
                "logo": {
                    "asset_id": "logo",
                    "filename": "logo.png",
                    "path": "logo.png",
                }
            },
        )

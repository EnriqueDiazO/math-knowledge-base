"""Tests for the CPI latex_notes persistence adapter."""

# ruff: noqa: D103

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest

from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_footer_text
from editor.cpi.models import CPI_NOTE_FORMAT
from editor.cpi.models import DEFAULT_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.models import generate_latex_body
from editor.cpi.persistence import build_cpi_note_document
from editor.cpi.persistence import extract_cpi_document
from editor.cpi.persistence import is_cpi_note


def sample_document() -> CpiDocument:
    second_page = CpiPage(
        page_number=2,
        comprehension=CpiRegion(heading="Comprensión", latex="Comprendí el caso general."),
        production=CpiRegion(heading="Producción", latex=r"\[ x^2+y^2=z^2 \]"),
        integration=CpiRegion(heading="Integración", latex="Aplicarlo en el siguiente problema."),
    )
    first_page = CpiPage(
        page_number=1,
        comprehension=CpiRegion(heading="Comprensión", latex="Entendí la definición."),
        production=CpiRegion(heading="Producción", latex="Resolví un ejemplo."),
        integration=CpiRegion(heading="Integración", latex="Conectar con matrices."),
    )
    return CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(second_page, first_page),
    )


def sample_metadata() -> dict:
    now = datetime(2026, 7, 7, 12, 0, 0)
    return {
        "title": "Nota CPI",
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "tags": ["cpi"],
        "created_at": now,
        "updated_at": now,
    }


def test_cpi_document_round_trip_to_dict_from_dict() -> None:
    document = sample_document()

    restored = CpiDocument.from_dict(document.to_dict())

    assert restored == CpiDocument.from_dict(restored.to_dict())
    assert [page["page_number"] for page in restored.to_dict()["pages"]] == [1, 2]


def test_cpi_legacy_document_without_identity_gets_safe_defaults() -> None:
    payload = sample_document().to_dict()
    payload.pop("attribution")
    payload.pop("watermark")

    restored = CpiDocument.from_dict(payload)

    assert restored.attribution == CornellAttribution()
    assert restored.watermark == CornellWatermark()
    assert not restored.attribution.enabled
    assert not restored.watermark.enabled


def test_cpi_document_identity_round_trip_to_dict_from_dict() -> None:
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=sample_document().pages,
        attribution=CornellAttribution(
            enabled=True,
            mode="auto",
            author="Enrique Díaz Ocampo",
            course="Python",
            year="2026",
            position="top_right",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="text",
            text="COCID",
            opacity=0.08,
            scale=0.5,
            position="center",
        ),
    )

    restored = CpiDocument.from_dict(document.to_dict())

    assert restored.attribution.mode == "auto"
    assert restored.attribution.author == "Enrique Díaz Ocampo"
    assert restored.attribution.course == "Python"
    assert restored.attribution.year == "2026"
    assert restored.attribution.position == "top_right"
    assert restored.watermark.enabled
    assert restored.watermark.type == "text"
    assert restored.watermark.text == "COCID"
    assert restored.watermark.opacity == 0.08
    assert restored.watermark.scale == 0.5
    assert restored.watermark.position == "center"
    assert build_footer_text(restored.attribution) == "© 2026 Enrique Díaz Ocampo · Python"


def test_cpi_document_accepts_serialized_identity_on_construction() -> None:
    attribution = CornellAttribution(
        enabled=True,
        mode="custom",
        text="Material CPI",
        position="bottom_right",
    )
    watermark = CornellWatermark(
        enabled=True,
        type="image",
        image_id="watermark-logo",
    )

    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=sample_document().pages,
        attribution=attribution.to_dict(),
        watermark=watermark.to_dict(),
    )

    assert document.attribution == attribution
    assert document.watermark == watermark


def test_cpi_document_custom_footer_and_image_watermark_round_trip() -> None:
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=sample_document().pages,
        attribution=CornellAttribution(
            enabled=True,
            mode="custom",
            text="Material de clase",
            position="bottom_right",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id="watermark-logo",
            opacity=0.12,
            scale=0.35,
            position="top_right",
        ),
    )

    restored = CpiDocument.from_dict(document.to_dict())

    assert build_footer_text(restored.attribution) == "Material de clase"
    assert restored.watermark.image_id == "watermark-logo"


def test_cpi_region_accepts_legacy_payload_without_image_ids() -> None:
    region = CpiRegion.from_dict({"heading": "Comprensión", "latex": "Texto"})

    assert region.image_ids == ()
    assert region.to_dict()["image_ids"] == []


def test_cpi_region_round_trip_with_image_ids() -> None:
    region = CpiRegion(heading="Producción", latex="Texto", image_ids=("img-prod",))

    restored = CpiRegion.from_dict(region.to_dict())

    assert restored.image_ids == ("img-prod",)


def test_cpi_document_rejects_duplicate_page_numbers() -> None:
    page = sample_document().ordered_pages()[0]

    with pytest.raises(ValueError, match="page_number"):
        CpiDocument(schema_version=1, template_id=DEFAULT_TEMPLATE_ID, pages=(page, page))


def test_generate_latex_body_uses_ordered_regions() -> None:
    latex_body = generate_latex_body(sample_document())

    assert latex_body.index("Entendí la definición.") < latex_body.index("Comprendí el caso general.")
    assert r"\paragraph*{Comprensión}" in latex_body
    assert r"\paragraph*{Producción}" in latex_body
    assert r"\paragraph*{Integración}" in latex_body


def test_build_cpi_note_document_preserves_metadata_and_regenerates_latex_body() -> None:
    metadata = {**sample_metadata(), "latex_body": "stale", "cpi": {"stale": True}}
    document = sample_document()

    note = build_cpi_note_document(metadata, document)

    assert note["note_format"] == CPI_NOTE_FORMAT
    assert note["latex_body"] == generate_latex_body(document)
    assert note["cpi"] == document.to_dict()
    assert note["title"] == metadata["title"]


def test_build_cpi_note_document_derives_global_image_ids_from_regions() -> None:
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CpiPage(
                page_number=1,
                comprehension=CpiRegion(
                    heading="Comprensión",
                    latex="Texto",
                    image_ids=("img-comp",),
                ),
                production=CpiRegion(
                    heading="Producción",
                    latex="Texto",
                    image_ids=("img-prod",),
                ),
                integration=CpiRegion(
                    heading="Integración",
                    latex="Texto",
                    image_ids=("img-comp", "img-int"),
                ),
            ),
        ),
    )

    note = build_cpi_note_document(sample_metadata(), document)

    assert note["image_ids"] == ["img-comp", "img-prod", "img-int"]


def test_build_cpi_note_document_includes_enabled_watermark_image_id() -> None:
    page = CpiPage(
        page_number=1,
        comprehension=CpiRegion(heading="Comprensión", latex="Texto", image_ids=("img-comp",)),
        production=CpiRegion(heading="Producción", latex="Texto"),
        integration=CpiRegion(heading="Integración", latex="Texto"),
    )
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(page,),
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id="watermark-logo",
        ),
    )

    note = build_cpi_note_document(sample_metadata(), document)

    assert note["image_ids"] == ["img-comp", "watermark-logo"]


def test_extract_cpi_document_round_trip_from_mongo_dict() -> None:
    document = sample_document()
    note = build_cpi_note_document(sample_metadata(), document)

    restored = extract_cpi_document(note)

    assert restored.to_dict() == document.to_dict()
    assert is_cpi_note(note)


def test_build_cpi_note_document_rejects_wrong_note_format() -> None:
    metadata = {**sample_metadata(), "note_format": "cornell_math_v1"}

    with pytest.raises(ValueError, match="Unsupported CPI note_format"):
        build_cpi_note_document(metadata, sample_document())


def test_extract_cpi_document_rejects_wrong_note_format() -> None:
    with pytest.raises(ValueError, match="Unsupported note_format"):
        extract_cpi_document({"note_format": "freeform", "cpi": {}})


def test_build_cpi_note_document_does_not_mutate_input_metadata() -> None:
    metadata = {**sample_metadata(), "tags": ["cpi"]}
    before = deepcopy(metadata)

    note = build_cpi_note_document(metadata, sample_document())
    note["tags"].append("mutated")

    assert metadata == before

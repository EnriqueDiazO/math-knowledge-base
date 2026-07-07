"""Tests for the Cornell latex_notes persistence adapter."""

# ruff: noqa: D103

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_footer_text
from editor.cornell.models import generate_latex_body
from editor.cornell.persistence import build_cornell_note_document
from editor.cornell.persistence import extract_cornell_document
from editor.cornell.persistence import is_cornell_note


def sample_document() -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CornellPage(
                page_id="p001",
                order=1,
                cue=CornellRegion(heading="Ideas principales", latex="Cue body"),
                main=CornellRegion(heading="Aritmética", latex=r"\[ A+B=B+A \]"),
                summary=CornellRegion(heading="Observaciones", latex="Summary body"),
            ),
        ),
    )


def sample_document_with_images() -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CornellPage(
                page_id="p001",
                order=1,
                cue=CornellRegion(heading="Ideas principales", latex="Cue body", image_ids=("cue-img",)),
                main=CornellRegion(heading="Aritmética", latex=r"\[ A+B=B+A \]", image_ids=("main-img",)),
                summary=CornellRegion(heading="Observaciones", latex="Summary body", image_ids=("cue-img",)),
            ),
        ),
    )


def sample_metadata() -> dict:
    now = datetime(2026, 7, 7, 12, 0, 0)
    return {
        "title": "Nota Cornell",
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "tags": ["matrices", "cornell"],
        "image_ids": ["asset-1"],
        "created_at": now,
        "updated_at": now,
    }


def test_is_cornell_note_detects_cornell_note() -> None:
    note = build_cornell_note_document(sample_metadata(), sample_document())

    assert is_cornell_note(note)


def test_is_cornell_note_detects_legacy_freeform_note() -> None:
    assert not is_cornell_note({"title": "Legacy", "latex_body": "freeform"})
    assert not is_cornell_note({"note_format": "freeform", "latex_body": "body"})
    assert not is_cornell_note(None)


def test_build_cornell_note_document_preserves_normal_metadata() -> None:
    metadata = sample_metadata()
    note = build_cornell_note_document(metadata, sample_document())

    for field, value in metadata.items():
        if field == "image_ids":
            continue
        assert note[field] == value
    assert note["image_ids"] == []
    assert note["note_format"] == CORNELL_NOTE_FORMAT
    assert "cornell" in note


def test_build_cornell_note_document_derives_global_image_ids_from_regions() -> None:
    note = build_cornell_note_document(sample_metadata(), sample_document_with_images())

    assert note["image_ids"] == ["cue-img", "main-img"]


def test_build_cornell_note_document_includes_enabled_watermark_image_id() -> None:
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=sample_document_with_images().pages,
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id="watermark-logo",
        ),
    )

    note = build_cornell_note_document(sample_metadata(), document)

    assert note["image_ids"] == ["cue-img", "main-img", "watermark-logo"]


def test_build_cornell_note_document_regenerates_latex_body() -> None:
    metadata = {
        **sample_metadata(),
        "latex_body": "external stale body",
        "cornell": {"stale": True},
    }
    document = sample_document()
    note = build_cornell_note_document(metadata, document)

    assert note["latex_body"] == generate_latex_body(document)
    assert note["latex_body"] != "external stale body"
    assert note["cornell"] == document.to_dict()


def test_extract_cornell_document_round_trip_from_mongo_dict() -> None:
    document = sample_document()
    note = build_cornell_note_document(sample_metadata(), document)

    restored = extract_cornell_document(note)

    assert restored == document


def test_attribution_footer_mode_round_trip_from_mongo_dict() -> None:
    document = CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=sample_document().pages,
        attribution=CornellAttribution(
            enabled=True,
            mode="auto",
            text="Texto personalizado inactivo",
            author="Enrique Díaz Ocampo",
            course="Python",
            year="2026",
            position="bottom_right",
        ),
    )
    note = build_cornell_note_document(sample_metadata(), document)

    restored = extract_cornell_document(note)

    assert restored.attribution.mode == "auto"
    assert restored.attribution.text == "Texto personalizado inactivo"
    assert build_footer_text(restored.attribution) == "© 2026 Enrique Díaz Ocampo · Python"


def test_build_cornell_note_document_rejects_wrong_note_format() -> None:
    metadata = {**sample_metadata(), "note_format": "freeform"}

    with pytest.raises(ValueError, match="Unsupported Cornell note_format"):
        build_cornell_note_document(metadata, sample_document())


def test_extract_cornell_document_rejects_wrong_note_format() -> None:
    with pytest.raises(ValueError, match="Unsupported note_format"):
        extract_cornell_document({"note_format": "freeform", "cornell": {}})


def test_extract_cornell_document_rejects_invalid_cornell_structure() -> None:
    note = {
        **sample_metadata(),
        "note_format": CORNELL_NOTE_FORMAT,
        "latex_body": "stale",
        "cornell": {"schema_version": 1, "template_id": DEFAULT_TEMPLATE_ID},
    }

    with pytest.raises(ValueError, match="pages"):
        extract_cornell_document(note)


def test_extract_cornell_document_rejects_legacy_note() -> None:
    with pytest.raises(ValueError, match="not a cornell"):
        extract_cornell_document({"title": "Legacy", "latex_body": "body"})


def test_build_cornell_note_document_does_not_mutate_input_metadata() -> None:
    metadata = {
        **sample_metadata(),
        "latex_body": "external stale body",
        "tags": ["matrices"],
        "image_ids": ["asset-1"],
    }
    before = deepcopy(metadata)

    note = build_cornell_note_document(metadata, sample_document())
    note["tags"].append("mutated")
    note["image_ids"].append("asset-2")

    assert metadata == before

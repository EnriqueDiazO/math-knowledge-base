"""Tests for the Cornell latex_notes persistence adapter."""

# ruff: noqa: D103

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
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
        assert note[field] == value
    assert note["note_format"] == CORNELL_NOTE_FORMAT
    assert "cornell" in note


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

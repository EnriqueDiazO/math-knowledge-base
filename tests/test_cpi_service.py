"""Tests for the CPI CRUD service layer."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest

from editor.cornell.models import CornellWatermark
from editor.cpi.models import CPI_NOTE_FORMAT
from editor.cpi.models import DEFAULT_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.models import generate_latex_body
from editor.cpi.persistence import build_cpi_note_document
from editor.cpi.service import create_cpi_note
from editor.cpi.service import delete_cpi_note
from editor.cpi.service import duplicate_cpi_note
from editor.cpi.service import get_cpi_note
from editor.cpi.service import list_cpi_notes
from editor.cpi.service import update_cpi_note


@dataclass(frozen=True, slots=True)
class FakeInsertResult:
    inserted_id: str


@dataclass(frozen=True, slots=True)
class FakeUpdateResult:
    matched_count: int
    modified_count: int


@dataclass(frozen=True, slots=True)
class FakeDeleteResult:
    deleted_count: int


class FakeMathMongo:
    def __init__(self) -> None:
        self.notes: dict[str, dict[str, Any]] = {}
        self.next_id = 1
        self.last_query: dict[str, Any] | None = None
        self.last_limit: int | None = None

    def create_notebook_note(self, note_data: dict) -> FakeInsertResult:
        note_id = f"note-{self.next_id}"
        self.next_id += 1
        note = deepcopy(note_data)
        note["_id"] = note_id
        self.notes[note_id] = note
        return FakeInsertResult(inserted_id=note_id)

    def get_notebook_note_by_id(self, note_id: str) -> dict[str, Any] | None:
        note = self.notes.get(str(note_id))
        return deepcopy(note) if note is not None else None

    def update_notebook_note(self, note_id: str, note_data: dict) -> FakeUpdateResult:
        if str(note_id) not in self.notes:
            return FakeUpdateResult(matched_count=0, modified_count=0)
        self.notes[str(note_id)].update(deepcopy(note_data))
        return FakeUpdateResult(matched_count=1, modified_count=1)

    def delete_notebook_note(self, note_id: str) -> FakeDeleteResult:
        if str(note_id) not in self.notes:
            return FakeDeleteResult(deleted_count=0)
        del self.notes[str(note_id)]
        return FakeDeleteResult(deleted_count=1)

    def get_notebook_notes(self, query: dict | None = None, limit: int = 100) -> list[dict]:
        self.last_query = deepcopy(query or {})
        self.last_limit = int(limit)
        matches = [
            deepcopy(note)
            for note in self.notes.values()
            if self._matches(note, self.last_query)
        ]
        return matches[: self.last_limit]

    def _matches(self, note: dict[str, Any], query: dict[str, Any]) -> bool:
        if not query:
            return True
        if "$and" in query:
            return all(self._matches(note, clause) for clause in query["$and"])
        return all(note.get(key) == value for key, value in query.items())


def sample_document(production: str = "Resolví un ejemplo.") -> CpiDocument:
    return CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CpiPage(
                page_number=1,
                comprehension=CpiRegion(heading="Comprensión", latex="Entendí la definición."),
                production=CpiRegion(heading="Producción", latex=production),
                integration=CpiRegion(heading="Integración", latex="Siguiente acción."),
            ),
        ),
    )


def sample_metadata() -> dict[str, Any]:
    return {
        "title": "CPI note",
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "tags": ["cpi"],
    }


def create_sample_cpi(db: FakeMathMongo) -> str:
    result = create_cpi_note(db, sample_metadata(), sample_document())
    return result.inserted_id


def test_create_cpi_note_uses_existing_backend_and_regenerates_latex_body() -> None:
    db = FakeMathMongo()
    metadata = {**sample_metadata(), "latex_body": "stale external body"}
    document = sample_document()

    result = create_cpi_note(db, metadata, document)

    stored = db.notes[result.inserted_id]
    assert stored["note_format"] == CPI_NOTE_FORMAT
    assert stored["latex_body"] == generate_latex_body(document)
    assert stored["title"] == metadata["title"]


def test_get_cpi_note_reads_and_regenerates_stale_latex_body() -> None:
    db = FakeMathMongo()
    note_id = create_sample_cpi(db)
    db.notes[note_id]["latex_body"] = "stale stored body"

    note = get_cpi_note(db, note_id)

    assert note is not None
    assert note["latex_body"] == generate_latex_body(sample_document())


def test_update_cpi_note_preserves_metadata_and_rebuilds_payload() -> None:
    db = FakeMathMongo()
    note_id = create_sample_cpi(db)
    metadata = {**sample_metadata(), "title": "Updated", "latex_body": "stale"}
    document = sample_document(production="Producción actualizada")

    result = update_cpi_note(db, note_id, metadata, document)

    assert result.matched_count == 1
    stored = db.notes[note_id]
    assert stored["title"] == "Updated"
    assert stored["latex_body"] == generate_latex_body(document)
    assert stored["cpi"]["pages"][0]["production"]["latex"] == "Producción actualizada"


def test_list_cpi_notes_returns_only_cpi_notes() -> None:
    db = FakeMathMongo()
    cpi_id = create_sample_cpi(db)
    db.notes["cornell"] = {"_id": "cornell", "note_format": "cornell_math_v1", "latex_body": "x"}
    db.notes["legacy"] = {"_id": "legacy", "title": "Legacy", "latex_body": "freeform"}

    notes = list_cpi_notes(db)

    assert [note["_id"] for note in notes] == [cpi_id]
    assert db.last_query == {"note_format": CPI_NOTE_FORMAT}


def test_list_cpi_notes_combines_query_with_cpi_filter() -> None:
    db = FakeMathMongo()
    algebra_id = create_sample_cpi(db)
    geometry_note = build_cpi_note_document(
        {**sample_metadata(), "project": "Geometry"},
        sample_document(production="Geometría"),
    )
    geometry_note["_id"] = "geometry"
    db.notes["geometry"] = geometry_note

    notes = list_cpi_notes(db, query={"project": "Algebra"}, limit=10)

    assert [note["_id"] for note in notes] == [algebra_id]
    assert db.last_query == {"$and": [{"note_format": CPI_NOTE_FORMAT}, {"project": "Algebra"}]}
    assert db.last_limit == 10


def test_update_cpi_note_rejects_legacy_without_mutating_it() -> None:
    db = FakeMathMongo()
    legacy = {"_id": "legacy", "title": "Legacy", "latex_body": "freeform"}
    db.notes["legacy"] = deepcopy(legacy)

    with pytest.raises(ValueError, match="not a cpi_v1"):
        update_cpi_note(db, "legacy", sample_metadata(), sample_document())

    assert db.notes["legacy"] == legacy


def test_update_cpi_note_preserves_seed_identity() -> None:
    db = FakeMathMongo()
    note_id = create_sample_cpi(db)
    db.notes[note_id]["seed_id"] = "stable-tutorial"

    update_cpi_note(db, note_id, sample_metadata(), sample_document())

    assert db.notes[note_id]["seed_id"] == "stable-tutorial"


def test_delete_cpi_note_deletes_only_valid_cpi_note() -> None:
    db = FakeMathMongo()
    note_id = create_sample_cpi(db)

    result = delete_cpi_note(db, note_id)

    assert result.deleted_count == 1
    assert note_id not in db.notes


def test_duplicate_cpi_note_preserves_branding_and_shares_asset(monkeypatch) -> None:
    db = FakeMathMongo()
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=sample_document().pages,
        watermark=CornellWatermark(enabled=True, type="image", image_id="shared-logo"),
    )
    original_id = create_cpi_note(db, sample_metadata(), document).inserted_id
    attached: list[tuple[str, tuple[str, ...]]] = []
    monkeypatch.setattr(
        "editor.cpi.service.attach_media_assets_to_note",
        lambda _db, *, note_id, asset_ids: attached.append((note_id, tuple(asset_ids))),
    )

    result = duplicate_cpi_note(db, original_id)

    duplicate = db.notes[result.inserted_id]
    assert duplicate["cpi"]["watermark"] == document.watermark.to_dict()
    assert duplicate["image_ids"] == ["shared-logo"]
    assert attached == [(result.inserted_id, ("shared-logo",))]

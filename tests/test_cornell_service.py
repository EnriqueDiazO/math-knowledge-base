"""Tests for the Cornell CRUD service layer."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import generate_latex_body
from editor.cornell.persistence import build_cornell_note_document
from editor.cornell.service import create_cornell_note
from editor.cornell.service import delete_cornell_note
from editor.cornell.service import get_cornell_note
from editor.cornell.service import list_cornell_notes
from editor.cornell.service import update_cornell_note


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


class FailingMathMongo(FakeMathMongo):
    def __init__(self, method_name: str) -> None:
        super().__init__()
        self.method_name = method_name

    def _maybe_fail(self, method_name: str) -> None:
        if method_name == self.method_name:
            raise RuntimeError(f"{method_name} failed")

    def create_notebook_note(self, note_data: dict) -> FakeInsertResult:
        self._maybe_fail("create_notebook_note")
        return super().create_notebook_note(note_data)

    def get_notebook_note_by_id(self, note_id: str) -> dict[str, Any] | None:
        self._maybe_fail("get_notebook_note_by_id")
        return super().get_notebook_note_by_id(note_id)

    def get_notebook_notes(self, query: dict | None = None, limit: int = 100) -> list[dict]:
        self._maybe_fail("get_notebook_notes")
        return super().get_notebook_notes(query=query, limit=limit)


def sample_document(main_heading: str = "Aritmética") -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(
            CornellPage(
                page_id="p001",
                order=1,
                cue=CornellRegion(heading="Ideas", latex="Cue body"),
                main=CornellRegion(heading=main_heading, latex=r"\[ A+B=B+A \]"),
                summary=CornellRegion(heading="Resumen", latex="Summary body"),
            ),
        ),
    )


def sample_metadata() -> dict[str, Any]:
    now = datetime(2026, 7, 7, 12, 0, 0)
    return {
        "title": "Cornell note",
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "tags": ["cornell"],
        "image_ids": ["asset-1"],
        "created_at": now,
        "updated_at": now,
    }


def create_sample_cornell(db: FakeMathMongo) -> str:
    result = create_cornell_note(db, sample_metadata(), sample_document())
    return result.inserted_id


def test_create_cornell_note_uses_existing_backend_and_regenerates_latex_body() -> None:
    db = FakeMathMongo()
    metadata = {**sample_metadata(), "latex_body": "stale external body"}
    document = sample_document()

    result = create_cornell_note(db, metadata, document)

    stored = db.notes[result.inserted_id]
    assert stored["note_format"] == CORNELL_NOTE_FORMAT
    assert stored["latex_body"] == generate_latex_body(document)
    assert stored["title"] == metadata["title"]


def test_get_cornell_note_reads_and_regenerates_stale_latex_body() -> None:
    db = FakeMathMongo()
    note_id = create_sample_cornell(db)
    db.notes[note_id]["latex_body"] = "stale stored body"

    note = get_cornell_note(db, note_id)

    assert note is not None
    assert note["latex_body"] == generate_latex_body(sample_document())


def test_update_cornell_note_preserves_metadata_and_rebuilds_payload() -> None:
    db = FakeMathMongo()
    note_id = create_sample_cornell(db)
    metadata = {**sample_metadata(), "title": "Updated", "latex_body": "stale"}
    document = sample_document(main_heading="Matrices actualizadas")

    result = update_cornell_note(db, note_id, metadata, document)

    assert result.matched_count == 1
    stored = db.notes[note_id]
    assert stored["title"] == "Updated"
    assert stored["latex_body"] == generate_latex_body(document)
    assert stored["cornell"]["pages"][0]["main"]["heading"] == "Matrices actualizadas"


def test_delete_cornell_note_deletes_only_valid_cornell_note() -> None:
    db = FakeMathMongo()
    note_id = create_sample_cornell(db)

    result = delete_cornell_note(db, note_id)

    assert result.deleted_count == 1
    assert note_id not in db.notes


def test_list_cornell_notes_returns_only_cornell_notes() -> None:
    db = FakeMathMongo()
    cornell_id = create_sample_cornell(db)
    db.notes["legacy"] = {"_id": "legacy", "title": "Legacy", "latex_body": "freeform"}

    notes = list_cornell_notes(db)

    assert [note["_id"] for note in notes] == [cornell_id]
    assert db.last_query == {"note_format": CORNELL_NOTE_FORMAT}


def test_list_cornell_notes_combines_query_with_cornell_filter() -> None:
    db = FakeMathMongo()
    algebra_id = create_sample_cornell(db)
    geometry_note = build_cornell_note_document(
        {**sample_metadata(), "project": "Geometry"},
        sample_document(main_heading="Geometría"),
    )
    geometry_note["_id"] = "geometry"
    db.notes["geometry"] = geometry_note

    notes = list_cornell_notes(db, query={"project": "Algebra"}, limit=10)

    assert [note["_id"] for note in notes] == [algebra_id]
    assert db.last_query == {"$and": [{"note_format": CORNELL_NOTE_FORMAT}, {"project": "Algebra"}]}
    assert db.last_limit == 10


def test_get_cornell_note_rejects_legacy_note() -> None:
    db = FakeMathMongo()
    db.notes["legacy"] = {"_id": "legacy", "title": "Legacy", "latex_body": "freeform"}

    with pytest.raises(ValueError, match="not a cornell"):
        get_cornell_note(db, "legacy")


def test_update_cornell_note_rejects_legacy_without_mutating_it() -> None:
    db = FakeMathMongo()
    legacy = {"_id": "legacy", "title": "Legacy", "latex_body": "freeform"}
    db.notes["legacy"] = deepcopy(legacy)

    with pytest.raises(ValueError, match="not a cornell"):
        update_cornell_note(db, "legacy", sample_metadata(), sample_document())

    assert db.notes["legacy"] == legacy


def test_delete_cornell_note_rejects_legacy_without_deleting_it() -> None:
    db = FakeMathMongo()
    legacy = {"_id": "legacy", "title": "Legacy", "latex_body": "freeform"}
    db.notes["legacy"] = deepcopy(legacy)

    with pytest.raises(ValueError, match="not a cornell"):
        delete_cornell_note(db, "legacy")

    assert db.notes["legacy"] == legacy


def test_service_does_not_mutate_arguments() -> None:
    db = FakeMathMongo()
    metadata = {**sample_metadata(), "tags": ["cornell"], "image_ids": ["asset-1"]}
    document = sample_document()
    metadata_before = deepcopy(metadata)
    document_before = document.to_dict()

    create_cornell_note(db, metadata, document)

    assert metadata == metadata_before
    assert document.to_dict() == document_before


def test_backend_errors_are_propagated_clearly() -> None:
    db = FailingMathMongo("create_notebook_note")

    with pytest.raises(RuntimeError, match="create_notebook_note failed"):
        create_cornell_note(db, sample_metadata(), sample_document())


def test_list_backend_errors_are_propagated_clearly() -> None:
    db = FailingMathMongo("get_notebook_notes")

    with pytest.raises(RuntimeError, match="get_notebook_notes failed"):
        list_cornell_notes(db)

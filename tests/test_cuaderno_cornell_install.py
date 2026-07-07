"""Tests for Cornell support in the Cuaderno Mongo installer."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from scripts import install_cuaderno_mode as installer


class FakeCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.full_name = f"fake.{name}"
        self.documents: list[dict[str, Any]] = []
        self.indexes: list[dict[str, Any]] = [{"name": "_id_", "key": {"_id": 1}}]
        self.options_data: dict[str, Any] = {}

    def list_indexes(self) -> list[dict[str, Any]]:
        return deepcopy(self.indexes)

    def create_index(self, keys: list[tuple[str, int]], *, name: str, unique: bool = False) -> str:
        self.indexes.append({"name": name, "key": dict(keys), "unique": unique})
        return name

    def options(self) -> dict[str, Any]:
        return deepcopy(self.options_data)


class FakeDB:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.commands: list[tuple[str, str, dict[str, Any]]] = []

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self.collections:
            self.collections[name] = FakeCollection(name)
        return self.collections[name]

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> None:
        if name in self.collections:
            raise AssertionError(f"collection already exists: {name}")
        self.collections[name] = FakeCollection(name)

    def command(self, command_name: str, collection_name: str, **kwargs: Any) -> dict[str, int]:
        if command_name != "collMod":
            raise AssertionError(f"unexpected command: {command_name}")
        collection = self[collection_name]
        collection.options_data.update(deepcopy(kwargs))
        self.commands.append((command_name, collection_name, deepcopy(kwargs)))
        return {"ok": 1}


def _index_key_counts(collection: FakeCollection) -> Counter[tuple[tuple[str, int], ...]]:
    return Counter(tuple(index["key"].items()) for index in collection.list_indexes())


def _required_fields_present(document: dict[str, Any], schema: dict[str, Any]) -> bool:
    return all(field in document for field in schema.get("required", []))


def test_cuaderno_install_is_idempotent_and_preserves_existing_latex_notes(monkeypatch) -> None:
    monkeypatch.setattr(installer, "_ensure_media_directories", lambda: None)
    db = FakeDB()
    db.create_collection("latex_notes")
    legacy_note = {
        "_id": "legacy-1",
        "title": "Legacy",
        "date": "2026-07-07",
        "latex_body": "Texto libre",
        "created_at": "now",
        "updated_at": "now",
    }
    db["latex_notes"].documents.append(deepcopy(legacy_note))

    assert installer.install(db) == 0
    assert installer.install(db) == 0

    assert "latex_notes" in db.list_collection_names()
    assert db["latex_notes"].documents == [legacy_note]
    index_counts = _index_key_counts(db["latex_notes"])
    for keys, _name in installer.CORNELL_LATEX_NOTE_INDEXES:
        assert index_counts[tuple(keys)] == 1


def test_latex_notes_validator_is_legacy_and_cornell_compatible() -> None:
    validator = installer._latex_notes_validator()
    schema = validator["$jsonSchema"]
    properties = schema["properties"]

    legacy_note = {
        "title": "Legacy",
        "date": "2026-07-07",
        "latex_body": "Texto libre",
    }
    cornell_note = {
        **legacy_note,
        "note_format": installer.CORNELL_NOTE_FORMAT,
        "cornell": {
            "schema_version": 1,
            "template_id": "historical_cornell_math_letter_v1",
            "pages": [
                {
                    "page_id": "p001",
                    "order": 1,
                    "cue": {"heading": "Cue", "latex": "Cue body", "image_ids": []},
                    "main": {"heading": "Main", "latex": "Main body", "image_ids": []},
                    "summary": {"heading": "Summary", "latex": "Summary body", "image_ids": []},
                    "source_refs": [],
                }
            ],
        },
    }
    cornell_schema = properties["cornell"]
    page_schema = cornell_schema["properties"]["pages"]["items"]

    assert "note_format" not in schema["required"]
    assert "cornell" not in schema["required"]
    assert "created_at" not in schema["required"]
    assert "updated_at" not in schema["required"]
    assert properties["note_format"]["enum"] == [installer.CORNELL_NOTE_FORMAT]
    assert _required_fields_present(legacy_note, schema)
    assert _required_fields_present(cornell_note, schema)
    assert _required_fields_present(cornell_note["cornell"], cornell_schema)
    assert _required_fields_present(cornell_note["cornell"]["pages"][0], page_schema)


def test_cornell_install_status_reports_validator_and_indexes(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(installer, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(installer, "MEDIA_ROOT", Path("media"))
    monkeypatch.setattr(installer, "MEDIA_IMAGES_DIR", Path("media/images"))
    db = FakeDB()

    assert installer.install(db) == 0
    assert installer.status(db) == 0

    output = capsys.readouterr().out
    assert "Cornell:" in output
    assert "validador cornell_math_v1: OK" in output
    assert "índices Cornell: OK" in output
    assert installer._latex_notes_validator_supports_cornell(db)
    assert installer._latex_notes_has_cornell_indexes(db)

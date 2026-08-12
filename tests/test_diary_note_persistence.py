"""Regression tests for lazy, per-document Diario settings persistence."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path
from typing import Any

from editor.diary_note_models import NoteReference
from editor.diary_note_models import settings_from_note
from editor.diary_note_persistence import persist_diary_note_update


class RecordingCollection:
    """Small in-memory recorder that applies the supported dotted ``$set`` paths."""

    def __init__(self, documents: list[dict[str, Any]]) -> None:
        """Copy input documents so assertions can detect unintended mutations."""
        self.documents = {document["_id"]: dict(document) for document in documents}
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
    ) -> object:
        """Record and apply one exact-ID update."""
        self.calls.append((query, update))
        document = self.documents[query["_id"]]
        for path, value in update["$set"].items():
            target = document
            parts = path.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
        return object()


def _legacy_note(note_id: str = "legacy-a") -> dict[str, Any]:
    return {
        "_id": note_id,
        "title": "Nota histórica",
        "latex_body": r"\section{Contenido}",
        "unknown_historical_field": {"preserve": True},
    }


def test_a_opening_legacy_note_performs_no_mongodb_write() -> None:
    collection = RecordingCollection([_legacy_note()])

    settings = settings_from_note(collection.documents["legacy-a"])

    assert settings.table_of_contents.show_table_of_contents is False
    assert collection.calls == []


def test_b_saving_legacy_note_without_new_changes_adds_no_new_fields() -> None:
    note = _legacy_note()
    collection = RecordingCollection([note])
    settings = settings_from_note(note)

    persist_diary_note_update(
        collection,
        note,
        ordinary_fields={"title": note["title"]},
        settings=settings,
    )

    _, update = collection.calls[0]
    assert update == {"$set": {"title": "Nota histórica"}}
    assert "academic_metadata" not in collection.documents["legacy-a"]
    assert "page_layout" not in collection.documents["legacy-a"]
    assert "table_of_contents" not in collection.documents["legacy-a"]
    assert "references" not in collection.documents["legacy-a"]


def test_c_changing_only_toc_visibility_emits_one_dotted_set() -> None:
    note = _legacy_note()
    collection = RecordingCollection([note])
    settings = settings_from_note(note)
    settings.table_of_contents.show_table_of_contents = True

    persist_diary_note_update(collection, note, settings=settings)

    assert collection.calls == [
        (
            {"_id": "legacy-a"},
            {"$set": {"table_of_contents.show_table_of_contents": True}},
        )
    ]


def test_d_adding_reference_only_sets_ordered_reference_array() -> None:
    note = _legacy_note()
    collection = RecordingCollection([note])
    settings = settings_from_note(note)
    settings.references = [NoteReference(title="Referencia parcial")]

    persist_diary_note_update(collection, note, settings=settings)

    query, update = collection.calls[0]
    assert query == {"_id": "legacy-a"}
    assert set(update["$set"]) == {"references"}
    assert update["$set"]["references"][0]["title"] == "Referencia parcial"


def test_e_only_the_selected_document_is_modified() -> None:
    selected = _legacy_note("selected")
    untouched = _legacy_note("untouched")
    collection = RecordingCollection([selected, untouched])
    settings = settings_from_note(selected)
    settings.academic_metadata.institution = "Institución"

    persist_diary_note_update(collection, selected, settings=settings)

    assert collection.calls[0][0] == {"_id": "selected"}
    assert "academic_metadata" in collection.documents["selected"]
    assert collection.documents["untouched"] == untouched


def test_f_feature_has_no_bulk_update_replace_or_backfill_api() -> None:
    feature_files = (
        Path("editor/diary_note_models.py"),
        Path("editor/diary_note_persistence.py"),
        Path("editor/diary_note_ui.py"),
        Path("editor/diary_note_latex.py"),
        Path("editor/cuaderno_page.py"),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in feature_files)

    forbidden = ("update_many", "replace_many", "replace_one", "backfill")
    assert all(token not in source for token in forbidden)

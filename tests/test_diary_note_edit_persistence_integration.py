"""Integration contract from Diario edit state through Mongo and back to UI state."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from copy import deepcopy
from typing import Any

from editor.diary_note_persistence import persist_diary_note_update
from editor.diary_note_ui import add_manual_reference_state
from editor.diary_note_ui import initialize_note_settings_state
from editor.diary_note_ui import settings_from_ui_state


class _UpdateResult:
    acknowledged = True
    matched_count = 1
    modified_count = 1


class _RecordingCollection:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = deepcopy(document)
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
    ) -> _UpdateResult:
        assert query == {"_id": self.document["_id"]}
        assert set(update) == {"$set"}
        self.calls.append((deepcopy(query), deepcopy(update)))
        for dotted_path, value in update["$set"].items():
            target = self.document
            parts = dotted_path.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = deepcopy(value)
        return _UpdateResult()


def _legacy_note() -> dict[str, Any]:
    return {
        "_id": "legacy-edit-integration",
        "title": "Nota legacy",
        "date": "2026-08-12",
        "latex_body": r"\chapter{Contenido}",
        "unknown_historical_field": {"preserve": True},
    }


def _settings_key(prefix: str, group: str, field: str) -> str:
    return f"{prefix}_settings_{group}_{field}"


def _reference_key(prefix: str, reference_id: str, field: str) -> str:
    return f"{prefix}_reference_{reference_id}_{field}"


def test_all_edited_settings_persist_and_reconstruct_after_widget_cleanup() -> None:
    original = _legacy_note()
    collection = _RecordingCollection(original)
    prefix = "diary_edit_legacy_structured"
    state: dict[str, Any] = {}
    initialize_note_settings_state(
        state,
        prefix=prefix,
        note=original,
        identity=str(original["_id"]),
    )
    academic_values = {
        "institution": "Institución persistida",
        "program": "Programa persistido",
        "course_code": "DI-204",
        "course_name": "Curso persistido",
        "week": "Semana 4",
        "session": "Sesión 2",
        "short_title": "Título corto persistido",
    }
    for field, value in academic_values.items():
        state[_settings_key(prefix, "academic", field)] = value
    layout_values: dict[str, Any] = {
        "enabled": True,
        "header_left": "Encabezado izquierdo personalizado",
        "header_center": "Encabezado central personalizado",
        "header_right": "Encabezado derecho personalizado",
        "footer_left": "Pie izquierdo personalizado",
        "footer_center": "Pie central personalizado",
        "footer_right": "Pie derecho personalizado",
    }
    for field, value in layout_values.items():
        state[_settings_key(prefix, "layout", field)] = value
    toc_values: dict[str, Any] = {
        "show_table_of_contents": True,
        "toc_title": "Índice persistido",
        "toc_depth": 1,
        "position": "after_title",
    }
    for field, value in toc_values.items():
        state[_settings_key(prefix, "toc", field)] = value
    list_of_figures_values: dict[str, Any] = {
        "show_list_of_figures": True,
        "title": "Índice de figuras",
    }
    for field, value in list_of_figures_values.items():
        state[_settings_key(prefix, "lof", field)] = value
    list_of_tables_values: dict[str, Any] = {
        "show_list_of_tables": True,
        "title": "Índice de tablas",
    }
    for field, value in list_of_tables_values.items():
        state[_settings_key(prefix, "lot", field)] = value
    reference_id = add_manual_reference_state(state, prefix)
    reference_values = {
        "kind": "article",
        "citation_key": "persisted2026",
        "authors": "Autora persistida",
        "title": "Referencia persistida",
        "year_or_date": "2026",
        "url": "https://example.test/persisted_reference",
    }
    for field, value in reference_values.items():
        state[_reference_key(prefix, reference_id, field)] = value

    edited_settings = settings_from_ui_state(state, prefix)
    persist_diary_note_update(collection, original, settings=edited_settings)

    assert len(collection.calls) == 1
    set_payload = collection.calls[0][1]["$set"]
    assert set(set_payload) == {
        *(f"academic_metadata.{field}" for field in academic_values),
        *(f"page_layout.{field}" for field in layout_values),
        *(f"table_of_contents.{field}" for field in toc_values),
        *(f"list_of_figures.{field}" for field in list_of_figures_values),
        *(f"list_of_tables.{field}" for field in list_of_tables_values),
        "references",
    }
    assert collection.document["unknown_historical_field"] == {"preserve": True}

    # Streamlit removes widget keys while the Read view is active, but retains
    # non-widget bookkeeping such as loaded_identity.  Reopening the same note
    # must therefore reload the persisted document instead of trusting the marker.
    reopened_state = {
        f"{prefix}_settings_loaded_identity": str(original["_id"]),
        f"{prefix}_settings_reference_ids": [reference_id],
        _reference_key(prefix, reference_id, "origin"): "manual",
        _reference_key(prefix, reference_id, "catalog_reference_id"): None,
        _reference_key(prefix, reference_id, "__extra__"): {},
    }
    initialize_note_settings_state(
        reopened_state,
        prefix=prefix,
        note=collection.document,
        identity=str(original["_id"]),
    )
    reopened = settings_from_ui_state(reopened_state, prefix)

    for field, value in academic_values.items():
        assert getattr(reopened.academic_metadata, field) == value
    for field, value in layout_values.items():
        assert getattr(reopened.page_layout, field) == value
    for field, value in toc_values.items():
        actual = getattr(reopened.table_of_contents, field)
        assert getattr(actual, "value", actual) == value
    for field, value in list_of_figures_values.items():
        assert getattr(reopened.list_of_figures, field) == value
    for field, value in list_of_tables_values.items():
        assert getattr(reopened.list_of_tables, field) == value
    assert len(reopened.references) == 1
    assert reopened.references[0].reference_id == reference_id
    for field, value in reference_values.items():
        actual = getattr(reopened.references[0], field)
        assert getattr(actual, "value", actual) == value
    assert len(collection.calls) == 1

    # Re-saving exactly what was reconstructed emits no settings write.
    assert (
        persist_diary_note_update(
            collection,
            collection.document,
            settings=reopened,
        )
        is None
    )
    assert len(collection.calls) == 1


def test_opening_and_reopening_unchanged_legacy_note_performs_zero_writes() -> None:
    original = _legacy_note()
    collection = _RecordingCollection(original)
    prefix = "diary_edit_unchanged_structured"
    state: dict[str, Any] = {}

    initialize_note_settings_state(
        state,
        prefix=prefix,
        note=collection.document,
        identity=str(original["_id"]),
    )
    defaults = settings_from_ui_state(state, prefix)
    assert persist_diary_note_update(collection, original, settings=defaults) is None

    state = {f"{prefix}_settings_loaded_identity": str(original["_id"])}
    initialize_note_settings_state(
        state,
        prefix=prefix,
        note=collection.document,
        identity=str(original["_id"]),
    )

    assert settings_from_ui_state(state, prefix) == defaults
    assert collection.calls == []
    assert collection.document == original

"""Unit tests for backward-compatible Diario note settings."""

# ruff: noqa: D103

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from editor.diary_note_models import DiaryNoteSettings
from editor.diary_note_models import NoteReference
from editor.diary_note_models import default_diary_note_settings
from editor.diary_note_models import move_reference
from editor.diary_note_models import note_reference_from_catalog
from editor.diary_note_models import note_with_settings
from editor.diary_note_models import reference_warnings
from editor.diary_note_models import resolve_tokens
from editor.diary_note_models import settings_from_note
from editor.diary_note_models import settings_persistence_set
from editor.diary_note_models import settings_warnings
from editor.diary_note_models import token_values
from mathmongo.source_catalog.models import Reference


def test_old_note_loads_with_conservative_defaults() -> None:
    note = {
        "_id": "legacy",
        "title": "Nota antigua",
        "date": "2026-08-11",
        "latex_body": r"\section{Uno}",
        "unknown_legacy_field": {"keep": True},
    }

    settings = settings_from_note(note)
    round_tripped = note_with_settings(note, settings)

    assert settings.references == []
    assert settings.page_layout.enabled is False
    assert settings.table_of_contents.show_table_of_contents is False
    assert round_tripped["unknown_legacy_field"] == {"keep": True}
    assert round_tripped["latex_body"] == note["latex_body"]
    assert settings_persistence_set(note, settings) == {}


def test_new_note_uses_metadata_driven_page_layout_defaults() -> None:
    settings = default_diary_note_settings(new_note=True)

    assert settings.page_layout.enabled is True
    assert settings.page_layout.header_left == "{institution} · {course_code}"
    assert settings.page_layout.header_right == "{week} · {short_title}"
    assert settings.page_layout.footer_left == "{course_name}"
    assert settings.page_layout.footer_right == "{author}"
    assert settings.page_layout.show_page_number is True
    assert settings.table_of_contents.show_table_of_contents is False


def test_references_preserve_stable_ids_and_order_after_serialization() -> None:
    first = NoteReference(title="Primera", position=7)
    second = NoteReference(title="Segunda", position=9)
    settings = DiaryNoteSettings(references=[first, second])

    restored = settings_from_note(note_with_settings({}, settings))
    moved = move_reference(restored.references, second.reference_id, -1)

    assert [item.reference_id for item in restored.references] == [
        first.reference_id,
        second.reference_id,
    ]
    assert [item.position for item in restored.references] == [0, 1]
    assert [item.reference_id for item in moved] == [second.reference_id, first.reference_id]
    assert [item.position for item in moved] == [0, 1]


def test_empty_reference_is_a_persisted_non_exportable_draft() -> None:
    reference = NoteReference()
    restored = settings_from_note(note_with_settings({}, DiaryNoteSettings(references=[reference])))

    assert restored.references[0].reference_id == reference.reference_id
    assert restored.references[0].exportable is False
    assert "no se exportará" in reference_warnings(restored.references[0])[0]


def test_catalog_reference_becomes_linked_reproducible_snapshot() -> None:
    catalog = Reference(
        reference_id="ref_2bcbff88-871f-48a4-b726-459440dad62a",
        reference_type="article",
        authors=[{"literal": "Institución & Datos"}],
        title="Título ágil",
        year=2026,
        journal="Revista",
        url="https://example.test/a_b?x=1&y=2",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    snapshot = note_reference_from_catalog(catalog, position=3)

    assert snapshot.catalog_reference_id == catalog.reference_id
    assert snapshot.origin.value == "catalog"
    assert snapshot.authors == "Institución & Datos"
    assert snapshot.title == catalog.title
    assert snapshot.position == 3


def test_token_resolution_uses_one_metadata_context_and_drops_unknown_tokens() -> None:
    settings = default_diary_note_settings(new_note=True)
    settings.academic_metadata.institution = "COCID"
    settings.academic_metadata.course_code = "DI104"
    settings.academic_metadata.short_title = "Objetos"
    values = token_values(
        {"title": "Título completo", "date": "2026-08-11"},
        settings,
    )

    resolved, warnings = resolve_tokens(
        "{institution} · {course_code} · {short_title} · {missing}",
        values,
    )

    assert resolved == "COCID · DI104 · Objetos ·"
    assert warnings == ("Token desconocido omitido: {missing}",)


def test_invalid_doi_url_and_duplicate_citation_keys_warn_without_blocking_save() -> None:
    settings = DiaryNoteSettings(
        references=[
            NoteReference(title="Uno", citation_key="same", doi="not-a-doi"),
            NoteReference(title="Dos", citation_key="SAME", url="example.test"),
        ]
    )

    warnings = settings_warnings(settings)

    assert any("DOI" in warning for warning in warnings)
    assert any("URL" in warning for warning in warnings)
    assert any("repetida" in warning for warning in warnings)

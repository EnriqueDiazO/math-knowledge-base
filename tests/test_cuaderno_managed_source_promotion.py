"""Managed Source contract for Cuaderno diary promotion."""

# ruff: noqa: D103

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.helpers.concept_builders import build_concept_metadata
from editor.helpers.managed_source_selection import can_save_with_managed_source
from editor.helpers.managed_source_selection import load_active_sources
from editor.helpers.managed_source_selection import resolve_active_source
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.repository import PageResult
from schemas.schemas import ConceptoBase

ROOT = Path(__file__).resolve().parents[1]
CUADERNO = ROOT / "editor" / "cuaderno_page.py"
ACTIVE_ID = "src_123e4567-e89b-42d3-a456-426614174100"
ARCHIVED_ID = "src_123e4567-e89b-42d3-a456-426614174101"


def _promote_branch() -> str:
    source = CUADERNO.read_text(encoding="utf-8")
    start = source.index("def _render_diary_promote_note")
    end = source.index("\ndef _render_diary_section", start)
    return source[start:end]


class _ReadOnlySourceRepository:
    def __init__(
        self,
        sources: list[Source],
        *,
        fail_list: bool = False,
        fail_get: bool = False,
    ) -> None:
        self.sources = list(sources)
        self.fail_list = fail_list
        self.fail_get = fail_get
        self.list_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []
        self.write_calls: list[str] = []

    def list(self, *, page: int, page_size: int, status: str | None = None):
        self.list_calls.append({"page": page, "page_size": page_size, "status": status})
        if self.fail_list:
            raise RuntimeError("catalog unavailable")
        values = tuple(source for source in self.sources if source.status.value == status)
        return PageResult(values, page=page, page_size=page_size, total=len(values))

    def get_by_id(self, source_id: str) -> Source | None:
        self.get_calls.append(source_id)
        if self.fail_get:
            raise RuntimeError("catalog changed")
        return next((source for source in self.sources if source.source_id == source_id), None)

    def insert(self, *_args, **_kwargs) -> None:
        self.write_calls.append("insert")
        raise AssertionError("Cuaderno promotion must not create Sources")

    def update(self, *_args, **_kwargs) -> None:
        self.write_calls.append("update")
        raise AssertionError("Cuaderno promotion must not update Sources")


class _Collection:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []

    def insert_one(self, document: dict[str, Any]) -> object:
        self.inserted.append(dict(document))
        return object()

    def delete_one(self, _query: dict[str, Any]) -> object:
        raise AssertionError("rollback was not expected")


class _Database:
    def __init__(self) -> None:
        self.concepts = _Collection()
        self.latex_documents = _Collection()


def _source(name: str, source_id: str, *, status: SourceStatus) -> Source:
    return Source(name=name, source_id=source_id, status=status)


def test_promote_ui_has_no_free_source_or_custom_fallback() -> None:
    branch = _promote_branch()

    assert 'st.text_input(\n            "Source"' not in branch
    assert "default_source" not in branch
    assert "(Custom...)" not in branch
    assert "New source name" not in branch
    assert "SourceRepository(" in branch
    assert "load_active_sources(" in branch
    assert "options=managed_source_ids" in branch
    assert "format_func" in branch


def test_promote_ui_blocks_empty_or_failed_catalog_and_rehydrates_before_insert() -> None:
    branch = _promote_branch()

    assert "No hay Sources activas disponibles" in branch
    assert "No se pudieron cargar las Sources administradas" in branch
    assert "disabled=not source_selection_valid" in branch
    assert "resolve_active_source(" in branch
    assert branch.index("resolve_active_source(") < branch.index("insert_concept_with_latex_atomic(")


def test_promote_options_are_active_catalog_records_not_legacy_concept_strings() -> None:
    active = _source("Managed without concepts", ACTIVE_ID, status=SourceStatus.ACTIVE)
    archived = _source("Archived", ARCHIVED_ID, status=SourceStatus.ARCHIVED)
    repository = _ReadOnlySourceRepository([archived, active])

    options = load_active_sources(repository)

    assert options == (active,)
    assert "Legacy concepts only" not in {source.name for source in options}
    assert repository.write_calls == []


def test_promote_empty_or_failed_catalog_cannot_resolve_a_save_target() -> None:
    empty = _ReadOnlySourceRepository([])
    failed = _ReadOnlySourceRepository([], fail_list=True)

    assert load_active_sources(empty) == ()
    assert can_save_with_managed_source(None) is False
    with pytest.raises(RuntimeError, match="catalog unavailable"):
        load_active_sources(failed)


def test_promote_rehydrates_by_id_and_rejects_archived_or_changed_targets() -> None:
    active = _source("Current snapshot", ACTIVE_ID, status=SourceStatus.ACTIVE)
    archived = _source("Archived", ARCHIVED_ID, status=SourceStatus.ARCHIVED)
    repository = _ReadOnlySourceRepository([active, archived])

    selected = resolve_active_source(repository, ACTIVE_ID)

    assert selected == active
    assert resolve_active_source(repository, ARCHIVED_ID) is None
    assert repository.get_calls == [ACTIVE_ID, ARCHIVED_ID]
    assert repository.write_calls == []


def test_promoted_concept_and_latex_persist_same_snapshot_and_source_id() -> None:
    active = _source("Managed snapshot", ACTIVE_ID, status=SourceStatus.ACTIVE)
    repository = _ReadOnlySourceRepository([active])
    selected = resolve_active_source(repository, ACTIVE_ID)
    assert selected is not None
    concept = ConceptoBase(
        id="definition:promoted",
        tipo="definicion",
        contenido_latex="x=x",
        categorias=["diario"],
        source=selected.name,
        source_id=selected.source_id,
    )
    metadata = build_concept_metadata(concept)
    database = _Database()
    now = datetime(2026, 7, 18, 12, 0, 0)

    insert_concept_with_latex_atomic(
        database,
        concept.id,
        concept.source,
        metadata,
        concept.contenido_latex,
        now,
    )

    assert database.concepts.inserted[0]["source"] == active.name
    assert database.concepts.inserted[0]["source_id"] == active.source_id
    assert database.latex_documents.inserted[0]["source"] == active.name
    assert database.latex_documents.inserted[0]["source_id"] == active.source_id
    assert repository.write_calls == []


def test_changing_database_rebuilds_promote_options_from_that_repository() -> None:
    first = _ReadOnlySourceRepository(
        [_source("Database A", ACTIVE_ID, status=SourceStatus.ACTIVE)]
    )
    second = _ReadOnlySourceRepository(
        [_source("Database B", ARCHIVED_ID, status=SourceStatus.ACTIVE)]
    )

    assert [source.source_id for source in load_active_sources(first)] == [ACTIVE_ID]
    assert [source.source_id for source in load_active_sources(second)] == [ARCHIVED_ID]
    assert first.write_calls == second.write_calls == []

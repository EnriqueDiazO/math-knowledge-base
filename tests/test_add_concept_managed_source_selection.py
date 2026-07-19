"""Managed Source selection contract for the Add Concept page."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.models import SourceType
from mathmongo.source_catalog.repository import PageResult
from schemas.schemas import ConceptoBase

ACTIVE_ID = "src_123e4567-e89b-42d3-a456-426614174000"
ARCHIVED_ID = "src_123e4567-e89b-42d3-a456-426614174001"
SECOND_ID = "src_123e4567-e89b-42d3-a456-426614174002"


def _selection_module():
    return importlib.import_module("editor.helpers.managed_source_selection")


def _source(
    name: str,
    source_id: str,
    *,
    status: SourceStatus = SourceStatus.ACTIVE,
    source_type: SourceType = SourceType.OTHER,
) -> Source:
    return Source(
        name=name,
        source_id=source_id,
        status=status,
        source_type=source_type,
    )


class _SourceRepository:
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

    def list(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> PageResult[Source]:
        self.list_calls.append(
            {"page": page, "page_size": page_size, "status": status}
        )
        if self.fail_list:
            raise RuntimeError("catalog read failed")
        status_value = getattr(status, "value", status)
        filtered = [
            source
            for source in self.sources
            if status_value is None or source.status.value == status_value
        ]
        start = (page - 1) * page_size
        return PageResult(
            items=tuple(filtered[start : start + page_size]),
            page=page,
            page_size=page_size,
            total=len(filtered),
        )

    def get_by_id(self, source_id: str) -> Source | None:
        self.get_calls.append(source_id)
        if self.fail_get:
            raise RuntimeError("catalog hydration failed")
        return next(
            (source for source in self.sources if source.source_id == source_id),
            None,
        )

    def insert(self, _source: Source) -> None:
        self.write_calls.append("insert")
        raise AssertionError("Add Concept must never create a Source")

    def update(self, _source_id: str, _changes: dict[str, Any]) -> None:
        self.write_calls.append("update")
        raise AssertionError("Add Concept must never update a Source")


def _add_concept_branch() -> str:
    source = (
        Path(__file__).resolve().parents[1] / "editor" / "editor_streamlit.py"
    ).read_text(encoding="utf-8")
    start = source.index('elif page == "➕ Add Concept":')
    end = source.index('\nelif page == "✏️ Edit Concept":', start)
    return source[start:end]


def test_lists_only_active_sources_from_the_managed_catalog() -> None:
    module = _selection_module()
    active = _source("Managed active", ACTIVE_ID)
    archived = _source("Managed archived", ARCHIVED_ID, status=SourceStatus.ARCHIVED)
    repository = _SourceRepository([archived, active])

    sources = module.load_active_sources(repository)

    assert sources == (active,)
    assert repository.list_calls == [
        {"page": 1, "page_size": 100, "status": SourceStatus.ACTIVE.value}
    ]
    assert repository.write_calls == []


def test_managed_source_without_concepts_is_available_but_legacy_text_is_not() -> None:
    module = _selection_module()
    managed = _source("Managed without concepts", ACTIVE_ID)
    repository = _SourceRepository([managed])

    sources = module.load_active_sources(repository)

    assert [source.name for source in sources] == ["Managed without concepts"]
    assert "Legacy concepts only" not in {source.name for source in sources}


def test_source_labels_include_name_and_disambiguate_duplicate_names() -> None:
    module = _selection_module()
    first = _source("Duplicate", ACTIVE_ID, source_type=SourceType.BOOK)
    second = _source("Duplicate", SECOND_ID, source_type=SourceType.WEB)

    labels = module.source_labels((first, second))

    assert "Duplicate" in labels[ACTIVE_ID]
    assert "Duplicate" in labels[SECOND_ID]
    assert labels[ACTIVE_ID] != labels[SECOND_ID]
    assert ACTIVE_ID.removeprefix("src_")[:8] in labels[ACTIVE_ID]
    assert SECOND_ID.removeprefix("src_")[:8] in labels[SECOND_ID]


def test_selection_resolves_by_source_id_and_returns_the_name_snapshot() -> None:
    module = _selection_module()
    selected = _source("Snapshot name", ACTIVE_ID)
    repository = _SourceRepository([selected])

    resolved = module.resolve_active_source(repository, ACTIVE_ID)

    assert resolved is not None
    assert resolved.source_id == ACTIVE_ID
    assert resolved.name == "Snapshot name"
    assert repository.get_calls == [ACTIVE_ID]
    assert module.can_save_with_managed_source(resolved) is True
    assert repository.write_calls == []


def test_missing_or_archived_selection_cannot_be_saved() -> None:
    module = _selection_module()
    archived = _source("Archived", ARCHIVED_ID, status=SourceStatus.ARCHIVED)
    repository = _SourceRepository([archived])

    assert module.resolve_active_source(repository, None) is None
    assert module.resolve_active_source(repository, "") is None
    assert module.resolve_active_source(repository, ACTIVE_ID) is None
    assert module.resolve_active_source(repository, ARCHIVED_ID) is None
    assert module.can_save_with_managed_source(None) is False
    assert module.can_save_with_managed_source(archived) is False


def test_empty_catalog_returns_no_options_and_disables_save() -> None:
    module = _selection_module()
    repository = _SourceRepository([])

    assert module.load_active_sources(repository) == ()
    assert module.can_save_with_managed_source(None) is False


def test_catalog_read_and_hydration_errors_are_not_silently_replaced() -> None:
    module = _selection_module()
    failing_list = _SourceRepository([], fail_list=True)
    failing_get = _SourceRepository(
        [_source("Managed", ACTIVE_ID)],
        fail_get=True,
    )

    with pytest.raises(RuntimeError, match="catalog read failed"):
        module.load_active_sources(failing_list)
    with pytest.raises(RuntimeError, match="catalog hydration failed"):
        module.resolve_active_source(failing_get, ACTIVE_ID)


def test_all_active_source_pages_are_loaded() -> None:
    module = _selection_module()
    sources = [Source(name=f"Managed {index:03d}") for index in range(101)]
    repository = _SourceRepository(sources)

    loaded = module.load_active_sources(repository)

    assert len(loaded) == 101
    assert [call["page"] for call in repository.list_calls] == [1, 2]
    assert all(call["page_size"] == 100 for call in repository.list_calls)


def test_changing_active_database_rebuilds_options_from_the_new_repository() -> None:
    module = _selection_module()
    first = _SourceRepository([_source("First database", ACTIVE_ID)])
    second = _SourceRepository([_source("Second database", SECOND_ID)])

    first_options = module.load_active_sources(first)
    second_options = module.load_active_sources(second)

    assert [source.source_id for source in first_options] == [ACTIVE_ID]
    assert [source.source_id for source in second_options] == [SECOND_ID]
    assert len(first.list_calls) == 1
    assert len(second.list_calls) == 1


def test_add_concept_ui_removes_legacy_source_controls() -> None:
    branch = _add_concept_branch()

    assert 'db.concepts.distinct("source")' not in branch
    assert "(Custom...)" not in branch
    assert "New source name" not in branch
    assert "catalog_context.source_repository" in branch
    assert "managed_source_ids" in branch
    assert "format_func" in branch
    assert "index=None" in branch


def test_add_concept_handles_empty_and_failed_catalog_without_free_text() -> None:
    branch = _add_concept_branch()

    assert (
        "No hay Sources disponibles. Crea primero una Source desde Add Source."
        in branch
    )
    assert "No se pudieron cargar las Sources administradas" in branch
    assert "disabled=not source_selection_valid" in branch


def test_add_concept_rehydrates_and_persists_source_id_plus_snapshot() -> None:
    branch = _add_concept_branch()

    assert "resolve_active_source(" in branch
    assert '"source_id": source_id' in branch
    assert '"source": source' in branch
    assert "selected_source.name" in branch
    assert "selected_source.source_id" in branch


def test_add_concept_has_no_source_creation_or_catalog_writes() -> None:
    branch = _add_concept_branch()

    for forbidden in (
        "create_source(",
        "sources.insert_one(",
        "sources.update_one(",
        "source_repository.insert(",
        "source_repository.update(",
        "upsert",
    ):
        assert forbidden not in branch


def test_legacy_concepts_without_source_id_remain_readable() -> None:
    concept = ConceptoBase(
        id="definition:legacy",
        tipo="definicion",
        contenido_latex="x = x",
        categorias=["Algebra"],
        source="Legacy concepts only",
    )

    assert concept.source == "Legacy concepts only"
    assert concept.source_id is None

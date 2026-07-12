"""Business-rule tests for the explicitly scoped Source Catalog service."""

# ruff: noqa: D103

from __future__ import annotations

from typing import Any

import pytest

from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.service import CatalogResultStatus
from mathmongo.source_catalog.service import SourceCatalogService


class _SourceRepository:
    def __init__(self, database: Any) -> None:
        self.database = database
        self.records: dict[str, Source] = {}
        self.blockers: dict[str, list[str]] = {}
        self.update_calls = 0

    def insert(self, source: Source) -> Source:
        self.records[source.source_id] = source
        return source

    def get_by_id(self, source_id: str) -> Source | None:
        return self.records.get(source_id)

    def duplicate_candidates(self, _candidate: Source) -> list[Source]:
        return list(self.records.values())

    def update(self, source_id: str, changes: dict) -> Source | None:
        self.update_calls += 1
        current = self.records.get(source_id)
        if current is None:
            return None
        data = current.model_dump(mode="python")
        data.update(changes)
        updated = Source.model_validate(data)
        self.records[source_id] = updated
        return updated

    def archive(self, source_id: str) -> Source | None:
        current = self.records.get(source_id)
        if current is None:
            return None
        self.records[source_id] = current.archived()
        return self.records[source_id]

    def reactivate(self, source_id: str) -> Source | None:
        current = self.records.get(source_id)
        if current is None:
            return None
        self.records[source_id] = current.reactivated()
        return self.records[source_id]

    def deletion_blockers(self, source_id: str) -> list[str]:
        return self.blockers.get(source_id, [])

    def physical_delete_if_unused(self, source_id: str) -> bool:
        if self.deletion_blockers(source_id):
            raise AssertionError("service must inspect blockers first")
        return self.records.pop(source_id, None) is not None


class _ReferenceRepository:
    def __init__(self, database: Any) -> None:
        self.database = database
        self.records: dict[str, Reference] = {}
        self.blockers: dict[str, list[str]] = {}
        self.update_calls = 0

    def insert(self, reference: Reference) -> Reference:
        self.records[reference.reference_id] = reference
        return reference

    def get_by_id(self, reference_id: str) -> Reference | None:
        return self.records.get(reference_id)

    def duplicate_candidates(self, _candidate: Reference) -> list[Reference]:
        return list(self.records.values())

    def update(self, reference_id: str, changes: dict) -> Reference | None:
        self.update_calls += 1
        current = self.records.get(reference_id)
        if current is None:
            return None
        data = current.model_dump(mode="python")
        data.update(changes)
        updated = Reference.model_validate(data)
        self.records[reference_id] = updated
        return updated

    def archive(self, reference_id: str) -> Reference | None:
        current = self.records.get(reference_id)
        if current is None:
            return None
        self.records[reference_id] = current.archived()
        return self.records[reference_id]

    def reactivate(self, reference_id: str) -> Reference | None:
        current = self.records.get(reference_id)
        if current is None:
            return None
        self.records[reference_id] = current.reactivated()
        return self.records[reference_id]

    def associate_source(self, reference_id: str, source_id: str) -> Reference | None:
        current = self.records.get(reference_id)
        if current is None:
            return None
        self.records[reference_id] = current.associated_with(source_id)
        return self.records[reference_id]

    def disassociate_source(self, reference_id: str, source_id: str) -> Reference | None:
        current = self.records.get(reference_id)
        if current is None:
            return None
        self.records[reference_id] = current.disassociated_from(source_id)
        return self.records[reference_id]

    def deletion_blockers(self, reference_id: str) -> list[str]:
        current = self.records.get(reference_id)
        if current is not None and current.source_ids:
            return ["source_ids"]
        return self.blockers.get(reference_id, [])

    def physical_delete_if_unused(self, reference_id: str) -> bool:
        if self.deletion_blockers(reference_id):
            raise AssertionError("service must inspect blockers first")
        return self.records.pop(reference_id, None) is not None


def _service(database: Any | None = None) -> tuple[SourceCatalogService, _SourceRepository, _ReferenceRepository]:
    database = database or object()
    sources = _SourceRepository(database)
    references = _ReferenceRepository(database)
    return (
        SourceCatalogService(
            database,
            source_repository=sources,
            reference_repository=references,
        ),
        sources,
        references,
    )


def test_service_rejects_repository_from_another_active_database() -> None:
    database_a = object()
    database_b = object()
    with pytest.raises(ValueError, match="same explicit active database"):
        SourceCatalogService(
            database_a,
            source_repository=_SourceRepository(database_a),
            reference_repository=_ReferenceRepository(database_b),
        )


def test_rename_keeps_id_and_optionally_preserves_previous_name() -> None:
    service, _, _ = _service()
    created = service.create_source({"name": "Original"})

    renamed = service.rename_source(
        created.value.source_id,
        "Renamed",
        keep_previous_as_alias=True,
    )

    assert renamed.status == CatalogResultStatus.SUCCESS
    assert renamed.value.source_id == created.value.source_id
    assert [alias.value for alias in renamed.value.aliases] == ["Original"]


def test_unified_source_update_writes_name_aliases_and_profile_once() -> None:
    service, sources, _ = _service()
    created = service.create_source(
        {"name": "Original", "aliases": ["Existing"], "description": "Before"}
    ).value

    updated = service.update_source(
        created.source_id,
        {
            "name": "Renamed",
            "aliases": ["Manual"],
            "description": "After",
        },
        preserve_previous_name_as_alias=True,
    )

    assert updated.status == CatalogResultStatus.SUCCESS
    assert updated.persisted
    assert updated.value.source_id == created.source_id
    assert updated.value.name == "Renamed"
    assert [alias.value for alias in updated.value.aliases] == ["Manual", "Original"]
    assert updated.value.description == "After"
    assert sources.update_calls == 1


def test_alias_update_duplicate_gate_excludes_self_and_requires_override() -> None:
    service, sources, _ = _service()
    existing = service.create_source({"name": "Shared Alias"}).value
    target = service.create_source({"name": "Target"}).value

    gated = service.update_source(target.source_id, {"aliases": [existing.name]})

    assert gated.status == CatalogResultStatus.WARNING
    assert gated.persisted is False
    assert sources.records[target.source_id].aliases == []

    accepted = service.update_source(
        target.source_id,
        {"aliases": [existing.name]},
        allow_duplicate=True,
    )

    assert accepted.status == CatalogResultStatus.WARNING
    assert accepted.persisted
    assert [alias.value for alias in accepted.value.aliases] == [existing.name]


def test_reference_never_creates_a_missing_source() -> None:
    service, sources, references = _service()
    unknown = Source(name="Not persisted").source_id

    result = service.create_reference({"doi": "10.1000/test", "source_ids": [unknown]})

    assert result.status == CatalogResultStatus.ERROR
    assert sources.records == {}
    assert references.records == {}


def test_possible_duplicate_warns_without_write_or_merge() -> None:
    service, _, references = _service()
    first = service.create_reference({"title": "Álgebra", "year": 2020})
    assert first.persisted

    warned = service.create_reference({"title": "Algebra", "year": 2020})

    assert warned.status == CatalogResultStatus.WARNING
    assert warned.persisted is False
    assert len(references.records) == 1


def test_reference_update_duplicate_gate_excludes_self_and_preserves_raw() -> None:
    service, _, references = _service()
    first = service.create_reference({"title": "First", "doi": "10.1000/shared"}).value
    raw = "@article{second, title={Second}}"
    second = service.create_reference(
        {"title": "Second", "doi": "10.1000/second", "bibtex": {"raw": raw}}
    ).value

    gated = service.update_reference(
        second.reference_id,
        {"doi": first.doi},
    )

    assert gated.status == CatalogResultStatus.CONFLICT
    assert gated.persisted is False
    assert references.records[second.reference_id].doi == "10.1000/second"

    accepted = service.update_reference(
        second.reference_id,
        {"doi": first.doi},
        allow_duplicate=True,
    )

    assert accepted.status == CatalogResultStatus.WARNING
    assert accepted.persisted
    assert accepted.value.reference_id == second.reference_id
    assert accepted.value.bibtex.raw == raw
    assert all(match.entity_id != second.reference_id for match in accepted.duplicates)
    assert references.update_calls == 1


def test_association_is_idempotent_and_physical_delete_is_guarded() -> None:
    service, _, _ = _service()
    source = service.create_source({"name": "Book"}).value
    reference = service.create_reference({"doi": "10.1000/a"}).value

    associated = service.associate_reference(reference.reference_id, source.source_id)
    repeated = service.associate_reference(reference.reference_id, source.source_id)
    blocked = service.delete_reference_if_unused(reference.reference_id)
    disassociated = service.disassociate_reference(reference.reference_id, source.source_id)
    deleted = service.delete_reference_if_unused(reference.reference_id)

    assert associated.value.source_ids == [source.source_id]
    assert repeated.value.source_ids == [source.source_id]
    assert blocked.status == CatalogResultStatus.BLOCKED
    assert disassociated.value.source_ids == []
    assert deleted.status == CatalogResultStatus.SUCCESS


def test_future_detector_fails_closed_before_source_delete() -> None:
    database = object()
    sources = _SourceRepository(database)
    references = _ReferenceRepository(database)
    service = SourceCatalogService(
        database,
        source_repository=sources,
        reference_repository=references,
        future_source_link_detectors=(lambda supplied_db, _source_id: [
            "future_link" if supplied_db is database else "wrong_database"
        ],),
    )
    source = service.create_source({"name": "Linked"}).value

    result = service.delete_source_if_unused(source.source_id)

    assert result.status == CatalogResultStatus.BLOCKED
    assert result.blockers == ("future_link",)
    assert source.source_id in sources.records


def test_bibtex_preview_has_no_write_and_imports_only_selected_entry() -> None:
    service, _, references = _service()
    preview = service.preview_bibtex(
        """
        @article{one, title={First}}
        @book{two, doi={https://doi.org/10.1000/two}}
        """
    )

    assert len(preview.candidates) == 2
    assert references.records == {}

    imported = service.import_selected_bibtex_candidates(preview, [2])

    assert imported.status == CatalogResultStatus.SUCCESS
    assert imported.value.imported_count == 1
    assert len(references.records) == 1
    stored = next(iter(references.records.values()))
    assert stored.bibtex.key == "two"
    assert stored.bibtex.raw.startswith("@book")

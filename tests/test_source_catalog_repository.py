"""Faithful isolated Mongo doubles for Source Catalog repositories and indexes."""

# ruff: noqa: D103

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any

import pytest
from bson import BSON
from pymongo.errors import DuplicateKeyError

from mathmongo.source_catalog.indexes import IndexPlanConflictError
from mathmongo.source_catalog.indexes import IndexState
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import ImmutableFieldError
from mathmongo.source_catalog.repository import PhysicalDeletionBlockedError
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import RepositoryConflictError
from mathmongo.source_catalog.repository import SourceRepository


def _values(document: Any, path: str) -> list[Any]:
    current = [document]
    for part in path.split("."):
        following: list[Any] = []
        for value in current:
            if isinstance(value, dict) and part in value:
                nested = value[part]
                following.extend(nested if isinstance(nested, list) else [nested])
            elif isinstance(value, list):
                for nested in value:
                    if isinstance(nested, dict) and part in nested:
                        item = nested[part]
                        following.extend(item if isinstance(item, list) else [item])
        current = following
    return current


def _condition_matches(values: list[Any], condition: Any) -> bool:
    if isinstance(condition, dict):
        if "$in" in condition:
            expected = condition["$in"]
            return any(value in expected for value in values)
        if "$regex" in condition:
            flags = re.IGNORECASE if "i" in condition.get("$options", "") else 0
            expression = re.compile(condition["$regex"], flags)
            return any(expression.search(str(value)) for value in values)
    return any(
        condition in value if isinstance(value, list) else value == condition
        for value in values
    )


def _matches(document: dict, query: dict) -> bool:
    for key, condition in query.items():
        if key == "$or":
            if not any(_matches(document, alternative) for alternative in condition):
                return False
        elif not _condition_matches(_values(document, key), condition):
            return False
    return True


class _Cursor:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = [copy.deepcopy(document) for document in documents]

    def sort(self, fields: list[tuple[str, int]]):
        for field, direction in reversed(fields):
            self.documents.sort(
                key=lambda document: (_values(document, field) or [None])[0],
                reverse=direction < 0,
            )
        return self

    def skip(self, amount: int):
        self.documents = self.documents[amount:]
        return self

    def limit(self, amount: int):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


@dataclass
class _WriteResult:
    matched_count: int = 0
    deleted_count: int = 0


class _Collection:
    def __init__(self, name: str, documents: list[dict] | None = None) -> None:
        self.name = name
        self.documents = [copy.deepcopy(document) for document in documents or []]
        self.queries: list[dict] = []
        self.indexes: list[dict] = [{"name": "_id_", "key": [("_id", 1)]}]

    def insert_one(self, document: dict) -> None:
        id_field = "source_id" if self.name == "sources" else "reference_id"
        if id_field in document and any(
            existing.get(id_field) == document[id_field] for existing in self.documents
        ):
            raise DuplicateKeyError("duplicate fake domain ID")
        self.documents.append(copy.deepcopy(document))

    def find_one(self, query: dict):
        self.queries.append(copy.deepcopy(query))
        return next(
            (copy.deepcopy(document) for document in self.documents if _matches(document, query)),
            None,
        )

    def find(self, query: dict):
        self.queries.append(copy.deepcopy(query))
        return _Cursor([document for document in self.documents if _matches(document, query)])

    def count_documents(self, query: dict) -> int:
        self.queries.append(copy.deepcopy(query))
        return sum(_matches(document, query) for document in self.documents)

    def update_one(self, query: dict, update: dict) -> _WriteResult:
        for document in self.documents:
            if not _matches(document, query):
                continue
            for field, value in update.get("$set", {}).items():
                document[field] = copy.deepcopy(value)
            for field, value in update.get("$addToSet", {}).items():
                document.setdefault(field, [])
                if value not in document[field]:
                    document[field].append(value)
            for field, value in update.get("$pull", {}).items():
                document[field] = [item for item in document.get(field, []) if item != value]
            return _WriteResult(matched_count=1)
        return _WriteResult()

    def delete_one(self, query: dict) -> _WriteResult:
        for index, document in enumerate(self.documents):
            if _matches(document, query):
                self.documents.pop(index)
                return _WriteResult(deleted_count=1)
        return _WriteResult()

    def list_indexes(self):
        return iter(copy.deepcopy(self.indexes))

    def create_index(
        self,
        keys: list[tuple[str, int]],
        *,
        name: str,
        unique: bool,
    ) -> str:
        existing = next((index for index in self.indexes if index["name"] == name), None)
        if existing is None:
            self.indexes.append({"name": name, "key": list(keys), "unique": unique})
        return name


class _Database:
    def __init__(self) -> None:
        self.collections: dict[str, _Collection] = {}
        self.accesses: list[str] = []

    def __getitem__(self, name: str) -> _Collection:
        self.accesses.append(name)
        return self.collections.setdefault(name, _Collection(name))

    def list_collection_names(self) -> list[str]:
        return list(self.collections)


def test_repository_construction_has_no_collection_or_index_side_effect() -> None:
    database = _Database()

    SourceRepository(database)
    ReferenceRepository(database)
    SourceCatalogIndexManager(database)

    assert database.accesses == []
    assert database.collections == {}


def test_two_explicit_databases_remain_isolated() -> None:
    first = _Database()
    second = _Database()
    first_repository = SourceRepository(first)
    second_repository = SourceRepository(second)

    source = first_repository.insert(Source(name="Only first"))

    assert first_repository.get_by_id(source.source_id) == source
    assert second_repository.get_by_id(source.source_id) is None


def test_duplicate_insert_and_immutable_update_are_typed_conflicts() -> None:
    repository = SourceRepository(_Database())
    source = repository.insert(Source(name="Unique"))

    with pytest.raises(RepositoryConflictError):
        repository.insert(source)
    with pytest.raises(ImmutableFieldError):
        repository.update(source.source_id, {"source_id": Source(name="Other").source_id})


def test_source_search_escapes_regex_and_paginates_server_side() -> None:
    database = _Database()
    repository = SourceRepository(database)
    literal = repository.insert(Source(name="[Algebra].*"))
    repository.insert(Source(name="Algebra ordinary"))
    for index in range(4):
        repository.insert(Source(name=f"Paged {index}"))

    result = repository.search("[Algebra].*", page=1, page_size=1)
    page = repository.search("Paged", page=2, page_size=2)

    assert [item.source_id for item in result.items] == [literal.source_id]
    regex = database["sources"].queries[-4]["$or"][0]["source_id"]["$regex"]
    assert regex == re.escape("[Algebra].*")
    assert page.total == 4
    assert len(page.items) == 2
    assert page.page == 2


def test_source_physical_delete_blocks_reference_and_exact_legacy_string() -> None:
    database = _Database()
    sources = SourceRepository(database)
    references = ReferenceRepository(database)
    source = sources.insert(
        Source(name="Catalog", legacy={"source_strings": ["Exact Legacy"]})
    )
    reference = references.insert(Reference(title="Linked", source_ids=[source.source_id]))
    database["concepts"].documents.append({"id": "c1", "source": "Exact Legacy"})

    with pytest.raises(PhysicalDeletionBlockedError) as caught:
        sources.physical_delete_if_unused(source.source_id)

    assert set(caught.value.blockers) == {"references:1", "legacy_concepts:1"}
    references.disassociate_source(reference.reference_id, source.source_id)
    database["concepts"].documents.clear()
    assert sources.physical_delete_if_unused(source.source_id) is True


def test_reference_association_states_and_safe_physical_delete() -> None:
    database = _Database()
    source = SourceRepository(database).insert(Source(name="Book"))
    repository = ReferenceRepository(database)
    reference = repository.insert(Reference(doi="doi:10.1000/example"))

    associated = repository.associate_source(reference.reference_id, source.source_id)
    repeated = repository.associate_source(reference.reference_id, source.source_id)
    archived = repository.archive(reference.reference_id)
    active = repository.reactivate(reference.reference_id)

    assert associated.source_ids == [source.source_id]
    assert repeated.source_ids == [source.source_id]
    assert archived.status.value == "archived"
    assert active.status.value == "active"
    with pytest.raises(PhysicalDeletionBlockedError):
        repository.physical_delete_if_unused(reference.reference_id)
    repository.disassociate_source(reference.reference_id, source.source_id)
    assert repository.physical_delete_if_unused(reference.reference_id) is True


def test_repository_hydrates_naive_bson_datetimes_as_utc() -> None:
    database = _Database()
    source = Source(name="BSON")
    reference = Reference(
        title="Nested BSON",
        accessed_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )
    source_document = BSON(BSON.encode(source.model_dump(mode="python"))).decode()
    reference_document = BSON(BSON.encode(reference.model_dump(mode="python"))).decode()
    assert source_document["created_at"].tzinfo is None
    assert reference_document["provenance"]["imported_at"].tzinfo is None
    database["sources"].documents.append(source_document)
    database["references"].documents.append(reference_document)

    loaded_source = SourceRepository(database).get_by_id(source.source_id)
    loaded_reference = ReferenceRepository(database).get_by_id(reference.reference_id)

    assert loaded_source.created_at.tzinfo == timezone.utc
    assert loaded_reference.accessed_at.tzinfo == timezone.utc
    assert loaded_reference.provenance.imported_at.tzinfo == timezone.utc


def test_index_status_plan_apply_is_explicit_and_idempotent() -> None:
    database = _Database()
    manager = SourceCatalogIndexManager(database)

    first_plan = manager.plan()
    first_apply = manager.apply()
    index_counts = {
        name: len(collection.indexes) for name, collection in database.collections.items()
    }
    second_apply = manager.apply()

    assert first_plan.missing
    assert not first_plan.conflicts
    assert all(status.state == IndexState.PRESENT for status in first_apply.statuses)
    assert all(status.state == IndexState.PRESENT for status in second_apply.statuses)
    assert index_counts == {
        name: len(collection.indexes) for name, collection in database.collections.items()
    }


def test_index_manager_reports_stable_name_conflict_without_creation() -> None:
    database = _Database()
    database["sources"].indexes.append(
        {
            "name": "sources_source_id_unique",
            "key": [("source_id", 1)],
            "unique": False,
        }
    )
    manager = SourceCatalogIndexManager(database)

    with pytest.raises(IndexPlanConflictError):
        manager.apply()

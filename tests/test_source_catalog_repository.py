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
        condition in value if isinstance(value, list) else value == condition for value in values
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
        self.projections: list[dict[str, Any] | None] = []
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

    def find(self, query: dict, projection: dict[str, Any] | None = None):
        self.queries.append(copy.deepcopy(query))
        self.projections.append(copy.deepcopy(projection))
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


def test_source_associations_load_with_one_bounded_bulk_query() -> None:
    database = _Database()
    repository = SourceRepository(database)
    first = repository.insert(Source(name="First"))
    second = repository.insert(Source(name="Second"))
    missing_id = Source(name="Missing").source_id
    query_count = len(database["sources"].queries)

    loaded = repository.get_by_ids([second.source_id, missing_id, first.source_id])

    assert {source.source_id for source in loaded} == {
        first.source_id,
        second.source_id,
    }
    assert len(database["sources"].queries) == query_count + 1
    assert database["sources"].queries[-1] == {
        "source_id": {"$in": [second.source_id, missing_id, first.source_id]}
    }


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


def test_source_duplicate_candidates_find_accent_and_punctuation_suggestion() -> None:
    database = _Database()
    repository = SourceRepository(database)
    existing = repository.insert(Source(name="Teoria de Grupos!"))

    candidates = repository.duplicate_candidates(Source(name="Teoría-de Grupos"))

    assert [candidate.source_id for candidate in candidates] == [existing.source_id]
    query = database["sources"].queries[-1]
    assert query != {}
    patterns = [
        condition["$regex"]
        for alternative in query["$or"]
        for condition in alternative.values()
        if isinstance(condition, dict) and "$regex" in condition
    ]
    assert patterns
    assert all("Teoría-de Grupos" not in pattern for pattern in patterns)


@pytest.mark.parametrize(
    ("existing_data", "candidate_data"),
    [
        (
            {"url": "HTTPS://EXAMPLE.TEST:443/path"},
            {"url": "https://example.test/path"},
        ),
        (
            {"authors": ["Ada Lovelace"]},
            {"authors": ["Ada Lovelace"]},
        ),
        (
            {"title": "Theorie des Groupes!", "year": 2020},
            {"title": "Théorie-des Groupes", "year": 2020},
        ),
    ],
)
def test_reference_duplicate_candidates_cover_weak_identity_queries(
    existing_data: dict,
    candidate_data: dict,
) -> None:
    database = _Database()
    repository = ReferenceRepository(database)
    existing = repository.insert(Reference(**existing_data))

    candidates = repository.duplicate_candidates(Reference(**candidate_data))

    assert [candidate.reference_id for candidate in candidates] == [existing.reference_id]
    assert database["references"].queries[-1] != {}


def test_reference_duplicate_candidates_prioritize_exact_identity_before_weak_limit() -> None:
    database = _Database()
    repository = ReferenceRepository(database)
    for index in range(120):
        repository.insert(
            Reference(
                title=f"Weak candidate {index}",
                authors=["Common Author"],
            )
        )
    exact = repository.insert(
        Reference(
            title="Exact DOI",
            authors=["Common Author"],
            doi="10.1000/exact-priority",
        )
    )

    candidates = repository.duplicate_candidates(
        Reference(authors=["Common Author"], doi="10.1000/exact-priority")
    )

    assert candidates[0].reference_id == exact.reference_id
    assert len(candidates) <= 100


def test_reference_quality_projection_excludes_raw_bibtex_and_notes() -> None:
    database = _Database()
    source = SourceRepository(database).insert(Source(name="Quality"))
    repository = ReferenceRepository(database)
    reference = repository.insert(
        Reference(
            title="Projected",
            notes="large private notes",
            bibtex={"key": "Projected", "raw": "@misc{Projected}"},
            source_ids=[source.source_id],
        )
    )

    page = repository.list_quality_candidates(source_id=source.source_id)

    assert page.total == 1
    assert page.items[0].reference_id == reference.reference_id
    projection = database["references"].projections[-1]
    assert projection is not None
    assert "bibtex.key" in projection
    assert "bibtex.raw" not in projection
    assert "notes" not in projection


def test_source_physical_delete_blocks_reference_and_exact_legacy_string() -> None:
    database = _Database()
    sources = SourceRepository(database)
    references = ReferenceRepository(database)
    source = sources.insert(Source(name="Catalog", legacy={"source_strings": ["Exact Legacy"]}))
    reference = references.insert(Reference(title="Linked", source_ids=[source.source_id]))
    database["concepts"].documents.append({"id": "c1", "source": "Exact Legacy"})

    with pytest.raises(PhysicalDeletionBlockedError) as caught:
        sources.physical_delete_if_unused(source.source_id)

    assert set(caught.value.blockers) == {"references:1", "legacy_concepts:1"}
    references.disassociate_source(reference.reference_id, source.source_id)
    database["concepts"].documents.clear()
    assert sources.physical_delete_if_unused(source.source_id) is True


def test_source_physical_delete_blocks_exact_current_name_match() -> None:
    database = _Database()
    sources = SourceRepository(database)
    source = sources.insert(Source(name="Current Exact Name"))
    database["concepts"].documents.append({"id": "legacy-current-name", "source": source.name})

    with pytest.raises(PhysicalDeletionBlockedError) as caught:
        sources.physical_delete_if_unused(source.source_id)

    assert caught.value.blockers == ("legacy_concepts:1",)


def test_source_physical_delete_blocks_managed_concept_with_historical_snapshot() -> None:
    database = _Database()
    sources = SourceRepository(database)
    source = sources.insert(Source(name="Current managed name"))
    concept = {
        "id": "managed-concept",
        "source": "Historical snapshot",
        "source_id": source.source_id,
    }
    database["concepts"].documents.append(concept)

    with pytest.raises(PhysicalDeletionBlockedError) as caught:
        sources.physical_delete_if_unused(source.source_id)

    assert caught.value.blockers == ("linked_concepts_by_source_id:1",)
    assert database["concepts"].documents == [concept]
    assert sources.get_by_id(source.source_id) is not None


def test_source_physical_delete_blocks_managed_latex_without_concept() -> None:
    database = _Database()
    sources = SourceRepository(database)
    source = sources.insert(Source(name="Managed"))
    latex = {
        "id": "orphan-latex",
        "source": "Old snapshot",
        "source_id": source.source_id,
    }
    database["latex_documents"].documents.append(latex)

    with pytest.raises(PhysicalDeletionBlockedError) as caught:
        sources.physical_delete_if_unused(source.source_id)

    assert caught.value.blockers == ("linked_latex_documents_by_source_id:1",)
    assert database["latex_documents"].documents == [latex]


def test_source_physical_delete_reports_concept_and_latex_links_separately() -> None:
    database = _Database()
    sources = SourceRepository(database)
    source = sources.insert(Source(name="Managed"))
    database["concepts"].documents.append(
        {"id": "paired", "source": "Snapshot", "source_id": source.source_id}
    )
    database["latex_documents"].documents.append(
        {"id": "paired", "source": "Snapshot", "source_id": source.source_id}
    )

    with pytest.raises(PhysicalDeletionBlockedError) as caught:
        sources.physical_delete_if_unused(source.source_id)

    assert caught.value.blockers == (
        "linked_concepts_by_source_id:1",
        "linked_latex_documents_by_source_id:1",
    )


def test_managed_link_still_blocks_after_source_rename_or_archive() -> None:
    database = _Database()
    sources = SourceRepository(database)
    source = sources.insert(Source(name="Before"))
    database["concepts"].documents.append(
        {"id": "linked", "source": "Before", "source_id": source.source_id}
    )
    renamed = sources.update(source.source_id, {"name": "After"})
    assert renamed is not None
    archived = sources.archive(source.source_id)
    assert archived is not None and archived.status.value == "archived"

    with pytest.raises(PhysicalDeletionBlockedError) as caught:
        sources.physical_delete_if_unused(source.source_id)

    assert "linked_concepts_by_source_id:1" in caught.value.blockers


def test_legacy_blocker_uses_exact_names_without_similarity_fallback() -> None:
    database = _Database()
    sources = SourceRepository(database)
    source = sources.insert(Source(name="Exact managed name"))
    database["concepts"].documents.append(
        {"id": "similar-only", "source": "Exact managed name extended"}
    )

    assert sources.physical_delete_if_unused(source.source_id) is True
    assert database["concepts"].documents == [
        {"id": "similar-only", "source": "Exact managed name extended"}
    ]


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


@pytest.mark.parametrize(
    "option",
    [
        {"partialFilterExpression": {"source_id": {"$exists": True}}},
        {"sparse": True},
        {"collation": {"locale": "en"}},
        {"hidden": True},
    ],
)
def test_index_manager_rejects_unapproved_semantic_options(option: dict) -> None:
    database = _Database()
    database["sources"].indexes.append(
        {
            "name": "sources_source_id_unique",
            "key": [("source_id", 1)],
            "unique": True,
            **option,
        }
    )

    plan = SourceCatalogIndexManager(database).plan()
    conflict = next(
        status for status in plan.conflicts if status.spec.name == "sources_source_id_unique"
    )

    assert "unapproved options" in conflict.detail

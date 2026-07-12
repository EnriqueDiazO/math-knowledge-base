"""Tests for isolated, read-only legacy concept catalog projections."""

# ruff: noqa: D101,D102,D103

from __future__ import annotations

import copy
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

import pytest

from mathmongo.source_catalog import LegacyConceptRepository
from mathmongo.source_catalog.legacy_repository import MAX_LEGACY_PAGE_SIZE
from mathmongo.source_catalog.legacy_repository import MAX_LEGACY_SEARCH_LENGTH
from mathmongo.source_catalog.legacy_repository import legacy_source_values
from mathmongo.source_catalog.models import Source


def _values(document: Any, path: str) -> list[Any]:
    current = [document]
    for part in path.split("."):
        following: list[Any] = []
        for value in current:
            if isinstance(value, dict) and part in value:
                nested = value[part]
                following.extend(nested if isinstance(nested, list) else [nested])
        current = following
    return current


def _condition_matches(values: list[Any], condition: Any) -> bool:
    if not isinstance(condition, dict):
        return any(value == condition for value in values)
    if not condition:
        return any(value == {} for value in values)

    for operator, expected in condition.items():
        if operator == "$exists" and bool(values) is not bool(expected):
            return False
        if operator == "$in" and not any(value in expected for value in values):
            return False
        if operator == "$nin" and any(value in expected for value in values):
            return False
        if operator == "$regex":
            flags = re.IGNORECASE if "i" in condition.get("$options", "") else 0
            expression = re.compile(expected, flags)
            if not any(expression.search(str(value)) for value in values):
                return False
        if operator == "$options":
            continue
    return True


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, condition in query.items():
        if key == "$and":
            if not all(_matches(document, clause) for clause in condition):
                return False
        elif key == "$or":
            if not any(_matches(document, clause) for clause in condition):
                return False
        elif not _condition_matches(_values(document, key), condition):
            return False
    return True


def _sort_value(document: dict[str, Any], path: str) -> tuple[int, Any]:
    values = _values(document, path)
    value = values[0] if values else None
    if isinstance(value, datetime):
        return (2, value.timestamp())
    if value is None:
        return (0, "")
    return (1, str(value))


class _Cursor:
    def __init__(self, collection: _Collection, documents: list[dict[str, Any]]) -> None:
        self.collection = collection
        self.documents = [copy.deepcopy(document) for document in documents]

    def sort(self, fields: list[tuple[str, int]]) -> _Cursor:
        self.collection.last_sort = list(fields)
        for field, direction in reversed(fields):
            self.documents.sort(
                key=lambda document: _sort_value(document, field),
                reverse=direction < 0,
            )
        return self

    def skip(self, amount: int) -> _Cursor:
        self.collection.last_skip = amount
        self.documents = self.documents[amount:]
        return self

    def limit(self, amount: int) -> _Cursor:
        self.collection.last_limit = amount
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


class _Collection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = copy.deepcopy(documents)
        self.read_operations: list[str] = []
        self.queries: list[dict[str, Any]] = []
        self.projections: list[dict[str, Any]] = []
        self.last_sort: list[tuple[str, int]] = []
        self.last_skip: int | None = None
        self.last_limit: int | None = None

    def count_documents(self, query: dict[str, Any]) -> int:
        self.read_operations.append("count_documents")
        self.queries.append(copy.deepcopy(query))
        return sum(_matches(document, query) for document in self.documents)

    def find(
        self,
        query: dict[str, Any],
        projection: dict[str, Any],
    ) -> _Cursor:
        self.read_operations.append("find")
        self.queries.append(copy.deepcopy(query))
        self.projections.append(copy.deepcopy(projection))
        return _Cursor(
            self,
            [document for document in self.documents if _matches(document, query)],
        )

    def distinct(self, field: str, query: dict[str, Any]) -> list[Any]:
        self.read_operations.append("distinct")
        self.queries.append(copy.deepcopy(query))
        values: list[Any] = []
        for document in self.documents:
            if not _matches(document, query):
                continue
            for value in _values(document, field):
                if value not in values:
                    values.append(copy.deepcopy(value))
        return values


class _Database:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.concepts = _Collection(documents)
        self.accesses: list[str] = []

    def __getitem__(self, name: str) -> _Collection:
        self.accesses.append(name)
        if name != "concepts":
            raise AssertionError(f"unexpected collection access: {name}")
        return self.concepts


def _concept(
    concept_id: str,
    source: str,
    *,
    updated_at: datetime,
    title: str | None = None,
    concept_type: str = "definicion",
    categories: list[str] | None = None,
    reference: Any = None,
    include_reference: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": concept_id,
        "source": source,
        "titulo": title or concept_id,
        "tipo": concept_type,
        "categorias": list(categories or []),
        "ultima_actualizacion": updated_at,
        "unrequested_large_field": "must not be requested by projection",
    }
    if include_reference:
        result["referencia"] = copy.deepcopy(reference)
    return result


def test_construction_is_side_effect_free_and_source_values_exclude_aliases() -> None:
    database = _Database([])
    source = Source(
        name="Exact Source",
        aliases=["Not a legacy value"],
        legacy={"source_strings": ["Historical Source", "Exact Source"]},
    )

    LegacyConceptRepository(database)

    assert database.accesses == []
    assert legacy_source_values(source) == ("Exact Source", "Historical Source")


def test_exact_matching_excludes_fuzzy_names_aliases_and_the_other_database() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source = Source(
        name="Álgebra Exacta",
        aliases=["Alias Legacy Looking"],
        legacy={"source_strings": ["Historical-Exact"]},
    )
    first = _Database(
        [
            _concept("main", "Álgebra Exacta", updated_at=now),
            _concept("historical", "Historical-Exact", updated_at=now),
            _concept("accentless", "Algebra Exacta", updated_at=now),
            _concept("alias", "Alias Legacy Looking", updated_at=now),
            _concept("whitespace", " Álgebra Exacta ", updated_at=now),
        ]
    )
    second = _Database([_concept("other-db", "Álgebra Exacta", updated_at=now)])
    first_snapshot = copy.deepcopy(first.concepts.documents)
    second_snapshot = copy.deepcopy(second.concepts.documents)

    first_page = LegacyConceptRepository(first).list(source)
    second_page = LegacyConceptRepository(second).list(source)

    assert {item.id for item in first_page.items} == {"main", "historical"}
    assert [item.id for item in second_page.items] == ["other-db"]
    assert first.concepts.documents == first_snapshot
    assert second.concepts.documents == second_snapshot


def test_server_side_count_projection_stable_pagination_and_page_limit() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    documents = [
        _concept(
            f"concept-{index}",
            "Paged Source",
            updated_at=start + timedelta(days=index),
        )
        for index in range(6)
    ]
    database = _Database(documents)
    repository = LegacyConceptRepository(database)
    source = Source(name="Paged Source")

    page = repository.list(source, page=2, page_size=2)
    limited = repository.list(source, page_size=MAX_LEGACY_PAGE_SIZE + 50)

    assert page.total == repository.count(source) == 6
    assert page.pages == 3
    assert [item.id for item in page.items] == ["concept-3", "concept-2"]
    assert page.exact_source_values == ("Paged Source",)
    assert database.concepts.last_sort == [
        ("ultima_actualizacion", -1),
        ("source", 1),
        ("id", 1),
    ]
    assert database.concepts.projections
    assert database.concepts.projections[0]["_id"] == 0
    assert "referencia" not in database.concepts.projections[0]
    assert "referencia.paginas" in database.concepts.projections[0]
    assert "unrequested_large_field" not in database.concepts.projections[0]
    assert limited.page_size == MAX_LEGACY_PAGE_SIZE
    assert database.concepts.last_skip == 0
    assert database.concepts.last_limit == MAX_LEGACY_PAGE_SIZE


def test_type_reference_and_literal_search_filters_are_bounded_and_escaped() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    database = _Database(
        [
            _concept(
                "literal",
                "Filters",
                updated_at=now,
                title="A literal [A].* title",
                concept_type="teorema",
                reference={"fuente": "Book"},
            ),
            _concept(
                "ordinary",
                "Filters",
                updated_at=now,
                title="A literal Ax title",
                concept_type="teorema",
                include_reference=False,
            ),
            _concept(
                "definition",
                "Filters",
                updated_at=now,
                concept_type="definicion",
                reference={"fuente": "Book"},
            ),
        ]
    )
    repository = LegacyConceptRepository(database)
    source = Source(name="Filters")

    filtered = repository.list(
        source,
        concept_type="teorema",
        has_reference=True,
        search="[A].*",
    )

    assert [item.id for item in filtered.items] == ["literal"]
    assert repository.count(source, concept_type="teorema", has_reference=False) == 1
    assert repository.list_types(source) == ("definicion", "teorema")
    search_clause = database.concepts.queries[1]["$and"][-1]["$or"]
    assert search_clause[0]["id"]["$regex"] == re.escape("[A].*")
    with pytest.raises(ValueError, match=str(MAX_LEGACY_SEARCH_LENGTH)):
        repository.list(source, search="x" * (MAX_LEGACY_SEARCH_LENGTH + 1))


def test_typed_projection_maps_reference_locators_without_modifying_document() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    database = _Database(
        [
            _concept(
                "mapped",
                "Mapped",
                updated_at=now,
                title="Mapped title",
                concept_type="proposicion",
                categories=["Álgebra", "Análisis"],
                reference={
                    "fuente": "Historical book",
                    "paginas": "10-12",
                    "capitulo": 3,
                    "seccion": "2.1",
                },
            )
        ]
    )
    before = copy.deepcopy(database.concepts.documents)

    item = LegacyConceptRepository(database).list(Source(name="Mapped")).items[0]

    assert item.id == "mapped"
    assert item.title == "Mapped title"
    assert item.type == "proposicion"
    assert item.categories == ("Álgebra", "Análisis")
    assert item.has_reference is True
    assert (item.pages, item.chapter, item.section) == ("10-12", "3", "2.1")
    assert item.updated_at == now
    assert item.source == "Mapped"
    assert database.concepts.documents == before
    assert set(database.concepts.read_operations) <= {"find", "count_documents", "distinct"}


@pytest.mark.parametrize(
    ("page", "page_size"),
    [(0, 10), (1, 0), (True, 10), (1, False)],
)
def test_invalid_pagination_fails_before_a_query(page: Any, page_size: Any) -> None:
    database = _Database([])
    repository = LegacyConceptRepository(database)

    with pytest.raises(ValueError, match="positive integer"):
        repository.list(Source(name="Safe"), page=page, page_size=page_size)

    assert database.accesses == []

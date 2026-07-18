"""Contract tests for optional managed Source links on legacy concepts."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest
from pydantic import ValidationError

from editor.db.concept_repository import concept_exists
from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.db.concept_repository import semantic_duplicate_exists
from editor.helpers.concept_builders import build_concept_metadata
from schemas.schemas import ConceptoBase

SOURCE_ID = "src_123e4567-e89b-42d3-a456-426614174000"


class _Collection:
    def __init__(self, *, fail_insert: bool = False) -> None:
        self.fail_insert = fail_insert
        self.inserted: list[dict] = []
        self.deleted: list[dict] = []
        self.count_queries: list[tuple[dict, int]] = []
        self.find_one_queries: list[dict] = []

    def insert_one(self, document: dict) -> None:
        if self.fail_insert:
            raise RuntimeError("fixture insert failure")
        self.inserted.append(deepcopy(document))

    def delete_one(self, query: dict) -> None:
        self.deleted.append(deepcopy(query))

    def count_documents(self, query: dict, *, limit: int = 0) -> int:
        self.count_queries.append((deepcopy(query), limit))
        return 1

    def find_one(self, query: dict) -> dict:
        self.find_one_queries.append(deepcopy(query))
        return {"id": "concept", "source": "Python"}


class _Database:
    def __init__(self, *, fail_latex_insert: bool = False) -> None:
        self.concepts = _Collection()
        self.latex_documents = _Collection(fail_insert=fail_latex_insert)


def _concept(**changes: object) -> ConceptoBase:
    payload: dict[str, object] = {
        "id": "definition:contract",
        "tipo": "definicion",
        "contenido_latex": "x = x",
        "categorias": ["Algebra"],
        "source": "Python",
    }
    payload.update(changes)
    return ConceptoBase(**payload)


def test_legacy_concept_remains_valid_without_source_id() -> None:
    concept = _concept()

    assert concept.source == "Python"
    assert concept.source_id is None


def test_linked_concept_accepts_and_serializes_source_id() -> None:
    concept = _concept(source_id=SOURCE_ID)

    assert concept.source == "Python"
    assert concept.source_id == SOURCE_ID
    assert concept.model_dump(mode="python")["source_id"] == SOURCE_ID
    assert build_concept_metadata(concept)["source_id"] == SOURCE_ID


def test_source_remains_required_when_source_id_is_present() -> None:
    with pytest.raises(ValidationError, match="source"):
        _concept(source_id=SOURCE_ID, source=None)


def test_none_source_id_is_omitted_from_concept_metadata() -> None:
    concept = _concept(source_id=None)

    assert concept.source_id is None
    assert "source_id" not in build_concept_metadata(concept)


def test_linked_atomic_insert_persists_source_id_in_both_documents() -> None:
    database = _Database()
    concept = _concept(source_id=SOURCE_ID)
    metadata = build_concept_metadata(concept)
    now = datetime(2026, 7, 18, 12, 0, 0)

    insert_concept_with_latex_atomic(
        database,
        concept.id,
        concept.source,
        metadata,
        concept.contenido_latex,
        now,
    )

    assert database.concepts.inserted[0]["source"] == "Python"
    assert database.concepts.inserted[0]["source_id"] == SOURCE_ID
    assert database.latex_documents.inserted[0]["source"] == "Python"
    assert database.latex_documents.inserted[0]["source_id"] == SOURCE_ID


def test_legacy_atomic_insert_omits_null_source_id() -> None:
    database = _Database()
    concept = _concept()

    insert_concept_with_latex_atomic(
        database,
        concept.id,
        concept.source,
        build_concept_metadata(concept),
        concept.contenido_latex,
        datetime(2026, 7, 18, 12, 0, 0),
    )

    assert "source_id" not in database.concepts.inserted[0]
    assert "source_id" not in database.latex_documents.inserted[0]


def test_identity_queries_and_rollback_remain_id_plus_source() -> None:
    database = _Database(fail_latex_insert=True)
    concept = _concept(source_id=SOURCE_ID)

    assert concept_exists(database, concept.id, concept.source)
    assert semantic_duplicate_exists(database, "Contract", concept.tipo, concept.source)

    with pytest.raises(RuntimeError, match="fixture insert failure"):
        insert_concept_with_latex_atomic(
            database,
            concept.id,
            concept.source,
            build_concept_metadata(concept),
            concept.contenido_latex,
            datetime(2026, 7, 18, 12, 0, 0),
        )

    identity = {"id": concept.id, "source": "Python"}
    assert database.concepts.count_queries == [(identity, 1)]
    duplicate_query = database.concepts.find_one_queries[0]
    assert duplicate_query["source"] == "Python"
    assert "source_id" not in duplicate_query
    assert database.concepts.deleted == [identity]

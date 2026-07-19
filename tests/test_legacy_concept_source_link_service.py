"""Contract for explicitly linking one legacy concept to a managed Source."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import pytest

from editor.db.concept_source_link_service import ConceptSourceLinkStatus
from editor.db.concept_source_link_service import link_concept_to_existing_managed_source
from mathmongo.source_catalog.models import Source

CONCEPT_ID = "grupo"
LEGACY_SOURCE = "Nombre histórico"
TARGET_SOURCE_ID = "src_123e4567-e89b-42d3-a456-426614174000"
OTHER_SOURCE_ID = "src_223e4567-e89b-42d3-a456-426614174000"
_MISSING = object()


@dataclass(frozen=True)
class _UpdateResult:
    matched_count: int
    modified_count: int


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        actual = document.get(key, _MISSING)
        if isinstance(expected, dict) and set(expected) == {"$exists"}:
            if (actual is not _MISSING) is not bool(expected["$exists"]):
                return False
        elif actual is _MISSING or actual != expected:
            return False
    return True


class _Collection:
    def __init__(
        self,
        documents: list[dict[str, Any]],
        *,
        fail_update_calls: set[int] | None = None,
        miss_update_calls: set[int] | None = None,
        zero_modified_calls: set[int] | None = None,
        skip_apply_calls: set[int] | None = None,
    ) -> None:
        self.documents = deepcopy(documents)
        self.fail_update_calls = set(fail_update_calls or ())
        self.miss_update_calls = set(miss_update_calls or ())
        self.zero_modified_calls = set(zero_modified_calls or ())
        self.skip_apply_calls = set(skip_apply_calls or ())
        self.find_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.insert_calls: list[str] = []

    def find_one(
        self,
        query: dict[str, Any],
        *,
        session: object | None = None,
    ) -> dict[str, Any] | None:
        self.find_calls.append({"query": deepcopy(query), "session": session})
        return next(
            (deepcopy(document) for document in self.documents if _matches(document, query)),
            None,
        )

    def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        *,
        upsert: bool = False,
        session: object | None = None,
    ) -> _UpdateResult:
        call_number = len(self.update_calls) + 1
        self.update_calls.append(
            {
                "query": deepcopy(query),
                "update": deepcopy(update),
                "upsert": upsert,
                "session": session,
            }
        )
        if call_number in self.fail_update_calls:
            raise RuntimeError("fixture update failure")
        if call_number in self.miss_update_calls:
            return _UpdateResult(matched_count=0, modified_count=0)

        for index, document in enumerate(self.documents):
            if not _matches(document, query):
                continue
            before = deepcopy(document)
            updated = deepcopy(document)
            if call_number not in self.skip_apply_calls:
                updated.update(deepcopy(update.get("$set", {})))
                for key in update.get("$unset", {}):
                    updated.pop(key, None)
                self.documents[index] = updated
            modified = int(updated != before)
            if call_number in self.zero_modified_calls:
                modified = 0
            return _UpdateResult(matched_count=1, modified_count=modified)
        return _UpdateResult(matched_count=0, modified_count=0)


class _SourceCollection:
    WRITE_METHODS = {
        "insert_one",
        "insert_many",
        "update_one",
        "update_many",
        "replace_one",
        "delete_one",
        "delete_many",
        "bulk_write",
        "create_index",
    }

    def __init__(self, sources: list[dict[str, Any]]) -> None:
        self.documents = deepcopy(sources)
        self.find_calls: list[dict[str, Any]] = []
        self.write_calls: list[str] = []

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        self.find_calls.append(deepcopy(query))
        return next(
            (deepcopy(document) for document in self.documents if _matches(document, query)),
            None,
        )

    def __getattr__(self, operation: str):
        if operation not in self.WRITE_METHODS:
            raise AttributeError(operation)

        def forbidden(*_args: object, **_kwargs: object):
            self.write_calls.append(operation)
            raise AssertionError(f"sources.{operation} must never be called")

        return forbidden


class _DependencyCollection:
    WRITE_METHODS = _SourceCollection.WRITE_METHODS

    def __init__(self, name: str) -> None:
        self.name = name
        self.write_calls: list[str] = []

    def __getattr__(self, operation: str):
        if operation not in self.WRITE_METHODS:
            raise AttributeError(operation)

        def forbidden(*_args: object, **_kwargs: object):
            self.write_calls.append(operation)
            raise AssertionError(f"{self.name}.{operation} must never be called")

        return forbidden


class _TransactionSession:
    def __init__(self, database: _Database) -> None:
        self.database = database

    def __enter__(self) -> _TransactionSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def with_transaction(self, callback):
        concept_snapshot = deepcopy(self.database.concepts.documents)
        latex_snapshot = deepcopy(self.database.latex_documents.documents)
        try:
            return callback(self)
        except Exception:
            self.database.concepts.documents = concept_snapshot
            self.database.latex_documents.documents = latex_snapshot
            raise


class _TransactionClient:
    supports_transactions = True

    def __init__(self, database: _Database) -> None:
        self.database = database
        self.start_session_calls = 0

    def start_session(self) -> _TransactionSession:
        self.start_session_calls += 1
        return _TransactionSession(self.database)


class _Database:
    def __init__(
        self,
        concept: dict[str, Any] | None,
        latex: dict[str, Any] | None,
        *,
        sources: list[dict[str, Any]] | None = None,
        concept_options: dict[str, Any] | None = None,
        latex_options: dict[str, Any] | None = None,
        transactional: bool = False,
    ) -> None:
        self.concepts = _Collection(
            [] if concept is None else [concept],
            **(concept_options or {}),
        )
        self.latex_documents = _Collection(
            [] if latex is None else [latex],
            **(latex_options or {}),
        )
        self.sources = _SourceCollection(sources or [_source_document()])
        self.relations = _DependencyCollection("relations")
        self.knowledge_graph_maps = _DependencyCollection("knowledge_graph_maps")
        self.media_assets = _DependencyCollection("media_assets")
        self.concept_evidence_links = _DependencyCollection("concept_evidence_links")
        self.client = _TransactionClient(self) if transactional else None

    def __getitem__(self, name: str):
        return getattr(self, name)


def _source_document(
    *,
    source_id: str = TARGET_SOURCE_ID,
    name: str = "Nombre administrado actual",
    archived: bool = False,
) -> dict[str, Any]:
    source = Source(source_id=source_id, name=name)
    if archived:
        source = source.archived()
    return source.model_dump(mode="python")


def _documents(*, source_id: str | None | object = _MISSING):
    concept: dict[str, Any] = {
        "_id": "concept-object-id",
        "id": CONCEPT_ID,
        "source": LEGACY_SOURCE,
        "tipo": "definicion",
        "contenido_latex": "unchanged latex",
        "titulo": "Grupo",
    }
    latex: dict[str, Any] = {
        "_id": "latex-object-id",
        "id": CONCEPT_ID,
        "source": LEGACY_SOURCE,
        "contenido_latex": "unchanged latex",
    }
    if source_id is not _MISSING:
        concept["source_id"] = source_id
        latex["source_id"] = source_id
    return concept, latex


def _link(database: _Database, *, expected_source_id: str | None = None):
    return link_concept_to_existing_managed_source(
        database,
        concept_id=CONCEPT_ID,
        source=LEGACY_SOURCE,
        expected_source_id=expected_source_id,
        target_source_id=TARGET_SOURCE_ID,
    )


def _assert_no_out_of_scope_writes(database: _Database) -> None:
    assert database.sources.write_calls == []
    assert database.relations.write_calls == []
    assert database.knowledge_graph_maps.write_calls == []
    assert database.media_assets.write_calls == []
    assert database.concept_evidence_links.write_calls == []
    for collection in (database.concepts, database.latex_documents):
        assert collection.delete_calls == []
        assert collection.insert_calls == []
        assert all(call["upsert"] is False for call in collection.update_calls)


def test_links_legacy_pair_by_adding_only_source_id_and_preserving_identity() -> None:
    concept, latex = _documents()
    original_concept = deepcopy(concept)
    original_latex = deepcopy(latex)
    database = _Database(concept, latex)

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.SUCCESS
    assert database.concepts.documents[0] == {**original_concept, "source_id": TARGET_SOURCE_ID}
    assert database.latex_documents.documents[0] == {
        **original_latex,
        "source_id": TARGET_SOURCE_ID,
    }
    assert f"{database.concepts.documents[0]['id']}@{database.concepts.documents[0]['source']}" == (
        f"{CONCEPT_ID}@{LEGACY_SOURCE}"
    )
    _assert_no_out_of_scope_writes(database)


def test_never_replaces_legacy_source_snapshot_with_managed_source_name() -> None:
    concept, latex = _documents()
    database = _Database(concept, latex)

    result = _link(database)

    assert result.success
    assert database.concepts.documents[0]["source"] == LEGACY_SOURCE
    assert database.latex_documents.documents[0]["source"] == LEGACY_SOURCE
    assert database.sources.documents[0]["name"] != LEGACY_SOURCE


def test_missing_target_returns_not_found_without_writes() -> None:
    concept, latex = _documents()
    database = _Database(concept, latex, sources=[])
    database.sources.documents = []

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.TARGET_NOT_FOUND
    assert database.concepts.documents == [concept]
    assert database.latex_documents.documents == [latex]
    assert database.sources.find_calls == [{"source_id": TARGET_SOURCE_ID}]
    _assert_no_out_of_scope_writes(database)


def test_archived_target_returns_inactive_without_writes() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        sources=[_source_document(archived=True)],
    )

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.TARGET_INACTIVE
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []
    _assert_no_out_of_scope_writes(database)


def test_missing_concept_returns_structured_result() -> None:
    _concept, latex = _documents()
    database = _Database(None, latex)

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.CONCEPT_NOT_FOUND
    assert database.latex_documents.update_calls == []


def test_missing_latex_never_modifies_concept() -> None:
    concept, _latex = _documents()
    database = _Database(concept, None)

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.LATEX_NOT_FOUND
    assert database.concepts.documents == [concept]
    assert database.concepts.update_calls == []


def test_same_link_in_both_documents_is_idempotent_without_repeated_writes() -> None:
    concept, latex = _documents(source_id=TARGET_SOURCE_ID)
    database = _Database(concept, latex)

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.ALREADY_LINKED
    assert result.success
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []


def test_existing_different_link_is_a_conflict_without_writes() -> None:
    concept, latex = _documents(source_id=OTHER_SOURCE_ID)
    database = _Database(concept, latex)

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.ALREADY_LINKED_TO_DIFFERENT_SOURCE
    assert not result.success
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []


@pytest.mark.parametrize(
    ("concept_source_id", "latex_source_id"),
    [
        (_MISSING, OTHER_SOURCE_ID),
        (OTHER_SOURCE_ID, _MISSING),
        (OTHER_SOURCE_ID, TARGET_SOURCE_ID),
        (None, None),
    ],
)
def test_mismatched_or_explicit_null_link_state_never_writes(
    concept_source_id: str | None | object,
    latex_source_id: str | None | object,
) -> None:
    concept, _ = _documents(source_id=concept_source_id)
    _, latex = _documents(source_id=latex_source_id)
    database = _Database(concept, latex)

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.LINK_MISMATCH
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []


def test_compare_and_set_miss_returns_stale_without_claiming_success() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        concept_options={"miss_update_calls": {1}},
    )

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.STALE_IDENTITY
    assert not result.success
    assert database.latex_documents.update_calls == []


def test_second_update_failure_compensates_only_the_added_source_id() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        latex_options={"fail_update_calls": {1}},
    )

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.FAILED_COMPENSATED
    assert database.concepts.documents == [concept]
    assert database.latex_documents.documents == [latex]
    compensation = database.concepts.update_calls[1]
    assert compensation["update"] == {"$unset": {"source_id": ""}}
    assert compensation["query"] == {**concept, "source_id": TARGET_SOURCE_ID}
    _assert_no_out_of_scope_writes(database)


def test_concurrent_change_preventing_compensation_requires_recovery() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        concept_options={"miss_update_calls": {2}},
        latex_options={"fail_update_calls": {1}},
    )

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.PARTIAL_RECOVERY_REQUIRED
    assert not result.success
    assert database.concepts.documents[0]["source_id"] == TARGET_SOURCE_ID


def test_modified_count_zero_is_success_only_after_verified_final_state() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        concept_options={"zero_modified_calls": {1}},
        latex_options={"zero_modified_calls": {1}},
    )

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.SUCCESS
    assert database.concepts.documents[0]["source_id"] == TARGET_SOURCE_ID
    assert database.latex_documents.documents[0]["source_id"] == TARGET_SOURCE_ID


def test_unapplied_modified_count_zero_never_claims_success() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        concept_options={"zero_modified_calls": {1}, "skip_apply_calls": {1}},
    )

    result = _link(database)

    assert result.status is not ConceptSourceLinkStatus.SUCCESS
    assert not result.success


def test_transactional_success_updates_both_documents_in_one_session() -> None:
    concept, latex = _documents()
    database = _Database(concept, latex, transactional=True)

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.SUCCESS
    assert result.transaction_used
    assert database.client.start_session_calls == 1
    assert all(call["session"] is not None for call in database.concepts.update_calls)
    assert all(call["session"] is not None for call in database.latex_documents.update_calls)


def test_transaction_rolls_back_if_latex_update_fails() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        latex_options={"fail_update_calls": {1}},
        transactional=True,
    )

    result = _link(database)

    assert result.status is ConceptSourceLinkStatus.FAILED_COMPENSATED
    assert result.transaction_used
    assert database.concepts.documents == [concept]
    assert database.latex_documents.documents == [latex]


def test_operation_is_isolated_to_the_explicit_active_database() -> None:
    concept_a, latex_a = _documents()
    concept_b, latex_b = _documents()
    database_a = _Database(concept_a, latex_a)
    database_b = _Database(concept_b, latex_b)

    result = _link(database_a)

    assert result.success
    assert database_b.sources.find_calls == []
    assert database_b.concepts.find_calls == []
    assert database_b.latex_documents.find_calls == []
    assert database_b.concepts.documents == [concept_b]
    assert database_b.latex_documents.documents == [latex_b]

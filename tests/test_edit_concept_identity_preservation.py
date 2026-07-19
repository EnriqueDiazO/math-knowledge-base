"""Identity-preserving Edit Concept update contract."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from editor.db.concept_edit_service import ConceptEditStatus
from editor.db.concept_edit_service import update_concept_fields_preserving_identity

CONCEPT_ID = "definition:identity-contract"
SOURCE = "Historical snapshot"
SOURCE_ID = "src_123e4567-e89b-42d3-a456-426614174000"
NOW = datetime(2026, 7, 18, 12, 0, 0)
EARLIER = datetime(2026, 7, 17, 12, 0, 0)
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
    ) -> None:
        self.documents = deepcopy(documents)
        self.fail_update_calls = set(fail_update_calls or ())
        self.miss_update_calls = set(miss_update_calls or ())
        self.find_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

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
            updated.update(deepcopy(update.get("$set", {})))
            for key in update.get("$unset", {}):
                updated.pop(key, None)
            self.documents[index] = updated
            return _UpdateResult(
                matched_count=1,
                modified_count=int(updated != before),
            )
        return _UpdateResult(matched_count=0, modified_count=0)


class _ForbiddenCollection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []

    def __getattr__(self, operation: str):
        self.calls.append(operation)
        raise AssertionError(f"Edit Concept must not access {self.name}.{operation}")


class _TransactionSession:
    def __init__(self, database: _Database) -> None:
        self.database = database
        self.transaction_calls = 0

    def __enter__(self) -> _TransactionSession:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def with_transaction(self, callback):
        self.transaction_calls += 1
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
        self.sessions: list[_TransactionSession] = []

    def start_session(self) -> _TransactionSession:
        self.start_session_calls += 1
        session = _TransactionSession(self.database)
        self.sessions.append(session)
        return session


class _DynamicAttributeClient:
    """Match PyMongo's unknown-attribute behavior without opening a connection."""

    topology_description = SimpleNamespace(topology_type_name="Single")

    def __init__(self) -> None:
        self.start_session_calls = 0

    def start_session(self):
        self.start_session_calls += 1
        raise AssertionError("A single-server topology must use the fallback")

    def __getattr__(self, name: str):
        if name == "supports_transactions":
            return _DatabaseTruthValueTrap()
        raise AttributeError(name)


class _DatabaseTruthValueTrap:
    def __bool__(self):
        raise NotImplementedError("database truth-value testing is undefined")


class _Database:
    def __init__(
        self,
        concept: dict[str, Any] | None,
        latex: dict[str, Any] | None,
        *,
        concept_fail_updates: set[int] | None = None,
        concept_miss_updates: set[int] | None = None,
        latex_fail_updates: set[int] | None = None,
        latex_miss_updates: set[int] | None = None,
        transactional: bool = False,
    ) -> None:
        self.concepts = _Collection(
            [] if concept is None else [concept],
            fail_update_calls=concept_fail_updates,
            miss_update_calls=concept_miss_updates,
        )
        self.latex_documents = _Collection(
            [] if latex is None else [latex],
            fail_update_calls=latex_fail_updates,
            miss_update_calls=latex_miss_updates,
        )
        self.sources = _ForbiddenCollection("sources")
        self.relations = _ForbiddenCollection("relations")
        self.knowledge_graph_maps = _ForbiddenCollection("knowledge_graph_maps")
        self.media_assets = _ForbiddenCollection("media_assets")
        self.concept_evidence_links = _ForbiddenCollection("concept_evidence_links")
        self.client = _TransactionClient(self) if transactional else None


def _documents(*, source_id: str | None | object = _MISSING):
    concept: dict[str, Any] = {
        "_id": "concept-object-id",
        "id": CONCEPT_ID,
        "source": SOURCE,
        "tipo": "definicion",
        "titulo": "Before",
        "contenido_latex": "before latex",
        "ultima_actualizacion": EARLIER,
    }
    latex: dict[str, Any] = {
        "_id": "latex-object-id",
        "id": CONCEPT_ID,
        "source": SOURCE,
        "contenido_latex": "before latex",
        "ultima_actualizacion": EARLIER,
    }
    if source_id is not _MISSING:
        concept["source_id"] = source_id
        latex["source_id"] = source_id
    return concept, latex


def _update(database: _Database, *, expected_source_id: str | None = None, **kwargs):
    return update_concept_fields_preserving_identity(
        database,
        concept_id=CONCEPT_ID,
        source=SOURCE,
        expected_source_id=expected_source_id,
        changes={"titulo": "After"},
        contenido_latex="after latex",
        now=NOW,
        **kwargs,
    )


def _edit_concept_branch() -> str:
    source = (
        Path(__file__).resolve().parents[1] / "editor" / "editor_streamlit.py"
    ).read_text(encoding="utf-8")
    start = source.index('elif page == "✏️ Edit Concept":')
    end = source.index('\nelif page == "📚 Browse Concepts":', start)
    return source[start:end]


def _ordinary_save_block() -> str:
    branch = _edit_concept_branch()
    start = branch.index('if st.button("💾 Update Concept"')
    end = branch.index("# PDF Generation Button for Edit Concept", start)
    return branch[start:end]


def test_legacy_update_preserves_identity_and_absent_source_id() -> None:
    concept, latex = _documents()
    database = _Database(concept, latex)

    result = _update(database)

    assert result.success is True
    assert result.status is ConceptEditStatus.SUCCESS
    assert database.concepts.documents[0]["id"] == CONCEPT_ID
    assert database.concepts.documents[0]["source"] == SOURCE
    assert "source_id" not in database.concepts.documents[0]
    assert database.latex_documents.documents[0]["id"] == CONCEPT_ID
    assert database.latex_documents.documents[0]["source"] == SOURCE
    assert "source_id" not in database.latex_documents.documents[0]
    assert database.concepts.documents[0]["titulo"] == "After"
    assert database.latex_documents.documents[0]["contenido_latex"] == "after latex"


def test_linked_update_preserves_the_same_link_in_both_documents() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex)

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.SUCCESS
    assert database.concepts.documents[0]["source_id"] == SOURCE_ID
    assert database.latex_documents.documents[0]["source_id"] == SOURCE_ID
    assert database.concepts.documents[0]["source"] == SOURCE
    assert database.latex_documents.documents[0]["source"] == SOURCE


@pytest.mark.parametrize("field", ["id", "source", "source_id"])
def test_identity_fields_are_rejected_from_changes(field: str) -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex)

    result = update_concept_fields_preserving_identity(
        database,
        concept_id=CONCEPT_ID,
        source=SOURCE,
        expected_source_id=SOURCE_ID,
        changes={field: "forbidden"},
        contenido_latex="after latex",
        now=NOW,
    )

    assert result.success is False
    assert result.status is ConceptEditStatus.STALE_IDENTITY
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []


def test_edit_ui_has_read_only_identity_context_and_link_status() -> None:
    branch = _edit_concept_branch()

    assert 'st.text_input("ID",' not in branch
    assert 'st.text_input("Source",' not in branch
    assert "ID (immutable)" in branch
    assert "Source snapshot (immutable)" in branch
    assert "Managed Source ID" in branch
    assert "Legacy concept — not linked to a managed Source." in branch


def test_ordinary_save_payload_uses_only_original_identity() -> None:
    block = _ordinary_save_block()

    assert "update_concept_fields_preserving_identity(" in block
    assert "concept_id=original_concept_id" in block
    assert "source=original_source" in block
    assert "expected_source_id=original_source_id" in block
    assert "changes=concept_changes" in block
    assert '"id":' not in block
    assert '"source":' not in block
    assert '"source_id":' not in block
    assert "db.concepts.update_one(" not in block
    assert "db.latex_documents.update_one(" not in block


@pytest.mark.parametrize("catalog_state", ["renamed", "archived", "missing"])
def test_catalog_state_does_not_change_the_stored_link_or_snapshot(
    catalog_state: str,
) -> None:
    del catalog_state
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex)

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.SUCCESS
    assert database.concepts.documents[0]["source"] == SOURCE
    assert database.concepts.documents[0]["source_id"] == SOURCE_ID
    assert database.latex_documents.documents[0]["source"] == SOURCE
    assert database.latex_documents.documents[0]["source_id"] == SOURCE_ID
    assert database.sources.calls == []


def test_missing_concept_is_reported_without_any_write() -> None:
    _concept, latex = _documents()
    database = _Database(None, latex)

    result = _update(database)

    assert result.status is ConceptEditStatus.CONCEPT_NOT_FOUND
    assert result.success is False
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []


def test_missing_latex_is_reported_before_updating_the_concept() -> None:
    concept, _latex = _documents()
    database = _Database(concept, None)

    result = _update(database)

    assert result.status is ConceptEditStatus.LATEX_NOT_FOUND
    assert result.success is False
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []


def test_concept_compare_and_set_miss_prevents_latex_write_and_success() -> None:
    concept, latex = _documents()
    database = _Database(concept, latex, concept_miss_updates={1})

    result = _update(database)

    assert result.status is ConceptEditStatus.STALE_IDENTITY
    assert result.success is False
    assert result.concept_matched_count == 0
    assert database.latex_documents.update_calls == []


@pytest.mark.parametrize("latex_failure", ["raise", "miss"])
def test_second_update_failure_is_compensated_without_false_success(
    latex_failure: str,
) -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        latex_fail_updates={1} if latex_failure == "raise" else None,
        latex_miss_updates={1} if latex_failure == "miss" else None,
    )

    result = _update(database)

    assert result.status is ConceptEditStatus.FAILED_COMPENSATED
    assert result.success is False
    assert database.concepts.documents == [concept]
    assert database.latex_documents.documents == [latex]
    assert len(database.concepts.update_calls) == 2
    assert all(call["upsert"] is False for call in database.concepts.update_calls)


def test_failed_compensation_reports_partial_recovery_required() -> None:
    concept, latex = _documents()
    database = _Database(
        concept,
        latex,
        concept_miss_updates={2},
        latex_fail_updates={1},
    )

    result = _update(database)

    assert result.status is ConceptEditStatus.PARTIAL_RECOVERY_REQUIRED
    assert result.success is False
    assert database.concepts.documents[0]["titulo"] == "After"
    assert database.latex_documents.documents == [latex]


def test_transaction_backend_rolls_back_a_second_update_failure() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(
        concept,
        latex,
        latex_fail_updates={1},
        transactional=True,
    )

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.FAILED_COMPENSATED
    assert database.concepts.documents == [concept]
    assert database.latex_documents.documents == [latex]
    assert database.client is not None
    assert database.client.start_session_calls == 1
    assert database.client.sessions[0].transaction_calls == 1


def test_transaction_backend_commits_both_identity_preserving_updates() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex, transactional=True)

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.SUCCESS
    assert result.transaction_used is True
    assert result.concept_matched_count == 1
    assert result.latex_matched_count == 1
    assert database.concepts.documents[0]["source_id"] == SOURCE_ID
    assert database.latex_documents.documents[0]["source_id"] == SOURCE_ID
    assert database.client is not None
    assert database.client.start_session_calls == 1


def test_pymongo_dynamic_attribute_does_not_impersonate_transaction_marker() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex)
    client = _DynamicAttributeClient()
    database.client = client

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.SUCCESS
    assert result.transaction_used is False
    assert client.start_session_calls == 0
    assert database.concepts.documents[0]["source_id"] == SOURCE_ID
    assert database.latex_documents.documents[0]["source_id"] == SOURCE_ID


def test_no_sources_or_dependent_collections_are_written() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex)

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.SUCCESS
    for collection in (
        database.sources,
        database.relations,
        database.knowledge_graph_maps,
        database.media_assets,
        database.concept_evidence_links,
    ):
        assert collection.calls == []


def test_compare_and_set_filters_keep_the_original_historical_identity() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex)

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.SUCCESS
    concept_query = database.concepts.update_calls[0]["query"]
    latex_query = database.latex_documents.update_calls[0]["query"]
    assert concept_query["id"] == CONCEPT_ID
    assert concept_query["source"] == SOURCE
    assert concept_query["source_id"] == SOURCE_ID
    assert latex_query["id"] == CONCEPT_ID
    assert latex_query["source"] == SOURCE
    assert latex_query["source_id"] == SOURCE_ID
    assert all(call["upsert"] is False for call in database.concepts.update_calls)
    assert all(call["upsert"] is False for call in database.latex_documents.update_calls)


def test_source_id_mismatch_is_stale_and_never_reconstructed_by_name() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    database = _Database(concept, latex)

    result = _update(database, expected_source_id="src_different")

    assert result.status is ConceptEditStatus.STALE_IDENTITY
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []
    assert database.sources.calls == []


def test_mismatched_latex_link_is_stale_before_any_write() -> None:
    concept, latex = _documents(source_id=SOURCE_ID)
    latex["source_id"] = "src_different"
    database = _Database(concept, latex)

    result = _update(database, expected_source_id=SOURCE_ID)

    assert result.status is ConceptEditStatus.STALE_IDENTITY
    assert database.concepts.update_calls == []
    assert database.latex_documents.update_calls == []


def test_matched_but_unmodified_documents_still_count_as_success() -> None:
    concept, latex = _documents()
    concept.update({"titulo": "After", "contenido_latex": "after latex"})
    concept["ultima_actualizacion"] = NOW
    latex["contenido_latex"] = "after latex"
    latex["ultima_actualizacion"] = NOW
    database = _Database(concept, latex)

    result = _update(database)

    assert result.status is ConceptEditStatus.SUCCESS
    assert result.concept_matched_count == 1
    assert result.concept_modified_count == 0
    assert result.latex_matched_count == 1
    assert result.latex_modified_count == 0


def test_selection_and_success_rerun_reload_the_original_identity() -> None:
    branch = _edit_concept_branch()

    assert "selected_concept_key = (" in branch
    assert 'str(selected_concept["id"])' in branch
    assert 'str(selected_concept["source"])' in branch
    assert "st.session_state.edit_id =" not in branch
    assert "st.session_state.edit_source =" not in branch
    assert "st.session_state.pop(legacy_last_selected_key, None)" in branch
    assert "st.rerun()" in _ordinary_save_block()


def test_media_manager_receives_only_the_original_identity() -> None:
    branch = _edit_concept_branch()
    manager_start = branch.index("concept_media_assets = _render_concept_media_manager(")
    manager_block = branch[manager_start : manager_start + 260]

    assert "original_concept_id" in manager_block
    assert "original_source" in manager_block
    assert "edit_id" not in manager_block
    assert "edit_source" not in manager_block

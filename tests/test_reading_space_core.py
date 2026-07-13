"""Focused models, repositories, indexes, and service tests for Reading Space S3."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import copy
import hashlib
import socket
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from bson import BSON
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from mathmongo.reading_space.indexes import READING_SPACE_INDEXES
from mathmongo.reading_space.indexes import ReadingIndexState
from mathmongo.reading_space.indexes import ReadingSpaceIndexManager
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.reading_space.models import ReadingDocumentFilters
from mathmongo.reading_space.models import ReadingSort
from mathmongo.reading_space.models import ReadingStatus
from mathmongo.reading_space.repository import ReadableDocumentItem
from mathmongo.reading_space.repository import ReadableDocumentPage
from mathmongo.reading_space.repository import ReadableDocumentRepository
from mathmongo.reading_space.repository import ReadingStateRepository
from mathmongo.reading_space.repository import SourceSummaryCounts
from mathmongo.reading_space.service import ReadingOperationStatus
from mathmongo.reading_space.service import ReadingSpaceService
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import PdfVersion
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.service import DocumentIntegrityInspection
from mathmongo.source_documents.service import DocumentPdfPayload

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def _value(document: dict[str, Any], field: str) -> Any:
    current: Any = document
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for field, expected in query.items():
        observed = _value(document, field)
        if isinstance(expected, dict) and "$ne" in expected:
            if observed == expected["$ne"]:
                return False
        elif observed != expected:
            return False
    return True


class _Cursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = [copy.deepcopy(item) for item in documents]

    def sort(self, fields: list[tuple[str, int]]):
        for field, direction in reversed(fields):
            self.documents.sort(
                key=lambda item: (_value(item, field) is not None, _value(item, field)),
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
    def __init__(self, name: str) -> None:
        self.name = name
        self.documents: list[dict[str, Any]] = []
        self.indexes: list[dict[str, Any]] = [{"name": "_id_", "key": {"_id": 1}, "v": 2}]
        self.aggregate_results: list[list[dict[str, Any]]] = []
        self.aggregate_calls: list[list[dict[str, Any]]] = []

    def find_one(self, query: dict[str, Any]):
        return next(
            (copy.deepcopy(item) for item in self.documents if _matches(item, query)),
            None,
        )

    def find(self, query: dict[str, Any]):
        return _Cursor([item for item in self.documents if _matches(item, query)])

    def count_documents(self, query: dict[str, Any]) -> int:
        return sum(_matches(item, query) for item in self.documents)

    def _check_unique(self, candidate: dict[str, Any], *, ignored: int | None = None) -> None:
        if self.name != "document_reading_state":
            return
        for index, existing in enumerate(self.documents):
            if index == ignored:
                continue
            if existing.get("reading_state_id") == candidate.get("reading_state_id"):
                raise DuplicateKeyError("duplicate reading_state_id")
            if existing.get("user_scope") == candidate.get("user_scope") and existing.get(
                "document_id"
            ) == candidate.get("document_id"):
                raise DuplicateKeyError("duplicate user/document")

    def find_one_and_update(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        *,
        upsert: bool,
        return_document: Any,
    ):
        del return_document
        index = next(
            (i for i, item in enumerate(self.documents) if _matches(item, query)),
            None,
        )
        if index is None:
            if not upsert:
                return None
            candidate = copy.deepcopy(update.get("$setOnInsert", {}))
            candidate.update(copy.deepcopy(update.get("$set", {})))
            for field, amount in update.get("$inc", {}).items():
                candidate[field] = candidate.get(field, 0) + amount
            self._check_unique(candidate)
            self.documents.append(candidate)
            return copy.deepcopy(candidate)
        candidate = copy.deepcopy(self.documents[index])
        candidate.update(copy.deepcopy(update.get("$set", {})))
        for field, amount in update.get("$inc", {}).items():
            candidate[field] = candidate.get(field, 0) + amount
        self._check_unique(candidate, ignored=index)
        self.documents[index] = candidate
        return copy.deepcopy(candidate)

    def replace_one(
        self,
        query: dict[str, Any],
        document: dict[str, Any],
        *,
        upsert: bool,
    ) -> _WriteResult:
        assert upsert is False
        for index, existing in enumerate(self.documents):
            if _matches(existing, query):
                self._check_unique(document, ignored=index)
                self.documents[index] = copy.deepcopy(document)
                return _WriteResult(matched_count=1)
        return _WriteResult()

    def delete_one(self, query: dict[str, Any]) -> _WriteResult:
        for index, existing in enumerate(self.documents):
            if _matches(existing, query):
                self.documents.pop(index)
                return _WriteResult(deleted_count=1)
        return _WriteResult()

    def list_indexes(self):
        return tuple(copy.deepcopy(self.indexes))

    def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str:
        self.indexes.append(
            {
                "name": kwargs["name"],
                "key": dict(keys),
                "unique": kwargs["unique"],
                "v": 2,
            }
        )
        return str(kwargs["name"])

    def aggregate(self, pipeline: list[dict[str, Any]]):
        self.aggregate_calls.append(copy.deepcopy(pipeline))
        return iter(copy.deepcopy(self.aggregate_results.pop(0)))


class _Database:
    name = "reading-space-test"

    def __init__(self) -> None:
        self.collections: dict[str, _Collection] = {}
        self.accesses: list[str] = []

    def __getitem__(self, name: str) -> _Collection:
        self.accesses.append(name)
        return self.collections.setdefault(name, _Collection(name))

    def list_collection_names(self) -> list[str]:
        return list(self.collections)


def _source(database: _Database, name: str = "Reading Source") -> Source:
    source = Source(name=name)
    database["sources"].documents.append(source.model_dump(mode="python"))
    return source


def _pdf_document(source: Source, *, status: str = "active") -> SourceDocument:
    digest = hashlib.sha256(PDF_BYTES).hexdigest()
    version = PdfVersion(
        sha256=digest,
        size_bytes=len(PDF_BYTES),
        logical_path=f"source_documents/blobs/sha256/{digest[:2]}/{digest}.pdf",
        original_filename="paper.pdf",
    )
    return SourceDocument(
        source_id=source.source_id,
        kind="pdf",
        title="Paper",
        status=status,
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def _web_document(source: Source, *, title: str = "Web") -> SourceDocument:
    return SourceDocument(
        source_id=source.source_id,
        kind="web",
        title=title,
        web=WebDocument(url_raw="https://example.test/resource"),
    )


def _store_document(database: _Database, document: SourceDocument) -> None:
    database["source_documents"].documents.append(document.model_dump(mode="python"))


def test_reading_state_model_ids_status_pages_utc_and_extra() -> None:
    source = Source(name="Model")
    document = _web_document(source)
    state = DocumentReadingState(
        document_id=document.document_id,
        source_id=source.source_id,
        current_page=2,
        total_pages=4,
        tags=["Topology", "topology", " Algebra "],
    )

    assert state.reading_state_id.startswith("read_")
    assert state.status == ReadingStatus.UNREAD
    assert state.tags == ["Topology", "Algebra"]
    assert state.created_at.tzinfo == timezone.utc
    with pytest.raises(ValidationError, match="read_"):
        DocumentReadingState(
            reading_state_id="bad",
            document_id=document.document_id,
            source_id=source.source_id,
        )
    with pytest.raises(ValidationError):
        DocumentReadingState(
            document_id="doc_bad",
            source_id=source.source_id,
        )
    with pytest.raises(ValidationError):
        DocumentReadingState(
            document_id=document.document_id,
            source_id=source.source_id,
            status="reading",
        )
    with pytest.raises(ValidationError, match="current_page"):
        DocumentReadingState(
            document_id=document.document_id,
            source_id=source.source_id,
            current_page=5,
            total_pages=4,
        )
    with pytest.raises(ValidationError):
        DocumentReadingState(
            document_id=document.document_id,
            source_id=source.source_id,
            current_page=True,
        )
    for field in ("current_page", "total_pages", "open_count"):
        for invalid in ("2", 2.0):
            with pytest.raises(ValidationError, match="strict integers"):
                DocumentReadingState(
                    document_id=document.document_id,
                    source_id=source.source_id,
                    **{field: invalid},
                )
    with pytest.raises(ValidationError, match="completed_at"):
        DocumentReadingState(
            document_id=document.document_id,
            source_id=source.source_id,
            completed_at=datetime.now(timezone.utc),
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        DocumentReadingState(
            document_id=document.document_id,
            source_id=source.source_id,
            created_at=datetime(2026, 7, 12),
        )
    with pytest.raises(ValidationError):
        DocumentReadingState(
            document_id=document.document_id,
            source_id=source.source_id,
            annotation="forbidden",
        )


def test_repository_and_index_construction_are_lazy_and_apply_is_explicit() -> None:
    database = _Database()
    repository = ReadingStateRepository(database)
    manager = ReadingSpaceIndexManager(database)

    assert repository.database is database
    assert manager.database is database
    assert database.accesses == []
    plan = manager.plan()
    assert len(plan.missing) == len(READING_SPACE_INDEXES) == 6
    assert database.accesses == []

    applied = manager.apply()
    assert applied.initialized
    assert len(database["document_reading_state"].indexes) == 7
    assert all(item.state == ReadingIndexState.PRESENT for item in manager.status())


def test_repository_unique_upsert_get_open_page_status_recent_paging_and_clear() -> None:
    database = _Database()
    source = Source(name="Repository")
    first_document = _web_document(source, title="First")
    second_document = _web_document(source, title="Second")
    repository = ReadingStateRepository(database)
    first = repository.upsert_for_document(
        DocumentReadingState(
            document_id=first_document.document_id,
            source_id=source.source_id,
        )
    )
    replacement = repository.upsert_for_document(
        DocumentReadingState(
            document_id=first_document.document_id,
            source_id=source.source_id,
            tags=["queue"],
        )
    )

    assert replacement.reading_state_id == first.reading_state_id
    assert len(database["document_reading_state"].documents) == 1
    opened = repository.mark_opened(
        document_id=first.document_id,
        source_id=source.source_id,
        reference_id=None,
        at=first.created_at + timedelta(seconds=1),
    )
    reopened = repository.mark_opened(
        document_id=first.document_id,
        source_id=source.source_id,
        reference_id=None,
        at=first.created_at + timedelta(seconds=2),
    )
    page_saved = repository.update_current_page(first.document_id, 3, total_pages=8)
    completed = repository.update_status(first.document_id, ReadingStatus.COMPLETED)
    repository.mark_opened(
        document_id=second_document.document_id,
        source_id=source.source_id,
        reference_id=None,
        at=first.created_at + timedelta(seconds=3),
    )
    recent = repository.list_recent(page=1, page_size=1)
    by_source = repository.list_by_source(source.source_id, page=1, page_size=1)
    counts = repository.count_by_status(source_id=source.source_id)

    assert opened.open_count == 1
    assert reopened.open_count == 2
    assert reopened.first_opened_at == opened.first_opened_at
    assert page_saved.current_page == 3 and page_saved.total_pages == 8
    assert completed.status == ReadingStatus.COMPLETED
    assert completed.completed_at is not None
    assert recent.total == 2 and recent.pages == 2
    assert recent.items[0].document_id == second_document.document_id
    assert by_source.total == 2 and len(by_source.items) == 1
    assert counts[ReadingStatus.COMPLETED] == 1
    assert repository.clear_state_for_document(first.document_id) is True
    assert repository.clear_state_for_document(first.document_id) is False


def test_repository_hydrates_naive_bson_datetimes() -> None:
    database = _Database()
    source = Source(name="BSON")
    document = _web_document(source)
    state = DocumentReadingState(
        document_id=document.document_id,
        source_id=source.source_id,
        status=ReadingStatus.IN_PROGRESS,
        first_opened_at=datetime.now(timezone.utc),
        last_opened_at=datetime.now(timezone.utc),
        open_count=1,
    )
    raw = BSON(BSON.encode(state.model_dump(mode="python"))).decode()
    assert raw["created_at"].tzinfo is None
    database["document_reading_state"].documents.append(raw)

    loaded = ReadingStateRepository(database).get_by_document(document.document_id)

    assert loaded.created_at.tzinfo == timezone.utc
    assert loaded.last_opened_at.tzinfo == timezone.utc


def test_readable_document_repository_builds_server_side_join_filter_and_pagination() -> None:
    database = _Database()
    source = Source(name="Pipeline")
    document = _web_document(source)
    state = DocumentReadingState(
        document_id=document.document_id,
        source_id=source.source_id,
        status=ReadingStatus.COMPLETED,
    )
    database["source_documents"].aggregate_results.append(
        [
            {
                "items": [
                    {
                        **document.model_dump(mode="python"),
                        "_reading_state": state.model_dump(mode="python"),
                        "_reading_states": [state.model_dump(mode="python")],
                        "_effective_reading_status": "completed",
                    }
                ],
                "total": [{"value": 3}],
            }
        ]
    )
    repository = ReadableDocumentRepository(database)

    page = repository.list(
        filters=ReadingDocumentFilters(
            source_id=source.source_id,
            reading_status=ReadingStatus.COMPLETED,
            tags=["proof"],
            title_query="[safe]",
            order=ReadingSort.STATUS,
        ),
        page=2,
        page_size=1,
    )

    assert page.total == 3 and page.page == 2 and page.pages == 3
    assert page.items[0].state.status == ReadingStatus.COMPLETED
    pipeline = database["source_documents"].aggregate_calls[0]
    assert any("$lookup" in stage for stage in pipeline)
    facet = next(stage["$facet"] for stage in pipeline if "$facet" in stage)
    assert {"$skip": 1} in facet["items"]
    assert {"$limit": 1} in facet["items"]
    first_match = next(stage["$match"] for stage in pipeline if "$match" in stage)
    assert first_match["title"]["$regex"] == r"\[safe\]"


def test_recent_join_excludes_dangling_states_before_total_sort_and_pagination() -> None:
    database = _Database()
    source = Source(name="Recent join")
    valid_document = _web_document(source)
    valid_state = DocumentReadingState(
        document_id=valid_document.document_id,
        source_id=source.source_id,
        status=ReadingStatus.IN_PROGRESS,
        first_opened_at=datetime.now(timezone.utc),
        last_opened_at=datetime.now(timezone.utc),
        open_count=1,
    )
    dangling_document = _web_document(source, title="Dangling")
    dangling_state = DocumentReadingState(
        document_id=dangling_document.document_id,
        source_id=source.source_id,
        status=ReadingStatus.IN_PROGRESS,
        first_opened_at=valid_state.first_opened_at + timedelta(seconds=1),
        last_opened_at=valid_state.last_opened_at + timedelta(seconds=1),
        open_count=1,
    )
    database["document_reading_state"].documents.extend(
        [
            dangling_state.model_dump(mode="python"),
            valid_state.model_dump(mode="python"),
        ]
    )
    database["source_documents"].aggregate_results.append(
        [
            {
                "items": [
                    {
                        **valid_document.model_dump(mode="python"),
                        "_reading_state": valid_state.model_dump(mode="python"),
                        "_reading_states": [valid_state.model_dump(mode="python")],
                    }
                ],
                "total": [{"value": 1}],
            }
        ]
    )

    page = ReadableDocumentRepository(database).list_recent(page=1, page_size=1)

    assert page.total == 1
    assert [item.document.document_id for item in page.items] == [valid_document.document_id]
    pipeline = database["source_documents"].aggregate_calls[0]
    join_filter_index = next(
        index
        for index, stage in enumerate(pipeline)
        if stage.get("$match") == {"_reading_states.0": {"$exists": True}}
    )
    facet_index = next(index for index, stage in enumerate(pipeline) if "$facet" in stage)
    assert join_filter_index < facet_index
    facet = pipeline[facet_index]["$facet"]
    assert facet["items"][-2:] == [{"$skip": 0}, {"$limit": 1}]


class _ReadyIndexes:
    def plan(self):
        return SimpleNamespace(missing=(), conflicts=(), initialized=True)


class _MissingIndexes:
    def plan(self):
        return SimpleNamespace(missing=(object(),), conflicts=(), initialized=False)


class _DocumentService:
    def __init__(self, document: SourceDocument, *, healthy: bool = True) -> None:
        self.document = document
        self.healthy = healthy
        self.read_calls = 0
        self.publish_calls = 0

    def inspect_document_integrity(self, document_id: str) -> DocumentIntegrityInspection:
        assert document_id == self.document.document_id
        return DocumentIntegrityInspection(
            document_id,
            self.healthy,
            () if self.healthy else ("sha256_mismatch",),
        )

    def read_pdf_document(self, document_id: str) -> DocumentPdfPayload:
        assert document_id == self.document.document_id
        self.read_calls += 1
        version = self.document.pdf.current_version
        return DocumentPdfPayload(
            self.document, PDF_BYTES, version.original_filename, version.sha256
        )


class _ReadableStub:
    def __init__(
        self,
        summary: SourceSummaryCounts | None = None,
        *,
        database: _Database | None = None,
        document: SourceDocument | None = None,
    ) -> None:
        self.summary = summary or SourceSummaryCounts()
        self.database = database
        self.document = document

    def list(self, **_kwargs: Any) -> ReadableDocumentPage:
        return ReadableDocumentPage((), 1, 50, 0)

    def list_recent(
        self,
        *,
        user_scope: str,
        page: int,
        page_size: int,
    ) -> ReadableDocumentPage:
        assert self.database is not None and self.document is not None
        state = ReadingStateRepository(self.database).get_by_document(
            self.document.document_id,
            user_scope=user_scope,
        )
        items = (ReadableDocumentItem(self.document, state),) if state is not None else ()
        return ReadableDocumentPage(items, page, page_size, len(items))

    def source_summary(self, _source_id: str, *, user_scope: str) -> SourceSummaryCounts:
        assert user_scope == "local"
        return self.summary


def _service(
    database: _Database,
    document: SourceDocument,
    *,
    healthy: bool = True,
    ready: bool = True,
    readable: Any | None = None,
) -> tuple[ReadingSpaceService, _DocumentService]:
    document_service = _DocumentService(document, healthy=healthy)
    service = ReadingSpaceService(
        database,
        document_service=document_service,  # type: ignore[arg-type]
        index_manager=_ReadyIndexes() if ready else _MissingIndexes(),  # type: ignore[arg-type]
        readable_documents=(readable or _ReadableStub(database=database, document=document)),  # type: ignore[arg-type]
    )
    return service, document_service


def test_service_open_pdf_increments_without_publishing_and_preserves_first_open() -> None:
    database = _Database()
    source = _source(database)
    document = _pdf_document(source)
    _store_document(database, document)
    service, document_service = _service(database, document)

    first = service.open_document(document.document_id)
    second = service.open_document(document.document_id)

    assert first.status == ReadingOperationStatus.SUCCESS
    assert first.value.pdf_payload.pdf_bytes == PDF_BYTES
    assert second.value.reading_state.open_count == 2
    assert second.value.reading_state.first_opened_at == first.value.reading_state.first_opened_at
    assert document_service.read_calls == 2
    assert document_service.publish_calls == 0
    assert "concepts" not in database.collections


def test_service_blocks_archived_integrity_and_missing_indexes_without_state_write() -> None:
    database = _Database()
    source = _source(database)
    archived = _pdf_document(source, status="archived")
    _store_document(database, archived)
    archived_service, _ = _service(database, archived)
    assert archived_service.open_document(archived.document_id).status == (
        ReadingOperationStatus.ARCHIVED
    )

    active = _pdf_document(source)
    _store_document(database, active)
    damaged_service, damaged_reader = _service(database, active, healthy=False)
    assert damaged_service.open_document(active.document_id).status == (
        ReadingOperationStatus.INTEGRITY_ERROR
    )
    assert damaged_reader.read_calls == 0
    missing_service, _ = _service(database, active, ready=False)
    assert missing_service.open_document(active.document_id).status == (
        ReadingOperationStatus.INVALID_STATE
    )
    assert database["document_reading_state"].documents == []


def test_service_web_open_has_no_network_and_unread_actions_create_controlled_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _Database()
    source = _source(database)
    completed_doc = _web_document(source, title="Completed")
    deferred_doc = SourceDocument(
        source_id=source.source_id,
        kind="web",
        title="Deferred",
        web=WebDocument(url_raw="https://example.test/deferred"),
    )
    page_doc = _pdf_document(source)
    for document in (completed_doc, deferred_doc, page_doc):
        _store_document(database, document)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network access")),
    )
    service, _ = _service(database, completed_doc)

    invalid_web_page = service.update_current_page(completed_doc.document_id, 4)
    completed = service.mark_completed(completed_doc.document_id)
    deferred = service.mark_deferred(deferred_doc.document_id)
    page = service.update_current_page(page_doc.document_id, 4)
    opened = service.open_document(completed_doc.document_id)

    assert invalid_web_page.status == ReadingOperationStatus.INVALID_STATE
    assert completed.value.status == ReadingStatus.COMPLETED
    assert completed.value.open_count == 0 and completed.value.first_opened_at is None
    assert deferred.value.status == ReadingStatus.DEFERRED
    assert page.value.status == ReadingStatus.IN_PROGRESS and page.value.current_page == 4
    assert opened.value.reading_state.status == ReadingStatus.COMPLETED
    assert opened.value.reading_state.open_count == 1


def test_service_page_status_reset_recent_summary_missing_and_source_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _Database()
    source = _source(database)
    document = _pdf_document(source)
    _store_document(database, document)
    summary = SourceSummaryCounts(
        total_documents=2,
        pdf_documents=1,
        web_documents=1,
        unread=1,
        completed=1,
    )
    service, _ = _service(
        database,
        document,
        readable=_ReadableStub(summary, database=database, document=document),
    )
    service.open_document(document.document_id)

    page = service.update_current_page(document.document_id, 2, total_pages=5)
    completed = service.mark_completed(document.document_id)
    deferred = service.mark_deferred(document.document_id)
    dangling_document = _web_document(source, title="Missing recent Document")
    dangling_state = DocumentReadingState(
        document_id=dangling_document.document_id,
        source_id=source.source_id,
        status=ReadingStatus.IN_PROGRESS,
        first_opened_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        last_opened_at=datetime.now(timezone.utc) + timedelta(seconds=1),
        open_count=1,
    )
    database["document_reading_state"].documents.insert(
        0,
        dangling_state.model_dump(mode="python"),
    )
    monkeypatch.setattr(
        service.states,
        "list_recent",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("service must not paginate raw reading states")
        ),
    )
    recent = service.list_recent_documents()
    source_summary = service.get_source_reading_summary(source.source_id)
    reset = service.reset_reading_state(document.document_id)
    missing = service.open_document(_web_document(source).document_id)

    assert page.value.current_page == 2
    assert completed.value.completed_at is not None
    assert deferred.value.completed_at is None
    assert recent.value.items[0].document.document_id == document.document_id
    assert recent.value.total == 1
    assert source_summary.value.total_documents == 2
    assert reset.status == ReadingOperationStatus.SUCCESS
    assert service.get_reader_context(document.document_id).value.effective_status == (
        ReadingStatus.UNREAD
    )
    assert missing.status == ReadingOperationStatus.NOT_FOUND

    bad_state = DocumentReadingState(
        document_id=document.document_id,
        source_id=Source(name="Wrong").source_id,
    )
    database["document_reading_state"].documents.append(bad_state.model_dump(mode="python"))
    assert (
        service.get_reader_context(document.document_id).status == ReadingOperationStatus.CONFLICT
    )


def test_source_summary_pipeline_returns_empty_and_typed_counts() -> None:
    database = _Database()
    repository = ReadableDocumentRepository(database)
    database["source_documents"].aggregate_results.extend(
        [
            [],
            [
                {
                    "total_documents": 4,
                    "pdf_documents": 3,
                    "web_documents": 1,
                    "unread": 1,
                    "in_progress": 1,
                    "completed": 1,
                    "deferred": 1,
                    "last_opened_at": datetime(2026, 7, 12),
                }
            ],
        ]
    )

    empty = repository.source_summary(Source(name="Empty").source_id)
    counts = repository.source_summary(Source(name="Full").source_id)

    assert empty.total_documents == 0
    assert counts.total_documents == 4
    assert counts.last_opened_at.tzinfo == timezone.utc


def test_reading_space_static_scope_excludes_s4_and_local_io_tokens() -> None:
    forbidden = (
        "ReadingNote",
        "ConceptEvidenceLink",
        "highlight",
        "file://",
        "Path.as_uri",
        "webbrowser",
        "requests.get",
    )
    import mathmongo.reading_space.models as models_module
    import mathmongo.reading_space.service as service_module

    text = Path(models_module.__file__).read_text(encoding="utf-8")
    text += Path(service_module.__file__).read_text(encoding="utf-8")
    assert not any(token in text for token in forbidden)

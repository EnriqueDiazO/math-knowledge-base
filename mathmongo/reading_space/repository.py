"""MongoDB persistence and read-query boundaries for Reading Space."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from mathmongo.reading_space.errors import ReadingStateConflictError
from mathmongo.reading_space.errors import ReadingStateRepositoryError
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.reading_space.models import ReadingDocumentFilters
from mathmongo.reading_space.models import ReadingSort
from mathmongo.reading_space.models import ReadingStatus
from mathmongo.reading_space.models import utc_now
from mathmongo.reading_space.models import validate_user_scope
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import SourceDocument


@dataclass(frozen=True, slots=True)
class ReadingStatePage:
    items: tuple[DocumentReadingState, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


@dataclass(frozen=True, slots=True)
class ReadableDocumentItem:
    document: SourceDocument
    state: DocumentReadingState | None
    source: Source | None = None
    reference: Reference | None = None

    @property
    def effective_status(self) -> ReadingStatus:
        return self.state.status if self.state is not None else ReadingStatus.UNREAD


@dataclass(frozen=True, slots=True)
class ReadableDocumentPage:
    items: tuple[ReadableDocumentItem, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


@dataclass(frozen=True, slots=True)
class SourceSummaryCounts:
    total_documents: int = 0
    pdf_documents: int = 0
    web_documents: int = 0
    unread: int = 0
    in_progress: int = 0
    completed: int = 0
    deferred: int = 0
    last_opened_at: datetime | None = None


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")
    return page, page_size


def _aware_utc(value: Any) -> Any:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reading_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("_id", None)
    for field in (
        "last_opened_at",
        "first_opened_at",
        "completed_at",
        "created_at",
        "updated_at",
    ):
        if field in payload:
            payload[field] = _aware_utc(payload[field])
    return payload


def _reading_model(document: Any) -> DocumentReadingState | None:
    if document is None:
        return None
    return DocumentReadingState.model_validate(_reading_payload(document))


def _source_document_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("_id", None)
    for field in ("created_at", "updated_at", "archived_at"):
        if field in payload:
            payload[field] = _aware_utc(payload[field])
    pdf = payload.get("pdf")
    if isinstance(pdf, Mapping):
        pdf_payload = dict(pdf)
        versions: list[Any] = []
        for version in pdf_payload.get("versions", []):
            if isinstance(version, Mapping):
                version_payload = dict(version)
                if "created_at" in version_payload:
                    version_payload["created_at"] = _aware_utc(version_payload["created_at"])
                versions.append(version_payload)
            else:
                versions.append(version)
        pdf_payload["versions"] = versions
        payload["pdf"] = pdf_payload
    return payload


def _source_document_model(document: Any) -> SourceDocument:
    return SourceDocument.model_validate(_source_document_payload(document))


def _mongo_document(state: DocumentReadingState) -> dict[str, Any]:
    return state.model_dump(mode="python")


class ReadingStateRepository:
    """Persist one state per ``(user_scope, document_id)`` without auto-indexing."""

    COLLECTION = "document_reading_state"

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReadingStateRepository requires an explicit database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def upsert_for_document(
        self,
        state: DocumentReadingState | Mapping[str, Any],
    ) -> DocumentReadingState:
        candidate = (
            state
            if isinstance(state, DocumentReadingState)
            else DocumentReadingState.model_validate(state)
        )
        identity = {
            "user_scope": candidate.user_scope,
            "document_id": candidate.document_id,
        }
        current = self.get_by_document(candidate.document_id, user_scope=candidate.user_scope)
        if current is not None and current.source_id != candidate.source_id:
            raise ReadingStateConflictError(
                "Reading state source_id conflicts with the Source Document"
            )
        immutable = {
            "schema_version": candidate.schema_version,
            "reading_state_id": candidate.reading_state_id,
            "document_id": candidate.document_id,
            "source_id": candidate.source_id,
            "user_scope": candidate.user_scope,
            "created_at": candidate.created_at,
        }
        mutable = candidate.model_dump(mode="python", exclude=set(immutable))
        if current is not None:
            mutable["reference_id"] = candidate.reference_id
        try:
            raw = self._collection.find_one_and_update(
                identity,
                {"$set": mutable, "$setOnInsert": immutable},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ReadingStateConflictError(
                "Reading state identity conflicts with another persisted state"
            ) from exc
        except Exception as exc:
            raise ReadingStateRepositoryError("Reading state upsert failed") from exc
        model = _reading_model(raw)
        if model is None:
            raise ReadingStateRepositoryError("Reading state upsert returned no document")
        return model

    def get_by_document(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> DocumentReadingState | None:
        scope = validate_user_scope(user_scope)
        return _reading_model(
            self._collection.find_one({"user_scope": scope, "document_id": document_id})
        )

    def list_recent(
        self,
        *,
        user_scope: str = "local",
        page: int = 1,
        page_size: int = 20,
    ) -> ReadingStatePage:
        page, page_size = _pagination(page, page_size)
        query = {
            "user_scope": validate_user_scope(user_scope),
            "last_opened_at": {"$ne": None},
        }
        return self._page(
            query,
            page=page,
            page_size=page_size,
            sort=[("last_opened_at", -1), ("updated_at", -1), ("reading_state_id", 1)],
        )

    def list_by_source(
        self,
        source_id: str,
        *,
        user_scope: str = "local",
        status: ReadingStatus | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ReadingStatePage:
        page, page_size = _pagination(page, page_size)
        query: dict[str, Any] = {
            "source_id": source_id,
            "user_scope": validate_user_scope(user_scope),
        }
        if status is not None:
            query["status"] = ReadingStatus(status).value
        return self._page(
            query,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("reading_state_id", 1)],
        )

    def _page(
        self,
        query: dict[str, Any],
        *,
        page: int,
        page_size: int,
        sort: list[tuple[str, int]],
    ) -> ReadingStatePage:
        total = int(self._collection.count_documents(query))
        cursor = (
            self._collection.find(query).sort(sort).skip((page - 1) * page_size).limit(page_size)
        )
        return ReadingStatePage(
            tuple(model for raw in cursor if (model := _reading_model(raw)) is not None),
            page,
            page_size,
            total,
        )

    def _replace(self, state: DocumentReadingState) -> DocumentReadingState:
        try:
            result = self._collection.replace_one(
                {
                    "reading_state_id": state.reading_state_id,
                    "user_scope": state.user_scope,
                    "document_id": state.document_id,
                    "source_id": state.source_id,
                },
                _mongo_document(state),
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise ReadingStateConflictError("Concurrent reading-state conflict") from exc
        except Exception as exc:
            raise ReadingStateRepositoryError("Reading state update failed") from exc
        if not getattr(result, "matched_count", 0):
            raise ReadingStateConflictError("Reading state changed concurrently")
        return state

    def update_current_page(
        self,
        document_id: str,
        current_page: int,
        *,
        user_scope: str = "local",
        total_pages: int | None = None,
    ) -> DocumentReadingState | None:
        current = self.get_by_document(document_id, user_scope=user_scope)
        if current is None:
            return None
        payload = current.model_dump(mode="python")
        payload["current_page"] = current_page
        if total_pages is not None:
            payload["total_pages"] = total_pages
        if current.status in {ReadingStatus.UNREAD, ReadingStatus.DEFERRED}:
            payload["status"] = ReadingStatus.IN_PROGRESS
            payload["completed_at"] = None
        payload["updated_at"] = utc_now()
        return self._replace(DocumentReadingState.model_validate(payload))

    def update_status(
        self,
        document_id: str,
        status: ReadingStatus | str,
        *,
        user_scope: str = "local",
        at: datetime | None = None,
    ) -> DocumentReadingState | None:
        current = self.get_by_document(document_id, user_scope=user_scope)
        if current is None:
            return None
        timestamp = at or utc_now()
        next_status = ReadingStatus(status)
        payload = current.model_dump(mode="python")
        payload["status"] = next_status
        if next_status == ReadingStatus.COMPLETED:
            payload["completed_at"] = current.completed_at or timestamp
        else:
            payload["completed_at"] = None
        payload["updated_at"] = timestamp
        return self._replace(DocumentReadingState.model_validate(payload))

    def mark_opened(
        self,
        *,
        document_id: str,
        source_id: str,
        reference_id: str | None,
        user_scope: str = "local",
        at: datetime | None = None,
    ) -> DocumentReadingState:
        scope = validate_user_scope(user_scope)
        timestamp = at or utc_now()
        current = self.get_by_document(document_id, user_scope=scope)
        if current is None:
            return self.upsert_for_document(
                DocumentReadingState(
                    document_id=document_id,
                    source_id=source_id,
                    reference_id=reference_id,
                    user_scope=scope,
                    status=ReadingStatus.IN_PROGRESS,
                    first_opened_at=timestamp,
                    last_opened_at=timestamp,
                    open_count=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        if current.source_id != source_id:
            raise ReadingStateConflictError(
                "Reading state source_id conflicts with the Source Document"
            )
        next_status = current.status
        completed_at = current.completed_at
        if next_status in {ReadingStatus.UNREAD, ReadingStatus.DEFERRED}:
            next_status = ReadingStatus.IN_PROGRESS
            completed_at = None
        changes: dict[str, Any] = {
            "reference_id": reference_id,
            "status": next_status.value,
            "completed_at": completed_at,
            "last_opened_at": timestamp,
            "updated_at": timestamp,
        }
        if current.first_opened_at is None:
            changes["first_opened_at"] = timestamp
        try:
            raw = self._collection.find_one_and_update(
                {
                    "reading_state_id": current.reading_state_id,
                    "user_scope": scope,
                    "document_id": document_id,
                    "source_id": source_id,
                },
                {"$set": changes, "$inc": {"open_count": 1}},
                upsert=False,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            raise ReadingStateConflictError("Concurrent reading-state conflict") from exc
        except Exception as exc:
            raise ReadingStateRepositoryError("Could not mark the document opened") from exc
        model = _reading_model(raw)
        if model is None:
            raise ReadingStateConflictError("Reading state changed concurrently")
        return model

    def clear_state_for_document(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> bool:
        result = self._collection.delete_one(
            {"user_scope": validate_user_scope(user_scope), "document_id": document_id}
        )
        return bool(getattr(result, "deleted_count", 0))

    def count_by_status(
        self,
        *,
        user_scope: str = "local",
        source_id: str | None = None,
    ) -> dict[ReadingStatus, int]:
        base: dict[str, Any] = {"user_scope": validate_user_scope(user_scope)}
        if source_id is not None:
            base["source_id"] = source_id
        return {
            status: int(self._collection.count_documents({**base, "status": status.value}))
            for status in ReadingStatus
        }


class ReadableDocumentRepository:
    """Read-only global Source Document queries joined with one user scope."""

    COLLECTION = "source_documents"
    STATE_COLLECTION = "document_reading_state"

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReadableDocumentRepository requires an explicit database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    @staticmethod
    def _lookup(user_scope: str) -> list[dict[str, Any]]:
        return [
            {
                "$lookup": {
                    "from": ReadableDocumentRepository.STATE_COLLECTION,
                    "let": {"selected_document_id": "$document_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$document_id", "$$selected_document_id"]},
                                        {"$eq": ["$user_scope", user_scope]},
                                    ]
                                }
                            }
                        },
                        {"$limit": 1},
                    ],
                    "as": "_reading_states",
                }
            },
            {
                "$set": {
                    "_reading_state": {"$arrayElemAt": ["$_reading_states", 0]},
                    "_effective_reading_status": {
                        "$ifNull": [
                            {"$arrayElemAt": ["$_reading_states.status", 0]},
                            ReadingStatus.UNREAD.value,
                        ]
                    },
                }
            },
        ]

    @staticmethod
    def _document_match(filters: ReadingDocumentFilters) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if filters.source_id is not None:
            query["source_id"] = filters.source_id
        if filters.reference_id is not None:
            query["reference_id"] = filters.reference_id
        if filters.kind is not None:
            query["kind"] = filters.kind.value
        if filters.document_status is not None:
            query["status"] = filters.document_status.value
        if filters.title_query:
            query["title"] = {"$regex": re.escape(filters.title_query), "$options": "i"}
        return query

    @staticmethod
    def _sort(order: ReadingSort) -> list[tuple[str, int]]:
        if order == ReadingSort.TITLE:
            return [("title", 1), ("document_id", 1)]
        if order == ReadingSort.SOURCE:
            return [("source_id", 1), ("title", 1), ("document_id", 1)]
        if order == ReadingSort.STATUS:
            return [
                ("_effective_reading_status", 1),
                ("title", 1),
                ("document_id", 1),
            ]
        return [
            ("_reading_state.last_opened_at", -1),
            ("updated_at", -1),
            ("document_id", 1),
        ]

    def list(
        self,
        *,
        filters: ReadingDocumentFilters | Mapping[str, Any] | None = None,
        user_scope: str = "local",
        page: int = 1,
        page_size: int = 50,
    ) -> ReadableDocumentPage:
        page, page_size = _pagination(page, page_size)
        scope = validate_user_scope(user_scope)
        selected = (
            filters
            if isinstance(filters, ReadingDocumentFilters)
            else ReadingDocumentFilters.model_validate(filters or {})
        )
        pipeline: list[dict[str, Any]] = []
        document_match = self._document_match(selected)
        if document_match:
            pipeline.append({"$match": document_match})
        pipeline.extend(self._lookup(scope))
        joined_conditions: list[dict[str, Any]] = []
        if selected.reading_status is not None:
            joined_conditions.append({"_effective_reading_status": selected.reading_status.value})
        for tag in selected.tags:
            joined_conditions.append({"$or": [{"tags": tag}, {"_reading_state.tags": tag}]})
        if joined_conditions:
            pipeline.append(
                {
                    "$match": joined_conditions[0]
                    if len(joined_conditions) == 1
                    else {"$and": joined_conditions}
                }
            )
        pipeline.append(
            {
                "$facet": {
                    "items": [
                        {"$sort": dict(self._sort(selected.order))},
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                    ],
                    "total": [{"$count": "value"}],
                }
            }
        )
        result = tuple(self._collection.aggregate(pipeline))
        facet = result[0] if result else {}
        count_rows = facet.get("total", [])
        total = int(count_rows[0].get("value", 0)) if count_rows else 0
        items: list[ReadableDocumentItem] = []
        for raw in facet.get("items", []):
            payload = dict(raw)
            state_raw = payload.pop("_reading_state", None)
            payload.pop("_reading_states", None)
            payload.pop("_effective_reading_status", None)
            items.append(
                ReadableDocumentItem(
                    _source_document_model(payload),
                    _reading_model(state_raw),
                )
            )
        return ReadableDocumentPage(tuple(items), page, page_size, total)

    def list_recent(
        self,
        *,
        user_scope: str = "local",
        page: int = 1,
        page_size: int = 20,
    ) -> ReadableDocumentPage:
        """Join existing Documents before sorting and paginating recent reads."""
        page, page_size = _pagination(page, page_size)
        scope = validate_user_scope(user_scope)
        pipeline: list[dict[str, Any]] = [
            {
                "$lookup": {
                    "from": self.STATE_COLLECTION,
                    "let": {"selected_document_id": "$document_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$document_id", "$$selected_document_id"]},
                                        {"$eq": ["$user_scope", scope]},
                                    ]
                                },
                                "last_opened_at": {"$ne": None},
                            }
                        },
                        {"$limit": 1},
                    ],
                    "as": "_reading_states",
                }
            },
            {"$match": {"_reading_states.0": {"$exists": True}}},
            {"$set": {"_reading_state": {"$arrayElemAt": ["$_reading_states", 0]}}},
            {
                "$facet": {
                    "items": [
                        {
                            "$sort": {
                                "_reading_state.last_opened_at": -1,
                                "_reading_state.updated_at": -1,
                                "document_id": 1,
                            }
                        },
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                    ],
                    "total": [{"$count": "value"}],
                }
            },
        ]
        result = tuple(self._collection.aggregate(pipeline))
        facet = result[0] if result else {}
        count_rows = facet.get("total", [])
        total = int(count_rows[0].get("value", 0)) if count_rows else 0
        items: list[ReadableDocumentItem] = []
        for raw in facet.get("items", []):
            payload = dict(raw)
            state_raw = payload.pop("_reading_state", None)
            payload.pop("_reading_states", None)
            state = _reading_model(state_raw)
            if state is None:
                continue
            items.append(ReadableDocumentItem(_source_document_model(payload), state))
        return ReadableDocumentPage(tuple(items), page, page_size, total)

    def source_summary(
        self,
        source_id: str,
        *,
        user_scope: str = "local",
    ) -> SourceSummaryCounts:
        scope = validate_user_scope(user_scope)
        pipeline: list[dict[str, Any]] = [{"$match": {"source_id": source_id}}]
        pipeline.extend(self._lookup(scope))
        pipeline.append(
            {
                "$group": {
                    "_id": None,
                    "total_documents": {"$sum": 1},
                    "pdf_documents": {"$sum": {"$cond": [{"$eq": ["$kind", "pdf"]}, 1, 0]}},
                    "web_documents": {"$sum": {"$cond": [{"$eq": ["$kind", "web"]}, 1, 0]}},
                    "unread": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$_effective_reading_status", "unread"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "in_progress": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$_effective_reading_status", "in_progress"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "completed": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$_effective_reading_status", "completed"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "deferred": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$_effective_reading_status", "deferred"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "last_opened_at": {"$max": "$_reading_state.last_opened_at"},
                }
            }
        )
        rows = tuple(self._collection.aggregate(pipeline))
        if not rows:
            return SourceSummaryCounts()
        raw = dict(rows[0])
        return SourceSummaryCounts(
            total_documents=int(raw.get("total_documents", 0)),
            pdf_documents=int(raw.get("pdf_documents", 0)),
            web_documents=int(raw.get("web_documents", 0)),
            unread=int(raw.get("unread", 0)),
            in_progress=int(raw.get("in_progress", 0)),
            completed=int(raw.get("completed", 0)),
            deferred=int(raw.get("deferred", 0)),
            last_opened_at=_aware_utc(raw.get("last_opened_at")),
        )


__all__ = [
    "ReadableDocumentItem",
    "ReadableDocumentPage",
    "ReadableDocumentRepository",
    "ReadingStatePage",
    "ReadingStateRepository",
    "SourceSummaryCounts",
]

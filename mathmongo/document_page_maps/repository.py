"""Lazy MongoDB persistence for S4.2 Document page maps."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from mathmongo.document_page_maps.errors import DocumentPageMapConflictError
from mathmongo.document_page_maps.errors import DocumentPageMapRepositoryError
from mathmongo.document_page_maps.indexes import DOCUMENT_PAGE_MAPS_COLLECTION
from mathmongo.document_page_maps.models import DocumentPageMap
from mathmongo.document_page_maps.models import PageMapStatus
from mathmongo.document_page_maps.models import utc_now
from mathmongo.document_page_maps.models import validate_page_map_id
from mathmongo.source_documents.models import validate_document_id


@dataclass(frozen=True, slots=True)
class DocumentPageMapPage:
    items: tuple[DocumentPageMap, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


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


def _model(document: Any) -> DocumentPageMap | None:
    if document is None:
        return None
    payload = dict(document)
    payload.pop("_id", None)
    for field in ("created_at", "updated_at", "archived_at"):
        if field in payload:
            payload[field] = _aware_utc(payload[field])
    return DocumentPageMap.model_validate(payload)


class DocumentPageMapRepository:
    COLLECTION = DOCUMENT_PAGE_MAPS_COLLECTION

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("DocumentPageMapRepository requires an explicit database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def insert(self, page_map: DocumentPageMap | Mapping[str, Any]) -> DocumentPageMap:
        candidate = (
            page_map
            if isinstance(page_map, DocumentPageMap)
            else DocumentPageMap.model_validate(page_map)
        )
        try:
            self._collection.insert_one(candidate.model_dump(mode="python"))
        except DuplicateKeyError as exc:
            raise DocumentPageMapConflictError(
                f"Document page-map identity conflicts: {candidate.page_map_id}"
            ) from exc
        except Exception as exc:
            raise DocumentPageMapRepositoryError("Document page-map insert failed") from exc
        return candidate

    def get_by_id(self, page_map_id: str) -> DocumentPageMap | None:
        validate_page_map_id(page_map_id)
        return _model(self._collection.find_one({"page_map_id": page_map_id}))

    def get_active(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> DocumentPageMap | None:
        validate_document_id(document_id)
        cursor = self._collection.find(
            {
                "document_id": document_id,
                "user_scope": user_scope,
                "status": PageMapStatus.ACTIVE.value,
            }
        ).limit(2)
        items = tuple(item for raw in cursor if (item := _model(raw)) is not None)
        if len(items) > 1:
            raise DocumentPageMapConflictError(
                "Multiple active page maps exist for one user_scope and Document"
            )
        return items[0] if items else None

    def list_by_document(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
        status: PageMapStatus | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> DocumentPageMapPage:
        validate_document_id(document_id)
        page, page_size = _pagination(page, page_size)
        query: dict[str, Any] = {"document_id": document_id, "user_scope": user_scope}
        if status is not None:
            query["status"] = PageMapStatus(status).value
        total = int(self._collection.count_documents(query))
        cursor = (
            self._collection.find(query)
            .sort([("updated_at", -1), ("page_map_id", 1)])
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return DocumentPageMapPage(
            tuple(item for raw in cursor if (item := _model(raw)) is not None),
            page,
            page_size,
            total,
        )

    def replace(self, page_map: DocumentPageMap) -> DocumentPageMap | None:
        candidate = DocumentPageMap.model_validate(page_map.model_dump(mode="python"))
        try:
            result = self._collection.replace_one(
                {"page_map_id": candidate.page_map_id},
                candidate.model_dump(mode="python"),
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise DocumentPageMapConflictError(
                "Another active page map already exists for this Document"
            ) from exc
        except Exception as exc:
            raise DocumentPageMapRepositoryError("Document page-map update failed") from exc
        return candidate if getattr(result, "matched_count", 0) else None

    def archive(
        self,
        page_map_id: str,
        *,
        at: datetime | None = None,
    ) -> DocumentPageMap | None:
        current = self.get_by_id(page_map_id)
        if current is None or current.status == PageMapStatus.ARCHIVED:
            return current
        timestamp = at or utc_now()
        payload = current.model_dump(mode="python")
        payload.update(
            {"status": PageMapStatus.ARCHIVED, "updated_at": timestamp, "archived_at": timestamp}
        )
        return self.replace(DocumentPageMap.model_validate(payload))

    def reactivate(
        self,
        page_map_id: str,
        *,
        at: datetime | None = None,
    ) -> DocumentPageMap | None:
        current = self.get_by_id(page_map_id)
        if current is None or current.status == PageMapStatus.ACTIVE:
            return current
        payload = current.model_dump(mode="python")
        payload.update(
            {"status": PageMapStatus.ACTIVE, "updated_at": at or utc_now(), "archived_at": None}
        )
        return self.replace(DocumentPageMap.model_validate(payload))

    def reset(
        self,
        page_map_id: str,
        *,
        at: datetime | None = None,
    ) -> DocumentPageMap | None:
        current = self.get_by_id(page_map_id)
        if current is None:
            return None
        payload = current.model_dump(mode="python")
        payload.update({"rules": [], "manual_overrides": [], "updated_at": at or utc_now()})
        return self.replace(DocumentPageMap.model_validate(payload))


__all__ = ["DocumentPageMapPage", "DocumentPageMapRepository"]

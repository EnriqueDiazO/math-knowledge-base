"""MongoDB persistence boundary for Source Documents."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any

from pymongo.errors import DuplicateKeyError

from mathmongo.source_documents.indexes import SourceDocumentIndexManager
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import utc_now


class SourceDocumentRepositoryError(RuntimeError):
    """Base class for controlled Source Document persistence errors."""


class SourceDocumentRepositoryConflictError(SourceDocumentRepositoryError):
    """A stable identity already exists with incompatible data."""


@dataclass(frozen=True, slots=True)
class SourceDocumentPage:
    items: tuple[SourceDocument, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


def _aware_utc(value: Any) -> Any:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hydrate_datetimes(document: Mapping[str, Any]) -> dict[str, Any]:
    """Attach UTC to BSON datetimes returned naive by the legacy Mongo client."""
    payload = dict(document)
    for field_name in ("created_at", "updated_at", "archived_at"):
        if field_name in payload:
            payload[field_name] = _aware_utc(payload[field_name])
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


def _model(document: Any) -> SourceDocument | None:
    if document is None:
        return None
    payload = _hydrate_datetimes(document)
    payload.pop("_id", None)
    return SourceDocument.model_validate(payload)


def _mongo_document(document: SourceDocument) -> dict[str, Any]:
    return document.model_dump(mode="python")


class SourceDocumentRepository:
    """Persist Source Documents without modifying Sources, References, or concepts."""

    COLLECTION = "source_documents"
    MUTABLE_METADATA_FIELDS = frozenset(
        {"reference_id", "title", "description", "language", "tags", "rights"}
    )

    def __init__(self, database: Any, *, index_manager: Any | None = None) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("SourceDocumentRepository requires an explicit database")
        self.database = database
        self.index_manager = index_manager or SourceDocumentIndexManager(database)

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def ensure_indexes(self) -> tuple[str, ...]:
        return tuple(self.index_manager.ensure())

    def insert(self, document: SourceDocument | Mapping[str, Any]) -> SourceDocument:
        candidate = (
            document
            if isinstance(document, SourceDocument)
            else SourceDocument.model_validate(document)
        )
        try:
            self._collection.insert_one(_mongo_document(candidate))
        except DuplicateKeyError as exc:
            raise SourceDocumentRepositoryConflictError(
                f"Source Document identity already exists: {candidate.document_id}"
            ) from exc
        return candidate

    def get_by_id(self, document_id: str) -> SourceDocument | None:
        return _model(self._collection.find_one({"document_id": document_id}))

    def find_pdf_identity(self, source_id: str, sha256: str) -> tuple[SourceDocument, ...]:
        return tuple(
            model
            for raw in self._collection.find(
                {"source_id": source_id, "kind": "pdf", "pdf.versions.sha256": sha256}
            )
            if (model := _model(raw)) is not None
        )

    def find_web_identity(self, source_id: str, normalized_url: str) -> tuple[SourceDocument, ...]:
        return tuple(
            model
            for raw in self._collection.find(
                {
                    "source_id": source_id,
                    "kind": "web",
                    "web.url_normalized": normalized_url,
                }
            )
            if (model := _model(raw)) is not None
        )

    def list(
        self,
        source_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        status: DocumentStatus | str | None = None,
        kind: DocumentKind | str | None = None,
    ) -> SourceDocumentPage:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 100
        ):
            raise ValueError("page_size must be between 1 and 100")
        query: dict[str, Any] = {"source_id": source_id}
        if status is not None:
            query["status"] = getattr(status, "value", status)
        if kind is not None:
            query["kind"] = getattr(kind, "value", kind)
        total = int(self._collection.count_documents(query))
        cursor = self._collection.find(query)
        sort = getattr(cursor, "sort", None)
        if callable(sort):
            cursor = sort([("updated_at", -1), ("document_id", 1)])
        skip = getattr(cursor, "skip", None)
        if callable(skip):
            cursor = skip((page - 1) * page_size)
        limit = getattr(cursor, "limit", None)
        if callable(limit):
            cursor = limit(page_size)
        else:
            cursor = list(cursor)[(page - 1) * page_size : page * page_size]
        return SourceDocumentPage(
            tuple(model for raw in cursor if (model := _model(raw)) is not None),
            page,
            page_size,
            total,
        )

    def update_metadata(
        self,
        document_id: str,
        changes: Mapping[str, Any],
    ) -> SourceDocument | None:
        unexpected = set(changes) - self.MUTABLE_METADATA_FIELDS
        if unexpected:
            raise ValueError(f"Unsupported Source Document metadata fields: {sorted(unexpected)}")
        current = self.get_by_id(document_id)
        if current is None:
            return None
        payload = current.model_dump(mode="python")
        payload.update(dict(changes))
        payload["updated_at"] = utc_now()
        candidate = SourceDocument.model_validate(payload)
        try:
            result = self._collection.replace_one(
                {"document_id": document_id},
                _mongo_document(candidate),
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise SourceDocumentRepositoryConflictError(
                f"Concurrent Source Document conflict: {document_id}"
            ) from exc
        return candidate if getattr(result, "matched_count", 0) else None

    def replace(self, document: SourceDocument) -> SourceDocument | None:
        try:
            result = self._collection.replace_one(
                {"document_id": document.document_id},
                _mongo_document(document),
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise SourceDocumentRepositoryConflictError(
                f"Concurrent Source Document conflict: {document.document_id}"
            ) from exc
        return document if getattr(result, "matched_count", 0) else None

    def archive(self, document_id: str) -> SourceDocument | None:
        current = self.get_by_id(document_id)
        if current is None or current.status == DocumentStatus.ARCHIVED:
            return current
        return self.replace(SourceDocument.model_validate(current.archived().model_dump()))

    def reactivate(self, document_id: str) -> SourceDocument | None:
        current = self.get_by_id(document_id)
        if current is None or current.status == DocumentStatus.ACTIVE:
            return current
        return self.replace(SourceDocument.model_validate(current.reactivated().model_dump()))

    def count_for_reference(self, reference_id: str) -> int:
        return int(self._collection.count_documents({"reference_id": reference_id}))

    def count_for_source(self, source_id: str) -> int:
        return int(self._collection.count_documents({"source_id": source_id}))


__all__ = [
    "SourceDocumentPage",
    "SourceDocumentRepository",
    "SourceDocumentRepositoryConflictError",
    "SourceDocumentRepositoryError",
]

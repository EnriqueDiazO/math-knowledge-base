"""Lazy MongoDB repositories for S4 intellectual reading work."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from mathmongo.reading_annotations.errors import ReadingAnnotationConflictError
from mathmongo.reading_annotations.errors import ReadingAnnotationRepositoryError
from mathmongo.reading_annotations.indexes import CONCEPT_EVIDENCE_LINKS_COLLECTION
from mathmongo.reading_annotations.indexes import DOCUMENT_ANNOTATIONS_COLLECTION
from mathmongo.reading_annotations.indexes import READING_NOTES_COLLECTION
from mathmongo.reading_annotations.models import AnnotationKind
from mathmongo.reading_annotations.models import AnnotationStatus
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import EvidenceLinkStatus
from mathmongo.reading_annotations.models import ReadingNote
from mathmongo.reading_annotations.models import ReadingNoteStatus
from mathmongo.reading_annotations.models import ReadingNoteType
from mathmongo.reading_annotations.models import utc_now
from mathmongo.reading_annotations.models import validate_annotation_id
from mathmongo.reading_annotations.models import validate_evidence_link_id
from mathmongo.reading_annotations.models import validate_note_id

T = TypeVar("T", bound=BaseModel)
MAX_PAGE_SIZE = 100
MAX_SEARCH_LENGTH = 200


@dataclass(frozen=True, slots=True)
class S4Page(Generic[T]):
    items: tuple[T, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


AnnotationPage = S4Page[DocumentAnnotation]
ReadingNotePage = S4Page[ReadingNote]
ConceptEvidencePage = S4Page[ConceptEvidenceLink]


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    return page, page_size


def _search_pattern(query: str) -> str:
    if not isinstance(query, str):
        raise TypeError("search query must be text")
    value = query.strip()
    if not value:
        raise ValueError("search query cannot be empty")
    if len(value) > MAX_SEARCH_LENGTH:
        raise ValueError(f"search query cannot exceed {MAX_SEARCH_LENGTH} characters")
    return re.escape(value)


def _aware_utc(value: Any) -> Any:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _payload(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    payload.pop("_id", None)
    for field in ("created_at", "updated_at", "archived_at"):
        if field in payload:
            payload[field] = _aware_utc(payload[field])
    return payload


def _model(document: Any, model_type: type[T]) -> T | None:
    if document is None:
        return None
    return model_type.model_validate(_payload(document))


def _mongo_document(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="python")


def _page(
    collection: Any,
    query: dict[str, Any],
    *,
    page: int,
    page_size: int,
    sort: list[tuple[str, int]],
    model_type: type[T],
) -> S4Page[T]:
    page, page_size = _pagination(page, page_size)
    total = int(collection.count_documents(query))
    cursor = collection.find(query).sort(sort).skip((page - 1) * page_size).limit(page_size)
    items = tuple(item for raw in cursor if (item := _model(raw, model_type)) is not None)
    return S4Page(items, page, page_size, total)


class AnnotationRepository:
    COLLECTION = DOCUMENT_ANNOTATIONS_COLLECTION

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("AnnotationRepository requires an explicit database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def insert(self, annotation: DocumentAnnotation | Mapping[str, Any]) -> DocumentAnnotation:
        candidate = (
            annotation
            if isinstance(annotation, DocumentAnnotation)
            else DocumentAnnotation.model_validate(annotation)
        )
        try:
            self._collection.insert_one(_mongo_document(candidate))
        except DuplicateKeyError as exc:
            raise ReadingAnnotationConflictError(
                f"Annotation identity already exists: {candidate.annotation_id}"
            ) from exc
        except Exception as exc:
            raise ReadingAnnotationRepositoryError("Annotation insert failed") from exc
        return candidate

    def get_by_id(self, annotation_id: str) -> DocumentAnnotation | None:
        validate_annotation_id(annotation_id)
        return _model(
            self._collection.find_one({"annotation_id": annotation_id}),
            DocumentAnnotation,
        )

    def list_by_document(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
        status: AnnotationStatus | str | None = AnnotationStatus.ACTIVE,
        kind: AnnotationKind | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AnnotationPage:
        query: dict[str, Any] = {"document_id": document_id, "user_scope": user_scope}
        if status is not None:
            query["status"] = AnnotationStatus(status).value
        if kind is not None:
            query["kind"] = AnnotationKind(kind).value
        return _page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("annotation_id", 1)],
            model_type=DocumentAnnotation,
        )

    def list_by_source(
        self,
        source_id: str,
        *,
        user_scope: str = "local",
        status: AnnotationStatus | str | None = AnnotationStatus.ACTIVE,
        kind: AnnotationKind | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AnnotationPage:
        query: dict[str, Any] = {"source_id": source_id, "user_scope": user_scope}
        if status is not None:
            query["status"] = AnnotationStatus(status).value
        if kind is not None:
            query["kind"] = AnnotationKind(kind).value
        return _page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("annotation_id", 1)],
            model_type=DocumentAnnotation,
        )

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        source_id: str | None = None,
        user_scope: str = "local",
        status: AnnotationStatus | str | None = AnnotationStatus.ACTIVE,
        kind: AnnotationKind | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AnnotationPage:
        pattern = _search_pattern(query)
        selector: dict[str, Any] = {
            "user_scope": user_scope,
            "$or": [
                {"body": {"$regex": pattern, "$options": "i"}},
                {"quote_text": {"$regex": pattern, "$options": "i"}},
                {"tags": {"$regex": pattern, "$options": "i"}},
                {"page_label": {"$regex": pattern, "$options": "i"}},
            ],
        }
        if document_id is not None:
            selector["document_id"] = document_id
        if source_id is not None:
            selector["source_id"] = source_id
        if status is not None:
            selector["status"] = AnnotationStatus(status).value
        if kind is not None:
            selector["kind"] = AnnotationKind(kind).value
        return _page(
            self._collection,
            selector,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("annotation_id", 1)],
            model_type=DocumentAnnotation,
        )

    def _replace(self, annotation: DocumentAnnotation) -> DocumentAnnotation | None:
        try:
            result = self._collection.replace_one(
                {"annotation_id": annotation.annotation_id},
                _mongo_document(annotation),
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise ReadingAnnotationConflictError("Concurrent annotation conflict") from exc
        except Exception as exc:
            raise ReadingAnnotationRepositoryError("Annotation update failed") from exc
        return annotation if getattr(result, "matched_count", 0) else None

    def update_content(
        self,
        annotation_id: str,
        *,
        kind: AnnotationKind | str,
        page_number: int | None,
        page_label: str | None,
        quote_text: str | None,
        body: str,
        color_label: str | None,
        tags: list[str] | tuple[str, ...] | None = None,
        at: datetime | None = None,
    ) -> DocumentAnnotation | None:
        current = self.get_by_id(annotation_id)
        if current is None:
            return None
        payload = current.model_dump(mode="python")
        payload.update(
            {
                "kind": kind,
                "page_number": page_number,
                "page_label": page_label,
                "quote_text": quote_text,
                "body": body,
                "color_label": color_label,
                "updated_at": at or utc_now(),
            }
        )
        if tags is not None:
            payload["tags"] = list(tags)
        return self._replace(DocumentAnnotation.model_validate(payload))

    def update_tags(
        self,
        annotation_id: str,
        tags: list[str] | tuple[str, ...],
        *,
        at: datetime | None = None,
    ) -> DocumentAnnotation | None:
        current = self.get_by_id(annotation_id)
        if current is None:
            return None
        payload = current.model_dump(mode="python")
        payload.update({"tags": list(tags), "updated_at": at or utc_now()})
        return self._replace(DocumentAnnotation.model_validate(payload))

    def archive(
        self, annotation_id: str, *, at: datetime | None = None
    ) -> DocumentAnnotation | None:
        current = self.get_by_id(annotation_id)
        if current is None or current.status == AnnotationStatus.ARCHIVED:
            return current
        timestamp = at or utc_now()
        payload = current.model_dump(mode="python")
        payload.update(
            {"status": AnnotationStatus.ARCHIVED, "updated_at": timestamp, "archived_at": timestamp}
        )
        return self._replace(DocumentAnnotation.model_validate(payload))

    def reactivate(
        self,
        annotation_id: str,
        *,
        at: datetime | None = None,
    ) -> DocumentAnnotation | None:
        current = self.get_by_id(annotation_id)
        if current is None or current.status == AnnotationStatus.ACTIVE:
            return current
        payload = current.model_dump(mode="python")
        payload.update(
            {"status": AnnotationStatus.ACTIVE, "updated_at": at or utc_now(), "archived_at": None}
        )
        return self._replace(DocumentAnnotation.model_validate(payload))

    def count_by_document(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
        status: AnnotationStatus | str | None = None,
    ) -> int:
        query: dict[str, Any] = {"document_id": document_id, "user_scope": user_scope}
        if status is not None:
            query["status"] = AnnotationStatus(status).value
        return int(self._collection.count_documents(query))


class ReadingNoteRepository:
    COLLECTION = READING_NOTES_COLLECTION

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReadingNoteRepository requires an explicit database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def insert(self, note: ReadingNote | Mapping[str, Any]) -> ReadingNote:
        candidate = note if isinstance(note, ReadingNote) else ReadingNote.model_validate(note)
        try:
            self._collection.insert_one(_mongo_document(candidate))
        except DuplicateKeyError as exc:
            raise ReadingAnnotationConflictError(
                f"Reading Note identity already exists: {candidate.note_id}"
            ) from exc
        except Exception as exc:
            raise ReadingAnnotationRepositoryError("Reading Note insert failed") from exc
        return candidate

    def get_by_id(self, note_id: str) -> ReadingNote | None:
        validate_note_id(note_id)
        return _model(self._collection.find_one({"note_id": note_id}), ReadingNote)

    def _list(
        self,
        query: dict[str, Any],
        *,
        page: int,
        page_size: int,
    ) -> ReadingNotePage:
        return _page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("note_id", 1)],
            model_type=ReadingNote,
        )

    def list_by_document(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
        status: ReadingNoteStatus | str | None = ReadingNoteStatus.ACTIVE,
        note_type: ReadingNoteType | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ReadingNotePage:
        query: dict[str, Any] = {"document_id": document_id, "user_scope": user_scope}
        if status is not None:
            query["status"] = ReadingNoteStatus(status).value
        if note_type is not None:
            query["note_type"] = ReadingNoteType(note_type).value
        return self._list(query, page=page, page_size=page_size)

    def list_by_source(
        self,
        source_id: str,
        *,
        user_scope: str = "local",
        source_only: bool = False,
        status: ReadingNoteStatus | str | None = ReadingNoteStatus.ACTIVE,
        note_type: ReadingNoteType | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ReadingNotePage:
        query: dict[str, Any] = {"source_id": source_id, "user_scope": user_scope}
        if source_only:
            query["document_id"] = None
        if status is not None:
            query["status"] = ReadingNoteStatus(status).value
        if note_type is not None:
            query["note_type"] = ReadingNoteType(note_type).value
        return self._list(query, page=page, page_size=page_size)

    def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        source_id: str | None = None,
        user_scope: str = "local",
        source_only: bool = False,
        status: ReadingNoteStatus | str | None = ReadingNoteStatus.ACTIVE,
        note_type: ReadingNoteType | str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> ReadingNotePage:
        pattern = _search_pattern(query)
        selector: dict[str, Any] = {
            "user_scope": user_scope,
            "$or": [
                {"title": {"$regex": pattern, "$options": "i"}},
                {"body": {"$regex": pattern, "$options": "i"}},
                {"tags": {"$regex": pattern, "$options": "i"}},
            ],
        }
        if document_id is not None:
            selector["document_id"] = document_id
        if source_id is not None:
            selector["source_id"] = source_id
        if source_only:
            selector["document_id"] = None
        if status is not None:
            selector["status"] = ReadingNoteStatus(status).value
        if note_type is not None:
            selector["note_type"] = ReadingNoteType(note_type).value
        return self._list(selector, page=page, page_size=page_size)

    def _replace(self, note: ReadingNote) -> ReadingNote | None:
        try:
            result = self._collection.replace_one(
                {"note_id": note.note_id},
                _mongo_document(note),
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise ReadingAnnotationConflictError("Concurrent Reading Note conflict") from exc
        except Exception as exc:
            raise ReadingAnnotationRepositoryError("Reading Note update failed") from exc
        return note if getattr(result, "matched_count", 0) else None

    def update_content(
        self,
        note_id: str,
        *,
        title: str,
        body: str,
        note_type: ReadingNoteType | str,
        document_id: str | None,
        page_start: int | None,
        page_end: int | None,
        reference_id: str | None,
        tags: list[str] | tuple[str, ...] | None = None,
        at: datetime | None = None,
    ) -> ReadingNote | None:
        current = self.get_by_id(note_id)
        if current is None:
            return None
        payload = current.model_dump(mode="python")
        payload.update(
            {
                "title": title,
                "body": body,
                "note_type": note_type,
                "document_id": document_id,
                "page_start": page_start,
                "page_end": page_end,
                "reference_id": reference_id,
                "updated_at": at or utc_now(),
            }
        )
        if tags is not None:
            payload["tags"] = list(tags)
        return self._replace(ReadingNote.model_validate(payload))

    def update_tags(
        self,
        note_id: str,
        tags: list[str] | tuple[str, ...],
        *,
        at: datetime | None = None,
    ) -> ReadingNote | None:
        current = self.get_by_id(note_id)
        if current is None:
            return None
        payload = current.model_dump(mode="python")
        payload.update({"tags": list(tags), "updated_at": at or utc_now()})
        return self._replace(ReadingNote.model_validate(payload))

    def archive(self, note_id: str, *, at: datetime | None = None) -> ReadingNote | None:
        current = self.get_by_id(note_id)
        if current is None or current.status == ReadingNoteStatus.ARCHIVED:
            return current
        timestamp = at or utc_now()
        payload = current.model_dump(mode="python")
        payload.update(
            {
                "status": ReadingNoteStatus.ARCHIVED,
                "updated_at": timestamp,
                "archived_at": timestamp,
            }
        )
        return self._replace(ReadingNote.model_validate(payload))

    def reactivate(self, note_id: str, *, at: datetime | None = None) -> ReadingNote | None:
        current = self.get_by_id(note_id)
        if current is None or current.status == ReadingNoteStatus.ACTIVE:
            return current
        payload = current.model_dump(mode="python")
        payload.update(
            {"status": ReadingNoteStatus.ACTIVE, "updated_at": at or utc_now(), "archived_at": None}
        )
        return self._replace(ReadingNote.model_validate(payload))

    def count_by_source(
        self,
        source_id: str,
        *,
        user_scope: str = "local",
        status: ReadingNoteStatus | str | None = None,
    ) -> int:
        query: dict[str, Any] = {"source_id": source_id, "user_scope": user_scope}
        if status is not None:
            query["status"] = ReadingNoteStatus(status).value
        return int(self._collection.count_documents(query))


class ConceptEvidenceRepository:
    COLLECTION = CONCEPT_EVIDENCE_LINKS_COLLECTION

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ConceptEvidenceRepository requires an explicit database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def insert(self, link: ConceptEvidenceLink | Mapping[str, Any]) -> ConceptEvidenceLink:
        candidate = (
            link
            if isinstance(link, ConceptEvidenceLink)
            else ConceptEvidenceLink.model_validate(link)
        )
        try:
            self._collection.insert_one(_mongo_document(candidate))
        except DuplicateKeyError as exc:
            raise ReadingAnnotationConflictError(
                f"Concept evidence identity already exists: {candidate.evidence_link_id}"
            ) from exc
        except Exception as exc:
            raise ReadingAnnotationRepositoryError("Concept evidence insert failed") from exc
        return candidate

    def get_by_id(self, evidence_link_id: str) -> ConceptEvidenceLink | None:
        validate_evidence_link_id(evidence_link_id)
        return _model(
            self._collection.find_one({"evidence_link_id": evidence_link_id}),
            ConceptEvidenceLink,
        )

    @staticmethod
    def exact_identity(link: ConceptEvidenceLink) -> dict[str, Any]:
        return {
            "concept_legacy_source": link.concept_legacy_source,
            "concept_legacy_id": link.concept_legacy_id,
            "source_id": link.source_id,
            "reference_id": link.reference_id,
            "document_id": link.document_id,
            "annotation_id": link.annotation_id,
            "note_id": link.note_id,
            "page_number": link.page_number,
            "link_type": link.link_type.value,
        }

    def find_exact(self, link: ConceptEvidenceLink) -> ConceptEvidenceLink | None:
        return _model(self._collection.find_one(self.exact_identity(link)), ConceptEvidenceLink)

    def _list(
        self,
        query: dict[str, Any],
        *,
        page: int,
        page_size: int,
    ) -> ConceptEvidencePage:
        return _page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("evidence_link_id", 1)],
            model_type=ConceptEvidenceLink,
        )

    def list_by_concept(
        self,
        concept_legacy_id: str,
        concept_legacy_source: str,
        *,
        status: EvidenceLinkStatus | str | None = EvidenceLinkStatus.ACTIVE,
        page: int = 1,
        page_size: int = 50,
    ) -> ConceptEvidencePage:
        query: dict[str, Any] = {
            "concept_legacy_id": concept_legacy_id,
            "concept_legacy_source": concept_legacy_source,
        }
        if status is not None:
            query["status"] = EvidenceLinkStatus(status).value
        return self._list(query, page=page, page_size=page_size)

    def list_by_document(
        self,
        document_id: str,
        *,
        status: EvidenceLinkStatus | str | None = EvidenceLinkStatus.ACTIVE,
        page: int = 1,
        page_size: int = 50,
    ) -> ConceptEvidencePage:
        """Join indirect targets before server-side sorting and pagination."""
        page, page_size = _pagination(page, page_size)
        target_match: dict[str, Any] = {
            "$or": [
                {"document_id": document_id},
                {"_annotation.document_id": document_id},
                {"_note.document_id": document_id},
            ]
        }
        if status is not None:
            target_match["status"] = EvidenceLinkStatus(status).value
        pipeline = [
            {
                "$lookup": {
                    "from": DOCUMENT_ANNOTATIONS_COLLECTION,
                    "localField": "annotation_id",
                    "foreignField": "annotation_id",
                    "as": "_annotation",
                }
            },
            {
                "$lookup": {
                    "from": READING_NOTES_COLLECTION,
                    "localField": "note_id",
                    "foreignField": "note_id",
                    "as": "_note",
                }
            },
            {"$match": target_match},
            {"$sort": {"updated_at": -1, "evidence_link_id": 1}},
            {
                "$facet": {
                    "items": [
                        {"$skip": (page - 1) * page_size},
                        {"$limit": page_size},
                        {"$unset": ["_annotation", "_note"]},
                    ],
                    "total": [{"$count": "value"}],
                }
            },
        ]
        rows = list(self._collection.aggregate(pipeline))
        facet = rows[0] if rows else {"items": [], "total": []}
        total_rows = facet.get("total", [])
        total = int(total_rows[0].get("value", 0)) if total_rows else 0
        items = tuple(
            item
            for raw in facet.get("items", [])
            if (item := _model(raw, ConceptEvidenceLink)) is not None
        )
        return S4Page(items, page, page_size, total)

    def list_by_annotation(
        self,
        annotation_id: str,
        *,
        status: EvidenceLinkStatus | str | None = EvidenceLinkStatus.ACTIVE,
        page: int = 1,
        page_size: int = 50,
    ) -> ConceptEvidencePage:
        query: dict[str, Any] = {"annotation_id": annotation_id}
        if status is not None:
            query["status"] = EvidenceLinkStatus(status).value
        return self._list(query, page=page, page_size=page_size)

    def list_by_note(
        self,
        note_id: str,
        *,
        status: EvidenceLinkStatus | str | None = EvidenceLinkStatus.ACTIVE,
        page: int = 1,
        page_size: int = 50,
    ) -> ConceptEvidencePage:
        query: dict[str, Any] = {"note_id": note_id}
        if status is not None:
            query["status"] = EvidenceLinkStatus(status).value
        return self._list(query, page=page, page_size=page_size)

    def list_by_source(
        self,
        source_id: str,
        *,
        status: EvidenceLinkStatus | str | None = EvidenceLinkStatus.ACTIVE,
        page: int = 1,
        page_size: int = 50,
    ) -> ConceptEvidencePage:
        query: dict[str, Any] = {"source_id": source_id}
        if status is not None:
            query["status"] = EvidenceLinkStatus(status).value
        return self._list(query, page=page, page_size=page_size)

    def search(
        self,
        query: str,
        *,
        source_id: str | None = None,
        status: EvidenceLinkStatus | str | None = EvidenceLinkStatus.ACTIVE,
        page: int = 1,
        page_size: int = 50,
    ) -> ConceptEvidencePage:
        pattern = _search_pattern(query)
        selector: dict[str, Any] = {
            "$or": [
                {"concept_legacy_id": {"$regex": pattern, "$options": "i"}},
                {"concept_legacy_source": {"$regex": pattern, "$options": "i"}},
                {"comment": {"$regex": pattern, "$options": "i"}},
            ]
        }
        if source_id is not None:
            selector["source_id"] = source_id
        if status is not None:
            selector["status"] = EvidenceLinkStatus(status).value
        return self._list(selector, page=page, page_size=page_size)

    def _replace(self, link: ConceptEvidenceLink) -> ConceptEvidenceLink | None:
        try:
            result = self._collection.replace_one(
                {"evidence_link_id": link.evidence_link_id},
                _mongo_document(link),
                upsert=False,
            )
        except DuplicateKeyError as exc:
            raise ReadingAnnotationConflictError("Concurrent concept evidence conflict") from exc
        except Exception as exc:
            raise ReadingAnnotationRepositoryError("Concept evidence update failed") from exc
        return link if getattr(result, "matched_count", 0) else None

    def archive(
        self,
        evidence_link_id: str,
        *,
        at: datetime | None = None,
    ) -> ConceptEvidenceLink | None:
        current = self.get_by_id(evidence_link_id)
        if current is None or current.status == EvidenceLinkStatus.ARCHIVED:
            return current
        timestamp = at or utc_now()
        payload = current.model_dump(mode="python")
        payload.update(
            {
                "status": EvidenceLinkStatus.ARCHIVED,
                "updated_at": timestamp,
                "archived_at": timestamp,
            }
        )
        return self._replace(ConceptEvidenceLink.model_validate(payload))

    def reactivate(
        self,
        evidence_link_id: str,
        *,
        at: datetime | None = None,
    ) -> ConceptEvidenceLink | None:
        current = self.get_by_id(evidence_link_id)
        if current is None or current.status == EvidenceLinkStatus.ACTIVE:
            return current
        payload = current.model_dump(mode="python")
        payload.update(
            {
                "status": EvidenceLinkStatus.ACTIVE,
                "updated_at": at or utc_now(),
                "archived_at": None,
            }
        )
        return self._replace(ConceptEvidenceLink.model_validate(payload))

    def count_by_concept(
        self,
        concept_legacy_id: str,
        concept_legacy_source: str,
        *,
        status: EvidenceLinkStatus | str | None = None,
    ) -> int:
        query: dict[str, Any] = {
            "concept_legacy_id": concept_legacy_id,
            "concept_legacy_source": concept_legacy_source,
        }
        if status is not None:
            query["status"] = EvidenceLinkStatus(status).value
        return int(self._collection.count_documents(query))


__all__ = [
    "AnnotationPage",
    "AnnotationRepository",
    "ConceptEvidencePage",
    "ConceptEvidenceRepository",
    "ReadingNotePage",
    "ReadingNoteRepository",
    "S4Page",
]

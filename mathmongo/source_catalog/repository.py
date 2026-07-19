"""MongoDB repositories for Source Catalog entities.

Repositories never connect, select a database, create a collection, or create
an index. Every operation is scoped to the database supplied by its caller.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any
from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import utc_now
from mathmongo.source_catalog.normalization import suggestion_regex_pattern
from mathmongo.source_catalog.normalization import url_regex_pattern

T = TypeVar("T")
MAX_PAGE_SIZE = 100
MAX_SEARCH_LENGTH = 200


class RepositoryError(RuntimeError):
    """Base class for controlled Source Catalog persistence failures."""


class RepositoryConflictError(RepositoryError):
    """A unique-key conflict or concurrent conflicting write."""


class ImmutableFieldError(RepositoryError):
    """A requested update attempted to change immutable domain data."""


class PhysicalDeletionBlockedError(RepositoryError):
    """Physical deletion was rejected because links still exist."""

    def __init__(self, entity_id: str, blockers: tuple[str, ...]) -> None:
        """Retain machine-readable blockers for the service layer."""
        self.entity_id = entity_id
        self.blockers = blockers
        super().__init__(f"Physical deletion blocked for {entity_id}: {', '.join(blockers)}")


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T]):
    """One bounded, stable page and its server-side total."""

    items: tuple[T, ...]
    page: int
    page_size: int
    total: int

    @property
    def pages(self) -> int:
        """Return the total number of non-empty pages."""
        return (self.total + self.page_size - 1) // self.page_size if self.total else 0


def _pagination(page: int, page_size: int) -> tuple[int, int]:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page must be a positive integer")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        raise ValueError("page_size must be a positive integer")
    return page, min(page_size, MAX_PAGE_SIZE)


def _search_pattern(term: str) -> tuple[str, str]:
    if not isinstance(term, str):
        raise TypeError("search term must be text")
    value = term.strip()
    if not value:
        raise ValueError("search term cannot be empty")
    if len(value) > MAX_SEARCH_LENGTH:
        raise ValueError(f"search term cannot exceed {MAX_SEARCH_LENGTH} characters")
    return value, re.escape(value)


def _mongo_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return {key: _mongo_value(item) for key, item in value.model_dump(mode="python").items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _mongo_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mongo_value(item) for item in value]
    if isinstance(value, list):
        return [_mongo_value(item) for item in value]
    return value


def _mongo_document(model: BaseModel) -> dict[str, Any]:
    return _mongo_value(model)


def _filter_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _aware_utc(value: Any) -> Any:
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hydrate_catalog_datetimes(document: Mapping[str, Any]) -> dict[str, Any]:
    """Attach UTC to BSON datetimes returned naive by the legacy MongoClient."""
    hydrated = dict(document)
    for field_name in (
        "created_at",
        "updated_at",
        "archived_at",
        "accessed_at",
    ):
        if field_name in hydrated:
            hydrated[field_name] = _aware_utc(hydrated[field_name])
    provenance = hydrated.get("provenance")
    if isinstance(provenance, Mapping):
        provenance = dict(provenance)
        if "imported_at" in provenance:
            provenance["imported_at"] = _aware_utc(provenance["imported_at"])
        hydrated["provenance"] = provenance
    return hydrated


def _model_document(document: Mapping[str, Any] | None, model_type: type[T]) -> T | None:
    if document is None:
        return None
    data = _hydrate_catalog_datetimes(document)
    data.pop("_id", None)
    return model_type.model_validate(data)  # type: ignore[attr-defined,no-any-return]


def _cursor_page(
    collection: Any,
    query: dict[str, Any],
    *,
    page: int,
    page_size: int,
    sort: list[tuple[str, int]],
    model_type: type[T],
) -> PageResult[T]:
    page, page_size = _pagination(page, page_size)
    total = int(collection.count_documents(query))
    cursor = collection.find(query).sort(sort).skip((page - 1) * page_size).limit(page_size)
    items = tuple(_model_document(document, model_type) for document in cursor)
    return PageResult(items=items, page=page, page_size=page_size, total=total)  # type: ignore[arg-type]


class SourceRepository:
    """Persistence boundary for the `sources` collection of one database."""

    COLLECTION = "sources"
    _IMMUTABLE_FIELDS = frozenset({"_id", "source_id", "schema_version", "created_at"})
    _MUTABLE_FIELDS = frozenset(
        {
            "name",
            "name_normalized",
            "aliases",
            "source_type",
            "description",
            "language",
            "tags",
            "status",
            "rights_default",
            "legacy",
            "updated_at",
            "archived_at",
        }
    )

    def __init__(self, database: Any) -> None:
        """Retain the explicit database without touching a collection."""
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("SourceRepository requires an explicit MongoDB database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def insert(self, source: Source | Mapping[str, Any]) -> Source:
        """Validate and insert one Source without an upsert."""
        model = source if isinstance(source, Source) else Source.model_validate(source)
        try:
            self._collection.insert_one(_mongo_document(model))
        except DuplicateKeyError as exc:
            raise RepositoryConflictError(f"Source ID already exists: {model.source_id}") from exc
        return model

    def get_by_id(self, source_id: str) -> Source | None:
        """Load a Source by stable domain ID."""
        return _model_document(
            self._collection.find_one({"source_id": source_id}),
            Source,
        )

    def get_by_ids(self, source_ids: Iterable[str]) -> tuple[Source, ...]:
        """Load a caller-bounded set of Sources with one server-side query."""
        requested = tuple(dict.fromkeys(str(source_id) for source_id in source_ids))
        if not requested:
            return ()
        return tuple(
            model
            for document in self._collection.find(
                {"source_id": {"$in": list(requested)}}
            ).limit(len(requested))
            if (model := _model_document(document, Source)) is not None
        )

    def count(
        self,
        *,
        status: str | None = None,
        source_type: str | None = None,
    ) -> int:
        """Count Sources with optional status and type filters."""
        query: dict[str, Any] = {}
        if status is not None:
            query["status"] = _filter_value(status)
        if source_type is not None:
            query["source_type"] = _filter_value(source_type)
        return int(self._collection.count_documents(query))

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        source_type: str | None = None,
        tag: str | None = None,
    ) -> PageResult[Source]:
        """List a bounded Source page with stable ordering."""
        query: dict[str, Any] = {}
        if status is not None:
            query["status"] = _filter_value(status)
        if source_type is not None:
            query["source_type"] = _filter_value(source_type)
        if tag is not None:
            query["tags"] = tag
        return _cursor_page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("source_id", 1)],
            model_type=Source,
        )

    def search(
        self,
        term: str,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        source_type: str | None = None,
        tag: str | None = None,
    ) -> PageResult[Source]:
        """Search approved Source fields with an escaped bounded regex."""
        _value, escaped = _search_pattern(term)
        regex = {"$regex": escaped, "$options": "i"}
        query: dict[str, Any] = {
            "$or": [
                {"source_id": regex},
                {"name": regex},
                {"aliases.value": regex},
                {"source_type": regex},
                {"tags": regex},
                {"status": regex},
            ]
        }
        if status is not None:
            query["status"] = _filter_value(status)
        if source_type is not None:
            query["source_type"] = _filter_value(source_type)
        if tag is not None:
            query["tags"] = tag
        return _cursor_page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("name_normalized", 1), ("source_id", 1)],
            model_type=Source,
        )

    def update(self, source_id: str, changes: Mapping[str, Any]) -> Source | None:
        """Apply a validated controlled `$set` without changing the ID."""
        forbidden = set(changes) & self._IMMUTABLE_FIELDS
        unknown = set(changes) - self._MUTABLE_FIELDS
        if forbidden or unknown:
            fields = sorted(forbidden | unknown)
            raise ImmutableFieldError(f"Unsupported or immutable Source fields: {fields}")
        current = self.get_by_id(source_id)
        if current is None:
            return None
        candidate_data = current.model_dump(mode="python")
        candidate_data.update(dict(changes))
        candidate_data["updated_at"] = changes.get("updated_at", utc_now())
        candidate = Source.model_validate(candidate_data)
        candidate_dump = _mongo_document(candidate)
        set_fields = {key: candidate_dump[key] for key in changes}
        set_fields["updated_at"] = candidate_dump["updated_at"]
        if "name" in changes:
            set_fields["name_normalized"] = candidate_dump["name_normalized"]
        try:
            result = self._collection.update_one(
                {"source_id": source_id},
                {"$set": set_fields},
            )
        except DuplicateKeyError as exc:
            raise RepositoryConflictError(f"Concurrent Source conflict: {source_id}") from exc
        if not result.matched_count:
            return None
        return self.get_by_id(source_id)

    def archive(self, source_id: str) -> Source | None:
        """Archive a Source idempotently."""
        current = self.get_by_id(source_id)
        if current is None:
            return None
        archived = current.archived()
        if archived is current:
            return current
        return self.update(
            source_id,
            {
                "status": archived.status,
                "archived_at": archived.archived_at,
                "updated_at": archived.updated_at,
            },
        )

    def reactivate(self, source_id: str) -> Source | None:
        """Reactivate an archived Source idempotently."""
        current = self.get_by_id(source_id)
        if current is None:
            return None
        active = current.reactivated()
        if active is current:
            return current
        return self.update(
            source_id,
            {
                "status": active.status,
                "archived_at": None,
                "updated_at": active.updated_at,
            },
        )

    def duplicate_candidates(self, source: Source | Mapping[str, Any]) -> list[Source]:
        """Fetch a bounded server-side set for pure duplicate classification."""
        candidate = source if isinstance(source, Source) else Source.model_validate(source)
        bounded_aliases = candidate.aliases[: MAX_PAGE_SIZE - 1]
        display_values = [candidate.name, *(alias.value for alias in bounded_aliases)]
        normalized = [candidate.name_normalized, *(alias.normalized for alias in bounded_aliases)]
        identity_alternatives: list[dict[str, Any]] = [
            {"name_normalized": {"$in": normalized}},
            {"aliases.normalized": {"$in": normalized}},
            {"name": {"$regex": f"^{re.escape(candidate.name)}$", "$options": "i"}},
        ]
        suggestion_alternatives: list[dict[str, Any]] = []
        for display_value in display_values:
            pattern = suggestion_regex_pattern(display_value)
            if pattern is None:
                continue
            regex = {"$regex": pattern, "$options": "i"}
            suggestion_alternatives.extend(({"name": regex}, {"aliases.value": regex}))

        results: list[Source] = []
        seen: set[str] = set()
        for alternatives in (identity_alternatives, suggestion_alternatives):
            if not alternatives or len(results) >= MAX_PAGE_SIZE:
                continue
            for document in self._collection.find({"$or": alternatives}).limit(MAX_PAGE_SIZE):
                model = _model_document(document, Source)
                if model is None or model.source_id in seen:
                    continue
                seen.add(model.source_id)
                results.append(model)
                if len(results) >= MAX_PAGE_SIZE:
                    break
        return results

    def deletion_blockers(self, source_id: str) -> tuple[str, ...]:
        """Inspect managed, Reference, and exact legacy links read-only."""
        source = self.get_by_id(source_id)
        if source is None:
            return ()
        blockers: list[str] = []
        linked_concepts = int(
            self.database["concepts"].count_documents({"source_id": source_id})
        )
        if linked_concepts:
            blockers.append(f"linked_concepts_by_source_id:{linked_concepts}")
        linked_latex_documents = int(
            self.database["latex_documents"].count_documents(
                {"source_id": source_id}
            )
        )
        if linked_latex_documents:
            blockers.append(
                "linked_latex_documents_by_source_id:"
                f"{linked_latex_documents}"
            )
        reference_count = int(
            self.database[ReferenceRepository.COLLECTION].count_documents(
                {"source_ids": source_id}
            )
        )
        if reference_count:
            blockers.append(f"references:{reference_count}")
        legacy_source_values = list(
            dict.fromkeys((source.name, *source.legacy.source_strings))
        )
        if legacy_source_values:
            legacy_count = int(
                self.database["concepts"].count_documents(
                    {"source": {"$in": legacy_source_values}}
                )
            )
            if legacy_count:
                blockers.append(f"legacy_concepts:{legacy_count}")
        return tuple(blockers)

    def physical_delete_if_unused(self, source_id: str) -> bool:
        """Delete only after rechecking all S1A Source blockers."""
        blockers = self.deletion_blockers(source_id)
        if blockers:
            raise PhysicalDeletionBlockedError(source_id, blockers)
        result = self._collection.delete_one({"source_id": source_id})
        return bool(result.deleted_count)


class ReferenceRepository:
    """Persistence boundary for the `references` collection of one database."""

    COLLECTION = "references"
    _IMMUTABLE_FIELDS = frozenset(
        {"_id", "reference_id", "schema_version", "created_at", "source_ids"}
    )
    _MUTABLE_FIELDS = frozenset(
        {
            "reference_type",
            "bibtex",
            "authors",
            "title",
            "year",
            "year_raw",
            "journal",
            "publisher",
            "volume",
            "number",
            "edition",
            "isbn",
            "doi",
            "doi_normalized",
            "url",
            "accessed_at",
            "language",
            "notes",
            "fingerprints",
            "provenance",
            "status",
            "updated_at",
            "archived_at",
        }
    )

    def __init__(self, database: Any) -> None:
        """Retain the explicit database without touching a collection."""
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReferenceRepository requires an explicit MongoDB database")
        self.database = database

    @property
    def _collection(self) -> Any:
        return self.database[self.COLLECTION]

    def insert(self, reference: Reference | Mapping[str, Any]) -> Reference:
        """Validate and insert one Reference without an upsert."""
        model = reference if isinstance(reference, Reference) else Reference.model_validate(reference)
        try:
            self._collection.insert_one(_mongo_document(model))
        except DuplicateKeyError as exc:
            raise RepositoryConflictError(
                f"Reference ID already exists: {model.reference_id}"
            ) from exc
        return model

    def get_by_id(self, reference_id: str) -> Reference | None:
        """Load a Reference by stable domain ID."""
        return _model_document(
            self._collection.find_one({"reference_id": reference_id}),
            Reference,
        )

    def count(
        self,
        *,
        status: str | None = None,
        source_id: str | None = None,
    ) -> int:
        """Count References with optional status and Source filters."""
        query: dict[str, Any] = {}
        if status is not None:
            query["status"] = _filter_value(status)
        if source_id is not None:
            query["source_ids"] = source_id
        return int(self._collection.count_documents(query))

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        source_id: str | None = None,
        reference_type: str | None = None,
        year: int | None = None,
    ) -> PageResult[Reference]:
        """List a bounded Reference page with stable ordering."""
        query: dict[str, Any] = {}
        if status is not None:
            query["status"] = _filter_value(status)
        if source_id is not None:
            query["source_ids"] = source_id
        if reference_type is not None:
            query["reference_type"] = _filter_value(reference_type)
        if year is not None:
            query["year"] = year
        return _cursor_page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("updated_at", -1), ("reference_id", 1)],
            model_type=Reference,
        )

    def list_quality_candidates(
        self,
        *,
        source_id: str,
        page_size: int = 100,
    ) -> PageResult[Reference]:
        """Return a bounded diagnostic projection that excludes BibTeX raw and notes."""
        _page, page_size = _pagination(1, page_size)
        query = {"source_ids": source_id}
        projection = {
            "_id": 0,
            "reference_id": 1,
            "source_ids": 1,
            "reference_type": 1,
            "bibtex.key": 1,
            "authors": 1,
            "title": 1,
            "year": 1,
            "year_raw": 1,
            "journal": 1,
            "publisher": 1,
            "isbn": 1,
            "doi": 1,
            "url": 1,
            "accessed_at": 1,
            "status": 1,
            "archived_at": 1,
        }
        total = int(self._collection.count_documents(query))
        cursor = (
            self._collection.find(query, projection)
            .sort([("updated_at", -1), ("reference_id", 1)])
            .limit(page_size)
        )
        items = tuple(
            model
            for document in cursor
            if (model := _model_document(document, Reference)) is not None
        )
        return PageResult(items=items, page=1, page_size=page_size, total=total)

    def search(
        self,
        term: str,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        source_id: str | None = None,
    ) -> PageResult[Reference]:
        """Search approved bibliographic fields with escaped input."""
        value, escaped = _search_pattern(term)
        regex = {"$regex": escaped, "$options": "i"}
        alternatives: list[dict[str, Any]] = [
            {"reference_id": regex},
            {"bibtex.key": regex},
            {"bibtex.key_normalized": regex},
            {"doi": regex},
            {"doi_normalized": regex},
            {"isbn": regex},
            {"fingerprints.isbn_normalized": regex},
            {"authors.family": regex},
            {"authors.given": regex},
            {"authors.literal": regex},
            {"title": regex},
            {"year_raw": regex},
            {"status": regex},
        ]
        if value.isdigit():
            alternatives.append({"year": int(value)})
        query: dict[str, Any] = {"$or": alternatives}
        if status is not None:
            query["status"] = _filter_value(status)
        if source_id is not None:
            query["source_ids"] = source_id
        return _cursor_page(
            self._collection,
            query,
            page=page,
            page_size=page_size,
            sort=[("year", -1), ("title", 1), ("reference_id", 1)],
            model_type=Reference,
        )

    def update(self, reference_id: str, changes: Mapping[str, Any]) -> Reference | None:
        """Apply a validated controlled `$set` without changing the ID."""
        forbidden = set(changes) & self._IMMUTABLE_FIELDS
        unknown = set(changes) - self._MUTABLE_FIELDS
        if forbidden or unknown:
            fields = sorted(forbidden | unknown)
            raise ImmutableFieldError(f"Unsupported or immutable Reference fields: {fields}")
        current = self.get_by_id(reference_id)
        if current is None:
            return None
        candidate_data = current.model_dump(mode="python")
        candidate_data.update(dict(changes))
        candidate_data["updated_at"] = changes.get("updated_at", utc_now())
        candidate = Reference.model_validate(candidate_data)
        candidate_dump = _mongo_document(candidate)
        derived = {"doi_normalized", "fingerprints", "provenance", "status"}
        set_fields = {key: candidate_dump[key] for key in set(changes) | derived}
        set_fields["updated_at"] = candidate_dump["updated_at"]
        try:
            result = self._collection.update_one(
                {"reference_id": reference_id},
                {"$set": set_fields},
            )
        except DuplicateKeyError as exc:
            raise RepositoryConflictError(
                f"Concurrent Reference conflict: {reference_id}"
            ) from exc
        if not result.matched_count:
            return None
        return self.get_by_id(reference_id)

    def archive(self, reference_id: str) -> Reference | None:
        """Archive a Reference idempotently."""
        current = self.get_by_id(reference_id)
        if current is None:
            return None
        archived = current.archived()
        if archived is current:
            return current
        return self.update(
            reference_id,
            {
                "status": archived.status,
                "archived_at": archived.archived_at,
                "updated_at": archived.updated_at,
            },
        )

    def reactivate(self, reference_id: str) -> Reference | None:
        """Reactivate a Reference while retaining review diagnostics."""
        current = self.get_by_id(reference_id)
        if current is None:
            return None
        active = current.reactivated()
        if active is current:
            return current
        return self.update(
            reference_id,
            {
                "status": active.status,
                "archived_at": None,
                "updated_at": active.updated_at,
            },
        )

    def associate_source(self, reference_id: str, source_id: str) -> Reference | None:
        """Associate a Source once using `$addToSet`."""
        current = self.get_by_id(reference_id)
        if current is None:
            return None
        associated = current.associated_with(source_id)
        if associated is current:
            return current
        result = self._collection.update_one(
            {"reference_id": reference_id},
            {
                "$addToSet": {"source_ids": source_id},
                "$set": {"updated_at": associated.updated_at},
            },
        )
        return self.get_by_id(reference_id) if result.matched_count else None

    def disassociate_source(self, reference_id: str, source_id: str) -> Reference | None:
        """Remove one Source association idempotently."""
        current = self.get_by_id(reference_id)
        if current is None:
            return None
        disassociated = current.disassociated_from(source_id)
        if disassociated is current:
            return current
        result = self._collection.update_one(
            {"reference_id": reference_id},
            {
                "$pull": {"source_ids": source_id},
                "$set": {"updated_at": disassociated.updated_at},
            },
        )
        return self.get_by_id(reference_id) if result.matched_count else None

    def duplicate_candidates(
        self,
        reference: Reference | Mapping[str, Any],
    ) -> list[Reference]:
        """Fetch a bounded server-side set for pure duplicate classification."""
        candidate = (
            reference if isinstance(reference, Reference) else Reference.model_validate(reference)
        )
        identity_groups: list[list[dict[str, Any]]] = []
        if candidate.doi_normalized:
            identity_groups.append([{"doi_normalized": candidate.doi_normalized}])
        if candidate.fingerprints.isbn_normalized:
            identity_groups.append(
                [
                    {
                        "fingerprints.isbn_normalized": {
                            "$in": candidate.fingerprints.isbn_normalized
                        }
                    }
                ]
            )
        if candidate.bibtex.key_normalized:
            identity_groups.append(
                [{"bibtex.key_normalized": candidate.bibtex.key_normalized}]
            )
        if candidate.fingerprints.author_title_year:
            identity_groups.append(
                [
                    {
                        "fingerprints.author_title_year": (
                            candidate.fingerprints.author_title_year
                        )
                    }
                ]
            )
        suggestion_alternatives: list[dict[str, Any]] = []
        if candidate.title and (pattern := suggestion_regex_pattern(candidate.title)):
            suggestion_alternatives.append(
                {"title": {"$regex": pattern, "$options": "i"}}
            )
        if candidate.url and (pattern := url_regex_pattern(candidate.url)):
            suggestion_alternatives.append(
                {"url": {"$regex": pattern, "$options": "i"}}
            )
        for author in candidate.authors[:MAX_PAGE_SIZE]:
            author_fields = (
                ("authors.literal", author.literal),
                ("authors.family", author.family),
            )
            populated_primary = any(value for _field, value in author_fields)
            for field_name, value in author_fields:
                if value and (pattern := suggestion_regex_pattern(value)):
                    suggestion_alternatives.append(
                        {field_name: {"$regex": pattern, "$options": "i"}}
                    )
            if not populated_primary and author.given:
                pattern = suggestion_regex_pattern(author.given)
                if pattern:
                    suggestion_alternatives.append(
                        {"authors.given": {"$regex": pattern, "$options": "i"}}
                    )
        if not identity_groups and not suggestion_alternatives:
            return []

        results: list[Reference] = []
        seen: set[str] = set()
        for alternatives in (*identity_groups, suggestion_alternatives):
            if not alternatives or len(results) >= MAX_PAGE_SIZE:
                continue
            for document in self._collection.find({"$or": alternatives}).limit(MAX_PAGE_SIZE):
                model = _model_document(document, Reference)
                if model is None or model.reference_id in seen:
                    continue
                seen.add(model.reference_id)
                results.append(model)
                if len(results) >= MAX_PAGE_SIZE:
                    break
        return results

    def deletion_blockers(self, reference_id: str) -> tuple[str, ...]:
        """Report Source associations that forbid physical deletion."""
        reference = self.get_by_id(reference_id)
        if reference is None or not reference.source_ids:
            return ()
        return (f"source_ids:{len(reference.source_ids)}",)

    def physical_delete_if_unused(self, reference_id: str) -> bool:
        """Delete only after rechecking all S1A Reference blockers."""
        blockers = self.deletion_blockers(reference_id)
        if blockers:
            raise PhysicalDeletionBlockedError(reference_id, blockers)
        result = self._collection.delete_one({"reference_id": reference_id})
        return bool(result.deleted_count)


__all__ = [
    "ImmutableFieldError",
    "MAX_PAGE_SIZE",
    "MAX_SEARCH_LENGTH",
    "PageResult",
    "PhysicalDeletionBlockedError",
    "ReferenceRepository",
    "RepositoryConflictError",
    "RepositoryError",
    "SourceRepository",
]

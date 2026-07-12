"""Faithful deterministic MongoDB doubles for Source Catalog bootstrap tests.

The doubles deliberately keep collection handles separate from collection
existence.  This mirrors PyMongo: selecting ``database["sources"]`` is local and
does not create the collection.  Only an allowed insert or index creation
materializes a previously absent collection.

Normal writes are closed to the three S1C2A bootstrap collections, while
legacy collections are always read-only.  Explicit ``external_*`` helpers are
test controls for simulating a concurrent actor or snapshot drift; bootstrap
code cannot reach those controls through the Mongo-like API.
"""

# ruff: noqa: D105,D107

from __future__ import annotations

import copy
import re
import threading
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from typing import Literal

from bson import BSON
from pymongo.errors import DuplicateKeyError
from pymongo.errors import OperationFailure

LEGACY_COLLECTIONS = frozenset(
    {
        "backlog_items",
        "concepts",
        "deliverables",
        "knowledge_graph_maps",
        "latex_documents",
        "latex_notes",
        "media_assets",
        "relations",
        "weekly_reviews",
        "worklog_entries",
    }
)
ALLOWED_DOCUMENT_WRITE_COLLECTIONS = frozenset(
    {"sources", "references", "source_catalog_migration_manifest"}
)
ALLOWED_INDEX_WRITE_COLLECTIONS = frozenset({"sources", "references"})

EventKind = Literal["read", "write", "write_attempt", "forbidden", "external"]
FailpointMoment = Literal["before", "after"]


def _bson_copy(document: Mapping[str, Any]) -> dict[str, Any]:
    """Round-trip a document through BSON as a real server would.

    Besides rejecting values MongoDB cannot persist, this intentionally turns
    aware datetimes into naive UTC values and truncates them to milliseconds.
    Bootstrap tests therefore exercise the same timestamp equality boundary as
    real PyMongo persistence.
    """
    return BSON(BSON.encode(dict(document))).decode()


def _values(document: Any, path: str) -> list[Any]:
    """Return flattened values found at one dotted Mongo-style path."""
    current = [document]
    for part in path.split("."):
        following: list[Any] = []
        for value in current:
            if isinstance(value, Mapping) and part in value:
                nested = value[part]
                following.extend(nested if isinstance(nested, list) else [nested])
            elif isinstance(value, list):
                for nested in value:
                    if isinstance(nested, Mapping) and part in nested:
                        item = nested[part]
                        following.extend(item if isinstance(item, list) else [item])
        current = following
    return current


def _regex_matches(values: list[Any], pattern: Any, options: str = "") -> bool:
    flags = re.IGNORECASE if "i" in options else 0
    expression = pattern if isinstance(pattern, re.Pattern) else re.compile(str(pattern), flags)
    return any(expression.search(str(value)) is not None for value in values)


def _compare(values: list[Any], operator: str, expected: Any) -> bool:
    if operator == "$exists":
        return bool(values) is bool(expected)
    if operator == "$in":
        return any(
            _regex_matches([value], item) if isinstance(item, re.Pattern) else value == item
            for value in values
            for item in expected
        )
    if operator == "$nin":
        return not _compare(values, "$in", expected)
    if operator == "$all":
        return all(any(value == item for value in values) for item in expected)
    if operator == "$eq":
        return any(value == expected for value in values)
    if operator == "$ne":
        return not _compare(values, "$eq", expected)
    comparisons: dict[str, Callable[[Any, Any], bool]] = {
        "$gt": lambda value, other: value > other,
        "$gte": lambda value, other: value >= other,
        "$lt": lambda value, other: value < other,
        "$lte": lambda value, other: value <= other,
    }
    if operator in comparisons:
        comparator = comparisons[operator]
        return any(comparator(value, expected) for value in values)
    raise AssertionError(f"Unsupported fake Mongo query operator: {operator}")


def _condition_matches(values: list[Any], condition: Any) -> bool:
    if isinstance(condition, re.Pattern):
        return _regex_matches(values, condition)
    if isinstance(condition, Mapping):
        recognized = False
        for operator, expected in condition.items():
            if operator == "$options":
                continue
            if operator == "$regex":
                recognized = True
                if not _regex_matches(values, expected, str(condition.get("$options", ""))):
                    return False
                continue
            if str(operator).startswith("$"):
                recognized = True
                if not _compare(values, str(operator), expected):
                    return False
        if recognized:
            return True
    if condition is None and not values:
        # Mongo equality-to-null also selects documents where the field is absent.
        return True
    return any(
        condition in value if isinstance(value, list) else value == condition for value in values
    )


def matches_query(document: Mapping[str, Any], query: Mapping[str, Any]) -> bool:
    """Evaluate the bounded query subset used by repositories and the engine."""
    for key, condition in query.items():
        if key == "$or":
            if not any(matches_query(document, alternative) for alternative in condition):
                return False
        elif key == "$and":
            if not all(matches_query(document, alternative) for alternative in condition):
                return False
        elif key == "$nor":
            if any(matches_query(document, alternative) for alternative in condition):
                return False
        elif not _condition_matches(_values(document, key), condition):
            return False
    return True


def _set_path(document: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = document
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = copy.deepcopy(value)


def _unset_path(document: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    current: Any = document
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _project(document: Mapping[str, Any], projection: Mapping[str, Any] | None) -> dict[str, Any]:
    if not projection:
        return copy.deepcopy(dict(document))
    inclusion_roots = {
        str(path).split(".", maxsplit=1)[0]
        for path, enabled in projection.items()
        if path != "_id" and bool(enabled)
    }
    if inclusion_roots:
        result = {
            key: copy.deepcopy(value)
            for key, value in document.items()
            if key in inclusion_roots or (key == "_id" and projection.get("_id", 1))
        }
        return result
    result = copy.deepcopy(dict(document))
    for path, enabled in projection.items():
        if not enabled:
            _unset_path(result, str(path))
    return result


def _sort_value(document: Mapping[str, Any], path: str) -> tuple[bool, str, str]:
    values = _values(document, path)
    if not values:
        return True, "", ""
    value = values[0]
    return False, type(value).__name__, repr(value)


@dataclass(frozen=True, slots=True)
class FakeMongoEvent:
    """One ordered fake database observation."""

    sequence: int
    kind: EventKind
    operation: str
    collection: str | None
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FakeInsertOneResult:
    """Minimal acknowledged result returned by ``insert_one``."""

    inserted_id: Any
    acknowledged: bool = True


@dataclass(frozen=True, slots=True)
class FakeUpdateResult:
    """Minimal acknowledged result returned by update and replace operations."""

    matched_count: int = 0
    modified_count: int = 0
    upserted_id: Any = None
    acknowledged: bool = True


FailpointCallback = Callable[["FakeDatabase", str | None, dict[str, Any]], None]


@dataclass(slots=True)
class FakeFailpoint:
    """One-shot deterministic hook around a selected fake operation."""

    operation: str
    collection: str | None = None
    occurrence: int = 1
    moment: FailpointMoment = "before"
    callback: FailpointCallback | None = None
    exception: BaseException | None = None
    matched_calls: int = 0
    fired: bool = False

    def consider(
        self,
        database: FakeDatabase,
        *,
        operation: str,
        collection: str | None,
        moment: FailpointMoment,
        details: dict[str, Any],
    ) -> None:
        """Fire when operation, collection, moment, and occurrence all match."""
        if self.fired or self.operation != operation or self.moment != moment:
            return
        if self.collection is not None and self.collection != collection:
            return
        self.matched_calls += 1
        if self.matched_calls != self.occurrence:
            return
        self.fired = True
        if self.callback is not None:
            self.callback(database, collection, copy.deepcopy(details))
        if self.exception is not None:
            raise self.exception


class FakeCursor(Iterator[dict[str, Any]]):
    """Chainable deep-copying cursor with the subset used by MathMongo."""

    def __init__(self, documents: Iterable[Mapping[str, Any]]) -> None:
        self._documents = [copy.deepcopy(dict(document)) for document in documents]
        self._position = 0
        self.closed = False

    def sort(
        self,
        key_or_list: str | Iterable[tuple[str, int]],
        direction: int | None = None,
    ) -> FakeCursor:
        """Apply stable dotted-field sorting and return this cursor."""
        fields = (
            [(key_or_list, 1 if direction is None else direction)]
            if isinstance(key_or_list, str)
            else list(key_or_list)
        )
        for field, field_direction in reversed(fields):
            self._documents.sort(
                key=lambda document, path=field: _sort_value(document, path),
                reverse=field_direction < 0,
            )
        self._position = 0
        return self

    def skip(self, amount: int) -> FakeCursor:
        """Discard the requested leading documents."""
        self._documents = self._documents[max(0, int(amount)) :]
        self._position = 0
        return self

    def limit(self, amount: int) -> FakeCursor:
        """Apply a positive limit; zero retains Mongo's no-limit meaning."""
        value = int(amount)
        if value > 0:
            self._documents = self._documents[:value]
        self._position = 0
        return self

    def close(self) -> None:
        """Mark the cursor closed without changing stored documents."""
        self.closed = True

    def rewind(self) -> FakeCursor:
        """Reset iteration for tests that inspect a cursor twice."""
        self._position = 0
        self.closed = False
        return self

    def __iter__(self) -> FakeCursor:
        return self

    def __next__(self) -> dict[str, Any]:
        if self.closed or self._position >= len(self._documents):
            raise StopIteration
        document = copy.deepcopy(self._documents[self._position])
        self._position += 1
        return document

    def __getitem__(self, index: int | slice) -> Any:
        return copy.deepcopy(self._documents[index])


class FakeCollection:
    """Mongo-like collection handle that never materializes on selection/read."""

    _FORBIDDEN_WRITES = frozenset(
        {
            "bulk_write",
            "create_indexes",
            "delete_many",
            "delete_one",
            "drop",
            "drop_index",
            "drop_indexes",
            "insert_many",
            "map_reduce",
            "rename",
            "update_many",
        }
    )

    def __init__(self, database: FakeDatabase, name: str) -> None:
        self.database = database
        self.name = name

    def _documents(self) -> list[dict[str, Any]]:
        return self.database._documents.get(self.name, [])

    @property
    def documents(self) -> list[dict[str, Any]]:
        """Return a deep snapshot without materializing an absent collection."""
        return copy.deepcopy(self._documents())

    def count_documents(self, query: Mapping[str, Any], **kwargs: Any) -> int:
        """Count matching documents without creating the collection."""
        details = {"query": dict(query), "options": dict(kwargs)}
        self.database._trigger("count_documents", self.name, "before", details)
        result = sum(matches_query(document, query) for document in self._documents())
        self.database._record("read", "count_documents", self.name, {**details, "result": result})
        self.database._trigger("count_documents", self.name, "after", details)
        return result

    def find_one(
        self,
        query: Mapping[str, Any],
        projection: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Return the first matching projected document."""
        details = {
            "query": dict(query),
            "projection": dict(projection) if projection is not None else None,
            "options": dict(kwargs),
        }
        self.database._trigger("find_one", self.name, "before", details)
        result = next(
            (
                _project(document, projection)
                for document in self._documents()
                if matches_query(document, query)
            ),
            None,
        )
        self.database._record("read", "find_one", self.name, details)
        self.database._trigger("find_one", self.name, "after", details)
        return copy.deepcopy(result)

    def find(
        self,
        query: Mapping[str, Any] | None = None,
        projection: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> FakeCursor:
        """Return a projected cursor and honor direct ``limit`` options."""
        effective_query = dict(query or {})
        details = {
            "query": effective_query,
            "projection": dict(projection) if projection is not None else None,
            "options": dict(kwargs),
        }
        self.database._trigger("find", self.name, "before", details)
        rows = [
            _project(document, projection)
            for document in self._documents()
            if matches_query(document, effective_query)
        ]
        cursor = FakeCursor(rows)
        if "limit" in kwargs:
            cursor.limit(int(kwargs["limit"]))
        self.database._record("read", "find", self.name, details)
        self.database._trigger("find", self.name, "after", details)
        return cursor

    def insert_one(self, document: Mapping[str, Any], **kwargs: Any) -> FakeInsertOneResult:
        """Insert one BSON-normalized document under the strict write whitelist."""
        self.database._guard_document_write(self.name, "insert_one")
        incoming = copy.deepcopy(dict(document))
        details = {"document": incoming, "options": dict(kwargs)}
        self.database._trigger("insert_one", self.name, "before", details)
        with self.database._lock:
            if "_id" not in incoming:
                incoming["_id"] = self.database._next_fake_id(self.name)
            stored = _bson_copy(incoming)
            duplicate_field = self.database._duplicate_field(self.name, stored)
            if duplicate_field is not None:
                self.database._record(
                    "write_attempt",
                    "insert_one",
                    self.name,
                    {"duplicate_field": duplicate_field, "document": stored},
                )
                raise DuplicateKeyError(
                    f"duplicate fake key in {self.name}: {duplicate_field}",
                    details={"keyPattern": {duplicate_field: 1}},
                )
            self.database._materialize(self.name)
            self.database._documents[self.name].append(stored)
            self.database._record("write", "insert_one", self.name, {"document": stored})
        self.database._trigger("insert_one", self.name, "after", {"document": stored})
        return FakeInsertOneResult(stored["_id"])

    def update_one(
        self,
        query: Mapping[str, Any],
        update: Mapping[str, Any],
        *,
        upsert: bool = False,
        **kwargs: Any,
    ) -> FakeUpdateResult:
        """Apply a bounded modifier update; bootstrap upserts are rejected."""
        self.database._guard_document_write(self.name, "update_one")
        if upsert:
            self.database._reject_write(self.name, "update_one(upsert=True)")
        if not update or any(not str(operator).startswith("$") for operator in update):
            raise AssertionError("Fake update_one requires Mongo modifier operators")
        details = {"query": dict(query), "update": dict(update), "options": dict(kwargs)}
        self.database._trigger("update_one", self.name, "before", details)
        matched = 0
        modified = 0
        with self.database._lock:
            for index, original in enumerate(self._documents()):
                if not matches_query(original, query):
                    continue
                matched = 1
                candidate = copy.deepcopy(original)
                self._apply_update(candidate, update)
                stored = _bson_copy(candidate)
                duplicate_field = self.database._duplicate_field(
                    self.name,
                    stored,
                    exclude_index=index,
                )
                if duplicate_field is not None:
                    raise DuplicateKeyError(
                        f"duplicate fake key in {self.name}: {duplicate_field}",
                        details={"keyPattern": {duplicate_field: 1}},
                    )
                modified = int(stored != original)
                self.database._documents[self.name][index] = stored
                break
            self.database._record(
                "write",
                "update_one",
                self.name,
                {**details, "matched_count": matched, "modified_count": modified},
            )
        self.database._trigger("update_one", self.name, "after", details)
        return FakeUpdateResult(matched_count=matched, modified_count=modified)

    @staticmethod
    def _apply_update(document: dict[str, Any], update: Mapping[str, Any]) -> None:
        supported = {"$addToSet", "$inc", "$push", "$set", "$unset"}
        unexpected = set(update) - supported
        if unexpected:
            raise AssertionError(f"Unsupported fake Mongo update operators: {sorted(unexpected)}")
        for path, value in update.get("$set", {}).items():
            _set_path(document, path, value)
        for path in update.get("$unset", {}):
            _unset_path(document, path)
        for path, amount in update.get("$inc", {}).items():
            values = _values(document, path)
            _set_path(document, path, (values[0] if values else 0) + amount)
        for path, value in update.get("$push", {}).items():
            values = _values(document, path)
            current = (
                list(values[0]) if len(values) == 1 and isinstance(values[0], list) else values
            )
            current.append(copy.deepcopy(value))
            _set_path(document, path, current)
        for path, value in update.get("$addToSet", {}).items():
            values = _values(document, path)
            current = (
                list(values[0]) if len(values) == 1 and isinstance(values[0], list) else values
            )
            if value not in current:
                current.append(copy.deepcopy(value))
            _set_path(document, path, current)

    def replace_one(
        self,
        query: Mapping[str, Any],
        replacement: Mapping[str, Any],
        *,
        upsert: bool = False,
        **kwargs: Any,
    ) -> FakeUpdateResult:
        """Replace one matched document without supporting adoption by upsert."""
        self.database._guard_document_write(self.name, "replace_one")
        if upsert:
            self.database._reject_write(self.name, "replace_one(upsert=True)")
        details = {
            "query": dict(query),
            "replacement": dict(replacement),
            "options": dict(kwargs),
        }
        self.database._trigger("replace_one", self.name, "before", details)
        matched = 0
        modified = 0
        with self.database._lock:
            for index, original in enumerate(self._documents()):
                if not matches_query(original, query):
                    continue
                matched = 1
                candidate = copy.deepcopy(dict(replacement))
                candidate.setdefault("_id", original.get("_id"))
                stored = _bson_copy(candidate)
                duplicate_field = self.database._duplicate_field(
                    self.name,
                    stored,
                    exclude_index=index,
                )
                if duplicate_field is not None:
                    raise DuplicateKeyError(f"duplicate fake key in {self.name}: {duplicate_field}")
                modified = int(stored != original)
                self.database._documents[self.name][index] = stored
                break
            self.database._record(
                "write",
                "replace_one",
                self.name,
                {**details, "matched_count": matched, "modified_count": modified},
            )
        self.database._trigger("replace_one", self.name, "after", details)
        return FakeUpdateResult(matched_count=matched, modified_count=modified)

    def find_one_and_update(
        self,
        query: Mapping[str, Any],
        update: Mapping[str, Any],
        *,
        upsert: bool = False,
        return_document: Any = False,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Perform a CAS-style update and return the before or after document."""
        before = self.find_one(query)
        if before is None:
            if upsert:
                self.database._reject_write(self.name, "find_one_and_update(upsert=True)")
            return None
        result = self.update_one(query, update, upsert=False, **kwargs)
        if not result.matched_count:
            return None
        return self.find_one({"_id": before.get("_id")}) if bool(return_document) else before

    def list_indexes(self, **kwargs: Any) -> FakeCursor:
        """Return index metadata without materializing an absent collection."""
        details = {"options": dict(kwargs)}
        self.database._trigger("list_indexes", self.name, "before", details)
        indexes = self.database._indexes.get(self.name, [])
        self.database._record("read", "list_indexes", self.name, details)
        self.database._trigger("list_indexes", self.name, "after", details)
        return FakeCursor(indexes)

    def index_information(self) -> dict[str, dict[str, Any]]:
        """Return PyMongo-like index information keyed by stable index name."""
        return {
            str(index["name"]): {
                key: copy.deepcopy(value) for key, value in index.items() if key != "name"
            }
            for index in self.database._indexes.get(self.name, [])
        }

    def create_index(
        self,
        keys: str | Iterable[tuple[str, int]],
        *,
        name: str,
        unique: bool = False,
        **kwargs: Any,
    ) -> str:
        """Create one explicitly allowed index with stable-name conflict checks."""
        self.database._guard_index_write(self.name, "create_index")
        normalized_keys = [(keys, 1)] if isinstance(keys, str) else list(keys)
        document = {
            "name": name,
            "key": dict(normalized_keys),
            "unique": bool(unique),
            **copy.deepcopy(kwargs),
        }
        details = {"index": document}
        self.database._trigger("create_index", self.name, "before", details)
        with self.database._lock:
            self.database._materialize(self.name)
            existing = next(
                (index for index in self.database._indexes[self.name] if index.get("name") == name),
                None,
            )
            if existing is not None and existing != document:
                self.database._record(
                    "write_attempt",
                    "create_index",
                    self.name,
                    {"index": document, "conflict": True},
                )
                raise OperationFailure(f"fake index name conflict: {name}")
            if existing is None:
                self.database._indexes[self.name].append(copy.deepcopy(document))
                self.database._record("write", "create_index", self.name, details)
        self.database._trigger("create_index", self.name, "after", details)
        return name

    def __getattr__(self, name: str) -> Any:
        if name not in self._FORBIDDEN_WRITES:
            raise AttributeError(name)

        def reject(*_args: Any, **_kwargs: Any) -> None:
            self.database._reject_write(self.name, name)

        return reject


class FakeDatabase:
    """Thread-safe isolated database with strict bootstrap write boundaries."""

    def __init__(
        self,
        name: str,
        collections: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
        *,
        indexes: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
        allowed_document_writes: Iterable[str] = ALLOWED_DOCUMENT_WRITE_COLLECTIONS,
        allowed_index_writes: Iterable[str] = ALLOWED_INDEX_WRITE_COLLECTIONS,
    ) -> None:
        self.name = name
        self._lock = threading.RLock()
        self._handles: dict[str, FakeCollection] = {}
        self._documents: dict[str, list[dict[str, Any]]] = {}
        self._indexes: dict[str, list[dict[str, Any]]] = {}
        self._existing_names: set[str] = set()
        self._allowed_document_writes = frozenset(allowed_document_writes)
        self._allowed_index_writes = frozenset(allowed_index_writes)
        self._events: list[FakeMongoEvent] = []
        self._failpoints: list[FakeFailpoint] = []
        self._fake_id_counter = 0
        self._materialize_callbacks: list[Callable[[FakeDatabase], None]] = []
        for collection_name, documents in (collections or {}).items():
            self.seed_collection(collection_name, documents)
        for collection_name, specifications in (indexes or {}).items():
            if collection_name not in self._existing_names:
                self.seed_collection(collection_name, ())
            self._indexes[collection_name] = [copy.deepcopy(dict(item)) for item in specifications]

    @property
    def events(self) -> tuple[FakeMongoEvent, ...]:
        """Return a stable copy of the complete event history."""
        return tuple(copy.deepcopy(self._events))

    @property
    def read_events(self) -> tuple[FakeMongoEvent, ...]:
        """Return only server-like reads."""
        return tuple(event for event in self.events if event.kind == "read")

    @property
    def write_events(self) -> tuple[FakeMongoEvent, ...]:
        """Return only successful bootstrap writes."""
        return tuple(event for event in self.events if event.kind == "write")

    @property
    def write_attempt_events(self) -> tuple[FakeMongoEvent, ...]:
        """Return successful, rejected, and conflicting write attempts."""
        return tuple(
            event for event in self.events if event.kind in {"write", "write_attempt", "forbidden"}
        )

    @property
    def forbidden_events(self) -> tuple[FakeMongoEvent, ...]:
        """Return operations rejected by the strict fake boundary."""
        return tuple(event for event in self.events if event.kind == "forbidden")

    def __getitem__(self, name: str) -> FakeCollection:
        """Select a local handle without creating a MongoDB collection."""
        with self._lock:
            handle = self._handles.get(name)
            if handle is None:
                handle = FakeCollection(self, name)
                self._handles[name] = handle
            return handle

    def get_collection(self, name: str, **_kwargs: Any) -> FakeCollection:
        """PyMongo-compatible named handle selection without materialization."""
        return self[name]

    def list_collection_names(self, **kwargs: Any) -> list[str]:
        """List only materialized or explicitly seeded collections."""
        details = {"options": dict(kwargs)}
        self._trigger("list_collection_names", None, "before", details)
        result = sorted(self._existing_names)
        self._record("read", "list_collection_names", None, {**details, "result": result})
        self._trigger("list_collection_names", None, "after", details)
        return result

    def has_collection(self, name: str) -> bool:
        """Return collection presence without selecting a handle."""
        return name in self._existing_names

    def seed_collection(
        self,
        name: str,
        documents: Iterable[Mapping[str, Any]],
        *,
        indexes: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        """Establish initial server state without recording bootstrap writes."""
        with self._lock:
            self._existing_names.add(name)
            self._documents[name] = [_bson_copy(document) for document in documents]
            self._indexes[name] = (
                [copy.deepcopy(dict(index)) for index in indexes]
                if indexes is not None
                else [self._id_index()]
            )

    def snapshot(
        self,
        collection_names: Iterable[str] | None = None,
    ) -> dict[str, tuple[dict[str, Any], ...]]:
        """Return a deep deterministic document snapshot without recording reads."""
        names = sorted(collection_names or self._existing_names)
        return {
            name: tuple(copy.deepcopy(self._documents.get(name, [])))
            for name in names
            if name in self._existing_names
        }

    def legacy_snapshot(self) -> dict[str, tuple[dict[str, Any], ...]]:
        """Return only immutable legacy collection documents."""
        return self.snapshot(LEGACY_COLLECTIONS)

    def external_insert(self, collection: str, document: Mapping[str, Any]) -> None:
        """Simulate a concurrent actor, bypassing the bootstrap whitelist."""
        with self._lock:
            incoming = copy.deepcopy(dict(document))
            incoming.setdefault("_id", self._next_fake_id(collection))
            stored = _bson_copy(incoming)
            duplicate_field = self._duplicate_field(collection, stored)
            if duplicate_field is not None:
                raise DuplicateKeyError(
                    f"duplicate external fake key in {collection}: {duplicate_field}"
                )
            self._materialize(collection)
            self._documents[collection].append(stored)
            self._record("external", "external_insert", collection, {"document": stored})

    def external_replace_documents(
        self,
        collection: str,
        documents: Iterable[Mapping[str, Any]],
    ) -> None:
        """Replace server state to simulate drift outside the bootstrap process."""
        with self._lock:
            self._materialize(collection)
            self._documents[collection] = [_bson_copy(document) for document in documents]
            self._record(
                "external",
                "external_replace_documents",
                collection,
                {"count": len(self._documents[collection])},
            )

    def external_update_one(
        self,
        collection: str,
        query: Mapping[str, Any],
        changes: Mapping[str, Any],
    ) -> bool:
        """Mutate one matching document as a simulated concurrent actor."""
        with self._lock:
            for index, original in enumerate(self._documents.get(collection, [])):
                if not matches_query(original, query):
                    continue
                candidate = copy.deepcopy(original)
                for path, value in changes.items():
                    _set_path(candidate, path, value)
                self._documents[collection][index] = _bson_copy(candidate)
                self._record(
                    "external",
                    "external_update_one",
                    collection,
                    {"query": dict(query), "changes": dict(changes)},
                )
                return True
        return False

    def add_failpoint(
        self,
        operation: str,
        *,
        collection: str | None = None,
        occurrence: int = 1,
        moment: FailpointMoment = "before",
        callback: FailpointCallback | None = None,
        exception: BaseException | None = None,
    ) -> FakeFailpoint:
        """Register and return one deterministic one-shot operation hook."""
        if occurrence < 1:
            raise ValueError("failpoint occurrence must be positive")
        failpoint = FakeFailpoint(
            operation=operation,
            collection=collection,
            occurrence=occurrence,
            moment=moment,
            callback=callback,
            exception=exception,
        )
        self._failpoints.append(failpoint)
        return failpoint

    def clear_events(self) -> None:
        """Reset instrumentation while retaining documents and failpoints."""
        with self._lock:
            self._events.clear()

    def clear_failpoints(self) -> None:
        """Remove every configured failure hook."""
        self._failpoints.clear()

    def _trigger(
        self,
        operation: str,
        collection: str | None,
        moment: FailpointMoment,
        details: dict[str, Any],
    ) -> None:
        for failpoint in tuple(self._failpoints):
            failpoint.consider(
                self,
                operation=operation,
                collection=collection,
                moment=moment,
                details=details,
            )

    def _record(
        self,
        kind: EventKind,
        operation: str,
        collection: str | None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._events.append(
                FakeMongoEvent(
                    sequence=len(self._events) + 1,
                    kind=kind,
                    operation=operation,
                    collection=collection,
                    details=copy.deepcopy(dict(details or {})),
                )
            )

    def _materialize(self, name: str) -> None:
        newly_materialized = name not in self._existing_names
        self._existing_names.add(name)
        self._documents.setdefault(name, [])
        self._indexes.setdefault(name, [self._id_index()])
        if newly_materialized:
            for callback in tuple(self._materialize_callbacks):
                callback(self)

    @staticmethod
    def _id_index() -> dict[str, Any]:
        return {"name": "_id_", "key": {"_id": 1}, "unique": True}

    def _next_fake_id(self, collection: str) -> str:
        self._fake_id_counter += 1
        return f"fake_{collection}_{self._fake_id_counter:08d}"

    def _duplicate_field(
        self,
        collection: str,
        document: Mapping[str, Any],
        *,
        exclude_index: int | None = None,
    ) -> str | None:
        unique_fields = ["_id"]
        if collection == "sources":
            unique_fields.append("source_id")
        elif collection == "references":
            unique_fields.append("reference_id")
        elif collection == "source_catalog_migration_manifest":
            unique_fields.append("manifest_key")
        for index, existing in enumerate(self._documents.get(collection, [])):
            if exclude_index is not None and index == exclude_index:
                continue
            for field in unique_fields:
                if field in document and document.get(field) == existing.get(field):
                    return field
        return None

    def _guard_document_write(self, collection: str, operation: str) -> None:
        if collection in LEGACY_COLLECTIONS or collection not in self._allowed_document_writes:
            self._reject_write(collection, operation)

    def _guard_index_write(self, collection: str, operation: str) -> None:
        if collection not in self._allowed_index_writes:
            self._reject_write(collection, operation)

    def _reject_write(self, collection: str | None, operation: str) -> None:
        self._record("forbidden", operation, collection)
        raise AssertionError(f"unexpected MongoDB write operation: {collection}.{operation}")

    def create_collection(self, name: str, **_kwargs: Any) -> None:
        """Reject explicit collection creation; approved writes materialize implicitly."""
        self._reject_write(name, "create_collection")

    def drop_collection(self, name: str, **_kwargs: Any) -> None:
        """Reject destructive collection rollback."""
        self._reject_write(name, "drop_collection")

    def command(self, *_args: Any, **_kwargs: Any) -> None:
        """Reject database commands at the bootstrap persistence boundary."""
        self._reject_write(None, "database.command")


@dataclass(frozen=True, slots=True)
class FakeClientEvent:
    """One ordered fake MongoClient observation."""

    sequence: int
    operation: str
    details: dict[str, Any]


class FakeAdmin:
    """Read-only admin facade supporting only ping."""

    def __init__(self, client: FakeMongoClient) -> None:
        self.client = client

    def command(self, command: str | Mapping[str, Any]) -> dict[str, int]:
        """Accept only MongoDB ping and record it as a read."""
        if command not in ("ping", {"ping": 1}):
            raise AssertionError(f"unexpected fake admin command: {command!r}")
        self.client._record("admin.ping", {"command": copy.deepcopy(command)})
        return {"ok": 1}


class FakeMongoClient:
    """No-network MongoClient facade sharing database state across instances."""

    def __init__(
        self,
        databases: dict[str, FakeDatabase],
        existing_database_names: set[str],
    ) -> None:
        self._databases = databases
        self._existing_database_names = existing_database_names
        self.admin = FakeAdmin(self)
        self.closed = False
        self._events: list[FakeClientEvent] = []

    @property
    def events(self) -> tuple[FakeClientEvent, ...]:
        """Return client reads in call order."""
        return tuple(copy.deepcopy(self._events))

    def list_database_names(self, **kwargs: Any) -> list[str]:
        """List only databases with seeded or materialized server state."""
        result = sorted(self._existing_database_names)
        self._record("list_database_names", {"options": dict(kwargs), "result": result})
        return result

    def get_database(self, name: str, **kwargs: Any) -> FakeDatabase:
        """Select a database handle without creating a real database."""
        database = self._databases.get(name)
        if database is None:
            database = FakeDatabase(name)
            self._databases[name] = database

        def mark_existing(value: FakeDatabase, database_name: str = name) -> None:
            if value._existing_names:
                self._existing_database_names.add(database_name)

        if mark_existing not in database._materialize_callbacks:
            database._materialize_callbacks.append(mark_existing)
        self._record("get_database", {"name": name, "options": dict(kwargs)})
        return database

    def __getitem__(self, name: str) -> FakeDatabase:
        return self.get_database(name)

    def close(self) -> None:
        """Record deterministic cleanup without touching shared database state."""
        self.closed = True
        self._record("close", {})

    def drop_database(self, name: str, **_kwargs: Any) -> None:
        """Reject destructive target cleanup, which belongs to S1C2B."""
        self._record("forbidden.drop_database", {"name": name})
        raise AssertionError(f"unexpected MongoDB drop_database operation: {name}")

    def start_session(self, **_kwargs: Any) -> None:
        """Reject implicit transaction/rollback behavior in the S1C2A fake."""
        self._record("forbidden.start_session", {})
        raise AssertionError("unexpected MongoDB session/transaction operation")

    def _record(self, operation: str, details: Mapping[str, Any]) -> None:
        self._events.append(
            FakeClientEvent(
                sequence=len(self._events) + 1,
                operation=operation,
                details=copy.deepcopy(dict(details)),
            )
        )


class FakeMongoClientFactory:
    """Callable factory that proves every connection used an injected fake."""

    def __init__(
        self,
        databases: Mapping[str, FakeDatabase] | None = None,
        *,
        existing_database_names: Iterable[str] | None = None,
    ) -> None:
        self.databases = dict(databases or {})
        self.existing_database_names = set(existing_database_names or self.databases)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.clients: list[FakeMongoClient] = []

    @property
    def last_client(self) -> FakeMongoClient | None:
        """Return the most recently constructed client, if any."""
        return self.clients[-1] if self.clients else None

    def __call__(self, uri: str, **kwargs: Any) -> FakeMongoClient:
        """Construct a fresh client facade over shared in-memory databases."""
        self.calls.append((uri, copy.deepcopy(dict(kwargs))))
        client = FakeMongoClient(self.databases, self.existing_database_names)
        self.clients.append(client)
        return client


__all__ = [
    "ALLOWED_DOCUMENT_WRITE_COLLECTIONS",
    "ALLOWED_INDEX_WRITE_COLLECTIONS",
    "LEGACY_COLLECTIONS",
    "FakeClientEvent",
    "FakeCollection",
    "FakeCursor",
    "FakeDatabase",
    "FakeFailpoint",
    "FakeInsertOneResult",
    "FakeMongoClient",
    "FakeMongoClientFactory",
    "FakeMongoEvent",
    "FakeUpdateResult",
    "matches_query",
]

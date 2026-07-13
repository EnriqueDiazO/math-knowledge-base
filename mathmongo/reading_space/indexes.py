"""Explicit, inspectable indexes for the document reading space."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from mathmongo.reading_space.errors import ReadingSpaceIndexConflictError


class ReadingIndexState(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ReadingIndexSpec:
    name: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class ReadingIndexStatus:
    spec: ReadingIndexSpec
    state: ReadingIndexState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ReadingIndexPlan:
    statuses: tuple[ReadingIndexStatus, ...]

    @property
    def missing(self) -> tuple[ReadingIndexSpec, ...]:
        return tuple(item.spec for item in self.statuses if item.state == ReadingIndexState.MISSING)

    @property
    def conflicts(self) -> tuple[ReadingIndexStatus, ...]:
        return tuple(item for item in self.statuses if item.state == ReadingIndexState.CONFLICT)

    @property
    def present(self) -> tuple[ReadingIndexSpec, ...]:
        return tuple(item.spec for item in self.statuses if item.state == ReadingIndexState.PRESENT)

    @property
    def initialized(self) -> bool:
        return not self.missing and not self.conflicts


READING_SPACE_INDEXES = (
    ReadingIndexSpec(
        "document_reading_state_id_unique",
        (("reading_state_id", 1),),
        unique=True,
    ),
    ReadingIndexSpec(
        "document_reading_state_user_document_unique",
        (("user_scope", 1), ("document_id", 1)),
        unique=True,
    ),
    ReadingIndexSpec(
        "document_reading_state_source_status_updated",
        (("source_id", 1), ("status", 1), ("updated_at", -1)),
    ),
    ReadingIndexSpec(
        "document_reading_state_last_opened",
        (("last_opened_at", -1),),
    ),
    ReadingIndexSpec(
        "document_reading_state_reference",
        (("reference_id", 1),),
    ),
    ReadingIndexSpec(
        "document_reading_state_updated",
        (("updated_at", -1),),
    ),
)


def _index_keys(document: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    key = document.get("key", ())
    if hasattr(key, "items"):
        return tuple((str(field), int(direction)) for field, direction in key.items())
    return tuple((str(field), int(direction)) for field, direction in key)


def _unique_matches(document: dict[str, Any], expected: bool) -> bool:
    if "unique" not in document:
        return expected is False
    return isinstance(document["unique"], bool) and document["unique"] is expected


def _unapproved_options(document: dict[str, Any]) -> tuple[str, ...]:
    approved = {"key", "name", "unique", "v", "ns"}
    return tuple(sorted(str(name) for name in document if name not in approved))


class ReadingSpaceIndexManager:
    COLLECTION = "document_reading_state"

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReadingSpaceIndexManager requires an explicit database")
        self.database = database

    def _existing(self) -> tuple[dict[str, Any], ...]:
        if (
            hasattr(self.database, "list_collection_names")
            and self.COLLECTION not in self.database.list_collection_names()
        ):
            return ()
        return tuple(dict(item) for item in self.database[self.COLLECTION].list_indexes())

    def status(self) -> tuple[ReadingIndexStatus, ...]:
        existing = self._existing()
        statuses: list[ReadingIndexStatus] = []
        for spec in READING_SPACE_INDEXES:
            by_name = next((item for item in existing if item.get("name") == spec.name), None)
            if by_name is not None:
                keys_match = _index_keys(by_name) == spec.keys
                unique_matches = _unique_matches(by_name, spec.unique)
                extra = _unapproved_options(by_name)
                if keys_match and unique_matches and not extra:
                    statuses.append(ReadingIndexStatus(spec, ReadingIndexState.PRESENT))
                else:
                    detail = "stable name exists with different keys or uniqueness"
                    if keys_match and unique_matches and extra:
                        detail = "stable name exists with unapproved options: " + ",".join(extra)
                    statuses.append(ReadingIndexStatus(spec, ReadingIndexState.CONFLICT, detail))
                continue
            equivalent = next(
                (
                    item
                    for item in existing
                    if _index_keys(item) == spec.keys
                    and _unique_matches(item, spec.unique)
                    and not _unapproved_options(item)
                ),
                None,
            )
            if equivalent is None:
                statuses.append(ReadingIndexStatus(spec, ReadingIndexState.MISSING))
            else:
                statuses.append(
                    ReadingIndexStatus(
                        spec,
                        ReadingIndexState.CONFLICT,
                        f"equivalent index uses another name: {equivalent.get('name')}",
                    )
                )
        return tuple(statuses)

    def plan(self) -> ReadingIndexPlan:
        return ReadingIndexPlan(self.status())

    def apply(self) -> ReadingIndexPlan:
        plan = self.plan()
        if plan.conflicts:
            raise ReadingSpaceIndexConflictError(
                "Reading Space index conflicts require review: "
                + ", ".join(item.spec.name for item in plan.conflicts)
            )
        collection = self.database[self.COLLECTION]
        for spec in plan.missing:
            collection.create_index(list(spec.keys), name=spec.name, unique=spec.unique)
        applied = self.plan()
        if applied.conflicts:
            raise ReadingSpaceIndexConflictError(
                "Reading Space index conflicts require review: "
                + ", ".join(item.spec.name for item in applied.conflicts)
            )
        if applied.missing:
            raise RuntimeError(
                "Reading Space indexes remain missing: "
                + ", ".join(spec.name for spec in applied.missing)
            )
        return applied


__all__ = [
    "READING_SPACE_INDEXES",
    "ReadingIndexPlan",
    "ReadingIndexSpec",
    "ReadingIndexState",
    "ReadingIndexStatus",
    "ReadingSpaceIndexManager",
]

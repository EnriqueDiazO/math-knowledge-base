"""Explicit, inspectable indexes for S4.2 Document page maps."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from mathmongo.document_page_maps.errors import DocumentPageMapIndexConflictError

DOCUMENT_PAGE_MAPS_COLLECTION = "document_page_maps"


class PageMapIndexState(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class PageMapIndexSpec:
    name: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False
    partial_filter: tuple[tuple[str, Any], ...] | None = None

    @property
    def partial_filter_expression(self) -> dict[str, Any] | None:
        return dict(self.partial_filter) if self.partial_filter is not None else None


@dataclass(frozen=True, slots=True)
class PageMapIndexStatus:
    spec: PageMapIndexSpec
    state: PageMapIndexState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class PageMapIndexPlan:
    statuses: tuple[PageMapIndexStatus, ...]

    @property
    def missing(self) -> tuple[PageMapIndexSpec, ...]:
        return tuple(item.spec for item in self.statuses if item.state == PageMapIndexState.MISSING)

    @property
    def conflicts(self) -> tuple[PageMapIndexStatus, ...]:
        return tuple(item for item in self.statuses if item.state == PageMapIndexState.CONFLICT)

    @property
    def present(self) -> tuple[PageMapIndexSpec, ...]:
        return tuple(item.spec for item in self.statuses if item.state == PageMapIndexState.PRESENT)

    @property
    def initialized(self) -> bool:
        return not self.missing and not self.conflicts


DOCUMENT_PAGE_MAP_INDEXES = (
    PageMapIndexSpec(
        "document_page_maps_id_unique",
        (("page_map_id", 1),),
        unique=True,
    ),
    PageMapIndexSpec(
        "document_page_maps_active_identity_unique",
        (("user_scope", 1), ("document_id", 1)),
        unique=True,
        partial_filter=(("status", "active"),),
    ),
    PageMapIndexSpec(
        "document_page_maps_document_status_updated",
        (("document_id", 1), ("status", 1), ("updated_at", -1)),
    ),
)


def _index_keys(document: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    keys = document.get("key", ())
    if hasattr(keys, "items"):
        return tuple((str(field), int(direction)) for field, direction in keys.items())
    return tuple((str(field), int(direction)) for field, direction in keys)


def _unique_matches(document: dict[str, Any], expected: bool) -> bool:
    if "unique" not in document:
        return expected is False
    return isinstance(document["unique"], bool) and document["unique"] is expected


def _partial_matches(document: dict[str, Any], spec: PageMapIndexSpec) -> bool:
    observed = document.get("partialFilterExpression")
    expected = spec.partial_filter_expression
    if expected is None:
        return observed is None
    return isinstance(observed, dict) and observed == expected


def _unapproved_options(document: dict[str, Any]) -> tuple[str, ...]:
    approved = {"key", "name", "unique", "partialFilterExpression", "v", "ns"}
    return tuple(sorted(str(name) for name in document if name not in approved))


class DocumentPageMapIndexManager:
    COLLECTION = DOCUMENT_PAGE_MAPS_COLLECTION

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("DocumentPageMapIndexManager requires an explicit database")
        self.database = database

    def _existing(self) -> tuple[dict[str, Any], ...]:
        if (
            hasattr(self.database, "list_collection_names")
            and self.COLLECTION not in self.database.list_collection_names()
        ):
            return ()
        return tuple(dict(item) for item in self.database[self.COLLECTION].list_indexes())

    def status(self) -> tuple[PageMapIndexStatus, ...]:
        existing = self._existing()
        statuses: list[PageMapIndexStatus] = []
        for spec in DOCUMENT_PAGE_MAP_INDEXES:
            by_name = next((item for item in existing if item.get("name") == spec.name), None)
            if by_name is not None:
                matches = (
                    _index_keys(by_name) == spec.keys
                    and _unique_matches(by_name, spec.unique)
                    and _partial_matches(by_name, spec)
                    and not _unapproved_options(by_name)
                )
                statuses.append(
                    PageMapIndexStatus(
                        spec,
                        PageMapIndexState.PRESENT if matches else PageMapIndexState.CONFLICT,
                        "" if matches else "stable name has different keys, options, or uniqueness",
                    )
                )
                continue
            equivalent = next(
                (
                    item
                    for item in existing
                    if _index_keys(item) == spec.keys
                    and _unique_matches(item, spec.unique)
                    and _partial_matches(item, spec)
                    and not _unapproved_options(item)
                ),
                None,
            )
            if equivalent is None:
                statuses.append(PageMapIndexStatus(spec, PageMapIndexState.MISSING))
            else:
                statuses.append(
                    PageMapIndexStatus(
                        spec,
                        PageMapIndexState.CONFLICT,
                        f"equivalent index uses another name: {equivalent.get('name')}",
                    )
                )
        return tuple(statuses)

    def plan(self) -> PageMapIndexPlan:
        return PageMapIndexPlan(self.status())

    def apply(self) -> PageMapIndexPlan:
        plan = self.plan()
        if plan.conflicts:
            raise DocumentPageMapIndexConflictError(
                "Document page-map index conflicts require review: "
                + ", ".join(item.spec.name for item in plan.conflicts)
            )
        collection = self.database[self.COLLECTION]
        for spec in plan.missing:
            options: dict[str, Any] = {"name": spec.name, "unique": spec.unique}
            if spec.partial_filter_expression is not None:
                options["partialFilterExpression"] = spec.partial_filter_expression
            collection.create_index(list(spec.keys), **options)
        applied = self.plan()
        if not applied.initialized:
            raise DocumentPageMapIndexConflictError(
                "Document page-map indexes could not be initialized exactly"
            )
        return applied


__all__ = [
    "DOCUMENT_PAGE_MAP_INDEXES",
    "DOCUMENT_PAGE_MAPS_COLLECTION",
    "DocumentPageMapIndexManager",
    "PageMapIndexPlan",
    "PageMapIndexSpec",
    "PageMapIndexState",
    "PageMapIndexStatus",
]

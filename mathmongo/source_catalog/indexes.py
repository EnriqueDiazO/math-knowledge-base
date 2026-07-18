"""Explicit, inspectable index management for Source Catalog collections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IndexState(str, Enum):
    """Observed state of one approved index specification."""

    PRESENT = "present"
    MISSING = "missing"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class IndexSpec:
    """Stable collection, name, keys, and uniqueness for one index."""

    collection: str
    name: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class IndexStatus:
    """Comparison between one specification and current database metadata."""

    spec: IndexSpec
    state: IndexState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class IndexPlan:
    """Read-only collection of index statuses and derived actions."""

    statuses: tuple[IndexStatus, ...]

    @property
    def missing(self) -> tuple[IndexSpec, ...]:
        """Return specifications that an explicit apply would create."""
        return tuple(item.spec for item in self.statuses if item.state == IndexState.MISSING)

    @property
    def conflicts(self) -> tuple[IndexStatus, ...]:
        """Return definitions that require human review."""
        return tuple(item for item in self.statuses if item.state == IndexState.CONFLICT)

    @property
    def present(self) -> tuple[IndexSpec, ...]:
        """Return specifications already present exactly as approved."""
        return tuple(item.spec for item in self.statuses if item.state == IndexState.PRESENT)


class IndexPlanConflictError(RuntimeError):
    """The requested stable index name or definition conflicts with MongoDB."""

    def __init__(self, conflicts: tuple[IndexStatus, ...]) -> None:
        """Retain structured conflicts and expose their safe index names."""
        self.conflicts = conflicts
        names = ", ".join(item.spec.name for item in conflicts)
        super().__init__(f"Source Catalog index conflicts require review: {names}")


SOURCE_CATALOG_INDEXES: tuple[IndexSpec, ...] = (
    IndexSpec("sources", "sources_source_id_unique", (("source_id", 1),), unique=True),
    IndexSpec("sources", "sources_name_normalized", (("name_normalized", 1),)),
    IndexSpec("sources", "sources_aliases_normalized", (("aliases.normalized", 1),)),
    IndexSpec(
        "sources",
        "sources_status_source_type",
        (("status", 1), ("source_type", 1)),
    ),
    IndexSpec("sources", "sources_tags", (("tags", 1),)),
    IndexSpec("sources", "sources_updated_at", (("updated_at", -1),)),
    IndexSpec(
        "references",
        "references_reference_id_unique",
        (("reference_id", 1),),
        unique=True,
    ),
    IndexSpec("references", "references_source_ids", (("source_ids", 1),)),
    IndexSpec(
        "references",
        "references_bibtex_key_normalized",
        (("bibtex.key_normalized", 1),),
    ),
    IndexSpec("references", "references_doi_normalized", (("doi_normalized", 1),)),
    IndexSpec(
        "references",
        "references_isbn_normalized",
        (("fingerprints.isbn_normalized", 1),),
    ),
    IndexSpec(
        "references",
        "references_author_title_year",
        (("fingerprints.author_title_year", 1),),
    ),
    IndexSpec("references", "references_year_title", (("year", -1), ("title", 1))),
    IndexSpec("references", "references_status", (("status", 1),)),
    IndexSpec("references", "references_updated_at", (("updated_at", -1),)),
)


def _index_keys(document: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    key = document.get("key", ())
    if hasattr(key, "items"):
        return tuple((str(field), int(direction)) for field, direction in key.items())
    return tuple((str(field), int(direction)) for field, direction in key)


def _unique_matches(document: dict[str, Any], expected: bool) -> bool:
    """Treat omission as false but reject non-boolean truthy representations."""
    if "unique" not in document:
        return expected is False
    return isinstance(document["unique"], bool) and document["unique"] is expected


def _unapproved_options(document: dict[str, Any]) -> tuple[str, ...]:
    """Exclude only server identity/version fields from semantic option checks."""
    approved_fields = {"key", "name", "unique", "v", "ns"}
    return tuple(sorted(str(name) for name in document if name not in approved_fields))


class SourceCatalogIndexManager:
    """Plan and explicitly apply only the approved Source Catalog indexes."""

    def __init__(self, database: Any) -> None:
        """Retain an explicit database without inspecting or modifying it."""
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("SourceCatalogIndexManager requires an explicit database")
        self.database = database

    def _existing(self, collection_name: str) -> tuple[dict[str, Any], ...]:
        if (
            hasattr(self.database, "list_collection_names")
            and collection_name not in self.database.list_collection_names()
        ):
            return ()
        return tuple(dict(item) for item in self.database[collection_name].list_indexes())

    def status(self, collection_names: set[str] | None = None) -> tuple[IndexStatus, ...]:
        """Inspect index metadata, optionally limited to explicit collections."""
        specs = tuple(
            spec
            for spec in SOURCE_CATALOG_INDEXES
            if collection_names is None or spec.collection in collection_names
        )
        existing_by_collection = {
            collection: self._existing(collection)
            for collection in {spec.collection for spec in specs}
        }
        statuses: list[IndexStatus] = []
        for spec in specs:
            existing = existing_by_collection[spec.collection]
            by_name = next((item for item in existing if item.get("name") == spec.name), None)
            if by_name is not None:
                keys_match = _index_keys(by_name) == spec.keys
                unique_matches = _unique_matches(by_name, spec.unique)
                unapproved_options = _unapproved_options(by_name)
                if keys_match and unique_matches and not unapproved_options:
                    statuses.append(IndexStatus(spec, IndexState.PRESENT))
                else:
                    detail = "stable name exists with different keys or uniqueness"
                    if keys_match and unique_matches and unapproved_options:
                        detail = "stable name exists with unapproved options: " + ",".join(
                            unapproved_options
                        )
                    statuses.append(
                        IndexStatus(
                            spec,
                            IndexState.CONFLICT,
                            detail,
                        )
                    )
                continue
            equivalent = next(
                (
                    item
                    for item in existing
                    if _index_keys(item) == spec.keys and _unique_matches(item, spec.unique)
                ),
                None,
            )
            if equivalent is not None:
                statuses.append(
                    IndexStatus(
                        spec,
                        IndexState.CONFLICT,
                        f"equivalent index uses another name: {equivalent.get('name')}",
                    )
                )
            else:
                statuses.append(IndexStatus(spec, IndexState.MISSING))
        return tuple(statuses)

    def plan(self, collection_names: set[str] | None = None) -> IndexPlan:
        """Return the explicit present/missing/conflict plan for a subset."""
        return IndexPlan(self.status(collection_names))

    def apply(self, collection_names: set[str] | None = None) -> IndexPlan:
        """Create missing indexes only for the requested collection subset."""
        plan = self.plan(collection_names)
        if plan.conflicts:
            raise IndexPlanConflictError(plan.conflicts)
        for spec in plan.missing:
            self.database[spec.collection].create_index(
                list(spec.keys),
                name=spec.name,
                unique=spec.unique,
            )
        applied = self.plan(collection_names)
        if applied.conflicts or applied.missing:
            if applied.conflicts:
                raise IndexPlanConflictError(applied.conflicts)
            missing_names = ", ".join(spec.name for spec in applied.missing)
            raise RuntimeError(f"Indexes still missing after explicit apply: {missing_names}")
        return applied


__all__ = [
    "IndexPlan",
    "IndexPlanConflictError",
    "IndexSpec",
    "IndexState",
    "IndexStatus",
    "SOURCE_CATALOG_INDEXES",
    "SourceCatalogIndexManager",
]

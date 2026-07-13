"""Explicit, inspectable index plan for S4 collections."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from mathmongo.reading_annotations.errors import ReadingAnnotationIndexConflictError

DOCUMENT_ANNOTATIONS_COLLECTION = "document_annotations"
READING_NOTES_COLLECTION = "reading_notes"
CONCEPT_EVIDENCE_LINKS_COLLECTION = "concept_evidence_links"


class ReadingAnnotationIndexState(str, Enum):
    PRESENT = "present"
    MISSING = "missing"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class ReadingAnnotationIndexSpec:
    collection: str
    name: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class ReadingAnnotationIndexStatus:
    spec: ReadingAnnotationIndexSpec
    state: ReadingAnnotationIndexState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ReadingAnnotationIndexPlan:
    statuses: tuple[ReadingAnnotationIndexStatus, ...]

    @property
    def missing(self) -> tuple[ReadingAnnotationIndexSpec, ...]:
        return tuple(
            item.spec for item in self.statuses if item.state == ReadingAnnotationIndexState.MISSING
        )

    @property
    def conflicts(self) -> tuple[ReadingAnnotationIndexStatus, ...]:
        return tuple(
            item for item in self.statuses if item.state == ReadingAnnotationIndexState.CONFLICT
        )

    @property
    def present(self) -> tuple[ReadingAnnotationIndexSpec, ...]:
        return tuple(
            item.spec for item in self.statuses if item.state == ReadingAnnotationIndexState.PRESENT
        )

    @property
    def initialized(self) -> bool:
        return not self.missing and not self.conflicts


ANNOTATION_INDEXES = (
    ReadingAnnotationIndexSpec(
        DOCUMENT_ANNOTATIONS_COLLECTION,
        "document_annotations_id_unique",
        (("annotation_id", 1),),
        unique=True,
    ),
    ReadingAnnotationIndexSpec(
        DOCUMENT_ANNOTATIONS_COLLECTION,
        "document_annotations_document_status_updated",
        (("document_id", 1), ("status", 1), ("updated_at", -1)),
    ),
    ReadingAnnotationIndexSpec(
        DOCUMENT_ANNOTATIONS_COLLECTION,
        "document_annotations_source_status_updated",
        (("source_id", 1), ("status", 1), ("updated_at", -1)),
    ),
    ReadingAnnotationIndexSpec(
        DOCUMENT_ANNOTATIONS_COLLECTION,
        "document_annotations_reference",
        (("reference_id", 1),),
    ),
    ReadingAnnotationIndexSpec(
        DOCUMENT_ANNOTATIONS_COLLECTION,
        "document_annotations_kind",
        (("kind", 1),),
    ),
    ReadingAnnotationIndexSpec(
        DOCUMENT_ANNOTATIONS_COLLECTION,
        "document_annotations_tags",
        (("tags", 1),),
    ),
)

READING_NOTE_INDEXES = (
    ReadingAnnotationIndexSpec(
        READING_NOTES_COLLECTION,
        "reading_notes_id_unique",
        (("note_id", 1),),
        unique=True,
    ),
    ReadingAnnotationIndexSpec(
        READING_NOTES_COLLECTION,
        "reading_notes_document_status_updated",
        (("document_id", 1), ("status", 1), ("updated_at", -1)),
    ),
    ReadingAnnotationIndexSpec(
        READING_NOTES_COLLECTION,
        "reading_notes_source_status_updated",
        (("source_id", 1), ("status", 1), ("updated_at", -1)),
    ),
    ReadingAnnotationIndexSpec(
        READING_NOTES_COLLECTION,
        "reading_notes_reference",
        (("reference_id", 1),),
    ),
    ReadingAnnotationIndexSpec(
        READING_NOTES_COLLECTION,
        "reading_notes_type",
        (("note_type", 1),),
    ),
    ReadingAnnotationIndexSpec(
        READING_NOTES_COLLECTION,
        "reading_notes_tags",
        (("tags", 1),),
    ),
)

CONCEPT_EVIDENCE_INDEXES = (
    ReadingAnnotationIndexSpec(
        CONCEPT_EVIDENCE_LINKS_COLLECTION,
        "concept_evidence_links_id_unique",
        (("evidence_link_id", 1),),
        unique=True,
    ),
    ReadingAnnotationIndexSpec(
        CONCEPT_EVIDENCE_LINKS_COLLECTION,
        "concept_evidence_links_concept_status",
        (("concept_legacy_source", 1), ("concept_legacy_id", 1), ("status", 1)),
    ),
    ReadingAnnotationIndexSpec(
        CONCEPT_EVIDENCE_LINKS_COLLECTION,
        "concept_evidence_links_document_status",
        (("document_id", 1), ("status", 1)),
    ),
    ReadingAnnotationIndexSpec(
        CONCEPT_EVIDENCE_LINKS_COLLECTION,
        "concept_evidence_links_annotation",
        (("annotation_id", 1),),
    ),
    ReadingAnnotationIndexSpec(
        CONCEPT_EVIDENCE_LINKS_COLLECTION,
        "concept_evidence_links_note",
        (("note_id", 1),),
    ),
    ReadingAnnotationIndexSpec(
        CONCEPT_EVIDENCE_LINKS_COLLECTION,
        "concept_evidence_links_source_status",
        (("source_id", 1), ("status", 1)),
    ),
    ReadingAnnotationIndexSpec(
        CONCEPT_EVIDENCE_LINKS_COLLECTION,
        "concept_evidence_links_exact_identity_unique",
        (
            ("concept_legacy_source", 1),
            ("concept_legacy_id", 1),
            ("source_id", 1),
            ("reference_id", 1),
            ("document_id", 1),
            ("annotation_id", 1),
            ("note_id", 1),
            ("page_number", 1),
            ("link_type", 1),
        ),
        unique=True,
    ),
)

READING_ANNOTATION_INDEXES = (
    *ANNOTATION_INDEXES,
    *READING_NOTE_INDEXES,
    *CONCEPT_EVIDENCE_INDEXES,
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


def _unapproved_options(document: dict[str, Any]) -> tuple[str, ...]:
    approved = {"key", "name", "unique", "v", "ns"}
    return tuple(sorted(str(name) for name in document if name not in approved))


class ReadingAnnotationIndexManager:
    """Inspect or explicitly apply only the approved S4 indexes."""

    def __init__(self, database: Any) -> None:
        if database is None or not hasattr(database, "__getitem__"):
            raise ValueError("ReadingAnnotationIndexManager requires an explicit database")
        self.database = database

    def _existing(self, collection_name: str) -> tuple[dict[str, Any], ...]:
        if (
            hasattr(self.database, "list_collection_names")
            and collection_name not in self.database.list_collection_names()
        ):
            return ()
        return tuple(dict(item) for item in self.database[collection_name].list_indexes())

    def status(self) -> tuple[ReadingAnnotationIndexStatus, ...]:
        existing_by_collection = {
            collection: self._existing(collection)
            for collection in (
                DOCUMENT_ANNOTATIONS_COLLECTION,
                READING_NOTES_COLLECTION,
                CONCEPT_EVIDENCE_LINKS_COLLECTION,
            )
        }
        statuses: list[ReadingAnnotationIndexStatus] = []
        for spec in READING_ANNOTATION_INDEXES:
            existing = existing_by_collection[spec.collection]
            by_name = next((item for item in existing if item.get("name") == spec.name), None)
            if by_name is not None:
                keys_match = _index_keys(by_name) == spec.keys
                unique_match = _unique_matches(by_name, spec.unique)
                extras = _unapproved_options(by_name)
                if keys_match and unique_match and not extras:
                    statuses.append(
                        ReadingAnnotationIndexStatus(spec, ReadingAnnotationIndexState.PRESENT)
                    )
                else:
                    detail = "stable name exists with different keys or uniqueness"
                    if keys_match and unique_match and extras:
                        detail = "stable name exists with unapproved options: " + ",".join(extras)
                    statuses.append(
                        ReadingAnnotationIndexStatus(
                            spec,
                            ReadingAnnotationIndexState.CONFLICT,
                            detail,
                        )
                    )
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
                statuses.append(
                    ReadingAnnotationIndexStatus(spec, ReadingAnnotationIndexState.MISSING)
                )
            else:
                statuses.append(
                    ReadingAnnotationIndexStatus(
                        spec,
                        ReadingAnnotationIndexState.CONFLICT,
                        f"equivalent index uses another name: {equivalent.get('name')}",
                    )
                )
        return tuple(statuses)

    def plan(self) -> ReadingAnnotationIndexPlan:
        return ReadingAnnotationIndexPlan(self.status())

    def apply(self) -> ReadingAnnotationIndexPlan:
        plan = self.plan()
        if plan.conflicts:
            raise ReadingAnnotationIndexConflictError(
                "Reading annotation index conflicts require review: "
                + ", ".join(item.spec.name for item in plan.conflicts)
            )
        for spec in plan.missing:
            self.database[spec.collection].create_index(
                list(spec.keys),
                name=spec.name,
                unique=spec.unique,
            )
        applied = self.plan()
        if not applied.initialized:
            raise ReadingAnnotationIndexConflictError(
                "Reading annotation indexes could not be initialized exactly"
            )
        return applied


__all__ = [
    "ANNOTATION_INDEXES",
    "CONCEPT_EVIDENCE_INDEXES",
    "CONCEPT_EVIDENCE_LINKS_COLLECTION",
    "DOCUMENT_ANNOTATIONS_COLLECTION",
    "READING_ANNOTATION_INDEXES",
    "READING_NOTES_COLLECTION",
    "READING_NOTE_INDEXES",
    "ReadingAnnotationIndexManager",
    "ReadingAnnotationIndexPlan",
    "ReadingAnnotationIndexSpec",
    "ReadingAnnotationIndexState",
    "ReadingAnnotationIndexStatus",
]

"""Independent MongoDB indexes for Source Documents (outside the S1 catalog plan)."""

# ruff: noqa: D101,D102,D107

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceDocumentIndexSpec:
    name: str
    keys: tuple[tuple[str, int], ...]
    unique: bool = False
    partial_filter: dict[str, Any] | None = None


SOURCE_DOCUMENT_INDEXES = (
    SourceDocumentIndexSpec(
        "source_documents_document_id_unique",
        (("document_id", 1),),
        unique=True,
    ),
    SourceDocumentIndexSpec(
        "source_documents_source_status_updated",
        (("source_id", 1), ("status", 1), ("updated_at", -1)),
    ),
    SourceDocumentIndexSpec(
        "source_documents_reference_source",
        (("reference_id", 1), ("source_id", 1)),
    ),
    SourceDocumentIndexSpec(
        "source_documents_source_pdf_sha_unique",
        (("source_id", 1), ("pdf.versions.sha256", 1)),
        unique=True,
        partial_filter={"kind": "pdf"},
    ),
    SourceDocumentIndexSpec(
        "source_documents_source_web_url_unique",
        (("source_id", 1), ("web.url_normalized", 1)),
        unique=True,
        partial_filter={"kind": "web"},
    ),
)


class SourceDocumentIndexManager:
    """Apply only the isolated S2 index set after a confirmed document write."""

    def __init__(self, database: Any) -> None:
        self.database = database

    def ensure(self) -> tuple[str, ...]:
        """Create the approved idempotent indexes and return their names."""
        collection = self.database["source_documents"]
        names: list[str] = []
        for spec in SOURCE_DOCUMENT_INDEXES:
            kwargs: dict[str, Any] = {"name": spec.name, "unique": spec.unique}
            if spec.partial_filter is not None:
                kwargs["partialFilterExpression"] = spec.partial_filter
            collection.create_index(list(spec.keys), **kwargs)
            names.append(spec.name)
        return tuple(names)


__all__ = [
    "SOURCE_DOCUMENT_INDEXES",
    "SourceDocumentIndexManager",
    "SourceDocumentIndexSpec",
]

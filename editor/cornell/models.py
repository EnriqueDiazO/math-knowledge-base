"""Persistible data structures for Cornell-format math notes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CORNELL_NOTE_FORMAT = "cornell_math_v1"
DEFAULT_TEMPLATE_ID = "historical_cornell_math_letter_v1"


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _require_text(value: Any, field_name: str, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _tuple_of_strings(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise ValueError(f"{field_name} must be a sequence of strings")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a sequence of strings") from exc
    if not all(isinstance(item, str) for item in values):
        raise ValueError(f"{field_name} must contain only strings")
    return values


def _tuple_of_mappings(value: Any, field_name: str) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a sequence of mappings")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be a sequence of mappings") from exc
    if not all(isinstance(item, Mapping) for item in values):
        raise ValueError(f"{field_name} must contain only mappings")
    return tuple(dict(item) for item in values)


@dataclass(frozen=True, slots=True)
class CornellRegion:
    """One semantic region inside a Cornell page."""

    heading: str
    latex: str
    image_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Normalize image identifiers and validate text fields."""
        _require_text(self.heading, "heading")
        _require_text(self.latex, "latex")
        object.__setattr__(self, "image_ids", _tuple_of_strings(self.image_ids, "image_ids"))

    def to_dict(self) -> dict[str, Any]:
        """Serialize this region to a MongoDB-compatible dictionary."""
        return {
            "heading": self.heading,
            "latex": self.latex,
            "image_ids": list(self.image_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CornellRegion:
        """Build a region from a MongoDB-compatible dictionary."""
        source = _require_mapping(data, "region")
        return cls(
            heading=_require_text(source.get("heading"), "heading"),
            latex=_require_text(source.get("latex"), "latex"),
            image_ids=_tuple_of_strings(source.get("image_ids", ()), "image_ids"),
        )


@dataclass(frozen=True, slots=True)
class CornellPage:
    """One Cornell page with three synchronized semantic regions."""

    page_id: str
    order: int
    cue: CornellRegion
    main: CornellRegion
    summary: CornellRegion
    source_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        """Validate the page identity, order, regions, and source refs."""
        _require_text(self.page_id, "page_id", allow_empty=False)
        order = _require_int(self.order, "order")
        if order < 1:
            raise ValueError("order must be greater than or equal to 1")
        for field_name in ("cue", "main", "summary"):
            if not isinstance(getattr(self, field_name), CornellRegion):
                raise ValueError(f"{field_name} must be a CornellRegion")
        object.__setattr__(
            self,
            "source_refs",
            _tuple_of_mappings(self.source_refs, "source_refs"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize this page to a MongoDB-compatible dictionary."""
        return {
            "page_id": self.page_id,
            "order": self.order,
            "cue": self.cue.to_dict(),
            "main": self.main.to_dict(),
            "summary": self.summary.to_dict(),
            "source_refs": [dict(source_ref) for source_ref in self.source_refs],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CornellPage:
        """Build a page from a MongoDB-compatible dictionary."""
        source = _require_mapping(data, "page")
        return cls(
            page_id=_require_text(source.get("page_id"), "page_id", allow_empty=False),
            order=_require_int(source.get("order"), "order"),
            cue=CornellRegion.from_dict(_require_mapping(source.get("cue"), "cue")),
            main=CornellRegion.from_dict(_require_mapping(source.get("main"), "main")),
            summary=CornellRegion.from_dict(_require_mapping(source.get("summary"), "summary")),
            source_refs=_tuple_of_mappings(source.get("source_refs", ()), "source_refs"),
        )


@dataclass(frozen=True, slots=True)
class CornellDocument:
    """Persistible Cornell math document payload."""

    schema_version: int
    template_id: str
    pages: tuple[CornellPage, ...]

    def __post_init__(self) -> None:
        """Validate schema version and page uniqueness constraints."""
        schema_version = _require_int(self.schema_version, "schema_version")
        if schema_version < 1:
            raise ValueError("schema_version must be greater than or equal to 1")
        _require_text(self.template_id, "template_id", allow_empty=False)
        object.__setattr__(self, "pages", tuple(self.pages))
        if not all(isinstance(page, CornellPage) for page in self.pages):
            raise ValueError("pages must contain only CornellPage instances")

        page_ids = [page.page_id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("page_id values must be unique")
        page_orders = [page.order for page in self.pages]
        if len(page_orders) != len(set(page_orders)):
            raise ValueError("page orders must be unique")

    def ordered_pages(self) -> tuple[CornellPage, ...]:
        """Return pages sorted by their explicit page order."""
        return tuple(sorted(self.pages, key=lambda page: page.order))

    def to_dict(self) -> dict[str, Any]:
        """Serialize this document to a MongoDB-compatible dictionary."""
        return {
            "schema_version": self.schema_version,
            "template_id": self.template_id,
            "pages": [page.to_dict() for page in self.ordered_pages()],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CornellDocument:
        """Build a Cornell document from a MongoDB-compatible dictionary."""
        source = _require_mapping(data, "cornell")
        raw_pages = source.get("pages")
        if raw_pages is None or isinstance(raw_pages, (str, bytes)):
            raise ValueError("pages must be a sequence of page dictionaries")
        try:
            pages = tuple(CornellPage.from_dict(page) for page in raw_pages)
        except TypeError as exc:
            raise ValueError("pages must be a sequence of page dictionaries") from exc
        return cls(
            schema_version=_require_int(source.get("schema_version"), "schema_version"),
            template_id=_require_text(source.get("template_id"), "template_id", allow_empty=False),
            pages=pages,
        )


def generate_latex_body(document: CornellDocument) -> str:
    """Generate a compatibility latex_body derived from a Cornell document."""
    blocks: list[str] = []
    for page in document.ordered_pages():
        blocks.extend(
            [
                f"% Cornell page {page.order}: {page.page_id}",
                f"\\paragraph*{{{page.cue.heading}}}",
                page.cue.latex,
                f"\\paragraph*{{{page.main.heading}}}",
                page.main.latex,
                f"\\paragraph*{{{page.summary.heading}}}",
                page.summary.latex,
            ]
        )
    return "\n\n".join(block.strip() for block in blocks if block.strip())


def build_cornell_math_v1_payload(document: CornellDocument) -> dict[str, Any]:
    """Build the persistible cornell_math_v1 fragment for latex_notes."""
    return {
        "note_format": CORNELL_NOTE_FORMAT,
        "latex_body": generate_latex_body(document),
        "cornell": document.to_dict(),
    }

"""Persistible data structures for Cornell-format math notes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from typing import Any

CORNELL_NOTE_FORMAT = "cornell_math_v1"
DEFAULT_TEMPLATE_ID = "historical_cornell_math_letter_v1"
IDENTITY_POSITIONS = ("center", "bottom_right", "top_right")
WATERMARK_TYPES = ("text", "image")
FOOTER_MODES = ("auto", "custom")


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


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _require_float(
    value: Any,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    result = float(value)
    if result < minimum or result > maximum:
        raise ValueError(f"{field_name} must be between {minimum:g} and {maximum:g}")
    return result


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


def _position(value: Any, field_name: str, *, default: str) -> str:
    text = str(value or default).strip()
    if text not in IDENTITY_POSITIONS:
        allowed = ", ".join(IDENTITY_POSITIONS)
        raise ValueError(f"{field_name} must be one of: {allowed}")
    return text


def _footer_mode(value: Any, *, text: str = "") -> str:
    raw = str(value or "").strip()
    if not raw:
        return "custom" if text.strip() else "auto"
    if raw not in FOOTER_MODES:
        allowed = ", ".join(FOOTER_MODES)
        raise ValueError(f"attribution.mode must be one of: {allowed}")
    return raw


@dataclass(frozen=True, slots=True)
class CornellAttribution:
    """Optional page attribution rendered outside Cornell content regions."""

    enabled: bool = False
    mode: str = ""
    text: str = ""
    author: str = ""
    course: str = ""
    year: str = ""
    position: str = "bottom_right"

    def __post_init__(self) -> None:
        """Validate attribution settings."""
        _require_bool(self.enabled, "attribution.enabled")
        _require_text(self.text, "attribution.text")
        object.__setattr__(self, "mode", _footer_mode(self.mode, text=self.text))
        _require_text(self.author, "attribution.author")
        _require_text(self.course, "attribution.course")
        _require_text(self.year, "attribution.year")
        object.__setattr__(
            self,
            "position",
            _position(self.position, "attribution.position", default="bottom_right"),
        )

    def display_text(self) -> str:
        """Return the final footer text for rendering."""
        return build_footer_text(self)

    def to_dict(self) -> dict[str, Any]:
        """Serialize attribution settings."""
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "text": self.text,
            "author": self.author,
            "course": self.course,
            "year": self.year,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> CornellAttribution:
        """Build attribution settings from a persisted dictionary."""
        source = _require_mapping(data or {}, "attribution")
        text = _require_text(source.get("text", ""), "attribution.text")
        return cls(
            enabled=_require_bool(source.get("enabled", False), "attribution.enabled"),
            mode=_footer_mode(source.get("mode", source.get("footer_mode")), text=text),
            text=text,
            author=_require_text(source.get("author", ""), "attribution.author"),
            course=_require_text(source.get("course", ""), "attribution.course"),
            year=_require_text(source.get("year", ""), "attribution.year"),
            position=_position(source.get("position"), "attribution.position", default="bottom_right"),
        )


def build_footer_text(
    attribution: CornellAttribution | None = None,
    *,
    mode: str | None = None,
    text: str = "",
    author: str = "",
    course: str = "",
    year: str = "",
) -> str:
    """Build the final attribution footer text without duplicate separators."""
    if attribution is not None:
        mode = attribution.mode
        text = attribution.text
        author = attribution.author
        course = attribution.course
        year = attribution.year
    clean_text = text.strip()
    clean_author = author.strip()
    clean_course = course.strip()
    clean_year = year.strip()
    footer_mode = _footer_mode(mode, text=clean_text)
    if footer_mode == "custom":
        return clean_text
    if clean_author:
        owner = f"© {clean_year} {clean_author}" if clean_year else f"© {clean_author}"
        parts = [owner]
        if clean_course:
            parts.append(clean_course)
        return " · ".join(parts)
    return " · ".join(part for part in (clean_course, clean_year) if part)


@dataclass(frozen=True, slots=True)
class CornellWatermark:
    """Optional text or image watermark rendered behind Cornell page content."""

    enabled: bool = False
    type: str = "text"
    text: str = ""
    image_id: str = ""
    opacity: float = 0.05
    scale: float = 0.4
    position: str = "center"

    def __post_init__(self) -> None:
        """Validate watermark settings."""
        _require_bool(self.enabled, "watermark.enabled")
        watermark_type = str(self.type or "text").strip()
        if watermark_type not in WATERMARK_TYPES:
            allowed = ", ".join(WATERMARK_TYPES)
            raise ValueError(f"watermark.type must be one of: {allowed}")
        object.__setattr__(self, "type", watermark_type)
        _require_text(self.text, "watermark.text")
        _require_text(self.image_id, "watermark.image_id")
        object.__setattr__(
            self,
            "opacity",
            _require_float(self.opacity, "watermark.opacity", minimum=0.0, maximum=1.0),
        )
        object.__setattr__(
            self,
            "scale",
            _require_float(self.scale, "watermark.scale", minimum=0.05, maximum=2.0),
        )
        object.__setattr__(
            self,
            "position",
            _position(self.position, "watermark.position", default="center"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize watermark settings."""
        return {
            "enabled": self.enabled,
            "type": self.type,
            "text": self.text,
            "image_id": self.image_id,
            "opacity": self.opacity,
            "scale": self.scale,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> CornellWatermark:
        """Build watermark settings from a persisted dictionary."""
        source = _require_mapping(data or {}, "watermark")
        return cls(
            enabled=_require_bool(source.get("enabled", False), "watermark.enabled"),
            type=_require_text(source.get("type", "text"), "watermark.type", allow_empty=False),
            text=_require_text(source.get("text", ""), "watermark.text"),
            image_id=_require_text(source.get("image_id", ""), "watermark.image_id"),
            opacity=_require_float(source.get("opacity", 0.05), "watermark.opacity", minimum=0.0, maximum=1.0),
            scale=_require_float(source.get("scale", 0.4), "watermark.scale", minimum=0.05, maximum=2.0),
            position=_position(source.get("position"), "watermark.position", default="center"),
        )


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
    attribution: CornellAttribution = field(default_factory=CornellAttribution)
    watermark: CornellWatermark = field(default_factory=CornellWatermark)

    def __post_init__(self) -> None:
        """Validate schema version and page uniqueness constraints."""
        schema_version = _require_int(self.schema_version, "schema_version")
        if schema_version < 1:
            raise ValueError("schema_version must be greater than or equal to 1")
        _require_text(self.template_id, "template_id", allow_empty=False)
        object.__setattr__(self, "pages", tuple(self.pages))
        if not all(isinstance(page, CornellPage) for page in self.pages):
            raise ValueError("pages must contain only CornellPage instances")
        if not isinstance(self.attribution, CornellAttribution):
            raise ValueError("attribution must be a CornellAttribution")
        if not isinstance(self.watermark, CornellWatermark):
            raise ValueError("watermark must be a CornellWatermark")

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
            "attribution": self.attribution.to_dict(),
            "watermark": self.watermark.to_dict(),
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
            attribution=CornellAttribution.from_dict(source.get("attribution")),
            watermark=CornellWatermark.from_dict(source.get("watermark")),
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

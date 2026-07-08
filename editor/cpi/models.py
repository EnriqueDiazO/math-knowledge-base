"""Persistible data structures for CPI notes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellWatermark

CPI_NOTE_FORMAT = "cpi_v1"
DEFAULT_TEMPLATE_ID = "cpi_landscape_letter_v1"


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


def _coerce_attribution(value: Any) -> CornellAttribution:
    if isinstance(value, CornellAttribution):
        return value
    if value is None:
        return CornellAttribution()
    if isinstance(value, Mapping):
        return CornellAttribution.from_dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return CornellAttribution.from_dict(to_dict())
    raise ValueError("attribution must be a CornellAttribution")


def _coerce_watermark(value: Any) -> CornellWatermark:
    if isinstance(value, CornellWatermark):
        return value
    if value is None:
        return CornellWatermark()
    if isinstance(value, Mapping):
        return CornellWatermark.from_dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return CornellWatermark.from_dict(to_dict())
    raise ValueError("watermark must be a CornellWatermark")


@dataclass(frozen=True, slots=True)
class CpiRegion:
    """One semantic region inside a CPI page."""

    heading: str
    latex: str
    image_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Validate persisted text fields."""
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
    def from_dict(cls, data: Mapping[str, Any]) -> CpiRegion:
        """Build a region from a MongoDB-compatible dictionary."""
        source = _require_mapping(data, "region")
        return cls(
            heading=_require_text(source.get("heading"), "heading"),
            latex=_require_text(source.get("latex"), "latex"),
            image_ids=_tuple_of_strings(source.get("image_ids", ()), "image_ids"),
        )


@dataclass(frozen=True, slots=True)
class CpiPage:
    """One CPI page with comprehension, production, and integration regions."""

    page_number: int
    comprehension: CpiRegion
    production: CpiRegion
    integration: CpiRegion

    def __post_init__(self) -> None:
        """Validate the page number and regions."""
        page_number = _require_int(self.page_number, "page_number")
        if page_number < 1:
            raise ValueError("page_number must be greater than or equal to 1")
        for field_name in ("comprehension", "production", "integration"):
            if not isinstance(getattr(self, field_name), CpiRegion):
                raise ValueError(f"{field_name} must be a CpiRegion")

    def to_dict(self) -> dict[str, Any]:
        """Serialize this page to a MongoDB-compatible dictionary."""
        return {
            "page_number": self.page_number,
            "comprehension": self.comprehension.to_dict(),
            "production": self.production.to_dict(),
            "integration": self.integration.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CpiPage:
        """Build a page from a MongoDB-compatible dictionary."""
        source = _require_mapping(data, "page")
        return cls(
            page_number=_require_int(source.get("page_number"), "page_number"),
            comprehension=CpiRegion.from_dict(
                _require_mapping(source.get("comprehension"), "comprehension")
            ),
            production=CpiRegion.from_dict(
                _require_mapping(source.get("production"), "production")
            ),
            integration=CpiRegion.from_dict(
                _require_mapping(source.get("integration"), "integration")
            ),
        )


@dataclass(frozen=True, slots=True)
class CpiDocument:
    """Persistible CPI document payload."""

    schema_version: int
    template_id: str
    pages: tuple[CpiPage, ...]
    attribution: CornellAttribution = field(default_factory=CornellAttribution)
    watermark: CornellWatermark = field(default_factory=CornellWatermark)

    def __post_init__(self) -> None:
        """Validate schema version and page-number uniqueness."""
        schema_version = _require_int(self.schema_version, "schema_version")
        if schema_version < 1:
            raise ValueError("schema_version must be greater than or equal to 1")
        _require_text(self.template_id, "template_id", allow_empty=False)
        object.__setattr__(self, "pages", tuple(self.pages))
        if not all(isinstance(page, CpiPage) for page in self.pages):
            raise ValueError("pages must contain only CpiPage instances")
        object.__setattr__(self, "attribution", _coerce_attribution(self.attribution))
        object.__setattr__(self, "watermark", _coerce_watermark(self.watermark))
        page_numbers = [page.page_number for page in self.pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ValueError("page_number values must be unique")

    def ordered_pages(self) -> tuple[CpiPage, ...]:
        """Return pages sorted by their explicit page number."""
        return tuple(sorted(self.pages, key=lambda page: page.page_number))

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
    def from_dict(cls, data: Mapping[str, Any]) -> CpiDocument:
        """Build a CPI document from a MongoDB-compatible dictionary."""
        source = _require_mapping(data, "cpi")
        raw_pages = source.get("pages")
        if raw_pages is None or isinstance(raw_pages, (str, bytes)):
            raise ValueError("pages must be a sequence of page dictionaries")
        try:
            pages = tuple(CpiPage.from_dict(page) for page in raw_pages)
        except TypeError as exc:
            raise ValueError("pages must be a sequence of page dictionaries") from exc
        return cls(
            schema_version=_require_int(source.get("schema_version"), "schema_version"),
            template_id=_require_text(source.get("template_id"), "template_id", allow_empty=False),
            pages=pages,
            attribution=CornellAttribution.from_dict(source.get("attribution")),
            watermark=CornellWatermark.from_dict(source.get("watermark")),
        )


def generate_latex_body(document: CpiDocument) -> str:
    """Generate a compatibility latex_body derived from a CPI document."""
    blocks: list[str] = []
    for page in document.ordered_pages():
        blocks.extend(
            [
                f"% CPI page {page.page_number}",
                f"\\paragraph*{{{page.comprehension.heading}}}",
                page.comprehension.latex,
                f"\\paragraph*{{{page.production.heading}}}",
                page.production.latex,
                f"\\paragraph*{{{page.integration.heading}}}",
                page.integration.latex,
            ]
        )
    return "\n\n".join(block.strip() for block in blocks if block.strip())


def build_cpi_v1_payload(document: CpiDocument) -> dict[str, Any]:
    """Build the persistible cpi_v1 fragment for latex_notes."""
    return {
        "note_format": CPI_NOTE_FORMAT,
        "latex_body": generate_latex_body(document),
        "cpi": document.to_dict(),
    }

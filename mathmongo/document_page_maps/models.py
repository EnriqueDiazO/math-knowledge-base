"""Strict S4.2 contracts and pure page-label computation."""

# ruff: noqa: D101,D102,D103

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from enum import Enum
from typing import Any
from typing import Literal
from uuid import UUID
from uuid import uuid4

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from mathmongo.reading_space.models import LOCAL_USER_SCOPE
from mathmongo.source_catalog.models import validate_source_id
from mathmongo.source_documents.models import validate_document_id

DOCUMENT_PAGE_MAP_SCHEMA_VERSION = 1
MAX_PAGE_MAP_RULES = 500
MAX_PAGE_MAP_OVERRIDES = 2_000
MAX_PAGE_LABEL_CHARS = 200
MAX_PAGE_PREFIX_CHARS = 100


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_page_map_id() -> str:
    return f"pmap_{uuid4()}"


def new_rule_id() -> str:
    return f"prule_{uuid4()}"


def _validate_uuid4_id(value: Any, *, prefix: str, field_name: str) -> str:
    text = str(value or "")
    marker = f"{prefix}_"
    if not text.startswith(marker):
        raise ValueError(f"{field_name} must start with {marker!r}")
    suffix = text[len(marker) :]
    try:
        parsed = UUID(suffix)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain a UUID v4 after {marker!r}") from exc
    if parsed.version != 4 or str(parsed) != suffix:
        raise ValueError(f"{field_name} must contain a canonical lowercase UUID v4")
    return text


def validate_page_map_id(value: Any) -> str:
    return _validate_uuid4_id(value, prefix="pmap", field_name="page_map_id")


def validate_rule_id(value: Any) -> str:
    return _validate_uuid4_id(value, prefix="prule", field_name="rule_id")


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _strict_positive_int(value: Any, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be a strict integer greater than or equal to 1")
    return value


def _bounded_text(value: Any, *, field_name: str, maximum: int) -> str:
    if isinstance(value, bytes):
        raise ValueError(f"{field_name} must be text, not bytes")
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    if len(text) > maximum:
        raise ValueError(f"{field_name} cannot exceed {maximum} characters")
    if "\x00" in text:
        raise ValueError(f"{field_name} cannot contain NUL characters")
    return text


class PageMapModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PageLabelStyle(str, Enum):
    ARABIC = "arabic"
    ROMAN_LOWER = "roman_lower"
    ROMAN_UPPER = "roman_upper"
    LITERAL = "literal"


class PageMapStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class PageLabelRule(PageMapModel):
    rule_id: str = Field(default_factory=new_rule_id, frozen=True)
    pdf_start_page: int = Field(ge=1)
    pdf_end_page: int | None = Field(default=None, ge=1)
    label_start: int | str
    label_style: PageLabelStyle = PageLabelStyle.ARABIC
    label_prefix: str | None = None

    @field_validator("rule_id")
    @classmethod
    def rule_id_is_valid(cls, value: Any) -> str:
        return validate_rule_id(value)

    @field_validator("pdf_start_page", "pdf_end_page", mode="before")
    @classmethod
    def pages_are_strict(cls, value: Any, info: Any) -> Any:
        if value is None and info.field_name == "pdf_end_page":
            return None
        return _strict_positive_int(value, info.field_name)

    @field_validator("label_start", mode="before")
    @classmethod
    def label_start_is_strict_scalar(cls, value: Any) -> int | str:
        if type(value) not in {int, str}:
            raise ValueError("label_start must be a strict integer or text")
        return value

    @field_validator("label_prefix", mode="before")
    @classmethod
    def prefix_is_optional_bounded_text(cls, value: Any) -> str | None:
        if value is None or not str(value).strip():
            return None
        return _bounded_text(
            value,
            field_name="label_prefix",
            maximum=MAX_PAGE_PREFIX_CHARS,
        )

    @model_validator(mode="after")
    def rule_is_consistent(self) -> PageLabelRule:
        if self.pdf_end_page is not None and self.pdf_end_page < self.pdf_start_page:
            raise ValueError("pdf_end_page cannot be earlier than pdf_start_page")
        if self.label_style == PageLabelStyle.LITERAL:
            if type(self.label_start) is not str:
                raise ValueError("literal rules require label_start text")
            literal = _bounded_text(
                self.label_start,
                field_name="label_start",
                maximum=MAX_PAGE_LABEL_CHARS,
            )
            object.__setattr__(self, "label_start", literal)
        elif type(self.label_start) is not int or self.label_start < 1:
            raise ValueError("arabic and roman rules require a positive strict integer label_start")
        return self


class ManualPageOverride(PageMapModel):
    pdf_page: int = Field(ge=1)
    book_page_label: str

    @field_validator("pdf_page", mode="before")
    @classmethod
    def page_is_strict(cls, value: Any) -> int:
        return _strict_positive_int(value, "pdf_page")

    @field_validator("book_page_label", mode="before")
    @classmethod
    def label_is_nonempty(cls, value: Any) -> str:
        return _bounded_text(
            value,
            field_name="book_page_label",
            maximum=MAX_PAGE_LABEL_CHARS,
        )


class DocumentPageMap(PageMapModel):
    schema_version: Literal[DOCUMENT_PAGE_MAP_SCHEMA_VERSION] = DOCUMENT_PAGE_MAP_SCHEMA_VERSION
    page_map_id: str = Field(default_factory=new_page_map_id, frozen=True)
    document_id: str = Field(frozen=True)
    source_id: str = Field(frozen=True)
    user_scope: Literal[LOCAL_USER_SCOPE] = Field(default=LOCAL_USER_SCOPE, frozen=True)
    status: PageMapStatus = PageMapStatus.ACTIVE
    rules: list[PageLabelRule] = Field(default_factory=list)
    manual_overrides: list[ManualPageOverride] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @field_validator("page_map_id")
    @classmethod
    def page_map_id_is_valid(cls, value: Any) -> str:
        return validate_page_map_id(value)

    @field_validator("document_id")
    @classmethod
    def document_id_is_valid(cls, value: Any) -> str:
        return validate_document_id(value)

    @field_validator("source_id")
    @classmethod
    def source_id_is_valid(cls, value: Any) -> str:
        return validate_source_id(value)

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def page_map_is_consistent(self) -> DocumentPageMap:
        if len(self.rules) > MAX_PAGE_MAP_RULES:
            raise ValueError(f"page map cannot contain more than {MAX_PAGE_MAP_RULES} rules")
        if len(self.manual_overrides) > MAX_PAGE_MAP_OVERRIDES:
            raise ValueError(
                f"page map cannot contain more than {MAX_PAGE_MAP_OVERRIDES} manual overrides"
            )
        rules = sorted(
            self.rules,
            key=lambda item: (
                item.pdf_start_page,
                item.pdf_end_page if item.pdf_end_page is not None else float("inf"),
                item.rule_id,
            ),
        )
        if len({item.rule_id for item in rules}) != len(rules):
            raise ValueError("page label rules must have unique rule_id values")
        for previous, current in zip(rules, rules[1:], strict=False):
            if previous.pdf_end_page is None or current.pdf_start_page <= previous.pdf_end_page:
                raise ValueError("page label rules cannot overlap")
        overrides = sorted(self.manual_overrides, key=lambda item: item.pdf_page)
        if len({item.pdf_page for item in overrides}) != len(overrides):
            raise ValueError("manual page overrides must have unique pdf_page values")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        archived_at = self.archived_at
        if self.status == PageMapStatus.ARCHIVED and archived_at is None:
            archived_at = self.updated_at
        if self.status == PageMapStatus.ACTIVE and archived_at is not None:
            raise ValueError("active page map cannot have archived_at")
        if archived_at is not None and not self.created_at <= archived_at <= self.updated_at:
            raise ValueError("archived_at must be between created_at and updated_at")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "manual_overrides", overrides)
        object.__setattr__(self, "archived_at", archived_at)
        return self


def _roman(number: int) -> str:
    values = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    remainder = number
    result: list[str] = []
    for value, token in values:
        count, remainder = divmod(remainder, value)
        if count:
            result.append(token * count)
    return "".join(result)


def compute_book_page_label(page_map: DocumentPageMap, pdf_page: int) -> str | None:
    """Compute one logical book label; a manual override always wins."""
    page = _strict_positive_int(pdf_page, "pdf_page")
    override = next(
        (item for item in page_map.manual_overrides if item.pdf_page == page),
        None,
    )
    if override is not None:
        return override.book_page_label
    rule = next(
        (
            item
            for item in page_map.rules
            if item.pdf_start_page <= page
            and (item.pdf_end_page is None or page <= item.pdf_end_page)
        ),
        None,
    )
    if rule is None:
        return None
    prefix = rule.label_prefix or ""
    if rule.label_style == PageLabelStyle.LITERAL:
        return prefix + str(rule.label_start)
    number = int(rule.label_start) + page - rule.pdf_start_page
    if rule.label_style == PageLabelStyle.ARABIC:
        label = str(number)
    else:
        label = _roman(number)
        if rule.label_style == PageLabelStyle.ROMAN_LOWER:
            label = label.lower()
    return prefix + label


__all__ = [
    "DOCUMENT_PAGE_MAP_SCHEMA_VERSION",
    "DocumentPageMap",
    "ManualPageOverride",
    "PageLabelRule",
    "PageLabelStyle",
    "PageMapStatus",
    "compute_book_page_label",
    "new_page_map_id",
    "new_rule_id",
    "utc_now",
    "validate_page_map_id",
    "validate_rule_id",
]

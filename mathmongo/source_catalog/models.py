"""Pydantic v2 contracts for Sources and bibliographic References."""

# ruff: noqa: D101,D102

from __future__ import annotations

import hashlib
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

from mathmongo.source_catalog.normalization import INVALID_ISBN_WARNING_PREFIX
from mathmongo.source_catalog.normalization import analyze_isbn
from mathmongo.source_catalog.normalization import author_title_year_fingerprint
from mathmongo.source_catalog.normalization import clean_text
from mathmongo.source_catalog.normalization import normalize_alias
from mathmongo.source_catalog.normalization import normalize_bibtex_key
from mathmongo.source_catalog.normalization import normalize_doi
from mathmongo.source_catalog.normalization import normalize_source_name

SCHEMA_VERSION = 1


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for BSON persistence."""
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _new_domain_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def new_source_id() -> str:
    """Generate a canonical Source domain identifier."""
    return _new_domain_id("src")


def new_reference_id() -> str:
    """Generate a canonical Reference domain identifier."""
    return _new_domain_id("ref")


def _validate_domain_id(value: Any, prefix: str) -> str:
    text = str(value or "")
    expected_prefix = f"{prefix}_"
    if not text.startswith(expected_prefix):
        raise ValueError(f"identifier must start with {expected_prefix!r}")
    suffix = text[len(expected_prefix) :]
    try:
        parsed = UUID(suffix)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"identifier must contain a UUID v4 after {expected_prefix!r}") from exc
    if parsed.version != 4 or str(parsed) != suffix:
        raise ValueError(
            f"identifier must contain a canonical lowercase UUID v4 after {expected_prefix!r}"
        )
    return text


def validate_source_id(value: Any) -> str:
    """Validate and return a canonical ``src_<uuid4>`` identifier."""
    return _validate_domain_id(value, "src")


def validate_reference_id(value: Any) -> str:
    """Validate and return a canonical ``ref_<uuid4>`` identifier."""
    return _validate_domain_id(value, "ref")


class SourceType(str, Enum):
    BOOK = "book"
    ARTICLE = "article"
    THESIS = "thesis"
    WEB = "web"
    DOCUMENTATION = "documentation"
    COURSE = "course"
    CORPUS = "corpus"
    REPORT = "report"
    PROJECT = "project"
    BIBLIOGRAPHIC_COLLECTION = "bibliographic_collection"
    OTHER = "other"


class SourceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ReferenceType(str, Enum):
    BOOK = "book"
    ARTICLE = "article"
    THESIS = "thesis"
    WEB = "web"
    REPORT = "report"
    PROCEEDINGS = "proceedings"
    CHAPTER = "chapter"
    COURSE = "course"
    MISC = "misc"
    OTHER = "other"


class ReferenceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    NEEDS_REVIEW = "needs_review"


class CopyrightStatus(str, Enum):
    UNKNOWN = "unknown"
    COPYRIGHTED = "copyrighted"
    PUBLIC_DOMAIN = "public_domain"
    LICENSED = "licensed"


class RedistributionPolicy(str, Enum):
    ASK = "ask"
    INCLUDE = "include"
    METADATA_ONLY = "metadata_only"
    EXCLUDE = "exclude"


class ImportMethod(str, Enum):
    MANUAL = "manual"
    BIBTEX_PASTE = "bibtex_paste"
    BIB_FILE = "bib_file"
    LEGACY = "legacy"


class CatalogModel(BaseModel):
    """Strict base configuration shared by Source catalog contracts."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SourceAlias(CatalogModel):
    value: str
    normalized: str = ""

    @model_validator(mode="after")
    def derive_normalized_value(self) -> SourceAlias:
        value = clean_text(self.value)
        if not value:
            raise ValueError("alias value cannot be empty")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "normalized", normalize_alias(value))
        return self


class SourceRights(CatalogModel):
    copyright_status: CopyrightStatus = CopyrightStatus.UNKNOWN
    redistribution: RedistributionPolicy = RedistributionPolicy.ASK
    license: str | None = None
    notes: str | None = None

    @field_validator("license", "notes", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str | None:
        text = clean_text(value)
        return text or None


class SourceLegacy(CatalogModel):
    source_strings: list[str] = Field(default_factory=list)
    migration_batch_id: str | None = None

    @field_validator("source_strings", mode="before")
    @classmethod
    def preserve_unique_exact_strings(cls, value: Any) -> list[str]:
        if value is None:
            return []
        values = [value] if isinstance(value, str) else list(value)
        result: list[str] = []
        seen: set[str] = set()
        for item in values:
            if not isinstance(item, str):
                raise ValueError("legacy source_strings must contain only strings")
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @field_validator("migration_batch_id", mode="before")
    @classmethod
    def clean_batch_id(cls, value: Any) -> str | None:
        text = clean_text(value)
        return text or None


def _dedupe_display_values(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        iterable = [values]
    else:
        iterable = list(values)
    result: list[str] = []
    seen: set[str] = set()
    for value in iterable:
        text = clean_text(value)
        normalized = normalize_source_name(text)
        if text and normalized not in seen:
            seen.add(normalized)
            result.append(text)
    return result


class Source(CatalogModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    source_id: str = Field(default_factory=new_source_id, frozen=True)
    name: str
    name_normalized: str = ""
    aliases: list[SourceAlias] = Field(default_factory=list)
    source_type: SourceType = SourceType.OTHER
    description: str = ""
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: SourceStatus = SourceStatus.ACTIVE
    rights_default: SourceRights = Field(default_factory=SourceRights)
    legacy: SourceLegacy = Field(default_factory=SourceLegacy)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @field_validator("source_id")
    @classmethod
    def source_id_is_stable_uuid(cls, value: Any) -> str:
        return validate_source_id(value)

    @field_validator("aliases", mode="before")
    @classmethod
    def coerce_aliases(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        values = [value] if isinstance(value, (str, dict, SourceAlias)) else list(value)
        return [{"value": item} if isinstance(item, str) else item for item in values]

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Any) -> list[str]:
        return _dedupe_display_values(value)

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: Any) -> str:
        return clean_text(value)

    @field_validator("language", mode="before")
    @classmethod
    def clean_language(cls, value: Any) -> str | None:
        text = clean_text(value)
        return text or None

    @field_validator("created_at", "updated_at", "archived_at")
    @classmethod
    def timestamps_are_aware_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def derive_and_validate_source(self) -> Source:
        validate_source_id(self.source_id)
        name = clean_text(self.name)
        if not name:
            raise ValueError("name cannot be empty")
        normalized_name = normalize_source_name(name)
        aliases: list[SourceAlias] = []
        seen = {normalized_name}
        for alias in self.aliases:
            if alias.normalized in seen:
                continue
            seen.add(alias.normalized)
            aliases.append(alias)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        archived_at = self.archived_at
        if self.status == SourceStatus.ARCHIVED and archived_at is None:
            archived_at = self.updated_at
        if self.status == SourceStatus.ACTIVE and archived_at is not None:
            raise ValueError("active Source cannot have archived_at")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "name_normalized", normalized_name)
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "archived_at", archived_at)
        return self

    def renamed(
        self,
        new_name: str,
        *,
        keep_previous_as_alias: bool = False,
        at: datetime | None = None,
    ) -> Source:
        """Return a renamed Source while preserving its stable domain ID."""
        aliases: list[Any] = [alias.model_dump(mode="python") for alias in self.aliases]
        if keep_previous_as_alias:
            aliases.append({"value": self.name})
        data = self.model_dump(mode="python")
        data.update({"name": new_name, "aliases": aliases, "updated_at": at or utc_now()})
        return Source.model_validate(data)

    def archived(self, *, at: datetime | None = None) -> Source:
        """Return an archived copy; archiving is idempotent."""
        if self.status == SourceStatus.ARCHIVED:
            return self
        timestamp = at or utc_now()
        data = self.model_dump(mode="python")
        data.update(
            {"status": SourceStatus.ARCHIVED, "updated_at": timestamp, "archived_at": timestamp}
        )
        return Source.model_validate(data)

    def reactivated(self, *, at: datetime | None = None) -> Source:
        """Return an active copy with the archive marker cleared."""
        if self.status == SourceStatus.ACTIVE and self.archived_at is None:
            return self
        data = self.model_dump(mode="python")
        data.update(
            {"status": SourceStatus.ACTIVE, "updated_at": at or utc_now(), "archived_at": None}
        )
        return Source.model_validate(data)


class ReferenceAuthor(CatalogModel):
    family: str | None = None
    given: str | None = None
    literal: str | None = None
    orcid: str | None = None

    @field_validator("family", "given", "literal", "orcid", mode="before")
    @classmethod
    def clean_author_text(cls, value: Any) -> str | None:
        text = clean_text(value)
        return text or None

    @model_validator(mode="after")
    def author_has_a_name(self) -> ReferenceAuthor:
        if not (self.literal or self.family or self.given):
            raise ValueError("author must have literal, family, or given text")
        return self


class BibTeXData(CatalogModel):
    key: str | None = None
    key_normalized: str | None = None
    entry_type: str | None = None
    raw: str | None = None
    raw_sha256: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)

    @field_validator("entry_type", mode="before")
    @classmethod
    def normalize_entry_type(cls, value: Any) -> str | None:
        text = clean_text(value)
        return text.casefold() or None

    @field_validator("extra", mode="before")
    @classmethod
    def limit_extra_fields(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("bibtex.extra must be a mapping")
        if len(value) > 64:
            raise ValueError("bibtex.extra cannot contain more than 64 fields")
        result: dict[str, str] = {}
        for key, item in value.items():
            key_text = clean_text(key)
            if not key_text or len(key_text) > 128:
                raise ValueError("bibtex.extra keys must contain 1 to 128 characters")
            item_text = str(item)
            if len(item_text) > 4096:
                raise ValueError("bibtex.extra values cannot exceed 4096 characters")
            result[key_text] = item_text
        return result

    @model_validator(mode="after")
    def derive_bibtex_fields(self) -> BibTeXData:
        key = self.key
        if key is not None and not str(key).strip():
            key = None
        raw = self.raw
        raw_sha256 = self.raw_sha256
        if raw is not None:
            calculated = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if raw_sha256 is not None and raw_sha256.casefold() != calculated:
                raise ValueError("bibtex.raw_sha256 does not match bibtex.raw")
            raw_sha256 = calculated
        elif raw_sha256 is not None:
            raise ValueError("bibtex.raw_sha256 requires bibtex.raw")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "key_normalized", normalize_bibtex_key(key))
        object.__setattr__(self, "raw_sha256", raw_sha256)
        return self


class ReferenceFingerprints(CatalogModel):
    author_title_year: str | None = None
    isbn_normalized: list[str] = Field(default_factory=list)


class ReferenceProvenance(CatalogModel):
    import_method: ImportMethod = ImportMethod.MANUAL
    imported_at: datetime = Field(default_factory=utc_now)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("imported_at")
    @classmethod
    def imported_at_is_aware_utc(cls, value: datetime) -> datetime:
        return _aware_utc(value, "imported_at")

    @field_validator("warnings", mode="before")
    @classmethod
    def clean_warnings(cls, value: Any) -> list[str]:
        return _dedupe_display_values(value)


_REFERENCE_TYPE_ALIASES = {
    "book": ReferenceType.BOOK,
    "booklet": ReferenceType.BOOK,
    "article": ReferenceType.ARTICLE,
    "phdthesis": ReferenceType.THESIS,
    "mastersthesis": ReferenceType.THESIS,
    "thesis": ReferenceType.THESIS,
    "online": ReferenceType.WEB,
    "website": ReferenceType.WEB,
    "web": ReferenceType.WEB,
    "techreport": ReferenceType.REPORT,
    "report": ReferenceType.REPORT,
    "proceedings": ReferenceType.PROCEEDINGS,
    "inproceedings": ReferenceType.PROCEEDINGS,
    "conference": ReferenceType.PROCEEDINGS,
    "inbook": ReferenceType.CHAPTER,
    "incollection": ReferenceType.CHAPTER,
    "chapter": ReferenceType.CHAPTER,
    "course": ReferenceType.COURSE,
    "misc": ReferenceType.MISC,
    "unpublished": ReferenceType.MISC,
    "other": ReferenceType.OTHER,
}


class Reference(CatalogModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    reference_id: str = Field(default_factory=new_reference_id, frozen=True)
    source_ids: list[str] = Field(default_factory=list)
    reference_type: ReferenceType = ReferenceType.MISC
    bibtex: BibTeXData = Field(default_factory=BibTeXData)
    authors: list[ReferenceAuthor] = Field(default_factory=list)
    title: str | None = None
    year: int | None = None
    year_raw: str | None = None
    journal: str | None = None
    publisher: str | None = None
    volume: str | None = None
    number: str | None = None
    edition: str | None = None
    isbn: list[str] = Field(default_factory=list)
    doi: str | None = None
    doi_normalized: str | None = None
    url: str | None = None
    accessed_at: datetime | None = None
    language: str | None = None
    notes: str | None = None
    fingerprints: ReferenceFingerprints = Field(default_factory=ReferenceFingerprints)
    provenance: ReferenceProvenance = Field(default_factory=ReferenceProvenance)
    status: ReferenceStatus = ReferenceStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None

    @field_validator("reference_id")
    @classmethod
    def reference_id_is_stable_uuid(cls, value: Any) -> str:
        return validate_reference_id(value)

    @field_validator("source_ids", mode="before")
    @classmethod
    def unique_source_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []
        values = [value] if isinstance(value, str) else list(value)
        result: list[str] = []
        seen: set[str] = set()
        for item in values:
            source_id = validate_source_id(item)
            if source_id not in seen:
                seen.add(source_id)
                result.append(source_id)
        return result

    @field_validator("reference_type", mode="before")
    @classmethod
    def map_reference_type(cls, value: Any) -> Any:
        if isinstance(value, ReferenceType):
            return value
        text = clean_text(value).casefold()
        return _REFERENCE_TYPE_ALIASES.get(text, value)

    @field_validator("authors", mode="before")
    @classmethod
    def coerce_authors(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        values = [value] if isinstance(value, (str, dict, ReferenceAuthor)) else list(value)
        return [{"literal": item} if isinstance(item, str) else item for item in values]

    @field_validator("isbn", mode="before")
    @classmethod
    def preserve_isbn_values(cls, value: Any) -> list[str]:
        if value is None:
            return []
        values = [value] if isinstance(value, str) else list(value)
        result: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = str(item)
            if text.strip() and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    @field_validator(
        "title",
        "year_raw",
        "journal",
        "publisher",
        "volume",
        "number",
        "edition",
        "url",
        "language",
        "notes",
        mode="before",
    )
    @classmethod
    def clean_reference_text(cls, value: Any) -> str | None:
        text = clean_text(value)
        return text or None

    @field_validator("doi", mode="before")
    @classmethod
    def preserve_nonempty_doi(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.strip() else None

    @field_validator("accessed_at", "created_at", "updated_at", "archived_at")
    @classmethod
    def reference_timestamps_are_aware_utc(
        cls, value: datetime | None, info: Any
    ) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, info.field_name)

    @model_validator(mode="after")
    def derive_and_validate_reference(self) -> Reference:
        validate_reference_id(self.reference_id)
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")

        doi_normalized = normalize_doi(self.doi)
        valid_isbns: list[str] = []
        previous_warnings = list(self.provenance.warnings)
        had_generated_isbn_warning = any(
            warning.startswith(INVALID_ISBN_WARNING_PREFIX) for warning in previous_warnings
        )
        warnings = [
            warning
            for warning in previous_warnings
            if not warning.startswith(INVALID_ISBN_WARNING_PREFIX)
        ]
        for value in self.isbn:
            analysis = analyze_isbn(value)
            if analysis.valid and analysis.normalized and analysis.normalized not in valid_isbns:
                valid_isbns.append(analysis.normalized)
            elif analysis.warning and analysis.warning not in warnings:
                warnings.append(analysis.warning)

        author_fingerprint = author_title_year_fingerprint(
            [author.model_dump(mode="python") for author in self.authors],
            self.title,
            self.year if self.year is not None else self.year_raw,
        )
        fingerprints = ReferenceFingerprints(
            author_title_year=author_fingerprint,
            isbn_normalized=valid_isbns,
        )
        provenance_data = self.provenance.model_dump(mode="python")
        provenance_data["warnings"] = warnings
        provenance = ReferenceProvenance.model_validate(provenance_data)

        has_identity = any(
            (
                bool(clean_text(self.title)),
                bool(self.authors),
                bool(doi_normalized),
                bool(self.isbn),
                bool(clean_text(self.url)),
                bool(self.bibtex.key and self.bibtex.key.strip()),
            )
        )
        if not has_identity:
            raise ValueError("Reference requires title, authors, DOI, ISBN, URL, or a BibTeX key")

        status = self.status
        archived_at = self.archived_at
        if warnings and status == ReferenceStatus.ACTIVE:
            status = ReferenceStatus.NEEDS_REVIEW
        elif had_generated_isbn_warning and not warnings and status == ReferenceStatus.NEEDS_REVIEW:
            status = ReferenceStatus.ACTIVE
        if status == ReferenceStatus.ARCHIVED and archived_at is None:
            archived_at = self.updated_at
        if status != ReferenceStatus.ARCHIVED and archived_at is not None:
            raise ValueError("non-archived Reference cannot have archived_at")

        object.__setattr__(self, "doi_normalized", doi_normalized)
        object.__setattr__(self, "fingerprints", fingerprints)
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "archived_at", archived_at)
        return self

    def associated_with(self, source_id: str, *, at: datetime | None = None) -> Reference:
        """Return a copy associated with a Source; duplicate association is a no-op."""
        source_id = validate_source_id(source_id)
        if source_id in self.source_ids:
            return self
        data = self.model_dump(mode="python")
        data.update({"source_ids": [*self.source_ids, source_id], "updated_at": at or utc_now()})
        return Reference.model_validate(data)

    def disassociated_from(self, source_id: str, *, at: datetime | None = None) -> Reference:
        """Return a copy without one Source association."""
        source_id = validate_source_id(source_id)
        if source_id not in self.source_ids:
            return self
        data = self.model_dump(mode="python")
        data.update(
            {
                "source_ids": [item for item in self.source_ids if item != source_id],
                "updated_at": at or utc_now(),
            }
        )
        return Reference.model_validate(data)

    def archived(self, *, at: datetime | None = None) -> Reference:
        """Return an archived copy; archiving is idempotent."""
        if self.status == ReferenceStatus.ARCHIVED:
            return self
        timestamp = at or utc_now()
        data = self.model_dump(mode="python")
        data.update(
            {"status": ReferenceStatus.ARCHIVED, "updated_at": timestamp, "archived_at": timestamp}
        )
        return Reference.model_validate(data)

    def reactivated(self, *, at: datetime | None = None) -> Reference:
        """Reactivate, retaining ``needs_review`` when diagnostics still exist."""
        if self.status != ReferenceStatus.ARCHIVED and self.archived_at is None:
            return self
        target_status = (
            ReferenceStatus.NEEDS_REVIEW if self.provenance.warnings else ReferenceStatus.ACTIVE
        )
        data = self.model_dump(mode="python")
        data.update({"status": target_status, "updated_at": at or utc_now(), "archived_at": None})
        return Reference.model_validate(data)


# Compatibility spellings for callers that prefer conventional casing.
Author = ReferenceAuthor
BibtexData = BibTeXData
CatalogStatus = SourceStatus


__all__ = [
    "Author",
    "BibTeXData",
    "BibtexData",
    "CatalogStatus",
    "CopyrightStatus",
    "ImportMethod",
    "RedistributionPolicy",
    "Reference",
    "ReferenceAuthor",
    "ReferenceFingerprints",
    "ReferenceProvenance",
    "ReferenceStatus",
    "ReferenceType",
    "SCHEMA_VERSION",
    "Source",
    "SourceAlias",
    "SourceLegacy",
    "SourceRights",
    "SourceStatus",
    "SourceType",
    "new_reference_id",
    "new_source_id",
    "utc_now",
    "validate_reference_id",
    "validate_source_id",
]

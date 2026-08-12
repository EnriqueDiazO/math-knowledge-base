"""Typed, backward-compatible settings for free-form Diario notes."""

# ruff: noqa: D102

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import Enum
from typing import Any
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from mathmongo.source_catalog.models import Reference

DIARY_NOTE_SCHEMA_VERSION = 1
DEFAULT_TOC_TITLE = "Contenido"
KNOWN_HEADER_FOOTER_TOKENS = (
    "institution",
    "program",
    "course_code",
    "course_name",
    "week",
    "session",
    "short_title",
    "title",
    "author",
    "date",
    "page",
)
_TOKEN_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def new_note_reference_id() -> str:
    """Return a stable note-local reference identifier."""
    return f"note_ref_{uuid4()}"


class NoteReferenceKind(str, Enum):
    """Bibliographic kinds supported by the Diario editor and renderer."""

    BOOK = "book"
    CHAPTER = "chapter"
    ARTICLE = "article"
    WEBSITE = "website"
    DOCUMENTATION = "documentation"
    THESIS = "thesis"
    DATASET = "dataset"
    SOFTWARE = "software"
    INSTITUTIONAL = "institutional"
    OTHER = "other"


class ReferenceOrigin(str, Enum):
    """Whether a note reference was entered manually or snapshotted from the catalog."""

    MANUAL = "manual"
    CATALOG = "catalog"


class FirstPageStyle(str, Enum):
    """Header/footer behavior for the title page produced by ``report``."""

    SAME = "same"
    PLAIN = "plain"
    EMPTY = "empty"


class PageNumberPosition(str, Enum):
    """Supported controlled locations for one page number."""

    FOOTER_LEFT = "footer_left"
    FOOTER_CENTER = "footer_center"
    FOOTER_RIGHT = "footer_right"


class TocPosition(str, Enum):
    """Supported insertion points in the current free-form note structure."""

    AFTER_TITLE = "after_title"
    AFTER_METADATA = "after_metadata"


class DiarySettingsModel(BaseModel):
    """Base configuration that tolerates future fields during lazy migrations."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)


class AcademicMetadata(DiarySettingsModel):
    """Academic data not already represented by top-level note fields."""

    institution: str = ""
    program: str = ""
    course_code: str = ""
    course_name: str = ""
    week: str = ""
    session: str = ""
    short_title: str = ""
    topic: str = ""
    objective: str = ""
    linked_activity: str = ""
    author: str = ""
    version: str = ""
    language: str = ""
    pdf_subject: str = ""
    pdf_keywords: list[str] = Field(default_factory=list)

    @field_validator(
        "institution",
        "program",
        "course_code",
        "course_name",
        "week",
        "session",
        "short_title",
        "topic",
        "objective",
        "linked_activity",
        "author",
        "version",
        "language",
        "pdf_subject",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return _clean_text(value)

    @field_validator("pdf_keywords", mode="before")
    @classmethod
    def normalize_keywords(cls, value: Any) -> list[str]:
        if value is None:
            return []
        values = value.split(",") if isinstance(value, str) else list(value)
        result: list[str] = []
        seen: set[str] = set()
        for item in values:
            text = _clean_text(item)
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                result.append(text)
        return result


class NoteReference(DiarySettingsModel):
    """Ordered note-local snapshot that may remain incomplete as a draft."""

    reference_id: str = Field(default_factory=new_note_reference_id)
    origin: ReferenceOrigin = ReferenceOrigin.MANUAL
    catalog_reference_id: str | None = None
    kind: NoteReferenceKind = NoteReferenceKind.OTHER
    citation_key: str = ""
    authors: str = ""
    title: str = ""
    year_or_date: str = ""
    container_title: str = ""
    publisher: str = ""
    volume: str = ""
    number: str = ""
    pages: str = ""
    edition: str = ""
    doi: str = ""
    url: str = ""
    accessed_date: str = ""
    language: str = ""
    note: str = ""
    position: int = Field(default=0, ge=0)

    @field_validator("reference_id")
    @classmethod
    def stable_reference_id(cls, value: Any) -> str:
        text = str(value or "")
        if not re.fullmatch(r"note_ref_[0-9a-f-]{36}", text):
            raise ValueError("note reference_id must be a stable note_ref UUID")
        return text

    @field_validator("catalog_reference_id", mode="before")
    @classmethod
    def normalize_catalog_reference_id(cls, value: Any) -> str | None:
        text = _clean_text(value)
        return text or None

    @field_validator(
        "citation_key",
        "authors",
        "title",
        "year_or_date",
        "container_title",
        "publisher",
        "volume",
        "number",
        "pages",
        "edition",
        "doi",
        "url",
        "accessed_date",
        "language",
        "note",
        mode="before",
    )
    @classmethod
    def normalize_reference_text(cls, value: Any) -> str:
        return _clean_text(value)

    @model_validator(mode="after")
    def catalog_origin_has_link(self) -> NoteReference:
        if self.origin == ReferenceOrigin.CATALOG and not self.catalog_reference_id:
            raise ValueError("catalog references require catalog_reference_id")
        return self

    @property
    def exportable(self) -> bool:
        """A title is the minimum required for a coherent bibliography item."""
        return bool(self.title)


class HeaderFooterSettings(DiarySettingsModel):
    """Per-note page furniture with metadata tokens and one controlled page number."""

    enabled: bool = False
    header_left: str = "{institution} · {course_code}"
    header_center: str = ""
    header_right: str = "{week} · {short_title}"
    footer_left: str = "{course_name}"
    footer_center: str = ""
    footer_right: str = "{author}"
    first_page_style: FirstPageStyle = FirstPageStyle.SAME
    show_page_number: bool = True
    page_number_position: PageNumberPosition = PageNumberPosition.FOOTER_CENTER

    @field_validator(
        "header_left",
        "header_center",
        "header_right",
        "footer_left",
        "footer_center",
        "footer_right",
        mode="before",
    )
    @classmethod
    def normalize_slot_text(cls, value: Any) -> str:
        return _clean_text(value)


class TableOfContentsSettings(DiarySettingsModel):
    """Native LaTeX table-of-contents configuration for free-form notes."""

    show_table_of_contents: bool = False
    toc_title: str = DEFAULT_TOC_TITLE
    toc_depth: int = Field(default=2, ge=0, le=2)
    position: TocPosition = TocPosition.AFTER_METADATA

    @field_validator("toc_title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> str:
        return _clean_text(value) or DEFAULT_TOC_TITLE


class DiaryNoteSettings(DiarySettingsModel):
    """All structured additions persisted inside one ``latex_notes`` document."""

    schema_version: Literal[1] = DIARY_NOTE_SCHEMA_VERSION
    academic_metadata: AcademicMetadata = Field(default_factory=AcademicMetadata)
    references: list[NoteReference] = Field(default_factory=list)
    page_layout: HeaderFooterSettings = Field(default_factory=HeaderFooterSettings)
    table_of_contents: TableOfContentsSettings = Field(default_factory=TableOfContentsSettings)

    @model_validator(mode="after")
    def references_have_stable_order_and_identity(self) -> DiaryNoteSettings:
        seen: set[str] = set()
        ordered: list[NoteReference] = []
        for position, reference in enumerate(self.references):
            if reference.reference_id in seen:
                raise ValueError("note reference identifiers must be unique")
            seen.add(reference.reference_id)
            if reference.position != position:
                reference = reference.model_copy(update={"position": position})
            ordered.append(reference)
        object.__setattr__(self, "references", ordered)
        return self


def default_diary_note_settings(*, new_note: bool = False) -> DiaryNoteSettings:
    """Return conservative legacy defaults or metadata-driven defaults for a new note."""
    layout = HeaderFooterSettings(enabled=new_note)
    return DiaryNoteSettings(page_layout=layout)


def settings_from_note(note: Mapping[str, Any], *, new_note: bool = False) -> DiaryNoteSettings:
    """Read structured settings lazily from old or current Mongo note documents."""
    if not isinstance(note, Mapping):
        raise TypeError("note must be a mapping")
    defaults = default_diary_note_settings(new_note=new_note)
    return DiaryNoteSettings.model_validate(
        {
            "schema_version": note.get("note_schema_version", DIARY_NOTE_SCHEMA_VERSION),
            "academic_metadata": note.get("academic_metadata")
            or defaults.academic_metadata.model_dump(mode="json"),
            "references": note.get("references") or [],
            "page_layout": note.get("page_layout") or defaults.page_layout.model_dump(mode="json"),
            "table_of_contents": note.get("table_of_contents")
            or defaults.table_of_contents.model_dump(mode="json"),
        }
    )


def settings_document_fields(settings: DiaryNoteSettings) -> dict[str, Any]:
    """Return the complete structured fields for a new note or an export copy.

    This function is deliberately not used to update an existing Mongo document.
    Existing notes must use :func:`settings_persistence_set`, which emits only the
    changed dotted paths and therefore never writes lazy defaults back to a legacy
    note merely because it was opened.
    """
    data = settings.model_dump(mode="json")
    return {
        "note_schema_version": data["schema_version"],
        "academic_metadata": data["academic_metadata"],
        "references": data["references"],
        "page_layout": data["page_layout"],
        "table_of_contents": data["table_of_contents"],
    }


def settings_persistence_set(
    original_note: Mapping[str, Any],
    settings: DiaryNoteSettings,
) -> dict[str, Any]:
    """Build a minimal ``$set`` payload for one existing Diario note.

    Defaults materialized while reading a legacy note remain memory-only.  Known
    scalar settings are compared field by field and emitted as dotted Mongo paths;
    references are emitted as one ordered array only when that array changed.
    Unknown document and nested configuration fields are never rewritten.
    """
    original = settings_from_note(original_note)
    current_data = settings.model_dump(mode="json")
    original_data = original.model_dump(mode="json")
    updates: dict[str, Any] = {}

    for root, model_type in (
        ("academic_metadata", AcademicMetadata),
        ("page_layout", HeaderFooterSettings),
        ("table_of_contents", TableOfContentsSettings),
    ):
        for field in model_type.model_fields:
            if current_data[root][field] != original_data[root][field]:
                updates[f"{root}.{field}"] = current_data[root][field]

    if current_data["references"] != original_data["references"]:
        updates["references"] = current_data["references"]

    # Never introduce a schema marker solely because a legacy note was loaded.
    # If a future stored marker is explicitly upgraded, keep that change narrow.
    if "note_schema_version" in original_note:
        stored_version = original_note.get("note_schema_version")
        if stored_version != current_data["schema_version"]:
            updates["note_schema_version"] = current_data["schema_version"]
    return updates


def note_with_settings(
    note: Mapping[str, Any],
    settings: DiaryNoteSettings,
) -> dict[str, Any]:
    """Overlay structured fields while preserving every unknown top-level field."""
    result = dict(note)
    result.update(settings_document_fields(settings))
    return result


def token_values(note: Mapping[str, Any], settings: DiaryNoteSettings) -> dict[str, str]:
    """Build the single metadata token context used by previews and LaTeX."""
    metadata = settings.academic_metadata
    title = _clean_text(note.get("title"))
    return {
        "institution": metadata.institution,
        "program": metadata.program,
        "course_code": metadata.course_code,
        "course_name": metadata.course_name,
        "week": metadata.week,
        "session": metadata.session,
        "short_title": metadata.short_title or title,
        "title": title,
        "author": metadata.author,
        "date": _clean_text(note.get("date")),
    }


def resolve_tokens(
    template: str,
    values: Mapping[str, str],
    *,
    page_value: str = "1",
) -> tuple[str, tuple[str, ...]]:
    """Resolve allowed tokens, dropping unknown tokens with explicit warnings."""
    warnings: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "page":
            return page_value
        if token not in KNOWN_HEADER_FOOTER_TOKENS:
            warnings.append(f"Token desconocido omitido: {{{token}}}")
            return ""
        return str(values.get(token) or "")

    return _clean_text(_TOKEN_RE.sub(replace, str(template or ""))), tuple(dict.fromkeys(warnings))


def reference_warnings(reference: NoteReference) -> tuple[str, ...]:
    """Return tolerant draft diagnostics without preventing persistence."""
    warnings: list[str] = []
    if not reference.title:
        warnings.append("Borrador sin título: se conservará, pero no se exportará.")
    if reference.doi:
        normalized = re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
            "",
            reference.doi,
            flags=re.IGNORECASE,
        )
        if not _DOI_RE.fullmatch(normalized):
            warnings.append("El DOI no tiene un formato reconocible; se conservará para revisión.")
    if reference.url:
        try:
            parsed = urlsplit(reference.url)
            valid_url = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except ValueError:
            valid_url = False
        if not valid_url:
            warnings.append("La URL no es HTTP(S) completa; se conservará para revisión.")
    return tuple(warnings)


def settings_warnings(settings: DiaryNoteSettings) -> tuple[str, ...]:
    """Aggregate reference, citation-key, token, and length diagnostics."""
    warnings: list[str] = []
    citation_keys: dict[str, int] = {}
    for reference in settings.references:
        warnings.extend(
            f"Referencia {reference.position + 1}: {warning}"
            for warning in reference_warnings(reference)
        )
        key = reference.citation_key.casefold()
        if key:
            citation_keys[key] = citation_keys.get(key, 0) + 1
    for key, count in citation_keys.items():
        if count > 1:
            warnings.append(
                f"La clave de cita {key!r} está repetida; la exportación la hará única."
            )
    layout = settings.page_layout
    for slot_name in (
        "header_left",
        "header_center",
        "header_right",
        "footer_left",
        "footer_center",
        "footer_right",
    ):
        value = getattr(layout, slot_name)
        unknown = [
            token for token in _TOKEN_RE.findall(value) if token not in KNOWN_HEADER_FOOTER_TOKENS
        ]
        warnings.extend(f"{slot_name}: token desconocido {{{token}}}." for token in unknown)
        if len(value) > 100:
            warnings.append(f"{slot_name}: el texto puede ser demasiado largo para la página.")
    return tuple(dict.fromkeys(warnings))


_CATALOG_KIND_MAP = {
    "book": NoteReferenceKind.BOOK,
    "article": NoteReferenceKind.ARTICLE,
    "thesis": NoteReferenceKind.THESIS,
    "web": NoteReferenceKind.WEBSITE,
    "report": NoteReferenceKind.INSTITUTIONAL,
    "proceedings": NoteReferenceKind.ARTICLE,
    "chapter": NoteReferenceKind.CHAPTER,
    "course": NoteReferenceKind.INSTITUTIONAL,
    "misc": NoteReferenceKind.OTHER,
    "other": NoteReferenceKind.OTHER,
}


def note_reference_from_catalog(reference: Reference, *, position: int = 0) -> NoteReference:
    """Create a reproducible note-local snapshot linked to one catalog Reference."""
    authors = "; ".join(
        author.literal or " ".join(part for part in (author.given, author.family) if part)
        for author in reference.authors
    )
    accessed = reference.accessed_at.date().isoformat() if reference.accessed_at else ""
    extra = reference.bibtex.extra
    return NoteReference(
        origin=ReferenceOrigin.CATALOG,
        catalog_reference_id=reference.reference_id,
        kind=_CATALOG_KIND_MAP.get(reference.reference_type.value, NoteReferenceKind.OTHER),
        citation_key=reference.bibtex.key or "",
        authors=authors,
        title=reference.title or "",
        year_or_date=str(reference.year or reference.year_raw or ""),
        container_title=reference.journal or extra.get("booktitle", ""),
        publisher=reference.publisher or "",
        volume=reference.volume or "",
        number=reference.number or "",
        pages=extra.get("pages", ""),
        edition=reference.edition or "",
        doi=reference.doi or "",
        url=reference.url or "",
        accessed_date=accessed,
        language=reference.language or "",
        note=reference.notes or "",
        position=position,
    )


def move_reference(
    references: list[NoteReference],
    reference_id: str,
    offset: int,
) -> list[NoteReference]:
    """Move one stable reference by one relative offset without changing its ID."""
    items = list(references)
    current = next(
        (index for index, item in enumerate(items) if item.reference_id == reference_id),
        None,
    )
    if current is None:
        return [item.model_copy(update={"position": index}) for index, item in enumerate(items)]
    target = max(0, min(len(items) - 1, current + offset))
    if target != current:
        items[current], items[target] = items[target], items[current]
    return [item.model_copy(update={"position": index}) for index, item in enumerate(items)]


__all__ = [
    "AcademicMetadata",
    "DEFAULT_TOC_TITLE",
    "DIARY_NOTE_SCHEMA_VERSION",
    "DiaryNoteSettings",
    "FirstPageStyle",
    "HeaderFooterSettings",
    "KNOWN_HEADER_FOOTER_TOKENS",
    "NoteReference",
    "NoteReferenceKind",
    "PageNumberPosition",
    "ReferenceOrigin",
    "TableOfContentsSettings",
    "TocPosition",
    "default_diary_note_settings",
    "move_reference",
    "new_note_reference_id",
    "note_reference_from_catalog",
    "note_with_settings",
    "reference_warnings",
    "resolve_tokens",
    "settings_from_note",
    "settings_document_fields",
    "settings_persistence_set",
    "settings_warnings",
    "token_values",
]

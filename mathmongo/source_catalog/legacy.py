"""Read-only previews for legacy concept Source and reference metadata."""

# ruff: noqa: D101,D102

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator

from mathmongo.source_catalog.models import ImportMethod
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import ReferenceType
from mathmongo.source_catalog.normalization import clean_text
from mathmongo.source_catalog.normalization import normalize_source_name
from mathmongo.source_catalog.normalization import suggestion_key


class LegacyPreviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class LegacySourcePreview(LegacyPreviewModel):
    exact_value: str | None = None
    normalized: str | None = None
    suggestion: str | None = None
    usable: bool = False
    warnings: list[str] = Field(default_factory=list)


class LegacyLocatorPreview(LegacyPreviewModel):
    pages: str | None = None
    chapter: str | None = None
    section: str | None = None
    equation: str | None = None
    theorem: str | None = None

    @field_validator("pages", "chapter", "section", "equation", "theorem", mode="before")
    @classmethod
    def preserve_locator_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.strip() else None

    @property
    def has_locator(self) -> bool:
        return any((self.pages, self.chapter, self.section, self.equation, self.theorem))


class LegacyReferencePreview(LegacyPreviewModel):
    candidate: Reference | None = None
    locator: LegacyLocatorPreview = Field(default_factory=LegacyLocatorPreview)
    original_reference: Any = None
    unmapped_fields: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.candidate is not None and not self.errors


class LegacyConceptPreview(LegacyPreviewModel):
    concept_id: str | None = None
    source: LegacySourcePreview
    reference: LegacyReferencePreview


_REFERENCE_TYPE_MAP = {
    "libro": ReferenceType.BOOK,
    "book": ReferenceType.BOOK,
    "articulo": ReferenceType.ARTICLE,
    "artículo": ReferenceType.ARTICLE,
    "article": ReferenceType.ARTICLE,
    "tesis": ReferenceType.THESIS,
    "tesina": ReferenceType.THESIS,
    "thesis": ReferenceType.THESIS,
    "pagina_web": ReferenceType.WEB,
    "página_web": ReferenceType.WEB,
    "web": ReferenceType.WEB,
    "informe": ReferenceType.REPORT,
    "report": ReferenceType.REPORT,
    "proceedings": ReferenceType.PROCEEDINGS,
    "capitulo": ReferenceType.CHAPTER,
    "capítulo": ReferenceType.CHAPTER,
    "chapter": ReferenceType.CHAPTER,
    "curso": ReferenceType.COURSE,
    "course": ReferenceType.COURSE,
    "miscelanea": ReferenceType.MISC,
    "miscelánea": ReferenceType.MISC,
    "misc": ReferenceType.MISC,
}

_MAPPED_REFERENCE_FIELDS = {
    "tipo",
    "tipo_referencia",
    "autor",
    "autores",
    "authors",
    "titulo",
    "title",
    "fuente",
    "anio",
    "year",
    "year_raw",
    "journal",
    "revista",
    "editorial",
    "publisher",
    "tomo",
    "volume",
    "numero",
    "number",
    "edicion",
    "edition",
    "isbn",
    "issbn",
    "doi",
    "url",
    "idioma",
    "language",
    "notas",
    "notes",
    "citekey",
    "bibtex_key",
    "bibtex",
    "bibtex_entry",
    "paginas",
    "pages",
    "pagina",
    "capitulo",
    "chapter",
    "seccion",
    "section",
    "ecuacion",
    "equation",
    "teorema",
    "theorem",
}


def extract_legacy_source_string(concept: Mapping[str, Any] | None) -> str | None:
    """Return the exact legacy ``concept.source`` string without normalization."""
    if not isinstance(concept, Mapping):
        return None
    value = concept.get("source")
    return value if isinstance(value, str) else None


def preview_legacy_source(concept_or_value: Mapping[str, Any] | Any) -> LegacySourcePreview:
    """Build a diagnostic Source preview without creating a Source model."""
    if isinstance(concept_or_value, Mapping):
        value = concept_or_value.get("source")
    else:
        value = concept_or_value
    warnings: list[str] = []
    if value is None:
        warnings.append("Legacy concept has no source field.")
        return LegacySourcePreview(warnings=warnings)
    if not isinstance(value, str):
        warnings.append(f"Legacy source is not a string: {type(value).__name__}.")
        return LegacySourcePreview(warnings=warnings)
    normalized = normalize_source_name(value)
    if not normalized:
        warnings.append("Legacy source is blank after normalization.")
    if value != clean_text(value):
        warnings.append(
            "Legacy source contains outer or repeated whitespace; exact value was preserved."
        )
    return LegacySourcePreview(
        exact_value=value,
        normalized=normalized or None,
        suggestion=suggestion_key(value) or None,
        usable=bool(normalized),
        warnings=warnings,
    )


def _first(reference: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = reference.get(key)
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return None


def _legacy_reference_type(value: Any) -> ReferenceType:
    key = clean_text(value).casefold()
    return _REFERENCE_TYPE_MAP.get(key, ReferenceType.OTHER if key else ReferenceType.MISC)


def _legacy_authors(reference: Mapping[str, Any]) -> list[Any]:
    authors = _first(reference, "authors", "autores")
    if authors is not None:
        if isinstance(authors, (str, Mapping)):
            return [authors]
        try:
            return list(authors)
        except TypeError:
            return [str(authors)]
    author = reference.get("autor")
    return [str(author)] if author is not None and str(author).strip() else []


def _legacy_isbns(reference: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for key in ("isbn", "issbn"):
        value = reference.get(key)
        if value is None:
            continue
        values = (
            [value]
            if isinstance(value, str)
            else list(value)
            if isinstance(value, (list, tuple, set))
            else [value]
        )
        for item in values:
            text = str(item)
            if text.strip() and text not in result:
                result.append(text)
    return result


def extract_legacy_locator(reference: Mapping[str, Any] | None) -> LegacyLocatorPreview:
    """Separate concept-specific locator data from bibliography metadata."""
    if not isinstance(reference, Mapping):
        return LegacyLocatorPreview()
    return LegacyLocatorPreview(
        pages=_first(reference, "paginas", "pages", "pagina"),
        chapter=_first(reference, "capitulo", "chapter"),
        section=_first(reference, "seccion", "section"),
        equation=_first(reference, "ecuacion", "equation"),
        theorem=_first(reference, "teorema", "theorem"),
    )


def preview_legacy_reference(
    reference_or_concept: Mapping[str, Any] | Any,
    *,
    source_id: str | None = None,
    concept_citekey: str | None = None,
) -> LegacyReferencePreview:
    """Convert embedded legacy metadata into a validated, unsaved candidate."""
    concept: Mapping[str, Any] | None = None
    if isinstance(reference_or_concept, Mapping) and "referencia" in reference_or_concept:
        concept = reference_or_concept
        raw_reference = concept.get("referencia")
        if concept_citekey is None and isinstance(concept.get("citekey"), str):
            concept_citekey = concept.get("citekey")
    else:
        raw_reference = reference_or_concept

    warnings: list[str] = []
    errors: list[str] = []
    if raw_reference is None:
        return LegacyReferencePreview(
            original_reference=None,
            warnings=["Legacy concept has no embedded reference."],
        )
    if isinstance(raw_reference, str):
        reference: dict[str, Any] = {"titulo": raw_reference}
        warnings.append("Free-text legacy reference was preserved as a title candidate for review.")
    elif isinstance(raw_reference, Mapping):
        reference = deepcopy(dict(raw_reference))
    else:
        return LegacyReferencePreview(
            original_reference=deepcopy(raw_reference),
            errors=[f"Unsupported legacy reference type: {type(raw_reference).__name__}."],
        )

    locator = extract_legacy_locator(reference)
    type_value = _first(reference, "tipo_referencia", "tipo")
    citekey = _first(reference, "citekey", "bibtex_key") or concept_citekey
    bibtex_value = reference.get("bibtex")
    if isinstance(bibtex_value, Mapping):
        bibtex_data = deepcopy(dict(bibtex_value))
        if citekey and not bibtex_data.get("key"):
            bibtex_data["key"] = citekey
    else:
        raw_bibtex = _first(reference, "bibtex_entry")
        bibtex_data = {"key": citekey, "raw": raw_bibtex}

    year_value = _first(reference, "anio", "year")
    year: int | None = None
    year_raw = _first(reference, "year_raw")
    if isinstance(year_value, int) and not isinstance(year_value, bool):
        year = year_value
        year_raw = str(year_value) if year_raw is None else year_raw
    elif year_value is not None:
        raw_text = str(year_value)
        year_raw = raw_text if year_raw is None else year_raw
        if raw_text.strip().isdigit():
            year = int(raw_text.strip())

    title = _first(reference, "titulo", "title", "fuente")
    candidate_data: dict[str, Any] = {
        "source_ids": [source_id] if source_id else [],
        "reference_type": _legacy_reference_type(type_value),
        "bibtex": bibtex_data,
        "authors": _legacy_authors(reference),
        "title": title,
        "year": year,
        "year_raw": year_raw,
        "journal": _first(reference, "journal", "revista"),
        "publisher": _first(reference, "publisher", "editorial"),
        "volume": _first(reference, "volume", "tomo"),
        "number": _first(reference, "number", "numero"),
        "edition": _first(reference, "edition", "edicion"),
        "isbn": _legacy_isbns(reference),
        "doi": reference.get("doi"),
        "url": reference.get("url"),
        "language": _first(reference, "language", "idioma"),
        "notes": _first(reference, "notes", "notas"),
        "provenance": {
            "import_method": ImportMethod.LEGACY,
            "warnings": warnings,
        },
    }

    if "issbn" in reference:
        warnings.append(
            "Legacy field 'issbn' was preserved as ISBN input and requires normalization review."
        )
        candidate_data["provenance"]["warnings"] = warnings
    if type_value and _legacy_reference_type(type_value) == ReferenceType.OTHER:
        warnings.append(f"Unknown legacy reference type retained for review: {type_value!r}.")
        candidate_data["provenance"]["warnings"] = warnings

    unmapped = {
        str(key): deepcopy(value)
        for key, value in reference.items()
        if str(key) not in _MAPPED_REFERENCE_FIELDS
    }
    try:
        candidate = Reference.model_validate(candidate_data)
    except Exception as exc:
        candidate = None
        errors.append(str(exc))

    return LegacyReferencePreview(
        candidate=candidate,
        locator=locator,
        original_reference=deepcopy(raw_reference),
        unmapped_fields=unmapped,
        warnings=warnings,
        errors=errors,
    )


def preview_legacy_concept(
    concept: Mapping[str, Any],
    *,
    source_id: str | None = None,
) -> LegacyConceptPreview:
    """Preview one legacy concept without changing it or connecting to MongoDB."""
    if not isinstance(concept, Mapping):
        raise TypeError("concept must be a mapping")
    concept_id = concept.get("id")
    return LegacyConceptPreview(
        concept_id=str(concept_id) if concept_id is not None else None,
        source=preview_legacy_source(concept),
        reference=preview_legacy_reference(concept, source_id=source_id),
    )


# Descriptive aliases used by migration/preview callers.
convert_legacy_reference_to_candidate = preview_legacy_reference
legacy_reference_to_candidate = preview_legacy_reference


__all__ = [
    "LegacyConceptPreview",
    "LegacyLocatorPreview",
    "LegacyReferencePreview",
    "LegacySourcePreview",
    "convert_legacy_reference_to_candidate",
    "extract_legacy_locator",
    "extract_legacy_source_string",
    "legacy_reference_to_candidate",
    "preview_legacy_concept",
    "preview_legacy_reference",
    "preview_legacy_source",
]

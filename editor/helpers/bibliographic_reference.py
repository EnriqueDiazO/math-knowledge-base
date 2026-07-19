"""Pure adaptation from Source Catalog BibTeX candidates to concept references."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mathmongo.source_catalog.bibtex import parse_bibtex_authors
from mathmongo.source_catalog.normalization import normalize_doi

_BIBTEX_TYPE_TO_CONCEPT_TYPE = {
    "article": "articulo",
    "book": "libro",
    "booklet": "libro",
    "electronic": "pagina_web",
    "manual": "libro",
    "mastersthesis": "tesina",
    "misc": "miscelanea",
    "online": "pagina_web",
    "phdthesis": "tesis",
    "thesis": "tesis",
    "web": "pagina_web",
    "www": "pagina_web",
}
_CONCEPT_REFERENCE_FIELDS = (
    "tipo_referencia",
    "autor",
    "fuente",
    "anio",
    "tomo",
    "edicion",
    "paginas",
    "capitulo",
    "seccion",
    "editorial",
    "doi",
    "url",
    "issbn",
    "citekey",
)
_YEAR_FROM_DATE_RE = re.compile(r"^\s*([+-]?\d{1,4})(?:\D|$)")


@dataclass(frozen=True, slots=True)
class NormalizedBibliographicEntry:
    """One non-persisted BibTeX candidate adapted to the legacy concept form."""

    reference: dict[str, Any]
    warnings: tuple[str, ...] = ()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _display_text(value: Any) -> str | None:
    """Remove one complete BibTeX protection group from a display value."""
    text = _optional_text(value)
    if not text or len(text) < 2 or text[0] != "{" or text[-1] != "}":
        return text
    depth = 0
    escaped = False
    for index, character in enumerate(text):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return text
            if depth < 0:
                return text
    return text[1:-1].strip() if depth == 0 else text


def _casefolded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key).casefold(): item for key, item in value.items()}


def _author_text(authors: Any) -> str | None:
    if not isinstance(authors, list | tuple):
        return None
    names: list[str] = []
    for author in authors:
        if not isinstance(author, Mapping):
            text = _optional_text(author)
        else:
            literal = _optional_text(author.get("literal"))
            if literal:
                text = literal
            else:
                text = " ".join(
                    part
                    for part in (
                        _optional_text(author.get("given")),
                        _optional_text(author.get("family")),
                    )
                    if part
                ) or None
        if text:
            names.append(text)
    return "; ".join(names) or None


def _editor_fallback(value: Any) -> str | None:
    text = _optional_text(value)
    return _author_text(parse_bibtex_authors(text)) if text else None


def _pages(value: Any) -> str | None:
    text = _optional_text(value)
    return text.replace("--", "-") if text else None


def _year(reference_data: Mapping[str, Any], extra: Mapping[str, Any]) -> int | None:
    value = reference_data.get("year")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raw = _optional_text(reference_data.get("year_raw"))
    if raw and re.fullmatch(r"[+-]?\d{1,4}", raw):
        return int(raw)
    date = _optional_text(extra.get("date"))
    match = _YEAR_FROM_DATE_RE.match(date or "")
    return int(match.group(1)) if match else None


def _joined_identifier(value: Any) -> str | None:
    if isinstance(value, str):
        return _optional_text(value)
    if not isinstance(value, list | tuple):
        return None
    items = [text for item in value if (text := _optional_text(item))]
    return "; ".join(items) or None


def _warning_for_omitted(field_name: str) -> str:
    return (
        f"BibTeX field {field_name!r} has no separate legacy concept field and "
        "was not stored."
    )


def normalize_bibliographic_entry(
    candidate: Mapping[str, Any],
) -> NormalizedBibliographicEntry:
    """Return the exact editable Add Concept reference contract for one candidate.

    ``candidate`` is the public candidate mapping produced by
    :mod:`mathmongo.source_catalog.bibtex`, the parser shared with Add Source.
    This adapter is pure and never opens files, accesses MongoDB, or persists a
    Reference.
    """
    if not isinstance(candidate, Mapping):
        raise TypeError("BibTeX candidate must be a mapping.")
    reference_data = candidate.get("reference_data")
    if not isinstance(reference_data, Mapping):
        raise ValueError("BibTeX candidate has no normalized reference_data mapping.")
    bibtex_data = reference_data.get("bibtex")
    if not isinstance(bibtex_data, Mapping):
        bibtex_data = {}
    extra = _casefolded_mapping(bibtex_data.get("extra"))

    entry_type = _optional_text(candidate.get("entry_type")) or _optional_text(
        bibtex_data.get("entry_type")
    )
    entry_type = entry_type.casefold() if entry_type else "unknown"
    warnings: list[str] = []
    concept_type = _BIBTEX_TYPE_TO_CONCEPT_TYPE.get(entry_type)
    if concept_type is None:
        concept_type = "miscelanea"
        warnings.append(
            f"BibTeX type {entry_type!r} has no exact legacy concept type; "
            "using 'miscelanea'."
        )

    authors = _author_text(reference_data.get("authors"))
    editor = _optional_text(extra.get("editor"))
    if not authors and editor:
        authors = _editor_fallback(editor)
    elif editor:
        warnings.append(_warning_for_omitted("editor"))

    title = _display_text(reference_data.get("title"))
    booktitle = _display_text(extra.get("booktitle"))
    journal = _display_text(reference_data.get("journal"))
    publisher = _display_text(reference_data.get("publisher"))
    source_title = title or booktitle or journal or publisher
    if title and booktitle:
        warnings.append(_warning_for_omitted("booktitle"))
    if title and journal:
        warnings.append(_warning_for_omitted("journal"))

    explicit_section = _optional_text(extra.get("section"))
    number = _optional_text(reference_data.get("number"))
    section = explicit_section or number
    if explicit_section and number:
        warnings.append(_warning_for_omitted("number"))

    isbn = _joined_identifier(reference_data.get("isbn"))
    issn = _optional_text(extra.get("issn"))
    if isbn and issn:
        warnings.append(_warning_for_omitted("issn"))
    identifier = isbn or issn

    consumed_extra = {
        "booktitle",
        "chapter",
        "date",
        "editor",
        "issn",
        "pages",
        "section",
    }
    for field_name in sorted(extra):
        if field_name not in consumed_extra:
            warnings.append(_warning_for_omitted(field_name))
    for field_name in ("language", "notes"):
        if _optional_text(reference_data.get(field_name)):
            warnings.append(_warning_for_omitted(field_name))

    reference = {
        "tipo_referencia": concept_type,
        "autor": authors,
        "fuente": source_title,
        "anio": _year(reference_data, extra),
        "tomo": _optional_text(reference_data.get("volume")),
        "edicion": _optional_text(reference_data.get("edition")),
        "paginas": _pages(extra.get("pages")),
        "capitulo": _optional_text(extra.get("chapter")),
        "seccion": section,
        "editorial": publisher,
        "doi": normalize_doi(reference_data.get("doi")),
        "url": _optional_text(reference_data.get("url")),
        "issbn": identifier,
        "citekey": _optional_text(candidate.get("citekey"))
        or _optional_text(bibtex_data.get("key")),
    }
    if tuple(reference) != _CONCEPT_REFERENCE_FIELDS:
        raise RuntimeError("Internal concept reference field contract changed unexpectedly.")
    return NormalizedBibliographicEntry(
        reference=reference,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = [
    "NormalizedBibliographicEntry",
    "normalize_bibliographic_entry",
]

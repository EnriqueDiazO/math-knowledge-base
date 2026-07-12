"""Lossless separation and diagnostics for concept-specific legacy locators."""

from __future__ import annotations

import re
from collections.abc import Iterable
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from mathmongo.source_catalog.normalization import clean_text
from mathmongo.source_catalog_migration.canonical import canonical_json
from mathmongo.source_catalog_migration.models import LegacyLocator
from mathmongo.source_catalog_migration.models import LocatorStatistics

LOCATOR_ALIASES: dict[str, tuple[str, ...]] = {
    "pages": ("paginas", "pages", "pagina"),
    "chapter": ("capitulo", "chapter"),
    "section": ("seccion", "section"),
    "equation": ("ecuacion", "equation"),
    "theorem": ("teorema", "theorem"),
}
_NOTE_ALIASES = ("notas", "notes")
_LOCATOR_NOTE_RE = re.compile(
    r"\b(?:p(?:age|ages|á?gina|á?ginas)?\.?|chapter|cap[ií]tulo|section|secci[oó]n|"
    r"equation|ecuaci[oó]n|theorem|teorema)\b",
    re.IGNORECASE,
)
_ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
_RANGE_RE = re.compile(r"\d\s*[-\u2010-\u2015\u2212]\s*\d")


def _first_preserved(reference: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
    first_present: Any = None
    has_present = False
    for name in aliases:
        if name not in reference:
            continue
        value = reference[name]
        if not has_present:
            first_present = value
            has_present = True
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return first_present if has_present else None


def _clearly_locating_note(value: Any) -> bool:
    return isinstance(value, str) and bool(_LOCATOR_NOTE_RE.search(clean_text(value)))


def locator_field_names(reference: Mapping[str, Any]) -> frozenset[str]:
    """Return exact raw keys that must not enter a bibliography fingerprint."""
    names = {
        alias for aliases in LOCATOR_ALIASES.values() for alias in aliases if alias in reference
    }
    for alias in _NOTE_ALIASES:
        if alias in reference and _clearly_locating_note(reference.get(alias)):
            names.add(alias)
    return frozenset(names)


def _locator_flags(locator: LegacyLocator) -> tuple[str, ...]:
    flags: list[str] = []
    values_by_field: dict[str, list[Any]] = {}
    for canonical, aliases in LOCATOR_ALIASES.items():
        alias_values = [
            locator.raw_alias_values[alias]
            for alias in aliases
            if alias in locator.raw_alias_values
        ]
        values = alias_values or [getattr(locator, f"{canonical}_raw")]
        values_by_field[canonical] = values
        populated_variants = {
            canonical_json(value)
            for value in values
            if value is not None and (not isinstance(value, str) or value.strip())
        }
        if len(populated_variants) > 1:
            flags.append(f"locator_{canonical}_alias_conflict")
        if any(value is not None and not isinstance(value, (str, int, float)) for value in values):
            flags.append(f"{canonical}_non_scalar")

    for value in values_by_field["pages"]:
        pages = clean_text(value)
        if pages.casefold() == "n/a":
            flags.append("locator_pages_na")
        if pages and _ROMAN_RE.fullmatch(pages):
            flags.append("locator_pages_roman")
        if pages and _RANGE_RE.search(pages):
            flags.append("locator_pages_range")
    if any(clean_text(value).startswith("!.") for value in values_by_field["section"]):
        flags.append("locator_section_suspicious")
    if locator.notes_raw is not None and not isinstance(
        locator.notes_raw,
        (str, int, float),
    ):
        flags.append("notes_non_scalar")
    return tuple(sorted(set(flags)))


def extract_locator(reference: Mapping[str, Any] | None) -> LegacyLocator:
    """Preserve locator aliases, values, and absent-vs-null diagnostics."""
    if not isinstance(reference, Mapping):
        return LegacyLocator()
    present: list[str] = []
    null: list[str] = []
    values: dict[str, Any] = {}
    for canonical, aliases in LOCATOR_ALIASES.items():
        matching = [alias for alias in aliases if alias in reference]
        if matching:
            present.append(canonical)
            if all(reference.get(alias) is None for alias in matching):
                null.append(canonical)
        values[canonical] = _first_preserved(reference, aliases)
    notes_raw = None
    matching_notes = [alias for alias in _NOTE_ALIASES if alias in reference]
    if matching_notes:
        note_value = _first_preserved(reference, _NOTE_ALIASES)
        if _clearly_locating_note(note_value):
            present.append("notes")
            if all(reference.get(alias) is None for alias in matching_notes):
                null.append("notes")
            notes_raw = note_value
    raw_alias_values = {
        alias: deepcopy(reference[alias]) for alias in sorted(locator_field_names(reference))
    }
    locator = LegacyLocator(
        pages_raw=values["pages"],
        chapter_raw=values["chapter"],
        section_raw=values["section"],
        equation_raw=values["equation"],
        theorem_raw=values["theorem"],
        notes_raw=notes_raw,
        raw_alias_values=raw_alias_values,
        present_fields=tuple(present),
        null_fields=tuple(null),
    )
    return locator.model_copy(update={"flags": _locator_flags(locator)})


def locator_has_value(locator: LegacyLocator) -> bool:
    """Return whether at least one locator contains a non-empty raw value."""
    return any(
        value is not None and (not isinstance(value, str) or bool(value.strip()))
        for value in (
            locator.pages_raw,
            locator.chapter_raw,
            locator.section_raw,
            locator.equation_raw,
            locator.theorem_raw,
            locator.notes_raw,
        )
    )


def unique_locators(locators: Iterable[LegacyLocator]) -> tuple[LegacyLocator, ...]:
    """Return deterministically ordered lossless locator variants."""
    by_payload = {canonical_json(locator): locator for locator in locators}
    return tuple(by_payload[key] for key in sorted(by_payload))


def locator_statistics(locators: Iterable[LegacyLocator]) -> LocatorStatistics:
    """Aggregate field presence and unique variants without changing raw values."""
    values = tuple(locators)

    def populated(field: str) -> int:
        return sum(
            (value := getattr(locator, field)) is not None
            and (not isinstance(value, str) or bool(value.strip()))
            for locator in values
        )

    return LocatorStatistics(
        concepts_with_locator=sum(locator_has_value(locator) for locator in values),
        pages_present=populated("pages_raw"),
        chapter_present=populated("chapter_raw"),
        section_present=populated("section_raw"),
        equation_present=populated("equation_raw"),
        theorem_present=populated("theorem_raw"),
        notes_present=populated("notes_raw"),
        variant_count=len(unique_locators(values)),
    )


__all__ = [
    "LOCATOR_ALIASES",
    "extract_locator",
    "locator_field_names",
    "locator_has_value",
    "locator_statistics",
    "unique_locators",
]

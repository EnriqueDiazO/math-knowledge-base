"""Deterministic, conflict-aware planning of legacy bibliographic References."""

from __future__ import annotations

import re
from collections import Counter
from collections import defaultdict
from collections.abc import Iterable
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from mathmongo.source_catalog.normalization import analyze_isbn
from mathmongo.source_catalog.normalization import author_title_year_fingerprint
from mathmongo.source_catalog.normalization import clean_text
from mathmongo.source_catalog.normalization import normalize_authors
from mathmongo.source_catalog.normalization import normalize_bibtex_key
from mathmongo.source_catalog.normalization import normalize_doi
from mathmongo.source_catalog.normalization import normalize_title
from mathmongo.source_catalog.normalization import normalize_url
from mathmongo.source_catalog.normalization import suggestion_key
from mathmongo.source_catalog_migration.canonical import candidate_key
from mathmongo.source_catalog_migration.canonical import canonical_json
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.inventory import LegacyInventory
from mathmongo.source_catalog_migration.inventory import has_embedded_reference
from mathmongo.source_catalog_migration.locator import extract_locator
from mathmongo.source_catalog_migration.locator import locator_field_names
from mathmongo.source_catalog_migration.locator import locator_statistics
from mathmongo.source_catalog_migration.locator import unique_locators
from mathmongo.source_catalog_migration.models import Conflict
from mathmongo.source_catalog_migration.models import LegacyKey
from mathmongo.source_catalog_migration.models import LegacyLocator
from mathmongo.source_catalog_migration.models import ReferenceCandidate
from mathmongo.source_catalog_migration.models import ReviewItem
from mathmongo.source_catalog_migration.models import ReviewStatus
from mathmongo.source_catalog_migration.models import WeakReferenceSuggestion

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_REFERENCE_TYPE_MAP = {
    "libro": "book",
    "book": "book",
    "articulo": "article",
    "artículo": "article",
    "article": "article",
    "tesis": "thesis",
    "tesina": "thesis",
    "thesis": "thesis",
    "pagina_web": "web",
    "página_web": "web",
    "web": "web",
    "informe": "report",
    "report": "report",
    "proceedings": "proceedings",
    "capitulo": "chapter",
    "capítulo": "chapter",
    "chapter": "chapter",
    "curso": "course",
    "course": "course",
    "miscelanea": "misc",
    "miscelánea": "misc",
    "misc": "misc",
}
_BIBLIOGRAPHY_ALIASES = {
    "reference_type": ("tipo_referencia", "tipo"),
    "authors": ("authors", "autores", "autor"),
    "title": ("titulo", "title", "fuente"),
    "year": ("anio", "year"),
    "year_raw": ("year_raw",),
    "journal": ("journal", "revista"),
    "publisher": ("publisher", "editorial"),
    "volume": ("volume", "tomo"),
    "number": ("number", "numero"),
    "edition": ("edition", "edicion"),
    "isbn": ("isbn", "issbn"),
    "doi": ("doi",),
    "url": ("url",),
    "citekey": ("citekey", "bibtex_key"),
    "language": ("language", "idioma"),
    "notes": ("notes", "notas"),
}
_ALL_BIBLIOGRAPHY_FIELDS = frozenset(
    alias for aliases in _BIBLIOGRAPHY_ALIASES.values() for alias in aliases
)
_COMPATIBILITY_FIELDS = (
    "reference_type",
    "unknown_reference_type",
    "authors",
    "title",
    "year",
    "journal",
    "publisher",
    "volume",
    "number",
    "edition",
    "language",
    "other_fields",
)


@dataclass(frozen=True, slots=True)
class ReferenceObservation:
    """One concept's embedded bibliography after lossless locator separation."""

    legacy_key: LegacyKey
    source_candidate_key: str
    raw_reference: Any
    raw_bibliography: dict[str, Any]
    locator: LegacyLocator
    normalized: dict[str, Any]
    proposed: dict[str, Any]
    unknown_fields: tuple[str, ...]
    flags: tuple[str, ...]
    bibliographic_fingerprint: str

    @property
    def sort_key(self) -> tuple[str, str]:
        """Order observations by exact legacy Source and concept ID."""
        return self.legacy_key.source, self.legacy_key.id


@dataclass(frozen=True, slots=True)
class ReferencePlanningResult:
    """Reference candidates plus stable lookup and human-review diagnostics."""

    candidates: tuple[ReferenceCandidate, ...]
    candidate_by_legacy_key: dict[tuple[str, str], str]
    observations: tuple[ReferenceObservation, ...]
    conflicts: tuple[Conflict, ...]
    review_items: tuple[ReviewItem, ...]
    weak_suggestions: tuple[WeakReferenceSuggestion, ...]
    conflict_safety_passed: bool


@dataclass(slots=True)
class _Group:
    observations: list[ReferenceObservation]
    rules: set[str]


@dataclass(frozen=True, slots=True)
class _PendingConflict:
    rule: str
    token: str
    left_keys: tuple[tuple[str, str], ...]
    right_keys: tuple[tuple[str, str], ...]
    contradictory_fields: tuple[str, ...]
    matching_fields: tuple[str, ...]


def is_valid_doi(value: Any) -> bool:
    """Return whether a normalized DOI is safe to use as strong evidence."""
    normalized = normalize_doi(value)
    return bool(
        normalized and _DOI_RE.fullmatch(normalized) and not any(c.isspace() for c in normalized)
    )


def _first(reference: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    first_present: Any = None
    present = False
    for alias in aliases:
        if alias not in reference:
            continue
        value = reference[alias]
        if not present:
            first_present = value
            present = True
        if value is not None and (not isinstance(value, str) or value.strip()):
            return value
    return first_present if present else None


def _as_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, Mapping)):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _reference_mapping(value: Any) -> tuple[dict[str, Any], tuple[str, ...]]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value)), ()
    if isinstance(value, str):
        return {"legacy_free_text": value, "titulo": value}, ("free_text_reference",)
    return {"legacy_unsupported_value": deepcopy(value)}, ("unsupported_reference_type",)


def _reference_type(value: Any) -> str:
    normalized = clean_text(value).casefold()
    if not normalized:
        return "misc"
    return _REFERENCE_TYPE_MAP.get(normalized, "other")


def _unknown_reference_type(value: Any) -> str:
    normalized = clean_text(value).casefold()
    return normalized if normalized and normalized not in _REFERENCE_TYPE_MAP else ""


def _raw_authors(value: Any) -> list[Any]:
    return _as_values(value)


def _alias_comparison_value(field: str, value: Any) -> Any:
    if field == "reference_type":
        return _reference_type(value), _unknown_reference_type(value)
    if field == "authors":
        return normalize_authors(_raw_authors(value))
    if field in {"title", "journal", "publisher"}:
        return normalize_title(value)
    if field in {"year", "year_raw", "volume", "number", "edition", "language", "notes"}:
        return clean_text(value).casefold()
    if field == "isbn":
        observations = [analyze_isbn(item) for item in _as_values(value) if item is not None]
        return tuple(
            sorted(
                {item.normalized or clean_text(item.original).casefold() for item in observations}
            )
        )
    if field == "doi":
        return normalize_doi(value)
    if field == "url":
        return normalize_url(value)
    if field == "citekey":
        return normalize_bibtex_key(value)
    return value


def _bibliography_alias_conflicts(reference: Mapping[str, Any]) -> tuple[str, ...]:
    conflicts: list[str] = []
    for field, aliases in _BIBLIOGRAPHY_ALIASES.items():
        values = [
            reference[alias]
            for alias in aliases
            if alias in reference
            and reference[alias] is not None
            and (not isinstance(reference[alias], str) or reference[alias].strip())
        ]
        if len(values) < 2:
            continue
        normalized = {canonical_json(_alias_comparison_value(field, value)) for value in values}
        if len(normalized) > 1:
            conflicts.append(field)
    return tuple(sorted(conflicts))


def _normalized_reference(
    concept: Mapping[str, Any],
    reference: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    flags: list[str] = []
    raw_type = _first(reference, _BIBLIOGRAPHY_ALIASES["reference_type"])
    unknown_type = _unknown_reference_type(raw_type)
    if unknown_type:
        flags.append("unknown_reference_type")
    for field in _bibliography_alias_conflicts(reference):
        flags.append(f"bibliography_{field}_alias_conflict")
    raw_authors = _raw_authors(_first(reference, _BIBLIOGRAPHY_ALIASES["authors"]))
    raw_title = _first(reference, _BIBLIOGRAPHY_ALIASES["title"])
    raw_year = _first(reference, _BIBLIOGRAPHY_ALIASES["year"])
    raw_year_text = _first(reference, _BIBLIOGRAPHY_ALIASES["year_raw"])
    embedded_citekey = _first(reference, _BIBLIOGRAPHY_ALIASES["citekey"])
    top_citekey = concept.get("citekey") if "citekey" in concept else None
    normalized_citekeys = tuple(
        sorted(
            {
                value
                for raw in (embedded_citekey, top_citekey)
                if (value := normalize_bibtex_key(raw))
            }
        )
    )
    if len(normalized_citekeys) > 1:
        flags.append("citekey_metadata_conflict")

    doi_raw = _first(reference, _BIBLIOGRAPHY_ALIASES["doi"])
    doi_normalized = normalize_doi(doi_raw)
    valid_doi = doi_normalized if is_valid_doi(doi_raw) else None
    if doi_normalized and not valid_doi:
        flags.append("invalid_doi")

    isbn_raw: list[Any] = []
    for alias in _BIBLIOGRAPHY_ALIASES["isbn"]:
        if alias in reference:
            isbn_raw.extend(_as_values(reference.get(alias)))
    isbn_observations = [analyze_isbn(value) for value in isbn_raw if value is not None]
    valid_isbns = tuple(
        sorted({item.normalized for item in isbn_observations if item.valid and item.normalized})
    )
    invalid_isbns = tuple(
        sorted({item.normalized or item.original for item in isbn_observations if not item.valid})
    )
    if invalid_isbns:
        flags.append("invalid_legacy_isbn")

    year_normalized = clean_text(raw_year if raw_year is not None else raw_year_text).casefold()
    normalized_authors = normalize_authors(raw_authors)
    normalized_title = normalize_title(raw_title)
    normalized = {
        "reference_type": _reference_type(raw_type),
        "unknown_reference_type": unknown_type,
        "authors": normalized_authors,
        "title": normalized_title,
        "year": year_normalized,
        "journal": normalize_title(_first(reference, _BIBLIOGRAPHY_ALIASES["journal"])),
        "publisher": normalize_title(_first(reference, _BIBLIOGRAPHY_ALIASES["publisher"])),
        "volume": clean_text(_first(reference, _BIBLIOGRAPHY_ALIASES["volume"])).casefold(),
        "number": clean_text(_first(reference, _BIBLIOGRAPHY_ALIASES["number"])).casefold(),
        "edition": clean_text(_first(reference, _BIBLIOGRAPHY_ALIASES["edition"])).casefold(),
        "doi": valid_doi,
        "doi_observed": doi_normalized,
        "valid_isbns": valid_isbns,
        "invalid_isbns": invalid_isbns,
        "citekeys": normalized_citekeys,
        "url": normalize_url(_first(reference, _BIBLIOGRAPHY_ALIASES["url"])),
        "language": clean_text(_first(reference, _BIBLIOGRAPHY_ALIASES["language"])).casefold(),
        "notes": clean_text(_first(reference, _BIBLIOGRAPHY_ALIASES["notes"])),
        "author_title_year": author_title_year_fingerprint(
            raw_authors,
            raw_title,
            raw_year if raw_year is not None else raw_year_text,
        ),
    }
    proposed = {
        "reference_type": _reference_type(raw_type),
        "authors": deepcopy(raw_authors),
        "title": deepcopy(raw_title),
        "year": deepcopy(raw_year),
        "year_raw": deepcopy(raw_year_text),
        "journal": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["journal"])),
        "publisher": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["publisher"])),
        "volume": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["volume"])),
        "number": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["number"])),
        "edition": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["edition"])),
        "isbn": deepcopy(isbn_raw),
        "doi": deepcopy(doi_raw),
        "url": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["url"])),
        "citekey": deepcopy(embedded_citekey or top_citekey),
        "language": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["language"])),
        "notes": deepcopy(_first(reference, _BIBLIOGRAPHY_ALIASES["notes"])),
    }
    return normalized, proposed, tuple(sorted(set(flags))), normalized_citekeys


def _drop_empty(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {str(key): _drop_empty(item) for key, item in value.items()}
        return {key: item for key, item in result.items() if item not in (None, "", [], {}, ())}
    if isinstance(value, tuple):
        return tuple(_drop_empty(item) for item in value)
    if isinstance(value, list):
        return [_drop_empty(item) for item in value]
    return value


def _fingerprint_payload(normalized: Mapping[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            key: value
            for key, value in normalized.items()
            if key not in {"author_title_year", "doi_observed", "invalid_isbns"}
        }
    )


def build_reference_observations(
    inventory: LegacyInventory,
    source_keys: Mapping[str, str],
) -> tuple[ReferenceObservation, ...]:
    """Convert each nonempty embedded reference without UUIDs or timestamps."""
    observations: list[ReferenceObservation] = []
    for concept in inventory.concepts:
        if not has_embedded_reference(concept):
            continue
        raw_value = concept.get("referencia")
        reference, initial_flags = _reference_mapping(raw_value)
        locator = extract_locator(reference)
        excluded = locator_field_names(reference)
        raw_bibliography = {
            str(key): deepcopy(value)
            for key, value in reference.items()
            if str(key) not in excluded
        }
        if "citekey" in concept:
            raw_bibliography["legacy_concept_citekey"] = deepcopy(concept.get("citekey"))
        normalized, proposed, flags, _citekeys = _normalized_reference(
            concept,
            raw_bibliography,
        )
        unknown = tuple(
            sorted(
                str(key)
                for key in reference
                if str(key) not in _ALL_BIBLIOGRAPHY_FIELDS and str(key) not in excluded
            )
        )
        if unknown:
            normalized = dict(normalized)
            normalized["other_fields"] = _drop_empty(
                {key: deepcopy(reference[key]) for key in unknown}
            )
            proposed = dict(proposed)
            proposed["other_fields"] = {key: deepcopy(reference[key]) for key in unknown}
        fingerprint = sha256_digest(_fingerprint_payload(normalized))
        legacy_key = LegacyKey(id=str(concept.get("id")), source=str(concept.get("source")))
        observations.append(
            ReferenceObservation(
                legacy_key=legacy_key,
                source_candidate_key=source_keys[legacy_key.source],
                raw_reference=deepcopy(raw_value),
                raw_bibliography=raw_bibliography,
                locator=locator,
                normalized=normalized,
                proposed=proposed,
                unknown_fields=unknown,
                flags=tuple(sorted(set(initial_flags) | set(flags) | set(locator.flags))),
                bibliographic_fingerprint=fingerprint,
            )
        )
    return tuple(sorted(observations, key=lambda item: item.sort_key))


def _tokens(observation: ReferenceObservation, rule: str) -> tuple[str, ...]:
    normalized = observation.normalized
    if rule == "doi":
        value = normalized.get("doi")
        return (value,) if value else ()
    if rule == "isbn":
        return tuple(normalized.get("valid_isbns") or ())
    if rule == "citekey":
        return tuple(normalized.get("citekeys") or ()) if _identity_sufficient(observation) else ()
    if rule == "author_title_year":
        value = normalized.get("author_title_year")
        return (value,) if value else ()
    return (observation.bibliographic_fingerprint,)


def _populated(value: Any) -> bool:
    return value not in (None, "", (), [], {})


def _flag_contradictory_fields(flags: Iterable[str]) -> tuple[str, ...]:
    fields: set[str] = set()
    for flag in flags:
        if flag == "citekey_metadata_conflict":
            fields.add("citekey")
        elif flag.startswith("bibliography_") and flag.endswith("_alias_conflict"):
            fields.add(flag.removeprefix("bibliography_").removesuffix("_alias_conflict"))
    return tuple(sorted(fields))


def _compatible(
    left: ReferenceObservation, right: ReferenceObservation
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    contradictions: list[str] = [
        *_flag_contradictory_fields(left.flags),
        *_flag_contradictory_fields(right.flags),
    ]
    matching: list[str] = []
    for field in _COMPATIBILITY_FIELDS:
        left_value = left.normalized.get(field)
        right_value = right.normalized.get(field)
        if not _populated(left_value) or not _populated(right_value):
            continue
        if left_value == right_value:
            matching.append(field)
        else:
            contradictions.append(field)
    for field in ("doi",):
        left_value = left.normalized.get(field)
        right_value = right.normalized.get(field)
        if _populated(left_value) and _populated(right_value):
            if left_value == right_value:
                matching.append(field)
            else:
                contradictions.append(field)
    left_isbns = set(left.normalized.get("valid_isbns") or ())
    right_isbns = set(right.normalized.get("valid_isbns") or ())
    if left_isbns and right_isbns:
        if left_isbns & right_isbns:
            matching.append("isbn")
        else:
            contradictions.append("isbn")
    left_citekeys = set(left.normalized.get("citekeys") or ())
    right_citekeys = set(right.normalized.get("citekeys") or ())
    if left_citekeys and right_citekeys:
        if left_citekeys & right_citekeys:
            matching.append("citekey")
        else:
            contradictions.append("citekey")
    return not contradictions, tuple(sorted(set(matching))), tuple(sorted(set(contradictions)))


def _groups_compatible(
    left: _Group, right: _Group
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    matching: set[str] = set()
    contradictions: set[str] = set()
    for left_item in left.observations:
        for right_item in right.observations:
            compatible, pair_matching, pair_contradictions = _compatible(left_item, right_item)
            matching.update(pair_matching)
            contradictions.update(pair_contradictions)
            if not compatible:
                return False, tuple(sorted(matching)), tuple(sorted(contradictions))
    return True, tuple(sorted(matching)), ()


def _group_keys(group: _Group) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted((item.legacy_key.id, item.legacy_key.source) for item in group.observations)
    )


def _merge_by_rule(
    groups: list[_Group],
    rule: str,
    conflicts: list[_PendingConflict],
) -> None:
    while True:
        merged = False
        token_groups: dict[str, list[int]] = defaultdict(list)
        for index, group in enumerate(groups):
            tokens = {
                token for observation in group.observations for token in _tokens(observation, rule)
            }
            for token in sorted(tokens):
                token_groups[token].append(index)
        for token in sorted(token_groups):
            indices = sorted(set(token_groups[token]))
            for position, left_index in enumerate(indices):
                for right_index in indices[position + 1 :]:
                    left = groups[left_index]
                    right = groups[right_index]
                    compatible, matching, contradictory = _groups_compatible(left, right)
                    if not compatible:
                        conflicts.append(
                            _PendingConflict(
                                rule=rule,
                                token=token,
                                left_keys=_group_keys(left),
                                right_keys=_group_keys(right),
                                contradictory_fields=contradictory,
                                matching_fields=matching,
                            )
                        )
                        continue
                    left.observations.extend(right.observations)
                    left.observations.sort(key=lambda item: item.sort_key)
                    left.rules.update(right.rules)
                    left.rules.add(rule)
                    del groups[right_index]
                    merged = True
                    break
                if merged:
                    break
            if merged:
                break
        if not merged:
            return


def _identity_sufficient(observation: ReferenceObservation) -> bool:
    normalized = observation.normalized
    if normalized.get("doi") or normalized.get("valid_isbns"):
        return True
    if normalized.get("author_title_year"):
        return True
    signals = sum(
        _populated(normalized.get(field)) for field in ("authors", "title", "year", "url")
    )
    if normalized.get("citekeys") and signals >= 1:
        return True
    return signals >= 2


def _primary_rule(group: _Group) -> str:
    observations = group.observations
    for rule in ("doi", "isbn", "citekey", "author_title_year"):
        if any(_tokens(item, rule) for item in observations):
            return rule
    return "bibliographic_fingerprint"


def _merged_normalized(group: _Group) -> dict[str, Any]:
    fields = sorted({key for item in group.observations for key in item.normalized})
    merged: dict[str, Any] = {}
    for field in fields:
        values = [item.normalized.get(field) for item in group.observations]
        nonempty = [value for value in values if _populated(value)]
        if not nonempty:
            merged[field] = values[0] if values else None
            continue
        if field in {"valid_isbns", "invalid_isbns", "citekeys"}:
            merged[field] = tuple(
                sorted({nested for value in nonempty for nested in _as_values(value)})
            )
            continue
        counts = Counter(canonical_json(value) for value in nonempty)
        selected = min(counts, key=lambda key: (-counts[key], key))
        merged[field] = next(value for value in nonempty if canonical_json(value) == selected)
    return merged


def _merged_proposal(group: _Group) -> dict[str, Any]:
    fields = sorted({key for item in group.observations for key in item.proposed})
    result: dict[str, Any] = {}
    for field in fields:
        values = [item.proposed.get(field) for item in group.observations]
        populated = [value for value in values if _populated(value)]
        if not populated:
            result[field] = values[0] if values else None
            continue
        counts = Counter(canonical_json(value) for value in populated)
        selected = min(counts, key=lambda key: (-counts[key], key))
        result[field] = deepcopy(
            next(value for value in populated if canonical_json(value) == selected)
        )
    return result


def _raw_summary(raw: Mapping[str, Any]) -> str:
    fields = sorted(str(key) for key, value in raw.items() if _populated(value))
    return "fields=" + ",".join(fields[:16]) + (",..." if len(fields) > 16 else "")


def _candidate_model(
    group: _Group,
    *,
    conflicted_keys: set[tuple[str, str]],
) -> ReferenceCandidate:
    observations = tuple(sorted(group.observations, key=lambda item: item.sort_key))
    merged_normalized = _merged_normalized(group)
    primary_rule = _primary_rule(group)
    legacy_keys = tuple(item.legacy_key for item in observations)
    component_conflict = any(
        (item.legacy_key.id, item.legacy_key.source) in conflicted_keys for item in observations
    )
    internal_citekey_conflict = any(
        "citekey_metadata_conflict" in item.flags for item in observations
    )
    internal_contradictions = tuple(
        sorted({field for item in observations for field in _flag_contradictory_fields(item.flags)})
    )
    internal_review_warning = any(
        flag in {"invalid_doi", "invalid_legacy_isbn", "unknown_reference_type"}
        or flag.startswith("bibliography_")
        and flag.endswith("_alias_conflict")
        for item in observations
        for flag in item.flags
    )
    sufficient = all(_identity_sufficient(item) for item in observations)
    if component_conflict:
        classification = ReviewStatus.METADATA_CONFLICT
    elif not sufficient:
        classification = ReviewStatus.INSUFFICIENT_IDENTITY
    elif internal_citekey_conflict or internal_review_warning:
        classification = ReviewStatus.REVIEW_REQUIRED
    elif {"doi", "isbn"} & group.rules and len(
        {item.bibliographic_fingerprint for item in observations}
    ) > 1:
        classification = ReviewStatus.SAFE_STRONG
    elif {"citekey", "author_title_year"} & group.rules and len(
        {item.bibliographic_fingerprint for item in observations}
    ) > 1:
        classification = ReviewStatus.REVIEW_REQUIRED
    elif primary_rule == "citekey" and len(observations) > 1:
        classification = ReviewStatus.REVIEW_REQUIRED
    else:
        classification = ReviewStatus.SAFE_EXACT
    content = {
        "normalized_bibliography": _fingerprint_payload(merged_normalized),
        "legacy_keys": [item.model_dump(mode="json") for item in legacy_keys],
    }
    key = candidate_key("reference_candidate", content)
    raw_by_payload = {
        canonical_json(item.raw_bibliography): deepcopy(item.raw_bibliography)
        for item in observations
    }
    locator_variants = unique_locators(item.locator for item in observations)
    warnings = sorted({flag for item in observations for flag in item.flags})
    matching_fields = sorted(
        field
        for field in _COMPATIBILITY_FIELDS
        if len(
            {
                canonical_json(item.normalized.get(field))
                for item in observations
                if _populated(item.normalized.get(field))
            }
        )
        == 1
    )
    contradictory_fields = internal_contradictions
    return ReferenceCandidate(
        reference_candidate_key=key,
        classification=classification,
        grouping_rules=tuple(sorted({primary_rule, *group.rules})),
        concept_count=len(observations),
        source_candidate_keys=tuple(sorted({item.source_candidate_key for item in observations})),
        legacy_keys=legacy_keys,
        bibliographic_fingerprint=sha256_digest(_fingerprint_payload(merged_normalized)),
        normalized_bibliography=_fingerprint_payload(merged_normalized),
        proposed_bibliography=_merged_proposal(group),
        raw_variants=tuple(raw_by_payload[payload] for payload in sorted(raw_by_payload)),
        raw_variant_count=len(raw_by_payload),
        unknown_fields=tuple(
            sorted({field for item in observations for field in item.unknown_fields})
        ),
        normalized_doi=merged_normalized.get("doi"),
        normalized_isbns=tuple(merged_normalized.get("valid_isbns") or ()),
        normalized_citekeys=tuple(merged_normalized.get("citekeys") or ()),
        matching_fields=tuple(matching_fields),
        contradictory_fields=contradictory_fields,
        locator_variants=locator_variants,
        locator_statistics=locator_statistics(item.locator for item in observations),
        warnings=tuple(warnings),
    )


def _review_items(candidates: tuple[ReferenceCandidate, ...]) -> tuple[ReviewItem, ...]:
    items: list[ReviewItem] = []
    for candidate in candidates:
        problems: set[str] = set()
        if candidate.classification not in {ReviewStatus.SAFE_EXACT, ReviewStatus.SAFE_STRONG}:
            problems.add(candidate.classification.value)
        for warning in candidate.warnings:
            if (
                warning
                in {
                    "invalid_doi",
                    "invalid_legacy_isbn",
                    "citekey_metadata_conflict",
                    "unsupported_reference_type",
                    "free_text_reference",
                    "unknown_reference_type",
                }
                or warning.startswith("bibliography_")
                and warning.endswith("_alias_conflict")
            ):
                problems.add(warning)
        for locator in candidate.locator_variants:
            problems.update(locator.flags)
        for problem in sorted(problems):
            key = candidate_key(
                "review",
                {"candidate_key": candidate.reference_candidate_key, "problem": problem},
            )
            items.append(
                ReviewItem(
                    review_key=key,
                    candidate_key=candidate.reference_candidate_key,
                    problem_type=problem,
                    source_candidate_keys=candidate.source_candidate_keys,
                    concept_count=candidate.concept_count,
                    matching_fields=candidate.matching_fields,
                    contradictory_fields=candidate.contradictory_fields,
                    normalized_doi=candidate.normalized_doi,
                    normalized_isbns=candidate.normalized_isbns,
                    normalized_citekeys=candidate.normalized_citekeys,
                    raw_variant_summaries=tuple(
                        _raw_summary(raw) for raw in candidate.raw_variants[:8]
                    ),
                    locator_variants=candidate.locator_variants[:16],
                )
            )
    return tuple(sorted(items, key=lambda item: item.review_key))


def plan_references(
    inventory: LegacyInventory,
    source_keys: Mapping[str, str],
) -> ReferencePlanningResult:
    """Group embedded bibliographies while keeping concepts strictly distinct."""
    observations = build_reference_observations(inventory, source_keys)
    by_fingerprint: dict[tuple[str, ...], list[ReferenceObservation]] = defaultdict(list)
    for observation in observations:
        has_internal_contradiction = bool(_flag_contradictory_fields(observation.flags))
        if _identity_sufficient(observation) and not has_internal_contradiction:
            grouping_key = (observation.bibliographic_fingerprint,)
        else:
            # An identical weak payload is not enough evidence to assert that two
            # concepts cite one work. Keep each observation independently reviewable.
            grouping_key = (
                observation.bibliographic_fingerprint,
                observation.legacy_key.source,
                observation.legacy_key.id,
            )
        by_fingerprint[grouping_key].append(observation)
    groups = [
        _Group(observations=sorted(items, key=lambda item: item.sort_key), rules=set())
        for _fingerprint, items in sorted(by_fingerprint.items())
    ]
    pending_conflicts: list[_PendingConflict] = []
    for rule in ("doi", "isbn", "citekey", "author_title_year"):
        _merge_by_rule(groups, rule, pending_conflicts)

    conflict_keys = {
        key for conflict in pending_conflicts for key in (*conflict.left_keys, *conflict.right_keys)
    }
    candidates = tuple(
        sorted(
            (_candidate_model(group, conflicted_keys=conflict_keys) for group in groups),
            key=lambda item: item.reference_candidate_key,
        )
    )
    candidate_for_key = {
        (legacy.id, legacy.source): candidate.reference_candidate_key
        for candidate in candidates
        for legacy in candidate.legacy_keys
    }
    candidate_models = {candidate.reference_candidate_key: candidate for candidate in candidates}
    pending_by_candidates: dict[tuple[str, ...], list[_PendingConflict]] = defaultdict(list)
    conflict_safety_passed = True
    for pending in pending_conflicts:
        left_candidates = {
            candidate_for_key[key] for key in pending.left_keys if key in candidate_for_key
        }
        right_candidates = {
            candidate_for_key[key] for key in pending.right_keys if key in candidate_for_key
        }
        candidate_keys = tuple(sorted(left_candidates | right_candidates))
        if len(candidate_keys) < 2:
            conflict_safety_passed = False
            continue
        if left_candidates & right_candidates:
            conflict_safety_passed = False
        pending_by_candidates[candidate_keys].append(pending)

    conflicts_by_key: dict[str, Conflict] = {}
    rule_priority = {
        rule: index for index, rule in enumerate(("doi", "isbn", "citekey", "author_title_year"))
    }
    for candidate_keys, evidence in sorted(pending_by_candidates.items()):
        primary = min(evidence, key=lambda item: (rule_priority[item.rule], item.token))
        models = [candidate_models[key] for key in candidate_keys]
        conflict_key = candidate_key(
            "conflict",
            {
                "candidates": candidate_keys,
                "evidence": sorted((item.rule, item.token) for item in evidence),
            },
        )
        conflicts_by_key[conflict_key] = Conflict(
            conflict_key=conflict_key,
            conflict_type=f"{primary.rule}_metadata_conflict",
            reference_candidate_keys=candidate_keys,
            source_candidate_keys=tuple(
                sorted({key for model in models for key in model.source_candidate_keys})
            ),
            concept_count=sum(model.concept_count for model in models),
            matching_fields=tuple(
                sorted({field for item in evidence for field in item.matching_fields})
            ),
            contradictory_fields=tuple(
                sorted({field for item in evidence for field in item.contradictory_fields})
            ),
            normalized_doi=next(
                (item.token for item in evidence if item.rule == "doi"),
                None,
            ),
            normalized_isbns=tuple(
                sorted({item.token for item in evidence if item.rule == "isbn"})
            ),
            normalized_citekeys=tuple(
                sorted({item.token for item in evidence if item.rule == "citekey"})
            ),
            raw_variant_summaries=tuple(
                _raw_summary(raw) for model in models for raw in model.raw_variants[:4]
            )[:16],
            locator_variants=tuple(
                locator for model in models for locator in model.locator_variants[:8]
            )[:16],
        )
    conflicts = tuple(conflicts_by_key[key] for key in sorted(conflicts_by_key))
    matching_by_candidate: dict[str, set[str]] = defaultdict(set)
    contradictory_by_candidate: dict[str, set[str]] = defaultdict(set)
    for conflict in conflicts:
        for key in conflict.reference_candidate_keys:
            matching_by_candidate[key].update(conflict.matching_fields)
            contradictory_by_candidate[key].update(conflict.contradictory_fields)
    candidates = tuple(
        candidate.model_copy(
            update={
                "matching_fields": tuple(
                    sorted(
                        set(candidate.matching_fields)
                        | matching_by_candidate[candidate.reference_candidate_key]
                    )
                ),
                "contradictory_fields": tuple(
                    sorted(
                        set(candidate.contradictory_fields)
                        | contradictory_by_candidate[candidate.reference_candidate_key]
                    )
                ),
            }
        )
        for candidate in candidates
    )
    review_items = _review_items(candidates)
    updated_candidate_models = {
        candidate.reference_candidate_key: candidate for candidate in candidates
    }
    weak_suggestions: list[WeakReferenceSuggestion] = []
    for left_key, right_key in weak_reference_suggestions(candidates):
        left = updated_candidate_models[left_key]
        right = updated_candidate_models[right_key]
        similarity_key = suggestion_key(left.proposed_bibliography.get("title"))
        weak_suggestions.append(
            WeakReferenceSuggestion(
                suggestion_key=candidate_key(
                    "weak_reference_suggestion",
                    {
                        "candidates": (left_key, right_key),
                        "reason": "weak_title_similarity",
                        "title_similarity_key": similarity_key,
                    },
                ),
                reference_candidate_keys=(left_key, right_key),
                source_candidate_keys=tuple(
                    sorted(set(left.source_candidate_keys) | set(right.source_candidate_keys))
                ),
                concept_count=left.concept_count + right.concept_count,
                title_similarity_key=similarity_key,
            )
        )
    return ReferencePlanningResult(
        candidates=candidates,
        candidate_by_legacy_key=candidate_for_key,
        observations=observations,
        conflicts=conflicts,
        review_items=review_items,
        weak_suggestions=tuple(sorted(weak_suggestions, key=lambda item: item.suggestion_key)),
        conflict_safety_passed=conflict_safety_passed
        and all(
            all(
                _compatible(left, right)[0]
                for index, left in enumerate(group.observations)
                for right in group.observations[index + 1 :]
            )
            for group in groups
        ),
    )


def weak_reference_suggestions(
    candidates: Iterable[ReferenceCandidate],
) -> tuple[tuple[str, str], ...]:
    """Return warning-only candidate pairs with weak title similarity; never merge them."""
    values = tuple(sorted(candidates, key=lambda item: item.reference_candidate_key))
    suggestions: list[tuple[str, str]] = []
    for index, left in enumerate(values):
        left_title = suggestion_key(left.proposed_bibliography.get("title"))
        if not left_title:
            continue
        for right in values[index + 1 :]:
            right_title = suggestion_key(right.proposed_bibliography.get("title"))
            if left_title == right_title:
                suggestions.append((left.reference_candidate_key, right.reference_candidate_key))
    return tuple(suggestions)


__all__ = [
    "ReferenceObservation",
    "ReferencePlanningResult",
    "build_reference_observations",
    "is_valid_doi",
    "plan_references",
    "weak_reference_suggestions",
]

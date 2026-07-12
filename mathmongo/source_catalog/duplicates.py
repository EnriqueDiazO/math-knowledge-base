"""Typed, side-effect-free duplicate diagnostics for Source catalog records."""

# ruff: noqa: D101,D102

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.normalization import clean_text
from mathmongo.source_catalog.normalization import normalize_author
from mathmongo.source_catalog.normalization import normalize_bibtex_key
from mathmongo.source_catalog.normalization import normalize_doi
from mathmongo.source_catalog.normalization import normalize_isbn
from mathmongo.source_catalog.normalization import normalize_title
from mathmongo.source_catalog.normalization import normalize_url
from mathmongo.source_catalog.normalization import suggestion_key


class DuplicateClassification(str, Enum):
    EXACT = "exact"
    STRONG = "strong"
    POSSIBLE = "possible"
    WEAK = "weak"
    NONE = "none"


class DuplicateEvidenceType(str, Enum):
    EXACT = "exact"
    SOURCE_NAME = "source_name"
    SOURCE_ALIAS = "source_alias"
    DOI = "doi"
    ISBN = "isbn"
    BIBTEX_KEY = "bibtex_key"
    AUTHOR_TITLE_YEAR = "author_title_year"
    URL = "url"
    SUGGESTION = "suggestion"


class DuplicateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_type: DuplicateEvidenceType
    value: str | None = None
    contextual: bool = False
    explanation: str = ""


class DuplicateMatch(BaseModel):
    """Classification of one existing entity against a candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str
    classification: DuplicateClassification
    evidence: list[DuplicateEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_candidate(self) -> bool:
        return self.classification != DuplicateClassification.NONE


# Backwards-friendly semantic alias for repository return annotations.
DuplicateCandidate = DuplicateMatch


def _as_source(value: Source | Mapping[str, Any]) -> Source:
    return value if isinstance(value, Source) else Source.model_validate(value)


def _as_reference(value: Reference | Mapping[str, Any]) -> Reference:
    return value if isinstance(value, Reference) else Reference.model_validate(value)


def _source_exact_signature(source: Source) -> tuple[Any, ...]:
    return (
        source.name,
        tuple((alias.value, alias.normalized) for alias in source.aliases),
        source.source_type.value,
        source.description,
        source.language,
        tuple(source.tags),
        source.rights_default.model_dump(mode="json"),
    )


def classify_source_duplicate(
    candidate: Source | Mapping[str, Any],
    existing: Source | Mapping[str, Any],
) -> DuplicateMatch:
    """Classify Source similarity without authorizing a merge."""
    candidate = _as_source(candidate)
    existing = _as_source(existing)

    if _source_exact_signature(candidate) == _source_exact_signature(existing):
        return DuplicateMatch(
            entity_id=existing.source_id,
            classification=DuplicateClassification.EXACT,
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.EXACT,
                    value=candidate.name_normalized,
                    explanation="All normalized catalog fields are equal.",
                )
            ],
        )

    if candidate.name_normalized == existing.name_normalized:
        return DuplicateMatch(
            entity_id=existing.source_id,
            classification=DuplicateClassification.STRONG,
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.SOURCE_NAME,
                    value=candidate.name_normalized,
                    explanation="Normalized Source names are equal.",
                )
            ],
            warnings=["Review both Sources; normalized equality never merges them automatically."],
        )

    candidate_aliases = {alias.normalized for alias in candidate.aliases}
    existing_aliases = {alias.normalized for alias in existing.aliases}
    alias_overlap = (
        candidate.name_normalized in existing_aliases
        or existing.name_normalized in candidate_aliases
        or bool(candidate_aliases & existing_aliases)
    )
    if alias_overlap:
        shared = sorted(candidate_aliases & existing_aliases)
        value = shared[0] if shared else candidate.name_normalized
        return DuplicateMatch(
            entity_id=existing.source_id,
            classification=DuplicateClassification.POSSIBLE,
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.SOURCE_ALIAS,
                    value=value,
                    explanation="A primary name or alias overlaps after catalog normalization.",
                )
            ],
            warnings=["Alias overlap requires human review."],
        )

    candidate_suggestions = {
        suggestion_key(candidate.name),
        *(suggestion_key(alias.value) for alias in candidate.aliases),
    }
    existing_suggestions = {
        suggestion_key(existing.name),
        *(suggestion_key(alias.value) for alias in existing.aliases),
    }
    candidate_suggestions.discard("")
    existing_suggestions.discard("")
    weak_overlap = sorted(candidate_suggestions & existing_suggestions)
    if weak_overlap:
        return DuplicateMatch(
            entity_id=existing.source_id,
            classification=DuplicateClassification.WEAK,
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.SUGGESTION,
                    value=weak_overlap[0],
                    explanation="Names match only after removing accents and punctuation.",
                )
            ],
            warnings=[
                "Weak normalization is a suggestion only and must never trigger automatic merging."
            ],
        )

    return DuplicateMatch(entity_id=existing.source_id, classification=DuplicateClassification.NONE)


def _reference_exact_signature(reference: Reference) -> tuple[Any, ...]:
    authors = tuple(
        normalize_author(author.model_dump(mode="python")) for author in reference.authors
    )
    isbns = tuple(sorted(filter(None, (normalize_isbn(value) for value in reference.isbn))))
    return (
        reference.reference_type.value,
        normalize_doi(reference.doi),
        isbns,
        normalize_bibtex_key(reference.bibtex.key),
        authors,
        normalize_title(reference.title),
        reference.year,
        clean_text(reference.year_raw).casefold(),
        normalize_title(reference.journal),
        normalize_title(reference.publisher),
        clean_text(reference.volume).casefold(),
        clean_text(reference.number).casefold(),
        clean_text(reference.edition).casefold(),
        normalize_url(reference.url),
    )


def _has_exact_reference_identity(reference: Reference) -> bool:
    """Require more than a globally ambiguous citekey/title before EXACT."""
    if normalize_doi(reference.doi) or reference.fingerprints.isbn_normalized:
        return True
    if reference.fingerprints.author_title_year:
        return True
    signals = sum(
        (
            bool(reference.authors),
            bool(normalize_title(reference.title)),
            reference.year is not None or bool(clean_text(reference.year_raw)),
            bool(normalize_url(reference.url)),
        )
    )
    return signals >= 2


def _shared_context(
    candidate: Reference,
    existing: Reference,
    source_context_ids: Iterable[str] | None,
    import_context: str | None,
) -> bool:
    candidate_sources = set(candidate.source_ids)
    existing_sources = set(existing.source_ids)
    if candidate_sources & existing_sources:
        return True
    if source_context_ids is not None:
        context = {str(value) for value in source_context_ids if str(value)}
        if (
            context
            and (not candidate_sources or bool(candidate_sources & context))
            and (not existing_sources or bool(existing_sources & context))
        ):
            return True
    return bool(clean_text(import_context))


def classify_reference_duplicate(
    candidate: Reference | Mapping[str, Any],
    existing: Reference | Mapping[str, Any],
    *,
    source_context_ids: Iterable[str] | None = None,
    import_context: str | None = None,
) -> DuplicateMatch:
    """Classify bibliographic evidence in approved priority order."""
    candidate = _as_reference(candidate)
    existing = _as_reference(existing)

    if (
        _reference_exact_signature(candidate) == _reference_exact_signature(existing)
        and _has_exact_reference_identity(candidate)
        and _has_exact_reference_identity(existing)
    ):
        return DuplicateMatch(
            entity_id=existing.reference_id,
            classification=DuplicateClassification.EXACT,
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.EXACT,
                    explanation="All normalized bibliographic identity fields are equal.",
                )
            ],
        )

    candidate_doi = normalize_doi(candidate.doi)
    existing_doi = normalize_doi(existing.doi)
    if candidate_doi and candidate_doi == existing_doi:
        return DuplicateMatch(
            entity_id=existing.reference_id,
            classification=DuplicateClassification.STRONG,
            evidence=[
                DuplicateEvidence(evidence_type=DuplicateEvidenceType.DOI, value=candidate_doi)
            ],
            warnings=[
                "Matching DOI is strong evidence, but contradictory metadata still requires review."
            ],
        )

    candidate_isbns = set(candidate.fingerprints.isbn_normalized)
    existing_isbns = set(existing.fingerprints.isbn_normalized)
    shared_isbns = sorted(candidate_isbns & existing_isbns)
    if shared_isbns:
        return DuplicateMatch(
            entity_id=existing.reference_id,
            classification=DuplicateClassification.STRONG,
            evidence=[
                DuplicateEvidence(evidence_type=DuplicateEvidenceType.ISBN, value=shared_isbns[0])
            ],
            warnings=[
                "Matching valid ISBN is strong evidence, not permission to merge editions automatically."
            ],
        )

    candidate_key = normalize_bibtex_key(candidate.bibtex.key)
    existing_key = normalize_bibtex_key(existing.bibtex.key)
    if candidate_key and candidate_key == existing_key:
        contextual = _shared_context(candidate, existing, source_context_ids, import_context)
        return DuplicateMatch(
            entity_id=existing.reference_id,
            classification=(
                DuplicateClassification.POSSIBLE if contextual else DuplicateClassification.WEAK
            ),
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.BIBTEX_KEY,
                    value=candidate_key,
                    contextual=contextual,
                    explanation=(
                        "BibTeX key matches within a Source/import context."
                        if contextual
                        else "BibTeX key matches without a shared Source/import context."
                    ),
                )
            ],
            warnings=["BibTeX keys are not globally unique and cannot trigger an automatic merge."],
        )

    candidate_fingerprint = candidate.fingerprints.author_title_year
    existing_fingerprint = existing.fingerprints.author_title_year
    if candidate_fingerprint and candidate_fingerprint == existing_fingerprint:
        return DuplicateMatch(
            entity_id=existing.reference_id,
            classification=DuplicateClassification.POSSIBLE,
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.AUTHOR_TITLE_YEAR,
                    value=candidate_fingerprint,
                )
            ],
            warnings=["Author/title/year equality requires human review."],
        )

    candidate_url = normalize_url(candidate.url)
    existing_url = normalize_url(existing.url)
    if candidate_url and candidate_url == existing_url:
        return DuplicateMatch(
            entity_id=existing.reference_id,
            classification=DuplicateClassification.WEAK,
            evidence=[
                DuplicateEvidence(evidence_type=DuplicateEvidenceType.URL, value=candidate_url)
            ],
            warnings=["The same URL can describe different versions or resources."],
        )

    candidate_title = suggestion_key(candidate.title)
    existing_title = suggestion_key(existing.title)
    candidate_authors = {
        suggestion_key(normalize_author(author.model_dump(mode="python")))
        for author in candidate.authors
    }
    existing_authors = {
        suggestion_key(normalize_author(author.model_dump(mode="python")))
        for author in existing.authors
    }
    candidate_authors.discard("")
    existing_authors.discard("")
    shared_authors = sorted(candidate_authors & existing_authors)
    title_matches = bool(candidate_title and candidate_title == existing_title)
    if title_matches or shared_authors:
        value = candidate_title if title_matches else shared_authors[0]
        explanation = (
            "Accent/punctuation-insensitive title similarity."
            if title_matches
            else "Accent/punctuation-insensitive author similarity."
        )
        return DuplicateMatch(
            entity_id=existing.reference_id,
            classification=DuplicateClassification.WEAK,
            evidence=[
                DuplicateEvidence(
                    evidence_type=DuplicateEvidenceType.SUGGESTION,
                    value=value,
                    explanation=explanation,
                )
            ],
            warnings=["Similarity is only a warning; no record was fused or changed."],
        )

    return DuplicateMatch(
        entity_id=existing.reference_id, classification=DuplicateClassification.NONE
    )


_CLASSIFICATION_RANK = {
    DuplicateClassification.EXACT: 0,
    DuplicateClassification.STRONG: 1,
    DuplicateClassification.POSSIBLE: 2,
    DuplicateClassification.WEAK: 3,
    DuplicateClassification.NONE: 4,
}


def find_source_duplicates(
    candidate: Source | Mapping[str, Any],
    existing_sources: Iterable[Source | Mapping[str, Any]],
    *,
    include_none: bool = False,
) -> list[DuplicateMatch]:
    """Return deterministically ordered Source duplicate diagnostics."""
    matches = [classify_source_duplicate(candidate, existing) for existing in existing_sources]
    if not include_none:
        matches = [match for match in matches if match.is_candidate]
    return sorted(
        matches, key=lambda match: (_CLASSIFICATION_RANK[match.classification], match.entity_id)
    )


def find_reference_duplicates(
    candidate: Reference | Mapping[str, Any],
    existing_references: Iterable[Reference | Mapping[str, Any]],
    *,
    source_context_ids: Iterable[str] | None = None,
    import_context: str | None = None,
    include_none: bool = False,
) -> list[DuplicateMatch]:
    """Return deterministically ordered Reference duplicate diagnostics."""
    matches = [
        classify_reference_duplicate(
            candidate,
            existing,
            source_context_ids=source_context_ids,
            import_context=import_context,
        )
        for existing in existing_references
    ]
    if not include_none:
        matches = [match for match in matches if match.is_candidate]
    return sorted(
        matches, key=lambda match: (_CLASSIFICATION_RANK[match.classification], match.entity_id)
    )


__all__ = [
    "DuplicateCandidate",
    "DuplicateClassification",
    "DuplicateEvidence",
    "DuplicateEvidenceType",
    "DuplicateMatch",
    "classify_reference_duplicate",
    "classify_source_duplicate",
    "find_reference_duplicates",
    "find_source_duplicates",
]

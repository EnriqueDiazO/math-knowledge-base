"""Tests for Source catalog domain contracts and pure migration helpers."""

# ruff: noqa: D103

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import pytest
from pydantic import ValidationError

from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateEvidenceType
from mathmongo.source_catalog.duplicates import classify_reference_duplicate
from mathmongo.source_catalog.duplicates import classify_source_duplicate
from mathmongo.source_catalog.legacy import extract_legacy_source_string
from mathmongo.source_catalog.legacy import preview_legacy_concept
from mathmongo.source_catalog.legacy import preview_legacy_reference
from mathmongo.source_catalog.models import BibTeXData
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import ReferenceStatus
from mathmongo.source_catalog.models import ReferenceType
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.models import SourceType
from mathmongo.source_catalog.normalization import author_title_year_fingerprint
from mathmongo.source_catalog.normalization import is_valid_isbn
from mathmongo.source_catalog.normalization import normalize_bibtex_key
from mathmongo.source_catalog.normalization import normalize_doi
from mathmongo.source_catalog.normalization import normalize_isbn
from mathmongo.source_catalog.normalization import normalize_source_name
from mathmongo.source_catalog.normalization import normalize_url
from mathmongo.source_catalog.normalization import suggestion_key

ID_RE = re.compile(
    r"^(src|ref)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def later(model: Source | Reference) -> datetime:
    return model.updated_at + timedelta(seconds=1)


def test_source_generates_prefixed_uuid4_and_aware_timestamps() -> None:
    source = Source(name="Analysis", source_type=SourceType.BOOK)

    assert ID_RE.fullmatch(source.source_id)
    assert source.source_id.startswith("src_")
    assert source.created_at.tzinfo is timezone.utc
    assert source.updated_at.tzinfo is timezone.utc
    assert source.status == SourceStatus.ACTIVE


def test_source_normalizes_unicode_whitespace_and_casefold() -> None:
    source = Source(name="  Ｃafe\u0301\t  MÉTODOS  ")

    assert source.name == "Café MÉTODOS"
    assert source.name_normalized == "café métodos"
    assert normalize_source_name(" STRASSE ") == "strasse"
    assert normalize_source_name("Straße") == "strasse"


def test_source_aliases_are_normalized_deduplicated_and_exclude_name() -> None:
    source = Source(
        name="Álgebra Lineal",
        aliases=[" Algebra   Lineal ", "Linear Algebra", "linear algebra", {"value": "Matrices"}],
    )

    assert [(alias.value, alias.normalized) for alias in source.aliases] == [
        ("Algebra Lineal", "algebra lineal"),
        ("Linear Algebra", "linear algebra"),
        ("Matrices", "matrices"),
    ]


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_source_rejects_empty_name(name: str) -> None:
    with pytest.raises(ValidationError, match="name cannot be empty"):
        Source(name=name)


def test_source_id_is_immutable_on_assignment() -> None:
    source = Source(name="Topology")

    with pytest.raises(ValidationError):
        source.source_id = Source(name="Other").source_id


def test_source_rename_preserves_id_and_optionally_adds_previous_alias() -> None:
    source = Source(name="Old Name", aliases=["Existing"])
    renamed = source.renamed("New Name", keep_previous_as_alias=True, at=later(source))

    assert renamed.source_id == source.source_id
    assert renamed.name == "New Name"
    assert [alias.value for alias in renamed.aliases] == ["Existing", "Old Name"]
    assert source.name == "Old Name"


def test_source_archive_and_reactivate_are_pure_and_keep_id() -> None:
    source = Source(name="Archived Source")
    archived = source.archived(at=later(source))
    reactivated = archived.reactivated(at=later(archived))

    assert archived.source_id == source.source_id
    assert archived.status == SourceStatus.ARCHIVED
    assert archived.archived_at == archived.updated_at
    assert reactivated.source_id == source.source_id
    assert reactivated.status == SourceStatus.ACTIVE
    assert reactivated.archived_at is None
    assert source.status == SourceStatus.ACTIVE


def test_domain_models_reject_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Source(name="Naive", created_at=datetime.now(), updated_at=datetime.now())

    with pytest.raises(ValidationError, match="timezone-aware"):
        Reference(doi="10.1/test", created_at=datetime.now(), updated_at=datetime.now())


def test_reference_generates_prefixed_uuid4_and_accepts_structured_and_literal_authors() -> None:
    reference = Reference(
        reference_type=ReferenceType.ARTICLE,
        authors=[{"family": "Noether", "given": "Emmy"}, "The Bourbaki Group"],
        title="Ideal Theory",
    )

    assert ID_RE.fullmatch(reference.reference_id)
    assert reference.reference_id.startswith("ref_")
    assert reference.authors[0].family == "Noether"
    assert reference.authors[0].given == "Emmy"
    assert reference.authors[1].literal == "The Bourbaki Group"


def test_doi_is_preserved_and_normalized_and_can_be_only_identity() -> None:
    original = " HTTPS://doi.org/10.1000/ABC.Def "
    reference = Reference(doi=original)

    assert reference.doi == original
    assert reference.doi_normalized == "10.1000/abc.def"
    assert normalize_doi("doi:10.1000/ABC.Def") == reference.doi_normalized
    assert normalize_doi("http://dx.doi.org/10.1000/ABC.Def") == reference.doi_normalized


def test_isbn10_and_isbn13_normalization_and_checksum() -> None:
    assert normalize_isbn("ISBN-10: 0-306-40615-2") == "0306406152"
    assert normalize_isbn("978-0-306-40615-7") == "9780306406157"
    assert is_valid_isbn("0-306-40615-2")
    assert is_valid_isbn("978-0-306-40615-7")
    assert not is_valid_isbn("978-0-306-40615-8")

    reference = Reference(isbn=["0-306-40615-2", "978-0-306-40615-7"])
    assert reference.fingerprints.isbn_normalized == ["0306406152", "9780306406157"]
    assert reference.status == ReferenceStatus.ACTIVE


def test_invalid_legacy_isbn_is_retained_and_marked_for_review() -> None:
    reference = Reference(isbn=["ISSBN legacy ???"])

    assert reference.isbn == ["ISSBN legacy ???"]
    assert reference.fingerprints.isbn_normalized == []
    assert reference.status == ReferenceStatus.NEEDS_REVIEW
    assert any("Invalid legacy ISBN" in warning for warning in reference.provenance.warnings)


def test_correcting_invalid_isbn_removes_generated_warning_and_review_status() -> None:
    reference = Reference(title="Correctable", isbn=["bad isbn"])
    data = reference.model_dump(mode="python")
    data["isbn"] = ["978-0-306-40615-7"]

    corrected = Reference.model_validate(data)

    assert corrected.status == ReferenceStatus.ACTIVE
    assert corrected.fingerprints.isbn_normalized == ["9780306406157"]
    assert not any(
        warning.startswith("Invalid legacy ISBN retained for review:")
        for warning in corrected.provenance.warnings
    )


def test_bibtex_key_raw_and_sha_are_preserved_and_normalized() -> None:
    raw = "@article{Müller2020, title={Über Algebra}}"
    reference = Reference(
        bibtex={
            "key": "Müller2020",
            "entry_type": "ARTICLE",
            "raw": raw,
            "extra": {"school": "ETH"},
        }
    )

    assert reference.bibtex.key == "Müller2020"
    assert reference.bibtex.key_normalized == "müller2020"
    assert reference.bibtex.entry_type == "article"
    assert reference.bibtex.raw == raw
    assert reference.bibtex.raw_sha256 == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert reference.bibtex.extra == {"school": "ETH"}
    assert normalize_bibtex_key(reference.bibtex.key) == "müller2020"


def test_bibtex_rejects_a_mismatched_raw_hash() -> None:
    with pytest.raises(ValidationError, match="raw_sha256 does not match"):
        BibTeXData(key="x", raw="entry", raw_sha256="0" * 64)


def test_reference_source_association_is_unique_and_pure() -> None:
    first = Source(name="First")
    second = Source(name="Second")
    reference = Reference(title="Shared reference", source_ids=[first.source_id, first.source_id])

    assert reference.source_ids == [first.source_id]
    associated = reference.associated_with(second.source_id, at=later(reference))
    unchanged = associated.associated_with(second.source_id)
    disassociated = associated.disassociated_from(first.source_id, at=later(associated))

    assert associated.source_ids == [first.source_id, second.source_id]
    assert unchanged is associated
    assert disassociated.source_ids == [second.source_id]
    assert reference.source_ids == [first.source_id]


def test_reference_archive_and_reactivate_preserve_needs_review() -> None:
    reference = Reference(isbn=["bad isbn"])
    archived = reference.archived(at=later(reference))
    reactivated = archived.reactivated(at=later(archived))

    assert archived.status == ReferenceStatus.ARCHIVED
    assert archived.archived_at == archived.updated_at
    assert reactivated.status == ReferenceStatus.NEEDS_REVIEW
    assert reactivated.archived_at is None
    assert reactivated.reference_id == reference.reference_id


def test_reference_requires_at_least_one_bibliographic_identity_signal() -> None:
    with pytest.raises(
        ValidationError, match="requires title, authors, DOI, ISBN, URL, or a BibTeX key"
    ):
        Reference()


def test_normalization_url_fingerprint_and_suggestion_are_deterministic() -> None:
    assert normalize_url("HTTPS://Example.COM:443/path?q=1") == "https://example.com/path?q=1"
    assert suggestion_key("  Théorie—des Groupes! ") == "theorie des groupes"
    first = author_title_year_fingerprint([{"family": "Noether", "given": "Emmy"}], "Ideals", 1921)
    second = author_title_year_fingerprint(
        [{"family": "Noether", "given": "Emmy"}], "Ideals", "1921"
    )
    assert first == second
    assert first is not None and len(first) == 64


def test_source_duplicate_classification_distinguishes_strong_and_weak() -> None:
    strong = classify_source_duplicate(
        Source(name="Linear  Algebra"), Source(name="linear algebra", description="Other")
    )
    weak = classify_source_duplicate(
        Source(name="Teoría-de Grupos"), Source(name="Teoria de Grupos", description="Other")
    )

    assert strong.classification == DuplicateClassification.STRONG
    assert strong.evidence[0].evidence_type == DuplicateEvidenceType.SOURCE_NAME
    assert weak.classification == DuplicateClassification.WEAK
    assert weak.evidence[0].evidence_type == DuplicateEvidenceType.SUGGESTION


def test_reference_duplicate_classifies_doi_and_valid_isbn_as_strong() -> None:
    doi_match = classify_reference_duplicate(
        Reference(title="Candidate", doi="https://doi.org/10.1/ABC"),
        Reference(title="Existing", doi="doi:10.1/abc"),
    )
    isbn_match = classify_reference_duplicate(
        Reference(title="Candidate", isbn=["978-0-306-40615-7"]),
        Reference(title="Different edition", isbn=["9780306406157"]),
    )

    assert doi_match.classification == DuplicateClassification.STRONG
    assert doi_match.evidence[0].evidence_type == DuplicateEvidenceType.DOI
    assert isbn_match.classification == DuplicateClassification.STRONG
    assert isbn_match.evidence[0].evidence_type == DuplicateEvidenceType.ISBN


def test_reference_duplicate_bibtex_key_is_contextual_not_global() -> None:
    source = Source(name="Context")
    candidate = Reference(
        title="Candidate", bibtex={"key": "SameKey"}, source_ids=[source.source_id]
    )
    existing_contextual = Reference(
        title="Other", bibtex={"key": "samekey"}, source_ids=[source.source_id]
    )
    existing_global = Reference(title="Other", bibtex={"key": "samekey"})

    contextual = classify_reference_duplicate(candidate, existing_contextual)
    global_match = classify_reference_duplicate(candidate, existing_global)

    assert contextual.classification == DuplicateClassification.POSSIBLE
    assert contextual.evidence[0].contextual is True
    assert global_match.classification == DuplicateClassification.WEAK
    assert global_match.evidence[0].contextual is False


def test_reference_duplicate_citekey_only_is_never_exact_globally() -> None:
    candidate = Reference(bibtex={"key": "OnlyKey"})
    existing = Reference(bibtex={"key": "onlykey"})

    match = classify_reference_duplicate(candidate, existing)

    assert match.classification == DuplicateClassification.WEAK
    assert match.evidence[0].evidence_type == DuplicateEvidenceType.BIBTEX_KEY


def test_reference_duplicate_author_title_year_is_possible_not_automatic() -> None:
    candidate = Reference(authors=["Ada Lovelace"], title="Notes", year=1843, journal="A")
    existing = Reference(authors=["Ada Lovelace"], title="Notes", year=1843, journal="B")

    match = classify_reference_duplicate(candidate, existing)

    assert match.classification == DuplicateClassification.POSSIBLE
    assert match.evidence[0].evidence_type == DuplicateEvidenceType.AUTHOR_TITLE_YEAR
    assert match.warnings


def test_weak_reference_similarity_never_fuses() -> None:
    candidate = Reference(title="Théorie-des Groupes", year=2020)
    existing = Reference(title="Theorie des Groupes!", year=2020, publisher="Different")

    match = classify_reference_duplicate(candidate, existing)

    assert match.classification == DuplicateClassification.WEAK
    assert "no record was fused" in match.warnings[0]


@pytest.mark.parametrize(
    ("candidate", "existing"),
    [
        (Reference(title="Identity Only"), Reference(title="identity only")),
        (Reference(authors=["Sole Author"]), Reference(authors=["sole author"])),
    ],
)
def test_minimal_reference_identity_matches_are_weak_warnings(
    candidate: Reference,
    existing: Reference,
) -> None:
    match = classify_reference_duplicate(candidate, existing)

    assert match.classification == DuplicateClassification.WEAK
    assert match.evidence[0].evidence_type == DuplicateEvidenceType.SUGGESTION
    assert match.warnings


def test_legacy_preview_preserves_exact_source_and_separates_locator() -> None:
    concept = {
        "id": "def:legacy",
        "source": "  Legacy Source  ",
        "citekey": "LegacyExactKey",
        "referencia": {
            "tipo_referencia": "libro",
            "autor": "Literal Legacy Author",
            "fuente": "Legacy Book",
            "anio": "1999a",
            "issbn": "invalid historical isbn",
            "paginas": "10-12",
            "capitulo": "3",
            "seccion": "2.1",
            "custom_historical": {"keep": True},
        },
    }
    original = concept["referencia"].copy()

    preview = preview_legacy_concept(concept)

    assert extract_legacy_source_string(concept) == "  Legacy Source  "
    assert preview.source.exact_value == "  Legacy Source  "
    assert preview.source.normalized == "legacy source"
    assert preview.reference.valid
    assert preview.reference.candidate is not None
    assert preview.reference.candidate.reference_type == ReferenceType.BOOK
    assert preview.reference.candidate.bibtex.key == "LegacyExactKey"
    assert preview.reference.candidate.year is None
    assert preview.reference.candidate.year_raw == "1999a"
    assert preview.reference.candidate.status == ReferenceStatus.NEEDS_REVIEW
    assert preview.reference.locator.pages == "10-12"
    assert preview.reference.locator.chapter == "3"
    assert preview.reference.locator.section == "2.1"
    assert preview.reference.unmapped_fields == {"custom_historical": {"keep": True}}
    assert concept["referencia"] == original


def test_legacy_free_text_reference_becomes_preview_without_writing() -> None:
    preview = preview_legacy_reference("Author, A Historical Free-Text Work, 1970")

    assert preview.valid
    assert preview.candidate is not None
    assert preview.candidate.title == "Author, A Historical Free-Text Work, 1970"
    assert preview.warnings


def test_empty_legacy_reference_reports_error_instead_of_raising_or_writing() -> None:
    preview = preview_legacy_reference({})

    assert preview.candidate is None
    assert preview.errors
    assert preview.original_reference == {}

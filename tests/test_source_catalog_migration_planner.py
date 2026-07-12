"""Focused contracts for the read-only S1C1 Source Catalog planner."""

# ruff: noqa: D103

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any

import pytest

from mathmongo.source_catalog_migration.inventory import InventoryError
from mathmongo.source_catalog_migration.inventory import build_inventory
from mathmongo.source_catalog_migration.models import InputSnapshot
from mathmongo.source_catalog_migration.models import ReviewStatus
from mathmongo.source_catalog_migration.models import ZipSafetyReport
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_EXPECTATIONS
from mathmongo.source_catalog_migration.planner import SnapshotExpectations
from mathmongo.source_catalog_migration.planner import build_plan
from mathmongo.source_catalog_migration.planner import semantic_plan_payload
from mathmongo.source_catalog_migration.reference_planner import build_reference_observations
from mathmongo.source_catalog_migration.source_planner import plan_source_keys
from mathmongo.source_catalog_migration.zip_reader import FileIdentity
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export

FIXED_TIME = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
REAL_ZIP = Path(__file__).resolve().parents[1] / "mathkb_export_20260712_073927.zip"
REAL_ZIP_SHA256 = "9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8"
_MISSING = object()
_FINAL_DOMAIN_ID_RE = re.compile(
    r"\b(?:src|ref)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


def _concept(
    concept_id: str,
    source: str,
    reference: Any = _MISSING,
    *,
    citekey: Any = _MISSING,
) -> dict[str, Any]:
    document: dict[str, Any] = {"id": concept_id, "source": source}
    if reference is not _MISSING:
        document["referencia"] = deepcopy(reference)
    if citekey is not _MISSING:
        document["citekey"] = deepcopy(citekey)
    return document


def _book_reference(**changes: Any) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "tipo_referencia": "libro",
        "autor": "Ada Author",
        "fuente": "A Deterministic Treatise",
        "anio": 2024,
    }
    reference.update(changes)
    return reference


def _loaded_export(
    concepts: list[dict[str, Any]],
    *,
    extra_collections: dict[str, list[dict[str, Any]]] | None = None,
    database_name: str = "Synthetic",
) -> LoadedLegacyExport:
    collections: dict[str, tuple[dict[str, Any], ...]] = {"concepts": tuple(deepcopy(concepts))}
    for name, documents in (extra_collections or {}).items():
        collections[name] = tuple(deepcopy(documents))
    counts = {name: len(documents) for name, documents in collections.items()}
    digest = "a" * 64
    snapshot = InputSnapshot(
        filename="synthetic.zip",
        sha256=digest,
        size_bytes=1,
        modified_at=FIXED_TIME,
        exported_at=FIXED_TIME,
        database_name=database_name,
        counts=counts,
        format_name="synthetic_legacy_export",
        format_version="unversioned",
        format_version_source="test_fixture",
        members=(),
    )
    safety = ZipSafetyReport(
        validated=True,
        member_count=0,
        file_count=0,
        total_uncompressed_bytes=0,
        total_compressed_bytes=0,
        maximum_compression_ratio=0.0,
        base_directory="synthetic",
    )
    identity = FileIdentity(
        device=1,
        inode=1,
        size_bytes=1,
        modified_ns=1,
        sha256=digest,
    )
    return LoadedLegacyExport(
        input_snapshot=snapshot,
        zip_safety=safety,
        metadata={"collections": counts, "media_files": {}},
        collections=collections,
        member_sha256={},
        input_identity=identity,
    )


def _plan(
    concepts: list[dict[str, Any]],
    *,
    generated_at: datetime = FIXED_TIME,
):
    return build_plan(
        _loaded_export(concepts),
        expectations=SnapshotExpectations(),
        generated_at=generated_at,
    )


def _binding(plan, concept_id: str, source: str = "Source"):
    return next(
        item
        for item in plan.concept_bindings
        if item.legacy_key.id == concept_id and item.legacy_key.source == source
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_sources_preserve_exact_strings_counts_and_never_merge_similar_names() -> None:
    plan = _plan(
        [
            _concept("one", "Alpha"),
            _concept("two", "Alpha"),
            _concept("three", "alpha"),
            _concept("four", "Alpha-Book"),
            _concept("five", "Alpha_Book"),
            _concept("six", "  Alpha  "),
        ]
    )

    by_exact = {item.exact_string: item for item in plan.source_candidates}

    assert set(by_exact) == {
        "Alpha",
        "alpha",
        "Alpha-Book",
        "Alpha_Book",
        "  Alpha  ",
    }
    assert by_exact["Alpha"].concept_count == 2
    assert by_exact["Alpha"].legacy_source_strings == ("Alpha",)
    assert by_exact["  Alpha  "].suggested_display_name == "  Alpha  "
    assert by_exact["  Alpha  "].normalized_string == "alpha"
    assert by_exact["Alpha"].source_candidate_key != by_exact["alpha"].source_candidate_key
    assert (
        by_exact["Alpha-Book"].source_candidate_key != by_exact["Alpha_Book"].source_candidate_key
    )
    assert by_exact["Alpha"].review_status == ReviewStatus.REVIEW_REQUIRED
    assert by_exact["alpha"].review_status == ReviewStatus.REVIEW_REQUIRED
    assert by_exact["  Alpha  "].review_status == ReviewStatus.REVIEW_REQUIRED


def test_source_and_plan_keys_are_deterministic_under_input_reordering() -> None:
    concepts = [
        _concept("b", "Second", _book_reference(paginas="9")),
        _concept("a", "First", _book_reference(paginas="1")),
    ]

    first = _plan(concepts, generated_at=FIXED_TIME)
    second = _plan(
        list(reversed(concepts)),
        generated_at=FIXED_TIME + timedelta(hours=1),
    )

    assert {item.exact_string: item.source_candidate_key for item in first.source_candidates} == {
        item.exact_string: item.source_candidate_key for item in second.source_candidates
    }
    assert [item.binding_candidate_key for item in first.concept_bindings] == [
        item.binding_candidate_key for item in second.concept_bindings
    ]
    assert first.semantic_sha256 == second.semantic_sha256
    assert semantic_plan_payload(first) == semantic_plan_payload(second)


def test_matching_valid_doi_with_compatible_metadata_forms_one_strong_candidate() -> None:
    doi = "10.1234/compatible"
    plan = _plan(
        [
            _concept("one", "Source", _book_reference(doi=f"https://doi.org/{doi}")),
            _concept(
                "two",
                "Source",
                _book_reference(doi=f"DOI: {doi.upper()}", editorial="Press"),
            ),
        ]
    )

    assert plan.summary.reference_candidate_count == 1
    candidate = plan.reference_candidates[0]
    assert candidate.normalized_doi == doi
    assert candidate.concept_count == 2
    assert candidate.classification == ReviewStatus.SAFE_STRONG
    assert "doi" in candidate.grouping_rules
    assert not plan.conflicts


def test_matching_doi_with_contradictory_metadata_stays_separate_and_conflicted() -> None:
    doi = "10.1234/conflict"
    plan = _plan(
        [
            _concept("one", "Source", _book_reference(doi=doi, fuente="First Work")),
            _concept("two", "Source", _book_reference(doi=doi, fuente="Second Work")),
        ]
    )

    assert plan.summary.reference_candidate_count == 2
    assert len(plan.conflicts) == 1
    conflict = plan.conflicts[0]
    assert conflict.conflict_type == "doi_metadata_conflict"
    assert conflict.normalized_doi == doi
    assert "title" in conflict.contradictory_fields
    assert len(conflict.reference_candidate_keys) == 2
    assert {item.classification for item in plan.reference_candidates} == {
        ReviewStatus.METADATA_CONFLICT
    }
    assert (
        _binding(plan, "one").reference_candidate_key
        != _binding(plan, "two").reference_candidate_key
    )


def test_matching_doi_with_contradictory_language_stays_separate() -> None:
    doi = "10.1234/language-conflict"
    plan = _plan(
        [
            _concept("one", "Source", _book_reference(doi=doi, idioma="es")),
            _concept("two", "Source", _book_reference(doi=doi, idioma="en")),
        ]
    )

    assert plan.summary.reference_candidate_count == 2
    assert len(plan.conflicts) == 1
    assert "language" in plan.conflicts[0].contradictory_fields
    assert {candidate.classification for candidate in plan.reference_candidates} == {
        ReviewStatus.METADATA_CONFLICT
    }


def test_unknown_reference_types_are_preserved_and_never_collapsed() -> None:
    plan = _plan(
        [
            _concept(
                "one",
                "Source",
                _book_reference(tipo_referencia="video"),
            ),
            _concept(
                "two",
                "Source",
                _book_reference(tipo_referencia="podcast"),
            ),
        ]
    )

    assert plan.summary.reference_candidate_count == 2
    assert len(plan.conflicts) == 1
    assert "unknown_reference_type" in plan.conflicts[0].contradictory_fields
    assert all(
        "unknown_reference_type" in candidate.normalized_bibliography
        for candidate in plan.reference_candidates
    )
    assert {
        candidate.proposed_bibliography["reference_type"] for candidate in plan.reference_candidates
    } == {"other"}


def test_conflicting_bibliography_aliases_are_raw_preserved_and_reviewed() -> None:
    plan = _plan(
        [
            _concept(
                "one",
                "Source",
                _book_reference(titulo="First title", fuente="Second title"),
            )
        ]
    )

    candidate = plan.reference_candidates[0]
    binding = _binding(plan, "one")
    assert candidate.classification == ReviewStatus.REVIEW_REQUIRED
    assert binding.review_status == ReviewStatus.REVIEW_REQUIRED
    assert candidate.raw_variants[0]["titulo"] == "First title"
    assert candidate.raw_variants[0]["fuente"] == "Second title"
    assert "title" in candidate.contradictory_fields
    assert "bibliography_title_alias_conflict" in candidate.warnings
    assert "bibliography_title_alias_conflict" in {item.problem_type for item in plan.review_items}


def test_valid_isbn_is_normalized_and_groups_compatible_raw_spellings() -> None:
    plan = _plan(
        [
            _concept("one", "Source", _book_reference(issbn="978-0-306-40615-7")),
            _concept("two", "Source", _book_reference(isbn="9780306406157")),
        ]
    )

    candidate = plan.reference_candidates[0]
    assert plan.summary.reference_candidate_count == 1
    assert candidate.normalized_isbns == ("9780306406157",)
    assert candidate.raw_variant_count == 2
    assert "isbn" in candidate.grouping_rules
    assert "invalid_legacy_isbn" not in candidate.warnings


def test_invalid_legacy_issbn_is_preserved_and_requires_review() -> None:
    raw_isbn = "legacy partial ISBN"
    plan = _plan([_concept("one", "Source", _book_reference(issbn=raw_isbn))])

    candidate = plan.reference_candidates[0]
    assert candidate.normalized_isbns == ()
    assert candidate.proposed_bibliography["isbn"] == [raw_isbn]
    assert candidate.raw_variants[0]["issbn"] == raw_isbn
    assert "invalid_legacy_isbn" in candidate.warnings
    assert candidate.classification == ReviewStatus.REVIEW_REQUIRED
    assert "invalid_legacy_isbn" in {item.problem_type for item in plan.review_items}


def test_contextual_citekey_groups_compatible_variants_but_requires_review() -> None:
    plan = _plan(
        [
            _concept(
                "one",
                "Source",
                _book_reference(citekey="SharedKey"),
            ),
            _concept(
                "two",
                "Source",
                _book_reference(editorial="Press"),
                citekey="sharedkey",
            ),
        ]
    )

    candidate = plan.reference_candidates[0]
    assert plan.summary.reference_candidate_count == 1
    assert candidate.normalized_citekeys == ("sharedkey",)
    assert candidate.classification == ReviewStatus.REVIEW_REQUIRED
    assert "citekey" in candidate.grouping_rules
    assert "review_required" in {item.problem_type for item in plan.review_items}


def test_conflicting_top_level_and_embedded_citekeys_require_review() -> None:
    plan = _plan(
        [
            _concept(
                "one",
                "Source",
                _book_reference(citekey="EmbeddedKey"),
                citekey="TopLevelKey",
            )
        ]
    )

    candidate = plan.reference_candidates[0]
    binding = _binding(plan, "one")
    review = next(
        item for item in plan.review_items if item.problem_type == "citekey_metadata_conflict"
    )
    assert candidate.classification == ReviewStatus.REVIEW_REQUIRED
    assert binding.review_status == ReviewStatus.REVIEW_REQUIRED
    assert candidate.normalized_citekeys == ("embeddedkey", "toplevelkey")
    assert candidate.raw_variants[0]["citekey"] == "EmbeddedKey"
    assert candidate.raw_variants[0]["legacy_concept_citekey"] == "TopLevelKey"
    assert candidate.contradictory_fields == ("citekey",)
    assert review.contradictory_fields == ("citekey",)


def test_citekey_only_is_not_global_identity_and_remains_separate() -> None:
    plan = _plan(
        [
            _concept("one", "First Source", {"citekey": "Shared"}),
            _concept("two", "Second Source", {"citekey": "shared"}),
        ]
    )

    assert plan.summary.reference_candidate_count == 2
    assert {candidate.classification for candidate in plan.reference_candidates} == {
        ReviewStatus.INSUFFICIENT_IDENTITY
    }
    assert (
        _binding(plan, "one", "First Source").reference_candidate_key
        != _binding(
            plan,
            "two",
            "Second Source",
        ).reference_candidate_key
    )


def test_matching_citekey_with_incompatible_metadata_is_a_conflict() -> None:
    plan = _plan(
        [
            _concept(
                "one",
                "Source",
                _book_reference(citekey="SharedKey", fuente="First Work"),
            ),
            _concept(
                "two",
                "Source",
                _book_reference(citekey="sharedkey", fuente="Second Work"),
            ),
        ]
    )

    assert plan.summary.reference_candidate_count == 2
    assert len(plan.conflicts) == 1
    conflict = plan.conflicts[0]
    assert conflict.conflict_type == "citekey_metadata_conflict"
    assert conflict.normalized_citekeys == ("sharedkey",)
    assert "title" in conflict.contradictory_fields
    assert all(
        "title" in item.contradictory_fields
        for item in plan.review_items
        if item.problem_type == "metadata_conflict"
    )


def test_exact_author_title_year_groups_compatible_variants_for_review() -> None:
    plan = _plan(
        [
            _concept("one", "Source", _book_reference()),
            _concept("two", "Source", _book_reference(editorial="Press")),
        ]
    )

    candidate = plan.reference_candidates[0]
    assert plan.summary.reference_candidate_count == 1
    assert candidate.concept_count == 2
    assert candidate.classification == ReviewStatus.REVIEW_REQUIRED
    assert "author_title_year" in candidate.grouping_rules


def test_weak_title_similarity_is_reported_without_merging_candidates() -> None:
    plan = _plan(
        [
            _concept(
                "one",
                "Source",
                {"autor": "First Author", "fuente": "Shared title", "anio": 2000},
            ),
            _concept(
                "two",
                "Source",
                {"autor": "Second Author", "fuente": "Shared title", "anio": 2001},
            ),
        ]
    )

    assert plan.summary.reference_candidate_count == 2
    assert plan.summary.weak_suggestion_count == 1
    suggestion = plan.weak_reference_suggestions[0]
    assert suggestion.reason == "weak_title_similarity"
    assert len(suggestion.reference_candidate_keys) == 2
    assert suggestion.concept_count == 2
    assert (
        _binding(plan, "one").reference_candidate_key
        != _binding(
            plan,
            "two",
        ).reference_candidate_key
    )


def test_insufficient_identity_remains_one_candidate_per_concept() -> None:
    plan = _plan(
        [
            _concept("one", "Source", {"fuente": "Title only"}),
            _concept("two", "Source", {"fuente": "Title only"}),
        ]
    )

    assert plan.summary.reference_candidate_count == 2
    assert {candidate.classification for candidate in plan.reference_candidates} == {
        ReviewStatus.INSUFFICIENT_IDENTITY
    }
    assert all(candidate.concept_count == 1 for candidate in plan.reference_candidates)
    assert (
        _binding(plan, "one").reference_candidate_key
        != _binding(plan, "two").reference_candidate_key
    )


def test_one_reference_candidate_can_be_shared_across_sources_without_merging_concepts() -> None:
    reference = _book_reference(doi="10.1234/shared", paginas="42")
    plan = _plan(
        [
            _concept("one", "First Source", reference),
            _concept("two", "Second Source", reference),
        ]
    )

    candidate = plan.reference_candidates[0]
    first_binding = _binding(plan, "one", "First Source")
    second_binding = _binding(plan, "two", "Second Source")

    assert plan.summary.reference_candidate_count == 1
    assert candidate.concept_count == 2
    assert len(candidate.source_candidate_keys) == 2
    assert first_binding.binding_candidate_key != second_binding.binding_candidate_key
    assert first_binding.reference_candidate_key == second_binding.reference_candidate_key
    assert first_binding.locator.pages_raw == second_binding.locator.pages_raw == "42"


def test_locator_is_excluded_while_raw_unknown_bibliography_is_preserved() -> None:
    first_reference = _book_reference(
        doi="10.1234/locator-free",
        paginas="10-12",
        capitulo="I",
        custom_historical={"preserve": True},
    )
    second_reference = {
        **first_reference,
        "paginas": "xxvii",
        "capitulo": None,
    }
    export = _loaded_export(
        [
            _concept("one", "Source", first_reference),
            _concept("two", "Source", second_reference),
        ]
    )
    inventory_plan = build_plan(
        export,
        expectations=SnapshotExpectations(),
        generated_at=FIXED_TIME,
    )
    candidate = inventory_plan.reference_candidates[0]

    assert inventory_plan.summary.reference_candidate_count == 1
    assert candidate.raw_variant_count == 1
    assert candidate.unknown_fields == ("custom_historical",)
    assert candidate.raw_variants[0]["custom_historical"] == {"preserve": True}
    assert "paginas" not in candidate.raw_variants[0]
    assert "capitulo" not in candidate.raw_variants[0]
    assert not {
        "paginas",
        "pages",
        "pagina",
        "capitulo",
        "chapter",
        "seccion",
        "section",
    } & set(candidate.normalized_bibliography)
    assert {locator.pages_raw for locator in candidate.locator_variants} == {
        "10-12",
        "xxvii",
    }

    inventory = build_inventory(export)
    source_keys = plan_source_keys(inventory)
    observations = build_reference_observations(inventory, source_keys)
    assert observations[0].bibliographic_fingerprint == observations[1].bibliographic_fingerprint
    assert observations[0].raw_reference["paginas"] == "10-12"
    assert observations[1].raw_reference["paginas"] == "xxvii"


def test_concurrent_locator_aliases_are_preserved_without_entering_fingerprint() -> None:
    plan = _plan(
        [
            _concept(
                "one",
                "Source",
                _book_reference(paginas="10", pages="11", capitulo=None, chapter="II"),
            )
        ]
    )

    binding = _binding(plan, "one")
    candidate = plan.reference_candidates[0]
    assert binding.locator.pages_raw == "10"
    assert binding.locator.chapter_raw == "II"
    assert binding.locator.raw_alias_values == {
        "capitulo": None,
        "chapter": "II",
        "pages": "11",
        "paginas": "10",
    }
    assert candidate.locator_variants[0].raw_alias_values == binding.locator.raw_alias_values
    assert "locator_pages_alias_conflict" in binding.flags
    assert not set(binding.locator.raw_alias_values) & set(candidate.normalized_bibliography)


def test_missing_reference_binding_is_explicit_and_has_no_reference_candidate() -> None:
    plan = _plan([_concept("missing", "Source")])
    binding = _binding(plan, "missing")

    assert plan.summary.embedded_reference_count == 0
    assert plan.summary.missing_reference_count == 1
    assert plan.summary.reference_candidate_count == 0
    assert binding.reference_candidate_key is None
    assert binding.review_status == ReviewStatus.MISSING_REFERENCE
    assert "missing_reference" in binding.flags


def test_whitespace_reference_uses_the_same_missing_partition_everywhere() -> None:
    plan = _plan([_concept("blank", "Source", "  \n\t ")])
    binding = _binding(plan, "blank")

    assert plan.summary.embedded_reference_count == 0
    assert plan.summary.missing_reference_count == 1
    assert plan.summary.reference_candidate_count == 0
    assert binding.reference_candidate_key is None
    assert binding.review_status == ReviewStatus.MISSING_REFERENCE
    assert "empty_reference" in binding.flags
    assert plan.invariants.reference_partition_matches


def test_na_ranges_and_roman_pages_are_preserved_as_binding_review_flags() -> None:
    plan = _plan(
        [
            _concept("na", "Source", _book_reference(paginas="N/A")),
            _concept("range", "Source", _book_reference(paginas="10-12")),
            _concept("roman", "Source", _book_reference(paginas="xxvii")),
        ]
    )

    expected = {
        "na": ("N/A", "locator_pages_na"),
        "range": ("10-12", "locator_pages_range"),
        "roman": ("xxvii", "locator_pages_roman"),
    }
    for concept_id, (raw_pages, flag) in expected.items():
        binding = _binding(plan, concept_id)
        assert binding.locator.pages_raw == raw_pages
        assert flag in binding.flags
        assert binding.review_status == ReviewStatus.REVIEW_REQUIRED

    assert {
        "locator_pages_na",
        "locator_pages_range",
        "locator_pages_roman",
    } <= {item.problem_type for item in plan.review_items}


def test_matching_reference_and_locator_never_fuses_concept_bindings() -> None:
    reference = _book_reference(doi="10.1234/same-page", paginas="7")
    plan = _plan(
        [
            _concept("one", "Source", reference),
            _concept("two", "Source", reference),
            _concept("three", "Source", reference),
        ]
    )

    assert plan.summary.reference_candidate_count == 1
    assert plan.summary.binding_count == 3
    assert len({item.binding_candidate_key for item in plan.concept_bindings}) == 3
    assert len({item.reference_candidate_key for item in plan.concept_bindings}) == 1
    assert [item.legacy_key.id for item in plan.concept_bindings] == [
        "one",
        "three",
        "two",
    ]


def test_plan_invariants_and_semantic_digest_are_deterministic_and_have_no_final_ids() -> None:
    concepts = [
        _concept("with", "Source", _book_reference(doi="10.1234/invariants")),
        _concept("without", "Source"),
    ]
    expectations = SnapshotExpectations(
        concept_count=2,
        source_count=1,
        with_reference=1,
        without_reference=1,
        collection_counts={"concepts": 2},
    )
    export = _loaded_export(concepts)
    first = build_plan(export, expectations=expectations, generated_at=FIXED_TIME)
    second = build_plan(
        export,
        expectations=expectations,
        generated_at=FIXED_TIME + timedelta(days=1),
    )

    assert first.invariants.passed
    assert first.invariants.unique_legacy_keys
    assert first.invariants.unique_binding_keys
    assert first.invariants.no_concepts_lost
    assert first.invariants.no_concepts_duplicated
    assert first.invariants.locators_excluded_from_bibliographic_fingerprints
    assert first.invariants.metadata_conflicts_not_merged
    assert first.invariants.no_final_domain_ids
    assert first.semantic_sha256 == second.semantic_sha256
    assert not _FINAL_DOMAIN_ID_RE.search(str(first.model_dump(mode="json")))


def test_duplicate_legacy_keys_fail_closed_before_bindings_are_planned() -> None:
    export = _loaded_export([_concept("same", "Source"), _concept("same", "Source")])

    with pytest.raises(InventoryError, match="Duplicate legacy concept key"):
        build_plan(export, expectations=SnapshotExpectations(), generated_at=FIXED_TIME)


@pytest.mark.skipif(not REAL_ZIP.is_file(), reason="authoritative user ZIP is not available")
def test_authoritative_zip_read_only_counts_and_semantic_determinism() -> None:
    before_stat = REAL_ZIP.stat()
    before_sha256 = _file_sha256(REAL_ZIP)

    export = read_legacy_export(REAL_ZIP, database_name="MathV0")
    first = build_plan(
        export,
        expectations=AUTHORITATIVE_EXPECTATIONS,
        generated_at=FIXED_TIME,
    )
    second = build_plan(
        export,
        expectations=AUTHORITATIVE_EXPECTATIONS,
        generated_at=FIXED_TIME + timedelta(minutes=1),
    )

    after_stat = REAL_ZIP.stat()
    after_sha256 = _file_sha256(REAL_ZIP)
    assert before_sha256 == after_sha256 == REAL_ZIP_SHA256
    assert (
        before_stat.st_dev,
        before_stat.st_ino,
        before_stat.st_size,
        before_stat.st_mtime_ns,
    ) == (
        after_stat.st_dev,
        after_stat.st_ino,
        after_stat.st_size,
        after_stat.st_mtime_ns,
    )
    assert export.input_snapshot.sha256 == REAL_ZIP_SHA256
    assert export.input_snapshot.format_version == "unversioned"
    assert first.summary.concept_count == 186
    assert first.summary.source_candidate_count == 16
    assert first.summary.embedded_reference_count == 145
    assert first.summary.missing_reference_count == 41
    assert first.summary.reference_candidate_count == 20
    assert first.summary.binding_count == 186
    assert first.summary.conflict_count == 0
    assert first.summary.review_item_count == 5
    assert first.summary.weak_suggestion_count == 2
    assert first.invariants.passed
    assert (
        len({(item.legacy_key.id, item.legacy_key.source) for item in first.concept_bindings})
        == 186
    )
    assert (
        sum(candidate.locator_statistics.variant_count for candidate in first.reference_candidates)
        == 48
    )
    assert {candidate.classification for candidate in first.reference_candidates} == {
        ReviewStatus.SAFE_EXACT
    }
    assert first.coupled_collections.concept_counterparts_in_latex_documents == 186
    assert first.coupled_collections.orphan_latex_documents == 1
    assert first.coupled_collections.relations == 136
    assert first.coupled_collections.knowledge_graph_maps == 2
    assert first.coupled_collections.media_assets == 10
    assert first.coupled_collections.latex_notes == 34
    assert first.semantic_sha256 == second.semantic_sha256
    assert semantic_plan_payload(first) == semantic_plan_payload(second)

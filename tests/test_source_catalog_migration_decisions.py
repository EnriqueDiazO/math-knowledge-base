"""Human-decision and safe-result contracts for the S1C2A bootstrap."""

# ruff: noqa: D103

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mathmongo.source_catalog_migration.apply_result import ApplyOutcome
from mathmongo.source_catalog_migration.apply_result import ApplyResult
from mathmongo.source_catalog_migration.apply_result import IndexApplyResult
from mathmongo.source_catalog_migration.apply_result import render_apply_result
from mathmongo.source_catalog_migration.decisions import DecisionFileError
from mathmongo.source_catalog_migration.decisions import DecisionSet
from mathmongo.source_catalog_migration.decisions import DecisionValidationError
from mathmongo.source_catalog_migration.decisions import build_decisions_template
from mathmongo.source_catalog_migration.decisions import decisions_json
from mathmongo.source_catalog_migration.decisions import decisions_sha256
from mathmongo.source_catalog_migration.decisions import load_decisions
from mathmongo.source_catalog_migration.decisions import validate_decisions
from mathmongo.source_catalog_migration.models import InputSnapshot
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.models import ReferenceCandidate
from mathmongo.source_catalog_migration.models import ReviewItem
from mathmongo.source_catalog_migration.models import ReviewStatus
from mathmongo.source_catalog_migration.models import WeakReferenceSuggestion

ZIP_SHA256 = "a" * 64
PLAN_SHA256 = "b" * 64
MIGRATION_ID = "mig_00000000-0000-4000-8000-000000000001"


def _reference(key: str, classification: ReviewStatus) -> ReferenceCandidate:
    return ReferenceCandidate.model_construct(
        reference_candidate_key=key,
        classification=classification,
        grouping_rules=("bibliographic_fingerprint",),
        concept_count=1,
        source_candidate_keys=("source_candidate_one",),
        legacy_keys=(),
        bibliographic_fingerprint="c" * 64,
        normalized_bibliography={"title": key},
        proposed_bibliography={"title": key},
        raw_variants=({},),
        raw_variant_count=1,
    )


def _plan(
    *,
    classifications: tuple[ReviewStatus, ...] = (
        ReviewStatus.SAFE_EXACT,
        ReviewStatus.SAFE_EXACT,
    ),
    non_locator_review: bool = False,
) -> MigrationPlan:
    references = tuple(
        _reference(f"reference_candidate_{index}", classification)
        for index, classification in enumerate(classifications, start=1)
    )
    weak = (
        WeakReferenceSuggestion(
            suggestion_key="weak_reference_suggestion_one",
            reference_candidate_keys=(
                references[0].reference_candidate_key,
                references[-1].reference_candidate_key,
            ),
            source_candidate_keys=("source_candidate_one",),
            concept_count=2,
            title_similarity_key="shared title",
        ),
    )
    reviews = (
        ReviewItem(
            review_key="review_one",
            candidate_key=references[0].reference_candidate_key,
            problem_type=("invalid_legacy_isbn" if non_locator_review else "locator_pages_range"),
            source_candidate_keys=("source_candidate_one",),
            concept_count=1,
        ),
    )
    snapshot = InputSnapshot.model_construct(sha256=ZIP_SHA256)
    return MigrationPlan.model_construct(
        input_snapshot=snapshot,
        semantic_sha256=PLAN_SHA256,
        reference_candidates=references,
        weak_reference_suggestions=weak,
        review_items=reviews,
    )


def _complete_decisions(plan: MigrationPlan, *, bulk: bool = True) -> DecisionSet:
    return DecisionSet(
        zip_sha256=ZIP_SHA256,
        plan_semantic_sha256=PLAN_SHA256,
        accept_all_safe_exact=bulk,
        accepted_reference_candidates=(
            ()
            if bulk
            else tuple(item.reference_candidate_key for item in plan.reference_candidates)
        ),
        weak_suggestion_decisions={
            item.suggestion_key: "keep_separate" for item in plan.weak_reference_suggestions
        },
        locator_review_decisions={item.review_key: "defer" for item in plan.review_items},
    )


def test_template_is_typed_but_deliberately_not_applicable() -> None:
    plan = _plan()

    template = build_decisions_template(plan)

    assert template.accept_all_safe_exact is None
    assert template.accepted_reference_candidates == ()
    assert template.weak_suggestion_decisions == {"weak_reference_suggestion_one": None}
    assert template.locator_review_decisions == {"review_one": None}
    assert '"accept_all_safe_exact": null' in decisions_json(template)
    with pytest.raises(DecisionValidationError, match="placeholder"):
        validate_decisions(template, plan)


@pytest.mark.parametrize("bulk", [True, False])
def test_complete_decisions_are_bound_to_exact_plan_and_cover_every_item(bulk: bool) -> None:
    plan = _plan()
    decisions = _complete_decisions(plan, bulk=bulk)

    validated = validate_decisions(
        decisions,
        plan,
        expected_zip_sha256=ZIP_SHA256,
        expected_plan_sha256=PLAN_SHA256,
    )

    assert validated.decisions_sha256 == decisions_sha256(decisions)
    assert validated.effective_reference_candidates == (
        "reference_candidate_1",
        "reference_candidate_2",
    )
    assert validated.weak_suggestion_keys == ("weak_reference_suggestion_one",)
    assert validated.locator_review_keys == ("review_one",)


def test_decisions_hash_is_independent_of_array_and_object_order() -> None:
    plan = _plan()
    first = _complete_decisions(plan, bulk=False)
    second = DecisionSet(
        zip_sha256=ZIP_SHA256,
        plan_semantic_sha256=PLAN_SHA256,
        accept_all_safe_exact=False,
        accepted_reference_candidates=tuple(reversed(first.accepted_reference_candidates)),
        weak_suggestion_decisions=dict(reversed(first.weak_suggestion_decisions.items())),
        locator_review_decisions=dict(reversed(first.locator_review_decisions.items())),
    )

    assert decisions_sha256(first) == decisions_sha256(second)
    assert decisions_json(first, pretty=False) == decisions_json(second, pretty=False)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"zip_sha256": "c" * 64}, "ZIP hash"),
        ({"plan_semantic_sha256": "c" * 64}, "plan hash"),
        ({"accepted_reference_candidates": ("reference_candidate_missing",)}, "Unknown"),
        ({"weak_suggestion_decisions": {}, "accept_all_safe_exact": True}, "Weak suggestion"),
        ({"locator_review_decisions": {}, "accept_all_safe_exact": True}, "Locator review"),
    ],
)
def test_hash_key_and_completeness_mismatches_fail_closed(
    change: dict[str, object],
    message: str,
) -> None:
    plan = _plan()
    payload = _complete_decisions(plan).model_dump(mode="python")
    payload.update(change)
    decisions = DecisionSet.model_validate(payload)

    with pytest.raises(DecisionValidationError, match=message):
        validate_decisions(decisions, plan)


def test_unknown_decision_values_and_duplicate_accepted_keys_are_schema_errors() -> None:
    plan = _plan()
    payload = _complete_decisions(plan).model_dump(mode="python")
    payload["weak_suggestion_decisions"] = {"weak_reference_suggestion_one": "merge"}
    with pytest.raises(ValidationError):
        DecisionSet.model_validate(payload)

    payload = _complete_decisions(plan, bulk=False).model_dump(mode="python")
    payload["accepted_reference_candidates"] = [
        "reference_candidate_1",
        "reference_candidate_1",
    ]
    with pytest.raises(ValidationError, match="duplicate"):
        DecisionSet.model_validate(payload)


def test_non_safe_reference_or_non_locator_review_has_no_silent_decision() -> None:
    unsafe_plan = _plan(classifications=(ReviewStatus.SAFE_EXACT, ReviewStatus.SAFE_STRONG))
    with pytest.raises(DecisionValidationError, match="non-safe-exact"):
        validate_decisions(_complete_decisions(unsafe_plan), unsafe_plan)

    non_locator_plan = _plan(non_locator_review=True)
    with pytest.raises(DecisionValidationError, match="non-locator"):
        validate_decisions(_complete_decisions(non_locator_plan), non_locator_plan)


def test_loader_reads_regular_bounded_utf8_json_without_reordering_semantics(
    tmp_path: Path,
) -> None:
    plan = _plan()
    decisions = _complete_decisions(plan, bulk=False)
    path = tmp_path / "decisions.json"
    path.write_text(decisions_json(decisions), encoding="utf-8")

    loaded = load_decisions(path)

    assert loaded == decisions
    assert validate_decisions(loaded, plan).decisions_sha256 == decisions_sha256(decisions)


def test_loader_rejects_symlinks_non_regular_oversized_and_duplicate_keys(
    tmp_path: Path,
) -> None:
    regular = tmp_path / "regular.json"
    regular.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(regular)
    with pytest.raises(DecisionFileError, match="Symbolic"):
        load_decisions(link)

    with pytest.raises(DecisionFileError, match="regular"):
        load_decisions(tmp_path)

    oversized = tmp_path / "oversized.json"
    oversized.write_text("x" * 33, encoding="utf-8")
    with pytest.raises(DecisionFileError, match="size limit"):
        load_decisions(oversized, max_bytes=32)

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":1,"schema_version":1}',
        encoding="utf-8",
    )
    with pytest.raises(DecisionFileError, match="UTF-8 JSON"):
        load_decisions(duplicate)


def test_loader_rejects_malformed_root_extra_fields_and_noncanonical_hash(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(DecisionFileError, match="root"):
        load_decisions(malformed)

    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "zip_sha256": ZIP_SHA256.upper(),
                "plan_semantic_sha256": PLAN_SHA256,
                "accept_all_safe_exact": True,
                "accepted_reference_candidates": [],
                "weak_suggestion_decisions": {},
                "locator_review_decisions": {},
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DecisionFileError, match="schema version 1"):
        load_decisions(invalid)


def _apply_result(outcome: ApplyOutcome = ApplyOutcome.APPLIED, **changes: object) -> ApplyResult:
    payload: dict[str, object] = {
        "outcome": outcome,
        "target_database": "MathV0_s1c2_validation_test",
        "migration_id": MIGRATION_ID,
        "zip_sha256": ZIP_SHA256,
        "plan_semantic_sha256": PLAN_SHA256,
        "decisions_sha256": "c" * 64,
        "expected_sources": 16,
        "sources_created": 16,
        "sources_identical": 0,
        "expected_references": 20,
        "references_created": 20,
        "references_identical": 0,
        "indexes": IndexApplyResult(
            planned=("sources_source_id_unique",),
            applied=("sources_source_id_unique",),
            final_state_sha256="d" * 64,
        ),
        "manifest_state": "applied",
        "invariant_hashes_before": {"legacy": "e" * 64},
        "invariant_hashes_after": {"legacy": "e" * 64},
        "invariants_passed": True,
        "next_action": "Review the isolated validation result.",
    }
    payload.update(changes)
    return ApplyResult.model_validate(payload)


@pytest.mark.parametrize("outcome", tuple(ApplyOutcome))
def test_every_required_apply_outcome_is_typed_and_serializable(outcome: ApplyOutcome) -> None:
    result = _apply_result(outcome)

    assert result.status == outcome
    assert json.loads(render_apply_result(result, "json"))["outcome"] == outcome.value


def test_apply_result_text_is_bounded_and_redacts_credentials_paths_and_uri() -> None:
    secret = (
        "Traceback (most recent call last): mongodb://alice:secret@localhost:27017/db "
        "password=hunter2 /home/alice/private/file " + "x" * 1_000
    )
    result = _apply_result(
        outcome=ApplyOutcome.FAILED,
        sources_created=1,
        references_created=0,
        invariant_hashes_after={},
        invariants_passed=False,
        errors=(secret,) * 20,
        next_action="Inspect safely.",
    )

    text = render_apply_result(result, "text")
    rendered_json = render_apply_result(result, "json")

    assert len(result.errors) == 8
    assert "alice" not in text + rendered_json
    assert "hunter2" not in text + rendered_json
    assert "/home/alice" not in text + rendered_json
    assert "<redacted MongoDB URI>" in text
    assert all(len(error) <= 400 for error in result.errors)


def test_apply_result_rejects_impossible_counts_extra_fields_and_bad_format() -> None:
    with pytest.raises(ValidationError, match="exceed"):
        _apply_result(sources_created=17)
    with pytest.raises(ValidationError, match="extra"):
        _apply_result(unexpected=True)
    with pytest.raises(ValueError, match="Unsupported"):
        render_apply_result(_apply_result(), "yaml")

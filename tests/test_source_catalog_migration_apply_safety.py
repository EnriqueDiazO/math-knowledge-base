"""Authorization and double-read preflight tests using only the strict fake."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from source_catalog_migration_fakes import FakeDatabase

from mathmongo.source_catalog_migration import apply_safety as safety_module
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_EXPECTED_COUNTS
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_PLAN_SEMANTIC_SHA256
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_ZIP_SHA256
from mathmongo.source_catalog_migration.apply_safety import ApplyAuthorization
from mathmongo.source_catalog_migration.apply_safety import ApplySafetyError
from mathmongo.source_catalog_migration.apply_safety import LegacySnapshotComparison
from mathmongo.source_catalog_migration.apply_safety import preflight_legacy_database
from mathmongo.source_catalog_migration.apply_safety import require_successful_legacy_preflight
from mathmongo.source_catalog_migration.apply_safety import validate_apply_authorization
from mathmongo.source_catalog_migration.apply_safety import validate_authoritative_plan
from mathmongo.source_catalog_migration.decisions import DecisionSet
from mathmongo.source_catalog_migration.models import Conflict
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_EXPECTATIONS
from mathmongo.source_catalog_migration.planner import build_plan
from mathmongo.source_catalog_migration.planner import semantic_plan_payload
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_ZIP = PROJECT_ROOT / "mathkb_export_20260712_073927.zip"
TARGET = "MathV0_s1c2_validation_apply_safety_tests"


@pytest.fixture(scope="module")
def authoritative_export() -> LoadedLegacyExport:
    if not REAL_ZIP.is_file():
        pytest.skip("The approved untracked authoritative ZIP is not present")
    before = (REAL_ZIP.stat().st_size, REAL_ZIP.stat().st_mtime_ns)
    export = read_legacy_export(
        REAL_ZIP,
        database_name="MathV0",
        fail_on_input_change=True,
    )
    after = (REAL_ZIP.stat().st_size, REAL_ZIP.stat().st_mtime_ns)
    assert before == after
    assert export.input_snapshot.sha256 == AUTHORITATIVE_ZIP_SHA256
    return export


@pytest.fixture(scope="module")
def authoritative_plan(authoritative_export: LoadedLegacyExport) -> MigrationPlan:
    plan = build_plan(authoritative_export, expectations=AUTHORITATIVE_EXPECTATIONS)
    assert plan.semantic_sha256 == AUTHORITATIVE_PLAN_SEMANTIC_SHA256
    return plan


@pytest.fixture(scope="module")
def complete_decisions(authoritative_plan: MigrationPlan) -> DecisionSet:
    return DecisionSet(
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        accept_all_safe_exact=True,
        accepted_reference_candidates=(),
        weak_suggestion_decisions={
            item.suggestion_key: "keep_separate"
            for item in authoritative_plan.weak_reference_suggestions
        },
        locator_review_decisions={
            item.review_key: "defer" for item in authoritative_plan.review_items
        },
    )


def _authorization(**changes: Any) -> ApplyAuthorization:
    values = {
        "target_database": TARGET,
        "allow_isolated_write": True,
        "confirmed_database": TARGET,
        "expected_zip_sha": AUTHORITATIVE_ZIP_SHA256,
        "expected_plan_sha": AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
    }
    values.update(changes)
    return ApplyAuthorization.model_validate(values)


def _target_database(
    export: LoadedLegacyExport,
    *,
    extra_collections: dict[str, tuple[dict, ...]] | None = None,
) -> FakeDatabase:
    collections = {name: documents for name, documents in export.collections.items()}
    collections.update(extra_collections or {})
    return FakeDatabase(TARGET, collections)


def test_exact_authorization_accepts_both_isolated_target_prefixes() -> None:
    targets = (
        "MathV0_s1c2_validation_20260712",
        "mathmongo_s1c2_validation_test-01",
    )

    for target in targets:
        authorization = _authorization(
            target_database=target,
            confirmed_database=target,
        )
        assert validate_apply_authorization(authorization) is authorization


@pytest.mark.parametrize(
    "target",
    ["MathV0", "mathmongo", "admin", "config", "local", "MATHV0", "ADMIN"],
)
def test_authorization_rejects_protected_database_names(target: str) -> None:
    with pytest.raises(ApplySafetyError) as exc_info:
        validate_apply_authorization(
            _authorization(target_database=target, confirmed_database=target)
        )

    assert exc_info.value.code == "forbidden_target"


@pytest.mark.parametrize(
    "target",
    [
        "MathV0_s1c2_validation_",
        "mathmongo_s1c2_validation_",
        "MathV0_validation_test",
        "prefix_MathV0_s1c2_validation_test",
        "MathV0_s1c2_validation_bad.name",
        "MathV0_s1c2_validation_bad/name",
        "MathV0_s1c2_validation_bad suffix",
        "MathV0_s1c2_validation_á",
    ],
)
def test_authorization_rejects_missing_or_malformed_isolated_suffix(target: str) -> None:
    with pytest.raises(ApplySafetyError) as exc_info:
        validate_apply_authorization(
            _authorization(target_database=target, confirmed_database=target)
        )

    assert exc_info.value.code == "invalid_target"


def test_authorization_requires_write_flag_and_exact_confirmation() -> None:
    with pytest.raises(ApplySafetyError) as flag_error:
        validate_apply_authorization(_authorization(allow_isolated_write=False))
    with pytest.raises(ApplySafetyError) as confirmation_error:
        validate_apply_authorization(_authorization(confirmed_database=f"{TARGET}_different"))

    assert flag_error.value.code == "write_not_authorized"
    assert confirmation_error.value.code == "database_confirmation_mismatch"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("expected_zip_sha", "0" * 64, "zip_hash_mismatch"),
        ("expected_plan_sha", "0" * 64, "plan_hash_mismatch"),
    ],
)
def test_authorization_requires_exact_authoritative_hashes(
    field: str,
    value: str,
    expected_code: str,
) -> None:
    with pytest.raises(ApplySafetyError) as exc_info:
        validate_apply_authorization(_authorization(**{field: value}))

    assert exc_info.value.code == expected_code


def test_plan_and_double_read_database_preflights_pass_without_writes(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    plan_preflight = validate_authoritative_plan(authoritative_plan, complete_decisions)
    database = _target_database(authoritative_export)

    comparison = preflight_legacy_database(
        authoritative_export,
        database,
        require_catalog_absent=True,
    )

    assert plan_preflight.passed is True
    assert plan_preflight.expected_counts == AUTHORITATIVE_EXPECTED_COUNTS
    assert plan_preflight.zip_sha256 == AUTHORITATIVE_ZIP_SHA256
    assert plan_preflight.plan_semantic_sha256 == AUTHORITATIVE_PLAN_SEMANTIC_SHA256
    assert require_successful_legacy_preflight(comparison) is comparison
    assert comparison.successful is True
    assert comparison.snapshot_drift is False
    assert comparison.live_database_drift is False
    assert comparison.writes_attempted == 0
    assert (
        len([event for event in database.read_events if event.operation == "list_collection_names"])
        == 2
    )
    assert database.write_attempt_events == ()
    assert database.forbidden_events == ()


def test_plan_preflight_recomputes_semantic_payload_instead_of_trusting_hash_field(
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    altered_summary = authoritative_plan.summary.model_copy(update={"source_candidate_count": 15})
    tampered = authoritative_plan.model_copy(update={"summary": altered_summary})
    assert tampered.semantic_sha256 == AUTHORITATIVE_PLAN_SEMANTIC_SHA256

    with pytest.raises(ApplySafetyError) as exc_info:
        validate_authoritative_plan(tampered, complete_decisions)

    assert exc_info.value.code == "plan_self_hash_mismatch"


def test_plan_preflight_rejects_incomplete_human_decisions(
    authoritative_plan: MigrationPlan,
) -> None:
    incomplete = DecisionSet(
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        accept_all_safe_exact=None,
    )

    with pytest.raises(ApplySafetyError) as exc_info:
        validate_authoritative_plan(authoritative_plan, incomplete)

    assert exc_info.value.code == "invalid_decisions"


def test_plan_preflight_explicitly_rejects_failed_invariants(
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authoritative_payload = semantic_plan_payload(authoritative_plan)
    failed = authoritative_plan.invariants.model_copy(update={"zip_unchanged": False})
    tampered = authoritative_plan.model_copy(update={"invariants": failed})
    monkeypatch.setattr(
        safety_module,
        "semantic_plan_payload",
        lambda _plan: authoritative_payload,
    )

    with pytest.raises(ApplySafetyError) as exc_info:
        validate_authoritative_plan(tampered, complete_decisions)

    assert exc_info.value.code == "plan_invariant_failed"


def test_plan_preflight_explicitly_rejects_a_conflict_queue(
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authoritative_payload = semantic_plan_payload(authoritative_plan)
    source_keys = tuple(
        item.source_candidate_key for item in authoritative_plan.source_candidates[:2]
    )
    reference_keys = tuple(
        item.reference_candidate_key for item in authoritative_plan.reference_candidates[:2]
    )
    conflict = Conflict(
        conflict_key="conflict_test",
        conflict_type="metadata_conflict",
        reference_candidate_keys=reference_keys,
        source_candidate_keys=source_keys,
        concept_count=2,
    )
    tampered = authoritative_plan.model_copy(update={"conflicts": (conflict,)})
    monkeypatch.setattr(
        safety_module,
        "semantic_plan_payload",
        lambda _plan: authoritative_payload,
    )

    with pytest.raises(ApplySafetyError) as exc_info:
        validate_authoritative_plan(tampered, complete_decisions)

    assert exc_info.value.code == "plan_conflict"


@pytest.mark.parametrize("collection_name", ["sources", "references"])
def test_first_preflight_blocks_physically_present_empty_catalog_collection(
    collection_name: str,
    authoritative_export: LoadedLegacyExport,
) -> None:
    database = _target_database(
        authoritative_export,
        extra_collections={collection_name: ()},
    )
    assert database[collection_name].count_documents({}) == 0

    comparison = preflight_legacy_database(
        authoritative_export,
        database,
        require_catalog_absent=True,
    )

    assert comparison.snapshot_drift is True
    assert comparison.successful is False
    if collection_name == "sources":
        assert comparison.sources_collection_absent is False
    else:
        assert comparison.references_collection_absent is False
    assert any("physically present" in detail for detail in comparison.drift_details)
    with pytest.raises(ApplySafetyError) as exc_info:
        require_successful_legacy_preflight(comparison)
    assert exc_info.value.code == "snapshot_drift"
    assert database.write_attempt_events == ()


def test_compatible_resume_preflight_allows_existing_catalog_collections(
    authoritative_export: LoadedLegacyExport,
) -> None:
    database = _target_database(
        authoritative_export,
        extra_collections={"sources": (), "references": ()},
    )

    comparison = preflight_legacy_database(
        authoritative_export,
        database,
        require_catalog_absent=False,
    )

    assert comparison.catalog_absence_required is False
    assert comparison.sources_collection_absent is False
    assert comparison.references_collection_absent is False
    assert comparison.snapshot_drift is False
    assert comparison.successful is True
    assert require_successful_legacy_preflight(comparison) is comparison
    assert database.write_attempt_events == ()


def test_preflight_rejects_an_absent_expected_empty_legacy_collection(
    authoritative_export: LoadedLegacyExport,
) -> None:
    collections = dict(authoritative_export.collections)
    assert collections.pop("weekly_reviews") == ()
    database = FakeDatabase(TARGET, collections)

    comparison = preflight_legacy_database(
        authoritative_export,
        database,
        require_catalog_absent=True,
    )

    assert comparison.snapshot_drift is True
    assert comparison.counts_match is True
    assert comparison.fingerprints_match is True
    assert any("presence differs" in detail for detail in comparison.drift_details)
    with pytest.raises(ApplySafetyError) as exc_info:
        require_successful_legacy_preflight(comparison)
    assert exc_info.value.code == "snapshot_drift"
    assert database.write_attempt_events == ()


def test_stable_target_mismatch_is_snapshot_drift_not_concurrent_drift(
    authoritative_export: LoadedLegacyExport,
) -> None:
    database = _target_database(authoritative_export)
    first = authoritative_export.collections["concepts"][0]
    assert database.external_update_one(
        "concepts",
        {"id": first["id"], "source": first["source"]},
        {"source": f"{first['source']}_externally_changed"},
    )

    comparison = preflight_legacy_database(
        authoritative_export,
        database,
        require_catalog_absent=True,
    )

    assert comparison.snapshot_drift is True
    assert comparison.live_database_drift is False
    assert comparison.fingerprints_match is False
    with pytest.raises(ApplySafetyError) as exc_info:
        require_successful_legacy_preflight(comparison)
    assert exc_info.value.code == "snapshot_drift"
    assert database.write_attempt_events == ()


def test_mutation_between_reads_is_detected_as_live_database_drift(
    authoritative_export: LoadedLegacyExport,
) -> None:
    database = _target_database(authoritative_export)
    first = authoritative_export.collections["concepts"][0]

    def mutate_between_snapshots(
        fake: FakeDatabase,
        _collection: str | None,
        _details: dict,
    ) -> None:
        assert fake.external_update_one(
            "concepts",
            {"id": first["id"], "source": first["source"]},
            {"__concurrent_change": True},
        )

    failpoint = database.add_failpoint(
        "list_collection_names",
        occurrence=2,
        callback=mutate_between_snapshots,
    )

    comparison = preflight_legacy_database(
        authoritative_export,
        database,
        require_catalog_absent=True,
    )

    assert failpoint.fired is True
    assert comparison.snapshot_drift is True
    assert comparison.live_database_drift is True
    assert comparison.fingerprints_match is False
    assert any("changed between" in detail for detail in comparison.drift_details)
    with pytest.raises(ApplySafetyError) as exc_info:
        require_successful_legacy_preflight(comparison)
    assert exc_info.value.code == "snapshot_drift"
    assert database.write_attempt_events == ()


@pytest.mark.parametrize(
    ("changes", "expected_code"),
    [
        ({"snapshot_drift": True}, "snapshot_drift"),
        ({"live_database_drift": True}, "live_database_drift"),
        ({"writes_attempted": 1}, "preflight_write_detected"),
        (
            {
                "catalog_absence_required": True,
                "sources_collection_absent": False,
            },
            "sources_collection_present",
        ),
        (
            {
                "catalog_absence_required": True,
                "references_collection_absent": False,
            },
            "references_collection_present",
        ),
        ({"counts_match": False}, "legacy_snapshot_mismatch"),
        ({"fingerprints_match": False}, "legacy_snapshot_mismatch"),
        ({"legacy_indexes_stable": False}, "legacy_index_drift"),
    ],
)
def test_success_requirement_checks_every_explicit_preflight_flag(
    changes: dict[str, Any],
    expected_code: str,
) -> None:
    good = LegacySnapshotComparison(
        database_name=TARGET,
        expected_zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        expected_aggregate_sha256="1" * 64,
        before_aggregate_sha256="1" * 64,
        after_aggregate_sha256="1" * 64,
        before_indexes_sha256="2" * 64,
        after_indexes_sha256="2" * 64,
        snapshot_drift=False,
        live_database_drift=False,
        writes_attempted=0,
        counts_match=True,
        fingerprints_match=True,
        legacy_indexes_stable=True,
        sources_collection_absent=True,
        references_collection_absent=True,
        catalog_absence_required=True,
    )
    unsafe = good.model_copy(update=changes)

    with pytest.raises(ApplySafetyError) as exc_info:
        require_successful_legacy_preflight(unsafe)

    assert exc_info.value.code == expected_code

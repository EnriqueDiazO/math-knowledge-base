"""Keep approved migration identity independent from physical archive metadata."""

import os
import shutil

import pytest

from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_EXPECTATIONS
from mathmongo.source_catalog_migration.planner import build_plan
from mathmongo.source_catalog_migration.planner import semantic_plan_payload
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export
from test_source_catalog_migration_bootstrap import authoritative_export as authoritative_export
from test_source_catalog_migration_bootstrap import complete_decisions as complete_decisions


def test_same_corpus_has_the_same_plan_after_copy_rename_and_touch(authoritative_export, tmp_path):
    """Relocating identical bytes cannot revoke or alter the semantic approval."""
    from test_source_catalog_migration_bootstrap import REAL_ZIP
    copy = tmp_path / "renamed-approved.zip"
    shutil.copyfile(REAL_ZIP, copy)
    os.utime(copy, (1_600_000_000, 1_600_000_000))
    relocated = read_legacy_export(copy, database_name="MathV0", fail_on_input_change=True)
    first = build_plan(authoritative_export, expectations=AUTHORITATIVE_EXPECTATIONS)
    second = build_plan(relocated, expectations=AUTHORITATIVE_EXPECTATIONS)
    assert authoritative_export.input_snapshot.sha256 == relocated.input_snapshot.sha256
    assert first.semantic_sha256 == second.semantic_sha256
    assert semantic_plan_payload(first) == semantic_plan_payload(second)


def test_semantic_identity_still_binds_content_database_and_candidates(authoritative_export):
    """Dropping physical metadata must not drop security-relevant plan evidence."""
    plan = build_plan(authoritative_export, expectations=AUTHORITATIVE_EXPECTATIONS)
    original = semantic_plan_payload(plan)
    for field, value in (("sha256", "different-content"), ("database_name", "another-target")):
        changed = {**original, "input_snapshot": {**original["input_snapshot"], field: value}}
        assert sha256_digest(changed) != plan.semantic_sha256
    changed = {**original, "concept_bindings": []}
    assert sha256_digest(changed) != plan.semantic_sha256


def test_v1_plan_cannot_be_applied_using_v2_approval(authoritative_export, complete_decisions):
    """Changing canonicalization requires a new plan/decisions, never implicit acceptance."""
    from mathmongo.source_catalog_migration.apply_safety import ApplySafetyError
    from mathmongo.source_catalog_migration.apply_safety import validate_authoritative_inputs
    plan = build_plan(authoritative_export, expectations=AUTHORITATIVE_EXPECTATIONS)
    legacy = plan.model_copy(update={"planner_version": "s1c1-v1"})
    legacy = legacy.model_copy(update={"semantic_sha256": sha256_digest(semantic_plan_payload(legacy))})
    # Approval is rejected before decisions can authorize any mutation.
    with pytest.raises(ApplySafetyError, match="not authoritative"):
        validate_authoritative_inputs(authoritative_export, legacy, complete_decisions)

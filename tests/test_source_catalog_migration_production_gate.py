"""Fake-only coverage for the guarded MathV0 Source Catalog production path."""

# ruff: noqa: D103

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from source_catalog_migration_fakes import FakeDatabase
from source_catalog_migration_fakes import FakeMongoClientFactory

from mathmongo.source_catalog_migration import backup_safety as backup_safety_module
from mathmongo.source_catalog_migration import bootstrap as bootstrap_module
from mathmongo.source_catalog_migration import cli as migration_cli
from mathmongo.source_catalog_migration.apply_result import ApplyOutcome
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_PLAN_SEMANTIC_SHA256
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_ZIP_SHA256
from mathmongo.source_catalog_migration.apply_safety import PRODUCTION_CONFIRMATION_PHRASE
from mathmongo.source_catalog_migration.apply_safety import ApplyAuthorization
from mathmongo.source_catalog_migration.apply_safety import ApplySafetyError
from mathmongo.source_catalog_migration.apply_safety import legacy_snapshot_from_documents
from mathmongo.source_catalog_migration.apply_safety import validate_apply_authorization
from mathmongo.source_catalog_migration.backup_safety import ProductionBackupRevalidationError
from mathmongo.source_catalog_migration.backup_safety import validate_production_backup
from mathmongo.source_catalog_migration.bootstrap import BootstrapEngine
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.decisions import DecisionSet
from mathmongo.source_catalog_migration.decisions import decisions_json
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_EXPECTATIONS
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_SNAPSHOT_COUNTS
from mathmongo.source_catalog_migration.planner import build_plan
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export

ROOT = Path(__file__).resolve().parents[1]
REAL_ZIP = ROOT / "mathkb_export_20260712_073927.zip"
PRODUCTION_DATABASE = "MathV0"
ISOLATED_DATABASE = "MathV0_s1c2_validation_production_gate_tests"


@dataclass(frozen=True, slots=True)
class _BackupFixture:
    path: Path
    sha256: str
    write_freeze_at: datetime
    exported_at: datetime
    completed_at: datetime
    legacy_aggregate_sha256: str
    media_aggregate_sha256: str
    media_file_count: int


@dataclass(frozen=True, slots=True)
class _AuthoritativeBundle:
    export: LoadedLegacyExport
    plan: MigrationPlan
    decisions: DecisionSet
    media_files: dict[str, bytes]


def _regular_member(name: str, payload: str) -> tuple[zipfile.ZipInfo, str]:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info, payload


def _placeholder_collections(
    counts: dict[str, int] | None = None,
) -> dict[str, tuple[dict[str, Any], ...]]:
    effective = counts or dict(AUTHORITATIVE_SNAPSHOT_COUNTS)
    return {name: tuple({} for _ in range(count)) for name, count in effective.items()}


def _write_backup(
    root: Path,
    *,
    collections: dict[str, tuple[dict[str, Any], ...]] | None = None,
    media_files: dict[str, bytes] | None = None,
    database_name: str = PRODUCTION_DATABASE,
    format_name: str = "mathkb_legacy_export",
    format_version: int = 1,
    metadata_changes: dict[str, Any] | None = None,
    age: timedelta = timedelta(0),
) -> _BackupFixture:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    archive_path = root / "mathv0-pre-apply.zip"
    now = datetime.now(timezone.utc)
    write_freeze_at = now - age - timedelta(seconds=4)
    exported_at = now - age - timedelta(seconds=3)
    completed_at = now - age - timedelta(seconds=2)
    documents = collections or _placeholder_collections()
    physical_media = dict(media_files or {})
    metadata: dict[str, Any] = {
        "format": format_name,
        "format_version": format_version,
        "database_name": database_name,
        "exported_at": exported_at.isoformat(),
        "snapshot_completed_at": completed_at.isoformat(),
        "collections": {name: len(rows) for name, rows in documents.items()},
        "media_files": {name: len(data) for name, data in sorted(physical_media.items())},
    }
    metadata.update(metadata_changes or {})
    base = "mathkb_export_production_gate_test"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info, payload = _regular_member(f"{base}/metadata.json", json.dumps(metadata))
        archive.writestr(info, payload)
        for collection_name, rows in sorted(documents.items()):
            info, payload = _regular_member(
                f"{base}/collections/{collection_name}.json",
                json.dumps(rows, ensure_ascii=False),
            )
            archive.writestr(info, payload)
        for relative_name, media_data in sorted(physical_media.items()):
            info = zipfile.ZipInfo(f"{base}/{relative_name}")
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, media_data)
    archive_path.chmod(0o600)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    legacy_aggregate_sha256 = legacy_snapshot_from_documents(
        documents,
        database_name=PRODUCTION_DATABASE,
    ).aggregate_sha256
    media_rows = [
        {
            "name": name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        for name, data in sorted(physical_media.items())
    ]
    return _BackupFixture(
        path=archive_path,
        sha256=digest,
        write_freeze_at=write_freeze_at,
        exported_at=exported_at,
        completed_at=completed_at,
        legacy_aggregate_sha256=legacy_aggregate_sha256,
        media_aggregate_sha256=sha256_digest(media_rows),
        media_file_count=len(media_rows),
    )


def _validate_backup(backup: _BackupFixture):
    return validate_production_backup(
        backup.path,
        backup_sha=backup.sha256,
        confirm_backup_sha=backup.sha256,
        write_freeze_at=backup.write_freeze_at,
        _expected_legacy_aggregate_sha256=backup.legacy_aggregate_sha256,
        _expected_media_aggregate_sha256=backup.media_aggregate_sha256,
        _expected_media_file_count=backup.media_file_count,
    )


def _production_authorization(backup: _BackupFixture) -> ApplyAuthorization:
    evidence = _validate_backup(backup)
    return ApplyAuthorization(
        target_database=PRODUCTION_DATABASE,
        allow_production_write=True,
        confirmed_database=PRODUCTION_DATABASE,
        confirm_production_phrase=PRODUCTION_CONFIRMATION_PHRASE,
        expected_zip_sha=AUTHORITATIVE_ZIP_SHA256,
        expected_plan_sha=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        production_backup=evidence,
        production_backup_path=backup.path,
        production_backup_sha=backup.sha256,
        confirm_production_backup_sha=backup.sha256,
        write_freeze_at=backup.write_freeze_at,
    )


def _production_cli_arguments(backup: _BackupFixture | None = None) -> list[str]:
    path = backup.path if backup is not None else Path("/definitely/missing/mathv0-backup.zip")
    digest = backup.sha256 if backup is not None else "b" * 64
    freeze = (
        backup.write_freeze_at
        if backup is not None
        else datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    return [
        "apply",
        "--input-zip",
        "authoritative.zip",
        "--decisions",
        "decisions.json",
        "--database",
        PRODUCTION_DATABASE,
        "--allow-production-write",
        "--confirm-database",
        PRODUCTION_DATABASE,
        "--confirm-production-phrase",
        PRODUCTION_CONFIRMATION_PHRASE,
        "--backup-path",
        str(path),
        "--backup-sha",
        digest,
        "--confirm-backup-sha",
        digest,
        "--write-freeze-at",
        freeze.isoformat(),
        "--expected-zip-sha",
        AUTHORITATIVE_ZIP_SHA256,
        "--expected-plan-sha",
        AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
    ]


def _replace_option(arguments: list[str], option: str, value: str) -> list[str]:
    result = list(arguments)
    result[result.index(option) + 1] = value
    return result


@pytest.fixture(scope="module")
def authoritative_bundle() -> _AuthoritativeBundle:
    if not REAL_ZIP.is_file():
        pytest.skip("The approved authoritative ZIP is not present")
    export = read_legacy_export(
        REAL_ZIP,
        database_name=PRODUCTION_DATABASE,
        fail_on_input_change=True,
    )
    plan = build_plan(export, expectations=AUTHORITATIVE_EXPECTATIONS)
    decisions = DecisionSet(
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        accept_all_safe_exact=True,
        accepted_reference_candidates=(),
        weak_suggestion_decisions={
            item.suggestion_key: "keep_separate" for item in plan.weak_reference_suggestions
        },
        locator_review_decisions={item.review_key: "defer" for item in plan.review_items},
    )
    with zipfile.ZipFile(REAL_ZIP) as archive:
        media_files = {
            name.split("/", 1)[1]: archive.read(name)
            for name in archive.namelist()
            if "/media/" in name and not name.endswith("/")
        }
    return _AuthoritativeBundle(
        export=export,
        plan=plan,
        decisions=decisions,
        media_files=media_files,
    )


def test_mathv0_without_production_flag_fails_before_any_input_or_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _production_cli_arguments()
    arguments.remove("--allow-production-write")
    monkeypatch.setattr(
        migration_cli,
        "_load_authoritative_plan",
        lambda *_args: (_ for _ in ()).throw(AssertionError("ZIP must not be read")),
    )
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: (_ for _ in ()).throw(AssertionError("config must not be read")),
    )

    assert migration_cli.main(arguments) == migration_cli.EXIT_USAGE


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--confirm-production-phrase", "APPLY SOMETHING ELSE"),
        ("--confirm-database", "MathV0_typo"),
        ("--expected-zip-sha", "d" * 64),
        ("--expected-plan-sha", "e" * 64),
    ],
)
def test_invalid_production_assertions_fail_before_backup_zip_config_or_client(
    option: str,
    value: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _replace_option(_production_cli_arguments(), option, value)
    monkeypatch.setattr(
        migration_cli,
        "validate_production_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("backup must not be read")),
    )
    monkeypatch.setattr(
        migration_cli,
        "_load_authoritative_plan",
        lambda *_args: (_ for _ in ()).throw(AssertionError("ZIP must not be read")),
    )
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: (_ for _ in ()).throw(AssertionError("config must not be read")),
    )

    assert migration_cli.main(arguments) == migration_cli.EXIT_APPLY_BLOCKED


def test_production_rejects_output_file_and_combined_write_modes_before_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        migration_cli,
        "validate_production_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("backup must not be read")),
    )
    with_output = [*_production_cli_arguments(), "--output", str(tmp_path / "result.json")]
    both_modes = [*_production_cli_arguments(), "--allow-isolated-write"]

    assert migration_cli.main(with_output) == migration_cli.EXIT_APPLY_BLOCKED
    assert migration_cli.main(both_modes) == migration_cli.EXIT_APPLY_BLOCKED


def test_missing_backup_fails_before_authoritative_zip_config_or_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _production_cli_arguments()
    arguments = _replace_option(arguments, "--backup-path", str(tmp_path / "missing.zip"))
    monkeypatch.setattr(
        migration_cli,
        "_load_authoritative_plan",
        lambda *_args: (_ for _ in ()).throw(AssertionError("ZIP must not be read")),
    )
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: (_ for _ in ()).throw(AssertionError("config must not be read")),
    )

    assert migration_cli.main(arguments) == migration_cli.EXIT_APPLY_BLOCKED


def test_backup_symlink_is_rejected(tmp_path: Path) -> None:
    backup = _write_backup(tmp_path / "private")
    symlink = backup.path.with_name("linked-backup.zip")
    symlink.symlink_to(backup.path)

    with pytest.raises(ApplySafetyError) as caught:
        validate_production_backup(
            symlink,
            backup_sha=backup.sha256,
            confirm_backup_sha=backup.sha256,
            write_freeze_at=backup.write_freeze_at,
        )

    assert caught.value.code == "invalid_backup_path"


def test_backup_inside_site_packages_named_tree_is_rejected(tmp_path: Path) -> None:
    backup = _write_backup(tmp_path / "site-packages" / "private")

    with pytest.raises(ApplySafetyError) as caught:
        _validate_backup(backup)

    assert caught.value.code == "backup_inside_site_packages"


def test_backup_hash_and_confirmation_must_match_real_bytes(tmp_path: Path) -> None:
    backup = _write_backup(tmp_path / "private")

    with pytest.raises(ApplySafetyError) as confirmation:
        validate_production_backup(
            backup.path,
            backup_sha=backup.sha256,
            confirm_backup_sha="c" * 64,
            write_freeze_at=backup.write_freeze_at,
        )
    assert confirmation.value.code == "backup_confirmation_mismatch"

    with pytest.raises(ApplySafetyError) as content:
        validate_production_backup(
            backup.path,
            backup_sha="d" * 64,
            confirm_backup_sha="d" * 64,
            write_freeze_at=backup.write_freeze_at,
        )
    assert content.value.code == "backup_hash_mismatch"


def test_backup_path_swap_after_single_fd_capture_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = _write_backup(tmp_path / "path-swap")
    original_parser = backup_safety_module._parse_backup_bytes
    original_stat = backup.path.stat()

    def mutate_path_after_capture(data: bytes):
        changed = bytearray(backup.path.read_bytes())
        changed[10] ^= 1
        backup.path.write_bytes(changed)
        backup.path.chmod(0o600)
        # Restore mtime deliberately; ctime and the final bytes still expose the swap.
        os.utime(
            backup.path,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        return original_parser(data)

    monkeypatch.setattr(
        backup_safety_module,
        "_parse_backup_bytes",
        mutate_path_after_capture,
    )

    with pytest.raises(ApplySafetyError) as caught:
        _validate_backup(backup)

    assert caught.value.code == "backup_changed"


def test_backup_parent_replaced_by_symlink_during_parse_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = _write_backup(tmp_path / "ancestor-swap")
    original_parser = backup_safety_module._parse_backup_bytes
    parent = backup.path.parent
    moved_parent = parent.with_name("ancestor-swap-moved")

    def replace_parent_with_symlink(data: bytes):
        parent.rename(moved_parent)
        parent.symlink_to(moved_parent, target_is_directory=True)
        return original_parser(data)

    monkeypatch.setattr(
        backup_safety_module,
        "_parse_backup_bytes",
        replace_parent_with_symlink,
    )

    with pytest.raises(ApplySafetyError) as caught:
        _validate_backup(backup)

    assert caught.value.code == "backup_changed"


def test_backup_and_parent_permissions_must_be_private(tmp_path: Path) -> None:
    backup = _write_backup(tmp_path / "private")
    backup.path.chmod(0o644)

    with pytest.raises(ApplySafetyError) as file_error:
        _validate_backup(backup)
    assert file_error.value.code == "backup_permissions_not_private"

    backup.path.chmod(0o600)
    backup.path.parent.chmod(0o755)
    with pytest.raises(ApplySafetyError) as parent_error:
        _validate_backup(backup)
    assert parent_error.value.code == "backup_permissions_not_private"


def test_backup_parent_permission_change_at_final_chain_check_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = _write_backup(tmp_path / "late-parent-mode-change")
    original_verify = backup_safety_module._verify_directory_chain
    calls = 0

    def change_mode_on_final_check(descriptors: list[int], parts: tuple[str, ...]) -> None:
        nonlocal calls
        calls += 1
        original_verify(descriptors, parts)
        if calls == 2:
            backup.path.parent.chmod(0o755)

    monkeypatch.setattr(
        backup_safety_module,
        "_verify_directory_chain",
        change_mode_on_final_check,
    )

    with pytest.raises(ApplySafetyError) as caught:
        _validate_backup(backup)

    assert caught.value.code == "backup_changed"
    assert calls == 2


@pytest.mark.parametrize(
    ("metadata_changes", "expected_code"),
    [
        ({"database_name": "AnotherDatabase"}, "backup_database_mismatch"),
        ({"format": "unknown-export"}, "backup_format_mismatch"),
        ({"format_version": 99}, "backup_format_mismatch"),
        ({"snapshot_completed_at": None}, "invalid_backup_metadata"),
    ],
)
def test_backup_metadata_must_identify_supported_mathv0_export(
    metadata_changes: dict[str, Any],
    expected_code: str,
    tmp_path: Path,
) -> None:
    backup = _write_backup(
        tmp_path / expected_code,
        metadata_changes=metadata_changes,
    )

    with pytest.raises(ApplySafetyError) as caught:
        _validate_backup(backup)

    assert caught.value.code == expected_code


def test_backup_requires_exact_authoritative_legacy_counts(tmp_path: Path) -> None:
    counts = dict(AUTHORITATIVE_SNAPSHOT_COUNTS)
    counts["concepts"] -= 1
    backup = _write_backup(
        tmp_path / "counts",
        collections=_placeholder_collections(counts),
    )

    with pytest.raises(ApplySafetyError) as caught:
        _validate_backup(backup)

    assert caught.value.code == "backup_counts_mismatch"


def test_backup_requires_authoritative_legacy_fingerprints_not_only_counts(
    tmp_path: Path,
) -> None:
    backup = _write_backup(tmp_path / "fingerprints")

    with pytest.raises(ApplySafetyError) as caught:
        validate_production_backup(
            backup.path,
            backup_sha=backup.sha256,
            confirm_backup_sha=backup.sha256,
            write_freeze_at=backup.write_freeze_at,
        )

    assert caught.value.code == "backup_fingerprint_mismatch"


def test_backup_requires_authoritative_physical_media_inventory(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
) -> None:
    backup = _write_backup(
        tmp_path / "media-missing",
        collections=authoritative_bundle.export.collections,
    )

    with pytest.raises(ApplySafetyError) as caught:
        validate_production_backup(
            backup.path,
            backup_sha=backup.sha256,
            confirm_backup_sha=backup.sha256,
            write_freeze_at=backup.write_freeze_at,
        )

    assert caught.value.code == "backup_media_mismatch"


@pytest.mark.parametrize("mutation", ["bytes", "name"])
def test_backup_rejects_changed_media_with_authoritative_file_count(
    mutation: str,
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
) -> None:
    media_files = dict(authoritative_bundle.media_files)
    original_name = sorted(media_files)[0]
    original_bytes = media_files.pop(original_name)
    if mutation == "bytes":
        media_files[original_name] = bytes([original_bytes[0] ^ 1]) + original_bytes[1:]
    else:
        original_path = Path(original_name)
        renamed = original_path.with_name(f"renamed-{original_path.name}").as_posix()
        media_files[renamed] = original_bytes
    backup = _write_backup(
        tmp_path / f"media-{mutation}",
        collections=authoritative_bundle.export.collections,
        media_files=media_files,
    )

    with pytest.raises(ApplySafetyError) as caught:
        validate_production_backup(
            backup.path,
            backup_sha=backup.sha256,
            confirm_backup_sha=backup.sha256,
            write_freeze_at=backup.write_freeze_at,
        )

    assert backup.media_file_count == 15
    assert caught.value.code == "backup_media_mismatch"


def test_backup_must_start_after_write_freeze(tmp_path: Path) -> None:
    backup = _write_backup(tmp_path / "freeze")
    freeze_after_export_started = backup.exported_at + timedelta(seconds=1)

    with pytest.raises(ApplySafetyError) as caught:
        validate_production_backup(
            backup.path,
            backup_sha=backup.sha256,
            confirm_backup_sha=backup.sha256,
            write_freeze_at=freeze_after_export_started,
            _expected_legacy_aggregate_sha256=backup.legacy_aggregate_sha256,
            _expected_media_aggregate_sha256=backup.media_aggregate_sha256,
            _expected_media_file_count=backup.media_file_count,
        )

    assert caught.value.code == "backup_precedes_write_freeze"


def test_week_old_backup_is_not_fresh(tmp_path: Path) -> None:
    backup = _write_backup(tmp_path / "stale", age=timedelta(days=7))

    with pytest.raises(ApplySafetyError) as caught:
        _validate_backup(backup)

    assert caught.value.code == "backup_not_fresh"


def test_valid_backup_returns_only_path_free_audit_evidence(tmp_path: Path) -> None:
    backup = _write_backup(tmp_path / "valid")

    evidence = _validate_backup(backup)

    payload = evidence.model_dump(mode="json")
    assert evidence.validation_passed is True
    assert evidence.database_name == PRODUCTION_DATABASE
    assert evidence.sha256 == backup.sha256
    assert evidence.collection_counts == AUTHORITATIVE_SNAPSHOT_COUNTS
    assert evidence.legacy_aggregate_sha256 == backup.legacy_aggregate_sha256
    assert evidence.media_aggregate_sha256 == backup.media_aggregate_sha256
    assert evidence.media_file_count == backup.media_file_count
    assert evidence.file_mode == "0600"
    assert evidence.parent_mode == "0700"
    assert str(backup.path.parent) not in json.dumps(payload)


def test_production_engine_happy_path_uses_only_fake_database(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
) -> None:
    backup = _write_backup(
        tmp_path / "happy",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    assert backup.media_file_count == 15
    assert (
        backup.media_aggregate_sha256
        == "dd4c7eda2d9b269aa84a77b29dfc0fe6cd51cc5751b9d781c49250d1123851b9"
    )
    authorization = _production_authorization(backup)
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)

    result = BootstrapEngine(database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )

    assert result.outcome == ApplyOutcome.APPLIED
    assert result.target_database == PRODUCTION_DATABASE
    assert result.sources_created == 16
    assert result.references_created == 20
    assert database["sources"].count_documents({}) == 16
    assert database["references"].count_documents({}) == 20
    assert database[MANIFEST_COLLECTION].count_documents({}) == 1
    manifest_document = database.snapshot((MANIFEST_COLLECTION,))[MANIFEST_COLLECTION][0]
    backup_evidence = manifest_document["production_backup_evidence"]
    assert backup_evidence["sha256"] == backup.sha256
    assert backup_evidence["legacy_aggregate_sha256"] == backup.legacy_aggregate_sha256
    assert backup_evidence["media_aggregate_sha256"] == backup.media_aggregate_sha256
    assert backup_evidence["media_file_count"] == backup.media_file_count
    assert backup_evidence["file_name"] == backup.path.name
    assert str(backup.path.parent) not in json.dumps(backup_evidence, default=str)
    assert database.forbidden_events == ()


def test_production_first_apply_rechecks_physical_catalog_absence_at_write_boundary(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = _write_backup(
        tmp_path / "catalog-appears-at-boundary",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    authorization = _production_authorization(backup)
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)
    original_revalidate = bootstrap_module.revalidate_production_authorization
    calls = 0

    def materialize_sources_on_second_revalidation(value: ApplyAuthorization):
        nonlocal calls
        calls += 1
        result = original_revalidate(value)
        if calls == 2:
            database._materialize("sources")
        return result

    monkeypatch.setattr(
        bootstrap_module,
        "revalidate_production_authorization",
        materialize_sources_on_second_revalidation,
    )

    result = BootstrapEngine(database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )

    assert result.outcome == ApplyOutcome.BLOCKED
    assert result.manifest_state is None
    assert calls == 2
    assert database.has_collection("sources")
    assert not database.has_collection(MANIFEST_COLLECTION)
    assert database.write_attempt_events == ()


def test_stale_backup_is_blocked_for_first_apply_but_same_evidence_can_resume(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
) -> None:
    stale_backup = _write_backup(
        tmp_path / "stale-first",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
        age=timedelta(days=7),
    )
    stale_evidence = validate_production_backup(
        stale_backup.path,
        backup_sha=stale_backup.sha256,
        confirm_backup_sha=stale_backup.sha256,
        write_freeze_at=stale_backup.write_freeze_at,
        require_fresh=False,
    )
    assert stale_evidence.fresh is False
    stale_authorization = ApplyAuthorization(
        target_database=PRODUCTION_DATABASE,
        allow_production_write=True,
        confirmed_database=PRODUCTION_DATABASE,
        confirm_production_phrase=PRODUCTION_CONFIRMATION_PHRASE,
        expected_zip_sha=AUTHORITATIVE_ZIP_SHA256,
        expected_plan_sha=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        production_backup=stale_evidence,
        production_backup_path=stale_backup.path,
        production_backup_sha=stale_backup.sha256,
        confirm_production_backup_sha=stale_backup.sha256,
        write_freeze_at=stale_backup.write_freeze_at,
    )
    forged_fresh_evidence = stale_evidence.model_copy(update={"fresh": True})
    stale_authorization = stale_authorization.model_copy(
        update={"production_backup": forged_fresh_evidence}
    )
    untouched = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)

    blocked = BootstrapEngine(untouched).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=stale_authorization,
    )

    assert blocked.outcome == ApplyOutcome.BLOCKED
    assert untouched.write_events == ()

    fresh_backup = _write_backup(
        tmp_path / "fresh-then-aged",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    fresh_authorization = _production_authorization(fresh_backup)
    applied_database = FakeDatabase(
        PRODUCTION_DATABASE,
        authoritative_bundle.export.collections,
    )
    assert (
        BootstrapEngine(applied_database)
        .apply(
            export=authoritative_bundle.export,
            plan=authoritative_bundle.plan,
            decisions=authoritative_bundle.decisions,
            authorization=fresh_authorization,
        )
        .outcome
        == ApplyOutcome.APPLIED
    )
    aged_evidence = fresh_authorization.production_backup.model_copy(update={"fresh": False})
    resume_authorization = fresh_authorization.model_copy(
        update={"production_backup": aged_evidence}
    )
    applied_database.clear_events()

    resumed = BootstrapEngine(applied_database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=resume_authorization,
    )

    assert resumed.outcome == ApplyOutcome.ALREADY_APPLIED
    assert applied_database.write_events == ()


def test_production_cli_runs_full_fake_engine_and_second_apply_is_noop(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backup = _write_backup(
        tmp_path / "cli-happy",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        decisions_json(authoritative_bundle.decisions),
        encoding="utf-8",
    )
    decisions_path.chmod(0o600)
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)
    factory = FakeMongoClientFactory({PRODUCTION_DATABASE: database})
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: SimpleNamespace(mongo_uri="mongodb://fake.invalid:27017"),
    )
    arguments = _replace_option(
        _replace_option(
            _production_cli_arguments(backup),
            "--input-zip",
            str(REAL_ZIP),
        ),
        "--decisions",
        str(decisions_path),
    )
    arguments.extend(("--output-format", "json"))

    assert migration_cli.main(arguments, client_factory=factory) == migration_cli.EXIT_OK
    first = json.loads(capsys.readouterr().out)
    assert first["outcome"] == "applied"
    assert first["sources_created"] == 16
    assert first["references_created"] == 20
    database.clear_events()

    assert migration_cli.main(arguments, client_factory=factory) == migration_cli.EXIT_OK
    second = json.loads(capsys.readouterr().out)
    assert second["outcome"] == "already_applied"
    assert second["sources_created"] == 0
    assert second["references_created"] == 0
    assert database.write_events == ()
    assert database.forbidden_events == ()


def test_engine_revalidates_backup_before_any_database_operation(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
) -> None:
    backup = _write_backup(
        tmp_path / "changed-before-engine",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    authorization = _production_authorization(backup)
    backup.path.write_bytes(backup.path.read_bytes() + b"changed-after-cli-validation")
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)

    result = BootstrapEngine(database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )

    assert result.outcome == ApplyOutcome.BLOCKED
    assert database.events == ()
    assert database.write_attempt_events == ()


def test_failed_resume_does_not_mutate_manifest_when_final_backup_reread_fails(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = _write_backup(
        tmp_path / "resume-revalidation",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    authorization = _production_authorization(backup)
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)

    def interrupt_after_manifest(label: str, _ordinal: int | None) -> None:
        if label == "manifest_prepared":
            raise RuntimeError("simulated interruption after durable manifest")

    interrupted = BootstrapEngine(database, checkpoint=interrupt_after_manifest).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )
    assert interrupted.outcome == ApplyOutcome.FAILED
    manifest_before = database.snapshot((MANIFEST_COLLECTION,))
    database.clear_events()
    calls = 0

    def fail_second_revalidation(value: ApplyAuthorization) -> ApplyAuthorization:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ProductionBackupRevalidationError(
                "backup_changed",
                "The production backup changed before the write boundary.",
            )
        return value

    monkeypatch.setattr(
        bootstrap_module,
        "revalidate_production_authorization",
        fail_second_revalidation,
    )

    resumed = BootstrapEngine(database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )

    assert calls == 2
    assert resumed.outcome == ApplyOutcome.BLOCKED
    assert database.snapshot((MANIFEST_COLLECTION,)) == manifest_before
    assert database.write_events == ()


def test_backup_crossing_freshness_boundary_before_first_write_is_blocked(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = _write_backup(
        tmp_path / "freshness-boundary",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    authorization = _production_authorization(backup)
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)
    calls = 0

    def age_on_second_read(value: ApplyAuthorization) -> ApplyAuthorization:
        nonlocal calls
        calls += 1
        assert value.production_backup is not None
        observed = value.production_backup.model_copy(update={"fresh": calls == 1})
        return value.model_copy(update={"production_backup": observed})

    monkeypatch.setattr(
        bootstrap_module,
        "revalidate_production_authorization",
        age_on_second_read,
    )

    result = BootstrapEngine(database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )

    assert calls == 2
    assert result.outcome == ApplyOutcome.BLOCKED
    assert database.write_events == ()


def test_production_engine_blocks_live_drift_before_any_write(
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
) -> None:
    backup = _write_backup(
        tmp_path / "drift",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    authorization = _production_authorization(backup)
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)
    first = authoritative_bundle.export.collections["concepts"][0]

    def mutate_between_snapshots(
        fake: FakeDatabase,
        _collection: str | None,
        _details: dict[str, Any],
    ) -> None:
        assert fake.external_update_one(
            "concepts",
            {"id": first["id"], "source": first["source"]},
            {"__production_gate_drift": True},
        )

    failpoint = database.add_failpoint(
        "list_collection_names",
        occurrence=3,
        callback=mutate_between_snapshots,
    )

    result = BootstrapEngine(database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )

    assert failpoint.fired is True
    assert result.outcome == ApplyOutcome.BLOCKED
    assert database.write_events == ()
    assert not database.has_collection(MANIFEST_COLLECTION)


@pytest.mark.parametrize("collection_name", ["sources", "references", MANIFEST_COLLECTION])
def test_first_production_apply_blocks_physically_preexisting_catalog_collections(
    collection_name: str,
    authoritative_bundle: _AuthoritativeBundle,
    tmp_path: Path,
) -> None:
    backup = _write_backup(
        tmp_path / f"preexisting-{collection_name}",
        collections=authoritative_bundle.export.collections,
        media_files=authoritative_bundle.media_files,
    )
    authorization = _production_authorization(backup)
    database = FakeDatabase(PRODUCTION_DATABASE, authoritative_bundle.export.collections)
    database.seed_collection(collection_name, ())

    result = BootstrapEngine(database).apply(
        export=authoritative_bundle.export,
        plan=authoritative_bundle.plan,
        decisions=authoritative_bundle.decisions,
        authorization=authorization,
    )

    assert result.outcome == ApplyOutcome.BLOCKED
    assert database.write_events == ()
    if collection_name != MANIFEST_COLLECTION:
        assert not database.has_collection(MANIFEST_COLLECTION)


def test_existing_isolated_authorization_remains_valid_without_production_fields() -> None:
    authorization = ApplyAuthorization(
        target_database=ISOLATED_DATABASE,
        allow_isolated_write=True,
        confirmed_database=ISOLATED_DATABASE,
        expected_zip_sha=AUTHORITATIVE_ZIP_SHA256,
        expected_plan_sha=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
    )

    assert validate_apply_authorization(authorization) is authorization


def test_apply_status_allows_explicit_read_only_mathv0_without_write_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase(PRODUCTION_DATABASE, {"concepts": ()})
    factory = FakeMongoClientFactory({PRODUCTION_DATABASE: database})
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: SimpleNamespace(mongo_uri="mongodb://fake.invalid:27017"),
    )

    result = migration_cli.main(
        [
            "apply-status",
            "--database",
            PRODUCTION_DATABASE,
            "--allow-live-read",
            "--output-format",
            "json",
        ],
        client_factory=factory,
    )

    assert result == migration_cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["manifest_count"] == 0
    assert database.write_events == ()


def test_parser_has_no_force_skip_ignore_overwrite_drop_or_rollback_flags() -> None:
    parser = migration_cli.build_parser()
    subparser_action = next(
        action for action in parser._actions if getattr(action, "choices", None)
    )
    help_text = subparser_action.choices["apply"].format_help()

    for forbidden in (
        "--force",
        "--skip-preflight",
        "--ignore-drift",
        "--ignore-conflicts",
        "--overwrite",
        "--drop-existing",
        "--rollback-delete",
    ):
        assert forbidden not in help_text

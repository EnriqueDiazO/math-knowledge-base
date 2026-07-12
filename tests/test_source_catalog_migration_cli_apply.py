"""CLI isolation and dependency-injection tests for S1C2A commands."""

# ruff: noqa: D103

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from source_catalog_migration_fakes import FakeDatabase
from source_catalog_migration_fakes import FakeMongoClientFactory

from mathmongo.source_catalog_migration import cli as migration_cli
from mathmongo.source_catalog_migration.apply_result import ApplyOutcome
from mathmongo.source_catalog_migration.apply_result import ApplyResult
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_PLAN_SEMANTIC_SHA256
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_ZIP_SHA256
from mathmongo.source_catalog_migration.decisions import DecisionSet
from mathmongo.source_catalog_migration.decisions import DecisionValidationError
from mathmongo.source_catalog_migration.decisions import decisions_json
from mathmongo.source_catalog_migration.decisions import validate_decisions
from mathmongo.source_catalog_migration.manifest import ManifestError
from mathmongo.source_catalog_migration.manifest import ManifestExpectedCounts
from mathmongo.source_catalog_migration.manifest import ManifestIndexStatus
from mathmongo.source_catalog_migration.manifest import ManifestState
from mathmongo.source_catalog_migration.models import InputSnapshot
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_EXPECTATIONS
from mathmongo.source_catalog_migration.planner import build_plan
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export

TARGET = "MathV0_s1c2_validation_cli_test"
MIGRATION_ID = "mig_00000000-0000-4000-8000-000000000001"
REAL_ZIP = Path(__file__).resolve().parents[1] / "mathkb_export_20260712_073927.zip"


def _snapshot() -> InputSnapshot:
    return InputSnapshot.model_construct(
        database_name="MathV0",
        sha256=AUTHORITATIVE_ZIP_SHA256,
    )


def _plan() -> MigrationPlan:
    return MigrationPlan.model_construct(
        input_snapshot=_snapshot(),
        semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        reference_candidates=(),
        weak_reference_suggestions=(),
        review_items=(),
    )


def _export() -> Any:
    return SimpleNamespace(
        input_snapshot=_snapshot(),
        input_identity=object(),
    )


def _decisions() -> DecisionSet:
    return DecisionSet(
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        accept_all_safe_exact=True,
        accepted_reference_candidates=(),
        weak_suggestion_decisions={},
        locator_review_decisions={},
    )


def _result(outcome: ApplyOutcome) -> ApplyResult:
    return ApplyResult(
        outcome=outcome,
        target_database=TARGET,
        migration_id=MIGRATION_ID,
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        decisions_sha256="c" * 64,
        expected_sources=16,
        sources_created=16 if outcome == ApplyOutcome.APPLIED else 0,
        sources_identical=16 if outcome == ApplyOutcome.IDENTICAL else 0,
        expected_references=20,
        references_created=20 if outcome == ApplyOutcome.APPLIED else 0,
        references_identical=20 if outcome == ApplyOutcome.IDENTICAL else 0,
        manifest_state="applied" if outcome != ApplyOutcome.FAILED else "failed",
        invariants_passed=outcome
        not in {ApplyOutcome.BLOCKED, ApplyOutcome.CONFLICT, ApplyOutcome.FAILED},
        next_action="Inspect the isolated result.",
    )


def _apply_arguments(*extra: str) -> list[str]:
    return [
        "apply",
        "--input-zip",
        "authoritative.zip",
        "--decisions",
        "decisions.json",
        "--database",
        TARGET,
        "--allow-isolated-write",
        "--confirm-database",
        TARGET,
        "--expected-zip-sha",
        AUTHORITATIVE_ZIP_SHA256,
        "--expected-plan-sha",
        AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        *extra,
    ]


class _Admin:
    def __init__(self, client: _Client) -> None:
        self.client = client

    def command(self, command: str) -> dict[str, int]:
        assert command == "ping"
        self.client.operations.append("ping")
        return {"ok": 1}


class _Database:
    def __init__(self, name: str = TARGET) -> None:
        self.name = name


class _Client:
    def __init__(self, database: _Database | None = None) -> None:
        self.database = database or _Database()
        self.admin = _Admin(self)
        self.operations: list[str] = []
        self.closed = False

    def list_database_names(self) -> list[str]:
        self.operations.append("list_database_names")
        return [self.database.name]

    def get_database(self, name: str) -> _Database:
        self.operations.append(f"get_database:{name}")
        return self.database

    def close(self) -> None:
        self.closed = True


class _ClientFactory:
    def __init__(self, client: _Client | None = None) -> None:
        self.client = client or _Client()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, uri: str, **kwargs: Any) -> _Client:
        self.calls.append((uri, kwargs))
        return self.client


def _patch_apply_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        migration_cli, "_load_authoritative_plan", lambda _args: (_export(), _plan())
    )
    monkeypatch.setattr(migration_cli, "load_decisions", lambda _path: _decisions())
    monkeypatch.setattr(migration_cli, "validate_authoritative_plan", lambda *_args: object())
    monkeypatch.setattr(migration_cli, "verify_input_unchanged", lambda *_args: None)
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: SimpleNamespace(mongo_uri="mongodb://localhost:27017"),
    )


def test_parser_exposes_separate_write_gates_and_no_expansive_write_flags() -> None:
    parser = migration_cli.build_parser()
    subparser_action = next(
        action for action in parser._actions if getattr(action, "choices", None)
    )

    assert {"decisions-template", "apply-status", "apply"} <= set(subparser_action.choices)
    apply_help = subparser_action.choices["apply"].format_help()
    assert "--allow-isolated-write" in apply_help
    assert "--allow-production-write" in apply_help
    assert "--confirm-production-phrase" in apply_help
    assert "--backup-path" in apply_help
    assert "--backup-sha" in apply_help
    assert "--confirm-backup-sha" in apply_help
    assert "--force" not in apply_help
    for forbidden in (
        "--skip-preflight",
        "--skip-drift-check",
        "--ignore-drift",
        "--ignore-conflicts",
        "--overwrite",
        "--drop-existing",
        "--rollback-delete",
    ):
        assert forbidden not in apply_help
    assert "--database-name" not in apply_help


def test_decisions_template_always_labels_snapshot_mathv0_and_never_accesses_config_or_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export = _export()
    plan = _plan()
    observed_database_names: list[str] = []
    written: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration_cli,
        "read_legacy_export",
        lambda _path, **kwargs: observed_database_names.append(kwargs["database_name"]) or export,
    )
    monkeypatch.setattr(migration_cli, "build_inventory", lambda _export: object())
    monkeypatch.setattr(migration_cli, "build_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(migration_cli, "validate_plan", lambda *_args: None)
    monkeypatch.setattr(migration_cli, "verify_input_unchanged", lambda *_args: None)
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: (_ for _ in ()).throw(AssertionError("template must not read config")),
    )
    monkeypatch.setattr(
        migration_cli,
        "write_report",
        lambda path, content, **_kwargs: written.append((str(path), content)),
    )

    result = migration_cli.main(
        [
            "decisions-template",
            "--input-zip",
            "authoritative.zip",
            "--output",
            str(tmp_path / "decisions.json"),
        ],
        client_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("template must not construct a client")
        ),
    )

    assert result == migration_cli.EXIT_OK
    assert observed_database_names == ["MathV0"]
    payload = json.loads(written[0][1])
    assert payload["accept_all_safe_exact"] is None
    template = DecisionSet.model_validate(payload)
    with pytest.raises(DecisionValidationError):
        validate_decisions(template, plan)


@pytest.mark.parametrize(
    "replacement",
    [
        ("--database", "MathV0"),
        ("--expected-zip-sha", "d" * 64),
        ("--expected-plan-sha", "e" * 64),
        ("--confirm-database", TARGET + "_different"),
    ],
)
def test_invalid_apply_authorization_fails_before_zip_config_or_client(
    replacement: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _apply_arguments()
    option, value = replacement
    arguments[arguments.index(option) + 1] = value
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
    calls: list[str] = []

    result = migration_cli.main(
        arguments,
        client_factory=lambda *_args, **_kwargs: calls.append("client"),
    )

    assert result == migration_cli.EXIT_APPLY_BLOCKED
    assert calls == []


def test_apply_without_write_flag_retains_usage_exit_before_input_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        migration_cli,
        "read_legacy_export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not read ZIP")),
    )
    arguments = [item for item in _apply_arguments() if item != "--allow-isolated-write"]

    assert migration_cli.main(arguments) == migration_cli.EXIT_USAGE


def test_apply_uses_injected_client_and_engine_after_all_pure_validation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_apply_inputs(monkeypatch)
    factory = _ClientFactory()
    engine_calls: list[tuple[_Database, dict[str, Any]]] = []

    class Engine:
        def __init__(self, database: _Database) -> None:
            self.database = database

        def apply(self, **kwargs: Any) -> ApplyResult:
            engine_calls.append((self.database, kwargs))
            return _result(ApplyOutcome.APPLIED)

    result = migration_cli.main(
        [*_apply_arguments(), "--output-format", "json"],
        client_factory=factory,
        engine_factory=Engine,
    )

    assert result == migration_cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["outcome"] == "applied"
    assert factory.calls == [
        (
            "mongodb://localhost:27017",
            {
                "serverSelectionTimeoutMS": 2_500,
                "connectTimeoutMS": 2_500,
                "socketTimeoutMS": 10_000,
                "retryWrites": False,
                "appname": "MathMongo-S1C2P-bootstrap",
            },
        )
    ]
    assert factory.client.closed is True
    database, call = engine_calls[0]
    assert database.name == TARGET
    assert call["export"].input_snapshot.database_name == "MathV0"
    assert call["authorization"].target_database == TARGET
    assert call["decisions"] == _decisions()


def test_post_apply_verification_failure_requires_apply_status_before_retry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_apply_inputs(monkeypatch)

    class Engine:
        def __init__(self, _database: _Database) -> None:
            pass

        def apply(self, **_kwargs: Any) -> ApplyResult:
            return _result(ApplyOutcome.APPLIED)

    verifications = 0

    def fail_after_engine(*_args: Any) -> None:
        nonlocal verifications
        verifications += 1
        if verifications == 2:
            raise OSError("changed after apply")

    monkeypatch.setattr(migration_cli, "verify_input_unchanged", fail_after_engine)

    result = migration_cli.main(
        _apply_arguments(),
        client_factory=_ClientFactory(),
        engine_factory=Engine,
    )

    assert result == migration_cli.EXIT_ERROR
    error = capsys.readouterr().err
    assert "apply may have completed" in error
    assert "apply-status" in error


def test_apply_cli_runs_real_engine_only_against_injected_fake_and_second_run_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if not REAL_ZIP.is_file():
        pytest.skip("The approved untracked authoritative ZIP is not present")
    export = read_legacy_export(REAL_ZIP, database_name="MathV0", fail_on_input_change=True)
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
    decision_path = tmp_path / "decisions.json"
    decision_path.write_text(decisions_json(decisions), encoding="utf-8")
    database = FakeDatabase(TARGET, export.collections)
    factory = FakeMongoClientFactory({TARGET: database})
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: SimpleNamespace(mongo_uri="mongodb://fake.invalid:27017"),
    )
    arguments = [
        "apply",
        "--input-zip",
        str(REAL_ZIP),
        "--decisions",
        str(decision_path),
        "--database",
        TARGET,
        "--allow-isolated-write",
        "--confirm-database",
        TARGET,
        "--expected-zip-sha",
        AUTHORITATIVE_ZIP_SHA256,
        "--expected-plan-sha",
        AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        "--output-format",
        "json",
    ]

    assert migration_cli.main(arguments, client_factory=factory) == migration_cli.EXIT_OK
    first = json.loads(capsys.readouterr().out)
    assert first["outcome"] == "applied"
    assert first["sources_created"] == 16
    assert first["references_created"] == 20
    assert database.forbidden_events == ()

    database.clear_events()
    assert migration_cli.main(arguments, client_factory=factory) == migration_cli.EXIT_OK
    second = json.loads(capsys.readouterr().out)
    assert second["outcome"] == "already_applied"
    assert second["sources_identical"] == 16
    assert second["references_identical"] == 20
    assert database.write_attempt_events == ()


@pytest.mark.parametrize(
    ("outcome", "expected_exit"),
    [
        (ApplyOutcome.PREPARED, migration_cli.EXIT_OK),
        (ApplyOutcome.RESUMED, migration_cli.EXIT_OK),
        (ApplyOutcome.ALREADY_APPLIED, migration_cli.EXIT_OK),
        (ApplyOutcome.IDENTICAL, migration_cli.EXIT_OK),
        (ApplyOutcome.BLOCKED, migration_cli.EXIT_APPLY_BLOCKED),
        (ApplyOutcome.CONFLICT, migration_cli.EXIT_APPLY_CONFLICT),
        (ApplyOutcome.FAILED, migration_cli.EXIT_ERROR),
    ],
)
def test_apply_outcomes_have_stable_exit_codes(
    outcome: ApplyOutcome,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_apply_inputs(monkeypatch)

    class Engine:
        def __init__(self, _database: _Database) -> None:
            pass

        def apply(self, **_kwargs: Any) -> ApplyResult:
            return _result(outcome)

    assert (
        migration_cli.main(
            _apply_arguments(),
            client_factory=_ClientFactory(),
            engine_factory=Engine,
        )
        == expected_exit
    )


def test_apply_status_requires_read_authorization_before_config_or_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: (_ for _ in ()).throw(AssertionError("must not read config")),
    )
    calls: list[str] = []

    result = migration_cli.main(
        ["apply-status", "--database", TARGET],
        client_factory=lambda *_args, **_kwargs: calls.append("client"),
    )

    assert result == migration_cli.EXIT_USAGE
    assert calls == []


def test_apply_status_is_read_only_bounded_and_omits_final_id_maps(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        migration_cli,
        "resolve_config",
        lambda: SimpleNamespace(mongo_uri="mongodb://localhost:27017"),
    )
    factory = _ClientFactory()
    now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    manifest = SimpleNamespace(
        manifest_key="manifest_key_hash",
        migration_id=MIGRATION_ID,
        state=ManifestState.PREPARED,
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        planner_version="s1c1-v1",
        decisions_sha256="c" * 64,
        expected_counts=ManifestExpectedCounts(
            concepts=186,
            source_candidates=16,
            concepts_with_reference=145,
            concepts_without_reference=41,
            reference_candidates=20,
            bindings=186,
            conflicts=0,
            review_items=5,
            weak_suggestions=2,
        ),
        sources_created=0,
        sources_identical=0,
        references_created=0,
        references_identical=0,
        indexes_status=ManifestIndexStatus(),
        invariant_hashes_before=None,
        invariant_hashes_after=None,
        errors=(
            ManifestError(
                code="unsafe_external_error",
                message=(
                    "mongodb://alice:secret@example.test/db password=hidden /home/alice/private.txt"
                ),
                occurred_at=now,
                state=ManifestState.PREPARED,
                attempt=0,
            ),
        ),
        attempts=0,
        resume_count=0,
        created_at=now,
        started_at=None,
        completed_at=None,
        last_updated_at=now,
        source_id_map={"candidate": "must-not-leak"},
        reference_id_map={"candidate": "must-not-leak"},
    )
    stores: list[_Database] = []

    class Store:
        def __init__(self, database: _Database) -> None:
            stores.append(database)

        def find_for_target(self, target: str) -> tuple[Any, ...]:
            assert target == TARGET
            return (manifest,)

    result = migration_cli.main(
        [
            "apply-status",
            "--database",
            TARGET,
            "--allow-live-read",
            "--output-format",
            "json",
        ],
        client_factory=factory,
        manifest_store_factory=Store,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == migration_cli.EXIT_OK
    assert payload["manifest_count"] == 1
    assert payload["manifests"][0]["state"] == "prepared"
    assert "source_id_map" not in payload["manifests"][0]
    assert "reference_id_map" not in payload["manifests"][0]
    assert "must-not-leak" not in json.dumps(payload)
    serialized = json.dumps(payload)
    assert "alice" not in serialized
    assert "secret" not in serialized
    assert "hidden" not in serialized
    assert "/home/" not in serialized
    assert "<redacted" in payload["manifests"][0]["errors"][0]["message"]
    assert stores == [factory.client.database]
    assert factory.client.closed is True

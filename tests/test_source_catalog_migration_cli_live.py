"""CLI, private report output, and strict read-only live comparison tests for S1C1."""

# ruff: noqa: D101,D102,D103

from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
import sys
import zipfile
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import pydantic
import pymongo
import pytest

from mathmongo.source_catalog_migration import cli as migration_cli
from mathmongo.source_catalog_migration import report as migration_report
from mathmongo.source_catalog_migration.live_compare import LIVE_DATABASE_NAME
from mathmongo.source_catalog_migration.live_compare import RELEVANT_COLLECTIONS
from mathmongo.source_catalog_migration.live_compare import LiveComparisonError
from mathmongo.source_catalog_migration.live_compare import LiveReadNotAllowedError
from mathmongo.source_catalog_migration.live_compare import compare_live
from mathmongo.source_catalog_migration.models import CollectionState
from mathmongo.source_catalog_migration.models import CoupledCollections
from mathmongo.source_catalog_migration.models import InputSnapshot
from mathmongo.source_catalog_migration.models import LiveComparison
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.models import PlanInvariants
from mathmongo.source_catalog_migration.models import PlanSummary
from mathmongo.source_catalog_migration.models import StatusReport
from mathmongo.source_catalog_migration.models import ZipSafetyReport
from mathmongo.source_catalog_migration.report import ReportOutputError
from mathmongo.source_catalog_migration.report import write_report
from mathmongo.source_catalog_migration.zip_reader import FileIdentity
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = datetime(2026, 7, 12, 7, 39, 27, tzinfo=timezone.utc)
SAMPLE_CONCEPT = {
    "_id": "000000000000000000000001",
    "id": "concept-1",
    "source": "Exact_Source",
    "referencia": {
        "tipo_referencia": "Libro",
        "autor": "Author",
        "fuente": "Title",
        "anio": 2020,
        "paginas": "iv-v",
    },
}


def _collection_documents(
    *,
    concept: dict[str, Any] | None = None,
) -> dict[str, tuple[dict[str, Any], ...]]:
    collections = {name: () for name in RELEVANT_COLLECTIONS}
    collections["concepts"] = (copy.deepcopy(concept or SAMPLE_CONCEPT),)
    return collections


def _input_snapshot(
    collections: dict[str, tuple[dict[str, Any], ...]] | None = None,
) -> InputSnapshot:
    collection_data = collections or _collection_documents()
    return InputSnapshot(
        filename="synthetic.zip",
        sha256="a" * 64,
        size_bytes=1024,
        modified_at=FIXED_TIME,
        exported_at=FIXED_TIME,
        database_name="Synthetic",
        counts={name: len(documents) for name, documents in collection_data.items()},
        format_name="mathkb_legacy_export",
        format_version="unversioned",
        format_version_source="layout_inference",
        members=(),
    )


def _zip_safety() -> ZipSafetyReport:
    return ZipSafetyReport(
        validated=True,
        member_count=2,
        file_count=2,
        total_uncompressed_bytes=512,
        total_compressed_bytes=512,
        maximum_compression_ratio=1.0,
        base_directory="synthetic",
    )


def _summary() -> PlanSummary:
    return PlanSummary(
        concept_count=1,
        source_candidate_count=1,
        embedded_reference_count=1,
        missing_reference_count=0,
        reference_candidate_count=1,
        binding_count=1,
        conflict_count=0,
        review_item_count=0,
    )


def _coupled_collections() -> CoupledCollections:
    return CoupledCollections(
        consumers=(),
        concept_counterparts_in_latex_documents=0,
        orphan_latex_documents=0,
        relations=0,
        knowledge_graph_maps=0,
        media_assets=0,
        latex_notes=0,
    )


def _invariants() -> PlanInvariants:
    return PlanInvariants(
        concept_count_matches=True,
        source_count_matches=True,
        reference_partition_matches=True,
        binding_count_matches=True,
        unique_legacy_keys=True,
        unique_binding_keys=True,
        no_concepts_lost=True,
        no_concepts_duplicated=True,
        locators_excluded_from_bibliographic_fingerprints=True,
        metadata_conflicts_not_merged=True,
        no_final_domain_ids=True,
        zip_unchanged=True,
    )


def _plan(
    collections: dict[str, tuple[dict[str, Any], ...]] | None = None,
) -> MigrationPlan:
    return MigrationPlan(
        input_snapshot=_input_snapshot(collections),
        summary=_summary(),
        source_candidates=(),
        reference_candidates=(),
        concept_bindings=(),
        review_items=(),
        conflicts=(),
        coupled_collections=_coupled_collections(),
        invariants=_invariants(),
        generated_at=FIXED_TIME,
        semantic_sha256="b" * 64,
    )


def _status() -> StatusReport:
    return StatusReport(
        input_snapshot=_input_snapshot(),
        zip_safety=_zip_safety(),
        summary=_summary(),
        coupled_collections=_coupled_collections(),
        ready_to_plan=True,
    )


def _loaded_export(
    collections: dict[str, tuple[dict[str, Any], ...]] | None = None,
) -> LoadedLegacyExport:
    collection_data = collections or _collection_documents()
    return LoadedLegacyExport(
        input_snapshot=_input_snapshot(collection_data),
        zip_safety=_zip_safety(),
        metadata={
            "collections": {name: len(documents) for name, documents in collection_data.items()},
            "media_files": {},
        },
        collections=collection_data,
        member_sha256={},
        input_identity=FileIdentity(
            device=1,
            inode=2,
            size_bytes=1024,
            modified_ns=int(FIXED_TIME.timestamp() * 1_000_000_000),
            sha256="a" * 64,
        ),
    )


def _patch_cli_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    compare=None,
) -> tuple[LoadedLegacyExport, MigrationPlan, StatusReport]:
    export = _loaded_export()
    plan = _plan(export.collections)
    status = _status()
    monkeypatch.setattr(migration_cli, "read_legacy_export", lambda *_args, **_kwargs: export)
    monkeypatch.setattr(migration_cli, "authoritative_expectations", lambda _name: object())
    monkeypatch.setattr(migration_cli, "build_inventory", lambda _export: object())
    monkeypatch.setattr(migration_cli, "build_status", lambda *_args, **_kwargs: status)
    monkeypatch.setattr(migration_cli, "build_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(migration_cli, "validate_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        migration_cli,
        "verify_input_unchanged",
        lambda *_args, **_kwargs: None,
    )
    if compare is not None:
        monkeypatch.setattr(migration_cli, "compare_live", compare)
    return export, plan, status


@pytest.mark.parametrize(
    ("command", "format_arguments", "expected_text", "json_key"),
    [
        ("status", [], "MathMongo S1C1 legacy Source Catalog status", None),
        ("status", ["--output-format", "json"], None, "ready_to_plan"),
        (
            "dry-run",
            ["--output-format", "text"],
            "MathMongo S1C1 legacy Source Catalog dry-run",
            None,
        ),
        ("dry-run", ["--output-format", "json"], None, "semantic_sha256"),
    ],
)
def test_cli_status_and_dry_run_render_stdout_without_writes_or_live_access(
    command: str,
    format_arguments: list[str],
    expected_text: str | None,
    json_key: str | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli_pipeline(monkeypatch)
    monkeypatch.setattr(
        migration_cli,
        "write_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stdout mode must not write a report")
        ),
    )
    monkeypatch.setattr(
        migration_cli,
        "compare_live",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("status/dry-run must not access live MongoDB")
        ),
    )

    result = migration_cli.main([command, "--input-zip", "synthetic.zip", *format_arguments])

    captured = capsys.readouterr()
    assert result == migration_cli.EXIT_OK
    assert captured.err == ""
    if json_key is not None:
        payload = json.loads(captured.out)
        assert json_key in payload
        assert payload["input_snapshot"]["filename"] == "synthetic.zip"
    else:
        assert expected_text in captured.out


def test_apply_is_rejected_before_input_or_output_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        migration_cli,
        "read_legacy_export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("apply must be rejected before reading the ZIP")
        ),
    )

    result = migration_cli.main(["apply", "--input-zip", "synthetic.zip"])

    captured = capsys.readouterr()
    assert result == migration_cli.EXIT_USAGE
    assert captured.out == ""
    assert "requires either the isolated-write" in captured.err
    assert "separately guarded production-write authorization" in captured.err
    assert "not available" not in captured.err


@pytest.mark.parametrize(
    ("database_name", "allow_live_read", "error_type", "message"),
    [
        ("MathV0", False, LiveReadNotAllowedError, "--allow-live-read"),
        ("mathmongo", True, LiveComparisonError, "only the explicit database MathV0"),
    ],
)
def test_compare_live_requires_authorization_and_exact_mathv0_before_client_creation(
    database_name: str,
    allow_live_read: bool,
    error_type: type[LiveComparisonError],
    message: str,
) -> None:
    factory_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def forbidden_factory(*args: Any, **kwargs: Any) -> None:
        factory_calls.append((args, kwargs))
        raise AssertionError("invalid compare-live input must not construct a Mongo client")

    export = _loaded_export()
    plan = _plan(export.collections)
    with pytest.raises(error_type, match=message):
        compare_live(
            export,
            plan,
            database_name=database_name,
            allow_live_read=allow_live_read,
            mongo_uri="mongodb://unused.example:27017",
            client_factory=forbidden_factory,
        )

    assert factory_calls == []


@pytest.mark.parametrize(
    ("arguments", "expected_message"),
    [
        (["--database", "MathV0"], "--allow-live-read"),
        (
            ["--database", "mathmongo", "--allow-live-read"],
            "only the explicit database MathV0",
        ),
    ],
)
def test_cli_compare_live_rejects_missing_permission_or_wrong_database(
    arguments: list[str],
    expected_message: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli_pipeline(monkeypatch)

    result = migration_cli.main(["compare-live", "--input-zip", "synthetic.zip", *arguments])

    captured = capsys.readouterr()
    assert result == migration_cli.EXIT_ERROR
    assert expected_message in captured.err
    assert captured.out == ""


def test_compare_live_rejects_a_non_mathv0_snapshot_label_before_reading_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        migration_cli,
        "read_legacy_export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid database label must fail before ZIP access")
        ),
    )

    result = migration_cli.main(
        [
            "compare-live",
            "--input-zip",
            "synthetic.zip",
            "--database",
            "MathV0",
            "--allow-live-read",
            "--database-name",
            "NotMathV0",
        ]
    )

    captured = capsys.readouterr()
    assert result == migration_cli.EXIT_ERROR
    assert "requires --database-name MathV0" in captured.err
    assert captured.out == ""


class _StrictReadOnlyCollection:
    _FORBIDDEN_OPERATIONS = {
        "aggregate",
        "bulk_write",
        "create_index",
        "create_indexes",
        "delete_many",
        "delete_one",
        "drop",
        "insert_many",
        "insert_one",
        "map_reduce",
        "rename",
        "replace_one",
        "update_many",
        "update_one",
    }

    def __init__(
        self,
        database: _StrictReadOnlyDatabase,
        name: str,
        documents: tuple[dict[str, Any], ...],
    ) -> None:
        self.database = database
        self.name = name
        self.documents = [copy.deepcopy(document) for document in documents]

    def count_documents(self, query: dict[str, Any], **kwargs: Any) -> int:
        assert query == {}
        assert kwargs == {"maxTimeMS": 10_000}
        self.database.read_operations.append(f"{self.name}.count_documents")
        return len(self.documents)

    def find(
        self,
        query: dict[str, Any],
        projection: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], ...]:
        assert query == {}
        assert projection is not None, "live reads must always supply a projection"
        if self.database.require_nonempty_projection:
            assert projection, "live reads must use a non-empty bounded projection"
        assert kwargs == {"limit": 10_001, "max_time_ms": 10_000}
        self.database.read_operations.append(f"{self.name}.find")
        return tuple(copy.deepcopy(self.documents))

    def list_indexes(self) -> tuple[dict[str, Any], ...]:
        self.database.read_operations.append(f"{self.name}.list_indexes")
        return ({"name": "_id_", "key": {"_id": 1}},)

    def __getattr__(self, name: str):
        if name not in self._FORBIDDEN_OPERATIONS:
            raise AttributeError(name)

        def reject(*_args: Any, **_kwargs: Any) -> None:
            self.database.write_attempts.append(f"{self.name}.{name}")
            raise AssertionError(f"unexpected MongoDB write operation: {self.name}.{name}")

        return reject


class _StrictReadOnlyDatabase:
    _FORBIDDEN_OPERATIONS = {
        "command",
        "create_collection",
        "drop_collection",
        "validate_collection",
    }

    def __init__(
        self,
        collections: dict[str, tuple[dict[str, Any], ...]],
        *,
        mutate_on_second_snapshot: bool = False,
        require_nonempty_projection: bool = False,
    ) -> None:
        self.name = LIVE_DATABASE_NAME
        self.read_operations: list[str] = []
        self.write_attempts: list[str] = []
        self.snapshot_calls = 0
        self.mutate_on_second_snapshot = mutate_on_second_snapshot
        self.require_nonempty_projection = require_nonempty_projection
        self.collections = {
            name: _StrictReadOnlyCollection(self, name, documents)
            for name, documents in collections.items()
        }

    def __getitem__(self, name: str) -> _StrictReadOnlyCollection:
        self.read_operations.append(f"database[{name}]")
        return self.collections[name]

    def list_collection_names(self) -> list[str]:
        self.snapshot_calls += 1
        self.read_operations.append("database.list_collection_names")
        if self.mutate_on_second_snapshot and self.snapshot_calls == 2:
            self.collections["concepts"].documents.append(
                {
                    "_id": "000000000000000000000002",
                    "id": "external-change",
                    "source": "External_Source",
                }
            )
        return sorted(self.collections)

    def __getattr__(self, name: str):
        if name not in self._FORBIDDEN_OPERATIONS:
            raise AttributeError(name)

        def reject(*_args: Any, **_kwargs: Any) -> None:
            self.write_attempts.append(f"database.{name}")
            raise AssertionError(f"unexpected MongoDB write operation: database.{name}")

        return reject


class _StrictAdmin:
    def __init__(self, client: _StrictReadOnlyClient) -> None:
        self.client = client

    def command(self, command: str | dict[str, int]) -> dict[str, int]:
        assert command in ("ping", {"ping": 1})
        self.client.read_operations.append("admin.ping")
        return {"ok": 1}


class _StrictReadOnlyClient:
    def __init__(self, database: _StrictReadOnlyDatabase) -> None:
        self.database = database
        self.admin = _StrictAdmin(self)
        self.read_operations: list[str] = []
        self.closed = False

    def list_database_names(self) -> list[str]:
        self.read_operations.append("client.list_database_names")
        return [LIVE_DATABASE_NAME]

    def get_database(self, name: str) -> _StrictReadOnlyDatabase:
        assert name == LIVE_DATABASE_NAME
        self.read_operations.append(f"client.get_database[{name}]")
        return self.database

    def close(self) -> None:
        self.closed = True


class _StrictClientFactory:
    def __init__(self, database: _StrictReadOnlyDatabase) -> None:
        self.client = _StrictReadOnlyClient(database)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, uri: str, **kwargs: Any) -> _StrictReadOnlyClient:
        self.calls.append((uri, dict(kwargs)))
        return self.client


def test_compare_live_uses_only_bounded_projected_reads_and_conservative_client_options() -> None:
    collections = _collection_documents()
    database = _StrictReadOnlyDatabase(
        collections,
        require_nonempty_projection=True,
    )
    factory = _StrictClientFactory(database)
    export = _loaded_export(collections)
    plan = _plan(collections)

    updated_plan, comparison = compare_live(
        export,
        plan,
        database_name=LIVE_DATABASE_NAME,
        allow_live_read=True,
        mongo_uri="mongodb://localhost:27017",
        client_factory=factory,
    )

    assert comparison.live_database_drift is False
    assert comparison.snapshot_drift is False
    assert comparison.writes_attempted == 0
    assert database.write_attempts == []
    assert factory.client.closed is True
    assert updated_plan.live_comparison == comparison
    assert factory.calls == [
        (
            "mongodb://localhost:27017",
            {
                "serverSelectionTimeoutMS": 2_500,
                "connectTimeoutMS": 2_500,
                "socketTimeoutMS": 10_000,
                "retryWrites": False,
                "appname": "MathMongo-S1C1-read-only",
            },
        )
    ]
    assert factory.client.read_operations == [
        "admin.ping",
        "client.list_database_names",
        "client.get_database[MathV0]",
    ]
    assert all(
        operation.endswith(("count_documents", "find", "list_indexes"))
        or operation.startswith("database")
        for operation in database.read_operations
    )


def test_compare_live_reports_database_drift_between_snapshots_without_writes() -> None:
    collections = _collection_documents()
    database = _StrictReadOnlyDatabase(
        collections,
        mutate_on_second_snapshot=True,
    )
    factory = _StrictClientFactory(database)
    export = _loaded_export(collections)

    _updated_plan, comparison = compare_live(
        export,
        _plan(collections),
        database_name=LIVE_DATABASE_NAME,
        allow_live_read=True,
        mongo_uri="mongodb://localhost:27017",
        client_factory=factory,
    )

    assert comparison.live_database_drift is True
    assert comparison.successful is False
    assert comparison.before != comparison.after
    assert comparison.snapshot_drift is False
    assert database.write_attempts == []
    assert factory.client.closed is True


def test_compare_live_preserves_zip_plan_and_reports_stable_snapshot_drift() -> None:
    zip_collections = _collection_documents()
    live_concept = copy.deepcopy(SAMPLE_CONCEPT)
    live_concept["source"] = "Different_Live_Source"
    live_collections = _collection_documents(concept=live_concept)
    database = _StrictReadOnlyDatabase(live_collections)
    factory = _StrictClientFactory(database)
    plan = _plan(zip_collections)

    updated_plan, comparison = compare_live(
        _loaded_export(zip_collections),
        plan,
        database_name=LIVE_DATABASE_NAME,
        allow_live_read=True,
        mongo_uri="mongodb://localhost:27017",
        client_factory=factory,
    )

    assert comparison.live_database_drift is False
    assert comparison.snapshot_drift is True
    assert comparison.concept_keys_match is False
    assert comparison.source_counts_match is False
    assert updated_plan.source_candidates == plan.source_candidates
    assert updated_plan.reference_candidates == plan.reference_candidates
    assert updated_plan.concept_bindings == plan.concept_bindings
    assert updated_plan.live_comparison == comparison
    assert database.write_attempts == []


def test_compare_live_detects_references_swapped_between_legacy_keys() -> None:
    first = copy.deepcopy(SAMPLE_CONCEPT)
    first["id"] = "first"
    first["referencia"]["fuente"] = "First work"
    second = copy.deepcopy(SAMPLE_CONCEPT)
    second["id"] = "second"
    second["referencia"]["fuente"] = "Second work"
    zip_collections = {name: () for name in RELEVANT_COLLECTIONS}
    zip_collections["concepts"] = (first, second)
    live_first = copy.deepcopy(first)
    live_second = copy.deepcopy(second)
    live_first["referencia"], live_second["referencia"] = (
        live_second["referencia"],
        live_first["referencia"],
    )
    live_collections = dict(zip_collections)
    live_collections["concepts"] = (live_first, live_second)
    database = _StrictReadOnlyDatabase(live_collections)

    _updated_plan, comparison = compare_live(
        _loaded_export(zip_collections),
        _plan(zip_collections),
        database_name=LIVE_DATABASE_NAME,
        allow_live_read=True,
        mongo_uri="mongodb://localhost:27017",
        client_factory=_StrictClientFactory(database),
    )

    assert comparison.concept_keys_match is True
    assert comparison.reference_fingerprints_match is False
    assert comparison.snapshot_drift is True


class _FutureFieldMutationDatabase(_StrictReadOnlyDatabase):
    def list_collection_names(self) -> list[str]:
        names = super().list_collection_names()
        if self.snapshot_calls == 2:
            self.collections["concepts"].documents[0]["future_legacy_field"] = "changed"
        return names


def test_compare_live_fingerprint_covers_unknown_future_fields() -> None:
    collections = _collection_documents()
    database = _FutureFieldMutationDatabase(collections)

    _updated_plan, comparison = compare_live(
        _loaded_export(collections),
        _plan(collections),
        database_name=LIVE_DATABASE_NAME,
        allow_live_read=True,
        mongo_uri="mongodb://localhost:27017",
        client_factory=_StrictClientFactory(database),
    )

    assert comparison.live_database_drift is True
    assert comparison.before.fingerprints != comparison.after.fingerprints


def test_compare_live_treats_preexisting_catalog_collections_as_snapshot_drift() -> None:
    collections = _collection_documents()
    collections["sources"] = ()
    collections["references"] = ()
    database = _StrictReadOnlyDatabase(collections)

    _updated_plan, comparison = compare_live(
        _loaded_export(_collection_documents()),
        _plan(_collection_documents()),
        database_name=LIVE_DATABASE_NAME,
        allow_live_read=True,
        mongo_uri="mongodb://localhost:27017",
        client_factory=_StrictClientFactory(database),
    )

    assert comparison.sources_collection_absent is False
    assert comparison.references_collection_absent is False
    assert comparison.snapshot_drift is True


def _collection_state(marker: str) -> CollectionState:
    return CollectionState(
        collection_names=("concepts",),
        counts={"concepts": 1},
        fingerprints={"concepts": marker * 64},
        indexes={"concepts": ()},
        indexes_fingerprint=marker * 64,
    )


def _live_comparison(*, live_drift: bool, snapshot_drift: bool) -> LiveComparison:
    before = _collection_state("a")
    after = _collection_state("b" if live_drift else "a")
    return LiveComparison(
        database_name="MathV0",
        uri_redacted="mongodb://localhost:27017",
        before=before,
        after=after,
        read_operations=("ping", "find_with_projection"),
        writes_attempted=0,
        live_database_drift=live_drift,
        snapshot_drift=snapshot_drift,
        sources_collection_absent=True,
        references_collection_absent=True,
        concept_count_expected=1,
        concept_count_live=1,
        concept_keys_match=not snapshot_drift,
        source_counts_match=not snapshot_drift,
        reference_partition_matches=True,
        reference_fingerprints_match=True,
        consumer_counts_match=True,
    )


@pytest.mark.parametrize(
    ("live_drift", "snapshot_drift", "expected_exit"),
    [
        (True, False, migration_cli.EXIT_LIVE_DRIFT),
        (False, True, migration_cli.EXIT_SNAPSHOT_DRIFT),
    ],
)
def test_cli_maps_live_and_snapshot_drift_to_distinct_nonzero_exit_codes(
    live_drift: bool,
    snapshot_drift: bool,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    comparison = _live_comparison(
        live_drift=live_drift,
        snapshot_drift=snapshot_drift,
    )

    def fake_compare(_export, plan, **_kwargs):
        return plan.model_copy(update={"live_comparison": comparison}), comparison

    _patch_cli_pipeline(monkeypatch, compare=fake_compare)

    result = migration_cli.main(
        [
            "compare-live",
            "--input-zip",
            "synthetic.zip",
            "--database",
            "MathV0",
            "--allow-live-read",
        ]
    )

    assert result == expected_exit
    assert "Live MathV0 comparison" in capsys.readouterr().out


def test_live_connection_errors_redact_uri_and_credentials() -> None:
    uri = "mongodb://alice:secret@db.example:27018/MathV0?authSource=admin"

    def failing_factory(received_uri: str, **_kwargs: Any) -> None:
        raise RuntimeError(f"connection failed for {received_uri}; user=alice password=secret")

    export = _loaded_export()
    with pytest.raises(LiveComparisonError) as exc_info:
        compare_live(
            export,
            _plan(export.collections),
            database_name=LIVE_DATABASE_NAME,
            allow_live_read=True,
            mongo_uri=uri,
            client_factory=failing_factory,
        )

    message = str(exc_info.value)
    assert uri not in message
    assert "alice" not in message
    assert "secret" not in message
    assert "mongodb://db.example:27018/MathV0" in message


def test_cli_explicit_output_is_private_and_exclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli_pipeline(monkeypatch)
    home = tmp_path / "private-home"
    monkeypatch.setenv("HOME", str(home))
    relative_output = "review reports/status.json"
    arguments = [
        "status",
        "--input-zip",
        "synthetic.zip",
        "--output-format",
        "json",
        "--output",
        relative_output,
    ]

    assert migration_cli.main(arguments) == migration_cli.EXIT_OK
    first_capture = capsys.readouterr()
    destination = home / relative_output
    assert first_capture.out == ""
    assert first_capture.err == ""
    assert destination.parent.stat().st_mode & 0o777 == 0o700
    assert destination.stat().st_mode & 0o777 == 0o600
    original = destination.read_bytes()
    assert json.loads(original)["ready_to_plan"] is True

    assert migration_cli.main(arguments) == migration_cli.EXIT_ERROR
    second_capture = capsys.readouterr()
    assert "Refusing to replace an existing report" in second_capture.err
    assert destination.read_bytes() == original


def test_output_exclusive_open_race_never_deletes_competing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "race.json"
    original_open = migration_report.os.open

    def competing_open(path, _flags, mode):
        descriptor = original_open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        os.write(descriptor, b"competing process")
        os.close(descriptor)
        raise FileExistsError("simulated O_EXCL race")

    monkeypatch.setattr(migration_report.os, "open", competing_open)

    with pytest.raises(FileExistsError, match="O_EXCL race"):
        write_report(destination, "planner output")

    assert destination.read_bytes() == b"competing process"


def test_cli_output_rejects_symlink_without_touching_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli_pipeline(monkeypatch)
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    outside = tmp_path / "outside.json"
    outside.write_text("keep", encoding="utf-8")
    destination = home / "linked.json"
    destination.symlink_to(outside)
    monkeypatch.setenv("HOME", str(home))

    result = migration_cli.main(
        [
            "status",
            "--input-zip",
            "synthetic.zip",
            "--output",
            destination.name,
        ]
    )

    assert result == migration_cli.EXIT_ERROR
    assert "Symbolic links" in capsys.readouterr().err
    assert destination.is_symlink()
    assert outside.read_text(encoding="utf-8") == "keep"


def test_cli_output_rejects_checkout_destination(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli_pipeline(monkeypatch)
    destination = PROJECT_ROOT / "forbidden-s1c1-report.json"
    assert not destination.exists()

    result = migration_cli.main(
        [
            "status",
            "--input-zip",
            "synthetic.zip",
            "--output",
            str(destination),
        ]
    )

    assert result == migration_cli.EXIT_ERROR
    assert "installed MathMongo package" in capsys.readouterr().err
    assert not destination.exists()


def test_report_output_rejects_site_packages_before_opening_a_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site_package = Path(pydantic.__file__).resolve().parent
    destination = site_package / "forbidden-s1c1-report.json"
    assert not destination.exists()
    open_attempts: list[Path] = []

    def forbidden_open(path: str | os.PathLike[str], *_args: Any, **_kwargs: Any) -> int:
        open_attempts.append(Path(path))
        raise AssertionError("site-packages validation must run before os.open")

    monkeypatch.setattr("mathmongo.source_catalog_migration.report.os.open", forbidden_open)

    with pytest.raises((ReportOutputError, ValueError), match="site-packages|installed"):
        write_report(destination, "private\n", environment=dict(os.environ))

    assert open_attempts == []
    assert not destination.exists()


def _write_synthetic_export(path: Path) -> None:
    concepts = [
        copy.deepcopy(SAMPLE_CONCEPT),
        {
            "_id": "000000000000000000000002",
            "id": "concept-2",
            "source": "Second_Exact_Source",
        },
    ]
    collections = {"concepts": concepts}
    metadata = {
        "exported_at": FIXED_TIME.isoformat().replace("+00:00", "Z"),
        "collections": {name: len(documents) for name, documents in collections.items()},
        "media_files": {},
    }

    def write_regular_member(
        archive: zipfile.ZipFile,
        name: str,
        payload: str,
    ) -> None:
        info = zipfile.ZipInfo(name)
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o600) << 16
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, payload)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        write_regular_member(
            archive,
            "synthetic/metadata.json",
            json.dumps(metadata, ensure_ascii=False),
        )
        for name, documents in collections.items():
            write_regular_member(
                archive,
                f"synthetic/collections/{name}.json",
                json.dumps(documents, ensure_ascii=False),
            )


def _file_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    if not root.exists():
        return {}
    result: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if path.is_file():
            stat_result = path.stat()
            result[str(path)] = (stat_result.st_size, stat_result.st_mtime_ns)
    return result


def test_real_status_and_dry_run_write_nothing_to_home_cwd_or_site_packages(
    tmp_path: Path,
) -> None:
    input_zip = tmp_path / "synthetic.zip"
    _write_synthetic_export(input_zip)
    input_before = input_zip.read_bytes()
    working = tmp_path / "empty-cwd"
    working.mkdir()
    home = tmp_path / "home"
    xdg_roots = {
        "XDG_CONFIG_HOME": tmp_path / "config",
        "XDG_DATA_HOME": tmp_path / "data",
        "XDG_CACHE_HOME": tmp_path / "cache",
        "XDG_STATE_HOME": tmp_path / "state",
    }
    site_roots = {
        Path(pydantic.__file__).resolve().parent,
        Path(pymongo.__file__).resolve().parent,
    }
    site_before = {root: _file_snapshot(root) for root in site_roots}
    environment = os.environ.copy()
    python_path = os.pathsep.join(
        dict.fromkeys(
            [
                str(PROJECT_ROOT),
                *(str(root.parent) for root in site_roots),
            ]
        )
    )
    environment.update(
        {
            "HOME": str(home),
            "PYTHONPATH": python_path,
            "PYTHONDONTWRITEBYTECODE": "1",
            **{name: str(path) for name, path in xdg_roots.items()},
        }
    )

    commands = (
        [
            "status",
            "--input-zip",
            str(input_zip),
            "--database-name",
            "Synthetic",
        ],
        [
            "dry-run",
            "--input-zip",
            str(input_zip),
            "--database-name",
            "Synthetic",
            "--output-format",
            "json",
        ],
    )
    for arguments in commands:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "mathmongo.migrate_source_catalog",
                *arguments,
            ],
            cwd=working,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout

    assert list(working.iterdir()) == []
    assert not home.exists()
    assert all(not path.exists() for path in xdg_roots.values())
    assert input_zip.read_bytes() == input_before
    assert {root: _file_snapshot(root) for root in site_roots} == site_before

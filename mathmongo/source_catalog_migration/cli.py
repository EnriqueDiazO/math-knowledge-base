"""CLI boundary for planning and explicitly guarded Source Catalog bootstrap."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from mathmongo.config import redact_mongo_uri
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error
from mathmongo.source_catalog_migration.apply_result import ApplyOutcome
from mathmongo.source_catalog_migration.apply_result import ApplyResult
from mathmongo.source_catalog_migration.apply_result import render_apply_result
from mathmongo.source_catalog_migration.apply_result import safe_apply_diagnostic
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_PLAN_SEMANTIC_SHA256
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_ZIP_SHA256
from mathmongo.source_catalog_migration.apply_safety import PRODUCTION_CONFIRMATION_PHRASE
from mathmongo.source_catalog_migration.apply_safety import PRODUCTION_TARGET_DATABASE
from mathmongo.source_catalog_migration.apply_safety import ApplyAuthorization
from mathmongo.source_catalog_migration.apply_safety import ApplySafetyError
from mathmongo.source_catalog_migration.apply_safety import validate_apply_authorization
from mathmongo.source_catalog_migration.apply_safety import validate_authoritative_plan
from mathmongo.source_catalog_migration.backup_safety import parse_write_freeze_at
from mathmongo.source_catalog_migration.backup_safety import validate_production_backup
from mathmongo.source_catalog_migration.canonical import json_safe
from mathmongo.source_catalog_migration.decisions import DecisionError
from mathmongo.source_catalog_migration.decisions import build_decisions_template
from mathmongo.source_catalog_migration.decisions import decisions_json
from mathmongo.source_catalog_migration.decisions import load_decisions
from mathmongo.source_catalog_migration.inventory import InventoryError
from mathmongo.source_catalog_migration.inventory import build_inventory
from mathmongo.source_catalog_migration.live_compare import LIVE_DATABASE_NAME
from mathmongo.source_catalog_migration.live_compare import LiveComparisonError
from mathmongo.source_catalog_migration.live_compare import compare_live
from mathmongo.source_catalog_migration.manifest import ManifestPersistenceError
from mathmongo.source_catalog_migration.manifest import ManifestStore
from mathmongo.source_catalog_migration.planner import PlanInvariantError
from mathmongo.source_catalog_migration.planner import authoritative_expectations
from mathmongo.source_catalog_migration.planner import build_plan
from mathmongo.source_catalog_migration.planner import build_status
from mathmongo.source_catalog_migration.planner import validate_plan
from mathmongo.source_catalog_migration.report import ReportOutputError
from mathmongo.source_catalog_migration.report import render_report
from mathmongo.source_catalog_migration.report import write_report
from mathmongo.source_catalog_migration.zip_reader import InputChangedError
from mathmongo.source_catalog_migration.zip_reader import ZipSafetyLimits
from mathmongo.source_catalog_migration.zip_reader import ZipValidationError
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export
from mathmongo.source_catalog_migration.zip_reader import verify_input_unchanged

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_SNAPSHOT_DRIFT = 3
EXIT_LIVE_DRIFT = 4
EXIT_APPLY_BLOCKED = 5
EXIT_APPLY_CONFLICT = 6


class CatalogCLIConnectionError(RuntimeError):
    """A bounded, credential-redacted target connection failure."""


class CatalogCLIExecutionError(RuntimeError):
    """An unexpected guarded-target operation failed with a safe diagnostic."""


class CatalogCLIUsageError(ValueError):
    """A S1C2A command omitted an explicit non-positional authorization flag."""


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-zip", required=True, help="Authoritative legacy export ZIP.")
    parser.add_argument(
        "--output-format",
        choices=("text", "json"),
        default="text",
        help="Report serialization (default: text).",
    )
    parser.add_argument(
        "--output",
        help="Explicit report path. Omit to write only to stdout.",
    )
    parser.add_argument(
        "--fail-on-input-change",
        action="store_true",
        help="Fail if input identity changes; dry-run always enforces this policy.",
    )
    parser.add_argument(
        "--database-name",
        default="MathV0",
        help="Operator assertion recorded as snapshot metadata (default: MathV0).",
    )
    parser.add_argument("--max-zip-members", type=int, default=1_000)
    parser.add_argument("--max-zip-member-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-zip-total-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--max-zip-compression-ratio", type=float, default=100.0)


def _add_authoritative_zip_options(parser: argparse.ArgumentParser) -> None:
    """Add ZIP options while fixing its source-database assertion to MathV0."""
    parser.add_argument("--input-zip", required=True, help="Authoritative MathV0 export ZIP.")
    parser.add_argument(
        "--fail-on-input-change",
        action="store_true",
        help="Fail if the authoritative input changes during the operation.",
    )
    parser.add_argument("--max-zip-members", type=int, default=1_000)
    parser.add_argument("--max-zip-member-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-zip-total-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--max-zip-compression-ratio", type=float, default=100.0)


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-format",
        choices=("text", "json"),
        default="text",
        help="Report serialization (default: text).",
    )
    parser.add_argument("--output", help="Explicit private report path; omit for stdout.")


def build_parser() -> argparse.ArgumentParser:
    """Build every parser without importing PyMongo or touching config/HOME."""
    parser = argparse.ArgumentParser(
        prog="python -m mathmongo.migrate_source_catalog",
        description="Read-only legacy Source Catalog status and deterministic planning.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="Validate and inventory the ZIP.")
    _add_common_options(status)
    dry_run = subparsers.add_parser("dry-run", help="Build a deterministic non-writing plan.")
    _add_common_options(dry_run)
    compare = subparsers.add_parser(
        "compare-live",
        help="Compare the immutable ZIP plan with live MathV0 in read-only mode.",
    )
    _add_common_options(compare)
    compare.add_argument("--database", required=True, help="Must be explicitly MathV0.")
    compare.add_argument(
        "--allow-live-read",
        action="store_true",
        help="Required authorization for direct read-only PyMongo access.",
    )
    template = subparsers.add_parser(
        "decisions-template",
        help="Create an incomplete human-decision JSON template without MongoDB access.",
    )
    _add_authoritative_zip_options(template)
    template.add_argument("--output", required=True, help="New private JSON template path.")

    apply_status = subparsers.add_parser(
        "apply-status",
        help="Read bootstrap manifest status from an explicit guarded target.",
    )
    apply_status.add_argument("--database", required=True, help="Exact guarded target database.")
    apply_status.add_argument(
        "--allow-live-read",
        action="store_true",
        help="Required authorization for read-only manifest access.",
    )
    _add_output_options(apply_status)

    apply = subparsers.add_parser(
        "apply",
        help="Apply the approved catalog plan through an explicit isolated or MathV0 gate.",
    )
    _add_authoritative_zip_options(apply)
    apply.add_argument("--decisions", required=True, help="Validated human-decision JSON file.")
    apply.add_argument("--database", required=True, help="Exact guarded target database.")
    apply.add_argument(
        "--allow-isolated-write",
        action="store_true",
        help="Required explicit authorization for isolated catalog writes.",
    )
    apply.add_argument(
        "--allow-production-write",
        action="store_true",
        help="Required explicit authorization for the separately guarded MathV0 path.",
    )
    apply.add_argument(
        "--confirm-database",
        required=True,
        help="Must repeat the exact guarded target database name.",
    )
    apply.add_argument(
        "--confirm-production-phrase",
        help=f"MathV0 only: must be exactly {PRODUCTION_CONFIRMATION_PHRASE!r}.",
    )
    apply.add_argument("--backup-path", help="MathV0 only: fresh private pre-apply backup ZIP.")
    apply.add_argument("--backup-sha", help="MathV0 only: SHA-256 of the fresh backup.")
    apply.add_argument(
        "--confirm-backup-sha",
        help="MathV0 only: repeat the exact fresh-backup SHA-256.",
    )
    apply.add_argument(
        "--write-freeze-at",
        help="MathV0 only: timezone-aware timestamp recorded after writes were frozen.",
    )
    apply.add_argument("--expected-zip-sha", required=True, help="Complete authoritative ZIP hash.")
    apply.add_argument(
        "--expected-plan-sha",
        required=True,
        help="Complete authoritative semantic-plan hash.",
    )
    _add_output_options(apply)
    return parser


def _limits(args: argparse.Namespace) -> ZipSafetyLimits:
    return ZipSafetyLimits(
        max_members=args.max_zip_members,
        max_member_bytes=args.max_zip_member_bytes,
        max_total_bytes=args.max_zip_total_bytes,
        max_compression_ratio=args.max_zip_compression_ratio,
    )


def _emit(report, args: argparse.Namespace) -> None:
    content = render_report(report, args.output_format)
    _emit_content(content, args)


def _emit_content(content: str, args: argparse.Namespace) -> None:
    """Emit already-bounded content to stdout or an explicit private file."""
    if args.output:
        write_report(args.output, content, environment=dict(os.environ))
    else:
        sys.stdout.write(content)


def _load_authoritative_plan(args: argparse.Namespace):
    """Load the fixed MathV0 snapshot and build its unchanged S1C1 plan."""
    export = read_legacy_export(
        args.input_zip,
        database_name=LIVE_DATABASE_NAME,
        limits=_limits(args),
        fail_on_input_change=args.fail_on_input_change,
    )
    expectations = authoritative_expectations(LIVE_DATABASE_NAME)
    inventory = build_inventory(export)
    plan = build_plan(export, expectations=expectations)
    validate_plan(plan, inventory, expectations)
    if export.input_snapshot.database_name != LIVE_DATABASE_NAME:
        raise ApplySafetyError(
            "snapshot_database_mismatch",
            "The authoritative snapshot must remain labelled MathV0.",
        )
    if export.input_snapshot.sha256 != AUTHORITATIVE_ZIP_SHA256:
        raise ApplySafetyError("zip_hash_mismatch", "The input ZIP is not authoritative.")
    if plan.semantic_sha256 != AUTHORITATIVE_PLAN_SEMANTIC_SHA256:
        raise ApplySafetyError("plan_hash_mismatch", "The semantic plan is not authoritative.")
    verify_input_unchanged(args.input_zip, export.input_identity)
    return export, plan


def _apply_authorization(args: argparse.Namespace) -> ApplyAuthorization:
    """Validate every write assertion before reading config or constructing a client."""
    is_production = args.database == PRODUCTION_TARGET_DATABASE
    if is_production:
        if args.output:
            raise ApplySafetyError(
                "production_output_requires_stdout",
                "MathV0 apply emits only to captured stdout; --output is forbidden.",
            )
        if args.allow_production_write is not True:
            raise ApplySafetyError(
                "production_write_not_authorized",
                "MathV0 apply requires --allow-production-write.",
            )
        if args.allow_isolated_write is True:
            raise ApplySafetyError(
                "authorization_mode_conflict",
                "Production and isolated write flags cannot be combined.",
            )
        if args.confirm_database != PRODUCTION_TARGET_DATABASE:
            raise ApplySafetyError(
                "database_confirmation_mismatch",
                "The exact MathV0 database confirmation does not match.",
            )
        if args.confirm_production_phrase != PRODUCTION_CONFIRMATION_PHRASE:
            raise ApplySafetyError(
                "production_phrase_mismatch",
                "The exact MathV0 production confirmation phrase does not match.",
            )
        if args.expected_zip_sha != AUTHORITATIVE_ZIP_SHA256:
            raise ApplySafetyError(
                "zip_hash_mismatch", "The expected ZIP hash is not authoritative."
            )
        if args.expected_plan_sha != AUTHORITATIVE_PLAN_SEMANTIC_SHA256:
            raise ApplySafetyError(
                "plan_hash_mismatch",
                "The expected semantic plan hash is not authoritative.",
            )
        if not all(
            (args.backup_path, args.backup_sha, args.confirm_backup_sha, args.write_freeze_at)
        ):
            raise ApplySafetyError(
                "production_backup_required",
                "MathV0 apply requires backup path, both backup hashes, and write-freeze time.",
            )
        freeze = parse_write_freeze_at(args.write_freeze_at)
        backup = validate_production_backup(
            args.backup_path,
            backup_sha=args.backup_sha,
            confirm_backup_sha=args.confirm_backup_sha,
            write_freeze_at=freeze,
            require_fresh=False,
        )
    else:
        production_only = (
            args.allow_production_write,
            args.confirm_production_phrase,
            args.backup_path,
            args.backup_sha,
            args.confirm_backup_sha,
            args.write_freeze_at,
        )
        if any(value not in (None, False) for value in production_only):
            raise ApplySafetyError(
                "unexpected_production_authorization",
                "Production-only flags are forbidden for an isolated target.",
            )
        freeze = None
        backup = None
    try:
        authorization = ApplyAuthorization(
            target_database=args.database,
            allow_isolated_write=args.allow_isolated_write,
            allow_production_write=args.allow_production_write,
            confirmed_database=args.confirm_database,
            expected_zip_sha=args.expected_zip_sha,
            expected_plan_sha=args.expected_plan_sha,
            confirm_production_phrase=args.confirm_production_phrase,
            production_backup=backup,
            production_backup_path=args.backup_path if is_production else None,
            production_backup_sha=args.backup_sha if is_production else None,
            confirm_production_backup_sha=(args.confirm_backup_sha if is_production else None),
            write_freeze_at=freeze,
        )
    except (TypeError, ValueError) as exc:
        raise ApplySafetyError(
            "invalid_authorization",
            "The write authorization fields are invalid.",
        ) from exc
    return validate_apply_authorization(authorization)


def _validate_apply_status_request(args: argparse.Namespace) -> None:
    """Reuse isolated-name safety without treating a status read as write authority."""
    if args.allow_live_read is not True:
        raise CatalogCLIUsageError("apply-status requires --allow-live-read")
    if args.database == PRODUCTION_TARGET_DATABASE:
        return
    try:
        authorization = ApplyAuthorization(
            target_database=args.database,
            allow_isolated_write=True,
            confirmed_database=args.database,
            expected_zip_sha=AUTHORITATIVE_ZIP_SHA256,
            expected_plan_sha=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        )
    except (TypeError, ValueError) as exc:
        raise ApplySafetyError(
            "invalid_target",
            "The isolated target database name is invalid.",
        ) from exc
    validate_apply_authorization(authorization)


def _default_client_factory():
    """Import PyMongo only after all pure command authorization has passed."""
    from pymongo import MongoClient

    return MongoClient


def _connect_target_database(database_name: str, client_factory=None):
    """Connect conservatively to one already-existing explicit target database."""
    config = resolve_config()
    uri = config.mongo_uri
    factory = client_factory or _default_client_factory()
    client = None
    try:
        client = factory(
            uri,
            serverSelectionTimeoutMS=2_500,
            connectTimeoutMS=2_500,
            socketTimeoutMS=10_000,
            retryWrites=False,
            appname="MathMongo-S1C2P-bootstrap",
        )
        client.admin.command("ping")
        if database_name not in tuple(client.list_database_names()):
            raise RuntimeError("The exact guarded target database does not already exist.")
        database = client.get_database(database_name)
        if getattr(database, "name", None) != database_name:
            raise RuntimeError("The MongoDB database object does not match the exact target name.")
        return client, database
    except Exception as exc:
        if client is not None:
            client.close()
        safe = sanitize_mongo_error(exc, uri)
        raise CatalogCLIConnectionError(
            f"Target connection failed at {redact_mongo_uri(uri)}: {safe}"
        ) from exc


def _manifest_status_payload(database_name: str, manifests: Sequence[Any]) -> dict[str, Any]:
    """Project manifests without final ID maps, entity hashes, or raw bibliography."""
    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        rows.append(
            {
                "manifest_key": manifest.manifest_key,
                "migration_id": manifest.migration_id,
                "state": manifest.state.value,
                "zip_sha256": manifest.zip_sha256,
                "plan_semantic_sha256": manifest.plan_semantic_sha256,
                "planner_version": manifest.planner_version,
                "decisions_sha256": manifest.decisions_sha256,
                "production_backup_evidence": (
                    manifest.production_backup_evidence.model_dump(mode="json")
                    if getattr(manifest, "production_backup_evidence", None) is not None
                    else None
                ),
                "expected_counts": manifest.expected_counts.model_dump(mode="json"),
                "sources_created": manifest.sources_created,
                "sources_identical": manifest.sources_identical,
                "references_created": manifest.references_created,
                "references_identical": manifest.references_identical,
                "indexes_status": manifest.indexes_status.model_dump(mode="json"),
                "invariant_hashes_before": (
                    None
                    if manifest.invariant_hashes_before is None
                    else manifest.invariant_hashes_before.model_dump(mode="json")
                ),
                "invariant_hashes_after": (
                    None
                    if manifest.invariant_hashes_after is None
                    else manifest.invariant_hashes_after.model_dump(mode="json")
                ),
                "errors": [
                    {
                        **item.model_dump(mode="json"),
                        "message": safe_apply_diagnostic(item.message),
                    }
                    for item in manifest.errors
                ],
                "attempts": manifest.attempts,
                "resume_count": manifest.resume_count,
                "created_at": manifest.created_at,
                "started_at": manifest.started_at,
                "completed_at": manifest.completed_at,
                "last_updated_at": manifest.last_updated_at,
            }
        )
    return json_safe(
        {
            "schema_version": 1,
            "target_database": database_name,
            "manifest_count": len(rows),
            "manifests": rows,
        }
    )


def _render_apply_status(database_name: str, manifests: Sequence[Any], output_format: str) -> str:
    payload = _manifest_status_payload(database_name, manifests)
    if output_format == "json":
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
    if output_format != "text":
        raise ValueError(f"Unsupported apply-status format: {output_format}")
    lines = [
        "MathMongo S1C2A Source Catalog apply status",
        f"Target database: {database_name}",
        f"Manifests: {len(manifests)}",
    ]
    for manifest in manifests:
        lines.extend(
            (
                f"Migration ID: {manifest.migration_id}",
                f"State: {manifest.state.value}",
                f"ZIP SHA-256: {manifest.zip_sha256}",
                f"Plan SHA-256: {manifest.plan_semantic_sha256}",
                f"Decisions SHA-256: {manifest.decisions_sha256}",
                (
                    "Sources: "
                    f"expected={manifest.expected_counts.source_candidates}; "
                    f"created={manifest.sources_created}; identical={manifest.sources_identical}"
                ),
                (
                    "References: "
                    f"expected={manifest.expected_counts.reference_candidates}; "
                    f"created={manifest.references_created}; "
                    f"identical={manifest.references_identical}"
                ),
                f"Attempts: {manifest.attempts}; resumes={manifest.resume_count}",
            )
        )
        lines.extend(f"Error: {safe_apply_diagnostic(error.message)}" for error in manifest.errors)
    if not manifests:
        lines.append("No compatible bootstrap manifest exists for this target.")
    return "\n".join(lines) + "\n"


def _run_decisions_template(args: argparse.Namespace) -> int:
    export, plan = _load_authoritative_plan(args)
    template = build_decisions_template(plan)
    verify_input_unchanged(args.input_zip, export.input_identity)
    write_report(
        args.output,
        decisions_json(template),
        environment=dict(os.environ),
    )
    return EXIT_OK


def _run_apply_status(
    args: argparse.Namespace,
    *,
    client_factory=None,
    manifest_store_factory=None,
) -> int:
    _validate_apply_status_request(args)
    client, database = _connect_target_database(args.database, client_factory)
    try:
        store_type = manifest_store_factory or ManifestStore
        try:
            manifests = store_type(database).find_for_target(args.database)
        except ManifestPersistenceError:
            raise
        except Exception as exc:
            raise CatalogCLIExecutionError(safe_apply_diagnostic(exc)) from exc
    finally:
        client.close()
    _emit_content(_render_apply_status(args.database, manifests, args.output_format), args)
    return EXIT_OK


def _run_apply(
    args: argparse.Namespace,
    *,
    client_factory=None,
    engine_factory=None,
) -> int:
    authorization = _apply_authorization(args)
    export, plan = _load_authoritative_plan(args)
    decisions = load_decisions(args.decisions)
    validate_authoritative_plan(plan, decisions)
    verify_input_unchanged(args.input_zip, export.input_identity)
    client, database = _connect_target_database(args.database, client_factory)
    engine_completed = False
    try:
        if engine_factory is None:
            from mathmongo.source_catalog_migration.bootstrap import BootstrapEngine

            engine_factory = BootstrapEngine
        try:
            result = engine_factory(database).apply(
                export=export,
                plan=plan,
                decisions=decisions,
                authorization=authorization,
            )
            engine_completed = True
        except (ApplySafetyError, DecisionError, ManifestPersistenceError):
            raise
        except Exception as exc:
            raise CatalogCLIExecutionError(safe_apply_diagnostic(exc)) from exc
    finally:
        client.close()
        try:
            verify_input_unchanged(args.input_zip, export.input_identity)
        except Exception as exc:
            if engine_completed:
                raise CatalogCLIExecutionError(
                    "Post-apply ZIP verification failed; apply may have completed. "
                    "Run apply-status before any retry."
                ) from exc
            raise
    if not isinstance(result, ApplyResult):
        raise TypeError("BootstrapEngine.apply must return ApplyResult")
    try:
        _emit_content(render_apply_result(result, args.output_format), args)
    except Exception as exc:
        raise CatalogCLIExecutionError(
            "Apply completed but result emission failed; run apply-status before any retry."
        ) from exc
    if result.outcome in {
        ApplyOutcome.PREPARED,
        ApplyOutcome.APPLIED,
        ApplyOutcome.RESUMED,
        ApplyOutcome.ALREADY_APPLIED,
        ApplyOutcome.IDENTICAL,
    }:
        return EXIT_OK
    if result.outcome == ApplyOutcome.BLOCKED:
        return EXIT_APPLY_BLOCKED
    if result.outcome == ApplyOutcome.CONFLICT:
        return EXIT_APPLY_CONFLICT
    return EXIT_ERROR


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory=None,
    engine_factory=None,
    manifest_store_factory=None,
) -> int:
    """Execute one planner/bootstrap command and return a stable process exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if (
        arguments
        and arguments[0] == "apply"
        and "--allow-isolated-write" not in arguments
        and "--allow-production-write" not in arguments
    ):
        print(
            "Error: apply requires either the isolated-write or the separately guarded "
            "production-write authorization.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    parser = build_parser()
    try:
        args = parser.parse_args(arguments)
        if args.command == "decisions-template":
            return _run_decisions_template(args)
        if args.command == "apply-status":
            return _run_apply_status(
                args,
                client_factory=client_factory,
                manifest_store_factory=manifest_store_factory,
            )
        if args.command == "apply":
            return _run_apply(
                args,
                client_factory=client_factory,
                engine_factory=engine_factory,
            )
        if args.command == "compare-live" and args.database_name != LIVE_DATABASE_NAME:
            raise ValueError(
                "compare-live requires --database-name MathV0 to match --database MathV0"
            )
        export = read_legacy_export(
            args.input_zip,
            database_name=args.database_name,
            limits=_limits(args),
            fail_on_input_change=args.fail_on_input_change,
        )
        expectations = authoritative_expectations(args.database_name)
        if args.command == "status":
            status = build_status(export, expectations=expectations)
            verify_input_unchanged(args.input_zip, export.input_identity)
            _emit(status, args)
            return EXIT_OK if status.ready_to_plan else EXIT_ERROR

        inventory = build_inventory(export)
        plan = build_plan(export, expectations=expectations)
        validate_plan(plan, inventory, expectations)
        if args.command == "dry-run":
            verify_input_unchanged(args.input_zip, export.input_identity)
            _emit(plan, args)
            return EXIT_OK

        plan, comparison = compare_live(
            export,
            plan,
            database_name=args.database,
            allow_live_read=args.allow_live_read,
        )
        verify_input_unchanged(args.input_zip, export.input_identity)
        _emit(plan, args)
        if comparison.live_database_drift:
            return EXIT_LIVE_DRIFT
        if comparison.snapshot_drift:
            return EXIT_SNAPSHOT_DRIFT
        return EXIT_OK
    except SystemExit:
        raise
    except CatalogCLIUsageError as exc:
        print(f"Error: {safe_apply_diagnostic(exc)}", file=sys.stderr)
        return EXIT_USAGE
    except (ApplySafetyError, DecisionError) as exc:
        print(f"Error: {safe_apply_diagnostic(exc)}", file=sys.stderr)
        return EXIT_APPLY_BLOCKED
    except (CatalogCLIConnectionError, CatalogCLIExecutionError, ManifestPersistenceError) as exc:
        print(f"Error: {safe_apply_diagnostic(exc)}", file=sys.stderr)
        return EXIT_ERROR
    except (
        InputChangedError,
        InventoryError,
        PlanInvariantError,
        ReportOutputError,
        ZipValidationError,
        LiveComparisonError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Error: {safe_apply_diagnostic(exc)}", file=sys.stderr)
        return EXIT_ERROR


__all__ = [
    "EXIT_ERROR",
    "EXIT_APPLY_BLOCKED",
    "EXIT_APPLY_CONFLICT",
    "EXIT_LIVE_DRIFT",
    "EXIT_OK",
    "EXIT_SNAPSHOT_DRIFT",
    "EXIT_USAGE",
    "build_parser",
    "main",
]

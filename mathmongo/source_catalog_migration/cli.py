"""Command-line boundary for S1C1 status, dry-run, and read-only comparison."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from mathmongo.source_catalog_migration.inventory import InventoryError
from mathmongo.source_catalog_migration.inventory import build_inventory
from mathmongo.source_catalog_migration.live_compare import LIVE_DATABASE_NAME
from mathmongo.source_catalog_migration.live_compare import LiveComparisonError
from mathmongo.source_catalog_migration.live_compare import compare_live
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


def build_parser() -> argparse.ArgumentParser:
    """Build the S1C1 parser without importing PyMongo or touching config/HOME."""
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
    if args.output:
        write_report(args.output, content, environment=dict(os.environ))
    else:
        sys.stdout.write(content)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute one S1C1 command and return a stable process exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "apply":
        print(
            "Error: apply is not available in S1C1; it belongs to S1C2.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    parser = build_parser()
    try:
        args = parser.parse_args(arguments)
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
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR


__all__ = [
    "EXIT_ERROR",
    "EXIT_LIVE_DRIFT",
    "EXIT_OK",
    "EXIT_SNAPSHOT_DRIFT",
    "EXIT_USAGE",
    "build_parser",
    "main",
]

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from exporters_latex.latex_validation import default_report_paths
from exporters_latex.latex_validation import validate_concept_from_mongo
from exporters_latex.latex_validation import validate_source_from_mongo
from exporters_latex.latex_validation import write_json_report
from exporters_latex.latex_validation import write_markdown_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate LaTeX concepts from MongoDB.")
    parser.add_argument("--source", required=True, help="Concept source to validate.")
    parser.add_argument("--concept-id", help="Validate a single concept id.")
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--db-name", default="mathmongo")
    parser.add_argument("--json-output", help="Write JSON report to this path.")
    parser.add_argument("--markdown-output", help="Write Markdown report to this path.")
    parser.add_argument(
        "--apply-safe-fixes-preview",
        action="store_true",
        help="Apply safe fixes only in the validation preview/report.",
    )
    parser.add_argument(
        "--apply-safe-fixes",
        action="store_true",
        help="Prepare safe fixes for writing to MongoDB. Requires --write-to-mongo.",
    )
    parser.add_argument(
        "--write-to-mongo",
        action="store_true",
        help="Write safe fixes to MongoDB after confirmation.",
    )
    parser.add_argument("--no-compile", action="store_true", help="Skip pdflatex compile validation.")
    parser.add_argument("--no-linters", action="store_true", help="Skip chktex/lacheck.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from mathdatabase.mathmongo import MathMongo

    db = MathMongo(args.mongo_uri, args.db_name)
    apply_fixes = args.apply_safe_fixes_preview or args.apply_safe_fixes

    if args.concept_id:
        result = validate_concept_from_mongo(
            args.concept_id,
            args.source,
            db,
            apply_fixes=apply_fixes,
            run_compile=not args.no_compile,
            run_linters=not args.no_linters,
        )
        report = {
            "source": args.source,
            "total": 1,
            "ok": 1 if result.status == "ok" else 0,
            "warnings": 1 if result.status == "warning" else 0,
            "errors": 1 if result.status == "error" else 0,
            "results": [result.__dict__],
        }
    else:
        report = validate_source_from_mongo(
            args.source,
            db,
            apply_fixes=apply_fixes,
            run_compile=not args.no_compile,
            run_linters=not args.no_linters,
        )

    print(
        f"Validated {report['total']} concepts: "
        f"{report['ok']} ok, {report['warnings']} warnings, {report['errors']} errors"
    )

    json_path, md_path = default_report_paths(args.source)
    if args.json_output:
        json_path = Path(args.json_output)
    if args.markdown_output:
        md_path = Path(args.markdown_output)

    if args.json_output:
        print(f"JSON report: {write_json_report(report, json_path)}")
    if args.markdown_output:
        print(f"Markdown report: {write_markdown_report(report, md_path)}")

    if args.write_to_mongo:
        if not args.apply_safe_fixes:
            print("--write-to-mongo requires --apply-safe-fixes.", file=sys.stderr)
            return 2
        confirmation = input(
            "This will update latex_documents in MongoDB. Type WRITE LATEX FIXES to continue: "
        )
        if confirmation != "WRITE LATEX FIXES":
            print("Cancelled. MongoDB was not modified.")
            return 1
        updated = 0
        for result in report["results"]:
            if not result.get("safe_fixes"):
                continue
            db.update_latex_document(
                result["concept_id"],
                result["source"],
                result["corrected_latex_preview"],
            )
            updated += 1
        print(f"Updated {updated} latex_documents.")

    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

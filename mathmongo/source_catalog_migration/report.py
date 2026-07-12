"""Bounded text/JSON reports and explicit private output writing for S1C1."""

from __future__ import annotations

import json
import os
import site
import stat
import sysconfig
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.models import StatusReport


class ReportOutputError(RuntimeError):
    """An explicit report destination violates the private-output contract."""


def _site_package_roots() -> tuple[Path, ...]:
    """Return known interpreter package roots without creating any directories."""
    values: set[str] = set()
    for key in ("purelib", "platlib"):
        value = sysconfig.get_path(key)
        if value:
            values.add(value)
    try:
        values.update(site.getsitepackages())
    except AttributeError:
        pass
    user_site = site.getusersitepackages()
    if isinstance(user_site, str):
        values.add(user_site)
    else:
        values.update(user_site)
    return tuple(sorted((Path(value).resolve(strict=False) for value in values), key=str))


def _validate_report_path(path: Path) -> Path:
    """Reject checkout, symlink, containment, and site-packages destinations."""
    try:
        candidate = validate_mutable_path(path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReportOutputError(str(exc)) from exc
    if {"site-packages", "dist-packages"} & set(candidate.parts):
        raise ReportOutputError(
            f"Refusing to write a report inside a package directory: {candidate}"
        )
    for root in _site_package_roots():
        if candidate == root or candidate.is_relative_to(root):
            raise ReportOutputError(f"Refusing to write a report inside site-packages: {candidate}")
    return candidate


def render_json(report: BaseModel) -> str:
    """Return stable UTF-8 JSON without relying on Pydantic's default ordering."""
    return (
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def _snapshot_lines(report: StatusReport | MigrationPlan) -> list[str]:
    snapshot = report.input_snapshot
    return [
        f"Snapshot: {snapshot.filename}",
        f"SHA-256: {snapshot.sha256}",
        f"Size: {snapshot.size_bytes} bytes",
        f"Exported at: {snapshot.exported_at or 'not declared'}",
        f"Database assertion: {snapshot.database_name}",
        (
            f"Format: {snapshot.format_name} {snapshot.format_version} "
            f"({snapshot.format_version_source})"
        ),
    ]


def _consumer_lines(report: StatusReport | MigrationPlan) -> list[str]:
    coupled = report.coupled_collections
    lines = [
        "Legacy consumers:",
        (
            "  latex_documents: "
            f"{coupled.concept_counterparts_in_latex_documents} counterparts, "
            f"{coupled.orphan_latex_documents} orphan"
        ),
    ]
    for consumer in coupled.consumers:
        lines.append(
            f"  {consumer.collection}: {consumer.document_count} documents; "
            f"legacy keys={consumer.legacy_key_usages}; "
            f"id@source={consumer.id_at_source_usages}"
        )
        lines.extend(f"    warning: {warning}" for warning in consumer.warnings)
    return lines


def _bounded(value: object, *, limit: int = 160) -> str:
    """Render one diagnostic value on one bounded line."""
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    rendered = rendered.replace("\n", "\\n").replace("\r", "\\r")
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


def _locator_summary(locator) -> str:
    payload = {
        "pages": locator.pages_raw,
        "chapter": locator.chapter_raw,
        "section": locator.section_raw,
        "equation": locator.equation_raw,
        "theorem": locator.theorem_raw,
        "notes": locator.notes_raw,
        "present": locator.present_fields,
        "null": locator.null_fields,
        "flags": locator.flags,
    }
    return _bounded(payload)


def render_status_text(report: StatusReport) -> str:
    """Render ZIP identity, safety, counts, and readiness without raw metadata."""
    safety = report.zip_safety
    summary = report.summary
    lines = ["MathMongo S1C1 legacy Source Catalog status", *_snapshot_lines(report)]
    lines.extend(
        [
            (
                f"ZIP safety: validated={safety.validated}; members={safety.member_count}; "
                f"files={safety.file_count}; uncompressed={safety.total_uncompressed_bytes}; "
                f"max_ratio={safety.maximum_compression_ratio:g}"
            ),
            "Declared collections:",
        ]
    )
    lines.extend(
        f"  {name}: {count}" for name, count in sorted(report.input_snapshot.counts.items())
    )
    lines.extend(
        [
            "Planner inventory:",
            f"  concepts: {summary.concept_count}",
            f"  Source candidates: {summary.source_candidate_count}",
            f"  embedded References: {summary.embedded_reference_count}",
            f"  concepts without Reference: {summary.missing_reference_count}",
            f"  calculated Reference candidates: {summary.reference_candidate_count}",
            f"  weak non-merging suggestions: {summary.weak_suggestion_count}",
            f"  concept bindings: {summary.binding_count}",
            *_consumer_lines(report),
            f"Ready to plan: {report.ready_to_plan}",
        ]
    )
    lines.extend(f"Issue: {issue}" for issue in report.issues)
    return "\n".join(lines) + "\n"


def render_plan_text(plan: MigrationPlan) -> str:
    """Render a bounded human-review summary without raw References or bodies."""
    summary = plan.summary
    classification_counts = Counter(
        candidate.classification.value for candidate in plan.reference_candidates
    )
    rule_counts = Counter(
        candidate.grouping_rules[0] if candidate.grouping_rules else "none"
        for candidate in plan.reference_candidates
    )
    problem_counts = Counter(item.problem_type for item in plan.review_items)
    source_names = {
        candidate.source_candidate_key: candidate.exact_string
        for candidate in plan.source_candidates
    }
    lines = [
        "MathMongo S1C1 legacy Source Catalog dry-run",
        *_snapshot_lines(plan),
        f"Semantic SHA-256: {plan.semantic_sha256}",
        "Summary:",
        f"  concepts: {summary.concept_count}",
        f"  Source candidates: {summary.source_candidate_count}",
        f"  Reference candidates: {summary.reference_candidate_count}",
        f"  bindings: {summary.binding_count}",
        f"  with Reference: {summary.embedded_reference_count}",
        f"  without Reference: {summary.missing_reference_count}",
        f"  conflicts: {summary.conflict_count}",
        f"  review items: {summary.review_item_count}",
        f"  weak non-merging suggestions: {summary.weak_suggestion_count}",
        "Source candidates (exact strings; no merging):",
    ]
    for source in sorted(plan.source_candidates, key=lambda item: item.exact_string):
        lines.append(
            f"  {_bounded(source.exact_string)}: concepts={source.concept_count}; "
            f"with_ref={source.concepts_with_reference}; "
            f"without_ref={source.concepts_without_reference}; "
            f"Reference candidates={len(source.reference_candidate_keys)}; "
            f"locators={source.locator_statistics.variant_count}; "
            f"status={source.review_status.value}"
        )
    lines.append("Reference classifications:")
    lines.extend(f"  {name}: {count}" for name, count in sorted(classification_counts.items()))
    lines.append("Primary grouping rules:")
    lines.extend(f"  {name}: {count}" for name, count in sorted(rule_counts.items()))
    lines.append("Reference candidate groups (bibliography omitted):")
    for candidate in plan.reference_candidates:
        involved_sources = tuple(
            sorted(source_names.get(key, key) for key in candidate.source_candidate_keys)
        )
        lines.append(
            f"  {candidate.reference_candidate_key}: "
            f"class={candidate.classification.value}; concepts={candidate.concept_count}; "
            f"rules={','.join(candidate.grouping_rules)}; "
            f"Sources={_bounded(involved_sources)}; "
            f"raw_variants={candidate.raw_variant_count}; "
            f"locator_variants={candidate.locator_statistics.variant_count}"
        )
    lines.append("Weak similarity suggestions (never merged):")
    if plan.weak_reference_suggestions:
        for suggestion in plan.weak_reference_suggestions:
            lines.append(
                f"  {suggestion.suggestion_key}: "
                f"candidates={','.join(suggestion.reference_candidate_keys)}; "
                f"concepts={suggestion.concept_count}; reason={suggestion.reason}"
            )
    else:
        lines.append("  none")
    lines.append("Conflicts:")
    if plan.conflicts:
        for conflict in plan.conflicts:
            lines.append(
                f"  {conflict.conflict_key}: type={conflict.conflict_type}; "
                f"concepts={conflict.concept_count}; "
                f"matching={','.join(conflict.matching_fields) or 'none'}; "
                f"contradictory={','.join(conflict.contradictory_fields) or 'none'}"
            )
    else:
        lines.append("  none")
    lines.append("Review queue (bounded diagnostics):")
    if problem_counts:
        lines.extend(f"  {name}: {count}" for name, count in sorted(problem_counts.items()))
        for item in plan.review_items:
            involved_sources = tuple(
                sorted(source_names.get(key, key) for key in item.source_candidate_keys)
            )
            locator_summaries = tuple(
                _locator_summary(locator) for locator in item.locator_variants
            )
            lines.append(
                f"  {item.review_key}: candidate={item.candidate_key}; "
                f"problem={item.problem_type}; concepts={item.concept_count}; "
                f"Sources={_bounded(involved_sources)}; "
                f"matching={','.join(item.matching_fields) or 'none'}; "
                f"contradictory={','.join(item.contradictory_fields) or 'none'}; "
                f"doi={item.normalized_doi or 'none'}; "
                f"isbn={','.join(item.normalized_isbns) or 'none'}; "
                f"citekey={','.join(item.normalized_citekeys) or 'none'}; "
                f"raw={_bounded(item.raw_variant_summaries)}; "
                f"locators={_bounded(locator_summaries)}; "
                f"actions={','.join(item.possible_actions)}"
            )
    else:
        lines.append("  none")
    lines.extend(_consumer_lines(plan))
    lines.extend(
        [
            f"All invariants passed: {plan.invariants.passed}",
            "Writes: MongoDB=0; ZIP=0; final source_id/reference_id=0; apply=not run",
        ]
    )
    if plan.live_comparison is not None:
        live = plan.live_comparison
        lines.extend(
            [
                "Live MathV0 comparison:",
                f"  URI: {live.uri_redacted}",
                f"  concurrent live drift: {live.live_database_drift}",
                f"  ZIP/live snapshot drift: {live.snapshot_drift}",
                f"  concepts: {live.concept_count_live}",
                f"  concept keys match: {live.concept_keys_match}",
                f"  Source counts match: {live.source_counts_match}",
                f"  Reference fingerprints match: {live.reference_fingerprints_match}",
                f"  consumer counts match: {live.consumer_counts_match}",
                f"  sources absent: {live.sources_collection_absent}",
                f"  references absent: {live.references_collection_absent}",
                f"  writes attempted: {live.writes_attempted}",
                f"  index fingerprint before: {live.before.indexes_fingerprint}",
                f"  index fingerprint after: {live.after.indexes_fingerprint}",
            ]
        )
        for collection in sorted(set(live.before.fingerprints) | set(live.after.fingerprints)):
            lines.append(
                f"  {collection} fingerprint: "
                f"before={live.before.fingerprints.get(collection, 'absent')}; "
                f"after={live.after.fingerprints.get(collection, 'absent')}"
            )
        lines.extend(f"  drift: {detail}" for detail in live.drift_details)
    return "\n".join(lines) + "\n"


def render_report(report: BaseModel, output_format: str) -> str:
    """Render one supported report type in the requested format."""
    if output_format == "json":
        return render_json(report)
    if output_format != "text":
        raise ValueError(f"Unsupported output format: {output_format}")
    if isinstance(report, StatusReport):
        return render_status_text(report)
    if isinstance(report, MigrationPlan):
        return render_plan_text(report)
    raise TypeError(f"Unsupported report model: {type(report).__name__}")


def _create_private_parents(parent: Path) -> None:
    missing: list[Path] = []
    current = parent
    while not current.exists():
        missing.append(current)
        if current == current.parent:
            break
        current = current.parent
    if not current.is_dir():
        raise ReportOutputError(f"Output ancestor is not a directory: {current}")
    validate_mutable_path(current)
    for directory in reversed(missing):
        validated = validate_mutable_path(directory)
        validated.mkdir(mode=0o700)
        validated.chmod(0o700)


def write_report(
    output: str | os.PathLike[str],
    content: str,
    *,
    environment: dict[str, str] | None = None,
) -> Path:
    """Create one explicitly authorized report with exclusive mode 0600."""
    if str(output) == "-":
        raise ReportOutputError("Use stdout by omitting --output; '-' is not a file destination")
    destination = _validate_report_path(resolve_home_path(output, environment))
    if destination.exists():
        raise ReportOutputError(f"Refusing to replace an existing report: {destination}")
    _create_private_parents(destination.parent)
    try:
        destination = validate_mutable_path(
            destination,
            allowed_root=destination.parent,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReportOutputError(str(exc)) from exc
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    created_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(destination, flags, 0o600)
        opened = os.fstat(descriptor)
        created_identity = (opened.st_dev, opened.st_ino)
        os.fchmod(descriptor, 0o600)
        payload = content.encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if created_identity is not None:
            try:
                current = destination.lstat()
            except FileNotFoundError:
                pass
            else:
                if (
                    stat.S_ISREG(current.st_mode)
                    and (current.st_dev, current.st_ino) == created_identity
                ):
                    destination.unlink(missing_ok=True)
        raise
    return destination


__all__ = [
    "ReportOutputError",
    "render_json",
    "render_plan_text",
    "render_report",
    "render_status_text",
    "write_report",
]

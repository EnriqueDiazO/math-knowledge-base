"""Typed, fail-closed human decisions for the S1C2 catalog bootstrap."""

# ruff: noqa: D101,D102

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import StrictBool
from pydantic import ValidationError
from pydantic import field_validator

from mathmongo.paths import find_symlink_component
from mathmongo.source_catalog_migration.canonical import canonical_json
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.models import ReviewStatus

DECISIONS_SCHEMA_VERSION = 1
DEFAULT_MAX_DECISIONS_BYTES = 256 * 1024
HARD_MAX_DECISIONS_BYTES = 1024 * 1024
_SHA256_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")

WeakSuggestionDecision = Literal["keep_separate"]
LocatorReviewDecision = Literal["defer"]


class DecisionError(ValueError):
    """Base class for controlled human-decision failures."""


class DecisionFileError(DecisionError):
    """A decisions file is unsafe, oversized, malformed, or schema-invalid."""


class DecisionValidationError(DecisionError):
    """Typed decisions do not completely authorize the supplied immutable plan."""


class _DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _validate_sha256(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    if len(value) != _SHA256_LENGTH or any(char not in _HEX_DIGITS for char in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _unique_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be an array of candidate keys")
    values: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{field_name} must contain only non-empty strings")
        if item in seen:
            raise ValueError(f"{field_name} cannot contain duplicate keys")
        seen.add(item)
        values.append(item)
    return tuple(values)


def _decision_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object keyed by planner key")
    result: dict[str, Any] = {}
    for key, decision in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{field_name} keys must be non-empty strings")
        result[key] = decision
    return result


class DecisionSet(_DecisionModel):
    """Versioned operator input; ``None`` values are non-applicable placeholders."""

    schema_version: Literal[1] = DECISIONS_SCHEMA_VERSION
    zip_sha256: str
    plan_semantic_sha256: str
    accept_all_safe_exact: StrictBool | None = None
    accepted_reference_candidates: tuple[str, ...] = ()
    weak_suggestion_decisions: dict[str, WeakSuggestionDecision | None] = Field(
        default_factory=dict
    )
    locator_review_decisions: dict[str, LocatorReviewDecision | None] = Field(default_factory=dict)

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_exact_integer(cls, value: Any) -> int:
        if type(value) is not int or value != DECISIONS_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be exactly {DECISIONS_SCHEMA_VERSION}")
        return value

    @field_validator("zip_sha256", "plan_semantic_sha256")
    @classmethod
    def hashes_are_canonical(cls, value: Any, info: Any) -> str:
        return _validate_sha256(value, info.field_name)

    @field_validator("accepted_reference_candidates", mode="before")
    @classmethod
    def accepted_keys_are_unique(cls, value: Any) -> tuple[str, ...]:
        return _unique_string_tuple(value, "accepted_reference_candidates")

    @field_validator("weak_suggestion_decisions", mode="before")
    @classmethod
    def weak_decisions_are_a_mapping(cls, value: Any) -> dict[str, Any]:
        return _decision_mapping(value, "weak_suggestion_decisions")

    @field_validator("locator_review_decisions", mode="before")
    @classmethod
    def locator_decisions_are_a_mapping(cls, value: Any) -> dict[str, Any]:
        return _decision_mapping(value, "locator_review_decisions")


class ValidatedDecisions(_DecisionModel):
    """Complete decisions bound to one exact ZIP and semantic plan."""

    decisions: DecisionSet
    decisions_sha256: str
    effective_reference_candidates: tuple[str, ...]
    weak_suggestion_keys: tuple[str, ...]
    locator_review_keys: tuple[str, ...]

    @field_validator("decisions_sha256")
    @classmethod
    def hash_is_canonical(cls, value: Any) -> str:
        return _validate_sha256(value, "decisions_sha256")


def canonical_decisions_payload(decisions: DecisionSet) -> dict[str, Any]:
    """Return an order-independent payload without changing decision semantics."""
    return {
        "schema_version": decisions.schema_version,
        "zip_sha256": decisions.zip_sha256,
        "plan_semantic_sha256": decisions.plan_semantic_sha256,
        "accept_all_safe_exact": decisions.accept_all_safe_exact,
        "accepted_reference_candidates": sorted(decisions.accepted_reference_candidates),
        "weak_suggestion_decisions": {
            key: decisions.weak_suggestion_decisions[key]
            for key in sorted(decisions.weak_suggestion_decisions)
        },
        "locator_review_decisions": {
            key: decisions.locator_review_decisions[key]
            for key in sorted(decisions.locator_review_decisions)
        },
    }


def decisions_sha256(decisions: DecisionSet) -> str:
    """Hash typed decisions independently of JSON object/list ordering."""
    return sha256_digest(canonical_decisions_payload(decisions))


def decisions_json(decisions: DecisionSet, *, pretty: bool = True) -> str:
    """Serialize decisions deterministically; templates retain explicit ``null`` values."""
    payload = canonical_decisions_payload(decisions)
    if not pretty:
        return canonical_json(payload) + "\n"
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


def build_decisions_template(plan: MigrationPlan) -> DecisionSet:
    """Build a deliberately incomplete template without silently accepting anything."""
    return DecisionSet(
        zip_sha256=plan.input_snapshot.sha256,
        plan_semantic_sha256=plan.semantic_sha256,
        accept_all_safe_exact=None,
        accepted_reference_candidates=(),
        weak_suggestion_decisions={
            item.suggestion_key: None
            for item in sorted(
                plan.weak_reference_suggestions,
                key=lambda value: value.suggestion_key,
            )
        },
        locator_review_decisions={
            item.review_key: None
            for item in sorted(plan.review_items, key=lambda value: value.review_key)
        },
    )


def _set_mismatch(label: str, supplied: set[str], expected: set[str]) -> str | None:
    missing = sorted(expected - supplied)
    unknown = sorted(supplied - expected)
    if not missing and not unknown:
        return None
    parts: list[str] = []
    if missing:
        parts.append(f"missing={missing}")
    if unknown:
        parts.append(f"unknown={unknown}")
    return f"{label} keys do not exactly match the plan ({'; '.join(parts)})"


def validate_decisions(
    decisions: DecisionSet,
    plan: MigrationPlan,
    *,
    expected_zip_sha256: str | None = None,
    expected_plan_sha256: str | None = None,
) -> ValidatedDecisions:
    """Fail closed unless every decision exactly covers the immutable supplied plan."""
    plan_zip_sha256 = plan.input_snapshot.sha256
    plan_semantic_sha256 = plan.semantic_sha256
    expected_zip = plan_zip_sha256 if expected_zip_sha256 is None else expected_zip_sha256
    expected_plan = plan_semantic_sha256 if expected_plan_sha256 is None else expected_plan_sha256
    _validate_sha256(expected_zip, "expected_zip_sha256")
    _validate_sha256(expected_plan, "expected_plan_sha256")

    issues: list[str] = []
    if expected_zip != plan_zip_sha256:
        issues.append("The expected ZIP hash does not match the plan input snapshot")
    if expected_plan != plan_semantic_sha256:
        issues.append("The expected plan hash does not match the supplied plan")
    if decisions.zip_sha256 != plan_zip_sha256 or decisions.zip_sha256 != expected_zip:
        issues.append("Decisions ZIP hash does not match the exact ZIP and plan")
    if (
        decisions.plan_semantic_sha256 != plan_semantic_sha256
        or decisions.plan_semantic_sha256 != expected_plan
    ):
        issues.append("Decisions plan hash does not match the exact semantic plan")

    all_reference_keys = {item.reference_candidate_key for item in plan.reference_candidates}
    safe_exact_keys = {
        item.reference_candidate_key
        for item in plan.reference_candidates
        if item.classification == ReviewStatus.SAFE_EXACT
    }
    unresolved_reference_keys = all_reference_keys - safe_exact_keys
    if unresolved_reference_keys:
        issues.append(
            "The plan contains non-safe-exact Reference candidates without a supported "
            f"S1C2A decision: {sorted(unresolved_reference_keys)}"
        )

    explicit_accepted = set(decisions.accepted_reference_candidates)
    unknown_accepted = explicit_accepted - all_reference_keys
    non_safe_accepted = explicit_accepted - safe_exact_keys
    if unknown_accepted:
        issues.append(f"Unknown accepted Reference candidate keys: {sorted(unknown_accepted)}")
    if non_safe_accepted:
        issues.append(
            "Only safe_exact Reference candidates may be accepted in S1C2A: "
            f"{sorted(non_safe_accepted)}"
        )
    if decisions.accept_all_safe_exact is None:
        issues.append("accept_all_safe_exact is still an undecided template placeholder")
        effective_accepted = explicit_accepted
    elif decisions.accept_all_safe_exact:
        effective_accepted = safe_exact_keys | explicit_accepted
    else:
        effective_accepted = explicit_accepted
    accepted_mismatch = _set_mismatch(
        "Accepted Reference candidate",
        effective_accepted,
        safe_exact_keys,
    )
    if accepted_mismatch:
        issues.append(accepted_mismatch)

    expected_weak = {item.suggestion_key for item in plan.weak_reference_suggestions}
    supplied_weak = set(decisions.weak_suggestion_decisions)
    if mismatch := _set_mismatch("Weak suggestion decision", supplied_weak, expected_weak):
        issues.append(mismatch)
    undecided_weak = sorted(
        key for key, value in decisions.weak_suggestion_decisions.items() if value is None
    )
    if undecided_weak:
        issues.append(f"Weak suggestions are still undecided: {undecided_weak}")

    non_locator_reviews = sorted(
        item.review_key
        for item in plan.review_items
        if not item.problem_type.startswith("locator_")
    )
    if non_locator_reviews:
        issues.append(
            "The plan contains non-locator review items without a supported S1C2A "
            f"decision: {non_locator_reviews}"
        )
    expected_locator = {item.review_key for item in plan.review_items}
    supplied_locator = set(decisions.locator_review_decisions)
    if mismatch := _set_mismatch(
        "Locator review decision",
        supplied_locator,
        expected_locator,
    ):
        issues.append(mismatch)
    undecided_locator = sorted(
        key for key, value in decisions.locator_review_decisions.items() if value is None
    )
    if undecided_locator:
        issues.append(f"Locator reviews are still undecided: {undecided_locator}")

    if issues:
        raise DecisionValidationError("; ".join(issues))

    return ValidatedDecisions(
        decisions=decisions,
        decisions_sha256=decisions_sha256(decisions),
        effective_reference_candidates=tuple(sorted(effective_accepted)),
        weak_suggestion_keys=tuple(sorted(expected_weak)),
        locator_review_keys=tuple(sorted(expected_locator)),
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Unsupported JSON constant: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_decisions(
    path: str | os.PathLike[str],
    *,
    max_bytes: int = DEFAULT_MAX_DECISIONS_BYTES,
) -> DecisionSet:
    """Read one bounded regular JSON file without following symbolic links."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise TypeError("max_bytes must be an integer")
    if max_bytes < 1 or max_bytes > HARD_MAX_DECISIONS_BYTES:
        raise ValueError(f"max_bytes must be between 1 and {HARD_MAX_DECISIONS_BYTES}")
    lexical = Path(os.path.abspath(Path(path).expanduser()))
    if find_symlink_component(lexical) is not None:
        raise DecisionFileError("Symbolic links are not allowed in decisions paths")

    try:
        lexical_status = lexical.lstat()
    except OSError as exc:
        raise DecisionFileError("Unable to read the decisions file safely") from exc
    if not stat.S_ISREG(lexical_status.st_mode):
        raise DecisionFileError("Decisions input must be a regular file")

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    descriptor: int | None = None
    try:
        descriptor = os.open(lexical, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise DecisionFileError("Decisions input must be a regular file")
        if before.st_size > max_bytes:
            raise DecisionFileError("Decisions input exceeds the configured size limit")
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = None
            payload = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
        if len(payload) > max_bytes:
            raise DecisionFileError("Decisions input exceeds the configured size limit")
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_identity != after_identity:
            raise DecisionFileError("Decisions input changed while it was being read")
    except DecisionFileError:
        raise
    except OSError as exc:
        raise DecisionFileError("Unable to read the decisions file safely") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)

    try:
        text = payload.decode("utf-8")
        raw = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DecisionFileError("Decisions input must be canonical UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise DecisionFileError("Decisions JSON root must be an object")
    if "schema_version" not in raw:
        raise DecisionFileError("Decisions input must declare schema_version")
    try:
        return DecisionSet.model_validate(raw)
    except ValidationError as exc:
        raise DecisionFileError("Decisions input does not match schema version 1") from exc


# Descriptive aliases for callers that use the full phase terminology.
HumanDecisions = DecisionSet
SourceCatalogMigrationDecisions = DecisionSet


__all__ = [
    "DECISIONS_SCHEMA_VERSION",
    "DEFAULT_MAX_DECISIONS_BYTES",
    "DecisionError",
    "DecisionFileError",
    "DecisionSet",
    "DecisionValidationError",
    "HARD_MAX_DECISIONS_BYTES",
    "HumanDecisions",
    "LocatorReviewDecision",
    "SourceCatalogMigrationDecisions",
    "ValidatedDecisions",
    "WeakSuggestionDecision",
    "build_decisions_template",
    "canonical_decisions_payload",
    "decisions_json",
    "decisions_sha256",
    "load_decisions",
    "validate_decisions",
]

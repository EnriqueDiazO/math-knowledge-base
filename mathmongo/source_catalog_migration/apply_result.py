"""Typed, bounded outcomes for the S1C2 Source Catalog bootstrap."""

# ruff: noqa: D101,D102

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import StrictBool
from pydantic import field_validator
from pydantic import model_validator

APPLY_RESULT_SCHEMA_VERSION = 1
MAX_RESULT_ERRORS = 8
MAX_RESULT_ERROR_CHARS = 400
MAX_NEXT_ACTION_CHARS = 300
_SHA256_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")
_MONGO_URI_RE = re.compile(r"mongodb(?:\+srv)?://[^\s'\"<>]+", re.IGNORECASE)
_CREDENTIAL_RE = re.compile(
    r"(?i)(?P<prefix>[\"']?(?:password|passwd|pwd|token|secret|api[_-]?key|"
    r"access[_-]?token|authorization)[\"']?\s*[=:]\s*)"
    r"(?P<value>[\"'][^\"']*[\"']|[^,;}\]]+)"
)
_INTERNAL_PATH_RE = re.compile(
    r"(?<![\w/])/(?:home|Users|root|tmp|var|opt|srv|mnt|workspace|private|usr|etc|Library)"
    r"(?:/[^\s,;:'\"<>\])]+)+"
)


class ApplyOutcome(str, Enum):
    """Stable disposition of one prepared or attempted bootstrap invocation."""

    PREPARED = "prepared"
    APPLIED = "applied"
    RESUMED = "resumed"
    ALREADY_APPLIED = "already_applied"
    IDENTICAL = "identical"
    BLOCKED = "blocked"
    CONFLICT = "conflict"
    FAILED = "failed"


class _ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _canonical_hash(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    if len(value) != _SHA256_LENGTH or any(char not in _HEX_DIGITS for char in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def safe_apply_diagnostic(value: Any, *, max_characters: int = MAX_RESULT_ERROR_CHARS) -> str:
    """Redact credentials, MongoDB URIs, local paths, traces, and excess detail."""
    message = str(value or "The operation failed without a diagnostic")
    message = _MONGO_URI_RE.sub("<redacted MongoDB URI>", message)
    message = _CREDENTIAL_RE.sub(
        lambda match: f"{match.group('prefix')}<redacted>",
        message,
    )
    message = _INTERNAL_PATH_RE.sub("<redacted local path>", message)
    message = message.replace("Traceback (most recent call last):", "")
    message = " ".join(message.split())
    if len(message) > max_characters:
        message = message[: max_characters - 1].rstrip() + "…"
    return message or "The operation failed without a safe diagnostic"


class IndexApplyResult(_ResultModel):
    """Bounded summary of the explicit Source Catalog index cycle."""

    planned: tuple[str, ...] = ()
    applied: tuple[str, ...] = ()
    already_present: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    final_state_sha256: str | None = None

    @field_validator("planned", "applied", "already_present", "conflicts", mode="before")
    @classmethod
    def index_names_are_unique(cls, value: Any, info: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str) or not isinstance(value, (list, tuple)):
            raise ValueError(f"{info.field_name} must be an array of index names")
        if len(value) > 64:
            raise ValueError(f"{info.field_name} cannot contain more than 64 index names")
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str) or not item or len(item) > 160:
                raise ValueError(f"{info.field_name} must contain non-empty strings")
            if item in seen:
                raise ValueError(f"{info.field_name} cannot contain duplicates")
            seen.add(item)
            result.append(item)
        return tuple(result)

    @field_validator("final_state_sha256")
    @classmethod
    def final_hash_is_canonical(cls, value: Any) -> str | None:
        return None if value is None else _canonical_hash(value, "final_state_sha256")


class ApplyResult(_ResultModel):
    """Safe report payload for preparation, application, resume, or failure."""

    schema_version: Literal[1] = APPLY_RESULT_SCHEMA_VERSION
    outcome: ApplyOutcome
    target_database: str
    migration_id: str | None = None
    zip_sha256: str
    plan_semantic_sha256: str
    decisions_sha256: str | None = None
    expected_sources: int
    sources_created: int = 0
    sources_identical: int = 0
    expected_references: int
    references_created: int = 0
    references_identical: int = 0
    indexes: IndexApplyResult = Field(default_factory=IndexApplyResult)
    manifest_state: str | None = None
    invariant_hashes_before: dict[str, str] = Field(default_factory=dict)
    invariant_hashes_after: dict[str, str] = Field(default_factory=dict)
    invariants_passed: StrictBool = False
    errors: tuple[str, ...] = ()
    next_action: str

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_exact_integer(cls, value: Any) -> int:
        if type(value) is not int or value != APPLY_RESULT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be exactly {APPLY_RESULT_SCHEMA_VERSION}")
        return value

    @field_validator("target_database", "manifest_state", mode="before")
    @classmethod
    def bounded_labels(cls, value: Any, info: Any) -> str | None:
        if value is None and info.field_name == "manifest_state":
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{info.field_name} must be non-empty text")
        text = value.strip()
        if len(text) > 160:
            raise ValueError(f"{info.field_name} is too long")
        return text

    @field_validator("migration_id")
    @classmethod
    def migration_id_is_uuid4(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith("mig_"):
            raise ValueError("migration_id must be mig_<uuid4>")
        suffix = value[4:]
        try:
            parsed = UUID(suffix)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("migration_id must be mig_<uuid4>") from exc
        if parsed.version != 4 or str(parsed) != suffix:
            raise ValueError("migration_id must be a canonical lowercase mig_<uuid4>")
        return value

    @field_validator("zip_sha256", "plan_semantic_sha256")
    @classmethod
    def required_hashes_are_canonical(cls, value: Any, info: Any) -> str:
        return _canonical_hash(value, info.field_name)

    @field_validator("decisions_sha256")
    @classmethod
    def decisions_hash_is_canonical(cls, value: Any) -> str | None:
        return None if value is None else _canonical_hash(value, "decisions_sha256")

    @field_validator(
        "expected_sources",
        "sources_created",
        "sources_identical",
        "expected_references",
        "references_created",
        "references_identical",
        mode="before",
    )
    @classmethod
    def counts_are_nonnegative_integers(cls, value: Any, info: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{info.field_name} must be a non-negative integer")
        return value

    @field_validator("invariant_hashes_before", "invariant_hashes_after", mode="before")
    @classmethod
    def invariant_hashes_are_canonical(cls, value: Any, info: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{info.field_name} must be an object")
        if len(value) > 32:
            raise ValueError(f"{info.field_name} cannot contain more than 32 entries")
        result: dict[str, str] = {}
        for key, digest in value.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise ValueError(f"{info.field_name} keys must be bounded non-empty text")
            result[key] = _canonical_hash(digest, f"{info.field_name}.{key}")
        return result

    @field_validator("errors", mode="before")
    @classmethod
    def errors_are_bounded_and_redacted(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        values = [value] if isinstance(value, str) else list(value)
        return tuple(safe_apply_diagnostic(item) for item in values[:MAX_RESULT_ERRORS])

    @field_validator("next_action", mode="before")
    @classmethod
    def next_action_is_bounded(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("next_action must be non-empty text")
        text = safe_apply_diagnostic(value, max_characters=MAX_NEXT_ACTION_CHARS)
        if not text:
            raise ValueError("next_action must be non-empty")
        return text

    @model_validator(mode="after")
    def result_counts_are_possible(self) -> ApplyResult:
        if self.sources_created + self.sources_identical > self.expected_sources:
            raise ValueError("Source result counts exceed expected_sources")
        if self.references_created + self.references_identical > self.expected_references:
            raise ValueError("Reference result counts exceed expected_references")
        return self

    @property
    def status(self) -> ApplyOutcome:
        """Compatibility spelling for callers that call the disposition status."""
        return self.outcome


def render_apply_result_json(result: ApplyResult) -> str:
    """Render stable JSON containing only the bounded typed result."""
    return (
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def render_apply_result_text(result: ApplyResult) -> str:
    """Render a bounded operational summary without URI or document bodies."""
    migration_id = result.migration_id or "not allocated"
    decisions_hash = result.decisions_sha256 or "not available"
    lines = [
        "MathMongo S1C2A Source Catalog bootstrap result",
        f"Outcome: {result.outcome.value}",
        f"Target database: {result.target_database}",
        f"Migration ID: {migration_id}",
        f"ZIP SHA-256: {result.zip_sha256}",
        f"Plan SHA-256: {result.plan_semantic_sha256}",
        f"Decisions SHA-256: {decisions_hash}",
        (
            "Sources: "
            f"expected={result.expected_sources}; created={result.sources_created}; "
            f"identical={result.sources_identical}"
        ),
        (
            "References: "
            f"expected={result.expected_references}; created={result.references_created}; "
            f"identical={result.references_identical}"
        ),
        (
            "Indexes: "
            f"planned={len(result.indexes.planned)}; applied={len(result.indexes.applied)}; "
            f"already_present={len(result.indexes.already_present)}; "
            f"conflicts={len(result.indexes.conflicts)}"
        ),
        f"Index state SHA-256: {result.indexes.final_state_sha256 or 'not available'}",
        f"Manifest state: {result.manifest_state or 'not created'}",
        f"Invariants passed: {result.invariants_passed}",
    ]
    for name, digest in sorted(result.invariant_hashes_before.items()):
        lines.append(f"Invariant before {name}: {digest}")
    for name, digest in sorted(result.invariant_hashes_after.items()):
        lines.append(f"Invariant after {name}: {digest}")
    lines.extend(f"Error: {error}" for error in result.errors)
    lines.append(f"Next action: {result.next_action}")
    return "\n".join(lines) + "\n"


def render_apply_result(result: ApplyResult, output_format: str) -> str:
    """Render one apply result as bounded text or deterministic JSON."""
    if output_format == "json":
        return render_apply_result_json(result)
    if output_format == "text":
        return render_apply_result_text(result)
    raise ValueError(f"Unsupported apply result format: {output_format}")


# Semantic aliases used by the bootstrap engine and CLI layers.
BootstrapOutcome = ApplyOutcome
BootstrapResult = ApplyResult
ApplyResultStatus = ApplyOutcome


__all__ = [
    "APPLY_RESULT_SCHEMA_VERSION",
    "ApplyOutcome",
    "ApplyResult",
    "ApplyResultStatus",
    "BootstrapOutcome",
    "BootstrapResult",
    "IndexApplyResult",
    "MAX_RESULT_ERRORS",
    "MAX_RESULT_ERROR_CHARS",
    "render_apply_result",
    "render_apply_result_json",
    "render_apply_result_text",
    "safe_apply_diagnostic",
]

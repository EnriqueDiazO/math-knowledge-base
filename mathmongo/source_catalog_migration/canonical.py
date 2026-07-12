"""Canonical JSON and namespaced SHA-256 helpers for S1C1."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from datetime import date
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from mathmongo.source_catalog_migration.models import PLANNER_NAMESPACE
from mathmongo.source_catalog_migration.models import PLANNER_VERSION


def json_safe(value: Any) -> Any:
    """Convert BSON/Pydantic values to a portable, deterministic JSON tree."""
    if isinstance(value, BaseModel):
        return json_safe(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return json_safe(value.value)
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        safe_items = [json_safe(item) for item in value]
        return sorted(safe_items, key=canonical_json)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"$binary_base64": base64.b64encode(value).decode("ascii")}
    # ObjectId and other small BSON scalar wrappers have stable string forms.
    if value.__class__.__module__.startswith("bson"):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(value: Any) -> str:
    """Serialize a portable tree without whitespace or key-order variation."""
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_digest(value: Any) -> str:
    """Hash one canonical payload with SHA-256."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def candidate_key(kind: str, content: Any) -> str:
    """Build a deterministic candidate key namespaced by planner version."""
    digest = sha256_digest(
        {
            "namespace": PLANNER_NAMESPACE,
            "planner_version": PLANNER_VERSION,
            "kind": kind,
            "content": content,
        }
    )
    return f"{kind}_{digest}"


__all__ = ["candidate_key", "canonical_json", "json_safe", "sha256_digest"]

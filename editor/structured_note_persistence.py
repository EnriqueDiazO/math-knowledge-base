"""Minimal snapshot updates shared by the established Cornell and CPI services."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from pymongo.results import UpdateResult


class StructuredSourceConflictError(ValueError):
    """A stored historical projection cannot be regenerated without an explicit decision."""


def merge_known_fields(raw, before, after):
    """Change known values while retaining unknown keys and absent lazy defaults."""
    if before == after:
        return deepcopy(raw)
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        result = deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
        for key, value in after.items():
            if key not in before or value != before[key]:
                result[key] = merge_known_fields(result.get(key), before.get(key), value)
        for key in before.keys() - after.keys():
            result.pop(key, None)
        return result
    return deepcopy(after)


def validated_page_origins(before, after, origins):
    """Validate explicit page ownership separately from displayed order/number."""
    identity = (
        "page_id"
        if any("page_id" in page for page in before["pages"] + after["pages"])
        else "page_number"
    )
    defaults = [page[identity] for page in after["pages"]]
    if origins is None:
        return identity, defaults
    if len(origins) != len(defaults):
        raise ValueError("Page origins must match the proposed page count")
    previous = {page[identity] for page in before["pages"]}
    if any(key is not None and key not in previous for key in origins):
        raise ValueError("A page origin is not part of the observed note")
    return identity, list(origins)


def merge_structured_document(raw, before, after, *, page_origins=None):
    """Preserve page-owned unknown fields across an explicit page reorder or duplication."""
    identity, origins = validated_page_origins(before, after, page_origins)
    result = merge_known_fields(
        raw,
        {k: v for k, v in before.items() if k != "pages"},
        {k: v for k, v in after.items() if k != "pages"},
    )
    previous = {page[identity]: page for page in before["pages"]}
    original = {page[identity]: page for page in raw.get("pages", [])}
    pages = []
    for index, page in enumerate(after["pages"]):
        key = origins[index]
        pages.append(merge_known_fields(original.get(key), previous.get(key), page))
    result["pages"] = pages
    return result


def update_structured_note(db, existing, candidate, before_payload, field, *, page_origins=None):
    """Use one canonical facade write; older adapters keep their established call signature."""
    updater = getattr(type(db), "update_notebook_note_from_snapshot", None)
    if not callable(updater):
        return db.update_notebook_note(existing["_id"], candidate)
    changes = {
        key: deepcopy(value)
        for key, value in candidate.items()
        if key not in {field, "latex_body", "image_ids"} and existing.get(key) != value
    }
    before, after = before_payload[field], candidate[field]
    identity, origins = validated_page_origins(before, after, page_origins)
    origins_changed = origins != [page[identity] for page in after["pages"]]
    if before != after or origins_changed:
        if before != after and existing.get("latex_body", "") != before_payload["latex_body"]:
            raise StructuredSourceConflictError(
                "La fuente histórica y sus regiones no coinciden. Conserva el original y revisa la estructura antes de regenerarla."
            )
        changes[field] = merge_structured_document(
            existing[field], before, after, page_origins=page_origins
        )
        if before != after:
            changes["latex_body"] = candidate["latex_body"]
            changes["image_ids"] = candidate["image_ids"]
    if not changes:
        return UpdateResult({"n": 1, "nModified": 0, "ok": 1.0}, acknowledged=True)
    return updater(db, existing, changes)

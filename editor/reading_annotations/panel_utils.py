"""Shared presentation helpers for typed S4 service results."""

from __future__ import annotations

from typing import Any

from editor.source_catalog.shared import safe_error_message


def enum_value(value: Any) -> str:
    """Return a stable string for enums and already-normalized values."""
    return str(getattr(value, "value", value))


def result_ok(result: Any) -> bool:
    """Recognize the common typed success result without importing UI state."""
    completed = getattr(result, "completed", None)
    if completed is not None:
        return bool(completed)
    return enum_value(getattr(result, "status", "error")) == "success"


def result_items(result: Any) -> tuple[Any, ...]:
    """Extract a bounded tuple from a typed page result."""
    value = getattr(result, "value", None)
    if value is None:
        return ()
    items = getattr(value, "items", value)
    try:
        return tuple(items)
    except TypeError:
        return ()


def render_result(ui: Any, result: Any, *, success: str) -> bool:
    """Render a safe typed outcome and return whether it completed."""
    ok = result_ok(result)
    status = enum_value(getattr(result, "status", "error"))
    message = safe_error_message(getattr(result, "message", "") or success)
    if ok:
        ui.success(message)
    elif status in {"not_found", "archived"}:
        ui.warning(message)
    else:
        ui.error(message)
    return ok


def local_match(
    record: Any,
    *,
    query: str,
    record_type: str,
    required_type: str,
) -> bool:
    """Apply a bounded in-page metadata filter without inspecting PDF content."""
    if required_type and required_type != "all" and record_type != required_type:
        return False
    needle = query.strip().casefold()
    if not needle:
        return True
    fields = (
        getattr(record, "title", ""),
        getattr(record, "body", ""),
        getattr(record, "quote_text", ""),
        " ".join(getattr(record, "tags", ()) or ()),
    )
    return any(needle in str(value or "").casefold() for value in fields)


__all__ = ["enum_value", "local_match", "render_result", "result_items", "result_ok"]

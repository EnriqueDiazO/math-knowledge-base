"""Shared UI decision for creating or associating a Reference candidate."""

from __future__ import annotations

from typing import Any

from editor.source_catalog.state import draft_fingerprint
from editor.source_catalog.state import state_key
from editor.source_catalog.workflows import ReferenceSavePlan
from editor.source_catalog.workflows import duplicate_confirmation_required
from mathmongo.source_catalog.models import Reference


def render_reference_save_plan(
    ui: Any,
    *,
    key_prefix: str,
    label: str,
    reference: Reference,
    duplicates: tuple[Any, ...],
    confirmed_duplicate: bool = False,
) -> tuple[ReferenceSavePlan | None, bool]:
    """Choose a new Reference or an explicit association to an existing one."""
    matches = list(duplicates)
    decision_key = f"{key_prefix}_{draft_fingerprint(reference)}"
    has_strong = any(match.classification.value in {"exact", "strong"} for match in matches)
    options = ["create:new", *(f"associate:{match.entity_id}" for match in matches)]
    choice = ui.selectbox(
        f"Action for {label}",
        options,
        index=1 if has_strong else 0,
        format_func=lambda value: (
            "Create a separate Reference"
            if value == "create:new"
            else f"Associate existing {value.split(':', 1)[1]}"
        ),
        key=state_key(decision_key, "action"),
    )
    if choice.startswith("associate:"):
        return (
            ReferenceSavePlan(
                label=label,
                existing_reference_id=choice.split(":", 1)[1],
            ),
            True,
        )

    needs_confirmation = duplicate_confirmation_required(matches)
    confirmed = confirmed_duplicate
    if needs_confirmation and not confirmed:
        confirmed = ui.checkbox(
            "I reviewed exact/strong/possible matches and want a separate Reference",
            key=state_key(decision_key, "allow_duplicate"),
        )
    allow_duplicate = bool(matches) and (confirmed or not needs_confirmation)
    return (
        ReferenceSavePlan(
            label=label,
            candidate=reference,
            allow_duplicate=allow_duplicate,
        ),
        not needs_confirmation or confirmed,
    )


__all__ = ["render_reference_save_plan"]

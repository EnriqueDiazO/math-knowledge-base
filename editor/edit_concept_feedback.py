"""Scoped post-rerun feedback for the Edit Concept update workflow."""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

from editor.db.concept_edit_service import ConceptEditResult
from editor.db.concept_edit_service import ConceptEditStatus

SESSION_PREFIX = "edit_concept_update_feedback_"
SCOPE_KEY = f"{SESSION_PREFIX}database_scope"
FLASH_KEY = f"{SESSION_PREFIX}flash"


@dataclass(frozen=True)
class UpdateFeedback:
    """Visible UI feedback derived from one structured service result."""

    level: str
    message: str


def _concept_label(concept_id: str, source: str) -> str:
    source_suffix = f" — {source}" if source else ""
    return f"{concept_id}{source_suffix}"


def feedback_for_update_result(
    result: ConceptEditResult,
    *,
    concept_id: str,
    source: str,
) -> UpdateFeedback:
    """Map every service status to explicit, non-ambiguous user feedback."""
    label = _concept_label(concept_id, source)
    if result.status is ConceptEditStatus.SUCCESS:
        no_changes = (
            result.concept_matched_count == 1
            and result.latex_matched_count == 1
            and result.concept_modified_count == 0
            and result.latex_modified_count == 0
        )
        if no_changes:
            return UpdateFeedback(
                level="success",
                message=(
                    f"Concepto confirmado sin cambios: {label}. "
                    "El contenido persistido ya era idéntico."
                ),
            )
        return UpdateFeedback(
            level="success",
            message=f"Concepto actualizado correctamente: {label}.",
        )
    if result.status is ConceptEditStatus.CONCEPT_NOT_FOUND:
        return UpdateFeedback(
            level="error",
            message=(
                f"El concepto original ya no existe: {label}. "
                "No se guardó ningún cambio."
            ),
        )
    if result.status is ConceptEditStatus.LATEX_NOT_FOUND:
        return UpdateFeedback(
            level="error",
            message=(
                f"Falta el documento LaTeX correspondiente a {label}. "
                "La inconsistencia impidió la actualización."
            ),
        )
    if result.status is ConceptEditStatus.STALE_IDENTITY:
        return UpdateFeedback(
            level="warning",
            message=(
                f"La identidad almacenada de {label} cambió desde que se abrió el formulario. "
                "Recarga el concepto antes de volver a intentarlo."
            ),
        )
    if result.status is ConceptEditStatus.FAILED_COMPENSATED:
        return UpdateFeedback(
            level="error",
            message=(
                f"La actualización coordinada de {label} falló y fue revertida; "
                "no quedó una actualización persistente."
            ),
        )
    return UpdateFeedback(
        level="error",
        message=(
            f"La actualización de {label} puede haber quedado parcial y requiere recuperación "
            f"antes de reintentar. Detalles: {result.message}"
        ),
    )


def sync_update_feedback_scope(
    state: MutableMapping[str, Any],
    database_scope: str | None,
) -> bool:
    """Discard pending Edit Concept feedback when the active database changes."""
    missing = object()
    previous = state.get(SCOPE_KEY, missing)
    changed = previous is not missing and previous != database_scope
    if changed:
        state.pop(FLASH_KEY, None)
    state[SCOPE_KEY] = database_scope
    return changed


def store_update_success_flash(
    state: MutableMapping[str, Any],
    result: ConceptEditResult,
    *,
    database_scope: str | None,
    concept_id: str,
    source: str,
) -> bool:
    """Persist feedback only when the structured service result is successful."""
    feedback = feedback_for_update_result(
        result,
        concept_id=concept_id,
        source=source,
    )
    if feedback.level != "success":
        return False
    state[SCOPE_KEY] = database_scope
    state[FLASH_KEY] = {
        "level": feedback.level,
        "message": feedback.message,
        "concept_id": concept_id,
        "source": source,
        "database_scope": database_scope,
    }
    return True


def render_update_flash(
    ui: Any,
    state: MutableMapping[str, Any],
    *,
    database_scope: str | None,
    concept_id: str,
    source: str,
) -> bool:
    """Consume and render one flash only for its original database and concept."""
    value = state.pop(FLASH_KEY, None)
    if not isinstance(value, dict):
        return False
    if (
        value.get("database_scope") != database_scope
        or value.get("concept_id") != concept_id
        or value.get("source") != source
    ):
        return False
    level = value.get("level")
    message = value.get("message")
    if level not in {"success", "info", "warning", "error"} or not isinstance(
        message, str
    ):
        return False
    renderer = getattr(ui, level)
    renderer(message)
    return True


def safe_update_exception_message(_error: Exception) -> str:
    """Return safe feedback without exposing connection details or clearing drafts."""
    return (
        "Ocurrió un error inesperado al actualizar el concepto. "
        "No se limpió el formulario; revisa la conexión y vuelve a intentarlo."
    )


__all__ = [
    "FLASH_KEY",
    "SESSION_PREFIX",
    "SCOPE_KEY",
    "UpdateFeedback",
    "feedback_for_update_result",
    "render_update_flash",
    "safe_update_exception_message",
    "store_update_success_flash",
    "sync_update_feedback_scope",
]

"""Contextual confirmations and recovery over the single concept-deletion service."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from mathmongo.concepts.deletion import ConceptDeletionService

PREFIX = "concept_delete_"


def _scope(database):
    return hashlib.sha256(f"{database.name}:{id(database):x}".encode()).hexdigest()[:20]


def _run(ui, database, key, entry):
    result = ConceptDeletionService(database).delete(entry["plan"], entry["operation_id"])
    if result.completed:
        ui.session_state.pop(key, None)
        ui.session_state[PREFIX + "flash_" + _scope(database)] = result.message
        ui.rerun()
    entry["partial"] = result.status == "partial"
    ui.session_state[key] = entry
    ui.error(result.message)


def render_deletion_feedback(ui, database):
    """Recover a failed acknowledged operation even if its concept row disappeared."""
    if database is None:
        return
    scope = _scope(database)
    flash = ui.session_state.pop(PREFIX + "flash_" + scope, None)
    if flash:
        ui.success(flash)
    for key in tuple(ui.session_state):
        if not str(key).startswith(PREFIX + "operation_" + scope):
            continue
        entry = ui.session_state[key]
        if not isinstance(entry, dict) or not entry.get("partial"):
            continue
        ui.warning(
            f'La eliminación de «{entry["title"]}» quedó sin confirmar. Se conserva el mismo intento para recuperarla; no se borran cambios ajenos.'
        )
        if ui.button("Reintentar eliminación de «" + entry["title"] + "»", key=key + "_retry"):
            _run(ui, database, key, entry)


def render_concept_deletion(ui, database, concept, *, scope):
    """Bind the name confirmation and snapshot to the selected DB/object identity."""
    token = hashlib.sha256(
        repr((concept.get("_id"), concept["id"], concept["source"], scope)).encode()
    ).hexdigest()[:20]
    key = PREFIX + "operation_" + _scope(database) + "_" + token
    if ui.button("Eliminar concepto…", key=key + "_arm"):
        try:
            plan = ConceptDeletionService(database).plan(concept["id"], concept["source"])
            if plan.blocked:
                ui.warning(plan.blocked)
            else:
                ui.session_state[key] = {
                    "plan": plan,
                    "operation_id": str(uuid4()),
                    "title": concept.get("titulo") or str(concept["id"]),
                    "partial": False,
                }
        except Exception:
            ui.error(
                "No se pudo comprobar la eliminación. Comprueba la conexión y vuelve a abrir este concepto; no se aplicó un borrado."
            )
    entry = ui.session_state.get(key)
    if not isinstance(entry, dict) or entry.get("partial"):
        return
    ui.warning(
        f'Se eliminará «{entry["title"]}» y sus relaciones de esta biblioteca. Las notas, referencias, documentos y archivos se conservan. Los vínculos de procedencia o esferas guardadas bloquean esta acción.'
    )
    confirmation = ui.text_input("Escribe el nombre del concepto para confirmar", key=key + "_name")
    if ui.button(
        "Confirmar eliminación", key=key + "_confirm", disabled=confirmation != entry["title"]
    ):
        _run(ui, database, key, entry)
    if ui.button("Cancelar eliminación", key=key + "_cancel"):
        ui.session_state.pop(key, None)
        ui.rerun()

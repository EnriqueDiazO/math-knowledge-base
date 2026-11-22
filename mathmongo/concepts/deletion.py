"""Recoverable concept deletion on standalone MongoDB, without destructive repair.

Evidence and explicit saved-map memberships block deletion. Bibliographic sources,
notes, documents and media bytes are retained. Relations are removed by their
observed BSON identity; changed records are never erased by compensation.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pymongo.errors import PyMongoError

from mathmongo.concurrency import digest
from mathmongo.concurrency import exact_document


@dataclass(frozen=True)
class DeletionPlan:
    """A backend snapshot bound to one database object and one composite identity."""

    context: str
    identity: dict
    snapshot: dict
    revision: str
    blocked: str = ""


@dataclass(frozen=True)
class DeletionResult:
    """Success requires a confirmed final read; partial work retains its journal."""

    status: str
    message: str

    @property
    def completed(self):
        """Only a verified removal can be announced as deleted."""
        return self.status == "deleted"


class ConceptDeletionService:
    """Share one contract between compatibility pages and future HTTP consumers."""

    def __init__(self, database):
        """Bind without maintenance or writes."""
        self.db = database
        self.context = f"{database.name}:{id(database):x}"
        self.operations = database["_knowledge_map_operations"]

    @staticmethod
    def relation_query(identity):
        """Recognize canonical string endpoints and historical structured endpoints."""
        key = f"{identity['id']}@{identity['source']}"
        return {
            "$or": [
                {"desde": key},
                {"hasta": key},
                {"desde_id": identity["id"], "desde_source": identity["source"]},
                {"hasta_id": identity["id"], "hasta_source": identity["source"]},
            ]
        }

    def _blocker(self, identity):
        evidence = {
            "concept_legacy_id": identity["id"],
            "concept_legacy_source": identity["source"],
        }
        if self.db.concept_evidence_links.find_one(evidence, {"_id": 1}):
            return "El concepto conserva vínculos de procedencia. Revisa sus vínculos en Lectura → Conocimiento antes de eliminarlo; las notas y documentos se conservan."
        key = f"{identity['id']}@{identity['source']}"
        if self.db.knowledge_graph_maps.find_one(
            {
                "$or": [
                    {"study_view.members": key},
                    {"graph_state.nodes.id": key},
                    {"graph_state.nodes.key": key},
                ]
            },
            {"_id": 1},
        ):
            return "El concepto pertenece a una esfera guardada. Abre Espacios y retíralo de esa vista antes de eliminarlo de la biblioteca."
        return ""

    def plan(self, concept_id, source):
        """Inspect all known dependency types without changing collections or records."""
        identity = {"id": concept_id, "source": source}
        concept = self.db.concepts.find_one(identity)
        latex = self.db.latex_documents.find_one(identity)
        relations = list(self.db.relations.find(self.relation_query(identity)).sort("_id", 1))
        snapshot = {"concept": concept, "latex": latex, "relations": relations}
        blocked = self._blocker(identity)
        if concept is None:
            blocked = "El concepto ya no está disponible. Actualiza la lista antes de continuar."
        elif concept.get("_delete_operation"):
            blocked = "Hay una eliminación sin confirmar. Recupera el mismo intento; no inicies otra eliminación."
        return DeletionPlan(self.context, identity, snapshot, digest(snapshot), blocked)

    def delete(self, plan: DeletionPlan, operation_id: str):
        """Claim the observed concept, remove only observed relations/content, verify."""
        if plan.context != self.context:
            return DeletionResult("conflict", "La biblioteca cambió. No se eliminó ningún dato.")
        try:
            UUID(operation_id)
        except (ValueError, TypeError):
            return DeletionResult("invalid", "El intento de eliminación no es válido.")
        try:
            record = self.operations.find_one({"_id": operation_id})
            if record is not None:
                if (
                    record.get("kind") != "concept_delete"
                    or record.get("delete_revision") != plan.revision
                ):
                    return DeletionResult(
                        "conflict",
                        "Este intento pertenece a otra operación. Conserva el contexto original.",
                    )
                if record.get("delete_completed"):
                    if self.db.concepts.find_one(plan.identity) or self.db.latex_documents.find_one(
                        plan.identity
                    ):
                        return DeletionResult(
                            "conflict",
                            "Hay un registro nuevo con esa identidad. El intento anterior no lo elimina.",
                        )
                    return DeletionResult(
                        "deleted", "Concepto eliminado y resultado confirmado anteriormente."
                    )
            else:
                current = self.plan(plan.identity["id"], plan.identity["source"])
                if current.blocked:
                    return DeletionResult("blocked", current.blocked)
                if current.revision != plan.revision:
                    return DeletionResult(
                        "conflict",
                        "El concepto o sus relaciones cambiaron. Revisa de nuevo antes de confirmar.",
                    )
                self.operations.insert_one(
                    {
                        "_id": operation_id,
                        "kind": "concept_delete",
                        "delete_revision": plan.revision,
                        "payload_hash": digest(["concept_delete", plan.revision]),
                        "delete_snapshot": plan.snapshot,
                        "delete_identity": plan.identity,
                    }
                )
            return self._remove(plan, operation_id)
        except PyMongoError:
            return DeletionResult(
                "partial",
                "No se confirmó la eliminación completa. Conserva este intento y reinténtalo; no se borran recursos compartidos ni cambios ajenos.",
            )

    def _remove(self, plan, operation_id):
        identity, before = plan.identity, plan.snapshot
        current = self.db.concepts.find_one(identity)
        if current is not None and current.get("_delete_operation") != operation_id:
            claimed = self.db.concepts.update_one(
                exact_document(before["concept"]), {"$set": {"_delete_operation": operation_id}}
            )
            if not claimed.matched_count:
                return DeletionResult(
                    "conflict", "Otro flujo modificó el concepto. No se borra su versión nueva."
                )
        blocker = self._blocker(identity)
        if blocker:
            self.db.concepts.update_one(
                {**identity, "_delete_operation": operation_id},
                {"$unset": {"_delete_operation": ""}},
            )
            return DeletionResult("blocked", blocker)
        for relation in before["relations"]:
            actual = self.db.relations.find_one({"_id": relation["_id"]})
            if (
                actual is not None
                and not self.db.relations.delete_one(exact_document(relation)).deleted_count
            ):
                return DeletionResult(
                    "partial",
                    "Una relación cambió durante la eliminación. Se conserva para revisión; recupera el mismo intento.",
                )
        if self.db.relations.find_one(self.relation_query(identity)):
            return DeletionResult(
                "partial",
                "Se detectó otra relación. No se elimina automáticamente; revisa el concepto y recupera este intento.",
            )
        latex = self.db.latex_documents.find_one(identity)
        if latex is not None:
            if (
                before["latex"] is None
                or not self.db.latex_documents.delete_one(
                    exact_document(before["latex"])
                ).deleted_count
            ):
                return DeletionResult(
                    "partial",
                    "El contenido cambió durante la eliminación. Se conserva su versión actual; recupera este intento tras revisarla.",
                )
        current = self.db.concepts.find_one(identity)
        if current is not None:
            expected = {**before["concept"], "_delete_operation": operation_id}
            if not self.db.concepts.delete_one(exact_document(expected)).deleted_count:
                return DeletionResult(
                    "partial",
                    "La ficha cambió. No se elimina una versión ajena; conserva el mismo intento para revisión.",
                )
        key = f"{identity['id']}@{identity['source']}"
        # The detach contract retains unreferenced files unless cleanup is explicit.
        self.db.media_assets.update_many({"concept_ids": key}, {"$pull": {"concept_ids": key}})
        if (
            self.db.concepts.find_one(identity)
            or self.db.latex_documents.find_one(identity)
            or self.db.relations.find_one(self.relation_query(identity))
            or self._blocker(identity)
        ):
            return DeletionResult(
                "partial",
                "La comprobación final detectó datos pendientes. No se anuncia una eliminación completa.",
            )
        self.operations.update_one({"_id": operation_id}, {"$set": {"delete_completed": True}})
        return DeletionResult(
            "deleted",
            "Concepto eliminado. Sus relaciones se retiraron; fuentes, notas, documentos y archivos compartidos se conservaron.",
        )

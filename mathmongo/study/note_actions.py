"""Explicit, retryable whole-note operations over the canonical notebook services."""

from importlib import import_module

from pymongo.errors import DuplicateKeyError
from pymongo.errors import PyMongoError

from editor.notebook_lifecycle import delete_note_record
from editor.utils.media_assets import detach_media_assets_from_note_record
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.concurrency import digest
from mathmongo.study.library_management import rejected


class NoteActions:
    """One scoped activity; no resource bytes, derived concepts or references are deleted."""

    def __init__(self, notes, family):
        """Use the activity's existing facade and its already scoped database."""
        self.notes = notes
        self.family = family
        self.db = notes.db
        self.mongo = notes.mongo

    def execute(self, identity, action, request_id, revision, title=""):
        """A network failure retains the same operation; failures never announce success."""
        fingerprint = digest(
            {
                "family": self.family,
                "identity": identity,
                "action": action,
                "revision": revision,
                "title": title,
            }
        )
        try:
            if action == "duplicate":
                return self.duplicate(identity, request_id, revision, title, fingerprint)
            return self.delete(identity, request_id, revision, fingerprint)
        except AdvancedReaderError:
            raise
        except (PyMongoError, RuntimeError):
            raise AdvancedReaderError(
                "note_action_incomplete",
                "No se pudo confirmar la operación. Conservamos la solicitud; reintenta el mismo envío para comprobarla y terminar las asociaciones pendientes.",
                status_code=503,
            ) from None
        except ValueError:
            raise rejected(
                "La nota cambió o la operación no se confirmó. Conserva tu borrador y consulta su versión guardada antes de volver a confirmar."
            ) from None

    def duplicate(self, identity, request_id, revision, title, fingerprint):
        """Use the format's native copy service with one raw, revision-bound snapshot."""
        if self.family == "diary":
            raise rejected("Esta actividad no ofrece duplicación de nota completa.")
        target = self.family + "_copy_" + str(request_id)
        copied = self.mongo.get_notebook_note_by_id(target)
        if copied is None:
            original = self.notes.opened(identity)
            if digest(original) != revision:
                raise rejected()
            service = import_module("editor." + self.family + ".service")
            operation = getattr(service, "duplicate_" + self.family + "_note")
            result = operation(
                self.mongo,
                identity,
                {"title": title},
                expected_snapshot=original,
                target_id=target,
                creation_fingerprint=fingerprint,
            )
            if result is None or not result.acknowledged:
                raise RuntimeError("Copy not acknowledged")
            copied = self.mongo.get_notebook_note_by_id(target)
        if (
            copied is None
            or copied.get("study_copy_fingerprint") != fingerprint
            or copied.get("study_copy_source") != identity
        ):
            raise rejected("El intento ya pertenece a otra copia. No se sobrescribió ninguna nota.")
        self.notes.parse(copied[self.family])
        self.notes._synchronize_media(copied)
        return self.notes.describe(copied)

    def _prepare_delete(self, identity, request_id, revision, fingerprint):
        """Persist the observed snapshot before the destructive compare-and-delete."""
        operations = self.db["study_note_operations"]
        key = self.family + ":delete:" + str(request_id)
        receipt = operations.find_one({"_id": key})
        if receipt is None:
            original = self.notes.opened(identity)
            if digest(original) != revision:
                raise rejected()
            prepared = {
                "_id": key,
                "fingerprint": fingerprint,
                "identity": original["_id"],
                "snapshot": original,
                "completed": False,
            }
            try:
                operations.insert_one(prepared)
            except DuplicateKeyError:
                pass
            receipt = operations.find_one({"_id": key})
        if (
            receipt is None
            or receipt.get("fingerprint") != fingerprint
            or receipt.get("conflicted")
        ):
            raise rejected(
                "La solicitud pertenece a otra operación o revisión. No se modificó la nota."
            )
        return receipt

    def _finish_delete(self, identity, receipt):
        """Resume native deletion and asset cleanup, preserving other BSON identities."""
        operations = self.db["study_note_operations"]
        original = receipt["snapshot"]
        try:
            if self.family == "diary":
                delete_note_record(self.mongo, original)
            else:
                operation = getattr(self.notes.spec.services, "delete_" + self.family + "_note")
                operation(self.mongo, identity, expected_snapshot=original)
        except ValueError:
            # A rejected CAS is terminal for this revision. Do not retain its body.
            operations.update_one(
                {"_id": receipt["_id"]}, {"$set": {"conflicted": True}, "$unset": {"snapshot": ""}}
            )
            raise
        if self.mongo.get_notebook_note_by_id(identity) is None:
            detach_media_assets_from_note_record(self.mongo, note_id=identity)
        result = operations.update_one(
            {"_id": receipt["_id"], "fingerprint": receipt["fingerprint"]},
            {"$set": {"completed": True}, "$unset": {"snapshot": ""}},
        )
        if not result.acknowledged or result.matched_count != 1:
            raise RuntimeError("Cleanup receipt not acknowledged")

    def delete(self, identity, request_id, revision, fingerprint):
        """Journal before CAS; after partial failure resume only this note's cleanup."""
        receipt = self._prepare_delete(identity, request_id, revision, fingerprint)
        if not receipt["completed"]:
            self._finish_delete(identity, receipt)
        if self.db.latex_notes.find_one({"_id": receipt["identity"]}) is not None:
            raise rejected(
                "Existe una nota actual con esa identidad. No se eliminó esa versión ni sus recursos."
            )
        confirmed = self.db.study_note_operations.find_one({"_id": receipt["_id"]})
        if not confirmed or not confirmed.get("completed"):
            raise RuntimeError("Deletion not confirmed")
        return {"status": "deleted", "note_id": identity, "family": self.family}

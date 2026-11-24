"""User activities over canonical catalog services, with explicit optimistic revisions."""

from __future__ import annotations

from pydantic import ValidationError

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import reference_revision
from mathmongo.source_catalog.repository import source_revision
from mathmongo.source_catalog.service import SourceCatalogService
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.repository import document_revision


def rejected(
    message="La ficha cambió o no se pudo guardar. El borrador se conserva; consulta la versión actual antes de reintentar.",
):
    """Keep internal Mongo/provider errors out of the public activity."""
    return AdvancedReaderError("catalog_conflict", message, status_code=409)


def record_response(record, revision):
    """Details are fetched only when opening the corresponding editor."""
    return {**record.model_dump(mode="json"), "revision": revision(record)}


def changed_model(model, current, changes):
    """Validate the proposed metadata without exposing internal exception payloads."""
    try:
        return model.model_validate({**current.model_dump(mode="python"), **changes})
    except ValidationError:
        raise AdvancedReaderError(
            "invalid_catalog_fields",
            "Revisa el nombre, los campos bibliográficos y sus tipos antes de guardar. El borrador se conserva.",
            status_code=422,
        ) from None


class LibraryManagement:
    """No connections, automatic preparation, file purges or replacement domain models."""

    def __init__(self, app, documents):
        """Bind existing catalog and document services to the same explicit library."""
        self.app = app
        self.catalog = SourceCatalogService(app.db)
        self.documents = documents

    def source(self, identity):
        """Fetch source metadata and its revision without preparing storage."""
        record = self.catalog.sources.get_by_id(identity)
        if record is None:
            raise rejected("La fuente ya no está disponible. Vuelve a Biblioteca.")
        return record_response(record, source_revision)

    def reference(self, identity, source_id):
        """Fetch only a reference associated with the requested source."""
        record = self.catalog.references.get_by_id(identity)
        if record is None or source_id not in record.source_ids:
            raise rejected("La referencia no está asociada a esta fuente. Actualiza la ficha.")
        return record_response(record, reference_revision)

    def document(self, identity, source_id):
        """Fetch document metadata only within its owning source."""
        record = self.documents.documents.get_by_id(identity)
        if record is None or record.source_id != source_id:
            raise rejected("El documento no pertenece a esta fuente o ya no está disponible.")
        return record_response(record, document_revision)

    def edit_source(self, identity, changes, revision):
        """Apply a minimal source edit and confirm its observed values."""
        current = self.catalog.sources.get_by_id(identity)
        if current is None:
            raise rejected()
        candidate = changed_model(Source, current, changes)
        if source_revision(current) != revision:
            if all(getattr(current, key) == getattr(candidate, key) for key in changes):
                return self.source(identity)
            raise rejected()
        result = self.catalog.update_source(
            identity, changes, preserve_previous_name_as_alias=True, expected_revision=revision
        )
        if not result.persisted:
            raise rejected(
                "La fuente no se guardó. Revisa las coincidencias de nombre en Biblioteca y la versión actual; el borrador se conserva."
            )
        confirmed = self.source(identity)
        if any(confirmed[key] != candidate.model_dump(mode="json")[key] for key in changes):
            raise rejected()
        return confirmed

    def edit_reference(self, identity, source_id, changes, revision):
        """Edit canonical shared bibliography without rewriting citation snapshots."""
        current = self.catalog.references.get_by_id(identity)
        if current is None or source_id not in current.source_ids:
            raise rejected()
        candidate = changed_model(Reference, current, changes)
        if reference_revision(current) != revision:
            if all(getattr(current, key) == getattr(candidate, key) for key in changes):
                return self.reference(identity, source_id)
            raise rejected()
        result = self.catalog.update_reference(identity, changes, expected_revision=revision)
        if not result.persisted:
            raise rejected(
                "La referencia no se guardó. Revisa duplicados y la versión actual. No se sobrescribieron las otras fichas."
            )
        confirmed = self.reference(identity, source_id)
        if any(confirmed[key] != candidate.model_dump(mode="json")[key] for key in changes):
            raise rejected()
        return confirmed

    def edit_document(self, identity, source_id, changes, revision):
        """Edit document metadata while retaining identity, bytes and PDF versions."""
        current = self.documents.documents.get_by_id(identity)
        if current is None or current.source_id != source_id:
            raise rejected()
        if document_revision(current) != revision:
            if all(
                current.model_dump(mode="json").get(key) == value for key, value in changes.items()
            ):
                return self.document(identity, source_id)
            raise rejected()
        candidate = changed_model(SourceDocument, current, changes)
        result = self.documents.update_document_metadata(
            identity, changes, expected_revision=revision
        )
        if not result.completed:
            raise rejected(
                "No se guardaron los datos del documento. Comprueba la referencia y la versión actual; el archivo se conserva."
            )
        confirmed = self.document(identity, source_id)
        if any(confirmed[key] != candidate.model_dump(mode="json")[key] for key in changes):
            raise rejected()
        return confirmed

    def state(self, kind, identity, source_id, status, revision):
        """Archive or reactivate explicitly, then confirm the backend state."""
        if kind == "source":
            current = self.source(identity)
            operation = (
                self.catalog.archive_source
                if status == "archived"
                else self.catalog.reactivate_source
            )
        else:
            current = self.document(identity, source_id)
            operation = (
                self.documents.archive_document
                if status == "archived"
                else self.documents.reactivate_document
            )
        if current["status"] == status:
            return current
        if current["revision"] != revision:
            raise rejected()
        result = operation(identity, expected_revision=revision)
        if not (getattr(result, "persisted", False) or getattr(result, "completed", False)):
            raise rejected()
        confirmed = (
            self.source(identity) if kind == "source" else self.document(identity, source_id)
        )
        if confirmed["status"] != status:
            raise rejected()
        return confirmed

    def detach_reference(self, identity, source_id, revision):
        """Remove one unused association without deleting the shared reference."""
        current = self.catalog.references.get_by_id(identity)
        if current is None:
            raise rejected()
        if source_id not in current.source_ids:
            return {"detached": True}
        if reference_revision(current) != revision:
            raise rejected()
        # Removing this association must not invalidate existing citations.
        for collection in ("source_documents", "reading_notes", "document_annotations", "concepts"):
            if self.app.db[collection].find_one({"source_id": source_id, "reference_id": identity}):
                raise rejected(
                    "Esta referencia se utiliza en documentos, notas o conceptos de la fuente. Conserva el vínculo o cambia primero esas citas."
                )
        result = self.catalog.disassociate_reference(identity, source_id)
        if not result.persisted or source_id in result.value.source_ids:
            raise rejected()
        return {"detached": True}

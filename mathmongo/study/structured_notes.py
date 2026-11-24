"""Scoped Cornell/CPI activities using the established document models and services."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module

from pymongo.errors import DuplicateKeyError

from editor.diary_note_latex import _reference_text
from editor.diary_note_models import note_reference_from_catalog
from editor.note_export import build_note_latex_bundle
from editor.structured_note_persistence import StructuredSourceConflictError
from editor.utils.media_assets import synchronize_note_media_references
from mathdatabase.mathmongo import MathMongo
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.concurrency import digest
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.study.library_management import rejected

METADATA_FIELDS = ("title", "date", "project", "context", "tags")


@dataclass(frozen=True)
class StructuredFormat:
    """Explicit presentation/model configuration, never inferred MongoDB forms."""

    family: str
    format_id: str
    document_type: type
    services: object
    regions: tuple[tuple[str, str], ...]
    template_ids: tuple[str, ...]


def structured_format(family):
    """Resolve only the two real canonical families."""
    if family not in {"cornell", "cpi"}:
        raise AdvancedReaderError(
            "structured_format", "Elige Cornell o CPI desde Cuaderno.", status_code=404
        )
    models = import_module("editor." + family + ".models")
    if family == "cornell":
        document_type, format_id = models.CornellDocument, models.CORNELL_NOTE_FORMAT
        regions = (("cue", "Ideas y preguntas"), ("main", "Desarrollo"), ("summary", "Síntesis"))
    else:
        document_type, format_id = models.CpiDocument, models.CPI_NOTE_FORMAT
        regions = (
            ("comprehension", "Comprensión"),
            ("production", "Producción"),
            ("integration", "Integración"),
        )
    return StructuredFormat(
        family,
        format_id,
        document_type,
        import_module("editor." + family + ".service"),
        regions,
        models.template_ids(),
    )


class StructuredNotes:
    """No connection, implicit preparation, byte deletion or alternative persistence model."""

    def __init__(self, database, family):
        """Bind the same library used by the shared HTTP guard."""
        self.db = database
        self.mongo = MathMongo.from_database(database)
        self.spec = structured_format(family)

    def parse(self, raw):
        """Validate real document shapes and bounded page counts without modifying input."""
        try:
            document = self.spec.document_type.from_dict(raw)
            if document.schema_version != 1 or not 1 <= len(document.pages) <= 30:
                raise ValueError("Unsupported version or page count")
            return document
        except (ValueError, TypeError, KeyError):
            raise AdvancedReaderError(
                "invalid_structured_document",
                "Revisa las páginas, sus regiones y la versión del documento. Se conserva el borrador.",
                status_code=422,
            ) from None

    def listing(self, q="", page=1):
        """Paged metadata excludes all region bodies and source LaTeX."""
        query = {"note_format": self.spec.format_id}
        if q:
            query["$or"] = [
                {key: {"$regex": re.escape(q), "$options": "i"}}
                for key in ("title", "latex_body", "project")
            ]
        records = self.mongo.get_notebook_notes(
            query, 20, projection={key: 1 for key in METADATA_FIELDS}, skip=(page - 1) * 20
        )
        return {
            "items": [
                {"note_id": str(row["_id"]), **{key: row.get(key) for key in METADATA_FIELDS}}
                for row in records
            ],
            "page": page,
            "total": self.db.latex_notes.count_documents(query),
        }

    def opened(self, identity):
        """Read one snapshot and enforce family before any state-changing operation."""
        note = self.mongo.get_notebook_note_by_id(identity)
        if note is None:
            raise AdvancedReaderError(
                "structured_missing",
                "La nota no está disponible. Vuelve a Cuaderno; el borrador se conserva.",
                status_code=404,
            )
        if note.get("note_format") != self.spec.format_id:
            raise rejected(
                "Esta nota pertenece a otro formato. Ábrela desde su actividad; no se convirtió ni sobrescribió."
            )
        self.parse(note.get(self.spec.family))
        return note

    def describe(self, note):
        """Keep raw source and raw extended fields distinct from their visual projection."""
        return {
            "note_id": str(note["_id"]),
            "revision": digest(note),
            "family": self.spec.family,
            "metadata": {key: deepcopy(note[key]) for key in METADATA_FIELDS if key in note},
            "document": deepcopy(note[self.spec.family]),
            "latex_body": note.get("latex_body", ""),
            "regions": [{"key": key, "label": label} for key, label in self.spec.regions],
            "template_ids": list(self.spec.template_ids),
        }

    def detail(self, identity):
        """Opening remains read-only and does not regenerate a historical source."""
        return self.describe(self.opened(identity))

    def _synchronize_media(self, note):
        """Reconcile only this note's registry references; retryable and never purges bytes."""
        previous = self.db.media_assets.distinct("asset_id", {"note_ids": str(note["_id"])})
        synchronize_note_media_references(
            self.mongo,
            note_id=str(note["_id"]),
            previous_asset_ids=previous,
            current_asset_ids=note.get("image_ids", []),
        )

    def create(self, operation_id, metadata, raw):
        """The unique note identity makes concurrent/lost-response creation idempotent."""
        document = self.parse(raw)
        fingerprint = digest({"metadata": metadata, "document": document.to_dict()})
        identity = self.spec.family + "_" + str(operation_id)
        note = self.mongo.get_notebook_note_by_id(identity)
        if note is None:
            create = getattr(self.spec.services, "create_" + self.spec.family + "_note")
            try:
                create(
                    self.mongo,
                    metadata,
                    document,
                    note_id=identity,
                    creation_fingerprint=fingerprint,
                )
            except DuplicateKeyError:
                pass
            note = self.opened(identity)
        if note.get("study_create_fingerprint") != fingerprint:
            raise rejected(
                "El intento ya pertenece a otra nota. No se reemplazó; conserva el borrador y abre la nota existente."
            )
        if self.parse(note[self.spec.family]).to_dict() != document.to_dict() or any(
            note.get(k) != v for k, v in metadata.items()
        ):
            raise rejected(
                "La nota cambió después de crearla. Abre su versión guardada; el borrador se conserva."
            )
        self._synchronize_media(note)
        return self.describe(note)

    def update(self, identity, revision, metadata, raw, origins=None):
        """One observed snapshot feeds the canonical service's atomic update."""
        original = self.opened(identity)
        document = self.parse(raw)
        current = self.parse(original[self.spec.family])
        fingerprint = digest(
            {
                "revision": revision,
                "metadata": metadata,
                "document": document.to_dict(),
                "origins": origins,
            }
        )
        if digest(original) != revision:
            if current.to_dict() != document.to_dict() or any(
                original.get(k) != v for k, v in metadata.items()
            ):
                raise rejected(
                    "Otra ventana cambió la nota. Conserva tus regiones y consulta la versión guardada antes de reintentar."
                )
            if origins is not None and original.get("study_update_fingerprint") != fingerprint:
                raise rejected(
                    "El orden de páginas pertenece a otra revisión. Conserva el borrador y abre la versión guardada."
                )
        else:
            operation = getattr(self.spec.services, "update_" + self.spec.family + "_note")
            try:
                result = operation(
                    self.mongo,
                    identity,
                    metadata,
                    document,
                    expected_snapshot=original,
                    page_origins=origins,
                    operation_fingerprint=fingerprint,
                )
            except StructuredSourceConflictError as error:
                raise rejected(str(error)) from None
            except ValueError:
                raise rejected(
                    "Revisa el origen de las páginas. No se movieron datos de otra página o nota."
                ) from None
            if result is None or not result.acknowledged or result.matched_count != 1:
                raise rejected()
        confirmed = self.opened(identity)
        if self.parse(confirmed[self.spec.family]).to_dict() != document.to_dict() or any(
            confirmed.get(k) != v for k, v in metadata.items()
        ):
            raise rejected()
        self._synchronize_media(confirmed)
        return self.describe(confirmed)

    def project(self, identity):
        """Reuse canonical templates, assets, metadata and document serialization."""
        return build_note_latex_bundle(self.opened(identity), db=self.db)

    def reference(self, identity):
        """Offer an editable canonical citation, not invented bibliographic metadata."""
        record = ReferenceRepository(self.db).get_by_id(identity)
        if record is None:
            raise rejected("La referencia ya no está disponible. Vuelve a buscarla en Biblioteca.")
        snapshot = note_reference_from_catalog(record)
        return {"reference": snapshot.model_dump(mode="json"), "latex": _reference_text(snapshot)}

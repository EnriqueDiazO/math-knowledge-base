"""Free-form Diario activities over existing latex_notes CRUD and settings contracts."""

from __future__ import annotations

import re
from datetime import datetime

from pymongo.errors import DuplicateKeyError

from editor.diary_note_models import default_diary_note_settings
from editor.diary_note_models import note_reference_from_catalog
from editor.diary_note_models import settings_document_fields
from editor.diary_note_models import settings_from_note
from editor.diary_note_persistence import persist_diary_note_update
from editor.note_export import LEGACY_NOTE_FORMATS
from editor.note_export import build_note_latex_bundle
from editor.note_export import normalized_note_format
from mathdatabase.mathmongo import MathMongo
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.concurrency import digest
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.study.document_export import compose_project
from mathmongo.study.library_management import rejected

SUMMARY_FIELDS = {
    field: 1 for field in ("title", "date", "project", "context", "tags", "note_format")
}
EDIT_FIELDS = {"title", "date", "project", "context", "tags", "latex_body"}


class Notebook:
    """One scoped database; opening and listing never prepare or normalize records."""

    def __init__(self, database):
        """Reuse the canonical Mongo facade without running its initializing constructor."""
        self.mongo = MathMongo.from_database(database)
        self.db = database
        self.references = ReferenceRepository(database)

    def summaries(self, *, q="", project="", source_id="", page=1):
        """Search title/body but return only bounded navigation metadata."""
        query = {"note_format": {"$in": list(LEGACY_NOTE_FORMATS)}}
        if q:
            query["$or"] = [
                {field: {"$regex": re.escape(q), "$options": "i"}}
                for field in ("title", "latex_body")
            ]
        if project:
            query["project"] = project
        if source_id:
            identities = self.db.references.distinct("reference_id", {"source_ids": source_id})
            query["references.catalog_reference_id"] = {"$in": identities}
        items = self.mongo.get_notebook_notes(
            query, 20, projection=SUMMARY_FIELDS, skip=(page - 1) * 20
        )
        return {
            "items": [
                {"note_id": str(item["_id"]), **{key: item.get(key) for key in SUMMARY_FIELDS}}
                for item in items
            ],
            "page": page,
            "total": self.db.latex_notes.count_documents(query),
        }

    def opened(self, identity):
        """Fetch exactly one historical identity and refuse a different structured format."""
        note = self.mongo.get_notebook_note_by_id(identity)
        if note is None:
            raise AdvancedReaderError(
                "notebook_missing",
                "La entrada ya no está disponible. Vuelve a Cuaderno; el borrador local se conserva.",
                status_code=404,
            )
        try:
            supported = normalized_note_format(note) == "freeform"
        except ValueError:
            supported = False
        if not supported:
            raise rejected(
                "Esta entrada utiliza Cornell, CPI u otro formato estructurado. Se conserva íntegra y requiere su editor específico; no se convirtió en Diario."
            )
        return note

    def detail(self, identity):
        """Expose the canonical source only on explicit opening, retaining raw storage."""
        return self.describe(self.opened(identity))

    @staticmethod
    def describe(note):
        """The revision covers all observed BSON, including unknown historical metadata."""
        return {
            "note_id": str(note["_id"]),
            "revision": digest(note),
            **{key: note.get(key, [] if key == "tags" else "") for key in EDIT_FIELDS},
            "references": settings_from_note(note).model_dump(mode="json")["references"],
            "image_count": len(note.get("image_ids") or []),
        }

    def selected_references(self, identities, existing=()):
        """Keep note-local identities, manual references and unchanged catalog snapshots."""
        prior = {item.catalog_reference_id: item for item in existing if item.catalog_reference_id}
        selected = [item for item in existing if not item.catalog_reference_id]
        for identity in dict.fromkeys(identities):
            if identity in prior:
                selected.append(prior[identity])
                continue
            record = self.references.get_by_id(identity)
            if record is None or record.status.value != "active":
                raise rejected(
                    "Una referencia seleccionada no está disponible. Revisa la asociación; el borrador se conserva."
                )
            selected.append(note_reference_from_catalog(record, position=len(selected)))
        return selected

    def create(self, identity, fields, reference_ids):
        """Persist one stable creation attempt; lost replies do not duplicate or overwrite."""
        fingerprint = digest({"fields": fields, "reference_ids": reference_ids})
        note_id = "diary_" + str(identity)
        existing = self.mongo.get_notebook_note_by_id(note_id)
        if existing is None:
            settings = default_diary_note_settings(new_note=True)
            settings.references = self.selected_references(reference_ids)
            note = {
                "_id": note_id,
                **fields,
                **settings_document_fields(settings),
                "study_create_fingerprint": fingerprint,
            }
            try:
                self.mongo.create_notebook_note(note)
            except DuplicateKeyError:
                pass  # A concurrent replay can only win this same unique identity.
            existing = self.opened(note_id)
        if existing.get("study_create_fingerprint") != fingerprint:
            raise rejected(
                "El identificador ya corresponde a otra entrada. No se reemplazó su contenido; recupera el borrador y revisa el intento."
            )
        return self.describe(existing)

    def update(self, identity, revision, changes):
        """One read supplies revision, original LaTeX and exact atomic update predicate."""
        original = self.opened(identity)
        fields = {
            key: value
            for key, value in changes.items()
            if key in EDIT_FIELDS and original.get(key) != value
        }
        settings = settings_from_note(original)
        settings_changed = False
        if "catalog_reference_ids" in changes:
            before_references = settings.model_dump(mode="json")["references"]
            settings.references = self.selected_references(
                changes["catalog_reference_ids"], settings.references
            )
            settings_changed = settings.model_dump(mode="json")["references"] != before_references
        if not fields and not settings_changed:
            return self.describe(original)  # Includes a safe replay; no lazy default write.
        if digest(original) != revision:
            raise rejected(
                "Otra ventana cambió la entrada. Tu borrador se conserva; abre la versión guardada antes de decidir qué cambios repetir."
            )
        result = persist_diary_note_update(
            self.db.latex_notes,
            original,
            ordinary_fields={**fields, "updated_at": datetime.now()},
            settings=settings if settings_changed else None,
            compare_snapshot=True,
        )
        if result is None or not result.acknowledged or result.matched_count != 1:
            raise rejected()
        confirmed = self.opened(identity)
        if any(confirmed.get(key) != value for key, value in fields.items()):
            raise rejected()
        if (
            settings_changed
            and confirmed.get("references") != settings_document_fields(settings)["references"]
        ):
            raise rejected()
        return self.describe(confirmed)

    def project(self, identity):
        """Reuse Diario's portable export and preserve an authored complete preamble."""
        note = self.opened(identity)
        body = str(note.get("latex_body") or "")
        leading = body.lstrip()
        while leading.startswith("%"):
            leading = leading.partition("\n")[2].lstrip()
        if leading.startswith((r"\documentclass{", r"\documentclass[")):
            return compose_project([{"contenido_latex": body}], note.get("title") or "Diario")
        return build_note_latex_bundle(note, db=self.db)

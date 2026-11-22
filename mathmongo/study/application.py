"""Read models for user activities, with full content resolved only on demand."""

from __future__ import annotations

import re
from types import SimpleNamespace
from uuid import uuid4

from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.knowledge_map.service import KnowledgeMapService
from mathmongo.knowledge_map.service import digest
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_space.preparation import ReadingPreparation
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository


class StudyApplication:
    """One immutable configured library, never chosen from a client database name."""

    def __init__(self, database):
        """Bind the configured library without creating resources or indexes."""
        self.db = database
        self.maps = KnowledgeMapService(
            SimpleNamespace(
                db=database,
                concepts=database.concepts,
                latex_documents=database.latex_documents,
                relations=database.relations,
            )
        )
        self.preparation = ReadingPreparation(database)
        self.sources = SourceRepository(database)
        self.references = ReferenceRepository(database)
        endpoint = sorted(str(node) for node in database.client.nodes)
        self.library_id = digest([endpoint, database.name])[:32]
        self.runtime_id = uuid4().hex

    def context(self):
        """Describe capabilities, not collection/index tables; inspection is read-only."""
        state = self.preparation.inspect()
        return {
            "library_id": self.library_id,
            "runtime_id": self.runtime_id,
            "name": self.db.name,
            "preparation": {
                "state": state.state.value,
                "reason": state.reason,
                "version": state.version,
                "notes_ready": state.capability_ready("notes"),
                "reading_ready": state.capability_ready("reading"),
            },
        }

    def library(self, query="", page=1):
        """Search bibliography on the server before paging; never truncate matches first."""
        pipeline = [
            {"$match": {"status": "active"}},
            {
                "$lookup": {
                    "from": "references",
                    "localField": "source_id",
                    "foreignField": "source_ids",
                    "as": "bibliography",
                }
            },
        ]
        if query.strip():
            pattern = {"$regex": re.escape(query.strip()), "$options": "i"}
            choices = [
                {field: pattern}
                for field in (
                    "name",
                    "aliases.value",
                    "bibliography.title",
                    "bibliography.authors.literal",
                    "bibliography.authors.family",
                    "bibliography.authors.given",
                    "bibliography.doi",
                    "bibliography.isbn",
                )
            ]
            if query.strip().isdigit():
                choices.append({"bibliography.year": int(query.strip())})
            pipeline.append({"$match": {"$or": choices}})
        pipeline.extend(
            [
                {"$sort": {"name": 1, "source_id": 1}},
                {
                    "$project": {
                        "_id": 0,
                        "source_id": 1,
                        "name": 1,
                        "description": 1,
                        "bibliography.title": 1,
                        "bibliography.authors": 1,
                        "bibliography.year": 1,
                        "bibliography.doi": 1,
                        "bibliography.isbn": 1,
                    }
                },
                {
                    "$facet": {
                        "items": [{"$skip": (page - 1) * 20}, {"$limit": 20}],
                        "count": [{"$count": "value"}],
                    }
                },
            ]
        )
        result = next(iter(self.db.sources.aggregate(pipeline, maxTimeMS=5000)))
        return {
            "items": result["items"],
            "total": result["count"][0]["value"] if result["count"] else 0,
            "page": page,
            "page_size": 20,
        }

    def source(self, source_id, documents):
        """Resolve a deep link exactly, independently of the current search page."""
        source = self.sources.get_by_id(source_id)
        if source is None:
            raise AdvancedReaderError(
                "source_not_found", "Esta fuente ya no está disponible.", status_code=404
            )
        items = documents.list(source_id, page_size=100, status="active").items
        references = self.references.list(source_id=source_id, page_size=100).items
        return {
            "source_id": source.source_id,
            "name": source.name,
            "description": source.description,
            "documents": [
                {
                    key: item.model_dump(mode="json")[key]
                    for key in ("document_id", "source_id", "reference_id", "title", "kind")
                }
                for item in items
            ],
            "references": [
                ref.model_dump(mode="json", exclude={"raw", "provenance"}) for ref in references
            ],
        }

    def notes(self, page=1):
        """Navigation summaries exclude note bodies; opening a note loads its content."""
        query = {"status": "active", "user_scope": "local"}
        items = list(
            self.db.reading_notes.find(
                query,
                {
                    "_id": 0,
                    "note_id": 1,
                    "title": 1,
                    "source_id": 1,
                    "document_id": 1,
                    "updated_at": 1,
                },
            )
            .sort("updated_at", -1)
            .skip((page - 1) * 20)
            .limit(20)
        )
        return {"items": items, "total": self.db.reading_notes.count_documents(query), "page": page}

    def note(self, note_id, reading):
        """Return only the requested canonical note and its optimistic revision."""
        result = reading.get_note(note_id)
        if not result.completed or result.value is None:
            raise AdvancedReaderError(
                "note_not_found",
                "La nota no está disponible. Conserva el borrador.",
                status_code=404,
            )
        note = result.value
        return {**note.model_dump(mode="json"), "revision": digest(note.model_dump())}

    def concept(self, key):
        """Use the same content snapshot for body and revision, avoiding a second read."""
        concept = self.maps.find(key)
        if concept is None:
            raise AdvancedReaderError(
                "concept_not_found", "El concepto ya no está disponible.", status_code=404
            )
        latex = self.maps.latex(concept)
        reading = ReadingAnnotationService(self.db)
        evidence = reading.list_concept_evidence(concept["id"], concept["source"], page_size=100)
        passages = []
        for link in evidence.value.items if evidence.completed and evidence.value else ():
            document_id, page, quote, annotation_id = (
                link.document_id,
                link.page_number,
                "",
                link.annotation_id,
            )
            if link.note_id:
                note = reading.get_note(link.note_id)
                if note.completed and note.value:
                    document_id, page = note.value.document_id, note.value.page_start
            if annotation_id:
                mark = reading.get_annotation(annotation_id)
                if mark.completed and mark.value:
                    document_id, page, quote = (
                        mark.value.document_id,
                        mark.value.page_number,
                        mark.value.quote_text or "",
                    )
            if document_id:
                passages.append(
                    {
                        "document_id": document_id,
                        "pdf_page": page,
                        "quote": quote,
                        "annotation_id": annotation_id,
                    }
                )
        return {
            "key": key,
            "id": str(concept["id"]),
            "titulo": concept.get("titulo") or str(concept["id"]),
            "source": concept["source"],
            "source_id": concept.get("source_id", ""),
            "tipo": concept.get("tipo", "nota"),
            "categorias": concept.get("categorias", []),
            "comentario": concept.get("comentario", ""),
            "reference_id": concept.get("reference_id", ""),
            "reference_locator": concept.get("reference_locator"),
            "contenido_latex": (latex or {}).get("contenido_latex", ""),
            "revision": digest([concept, latex]),
            "passages": passages,
        }

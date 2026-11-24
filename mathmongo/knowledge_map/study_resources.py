"""Room presentation and adapters to canonical reading-note/evidence services."""

from __future__ import annotations

from uuid import UUID
from uuid import uuid4

from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.source_documents.repository import SourceDocumentRepository


class StudyResources:
    """Keep the room free of a parallel note, concept or document store."""

    def __init__(self, maps):
        """Reuse the map ledger and selected database; constructors perform no I/O."""
        self.maps = maps
        self.db = maps.db
        self.reading = ReadingAnnotationService(self.db)
        self.documents = SourceDocumentRepository(self.db)

    def snapshot(self) -> dict:
        """Read bounded logical resources; never send blob paths or credentials."""
        from mathmongo.knowledge_map.service import digest

        documents, notes, annotations = [], [], []
        for source in self.maps.sources.list(page=1, page_size=100).items:
            documents.extend(
                {
                    key: item.model_dump(mode="json")[key]
                    for key in ("document_id", "source_id", "reference_id", "title", "kind")
                }
                for item in self.documents.list(
                    source.source_id, page_size=100, status="active"
                ).items
            )
            result = self.reading.list_source_notes(source.source_id, page_size=100)
            if result.completed and result.value:
                notes.extend(
                    {**note.model_dump(mode="json"), "revision": digest(note.model_dump())}
                    for note in result.value.items
                )
            marks = self.reading.list_source_annotations(source.source_id, page_size=100)
            if marks.completed and marks.value:
                annotations.extend(
                    {
                        key: mark.model_dump(mode="json")[key]
                        for key in (
                            "annotation_id",
                            "document_id",
                            "source_id",
                            "reference_id",
                            "page_number",
                            "page_label",
                            "quote_text",
                            "body",
                            "kind",
                        )
                    }
                    for mark in marks.value.items
                )
        rooms = [
            {"uid": item["room_uid"], "revision": digest(item), "state": item["study_room"]}
            for item in self.db["knowledge_graph_maps"].find({"study_room.version": 1}).limit(100)
        ]
        evidence = [
            {
                key: item.get(key)
                for key in (
                    "concept_legacy_id",
                    "concept_legacy_source",
                    "source_id",
                    "document_id",
                    "note_id",
                    "annotation_id",
                    "reference_id",
                    "page_number",
                    "link_type",
                )
            }
            for item in self.db["concept_evidence_links"].find({"status": "active"}).limit(10000)
        ]
        return {
            "documents": documents,
            "notes": notes,
            "annotations": annotations,
            "rooms": rooms,
            "evidence": evidence,
            "resource_limit": "Hasta 100 fuentes y 100 recursos por fuente; listas adicionales en la biblioteca.",
        }

    def save_room(self, intent, record) -> dict:
        """Save only room poses/references using the map's recoverable CAS writer."""
        from mathmongo.knowledge_map.service import MapConflictError

        try:
            UUID(intent.room_uid)
        except ValueError:
            raise MapConflictError("Identidad de habitación no válida.") from None
        room = intent.room_state
        if room is None:
            raise MapConflictError("Falta la habitación.")
        for sphere in room.spheres:
            if not self.db["knowledge_graph_maps"].find_one(
                {"map_uid": sphere.view_uid, "study_view.version": 1}
            ):
                raise MapConflictError(
                    "Una vista referida ya no está disponible; conserva la habitación local."
                )
        if room.document_id and self.documents.get_by_id(room.document_id) is None:
            raise MapConflictError("El documento ya no está disponible.")
        if room.note_id:
            note = self.reading.get_note(room.note_id)
            if not note.completed:
                raise MapConflictError("La nota ya no está disponible.")
        if bool(room.goal_view_uid) != bool(room.goal_id):
            raise MapConflictError('La pregunta necesita una vista y un identificador válidos.')
        if room.goal_id:
            selected = self.db['knowledge_graph_maps'].find_one({'map_uid': room.goal_view_uid, 'study_view.version': 1})
            if selected is None or room.goal_view_uid not in {s.view_uid for s in room.spheres} or not any(g.get('id') == room.goal_id for g in selected['study_view'].get('goals', [])):
                raise MapConflictError('La pregunta ya no está disponible en una esfera de la habitación.')
        return self.maps.save_presentation(
            intent,
            record,
            identifier="room:" + intent.room_uid,
            patch={"room_uid": intent.room_uid, "name": room.name, "study_room": room.model_dump()},
            response={"room_uid": intent.room_uid},
            message="Habitación guardada.",
        )

    def save_note(self, intent, record) -> dict:
        """Save a personal note explicitly; a draft never becomes a concept here."""
        from mathmongo.knowledge_map.service import MapConflictError
        from mathmongo.knowledge_map.service import digest

        note_id = intent.note_id or "note_" + intent.operation_id
        existing = self.reading.get_note(note_id)
        current = existing.value if existing.completed else None
        title, body = intent.titulo.strip(), intent.contenido_latex
        citation = self.maps.citation_patch(intent, current.source_id if current else intent.source_id)
        if not title or not body.strip():
            raise MapConflictError("Nombre y contenido de la nota son obligatorios.")
        if (
            current is not None
            and record.get("note_prepared")
            and current.title == title
            and current.body == body
        ):
            return self.maps.result(
                intent, "saved", "Nota guardada; no se publicó un concepto.", note_id=note_id
            )
        if intent.note_id:
            if current is None or digest(current.model_dump()) != intent.revision:
                raise MapConflictError(
                    "La nota cambió. Conserva el borrador y revisa la versión actual."
                )
            self.maps.operations.update_one(
                {"_id": intent.operation_id}, {"$set": {"note_prepared": True}}
            )
            result = self.reading.update_note(
                note_id,
                title=title,
                body=body,
                note_type=current.note_type,
                document_id=current.document_id,
                reference_id=intent.reference_id or current.reference_id,
                reference_locator=citation.get("reference_locator", current.reference_locator),
                page_start=current.page_start,
                page_end=current.page_end,
                tags=current.tags,
                expected_updated_at=current.updated_at,
            )
        else:
            document = self.documents.get_by_id(intent.document_id) if intent.document_id else None
            source = self.maps.sources.get_by_id(intent.source_id)
            if source is None or source.status.value != 'active':
                raise MapConflictError('Elige una Source activa para la nota.')
            if intent.document_id and (document is None or document.source_id != intent.source_id or document.status.value != 'active'):
                raise MapConflictError("Elige un documento activo de la Source indicada.")
            if current is not None:
                raise MapConflictError("La identidad de nota pertenece a otro registro.")
            tags = []
            page = None
            if intent.annotation_id:
                mark = self.reading.get_annotation(intent.annotation_id)
                if (
                    document is None
                    or not mark.completed
                    or mark.value is None
                    or mark.value.document_id != document.document_id
                    or mark.value.status.value != "active"
                ):
                    raise MapConflictError("La anotación no pertenece al documento activo.")
                tags = ["study-annotation:" + mark.value.annotation_id]
                page = mark.value.page_number
            self.maps.operations.update_one(
                {"_id": intent.operation_id}, {"$set": {"note_prepared": True}}
            )
            result = self.reading.create_note(
                source_id=intent.source_id,
                document_id=document.document_id if document else None,
                reference_id=intent.reference_id or (document.reference_id if document else None),
                reference_locator=citation.get("reference_locator"),
                title=title,
                body=body,
                note_id=note_id,
                tags=tags,
                page_start=page,
            )
        if not result.completed or result.value is None:
            raise MapConflictError(
                "No se confirmó la nota. Conserva el borrador. " + result.message
            )
        return self.maps.result(
            intent, "saved", "Nota guardada; no se publicó un concepto.", note_id=note_id
        )

    def publish_note(self, intent, record) -> dict:
        """Explicitly incorporate a note and retain canonical provenance targets."""
        from mathmongo.knowledge_map.service import MapConflictError
        from mathmongo.knowledge_map.service import digest
        from mathmongo.knowledge_map.service import identity

        result = self.reading.get_note(intent.note_id)
        note = result.value if result.completed else None
        if (
            note is None
            or note.status.value != "active"
            or digest(note.model_dump()) != intent.note_revision
        ):
            raise MapConflictError(
                "La nota de origen cambió o no está disponible; revisa antes de incorporar."
            )
        if intent.source_id != note.source_id:
            raise MapConflictError("La Source debe coincidir con la nota de origen.")
        if not intent.reference_id and note.reference_id:
            intent = intent.model_copy(update={"reference_id": note.reference_id, "reference_locator": note.reference_locator})
        node, duplicate = self.maps._create(intent)
        if duplicate:
            return self.maps.result(
                intent,
                "duplicate",
                "Ya existe un concepto equivalente; se conserva la nota.",
                key=identity(node),
            )
        links = [("ev_" + intent.operation_id, {"note_id": note.note_id})]
        for tag in note.tags:
            if not tag.startswith("study-annotation:"):
                continue
            mark_id = tag.removeprefix("study-annotation:")
            mark = self.reading.get_annotation(mark_id)
            if (
                not mark.completed
                or mark.value is None
                or mark.value.document_id != note.document_id
            ):
                continue
            allocated = record.get("annotation_evidence_id") or "ev_" + str(uuid4())
            self.maps.operations.update_one(
                {"_id": intent.operation_id}, {"$set": {"annotation_evidence_id": allocated}}
            )
            links.append((allocated, {"annotation_id": mark_id}))
            break
        for link_id, target in links:
            evidence = self.reading.create_concept_evidence_link(
                concept_legacy_id=str(node["id"]),
                concept_legacy_source=node["source"],
                source_id=note.source_id,
                reference_id=note.reference_id,
                link_type="related_context",
                evidence_link_id=link_id,
                **target,
            )
            if not evidence.completed:
                return self.maps.result(
                    intent,
                    "partial",
                    "Concepto guardado; procedencia sin confirmar. Reintenta el mismo intento.",
                    key=identity(node),
                )
        return self.maps.result(
            intent,
            "saved",
            "Concepto incorporado; nota y procedencia conservadas.",
            key=identity(node),
        )

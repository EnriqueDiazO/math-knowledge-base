"""Validated map intentions on standalone MongoDB; reads never create resources.

The durable operation ledger is scoped to the selected database. A retry reconciles
its canonical identity before writing. Partial edits keep valid data and never
compensate someone else's work. The map is not a second semantic graph.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Literal
from uuid import NAMESPACE_URL
from uuid import UUID
from uuid import uuid4
from uuid import uuid5

from bson import json_util
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError
from pydantic import field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.errors import PyMongoError

from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.helpers.concept_builders import build_concept_metadata
from editor.helpers.managed_source_selection import load_active_sources
from editor.helpers.managed_source_selection import resolve_active_source
from editor.validators.concept_validator import validate_semantic_duplicate
from mathmongo.knowledge_map.views import StudyRoom
from mathmongo.knowledge_map.views import StudyView
from mathmongo.source_catalog.citations import CitationLocator
from mathmongo.source_catalog.citations import legacy_citation
from mathmongo.source_catalog.models import validate_reference_id
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from schemas.schemas import ConceptoBase
from schemas.schemas import Relation
from schemas.schemas import TipoRelacion

CONCEPT_TYPES = ('definicion', 'teorema', 'proposicion', 'corolario', 'lema', 'ejemplo', 'nota')


class Intent(BaseModel):
    """Bounded allowlist of client intentions; arbitrary database updates are forbidden."""
    model_config = ConfigDict(extra='forbid', strict=True)
    operation_id: str
    action: Literal['create', 'create_connected', 'connect', 'edit', 'save_view', 'save_room', 'save_note', 'publish_note']
    key: str = Field(default='', max_length=1000)
    target: str = Field(default='', max_length=1000)
    source_id: str = Field(default='', max_length=100)
    titulo: str = Field(default='', max_length=500)
    tipo: str = Field(default='nota', max_length=40)
    contenido_latex: str = Field(default='', max_length=100_000)
    comentario: str = Field(default='', max_length=10_000)
    categorias: list[str] = Field(default_factory=list, max_length=100)
    relation_type: TipoRelacion = Field(default=TipoRelacion.requiere_concepto, strict=False)
    reverse: bool = False
    revision: str = Field(default='', max_length=64)
    map_uid: str = Field(default='', max_length=100)
    map_name: str = Field(default='Mi esfera de estudio', min_length=1, max_length=200)
    view_state: StudyView | None = None
    room_uid: str = Field(default='', max_length=100)
    room_state: StudyRoom | None = None
    note_id: str = Field(default='', max_length=100)
    note_revision: str = Field(default='', max_length=64)
    document_id: str = Field(default='', max_length=100)
    annotation_id: str = Field(default='', max_length=100)
    reference_id: str = Field(default='', max_length=100)
    reference_locator: CitationLocator | None = None

    @field_validator('reference_id')
    @classmethod
    def canonical_reference_id(cls, value: str) -> str:
        """Reject malformed link IDs before creating an operation ledger entry."""
        return validate_reference_id(value) if value else value


def identity(doc: dict) -> str:
    """Use the established graph identity without renaming legacy concepts."""
    return f"{doc['id']}@{doc['source']}"


def digest(value) -> str:
    """Hash BSON-aware snapshots, including unknown metadata."""
    return hashlib.sha256(json_util.dumps(value, sort_keys=True).encode()).hexdigest()


def exact_document(doc: dict) -> dict:
    """CAS includes unknown fields, absent fields and the original BSON types."""
    return {'_id': doc['_id'], '$expr': {'$eq': ['$$ROOT', {'$literal': doc}]}}


class MapConflictError(ValueError):
    """A stale edit, unavailable source or invalid semantic intention."""


class KnowledgeMapService:
    """Adapt existing repositories and schemas to recoverable map operations."""
    def __init__(self, mongo):
        """Bind to the explicitly selected application connection without writes."""
        self.mongo = mongo
        self.db = mongo.db
        self.sources = SourceRepository(self.db)
        self.operations = self.db['_knowledge_map_operations']

    def find(self, key: str) -> dict | None:
        """Resolve an exact existing id@source, never a title or fuzzy match."""
        concept_id, separator, source = key.rpartition('@')
        if not separator or not concept_id or not source:
            raise MapConflictError('Identidad no válida.')
        return self.mongo.concepts.find_one({'id': concept_id, 'source': source})

    def latex(self, doc: dict) -> dict | None:
        """Read the authoritative content document for one concept."""
        return self.mongo.latex_documents.find_one({'id': doc['id'], 'source': doc['source']})

    def revision(self, doc: dict) -> str:
        """Bind an edit to both records observed by its author."""
        return digest([doc, self.latex(doc)])

    def graph(self, *, include_study: bool = False) -> dict:
        """Load the same graph for both projections, with two bulk concept reads."""
        nodes = []
        latex_by_key = {identity(d): d for d in self.mongo.latex_documents.find({})
                        if d.get('id') is not None and d.get('source')}
        for doc in self.mongo.concepts.find({}):
            if doc.get('id') is None or not doc.get('source'):
                continue
            latex = latex_by_key.get(identity(doc))
            nodes.append({'key': identity(doc), 'id': str(doc['id']), 'source': doc['source'],
                          'titulo': doc.get('titulo') or str(doc['id']), 'tipo': doc.get('tipo', 'otro'),
                          'comentario': doc.get('comentario') or '', 'categorias': doc.get('categorias') or [],
                          'contenido_latex': (latex or {}).get('contenido_latex', doc.get('contenido_latex', '')),
                          'referencia': {k: str(v) for k, v in (doc.get('referencia') or {}).items() if v is not None},
                          'reference_id': doc.get('reference_id', ''),
                          'reference_locator': doc.get('reference_locator'),
                          'revision': digest([doc, latex])})
        keys = {node['key'] for node in nodes}
        edges = [{'key': str(r['_id']), 'from': r['desde'], 'to': r['hasta'],
                  'tipo': r.get('tipo', ''), 'descripcion': r.get('descripcion', '')}
                 for r in self.mongo.relations.find({})
                 if r.get('desde') in keys and r.get('hasta') in keys]
        sources = [{'id': s.source_id, 'name': s.name} for s in load_active_sources(self.sources)]
        views = [{'uid': str(v['map_uid']), 'name': v.get('name', 'Esfera de estudio'), 'revision': digest(v), 'state': v['study_view']}
                 for v in self.db['knowledge_graph_maps'].find({'study_view.version': 1}).limit(100)]
        result = {'views': views, 'nodes': sorted(nodes, key=lambda n: n['key']), 'edges': edges,
                'sources': sources, 'concept_types': list(CONCEPT_TYPES),
                'relation_types': [t.value for t in TipoRelacion]}
        if include_study:
            from mathmongo.knowledge_map.study_resources import StudyResources
            result.update(StudyResources(self).snapshot())
        return result

    def execute(self, payload: dict) -> dict:
        """Acknowledge only persisted results. Infrastructure errors are uncertain."""
        try:
            intent = Intent.model_validate(payload)
            UUID(intent.operation_id)
            if any(len(s) > 200 for s in intent.categorias):
                raise MapConflictError('Categoría demasiado larga.')
        except (ValueError, ValidationError):
            operation_id = payload.get('operation_id') if isinstance(payload, dict) else None
            if not isinstance(operation_id, str) or len(operation_id) > 100:
                operation_id = None
            return {'operation_id': operation_id, 'status': 'invalid', 'message': 'Datos no válidos; revisa los campos y conserva el borrador.'}
        try:
            return self._execute(intent)
        except PyMongoError:
            return self._failed_write(intent)

    def _failed_write(self, intent: Intent) -> dict:
        if intent.action in ('create', 'create_connected', 'publish_note'):
            try:
                owned = self.mongo.concepts.find_one({'_map_operation': intent.operation_id})
                if owned is not None:
                    return self.result(intent, 'partial', 'Concepto creado; operación sin confirmar por completo. Conserva el borrador y recupera el mismo intento.', key=identity(owned))
            except PyMongoError:
                pass  # A disconnected server cannot confirm which writes committed.
        return {'operation_id': intent.operation_id, 'status': 'uncertain',
                    'message': 'No se confirmó la operación. Conserva el borrador y reconcilia el mismo intento.'}

    def _execute(self, intent: Intent) -> dict:
        operation_id = intent.operation_id
        payload_hash = digest(intent.model_dump(mode='json'))
        now = datetime.now(timezone.utc)
        initial = {'_id': operation_id, 'payload_hash': payload_hash, 'created_at': now}
        try:
            self.operations.update_one({'_id': operation_id}, {'$setOnInsert': initial}, upsert=True)
        except DuplicateKeyError:
            pass  # The other instance inserted this exact operation ID.
        record = self.operations.find_one({'_id': operation_id})
        if record['payload_hash'] != payload_hash:
            return self.result(intent, 'invalid', 'El identificador pertenece a otro borrador. Abre un intento nuevo.')
        if record.get('result'):
            return record['result']
        token = str(uuid4())
        record = self.operations.find_one_and_update(
            {'_id': operation_id, '$or': [{'lease_until': {'$exists': False}}, {'lease_until': {'$lt': now}}]},
            {'$set': {'lease_until': now + timedelta(seconds=30), 'owner': token}},
            return_document=ReturnDocument.AFTER)
        if record is None:
            return self.result(intent, 'pending', 'Otro envío sigue en curso. Reconcilia este intento en 30 segundos.')
        try:
            result = self._apply(intent, record)
        except MapConflictError as exc:
            result = self.result(intent, 'conflict', str(exc))
        finally:
            # Release only this attempt's lease. A lost acknowledgement is resolved
            # by the next canonical lookup, never by blind re-creation.
            self.operations.update_one({'_id': operation_id, 'owner': token}, {'$unset': {'lease_until': '', 'owner': ''}})
        if result['status'] in ('saved', 'duplicate'):
            self.operations.update_one({'_id': operation_id}, {'$set': {'result': result}})
        return result

    @staticmethod
    def result(intent: Intent, status: str, message: str, **values) -> dict:
        """Return a safe acknowledgement associated with one stable operation."""
        return {'operation_id': intent.operation_id, 'status': status, 'message': message, **values}

    def _apply(self, intent: Intent, record: dict) -> dict:
        if intent.action in ('save_room', 'save_note', 'publish_note'):
            from mathmongo.knowledge_map.study_resources import StudyResources
            resources = StudyResources(self)
            handler = {'save_room': resources.save_room, 'save_note': resources.save_note,
                       'publish_note': resources.publish_note}[intent.action]
            return handler(intent, record)
        if intent.action == 'save_view':
            return self._save_view(intent, record)
        if intent.action == 'edit':
            return self._edit(intent, record)
        if intent.action == 'connect':
            return self._connect(intent, intent.key, intent.target)
        if intent.action == "create_connected" and self.find(intent.key) is None:
            raise MapConflictError("El concepto origen ya no existe.")
        node, duplicate = self._create(intent)
        if duplicate:
            return self.result(intent, 'duplicate', 'El concepto ya existe; sus datos se conservaron. Puedes seleccionarlo y conectarlo.', key=identity(node))
        if intent.action == 'create_connected':
            try:
                return self._connect(intent, intent.key, identity(node))
            except (MapConflictError, PyMongoError):
                return self.result(intent, 'partial', 'Concepto guardado; vínculo sin confirmar. Reintenta el mismo intento para recuperarlo.', key=identity(node))
        return self.result(intent, 'saved', 'Concepto guardado.', key=identity(node))

    def citation_patch(self, intent: Intent, source_id: str) -> dict:
        """Validate a canonical citation before any concept write; old citations stay intact."""
        if not intent.reference_id:
            return {}
        reference = ReferenceRepository(self.db).get_by_id(intent.reference_id)
        if reference is None or reference.status.value == 'archived' or source_id not in reference.source_ids:
            raise MapConflictError('La referencia no pertenece a esta Source activa. Revisa la cita.')
        locator = intent.reference_locator or CitationLocator()
        return {'reference_id': reference.reference_id, 'reference_locator': locator.model_dump(),
                'referencia': legacy_citation(reference, locator)}

    def _create(self, intent: Intent) -> tuple[dict, bool]:
        concept_id = f"{intent.tipo}:{uuid5(NAMESPACE_URL, intent.operation_id)}"
        existing = self.mongo.concepts.find_one({'id': concept_id, '_map_operation': intent.operation_id})
        if existing is not None:
            query = {'id': existing['id'], 'source': existing['source']}
            # Reconcile the original canonical identity even if the managed
            # Source has since been renamed or archived. Do not relocate data.
            self.mongo.latex_documents.update_one(query, {'$setOnInsert': {**query, 'contenido_latex': intent.contenido_latex, '_map_operation': intent.operation_id}}, upsert=True)
            return existing, False
        source = resolve_active_source(self.sources, intent.source_id)
        if source is None or '@' in source.name:
            raise MapConflictError('Elige una Source administrada activa compatible con la identidad id@source.')
        if not intent.titulo.strip() or not intent.contenido_latex.strip() or intent.tipo not in CONCEPT_TYPES:
            raise MapConflictError('Nombre, tipo y contenido son obligatorios.')
        citation = self.citation_patch(intent, source.source_id)
        query = {'id': concept_id, 'source': source.name}
        existing = self.mongo.concepts.find_one(query)
        if existing is not None:
            return existing, True
        if validate_semantic_duplicate(self.mongo, intent.titulo, intent.tipo, source.name):
            duplicate = self.mongo.concepts.find_one({'source': source.name, 'tipo': intent.tipo,
                         'titulo': {'$regex': f'^{re.escape(intent.titulo.strip())}$', '$options': 'i'}})
            if duplicate is None:
                raise MapConflictError('El duplicado cambió durante la comprobación; vuelve a revisar.')
            return duplicate, True
        concept = ConceptoBase(**query, source_id=source.source_id, tipo=intent.tipo,
                               titulo=intent.titulo.strip(), tipo_titulo='canonico', categorias=intent.categorias,
                               contenido_latex=intent.contenido_latex, comentario=intent.comentario)
        metadata = build_concept_metadata(concept)
        metadata.update(citation)
        metadata['_map_operation'] = intent.operation_id
        if self.mongo.latex_documents.find_one(query) is not None:
            raise MapConflictError('Existe contenido sin concepto; se conserva para revisión, sin recrear una eliminación ajena.')
        insert_concept_with_latex_atomic(self.mongo, concept_id, source.name, metadata,
                                        intent.contenido_latex, datetime.now(), operation_id=intent.operation_id)
        return self.mongo.concepts.find_one(query), False

    def _connect(self, intent: Intent, origin: str, target: str) -> dict:
        if intent.reverse:
            origin, target = target, origin
        left, right = self.find(origin), self.find(target)
        if left is None or right is None:
            raise MapConflictError('Uno de los extremos ya no existe; revisa el vínculo.')
        relation = Relation(desde_id=str(left['id']), desde_source=left['source'],
                            hasta_id=str(right['id']), hasta_source=right['source'], tipo=intent.relation_type)
        query = {'desde': origin, 'hasta': target, 'tipo': relation.tipo}
        # The audited unique index matches this identity; keep existing description
        # and all unknown relation metadata instead of replacing them on replay.
        self.mongo.relations.update_one(query, {'$setOnInsert': {**query, 'descripcion': ''}}, upsert=True)
        stored = self.mongo.relations.find_one(query)
        return self.result(intent, 'saved', 'Concepto y vínculo confirmados.', key=target if not intent.reverse else origin,
                           edge={'key': str(stored['_id']), 'from': origin, 'to': target, 'tipo': stored['tipo']})

    def _edit(self, intent: Intent, record: dict) -> dict:
        current = self.find(intent.key)
        if current is None:
            raise MapConflictError('El concepto ya no está disponible.')
        if not intent.titulo.strip() or not intent.contenido_latex.strip():
            raise MapConflictError('El nombre y el contenido son obligatorios.')
        if 'before_meta' not in record:
            if self.revision(current) != intent.revision:
                raise MapConflictError('Conflicto: el concepto cambió. Conserva el borrador y revisa la ficha actual.')
            record = {**record, 'before_meta': current, 'before_latex': self.latex(current)}
            self.operations.update_one({'_id': intent.operation_id}, {'$set': {
                'before_meta': record['before_meta'], 'before_latex': record['before_latex']}})
        citation = self.citation_patch(intent, current.get('source_id', ''))
        patch = {**citation, 'titulo': intent.titulo.strip(), 'comentario': intent.comentario,
                 'categorias': intent.categorias, '_map_edit_operation': intent.operation_id,
                 'ultima_actualizacion': record['created_at']}
        if current.get('_map_edit_operation') == intent.operation_id:
            if any(current.get(k) != v for k, v in patch.items()):
                raise MapConflictError('Conflicto tras una edición parcial; revisa los datos actuales.')
        else:
            result = self.mongo.concepts.update_one(exact_document(record['before_meta']), {'$set': patch})
            if not result.matched_count:
                raise MapConflictError('Conflicto: otro flujo modificó el concepto; el borrador se conserva.')
        return self._edit_content(intent, record, current)

    def _edit_content(self, intent: Intent, record: dict, current: dict) -> dict:
        before = record['before_latex']
        actual = self.latex(current)
        patch = {'contenido_latex': intent.contenido_latex, '_map_edit_operation': intent.operation_id,
                 'ultima_actualizacion': record['created_at']}
        if actual is not None and all(actual.get(k) == v for k, v in patch.items()):
            return self.result(intent, 'saved', 'Edición confirmada.', key=intent.key)
        try:
            if before is None:
                self.mongo.latex_documents.insert_one({'id': current['id'], 'source': current['source'], **patch})
            else:
                updated = self.mongo.latex_documents.update_one(exact_document(before), {'$set': patch})
                if not updated.matched_count:
                    raise MapConflictError('El contenido cambió en otro flujo.')
        except (MapConflictError, PyMongoError):
            return self.result(intent, 'partial', 'Ficha guardada; contenido sin confirmar o en conflicto. Conserva el borrador y reconcilia; no se sobrescriben cambios ajenos.', key=intent.key)
        return self.result(intent, 'saved', 'Edición confirmada.', key=intent.key)

    def _save_view(self, intent: Intent, record: dict) -> dict:
        """Save one presentation snapshot with CAS, retaining unrelated map fields."""
        try:
            UUID(intent.map_uid)
        except ValueError:
            raise MapConflictError('Identidad de vista no válida.') from None
        if intent.view_state is None:
            raise MapConflictError('Falta la disposición de la vista.')
        from visualizations.grafoconocimiento import GrafoConocimiento
        members = intent.view_state.members
        concepts = [doc for doc in self.mongo.concepts.find({}) if members is None or identity(doc) in members]
        keys = {identity(doc) for doc in concepts}
        relations = [doc for doc in self.mongo.relations.find({}) if doc.get('desde') in keys and doc.get('hasta') in keys]
        graph = GrafoConocimiento(concepts, relations)
        graph.construir_grafo()
        return self.save_presentation(
            intent, record, identifier='sphere:' + intent.map_uid,
            patch={'name': intent.map_name.strip(), 'study_view': intent.view_state.model_dump(),
                   'graph_state': graph.to_graph_state(), 'map_uid': intent.map_uid},
            response={'map_uid': intent.map_uid}, message='Disposición guardada.',
        )

    def save_presentation(self, intent: Intent, record: dict, *, identifier: str,
                          patch: dict, response: dict, message: str) -> dict:
        """Share recoverable snapshot CAS for views and rooms, never semantic CRUD."""
        maps = self.db['knowledge_graph_maps']
        query = {'_id': identifier}
        current = maps.find_one(query)
        if current is not None and current.get('_study_operation') == intent.operation_id:
            if digest(current) != record.get('view_expected_hash'):
                raise MapConflictError('La vista cambió después del guardado; conserva tu disposición y revisa la versión actual.')
            return self.result(intent, 'saved', message, **response, view_revision=digest(current))
        if current is not None and digest(current) != intent.revision:
            raise MapConflictError('Conflicto de vista: no se sobrescribió el otro mapa. Conserva la disposición local.')
        if current is None and intent.revision:
            raise MapConflictError('La vista guardada ya no existe; conserva la disposición local.')
        patch = {**patch, 'updated_at': record['created_at'], '_study_operation': intent.operation_id}
        after = {**(current or {**query, 'created_at': record['created_at'], 'filters': {}, 'tags': []}), **patch}
        self.operations.update_one({'_id': intent.operation_id}, {'$set': {'view_expected_hash': digest(after)}})
        if current is None:
            maps.insert_one(after)
        elif not maps.replace_one(exact_document(current), after).matched_count:
            raise MapConflictError('La vista cambió durante el guardado. No se sobrescribió.')
        return self.result(intent, 'saved', message, **response, view_revision=digest(after))

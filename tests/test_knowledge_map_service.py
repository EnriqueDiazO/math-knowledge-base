"""Real standalone persistence, in a process/dbpath owned by this test module."""
import shutil
import socket
import subprocess
import time
from datetime import datetime
from datetime import timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.errors import AutoReconnect
from pymongo.errors import ConnectionFailure

from mathmongo.knowledge_map.service import Intent
from mathmongo.knowledge_map.service import KnowledgeMapService
from mathmongo.source_catalog.models import Source


@pytest.fixture(scope='module')
def owned_client(tmp_path_factory):
    """Start an owned standalone process and reject leaked databases."""
    path = tmp_path_factory.mktemp('knowledge-map-mongod')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    executable = shutil.which('mongod')
    assert executable, 'Mandatory map tests require mongod; no user database fallback'
    process = subprocess.Popen([executable, '--dbpath', str(path), '--port', str(port),
                               '--bind_ip', '127.0.0.1', '--nounixsocket'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = MongoClient(f'mongodb://127.0.0.1:{port}', serverSelectionTimeoutMS=150)
    try:
        for _ in range(100):
            assert process.poll() is None
            try:
                client.admin.command('ping')
                break
            except ConnectionFailure:
                time.sleep(.1)
        assert client.admin.command('serverStatus')['pid'] == process.pid
        yield client
        assert not (set(client.list_database_names()) - {'admin', 'config', 'local'})
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=20)


@pytest.fixture
def service(owned_client):
    """Give every case an isolated indexed database and an active Source."""
    name = 'mathmongo_map_test_' + uuid4().hex
    db = owned_client[name]
    db.concepts.create_index([('id', 1), ('source', 1)], unique=True)
    db.latex_documents.create_index([('id', 1), ('source', 1)], unique=True)
    db.relations.create_index([('desde', 1), ('hasta', 1), ('tipo', 1)], unique=True)
    source = Source(name='Álgebra de prueba')
    db.sources.insert_one(source.model_dump(mode='python'))
    mongo = SimpleNamespace(db=db, concepts=db.concepts, relations=db.relations, latex_documents=db.latex_documents)
    api = KnowledgeMapService(mongo)
    api.test_source_id = source.source_id
    yield api
    owned_client.drop_database(name)


def create(api, **changes):
    """Build a creation intention using the managed Source fixture."""
    return {'operation_id': str(uuid4()), 'action': 'create', 'source_id': api.test_source_id,
            'titulo': 'Grupo $G$', 'tipo': 'definicion', 'contenido_latex': r'$G \times G \to G$', **changes}


def edit(api, key, **changes):
    """Capture the actual revision for an optimistic edit intention."""
    return {'operation_id': str(uuid4()), 'action': 'edit', 'key': key,
            'revision': api.revision(api.find(key)), 'titulo': 'Nombre editado',
            'contenido_latex': r'$\forall x\in G$', **changes}


def test_create_replay_and_reload_use_existing_collections(service):
    """Create replay and reload use existing collections."""
    payload = create(service)
    first = service.execute(payload)
    assert first['status'] == 'saved'
    assert service.execute(payload) == first
    reloaded = KnowledgeMapService(service.mongo)
    doc = reloaded.find(first['key'])
    assert doc['source_id'] == service.test_source_id
    assert reloaded.latex(doc)['contenido_latex'] == payload['contenido_latex']
    graph = reloaded.graph()
    assert len(graph['nodes']) == 1 and graph['edges'] == []
    assert graph['nodes'][0]['key'] == first['key']
    assert graph['sources'][0]['id'] == service.test_source_id


def test_duplicate_preserves_every_field_and_can_be_connected(service):
    """Duplicate preserves every field and can be connected."""
    original = service.execute(create(service))['key']
    service.mongo.concepts.update_one({'id': service.find(original)['id']}, {'$set': {'referencia': {'url': 'https://example.invalid'}, 'image_ids': ['shared'], 'unknown': [1, 2]}})
    before = service.find(original)
    result = service.execute(create(service, titulo='  GRUPO $G$  '))
    assert result['status'] == 'duplicate' and result['key'] == original
    assert service.find(original) == before
    target = service.execute(create(service, titulo='Destino'))['key']
    payload = {'operation_id': str(uuid4()), 'action': 'connect', 'key': original, 'target': target, 'relation_type': 'implica'}
    first = service.execute(payload)
    assert first['status'] == 'saved'
    service.execute({**payload, 'operation_id': str(uuid4())})
    assert service.mongo.relations.count_documents({}) == 1
    assert service.find(original) == before


@pytest.mark.parametrize('reverse', [False, True])
def test_connected_direction_type_and_parallel_self_links(service, reverse):
    """Connected direction type and parallel self links."""
    origin = service.execute(create(service))['key']
    payload = create(service, action='create_connected', key=origin, titulo='Anillo', reverse=reverse, relation_type='deriva_de')
    result = service.execute(payload)
    assert result['status'] == 'saved'
    edge = service.graph()['edges'][0]
    assert (edge['to'] if reverse else edge['from']) == origin
    assert edge['tipo'] == 'deriva_de'
    for relation_type in ['deriva_de', 'implica']:
        self_link = service.execute({'operation_id': str(uuid4()), 'action': 'connect', 'key': origin, 'target': origin, 'relation_type': relation_type})
        assert self_link['status'] == 'saved'
    assert len(service.graph()['edges']) == 3


def test_edit_preserves_identity_extra_metadata_references_and_images(service):
    """Edit preserves identity extra metadata references and images."""
    key = service.execute(create(service))['key']
    doc = service.find(key)
    service.mongo.concepts.update_one({'_id': doc['_id']}, {'$set': {'referencia': {'citation': 'private'}, 'image_ids': ['shared'], 'other': {'raw': '$G$'}}})
    before = service.find(key)
    payload = edit(service, key, categorias=['Álgebra'], comentario='\u003cscript\u003e literal')
    result = service.execute(payload)
    assert result['status'] == 'saved'
    after = service.find(key)
    for name in ['_id', 'id', 'source', 'source_id', 'referencia', 'image_ids', 'other', 'fecha_creacion']:
        assert after[name] == before[name]
    assert after['titulo'] == payload['titulo']
    assert service.latex(after)['contenido_latex'] == payload['contenido_latex']
    assert service.execute(payload) == result


def test_stale_edit_and_atomic_cas_never_overwrite_other_writer(service, monkeypatch):
    """Stale edit and atomic cas never overwrite other writer."""
    key = service.execute(create(service))['key']
    old = edit(service, key)
    service.mongo.concepts.update_one({'id': service.find(key)['id']}, {'$set': {'titulo': 'Otro escritor'}})
    assert service.execute(old)['status'] == 'conflict'
    fresh = edit(service, key)
    real = service.mongo.concepts.update_one
    def race(query, update, **kwargs):
        if '$expr' in query:
            real({'_id': query['_id']}, {'$set': {'new_unknown_field': 42}})
        return real(query, update, **kwargs)
    monkeypatch.setattr(service.mongo.concepts, 'update_one', race)
    assert service.execute(fresh)['status'] == 'conflict'
    assert service.find(key)['titulo'] == 'Otro escritor'
    assert service.find(key)['new_unknown_field'] == 42


def test_partial_connection_retries_owned_concept_without_deleting_it(service, monkeypatch):
    """Partial connection retries owned concept without deleting it."""
    origin = service.execute(create(service))['key']
    payload = create(service, action='create_connected', titulo='Conservado', key=origin)
    original = service._connect
    monkeypatch.setattr(service, '_connect', lambda *a: (_ for _ in ()).throw(AutoReconnect('private mongodb://not-for-browser')))
    partial = service.execute(payload)
    assert partial['status'] == 'partial'
    key = partial['key']
    service.mongo.concepts.update_one({'_id': service.find(key)['_id']}, {'$set': {'other_writer': 'keep'}})
    monkeypatch.setattr(service, '_connect', original)
    result = service.execute(payload)
    assert result['status'] == 'saved'
    assert service.mongo.concepts.count_documents({}) == 2
    assert service.find(key)['other_writer'] == 'keep'
    assert service.mongo.relations.count_documents({}) == 1


def test_partial_edit_recovers_content_without_rolling_back_metadata(service, monkeypatch):
    """Partial edit recovers content without rolling back metadata."""
    key = service.execute(create(service))['key']
    payload = edit(service, key)
    real = service.mongo.latex_documents.update_one
    monkeypatch.setattr(service.mongo.latex_documents, 'update_one', lambda *a, **k: (_ for _ in ()).throw(AutoReconnect('secret')))
    partial = service.execute(payload)
    assert partial['status'] == 'partial' and 'secret' not in str(partial)
    assert service.find(key)['titulo'] == payload['titulo']
    monkeypatch.setattr(service.mongo.latex_documents, 'update_one', real)
    assert service.execute(payload)['status'] == 'saved'
    assert service.latex(service.find(key))['contenido_latex'] == payload['contenido_latex']


def test_partial_edit_conflicting_content_is_not_overwritten(service, monkeypatch):
    """Partial edit conflicting content is not overwritten."""
    key = service.execute(create(service))['key']
    payload = edit(service, key)
    doc = service.find(key)
    service.mongo.latex_documents.update_one({'id': doc['id']}, {'$set': {'contenido_latex': 'Cambio externo'}})
    # Explicitly capture the already-reviewed metadata/content snapshot, then race.
    before_latex = service.latex(doc)
    service.operations.insert_one({'_id': payload['operation_id'], 'payload_hash': __import__('mathmongo.knowledge_map.service', fromlist=['digest']).digest(Intent.model_validate(payload).model_dump(mode='json')), 'before_meta': doc, 'before_latex': before_latex, 'created_at': datetime.now(timezone.utc)})
    service.mongo.latex_documents.update_one({'id': doc['id']}, {'$set': {'contenido_latex': 'Otro cambio'}})
    assert service.execute(payload)['status'] == 'partial'
    assert service.latex(service.find(key))['contenido_latex'] == 'Otro cambio'


@pytest.mark.parametrize('changes', [{'action': 'delete'}, {'unknown': True}, {'tipo': 'invalid'}, {'titulo': ''}, {'contenido_latex': ''}, {'operation_id': 'bad'}, {'source_id': 'missing'}, {'categorias': [2]}, {'relation_type': 'inventada'}])
def test_invalid_intentions_never_write_knowledge(service, changes):
    """Invalid intentions never write knowledge."""
    result = service.execute(create(service, **changes))
    assert result['status'] in ('invalid', 'conflict')
    assert service.mongo.concepts.count_documents({}) == 0
    assert service.mongo.relations.count_documents({}) == 0


def test_read_navigation_does_not_create_ledger_and_missing_endpoint_blocks(service):
    """Read navigation does not create ledger and missing endpoint blocks."""
    assert service.graph()['nodes'] == []
    assert '_knowledge_map_operations' not in service.db.list_collection_names()
    result = service.execute({'operation_id': str(uuid4()), 'action': 'connect', 'key': 'bad', 'target': 'bad'})
    assert result['status'] == 'conflict'


def test_uncertain_response_reconciles_and_id_cannot_change_payload(service, monkeypatch):
    """Uncertain response reconciles and id cannot change payload."""
    payload = create(service)
    original = service.operations.update_one
    def lost_ack(query, update, **kwargs):
        result = original(query, update, **kwargs)
        if 'result' in update.get('$set', {}):
            raise AutoReconnect('secret')
        return result
    monkeypatch.setattr(service.operations, 'update_one', lost_ack)
    assert service.execute(payload)['status'] == 'partial'
    monkeypatch.setattr(service.operations, 'update_one', original)
    assert service.execute(payload)['status'] == 'saved'
    assert service.mongo.concepts.count_documents({}) == 1
    assert service.execute({**payload, 'titulo': 'Changed'})['status'] == 'invalid'


def test_busy_operation_does_not_repeat_write(service):
    """Busy operation does not repeat write."""
    from mathmongo.knowledge_map.service import digest
    payload = create(service)
    service.operations.insert_one({'_id': payload['operation_id'], 'payload_hash': digest(Intent.model_validate(payload).model_dump(mode='json')), 'lease_until': datetime.now(timezone.utc).replace(year=2030)})
    assert service.execute(payload)['status'] == 'pending'
    assert service.mongo.concepts.count_documents({}) == 0


def test_lost_content_insert_ack_recovers_owned_orphan(service, monkeypatch):
    """Lost content insert ack recovers owned orphan."""
    payload = create(service)
    real = service.mongo.latex_documents.insert_one
    def lost_ack(document):
        real(document)
        raise AutoReconnect('lost content insert acknowledgement')
    monkeypatch.setattr(service.mongo.latex_documents, 'insert_one', lost_ack)
    assert service.execute(payload)['status'] == 'partial'
    assert service.mongo.concepts.count_documents({}) == 1
    assert service.mongo.latex_documents.count_documents({}) == 1
    monkeypatch.setattr(service.mongo.latex_documents, 'insert_one', real)
    result = service.execute(payload)
    assert result['status'] == 'saved'
    assert service.latex(service.find(result['key']))['contenido_latex'] == payload['contenido_latex']
    assert service.mongo.concepts.count_documents({}) == 1


def test_unowned_orphan_is_preserved_and_not_adopted(service):
    """Unowned orphan is preserved and not adopted."""
    from uuid import NAMESPACE_URL
    from uuid import uuid5
    payload = create(service)
    concept_id = f"definicion:{uuid5(NAMESPACE_URL, payload['operation_id'])}"
    orphan = {'id': concept_id, 'source': 'Álgebra de prueba', 'contenido_latex': 'Contenido ajeno'}
    service.mongo.latex_documents.insert_one(orphan)
    result = service.execute(payload)
    assert result['status'] == 'conflict'
    assert service.mongo.concepts.count_documents({}) == 0
    assert service.mongo.latex_documents.find_one({'id': concept_id}) == orphan


def test_creation_failure_never_deletes_a_concept_changed_and_referenced_elsewhere(service, monkeypatch):
    """Creation failure never deletes a concept changed and referenced elsewhere."""
    origin = service.execute(create(service, titulo='Origen'))['key']
    payload = create(service, titulo='Progreso válido')
    real = service.mongo.latex_documents.insert_one
    def other_flow_and_failure(document):
        doc = service.mongo.concepts.find_one({'_map_operation': payload['operation_id']})
        service.mongo.concepts.update_one({'_id': doc['_id']}, {'$set': {'other_writer': 'keep'}})
        service.mongo.relations.insert_one({'desde': origin, 'hasta': f"{doc['id']}@{doc['source']}", 'tipo': 'implica'})
        raise AutoReconnect('content failed after another flow linked the concept')
    monkeypatch.setattr(service.mongo.latex_documents, 'insert_one', other_flow_and_failure)
    partial = service.execute(payload)
    assert partial['status'] == 'partial'
    assert service.find(partial['key'])['other_writer'] == 'keep'
    assert service.mongo.relations.count_documents({}) == 1
    # A Source rename must not redirect a retry into a second logical identity.
    service.db.sources.update_one({'source_id': service.test_source_id}, {'$set': {'name': 'Nombre nuevo'}})
    monkeypatch.setattr(service.mongo.latex_documents, 'insert_one', real)
    result = service.execute(payload)
    assert result['status'] == 'saved' and result['key'] == partial['key']
    assert service.mongo.concepts.count_documents({}) == 2
    assert service.find(result['key'])['other_writer'] == 'keep'
    assert service.latex(service.find(result['key']))['contenido_latex'] == payload['contenido_latex']

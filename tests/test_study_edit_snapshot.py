"""Concurrent edits must never adopt a later content revision as their baseline."""

from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import edit
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def test_concurrent_latex_change_between_revision_check_and_baseline_is_not_overwritten(service, monkeypatch):
    """The content captured for comparison is the same snapshot used by CAS."""
    key = service.execute(create(service))['key']
    payload = edit(service, key, contenido_latex='Mi edición pendiente')
    original = service.latex
    reads = []

    def concurrent(document):
        value = original(document)
        reads.append(value)
        if len(reads) == 1:
            service.mongo.latex_documents.update_one({'_id': value['_id']},
                {'$set': {'contenido_latex': 'Cambio concurrente confirmado'}})
        return value

    monkeypatch.setattr(service, 'latex', concurrent)
    result = service.execute(payload)
    assert result['status'] == 'partial'
    assert service.mongo.latex_documents.find_one({'id': service.find(key)['id']})['contenido_latex'] == 'Cambio concurrente confirmado'
    stored = service.operations.find_one({'_id': payload['operation_id']})
    assert stored['before_latex']['contenido_latex'] != 'Cambio concurrente confirmado'
    assert not stored.get('result')

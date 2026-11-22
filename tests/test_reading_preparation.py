"""Preparation on an owned standalone MongoDB; never on the user's library."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from pymongo.errors import AutoReconnect
from pymongo.errors import OperationFailure

from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_space.preparation import PreparationState
from mathmongo.reading_space.preparation import ReadingPreparation
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def _documents(db):
    return {name: list(db[name].find()) for name in db.list_collection_names() if not name.startswith('system.')}


def test_pending_preparation_is_explicit_idempotent_and_does_not_publish_a_note(service):
    """Initial setup installs only approved missing indexes and preserves records."""
    db = service.db
    preparation = ReadingPreparation(db)
    before = _documents(db)
    pending = preparation.inspect()
    assert pending.state == PreparationState.PENDING
    assert _documents(db) == before  # inspection may not create even collections
    prepared = preparation.prepare(pending)
    assert prepared.ready
    assert preparation.inspect().ready
    for collection, records in before.items():
        assert list(db[collection].find()) == records
    assert db.reading_notes.count_documents({}) == 0
    indexes = {name: list(db[name].list_indexes()) for name in db.list_collection_names()}
    assert preparation.prepare(prepared).ready
    assert {name: list(db[name].list_indexes()) for name in db.list_collection_names()} == indexes
    note = ReadingAnnotationService(db).create_note(source_id=service.test_source_id,
        title='Nota guardada después', body='Contenido explícitamente confirmado')
    assert note.completed and db.reading_notes.count_documents({}) == 1


@pytest.mark.parametrize('problem', ['duplicates', 'conflicting_index'])
def test_incompatible_data_or_indexes_are_not_repaired_or_partially_prepared(service, problem):
    """No migration, deletion or unrelated index installation hides a conflict."""
    db = service.db
    if problem == 'duplicates':
        db.reading_notes.insert_many([{'note_id':'duplicate', 'body':'Primero'}, {'note_id':'duplicate', 'body':'Segundo'}])
    else:
        db.reading_notes.create_index([('body',1)],name='reading_notes_id_unique')
    before = _documents(db)
    indexes = {name: list(db[name].list_indexes()) for name in db.list_collection_names()}
    preparation = ReadingPreparation(db)
    status = preparation.inspect()
    assert status.state == PreparationState.INCOMPATIBLE
    assert preparation.prepare(status).state == PreparationState.INCOMPATIBLE
    assert _documents(db) == before
    assert {name: list(db[name].list_indexes()) for name in db.list_collection_names()} == indexes


@pytest.mark.parametrize('code', [13, 18])
def test_inspection_permission_failure_is_unverified_not_missing(service, monkeypatch, code):
    """Denied introspection cannot authorize an index creation plan."""
    preparation = ReadingPreparation(service.db)
    def denied():
        raise OperationFailure('Private driver detail',code=code)
    monkeypatch.setattr(preparation.managers[0][1], 'plan', denied)
    status = preparation.inspect()
    assert status.state == PreparationState.UNVERIFIED and status.reason == 'permission'
    assert not status.ready and not status.plans
    assert preparation.prepare(status).state == PreparationState.UNVERIFIED


def test_failed_preparation_cannot_claim_success_and_can_be_retried(service, monkeypatch):
    """A successful-looking apply return does not replace a backend read-back."""
    preparation = ReadingPreparation(service.db)
    pending = preparation.inspect()
    with monkeypatch.context() as patch:
        for _, manager in preparation.managers:
            patch.setattr(manager, 'apply', lambda: SimpleNamespace(initialized=True))
        after = preparation.prepare(pending)
    assert after.state == PreparationState.UNVERIFIED and after.reason == 'verification'
    assert service.db.reading_notes.count_documents({}) == 0
    assert preparation.prepare(after).ready


def test_partial_setup_permission_failure_preserves_completed_work_and_retry(service, monkeypatch):
    """Only missing work is retried; no compensating drop/delete is performed."""
    preparation = ReadingPreparation(service.db)
    manager = preparation.managers[1][1]
    def denied():
        raise OperationFailure('Cannot create indexes',code=13)
    with monkeypatch.context() as patch:
        patch.setattr(manager,'apply',denied)
        status = preparation.prepare(preparation.inspect())
    assert status.state == PreparationState.UNVERIFIED and status.reason == 'permission'
    assert status.capability_ready('reading') and not status.capability_ready('notes')
    assert preparation.prepare(status).ready


def test_lost_acknowledgement_is_success_only_after_complete_read_back(service, monkeypatch):
    """A transport exception may only be reconciled from verified stored state."""
    preparation = ReadingPreparation(service.db)
    manager = preparation.managers[1][1]
    original = manager.apply
    def lose_ack():
        original()
        raise AutoReconnect('Lost acknowledgement')
    monkeypatch.setattr(manager,'apply',lose_ack)
    assert preparation.prepare(preparation.inspect()).ready
    assert service.db.reading_notes.count_documents({}) == 0


def test_old_database_or_contract_confirmation_is_rejected_without_writes(service):
    """No stored success is transferable between endpoints or contract versions."""
    preparation = ReadingPreparation(service.db)
    pending = preparation.inspect()
    before = _documents(service.db)
    assert preparation.prepare(replace(pending,context='other database')).reason == 'context'
    assert preparation.prepare(replace(pending,version='older contract')).reason == 'context'
    assert _documents(service.db) == before


def test_ready_inspection_never_reapplies_indexes(service, monkeypatch):
    """Opening Reading or Diagnosis remains read-only after setup."""
    preparation = ReadingPreparation(service.db)
    assert preparation.prepare(preparation.inspect()).ready

    def forbidden():
        pytest.fail('Ready state must never perform maintenance')
    for _, manager in preparation.managers:
        monkeypatch.setattr(manager,'apply',forbidden)
    assert preparation.inspect().ready
    assert preparation.prepare(preparation.inspect()).ready


def test_read_only_pdf_preview_remains_available_without_initializing_or_recording_opening(service, tmp_path):
    """A blocked write capability does not prevent verified, non-writing reading."""
    from mathmongo.reading_space.service import ReadingSpaceService
    from mathmongo.source_documents.service import SourceDocumentService
    from mathmongo.source_documents.storage import SourceDocumentBlobStore
    from tests.advanced_reader_test_support import synthetic_text_pdf
    documents = SourceDocumentService(service.db, storage=SourceDocumentBlobStore(tmp_path))
    created = documents.create_pdf_document(source_id=service.test_source_id,
        pdf_bytes=synthetic_text_pdf(padding_bytes=0), original_filename='owned.pdf', title='Lectura aislada')
    assert created.completed and created.value is not None
    reading = ReadingSpaceService(service.db, document_service=documents)
    before = _documents(service.db)
    result = reading.preview_document(created.value.document_id)
    assert result.completed and result.value.pdf_payload.pdf_bytes.startswith(b'%PDF')
    assert result.value.integrity.ok
    assert _documents(service.db) == before
    assert not ReadingPreparation(service.db).inspect().ready
    assert not reading.open_document(created.value.document_id).completed

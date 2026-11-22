"""Real Streamlit preparation UI with a temporary, owned MongoDB library."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


@pytest.mark.parametrize('problem', ['permission', 'incompatible'])
def test_blocked_preparation_explains_the_next_action_without_offering_repair(service, tmp_path, monkeypatch, problem):
    """Neither denied inspection nor a conflicting index authorizes setup."""
    from pymongo.errors import OperationFailure

    from mathmongo.reading_space.indexes import ReadingSpaceIndexManager

    if problem == 'permission':
        def denied(_manager):
            raise OperationFailure('Private driver details', code=13)
        monkeypatch.setattr(ReadingSpaceIndexManager, 'plan', denied)
    else:
        service.db.reading_notes.create_index([('body', 1)], name='reading_notes_id_unique')
    before = {name: list(service.db[name].list_indexes()) for name in service.db.list_collection_names()}
    host, port = service.db.client.address
    script = tmp_path / 'blocked_app.py'
    script.write_text('''import streamlit as st
from pymongo import MongoClient
from types import SimpleNamespace
from editor.source_catalog.shared import build_catalog_context
from editor.reading_space.reader_page import render_reading_space_page
if 'connection' not in st.session_state:
    st.session_state.connection=SimpleNamespace(db=MongoClient(''' + repr(f'mongodb://{host}:{port}') + ''')[''' + repr(service.db.name) + '''])
render_reading_space_page(build_catalog_context('Prueba aislada',st.session_state.connection))
''')
    app = AppTest.from_file(str(script)).run(timeout=20)
    assert not app.exception
    labels = {button.label for button in app.button}
    assert 'Preparar notas y subrayados' not in labels
    assert 'Abrir diagnóstico' in labels
    messages = ' '.join(item.value for item in app.error)
    assert ('permisos' if problem == 'permission' else 'procedimiento de revisión') in messages
    assert 'Private driver details' not in messages
    assert not any('Nota guardada' in item.value for item in app.success)
    assert not app.dataframe
    assert {name: list(service.db[name].list_indexes()) for name in service.db.list_collection_names()} == before


def test_opening_diagnosis_does_not_apply_a_plan(service, tmp_path):
    """Inspection may show technical plans, but needs an explicit confirmation."""
    before = {name: list(service.db[name].find()) for name in service.db.list_collection_names()}
    indexes = {name: list(service.db[name].list_indexes()) for name in service.db.list_collection_names()}
    host, port = service.db.client.address
    script = tmp_path / 'diagnosis_app.py'
    script.write_text('''from pymongo import MongoClient
from types import SimpleNamespace
from editor.source_catalog.shared import build_catalog_context
from editor.reading_space.diagnostics import render_reading_diagnostics
connection=SimpleNamespace(db=MongoClient(''' + repr(f'mongodb://{host}:{port}') + ''')[''' + repr(service.db.name) + '''])
render_reading_diagnostics(build_catalog_context('Prueba aislada', connection))
''')
    app = AppTest.from_file(str(script)).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == 'Diagnóstico de la biblioteca'
    assert {name: list(service.db[name].find()) for name in service.db.list_collection_names()} == before
    assert {name: list(service.db[name].list_indexes()) for name in service.db.list_collection_names()} == indexes


def test_reading_offers_plain_preparation_without_diagnostic_tables(service, tmp_path: Path):
    """The user can prepare the library without interpreting collection names."""
    host, port = service.db.client.address
    script = tmp_path / 'reading_app.py'
    script.write_text('''import streamlit as st
from pymongo import MongoClient
from types import SimpleNamespace
from editor.source_catalog.shared import build_catalog_context
from editor.reading_space.reader_page import render_reading_space_page
if 'connection' not in st.session_state:
    st.session_state.connection=SimpleNamespace(db=MongoClient(''' + repr(f'mongodb://{host}:{port}') + ''')[''' + repr(service.db.name) + '''])
context=build_catalog_context('Prueba aislada',st.session_state.connection)
render_reading_space_page(context)
''')
    app = AppTest.from_file(str(script)).run(timeout=20)
    assert not app.exception
    labels = [button.label for button in app.button]
    assert 'Preparar notas y subrayados' in labels
    assert not app.dataframe
    for message in [*app.warning, *app.error]:
        assert 'Maintenance' not in message.value
        assert 'document_annotations' not in message.value
    next(button for button in app.button if button.label == 'Preparar notas y subrayados').click().run(timeout=20)
    assert not app.exception
    assert any('Función preparada' in item.value for item in app.success)
    assert not any('Nota guardada' in item.value for item in app.success)
    assert service.db.reading_notes.count_documents({}) == 0
    from mathmongo.reading_space.preparation import ReadingPreparation
    assert ReadingPreparation(service.db).inspect().ready


def test_failed_note_save_preserves_the_draft_and_success_requires_a_real_record(service, tmp_path, monkeypatch):
    """Permission-style failure retains text; retry saves once and reports it."""
    import streamlit as st

    from editor.reading_annotations.state import state_key
    from editor.reading_space import reader_page
    from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus
    from mathmongo.reading_annotations.service import ReadingAnnotationService
    from mathmongo.reading_annotations.service import ReadingAnnotationServiceResult
    from mathmongo.reading_space.preparation import ReadingPreparation
    from mathmongo.source_documents.models import SourceDocument
    from mathmongo.source_documents.models import WebDocument
    from mathmongo.source_documents.repository import SourceDocumentRepository
    preparation = ReadingPreparation(service.db)
    assert preparation.prepare(preparation.inspect()).ready
    document = SourceDocument(source_id=service.test_source_id, kind='web',
        title='Documento para una nota', web=WebDocument(url_raw='https://example.invalid/owned'))
    SourceDocumentRepository(service.db).insert(document)

    class FailingWriteService(ReadingAnnotationService):
        def create_note(self, **kwargs):
            if st.session_state.get('fail_save', True):
                return ReadingAnnotationServiceResult(ReadingAnnotationOperationStatus.ERROR,
                    message='Could not persist the Reading Note.')
            return super().create_note(**kwargs)

    monkeypatch.setattr(reader_page, 'ReadingAnnotationService', FailingWriteService)
    host, port = service.db.client.address
    script = tmp_path / 'note_app.py'
    script.write_text('''import streamlit as st
from pymongo import MongoClient
from types import SimpleNamespace
from editor.source_catalog.shared import build_catalog_context
from editor.reading_space.reader_page import render_reading_space_page
from editor.reading_space.state import ACTIVE_USER_SCOPE,SELECTED_DOCUMENT_ID,SELECTED_SOURCE_ID
if 'connection' not in st.session_state:
    st.session_state.connection=SimpleNamespace(db=MongoClient('''+repr(f'mongodb://{host}:{port}')+''')['''+repr(service.db.name)+'''])
    st.session_state[ACTIVE_USER_SCOPE]='local'
    st.session_state[SELECTED_DOCUMENT_ID]='''+repr(document.document_id)+'''
    st.session_state[SELECTED_SOURCE_ID]='''+repr(document.source_id)+'''
render_reading_space_page(build_catalog_context('Prueba aislada',st.session_state.connection))
''')
    app = AppTest.from_file(str(script)).run(timeout=20)
    assert not app.exception
    body_key = state_key('quick_note', 'body', document.document_id)
    submit_key = state_key('quick_note', 'submit', document.document_id)
    next(area for area in app.text_area if area.key == body_key).set_value('Borrador que debe conservarse')
    next(button for button in app.button if button.key == submit_key).click().run(timeout=20)
    assert not app.exception
    assert next(area for area in app.text_area if area.key == body_key).value == 'Borrador que debe conservarse'
    assert any('borrador se conserva' in item.value for item in app.error)
    assert not any('Nota guardada' in item.value for item in app.success)
    assert service.db.reading_notes.count_documents({}) == 0
    app.session_state['fail_save'] = False
    next(button for button in app.button if button.key == submit_key).click().run(timeout=20)
    assert not app.exception
    assert service.db.reading_notes.count_documents({}) == 1
    assert service.db.reading_notes.find_one()['body'] == 'Borrador que debe conservarse'
    assert any('Nota guardada' in item.value for item in app.success)

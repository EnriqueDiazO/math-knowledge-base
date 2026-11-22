"""Room navigation validates canonical resource identity without mutating the database."""
# ruff: noqa: D103
from copy import deepcopy
from uuid import uuid4

from editor.reading_annotations.state import PENDING_PAGE_SUGGESTION
from editor.reading_annotations.state import SELECTED_ANNOTATION_ID
from editor.reading_annotations.state import clear_annotation_state
from editor.reading_space.state import PENDING_TARGET
from editor.reading_space.state import apply_pending_current_page_value
from editor.reading_space.state import state_key
from editor.study_navigation import ROOM_RETURN
from editor.study_navigation import STUDY_ROOM_NAV_LABEL
from editor.study_navigation import add_study_room_navigation
from editor.study_navigation import open_room_source
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.repository import SourceDocumentRepository
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service
from tests.test_study_resources import reading as _reading

owned_client = _owned_client
service = _service
reading = _reading


def test_navigation_preserves_existing_pages_and_is_idempotent():
    pages = ['Inicio', '🗺️ Grafo de conocimiento', 'Exportar']
    expected = ['Inicio', '🗺️ Grafo de conocimiento', STUDY_ROOM_NAV_LABEL, 'Exportar']
    assert add_study_room_navigation(pages) == expected
    assert pages == ['Inicio', '🗺️ Grafo de conocimiento', 'Exportar']
    assert add_study_room_navigation(expected) == expected


def test_source_navigation_uses_canonical_locator_and_does_not_write(reading):
    maps, api, document, mark = reading
    state = {}
    before = {name: list(maps.db[name].find({})) for name in maps.db.list_collection_names()}
    assert open_room_source(state, maps.db, {'document_id': document.document_id, 'annotation_id': mark.annotation_id, 'page_number': 999})
    assert state[PENDING_TARGET]['source_id'] == document.source_id
    assert state[PENDING_TARGET]['document_id'] == document.document_id
    assert state[ROOM_RETURN] is True
    assert state[SELECTED_ANNOTATION_ID] == mark.annotation_id
    assert state.get(PENDING_PAGE_SUGGESTION, {}).get('page_number') != 999
    assert {name: list(maps.db[name].find({})) for name in before} == before
    # A different document's quote may never drive navigation through this ID.
    other = SourceDocument(source_id=document.source_id, kind='web', title='Otra fuente', web=WebDocument(url_raw='https://example.invalid/other'))
    SourceDocumentRepository(maps.db).insert(other)
    unchanged = deepcopy(state)
    assert not open_room_source(state, maps.db, {'document_id': other.document_id, 'annotation_id': mark.annotation_id})
    assert state == unchanged
    assert not open_room_source(state, maps.db, {'document_id': 'doc_' + str(uuid4())})
    assert not open_room_source(state, maps.db, {'document_id': '../etc/passwd'})
    assert not open_room_source(state, maps.db, None)


def test_pdf_locator_survives_first_reader_context_initialization(reading, tmp_path):
    maps, api, document, mark = reading
    from mathmongo.source_documents.service import SourceDocumentService
    from mathmongo.source_documents.storage import SourceDocumentBlobStore
    from tests.advanced_reader_test_support import synthetic_text_pdf
    created = SourceDocumentService(maps.db, storage=SourceDocumentBlobStore(tmp_path)).create_pdf_document(
        source_id=document.source_id, pdf_bytes=synthetic_text_pdf(padding_bytes=0), original_filename='owned.pdf', title='Owned PDF')
    document = created.value
    assert document is not None
    mark = api.create_annotation(document.document_id, kind='highlight', page_number=2, quote_text='Exact page').value
    assert mark is not None
    state = {}
    assert open_room_source(state, maps.db, {'document_id': document.document_id, 'annotation_id': mark.annotation_id})
    clear_annotation_state(state)  # same reset performed by reader initialization
    assert apply_pending_current_page_value(state) == (document.document_id, 2)
    assert state[state_key('current_page', document.document_id)] == 2

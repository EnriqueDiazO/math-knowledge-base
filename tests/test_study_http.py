"""Study HTTP contracts on a PID-verified temporary MongoDB, without Streamlit."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mathmongo.advanced_reader.app import create_app
from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.knowledge_map.service import digest
from mathmongo.source_catalog.models import Reference
from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service
BASE = "/api/study/v1"


@pytest.fixture
def http(service):
    """Use the real app and canonical repositories, never a user database."""
    deps = AdvancedReaderDependencies.from_database(service.db, database_name=service.db.name)
    with TestClient(
        create_app(deps),
        base_url="http://127.0.0.1:8766",
        headers={"Origin": "http://127.0.0.1:8766"},
    ) as client:
        context = client.get(BASE + "/context").json()
        client.headers["X-MathMongo-Library"] = context["library_id"]
        yield client, context


def test_context_and_library_reads_do_not_prepare_storage(service, http):
    """Library browsing remains possible when writing needs compatible preparation."""
    client, context = http
    assert context["preparation"]["state"] == "pending"
    before = set(service.db.list_collection_names())
    sources = client.get(BASE + "/library").json()
    assert sources["items"][0]["name"] == "Álgebra de prueba"
    assert client.get(BASE + "/sources/" + service.test_source_id).json()["documents"] == []
    assert set(service.db.list_collection_names()) == before
    assert "reading_notes" not in before


def test_prepare_then_save_reload_and_publish_note_is_explicit_and_idempotent(service, http):
    """A durable note survives a new HTTP client; publication creates one concept."""
    client, context = http
    prepared = client.post(BASE + "/prepare", json={"version": context["preparation"]["version"]})
    assert prepared.status_code == 200 and prepared.json()["preparation"]["state"] == "ready"
    operation = {
        "operation_id": str(uuid4()),
        "action": "save_note",
        "source_id": service.test_source_id,
        "titulo": "Una idea que se conserva",
        "contenido_latex": r"Una fracción $\frac{1}{2}$ y un argumento.",
    }
    first = client.post(BASE + "/operations", json=operation)
    assert first.status_code == 200 and first.json()["status"] == "saved"
    assert client.post(BASE + "/operations", json=operation).json() == first.json()
    assert service.db.concepts.count_documents({}) == 0
    assert service.db.reading_notes.count_documents({}) == 1
    note_id = first.json()["note_id"]
    note = client.get(BASE + "/notes/" + note_id).json()
    assert note["body"] == operation["contenido_latex"]
    assert "body" not in client.get(BASE + "/notes").json()["items"][0]
    publish = {
        **operation,
        "operation_id": str(uuid4()),
        "action": "publish_note",
        "note_id": note_id,
        "note_revision": note["revision"],
        "tipo": "definicion",
    }
    result = client.post(BASE + "/operations", json=publish).json()
    assert result["status"] == "saved", result
    assert client.post(BASE + "/operations", json=publish).json() == result
    assert service.db.concepts.count_documents({}) == 1
    detail = client.get(BASE + "/concepts/detail", params={"key": result["key"]}).json()
    assert detail["contenido_latex"] == operation["contenido_latex"]
    assert service.db.concept_evidence_links.count_documents({"note_id": note_id}) == 1


def test_wrong_library_or_preparation_version_cannot_write(service, http):
    """A confirmation from a different base/version has no authority here."""
    client, context = http
    before = set(service.db.list_collection_names())
    assert client.post(BASE + "/prepare", json={"version": "older"}).status_code == 409
    assert (
        client.post(
            BASE + "/prepare",
            json={"version": context["preparation"]["version"]},
            headers={"X-MathMongo-Library": "another-library"},
        ).status_code
        == 409
    )
    assert set(service.db.list_collection_names()) == before
    denied = client.get(
        "/api/advanced-reader/health", headers={"X-MathMongo-Library": "old-library"}
    )
    assert denied.status_code == 409 and denied.json()["error"]["code"] == "library_changed"


def test_navigation_never_reads_full_latex_and_detail_uses_the_same_snapshot(
    service, http, monkeypatch
):
    """Large content is loaded once for the selected concept, never for navigation."""
    result = service.execute(create(service, contenido_latex="Contenido grande " * 5000))
    client, _ = http
    collection = type(service.db.latex_documents)
    original_find = collection.find

    def bounded(self, *args, **kwargs):
        if self.name == "latex_documents":
            pytest.fail("Navigation read full LaTeX documents")
        return original_find(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(collection, "find", bounded)
        overview = client.get(BASE + "/overview").json()
    assert overview["nodes"][0]["contenido_latex"] == ""
    detail = client.get(BASE + "/concepts/detail", params={"key": result["key"]}).json()
    doc = service.find(result["key"])
    assert detail["revision"] == digest([doc, service.latex(doc)])
    assert detail["contenido_latex"].startswith("Contenido grande")


def test_bibliographic_search_filters_before_pagination_and_resolves_exact_source(service, http):
    """Author/year/DOI searching can find an item beyond the first source page."""
    from mathmongo.source_catalog.models import Source

    sources = [Source(name=f"Libro {index:03d}") for index in range(30)]
    service.db.sources.insert_many([source.model_dump(mode="python") for source in sources])
    ref = Reference(
        source_ids=[sources[-1].source_id],
        title="Artículo hallado",
        authors=[{"family": "Noether"}],
        year=1930,
        doi="10.1234/owned",
    )
    service.db.references.insert_one(ref.model_dump(mode="python"))
    client, _ = http
    for query in ("Noether", "1930", "10.1234/owned"):
        result = client.get(BASE + "/library", params={"q": query}).json()
        assert result["total"] == 1 and result["items"][0]["source_id"] == sources[-1].source_id
    exact = client.get(BASE + "/sources/" + sources[-1].source_id).json()
    assert exact["references"][0]["title"] == "Artículo hallado"


def test_study_writes_validate_origin_size_and_fields_before_mutating(service, http):
    """The new activity API inherits real origin, payload and domain boundaries."""
    client, _ = http
    operation = {'operation_id': str(uuid4()), 'action': 'save_note',
        'source_id': service.test_source_id, 'titulo': 'No debe escribirse', 'contenido_latex': 'Texto'}
    assert client.post(BASE+'/operations', json=operation, headers={'Origin':'http://example.invalid'}).status_code == 403
    assert client.post(BASE+'/operations', content=b'x'*(1024*1024+1), headers={'Content-Type':'application/json'}).status_code == 413
    invalid = client.post(BASE+'/operations', json={**operation, 'collection':'private'})
    assert invalid.status_code == 422 and invalid.json()['error']['code'] == 'invalid_study_request'
    assert 'borrador se conserva' in invalid.json()['error']['message']
    assert service.db.reading_notes.count_documents({}) == 0
    assert service.operations.count_documents({}) == 0

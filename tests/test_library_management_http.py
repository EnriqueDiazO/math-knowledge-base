"""Real library activities with PID-owned MongoDB and private temporary PDF storage."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mathmongo.advanced_reader.app import create_app
from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.service import SourceCatalogService
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from tests.advanced_reader_test_support import synthetic_text_pdf
from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service
BASE = "/api/study/v1"


@pytest.fixture
def http(service, tmp_path):
    """Every physical PDF and cache is under this fixture, never a user library."""
    dependencies = AdvancedReaderDependencies.from_database(
        service.db, database_name=service.db.name
    )
    dependencies.document_service.storage = SourceDocumentBlobStore(tmp_path)
    with TestClient(
        create_app(dependencies),
        base_url="http://127.0.0.1:8766",
        headers={"Origin": "http://127.0.0.1:8766"},
    ) as client:
        context = client.get(BASE + "/context").json()
        client.headers["X-MathMongo-Library"] = context["library_id"]
        yield client, dependencies


def prepare(client):
    """Run explicit compatible preparation, without changing the active database."""
    state = client.get(BASE + "/catalog/preparation").json()
    assert (
        client.post(BASE + "/catalog/prepare", json={"version": state["version"]}).json()["state"]
        == "ready"
    )


def test_source_edit_reload_idempotence_duplicate_and_legacy_identity(http, service):
    """Rename safely, retain old identities/aliases, detect duplicates and recover after reload."""
    client, _ = http
    root = BASE + "/sources/" + service.test_source_id
    before_names = set(service.db.list_collection_names())
    original = client.get(root + "/profile").json()
    assert set(service.db.list_collection_names()) == before_names
    assert (
        client.post(
            root + "/profile", json={"revision": original["revision"], "changes": {"name": "Nueva"}}
        ).status_code
        == 409
    )
    prepare(client)
    created = service.execute(create(service, titulo="Concepto conservado"))
    assert created["status"] == "saved"
    legacy = {"id": "historical", "source": original["name"], "titulo": "Histórico", "tipo": "nota"}
    service.db.concepts.insert_one(legacy.copy())
    payload = {
        "revision": original["revision"],
        "changes": {
            "name": "Nombre corregido",
            "description": "Descripción nueva",
            "tags": ["familia, literal"],
            "source_type": "web",
        },
    }
    first = client.post(root + "/profile", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["source_id"] == service.test_source_id
    assert original["name"] in [item["value"] for item in first.json()["aliases"]]
    assert (
        client.post(root + "/profile", json=payload).json()["revision"] == first.json()["revision"]
    )
    assert client.get(root + "/profile").json()["description"] == "Descripción nueva"
    assert {
        item["key"]
        for item in client.get(
            BASE + "/concepts", params={"source_id": service.test_source_id}
        ).json()["items"]
    } == {created["key"], "historical@" + original["name"]}
    catalog = SourceCatalogService(service.db)
    assert catalog.create_source(Source(name="Otra fuente")).persisted
    duplicate = client.post(
        root + "/profile",
        json={"revision": first.json()["revision"], "changes": {"name": "Otra fuente"}},
    )
    assert duplicate.status_code == 409
    assert client.get(root + "/profile").json()["name"] == "Nombre corregido"
    stale = client.post(
        root + "/profile",
        json={"revision": original["revision"], "changes": {"description": "Cambio obsoleto"}},
    )
    assert stale.status_code == 409
    assert service.db.concepts.find_one({"id": "historical"})["source"] == original["name"]


def test_shared_reference_edits_require_ack_and_preserve_other_metadata(http, service):
    """A deliberate shared change reaches both sources; stale and implicit changes do not."""
    client, _ = http
    prepare(client)
    catalog = SourceCatalogService(service.db)
    second = catalog.create_source(Source(name="Segunda fuente")).value
    reference = Reference(
        source_ids=[service.test_source_id, second.source_id],
        title="Título original",
        authors=[{"family": "Noether", "given": "Emmy", "orcid": "ORCID conservado"}],
        publisher="Editorial",
        bibtex={"key": "Original", "extra": {"pages": "1-12", "custom": "conservar"}},
    )
    assert catalog.create_reference(reference).persisted
    path = BASE + "/sources/" + service.test_source_id + "/references/" + reference.reference_id
    original = client.get(path).json()
    payload = {"revision": original["revision"], "changes": {"title": "Corrección compartida"}}
    assert client.post(path, json=payload).status_code == 409
    saved = client.post(path, json={**payload, "acknowledge_shared": True})
    assert saved.status_code == 200, saved.text
    stored = catalog.references.get_by_id(reference.reference_id)
    assert (
        stored.authors[0].orcid == "ORCID conservado"
        and stored.bibtex.extra["custom"] == "conservar"
    )
    assert set(stored.source_ids) == {service.test_source_id, second.source_id}
    assert (
        client.get(
            BASE + "/sources/" + second.source_id + "/references/" + reference.reference_id
        ).json()["title"]
        == "Corrección compartida"
    )
    assert client.post(path, json={**payload, "acknowledge_shared": True}).status_code == 200
    assert (
        client.post(
            path, json={**payload, "acknowledge_shared": True, "changes": {"publisher": "Obsoleta"}}
        ).status_code
        == 409
    )
    assert catalog.references.get_by_id(reference.reference_id).publisher == "Editorial"


def test_document_edit_archive_reactivate_never_removes_pdf_or_other_references(http, service):
    """A document's stable ID, bytes and shared reference survive metadata and state changes."""
    client, deps = http
    prepare(client)
    catalog = SourceCatalogService(service.db)
    ref = catalog.create_reference(
        Reference(source_ids=[service.test_source_id], title="Referencia", doi="10.1000/owned")
    ).value
    document = deps.document_service.create_pdf_document(
        source_id=service.test_source_id,
        reference_id=ref.reference_id,
        title="Original",
        pdf_bytes=synthetic_text_pdf(padding_bytes=0),
        original_filename="owned.pdf",
    ).value
    path = BASE + "/sources/" + service.test_source_id + "/documents/" + document.document_id
    original = client.get(path).json()
    saved = client.post(
        path,
        json={
            "revision": original["revision"],
            "changes": {"title": "Título corregido", "description": "Sin tocar el PDF"},
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["pdf"] == original["pdf"]
    archived = client.post(
        path + "/state", json={"revision": saved.json()["revision"], "status": "archived"}
    )
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    assert (
        client.post(
            path + "/state", json={"revision": saved.json()["revision"], "status": "archived"}
        ).status_code
        == 200
    )
    assert client.get(BASE + "/sources/" + service.test_source_id).json()["documents"] == []
    archived_list = client.get(
        BASE + "/sources/" + service.test_source_id, params={"document_status": "archived"}
    ).json()
    assert archived_list["documents"][0]["document_id"] == document.document_id
    active = client.post(
        path + "/state", json={"revision": archived.json()["revision"], "status": "active"}
    )
    assert active.json()["status"] == "active"
    assert deps.document_service.read_pdf_document(
        document.document_id
    ).pdf_bytes == synthetic_text_pdf(padding_bytes=0)
    assert catalog.references.get_by_id(ref.reference_id) is not None


def test_bibtex_preview_selective_import_replay_and_duplicates(http, service):
    """Preview is read-only, selection is explicit and repeated imports do not multiply records."""
    client, _ = http
    prepare(client)
    root = BASE + "/sources/" + service.test_source_id + "/bibtex"
    payload = {
        "operation_id": str(uuid4()),
        "content": "@article{One,title={One},author={Noether, Emmy},year={1918}}\n@book{Two,title={Two},author={Ada},year={1843}}",
    }
    preview = client.post(root + "/preview", json=payload)
    assert preview.status_code == 200, preview.text
    assert len(preview.json()["candidates"]) == 2 and service.db.references.count_documents({}) == 0
    index = preview.json()["candidates"][0]["entry_index"]
    imported = client.post(root + "/import", json={**payload, "selected": [index]})
    assert imported.status_code == 200, imported.text
    assert imported.json()["saved"] == 1, imported.text
    assert client.post(root + "/import", json={**payload, "selected": [index]}).json()["saved"] == 1
    assert service.db.references.count_documents({}) == 1
    duplicate = client.post(
        root + "/import", json={**payload, "operation_id": str(uuid4()), "selected": [index]}
    )
    assert duplicate.json()["items"][0]["status"] == "duplicates"
    assert client.post(root + "/import", json={**payload, "selected": [999]}).status_code == 409
    assert service.db.references.count_documents({}) == 1


def test_link_guard_filters_scope_and_read_summary(http, service):
    """Only unused associations may detach; filtered searches and foreign origins stay isolated."""
    client, _ = http
    prepare(client)
    catalog = SourceCatalogService(service.db)
    ref = catalog.create_reference(
        Reference(source_ids=[service.test_source_id], title="Citation")
    ).value
    path = BASE + "/sources/" + service.test_source_id + "/references/" + ref.reference_id
    record = client.get(path).json()
    service.db.reading_notes.insert_one(
        {"source_id": service.test_source_id, "reference_id": ref.reference_id}
    )
    payload = {"revision": record["revision"], "changes": {}}
    assert client.post(path + "/detach", json=payload).status_code == 409
    service.db.reading_notes.delete_many({})
    assert client.post(path + "/detach", json=payload).json()["detached"]
    assert catalog.references.get_by_id(ref.reference_id) is not None
    root = BASE + "/sources/" + service.test_source_id
    profile = client.get(root + "/profile").json()
    assert (
        client.post(
            root + "/state", json={"revision": profile["revision"], "status": "archived"}
        ).json()["status"]
        == "archived"
    )
    assert client.get(BASE + "/library").json()["total"] == 0
    assert client.get(BASE + "/library", params={"status": "archived"}).json()["total"] == 1
    assert (
        client.post(
            root + "/profile",
            json={"revision": profile["revision"], "changes": {}},
            headers={"X-MathMongo-Library": "foreign"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            root + "/profile",
            json={"revision": profile["revision"], "changes": {}},
            headers={"Origin": "https://foreign.invalid"},
        ).status_code
        == 403
    )


def test_reference_navigation_is_paged_and_does_not_load_full_bibtex(http, service):
    """Search reaches references after page one; full bibliographic source is demand-loaded."""
    client, _ = http
    prepare(client)
    records = [
        Reference(
            source_ids=[service.test_source_id],
            title=f"Referencia {index:03}",
            bibtex={"key": f"ref{index}", "raw": "Contenido BibTeX protegido"},
        ).model_dump(mode="python")
        for index in range(24)
    ]
    service.db.references.insert_many(records)
    path = BASE + "/sources/" + service.test_source_id
    first = client.get(path + "/references").json()
    second = client.get(path + "/references", params={"page": 2}).json()
    assert len(first["items"]) == 20 and len(second["items"]) == 4 and first["total"] == 24
    found = client.get(path + "/references", params={"q": "Referencia 023"}).json()
    assert found["total"] == 1 and found["items"][0]["title"] == "Referencia 023"
    summaries = client.get(path).json()["references"]
    assert all("bibtex" not in item and "provenance" not in item for item in summaries)
    full = client.get(path + "/references/" + found["items"][0]["reference_id"]).json()
    assert full["bibtex"]["raw"] == "Contenido BibTeX protegido"

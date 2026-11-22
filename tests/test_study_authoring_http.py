"""Authoring activities use canonical services and an owned standalone MongoDB."""

from uuid import uuid4

from tests.advanced_reader_test_support import synthetic_text_pdf
from tests.test_knowledge_map_service import create
from tests.test_study_http import http as _http
from tests.test_study_http import owned_client as _owned_client
from tests.test_study_http import service as _service

owned_client = _owned_client
service = _service
http = _http
BASE = "/api/study/v1"


def prepare(client):
    """Explicitly prepare the approved indexes before testing writes."""
    state = client.get(BASE + "/catalog/preparation").json()
    assert (
        client.post(BASE + "/catalog/prepare", json={"version": state["version"]}).json()["state"]
        == "ready"
    )


def test_source_reference_pdf_and_concept_edit_preserve_their_separate_identities(
    http, service, tmp_path
):
    """Read back every saved entity and retry without duplicate records or blobs."""
    client, _ = http
    from mathmongo.source_documents.storage import SourceDocumentBlobStore

    client.app.state.advanced_reader_dependencies.document_service.storage = (
        SourceDocumentBlobStore(tmp_path)
    )
    before = set(service.db.list_collection_names())
    client.get(BASE + "/catalog/preparation")
    assert set(service.db.list_collection_names()) == before
    prepare(client)
    payload = {
        "operation_id": str(uuid4()),
        "name": "Fuente nueva de prueba",
        "source_type": "book",
    }
    first = client.post(BASE + "/sources", json=payload)
    assert first.status_code == 200, first.text
    source = first.json()["source_id"]
    assert client.post(BASE + "/sources", json=payload).json() == first.json()
    ref = {
        "reference_id": "ref_" + str(uuid4()),
        "reference_type": "book",
        "title": "Álgebra de prueba",
        "authors": [{"literal": "Autora de prueba"}],
        "year": 2020,
    }
    capture = {
        "request_id": str(uuid4()),
        "action": "save",
        "source_id": source,
        "reference_data": ref,
    }
    saved = client.post(BASE + "/bibliography", json=capture).json()
    assert saved["status"] == "saved", saved
    assert (
        client.post(BASE + "/bibliography", json=capture).json()["reference_data"]["reference_id"]
        == ref["reference_id"]
    )
    document = {
        "operation_id": str(uuid4()),
        "title": "Documento de prueba",
        "filename": "owned.pdf",
        "reference_id": ref["reference_id"],
    }
    response = client.post(
        BASE + f"/sources/{source}/documents/pdf",
        params=document,
        content=synthetic_text_pdf(padding_bytes=0),
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            BASE + f"/sources/{source}/documents/pdf",
            params=document,
            content=synthetic_text_pdf(padding_bytes=0),
            headers={"Content-Type": "application/pdf"},
        ).json()
        == response.json()
    )
    concept = {
        "operation_id": str(uuid4()),
        "action": "create",
        "source_id": source,
        "titulo": "Definición de prueba",
        "tipo": "definicion",
        "contenido_latex": r"Una idea $\frac{1}{2}$.",
        "reference_id": ref["reference_id"],
    }
    result = client.post(BASE + "/operations", json=concept).json()
    assert result["status"] == "saved", result
    key = result["key"]
    initial = client.get(BASE + "/concepts/detail", params={"key": key}).json()
    metadata = service.find(key)
    service.db.concepts.update_one({"_id": metadata["_id"]}, {"$set": {"unknown_field": "retain"}})
    current = client.get(BASE + "/concepts/detail", params={"key": key}).json()
    edit = {
        **concept,
        "action": "edit",
        "operation_id": str(uuid4()),
        "key": key,
        "revision": current["revision"],
        "contenido_latex": "Cuerpo editado",
    }
    assert client.post(BASE + "/operations", json=edit).json()["status"] == "saved"
    latest = client.get(BASE + "/concepts/detail", params={"key": key}).json()
    assert latest["contenido_latex"] == "Cuerpo editado"
    assert (
        latest["id"] == initial["id"]
        and latest["source_id"] == source
        and latest["reference_id"] == ref["reference_id"]
    )
    assert service.find(key)["unknown_field"] == "retain"
    stale = {**edit, "operation_id": str(uuid4()), "contenido_latex": "No sobrescribir"}
    assert client.post(BASE + "/operations", json=stale).json()["status"] == "conflict"
    assert (
        client.get(BASE + "/concepts/detail", params={"key": key}).json()["contenido_latex"]
        == "Cuerpo editado"
    )
    assert service.db.sources.count_documents({"source_id": source}) == 1
    assert service.db.references.count_documents({"reference_id": ref["reference_id"]}) == 1
    assert service.db.source_documents.count_documents({"source_id": source}) == 1


def test_web_reference_without_identifiers_and_changed_url_replay_does_not_overwrite(http, service):
    """A web citation needs neither ISBN nor DOI and cannot silently replace a correction."""
    client, _ = http
    prepare(client)
    source = client.post(
        BASE + "/sources",
        json={"operation_id": str(uuid4()), "name": "Página académica", "source_type": "web"},
    ).json()["source_id"]
    payload = {
        "request_id": str(uuid4()),
        "action": "save",
        "source_id": source,
        "reference_data": {
            "reference_id": "ref_" + str(uuid4()),
            "reference_type": "web",
            "title": "Página sin identificadores",
            "url": "https://example.org/academia",
        },
    }
    result = client.post(BASE + "/bibliography", json=payload).json()
    assert result["status"] == "saved", result
    assert result["reference_data"]["doi"] is None and result["reference_data"]["isbn"] == []
    payload["reference_data"]["url"] = "https://example.org/changed"
    assert client.post(BASE + "/bibliography", json=payload).json()["status"] == "conflict"
    ref = service.db.references.find_one(
        {"reference_id": payload["reference_data"]["reference_id"]}
    )
    assert ref["url"] == "https://example.org/academia" and ref["accessed_at"] is None


def test_new_authoring_rejects_wrong_scope_unsafe_upload_and_duplicate_source(http, service):
    """Guards run before writes and duplicates preserve the original source."""
    client, _ = http
    prepare(client)
    payload = {
        "operation_id": str(uuid4()),
        "name": "Fuente inalterada",
        "description": "Datos originales",
    }
    source = client.post(BASE + "/sources", json=payload).json()["source_id"]
    original = service.db.sources.find_one({"source_id": source})
    assert (
        client.post(BASE + "/sources", json={**payload, "operation_id": str(uuid4())}).status_code
        == 409
    )
    assert service.db.sources.find_one({"source_id": source}) == original
    assert (
        client.post(
            BASE + "/sources", json=payload, headers={"X-MathMongo-Library": "another"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            BASE + "/sources", json=payload, headers={"Origin": "https://example.org"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            BASE + f"/sources/{source}/documents/pdf",
            params={"operation_id": str(uuid4()), "filename": "bad.pdf", "title": "No publicar"},
            content=b"not a pdf",
            headers={"Content-Type": "application/pdf"},
        ).status_code
        == 409
    )
    assert service.db.source_documents.count_documents({"source_id": source}) == 0


def test_body_edit_keeps_nullable_metadata_and_untouched_legacy_citation(http, service):
    """An adapter's empty controls do not normalize untouched stored metadata."""
    client, _ = http
    key = service.execute(create(service))["key"]
    original = service.find(key)
    keep = {
        "titulo": "  Identidad sin normalizar  ",
        "comentario": None,
        "categorias": None,
        "tipo_aplicacion": None,
        "referencia": {"autor": "Ficha corregida", "campo_compatible": "conservar"},
        "campo_desconocido": {"version": 7},
    }
    service.db.concepts.update_one({"_id": original["_id"]}, {"$set": keep})
    detail = client.get(BASE + "/concepts/detail", params={"key": key}).json()
    assert detail["comentario"] == "" and detail["categorias"] == []
    edit = {
        "operation_id": str(uuid4()),
        "action": "edit",
        "key": key,
        "revision": detail["revision"],
        "titulo": detail["titulo"],
        "contenido_latex": "Sólo el cuerpo cambia",
        "comentario": "",
        "categorias": [],
    }
    assert client.post(BASE + "/operations", json=edit).json()["status"] == "saved"
    after = service.find(key)
    for field, value in keep.items():
        assert after[field] == value
    assert after["id"] == original["id"] and after["source"] == original["source"]


def test_equivalent_identity_index_is_reused_even_after_a_legacy_nonunique_index(service):
    """An existing correct constraint needs neither replacement nor another index."""
    from mathdatabase.mathmongo import ensure_compatible_index
    from mathmongo.study.preparation import AuthoringPreparation

    keys = [("id", 1), ("source", 1)]
    service.db.concepts.drop_index("id_1_source_1")
    service.db.concepts.create_index(keys, name="legacy_nonunique")
    service.db.concepts.create_index(keys, name="correct_identity", unique=True)
    before = list(service.db.concepts.list_indexes())
    assert AuthoringPreparation(service.db).inspect(core_only=True)["state"] == "ready"
    assert ensure_compatible_index(service.db.concepts, keys, unique=True) == "correct_identity"
    assert list(service.db.concepts.list_indexes()) == before


def test_preparation_is_explicit_idempotent_and_checks_the_contract_version(http, service):
    """Inspection never creates collections and repeated preparation keeps records."""
    client, _ = http
    collections = set(service.db.list_collection_names())
    sources = list(service.db.sources.find({}))
    state = client.get(BASE + "/catalog/preparation").json()
    assert state["state"] == "pending"
    assert set(service.db.list_collection_names()) == collections
    assert client.post(BASE + "/catalog/prepare", json={"version": "outdated"}).status_code == 409
    assert set(service.db.list_collection_names()) == collections
    prepare(client)
    indexes = {
        name: list(service.db[name].list_indexes()) for name in service.db.list_collection_names()
    }
    prepare(client)
    assert {
        name: list(service.db[name].list_indexes()) for name in service.db.list_collection_names()
    } == indexes
    assert list(service.db.sources.find({})) == sources


def test_preparation_does_not_replace_incompatible_indexes_or_resolve_duplicates(http, service):
    """A nonunique identity index requires a separate reviewed procedure."""
    client, _ = http
    service.db.concepts.drop_index("id_1_source_1")
    service.db.concepts.create_index([("id", 1), ("source", 1)], name="retain_nonunique")
    service.db.concepts.insert_many(
        [
            {"id": "duplicate", "source": "retained", "detail": 1},
            {"id": "duplicate", "source": "retained", "detail": 2},
        ]
    )
    documents = list(service.db.concepts.find({}))
    indexes = list(service.db.concepts.list_indexes())
    state = client.get(BASE + "/catalog/preparation").json()
    assert state["state"] == "incompatible"
    assert (
        client.post(BASE + "/catalog/prepare", json={"version": state["version"]}).json()["state"]
        == "incompatible"
    )
    assert list(service.db.concepts.find({})) == documents
    assert list(service.db.concepts.list_indexes()) == indexes


def test_failed_preparation_inspection_is_not_reported_as_missing_indexes(
    http, service, monkeypatch
):
    """A driver permission failure has an unverified state and performs no write."""
    from pymongo.errors import OperationFailure

    from mathmongo.source_catalog.indexes import SourceCatalogIndexManager

    client, _ = http
    before = set(service.db.list_collection_names())

    def denied(_self):
        raise OperationFailure("owned test permission failure", code=13)

    monkeypatch.setattr(SourceCatalogIndexManager, "plan", denied)
    state = client.get(BASE + "/catalog/preparation").json()
    assert state["state"] == "unverified"
    assert "permisos" in state["reason"] and "faltan" not in state["reason"]
    assert (
        client.post(BASE + "/catalog/prepare", json={"version": state["version"]}).json()["state"]
        == "unverified"
    )
    assert set(service.db.list_collection_names()) == before

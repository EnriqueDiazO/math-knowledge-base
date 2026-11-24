"""Cornell/CPI HTTP contracts with real PID-owned MongoDB and isolated TeX."""

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib import import_module
from uuid import uuid4

import pytest
from pymongo.collection import Collection
from pymongo.errors import AutoReconnect

from mathmongo.source_catalog.models import Reference
from mathmongo.study.structured_notes import StructuredNotes
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service
from tests.test_library_management_http import http as _http

owned_client = _owned_client
service = _service
http = _http
BASE = "/api/study/v1/structured/"


def payload(family):
    """Use each family's real model, not a generic document fixture."""
    helpers = import_module("tests.test_" + family + "_service")
    return {
        "request_id": str(uuid4()),
        "metadata": {
            key: value
            for key, value in helpers.sample_metadata().items()
            if key in {"title", "date", "project", "context", "tags"}
        },
        "document": helpers.sample_document().to_dict(),
    }


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_create_reload_edit_and_lost_response_retry(http, service, family):
    """Unique creation and exact replay retain canonical regions, identity and associations."""
    client, _ = http
    root, body = BASE + family, payload(family)
    response = client.post(root, json=body)
    assert response.status_code == 200, response.text
    first = response.json()
    identity = first["note_id"]
    assert identity == family + "_" + body["request_id"]
    assert client.post(root, json=body).json() == first
    assert service.db.latex_notes.count_documents({"_id": identity}) == 1
    listing = client.get(root).json()
    assert listing["total"] == 1 and "document" not in listing["items"][0]
    assert "latex_body" not in listing["items"][0]
    assert client.get(root, params={"q": "[not-in-this-note"}).json()["total"] == 0
    detail = root + "/" + identity
    opened = client.get(detail).json()
    assert opened == first
    region = "main" if family == "cornell" else "production"
    changed = deepcopy(opened["document"])
    changed["pages"][0][region]["latex"] = r"Cambio con $\frac{x_i}{1+x}$ y \macro{intacta}"
    edit = {
        "revision": opened["revision"],
        "metadata": {"title": "Edición confirmada"},
        "document": changed,
    }
    saved = client.post(detail, json=edit)
    assert saved.status_code == 200, saved.text
    final = saved.json()
    assert final["metadata"]["title"] == "Edición confirmada"
    assert final["document"] == changed
    assert "\\macro{intacta}" in final["latex_body"]
    assert client.post(detail, json=edit).json() == final
    assert client.get(detail).json() == final
    body["metadata"]["title"] = "Un intento distinto"
    assert client.post(root, json=body).status_code == 409
    assert client.get(detail).json() == final


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_historical_noop_and_partial_edit_preserve_raw_unknowns(http, service, family):
    """No-op HTTP round trip preserves the entire stored BSON, including absent date."""
    client, _ = http
    first = client.post(BASE + family, json=payload(family)).json()
    identity, region = first["note_id"], "main" if family == "cornell" else "production"
    service.db.latex_notes.update_one(
        {"_id": identity},
        {
            "$unset": {"date": "", "context": ""},
            "$set": {
                family + ".custom": "retained",
                family + ".pages.0." + region + ".extra": [1, 2],
                "latex_body": r"\begin{concept}\unknown{α}\end{concept}",
            },
        },
    )
    path = BASE + family + "/" + identity
    before = service.db.latex_notes.find_one({"_id": identity})
    opened = client.get(path).json()
    request = {"revision": opened["revision"], "metadata": {}, "document": opened["document"]}
    assert client.post(path, json=request).status_code == 200
    assert service.db.latex_notes.find_one({"_id": identity}) == before
    request["metadata"] = {"title": "Sólo metadatos"}
    result = client.post(path, json=request)
    assert result.status_code == 200, result.text
    assert result.json()["latex_body"] == before["latex_body"]
    request["revision"] = result.json()["revision"]
    request["document"]["pages"][0][region]["latex"] = "No sobrescribir fuente histórica"
    assert client.post(path, json=request).status_code == 409
    assert service.db.latex_notes.find_one({"_id": identity})[family] == before[family]
    exported = client.post(path + "/export", json={"format": "tex"})
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert any(
            before["latex_body"].encode() in archive.read(name) for name in archive.namelist()
        )
    assert client.post(path + "/export", json={"format": "pdf"}).status_code == 409


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_atomic_http_edit_rejects_interleaved_writer(http, service, monkeypatch, family):
    """The HTTP revision cannot race the canonical persistence snapshot."""
    client, _ = http
    first = client.post(BASE + family, json=payload(family)).json()
    identity = first["note_id"]
    update = Collection.update_one

    def race(collection, query, changes, **options):
        if collection.database.name == service.db.name and collection.name == "latex_notes":
            update(collection, {"_id": identity}, {"$set": {"title": "Escritora concurrente"}})
        return update(collection, query, changes, **options)

    monkeypatch.setattr(Collection, "update_one", race)
    result = client.post(
        BASE + family + "/" + identity,
        json={
            "revision": first["revision"],
            "metadata": {"title": "Tardía"},
            "document": first["document"],
        },
    )
    assert result.status_code == 409
    stored = service.db.latex_notes.find_one({"_id": identity})
    assert stored["title"] == "Escritora concurrente" and stored[family] == first["document"]


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_actual_fit_export_and_overflow_preserve_saved_note(http, service, family):
    """Real isolated geometry/PDF succeeds for valid pages and blocks unreadable overflow."""
    client, _ = http
    first = client.post(BASE + family, json=payload(family)).json()
    path = BASE + family + "/" + first["note_id"]
    fit = client.post(path + "/fit", json={})
    assert fit.status_code == 200, fit.text
    assert not fit.json()["has_overflow"]
    assert len(fit.json()["pages"][0]["regions"]) == 3
    pdf = client.post(path + "/export", json={"format": "pdf"})
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF-")
    region = "summary" if family == "cornell" else "integration"
    huge = deepcopy(first["document"])
    huge["pages"][0][region]["latex"] = "Texto extenso de una región.\\par\n" * 200
    assert (
        client.post(
            path, json={"revision": first["revision"], "metadata": {}, "document": huge}
        ).status_code
        == 200
    )
    before = service.db.latex_notes.find_one({"_id": first["note_id"]})
    report = client.post(path + "/fit", json={})
    assert report.status_code == 200, report.text
    assert report.json()["has_overflow"]
    assert client.post(path + "/export", json={"format": "pdf"}).status_code == 422
    assert service.db.latex_notes.find_one({"_id": first["note_id"]}) == before


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_invalid_requests_and_library_guards_never_create_notes(http, service, family):
    """Read/write identity, model and origin failures are bounded and side-effect free."""
    client, _ = http
    root, body = BASE + family, payload(family)
    assert client.get(root + "/missing").status_code == 404
    assert client.post(root, json=body, headers={"X-MathMongo-Library": "other"}).status_code == 409
    assert (
        client.post(root, json=body, headers={"Origin": "https://invalid.example"}).status_code
        == 403
    )
    body["document"]["schema_version"] = 99
    assert client.post(root, json=body).status_code == 422
    body = payload(family)
    body["metadata"]["title"] = "  "
    assert client.post(root, json=body).status_code == 422
    assert service.db.latex_notes.count_documents({}) == 0
    first = client.post(root, json=payload(family)).json()
    other = "cpi" if family == "cornell" else "cornell"
    assert client.get(BASE + other + "/" + first["note_id"]).status_code == 409
    assert client.get(BASE + "unknown").status_code == 422
    assert client.get(root + "/references/missing").status_code == 409


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_concurrent_creations_and_recovery_after_media_reconciliation_failure(
    http, service, monkeypatch, family
):
    """A partial media-reference failure is retried against one note; shared resources survive."""
    body = payload(family)
    identity = family + "_" + body["request_id"]
    notes = StructuredNotes(service.db, family)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: notes.create(body["request_id"], body["metadata"], body["document"]),
                range(2),
            )
        )
    assert results[0]["note_id"] == results[1]["note_id"] == identity
    assert service.db.latex_notes.count_documents({"_id": identity}) == 1
    reference = Reference(title="Referencia compartida", source_ids=[service.test_source_id])
    service.db.references.insert_one(reference.model_dump(mode="python"))
    client, _ = http
    citation = client.get(BASE + family + "/references/" + reference.reference_id)
    assert citation.status_code == 200, citation.text
    assert "Referencia compartida" in citation.json()["latex"]
    assert citation.json()["reference"]["catalog_reference_id"] == reference.reference_id
    service.db.media_assets.insert_one({"asset_id": "shared-recovery", "note_ids": ["other-note"]})
    region = "main" if family == "cornell" else "production"
    body["request_id"] = str(uuid4())
    body["document"]["pages"][0][region]["image_ids"] = ["shared-recovery"]
    update = Collection.update_one
    broken = True

    def fail_media(collection, query, changes, **options):
        if (
            broken
            and collection.database.name == service.db.name
            and collection.name == "media_assets"
        ):
            raise AutoReconnect("owned simulated acknowledgement loss")
        return update(collection, query, changes, **options)

    monkeypatch.setattr(Collection, "update_one", fail_media)
    with pytest.raises(AutoReconnect):
        notes.create(body["request_id"], body["metadata"], body["document"])
    new_id = family + "_" + body["request_id"]
    assert service.db.latex_notes.count_documents({"_id": new_id}) == 1
    assert service.db.media_assets.find_one({"asset_id": "shared-recovery"})["note_ids"] == [
        "other-note"
    ]
    broken = False
    assert notes.create(body["request_id"], body["metadata"], body["document"])["note_id"] == new_id
    assert set(service.db.media_assets.find_one({"asset_id": "shared-recovery"})["note_ids"]) == {
        "other-note",
        new_id,
    }


def test_identical_cpi_pages_reorder_their_opaque_metadata_and_replay_exactly(http, service):
    """The visible page number is not ownership: identical region bodies can still move."""
    client, _ = http
    body = payload("cpi")
    second = deepcopy(body["document"]["pages"][0])
    second["page_number"] = 2
    body["document"]["pages"].append(second)
    first = client.post(BASE + "cpi", json=body).json()
    identity = first["note_id"]
    service.db.latex_notes.update_one(
        {"_id": identity}, {"$set": {"cpi.pages.0.opaque": "first", "cpi.pages.1.opaque": "second"}}
    )
    path = BASE + "cpi/" + identity
    opened = client.get(path).json()
    edit = {
        "revision": opened["revision"],
        "metadata": {},
        "document": opened["document"],
        "page_origins": [2, 1],
    }
    result = client.post(path, json=edit)
    assert result.status_code == 200, result.text
    assert [page["opaque"] for page in result.json()["document"]["pages"]] == ["second", "first"]
    assert client.post(path, json=edit).json() == result.json()
    edit["page_origins"] = [1, 2]
    assert client.post(path, json=edit).status_code == 409
    invalid = {**edit, "revision": result.json()["revision"], "page_origins": [99, 1]}
    assert client.post(path, json=invalid).status_code == 409
    assert client.get(path).json() == result.json()


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_historical_unsorted_pages_are_presented_in_order_without_rewriting_bson(
    http, service, family
):
    """The canonical display order is distinct from historical BSON array order."""
    client, _ = http
    body = payload(family)
    second = deepcopy(body["document"]["pages"][0])
    order = "order" if family == "cornell" else "page_number"
    second[order] = 2
    if family == "cornell":
        second["page_id"] = "second"
    body["document"]["pages"].append(second)
    first = client.post(BASE + family, json=body).json()
    identity = first["note_id"]
    service.db.latex_notes.update_one(
        {"_id": identity}, {"$set": {family + ".pages": list(reversed(first["document"]["pages"]))}}
    )
    before = service.db.latex_notes.find_one({"_id": identity})
    path = BASE + family + "/" + identity
    opened = client.get(path).json()
    assert [page[order] for page in opened["document"]["pages"]] == [1, 2]
    origins = [
        page["page_id" if family == "cornell" else "page_number"]
        for page in opened["document"]["pages"]
    ]
    edit = {
        "revision": opened["revision"],
        "metadata": {},
        "document": opened["document"],
        "page_origins": origins,
    }
    assert client.post(path, json=edit).status_code == 200
    assert service.db.latex_notes.find_one({"_id": identity}) == before
    edit["document"]["pages"].reverse()
    assert client.post(path, json=edit).status_code == 409
    assert service.db.latex_notes.find_one({"_id": identity}) == before

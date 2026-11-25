"""Image previews and PDF errors stay within their saved note and library."""

from copy import deepcopy

import pytest
from PIL import Image

from tests.test_structured_notes_http import http as _http
from tests.test_structured_notes_http import owned_client as _owned_client
from tests.test_structured_notes_http import payload
from tests.test_structured_notes_http import service as _service

owned_client = _owned_client
service = _service
http = _http


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_saved_note_image_resolution_is_scoped_and_missing_export_is_not_success(
    http, service, tmp_path, family
):
    """Inline-only images resolve even when reverse registry/top-level IDs are stale."""
    client, _ = http
    root = "/api/study/v1/structured/" + family
    first = client.post(root, json=payload(family)).json()
    region = "production" if family == "cpi" else "main"
    document = deepcopy(first["document"])
    document["pages"][0][region]["latex"] = "\\" + family + "image[0.7]{scoped-image}"
    note = client.post(
        root + "/" + first["note_id"],
        json={"revision": first["revision"], "metadata": {}, "document": document},
    ).json()
    identity = note["note_id"]
    path = tmp_path / "original.png"
    Image.new("RGB", (41, 23), "#197f96").save(path)
    service.db.media_assets.insert_one(
        {"asset_id": "scoped-image", "filename": "original.png", "path": str(path), "note_ids": []}
    )
    service.db.latex_notes.update_one({"_id": identity}, {"$set": {"image_ids": []}})
    endpoint = root + "/" + identity
    listing = client.get(endpoint + "/images")
    assert listing.status_code == 200 and listing.json()["images"][0]["state"] == "ready"
    assert str(tmp_path) not in listing.text
    response = client.get(endpoint + "/images/scoped-image")
    assert response.status_code == 200 and response.content == path.read_bytes()
    assert response.headers["content-type"] == "image/png"
    assert client.get(endpoint + "/images/not-in-this-note").status_code == 404
    assert (
        client.get(
            endpoint + "/images/scoped-image", headers={"X-MathMongo-Library": "other"}
        ).status_code
        == 409
    )
    before = service.db.latex_notes.find_one({"_id": identity})
    path.unlink()
    assert client.get(endpoint + "/images").json()["images"][0]["state"] == "missing"
    assert client.get(endpoint + "/images/scoped-image").status_code == 404
    failed = client.post(endpoint + "/export", json={"format": "pdf"})
    assert failed.status_code == 422 and failed.json()["error"]["code"] == "note_images_unavailable"
    assert "vuelve a asociar" in failed.json()["error"]["message"]
    assert service.db.latex_notes.find_one({"_id": identity}) == before


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_pdf_exports_one_observed_snapshot_during_a_concurrent_source_edit(
    http, service, monkeypatch, family
):
    """A later revision cannot replace the source between resource discovery and PDF measurement."""
    from mathmongo.study.structured_notes import StructuredNotes

    client, _ = http
    root = "/api/study/v1/structured/" + family
    first = client.post(root, json=payload(family)).json()
    observed = StructuredNotes.opened
    calls = []

    def race(notes, identity):
        snapshot = observed(notes, identity)
        calls.append(snapshot["latex_body"])
        notes.db.latex_notes.update_one(
            {"_id": snapshot["_id"]}, {"$set": {"latex_body": "Fuente cambiada por otra ventana"}}
        )
        return snapshot

    monkeypatch.setattr(StructuredNotes, "opened", race)
    response = client.post(root + "/" + first["note_id"] + "/export", json={"format": "pdf"})
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    assert len(calls) == 1 and calls[0] == first["latex_body"]
    assert (
        service.db.latex_notes.find_one({"_id": first["note_id"]})["latex_body"]
        == "Fuente cambiada por otra ventana"
    )

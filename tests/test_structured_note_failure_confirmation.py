"""Negative confirmation paths for structured notes, backed by the same owned MongoDB."""

import pytest

from exporters_latex.sandbox import CompiledDocument
from mathmongo.advanced_reader.document_access import AdvancedReaderError
from mathmongo.study.structured_notes import StructuredNotes
from mathmongo.study.structured_notes import structured_format
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service
from tests.test_library_management_http import http as _http
from tests.test_structured_notes_http import BASE
from tests.test_structured_notes_http import payload

owned_client = _owned_client
service = _service
http = _http


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_late_writer_and_obsolete_retries_cannot_announce_a_false_save(
    http, service, monkeypatch, family
):
    """Read-back is part of confirmation, including a race after the atomic write."""
    client, _ = http
    body = payload(family)
    first = client.post(BASE + family, json=body).json()
    identity = first["note_id"]
    path = BASE + family + "/" + identity
    notes = StructuredNotes(service.db, family)
    original_open = StructuredNotes.opened
    reads = 0

    def observed(self, requested):
        nonlocal reads
        reads += 1
        if reads == 2:
            self.db.latex_notes.update_one(
                {"_id": identity}, {"$set": {"title": "Otra escritura tras el CAS"}}
            )
        return original_open(self, requested)

    with monkeypatch.context() as patch:
        patch.setattr(StructuredNotes, "opened", observed)
        with pytest.raises(AdvancedReaderError) as error:
            notes.update(identity, first["revision"], {"title": "Mi edición"}, first["document"])
        assert error.value.status_code == 409
    assert client.get(path).json()["metadata"]["title"] == "Otra escritura tras el CAS"
    assert (
        client.post(
            path,
            json={
                "revision": first["revision"],
                "metadata": {"title": "Mi edición"},
                "document": first["document"],
            },
        ).status_code
        == 409
    )
    assert client.post(BASE + family, json=body).status_code == 409
    assert client.get(path).json()["metadata"]["title"] == "Otra escritura tras el CAS"


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_measurement_failure_and_failed_pdf_keep_source_and_tex_available(
    http, service, monkeypatch, family
):
    """Unknown TeX can be stored; failed isolated measurement never becomes a fit/PDF success."""
    client, _ = http
    body = payload(family)
    first = client.post(BASE + family, json=body).json()
    path = BASE + family + "/" + first["note_id"]
    before = service.db.latex_notes.find_one({"_id": first["note_id"]})
    # Only the final external compiler failure is injected. Geometry still runs in bwrap.
    monkeypatch.setattr(
        "mathmongo.study.structured_routes.compile_project",
        lambda bundle: CompiledDocument("failed", "No se confirmó la salida PDF."),
    )
    result = client.post(path + "/export", json={"format": "pdf"})
    assert (
        result.status_code == 422 and result.json()["error"]["code"] == "structured_export_failed"
    )
    assert service.db.latex_notes.find_one({"_id": first["note_id"]}) == before
    region = "main" if family == "cornell" else "production"
    first["document"]["pages"][0][region]["latex"] = r"\undefinedMathMongoCommand{preservar fuente}"
    edited = client.post(
        path, json={"revision": first["revision"], "metadata": {}, "document": first["document"]}
    )
    assert edited.status_code == 200, edited.text
    before = service.db.latex_notes.find_one({"_id": first["note_id"]})
    result = client.post(path + "/fit", json={})
    assert result.status_code == 422 and result.json()["error"]["code"] == "structured_fit_failed"
    assert client.post(path + "/export", json={"format": "tex"}).status_code == 200
    assert service.db.latex_notes.find_one({"_id": first["note_id"]}) == before


def test_unknown_activity_is_rejected_before_any_domain_operation():
    """The canonical dispatch helper cannot import an arbitrary module from an activity name."""
    with pytest.raises(AdvancedReaderError) as error:
        structured_format("../../../other")
    assert error.value.status_code == 404

"""Existing Cornell/CPI editorial models persist and export without losing unknowns."""

import subprocess
from copy import deepcopy

import pytest

from tests.test_structured_notes_http import http as _http
from tests.test_structured_notes_http import owned_client as _owned_client
from tests.test_structured_notes_http import payload
from tests.test_structured_notes_http import service as _service

owned_client = _owned_client
service = _service
http = _http
BASE = "/api/study/v1/structured/"


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_editorial_settings_preserve_regions_extensions_and_export(http, service, family, tmp_path):
    """Footers/watermarks use the canonical renderer and never rewrite untouched region bodies."""
    client, _ = http
    first = client.post(BASE + family, json=payload(family)).json()
    identity = first["note_id"]
    service.db.latex_notes.update_one({"_id": identity}, {"$set": {
        f"{family}.watermark.private_extension": {"keep": True}
    }})
    path = BASE + family + "/" + identity
    opened = client.get(path).json()
    document = deepcopy(opened["document"])
    document["attribution"].update(enabled=True, mode="custom", text="Autoría temporal conservada")
    document["watermark"].update(enabled=True, type="text", text="ESTUDIO", opacity=0.12, scale=0.4)
    request = {"revision": opened["revision"], "metadata": {}, "document": document}
    response = client.post(path, json=request)
    assert response.status_code == 200, response.text
    final = response.json()
    assert final["document"]["pages"] == opened["document"]["pages"]
    assert final["document"]["watermark"]["private_extension"] == {"keep": True}
    assert final["document"]["attribution"]["text"] == "Autoría temporal conservada"
    assert client.post(path, json=request).json() == final
    snapshot = service.db.latex_notes.find_one({"_id": identity})
    pdf = client.post(path + "/export", json={"format": "pdf"})
    assert pdf.status_code == 200, pdf.text[:300] if pdf.status_code != 200 else ""
    assert pdf.content.startswith(b"%PDF-")
    file = tmp_path / f"{family}-editorial.pdf"
    file.write_bytes(pdf.content)
    text = subprocess.run(["pdftotext", str(file), "-"], capture_output=True, text=True, check=True).stdout
    assert "Autoría temporal conservada" in " ".join(text.split())
    assert service.db.latex_notes.find_one({"_id": identity}) == snapshot


@pytest.mark.parametrize("family", ["cornell", "cpi"])
@pytest.mark.parametrize(("field", "value"), [("opacity", -0.1), ("scale", 2.1), ("position", "bottom_left")])
def test_invalid_editorial_setting_preserves_the_entire_note(http, service, family, field, value):
    """HTTP uses the canonical numeric/position rules before writing any note or resource."""
    client, _ = http
    opened = client.post(BASE + family, json=payload(family)).json()
    original = service.db.latex_notes.find_one({"_id": opened["note_id"]})
    document = deepcopy(opened["document"])
    document["watermark"][field] = value
    response = client.post(BASE + family + "/" + opened["note_id"], json={
        "revision": opened["revision"], "metadata": {}, "document": document,
    })
    assert response.status_code == 422
    assert service.db.latex_notes.find_one({"_id": opened["note_id"]}) == original

"""Diario behavior with real owned MongoDB, historical snapshots and isolated exports."""

import io
import os
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo.collection import Collection

from mathmongo.source_catalog.models import Reference
from mathmongo.study.notebook import Notebook
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service
from tests.test_library_management_http import http as _http

http = _http
owned_client = _owned_client
service = _service
BASE = "/api/study/v1/notebook"


def test_react_backend_imports_with_streamlit_unavailable(tmp_path):
    """The independent HTTP app remains importable in the Streamlit-free runtime."""
    script = """
import importlib.abc
import sys
class NoStreamlit(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'streamlit' or fullname.startswith('streamlit.'):
            raise ModuleNotFoundError('Streamlit is not part of this runtime')
sys.meta_path.insert(0, NoStreamlit())
from mathmongo.advanced_reader.app import create_app
from mathmongo.study.notebook import Notebook
assert 'streamlit' not in sys.modules
"""
    env = dict(
        os.environ,
        **{
            f"XDG_{kind}_HOME": str(tmp_path / kind.lower())
            for kind in ("CONFIG", "DATA", "CACHE", "STATE")
        },
    )
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def payload(**changes):
    """Build a complete independent Diario creation, without a source requirement."""
    return {
        "request_id": str(uuid4()),
        "title": "Entrada recuperable",
        "date": "2026-11-24",
        "latex_body": r"Texto con $x^2$.",
        "project": "Álgebra",
        **changes,
    }


def test_create_replay_and_reload_keep_exact_source_and_references(http, service):
    """A note snapshot remains stable even if the shared catalog reference later changes."""
    client, _ = http
    reference = Reference(title="Original", source_ids=[service.test_source_id])
    service.db.references.insert_one(reference.model_dump(mode="python"))
    request = payload(catalog_reference_ids=[reference.reference_id])
    before = set(service.db.list_collection_names())
    first = client.post(BASE, json=request)
    assert first.status_code == 200, first.text
    note = first.json()
    service.db.references.update_one(
        {"reference_id": reference.reference_id}, {"$set": {"title": "Catálogo corregido"}}
    )
    replay = client.post(BASE, json=request)
    assert replay.json() == note
    assert client.get(BASE + "/" + note["note_id"]).json() == note
    assert note["references"][0]["title"] == "Original"
    assert service.db.latex_notes.count_documents({}) == 1
    assert client.get(BASE, params={"source_id": service.test_source_id}).json()["total"] == 1
    assert set(service.db.list_collection_names()) - before == {"latex_notes"}
    assert client.post(BASE, json={**request, "title": "Otro intento"}).status_code == 409
    assert service.db.latex_notes.find_one({})["title"] == request["title"]


def test_concurrent_creation_has_one_idempotent_document(service):
    """Unique historical _id storage resolves concurrent retries without duplicate notes."""
    identity = uuid4()

    def create():
        return Notebook(service.db).create(identity, {"title": "Única", "latex_body": "$x$"}, [])

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _index: create(), range(2)))
    assert results[0] == results[1]
    assert service.db.latex_notes.count_documents({}) == 1


@pytest.mark.parametrize("identity", ["historical-string", ObjectId()])
def test_historical_open_and_unchanged_save_perform_no_normalization(http, service, identity):
    """ObjectId and string notes keep unknown macros, settings, media and all absent fields."""
    client, _ = http
    original = {
        "_id": identity,
        "title": "Histórica",
        "latex_body": "% no normalizar\n\\macroDesconocida{α}\n\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}\n",
        "unknown_historical": {"nested": [1, "two"]},
        "image_ids": ["shared"],
    }
    service.db.latex_notes.insert_one(original.copy())
    path = BASE + "/" + str(identity)
    opened = client.get(path)
    assert opened.status_code == 200, opened.text
    assert opened.json()["latex_body"] == original["latex_body"]
    saved = client.post(
        path,
        json={
            "revision": opened.json()["revision"],
            "changes": {"latex_body": original["latex_body"]},
        },
    )
    assert saved.json() == opened.json()
    assert service.db.latex_notes.find_one({"_id": identity}) == original


def test_minimal_edit_replay_and_stale_conflict_preserve_unknown_fields(http, service):
    """Editing one field preserves associations and a lost-ACK retry does not touch timestamps."""
    client, _ = http
    note = client.post(BASE, json=payload()).json()
    identity = note["note_id"]
    service.db.latex_notes.update_one(
        {"_id": identity},
        {"$set": {"unknown": 42, "image_ids": ["shared"], "page_layout.custom": "kept"}},
    )
    path = BASE + "/" + identity
    note = client.get(path).json()
    request = {
        "revision": note["revision"],
        "changes": {"latex_body": "Cambio localizado\n" + note["latex_body"]},
    }
    first = client.post(path, json=request)
    assert first.status_code == 200
    before_retry = service.db.latex_notes.find_one({"_id": identity})
    assert client.post(path, json=request).json() == first.json()
    assert service.db.latex_notes.find_one({"_id": identity}) == before_retry
    assert before_retry["unknown"] == 42 and before_retry["image_ids"] == ["shared"]
    assert before_retry["page_layout"]["custom"] == "kept"
    assert (
        client.post(
            path, json={"revision": note["revision"], "changes": {"title": "Desactualizada"}}
        ).status_code
        == 409
    )
    assert service.db.latex_notes.find_one({"_id": identity}) == before_retry


def test_atomic_snapshot_detects_race_between_revision_read_and_write(http, service, monkeypatch):
    """A writer interleaved at Mongo update cannot lose its title or other stored fields."""
    client, _ = http
    note = client.post(BASE, json=payload()).json()
    update = Collection.update_one

    def interleave(collection, query, values, **options):
        if (
            collection.database.name == service.db.name
            and collection.name == "latex_notes"
            and "$expr" in query
        ):
            update(collection, {"_id": note["note_id"]}, {"$set": {"title": "Otra ventana"}})
        return update(collection, query, values, **options)

    monkeypatch.setattr(Collection, "update_one", interleave)
    result = client.post(
        BASE + "/" + note["note_id"],
        json={"revision": note["revision"], "changes": {"latex_body": "Escritura tardía"}},
    )
    assert result.status_code == 409
    stored = service.db.latex_notes.find_one({"_id": note["note_id"]})
    assert stored["title"] == "Otra ventana" and stored["latex_body"] == note["latex_body"]


def test_search_is_paged_and_returns_summaries_without_document_body(http, service):
    """Body search, project filters and pagination do not load full source into navigation."""
    client, _ = http
    service.db.latex_notes.insert_many(
        [
            {
                "title": f"Entrada {index}",
                "latex_body": "buscar [literal]",
                "date": "2026-11-24",
                "project": "Álgebra",
            }
            for index in range(23)
        ]
    )
    result = client.get(BASE, params={"q": "[literal]", "page": 2}).json()
    assert len(result["items"]) == 3 and result["total"] == 23
    assert all("latex_body" not in item and "references" not in item for item in result["items"])
    assert client.get(BASE, params={"project": "Otra"}).json()["total"] == 0


@pytest.mark.parametrize("note_format", ["cornell_math_v1", "cpi_v1", "unknown_v4"])
def test_structured_notes_are_not_flattened_or_overwritten(http, service, note_format):
    """The free-form adapter cannot reinterpret Cornell/CPI or unknown historical schemas."""
    client, _ = http
    original = {
        "_id": "structured",
        "title": "Estructurada",
        "note_format": note_format,
        "latex_body": "Proyección",
        "regions": {"keep": True},
    }
    service.db.latex_notes.insert_one(original.copy())
    assert client.get(BASE + "/structured").status_code == 409
    assert (
        client.post(
            BASE + "/structured", json={"revision": "a" * 64, "changes": {"latex_body": "Aplanada"}}
        ).status_code
        == 409
    )
    assert client.get(BASE).json()["total"] == 0
    assert service.db.latex_notes.find_one({}) == original


def test_invalid_fields_scope_and_origin_never_write(http, service):
    """Malformed fields and a foreign library/browser origin are rejected before storage."""
    client, _ = http
    for fields in (
        {"title": " "},
        {"latex_body": ""},
        {"date": "2026-02-31"},
        {"collection": "other"},
        {"catalog_reference_ids": None},
    ):
        assert client.post(BASE, json=payload(**fields)).status_code == 422
    assert client.post(BASE, json=payload(catalog_reference_ids=["ref_missing"])).status_code == 409
    assert (
        client.post(BASE, json=payload(), headers={"X-MathMongo-Library": "different"}).status_code
        == 409
    )
    assert (
        client.post(BASE, json=payload(), headers={"Origin": "https://foreign.invalid"}).status_code
        == 403
    )
    assert service.db.latex_notes.count_documents({}) == 0
    assert client.get(BASE + "/absent").status_code == 404


def test_exports_reuse_canonical_templates_and_preserve_an_authored_preamble(
    http, service, tmp_path
):
    """New visual-compatible bodies and complete historical LaTeX compile with sandboxing."""
    client, _ = http
    body = r"\newcommand{\custom}[1]{#1^2}" + "\nDiario matemático $\\custom{x}$."
    note = client.post(BASE, json=payload(latex_body=body)).json()
    root = BASE + "/" + note["note_id"]
    zipped = client.post(root + "/export", json={"format": "tex"})
    assert zipped.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as archive:
        assert any(
            body.encode() in archive.read(name)
            for name in archive.namelist()
            if name.endswith(".tex")
        )
    pdf = client.post(root + "/export", json={"format": "pdf"})
    assert pdf.status_code == 200, pdf.text[:500]
    assert pdf.content.startswith(b"%PDF-")
    (tmp_path / "diario.pdf").write_bytes(pdf.content)
    complete = "% preámbulo propio\n\\documentclass{article}\n\\begin{document}\nCuerpo $x^2$ único.\n\\end{document}\n"
    service.db.latex_notes.insert_one({"_id": "full", "title": "Completa", "latex_body": complete})
    with zipfile.ZipFile(
        io.BytesIO(client.post(BASE + "/full/export", json={"format": "tex"}).content)
    ) as archive:
        main = next(name for name in archive.namelist() if name.endswith("/main.tex"))
        raw = next(name for name in archive.namelist() if name.endswith("/content/body.tex"))
        assert archive.read(raw).decode() == complete
        exported = archive.read(main).decode()
        assert exported.count(r"\documentclass") == 1 and exported.count(r"\begin{document}") == 1
        assert (
            exported.split(r"\begin{document}", 1)[1] == complete.split(r"\begin{document}", 1)[1]
        )
    assert client.post(BASE + "/full/export", json={"format": "pdf"}).status_code == 200

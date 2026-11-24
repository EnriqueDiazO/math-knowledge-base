"""Whole-note operations on owned MongoDB: historical source, replay, CAS and partial writes."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo.collection import Collection
from pymongo.errors import AutoReconnect

from tests.test_notebook_http import payload as diary_payload
from tests.test_structured_notes_http import http as _http
from tests.test_structured_notes_http import owned_client as _owned_client
from tests.test_structured_notes_http import payload
from tests.test_structured_notes_http import service as _service

http = _http
owned_client = _owned_client
service = _service


def new_note(client, family):
    """New note."""
    root = "/api/study/v1/notebook" if family == "diary" else "/api/study/v1/structured/" + family
    body = diary_payload() if family == "diary" else payload(family)
    response = client.post(root, json=body)
    assert response.status_code == 200, response.text
    note = response.json()
    return root + "/" + note["note_id"], note


def action(note, kind, **changes):
    """Action."""
    return {"action": kind, "revision": note["revision"], "request_id": str(uuid4()), **changes}


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_copy_is_exact_historical_and_idempotent_with_shared_resources(
    http, service, family, tmp_path
):
    """Copy is exact historical and idempotent with shared resources."""
    client, _ = http
    path, first = new_note(client, family)
    identity = first["note_id"]
    raw = r"\begin{concept}{Original}\tikz{\draw(0,0)--(1,1);}\unknown{á}\end{concept}"
    service.db.latex_notes.update_one(
        {"_id": identity},
        {
            "$set": {
                "latex_body": raw,
                "unknown": {"keep": [1, "á"]},
                family + ".custom": {"keep": True},
                "image_ids": ["shared-image"],
            }
        },
    )
    file = tmp_path / "shared.png"
    file.write_bytes(b"original private bytes")
    service.db.media_assets.insert_one(
        {
            "asset_id": "shared-image",
            "note_ids": [identity, "other-note"],
            "concept_ids": ["c@source"],
            "absolute_path": str(file),
        }
    )
    original = service.db.latex_notes.find_one({"_id": identity})
    first = client.get(path).json()
    request = action(first, "duplicate", title="Copia histórica")
    results = list(
        ThreadPoolExecutor(4).map(lambda _: client.post(path + "/actions", json=request), range(4))
    )
    assert all(r.status_code == 200 for r in results), [(r.status_code, r.text) for r in results]
    target = results[0].json()["note_id"]
    copied = service.db.latex_notes.find_one({"_id": target})
    assert (
        target != identity
        and copied["latex_body"] == raw
        and copied["unknown"] == original["unknown"]
    )
    assert copied[family] == original[family]
    assert service.db.latex_notes.count_documents({"study_copy_source": identity}) == 1
    assert set(service.db.media_assets.find_one({"asset_id": "shared-image"})["note_ids"]) == {
        identity,
        "other-note",
        target,
    }
    assert (
        service.db.latex_notes.find_one({"_id": identity}) == original
        and file.read_bytes() == b"original private bytes"
    )
    request["title"] = "Otro intento con el mismo identificador"
    assert client.post(path + "/actions", json=request).status_code == 409


@pytest.mark.parametrize("family", ["diary", "cornell", "cpi"])
def test_delete_replays_only_its_own_note_and_preserves_shared_references(
    http, service, family, tmp_path
):
    """Delete replays only its own note and preserves shared references."""
    client, _ = http
    path, note = new_note(client, family)
    identity = note["note_id"]
    file = tmp_path / "kept.png"
    file.write_bytes(b"never purged")
    service.db.media_assets.insert_one(
        {
            "asset_id": "shared",
            "note_ids": [identity, "other-note"],
            "concept_ids": ["concept@source"],
            "absolute_path": str(file),
        }
    )
    service.db.references.insert_one({"_id": "untouched-reference", "opaque": True})
    request = action(note, "delete")
    first = client.post(path + "/actions", json=request)
    assert first.status_code == 200, first.text
    assert (
        first.json()["status"] == "deleted"
        and service.db.latex_notes.find_one({"_id": identity}) is None
    )
    assert client.post(path + "/actions", json=request).json() == first.json()
    assert service.db.media_assets.find_one({"asset_id": "shared"})["note_ids"] == ["other-note"]
    assert file.exists() and service.db.references.find_one({"_id": "untouched-reference"}) == {
        "_id": "untouched-reference",
        "opaque": True,
    }
    receipt = service.db.study_note_operations.find_one({})
    assert receipt["completed"] and "snapshot" not in receipt
    request["revision"] = "a" * 64
    assert client.post(path + "/actions", json=request).status_code == 409


@pytest.mark.parametrize("family", ["diary", "cornell", "cpi"])
def test_stale_or_midflight_edit_never_deletes_or_detaches(http, service, family, monkeypatch):
    """Stale or midflight edit never deletes or detaches."""
    client, _ = http
    path, note = new_note(client, family)
    identity = note["note_id"]
    service.db.media_assets.insert_one({"asset_id": "keep", "note_ids": [identity]})
    native = Collection.delete_one
    attempted = False

    def race(collection, query, *args, **kwargs):
        """Race."""
        nonlocal attempted
        if collection.name == "latex_notes" and "$expr" in query and not attempted:
            attempted = True
            collection.update_one({"_id": identity}, {"$set": {"concurrent_extension": True}})
        return native(collection, query, *args, **kwargs)

    monkeypatch.setattr(Collection, "delete_one", race)
    result = client.post(path + "/actions", json=action(note, "delete"))
    assert attempted and result.status_code == 409
    assert service.db.latex_notes.find_one({"_id": identity})["concurrent_extension"] is True
    assert service.db.media_assets.find_one({"asset_id": "keep"})["note_ids"] == [identity]


@pytest.mark.parametrize("family", ["diary", "cornell", "cpi"])
def test_failed_cleanup_is_recoverable_after_deleted_note_reload(
    http, service, family, monkeypatch
):
    """Failed cleanup is recoverable after deleted note reload."""
    client, _ = http
    path, note = new_note(client, family)
    identity = note["note_id"]
    service.db.media_assets.insert_one({"asset_id": "kept", "note_ids": [identity, "remaining"]})
    native = Collection.update_one
    failed = False

    def interrupted(collection, query, update, *args, **kwargs):
        """Interrupted."""
        nonlocal failed
        if collection.name == "media_assets" and "$pull" in update and not failed:
            failed = True
            raise AutoReconnect("Owned cleanup interruption")
        return native(collection, query, update, *args, **kwargs)

    monkeypatch.setattr(Collection, "update_one", interrupted)
    request = action(note, "delete")
    response = client.post(path + "/actions", json=request)
    assert failed and response.status_code == 503
    assert service.db.latex_notes.find_one({"_id": identity}) is None
    assert client.get(path).status_code == 404
    retried = client.post(path + "/actions", json=request)
    assert retried.status_code == 200 and retried.json()["status"] == "deleted"
    assert service.db.media_assets.find_one({"asset_id": "kept"})["note_ids"] == ["remaining"]


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_copy_retry_finishes_resources_even_after_original_disappears(
    http, service, family, monkeypatch
):
    """Copy retry finishes resources even after original disappears."""
    client, _ = http
    path, note = new_note(client, family)
    identity = note["note_id"]
    region = "main" if family == "cornell" else "production"
    service.db.latex_notes.update_one(
        {"_id": identity},
        {"$set": {family + ".pages.0." + region + ".image_ids": ["image"], "image_ids": ["image"]}},
    )
    note = client.get(path).json()
    service.db.media_assets.insert_one({"asset_id": "image", "note_ids": [identity]})
    native = Collection.update_one
    failed = False

    def interrupted(collection, query, update, *args, **kwargs):
        """Interrupted."""
        nonlocal failed
        if collection.name == "media_assets" and "$addToSet" in update and not failed:
            failed = True
            raise AutoReconnect("Owned copy interruption")
        return native(collection, query, update, *args, **kwargs)

    monkeypatch.setattr(Collection, "update_one", interrupted)
    request = action(note, "duplicate", title="Copia pendiente")
    assert client.post(path + "/actions", json=request).status_code == 503
    assert failed and service.db.latex_notes.count_documents({"study_copy_source": identity}) == 1
    service.db.latex_notes.delete_one({"_id": identity})
    result = client.post(path + "/actions", json=request)
    assert result.status_code == 200, result.text
    target = result.json()["note_id"]
    assert target in service.db.media_assets.find_one({"asset_id": "image"})["note_ids"]
    assert service.db.latex_notes.count_documents({"study_copy_source": identity}) == 1


def test_scopes_wrong_formats_and_invalid_intents_never_write(http, service):
    """Scopes wrong formats and invalid intents never write."""
    client, _ = http
    path, note = new_note(client, "diary")
    snapshot = deepcopy(list(service.db.latex_notes.find()))
    assert (
        client.post(
            path + "/actions", json=action(note, "duplicate", title="No permitido")
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/actions", json=action(note, "delete", title="No permitido")
        ).status_code
        == 422
    )
    assert (
        client.post(
            path + "/actions", json=action(note, "delete"), headers={"X-MathMongo-Library": "other"}
        ).status_code
        == 409
    )
    wrong = path.replace("/notebook/", "/structured/cpi/")
    assert client.post(wrong + "/actions", json=action(note, "delete")).status_code == 409
    assert (
        list(service.db.latex_notes.find()) == snapshot
        and service.db.study_note_operations.count_documents({}) == 0
    )


def test_deleting_objectid_does_not_delete_an_equal_printable_string_identity(http, service):
    """Deleting objectid does not delete an equal printable string identity."""
    client, _ = http
    identity = ObjectId()
    key = str(identity)
    service.db.latex_notes.insert_many(
        [
            {"_id": identity, "title": "ObjectId", "latex_body": "original"},
            {"_id": key, "title": "String", "latex_body": "other"},
        ]
    )
    path = "/api/study/v1/notebook/" + key
    note = client.get(path).json()
    result = client.post(path + "/actions", json=action(note, "delete"))
    assert result.status_code == 200, result.text
    assert service.db.latex_notes.find_one({"_id": identity}) is None
    assert service.db.latex_notes.find_one({"_id": key})["latex_body"] == "other"


def test_connection_failure_is_not_misreported_as_a_missing_objectid_note(
    http, service, monkeypatch
):
    """A failed read cannot fall through to a different BSON identity and return missing."""
    client, _ = http
    identity = ObjectId()
    service.db.latex_notes.insert_one({"_id": identity, "title": "Real", "latex_body": "Intacto"})
    native = Collection.find_one
    failed = False

    def interrupted(collection, query=None, *args, **kwargs):
        nonlocal failed
        if collection.name == "latex_notes" and query == {"_id": identity} and not failed:
            failed = True
            raise AutoReconnect("Owned failed snapshot read")
        return native(collection, query, *args, **kwargs)

    monkeypatch.setattr(Collection, "find_one", interrupted)
    response = client.post(
        "/api/study/v1/notebook/" + str(identity) + "/actions",
        json={"action": "delete", "request_id": str(uuid4()), "revision": "a" * 64},
    )
    assert failed and response.status_code == 503
    assert service.db.latex_notes.find_one({"_id": identity})["latex_body"] == "Intacto"
    assert service.db.study_note_operations.count_documents({}) == 0


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_note_filters_preserve_mixed_historical_dates_and_ignore_other_formats(
    http, service, family
):
    """Date/context/project filters match historical BSON and string dates without mutation."""
    from datetime import datetime

    client, _ = http
    path, note = new_note(client, family)
    original = service.db.latex_notes.find_one({"_id": note["note_id"]})
    service.db.latex_notes.update_one(
        {"_id": original["_id"]},
        {"$set": {"date": "2026-11-24", "project": "Proyecto exacto", "context": "estudio"}},
    )
    copy = deepcopy(service.db.latex_notes.find_one({"_id": original["_id"]}))
    copy["_id"] = "bson-date"
    copy["date"] = datetime(2026, 11, 24, 23, 59, 59)
    service.db.latex_notes.insert_one(copy)
    other = deepcopy(copy)
    other["_id"] = "other-project"
    other["project"] = "Otro"
    service.db.latex_notes.insert_one(other)
    before = list(service.db.latex_notes.find().sort("_id", 1))
    root = "/api/study/v1/structured/" + family
    params = {
        "project": "Proyecto exacto",
        "context": "estudio",
        "date_from": "2026-11-24",
        "date_to": "2026-11-24",
    }
    response = client.get(root, params=params)
    assert response.status_code == 200
    assert {r["note_id"] for r in response.json()["items"]} == {original["_id"], "bson-date"}
    assert all("document" not in r and "latex_body" not in r for r in response.json()["items"])
    assert client.get(root, params={**params, "context": "otro"}).json()["total"] == 0
    assert client.get(root, params={**params, "q": "[literal"}).json()["total"] == 0
    assert (
        client.get(root, params={"date_from": "2026-11-25", "date_to": "2026-11-24"}).status_code
        == 422
    )
    assert client.get(root, params={"date_from": "not-a-date"}).status_code == 422
    assert list(service.db.latex_notes.find().sort("_id", 1)) == before

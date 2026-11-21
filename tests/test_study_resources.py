"""Study views/rooms and note provenance on an owned standalone MongoDB."""

from copy import deepcopy
from uuid import uuid4

import pytest
from pymongo.errors import AutoReconnect
from test_knowledge_map_service import create
from test_knowledge_map_service import owned_client as _owned_client
from test_knowledge_map_service import service as _map_service

from mathmongo.knowledge_map.service import digest
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.repository import SourceDocumentRepository

owned_client = _owned_client
service = _map_service

def save_view(api, *, uid=None, **state):
    """Prepare a presentation operation, without hidden resource creation."""
    return {
        "operation_id": str(uuid4()),
        "action": "save_view",
        "map_uid": uid or str(uuid4()),
        "map_name": "Vista temporal",
        "view_state": {"version": 1, **state},
    }


def test_two_views_share_identity_but_keep_independent_membership_and_positions(service):
    """Removing a view reference cannot delete or edit the canonical concept."""
    key = service.execute(create(service))["key"]
    before = service.find(key)
    left = save_view(service, members=[key], points={key: [0.0, 0.0, 1.0]})
    right = save_view(service, members=[key], points={key: [1.0, 0.0, 0.0]})
    a, b = service.execute(left), service.execute(right)
    assert a["status"] == b["status"] == "saved"
    assert service.execute(left) == a
    removed = service.execute(
        {
            **left,
            "operation_id": str(uuid4()),
            "revision": a["view_revision"],
            "view_state": {"version": 1, "members": []},
        }
    )
    assert removed["status"] == "saved"
    views = {v["uid"]: v for v in service.graph()["views"]}
    assert views[left["map_uid"]]["state"]["members"] == []
    assert views[right["map_uid"]]["state"]["members"] == [key]
    assert views[right["map_uid"]]["state"]["points"][key] == [1.0, 0.0, 0.0]
    assert service.find(key) == before
    assert service.mongo.concepts.count_documents({}) == 1


def test_presentation_conflicts_and_lost_ack_do_not_overwrite_foreign_fields(service, monkeypatch):
    """CAS and the operation ledger protect unknown map metadata and replay."""
    payload = save_view(service)
    original = service.db.knowledge_graph_maps.insert_one
    once = True

    def lose_ack(document):
        nonlocal once
        result = original(document)
        if once:
            once = False
            raise AutoReconnect("lost acknowledgement")
        return result

    monkeypatch.setattr(service.db.knowledge_graph_maps, "insert_one", lose_ack)
    # The database attribute creates a fresh Collection object; patch the class
    # method only for this exact namespace, retaining all other insert behavior.
    collection_type = type(service.db.knowledge_graph_maps)
    method = collection_type.insert_one

    def dispatch(collection, document, *args, **kwargs):
        if collection.full_name == service.db.knowledge_graph_maps.full_name:
            return lose_ack(document)
        return method(collection, document, *args, **kwargs)

    monkeypatch.setattr(collection_type, "insert_one", dispatch)
    assert service.execute(payload)["status"] == "uncertain"
    first = service.execute(payload)
    assert first["status"] == "saved"
    service.db.knowledge_graph_maps.update_one(
        {"map_uid": payload["map_uid"]}, {"$set": {"foreign": 7}}
    )
    stale = {**payload, "operation_id": str(uuid4()), "revision": first["view_revision"]}
    assert service.execute(stale)["status"] == "conflict"
    assert service.db.knowledge_graph_maps.find_one({"map_uid": payload["map_uid"]})["foreign"] == 7


@pytest.mark.parametrize(
    "state",
    [
        {"points": {"bad": [0.0, 0.0, 2.0]}},
        {"points": {"bad": [float("nan"), 0.0, 1.0]}},
        {"members": ["same", "same"]},
        {"flatPoints": {"bad": [7.0, 0.0]}},
    ],
)
def test_invalid_geometry_never_writes_a_map(service, state):
    """Out-of-surface/nonfinite state is rejected on the server."""
    assert service.execute(save_view(service, **state))["status"] == "invalid"
    assert service.db.knowledge_graph_maps.count_documents({}) == 0


@pytest.fixture
def reading(service):
    """Initialize reading indexes exclusively inside the owned fixture database."""
    ReadingAnnotationIndexManager(service.db).apply()
    document = SourceDocument(
        source_id=service.test_source_id,
        kind="web",
        title="Paper temporal",
        web=WebDocument(url_raw="https://example.invalid/temporary-paper"),
    )
    SourceDocumentRepository(service.db).insert(document)
    api = ReadingAnnotationService(service.db)
    mark = api.create_annotation(
        document.document_id, kind="highlight", quote_text="Pasaje temporal"
    ).value
    assert mark is not None
    return service, api, document, mark


def test_room_keeps_an_arbitrary_collection_of_view_references(reading):
    """Room placement and sphere coordinates have separate persistent contracts."""
    api, _, document, _ = reading
    views = [save_view(api) for _ in range(3)]
    for payload in views:
        assert api.execute(payload)["status"] == "saved"
    state = {
        "version": 1,
        "name": "Haseman temporal",
        "document_id": document.document_id,
        "spheres": [
            {"view_uid": v["map_uid"], "position": [float(i) / 3, 0.5]} for i, v in enumerate(views)
        ],
    }
    operation = {
        "operation_id": str(uuid4()),
        "action": "save_room",
        "room_uid": str(uuid4()),
        "room_state": state,
    }
    saved = api.execute(operation)
    assert saved["status"] == "saved" and api.execute(operation) == saved
    room = api.graph(include_study=True)["rooms"][0]
    assert {key: room["state"][key] for key in state} == state
    assert len(room["state"]["spheres"]) == 3
    assert api.mongo.concepts.count_documents({}) == 0


def test_annotation_note_and_explicit_concept_retain_canonical_provenance(reading):
    """Writing a note never publishes a concept; explicit incorporation preserves it."""
    api, notes, document, mark = reading
    operation = {
        "operation_id": str(uuid4()),
        "action": "save_note",
        "source_id": document.source_id,
        "document_id": document.document_id,
        "annotation_id": mark.annotation_id,
        "titulo": "Nota de trabajo",
        "contenido_latex": r"Prosa con $\frac12$.",
    }
    result = api.execute(operation)
    assert result["status"] == "saved" and api.execute(operation) == result
    assert api.mongo.concepts.count_documents({}) == 0
    note = notes.get_note(result["note_id"]).value
    before = deepcopy(note.model_dump())
    publish = create(
        api,
        action="publish_note",
        note_id=note.note_id,
        note_revision=digest(note.model_dump()),
        titulo="Concepto de la nota",
        contenido_latex=note.body,
    )
    concept = api.execute(publish)
    assert concept["status"] == "saved" and api.execute(publish) == concept
    assert api.mongo.concepts.count_documents({}) == 1
    assert notes.get_note(note.note_id).value.model_dump() == before
    links = list(api.db.concept_evidence_links.find({}))
    assert len(links) == 2
    assert {link.get("note_id") for link in links} == {note.note_id, None}
    assert {link.get("annotation_id") for link in links} == {mark.annotation_id, None}


def test_stale_note_and_whole_document_race_keep_foreign_body(reading, monkeypatch):
    """Editing from the room uses the same canonical service and atomic CAS."""
    api, notes, document, _ = reading
    note = notes.create_note(
        source_id=document.source_id,
        document_id=document.document_id,
        title="Original",
        body="Original",
    ).value
    loaded = notes.get_note(note.note_id).value
    payload = {
        "operation_id": str(uuid4()),
        "action": "save_note",
        "note_id": note.note_id,
        "revision": digest(loaded.model_dump()),
        "titulo": "Mi título",
        "contenido_latex": "Mi borrador",
    }
    collection = notes.notes._collection
    collection_type = type(collection)
    replace = collection_type.replace_one

    def race(target, query, replacement, *args, **kwargs):
        if target.full_name == collection.full_name:
            target.update_one({"note_id": note.note_id}, {"$set": {"body": "Edición ajena"}})
        return replace(target, query, replacement, *args, **kwargs)

    monkeypatch.setattr(collection_type, "replace_one", race)
    assert api.execute(payload)["status"] == "conflict"
    assert notes.get_note(note.note_id).value.body == "Edición ajena"
    assert notes.get_note(note.note_id).value.title == "Original"

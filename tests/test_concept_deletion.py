"""One deletion contract preserves intellectual evidence and shared resources."""

from dataclasses import replace
from uuid import uuid4

import pytest
from pymongo.errors import AutoReconnect

from mathmongo.concepts.deletion import ConceptDeletionService
from mathmongo.knowledge_map.service import MapConflictError
from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def seeded(service):
    """Build a concept with incoming/outgoing relations and shared media links."""
    first = service.execute(create(service))["key"]
    other = service.execute(create(service, titulo="Otro concepto"))["key"]
    service.execute(
        {"operation_id": str(uuid4()), "action": "connect", "key": first, "target": other}
    )
    service.execute(
        {"operation_id": str(uuid4()), "action": "connect", "key": other, "target": first}
    )
    concept = service.find(first)
    service.db.media_assets.insert_one(
        {
            "asset_id": "shared",
            "concept_ids": [first, other],
            "note_ids": ["note-kept"],
            "path": "kept.png",
        }
    )
    service.db.concepts.update_one({"_id": concept["_id"]}, {"$set": {"image_ids": ["shared"]}})
    return first, other, ConceptDeletionService(service.db)


def test_delete_removes_both_relation_directions_and_retains_shared_source_media_and_notes(service):
    """Verify delete removes both relation directions and retains shared source media and notes."""
    first, other, deletion = seeded(service)
    concept = service.find(first)
    plan = deletion.plan(concept["id"], concept["source"])
    operation = str(uuid4())
    result = deletion.delete(plan, operation)
    assert result.completed
    assert deletion.delete(plan, operation).completed
    assert service.find(first) is None and service.find(other) is not None
    assert service.db.latex_documents.count_documents(plan.identity) == 0
    assert service.db.relations.count_documents({}) == 0
    assert service.db.media_assets.find_one({"asset_id": "shared"})["concept_ids"] == [other]
    assert service.db.media_assets.find_one({"asset_id": "shared"})["note_ids"] == ["note-kept"]
    assert service.db.sources.count_documents({}) == 1


@pytest.mark.parametrize("dependency", ["evidence", "saved_view"])
def test_evidence_or_explicit_view_membership_blocks_without_writes(service, dependency):
    """Verify evidence or explicit view membership blocks without writes."""
    first, _other, deletion = seeded(service)
    concept = service.find(first)
    if dependency == "evidence":
        service.db.concept_evidence_links.insert_one(
            {
                "concept_legacy_id": concept["id"],
                "concept_legacy_source": concept["source"],
                "note_id": "retain",
            }
        )
    else:
        service.db.knowledge_graph_maps.insert_one({"study_view": {"members": [first]}})
    plan = deletion.plan(concept["id"], concept["source"])
    assert plan.blocked
    assert deletion.delete(plan, str(uuid4())).status == "blocked"
    assert service.find(first) == concept
    assert service.db.relations.count_documents({}) == 2
    assert service.operations.count_documents({"kind": "concept_delete"}) == 0


def test_wrong_context_stale_confirmation_and_new_identity_are_not_deleted(service):
    """Verify wrong context stale confirmation and new identity are not deleted."""
    first, _other, deletion = seeded(service)
    concept = service.find(first)
    plan = deletion.plan(concept["id"], concept["source"])
    assert (
        deletion.delete(replace(plan, context="another database"), str(uuid4())).status
        == "conflict"
    )
    service.db.concepts.update_one({"_id": concept["_id"]}, {"$set": {"titulo": "Cambió"}})
    assert deletion.delete(plan, str(uuid4())).status == "conflict"
    plan = deletion.plan(concept["id"], concept["source"])
    operation = str(uuid4())
    assert deletion.delete(plan, operation).completed
    service.db.concepts.insert_one(
        {"id": concept["id"], "source": concept["source"], "titulo": "Recreado explícitamente"}
    )
    assert deletion.delete(plan, operation).status == "conflict"
    assert service.find(first)["titulo"] == "Recreado explícitamente"


def test_partial_delete_retries_only_its_observed_records_and_never_claims_false_success(
    service, monkeypatch
):
    """Verify partial delete retries only its observed records and never claims false success."""
    first, other, deletion = seeded(service)
    concept = service.find(first)
    plan = deletion.plan(concept["id"], concept["source"])
    operation = str(uuid4())
    collection_type = type(service.db.latex_documents)
    original = collection_type.delete_one

    def interrupted(collection, *args, **kwargs):
        if collection.name == "latex_documents":
            raise AutoReconnect("Lost connection")
        return original(collection, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(collection_type, "delete_one", interrupted)
        result = deletion.delete(plan, operation)
    assert result.status == "partial" and not result.completed
    assert service.db.concepts.find_one(plan.identity)["_delete_operation"] == operation
    with pytest.raises(MapConflictError):
        service.find(first)
    assert service.find(other) is not None
    assert deletion.delete(plan, operation).completed
    assert service.find(first) is None
    assert service.db.media_assets.find_one({"asset_id": "shared"})["concept_ids"] == [other]


def test_concurrent_relation_change_is_preserved_for_review(service, monkeypatch):
    """Verify concurrent relation change is preserved for review."""
    first, _other, deletion = seeded(service)
    concept = service.find(first)
    plan = deletion.plan(concept["id"], concept["source"])
    # Change after the fresh preflight, while claiming the concept.
    collection_type = type(service.db.concepts)
    original = collection_type.update_one

    def concurrent(collection, query, update, *args, **kwargs):
        result = original(collection, query, update, *args, **kwargs)
        if collection.name == "concepts" and "_delete_operation" in update.get("$set", {}):
            service.db.relations.update_one(
                {"_id": plan.snapshot["relations"][0]["_id"]},
                {"$set": {"descripcion": "Cambio ajeno"}},
            )
        return result

    monkeypatch.setattr(collection_type, "update_one", concurrent)
    result = deletion.delete(plan, str(uuid4()))
    assert result.status == "partial"
    assert (
        service.db.relations.find_one({"_id": plan.snapshot["relations"][0]["_id"]})["descripcion"]
        == "Cambio ajeno"
    )
    assert service.db.latex_documents.count_documents(plan.identity) == 1


def test_evidence_insert_racing_deletion_is_compensated_without_erasing_the_note(
    service, monkeypatch
):
    """The association writer rechecks the concept after its acknowledged insert."""
    from mathmongo.reading_annotations.service import ReadingAnnotationService
    from mathmongo.reading_space.preparation import ReadingPreparation

    preparation = ReadingPreparation(service.db)
    assert preparation.prepare(preparation.inspect()).ready
    key = service.execute(create(service))["key"]
    concept = service.find(key)
    deletion = ConceptDeletionService(service.db)
    reading = ReadingAnnotationService(service.db)
    note = reading.create_note(
        source_id=service.test_source_id, title="Conservar nota", body="Texto intacto"
    ).value
    original = reading.evidence.insert

    def concurrent(candidate):
        assert deletion.delete(
            deletion.plan(concept["id"], concept["source"]), str(uuid4())
        ).completed
        return original(candidate)

    monkeypatch.setattr(reading.evidence, "insert", concurrent)
    result = reading.create_concept_evidence_link(
        concept_legacy_id=concept["id"],
        concept_legacy_source=concept["source"],
        source_id=service.test_source_id,
        note_id=note.note_id,
        link_type="related_context",
    )
    assert not result.completed
    assert service.db.concept_evidence_links.count_documents({}) == 0
    assert reading.get_note(note.note_id).value.body == "Texto intacto"


def test_relation_insert_racing_deletion_removes_only_its_new_edge(service, monkeypatch):
    """A stale endpoint check cannot reintroduce a dangling relation after deletion."""
    first = service.execute(create(service))["key"]
    other = service.execute(create(service, titulo="Otro"))["key"]
    concept = service.find(first)
    deletion = ConceptDeletionService(service.db)
    collection_type = type(service.db.relations)
    original = collection_type.update_one
    fired = []

    def concurrent(collection, query, update, *args, **kwargs):
        if collection.name == "relations" and "$setOnInsert" in update and not fired:
            fired.append(True)
            assert deletion.delete(
                deletion.plan(concept["id"], concept["source"]), str(uuid4())
            ).completed
        return original(collection, query, update, *args, **kwargs)

    monkeypatch.setattr(collection_type, "update_one", concurrent)
    result = service.execute(
        {"operation_id": str(uuid4()), "action": "connect", "key": first, "target": other}
    )
    assert result["status"] == "conflict"
    assert service.db.relations.count_documents({}) == 0
    assert service.find(other) is not None

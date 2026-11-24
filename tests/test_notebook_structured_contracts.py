"""Characterize real Cornell/CPI storage before implementing their React activities."""

from dataclasses import replace
from importlib import import_module

import pytest

from editor.cornell.models import CornellWatermark
from editor.utils.media_assets import attach_media_assets_to_note
from mathdatabase.mathmongo import MathMongo
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_structured_notes_keep_regions_identity_metadata_and_shared_media(
    service, tmp_path, family
):
    """Canonical create/edit/duplicate/delete retain regions and only detach their own media reference."""
    helpers = import_module("tests.test_" + family + "_service")
    api = import_module("editor." + family + ".service")
    document = replace(
        helpers.sample_document(),
        watermark=CornellWatermark(enabled=True, type="image", image_id="shared-logo"),
    )
    mongo = MathMongo.from_database(service.db)
    create = getattr(api, "create_" + family + "_note")
    get = getattr(api, "get_" + family + "_note")
    update = getattr(api, "update_" + family + "_note")
    duplicate = getattr(api, "duplicate_" + family + "_note")
    delete = getattr(api, "delete_" + family + "_note")
    path = tmp_path / "owned-shared.png"
    path.write_bytes(b"owned resource; these tests never render it")
    service.db.media_assets.insert_one(
        {"asset_id": "shared-logo", "note_ids": [], "absolute_path": str(path)}
    )
    identity = create(mongo, helpers.sample_metadata(), document).inserted_id
    attach_media_assets_to_note(mongo, note_id=str(identity), asset_ids=["shared-logo"])
    before = service.db.latex_notes.find_one({"_id": identity})
    service.db.latex_notes.update_one(
        {"_id": identity}, {"$set": {"unknown": {"preserve": True}, "seed_id": "stable-origin"}}
    )
    assert get(mongo, identity)[family] == document.to_dict()
    metadata = {key: before[key] for key in ("title", "date", "project", "context", "tags")}
    metadata["title"] = "Título actualizado sin aplanar regiones"
    assert update(mongo, identity, metadata, document).matched_count == 1
    current = service.db.latex_notes.find_one({"_id": identity})
    assert current[family] == before[family] and current["latex_body"] == before["latex_body"]
    assert current["unknown"] == {"preserve": True} and current["seed_id"] == "stable-origin"
    copied_id = duplicate(mongo, identity).inserted_id
    copied = service.db.latex_notes.find_one({"_id": copied_id})
    assert copied_id != identity and copied[family] == current[family]
    asset = service.db.media_assets.find_one({"asset_id": "shared-logo"})
    assert set(asset["note_ids"]) == {str(identity), str(copied_id)}
    assert delete(mongo, identity).deleted_count == 1
    assert service.db.latex_notes.find_one({"_id": copied_id})[family] == current[family]
    assert service.db.media_assets.find_one({"asset_id": "shared-logo"})["note_ids"] == [
        str(copied_id)
    ]
    assert path.exists()

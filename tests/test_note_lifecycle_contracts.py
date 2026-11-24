"""Historical canonical copies must retain full stored source and extensions."""

from importlib import import_module

import pytest

from mathdatabase.mathmongo import MathMongo
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_native_duplicate_keeps_exact_historical_source_and_unknown_fields(service, family):
    """Native duplicate keeps exact historical source and unknown fields."""
    helpers = import_module("tests.test_" + family + "_service")
    api = import_module("editor." + family + ".service")
    mongo = MathMongo.from_database(service.db)
    identity = getattr(api, "create_" + family + "_note")(
        mongo, helpers.sample_metadata(), helpers.sample_document()
    ).inserted_id
    raw = r"\begin{concept}{Original} \macroDesconocida{á}\end{concept}"
    service.db.latex_notes.update_one(
        {"_id": identity},
        {
            "$set": {
                "latex_body": raw,
                "unknown": {"preserve": [1, "á"]},
                family + ".custom": {"preserve": True},
            }
        },
    )
    before = service.db.latex_notes.find_one({"_id": identity})
    copied_id = getattr(api, "duplicate_" + family + "_note")(mongo, identity).inserted_id
    copy = service.db.latex_notes.find_one({"_id": copied_id})
    assert copy["latex_body"] == raw
    assert copy["unknown"] == before["unknown"]
    assert copy[family] == before[family]
    assert service.db.latex_notes.find_one({"_id": identity}) == before

"""Real standalone races and no-op preservation for the retained structured services."""

from dataclasses import replace
from importlib import import_module

import pytest
from pymongo.collection import Collection

from editor.structured_note_persistence import StructuredSourceConflictError
from mathdatabase.mathmongo import MathMongo
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def structured(service, family):
    """Create an owned note through the real canonical service."""
    helpers = import_module("tests.test_" + family + "_service")
    api = import_module("editor." + family + ".service")
    mongo = MathMongo.from_database(service.db)
    document = helpers.sample_document()
    metadata = helpers.sample_metadata()
    identity = getattr(api, "create_" + family + "_note")(mongo, metadata, document).inserted_id
    return api, mongo, identity, metadata, document


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_unchanged_structured_save_preserves_raw_source_unknown_fields_and_timestamps(
    service, family
):
    """Opening and saving a historical structure may not materialize defaults or regenerate source."""
    api, mongo, identity, metadata, document = structured(service, family)
    page_region = "main" if family == "cornell" else "production"
    service.db.latex_notes.update_one(
        {"_id": identity},
        {
            "$set": {
                "latex_body": "% fuente histórica conservada\n\\macroDesconocida{α}\n",
                family + ".custom": {"keep": [1, "two"]},
                family + ".pages.0." + page_region + ".custom": "unknown region field",
            }
        },
    )
    before = service.db.latex_notes.find_one({"_id": identity})
    result = getattr(api, "update_" + family + "_note")(mongo, identity, metadata, document)
    assert result.matched_count == 1 and result.modified_count == 0
    assert service.db.latex_notes.find_one({"_id": identity}) == before


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_structured_update_rejects_a_writer_interleaved_after_its_observed_snapshot(
    service, monkeypatch, family
):
    """The revision read and original body belong to one snapshot, even on standalone Mongo."""
    api, mongo, identity, metadata, document = structured(service, family)
    region = "main" if family == "cornell" else "production"
    changed_page = replace(
        document.pages[0],
        **{region: replace(getattr(document.pages[0], region), latex="Escritura tardía")},
    )
    changed = replace(document, pages=(changed_page,))
    before = service.db.latex_notes.find_one({"_id": identity})
    update = Collection.update_one

    def race(collection, query, values, **options):
        if collection.database.name == service.db.name and collection.name == "latex_notes":
            update(collection, {"_id": identity}, {"$set": {"title": "Otra ventana"}})
        return update(collection, query, values, **options)

    monkeypatch.setattr(Collection, "update_one", race)
    result = getattr(api, "update_" + family + "_note")(mongo, identity, metadata, changed)
    assert result.matched_count == 0
    stored = service.db.latex_notes.find_one({"_id": identity})
    assert stored["title"] == "Otra ventana"
    assert stored[family] == before[family] and stored["latex_body"] == before["latex_body"]


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_one_region_edit_keeps_unknown_page_fields_and_unmodified_regions(service, family):
    """A known field edit leaves unknown metadata and the other regions byte-identical."""
    api, mongo, identity, metadata, document = structured(service, family)
    region = "main" if family == "cornell" else "production"
    service.db.latex_notes.update_one(
        {"_id": identity},
        {
            "$set": {
                family + ".custom": {"nested": [1, 2]},
                family + ".pages.0.custom": "page",
                family + ".pages.0." + region + ".custom": "region",
            }
        },
    )
    before = service.db.latex_notes.find_one({"_id": identity})
    page = replace(
        document.pages[0],
        **{region: replace(getattr(document.pages[0], region), latex="Cambio $x$ con \\macro{α}")},
    )
    assert (
        getattr(api, "update_" + family + "_note")(
            mongo, identity, metadata, replace(document, pages=(page,))
        ).matched_count
        == 1
    )
    stored = service.db.latex_notes.find_one({"_id": identity})
    assert stored[family]["custom"] == before[family]["custom"]
    assert stored[family]["pages"][0]["custom"] == "page"
    assert stored[family]["pages"][0][region]["custom"] == "region"
    for other in ("cue", "summary") if family == "cornell" else ("comprehension", "integration"):
        assert stored[family]["pages"][0][other] == before[family]["pages"][0][other]
    assert "\\macro{α}" in stored["latex_body"]


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_metadata_only_edit_preserves_a_divergent_historical_projection(service, family):
    """Metadata may change without regenerating a legacy source unrelated to the projection."""
    api, mongo, identity, metadata, document = structured(service, family)
    body = "% preserve all original source\n\\custom{\u03b1}\n"
    service.db.latex_notes.update_one({"_id": identity}, {"$set": {"latex_body": body}})
    result = getattr(api, "update_" + family + "_note")(
        mongo, identity, {**metadata, "title": "Otro título"}, document
    )
    assert result.modified_count == 1
    stored = service.db.latex_notes.find_one({"_id": identity})
    assert stored["title"] == "Otro título" and stored["latex_body"] == body
    region = "main" if family == "cornell" else "production"
    changed = replace(
        document,
        pages=(
            replace(
                document.pages[0],
                **{region: replace(getattr(document.pages[0], region), latex="No sobrescribir")},
            ),
        ),
    )
    with pytest.raises(StructuredSourceConflictError):
        getattr(api, "update_" + family + "_note")(mongo, identity, metadata, changed)
    assert service.db.latex_notes.find_one({"_id": identity}) == stored


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_explicit_snapshot_has_no_second_read_and_rejects_identity_substitution(
    service, monkeypatch, family
):
    """HTTP adapters can pass their one observed note to the same canonical writer."""
    api, mongo, identity, metadata, document = structured(service, family)
    original = mongo.get_notebook_note_by_id(identity)

    def unexpected(*_args):
        pytest.fail("A second revision/body read would create a different snapshot")

    monkeypatch.setattr(mongo, "get_notebook_note_by_id", unexpected)
    assert (
        getattr(api, "update_" + family + "_note")(
            mongo,
            identity,
            {**metadata, "title": "Confirmado"},
            document,
            expected_snapshot=original,
        ).matched_count
        == 1
    )
    with pytest.raises(ValueError, match="identity"):
        getattr(api, "update_" + family + "_note")(
            mongo, "other-id", metadata, document, expected_snapshot=original
        )
    assert service.db.latex_notes.find_one({"_id": identity})["title"] == "Confirmado"


def test_cpi_page_origins_preserve_unknown_fields_when_reordering(service):
    """Page numbers can change order without moving unknown metadata to another page."""
    api, mongo, identity, metadata, document = structured(service, "cpi")
    second = replace(
        document.pages[0],
        page_number=2,
        production=replace(document.pages[0].production, latex="Página dos"),
    )
    both = replace(document, pages=(*document.pages, second))
    api.update_cpi_note(mongo, identity, metadata, both)
    service.db.latex_notes.update_one(
        {"_id": identity}, {"$set": {"cpi.pages.0.custom": "first", "cpi.pages.1.custom": "second"}}
    )
    reversed_document = replace(
        both, pages=(replace(second, page_number=1), replace(document.pages[0], page_number=2))
    )
    api.update_cpi_note(mongo, identity, metadata, reversed_document, page_origins=[2, 1])
    stored = service.db.latex_notes.find_one({"_id": identity})
    assert [page["custom"] for page in stored["cpi"]["pages"]] == ["second", "first"]
    for origins in ([1], [99, 1]):
        with pytest.raises(ValueError, match="origin"):
            api.update_cpi_note(mongo, identity, metadata, both, page_origins=origins)
        assert service.db.latex_notes.find_one({"_id": identity}) == stored

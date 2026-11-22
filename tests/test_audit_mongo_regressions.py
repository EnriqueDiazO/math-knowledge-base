"""Opt-in standalone MongoDB proof for duplicate insertion and shared images."""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.utils import media_assets
from exporters_latex.exportar_qmd_desde_mongo import main as export_qmd
from scripts.export_knowledge_graph import main as export_graph

pytestmark = pytest.mark.skipif(os.environ.get("MATHMONGO_RUN_MONGO_E2E") != "1",
                                reason="requires the owned mongod in scripts/quality_mongo.py")


@pytest.fixture
def database():
    """Create and drop only a fresh explicitly named audit database."""
    uri = os.environ["MONGODB_URI"]
    name = "mathmongo_audit_" + uuid4().hex
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    client.admin.command("ping")
    assert name not in client.list_database_names()
    print("temporary_database=" + name)
    db = client[name]
    try:
        db.concepts.create_index([("id", 1), ("source", 1)], unique=True)
        db.latex_documents.create_index([("id", 1), ("source", 1)], unique=True)
        yield db
    finally:
        client.drop_database(name)
        assert name not in client.list_database_names()
        client.close()


def test_real_duplicate_preserves_every_field_of_the_original(database):
    """A duplicate rejection must preserve metadata, content, identity and dates."""
    now = datetime(2026, 11, 21)
    insert_concept_with_latex_atomic(database, "def:one", "book",
                                     {"titulo": "Original", "tags": ["a", "b"],
                                      "custom": {"preserve": 42}}, "x^2=1", now)
    before = database.concepts.find_one({"id": "def:one"})
    latex_before = database.latex_documents.find_one({"id": "def:one"})
    with pytest.raises(DuplicateKeyError):
        insert_concept_with_latex_atomic(database, "def:one", "book", {"titulo": "Replacement"}, "x=0", now)
    assert database.concepts.find_one({"id": "def:one"}) == before
    assert database.latex_documents.find_one({"id": "def:one"}) == latex_before


def test_real_second_write_failure_compensates_only_new_metadata(database):
    """A pre-existing LaTeX conflict rolls back the new metadata only."""
    database.concepts.insert_one({"id": "keep", "source": "book", "custom": [1, 2]})
    preserved = database.concepts.find_one({"id": "keep"})
    database.latex_documents.insert_one({"id": "new", "source": "book", "contenido_latex": "old"})
    latex_before = list(database.latex_documents.find())
    with pytest.raises(DuplicateKeyError):
        insert_concept_with_latex_atomic(database, "new", "book", {"titulo": "New"}, "new", datetime(2026, 11, 21))
    assert list(database.concepts.find()) == [preserved]
    assert list(database.latex_documents.find()) == latex_before


def test_real_rollback_does_not_delete_a_concurrently_replaced_record(database):
    """Compensation must identify the inserted storage record, not just its identity."""
    def replace_and_fail(_document):
        database.concepts.delete_one({"id": "new", "source": "book"})
        database.concepts.insert_one({"id": "new", "source": "book", "titulo": "other writer"})
        raise OSError("second write failed")

    wrapped = SimpleNamespace(concepts=database.concepts,
                              latex_documents=SimpleNamespace(insert_one=replace_and_fail))
    with pytest.raises(OSError, match="second write"):
        insert_concept_with_latex_atomic(wrapped, "new", "book", {}, "x", datetime(2026, 11, 21))
    assert database.concepts.find_one({"id": "new"})["titulo"] == "other writer"


@pytest.mark.parametrize("second_kind", ["concept", "note"])
def test_real_shared_image_survives_until_its_last_reference(database, tmp_path, monkeypatch, second_kind):
    """Check both concept and notebook owners with deliberately stale reverse lists."""
    image = tmp_path / "data/media/images/shared.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    monkeypatch.setattr(media_assets, "DATA_DIR", tmp_path / "data")
    database.media_assets.insert_one({"asset_id": "asset", "path": "media/images/shared.png",
                                     "concept_ids": [], "note_ids": []})
    database.concepts.insert_one({"id": "one", "source": "book", "image_ids": ["asset"]})
    if second_kind == "concept":
        database.concepts.insert_one({"id": "two", "source": "book", "image_ids": ["asset"]})
    else:
        database.latex_notes.insert_one({"_id": "two", "image_ids": ["asset"]})
    assert not media_assets.detach_media_asset_from_concept(database, asset_id="asset", concept_id="one", source="book", delete_if_unreferenced=True)
    assert image.read_bytes() == b"image"
    assert database.media_assets.find_one({"asset_id": "asset"}) is not None
    if second_kind == "concept":
        deleted = media_assets.detach_media_asset_from_concept(database, asset_id="asset", concept_id="two", source="book", delete_if_unreferenced=True)
    else:
        deleted = media_assets.detach_media_asset_from_note(database, asset_id="asset", note_id="two", delete_if_unreferenced=True)
    assert deleted
    assert not image.exists()
    assert database.media_assets.find_one({"asset_id": "asset"}) is None


def test_real_export_commands_read_the_selected_database_without_writing(database, tmp_path):
    """Restore broken make targets using the actual split metadata/content format."""
    database.concepts.insert_one({"id": "def:one", "source": "Book", "tipo": ["definicion"], "titulo": "Only mine"})
    database.latex_documents.insert_one({"id": "def:one", "source": "Book", "contenido_latex": r"\frac{1}{2}"})
    collections_before = set(database.list_collection_names())
    before = {name: list(database[name].find()) for name in collections_before}
    uri = os.environ["MONGODB_URI"]
    assert export_qmd(["--mongo-uri", uri, "--db", database.name, "--output", str(tmp_path / "qmd")]) == 0
    qmds = list((tmp_path / "qmd").rglob("*.qmd"))
    assert len(qmds) == 1
    assert r"\frac{1}{2}" in qmds[0].read_text()
    output = tmp_path / "graph.html"
    assert export_graph(["--mongo-uri", uri, "--database", database.name, "--output", str(output)]) == 0
    assert "Only mine" in output.read_text()
    assert set(database.list_collection_names()) == collections_before
    assert {name: list(database[name].find()) for name in collections_before} == before

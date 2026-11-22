"""Observable regressions for the November audit's data-loss findings."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.utils import media_assets


class Collection:
    """Small stateful collection with equality/array membership and unique identity."""

    def __init__(self, documents=(), *, insert_error=None):
        """Start from private copies and optionally inject a first-write failure."""
        self.documents = deepcopy(list(documents))
        self.insert_error = insert_error

    @staticmethod
    def matches(document, query):
        """Match the equality and array-membership queries used by media deletion."""
        return all(value in document.get(key, []) if isinstance(document.get(key), list)
                   else document.get(key) == value for key, value in query.items())

    def find_one(self, query, _projection=None):
        """Return one stored record without mutating it."""
        return next((doc for doc in self.documents if self.matches(doc, query)), None)

    def insert_one(self, document):
        """Reject duplicates before making any persistent change."""
        if self.insert_error:
            raise self.insert_error
        identity = {key: document[key] for key in ("id", "source")}
        if self.find_one(identity) is not None:
            raise DuplicateKeyError("duplicate identity")
        self.documents.append(deepcopy(document))

    def update_one(self, query, changes):
        """Apply the $pull/$set operations used when detaching an asset."""
        document = self.find_one(query)
        if document is not None:
            for key, value in changes.get("$pull", {}).items():
                document[key] = [item for item in document.get(key, []) if item != value]
            document.update(changes.get("$set", {}))

    def delete_one(self, query):
        """Remove only the matching document, returning Mongo's deletion count."""
        document = self.find_one(query)
        if document is None:
            return SimpleNamespace(deleted_count=0)
        self.documents.remove(document)
        return SimpleNamespace(deleted_count=1)


def insert(database):
    """Exercise the public persistence helper with a stable concept identity."""
    insert_concept_with_latex_atomic(database, "def:one", "book", {"titulo": "new"},
                                     "x=1", datetime(2026, 11, 21))


def test_duplicate_insert_does_not_erase_the_existing_concept():
    """A rejected duplicate must leave both existing records intact."""
    existing = {"id": "def:one", "source": "book", "titulo": "original"}
    database = SimpleNamespace(concepts=Collection([existing]), latex_documents=Collection())
    with pytest.raises(DuplicateKeyError):
        insert(database)
    assert database.concepts.documents == [existing]
    assert database.latex_documents.documents == []


def test_failed_metadata_insert_never_rolls_back_an_existing_record():
    """Even an uncertain first write failure must not delete another record."""
    existing = {"id": "def:one", "source": "book", "titulo": "original"}
    database = SimpleNamespace(concepts=Collection([existing], insert_error=OSError("offline")),
                               latex_documents=Collection())
    with pytest.raises(OSError, match="offline"):
        insert(database)
    assert database.concepts.documents == [existing]


def test_failed_latex_insert_rolls_back_only_the_new_metadata():
    """Retain the documented compensation after a successful first insert."""
    database = SimpleNamespace(concepts=Collection(),
                               latex_documents=Collection(insert_error=OSError("latex offline")))
    with pytest.raises(OSError, match="latex offline"):
        insert(database)
    assert database.concepts.documents == []


@pytest.mark.parametrize("owner", ["concept", "note"])
@pytest.mark.parametrize("other_owner", ["concept", "note", None])
def test_detach_preserves_assets_still_referenced_by_real_documents(tmp_path, monkeypatch, owner, other_owner):
    """Stale reverse lists must not cause a shared image to be deleted."""
    data = tmp_path / "data"
    image = data / "media/images/shared.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    monkeypatch.setattr(media_assets, "DATA_DIR", data)
    collections = {
        "concepts": Collection([{"id": "mine", "source": "book", "image_ids": ["asset"]}]),
        "latex_notes": Collection([{"_id": "mine", "image_ids": ["asset"]}]),
        "media_assets": Collection([{"asset_id": "asset", "path": "media/images/shared.png",
                                     "concept_ids": [], "note_ids": []}]),
    }
    # Only one of the owner records exists in each scenario.
    collections["latex_notes" if owner == "concept" else "concepts"].documents.clear()
    if other_owner:
        target = collections["concepts" if other_owner == "concept" else "latex_notes"]
        target.documents.append({"id": "other", "_id": "other", "image_ids": ["asset"]})
    database = collections
    if owner == "concept":
        deleted = media_assets.detach_media_asset_from_concept(
            database, asset_id="asset", concept_id="mine", source="book", delete_if_unreferenced=True)
    else:
        deleted = media_assets.detach_media_asset_from_note(
            database, asset_id="asset", note_id="mine", delete_if_unreferenced=True)
    assert deleted is (other_owner is None)
    assert image.exists() is (other_owner is not None)
    assert bool(collections["media_assets"].documents) is (other_owner is not None)

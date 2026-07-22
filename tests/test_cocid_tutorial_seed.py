"""Tests for the reproducible COCID Drive/Docs tutorial seed."""

# ruff: noqa: D102,D103,D105,D107

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PIL import Image

from scripts.build_cocid_drive_docs_tutorial_assets import ASSET_SPECS
from scripts.build_cocid_drive_docs_tutorial_assets import build_assets
from scripts.seed_cocid_drive_docs_tutorial import CORNELL_SEED_ID
from scripts.seed_cocid_drive_docs_tutorial import CPI_SEED_ID
from scripts.seed_cocid_drive_docs_tutorial import build_cornell_tutorial_document
from scripts.seed_cocid_drive_docs_tutorial import build_cpi_tutorial_document
from scripts.seed_cocid_drive_docs_tutorial import seed_tutorial


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        actual = document.get(key)
        if isinstance(expected, dict) and "$in" in expected:
            if actual not in expected["$in"]:
                return False
        elif actual != expected:
            return False
    return True


class FakeCollection:
    """Minimal Mongo collection double used only by the seed unit tests."""

    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        return [deepcopy(doc) for doc in self.documents if _matches(doc, query)]

    def find_one(self, query: dict[str, Any], *_args: Any) -> dict[str, Any] | None:
        return next((deepcopy(doc) for doc in self.documents if _matches(doc, query)), None)

    def count_documents(self, query: dict[str, Any]) -> int:
        return sum(_matches(doc, query) for doc in self.documents)

    def insert_one(self, document: dict[str, Any]) -> SimpleNamespace:
        value = deepcopy(document)
        value.setdefault("_id", f"note-{len(self.documents) + 1}")
        self.documents.append(value)
        return SimpleNamespace(inserted_id=value["_id"])

    def replace_one(self, query: dict[str, Any], replacement: dict[str, Any]) -> SimpleNamespace:
        for index, document in enumerate(self.documents):
            if _matches(document, query):
                self.documents[index] = deepcopy(replacement)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> SimpleNamespace:
        for document in self.documents:
            if not _matches(document, query):
                continue
            for key, value in update.get("$set", {}).items():
                document[key] = value
            for key, value in update.get("$addToSet", {}).items():
                values = document.setdefault(key, [])
                if value not in values:
                    values.append(value)
            for key, value in update.get("$pull", {}).items():
                document[key] = [item for item in document.get(key, []) if item != value]
            return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class FakeDatabase:
    """Selected database double exposing the two collections in seed scope."""

    name = "temporary_seed_test"

    def __init__(self) -> None:
        self.collections = {
            "latex_notes": FakeCollection(),
            "media_assets": FakeCollection(),
        }

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections[name]


def _build_inputs(tmp_path: Path) -> tuple[Path, Path]:
    assets_dir = tmp_path / "assets"
    build_assets(assets_dir)
    logo_path = tmp_path / "cocid logo.png"
    Image.new("RGBA", (80, 80), (20, 80, 140, 180)).save(logo_path)
    return assets_dir, logo_path


def test_asset_generator_creates_six_readable_1600_by_900_pngs(tmp_path: Path) -> None:
    manifest = build_assets(tmp_path / "generated")

    assert set(manifest["assets"]) == set(ASSET_SPECS)
    for filename, spec in manifest["assets"].items():
        with Image.open(tmp_path / "generated" / filename) as image:
            assert image.size == (1600, 900)
            assert image.format == "PNG"
        assert spec["caption"]
        assert spec["alt_text"]


def test_tutorial_documents_contain_captions_and_cocid_branding() -> None:
    ids = {name: f"asset-{index}" for index, name in enumerate(ASSET_SPECS, start=1)}

    cornell = build_cornell_tutorial_document(ids, "cocid-logo")
    cpi = build_cpi_tutorial_document(ids, "cocid-logo")

    assert len(cornell.pages) == 2
    assert len(cpi.pages) == 1
    assert cornell.watermark.to_dict() == cpi.watermark.to_dict()
    assert cornell.watermark.image_id == "cocid-logo"
    assert cornell.watermark.opacity == 0.07
    assert cornell.watermark.scale == 0.70
    assert cornell.watermark.all_pages is True
    all_latex = " ".join(
        region.latex
        for page in cornell.pages
        for region in (page.cue, page.main, page.summary)
    ) + " " + " ".join(
        region.latex
        for page in cpi.pages
        for region in (page.comprehension, page.production, page.integration)
    )
    assert all(spec["caption"] in all_latex for spec in ASSET_SPECS.values())


def test_seed_is_idempotent_and_backup_precedes_all_writes(tmp_path: Path) -> None:
    assets_dir, logo_path = _build_inputs(tmp_path)
    db = FakeDatabase()
    events: list[str] = []

    def backup_creator(_db: Any, _output_dir: Path | None = None) -> Path:
        events.append("backup")
        return tmp_path / "focal.zip"

    def asset_importer(
        database: FakeDatabase,
        path: Path,
        *,
        tags: list[str],
        description: str,
    ) -> dict[str, Any]:
        events.append(f"asset:{path.name}")
        asset_id = f"logical-{path.stem}"
        existing = database["media_assets"].find_one({"asset_id": asset_id})
        if existing is not None:
            return existing
        document = {
            "asset_id": asset_id,
            "filename": path.name,
            "path": f"media/images/{path.name}",
            "note_ids": [],
            "tags": tags,
            "description": description,
        }
        database["media_assets"].documents.append(document)
        return document

    first = seed_tutorial(
        db,
        assets_dir=assets_dir,
        logo_path=logo_path,
        backup_dir=tmp_path,
        asset_importer=asset_importer,
        backup_creator=backup_creator,
    )
    second = seed_tutorial(
        db,
        assets_dir=assets_dir,
        logo_path=logo_path,
        backup_dir=tmp_path,
        asset_importer=asset_importer,
        backup_creator=backup_creator,
    )

    assert events[0] == "backup"
    assert events[8] == "backup"
    assert db["latex_notes"].count_documents({}) == 2
    assert db["media_assets"].count_documents({}) == 7
    assert first["notes"][CORNELL_SEED_ID]["action"] == "created"
    assert first["notes"][CPI_SEED_ID]["action"] == "created"
    assert second["notes"][CORNELL_SEED_ID]["action"] == "updated"
    assert second["notes"][CPI_SEED_ID]["action"] == "updated"


def test_seed_does_not_overwrite_foreign_note_with_same_title(tmp_path: Path) -> None:
    assets_dir, logo_path = _build_inputs(tmp_path)
    db = FakeDatabase()
    foreign = {
        "_id": "foreign",
        "title": "Tutorial breve: Google Drive y Google Docs",
        "latex_body": "contenido ajeno",
    }
    db["latex_notes"].documents.append(deepcopy(foreign))

    def importer(database: FakeDatabase, path: Path, **_kwargs: Any) -> dict[str, Any]:
        asset = {"asset_id": path.stem, "note_ids": []}
        if database["media_assets"].find_one({"asset_id": path.stem}) is None:
            database["media_assets"].documents.append(asset)
        return asset

    seed_tutorial(
        db,
        assets_dir=assets_dir,
        logo_path=logo_path,
        backup_dir=tmp_path,
        asset_importer=importer,
        backup_creator=lambda *_args: tmp_path / "focal.zip",
    )

    assert db["latex_notes"].find_one({"_id": "foreign"}) == foreign
    assert db["latex_notes"].count_documents({}) == 3
    assert db["latex_notes"].find_one({"seed_id": CORNELL_SEED_ID}) is not None
    assert db["latex_notes"].find_one({"seed_id": CPI_SEED_ID}) is not None

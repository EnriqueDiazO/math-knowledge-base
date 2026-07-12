"""Tests for XDG-first media storage with historical read fallback."""

# ruff: noqa: D103

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from editor.cornell import media as cornell_media
from editor.cpi import media as cpi_media
from editor.utils import db_export
from editor.utils import db_import
from editor.utils import media_assets


def test_media_resolves_xdg_first_then_legacy(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "xdg-data/mathmongo"
    legacy = tmp_path / "legacy"
    relative = Path("media/images/shared.png")
    legacy_file = legacy / relative
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_bytes(b"legacy")
    monkeypatch.setattr(media_assets, "DATA_DIR", data)
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", legacy)

    asset = {"path": relative.as_posix()}
    assert media_assets.resolve_media_asset_path(asset) == legacy_file

    current = data / relative
    current.parent.mkdir(parents=True)
    current.write_bytes(b"current")
    assert media_assets.resolve_media_asset_path(asset) == current


def test_absolute_historical_media_resolves_xdg_then_legacy_then_original(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "xdg-data/mathmongo"
    legacy = tmp_path / "legacy"
    old_checkout = tmp_path / "old-checkout"
    relative = Path("media/images/shared.png")
    original = old_checkout / relative
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    legacy_file = legacy / relative
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_bytes(b"legacy")
    current = data / relative
    current.parent.mkdir(parents=True)
    current.write_bytes(b"current")
    monkeypatch.setattr(media_assets, "DATA_DIR", data)
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", legacy)

    asset = {"path": str(original)}
    assert media_assets.resolve_media_asset_path(asset) == current

    current.unlink()
    assert media_assets.resolve_media_asset_path(asset) == legacy_file

    legacy_file.unlink()
    assert media_assets.resolve_media_asset_path(asset) == original


def test_absolute_media_outside_known_roots_remains_readable(tmp_path: Path, monkeypatch) -> None:
    absolute = tmp_path / "historical-assets/logo.png"
    absolute.parent.mkdir()
    absolute.write_bytes(b"historical")
    monkeypatch.setattr(media_assets, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", tmp_path / "legacy")

    assert media_assets.resolve_media_asset_path({"path": str(absolute)}) == absolute
    assert media_assets.media_path_exists({"path": str(absolute)})


@pytest.mark.parametrize(
    "renderer",
    (
        media_assets.latex_includegraphics_snippet,
        media_assets.html_image_snippet,
        media_assets.markdown_image_snippet,
    ),
)
def test_media_snippets_use_logical_path_for_absolute_historical_assets(
    tmp_path: Path,
    monkeypatch,
    renderer,
) -> None:
    data = tmp_path / "xdg-data/mathmongo"
    legacy = tmp_path / "legacy"
    historical = tmp_path / "old checkout/media/images/diagrama.png"
    unknown = tmp_path / "unclassified/diagrama.png"
    monkeypatch.setattr(media_assets, "DATA_DIR", data)
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", legacy)

    rendered = renderer({"path": str(historical), "filename": historical.name})
    assert "media/images/diagrama.png" in rendered
    assert str(tmp_path).lstrip("/") not in rendered

    fallback = renderer({"path": str(unknown), "filename": unknown.name})
    assert media_assets.relative_media_path(unknown) in fallback


def test_copy_media_tree_does_not_follow_a_source_root_symlink(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    outside_media = tmp_path / "outside-media"
    (outside_media / "images").mkdir(parents=True)
    (outside_media / "images/user-secret.png").write_bytes(b"must not copy")
    (legacy / "media").symlink_to(outside_media, target_is_directory=True)
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", legacy)
    monkeypatch.setattr(media_assets, "LOCAL_MEDIA_ROOT", tmp_path / "missing-xdg-media")

    destination = tmp_path / "latex-build"
    media_assets.copy_media_tree_for_latex(destination)

    assert not (destination / "media").exists()
    assert (outside_media / "images/user-secret.png").read_bytes() == b"must not copy"


def test_copy_media_tree_rejects_a_symlinked_destination(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "xdg-media"
    (source / "images").mkdir(parents=True)
    (source / "images/image.png").write_bytes(b"image")
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(media_assets, "LOCAL_MEDIA_ROOT", source)
    build = tmp_path / "build"
    build.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (build / "media").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="Symbolic links"):
        media_assets.copy_media_tree_for_latex(build)

    assert list(outside.iterdir()) == []


def test_cornell_and_cpi_absolute_assets_use_xdg_first(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    legacy = tmp_path / "legacy"
    relative = Path("media/images/logo.png")
    historical = legacy / relative
    historical.parent.mkdir(parents=True)
    historical.write_bytes(b"legacy")
    current = data / relative
    current.parent.mkdir(parents=True)
    current.write_bytes(b"current")
    monkeypatch.setattr(media_assets, "DATA_DIR", data)
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", legacy)
    monkeypatch.setattr(cornell_media, "PROJECT_ROOT", legacy)
    asset = {"asset_id": "logo", "filename": "logo.png", "path": str(historical)}

    assert cornell_media._safe_asset_source_path(asset) == current
    assert cpi_media._safe_asset_source_path(
        asset,
        allowed_extensions=cpi_media.CPI_LATEX_IMAGE_EXTENSIONS,
    ) == current

    current.unlink()
    assert cornell_media._safe_asset_source_path(asset) == historical
    assert cpi_media._safe_asset_source_path(
        asset,
        allowed_extensions=cpi_media.CPI_LATEX_IMAGE_EXTENSIONS,
    ) == historical


def test_deleting_media_never_deletes_legacy_fallback(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    legacy = tmp_path / "legacy"
    relative = Path("media/images/history.png")
    historical = legacy / relative
    historical.parent.mkdir(parents=True)
    historical.write_bytes(b"keep")
    monkeypatch.setattr(media_assets, "DATA_DIR", data)
    monkeypatch.setattr(media_assets, "LEGACY_PROJECT_ROOT", legacy)

    media_assets._delete_local_asset_file({"path": relative.as_posix()})

    assert historical.read_bytes() == b"keep"


def test_new_media_destination_is_only_under_xdg(tmp_path: Path, monkeypatch) -> None:
    images = tmp_path / "data/mathmongo/media/images"
    monkeypatch.setattr(media_assets, "LOCAL_MEDIA_IMAGES_DIR", images)
    destination = media_assets._unique_destination("new.png")
    destination.write_bytes(b"new")
    assert destination == images / "new.png"
    assert destination.is_file()


class _ExportCursor(list):
    def max_time_ms(self, milliseconds: int):
        return self


class _ExportCollection:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents

    def find(self, query: dict) -> _ExportCursor:
        return _ExportCursor(self.documents)


class _ExportDatabase:
    name = "fake-audit-db"

    def __init__(self, documents: dict[str, list[dict]]) -> None:
        self.documents = documents

    def list_collection_names(self) -> list[str]:
        return list(self.documents)

    def __getitem__(self, name: str) -> _ExportCollection:
        return _ExportCollection(self.documents.get(name, []))


class _FixedExportDatetime:
    @classmethod
    def utcnow(cls) -> datetime:
        return datetime(2026, 7, 11, 12, 34, 56)


@pytest.mark.parametrize(
    "symlink_location",
    ("export_dir", "collections_dir", "media_dir", "zip_path"),
)
def test_database_export_rejects_symlinked_staging_destinations(
    tmp_path: Path,
    monkeypatch,
    symlink_location: str,
) -> None:
    out_dir = tmp_path / "backups"
    out_dir.mkdir()
    base_name = "mathkb_export_20260711_123456"
    export_dir = out_dir / base_name
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    outside_file = tmp_path / "outside.zip"
    outside_file.write_bytes(b"must survive")

    if symlink_location == "export_dir":
        export_dir.symlink_to(outside_dir, target_is_directory=True)
    elif symlink_location == "zip_path":
        (out_dir / f"{base_name}.zip").symlink_to(outside_file)
    else:
        export_dir.mkdir()
        if symlink_location == "collections_dir":
            (export_dir / "collections").symlink_to(outside_dir, target_is_directory=True)
        elif symlink_location == "media_dir":
            (export_dir / "media").symlink_to(outside_dir, target_is_directory=True)

    monkeypatch.setattr(db_export, "datetime", _FixedExportDatetime)
    monkeypatch.setattr(db_export, "EXPORT_COLLECTIONS", ())
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", tmp_path / "missing-xdg-media")
    mongo = type("FakeMongo", (), {"db": _ExportDatabase({})})()

    with pytest.raises((FileExistsError, ValueError)):
        db_export.export_database_to_zip(mongo, out_dir)

    assert outside_file.read_bytes() == b"must survive"
    assert list(outside_dir.iterdir()) == []


def test_database_export_merges_legacy_then_xdg_without_real_mongo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy = tmp_path / "legacy"
    current = tmp_path / "xdg-data/mathmongo/media"
    for root, shared_bytes in ((legacy / "media", b"legacy"), (current, b"xdg")):
        (root / "images").mkdir(parents=True)
        (root / "images/shared.png").write_bytes(shared_bytes)
    (legacy / "media/images/legacy-only.png").write_bytes(b"legacy-only")
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", legacy)
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", current)
    monkeypatch.setattr(db_export, "EXPORT_COLLECTIONS", ("media_assets",))
    mongo = type(
        "FakeMongo",
        (),
        {"db": _ExportDatabase({"media_assets": [{"path": "media/images/shared.png"}]})},
    )()

    archive_path = db_export.export_database_to_zip(mongo, tmp_path / "backups")

    with zipfile.ZipFile(archive_path) as archive:
        shared_name = next(name for name in archive.namelist() if name.endswith("media/images/shared.png"))
        legacy_name = next(
            name for name in archive.namelist() if name.endswith("media/images/legacy-only.png")
        )
        assert archive.read(shared_name) == b"xdg"
        assert archive.read(legacy_name) == b"legacy-only"


class _ImportCollection:
    def __init__(self) -> None:
        self.documents: list[dict] = []

    def replace_one(self, query: dict, document: dict, upsert: bool) -> None:
        self.documents.append(document)

    def insert_one(self, document: dict) -> None:
        self.documents.append(document)


class _ImportDatabase:
    name = "fake-import-db"

    def __init__(self) -> None:
        self.collections: dict[str, _ImportCollection] = {}

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> None:
        self.collections.setdefault(name, _ImportCollection())

    def __getitem__(self, name: str) -> _ImportCollection:
        return self.collections.setdefault(name, _ImportCollection())


def test_database_import_writes_media_only_to_xdg_and_remaps_conflicts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data = tmp_path / "xdg-data/mathmongo"
    existing = data / "media/images/shared.png"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"existing")
    archive_path = tmp_path / "export.zip"
    base = "mathkb_export_audit"
    media_document = {"_id": "asset-1", "path": "media/images/shared.png", "filename": "shared.png"}
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(f"{base}/metadata.json", json.dumps({"collections": {"media_assets": 1}}))
        archive.writestr(f"{base}/collections/media_assets.json", json.dumps([media_document]))
        archive.writestr(f"{base}/media/images/shared.png", b"imported")
    monkeypatch.setattr(db_import, "DATA_DIR", data)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("media_assets",))
    database = _ImportDatabase()
    mongo = type("FakeMongo", (), {"db": database})()

    db_import.import_zip_into_database(archive_path, mongo)

    restored = sorted((data / "media/images").glob("shared_imported_*.png"))
    assert len(restored) == 1
    assert restored[0].read_bytes() == b"imported"
    assert existing.read_bytes() == b"existing"
    imported_document = database["media_assets"].documents[0]
    assert imported_document["path"] == restored[0].relative_to(data).as_posix()
    assert imported_document["filename"] == restored[0].name

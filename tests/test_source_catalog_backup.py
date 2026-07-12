"""Isolated export/import coverage for optional Source Catalog collections."""

# ruff: noqa: D103

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from editor.utils import db_export
from editor.utils import db_import
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source


class _Cursor(list):
    def max_time_ms(self, _milliseconds: int):
        return self


class _Collection:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self.documents = list(documents or [])

    def find(self, _query: dict) -> _Cursor:
        return _Cursor(self.documents)

    def find_one(self, query: dict):
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in query.items())
            ),
            None,
        )

    def insert_one(self, document: dict) -> None:
        self.documents.append(document)

    def replace_one(self, query: dict, document: dict, upsert: bool) -> None:
        existing = self.find_one(query)
        if existing is None:
            if upsert:
                self.documents.append(document)
            return
        self.documents[self.documents.index(existing)] = document


class _Database:
    name = "isolated-source-catalog-test"

    def __init__(self, documents: dict[str, list[dict]] | None = None) -> None:
        self.collections = {
            name: _Collection(items) for name, items in (documents or {}).items()
        }

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> None:
        self.collections.setdefault(name, _Collection())

    def __getitem__(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


def _mongo(database: _Database):
    return type("FakeMongo", (), {"db": database})()


def _write_archive(path: Path, collections: dict[str, list[dict]]) -> None:
    base = "mathkb_export_test"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{base}/metadata.json",
            json.dumps({"collections": {name: len(docs) for name, docs in collections.items()}}),
        )
        for name, documents in collections.items():
            archive.writestr(
                f"{base}/collections/{name}.json",
                json.dumps(documents),
            )


def _configure_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(db_export, "EXPORT_COLLECTIONS", ("concepts", "sources", "references"))
    monkeypatch.setattr(db_export, "SOURCE_CATALOG_COLLECTIONS", ("sources", "references"))
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", tmp_path / "missing-media")


def test_export_includes_catalog_collections_only_when_they_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_export(monkeypatch, tmp_path)

    absent_archive = db_export.export_database_to_zip(
        _mongo(_Database({"concepts": []})),
        tmp_path / "absent",
    )
    with zipfile.ZipFile(absent_archive) as archive:
        names = archive.namelist()
        assert any(name.endswith("collections/concepts.json") for name in names)
        assert not any(name.endswith("collections/sources.json") for name in names)
        assert not any(name.endswith("collections/references.json") for name in names)

    present_archive = db_export.export_database_to_zip(
        _mongo(_Database({"concepts": [], "sources": [], "references": []})),
        tmp_path / "present",
    )
    with zipfile.ZipFile(present_archive) as archive:
        names = archive.namelist()
        assert any(name.endswith("collections/sources.json") for name in names)
        assert any(name.endswith("collections/references.json") for name in names)


def test_historical_import_does_not_create_absent_catalog_collections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "historical.zip"
    _write_archive(archive, {"concepts": []})
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts", "sources", "references"))
    database = _Database()

    report = db_import.import_zip_into_database(archive, _mongo(database))

    assert report.imported_counts == {"concepts": 0}
    assert set(database.list_collection_names()) == {"concepts"}


def test_catalog_import_reports_identical_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    incoming = {
        "_id": "64b64c7f0123456789abcdef",
        "source_id": source_id,
        "name": "Algebra",
        "created_at": "2026-07-11T12:00:00+00:00",
        "updated_at": "2026-07-11T12:00:00+00:00",
    }
    archive = tmp_path / "identical.zip"
    _write_archive(archive, {"sources": [incoming]})
    existing = {
        "_id": "different-storage-id",
        "source_id": source_id,
        "name": "Algebra",
        "created_at": datetime(2026, 7, 11, 12, 0, 0),
        "updated_at": datetime(2026, 7, 11, 12, 0, 0),
    }
    database = _Database({"sources": [existing]})
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("sources", "references"))

    report = db_import.import_zip_into_database(archive, _mongo(database))

    assert report.catalog_identical == {"sources": 1}
    assert report.catalog_inserted == {}
    assert database["sources"].documents == [existing]
    assert "references" not in database.list_collection_names()


def test_catalog_import_blocks_different_document_with_same_domain_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    archive = tmp_path / "conflict.zip"
    _write_archive(
        archive,
        {"sources": [{"source_id": source_id, "name": "Incoming"}]},
    )
    existing = {"source_id": source_id, "name": "Existing"}
    database = _Database({"sources": [existing]})
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("sources", "references"))

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(archive, _mongo(database))

    assert caught.value.report.catalog_conflicts[0].domain_id == source_id
    assert database["sources"].documents == [existing]
    assert not (tmp_path / "data").exists()


def test_catalog_reference_roundtrip_restores_nested_bson_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Source(name="Roundtrip")
    reference = Reference(
        title="Aware timestamps",
        source_ids=[source.source_id],
        accessed_at=datetime.now().astimezone(),
    )
    archive = tmp_path / "roundtrip.zip"
    _write_archive(
        archive,
        {
            "sources": [db_export.mongo_to_json_safe(source.model_dump(mode="python"))],
            "references": [db_export.mongo_to_json_safe(reference.model_dump(mode="python"))],
        },
    )
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("sources", "references"))

    report = db_import.import_zip_into_database(archive, _mongo(database))

    restored = database["references"].documents[0]
    assert report.catalog_inserted == {"sources": 1, "references": 1}
    assert restored["reference_id"] == reference.reference_id
    assert restored["source_ids"] == [source.source_id]
    assert isinstance(restored["created_at"], datetime)
    assert isinstance(restored["accessed_at"], datetime)
    assert isinstance(restored["provenance"]["imported_at"], datetime)
    assert restored["created_at"].tzinfo is not None
    assert restored["provenance"]["imported_at"].tzinfo is not None

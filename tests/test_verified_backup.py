"""Tests for the teaching backup manifest without a real MongoDB database."""

# ruff: noqa: D103

from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from mathmongo import backup
from mathmongo.config import AppConfig


class _Collection:
    def __init__(self, documents: list[dict], indexes: list[dict]) -> None:
        self.documents = documents
        self.indexes = indexes

    def count_documents(self, _query: dict) -> int:
        return len(self.documents)

    def list_indexes(self):
        return iter(self.indexes)


class _Database:
    name = "teaching_source"

    def __init__(self) -> None:
        self.collections = {
            "notes": _Collection(
                [{"_id": "note-1"}],
                [
                    {"name": "_id_", "key": {"_id": 1}},
                    {"name": "notes_title", "key": {"title": 1}, "unique": True},
                ],
            )
        }

    def list_collections(self) -> list[dict]:
        return [
            {
                "name": "notes",
                "options": {
                    "validator": {"$jsonSchema": {"bsonType": "object"}},
                    "validationLevel": "strict",
                },
            }
        ]

    def __getitem__(self, name: str) -> _Collection:
        return self.collections[name]


def test_database_structure_is_read_only_and_captures_indexes_and_validators() -> None:
    database = _Database()
    structure = backup.database_structure(database)
    assert structure["notes"]["count"] == 1
    assert structure["notes"]["options"]["validationAction"] == "error"
    assert structure["notes"]["options"]["validationLevel"] == "strict"
    assert structure["notes"]["indexes"][1] == {
        "name": "notes_title",
        "key": [["title", 1]],
        "options": {"unique": True},
    }


def test_create_and_verify_backup_manifest_uses_safe_identity(tmp_path: Path, monkeypatch) -> None:
    archive_path = tmp_path / "mathkb_export_20260804_120000.zip"

    def export(_mongo, _output: Path) -> Path:
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("export/metadata.json", "{}")
            archive.writestr("export/collections/notes.json", "[]")
        return archive_path

    inspection = {"collections": {"notes": 1}}
    monkeypatch.setattr(backup, "export_database_to_zip", export)
    monkeypatch.setattr(backup, "inspect_export_zip", lambda _path: inspection)
    config = AppConfig(
        mongo_uri="mongodb://teacher:secret@localhost:27017/teaching_source",
        mongo_database="teaching_source",
    )
    archive, manifest = backup.create_verified_backup(
        SimpleNamespace(db=_Database()),
        tmp_path,
        config=config,
    )
    assert archive == archive_path
    payload = manifest.read_text(encoding="utf-8")
    assert "teacher" not in payload
    assert "secret" not in payload
    verified = backup.verify_backup(manifest)
    assert verified["database_name"] == "teaching_source"
    assert verified["collections"] == {"notes": 1}


@pytest.mark.parametrize("target", ("MathV0", "mathv0", "teaching_source", "admin", ""))
def test_restore_target_rejects_historical_source_and_unsafe_names(target: str) -> None:
    with pytest.raises(backup.BackupError):
        backup._validate_restore_target("teaching_source", target)


def test_verify_backup_rejects_tampered_archive(tmp_path: Path, monkeypatch) -> None:
    archive_path = tmp_path / "backup.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("export/metadata.json", "{}")
    inventory = backup._zip_member_inventory(archive_path)
    manifest_path = archive_path.with_suffix(".manifest.json")
    backup._write_manifest(
        manifest_path,
        {
            "format": backup.BACKUP_FORMAT,
            "source": {"database": "teaching_source"},
            "archive": {
                "filename": archive_path.name,
                "sha256": backup._sha256_file(archive_path),
                "size_bytes": archive_path.stat().st_size,
                "members": inventory,
            },
            "archive_collection_counts": {},
            "database_structure": {},
        },
    )
    monkeypatch.setattr(backup, "inspect_export_zip", lambda _path: {"collections": {}})
    archive_path.write_bytes(b"tampered")
    with pytest.raises(backup.BackupError, match="SHA-256"):
        backup.verify_backup(manifest_path)

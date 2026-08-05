"""Read-only doctor and explicit bootstrap safety coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from mathmongo import doctor
from mathmongo.config import AppConfig

# ruff: noqa: D103


class _Collection:
    def __init__(self, count: int = 0) -> None:
        self.count = count

    def count_documents(self, _query: dict) -> int:
        return self.count

    def list_indexes(self):
        return iter(({"name": "_id_", "key": {"_id": 1}},))

    def find(self, _query: dict, _projection: dict | None = None):
        return iter(())


class _ReadOnlyDatabase:
    name = "teaching_diagnostic"

    def __init__(self) -> None:
        self.collections = {
            "sources": _Collection(1),
            "references": _Collection(1),
            "source_documents": _Collection(1),
            "document_reading_state": _Collection(1),
            "media_assets": _Collection(1),
        }
        self.create_calls: list[str] = []

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def list_collections(self) -> list[dict]:
        return [{"name": name, "options": {}} for name in self.collections]

    def __getitem__(self, name: str) -> _Collection:
        return self.collections[name]

    def create_collection(self, name: str) -> None:
        self.create_calls.append(name)
        raise AssertionError("doctor must not create collections")


def test_doctor_report_is_read_only_and_redacts_connection_identity(monkeypatch, tmp_path: Path) -> None:
    database = _ReadOnlyDatabase()
    monkeypatch.setattr(doctor, "get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(doctor, "get_media_dir", lambda: tmp_path / "data/media")
    monkeypatch.setattr(doctor, "get_source_document_blobs_dir", lambda: tmp_path / "data/blobs")
    report = doctor.doctor_report(
        database,
        config=AppConfig(
            mongo_uri="mongodb://teacher:secret@localhost:27017/teaching_diagnostic",
            mongo_database=database.name,
        ),
    )
    assert report["identity"]["product"] == "MathMongo"
    assert report["identity"]["database"] == database.name
    assert report["identity"]["mongo_uri"] == "mongodb://localhost:27017/teaching_diagnostic"
    assert report["source_catalog"]["available"] is True
    assert report["reading_space"]["available"] is True
    assert database.create_calls == []


@pytest.mark.parametrize("name, confirmation", (("MathV0", "MathV0"), ("teaching", "different")))
def test_bootstrap_requires_a_confirmed_non_mathv0_target(name: str, confirmation: str) -> None:
    database = _ReadOnlyDatabase()
    database.name = name
    with pytest.raises(doctor.DoctorError):
        doctor._validate_bootstrap_target(database, confirmation)


def test_bootstrap_plan_does_not_create_missing_collections() -> None:
    database = _ReadOnlyDatabase()
    plan = doctor.bootstrap_plan(database)
    assert "latex_notes" not in plan["create_collections"]
    assert all(operation["action"] in {"create_collection", "create_index"} for operation in plan["operations"])
    assert {operation["collection"] for operation in plan["operations"]} >= {"sources", "references"}
    assert database.create_calls == []


def test_doctor_reports_a_physical_pdf_blob_without_metadata(monkeypatch, tmp_path: Path) -> None:
    database = _ReadOnlyDatabase()
    blob_root = tmp_path / "data/source_documents/blobs/sha256"
    sha256 = "a" * 64
    blob = blob_root / sha256[:2] / f"{sha256}.pdf"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"%PDF-synthetic")
    monkeypatch.setattr(doctor, "get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(doctor, "get_media_dir", lambda: tmp_path / "data/media")
    monkeypatch.setattr(doctor, "get_source_document_blobs_dir", lambda: blob_root)

    report = doctor.doctor_report(
        database,
        config=AppConfig(mongo_database=database.name),
    )

    assert report["source_documents"]["physical_pdf_blobs"] == 1
    assert report["source_documents"]["blobs_without_metadata"] == 1
    assert database.create_calls == []

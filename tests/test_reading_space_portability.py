"""Portable backup coverage for S3 document reading state."""

# ruff: noqa: D103

from __future__ import annotations

import json
import zipfile
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest
from bson import ObjectId

from editor.utils import db_export
from editor.utils import db_import
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.storage import SourceDocumentBlobStore


class _Cursor(list):
    def max_time_ms(self, _milliseconds: int):
        return self

    def limit(self, count: int):
        return _Cursor(self[:count])


class _Collection:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self.documents = list(documents or [])
        self.insert_calls = 0
        self.index_names: set[str] = set()

    @staticmethod
    def _values_at_path(value, parts: tuple[str, ...]) -> list[object]:
        if not parts:
            return [value]
        if isinstance(value, list):
            return [item for child in value for item in _Collection._values_at_path(child, parts)]
        if not isinstance(value, dict) or parts[0] not in value:
            return []
        return _Collection._values_at_path(value[parts[0]], parts[1:])

    @classmethod
    def _matches(cls, document: dict, query: dict) -> bool:
        return all(
            expected in cls._values_at_path(document, tuple(key.split(".")))
            for key, expected in query.items()
        )

    def find(self, query: dict) -> _Cursor:
        return _Cursor(document for document in self.documents if self._matches(document, query))

    def find_one(self, query: dict):
        return next(
            (document for document in self.documents if self._matches(document, query)),
            None,
        )

    def insert_one(self, document: dict) -> None:
        self.insert_calls += 1
        self.documents.append(document)

    def create_index(self, _keys, *, name: str, **_kwargs) -> str:
        self.index_names.add(name)
        return name


class _Database:
    def __init__(
        self,
        documents: dict[str, list[dict]] | None = None,
        *,
        name: str = "reading-space-portability-test",
    ) -> None:
        self.name = name
        self.collections = {name: _Collection(items) for name, items in (documents or {}).items()}

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> None:
        self.collections.setdefault(name, _Collection())

    def __getitem__(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


def _mongo(database: _Database):
    return type("FakeMongo", (), {"db": database})()


def _configure_portable_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(db_export, "EXPORT_COLLECTIONS", ("concepts",))
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", tmp_path / "missing-media")


def _portable_documents() -> dict[str, list[dict]]:
    fixed = datetime(2026, 7, 12, 22, 30, tzinfo=timezone.utc)
    source = Source(
        source_id="src_00000000-0000-4000-8000-000000000301",
        name="Reading Space Portable",
        created_at=fixed,
        updated_at=fixed,
    )
    reference = Reference(
        reference_id="ref_00000000-0000-4000-8000-000000000302",
        source_ids=[source.source_id],
        title="Reading reference",
        created_at=fixed,
        updated_at=fixed,
    )
    document = SourceDocument(
        document_id="doc_00000000-0000-4000-8000-000000000303",
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind=DocumentKind.WEB,
        title="Reading resource",
        web=WebDocument(url_raw="https://example.com/reading"),
        created_at=fixed,
        updated_at=fixed,
    )
    state = DocumentReadingState(
        reading_state_id="read_00000000-0000-4000-8000-000000000304",
        document_id=document.document_id,
        source_id=source.source_id,
        reference_id=reference.reference_id,
        user_scope="local",
        status="in_progress",
        current_page=4,
        total_pages=12,
        first_opened_at=fixed,
        last_opened_at=fixed,
        open_count=2,
        created_at=fixed,
        updated_at=fixed,
    )

    result: dict[str, list[dict]] = {}
    for collection_name, model, storage_id in (
        ("sources", source, "64b64c7f0123456789abc301"),
        ("references", reference, "64b64c7f0123456789abc302"),
        ("source_documents", document, "64b64c7f0123456789abc303"),
        ("document_reading_state", state, "64b64c7f0123456789abc304"),
    ):
        payload = model.model_dump(mode="python")
        payload["_id"] = ObjectId(storage_id)
        result[collection_name] = [payload]
    return result


def _write_portable_archive(path: Path, collections: dict[str, list[dict]]) -> None:
    base = "mathkb_export_reading_space"
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "reading-space-portability-test",
        "collections": {name: len(items) for name, items in collections.items()},
        "collection_encodings": {
            name: db_export.CATALOG_EXTENDED_JSON_ENCODING for name in collections
        },
        "media_files": {},
        "source_document_blobs": {},
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for collection_name, documents in collections.items():
            archive.writestr(
                f"{base}/collections/{collection_name}.json",
                db_export.bson_json_dumps(
                    documents,
                    json_options=db_export.CANONICAL_JSON_OPTIONS,
                ),
            )
        archive.writestr(f"{base}/metadata.json", json.dumps(metadata))


def _export_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_reading_state: bool = True,
) -> tuple[Path, dict[str, list[dict]]]:
    _configure_portable_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    if not include_reading_state:
        documents.pop("document_reading_state")
    origin = _Database({"concepts": [], **documents})
    archive = db_export.export_database_to_zip(
        _mongo(origin),
        tmp_path / "backups",
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
    )
    return archive, documents


def test_reading_state_roundtrip_preserves_identity_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, documents = _export_bundle(tmp_path, monkeypatch)

    with zipfile.ZipFile(archive) as exported:
        state_member = next(
            name
            for name in exported.namelist()
            if name.endswith("/collections/document_reading_state.json")
        )
        metadata_member = next(
            name for name in exported.namelist() if name.endswith("/metadata.json")
        )
        metadata = json.loads(exported.read(metadata_member))
        assert exported.read(state_member)
        assert metadata["collections"]["document_reading_state"] == 1
        assert metadata["collection_encodings"]["document_reading_state"] == (
            db_export.CATALOG_EXTENDED_JSON_ENCODING
        )
        assert metadata["source_document_blobs"] == {}

    destination = _Database()
    store = SourceDocumentBlobStore(tmp_path / "destination-data")
    first = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=store,
    )
    assert first.catalog_inserted["document_reading_state"] == 1
    restored = destination["document_reading_state"].documents
    assert len(restored) == 1
    assert restored[0]["_id"] == documents["document_reading_state"][0]["_id"]
    assert (
        restored[0]["reading_state_id"]
        == (documents["document_reading_state"][0]["reading_state_id"])
    )
    assert restored[0]["updated_at"] == documents["document_reading_state"][0]["updated_at"]
    assert destination["document_reading_state"].index_names == set()

    second = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=store,
    )
    assert second.catalog_inserted == {}
    assert second.catalog_identical["document_reading_state"] == 1
    assert destination["document_reading_state"].insert_calls == 1
    assert destination["document_reading_state"].index_names == set()


def test_s2_archive_without_reading_state_remains_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _documents = _export_bundle(
        tmp_path,
        monkeypatch,
        include_reading_state=False,
    )
    destination = _Database()

    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
    )

    assert report.catalog_inserted["source_documents"] == 1
    assert "document_reading_state" not in destination.list_collection_names()


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("missing_document", "absent from archive and destination"),
        ("wrong_source", "Source does not match"),
        ("wrong_reference", "Reference does not match"),
    ),
)
def test_reading_state_foreign_key_conflicts_block_before_writes(
    mutation: str,
    expected_reason: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    state = documents["document_reading_state"][0]
    if mutation == "missing_document":
        documents.pop("source_documents")
    elif mutation == "wrong_source":
        state["source_id"] = "src_00000000-0000-4000-8000-000000000399"
    else:
        state["reference_id"] = "ref_00000000-0000-4000-8000-000000000399"
    archive = tmp_path / f"{mutation}.zip"
    _write_portable_archive(archive, documents)
    destination = _Database()

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )

    assert any(
        expected_reason in conflict.reason for conflict in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())
    assert all(collection.index_names == set() for collection in destination.collections.values())


def test_same_reading_state_id_with_different_content_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    archive = tmp_path / "reading-id-conflict.zip"
    _write_portable_archive(archive, documents)
    existing = deepcopy(documents)
    existing["document_reading_state"][0]["current_page"] = 9
    destination = _Database(existing)

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )

    assert any(
        conflict.collection == "document_reading_state" and "same domain ID" in conflict.reason
        for conflict in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())
    assert all(collection.index_names == set() for collection in destination.collections.values())


def test_same_user_document_with_different_state_id_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    archive = tmp_path / "reading-identity-conflict.zip"
    _write_portable_archive(archive, documents)
    existing = deepcopy(documents)
    existing["document_reading_state"][0]["reading_state_id"] = (
        "read_00000000-0000-4000-8000-000000000399"
    )
    existing["document_reading_state"][0]["_id"] = ObjectId("64b64c7f0123456789abc399")
    destination = _Database(existing)

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )

    assert any(
        "same identity" in conflict.reason for conflict in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())
    assert all(collection.index_names == set() for collection in destination.collections.values())


def test_archive_duplicate_user_document_identity_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    duplicate = deepcopy(documents["document_reading_state"][0])
    duplicate["_id"] = ObjectId("64b64c7f0123456789abc399")
    duplicate["reading_state_id"] = "read_00000000-0000-4000-8000-000000000399"
    documents["document_reading_state"].append(duplicate)
    archive = tmp_path / "reading-archive-identity-conflict.zip"
    _write_portable_archive(archive, documents)
    destination = _Database()

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )

    assert any(
        "one user/document identity" in conflict.reason
        for conflict in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())
    assert all(collection.index_names == set() for collection in destination.collections.values())


def test_export_rejects_dangling_reading_state_without_publishing_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents.pop("source_documents")
    origin = _Database({"concepts": [], **documents})
    output = tmp_path / "backups"

    with pytest.raises(ValueError, match="absent from the export"):
        db_export.export_database_to_zip(
            _mongo(origin),
            output,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )

    assert list(output.iterdir()) == []


def test_export_rejects_duplicate_user_document_identity_without_publishing_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    duplicate = deepcopy(documents["document_reading_state"][0])
    duplicate["_id"] = ObjectId("64b64c7f0123456789abc399")
    duplicate["reading_state_id"] = "read_00000000-0000-4000-8000-000000000399"
    documents["document_reading_state"].append(duplicate)
    origin = _Database({"concepts": [], **documents})
    output = tmp_path / "backups"

    with pytest.raises(ValueError, match="one user/document identity"):
        db_export.export_database_to_zip(
            _mongo(origin),
            output,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )

    assert list(output.iterdir()) == []

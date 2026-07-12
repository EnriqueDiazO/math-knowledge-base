"""Portable database backup coverage for Source Document metadata and PDF blobs."""

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
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.indexes import SOURCE_DOCUMENT_INDEXES
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared


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
    name = "source-document-portability-test"

    def __init__(self, documents: dict[str, list[dict]] | None = None) -> None:
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


def _portable_documents(
    store: SourceDocumentBlobStore,
) -> tuple[list[dict], dict, list[dict], bytes]:
    fixed = datetime(2026, 7, 12, 21, 30, tzinfo=timezone.utc)
    source = Source(
        source_id="src_00000000-0000-4000-8000-000000000101",
        name="Portable Documents",
        created_at=fixed,
        updated_at=fixed,
    )
    reference = Reference(
        reference_id="ref_00000000-0000-4000-8000-000000000102",
        source_ids=[source.source_id],
        title="Portable PDF",
        created_at=fixed,
        updated_at=fixed,
    )
    second_source = Source(
        source_id="src_00000000-0000-4000-8000-000000000108",
        name="Portable Deduplicated Documents",
        created_at=fixed,
        updated_at=fixed,
    )
    pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    prepared = store.prepare_pdf(pdf_bytes)
    store.publish(prepared)
    first_version = pdf_version_from_prepared(
        prepared,
        original_filename="portable.pdf",
        version_id="dver_00000000-0000-4000-8000-000000000103",
        created_at=fixed,
    )
    second_version = pdf_version_from_prepared(
        prepared,
        original_filename="same-bytes.pdf",
        version_id="dver_00000000-0000-4000-8000-000000000104",
        created_at=fixed,
    )
    first_pdf = SourceDocument(
        document_id="doc_00000000-0000-4000-8000-000000000105",
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind=DocumentKind.PDF,
        title="PDF one",
        pdf=PdfDocument(versions=[first_version], current_version_id=first_version.version_id),
        created_at=fixed,
        updated_at=fixed,
    )
    second_pdf = SourceDocument(
        document_id="doc_00000000-0000-4000-8000-000000000106",
        source_id=second_source.source_id,
        kind=DocumentKind.PDF,
        title="PDF two",
        pdf=PdfDocument(versions=[second_version], current_version_id=second_version.version_id),
        created_at=fixed,
        updated_at=fixed,
    )
    web = SourceDocument(
        document_id="doc_00000000-0000-4000-8000-000000000107",
        source_id=source.source_id,
        kind=DocumentKind.WEB,
        title="Web resource",
        web=WebDocument(url_raw="HTTPS://Example.COM:443/resource#fragment"),
        created_at=fixed,
        updated_at=fixed,
    )
    source_document = source.model_dump(mode="python")
    source_document["_id"] = ObjectId("64b64c7f0123456789abc101")
    second_source_document = second_source.model_dump(mode="python")
    second_source_document["_id"] = ObjectId("64b64c7f0123456789abc108")
    reference_document = reference.model_dump(mode="python")
    reference_document["_id"] = ObjectId("64b64c7f0123456789abc102")
    documents = []
    for offset, document in enumerate((first_pdf, second_pdf, web), start=3):
        payload = document.model_dump(mode="python")
        payload["_id"] = ObjectId(f"64b64c7f0123456789abc1{offset:02d}")
        documents.append(payload)
    return [source_document, second_source_document], reference_document, documents, pdf_bytes


def _export_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, SourceDocumentBlobStore, list[dict], bytes]:
    _configure_portable_backup(monkeypatch, tmp_path)
    origin_store = SourceDocumentBlobStore(tmp_path / "origin-data")
    sources, reference, documents, pdf_bytes = _portable_documents(origin_store)
    origin = _Database(
        {
            "concepts": [],
            "sources": sources,
            "references": [reference],
            "source_documents": documents,
        }
    )
    archive = db_export.export_database_to_zip(
        _mongo(origin),
        tmp_path / "backups",
        source_document_blob_store=origin_store,
    )
    return archive, origin_store, documents, pdf_bytes


def _write_portable_archive(
    path: Path,
    *,
    sources: list[dict],
    reference: dict,
    documents: list[dict],
    pdf_bytes: bytes,
) -> None:
    logical_path = documents[0]["pdf"]["versions"][0]["logical_path"]
    sha256 = documents[0]["pdf"]["versions"][0]["sha256"]
    collections = {
        "sources": sources,
        "references": [reference],
        "source_documents": documents,
    }
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "source-document-portability-test",
        "collections": {name: len(items) for name, items in collections.items()},
        "collection_encodings": {
            name: db_export.CATALOG_EXTENDED_JSON_ENCODING for name in collections
        },
        "media_files": {},
        "source_document_blobs": {logical_path: {"sha256": sha256, "size_bytes": len(pdf_bytes)}},
    }
    base = "mathkb_export_source_documents"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as export_zip:
        for collection_name, items in collections.items():
            export_zip.writestr(
                f"{base}/collections/{collection_name}.json",
                db_export.bson_json_dumps(
                    items,
                    json_options=db_export.CANONICAL_JSON_OPTIONS,
                ),
            )
        export_zip.writestr(f"{base}/{logical_path}", pdf_bytes)
        export_zip.writestr(f"{base}/metadata.json", json.dumps(metadata))


def _duplicate_identity_document(document: dict, *, suffix: int) -> dict:
    duplicate = deepcopy(document)
    duplicate["_id"] = ObjectId(f"64b64c7f0123456789abc2{suffix:02d}")
    duplicate["document_id"] = f"doc_00000000-0000-4000-8000-0000000002{suffix:02d}"
    duplicate["title"] = f"Duplicate identity {suffix}"
    if duplicate.get("pdf") is not None:
        duplicate["pdf"]["versions"][0]["version_id"] = (
            f"dver_00000000-0000-4000-8000-0000000002{suffix:02d}"
        )
        duplicate["pdf"]["current_version_id"] = duplicate["pdf"]["versions"][0]["version_id"]
    return duplicate


def test_source_document_pdf_and_web_roundtrip_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _origin_store, documents, pdf_bytes = _export_bundle(tmp_path, monkeypatch)

    with zipfile.ZipFile(archive) as export_zip:
        names = export_zip.namelist()
        metadata_name = next(name for name in names if name.endswith("/metadata.json"))
        metadata = json.loads(export_zip.read(metadata_name))
        collection_name = next(
            name for name in names if name.endswith("/collections/source_documents.json")
        )
        blob_names = [name for name in names if "/source_documents/blobs/sha256/" in name]
        assert len(blob_names) == 1
        assert export_zip.read(blob_names[0]) == pdf_bytes
        assert metadata["collections"]["source_documents"] == 3
        assert metadata["collection_encodings"]["source_documents"] == (
            db_export.CATALOG_EXTENDED_JSON_ENCODING
        )
        logical_path = blob_names[0].split("/", 1)[1]
        assert metadata["source_document_blobs"] == {
            logical_path: {
                "sha256": documents[0]["pdf"]["versions"][0]["sha256"],
                "size_bytes": len(pdf_bytes),
            }
        }
        assert export_zip.read(collection_name)

    destination = _Database()
    destination_store = SourceDocumentBlobStore(tmp_path / "destination-data")
    first = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=destination_store,
    )
    assert first.catalog_inserted["source_documents"] == 3
    assert first.source_document_blobs_created == 1
    assert destination["source_documents"].index_names == {
        spec.name for spec in SOURCE_DOCUMENT_INDEXES
    }
    restored = destination["source_documents"].documents
    assert [item["_id"] for item in restored] == [item["_id"] for item in documents]
    assert [item["document_id"] for item in restored] == [item["document_id"] for item in documents]
    assert [item["pdf"]["versions"][0]["version_id"] for item in restored[:2]] == [
        item["pdf"]["versions"][0]["version_id"] for item in documents[:2]
    ]
    assert [item["pdf"]["versions"][0]["sha256"] for item in restored[:2]] == [
        item["pdf"]["versions"][0]["sha256"] for item in documents[:2]
    ]
    version = SourceDocument.model_validate(
        {key: value for key, value in restored[0].items() if key != "_id"}
    ).pdf.current_version
    blob_path = destination_store.path_for_version(version)
    before = blob_path.stat()
    assert blob_path.read_bytes() == pdf_bytes
    assert before.st_mode & 0o777 == 0o600

    second = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=destination_store,
    )
    after = blob_path.stat()
    assert second.catalog_inserted == {}
    assert second.catalog_identical["source_documents"] == 3
    assert second.source_document_blobs_created == 0
    assert second.source_document_blobs_identical == 1
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert destination["source_documents"].insert_calls == 3


def test_source_document_metadata_conflict_blocks_before_blob_or_legacy_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _origin_store, documents, _pdf_bytes = _export_bundle(tmp_path, monkeypatch)
    conflicting = dict(documents[0])
    conflicting["title"] = "Different destination title"
    destination = _Database(
        {
            "concepts": [{"_id": "existing-concept"}],
            "source_documents": [conflicting],
        }
    )
    destination_store = SourceDocumentBlobStore(tmp_path / "destination-data")

    with pytest.raises(db_import.CatalogImportConflictError):
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=destination_store,
        )

    assert destination["concepts"].documents == [{"_id": "existing-concept"}]
    assert destination["source_documents"].documents == [conflicting]
    assert not destination_store.documents_root.exists()


def test_source_document_blob_conflict_blocks_without_mongodb_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _origin_store, documents, _pdf_bytes = _export_bundle(tmp_path, monkeypatch)
    destination = _Database()
    destination_store = SourceDocumentBlobStore(tmp_path / "destination-data")
    version_payload = documents[0]["pdf"]["versions"][0]
    destination_path = destination_store.path_for_sha(version_payload["sha256"])
    destination_path.parent.mkdir(parents=True, mode=0o700)
    destination_path.write_bytes(b"%PDF-1.4\ndifferent\n%%EOF\n")
    destination_path.chmod(0o600)
    original = destination_path.read_bytes()

    with pytest.raises(ValueError, match="destination conflicts"):
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=destination_store,
        )

    assert destination_path.read_bytes() == original
    assert destination.list_collection_names() == ["sources", "references", "source_documents"]
    assert all(not collection.documents for collection in destination.collections.values())


@pytest.mark.parametrize(("document_index", "suffix"), ((0, 9), (2, 10)))
def test_export_rejects_duplicate_pdf_and_web_identities_per_source(
    document_index: int,
    suffix: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    store = SourceDocumentBlobStore(tmp_path / "origin-data")
    sources, reference, documents, _pdf_bytes = _portable_documents(store)
    documents.append(_duplicate_identity_document(documents[document_index], suffix=suffix))
    origin = _Database(
        {
            "concepts": [],
            "sources": sources,
            "references": [reference],
            "source_documents": documents,
        }
    )

    with pytest.raises(ValueError, match="different document IDs"):
        db_export.export_database_to_zip(
            _mongo(origin),
            tmp_path / "backups",
            source_document_blob_store=store,
        )

    assert list((tmp_path / "backups").iterdir()) == []


@pytest.mark.parametrize(("document_index", "suffix"), ((0, 11), (2, 12)))
def test_import_rejects_archive_internal_pdf_and_web_identity_duplicates(
    document_index: int,
    suffix: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    origin_store = SourceDocumentBlobStore(tmp_path / "origin-data")
    sources, reference, documents, pdf_bytes = _portable_documents(origin_store)
    documents.append(_duplicate_identity_document(documents[document_index], suffix=suffix))
    archive = tmp_path / f"duplicate-archive-identity-{suffix}.zip"
    _write_portable_archive(
        archive,
        sources=sources,
        reference=reference,
        documents=documents,
        pdf_bytes=pdf_bytes,
    )
    destination = _Database()
    destination_store = SourceDocumentBlobStore(tmp_path / "destination-data")

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=destination_store,
        )

    assert any(
        "one Source Document identity" in conflict.reason
        for conflict in caught.value.report.catalog_conflicts
    )
    assert not destination_store.documents_root.exists()
    assert all(not collection.documents for collection in destination.collections.values())


@pytest.mark.parametrize(("document_index", "suffix"), ((0, 13), (2, 14)))
def test_import_rejects_destination_pdf_and_web_identity_with_another_document_id(
    document_index: int,
    suffix: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _origin_store, documents, _pdf_bytes = _export_bundle(tmp_path, monkeypatch)
    conflicting = _duplicate_identity_document(
        documents[document_index],
        suffix=suffix,
    )
    destination = _Database({"source_documents": [conflicting]})
    destination_store = SourceDocumentBlobStore(tmp_path / "destination-data")

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=destination_store,
        )

    assert any(
        "different document ID for the same identity" in conflict.reason
        for conflict in caught.value.report.catalog_conflicts
    )
    assert destination["source_documents"].documents == [conflicting]
    assert destination["source_documents"].index_names == set()
    assert not destination_store.documents_root.exists()


def test_source_document_index_failure_precedes_blob_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _origin_store, _documents, _pdf_bytes = _export_bundle(tmp_path, monkeypatch)
    destination = _Database()
    destination_store = SourceDocumentBlobStore(tmp_path / "destination-data")

    class _FailingIndexManager:
        def __init__(self, _database) -> None:
            pass

        def ensure(self) -> tuple[str, ...]:
            raise RuntimeError("index conflict")

    monkeypatch.setattr(db_import, "SourceDocumentIndexManager", _FailingIndexManager)

    with pytest.raises(RuntimeError, match="index conflict"):
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=destination_store,
        )

    assert not destination_store.documents_root.exists()
    assert all(not collection.documents for collection in destination.collections.values())


def test_historical_archive_without_source_documents_remains_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_portable_backup(monkeypatch, tmp_path)
    archive = tmp_path / "historical.zip"
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr(
            "mathkb_export_historical/metadata.json",
            json.dumps({"collections": {"concepts": 1}}),
        )
        export_zip.writestr(
            "mathkb_export_historical/collections/concepts.json",
            json.dumps([{"_id": "legacy-concept"}]),
        )
    destination = _Database()

    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "unused-data"),
    )

    assert report.legacy_inserted == {"concepts": 1}
    assert destination["concepts"].documents == [{"_id": "legacy-concept"}]
    assert "source_documents" not in destination.list_collection_names()


@pytest.mark.parametrize("collision_kind", ("raw", "nfc"))
def test_source_document_zip_namespace_rejects_duplicate_and_nfc_collisions(
    collision_kind: str,
    tmp_path: Path,
) -> None:
    archive = tmp_path / f"source-document-{collision_kind}-collision.zip"
    base = "mathkb_export_collision"
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr(
            f"{base}/metadata.json",
            json.dumps({"collections": {"concepts": 0}}),
        )
        export_zip.writestr(f"{base}/collections/concepts.json", "[]")
        if collision_kind == "raw":
            name = f"{base}/source_documents/blobs/sha256/aa/{'a' * 64}.pdf"
            export_zip.writestr(name, b"%PDF-1.4\nfirst")
            with pytest.warns(UserWarning):
                export_zip.writestr(name, b"%PDF-1.4\nsecond")
        else:
            export_zip.writestr(
                f"{base}/source_documents/caf\N{LATIN SMALL LETTER E WITH ACUTE}.pdf",
                b"%PDF-1.4\nfirst",
            )
            export_zip.writestr(
                f"{base}/source_documents/cafe\N{COMBINING ACUTE ACCENT}.pdf",
                b"%PDF-1.4\nsecond",
            )

    with pytest.raises(ValueError, match="duplicate member"):
        db_import.inspect_export_zip(archive)

"""Portable backup coverage for S4.2 Document Page Maps."""

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
from mathmongo.document_page_maps.models import DocumentPageMap
from mathmongo.document_page_maps.models import PageLabelRule
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.service import pdf_version_from_prepared
from mathmongo.source_documents.storage import SourceDocumentBlobStore

PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"


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
        name: str = "page-map-portability-test",
    ) -> None:
        self.name = name
        self.collections = {
            collection_name: _Collection(items)
            for collection_name, items in (documents or {}).items()
        }
        self.create_order: list[str] = []

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> None:
        if name not in self.collections:
            self.create_order.append(name)
        self.collections.setdefault(name, _Collection())

    def __getitem__(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


def _mongo(database: _Database):
    return type("FakeMongo", (), {"db": database})()


def _configure_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(db_export, "EXPORT_COLLECTIONS", ("concepts",))
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", tmp_path / "missing-media")


def _portable_documents() -> dict[str, list[dict]]:
    fixed = datetime(2026, 7, 13, 3, 0, tzinfo=timezone.utc)
    source = Source(
        source_id="src_00000000-0000-4000-8000-000000000501",
        name="Page Map Portable",
        created_at=fixed,
        updated_at=fixed,
    )
    reference = Reference(
        reference_id="ref_00000000-0000-4000-8000-000000000502",
        source_ids=[source.source_id],
        title="Page Map reference",
        created_at=fixed,
        updated_at=fixed,
    )
    prepared = SourceDocumentBlobStore.prepare_pdf(PDF_BYTES)
    version = pdf_version_from_prepared(
        prepared,
        original_filename="page-map.pdf",
        version_id="dver_00000000-0000-4000-8000-000000000506",
        created_at=fixed,
    )
    document = SourceDocument(
        document_id="doc_00000000-0000-4000-8000-000000000503",
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind=DocumentKind.PDF,
        title="Mapped resource",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
        created_at=fixed,
        updated_at=fixed,
    )
    page_map = DocumentPageMap(
        page_map_id="pmap_00000000-0000-4000-8000-000000000504",
        document_id=document.document_id,
        source_id=source.source_id,
        rules=[
            PageLabelRule(
                rule_id="prule_00000000-0000-4000-8000-000000000505",
                pdf_start_page=9,
                label_start=1,
                label_style="arabic",
            )
        ],
        created_at=fixed,
        updated_at=fixed,
    )

    result: dict[str, list[dict]] = {"concepts": []}
    for collection_name, model, storage_id in (
        ("sources", source, "64b64c7f0123456789abc501"),
        ("references", reference, "64b64c7f0123456789abc502"),
        ("source_documents", document, "64b64c7f0123456789abc503"),
        ("document_page_maps", page_map, "64b64c7f0123456789abc504"),
    ):
        payload = model.model_dump(mode="python")
        payload["_id"] = ObjectId(storage_id)
        result[collection_name] = [payload]
    return result


def _write_archive(path: Path, collections: dict[str, list[dict]]) -> None:
    base = "mathkb_export_page_maps"
    portable = set(db_import.PORTABLE_EXTENDED_JSON_COLLECTIONS)
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "page-map-portability-test",
        "collections": {name: len(items) for name, items in collections.items()},
        "collection_encodings": {
            name: db_export.CATALOG_EXTENDED_JSON_ENCODING
            for name in collections
            if name in portable
        },
        "media_files": {},
        "source_document_blobs": {},
    }
    blobs: dict[str, bytes] = {}
    for document in collections.get("source_documents", []):
        pdf = document.get("pdf")
        if not isinstance(pdf, dict):
            continue
        for version in pdf.get("versions", []):
            logical_path = version["logical_path"]
            blobs[logical_path] = PDF_BYTES
            metadata["source_document_blobs"][logical_path] = {
                "sha256": version["sha256"],
                "size_bytes": version["size_bytes"],
            }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for collection_name, documents in collections.items():
            if collection_name in portable:
                payload = db_export.bson_json_dumps(
                    documents,
                    json_options=db_export.CANONICAL_JSON_OPTIONS,
                )
            else:
                payload = json.dumps([db_export.mongo_to_json_safe(item) for item in documents])
            archive.writestr(f"{base}/collections/{collection_name}.json", payload)
        for logical_path, payload in blobs.items():
            archive.writestr(f"{base}/{logical_path}", payload)
        archive.writestr(f"{base}/metadata.json", json.dumps(metadata))


def _export_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_page_maps: bool = True,
) -> tuple[Path, dict[str, list[dict]]]:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    if not include_page_maps:
        documents.pop("document_page_maps")
    origin_store = SourceDocumentBlobStore(tmp_path / "origin-data")
    origin_store.publish(origin_store.prepare_pdf(PDF_BYTES))
    archive = db_export.export_database_to_zip(
        _mongo(_Database(documents)),
        tmp_path / "backups",
        source_document_blob_store=origin_store,
    )
    return archive, documents


def test_page_map_roundtrip_is_canonical_idempotent_and_index_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, documents = _export_bundle(tmp_path, monkeypatch)

    with zipfile.ZipFile(archive) as exported:
        member = next(
            name
            for name in exported.namelist()
            if name.endswith("/collections/document_page_maps.json")
        )
        metadata_name = next(name for name in exported.namelist() if name.endswith("metadata.json"))
        metadata = json.loads(exported.read(metadata_name))
        payload = exported.read(member)
        assert b'"$date"' in payload
        assert metadata["collection_encodings"]["document_page_maps"] == (
            db_export.CATALOG_EXTENDED_JSON_ENCODING
        )
        assert len(metadata["source_document_blobs"]) == 1
        blob_metadata = next(iter(metadata["source_document_blobs"].values()))
        assert blob_metadata["size_bytes"] == len(PDF_BYTES)
        assert b"pdf_bytes" not in payload and b"blob" not in payload

    destination = _Database({"concepts": []})
    store = SourceDocumentBlobStore(tmp_path / "destination-data")
    first = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=store,
    )
    assert first.catalog_inserted["document_page_maps"] == 1
    assert db_import._PORTABLE_IMPORT_ORDER.index("source_documents") < (
        db_import._PORTABLE_IMPORT_ORDER.index("document_page_maps")
    )
    restored = destination["document_page_maps"].documents[0]
    assert restored["_id"] == documents["document_page_maps"][0]["_id"]
    assert restored["page_map_id"] == documents["document_page_maps"][0]["page_map_id"]
    assert restored["created_at"] == documents["document_page_maps"][0]["created_at"]
    assert restored["updated_at"] == documents["document_page_maps"][0]["updated_at"]
    assert destination["document_page_maps"].index_names == set()

    second = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=store,
    )
    assert second.catalog_inserted == {}
    assert second.catalog_identical["document_page_maps"] == 1
    assert destination["document_page_maps"].insert_calls == 1
    assert destination["document_page_maps"].index_names == set()


def test_historical_archive_without_page_maps_remains_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _documents = _export_bundle(tmp_path, monkeypatch, include_page_maps=False)
    destination = _Database({"concepts": []})

    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
    )

    assert report.catalog_inserted["source_documents"] == 1
    assert "document_page_maps" not in destination.list_collection_names()


def test_page_map_only_import_does_not_create_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    archive = tmp_path / "page-map-only.zip"
    _write_archive(archive, {"document_page_maps": documents["document_page_maps"]})
    destination = _Database(
        {
            "concepts": [],
            "source_documents": deepcopy(documents["source_documents"]),
        }
    )

    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
    )

    assert report.catalog_inserted["document_page_maps"] == 1
    assert all(collection.index_names == set() for collection in destination.collections.values())


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    (
        (
            "document_id",
            "doc_00000000-0000-4000-8000-000000000599",
            "Source Document absent",
        ),
        (
            "source_id",
            "src_00000000-0000-4000-8000-000000000599",
            "Source does not match",
        ),
    ),
)
def test_page_map_relationship_conflicts_block_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    value: str,
    reason: str,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["document_page_maps"][0][field_name] = value
    archive = tmp_path / f"invalid-page-map-{field_name}.zip"
    _write_archive(archive, documents)
    destination = _Database({"concepts": []})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(reason in item.reason for item in caught.value.report.catalog_conflicts)
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_import_rejects_page_map_for_web_document_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    pdf_document = documents["source_documents"][0]
    web_document = SourceDocument(
        document_id=pdf_document["document_id"],
        source_id=pdf_document["source_id"],
        reference_id=pdf_document["reference_id"],
        kind=DocumentKind.WEB,
        title=pdf_document["title"],
        web=WebDocument(url_raw="https://example.com/page-map"),
        created_at=pdf_document["created_at"],
        updated_at=pdf_document["updated_at"],
    ).model_dump(mode="python")
    web_document["_id"] = pdf_document["_id"]
    documents["source_documents"] = [web_document]
    archive = tmp_path / "web-page-map.zip"
    _write_archive(archive, documents)
    destination = _Database({"concepts": []})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )

    assert any(
        item.collection == "document_page_maps" and "non-PDF" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_same_page_map_id_with_different_content_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    archive = tmp_path / "same-page-map-id-conflict.zip"
    _write_archive(archive, documents)
    existing = deepcopy(documents["document_page_maps"][0])
    existing["rules"][0]["label_start"] = 2
    destination = _Database({"concepts": [], "document_page_maps": [existing]})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        item.collection == "document_page_maps" and "same domain ID" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_different_active_page_map_id_for_identity_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    archive = tmp_path / "active-page-map-identity-conflict.zip"
    _write_archive(archive, documents)
    existing = deepcopy(documents["document_page_maps"][0])
    existing["page_map_id"] = "pmap_00000000-0000-4000-8000-000000000598"
    existing["_id"] = ObjectId("64b64c7f0123456789abc598")
    destination = _Database({"concepts": [], "document_page_maps": [existing]})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        "different active Page Map ID" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_export_rejects_noncanonical_page_map_without_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["document_page_maps"][0]["rules"][0]["label_prefix"] = " chapter "
    out_dir = tmp_path / "backups"

    with pytest.raises(ValueError, match="document_page_maps contains a non-canonical"):
        db_export.export_database_to_zip(
            _mongo(_Database(documents)),
            out_dir,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )
    assert list(out_dir.glob("*.zip")) == []


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    (
        (
            "document_id",
            "doc_00000000-0000-4000-8000-000000000599",
            "Source Document absent",
        ),
        (
            "source_id",
            "src_00000000-0000-4000-8000-000000000599",
            "Source does not match",
        ),
    ),
)
def test_export_rejects_page_map_document_source_conflicts_without_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    value: str,
    message: str,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["document_page_maps"][0][field_name] = value
    out_dir = tmp_path / "backups"

    with pytest.raises(ValueError, match=message):
        db_export.export_database_to_zip(
            _mongo(_Database(documents)),
            out_dir,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )
    assert list(out_dir.glob("*.zip")) == []


def test_export_rejects_page_map_for_web_document_without_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    pdf_document = documents["source_documents"][0]
    web_document = SourceDocument(
        document_id=pdf_document["document_id"],
        source_id=pdf_document["source_id"],
        reference_id=pdf_document["reference_id"],
        kind=DocumentKind.WEB,
        title=pdf_document["title"],
        web=WebDocument(url_raw="https://example.com/page-map"),
        created_at=pdf_document["created_at"],
        updated_at=pdf_document["updated_at"],
    ).model_dump(mode="python")
    web_document["_id"] = pdf_document["_id"]
    documents["source_documents"] = [web_document]
    out_dir = tmp_path / "backups"

    with pytest.raises(ValueError, match="non-PDF Source Document"):
        db_export.export_database_to_zip(
            _mongo(_Database(documents)),
            out_dir,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )

    assert list(out_dir.glob("*.zip")) == []

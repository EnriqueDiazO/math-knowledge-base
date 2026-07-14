"""Portable backup coverage for S4 annotations, notes, and evidence."""

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
from bson.json_util import loads as bson_json_loads

from editor.utils import db_export
from editor.utils import db_import
from mathmongo.reading_annotations.models import ConceptEvidenceLink
from mathmongo.reading_annotations.models import DocumentAnnotation
from mathmongo.reading_annotations.models import ReadingNote
from mathmongo.reading_annotations.models import VisualAnnotationAnchor
from mathmongo.reading_annotations.models import visual_text_sha256
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import PdfVersion
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
        name: str = "reading-annotations-portability-test",
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
    fixed = datetime(2026, 7, 12, 23, 30, tzinfo=timezone.utc)
    source = Source(
        source_id="src_00000000-0000-4000-8000-000000000401",
        name="Reading Annotations Portable",
        created_at=fixed,
        updated_at=fixed,
    )
    reference = Reference(
        reference_id="ref_00000000-0000-4000-8000-000000000402",
        source_ids=[source.source_id],
        title="Annotation reference",
        created_at=fixed,
        updated_at=fixed,
    )
    document = SourceDocument(
        document_id="doc_00000000-0000-4000-8000-000000000403",
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind=DocumentKind.WEB,
        title="Annotated resource",
        web=WebDocument(url_raw="https://example.com/annotations"),
        created_at=fixed,
        updated_at=fixed,
    )
    state = DocumentReadingState(
        reading_state_id="read_00000000-0000-4000-8000-000000000404",
        document_id=document.document_id,
        source_id=source.source_id,
        reference_id=reference.reference_id,
        user_scope="local",
        status="in_progress",
        first_opened_at=fixed,
        last_opened_at=fixed,
        open_count=1,
        created_at=fixed,
        updated_at=fixed,
    )
    annotation = DocumentAnnotation(
        annotation_id="ann_00000000-0000-4000-8000-000000000405",
        document_id=document.document_id,
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind="comment",
        page_number=3,
        quote_text="A manual quote",
        body="A bounded comment",
        tags=["portable"],
        created_at=fixed,
        updated_at=fixed,
    )
    note = ReadingNote(
        note_id="note_00000000-0000-4000-8000-000000000406",
        document_id=document.document_id,
        source_id=source.source_id,
        reference_id=reference.reference_id,
        title="Portable note",
        body="A reading note body",
        note_type="summary",
        page_start=3,
        page_end=4,
        tags=["summary"],
        created_at=fixed,
        updated_at=fixed,
    )
    evidence = ConceptEvidenceLink(
        evidence_link_id="ev_00000000-0000-4000-8000-000000000407",
        concept_legacy_id="compactness",
        concept_legacy_source="Topology",
        source_id=source.source_id,
        reference_id=reference.reference_id,
        annotation_id=annotation.annotation_id,
        link_type="definition_source",
        comment="Traceable evidence",
        created_at=fixed,
        updated_at=fixed,
    )

    result: dict[str, list[dict]] = {
        "concepts": [
            {
                "_id": ObjectId("64b64c7f0123456789abc400"),
                "id": "compactness",
                "source": "Topology",
                "title": "Compactness",
            }
        ]
    }
    for collection_name, model, storage_id in (
        ("sources", source, "64b64c7f0123456789abc401"),
        ("references", reference, "64b64c7f0123456789abc402"),
        ("source_documents", document, "64b64c7f0123456789abc403"),
        ("document_reading_state", state, "64b64c7f0123456789abc404"),
        ("document_annotations", annotation, "64b64c7f0123456789abc405"),
        ("reading_notes", note, "64b64c7f0123456789abc406"),
        ("concept_evidence_links", evidence, "64b64c7f0123456789abc407"),
    ):
        payload = model.model_dump(mode="python")
        if collection_name == "document_annotations" and payload.get("schema_version") == 1:
            payload.pop("visual_anchor", None)
        payload["_id"] = ObjectId(storage_id)
        result[collection_name] = [payload]
    return result


def _visual_portable_documents() -> tuple[dict[str, list[dict]], bytes]:
    documents = _portable_documents()
    fixed = datetime(2026, 7, 12, 23, 30, tzinfo=timezone.utc)
    pdf_bytes = b"%PDF-1.4\n% S5B portable visual annotation\n%%EOF\n"
    prepared = SourceDocumentBlobStore.prepare_pdf(pdf_bytes)
    version = PdfVersion(
        version_id="dver_00000000-0000-4000-8000-000000000408",
        sha256=prepared.sha256,
        size_bytes=prepared.size_bytes,
        logical_path=prepared.logical_path,
        original_filename="portable-visual.pdf",
        created_at=fixed,
    )
    previous_document = documents["source_documents"][0]
    document = SourceDocument(
        document_id=previous_document["document_id"],
        source_id=previous_document["source_id"],
        reference_id=previous_document["reference_id"],
        kind=DocumentKind.PDF,
        title="Annotated PDF",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
        created_at=fixed,
        updated_at=fixed,
    )
    quote_text = "Every compact subset is closed."
    annotation = DocumentAnnotation(
        schema_version=2,
        annotation_id=documents["document_annotations"][0]["annotation_id"],
        document_id=document.document_id,
        source_id=document.source_id,
        reference_id=document.reference_id,
        kind="highlight",
        page_number=3,
        quote_text=quote_text,
        body="Persisted visual mark",
        color_label="purple",
        tags=["portable", "visual"],
        visual_anchor=VisualAnnotationAnchor(
            version_id=version.version_id,
            document_sha256=version.sha256,
            pdf_page=3,
            capture_rotation=90,
            rects=(
                {"x": 0.12, "y": 0.31, "width": 0.42, "height": 0.03},
                {"x": 0.12, "y": 0.35, "width": 0.20, "height": 0.03},
            ),
            text_sha256=visual_text_sha256(quote_text),
        ),
        created_at=fixed,
        updated_at=fixed,
    )
    document_payload = document.model_dump(mode="python")
    document_payload["_id"] = previous_document["_id"]
    annotation_payload = annotation.model_dump(mode="python")
    annotation_payload["_id"] = documents["document_annotations"][0]["_id"]
    documents["source_documents"] = [document_payload]
    documents["document_annotations"] = [annotation_payload]
    return documents, pdf_bytes


def _append_alternate_source_reference(documents: dict[str, list[dict]]) -> str:
    alternate = deepcopy(documents["references"][0])
    alternate_id = "ref_00000000-0000-4000-8000-000000000498"
    alternate["reference_id"] = alternate_id
    alternate["title"] = "Alternate Source reference"
    alternate["_id"] = ObjectId("64b64c7f0123456789abc498")
    documents["references"].append(alternate)
    return alternate_id


def _write_archive(
    path: Path,
    collections: dict[str, list[dict]],
    *,
    source_document_blobs: dict[str, bytes] | None = None,
) -> None:
    base = "mathkb_export_reading_annotations"
    portable = set(db_import.PORTABLE_EXTENDED_JSON_COLLECTIONS)
    blobs = dict(source_document_blobs or {})
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "reading-annotations-portability-test",
        "collections": {name: len(items) for name, items in collections.items()},
        "collection_encodings": {
            name: db_export.CATALOG_EXTENDED_JSON_ENCODING
            for name in collections
            if name in portable
        },
        "media_files": {},
        "source_document_blobs": {
            logical_path: {
                "sha256": SourceDocumentBlobStore.prepare_pdf(data).sha256,
                "size_bytes": len(data),
            }
            for logical_path, data in blobs.items()
        },
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
        for logical_path, data in blobs.items():
            archive.writestr(f"{base}/{logical_path}", data)
        archive.writestr(f"{base}/metadata.json", json.dumps(metadata))


def _export_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_s4: bool = True,
) -> tuple[Path, dict[str, list[dict]]]:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    if not include_s4:
        for collection_name in (
            "document_annotations",
            "reading_notes",
            "concept_evidence_links",
        ):
            documents.pop(collection_name)
    origin = _Database(documents)
    archive = db_export.export_database_to_zip(
        _mongo(origin),
        tmp_path / "backups",
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
    )
    return archive, documents


def test_s4_roundtrip_is_canonical_ordered_idempotent_and_index_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, documents = _export_bundle(tmp_path, monkeypatch)

    with zipfile.ZipFile(archive) as exported:
        metadata_name = next(name for name in exported.namelist() if name.endswith("metadata.json"))
        metadata = json.loads(exported.read(metadata_name))
        for collection_name in (
            "document_annotations",
            "reading_notes",
            "concept_evidence_links",
        ):
            member = next(
                name
                for name in exported.namelist()
                if name.endswith(f"/collections/{collection_name}.json")
            )
            assert exported.read(member)
            assert metadata["collection_encodings"][collection_name] == (
                db_export.CATALOG_EXTENDED_JSON_ENCODING
            )
        assert documents["document_annotations"][0]["schema_version"] == 1
        assert "visual_anchor" not in documents["document_annotations"][0]
        assert metadata["source_document_blobs"] == {}

    destination = _Database({"concepts": []})
    store = SourceDocumentBlobStore(tmp_path / "destination-data")
    first = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=store,
    )
    assert first.catalog_inserted["document_annotations"] == 1
    assert first.catalog_inserted["reading_notes"] == 1
    assert first.catalog_inserted["concept_evidence_links"] == 1
    assert first.source_document_blobs_created == 0
    order = db_import._PORTABLE_IMPORT_ORDER
    assert order.index("document_reading_state") < order.index("document_annotations")
    assert order.index("document_annotations") < order.index("reading_notes")
    assert order.index("reading_notes") < order.index("concept_evidence_links")
    for collection_name in (
        "document_annotations",
        "reading_notes",
        "concept_evidence_links",
    ):
        restored = destination[collection_name].documents[0]
        assert restored["_id"] == documents[collection_name][0]["_id"]
        assert restored["created_at"] == documents[collection_name][0]["created_at"]
        assert destination[collection_name].index_names == set()

    second = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=store,
    )
    assert second.catalog_inserted == {}
    assert second.catalog_identical["document_annotations"] == 1
    assert second.catalog_identical["reading_notes"] == 1
    assert second.catalog_identical["concept_evidence_links"] == 1
    assert destination["concept_evidence_links"].insert_calls == 1


def test_s3_archive_without_s4_remains_compatible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, _documents = _export_bundle(tmp_path, monkeypatch, include_s4=False)
    destination = _Database({"concepts": []})
    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
    )
    assert report.catalog_inserted["document_reading_state"] == 1
    assert not set(db_import.READING_ANNOTATION_COLLECTIONS) & set(
        destination.list_collection_names()
    )


def test_schema_v1_annotation_with_explicit_null_anchor_remains_portable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["document_annotations"][0]["visual_anchor"] = None
    archive = db_export.export_database_to_zip(
        _mongo(_Database(documents)),
        tmp_path / "backups",
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
    )
    destination = _Database({"concepts": []})

    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
    )

    assert report.catalog_inserted["document_annotations"] == 1
    assert destination["document_annotations"].documents[0]["visual_anchor"] is None
    assert destination["document_annotations"].index_names == set()


def test_schema_v2_logical_annotation_without_anchor_remains_portable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["document_annotations"][0]["schema_version"] = 2
    archive = db_export.export_database_to_zip(
        _mongo(_Database(documents)),
        tmp_path / "backups",
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
    )
    destination = _Database({"concepts": []})

    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
    )

    restored = destination["document_annotations"].documents[0]
    assert report.catalog_inserted["document_annotations"] == 1
    assert restored["schema_version"] == 2
    assert "visual_anchor" not in restored


def test_note_can_use_an_alternate_reference_from_the_same_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["reading_notes"][0]["reference_id"] = _append_alternate_source_reference(documents)
    archive = db_export.export_database_to_zip(
        _mongo(_Database(documents)),
        tmp_path / "backups",
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
    )
    destination = _Database({"concepts": []})
    report = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
    )
    assert report.catalog_inserted["reading_notes"] == 1


def test_evidence_reference_must_match_its_target_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["concept_evidence_links"][0]["reference_id"] = _append_alternate_source_reference(
        documents
    )
    archive = tmp_path / "evidence-reference-conflict.zip"
    _write_archive(archive, documents)
    destination = _Database({"concepts": []})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        "Evidence Reference does not match its target" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


@pytest.mark.parametrize(
    ("collection_name", "field_name", "value", "expected_reason"),
    (
        (
            "document_annotations",
            "document_id",
            "doc_00000000-0000-4000-8000-000000000499",
            "Source Document absent",
        ),
        (
            "reading_notes",
            "reference_id",
            "ref_00000000-0000-4000-8000-000000000499",
            "Reference is absent",
        ),
        (
            "concept_evidence_links",
            "annotation_id",
            "ann_00000000-0000-4000-8000-000000000499",
            "Annotation absent",
        ),
        (
            "concept_evidence_links",
            "concept_legacy_id",
            "missing-concept",
            "Legacy Concept is absent",
        ),
    ),
)
def test_s4_foreign_key_conflicts_block_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collection_name: str,
    field_name: str,
    value: str,
    expected_reason: str,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents[collection_name][0][field_name] = value
    archive = tmp_path / f"invalid-{collection_name}-{field_name}.zip"
    _write_archive(archive, documents)
    destination = _Database({"concepts": []})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(expected_reason in item.reason for item in caught.value.report.catalog_conflicts)
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_same_s4_domain_id_with_different_content_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    archive = tmp_path / "same-id-conflict.zip"
    _write_archive(archive, documents)
    existing = deepcopy(documents["reading_notes"][0])
    existing["body"] = "Different destination body"
    destination = _Database({"concepts": [], "reading_notes": [existing]})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        item.collection == "reading_notes" and "same domain ID" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_different_id_for_exact_evidence_identity_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    archive = tmp_path / "evidence-identity-conflict.zip"
    _write_archive(archive, documents)
    existing = deepcopy(documents["concept_evidence_links"][0])
    existing["evidence_link_id"] = "ev_00000000-0000-4000-8000-000000000499"
    existing["_id"] = ObjectId("64b64c7f0123456789abc499")
    destination = _Database({"concepts": [], "concept_evidence_links": [existing]})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        "same exact identity" in item.reason for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_ambiguous_legacy_concept_in_archive_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    duplicate = deepcopy(documents["concepts"][0])
    duplicate["_id"] = ObjectId("64b64c7f0123456789abc498")
    documents["concepts"].append(duplicate)
    archive = tmp_path / "ambiguous-concept.zip"
    _write_archive(archive, documents)
    destination = _Database({"concepts": [deepcopy(documents["concepts"][0])]})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        "Legacy Concept is absent or ambiguous" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_export_rejects_dangling_evidence_without_publishing_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["concept_evidence_links"][0]["concept_legacy_id"] = "absent"
    out_dir = tmp_path / "backups"

    with pytest.raises(ValueError, match="legacy Concept absent"):
        db_export.export_database_to_zip(
            _mongo(_Database(documents)),
            out_dir,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )
    assert list(out_dir.glob("*.zip")) == []


def test_export_rejects_noncanonical_s4_document_without_publishing_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents = _portable_documents()
    documents["reading_notes"][0]["title"] = "  Portable note  "
    documents["reading_notes"][0]["tags"] = [" summary ", "SUMMARY"]
    out_dir = tmp_path / "backups"

    with pytest.raises(ValueError, match="reading_notes contains a non-canonical"):
        db_export.export_database_to_zip(
            _mongo(_Database(documents)),
            out_dir,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )
    assert list(out_dir.glob("*.zip")) == []


def test_s5b_visual_annotation_roundtrip_preserves_anchor_and_is_index_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents, pdf_bytes = _visual_portable_documents()
    origin_store = SourceDocumentBlobStore(tmp_path / "origin-data")
    origin_store.publish(origin_store.prepare_pdf(pdf_bytes))

    archive = db_export.export_database_to_zip(
        _mongo(_Database(documents)),
        tmp_path / "backups",
        source_document_blob_store=origin_store,
    )
    expected_anchor = DocumentAnnotation.model_validate(
        {key: value for key, value in documents["document_annotations"][0].items() if key != "_id"}
    ).model_dump(mode="json")["visual_anchor"]
    with zipfile.ZipFile(archive) as exported:
        annotation_member = next(
            name
            for name in exported.namelist()
            if name.endswith("/collections/document_annotations.json")
        )
        payload = bson_json_loads(exported.read(annotation_member).decode("utf-8"))[0]
        assert payload["schema_version"] == 2
        assert payload["visual_anchor"] == expected_anchor

    destination = _Database({"concepts": []})
    destination_store = SourceDocumentBlobStore(tmp_path / "destination-data")
    first = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=destination_store,
    )
    restored = destination["document_annotations"].documents[0]
    assert first.catalog_inserted["document_annotations"] == 1
    assert restored["schema_version"] == 2
    assert restored["visual_anchor"] == expected_anchor
    assert restored["visual_anchor"]["rects"] == [
        {"x": 0.12, "y": 0.31, "width": 0.42, "height": 0.03},
        {"x": 0.12, "y": 0.35, "width": 0.2, "height": 0.03},
    ]
    assert destination["document_annotations"].index_names == set()

    second = db_import.import_zip_into_database(
        archive,
        _mongo(destination),
        source_document_blob_store=destination_store,
    )
    assert second.catalog_inserted == {}
    assert second.catalog_identical["document_annotations"] == 1
    assert destination["document_annotations"].insert_calls == 1
    assert destination["document_annotations"].index_names == set()


@pytest.mark.parametrize(
    ("field_name", "value", "expected_reason"),
    (
        (
            "version_id",
            "dver_00000000-0000-4000-8000-000000000499",
            "PDF version absent",
        ),
        ("document_sha256", "f" * 64, "SHA does not match"),
    ),
)
def test_s5b_import_rejects_visual_anchor_version_mismatch_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    value: str,
    expected_reason: str,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents, pdf_bytes = _visual_portable_documents()
    documents["document_annotations"][0]["visual_anchor"][field_name] = value
    prepared = SourceDocumentBlobStore.prepare_pdf(pdf_bytes)
    archive = tmp_path / f"visual-{field_name}-conflict.zip"
    _write_archive(
        archive,
        documents,
        source_document_blobs={prepared.logical_path: pdf_bytes},
    )
    destination = _Database({"concepts": []})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(expected_reason in item.reason for item in caught.value.report.catalog_conflicts)
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_s5b_import_rejects_invalid_visual_geometry_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents, pdf_bytes = _visual_portable_documents()
    documents["document_annotations"][0]["visual_anchor"]["rects"][0]["x"] = 0.9
    prepared = SourceDocumentBlobStore.prepare_pdf(pdf_bytes)
    archive = tmp_path / "invalid-visual-geometry.zip"
    _write_archive(
        archive,
        documents,
        source_document_blobs={prepared.logical_path: pdf_bytes},
    )
    destination = _Database({"concepts": []})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        item.collection == "document_annotations" and "invalid portable" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_s5b_export_rejects_visual_version_mismatch_without_publishing_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents, _pdf_bytes = _visual_portable_documents()
    documents["document_annotations"][0]["visual_anchor"]["version_id"] = (
        "dver_00000000-0000-4000-8000-000000000499"
    )
    out_dir = tmp_path / "backups"

    with pytest.raises(ValueError, match="PDF version absent"):
        db_export.export_database_to_zip(
            _mongo(_Database(documents)),
            out_dir,
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "origin-data"),
        )
    assert list(out_dir.glob("*.zip")) == []


def test_s5b_same_annotation_id_with_different_content_blocks_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_backup(monkeypatch, tmp_path)
    documents, pdf_bytes = _visual_portable_documents()
    prepared = SourceDocumentBlobStore.prepare_pdf(pdf_bytes)
    archive = tmp_path / "visual-same-id-conflict.zip"
    _write_archive(
        archive,
        documents,
        source_document_blobs={prepared.logical_path: pdf_bytes},
    )
    existing = deepcopy(documents["document_annotations"][0])
    existing["body"] = "Different destination presentation"
    destination = _Database({"concepts": [], "document_annotations": [existing]})

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(
            archive,
            _mongo(destination),
            source_document_blob_store=SourceDocumentBlobStore(tmp_path / "destination-data"),
        )
    assert any(
        item.collection == "document_annotations" and "same domain ID" in item.reason
        for item in caught.value.report.catalog_conflicts
    )
    assert all(collection.insert_calls == 0 for collection in destination.collections.values())


def test_s5b_relationship_preflight_accepts_a_valid_historical_pdf_version() -> None:
    documents, _pdf_bytes = _visual_portable_documents()
    raw_annotation = documents["document_annotations"][0]
    historical_version = deepcopy(documents["source_documents"][0]["pdf"]["versions"][0])
    current_version = deepcopy(historical_version)
    current_version["version_id"] = "dver_00000000-0000-4000-8000-000000000499"
    raw_document = deepcopy(documents["source_documents"][0])
    raw_document["pdf"]["versions"] = [historical_version, current_version]
    raw_document["pdf"]["current_version_id"] = current_version["version_id"]
    report = db_import.DatabaseImportReport()

    db_import._preflight_reading_annotation_relationships(
        raw_annotations=[raw_annotation],
        raw_notes=[],
        raw_evidence_links=[],
        sources=documents["sources"],
        references=documents["references"],
        source_documents=[raw_document],
        legacy_concepts=documents["concepts"],
        db=_Database(),
        report=report,
    )

    assert report.catalog_conflicts == []

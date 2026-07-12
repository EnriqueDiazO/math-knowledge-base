"""Focused domain, storage, repository, service, and index tests for S2."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import copy
import socket
import stat
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from typing import Any

import pytest
from bson import BSON
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from mathmongo.source_catalog.indexes import SOURCE_CATALOG_INDEXES
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents import storage as storage_module
from mathmongo.source_documents.indexes import SOURCE_DOCUMENT_INDEXES
from mathmongo.source_documents.indexes import SourceDocumentIndexManager
from mathmongo.source_documents.models import MAX_SOURCE_PDF_UPLOAD_BYTES
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import PdfVersion
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.models import normalize_web_url
from mathmongo.source_documents.repository import SourceDocumentRepository
from mathmongo.source_documents.service import DocumentOperationStatus
from mathmongo.source_documents.service import SourceDocumentService
from mathmongo.source_documents.storage import BlobConflictError
from mathmongo.source_documents.storage import BlobValidationError
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def _values(document: Any, path: str) -> list[Any]:
    current = [document]
    for part in path.split("."):
        following: list[Any] = []
        for value in current:
            if isinstance(value, dict) and part in value:
                nested = value[part]
                following.extend(nested if isinstance(nested, list) else [nested])
            elif isinstance(value, list):
                for nested in value:
                    if isinstance(nested, dict) and part in nested:
                        item = nested[part]
                        following.extend(item if isinstance(item, list) else [item])
        current = following
    return current


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    return all(
        any(value == expected for value in _values(document, field))
        for field, expected in query.items()
    )


class _Cursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = [copy.deepcopy(document) for document in documents]

    def sort(self, fields: list[tuple[str, int]]):
        for field, direction in reversed(fields):
            self.documents.sort(
                key=lambda document: (_values(document, field) or [None])[0],
                reverse=direction < 0,
            )
        return self

    def skip(self, amount: int):
        self.documents = self.documents[amount:]
        return self

    def limit(self, amount: int):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


@dataclass
class _WriteResult:
    matched_count: int = 0


class _Collection:
    def __init__(self, name: str, documents: list[dict[str, Any]] | None = None) -> None:
        self.name = name
        self.documents = [copy.deepcopy(document) for document in documents or []]
        self.index_calls: list[tuple[tuple[tuple[str, int], ...], dict[str, Any]]] = []
        self.insert_error: Exception | None = None
        self.insert_calls = 0

    def find_one(self, query: dict[str, Any]):
        return next(
            (copy.deepcopy(item) for item in self.documents if _matches(item, query)),
            None,
        )

    def find(self, query: dict[str, Any]):
        return _Cursor([item for item in self.documents if _matches(item, query)])

    def count_documents(self, query: dict[str, Any]) -> int:
        return sum(_matches(item, query) for item in self.documents)

    def insert_one(self, document: dict[str, Any]) -> None:
        self.insert_calls += 1
        if self.insert_error is not None:
            raise self.insert_error
        if self.name == "source_documents":
            document_id = document.get("document_id")
            if any(item.get("document_id") == document_id for item in self.documents):
                raise DuplicateKeyError("duplicate document_id")
            source_id = document.get("source_id")
            if document.get("kind") == "pdf":
                sha = _values(document, "pdf.versions.sha256")[0]
                if any(
                    item.get("source_id") == source_id
                    and item.get("kind") == "pdf"
                    and sha in _values(item, "pdf.versions.sha256")
                    for item in self.documents
                ):
                    raise DuplicateKeyError("duplicate PDF identity")
            if document.get("kind") == "web":
                normalized = _values(document, "web.url_normalized")[0]
                if any(
                    item.get("source_id") == source_id
                    and item.get("kind") == "web"
                    and normalized in _values(item, "web.url_normalized")
                    for item in self.documents
                ):
                    raise DuplicateKeyError("duplicate web identity")
        self.documents.append(copy.deepcopy(document))

    def replace_one(
        self,
        query: dict[str, Any],
        document: dict[str, Any],
        *,
        upsert: bool,
    ) -> _WriteResult:
        assert not upsert
        for index, existing in enumerate(self.documents):
            if _matches(existing, query):
                self.documents[index] = copy.deepcopy(document)
                return _WriteResult(1)
        return _WriteResult()

    def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str:
        self.index_calls.append((tuple(keys), copy.deepcopy(kwargs)))
        return str(kwargs["name"])


class _Database:
    name = "source-documents-test"

    def __init__(self) -> None:
        self.collections: dict[str, _Collection] = {}
        self.accesses: list[str] = []

    def __getitem__(self, name: str) -> _Collection:
        self.accesses.append(name)
        return self.collections.setdefault(name, _Collection(name))


def _database_with_sources(*sources: Source) -> _Database:
    database = _Database()
    database["sources"].documents.extend(source.model_dump(mode="python") for source in sources)
    return database


def _add_reference(database: _Database, reference: Reference) -> None:
    database["references"].documents.append(reference.model_dump(mode="python"))


def _pdf_version(store: SourceDocumentBlobStore, *, filename: str = "paper.pdf") -> PdfVersion:
    return pdf_version_from_prepared(store.prepare_pdf(PDF_BYTES), original_filename=filename)


def _pdf_document(
    store: SourceDocumentBlobStore,
    source: Source,
    *,
    title: str = "Paper",
) -> SourceDocument:
    version = _pdf_version(store)
    return SourceDocument(
        source_id=source.source_id,
        kind="pdf",
        title=title,
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def test_pdf_models_enforce_ids_payload_discriminator_path_limit_and_utc(tmp_path: Path) -> None:
    source = Source(name="Model Source")
    store = SourceDocumentBlobStore(tmp_path)
    version = _pdf_version(store)
    document = SourceDocument(
        source_id=source.source_id,
        kind=DocumentKind.PDF,
        title="  A   paper  ",
        tags=["Algebra", "algebra", " Topology "],
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )

    assert document.document_id.startswith("doc_")
    assert version.version_id.startswith("dver_")
    assert document.title == "A paper"
    assert document.tags == ["Algebra", "Topology"]
    assert version.logical_path.endswith(f"/{version.sha256}.pdf")
    assert document.model_dump(mode="python").get("pdf") is not None
    assert "pdf_bytes" not in document.model_dump(mode="python")

    with pytest.raises(ValidationError, match="require pdf"):
        SourceDocument(source_id=source.source_id, kind="pdf", title="Broken")
    with pytest.raises(ValidationError, match="forbid web"):
        SourceDocument(
            source_id=source.source_id,
            kind="pdf",
            title="Both",
            pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
            web=WebDocument(url_raw="https://example.test"),
        )
    with pytest.raises(ValidationError, match="canonical content-addressed"):
        PdfVersion(
            sha256="a" * 64,
            size_bytes=1,
            logical_path="/absolute/paper.pdf",
            original_filename="paper.pdf",
        )
    with pytest.raises(ValidationError, match="PDF leaf filename"):
        PdfVersion(
            sha256="a" * 64,
            size_bytes=1,
            logical_path=f"source_documents/blobs/sha256/aa/{'a' * 64}.pdf",
            original_filename="paper.txt",
        )
    with pytest.raises(ValidationError, match="PDF leaf filename"):
        PdfVersion(
            sha256="a" * 64,
            size_bytes=1,
            logical_path=f"source_documents/blobs/sha256/aa/{'a' * 64}.pdf",
            original_filename=f"{'x' * 252}.pdf",
        )
    with pytest.raises(ValidationError):
        PdfVersion(
            sha256="a" * 64,
            size_bytes=MAX_SOURCE_PDF_UPLOAD_BYTES + 1,
            logical_path=f"source_documents/blobs/sha256/aa/{'a' * 64}.pdf",
            original_filename="paper.pdf",
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        SourceDocument(
            source_id=source.source_id,
            kind="web",
            title="Naive",
            web=WebDocument(url_raw="https://example.test"),
            created_at=datetime(2026, 7, 12),
        )


def test_document_archive_and_reactivate_validate_timestamps(tmp_path: Path) -> None:
    source = Source(name="Status Source")
    document = _pdf_document(SourceDocumentBlobStore(tmp_path), source)
    archived = document.archived(at=document.updated_at + timedelta(seconds=1))
    active = archived.reactivated(at=archived.updated_at + timedelta(seconds=1))

    assert archived.status == DocumentStatus.ARCHIVED
    assert archived.archived_at == archived.updated_at
    assert active.status == DocumentStatus.ACTIVE
    assert active.archived_at is None
    with pytest.raises(ValidationError, match="timezone-aware"):
        document.archived(at=datetime(2026, 7, 12))


@pytest.mark.parametrize("url", ["file:///tmp/a", "data:application/pdf,x", "javascript:alert(1)"])
def test_web_model_rejects_non_http_schemes_without_network(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network access")),
    )
    with pytest.raises(ValueError, match="http or https"):
        normalize_web_url(url)


def test_web_normalization_is_conservative_and_credential_free() -> None:
    assert normalize_web_url("HTTPS://Example.TEST:443/path?q=1#fragment") == (
        "https://example.test/path?q=1"
    )
    assert normalize_web_url("http://example.test") == "http://example.test/"
    with pytest.raises(ValueError, match="credentials"):
        normalize_web_url("https://user:secret@example.test/private")
    with pytest.raises(ValueError, match="invalid port"):
        normalize_web_url("https://example.test:99999/")


def test_blob_validation_publication_dedup_and_private_permissions(tmp_path: Path) -> None:
    store = SourceDocumentBlobStore(tmp_path)
    prepared = store.prepare_pdf(PDF_BYTES)

    first = store.publish(prepared)
    second = SourceDocumentBlobStore(tmp_path).publish(prepared)
    path = store.path_for_sha(prepared.sha256)

    assert first.created is True
    assert second.created is False
    assert path.read_bytes() == PDF_BYTES
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert all(
        stat.S_IMODE(directory.stat().st_mode) == 0o700
        for directory in (
            store.documents_root,
            store.documents_root / "blobs",
            store.blob_root,
            path.parent,
        )
    )
    assert not list(path.parent.glob(".pending-*"))


def test_blob_validation_rejects_empty_header_nonbytes_and_limit() -> None:
    with pytest.raises(BlobValidationError, match="cannot be empty"):
        SourceDocumentBlobStore.prepare_pdf(b"")
    with pytest.raises(BlobValidationError, match="valid %PDF-"):
        SourceDocumentBlobStore.prepare_pdf(b"not a pdf")
    with pytest.raises(BlobValidationError, match="must be bytes"):
        SourceDocumentBlobStore.prepare_pdf(bytearray(PDF_BYTES))  # type: ignore[arg-type]
    with pytest.raises(BlobValidationError, match="exceeds"):
        SourceDocumentBlobStore.prepare_pdf(PDF_BYTES, max_bytes=len(PDF_BYTES) - 1)
    assert SourceDocumentBlobStore.prepare_pdf(
        PDF_BYTES,
        max_bytes=len(PDF_BYTES),
    ).size_bytes == len(PDF_BYTES)


def test_blob_publication_failure_is_atomic_and_cleans_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = SourceDocumentBlobStore(tmp_path)
    prepared = store.prepare_pdf(PDF_BYTES)
    destination = store.path_for_sha(prepared.sha256)

    monkeypatch.setattr(
        storage_module.os,
        "link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("link failed")),
    )
    with pytest.raises(OSError, match="link failed"):
        store.publish(prepared)

    assert not destination.exists()
    assert not list(destination.parent.glob(".pending-*"))


def test_blob_symlink_and_tamper_fail_closed_in_read_and_inspection(tmp_path: Path) -> None:
    store = SourceDocumentBlobStore(tmp_path)
    prepared = store.prepare_pdf(PDF_BYTES)
    store.publish(prepared)
    version = pdf_version_from_prepared(prepared, original_filename="paper.pdf")
    path = store.path_for_sha(prepared.sha256)
    path.unlink()
    target = tmp_path / "outside.pdf"
    target.write_bytes(PDF_BYTES)
    path.symlink_to(target)

    with pytest.raises((BlobConflictError, ValueError)):
        store.read_version(version)
    inspected = store.inspect_version(version)
    assert inspected.ok is False
    assert inspected.issues


def test_blob_integrity_checks_content_permissions_and_private_directories(tmp_path: Path) -> None:
    store = SourceDocumentBlobStore(tmp_path)
    prepared = store.prepare_pdf(PDF_BYTES)
    store.publish(prepared)
    version = pdf_version_from_prepared(prepared, original_filename="paper.pdf")
    path = store.path_for_sha(prepared.sha256)

    assert store.inspect_version(version).ok is True
    path.chmod(0o644)
    assert store.inspect_version(version).ok is False
    path.chmod(0o600)
    path.parent.chmod(0o755)
    inspected = store.inspect_version(version)
    assert inspected.ok is False
    assert "directory_permissions" in inspected.issues


def test_repository_roundtrip_paging_metadata_and_status(tmp_path: Path) -> None:
    source = Source(name="Repository Source")
    database = _database_with_sources(source)
    repository = SourceDocumentRepository(database)
    first = repository.insert(_pdf_document(SourceDocumentBlobStore(tmp_path), source))
    second = repository.insert(
        SourceDocument(
            source_id=source.source_id,
            kind="web",
            title="Web",
            web=WebDocument(url_raw="https://example.test/resource"),
        )
    )

    page = repository.list(source.source_id, page=1, page_size=1)
    updated = repository.update_metadata(
        first.document_id,
        {"title": "Updated", "tags": ["one", "ONE", "two"]},
    )
    archived = repository.archive(first.document_id)
    repeated = repository.archive(first.document_id)
    active = repository.reactivate(first.document_id)

    assert page.total == 2
    assert page.pages == 2
    assert len(page.items) == 1
    assert updated is not None and updated.title == "Updated"
    assert updated.tags == ["one", "two"]
    assert archived is not None and archived.status == DocumentStatus.ARCHIVED
    assert repeated is not None and repeated.status == DocumentStatus.ARCHIVED
    assert active is not None and active.status == DocumentStatus.ACTIVE
    assert repository.find_web_identity(
        source.source_id,
        second.web.url_normalized,
    ) == (second,)
    with pytest.raises(ValueError, match="Unsupported"):
        repository.update_metadata(first.document_id, {"source_id": Source(name="Other").source_id})


def test_repository_hydrates_top_level_and_nested_bson_datetimes(tmp_path: Path) -> None:
    source = Source(name="BSON Source")
    document = _pdf_document(SourceDocumentBlobStore(tmp_path), source)
    bson_document = BSON(BSON.encode(document.model_dump(mode="python"))).decode()
    assert bson_document["created_at"].tzinfo is None
    assert bson_document["pdf"]["versions"][0]["created_at"].tzinfo is None
    database = _Database()
    database["source_documents"].documents.append(bson_document)

    loaded = SourceDocumentRepository(database).get_by_id(document.document_id)

    assert loaded is not None
    assert loaded.created_at.tzinfo == timezone.utc
    assert loaded.pdf.current_version.created_at.tzinfo == timezone.utc


def test_source_document_indexes_are_separate_and_exactly_scoped() -> None:
    database = _Database()
    names = SourceDocumentIndexManager(database).ensure()
    calls = database["source_documents"].index_calls

    assert len(names) == len(SOURCE_DOCUMENT_INDEXES) == 5
    assert all(spec.collection != "source_documents" for spec in SOURCE_CATALOG_INDEXES)
    assert {kwargs["name"] for _keys, kwargs in calls} == set(names)
    pdf_call = next(kwargs for _keys, kwargs in calls if "pdf_sha" in kwargs["name"])
    web_call = next(kwargs for _keys, kwargs in calls if "web_url" in kwargs["name"])
    assert pdf_call["unique"] is True
    assert pdf_call["partialFilterExpression"] == {"kind": "pdf"}
    assert web_call["partialFilterExpression"] == {"kind": "web"}
    assert set(database.collections) == {"source_documents"}


def test_service_pdf_create_identical_conflict_and_global_blob_dedup(tmp_path: Path) -> None:
    first_source = Source(name="First")
    second_source = Source(name="Second")
    database = _database_with_sources(first_source, second_source)
    sources_before = copy.deepcopy(database["sources"].documents)
    service = SourceDocumentService(database, storage=SourceDocumentBlobStore(tmp_path))

    first = service.create_pdf_document(
        source_id=first_source.source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Paper",
    )
    identical = service.create_pdf_document(
        source_id=first_source.source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Paper",
    )
    conflict = service.create_pdf_document(
        source_id=first_source.source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Different metadata",
    )
    other_source = service.create_pdf_document(
        source_id=second_source.source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Paper",
    )

    assert first.status == DocumentOperationStatus.CREATED
    assert first.metadata_persisted and first.blob_created
    assert identical.status == DocumentOperationStatus.IDENTICAL
    assert conflict.status == DocumentOperationStatus.CONFLICT
    assert other_source.status == DocumentOperationStatus.CREATED
    assert other_source.metadata_persisted and not other_source.blob_created
    assert database["source_documents"].count_documents({}) == 2
    assert all("pdf_bytes" not in document for document in database["source_documents"].documents)
    assert database["sources"].documents == sources_before
    assert "concepts" not in database.collections


def test_service_rejects_invalid_pdf_missing_source_and_foreign_reference(tmp_path: Path) -> None:
    selected = Source(name="Selected")
    other = Source(name="Other")
    database = _database_with_sources(selected, other)
    foreign = Reference(title="Foreign", source_ids=[other.source_id])
    _add_reference(database, foreign)
    service = SourceDocumentService(database, storage=SourceDocumentBlobStore(tmp_path))

    missing = service.create_pdf_document(
        source_id=Source(name="Missing").source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Missing",
    )
    invalid = service.create_pdf_document(
        source_id=selected.source_id,
        pdf_bytes=b"not-pdf",
        original_filename="paper.pdf",
        title="Invalid",
    )
    wrong_reference = service.create_pdf_document(
        source_id=selected.source_id,
        reference_id=foreign.reference_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Wrong association",
    )

    assert missing.status == DocumentOperationStatus.NOT_FOUND
    assert invalid.status == DocumentOperationStatus.ERROR
    assert wrong_reference.status == DocumentOperationStatus.ERROR
    assert database["source_documents"].documents == []
    assert not (tmp_path / "source_documents").exists()


def test_service_reports_partial_when_metadata_fails_after_new_blob(tmp_path: Path) -> None:
    source = Source(name="Partial")
    database = _database_with_sources(source)
    database["source_documents"].insert_error = RuntimeError("Mongo unavailable")
    store = SourceDocumentBlobStore(tmp_path)
    service = SourceDocumentService(database, storage=store)

    result = service.create_pdf_document(
        source_id=source.source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Partial",
    )

    prepared = store.prepare_pdf(PDF_BYTES)
    assert result.status == DocumentOperationStatus.PARTIAL
    assert result.blob_created is True
    assert result.metadata_persisted is False
    assert store.path_for_sha(prepared.sha256).read_bytes() == PDF_BYTES
    assert database["source_documents"].documents == []


def test_service_storage_errors_do_not_expose_absolute_paths(tmp_path: Path) -> None:
    source = Source(name="Safe diagnostics")
    database = _database_with_sources(source)
    store = SourceDocumentBlobStore(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    store.documents_root.symlink_to(outside, target_is_directory=True)
    service = SourceDocumentService(database, storage=store)

    result = service.create_pdf_document(
        source_id=source.source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Unsafe storage",
    )

    assert result.status == DocumentOperationStatus.ERROR
    assert str(tmp_path) not in result.message
    assert "unsafe" in result.message


def test_service_web_is_network_free_and_normalized_duplicate_is_identical(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = Source(name="Web Source")
    database = _database_with_sources(source)
    service = SourceDocumentService(database, storage=SourceDocumentBlobStore(tmp_path))
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network access")),
    )

    created = service.create_web_document(
        source_id=source.source_id,
        url_raw="HTTPS://Example.TEST:443/resource#section",
        title="Web",
    )
    identical = service.create_web_document(
        source_id=source.source_id,
        url_raw="https://example.test/resource",
        title="Web",
    )

    assert created.status == DocumentOperationStatus.CREATED
    assert created.value.web.url_normalized == "https://example.test/resource"
    assert identical.status == DocumentOperationStatus.IDENTICAL
    for url in ("file:///tmp/a", "data:text/plain,a", "javascript:alert(1)"):
        rejected = service.create_web_document(
            source_id=source.source_id,
            url_raw=url,
            title="Rejected",
        )
        assert rejected.status == DocumentOperationStatus.ERROR
    assert database["source_documents"].count_documents({}) == 1


def test_service_update_archive_reactivate_and_reference_guard(tmp_path: Path) -> None:
    source = Source(name="Mutable")
    other = Source(name="Other")
    database = _database_with_sources(source, other)
    valid_reference = Reference(title="Valid", source_ids=[source.source_id])
    foreign_reference = Reference(title="Foreign", source_ids=[other.source_id])
    _add_reference(database, valid_reference)
    _add_reference(database, foreign_reference)
    service = SourceDocumentService(database, storage=SourceDocumentBlobStore(tmp_path))
    created = service.create_web_document(
        source_id=source.source_id,
        url_raw="https://example.test",
        title="Before",
    )

    updated = service.update_document_metadata(
        created.value.document_id,
        {"title": "After", "reference_id": valid_reference.reference_id},
    )
    blocked = service.update_document_metadata(
        created.value.document_id,
        {"reference_id": foreign_reference.reference_id},
    )
    archived = service.archive_document(created.value.document_id)
    repeated_archive = service.archive_document(created.value.document_id)
    active = service.reactivate_document(created.value.document_id)
    repeated_active = service.reactivate_document(created.value.document_id)

    assert updated.status == DocumentOperationStatus.SUCCESS
    assert updated.value.title == "After"
    assert blocked.status == DocumentOperationStatus.ERROR
    assert blocked.value.reference_id == valid_reference.reference_id
    assert archived.status == DocumentOperationStatus.SUCCESS
    assert repeated_archive.status == DocumentOperationStatus.IDENTICAL
    assert active.status == DocumentOperationStatus.SUCCESS
    assert repeated_active.status == DocumentOperationStatus.IDENTICAL


def test_service_integrity_and_pdf_payload_detect_tamper(tmp_path: Path) -> None:
    source = Source(name="Integrity")
    database = _database_with_sources(source)
    store = SourceDocumentBlobStore(tmp_path)
    service = SourceDocumentService(database, storage=store)
    created = service.create_pdf_document(
        source_id=source.source_id,
        pdf_bytes=PDF_BYTES,
        original_filename="paper.pdf",
        title="Integrity",
    )
    document = created.value

    healthy = service.inspect_document_integrity(document.document_id)
    payload = service.read_pdf_document(document.document_id)
    path = store.path_for_version(document.pdf.current_version)
    path.write_bytes(b"%PDF-tampered")
    path.chmod(0o600)
    damaged = service.inspect_document_integrity(document.document_id)

    assert healthy.ok is True
    assert payload.pdf_bytes is PDF_BYTES or payload.pdf_bytes == PDF_BYTES
    assert payload.sha256 == document.pdf.current_version.sha256
    assert damaged.ok is False
    assert damaged.issues
    with pytest.raises((BlobConflictError, BlobValidationError)):
        service.read_pdf_document(document.document_id)

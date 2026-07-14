"""Focused API-contract tests for the isolated S5A backend."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mathmongo.advanced_reader.app import create_app
from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.document_page_maps.service import PageMapOperationStatus
from mathmongo.document_page_maps.service import PageMapServiceResult
from mathmongo.reading_space.models import DocumentReadingState
from mathmongo.reading_space.models import ReadingStatus
from mathmongo.reading_space.service import ReaderContext
from mathmongo.reading_space.service import ReadingOperationStatus
from mathmongo.reading_space.service import ReadingServiceResult
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import WebDocument
from mathmongo.source_documents.service import DocumentIntegrityInspection
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared

BASE_URL = "http://127.0.0.1:8766"
API_PREFIX = "/api/advanced-reader"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


class FakeReadingService:
    def __init__(self, contexts: dict[str, ReaderContext]) -> None:
        self.contexts = contexts
        self.context_calls: list[str] = []
        self.page_updates: list[tuple[str, int]] = []

    def get_reader_context(
        self,
        document_id: str,
        *,
        user_scope: str = "local",
    ) -> ReadingServiceResult[ReaderContext]:
        assert user_scope == "local"
        self.context_calls.append(document_id)
        context = self.contexts.get(document_id)
        if context is None:
            return ReadingServiceResult(ReadingOperationStatus.NOT_FOUND)
        if context.document.status.value == "archived":
            return ReadingServiceResult(ReadingOperationStatus.ARCHIVED, context)
        return ReadingServiceResult(ReadingOperationStatus.SUCCESS, context)

    def update_current_page(
        self,
        document_id: str,
        current_page: int,
        *,
        user_scope: str = "local",
        total_pages: int | None = None,
    ) -> ReadingServiceResult[DocumentReadingState]:
        assert user_scope == "local"
        assert total_pages is None
        self.page_updates.append((document_id, current_page))
        context = self.contexts.get(document_id)
        if context is None:
            return ReadingServiceResult(ReadingOperationStatus.NOT_FOUND)
        known_total = getattr(context.reading_state, "total_pages", None)
        if isinstance(known_total, int) and current_page > known_total:
            return ReadingServiceResult(
                ReadingOperationStatus.INVALID_STATE,
                message="current_page cannot exceed total_pages",
            )
        values = (
            context.reading_state.model_dump(mode="python")
            if context.reading_state is not None
            else {
                "document_id": context.document.document_id,
                "source_id": context.document.source_id,
                "reference_id": context.document.reference_id,
            }
        )
        values.update(
            {
                "status": ReadingStatus.IN_PROGRESS,
                "current_page": current_page,
                "total_pages": known_total,
            }
        )
        state = DocumentReadingState.model_validate(values)
        self.contexts[document_id] = ReaderContext(
            document=context.document,
            source=context.source,
            reference=context.reference,
            reading_state=state,
            effective_status=state.status,
            openable=context.openable,
        )
        return ReadingServiceResult(ReadingOperationStatus.SUCCESS, state)


class FakeDocumentService:
    def __init__(self, storage: SourceDocumentBlobStore) -> None:
        self.storage = storage
        self.inspections: dict[str, DocumentIntegrityInspection | Exception] = {}
        self.inspection_calls: list[str] = []
        self.full_read_calls: list[str] = []

    def inspect_document_integrity(self, document_id: str) -> DocumentIntegrityInspection:
        self.inspection_calls.append(document_id)
        configured = self.inspections.get(document_id)
        if isinstance(configured, Exception):
            raise configured
        if configured is not None:
            return configured
        return DocumentIntegrityInspection(document_id, True, ())

    def read_pdf_document(self, document_id: str):
        self.full_read_calls.append(document_id)
        raise AssertionError("Advanced Reader must not load a full PDF through read_pdf_document")


class FakePageMapService:
    def __init__(self) -> None:
        self.labels: dict[tuple[str, int], str] = {}
        self.calls: list[tuple[str, int]] = []
        self.error: Exception | None = None

    def compute_page_label(self, document_id: str, pdf_page: int):
        self.calls.append((document_id, pdf_page))
        if self.error is not None:
            raise self.error
        label = self.labels.get((document_id, pdf_page))
        if label is None:
            return PageMapServiceResult(PageMapOperationStatus.NOT_FOUND)
        return PageMapServiceResult(
            PageMapOperationStatus.SUCCESS,
            SimpleNamespace(book_page_label=label),
        )


@dataclass
class BackendHarness:
    app: Any
    dependencies: AdvancedReaderDependencies
    document_service: FakeDocumentService
    reading_service: FakeReadingService
    page_map_service: FakePageMapService
    source: Source
    reference: Reference
    pdf: SourceDocument
    web: SourceDocument
    archived: SourceDocument
    pdf_bytes: bytes
    health_calls: list[str]

    def client(self, *, raise_server_exceptions: bool = False) -> TestClient:
        return TestClient(
            self.app,
            base_url=BASE_URL,
            raise_server_exceptions=raise_server_exceptions,
        )


def _reading_state(document: SourceDocument, *, total_pages: int | None = 10):
    return DocumentReadingState(
        document_id=document.document_id,
        source_id=document.source_id,
        reference_id=document.reference_id,
        status=ReadingStatus.IN_PROGRESS,
        current_page=2 if document.kind.value == "pdf" else None,
        total_pages=total_pages if document.kind.value == "pdf" else None,
        open_count=1,
    )


def _context(
    document: SourceDocument,
    source: Source,
    reference: Reference | None,
) -> ReaderContext:
    state = _reading_state(document)
    return ReaderContext(
        document=document,
        source=source,
        reference=reference,
        reading_state=state,
        effective_status=state.status,
        openable=document.status.value == "active",
    )


def make_backend_harness(
    tmp_path: Path,
    *,
    pdf_bytes: bytes = PDF_BYTES,
    original_filename: str = 'résumé "proof".pdf',
    frontend_ready: bool = True,
) -> BackendHarness:
    source = Source(name="Focused Source")
    reference = Reference(source_ids=[source.source_id], title="Focused Reference")
    storage = SourceDocumentBlobStore(tmp_path / "XDG data with spaces")
    prepared = storage.prepare_pdf(pdf_bytes)
    storage.publish(prepared)
    version = pdf_version_from_prepared(prepared, original_filename=original_filename)
    pdf = SourceDocument(
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind="pdf",
        title="Focused PDF",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )
    web = SourceDocument(
        source_id=source.source_id,
        kind="web",
        title="Focused Web",
        web=WebDocument(url_raw="https://example.test/resource"),
    )
    archived = SourceDocument(
        source_id=source.source_id,
        kind="pdf",
        title="Archived PDF",
        status="archived",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )
    contexts = {
        pdf.document_id: _context(pdf, source, reference),
        web.document_id: _context(web, source, None),
        archived.document_id: _context(archived, source, None),
    }
    reading_service = FakeReadingService(contexts)
    document_service = FakeDocumentService(storage)
    page_map_service = FakePageMapService()
    health_calls: list[str] = []
    frontend_root = tmp_path / "packaged frontend"
    if frontend_ready:
        (frontend_root / "assets").mkdir(parents=True)
        (frontend_root / "third-party").mkdir()
        (frontend_root / "index.html").write_text(
            '<!doctype html><link rel="stylesheet" href="/assets/app-abc.css">'
            '<script type="module" src="/assets/app-abc.js"></script>'
        )
        (frontend_root / "assets/app-abc.js").write_text("export {};")
        (frontend_root / "assets/app-abc.css").write_text(":root{}")
        (frontend_root / "assets/pdf.worker.min-worker123.mjs").write_text("export {};")
        (frontend_root / "favicon.svg").write_text("<svg></svg>")
        for name in (
            "THIRD_PARTY_NOTICES.txt",
            "pdfjs-LICENSE.txt",
            "react-LICENSE.txt",
            "react-dom-LICENSE.txt",
        ):
            (frontend_root / "third-party" / name).write_text("license")

    def health_check() -> bool:
        health_calls.append("ping")
        return True

    dependencies = AdvancedReaderDependencies(
        database_name="FocusedDb",
        document_service=document_service,  # type: ignore[arg-type]
        reading_service=reading_service,  # type: ignore[arg-type]
        page_map_service=page_map_service,  # type: ignore[arg-type]
        frontend_root=frontend_root,
        health_check=health_check,
    )
    return BackendHarness(
        app=create_app(dependencies),
        dependencies=dependencies,
        document_service=document_service,
        reading_service=reading_service,
        page_map_service=page_map_service,
        source=source,
        reference=reference,
        pdf=pdf,
        web=web,
        archived=archived,
        pdf_bytes=pdf_bytes,
        health_calls=health_calls,
    )


@pytest.fixture
def harness(tmp_path: Path) -> BackendHarness:
    return make_backend_harness(tmp_path)


def _error_code(response: Any) -> str:
    payload = response.json()
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message", "request_id"}
    assert payload["error"]["request_id"]
    return str(payload["error"]["code"])


def test_app_factory_requires_explicit_dependencies_and_is_lazy(harness: BackendHarness) -> None:
    with pytest.raises(ValueError, match="explicit"):
        create_app(None)  # type: ignore[arg-type]

    assert harness.app.state.advanced_reader_dependencies is harness.dependencies
    assert harness.document_service.inspection_calls == []
    assert harness.reading_service.context_calls == []
    assert harness.page_map_service.calls == []
    assert harness.health_calls == []


def test_health_is_bounded_and_read_only(harness: BackendHarness) -> None:
    with harness.client() as client:
        response = client.get(f"{API_PREFIX}/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "mathmongo-advanced-reader",
        "database": "FocusedDb",
        "frontend_ready": True,
    }
    assert harness.health_calls == ["ping"]
    assert harness.document_service.inspection_calls == []
    assert harness.reading_service.context_calls == []
    assert harness.reading_service.page_updates == []


def test_pdf_metadata_is_typed_complete_and_contains_no_storage_values(
    harness: BackendHarness,
    tmp_path: Path,
) -> None:
    harness.page_map_service.labels[(harness.pdf.document_id, 2)] = "iv"
    with harness.client() as client:
        response = client.get(f"{API_PREFIX}/documents/{harness.pdf.document_id}")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "document_id",
        "title",
        "kind",
        "status",
        "source",
        "reference",
        "version",
        "reading_state",
        "page_label",
        "integrity",
        "capabilities",
    }
    assert payload["document_id"] == harness.pdf.document_id
    assert payload["kind"] == "pdf" and payload["status"] == "active"
    assert payload["source"] == {
        "source_id": harness.source.source_id,
        "name": harness.source.name,
    }
    assert payload["reference"]["reference_id"] == harness.reference.reference_id
    assert payload["version"]["sha256"] == harness.pdf.pdf.current_version.sha256
    assert payload["reading_state"]["current_page"] == 2
    assert payload["page_label"] == {
        "pdf_page": 2,
        "book_page_label": "iv",
        "display_label": "Book page iv · PDF page 2",
    }
    assert payload["capabilities"]["temporary_selection_geometry"] is True
    assert payload["capabilities"]["persistent_highlights"] is False
    serialized = response.text
    for forbidden in (
        str(tmp_path),
        str(harness.document_service.storage.documents_root),
        harness.pdf.pdf.current_version.logical_path,
        "logical_path",
        "pdf_bytes",
        "mongodb://",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("target", "status_code", "code"),
    [
        ("missing", 404, "document_not_found"),
        ("invalid", 422, "invalid_document_id"),
        ("web", 415, "document_not_pdf"),
        ("archived", 409, "document_archived"),
    ],
)
def test_document_errors_are_stable(
    harness: BackendHarness,
    target: str,
    status_code: int,
    code: str,
) -> None:
    identifiers = {
        "missing": SourceDocument(
            source_id=harness.source.source_id,
            kind="web",
            title="Missing identity",
            web=WebDocument(url_raw="https://example.test/missing"),
        ).document_id,
        "invalid": "doc_not-a-canonical-uuid",
        "web": harness.web.document_id,
        "archived": harness.archived.document_id,
    }
    with harness.client() as client:
        response = client.get(f"{API_PREFIX}/documents/{identifiers[target]}")

    assert response.status_code == status_code
    assert _error_code(response) == code


@pytest.mark.parametrize(
    ("issues", "status_code", "code"),
    [
        (("sha256_mismatch",), 409, "integrity_error"),
        (("blob_missing",), 404, "blob_missing"),
    ],
)
def test_metadata_integrity_and_missing_blob_errors_are_typed(
    harness: BackendHarness,
    issues: tuple[str, ...],
    status_code: int,
    code: str,
) -> None:
    harness.document_service.inspections[harness.pdf.document_id] = DocumentIntegrityInspection(
        harness.pdf.document_id,
        False,
        issues,
    )
    with harness.client() as client:
        response = client.get(f"{API_PREFIX}/documents/{harness.pdf.document_id}")

    assert response.status_code == status_code
    assert _error_code(response) == code


def test_reading_state_is_read_only_until_an_explicit_valid_page_save(
    harness: BackendHarness,
) -> None:
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/reading-state"
    with harness.client() as client:
        before = client.get(path)
        saved = client.put(
            f"{path}/page",
            json={"pdf_page": 4},
            headers={"Origin": BASE_URL},
        )
        after = client.get(path)

    assert before.status_code == saved.status_code == after.status_code == 200
    assert before.json()["current_page"] == 2
    assert saved.json()["current_page"] == after.json()["current_page"] == 4
    assert harness.reading_service.page_updates == [(harness.pdf.document_id, 4)]


@pytest.mark.parametrize("value", [0, -1, True, "2", 2.5, None])
def test_invalid_page_payloads_are_rejected_without_writes(
    harness: BackendHarness,
    value: object,
) -> None:
    with harness.client() as client:
        response = client.put(
            f"{API_PREFIX}/documents/{harness.pdf.document_id}/reading-state/page",
            json={"pdf_page": value},
            headers={"Origin": BASE_URL},
        )

    assert response.status_code == 422
    assert _error_code(response) == "page_invalid"
    assert harness.reading_service.page_updates == []


def test_page_above_known_total_is_a_page_invalid_error(harness: BackendHarness) -> None:
    with harness.client() as client:
        response = client.put(
            f"{API_PREFIX}/documents/{harness.pdf.document_id}/reading-state/page",
            json={"pdf_page": 11},
            headers={"Origin": BASE_URL},
        )

    assert response.status_code == 422
    assert _error_code(response) == "page_invalid"


def test_page_map_resolves_and_absence_remains_nonblocking(harness: BackendHarness) -> None:
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/page-label"
    harness.page_map_service.labels[(harness.pdf.document_id, 9)] = "1"
    with harness.client() as client:
        mapped = client.get(path, params={"pdf_page": "9"})
        unmapped = client.get(path, params={"pdf_page": "10"})

    assert mapped.status_code == unmapped.status_code == 200
    assert mapped.json() == {
        "pdf_page": 9,
        "book_page_label": "1",
        "display_label": "Book page 1 · PDF page 9",
    }
    assert unmapped.json() == {
        "pdf_page": 10,
        "book_page_label": None,
        "display_label": "PDF page 10",
    }


def test_invalid_page_map_query_is_typed_and_does_not_create_a_map(
    harness: BackendHarness,
) -> None:
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/page-label"
    with harness.client() as client:
        response = client.get(path, params={"pdf_page": "0"})

    assert response.status_code == 422
    assert _error_code(response) == "page_invalid"
    assert harness.page_map_service.calls == []


def test_dependency_construction_and_health_do_not_access_collections_or_indexes(
    tmp_path: Path,
) -> None:
    class StrictDatabase:
        def __init__(self) -> None:
            self.collection_accesses: list[str] = []

        def __getitem__(self, name: str):
            self.collection_accesses.append(name)
            raise AssertionError(f"collection access is forbidden during construction: {name}")

    database = StrictDatabase()
    dependencies = AdvancedReaderDependencies.from_database(
        database,
        database_name="LazyDb",
        frontend_root=tmp_path / "missing frontend",
        health_check=lambda: True,
    )
    app = create_app(dependencies)
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get(f"{API_PREFIX}/health")

    assert response.status_code == 200
    assert response.json()["frontend_ready"] is False
    assert database.collection_accesses == []

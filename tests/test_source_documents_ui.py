"""Focused fake-render and static safety tests for the Source Documents UI."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from editor.pdf_preview import PdfPreviewPayload
from editor.pdf_preview import get_pdf_preview
from editor.pdf_preview import store_pdf_preview
from editor.source_catalog import edit_source_page
from editor.source_catalog.document_ui import DOCUMENT_PREVIEW_SUBJECT
from editor.source_catalog.document_ui import PDF_PREVIEW_NAMESPACE
from editor.source_catalog.document_ui import _operation_token
from editor.source_catalog.document_ui import render_source_documents
from editor.source_catalog.document_ui import uploaded_pdf_bytes
from editor.source_catalog.document_ui import uploaded_pdf_filename
from editor.source_catalog.state import ACTIVE_DATABASE_IDENTITY
from editor.source_catalog.state import state_key
from editor.source_catalog.state import sync_database_state
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import PageResult
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.repository import SourceDocumentPage
from mathmongo.source_documents.service import DocumentIntegrityInspection
from mathmongo.source_documents.service import DocumentOperationResult
from mathmongo.source_documents.service import DocumentOperationStatus
from mathmongo.source_documents.service import DocumentPdfPayload
from mathmongo.source_documents.storage import MAX_SOURCE_PDF_UPLOAD_BYTES
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared

ROOT = Path(__file__).resolve().parents[1]
VALID_PDF = b"%PDF-1.7\nsource document UI\n%%EOF\n"


class FakeUploadedFile:
    def __init__(self, data: bytes, *, name: str = "paper.pdf", size: int | None = None) -> None:
        self.data = data
        self.name = name
        self.size = len(data) if size is None else size
        self.position = 0
        self.read_calls: list[int] = []

    def read(self, amount: int = -1) -> bytes:
        self.read_calls.append(amount)
        if amount < 0:
            amount = len(self.data) - self.position
        result = self.data[self.position : self.position + amount]
        self.position += len(result)
        return result

    def tell(self) -> int:
        return self.position

    def seek(self, position: int) -> None:
        self.position = position


class ExplodingOversizeUpload:
    name = "large.pdf"
    size = MAX_SOURCE_PDF_UPLOAD_BYTES + 1

    def read(self, _amount: int) -> bytes:
        raise AssertionError("declared oversize upload must not be materialized")


class FakeUI:
    def __init__(
        self,
        *,
        values: dict[str, Any] | None = None,
        clicked: set[str] | None = None,
        submitted: set[str] | None = None,
        uploaded: Any = None,
        confirmed: bool = True,
    ) -> None:
        self.values = dict(values or {})
        self.clicked = set(clicked or ())
        self.submitted = set(submitted or ())
        self.uploaded = uploaded
        self.confirmed = confirmed
        self.file_uploader_kwargs: dict[str, Any] = {}
        self.session_state: dict[str, Any] = {}
        self.messages: list[tuple[str, str]] = []
        self.pdf_calls: list[tuple[bytes, dict[str, Any]]] = []
        self.download_calls: list[dict[str, Any]] = []
        self.links: list[str] = []
        self.rows: list[list[dict[str, Any]]] = []
        self.reruns = 0

    def _message(self, level: str, value: object) -> None:
        self.messages.append((level, str(value)))

    def _value(self, key: str, default: Any) -> Any:
        value = self.values.get(key, self.session_state.get(key, default))
        self.session_state[key] = value
        return value

    def subheader(self, value: object) -> None:
        self._message("subheader", value)

    def info(self, value: object) -> None:
        self._message("info", value)

    def success(self, value: object) -> None:
        self._message("success", value)

    def warning(self, value: object) -> None:
        self._message("warning", value)

    def error(self, value: object) -> None:
        self._message("error", value)

    def caption(self, value: object) -> None:
        self._message("caption", value)

    def write(self, value: object) -> None:
        self._message("write", value)

    def tabs(self, labels):
        return [nullcontext(self) for _label in labels]

    def expander(self, *_args, **_kwargs):
        return nullcontext(self)

    def form(self, *_args, **_kwargs):
        return nullcontext(self)

    def selectbox(self, _label, options, *, key, index=0, **_kwargs):
        return self._value(key, list(options)[index])

    def text_input(self, _label, *, key, value="", **_kwargs):
        return self._value(key, value)

    def text_area(self, _label, *, key, value="", **_kwargs):
        return self._value(key, value)

    def checkbox(self, label, *, key, value=False, **_kwargs):
        default = self.confirmed if str(label).startswith("Confirmo") else value
        return bool(self._value(key, default))

    def number_input(self, _label, *, key, value=1, **_kwargs):
        return self._value(key, value)

    def file_uploader(self, _label, *, key, **_kwargs):
        self.file_uploader_kwargs = dict(_kwargs)
        self.session_state.setdefault(key, self.uploaded)
        return self.uploaded

    def form_submit_button(self, label, **_kwargs):
        return label in self.submitted

    def button(self, label, *, key, **_kwargs):
        return key in self.clicked or label in self.clicked

    def dataframe(self, rows, **_kwargs) -> None:
        self.rows.append(list(rows))

    def link_button(self, _label, url) -> None:
        self.links.append(str(url))

    def pdf(self, data: bytes, **kwargs) -> None:
        self.pdf_calls.append((data, kwargs))

    def download_button(self, _label, **kwargs) -> None:
        self.download_calls.append(kwargs)

    def rerun(self) -> None:
        self.reruns += 1


class FakeReferenceRepository:
    def __init__(self, references: tuple[Reference, ...] = ()) -> None:
        self.references = references

    def list(self, *, source_id: str, page: int, page_size: int) -> PageResult[Reference]:
        assert page == 1
        assert page_size == 100
        items = tuple(item for item in self.references if source_id in item.source_ids)
        return PageResult(items, page=1, page_size=100, total=len(items))


def _pdf_document(source: Source, data: bytes = VALID_PDF) -> SourceDocument:
    prepared = SourceDocumentBlobStore.prepare_pdf(data)
    version = pdf_version_from_prepared(prepared, original_filename="paper.pdf")
    return SourceDocument(
        source_id=source.source_id,
        kind="pdf",
        title="Paper",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
    )


def _web_document(source: Source, *, reference_id: str | None = None) -> SourceDocument:
    return SourceDocument(
        source_id=source.source_id,
        reference_id=reference_id,
        kind="web",
        title="Web resource",
        web={"url_raw": "HTTPS://EXAMPLE.TEST:443/resource#fragment"},
    )


class FakeDocumentService:
    def __init__(self, source: Source, documents: tuple[SourceDocument, ...] = ()) -> None:
        self.source = source
        self.documents = documents
        self.pdf_bytes = VALID_PDF
        self.pdf_creates: list[dict[str, Any]] = []
        self.web_creates: list[dict[str, Any]] = []
        self.updates: list[tuple[str, dict[str, Any]]] = []
        self.archives: list[str] = []
        self.reactivations: list[str] = []
        self.inspections: list[str] = []

    def list_source_documents(self, source_id: str, **kwargs) -> SourceDocumentPage:
        assert source_id == self.source.source_id
        items = tuple(
            item
            for item in self.documents
            if (kwargs.get("status") is None or item.status.value == kwargs["status"])
            and (kwargs.get("kind") is None or item.kind.value == kwargs["kind"])
        )
        return SourceDocumentPage(items, kwargs["page"], kwargs["page_size"], len(items))

    def create_pdf_document(self, **kwargs) -> DocumentOperationResult:
        self.pdf_creates.append(kwargs)
        self.pdf_bytes = kwargs["pdf_bytes"]
        document = _pdf_document(self.source, self.pdf_bytes)
        self.documents = (*self.documents, document)
        return DocumentOperationResult(
            DocumentOperationStatus.CREATED,
            document,
            "created",
            metadata_persisted=True,
            blob_created=True,
        )

    def create_web_document(self, **kwargs) -> DocumentOperationResult:
        self.web_creates.append(kwargs)
        document = SourceDocument(
            source_id=self.source.source_id,
            reference_id=kwargs["reference_id"],
            kind="web",
            title=kwargs["title"],
            description=kwargs["description"],
            language=kwargs["language"],
            tags=kwargs["tags"],
            rights=kwargs["rights"],
            web={"url_raw": kwargs["url_raw"]},
        )
        return DocumentOperationResult(
            DocumentOperationStatus.CREATED,
            document,
            "created",
            metadata_persisted=True,
        )

    def read_pdf_document(self, document_id: str) -> DocumentPdfPayload:
        document = next(item for item in self.documents if item.document_id == document_id)
        assert document.pdf is not None
        return DocumentPdfPayload(
            document,
            self.pdf_bytes,
            document.pdf.current_version.original_filename,
            document.pdf.current_version.sha256,
        )

    def update_document_metadata(self, document_id: str, changes: dict[str, Any]):
        self.updates.append((document_id, changes))
        document = next(item for item in self.documents if item.document_id == document_id)
        return DocumentOperationResult(DocumentOperationStatus.SUCCESS, document, "updated", True)

    def archive_document(self, document_id: str):
        self.archives.append(document_id)
        document = next(item for item in self.documents if item.document_id == document_id)
        return DocumentOperationResult(DocumentOperationStatus.SUCCESS, document, "archived", True)

    def reactivate_document(self, document_id: str):
        self.reactivations.append(document_id)
        document = next(item for item in self.documents if item.document_id == document_id)
        return DocumentOperationResult(
            DocumentOperationStatus.SUCCESS, document, "reactivated", True
        )

    def inspect_document_integrity(self, document_id: str) -> DocumentIntegrityInspection:
        self.inspections.append(document_id)
        return DocumentIntegrityInspection(document_id, True, ())


def _context(source: Source, references: tuple[Reference, ...] = ()) -> SimpleNamespace:
    del source
    return SimpleNamespace(
        database_name="isolated_s2_ui",
        database=object(),
        reference_repository=FakeReferenceRepository(references),
    )


def test_uploaded_pdf_is_bounded_validated_and_position_preserved() -> None:
    uploaded = FakeUploadedFile(VALID_PDF)

    assert uploaded_pdf_filename(uploaded) == "paper.pdf"
    assert uploaded_pdf_bytes(uploaded) == VALID_PDF
    assert uploaded.position == 0
    assert uploaded.read_calls == [MAX_SOURCE_PDF_UPLOAD_BYTES + 1]

    with pytest.raises(ValueError, match="límite"):
        uploaded_pdf_bytes(ExplodingOversizeUpload())
    with pytest.raises(ValueError, match="cabecera"):
        uploaded_pdf_bytes(FakeUploadedFile(b"not a pdf"))
    with pytest.raises(ValueError, match="nombre PDF simple"):
        uploaded_pdf_filename(FakeUploadedFile(VALID_PDF, name="../paper.pdf"))


def test_add_pdf_persists_then_views_and_downloads_exact_service_bytes() -> None:
    source = Source(name="PDF owner")
    service = FakeDocumentService(source)
    ui = FakeUI(
        uploaded=FakeUploadedFile(VALID_PDF),
        submitted={"Guardar PDF Document"},
    )

    render_source_documents(
        ui,
        _context(source),
        source,
        writes_enabled=True,
        service=service,  # type: ignore[arg-type]
    )

    assert len(service.pdf_creates) == 1
    assert service.pdf_creates[0]["pdf_bytes"] == VALID_PDF
    assert ui.file_uploader_kwargs["max_upload_size"] == 50
    assert ui.pdf_calls[0][0] is service.pdf_bytes
    assert ui.pdf_calls[0][1]["height"] == 800
    assert ui.download_calls[0]["data"] is ui.pdf_calls[0][0]
    assert ui.download_calls[0]["file_name"] == "paper.pdf"
    assert ui.session_state[DOCUMENT_PREVIEW_SUBJECT]["source_id"] == source.source_id


def test_web_ui_rejects_local_scheme_without_service_call_and_normalizes_https() -> None:
    source = Source(name="Web owner")
    url_key = state_key("document_add_web_url", source.source_id)
    rejected_service = FakeDocumentService(source)
    rejected = FakeUI(values={url_key: "file:///private/paper.pdf"})

    render_source_documents(
        rejected,
        _context(source),
        source,
        writes_enabled=True,
        service=rejected_service,  # type: ignore[arg-type]
    )

    assert rejected_service.web_creates == []
    assert any(
        "http or https" in message for level, message in rejected.messages if level == "error"
    )

    accepted_service = FakeDocumentService(source)
    accepted = FakeUI(
        values={url_key: "HTTPS://EXAMPLE.TEST:443/resource#fragment"},
        submitted={"Guardar Web Document"},
    )
    render_source_documents(
        accepted,
        _context(source),
        source,
        writes_enabled=True,
        service=accepted_service,  # type: ignore[arg-type]
    )

    assert len(accepted_service.web_creates) == 1
    assert accepted_service.web_creates[0]["url_raw"].startswith("HTTPS://")
    rendered = " ".join(message for _level, message in accepted.messages)
    assert "https://example.test/resource" in rendered
    assert "not performed" in rendered


def test_list_edits_reference_metadata_archives_checks_integrity_and_links_web() -> None:
    source = Source(name="Document owner")
    reference = Reference(title="Associated", source_ids=[source.source_id])
    document = _web_document(source)
    service = FakeDocumentService(source, (document,))
    edit_open = state_key("document_edit_open", document.document_id)
    reference_key = state_key(f"document_edit_{document.document_id}", "reference_id")
    integrity_key = state_key("document_integrity", document.document_id)
    ui = FakeUI(
        values={edit_open: True, reference_key: reference.reference_id},
        clicked={integrity_key},
        submitted={"Guardar metadata", "Archivar Document"},
    )

    render_source_documents(
        ui,
        _context(source, (reference,)),
        source,
        writes_enabled=True,
        service=service,  # type: ignore[arg-type]
    )

    assert service.updates[0][0] == document.document_id
    assert service.updates[0][1]["reference_id"] == reference.reference_id
    assert service.archives == [document.document_id]
    assert service.inspections == [document.document_id]
    assert ui.links == ["https://example.test/resource"]


def test_operation_token_changes_when_only_reference_changes() -> None:
    context = SimpleNamespace(database_name="isolated_s2_ui")
    first = _operation_token(
        context,
        "update_document",
        "doc-id",
        {"title": "Same", "reference_id": "ref-one"},
    )
    second = _operation_token(
        context,
        "update_document",
        "doc-id",
        {"title": "Same", "reference_id": "ref-two"},
    )

    assert first != second
    assert "ref-one" not in first
    assert "ref-two" not in second


def test_database_switch_clears_only_source_document_preview() -> None:
    state: dict[str, Any] = {ACTIVE_DATABASE_IDENTITY: "old\x1fdatabase"}
    payload = PdfPreviewPayload(VALID_PDF, "sha", "paper.pdf", "context")
    store_pdf_preview(state, PDF_PREVIEW_NAMESPACE, payload)
    store_pdf_preview(state, "cornell", payload)
    state[DOCUMENT_PREVIEW_SUBJECT] = {"database": "old"}

    assert sync_database_state(state, connection_label="label", database_name="new")

    assert get_pdf_preview(state, PDF_PREVIEW_NAMESPACE, context_identity="context") is None
    assert get_pdf_preview(state, "cornell", context_identity="context") is payload
    assert DOCUMENT_PREVIEW_SUBJECT not in state


def test_source_switch_clears_only_source_document_preview() -> None:
    old_source = Source(name="Old")
    new_source = Source(name="New")
    ui = FakeUI()
    payload = PdfPreviewPayload(VALID_PDF, "sha", "paper.pdf", "context")
    store_pdf_preview(ui.session_state, PDF_PREVIEW_NAMESPACE, payload)
    store_pdf_preview(ui.session_state, "cornell", payload)
    ui.session_state[DOCUMENT_PREVIEW_SUBJECT] = {
        "database": "isolated_s2_ui",
        "source_id": old_source.source_id,
    }

    render_source_documents(
        ui,
        _context(new_source),
        new_source,
        writes_enabled=True,
        service=FakeDocumentService(new_source),  # type: ignore[arg-type]
    )

    assert (
        get_pdf_preview(ui.session_state, PDF_PREVIEW_NAMESPACE, context_identity="context") is None
    )
    assert get_pdf_preview(ui.session_state, "cornell", context_identity="context") is payload


def test_edit_source_page_routes_documents_with_write_guard(monkeypatch) -> None:
    source = Source(name="Routed")
    captured: list[tuple[str, bool]] = []
    ui = FakeUI()
    ui.title = lambda _value: None
    ui.divider = lambda: None
    ui.selectbox = lambda *_args, **_kwargs: "Documents"

    monkeypatch.setattr(edit_source_page, "render_active_database", lambda *_args: None)
    monkeypatch.setattr(
        edit_source_page,
        "render_catalog_status",
        lambda *_args: SimpleNamespace(initialized=True),
    )
    monkeypatch.setattr(edit_source_page, "_render_source_search", lambda *_args: source)
    monkeypatch.setattr(edit_source_page, "_render_overview_header", lambda *_args: None)
    monkeypatch.setattr(
        edit_source_page,
        "render_source_documents",
        lambda _ui, _context, selected, *, writes_enabled: captured.append(
            (selected.source_id, writes_enabled)
        ),
    )

    edit_source_page.render_edit_source_page(SimpleNamespace(), ui=ui)

    assert "Documents" in edit_source_page.SOURCE_SECTIONS
    assert captured == [(source.source_id, True)]


def test_source_document_ui_has_no_local_url_or_backend_http_escape_hatch() -> None:
    path = ROOT / "editor/source_catalog/document_ui.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    forbidden_imports = {"requests", "httpx", "aiohttp", "webbrowser", "urllib.request"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden_imports:
                    violations.append(f"{node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module in forbidden_imports:
            violations.append(f"{node.lineno}: imports from {node.module}")
        elif isinstance(node, ast.Attribute) and node.attr == "as_uri":
            violations.append(f"{node.lineno}: uses Path.as_uri")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "file://" in node.value.casefold():
                violations.append(f"{node.lineno}: contains local file URL")

    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "render_pdf_preview" in path.read_text(encoding="utf-8")
    assert "components" not in calls
    assert violations == []

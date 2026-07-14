"""Focused, network-free tests for the optional advanced-reader Streamlit bridge."""

# ruff: noqa: D103

from __future__ import annotations

import ast
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import pytest

from editor.reading_space import reader_page
from mathmongo.advanced_reader.streamlit_link import ADVANCED_READER_URL_ENV
from mathmongo.advanced_reader.streamlit_link import DEFAULT_ADVANCED_READER_URL
from mathmongo.advanced_reader.streamlit_link import MAX_HEALTH_RESPONSE_BYTES
from mathmongo.advanced_reader.streamlit_link import MAX_HEALTH_TIMEOUT_SECONDS
from mathmongo.advanced_reader.streamlit_link import AdvancedReaderDocumentReadiness
from mathmongo.advanced_reader.streamlit_link import AdvancedReaderDocumentStatus
from mathmongo.advanced_reader.streamlit_link import AdvancedReaderHealthStatus
from mathmongo.advanced_reader.streamlit_link import build_advanced_reader_url
from mathmongo.advanced_reader.streamlit_link import get_advanced_reader_base_url
from mathmongo.advanced_reader.streamlit_link import probe_advanced_reader
from mathmongo.advanced_reader.streamlit_link import probe_advanced_reader_document

DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000001"
DATABASE_NAME = "MathV0"
ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def __init__(self, status: int, payload: bytes, *, content_length: str | None = None) -> None:
        self.status = status
        self.payload = payload
        self.headers = {} if content_length is None else {"Content-Length": content_length}
        self.closed = False
        self.read_limits: list[int] = []

    def read(self, limit: int) -> bytes:
        self.read_limits.append(limit)
        return self.payload[:limit]

    def close(self) -> None:
        self.closed = True


class _UI:
    def __init__(self) -> None:
        self.captions: list[str] = []
        self.links: list[tuple[str, str, dict[str, object]]] = []

    def caption(self, value: object) -> None:
        self.captions.append(str(value))

    def link_button(self, label: str, url: str, **kwargs: object) -> None:
        self.links.append((label, url, dict(kwargs)))


def _health_payload(*, database: str = DATABASE_NAME, frontend_ready: bool = True) -> bytes:
    return json.dumps(
        {
            "status": "ok",
            "service": "mathmongo-advanced-reader",
            "database": database,
            "frontend_ready": frontend_ready,
        }
    ).encode("utf-8")


def _metadata_payload(
    *,
    document_id: str = DOCUMENT_ID,
    kind: str = "pdf",
    integrity: str = "ok",
) -> bytes:
    return json.dumps(
        {
            "document_id": document_id,
            "kind": kind,
            "integrity": integrity,
        }
    ).encode("utf-8")


def _http_error(status: int, code: str) -> HTTPError:
    payload = json.dumps({"error": {"code": code, "message": "safe", "request_id": "x"}})
    return HTTPError(
        f"{DEFAULT_ADVANCED_READER_URL}/metadata",
        status,
        "safe",
        {},
        BytesIO(payload.encode("utf-8")),
    )


def test_url_builder_uses_default_or_environment_and_only_document_query() -> None:
    default_url = build_advanced_reader_url(DOCUMENT_ID, environment={})
    configured_url = build_advanced_reader_url(
        DOCUMENT_ID,
        environment={ADVANCED_READER_URL_ENV: "http://localhost:9876/"},
    )

    assert get_advanced_reader_base_url({}) == DEFAULT_ADVANCED_READER_URL
    assert default_url.startswith(f"{DEFAULT_ADVANCED_READER_URL}/reader?")
    assert configured_url.startswith("http://localhost:9876/reader?")
    for value in (default_url, configured_url):
        parsed = urlsplit(value)
        assert parsed.path == "/reader"
        assert parse_qs(parsed.query, strict_parsing=True) == {"document_id": [DOCUMENT_ID]}
        assert parsed.fragment == ""


@pytest.mark.parametrize(
    ("document_id", "base_url"),
    [
        ("doc_not-a-uuid", DEFAULT_ADVANCED_READER_URL),
        (DOCUMENT_ID, "https://127.0.0.1:8766"),
        (DOCUMENT_ID, "http://0.0.0.0:8766"),
        (DOCUMENT_ID, "http://example.com:8766"),
        (DOCUMENT_ID, "http://user:secret@127.0.0.1:8766"),
        (DOCUMENT_ID, "http://127.0.0.1:8766/reader"),
        (DOCUMENT_ID, "http://127.0.0.1:8766?extra=true"),
        (DOCUMENT_ID, "http://127.0.0.1:8766#fragment"),
    ],
)
def test_url_builder_rejects_noncanonical_ids_and_unsafe_bases(
    document_id: str,
    base_url: str,
) -> None:
    with pytest.raises(ValueError):
        build_advanced_reader_url(document_id, base_url=base_url)


def test_health_probe_uses_fixed_get_endpoint_closes_response_and_caps_timeout() -> None:
    calls: list[tuple[str, str, float]] = []
    response = _Response(
        200,
        _health_payload(database="temporary"),
    )

    def opener(request, *, timeout):
        calls.append((request.full_url, request.get_method(), timeout))
        return response

    result = probe_advanced_reader(timeout_seconds=99, opener=opener)

    assert result.status == AdvancedReaderHealthStatus.AVAILABLE
    assert result.database == "temporary"
    assert calls == [
        (
            f"{DEFAULT_ADVANCED_READER_URL}/api/advanced-reader/health",
            "GET",
            MAX_HEALTH_TIMEOUT_SECONDS,
        )
    ]
    assert response.read_limits == [MAX_HEALTH_RESPONSE_BYTES + 1]
    assert response.closed is True


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "status": "ok",
                "service": "mathmongo-advanced-reader",
                "database": DATABASE_NAME,
                "frontend_ready": False,
            },
            AdvancedReaderHealthStatus.NOT_STARTED,
        ),
        (
            {"status": "ok", "service": "another-service", "frontend_ready": True},
            AdvancedReaderHealthStatus.INVALID,
        ),
        ({"status": "wrong", "frontend_ready": True}, AdvancedReaderHealthStatus.INVALID),
        (
            {
                "status": "ok",
                "service": "mathmongo-advanced-reader",
                "frontend_ready": True,
            },
            AdvancedReaderHealthStatus.INVALID,
        ),
    ],
)
def test_health_probe_requires_the_expected_ready_service_payload(
    payload: dict[str, object],
    expected: AdvancedReaderHealthStatus,
) -> None:
    response = _Response(200, json.dumps(payload).encode("utf-8"))

    assert probe_advanced_reader(opener=lambda *_args, **_kwargs: response).status == expected


def test_health_probe_rejects_oversized_json_without_reading_it() -> None:
    response = _Response(
        200,
        b"{}",
        content_length=str(MAX_HEALTH_RESPONSE_BYTES + 1),
    )

    result = probe_advanced_reader(opener=lambda *_args, **_kwargs: response)

    assert result.status == AdvancedReaderHealthStatus.INVALID
    assert response.read_limits == []


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (URLError(TimeoutError()), AdvancedReaderHealthStatus.TIMEOUT),
        (URLError(ConnectionRefusedError()), AdvancedReaderHealthStatus.NOT_STARTED),
    ],
)
def test_health_probe_classifies_network_failures_without_real_network(
    failure: Exception,
    expected: AdvancedReaderHealthStatus,
) -> None:
    def opener(*_args, **_kwargs):
        raise failure

    assert probe_advanced_reader(opener=opener).status == expected


def test_health_probe_fails_closed_before_opening_for_invalid_configuration() -> None:
    called = False

    def opener(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("opener must not be called")

    result = probe_advanced_reader(base_url="http://example.com", opener=opener)

    assert result.status == AdvancedReaderHealthStatus.INVALID
    assert called is False


def test_document_readiness_requires_health_database_frontend_and_exact_metadata() -> None:
    responses = iter(
        [
            _Response(200, _health_payload()),
            _Response(200, _metadata_payload()),
        ]
    )
    calls: list[tuple[str, str, float]] = []

    def opener(request, *, timeout):
        calls.append((request.full_url, request.get_method(), timeout))
        return next(responses)

    result = probe_advanced_reader_document(
        DOCUMENT_ID,
        DATABASE_NAME,
        timeout_seconds=99,
        opener=opener,
    )

    assert result.status == AdvancedReaderDocumentStatus.READY
    assert result.ready
    assert result.database == DATABASE_NAME
    assert calls == [
        (
            f"{DEFAULT_ADVANCED_READER_URL}/api/advanced-reader/health",
            "GET",
            MAX_HEALTH_TIMEOUT_SECONDS,
        ),
        (
            f"{DEFAULT_ADVANCED_READER_URL}/api/advanced-reader/documents/{DOCUMENT_ID}",
            "GET",
            MAX_HEALTH_TIMEOUT_SECONDS,
        ),
    ]


def test_document_readiness_database_mismatch_stops_before_metadata() -> None:
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _Response(200, _health_payload(database="another_database"))

    result = probe_advanced_reader_document(
        DOCUMENT_ID,
        DATABASE_NAME,
        opener=opener,
    )

    assert result.status == AdvancedReaderDocumentStatus.DATABASE_MISMATCH
    assert result.database == "another_database"
    assert calls == 1


def test_document_readiness_requires_frontend_ready_before_metadata() -> None:
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _Response(200, _health_payload(frontend_ready=False))

    result = probe_advanced_reader_document(
        DOCUMENT_ID,
        DATABASE_NAME,
        opener=opener,
    )

    assert result.status == AdvancedReaderDocumentStatus.NOT_STARTED
    assert calls == 1


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (404, "document_not_found", AdvancedReaderDocumentStatus.DOCUMENT_NOT_FOUND),
        (415, "document_not_pdf", AdvancedReaderDocumentStatus.NOT_PDF),
        (409, "integrity_error", AdvancedReaderDocumentStatus.INTEGRITY_ERROR),
        (404, "blob_missing", AdvancedReaderDocumentStatus.INTEGRITY_ERROR),
    ],
)
def test_document_readiness_classifies_sanitized_metadata_errors(
    status: int,
    code: str,
    expected: AdvancedReaderDocumentStatus,
) -> None:
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Response(200, _health_payload())
        raise _http_error(status, code)

    result = probe_advanced_reader_document(
        DOCUMENT_ID,
        DATABASE_NAME,
        opener=opener,
    )

    assert result.status == expected
    assert calls == 2


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (_metadata_payload(kind="web"), AdvancedReaderDocumentStatus.NOT_PDF),
        (
            _metadata_payload(integrity="failed"),
            AdvancedReaderDocumentStatus.INTEGRITY_ERROR,
        ),
        (
            _metadata_payload(document_id="doc_00000000-0000-4000-8000-000000000002"),
            AdvancedReaderDocumentStatus.INVALID,
        ),
    ],
)
def test_document_readiness_fails_closed_for_non_pdf_or_invalid_metadata(
    metadata: bytes,
    expected: AdvancedReaderDocumentStatus,
) -> None:
    responses = iter([_Response(200, _health_payload()), _Response(200, metadata)])
    result = probe_advanced_reader_document(
        DOCUMENT_ID,
        DATABASE_NAME,
        opener=lambda *_args, **_kwargs: next(responses),
    )

    assert result.status == expected


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (URLError(TimeoutError()), AdvancedReaderDocumentStatus.TIMEOUT),
        (URLError(ConnectionRefusedError()), AdvancedReaderDocumentStatus.NOT_STARTED),
    ],
)
def test_document_readiness_preserves_bounded_network_outcomes(
    failure: Exception,
    expected: AdvancedReaderDocumentStatus,
) -> None:
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Response(200, _health_payload())
        raise failure

    result = probe_advanced_reader_document(
        DOCUMENT_ID,
        DATABASE_NAME,
        opener=opener,
    )

    assert result.status == expected


def test_document_readiness_rejects_remote_base_or_invalid_identity_without_io() -> None:
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("invalid readiness input must not perform network I/O")

    remote = probe_advanced_reader_document(
        DOCUMENT_ID,
        DATABASE_NAME,
        base_url="http://example.com:8766",
        opener=opener,
    )
    invalid_database = probe_advanced_reader_document(
        DOCUMENT_ID,
        " MathV0 ",
        opener=opener,
    )

    assert remote.status == AdvancedReaderDocumentStatus.INVALID
    assert invalid_database.status == AdvancedReaderDocumentStatus.INVALID
    assert calls == 0


def test_streamlit_bridge_renders_explicit_available_link(monkeypatch) -> None:
    ui = _UI()
    calls: list[tuple[str, str]] = []

    def ready(document_id: str, database_name: str) -> AdvancedReaderDocumentReadiness:
        calls.append((document_id, database_name))
        return AdvancedReaderDocumentReadiness(
            AdvancedReaderDocumentStatus.READY,
            DEFAULT_ADVANCED_READER_URL,
            f"{DEFAULT_ADVANCED_READER_URL}/api/advanced-reader/documents/{DOCUMENT_ID}",
            DATABASE_NAME,
        )

    monkeypatch.setattr(
        reader_page,
        "probe_advanced_reader_document",
        ready,
    )

    reader_page._render_advanced_reader_link(
        ui,
        DOCUMENT_ID,
        database_name=DATABASE_NAME,
        enabled=True,
    )

    assert calls == [(DOCUMENT_ID, DATABASE_NAME)]
    assert ui.captions == ["Lector avanzado listo."]
    assert len(ui.links) == 1
    label, url, options = ui.links[0]
    assert label == "Abrir lector avanzado"
    assert parse_qs(urlsplit(url).query) == {"document_id": [DOCUMENT_ID]}
    assert "database" not in url
    assert "mongodb" not in url.casefold()
    assert options["disabled"] is False


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (AdvancedReaderDocumentStatus.NOT_STARTED, "Lector avanzado no iniciado."),
        (
            AdvancedReaderDocumentStatus.DATABASE_MISMATCH,
            "Lector avanzado conectado a otra base.",
        ),
        (
            AdvancedReaderDocumentStatus.DOCUMENT_NOT_FOUND,
            "El Document no existe en la base del lector.",
        ),
        (AdvancedReaderDocumentStatus.NOT_PDF, "El Document no es PDF."),
        (
            AdvancedReaderDocumentStatus.INTEGRITY_ERROR,
            "El PDF tiene un problema de integridad.",
        ),
        (AdvancedReaderDocumentStatus.TIMEOUT, "El lector no respondió a tiempo."),
    ],
)
def test_streamlit_bridge_reports_differentiated_spanish_readiness_and_disables_link(
    monkeypatch,
    status: AdvancedReaderDocumentStatus,
    message: str,
) -> None:
    ui = _UI()
    monkeypatch.setattr(
        reader_page,
        "probe_advanced_reader_document",
        lambda *_args: AdvancedReaderDocumentReadiness(
            status,
            DEFAULT_ADVANCED_READER_URL,
            f"{DEFAULT_ADVANCED_READER_URL}/api/advanced-reader/documents/{DOCUMENT_ID}",
        ),
    )

    reader_page._render_advanced_reader_link(
        ui,
        DOCUMENT_ID,
        database_name=DATABASE_NAME,
        enabled=True,
    )

    assert ui.captions[0].startswith(message)
    assert ui.links[0][2]["disabled"] is True


def test_streamlit_bridge_honors_disabled_configuration_without_probe(monkeypatch) -> None:
    ui = _UI()

    def forbidden_probe(*_args):
        raise AssertionError("disabled integration must not perform a health probe")

    monkeypatch.setattr(reader_page, "probe_advanced_reader_document", forbidden_probe)

    reader_page._render_advanced_reader_link(
        ui,
        DOCUMENT_ID,
        database_name=DATABASE_NAME,
        enabled=True,
        configured=False,
    )

    assert ui.captions == ["Lector avanzado deshabilitado en la configuración."]
    assert ui.links == []


def test_editor_integration_is_pdf_only_retains_fallback_and_starts_no_processes() -> None:
    path = ROOT / "editor/reading_space/reader_page.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    helper_path = ROOT / "mathmongo/advanced_reader/streamlit_link.py"
    helper_tree = ast.parse(
        helper_path.read_text(encoding="utf-8"),
        filename=str(helper_path),
    )
    callers = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "_render_advanced_reader_link"
            for child in ast.walk(node)
        )
    }
    imported_roots: set[str] = set()
    called_names: set[str] = set()
    fallback_buttons = 0
    for inspected_tree in (tree, helper_tree):
        for node in ast.walk(inspected_tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr)
                if (
                    inspected_tree is tree
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "button"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "Open PDF"
                ):
                    fallback_buttons += 1

    assert callers == {"_render_pdf_reader"}
    editor_imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not editor_imports.intersection({"http", "socket", "urllib"})
    assert not imported_roots.intersection({"asyncio", "multiprocessing", "subprocess"})
    assert not called_names.intersection({"Popen", "create_subprocess_exec", "spawn", "system"})
    assert fallback_buttons == 1

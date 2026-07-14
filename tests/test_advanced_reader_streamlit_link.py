"""Focused, network-free tests for the optional advanced-reader Streamlit bridge."""

# ruff: noqa: D103

from __future__ import annotations

import ast
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import pytest

from editor.reading_space import reader_page
from mathmongo.advanced_reader.streamlit_link import ADVANCED_READER_URL_ENV
from mathmongo.advanced_reader.streamlit_link import DEFAULT_ADVANCED_READER_URL
from mathmongo.advanced_reader.streamlit_link import MAX_HEALTH_RESPONSE_BYTES
from mathmongo.advanced_reader.streamlit_link import MAX_HEALTH_TIMEOUT_SECONDS
from mathmongo.advanced_reader.streamlit_link import AdvancedReaderHealth
from mathmongo.advanced_reader.streamlit_link import AdvancedReaderHealthStatus
from mathmongo.advanced_reader.streamlit_link import build_advanced_reader_url
from mathmongo.advanced_reader.streamlit_link import get_advanced_reader_base_url
from mathmongo.advanced_reader.streamlit_link import probe_advanced_reader

DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000001"
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
        json.dumps(
            {
                "status": "ok",
                "service": "mathmongo-advanced-reader",
                "database": "temporary",
                "frontend_ready": True,
            }
        ).encode("utf-8"),
    )

    def opener(request, *, timeout):
        calls.append((request.full_url, request.get_method(), timeout))
        return response

    result = probe_advanced_reader(timeout_seconds=99, opener=opener)

    assert result.status == AdvancedReaderHealthStatus.AVAILABLE
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
                "frontend_ready": False,
            },
            AdvancedReaderHealthStatus.NOT_STARTED,
        ),
        (
            {"status": "ok", "service": "another-service", "frontend_ready": True},
            AdvancedReaderHealthStatus.INVALID,
        ),
        ({"status": "wrong", "frontend_ready": True}, AdvancedReaderHealthStatus.INVALID),
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


def test_streamlit_bridge_renders_explicit_available_link(monkeypatch) -> None:
    ui = _UI()
    monkeypatch.setattr(
        reader_page,
        "probe_advanced_reader",
        lambda: AdvancedReaderHealth(
            AdvancedReaderHealthStatus.AVAILABLE,
            DEFAULT_ADVANCED_READER_URL,
            f"{DEFAULT_ADVANCED_READER_URL}/api/advanced-reader/health",
        ),
    )

    reader_page._render_advanced_reader_link(ui, DOCUMENT_ID, enabled=True)

    assert ui.captions == ["Lector avanzado disponible."]
    assert len(ui.links) == 1
    label, url, options = ui.links[0]
    assert label == "Abrir lector avanzado"
    assert parse_qs(urlsplit(url).query) == {"document_id": [DOCUMENT_ID]}
    assert options["disabled"] is False


def test_streamlit_bridge_reports_not_started_without_launching_anything(monkeypatch) -> None:
    ui = _UI()
    monkeypatch.setattr(
        reader_page,
        "probe_advanced_reader",
        lambda: AdvancedReaderHealth(
            AdvancedReaderHealthStatus.NOT_STARTED,
            DEFAULT_ADVANCED_READER_URL,
            f"{DEFAULT_ADVANCED_READER_URL}/api/advanced-reader/health",
        ),
    )

    reader_page._render_advanced_reader_link(ui, DOCUMENT_ID, enabled=True)

    assert "make advanced-reader" in ui.captions[0]
    assert ui.links[0][2]["disabled"] is True


def test_streamlit_bridge_honors_disabled_configuration_without_probe(monkeypatch) -> None:
    ui = _UI()

    def forbidden_probe():
        raise AssertionError("disabled integration must not perform a health probe")

    monkeypatch.setattr(reader_page, "probe_advanced_reader", forbidden_probe)

    reader_page._render_advanced_reader_link(
        ui,
        DOCUMENT_ID,
        enabled=True,
        configured=False,
    )

    assert ui.captions == ["Lector avanzado deshabilitado en la configuración."]
    assert ui.links == []


def test_editor_integration_is_pdf_only_and_contains_no_network_imports() -> None:
    path = ROOT / "editor/reading_space/reader_page.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert callers == {"_render_pdf_reader"}
    assert not imported_roots.intersection({"http", "socket", "urllib"})

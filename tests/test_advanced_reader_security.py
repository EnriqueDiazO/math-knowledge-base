"""Focused loopback, same-origin, header, and leakage tests for S5A."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path

import pytest
from test_advanced_reader_api import API_PREFIX
from test_advanced_reader_api import BASE_URL
from test_advanced_reader_api import make_backend_harness

from mathmongo.advanced_reader.security import SECURITY_HEADERS
from mathmongo.advanced_reader.security import redacted_request_path
from mathmongo.advanced_reader.security import validate_loopback_host
from mathmongo.advanced_reader.security import validate_public_url


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_only_explicit_loopback_hosts_are_valid(host: str) -> None:
    assert validate_loopback_host(host) == host


@pytest.mark.parametrize(
    "host",
    ["", "0.0.0.0", "127.0.0.2", "192.168.1.20", "example.com", "localhost.evil"],
)
def test_remote_wildcard_and_ambiguous_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ValueError, match="loopback|127.0.0.1"):
        validate_loopback_host(host)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:8766", "http://127.0.0.1:8766"),
        ("http://LOCALHOST:8766/", "http://localhost:8766"),
        ("http://[::1]:8766", "http://[::1]:8766"),
    ],
)
def test_public_url_is_canonical_path_free_loopback_http(value: str, expected: str) -> None:
    assert validate_public_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:8766",
        "http://0.0.0.0:8766",
        "http://user:secret@127.0.0.1:8766",
        "http://127.0.0.1:8766/reader",
        "http://127.0.0.1:8766?token=secret",
        "http://127.0.0.1:8766#fragment",
    ],
)
def test_public_url_rejects_remote_credentials_and_extra_context(value: str) -> None:
    with pytest.raises(ValueError):
        validate_public_url(value)


def test_non_loopback_host_header_is_rejected_before_dependencies(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    with harness.client() as client:
        response = client.get(
            f"{API_PREFIX}/health",
            headers={"Host": "example.com:8766"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "internal_error"
    assert harness.health_calls == []


@pytest.mark.parametrize(
    "host_header",
    [
        "user@localhost:8766",
        "localhost:notaport",
        "localhost:8766/path",
    ],
)
def test_ambiguous_loopback_host_headers_are_rejected(
    tmp_path: Path,
    host_header: str,
) -> None:
    harness = make_backend_harness(tmp_path)
    with harness.client() as client:
        response = client.get(
            f"{API_PREFIX}/health",
            headers={"Host": host_header},
        )

    assert response.status_code == 400
    assert harness.health_calls == []


def test_cross_origin_page_write_is_rejected_without_service_write(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/reading-state/page"
    with harness.client() as client:
        rejected = client.put(
            path,
            json={"pdf_page": 3},
            headers={"Origin": "http://127.0.0.1:9999"},
        )
        accepted = client.put(
            path,
            json={"pdf_page": 3},
            headers={"Origin": BASE_URL},
        )

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "internal_error"
    assert accepted.status_code == 200
    assert harness.reading_service.page_updates == [(harness.pdf.document_id, 3)]


def test_security_headers_cache_policy_no_cors_and_no_api_docs(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    with harness.client() as client:
        api = client.get(f"{API_PREFIX}/health")
        frontend = client.get("/reader", params={"document_id": harness.pdf.document_id})
        asset = client.get("/assets/app-abc.js")
        docs = client.get("/docs")
        openapi = client.get("/openapi.json")

    assert api.status_code == frontend.status_code == asset.status_code == 200
    for response in (api, frontend, asset, docs, openapi):
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value
        assert "access-control-allow-origin" not in response.headers
        assert response.headers["x-request-id"]
    assert api.headers["cache-control"] == "no-store, private"
    assert frontend.headers["cache-control"] == "no-cache"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert docs.status_code == openapi.status_code == 404


def test_frontend_missing_is_a_typed_safe_error(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path, frontend_ready=False)
    with harness.client() as client:
        health = client.get(f"{API_PREFIX}/health")
        frontend = client.get("/reader", params={"document_id": harness.pdf.document_id})

    assert health.status_code == 200
    assert health.json()["frontend_ready"] is False
    assert frontend.status_code == 503
    assert frontend.json()["error"]["code"] == "frontend_not_built"


def test_internal_and_integrity_errors_never_echo_paths_or_mongo_uri(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    secret_uri = "mongodb://alice:super-secret@127.0.0.1:27017/private"
    secret_path = str(tmp_path / "HOME/private/blob.pdf")
    harness.page_map_service.error = RuntimeError(f"{secret_path} {secret_uri}")
    with harness.client() as client:
        internal = client.get(
            f"{API_PREFIX}/documents/{harness.pdf.document_id}/page-label",
            params={"pdf_page": "2"},
        )
    harness.page_map_service.error = None
    harness.document_service.inspections[harness.pdf.document_id] = RuntimeError(
        f"failed at {secret_path} using {secret_uri}"
    )
    with harness.client() as client:
        integrity = client.get(f"{API_PREFIX}/documents/{harness.pdf.document_id}")

    assert internal.status_code == 500
    assert internal.json()["error"]["code"] == "internal_error"
    assert integrity.status_code == 409
    assert integrity.json()["error"]["code"] == "integrity_error"
    for response in (internal, integrity):
        assert secret_path not in response.text
        assert secret_uri not in response.text
        assert "alice" not in response.text
        assert "super-secret" not in response.text
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_health_failure_never_echoes_infrastructure_exception(tmp_path: Path) -> None:
    harness = make_backend_harness(tmp_path)
    secret = "mongodb://reader:password@localhost:27017/private"

    def fail_health() -> bool:
        raise RuntimeError(secret)

    object.__setattr__(harness.dependencies, "health_check", fail_health)
    with harness.client() as client:
        response = client.get(f"{API_PREFIX}/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert secret not in response.text
    assert "password" not in response.text


def test_request_path_redaction_never_logs_a_complete_document_id(
    tmp_path: Path,
) -> None:
    harness = make_backend_harness(tmp_path)
    path = f"{API_PREFIX}/documents/{harness.pdf.document_id}/pdf"
    redacted = redacted_request_path(path)

    assert harness.pdf.document_id not in redacted
    assert redacted.endswith(f"doc_…{harness.pdf.document_id[-8:]}/pdf")

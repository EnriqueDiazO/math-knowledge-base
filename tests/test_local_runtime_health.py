"""Unit tests for bounded loopback runtime health probes."""

# ruff: noqa: D103

from __future__ import annotations

import json

from mathmongo.local_runtime import health


def _payload(**overrides) -> bytes:
    value = {
        "status": "ok",
        "service": "mathmongo-advanced-reader",
        "database": "MathV0",
        "frontend_ready": True,
        **overrides,
    }
    return json.dumps(value).encode("utf-8")


def test_advanced_reader_health_success(monkeypatch) -> None:
    monkeypatch.setattr(health, "_get_local", lambda *_args, **_kwargs: (200, _payload()))

    result = health.probe_advanced_reader("127.0.0.1", 8766)

    assert result is not None
    assert result.ready is True
    assert result.database == "MathV0"


def test_advanced_reader_health_preserves_database_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(
        health,
        "_get_local",
        lambda *_args, **_kwargs: (200, _payload(database="another_database")),
    )

    result = health.probe_advanced_reader("127.0.0.1", 8766)

    assert result is not None
    assert result.database == "another_database"
    assert result.ready is True


def test_advanced_reader_health_preserves_frontend_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        health,
        "_get_local",
        lambda *_args, **_kwargs: (200, _payload(frontend_ready=False)),
    )

    result = health.probe_advanced_reader("127.0.0.1", 8766)

    assert result is not None
    assert result.frontend_ready is False
    assert result.ready is False


def test_advanced_reader_health_rejects_untrusted_or_malformed_payload(monkeypatch) -> None:
    responses = iter(
        [
            (200, b"not-json"),
            (200, _payload(database="bad/name")),
            (200, _payload(frontend_ready="yes")),
            (503, _payload()),
        ]
    )
    monkeypatch.setattr(health, "_get_local", lambda *_args, **_kwargs: next(responses))

    assert health.probe_advanced_reader("127.0.0.1", 8766) is None
    assert health.probe_advanced_reader("127.0.0.1", 8766) is None
    assert health.probe_advanced_reader("127.0.0.1", 8766) is None
    assert health.probe_advanced_reader("127.0.0.1", 8766) is None


def test_streamlit_health_accepts_only_small_success_body(monkeypatch) -> None:
    responses = iter([(200, b"ok\n"), (200, b"not streamlit"), (503, b"ok")])
    monkeypatch.setattr(health, "_get_local", lambda *_args, **_kwargs: next(responses))

    assert health.probe_streamlit("127.0.0.1", 8501) is True
    assert health.probe_streamlit("127.0.0.1", 8501) is False
    assert health.probe_streamlit("127.0.0.1", 8501) is False

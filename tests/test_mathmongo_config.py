"""Tests for MathMongo user configuration and precedence."""

# ruff: noqa: D103

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mathmongo.config import AppConfig
from mathmongo.config import get_config_file
from mathmongo.config import initialize_config
from mathmongo.config import load_config
from mathmongo.config import redact_mongo_uri
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error


def env(tmp_path: Path) -> dict[str, str]:
    return {
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "PATH": "",
    }


def test_initial_config_is_explicit_private_and_stable(tmp_path: Path) -> None:
    environment = env(tmp_path)
    config_file = get_config_file(environment)
    config_file.parent.mkdir(parents=True, mode=0o755)
    config_file.parent.chmod(0o755)
    assert not config_file.exists()
    path = initialize_config(environment)
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    payload = json.loads(path.read_text())
    assert payload["config_version"] == 1
    assert payload["mongo_database"] == "mathmongo"
    assert payload["export_directory"].endswith("Documents/MathMongo")


def test_precedence_explicit_then_env_then_file(tmp_path: Path) -> None:
    environment = env(tmp_path)
    path = initialize_config(environment)
    payload = json.loads(path.read_text())
    payload.update({"mongo_uri": "mongodb://file:27017", "streamlit_port": 8502})
    path.write_text(json.dumps(payload))
    environment.update({"MONGO_URI": "mongodb://env:27017", "MATHMONGO_STREAMLIT_PORT": "8503"})
    resolved = resolve_config(
        explicit={"mongo_uri": "mongodb://cli:27017"}, environment=environment
    )
    assert resolved.mongo_uri == "mongodb://cli:27017"
    assert resolved.streamlit_port == 8503


def test_existing_mongo_environment_aliases(tmp_path: Path) -> None:
    environment = env(tmp_path)
    environment.update({"MONGODB_URI": "mongodb://primary", "MONGODB_DB": "PrimaryDb"})
    resolved = resolve_config(environment=environment, stored=AppConfig())
    assert resolved.mongo_uri == "mongodb://primary"
    assert resolved.mongo_database == "PrimaryDb"


def test_invalid_config_types_fall_back_safely(tmp_path: Path) -> None:
    environment = env(tmp_path)
    path = get_config_file(environment)
    path.parent.mkdir(parents=True)
    path.write_text('{"streamlit_port": "invalid"}')
    assert load_config(environment).streamlit_port == 8501


def test_invalid_environment_values_preserve_valid_stored_config(tmp_path: Path) -> None:
    environment = env(tmp_path)
    environment.update(
        {
            "MATHMONGO_STREAMLIT_PORT": "invalid",
            "MATHMONGO_BROWSER_ENABLED": "maybe",
        }
    )
    resolved = resolve_config(
        environment=environment,
        stored=AppConfig(streamlit_port=8502, browser_enabled=False),
    )
    assert resolved.streamlit_port == 8502
    assert resolved.browser_enabled is False


def test_credentials_are_redacted() -> None:
    redacted = redact_mongo_uri("mongodb://alice:secret@db.example:27018/math")
    assert redacted == "mongodb://db.example:27018/math"
    assert "alice" not in redacted
    assert "secret" not in redacted


@pytest.mark.parametrize(
    "uri",
    [
        "mongodb:alice:secret@db.example/math",
        "alice:secret@db.example",
        "not-a-mongodb-uri",
        "",
    ],
)
def test_malformed_mongo_uris_fail_closed(uri: str) -> None:
    assert redact_mongo_uri(uri) == "<redacted MongoDB URI>"


def test_known_mongo_uri_is_removed_from_error_text() -> None:
    uri = "mongodb://alice:secret@db.example:27018/math"
    error = RuntimeError(f"Authentication failed for {uri}; user=alice password=secret")
    sanitized = sanitize_mongo_error(error, uri)
    assert sanitized == (
        "Authentication failed for mongodb://db.example:27018/math; "
        "user=<redacted> password=<redacted>"
    )


def test_streamlit_masks_uri_input_and_sanitizes_connection_errors() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "editor/editor_streamlit.py").read_text(encoding="utf-8")
    assert 'type="password"' in source
    assert "sanitize_mongo_error(e, mongo_uri)" in source

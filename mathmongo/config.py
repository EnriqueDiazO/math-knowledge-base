"""User configuration and precedence rules for MathMongo."""

# ruff: noqa: D103

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit
from urllib.parse import urlunsplit

from mathmongo.paths import get_config_dir
from mathmongo.paths import get_exports_dir
from mathmongo.paths import validate_mutable_path

CONFIG_VERSION = 1
DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DATABASE = "mathmongo"
DEFAULT_STREAMLIT_ADDRESS = "localhost"
DEFAULT_STREAMLIT_PORT = 8501
DEFAULT_ADVANCED_READER_HOST = "127.0.0.1"
DEFAULT_ADVANCED_READER_PORT = 8766
DEFAULT_ADVANCED_READER_PUBLIC_URL = "http://127.0.0.1:8766"
REDACTED_MONGO_URI = "<redacted MongoDB URI>"


def _parse_boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


@dataclass(frozen=True)
class AppConfig:
    """Resolved user settings; secrets must never be logged wholesale."""

    config_version: int = CONFIG_VERSION
    mongo_uri: str = DEFAULT_MONGO_URI
    mongo_database: str = DEFAULT_MONGO_DATABASE
    export_directory: str = ""
    streamlit_address: str = DEFAULT_STREAMLIT_ADDRESS
    streamlit_port: int = DEFAULT_STREAMLIT_PORT
    browser_enabled: bool = True
    advanced_reader_enabled: bool = True
    advanced_reader_host: str = DEFAULT_ADVANCED_READER_HOST
    advanced_reader_port: int = DEFAULT_ADVANCED_READER_PORT
    advanced_reader_public_url: str = DEFAULT_ADVANCED_READER_PUBLIC_URL


def get_config_file(environment: Mapping[str, str] | None = None) -> Path:
    return get_config_dir(environment) / "config.json"


def default_config(environment: Mapping[str, str] | None = None) -> AppConfig:
    return AppConfig(export_directory=str(get_exports_dir(environment)))


def load_config(environment: Mapping[str, str] | None = None) -> AppConfig:
    """Read configuration without creating it; invalid keys retain safe defaults."""
    defaults = default_config(environment)
    path = get_config_file(environment)
    if not path.is_file():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    allowed = {field: raw[field] for field in asdict(defaults) if field in raw}
    try:
        candidate = replace(defaults, **allowed)
        browser_enabled = _parse_boolean(candidate.browser_enabled)
        if browser_enabled is None:
            raise ValueError("invalid browser_enabled value")
        advanced_reader_enabled = _parse_boolean(candidate.advanced_reader_enabled)
        if advanced_reader_enabled is None:
            raise ValueError("invalid advanced_reader_enabled value")
        return AppConfig(
            config_version=int(candidate.config_version),
            mongo_uri=str(candidate.mongo_uri),
            mongo_database=str(candidate.mongo_database),
            export_directory=str(candidate.export_directory),
            streamlit_address=str(candidate.streamlit_address),
            streamlit_port=int(candidate.streamlit_port),
            browser_enabled=browser_enabled,
            advanced_reader_enabled=advanced_reader_enabled,
            advanced_reader_host=str(candidate.advanced_reader_host),
            advanced_reader_port=int(candidate.advanced_reader_port),
            advanced_reader_public_url=str(candidate.advanced_reader_public_url),
        )
    except (TypeError, ValueError):
        return defaults


def initialize_config(environment: Mapping[str, str] | None = None) -> Path:
    """Create the initial private config file only when explicitly requested."""
    config_dir = get_config_dir(environment)
    path = validate_mutable_path(
        config_dir / "config.json",
        allowed_root=config_dir.parent,
    )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if not path.exists():
        path.write_text(
            json.dumps(asdict(default_config(environment)), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    path.chmod(0o600)
    return path


def resolve_config(
    *,
    explicit: Mapping[str, object] | None = None,
    environment: Mapping[str, str] | None = None,
    stored: AppConfig | None = None,
) -> AppConfig:
    """Apply precedence explicit CLI > environment > file > defaults."""
    env = os.environ if environment is None else environment
    config = stored or load_config(env)
    env_values: dict[str, object] = {}
    for name in ("MONGODB_URI", "MONGO_URI"):
        if env.get(name):
            env_values["mongo_uri"] = env[name]
            break
    for name in ("MONGODB_DB", "MONGO_DB", "DB_NAME"):
        if env.get(name):
            env_values["mongo_database"] = env[name]
            break
    mappings = {
        "MATHMONGO_EXPORT_DIRECTORY": "export_directory",
        "MATHMONGO_STREAMLIT_ADDRESS": "streamlit_address",
        "MATHMONGO_ADVANCED_READER_HOST": "advanced_reader_host",
        "MATHMONGO_ADVANCED_READER_URL": "advanced_reader_public_url",
    }
    for env_name, field in mappings.items():
        if env.get(env_name) not in (None, ""):
            env_values[field] = env[env_name]
    raw_env_port = env.get("MATHMONGO_STREAMLIT_PORT")
    if raw_env_port not in (None, ""):
        try:
            env_values["streamlit_port"] = int(raw_env_port)
        except (TypeError, ValueError):
            pass
    raw_env_browser = env.get("MATHMONGO_BROWSER_ENABLED")
    if raw_env_browser not in (None, ""):
        parsed_browser = _parse_boolean(raw_env_browser)
        if parsed_browser is not None:
            env_values["browser_enabled"] = parsed_browser
    raw_reader_port = env.get("MATHMONGO_ADVANCED_READER_PORT")
    if raw_reader_port not in (None, ""):
        try:
            env_values["advanced_reader_port"] = int(raw_reader_port)
        except (TypeError, ValueError):
            pass
    raw_reader_enabled = env.get("MATHMONGO_ADVANCED_READER_ENABLED")
    if raw_reader_enabled not in (None, ""):
        parsed_reader_enabled = _parse_boolean(raw_reader_enabled)
        if parsed_reader_enabled is not None:
            env_values["advanced_reader_enabled"] = parsed_reader_enabled

    values = {**asdict(config), **env_values}
    for key, value in (explicit or {}).items():
        if value is None:
            continue
        if key in {"streamlit_port", "advanced_reader_port"}:
            try:
                values[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key in {"browser_enabled", "advanced_reader_enabled"}:
            parsed_browser = _parse_boolean(value)
            if parsed_browser is not None:
                values[key] = parsed_browser
        else:
            values[key] = value
    return AppConfig(**values)


def redact_mongo_uri(uri: str) -> str:
    """Remove credentials while retaining useful host/database diagnostics."""
    if not isinstance(uri, str) or not uri:
        return REDACTED_MONGO_URI
    try:
        parsed = urlsplit(uri)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
    except (TypeError, ValueError):
        return REDACTED_MONGO_URI
    if (
        scheme not in {"mongodb", "mongodb+srv"}
        or not parsed.netloc
        or not hostname
        or "@" in parsed.path
    ):
        return REDACTED_MONGO_URI
    try:
        port_value = parsed.port
    except ValueError:
        return REDACTED_MONGO_URI
    display_hostname = f"[{hostname}]" if ":" in hostname else hostname
    port = f":{port_value}" if port_value else ""
    return urlunsplit((scheme, f"{display_hostname}{port}", parsed.path, "", ""))


def sanitize_mongo_error(error: object, uri: str) -> str:
    """Remove a known MongoDB URI and its credentials from an error message."""
    message = str(error)
    raw_uri = str(uri or "")
    if not raw_uri:
        return message
    sanitized = message.replace(raw_uri, redact_mongo_uri(raw_uri))
    try:
        parsed = urlsplit(raw_uri)
    except ValueError:
        return sanitized
    for credential in (parsed.username, parsed.password):
        if credential:
            sanitized = sanitized.replace(credential, "<redacted>")
    return sanitized

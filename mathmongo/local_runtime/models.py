"""Validated value objects for the foreground local runtime supervisor."""

# ruff: noqa: D105

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from mathmongo.advanced_reader.security import validate_loopback_host

DEFAULT_DATABASE = "MathV0"
DEFAULT_STREAMLIT_HOST = "127.0.0.1"
DEFAULT_STREAMLIT_PORT = 8501
DEFAULT_ADVANCED_READER_HOST = "127.0.0.1"
DEFAULT_ADVANCED_READER_PORT = 8766
DEFAULT_LOG_LEVEL = "info"
LOG_LEVELS = frozenset({"critical", "error", "warning", "info", "debug"})


class LocalRuntimeError(RuntimeError):
    """A bounded, user-facing error that is safe to print without a traceback."""


class ServiceDisposition(str, Enum):
    """How a service participates in the current supervisor run."""

    STARTED = "started"
    REUSED = "reused"
    UNAVAILABLE = "unavailable"


def validate_port(value: int) -> int:
    """Return a valid TCP port and reject booleans and coercion surprises."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise LocalRuntimeError("El puerto debe estar entre 1 y 65535.")
    return value


def validate_database_name(value: str) -> str:
    """Apply MongoDB's bounded local database-name contract without exposing a URI."""
    name = " ".join(str(value or "").strip().split())
    forbidden = set('/\\."$*<>:|?\x00')
    if not name or len(name.encode("utf-8")) > 64 or any(char in forbidden for char in name):
        raise LocalRuntimeError("El nombre de base configurado no es valido.")
    return name


def validate_timeout(value: float, *, label: str, maximum: float) -> float:
    """Validate a finite, positive operational timeout."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LocalRuntimeError(f"{label} debe ser un numero positivo.")
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0 or timeout > maximum:
        raise LocalRuntimeError(f"{label} debe estar entre 0 y {maximum:g} segundos.")
    return timeout


@dataclass(frozen=True)
class RuntimeSettings:
    """Complete per-run configuration shared by both local services."""

    database: str = DEFAULT_DATABASE
    streamlit_host: str = DEFAULT_STREAMLIT_HOST
    streamlit_port: int = DEFAULT_STREAMLIT_PORT
    advanced_reader_host: str = DEFAULT_ADVANCED_READER_HOST
    advanced_reader_port: int = DEFAULT_ADVANCED_READER_PORT
    log_level: str = DEFAULT_LOG_LEVEL
    startup_timeout: float = 30.0
    request_timeout: float = 0.75
    poll_interval: float = 0.1
    shutdown_timeout: float = 5.0

    def __post_init__(self) -> None:
        try:
            streamlit_host = validate_loopback_host(self.streamlit_host)
            reader_host = validate_loopback_host(self.advanced_reader_host)
        except ValueError as exc:
            raise LocalRuntimeError(
                "Ambos servicios deben escuchar solo en localhost, 127.0.0.1 o ::1."
            ) from exc
        database = validate_database_name(self.database)
        streamlit_port = validate_port(self.streamlit_port)
        reader_port = validate_port(self.advanced_reader_port)
        log_level = str(self.log_level or "").strip().casefold()
        if log_level not in LOG_LEVELS:
            raise LocalRuntimeError("El nivel de log no es valido.")
        if streamlit_port == reader_port:
            raise LocalRuntimeError("Streamlit y Advanced Reader no pueden usar el mismo puerto.")
        object.__setattr__(self, "database", database)
        object.__setattr__(self, "streamlit_host", streamlit_host)
        object.__setattr__(self, "streamlit_port", streamlit_port)
        object.__setattr__(self, "advanced_reader_host", reader_host)
        object.__setattr__(self, "advanced_reader_port", reader_port)
        object.__setattr__(self, "log_level", log_level)
        object.__setattr__(
            self,
            "startup_timeout",
            validate_timeout(self.startup_timeout, label="El timeout de inicio", maximum=300),
        )
        object.__setattr__(
            self,
            "request_timeout",
            validate_timeout(self.request_timeout, label="El timeout HTTP", maximum=30),
        )
        object.__setattr__(
            self,
            "poll_interval",
            validate_timeout(self.poll_interval, label="El intervalo de sondeo", maximum=5),
        )
        object.__setattr__(
            self,
            "shutdown_timeout",
            validate_timeout(self.shutdown_timeout, label="El timeout de cierre", maximum=30),
        )


@dataclass(frozen=True)
class AdvancedReaderHealth:
    """Strict subset of the Advanced Reader health response used for reuse decisions."""

    status: str
    service: str
    database: str
    frontend_ready: bool

    @property
    def ready(self) -> bool:
        """Whether the response identifies a ready Advanced Reader."""
        return (
            self.status == "ok"
            and self.service == "mathmongo-advanced-reader"
            and self.frontend_ready is True
        )


__all__ = [
    "AdvancedReaderHealth",
    "DEFAULT_ADVANCED_READER_HOST",
    "DEFAULT_ADVANCED_READER_PORT",
    "DEFAULT_DATABASE",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_STREAMLIT_HOST",
    "DEFAULT_STREAMLIT_PORT",
    "LOG_LEVELS",
    "LocalRuntimeError",
    "RuntimeSettings",
    "ServiceDisposition",
    "validate_database_name",
    "validate_port",
]

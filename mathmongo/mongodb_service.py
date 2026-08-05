"""Inspect and, when explicitly allowed, start the local MongoDB service."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from mathmongo.config import redact_mongo_uri
from mathmongo.config import sanitize_mongo_error

MONGODB_SERVICE = "mongod"
SYSTEMCTL_TIMEOUT = 5.0
AUTHORIZATION_TIMEOUT = 120.0
STARTUP_TIMEOUT = 20.0
PING_TIMEOUT_MS = 750
MAX_DIAGNOSTIC_CHARS = 800

AuthorizationMode = Literal["none", "sudo", "pkexec", "auto"]

_CREDENTIAL = re.compile(
    r"(?i)\b(password|passwd|credential|secret|token)(\s*[:=]\s*)[^\s,;]+"
)


class MongoServiceState(str, Enum):
    """Combined systemd and PyMongo state for the configured MongoDB."""

    ACTIVE_AND_REACHABLE = "active_and_reachable"
    ACTIVE_BUT_UNREACHABLE = "active_but_unreachable"
    INACTIVE = "inactive"
    FAILED = "failed"
    SERVICE_NOT_FOUND = "service_not_found"
    SYSTEMD_UNAVAILABLE = "systemd_unavailable"


@dataclass(frozen=True)
class MongoServiceStatus:
    """A credential-free, read-only MongoDB service observation."""

    state: MongoServiceState
    service_state: str
    reachable: bool
    database: str
    safe_uri: str
    detail: str = ""


@dataclass(frozen=True)
class EnsureMongoResult:
    """Result of ensuring MongoDB without retaining authorization material."""

    ok: bool
    changed: bool
    cancelled: bool
    status: MongoServiceStatus
    message: str


def sanitize_mongo_diagnostic(value: object, mongo_uri: str) -> str:
    """Bound and remove MongoDB credentials from one subprocess diagnostic."""
    text = sanitize_mongo_error(value, mongo_uri)
    text = text.replace("\x00", "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    text = _CREDENTIAL.sub(lambda match: f"{match.group(1)}=<omitido>", text)
    return text[:MAX_DIAGNOSTIC_CHARS]


def mongodb_reachable(
    mongo_uri: str,
    database: str,
    *,
    timeout_ms: int = PING_TIMEOUT_MS,
) -> bool:
    """Ping the selected database with a short, bounded PyMongo client."""
    try:
        from pymongo import MongoClient

        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
        )
        try:
            client.get_database(database).command("ping")
        finally:
            client.close()
        return True
    except Exception:
        return False


def _run_systemctl(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    command: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def inspect_mongodb_service(
    mongo_uri: str,
    database: str,
    *,
    service_name: str = MONGODB_SERVICE,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    mongo_probe: Callable[[str, str], bool] = mongodb_reachable,
    which: Callable[[str], str | None] = shutil.which,
) -> MongoServiceStatus:
    """Combine systemd state and a bounded ping without changing the service."""
    safe_uri = redact_mongo_uri(mongo_uri)
    reachable = bool(mongo_probe(mongo_uri, database))
    systemctl = which("systemctl")
    if not systemctl:
        return MongoServiceStatus(
            MongoServiceState.SYSTEMD_UNAVAILABLE,
            "unavailable",
            reachable,
            database,
            safe_uri,
            "No se encontró systemctl.",
        )

    loaded = _run_systemctl(
        runner,
        [systemctl, "show", service_name, "--property=LoadState", "--value"],
        timeout=SYSTEMCTL_TIMEOUT,
    )
    if loaded is None:
        return MongoServiceStatus(
            MongoServiceState.SYSTEMD_UNAVAILABLE,
            "unavailable",
            reachable,
            database,
            safe_uri,
            "No fue posible consultar systemd.",
        )
    load_state = loaded.stdout.strip().casefold()
    load_error = sanitize_mongo_diagnostic(loaded.stderr, mongo_uri)
    if load_state == "not-found" or "not found" in load_error.casefold():
        return MongoServiceStatus(
            MongoServiceState.SERVICE_NOT_FOUND,
            "not-found",
            reachable,
            database,
            safe_uri,
            load_error,
        )
    if loaded.returncode != 0 or load_state not in {"loaded", "masked"}:
        return MongoServiceStatus(
            MongoServiceState.SYSTEMD_UNAVAILABLE,
            load_state or "unavailable",
            reachable,
            database,
            safe_uri,
            load_error,
        )

    active = _run_systemctl(
        runner,
        [systemctl, "is-active", service_name],
        timeout=SYSTEMCTL_TIMEOUT,
    )
    if active is None:
        return MongoServiceStatus(
            MongoServiceState.SYSTEMD_UNAVAILABLE,
            "unavailable",
            reachable,
            database,
            safe_uri,
            "No fue posible consultar el estado de mongod.",
        )
    service_state = active.stdout.strip().casefold() or "unknown"
    detail = sanitize_mongo_diagnostic(active.stderr, mongo_uri)
    if reachable:
        state = MongoServiceState.ACTIVE_AND_REACHABLE
    elif service_state in {"active", "activating", "deactivating"}:
        state = MongoServiceState.ACTIVE_BUT_UNREACHABLE
    elif service_state == "failed":
        state = MongoServiceState.FAILED
    elif service_state == "inactive":
        state = MongoServiceState.INACTIVE
    elif service_state in {"unknown", "not-found"}:
        state = MongoServiceState.SERVICE_NOT_FOUND
    else:
        state = MongoServiceState.SYSTEMD_UNAVAILABLE
    return MongoServiceStatus(
        state,
        service_state,
        reachable,
        database,
        safe_uri,
        detail,
    )


def mongo_status_lines(status: MongoServiceStatus) -> tuple[str, ...]:
    """Return stable, credential-free terminal diagnostics."""
    service_label = {
        MongoServiceState.SERVICE_NOT_FOUND: "no encontrado",
        MongoServiceState.SYSTEMD_UNAVAILABLE: "systemd no disponible",
    }.get(status.state, status.service_state)
    ping_label = "accesible" if status.reachable else "sin respuesta"
    state_label = {
        MongoServiceState.ACTIVE_AND_REACHABLE: "activo y accesible",
        MongoServiceState.ACTIVE_BUT_UNREACHABLE: "activo, pero no responde",
        MongoServiceState.INACTIVE: "detenido",
        MongoServiceState.FAILED: "fallido",
        MongoServiceState.SERVICE_NOT_FOUND: "servicio no encontrado",
        MongoServiceState.SYSTEMD_UNAVAILABLE: "systemd no disponible",
    }[status.state]
    return (
        f"MongoDB: {state_label}",
        f"Servicio mongod: {service_label}",
        f"Ping MongoDB: {ping_label}",
        f"Base seleccionada: {status.database}",
        f"URI: {status.safe_uri}",
    )


def _failure(status: MongoServiceStatus, message: str) -> EnsureMongoResult:
    return EnsureMongoResult(False, False, False, status, message)


def ensure_mongodb_running(
    *,
    mongo_uri: str,
    database: str,
    authorization_mode: AuthorizationMode = "auto",
    interactive: bool,
    graphical: bool = False,
    auto_start: bool = True,
    service_name: str = MONGODB_SERVICE,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    mongo_probe: Callable[[str, str], bool] = mongodb_reachable,
    which: Callable[[str], str | None] = shutil.which,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    startup_timeout: float = STARTUP_TIMEOUT,
    emit: Callable[[str], None] = print,
) -> EnsureMongoResult:
    """Start only an inactive mongod unit, then wait for systemd and PyMongo."""
    if authorization_mode not in {"none", "sudo", "pkexec", "auto"}:
        raise ValueError("Modo de autorización MongoDB no reconocido.")
    def inspect() -> MongoServiceStatus:
        return inspect_mongodb_service(
            mongo_uri,
            database,
            service_name=service_name,
            runner=runner,
            mongo_probe=mongo_probe,
            which=which,
        )
    status = inspect()
    if status.reachable:
        return EnsureMongoResult(True, False, False, status, "MongoDB ya está disponible.")
    if status.state is MongoServiceState.ACTIVE_BUT_UNREACHABLE:
        return _failure(
            status,
            "El servicio mongod está activo, pero MongoDB no responde. Revisa `make status`.",
        )
    if status.state is MongoServiceState.FAILED:
        return _failure(
            status,
            "El servicio mongod está en estado fallido. Revisa `make status` antes de iniciarlo.",
        )
    if status.state is MongoServiceState.SERVICE_NOT_FOUND:
        return _failure(status, "No se encontró el servicio `mongod` en systemd.")
    if status.state is MongoServiceState.SYSTEMD_UNAVAILABLE:
        return _failure(status, "systemd no está disponible para iniciar el servicio `mongod`.")
    if not auto_start or authorization_mode == "none":
        return _failure(
            status,
            "MongoDB está detenido. Inícialo con `sudo systemctl start mongod` y vuelve a intentar.",
        )

    resolved_mode = authorization_mode
    if resolved_mode == "auto":
        if graphical:
            resolved_mode = "pkexec"
        elif interactive:
            resolved_mode = "sudo"
        else:
            return _failure(
                status,
                "MongoDB está detenido y la sesión no es interactiva; no se intentó sudo. "
                "Inicia `mongod` o usa MONGO_AUTO_START=0 para sólo diagnosticar.",
            )
    if resolved_mode == "sudo" and not interactive:
        return _failure(
            status,
            "MongoDB está detenido y sudo requiere una terminal interactiva; no se solicitó contraseña.",
        )
    authorization = which(resolved_mode)
    systemctl = which("systemctl")
    if not authorization or not systemctl:
        mechanism = "diálogo gráfico pkexec" if resolved_mode == "pkexec" else "sudo"
        return _failure(
            status,
            f"MongoDB está detenido, pero no está disponible {mechanism}. "
            "Ejecuta `sudo systemctl start mongod` desde una terminal.",
        )

    emit("MongoDB está detenido. Se solicitará autorización para iniciar el servicio `mongod`.")
    try:
        started = runner(
            [authorization, systemctl, "start", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=AUTHORIZATION_TIMEOUT,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return _failure(status, "La autorización para iniciar MongoDB agotó el tiempo de espera.")
    except (OSError, subprocess.SubprocessError, ValueError):
        return _failure(status, "No fue posible solicitar autorización para iniciar MongoDB.")
    safe_error = sanitize_mongo_diagnostic(started.stderr, mongo_uri)
    cancelled = started.returncode in {126, 127} or any(
        marker in safe_error.casefold()
        for marker in ("cancel", "authentication failed", "incorrect password", "contraseña")
    )
    if started.returncode != 0:
        message = (
            "Inicio cancelado: MongoDB continúa detenido."
            if cancelled
            else "No fue posible iniciar el servicio `mongod`. Revisa `make status`."
        )
        return EnsureMongoResult(False, False, cancelled, status, message)

    deadline = monotonic() + max(0.1, startup_timeout)
    delay = 0.1
    latest = status
    while monotonic() < deadline:
        latest = inspect()
        if latest.reachable:
            return EnsureMongoResult(
                True,
                True,
                False,
                latest,
                "MongoDB: activo y accesible.",
            )
        if latest.state in {
            MongoServiceState.FAILED,
            MongoServiceState.SERVICE_NOT_FOUND,
            MongoServiceState.SYSTEMD_UNAVAILABLE,
        }:
            break
        sleep(delay)
        delay = min(delay * 2, 1.0)
    if latest.state is MongoServiceState.ACTIVE_BUT_UNREACHABLE:
        message = "El servicio mongod está activo, pero MongoDB no responde. Revisa `make status`."
    else:
        message = "MongoDB no quedó activo y accesible dentro del tiempo de espera."
    return EnsureMongoResult(False, True, False, latest, message)


__all__ = [
    "AuthorizationMode",
    "EnsureMongoResult",
    "MongoServiceState",
    "MongoServiceStatus",
    "ensure_mongodb_running",
    "inspect_mongodb_service",
    "mongo_status_lines",
    "mongodb_reachable",
    "sanitize_mongo_diagnostic",
]

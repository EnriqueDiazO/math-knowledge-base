"""Graphical launcher that safely ensures MongoDB before MathMongo."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path

from mathmongo.launcher import LaunchError
from mathmongo.launcher import require_unprivileged_user
from mathmongo.local_runtime.control import RuntimeController
from mathmongo.local_runtime.health import loopback_url
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.mongodb_service import AuthorizationMode
from mathmongo.mongodb_service import EnsureMongoResult
from mathmongo.mongodb_service import ensure_mongodb_running
from mathmongo.mongodb_service import sanitize_mongo_diagnostic
from mathmongo.paths import get_logs_dir
from mathmongo.paths import validate_mutable_path

DESKTOP_LOG_FILENAME = "desktop-launch.log"
MAX_LOG_BYTES = 1_000_000


def _safe_message(value: object, mongo_uri: str) -> str:
    return sanitize_mongo_diagnostic(value, mongo_uri)


def _desktop_log_path() -> Path:
    logs_dir = validate_mutable_path(get_logs_dir())
    path = validate_mutable_path(logs_dir / DESKTOP_LOG_FILENAME, allowed_root=logs_dir)
    rotated = validate_mutable_path(logs_dir / f"{DESKTOP_LOG_FILENAME}.1", allowed_root=logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    logs_dir.chmod(0o700)
    if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
        path.replace(rotated)
    return path


def _append_log(path: Path, message: str) -> None:
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")
    path.chmod(0o600)


def send_desktop_notification(
    message: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> None:
    """Best-effort notification; the private log remains the source of detail."""
    notify_send = which("notify-send")
    if not notify_send:
        return
    try:
        runner(
            [notify_send, "MathMongo", message[:300]],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return


def launch_desktop_runtime(
    settings: RuntimeSettings,
    *,
    mongo_uri: str,
    authorization_mode: AuthorizationMode = "auto",
    auto_start: bool = True,
    ensure: Callable[..., EnsureMongoResult] = ensure_mongodb_running,
    controller_factory: Callable[..., RuntimeController] = RuntimeController,
    browser_open: Callable[..., bool] = webbrowser.open,
    notify: Callable[[str], None] = send_desktop_notification,
    log_path_resolver: Callable[[], Path] = _desktop_log_path,
) -> int:
    """Ensure MongoDB, start the verified runtime, and open its local URL."""
    try:
        require_unprivileged_user()
    except LaunchError as exc:
        notify(str(exc))
        raise LocalRuntimeError(str(exc)) from exc

    try:
        log_path = log_path_resolver()
    except (OSError, ValueError, RuntimeError) as exc:
        message = "No se pudo preparar el log privado del acceso directo."
        notify(message)
        raise LocalRuntimeError(message) from exc

    def emit(value: str) -> None:
        try:
            _append_log(log_path, _safe_message(value, mongo_uri))
        except (OSError, ValueError):
            return

    emit("Inicio solicitado desde el acceso directo.")
    result = ensure(
        mongo_uri=mongo_uri,
        database=settings.database,
        authorization_mode=authorization_mode,
        interactive=False,
        graphical=True,
        auto_start=auto_start,
        emit=emit,
    )
    emit(result.message)
    if not result.ok:
        notify(result.message)
        return 6

    environment = dict(os.environ)
    environment["STREAMLIT_SERVER_HEADLESS"] = "true"
    controller = controller_factory(settings, mongo_uri=mongo_uri, environment=environment)
    try:
        action = controller.start()
    except LocalRuntimeError as exc:
        safe_error = _safe_message(exc, mongo_uri)
        emit(f"Error de runtime: {safe_error}")
        notify(safe_error)
        return 6

    url = loopback_url(settings.streamlit_host, settings.streamlit_port)
    emit(action.message)
    emit(f"Streamlit listo: {url}")
    try:
        opened = bool(browser_open(url, new=2))
    except (OSError, ValueError, webbrowser.Error):
        opened = False
    if not opened:
        message = f"MathMongo está activo. Abre {url} en el navegador."
        emit(message)
        notify(message)
    return 0


def desktop_error(message: object, mongo_uri: str) -> int:
    """Print a safe fallback for callers that cannot initialize desktop logging."""
    print(f"Error: {_safe_message(message, mongo_uri)}", file=sys.stderr)
    return 6


__all__ = [
    "DESKTOP_LOG_FILENAME",
    "desktop_error",
    "launch_desktop_runtime",
    "send_desktop_notification",
]

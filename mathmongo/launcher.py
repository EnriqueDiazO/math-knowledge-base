"""Reusable Streamlit launcher for MathMongo."""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from mathmongo.config import DEFAULT_MONGO_URI
from mathmongo.config import redact_mongo_uri
from mathmongo.paths import get_logs_dir
from mathmongo.paths import validate_mutable_path

DEFAULT_ADDRESS = "localhost"
DEFAULT_PORT = 8501
LOOPBACK_ADDRESSES = frozenset({"localhost", "127.0.0.1", "::1"})
MONGODB_URI = DEFAULT_MONGO_URI


class LaunchError(RuntimeError):
    """A user-facing launch failure that does not require a traceback."""


def resolve_streamlit_app() -> Path:
    """Resolve the installed editor entry point without importing its UI."""
    spec = importlib.util.find_spec("editor")
    if spec is None or not spec.submodule_search_locations:
        raise LaunchError("No se pudo localizar el paquete 'editor' instalado.")
    app_path = Path(next(iter(spec.submodule_search_locations))) / "editor_streamlit.py"
    if not app_path.is_file():
        raise LaunchError(f"No se localizó la aplicación Streamlit esperada: {app_path}")
    return app_path.resolve()


def validate_address(address: str) -> str:
    """Allow only explicit loopback addresses in the local launcher."""
    if address not in LOOPBACK_ADDRESSES:
        raise LaunchError(
            "La dirección debe limitarse a loopback: localhost, 127.0.0.1 o ::1."
        )
    return address


def validate_port(port: int) -> int:
    """Validate a TCP user port."""
    if not 1 <= port <= 65535:
        raise LaunchError("El puerto debe estar entre 1 y 65535.")
    return port


def streamlit_available() -> bool:
    """Return whether Streamlit is importable by the active interpreter."""
    return importlib.util.find_spec("streamlit") is not None


def mongodb_available(uri: str = MONGODB_URI) -> bool:
    """Check the existing local MongoDB prerequisite without changing it."""
    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        try:
            client.admin.command("ping")
        finally:
            client.close()
        return True
    except Exception:
        return False


def port_available(address: str, port: int) -> bool:
    """Check whether a loopback port can be bound without disturbing listeners."""
    family = socket.AF_INET6 if address == "::1" else socket.AF_INET
    bind_address = address if address != "localhost" else "127.0.0.1"
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            # Match Streamlit's reusable listener semantics so a recently closed
            # server in TIME_WAIT is not mistaken for an active foreign listener.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((bind_address, port))
    except OSError:
        return False
    return True


def build_streamlit_command(
    app_path: Path,
    *,
    address: str = DEFAULT_ADDRESS,
    port: int = DEFAULT_PORT,
    no_browser: bool = False,
    executable: str | None = None,
) -> list[str]:
    """Build the Streamlit command using the current Python interpreter."""
    command = [
        executable or sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        validate_address(address),
        "--server.port",
        str(validate_port(port)),
    ]
    if no_browser:
        command.extend(["--server.headless", "true"])
    return command


def launch_mathmongo(
    *,
    address: str = DEFAULT_ADDRESS,
    port: int = DEFAULT_PORT,
    no_browser: bool = False,
    mongodb_uri: str = MONGODB_URI,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    dependency_check: Callable[[], bool] = streamlit_available,
    mongodb_check: Callable[[str], bool] = mongodb_available,
    port_check: Callable[[str, int], bool] = port_available,
    app_resolver: Callable[[], Path] = resolve_streamlit_app,
    executable: str | None = None,
    desktop_launch: bool = False,
) -> int:
    """Validate prerequisites, run Streamlit, and return a useful exit code."""
    address = validate_address(address)
    port = validate_port(port)
    if not dependency_check():
        raise LaunchError(
            "Streamlit no está disponible en el intérprete activo. Instala MathMongo con sus dependencias."
        )
    if not mongodb_check(mongodb_uri):
        raise LaunchError(
            f"MongoDB no está disponible en {redact_mongo_uri(mongodb_uri)}. "
            "Inicia el servicio local antes de ejecutar MathMongo."
        )
    if not port_check(address, port):
        raise LaunchError(
            f"El puerto {port} ya está ocupado en {address}. Usa --port con otro puerto."
        )
    command = build_streamlit_command(
        app_resolver(),
        address=address,
        port=port,
        no_browser=no_browser,
        executable=executable,
    )
    try:
        if desktop_launch:
            logs_dir = validate_mutable_path(get_logs_dir())
            log_path = validate_mutable_path(
                logs_dir / "streamlit.log",
                allowed_root=logs_dir,
            )
            rotated_log = validate_mutable_path(
                logs_dir / "streamlit.log.1",
                allowed_root=logs_dir,
            )
            logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            logs_dir.chmod(0o700)
            if log_path.exists() and log_path.stat().st_size > 1_000_000:
                log_path.replace(rotated_log)
            with log_path.open("a", encoding="utf-8") as log_file:
                log_path.chmod(0o600)
                result = runner(command, check=False, stdout=log_file, stderr=subprocess.STDOUT)
        else:
            result = runner(command, check=False)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        raise LaunchError(f"No se pudo ejecutar Streamlit: {exc}") from exc
    return int(result.returncode)

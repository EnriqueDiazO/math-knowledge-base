"""Explicit loopback-only launcher for the Advanced Reader ASGI app."""

# ruff: noqa: D103

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Callable
from collections.abc import Sequence
from typing import Any

from mathmongo.advanced_reader.app import create_app
from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.advanced_reader.security import validate_loopback_host
from mathmongo.config import resolve_config
from mathmongo.launcher import port_available

DEFAULT_ADVANCED_READER_HOST = "127.0.0.1"
DEFAULT_ADVANCED_READER_PORT = 8766
LOG_LEVELS = ("critical", "error", "warning", "info", "debug")


class AdvancedReaderLaunchError(RuntimeError):
    """A safe launcher error that never carries a MongoDB URI or local path."""


def validate_port(port: int) -> int:
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise AdvancedReaderLaunchError("El puerto debe estar entre 1 y 65535.")
    return port


def validate_database_name(value: str) -> str:
    name = " ".join(str(value or "").strip().split())
    forbidden = set('/\\."$*<>:|?\x00')
    if not name or len(name.encode("utf-8")) > 64 or any(char in forbidden for char in name):
        raise AdvancedReaderLaunchError("El nombre de base configurado no es válido.")
    return name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mathmongo.advanced_reader",
        description="Inicia el lector PDF avanzado local de MathMongo.",
    )
    parser.add_argument("--host", help="Dirección loopback (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, help="Puerto local (default: 8766).")
    parser.add_argument("--database", help="Base de MathMongo configurada.")
    parser.add_argument(
        "--mongo-uri",
        help="URI MongoDB opcional; su valor nunca se imprime.",
    )
    parser.add_argument("--log-level", choices=LOG_LEVELS, default="info")
    return parser


def dependencies_from_client(
    client: Any,
    *,
    database_name: str,
) -> AdvancedReaderDependencies:
    return AdvancedReaderDependencies.from_database(
        client[database_name],
        database_name=database_name,
        health_check=lambda: bool(client.admin.command("ping")),
    )


def launch_advanced_reader(
    *,
    host: str,
    port: int,
    database_name: str,
    mongo_uri: str,
    log_level: str,
    client_factory: Callable[..., Any] | None = None,
    server_runner: Callable[..., Any] | None = None,
    port_check: Callable[[str, int], bool] = port_available,
) -> int:
    try:
        bind_host = validate_loopback_host(host)
    except ValueError as exc:
        raise AdvancedReaderLaunchError(
            "El servidor sólo puede escuchar en localhost, 127.0.0.1 o ::1."
        ) from exc
    bind_port = validate_port(port)
    database = validate_database_name(database_name)
    if log_level not in LOG_LEVELS:
        raise AdvancedReaderLaunchError("El nivel de log no es válido.")
    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("uvicorn") is None:
        raise AdvancedReaderLaunchError(
            "FastAPI y Uvicorn deben estar instalados en el entorno de MathMongo."
        )
    if not port_check(bind_host, bind_port):
        raise AdvancedReaderLaunchError(
            f"El puerto {bind_port} ya está ocupado en la interfaz loopback elegida."
        )
    if client_factory is None:
        from pymongo import MongoClient

        client_factory = MongoClient
    client = None
    try:
        client = client_factory(
            mongo_uri,
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        client.admin.command("ping")
        dependencies = dependencies_from_client(client, database_name=database)
        app = create_app(dependencies)
        if server_runner is None:
            import uvicorn

            server_runner = uvicorn.run
        server_runner(
            app,
            host=bind_host,
            port=bind_port,
            log_level=log_level,
            access_log=False,
        )
    except KeyboardInterrupt:
        return 130
    except AdvancedReaderLaunchError:
        raise
    except Exception as exc:
        raise AdvancedReaderLaunchError(
            "No se pudo iniciar el lector avanzado con la configuración local."
        ) from exc
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = resolve_config(
        explicit={
            "advanced_reader_host": args.host,
            "advanced_reader_port": args.port,
            "mongo_database": args.database,
            "mongo_uri": args.mongo_uri,
        }
    )
    if not settings.advanced_reader_enabled:
        print("Error: El lector avanzado está deshabilitado en la configuración.", file=sys.stderr)
        return 1
    try:
        return launch_advanced_reader(
            host=settings.advanced_reader_host,
            port=settings.advanced_reader_port,
            database_name=settings.mongo_database,
            mongo_uri=settings.mongo_uri,
            log_level=args.log_level,
        )
    except AdvancedReaderLaunchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


__all__ = [
    "AdvancedReaderLaunchError",
    "build_parser",
    "dependencies_from_client",
    "launch_advanced_reader",
    "main",
    "validate_database_name",
    "validate_port",
]

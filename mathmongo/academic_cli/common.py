"""Common configuration, output, and safety policy for academic CLI commands."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from dataclasses import is_dataclass
from datetime import date
from datetime import datetime
from enum import Enum
from enum import IntEnum
from typing import Any

from mathmongo.config import AppConfig
from mathmongo.config import redact_mongo_uri
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error


class ExitCode(IntEnum):
    """Documented stable process results for scripts and human invocations."""

    SUCCESS = 0
    VALIDATION = 2
    NOT_FOUND = 3
    CONFLICT = 4
    PARTIAL = 5
    CONNECTION = 6
    FILE_MEDIA = 7
    CANCELLED = 8


class AcademicCliError(RuntimeError):
    """A controlled message and exit status for one CLI invocation."""

    def __init__(self, message: str, code: ExitCode = ExitCode.VALIDATION) -> None:
        """Retain a nonzero, documented exit code with the safe message."""
        super().__init__(message)
        self.code = code


def add_common_options(parser: argparse.ArgumentParser) -> None:
    """Attach uniform non-secret options to one concrete academic command."""
    parser.add_argument("--database", help="Base MongoDB explícita para este comando.")
    parser.add_argument("--mongo-uri", help="URI MongoDB de esta invocación; nunca se imprime.")
    parser.add_argument("--output", choices=("table", "json"), default="table")
    parser.add_argument("--quiet", action="store_true", help="Suprime mensajes humanos no esenciales.")
    parser.add_argument("--verbose", action="store_true", help="Muestra diagnósticos seguros adicionales.")


def command_config(args: argparse.Namespace) -> AppConfig:
    """Resolve only public CLI overrides; parsing itself never opens MongoDB."""
    return resolve_config(
        explicit={
            "mongo_database": getattr(args, "database", None),
            "mongo_uri": getattr(args, "mongo_uri", None),
        }
    )


def selected_database(args: argparse.Namespace) -> str:
    """Return the unambiguous destination name displayed for every operation."""
    database = str(command_config(args).mongo_database or "").strip()
    if not database:
        raise AcademicCliError("La base destino es ambigua; usa --database.")
    return database


def connect_database(args: argparse.Namespace) -> tuple[Any, Any, AppConfig]:
    """Connect after parsing and return one explicit database handle.

    Read commands never call index initializers, cache writers, or collection
    creators. Services receive this exact database handle rather than creating a
    second persistence path in the CLI.
    """
    config = command_config(args)
    try:
        from pymongo import MongoClient

        client = MongoClient(config.mongo_uri, serverSelectionTimeoutMS=5000)
        database = client[config.mongo_database]
        client.admin.command("ping")
    except Exception as exc:
        message = sanitize_mongo_error(exc, config.mongo_uri)
        raise AcademicCliError(
            "No fue posible comunicarse con MongoDB. Verifica el estado del servicio y "
            f"vuelve a probar la conexión. Base configurada: {config.mongo_database}. "
            f"Host: {redact_mongo_uri(config.mongo_uri)}. Consulta `make status`. "
            f"Detalle: {message}",
            ExitCode.CONNECTION,
        ) from exc
    return client, database, config


def close_client(client: Any | None) -> None:
    """Close a PyMongo client when a concrete command finishes."""
    if client is not None:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def json_value(value: Any) -> Any:
    """Convert models and BSON-adjacent values to portable JSON values."""
    if hasattr(value, "model_dump"):
        return json_value(value.model_dump(mode="json"))
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [json_value(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if value.__class__.__name__ == "ObjectId":
        return str(value)
    return value


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, list | tuple | set):
        return ", ".join(_cell(item) for item in value)
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= 72 else text[:69].rstrip() + "…"


def emit(args: argparse.Namespace, value: Any, *, columns: tuple[str, ...] = ()) -> None:
    """Write clean table or JSON only to stdout."""
    payload = json_value(value)
    if getattr(args, "output", "table") == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
        return
    rows = payload if isinstance(payload, list) else [payload]
    if not rows:
        print("Sin resultados.")
        return
    normalized_rows = [row if isinstance(row, dict) else {"value": row} for row in rows]
    headers = columns or tuple(normalized_rows[0])
    widths = {
        header: max(len(header), *[len(_cell(row.get(header))) for row in normalized_rows])
        for header in headers
    }
    print("  ".join(header.ljust(widths[header]) for header in headers))
    print("  ".join("-" * widths[header] for header in headers))
    for row in normalized_rows:
        print("  ".join(_cell(row.get(header)).ljust(widths[header]) for header in headers))


def diagnostic(args: argparse.Namespace, message: str) -> None:
    """Send optional non-secret diagnostic output to stderr."""
    if getattr(args, "verbose", False) and not getattr(args, "quiet", False):
        print(message, file=sys.stderr)


def require_apply_confirmation(args: argparse.Namespace, *, operation: str) -> bool:
    """Apply the universal preview/apply contract without writing during a preview."""
    apply_requested = bool(getattr(args, "apply", False))
    yes_requested = validate_write_options(args)
    if not apply_requested:
        diagnostic(args, f"Vista previa de {operation}; no se escribirá en MongoDB ni XDG.")
        return False
    if yes_requested:
        return True
    if not sys.stdin.isatty():
        raise AcademicCliError(
            "La operación requiere confirmación interactiva; usa --apply --yes para automatización.",
            ExitCode.CANCELLED,
        )
    answer = input(f"Aplicar {operation} en {selected_database(args)}? [y/N] ").strip().casefold()
    if answer not in {"y", "yes", "s", "sí", "si"}:
        raise AcademicCliError("Operación cancelada.", ExitCode.CANCELLED)
    return True


def validate_write_options(args: argparse.Namespace) -> bool:
    """Reject an automation acknowledgement unless the caller requested application."""
    apply_requested = bool(getattr(args, "apply", False))
    yes_requested = bool(getattr(args, "yes", False))
    if yes_requested and not apply_requested:
        raise AcademicCliError("--yes sólo es válido junto con --apply.")
    return yes_requested

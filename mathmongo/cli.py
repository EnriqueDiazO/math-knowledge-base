"""Argument parser for the MathMongo launcher."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING

from mathmongo import __version__
from mathmongo.config import active_database_diagnostic
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error
from mathmongo.launcher import LaunchError
from mathmongo.launcher import launch_mathmongo
from mathmongo.paths import get_logs_dir
from mathmongo.paths import validate_mutable_path

if TYPE_CHECKING:
    from mathmongo.local_runtime.models import RuntimeSettings
    from mathmongo.local_runtime.state import ProcessIdentity
    from mathmongo.local_runtime.state import RuntimeObservation

# Keep this vocabulary local so ``import mathmongo.cli`` does not import the
# runtime supervisor (whose execution-only dependencies include PyMongo).
RUNTIME_LOG_LEVELS = ("critical", "error", "warning", "info", "debug")
MONGO_AUTHORIZATION_MODES = ("auto", "sudo", "pkexec", "none")


def _add_run_options(parser: argparse.ArgumentParser, *, suppress_defaults: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument("--port", type=int, default=default, help="Puerto local (8501).")
    parser.add_argument(
        "--address", default=default, help="Dirección loopback (localhost)."
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        default=default,
        help="No solicitar apertura automática del navegador.",
    )
    parser.add_argument(
        "--desktop-launch", action="store_true", default=default, help=argparse.SUPPRESS
    )


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", help="Base MongoDB para este runtime local.")
    parser.add_argument("--streamlit-host", help="Host loopback de Streamlit.")
    parser.add_argument("--streamlit-port", type=int, help="Puerto loopback de Streamlit.")
    parser.add_argument("--advanced-reader-host", help="Host loopback del Advanced Reader.")
    parser.add_argument("--advanced-reader-port", type=int, help="Puerto loopback del Advanced Reader.")
    parser.add_argument("--mongo-uri", help="URI MongoDB sólo para esta invocación; nunca se muestra.")
    parser.add_argument("--log-level", choices=RUNTIME_LOG_LEVELS, help="Nivel de diagnóstico local.")
    parser.add_argument(
        "--mongo-auth-mode",
        choices=MONGO_AUTHORIZATION_MODES,
        default="auto",
        help="Autorización para iniciar mongod: auto, sudo, pkexec o none.",
    )
    parser.add_argument(
        "--no-mongo-auto-start",
        action="store_true",
        help="No intentar iniciar mongod; sólo informar cómo resolverlo.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without importing Streamlit or connecting to MongoDB."""
    parser = argparse.ArgumentParser(
        prog="mathmongo",
        description="Controla el runtime y las operaciones académicas seguras de MathMongo.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_run_options(parser)
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Inicia la aplicación Streamlit.")
    _add_run_options(run_parser, suppress_defaults=True)
    subparsers.add_parser(
        "config",
        help="Muestra producto y base configurada sin conectarse.",
    )
    runtime_parser = subparsers.add_parser(
        "runtime",
        help="Inspecciona y controla únicamente el runtime local verificado.",
    )
    runtime_subparsers = runtime_parser.add_subparsers(dest="runtime_command", required=True)
    for name, help_text in (
        ("status", "Muestra el estado sin escribir ni detener procesos."),
        ("doctor", "Comprueba el runtime y MongoDB sin modificar servicios."),
        ("mongo-ensure", "Asegura únicamente el servicio mongod cuando está detenido."),
        ("start", "Asegura MongoDB e inicia un supervisor local en segundo plano."),
        ("run", "Asegura MongoDB y ejecuta el supervisor local en primer plano."),
    ):
        command_parser = runtime_subparsers.add_parser(name, help=help_text)
        _add_runtime_options(command_parser)
    stop_parser = runtime_subparsers.add_parser(
        "stop", help="Detiene únicamente un runtime con identidad confirmada."
    )
    _add_runtime_options(stop_parser)
    stop_parser.add_argument(
        "--force",
        action="store_true",
        help="Después de SIGTERM, permite SIGKILL sólo para PIDs ya verificados.",
    )
    restart_parser = runtime_subparsers.add_parser(
        "restart", help="Reinicia un runtime confirmado de forma segura."
    )
    _add_runtime_options(restart_parser)
    restart_parser.add_argument(
        "--recover-orphan",
        action="store_true",
        help="Recupera explícitamente un huérfano que coincida exactamente con este repositorio.",
    )
    restart_parser.add_argument(
        "--force",
        action="store_true",
        help="Permite SIGKILL sólo tras un cierre SIGTERM fallido del runtime confirmado.",
    )
    # Academic command handlers import repositories and domain models that
    # depend on PyMongo.  Keep the module entry point light: importing
    # ``mathmongo.cli`` must never load those dependencies or touch MongoDB.
    # They are needed only when a parser is actually constructed.
    from mathmongo.academic_cli.catalog import install_catalog_commands
    from mathmongo.academic_cli.documents import install_document_commands

    install_catalog_commands(subparsers)
    install_document_commands(subparsers)
    return parser


def _runtime_settings(args: argparse.Namespace, config) -> RuntimeSettings:
    from mathmongo.local_runtime.models import RuntimeSettings

    configured_streamlit_host = config.streamlit_address
    if configured_streamlit_host == "localhost":
        configured_streamlit_host = "127.0.0.1"
    return RuntimeSettings(
        database=getattr(args, "database", None) or config.mongo_database,
        streamlit_host=getattr(args, "streamlit_host", None) or configured_streamlit_host,
        streamlit_port=getattr(args, "streamlit_port", None) or config.streamlit_port,
        advanced_reader_host=getattr(args, "advanced_reader_host", None)
        or config.advanced_reader_host,
        advanced_reader_port=getattr(args, "advanced_reader_port", None)
        or config.advanced_reader_port,
        log_level=getattr(args, "log_level", None) or "info",
    )


def _print_identity(label: str, identity: ProcessIdentity | None) -> None:
    from mathmongo.local_runtime.processes import sanitize_log_line

    if identity is None:
        print(f"{label}: no identificado")
        return
    command = sanitize_log_line(" ".join(identity.command))
    print(f"{label}: PID {identity.pid}")
    print(f"  CWD: {identity.cwd}")
    print(f"  Comando: {command}")


def _print_runtime_observation(
    observation: RuntimeObservation,
    settings: RuntimeSettings,
) -> None:
    print(f"Runtime: {observation.kind.value}")
    print(observation.message)
    print(f"Streamlit: {settings.streamlit_host}:{settings.streamlit_port}")
    print(f"Advanced Reader: {settings.advanced_reader_host}:{settings.advanced_reader_port}")
    _print_identity("Supervisor", observation.supervisor)
    _print_identity("Streamlit", observation.streamlit)
    _print_identity("Advanced Reader", observation.advanced_reader)


def _inspect_mongo(settings: RuntimeSettings, mongo_uri: str):
    from mathmongo.mongodb_service import inspect_mongodb_service

    return inspect_mongodb_service(mongo_uri, settings.database)


def _print_mongo_status(status) -> None:
    from mathmongo.mongodb_service import mongo_status_lines

    for line in mongo_status_lines(status):
        print(line)


def _ensure_mongo(args: argparse.Namespace, settings: RuntimeSettings, mongo_uri: str):
    from mathmongo.local_runtime.models import LocalRuntimeError
    from mathmongo.mongodb_service import ensure_mongodb_running

    result = ensure_mongodb_running(
        mongo_uri=mongo_uri,
        database=settings.database,
        authorization_mode=getattr(args, "mongo_auth_mode", "auto"),
        interactive=sys.stdin.isatty(),
        auto_start=not getattr(args, "no_mongo_auto_start", False),
    )
    if not result.ok:
        raise LocalRuntimeError(result.message)
    print(result.message)
    return result


def _require_application_user() -> None:
    from mathmongo.launcher import require_unprivileged_user

    try:
        require_unprivileged_user()
    except LaunchError as exc:
        from mathmongo.local_runtime.models import LocalRuntimeError

        raise LocalRuntimeError(str(exc)) from exc


def _run_runtime_command(args: argparse.Namespace, config) -> int:
    from mathmongo.local_runtime.control import RuntimeController
    from mathmongo.local_runtime.models import LocalRuntimeError

    settings = _runtime_settings(args, config)
    controller = RuntimeController(
        settings,
        mongo_uri=args.mongo_uri or config.mongo_uri,
    )
    mongo_uri = args.mongo_uri or config.mongo_uri
    command = args.runtime_command
    if command == "status":
        _print_runtime_observation(controller.status(), settings)
        return 0
    if command == "doctor":
        observation = controller.status()
        mongo_status = _inspect_mongo(settings, mongo_uri)
        _print_runtime_observation(observation, settings)
        _print_mongo_status(mongo_status)
        if not mongo_status.reachable:
            print("No fue posible comunicarse con MongoDB. Verifica el estado del servicio y vuelve a probar la conexión.")
            return 6
        return 0
    if command == "mongo-ensure":
        _require_application_user()
        _ensure_mongo(args, settings, mongo_uri)
        return 0
    if command in {"start", "run", "restart"}:
        _require_application_user()
        _ensure_mongo(args, settings, mongo_uri)
    if command == "start":
        action = controller.start()
    elif command == "run":
        from mathmongo.local_runtime.launcher import LocalRuntimeSupervisor

        environment = dict(os.environ)
        environment["MONGODB_URI"] = mongo_uri
        environment["MONGODB_DB"] = settings.database
        return LocalRuntimeSupervisor(settings, base_environment=environment).run()
    elif command == "stop":
        action = controller.stop(force=args.force)
    elif command == "restart":
        action = controller.restart(
            recover_orphan=args.recover_orphan,
            force=args.force,
        )
    else:  # pragma: no cover - argparse owns the command vocabulary.
        raise LocalRuntimeError("Comando de runtime no reconocido.")
    print(action.message)
    _print_runtime_observation(action.observation, settings)
    if action.observation.kind.value == "owned":
        from mathmongo.local_runtime.health import loopback_url

        print(f"Streamlit: {loopback_url(settings.streamlit_host, settings.streamlit_port)}")
        print(
            "Advanced Reader: "
            f"{loopback_url(settings.advanced_reader_host, settings.advanced_reader_port)}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and translate expected launch failures into exit code 1."""
    args = build_parser().parse_args(argv)
    handler = getattr(args, "academic_handler", None)
    if handler is not None:
        from mathmongo.academic_cli.common import AcademicCliError

        try:
            return int(handler(args))
        except AcademicCliError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return int(exc.code)
    settings = resolve_config(
        explicit={
            "streamlit_address": getattr(args, "address", None),
            "streamlit_port": getattr(args, "port", None),
            "browser_enabled": False if getattr(args, "no_browser", False) else None,
        }
    )
    if args.command == "config":
        diagnostic = active_database_diagnostic(settings)
        print(f"Producto: {diagnostic['product']}")
        print(f"Base activa: {diagnostic['database']}")
        print(f"MongoDB: {diagnostic['mongo_uri']}")
        return 0
    if args.command == "runtime":
        from mathmongo.local_runtime.models import LocalRuntimeError

        try:
            return _run_runtime_command(args, settings)
        except LocalRuntimeError as exc:
            print(f"Error: {sanitize_mongo_error(exc, getattr(args, 'mongo_uri', None) or settings.mongo_uri)}", file=sys.stderr)
            return 6
    try:
        return launch_mathmongo(
            address=settings.streamlit_address,
            port=settings.streamlit_port,
            no_browser=not settings.browser_enabled,
            mongodb_uri=settings.mongo_uri,
            desktop_launch=getattr(args, "desktop_launch", False)
            or os.getenv("MATHMONGO_DESKTOP") == "1",
        )
    except LaunchError as exc:
        safe_error = sanitize_mongo_error(exc, settings.mongo_uri)
        if getattr(args, "desktop_launch", False) or os.getenv("MATHMONGO_DESKTOP") == "1":
            try:
                logs_dir = validate_mutable_path(get_logs_dir())
                launcher_log = validate_mutable_path(
                    logs_dir / "launcher.log",
                    allowed_root=logs_dir,
                )
                logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                logs_dir.chmod(0o700)
                with launcher_log.open("a", encoding="utf-8") as handle:
                    handle.write(f"Launch error: {safe_error}\n")
                launcher_log.chmod(0o600)
            except (OSError, ValueError):
                pass
        print(f"Error: {safe_error}", file=sys.stderr)
        return 1

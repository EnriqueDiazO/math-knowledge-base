"""Argument parser for the MathMongo launcher."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from mathmongo import __version__
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error
from mathmongo.launcher import LaunchError
from mathmongo.launcher import launch_mathmongo
from mathmongo.paths import get_logs_dir
from mathmongo.paths import validate_mutable_path


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


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without importing Streamlit or connecting to MongoDB."""
    parser = argparse.ArgumentParser(prog="mathmongo", description="Inicia la aplicación MathMongo.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_run_options(parser)
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Inicia la aplicación Streamlit.")
    _add_run_options(run_parser, suppress_defaults=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and translate expected launch failures into exit code 1."""
    args = build_parser().parse_args(argv)
    settings = resolve_config(
        explicit={
            "streamlit_address": getattr(args, "address", None),
            "streamlit_port": getattr(args, "port", None),
            "browser_enabled": False if getattr(args, "no_browser", False) else None,
        }
    )
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

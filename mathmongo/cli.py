"""Argument parser for the MathMongo launcher."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from mathmongo import __version__
from mathmongo.launcher import DEFAULT_ADDRESS
from mathmongo.launcher import DEFAULT_PORT
from mathmongo.launcher import LaunchError
from mathmongo.launcher import launch_mathmongo


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Puerto local (8501).")
    parser.add_argument(
        "--address", default=DEFAULT_ADDRESS, help="Dirección loopback (localhost)."
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="No solicitar apertura automática del navegador."
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without importing Streamlit or connecting to MongoDB."""
    parser = argparse.ArgumentParser(prog="mathmongo", description="Inicia la aplicación MathMongo.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    _add_run_options(parser)
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Inicia la aplicación Streamlit.")
    _add_run_options(run_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and translate expected launch failures into exit code 1."""
    args = build_parser().parse_args(argv)
    try:
        return launch_mathmongo(
            address=args.address,
            port=args.port,
            no_browser=args.no_browser,
        )
    except LaunchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

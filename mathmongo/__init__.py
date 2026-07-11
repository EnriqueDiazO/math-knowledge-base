"""Installable command-line entry point for MathMongo."""

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
from pathlib import Path


def _project_version() -> str:
    """Read installed metadata, falling back to the checkout's single Poetry source."""
    try:
        return version("mathmongo")
    except PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        try:
            text = pyproject.read_text(encoding="utf-8")
            poetry_section = text.split("[tool.poetry]", 1)[1].split("\n[", 1)[0]
            match = re.search(r'^version\s*=\s*"([^"]+)"', poetry_section, re.MULTILINE)
            if match:
                return match.group(1)
            raise ValueError("missing Poetry version")
        except (OSError, IndexError, ValueError) as exc:
            raise RuntimeError("No se pudo determinar la versión de MathMongo.") from exc


__version__ = _project_version()

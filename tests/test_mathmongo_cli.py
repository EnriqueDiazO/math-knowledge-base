"""Tests for both MathMongo command entry paths."""

# ruff: noqa: D103

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mathmongo import __version__
from mathmongo.cli import main


@pytest.mark.parametrize("arguments", [["--help"], ["run", "--help"]])
def test_cli_help(arguments: list[str], capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(arguments)
    assert exc_info.value.code == 0
    assert "usage: mathmongo" in capsys.readouterr().out


def test_cli_version_has_single_metadata_source(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"mathmongo {__version__}"


@pytest.mark.parametrize("arguments", [[], ["run"]])
def test_default_command_and_explicit_run_are_equivalent(arguments, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("mathmongo.cli.launch_mathmongo", lambda **kwargs: calls.append(kwargs) or 0)
    assert main(arguments) == 0
    assert calls == [{"address": "localhost", "port": 8501, "no_browser": False}]


def test_cli_forwards_custom_run_options(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("mathmongo.cli.launch_mathmongo", lambda **kwargs: calls.append(kwargs) or 0)
    assert main(["run", "--port", "8502", "--address", "::1", "--no-browser"]) == 0
    assert calls == [{"address": "::1", "port": 8502, "no_browser": True}]


@pytest.mark.parametrize("arguments", [["--help"], ["--version"]])
def test_python_module_entrypoint(arguments: list[str], tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root)
    result = subprocess.run(
        [sys.executable, "-m", "mathmongo", *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "mathmongo" in result.stdout.lower()


def test_run_gui_is_thin_compatible_wrapper() -> None:
    source = (Path(__file__).resolve().parents[1] / "run_gui.py").read_text()
    assert "from mathmongo.cli import main" in source
    assert "raise SystemExit(main())" in source


def test_importing_cli_does_not_import_streamlit_or_pymongo() -> None:
    code = (
        "import sys; import mathmongo.cli; "
        "assert 'streamlit' not in sys.modules; assert 'pymongo' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

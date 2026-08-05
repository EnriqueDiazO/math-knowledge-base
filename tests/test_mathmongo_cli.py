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
from mathmongo.config import AppConfig
from mathmongo.config import resolve_config
from mathmongo.launcher import LaunchError
from mathmongo.local_runtime.control import RuntimeAction
from mathmongo.local_runtime.state import RuntimeObservation
from mathmongo.local_runtime.state import RuntimeStateKind

_CLI_CONFIGURATION_ENVIRONMENT = (
    "MONGODB_URI",
    "MONGO_URI",
    "MONGODB_DB",
    "MONGO_DB",
    "DB_NAME",
    "MATHMONGO_EXPORT_DIRECTORY",
    "MATHMONGO_STREAMLIT_ADDRESS",
    "MATHMONGO_STREAMLIT_PORT",
    "MATHMONGO_BROWSER_ENABLED",
    "MATHMONGO_ADVANCED_READER_ENABLED",
    "MATHMONGO_ADVANCED_READER_HOST",
    "MATHMONGO_ADVANCED_READER_PORT",
    "MATHMONGO_ADVANCED_READER_URL",
    "MATHMONGO_DESKTOP",
)


def _configure_cli_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    mongo_uri: str,
    mongo_database: str,
) -> None:
    """Set every configuration input used by launcher tests explicitly."""
    for name in _CLI_CONFIGURATION_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    for name, value in {
        "HOME": tmp_path / "home",
        "XDG_CONFIG_HOME": tmp_path / "config",
        "XDG_DATA_HOME": tmp_path / "data",
        "XDG_CACHE_HOME": tmp_path / "cache",
        "XDG_STATE_HOME": tmp_path / "state",
        "XDG_RUNTIME_DIR": tmp_path / "runtime",
        "MONGODB_URI": mongo_uri,
        "MONGODB_DB": mongo_database,
    }.items():
        monkeypatch.setenv(name, str(value))


@pytest.mark.parametrize(
    "arguments",
    [["--help"], ["run", "--help"], ["source", "--help"], ["document", "--help"]],
)
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


def test_config_command_reports_product_and_active_database_without_launching(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "mathmongo.cli.resolve_config",
        lambda **_kwargs: AppConfig(
            mongo_uri="mongodb://teacher:secret@localhost:27017/MathV0",
            mongo_database="MathV0",
        ),
    )
    monkeypatch.setattr(
        "mathmongo.cli.launch_mathmongo",
        lambda **_kwargs: pytest.fail("config must not launch Streamlit or connect to MongoDB"),
    )
    assert main(["config"]) == 0
    output = capsys.readouterr().out
    assert "Producto: MathMongo" in output
    assert "Base activa: MathV0" in output
    assert "mongodb://localhost:27017/MathV0" in output
    assert "teacher" not in output
    assert "secret" not in output


@pytest.mark.parametrize("arguments", [[], ["run"]])
def test_default_command_and_explicit_run_are_equivalent(arguments, monkeypatch, tmp_path: Path) -> None:
    mongo_uri = "mongodb://127.0.0.1:27017"
    _configure_cli_environment(
        monkeypatch,
        tmp_path,
        mongo_uri=mongo_uri,
        mongo_database="cli_equivalence_database",
    )
    resolved = resolve_config()
    assert resolved.mongo_uri == mongo_uri
    assert resolved.mongo_database == "cli_equivalence_database"
    calls = []
    monkeypatch.setattr("mathmongo.cli.launch_mathmongo", lambda **kwargs: calls.append(kwargs) or 0)
    assert main(arguments) == 0
    assert calls == [
        {
            "address": "localhost",
            "port": 8501,
            "no_browser": False,
            "mongodb_uri": mongo_uri,
            "desktop_launch": False,
        }
    ]


def test_cli_forwards_custom_run_options(monkeypatch, tmp_path: Path) -> None:
    mongo_uri = "mongodb://127.0.0.1:27018"
    _configure_cli_environment(
        monkeypatch,
        tmp_path,
        mongo_uri=mongo_uri,
        mongo_database="cli_test_database",
    )
    resolved = resolve_config()
    assert resolved.mongo_uri == mongo_uri
    assert resolved.mongo_database == "cli_test_database"
    calls = []
    monkeypatch.setattr("mathmongo.cli.launch_mathmongo", lambda **kwargs: calls.append(kwargs) or 0)
    assert main(["run", "--port", "8502", "--address", "::1", "--no-browser"]) == 0
    assert calls == [
        {
            "address": "::1",
            "port": 8502,
            "no_browser": True,
            "mongodb_uri": mongo_uri,
            "desktop_launch": False,
        }
    ]


def test_options_before_run_are_not_overwritten(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("mathmongo.cli.launch_mathmongo", lambda **kwargs: calls.append(kwargs) or 0)
    assert main(["--port", "8510", "--no-browser", "run"]) == 0
    assert calls[0]["port"] == 8510
    assert calls[0]["no_browser"] is True


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


def test_importing_cli_does_not_import_streamlit_or_pymongo(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    isolated_paths = [
        tmp_path / "home",
        tmp_path / "config",
        tmp_path / "data",
        tmp_path / "cache",
        tmp_path / "state",
        tmp_path / "runtime",
    ]
    environment = os.environ.copy()
    for name in _CLI_CONFIGURATION_ENVIRONMENT:
        environment.pop(name, None)
    environment.update(
        {
            "PYTHONPATH": str(project_root),
            "HOME": str(isolated_paths[0]),
            "XDG_CONFIG_HOME": str(isolated_paths[1]),
            "XDG_DATA_HOME": str(isolated_paths[2]),
            "XDG_CACHE_HOME": str(isolated_paths[3]),
            "XDG_STATE_HOME": str(isolated_paths[4]),
            "XDG_RUNTIME_DIR": str(isolated_paths[5]),
            "MONGODB_URI": "mongodb://127.0.0.1:27017",
            "MONGODB_DB": "cli_import_isolation",
        }
    )
    code = (
        "from pathlib import Path; import sys; attempts = []; "
        "sys.addaudithook(lambda event, _args: attempts.append(event) if event == 'socket.connect' else None); "
        "import mathmongo.cli; "
        "assert 'streamlit' not in sys.modules; assert 'pymongo' not in sys.modules; "
        f"assert all(not Path(path).exists() for path in {list(map(str, isolated_paths))!r}); "
        "assert not attempts"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_redacts_configured_uri_from_stderr_and_desktop_log(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    uri = "mongodb://alice:secret@db.example:27018/math"
    logs_dir = tmp_path / "state/logs"

    def fail_launch(**kwargs) -> int:
        assert kwargs["mongodb_uri"] == uri
        raise LaunchError(f"Connection failed for {uri}; user=alice password=secret")

    monkeypatch.setattr("mathmongo.cli.resolve_config", lambda **kwargs: AppConfig(mongo_uri=uri))
    monkeypatch.setattr("mathmongo.cli.launch_mathmongo", fail_launch)
    monkeypatch.setattr("mathmongo.cli.get_logs_dir", lambda: logs_dir)
    monkeypatch.setenv("MATHMONGO_DESKTOP", "1")

    assert main(["run"]) == 1
    stderr = capsys.readouterr().err
    log_text = (logs_dir / "launcher.log").read_text(encoding="utf-8")
    for output in (stderr, log_text):
        assert uri not in output
        assert "alice" not in output
        assert "secret" not in output
        assert "mongodb://db.example:27018/math" in output


def test_cli_never_follows_a_launcher_log_symlink(tmp_path: Path, monkeypatch, capsys) -> None:
    logs_dir = tmp_path / "state/logs"
    logs_dir.mkdir(parents=True)
    outside = tmp_path / "outside.log"
    outside.write_text("keep\n", encoding="utf-8")
    (logs_dir / "launcher.log").symlink_to(outside)
    monkeypatch.setattr(
        "mathmongo.cli.launch_mathmongo",
        lambda **kwargs: (_ for _ in ()).throw(LaunchError("failed")),
    )
    monkeypatch.setattr("mathmongo.cli.get_logs_dir", lambda: logs_dir)
    monkeypatch.setenv("MATHMONGO_DESKTOP", "1")

    assert main(["run"]) == 1
    assert "failed" in capsys.readouterr().err
    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_runtime_start_ensures_mongodb_before_starting_controller(monkeypatch, capsys) -> None:
    events: list[str] = []
    owned = RuntimeObservation(RuntimeStateKind.OWNED, "owned")

    class Controller:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            events.append("start")
            return RuntimeAction(True, owned, "started")

    monkeypatch.setattr("mathmongo.local_runtime.control.RuntimeController", Controller)
    monkeypatch.setattr(
        "mathmongo.cli._ensure_mongo",
        lambda *_args, **_kwargs: events.append("ensure"),
    )

    assert (
        main(
            [
                "runtime",
                "start",
                "--database",
                "runtime_test",
                "--streamlit-port",
                "18501",
                "--advanced-reader-port",
                "18766",
            ]
        )
        == 0
    )
    assert events == ["ensure", "start"]
    assert "http://127.0.0.1:18501" in capsys.readouterr().out


def test_runtime_run_ensures_mongodb_before_foreground_supervisor(monkeypatch) -> None:
    events: list[str] = []

    class Controller:
        def __init__(self, *_args, **_kwargs):
            pass

    class Supervisor:
        def __init__(self, *_args, **_kwargs):
            events.append("supervisor")

        def run(self):
            events.append("run")
            return 17

    monkeypatch.setattr("mathmongo.local_runtime.control.RuntimeController", Controller)
    monkeypatch.setattr("mathmongo.local_runtime.launcher.LocalRuntimeSupervisor", Supervisor)
    monkeypatch.setattr(
        "mathmongo.cli._ensure_mongo",
        lambda *_args, **_kwargs: events.append("ensure"),
    )

    assert (
        main(
            [
                "runtime",
                "run",
                "--database",
                "runtime_test",
                "--streamlit-port",
                "18501",
                "--advanced-reader-port",
                "18766",
            ]
        )
        == 17
    )
    assert events == ["ensure", "supervisor", "run"]


def test_runtime_stop_never_calls_mongodb_ensure(monkeypatch) -> None:
    stopped = RuntimeObservation(RuntimeStateKind.STOPPED, "stopped")

    class Controller:
        def __init__(self, *_args, **_kwargs):
            pass

        def stop(self, *, force):
            assert force is False
            return RuntimeAction(False, stopped, "stopped")

    monkeypatch.setattr("mathmongo.local_runtime.control.RuntimeController", Controller)
    monkeypatch.setattr(
        "mathmongo.cli._ensure_mongo",
        lambda *_args, **_kwargs: pytest.fail("stop must not ensure MongoDB"),
    )

    assert (
        main(
            [
                "runtime",
                "stop",
                "--database",
                "runtime_test",
                "--streamlit-port",
                "18501",
                "--advanced-reader-port",
                "18766",
            ]
        )
        == 0
    )

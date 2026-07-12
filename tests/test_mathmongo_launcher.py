"""Tests for the installable MathMongo launcher."""

# ruff: noqa: D103

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from mathmongo.launcher import LaunchError
from mathmongo.launcher import build_streamlit_command
from mathmongo.launcher import launch_mathmongo
from mathmongo.launcher import port_available
from mathmongo.launcher import resolve_streamlit_app
from mathmongo.launcher import validate_address


def successful_runner(calls: list[list[str]], returncode: int = 0):
    def run(command, *, check):
        calls.append(command)
        assert check is False
        return subprocess.CompletedProcess(command, returncode)

    return run


def launch(calls: list[list[str]], **kwargs) -> int:
    return launch_mathmongo(
        runner=successful_runner(calls, kwargs.pop("returncode", 0)),
        dependency_check=lambda: True,
        mongodb_check=lambda uri: True,
        port_check=lambda address, port: True,
        app_resolver=lambda: Path("/tmp/path with spaces/editor_streamlit.py"),
        **kwargs,
    )


def test_build_command_uses_current_interpreter_and_local_defaults() -> None:
    command = build_streamlit_command(Path("/tmp/app.py"))

    assert command[:5] == [sys.executable, "-m", "streamlit", "run", "/tmp/app.py"]
    assert command[-4:] == ["--server.address", "localhost", "--server.port", "8501"]


def test_custom_options_and_no_browser_are_forwarded() -> None:
    calls: list[list[str]] = []

    assert launch(calls, port=8502, address="127.0.0.1", no_browser=True) == 0
    assert "/tmp/path with spaces/editor_streamlit.py" in calls[0]
    assert calls[0][-2:] == ["--server.headless", "true"]
    assert "8502" in calls[0]


def test_runner_return_code_is_propagated() -> None:
    calls: list[list[str]] = []
    assert launch(calls, returncode=7) == 7


def test_keyboard_interrupt_returns_shell_interrupt_code() -> None:
    def interrupt(command, *, check):
        raise KeyboardInterrupt

    result = launch_mathmongo(
        runner=interrupt,
        dependency_check=lambda: True,
        mongodb_check=lambda uri: True,
        port_check=lambda address, port: True,
        app_resolver=lambda: Path("/tmp/app.py"),
    )
    assert result == 130


def test_missing_streamlit_fails_before_process_execution() -> None:
    with pytest.raises(LaunchError, match="Streamlit no está disponible"):
        launch_mathmongo(dependency_check=lambda: False)


def test_missing_mongodb_is_a_clear_failure() -> None:
    with pytest.raises(LaunchError, match="MongoDB no está disponible"):
        launch_mathmongo(
            dependency_check=lambda: True,
            mongodb_check=lambda uri: False,
        )


def test_busy_port_is_not_reused() -> None:
    with pytest.raises(LaunchError, match="ya está ocupado"):
        launch_mathmongo(
            dependency_check=lambda: True,
            mongodb_check=lambda uri: True,
            port_check=lambda address, port: False,
        )


def test_port_probe_uses_reusable_listener_semantics(monkeypatch) -> None:
    calls = []

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def setsockopt(self, *args):
            calls.append(("setsockopt", args))

        def bind(self, address):
            calls.append(("bind", address))

    monkeypatch.setattr("mathmongo.launcher.socket.socket", lambda *args: Probe())
    assert port_available("localhost", 8501)
    assert calls[0][0] == "setsockopt"
    assert calls[1] == ("bind", ("127.0.0.1", 8501))


@pytest.mark.parametrize("address", ["0.0.0.0", "192.168.1.20", "example.com"])
def test_non_loopback_address_is_rejected(address: str) -> None:
    with pytest.raises(LaunchError, match="loopback"):
        validate_address(address)


def test_app_resolution_does_not_depend_on_cwd(tmp_path: Path, monkeypatch) -> None:
    expected = Path(__file__).resolve().parents[1] / "editor" / "editor_streamlit.py"
    monkeypatch.chdir(tmp_path)
    assert resolve_streamlit_app() == expected.resolve()


def test_missing_application_has_clear_error(monkeypatch) -> None:
    monkeypatch.setattr("mathmongo.launcher.importlib.util.find_spec", lambda name: None)
    with pytest.raises(LaunchError, match="paquete 'editor'"):
        resolve_streamlit_app()


def test_launcher_source_never_uses_shell_true() -> None:
    source = (Path(__file__).resolve().parents[1] / "mathmongo" / "launcher.py").read_text()
    assert "shell=True" not in source


def test_desktop_launch_writes_private_xdg_log(tmp_path: Path, monkeypatch) -> None:
    logs = tmp_path / "state/logs"
    calls = []

    def runner(command, *, check, stdout, stderr):
        calls.append(command)
        stdout.write("streamlit output\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("mathmongo.launcher.get_logs_dir", lambda: logs)
    result = launch_mathmongo(
        runner=runner,
        dependency_check=lambda: True,
        mongodb_check=lambda uri: True,
        port_check=lambda address, port: True,
        app_resolver=lambda: tmp_path / "editor_streamlit.py",
        desktop_launch=True,
    )
    log = logs / "streamlit.log"
    assert result == 0
    assert calls
    assert log.read_text() == "streamlit output\n"
    assert log.stat().st_mode & 0o777 == 0o600


def test_desktop_launch_rejects_a_streamlit_log_symlink(tmp_path: Path, monkeypatch) -> None:
    logs = tmp_path / "state/logs"
    logs.mkdir(parents=True)
    outside = tmp_path / "outside.log"
    outside.write_text("keep\n", encoding="utf-8")
    (logs / "streamlit.log").symlink_to(outside)
    monkeypatch.setattr("mathmongo.launcher.get_logs_dir", lambda: logs)

    with pytest.raises(LaunchError, match="Symbolic links"):
        launch_mathmongo(
            runner=lambda *args, **kwargs: pytest.fail("runner must not be called"),
            dependency_check=lambda: True,
            mongodb_check=lambda uri: True,
            port_check=lambda address, port: True,
            app_resolver=lambda: tmp_path / "editor_streamlit.py",
            desktop_launch=True,
        )

    assert outside.read_text(encoding="utf-8") == "keep\n"

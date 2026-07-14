"""Unit tests for unified foreground supervision and failure handling."""

# ruff: noqa: D103

from __future__ import annotations

import io
import signal
from pathlib import Path

import pytest

from mathmongo.local_runtime.launcher import LocalRuntimeSupervisor
from mathmongo.local_runtime.launcher import settings_from_args
from mathmongo.local_runtime.models import AdvancedReaderHealth
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.local_runtime.models import ServiceDisposition


def _health(
    *,
    database: str = "MathV0",
    frontend_ready: bool = True,
    status: str = "ok",
    service: str = "mathmongo-advanced-reader",
) -> AdvancedReaderHealth:
    return AdvancedReaderHealth(
        status=status,
        service=service,
        database=database,
        frontend_ready=frontend_ready,
    )


class _Process:
    def __init__(self, *, returncode: int | None = None, output: str = "") -> None:
        self.stdout = io.StringIO(output)
        self.returncode = returncode
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls: list[float | None] = []

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        assert self.returncode is not None
        return self.returncode


class _Factory:
    def __init__(self, *processes: _Process) -> None:
        self.pending = list(processes)
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command: list[str], **kwargs) -> _Process:
        self.calls.append((command, kwargs))
        return self.pending.pop(0)


def _supervisor(
    *,
    settings: RuntimeSettings | None = None,
    factory: _Factory | None = None,
    port_check=lambda _host, _port: True,
    reader_probe=lambda *_args, **_kwargs: _health(),
    streamlit_probe=lambda *_args, **_kwargs: True,
    app_resolver=lambda: Path("/wheel/editor/editor_streamlit.py"),
    sleep=lambda _seconds: None,
    output: list[str] | None = None,
) -> LocalRuntimeSupervisor:
    lines = [] if output is None else output
    return LocalRuntimeSupervisor(
        settings
        or RuntimeSettings(
            startup_timeout=0.1,
            request_timeout=0.05,
            poll_interval=0.001,
            shutdown_timeout=0.05,
        ),
        base_environment={"MONGODB_URI": "mongodb://temporary:27017"},
        executable="/venv/bin/python",
        port_check=port_check,
        reader_probe=reader_probe,
        streamlit_probe=streamlit_probe,
        app_resolver=app_resolver,
        popen_factory=factory or _Factory(),
        sleep=sleep,
        emit=lines.append,
    )


def test_cli_defaults_and_custom_ports() -> None:
    defaults = settings_from_args([])
    custom = settings_from_args(
        [
            "--database",
            "isolated",
            "--streamlit-port",
            "18501",
            "--advanced-reader-port",
            "18766",
            "--log-level",
            "debug",
        ]
    )

    assert defaults.database == "MathV0"
    assert defaults.streamlit_port == 8501
    assert defaults.advanced_reader_port == 8766
    assert custom.database == "isolated"
    assert custom.streamlit_port == 18501
    assert custom.advanced_reader_port == 18766
    assert custom.log_level == "debug"


def test_occupied_reader_port_with_non_reader_blocks_without_starting_children() -> None:
    factory = _Factory()
    supervisor = _supervisor(
        factory=factory,
        port_check=lambda _host, port: port != 8766,
        reader_probe=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(LocalRuntimeError, match="ocupado por otro proceso"):
        supervisor.run(install_signal_handlers=False)

    assert factory.calls == []


def test_reader_spawn_error_is_safe_and_leaves_no_owned_process() -> None:
    def fail_to_spawn(_command: list[str], **_kwargs):
        raise OSError("/home/person/private mongodb://user:pass@host")

    supervisor = _supervisor(factory=fail_to_spawn)

    with pytest.raises(LocalRuntimeError, match="No se pudo iniciar Advanced Reader") as captured:
        supervisor.run(install_signal_handlers=False)

    assert "/home/" not in str(captured.value)
    assert "mongodb://" not in str(captured.value)


def test_compatible_reader_is_reused_and_never_terminated() -> None:
    streamlit = _Process()
    factory = _Factory(streamlit)
    holder: dict[str, LocalRuntimeSupervisor] = {}

    def request_shutdown(_seconds: float) -> None:
        holder["supervisor"].request_shutdown(signal.SIGINT)

    supervisor = _supervisor(
        factory=factory,
        port_check=lambda _host, port: port != 8766,
        sleep=request_shutdown,
    )
    holder["supervisor"] = supervisor

    assert supervisor.run(install_signal_handlers=False) == 130
    assert supervisor.reader_disposition is ServiceDisposition.REUSED
    assert supervisor.streamlit_disposition is ServiceDisposition.STARTED
    assert len(factory.calls) == 1
    assert factory.calls[0][0][1:4] == ["-m", "streamlit", "run"]
    assert streamlit.terminate_calls == 1
    assert streamlit.wait_calls == [0.05]


def test_reader_database_mismatch_blocks_with_actionable_safe_command() -> None:
    factory = _Factory()
    supervisor = _supervisor(
        factory=factory,
        port_check=lambda _host, port: port != 8766,
        reader_probe=lambda *_args, **_kwargs: _health(database="other_database"),
    )

    with pytest.raises(LocalRuntimeError) as captured:
        supervisor.run(install_signal_handlers=False)

    message = str(captured.value)
    assert "other_database" in message
    assert "MathV0" in message
    assert "ss -ltnp" in message
    assert factory.calls == []


def test_reader_with_frontend_not_ready_is_not_reused() -> None:
    supervisor = _supervisor(
        port_check=lambda _host, port: port != 8766,
        reader_probe=lambda *_args, **_kwargs: _health(frontend_ready=False),
    )

    with pytest.raises(LocalRuntimeError, match="frontend no está listo"):
        supervisor.run(install_signal_handlers=False)


@pytest.mark.parametrize("health", [False, True])
def test_occupied_streamlit_port_is_conservatively_blocked(health: bool) -> None:
    factory = _Factory()
    supervisor = _supervisor(
        factory=factory,
        port_check=lambda _host, port: port != 8501,
        streamlit_probe=lambda *_args, **_kwargs: health,
    )

    with pytest.raises(LocalRuntimeError, match="STREAMLIT_PORT=8502"):
        supervisor.run(install_signal_handlers=False)

    assert factory.calls == []


def test_reader_child_failure_prevents_streamlit_start_and_is_reaped() -> None:
    reader = _Process(returncode=9, output="safe reader failure\n")
    factory = _Factory(reader)
    supervisor = _supervisor(
        factory=factory,
        reader_probe=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(LocalRuntimeError, match="Reader terminó"):
        supervisor.run(install_signal_handlers=False)

    assert len(factory.calls) == 1
    assert reader.wait_calls == [0]


def test_failed_reader_diagnostics_are_prefixed_bounded_and_redacted() -> None:
    reader = _Process(
        returncode=9,
        output=("mongodb://user:pass@localhost:27017 /home/person/blob.pdf password=hunter2\n"),
    )
    lines: list[str] = []
    supervisor = _supervisor(
        factory=_Factory(reader),
        reader_probe=lambda *_args, **_kwargs: None,
        output=lines,
    )

    with pytest.raises(LocalRuntimeError):
        supervisor.run(install_signal_handlers=False)

    rendered = "\n".join(lines)
    assert "[advanced-reader]" in rendered
    assert "user:pass" not in rendered
    assert "/home/" not in rendered
    assert "hunter2" not in rendered


def test_streamlit_child_failure_stops_and_reaps_reader() -> None:
    reader = _Process()
    streamlit = _Process(returncode=4)
    factory = _Factory(reader, streamlit)
    supervisor = _supervisor(factory=factory)

    with pytest.raises(LocalRuntimeError, match="Streamlit terminó"):
        supervisor.run(install_signal_handlers=False)

    assert reader.terminate_calls == 1
    assert reader.wait_calls == [0.05]
    assert streamlit.wait_calls == [0]


def test_ctrl_c_waits_and_reaps_owned_processes_without_zombies() -> None:
    reader = _Process()
    streamlit = _Process()
    factory = _Factory(reader, streamlit)
    holder: dict[str, LocalRuntimeSupervisor] = {}

    def request_shutdown(_seconds: float) -> None:
        holder["supervisor"].request_shutdown(signal.SIGINT)

    supervisor = _supervisor(factory=factory, sleep=request_shutdown)
    holder["supervisor"] = supervisor

    assert supervisor.run(install_signal_handlers=False) == 130
    for process in (reader, streamlit):
        assert process.terminate_calls == 1
        assert process.kill_calls == 0
        assert process.wait_calls == [0.05]


def test_unexpected_child_exit_stops_the_other_and_returns_nonzero() -> None:
    reader = _Process()
    streamlit = _Process()
    factory = _Factory(reader, streamlit)

    def ready_then_exit(*_args, **_kwargs) -> bool:
        streamlit.returncode = 7
        return True

    supervisor = _supervisor(factory=factory, streamlit_probe=ready_then_exit)

    assert supervisor.run(install_signal_handlers=False) == 7
    assert reader.terminate_calls == 1
    assert reader.wait_calls == [0.05]
    assert streamlit.wait_calls == [0]


def test_unexpected_reader_exit_stops_streamlit_and_returns_nonzero() -> None:
    reader = _Process()
    streamlit = _Process()
    factory = _Factory(reader, streamlit)

    def ready_then_exit(*_args, **_kwargs):
        reader.returncode = 6
        return _health()

    supervisor = _supervisor(factory=factory, reader_probe=ready_then_exit)

    assert supervisor.run(install_signal_handlers=False) == 6
    assert reader.wait_calls == [0]
    assert streamlit.terminate_calls == 1
    assert streamlit.wait_calls == [0.05]


def test_reader_spawn_error_starts_no_streamlit_and_hides_raw_exception() -> None:
    def popen(_command: list[str], **_kwargs):
        raise OSError("/srv/private mongodb://user:pass@host")

    supervisor = LocalRuntimeSupervisor(
        RuntimeSettings(
            startup_timeout=0.1,
            request_timeout=0.05,
            poll_interval=0.001,
            shutdown_timeout=0.05,
        ),
        base_environment={},
        port_check=lambda _host, _port: True,
        app_resolver=lambda: Path("/wheel/editor/editor_streamlit.py"),
        popen_factory=popen,
    )

    with pytest.raises(LocalRuntimeError, match="No se pudo iniciar Advanced Reader") as captured:
        supervisor.run(install_signal_handlers=False)

    assert "/srv/" not in str(captured.value)
    assert "mongodb://" not in str(captured.value)


def test_streamlit_spawn_error_stops_reader_without_exposing_raw_exception() -> None:
    reader = _Process()
    calls = 0

    def popen(_command: list[str], **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return reader
        raise OSError("/home/person/private mongodb://user:pass@host")

    lines: list[str] = []
    supervisor = LocalRuntimeSupervisor(
        RuntimeSettings(
            startup_timeout=0.1,
            request_timeout=0.05,
            poll_interval=0.001,
            shutdown_timeout=0.05,
        ),
        base_environment={},
        port_check=lambda _host, _port: True,
        reader_probe=lambda *_args, **_kwargs: _health(),
        streamlit_probe=lambda *_args, **_kwargs: True,
        app_resolver=lambda: Path("/wheel/editor/editor_streamlit.py"),
        popen_factory=popen,
        emit=lines.append,
    )

    with pytest.raises(LocalRuntimeError, match="No se pudo iniciar Streamlit") as captured:
        supervisor.run(install_signal_handlers=False)

    assert "/home/" not in str(captured.value)
    assert "mongodb://" not in str(captured.value)
    assert reader.terminate_calls == 1
    assert reader.wait_calls == [0.05]


def test_signal_during_reader_reuse_probe_prevents_any_child_start() -> None:
    factory = _Factory()
    holder: dict[str, LocalRuntimeSupervisor] = {}

    def probe(*_args, **_kwargs):
        holder["supervisor"].request_shutdown(signal.SIGINT)
        return _health()

    supervisor = _supervisor(
        factory=factory,
        port_check=lambda _host, port: port != 8766,
        reader_probe=probe,
    )
    holder["supervisor"] = supervisor

    assert supervisor.run(install_signal_handlers=False) == 130
    assert factory.calls == []


def test_streamlit_port_65535_never_suggests_invalid_65536() -> None:
    settings = RuntimeSettings(streamlit_port=65535)
    supervisor = _supervisor(
        settings=settings,
        port_check=lambda _host, port: port != 65535,
        streamlit_probe=lambda *_args, **_kwargs: True,
    )

    with pytest.raises(LocalRuntimeError) as captured:
        supervisor.run(install_signal_handlers=False)

    assert "65536" not in str(captured.value)
    assert "STREAMLIT_PORT=<puerto-libre>" in str(captured.value)


def test_started_commands_use_installed_editor_and_controlled_environment() -> None:
    reader = _Process()
    streamlit = _Process()
    factory = _Factory(reader, streamlit)
    holder: dict[str, LocalRuntimeSupervisor] = {}

    def stop(_seconds: float) -> None:
        holder["supervisor"].request_shutdown(signal.SIGTERM)

    supervisor = _supervisor(factory=factory, sleep=stop)
    holder["supervisor"] = supervisor

    assert supervisor.run(install_signal_handlers=False) == 143
    reader_command, reader_options = factory.calls[0]
    streamlit_command, streamlit_options = factory.calls[1]
    assert reader_command[0] == "/venv/bin/python"
    assert reader_command[1:3] == ["-m", "mathmongo.advanced_reader"]
    assert streamlit_command[4] == "/wheel/editor/editor_streamlit.py"
    assert reader_options["shell"] is False
    assert streamlit_options["shell"] is False
    assert reader_options["start_new_session"] is True
    assert streamlit_options["start_new_session"] is True
    assert reader_options["env"]["MONGODB_DB"] == "MathV0"
    assert streamlit_options["env"]["MONGODB_URI"] == "mongodb://temporary:27017"

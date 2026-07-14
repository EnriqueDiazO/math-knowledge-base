"""Unit tests for runtime settings, commands, environment, and child ownership."""

# ruff: noqa: D103

from __future__ import annotations

import io
import signal
import subprocess

import pytest

from mathmongo.local_runtime.health import loopback_url
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.local_runtime.processes import DATABASE_ENV_VAR
from mathmongo.local_runtime.processes import ManagedChild
from mathmongo.local_runtime.processes import PrefixedLogPump
from mathmongo.local_runtime.processes import SafeLineBuffer
from mathmongo.local_runtime.processes import build_advanced_reader_command
from mathmongo.local_runtime.processes import build_child_environment
from mathmongo.local_runtime.processes import build_streamlit_command
from mathmongo.local_runtime.processes import sanitize_log_line


class _Process:
    def __init__(self, *, timeout_once: bool = False) -> None:
        self.stdout = io.StringIO("")
        self.returncode: int | None = None
        self.timeout_once = timeout_once
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls: list[float | None] = []

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        if not self.timeout_once:
            self.returncode = -15

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if self.returncode is None and self.timeout_once:
            self.timeout_once = False
            raise subprocess.TimeoutExpired("child", timeout)
        assert self.returncode is not None
        return self.returncode


def test_runtime_settings_defaults_are_mathv0_and_loopback() -> None:
    settings = RuntimeSettings()

    assert settings.database == "MathV0"
    assert settings.streamlit_host == "127.0.0.1"
    assert settings.streamlit_port == 8501
    assert settings.advanced_reader_host == "127.0.0.1"
    assert settings.advanced_reader_port == 8766
    assert settings.log_level == "info"


def test_runtime_settings_accept_configurable_ports_and_database() -> None:
    settings = RuntimeSettings(
        database="runtime_test",
        streamlit_port=18501,
        advanced_reader_port=18766,
        log_level="warning",
    )

    assert settings.database == "runtime_test"
    assert settings.streamlit_port == 18501
    assert settings.advanced_reader_port == 18766
    assert settings.log_level == "warning"


@pytest.mark.parametrize("field", ["streamlit_host", "advanced_reader_host"])
@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.2", "example.test"])
def test_runtime_settings_reject_remote_hosts(field: str, host: str) -> None:
    with pytest.raises(LocalRuntimeError, match="solo"):
        RuntimeSettings(**{field: host})


def test_runtime_settings_reject_same_host_and_port() -> None:
    with pytest.raises(LocalRuntimeError, match="mismo puerto"):
        RuntimeSettings(streamlit_port=8766)


def test_commands_use_selected_executable_and_argument_lists() -> None:
    settings = RuntimeSettings(database="MathV0", streamlit_port=18501)

    assert build_advanced_reader_command(settings, executable="/venv/python") == [
        "/venv/python",
        "-m",
        "mathmongo.advanced_reader",
        "--host",
        "127.0.0.1",
        "--port",
        "8766",
        "--database",
        "MathV0",
        "--log-level",
        "info",
    ]
    assert build_streamlit_command(
        settings,
        "/installed/editor/editor_streamlit.py",
        executable="/venv/python",
    ) == [
        "/venv/python",
        "-m",
        "streamlit",
        "run",
        "/installed/editor/editor_streamlit.py",
        "--server.address",
        "127.0.0.1",
        "--server.port",
        "18501",
    ]


def test_child_environment_inherits_mongo_uri_and_overrides_official_database() -> None:
    original = {
        "MONGODB_URI": "mongodb://temporary.example:27017",
        DATABASE_ENV_VAR: "wrong",
        "KEEP_ME": "yes",
    }

    environment = build_child_environment(
        RuntimeSettings(database="MathV0", advanced_reader_port=18766),
        base_environment=original,
    )

    assert environment["MONGODB_URI"] == original["MONGODB_URI"]
    assert environment[DATABASE_ENV_VAR] == "MathV0"
    assert environment["MATHMONGO_ADVANCED_READER_URL"] == "http://127.0.0.1:18766"
    assert environment["KEEP_ME"] == "yes"
    assert original[DATABASE_ENV_VAR] == "wrong"


def test_loopback_url_brackets_ipv6_and_rejects_remote_host() -> None:
    assert loopback_url("::1", 8766) == "http://[::1]:8766"
    with pytest.raises(ValueError):
        loopback_url("8.8.8.8", 8766)


def test_log_sanitizer_bounds_and_redacts_sensitive_diagnostics() -> None:
    line = sanitize_log_line(
        "Mongo mongodb://user:pass@localhost:27017 /home/person/private.pdf "
        "/mnt/blobs/secret.pdf "
        f"source_documents/blobs/sha256/aa/{'a' * 64}.pdf password=hunter2"
    )

    assert "user" not in line
    assert "pass@" not in line
    assert "/home/" not in line
    assert "/mnt/" not in line
    assert "source_documents/blobs" not in line
    assert "hunter2" not in line
    assert "MongoDB URI omitida" in line


def test_log_pump_bounds_each_read_and_keeps_only_a_safe_tail() -> None:
    tail = SafeLineBuffer(maximum=3)
    emitted: list[str] = []
    pump = PrefixedLogPump(
        prefix="child",
        stream=io.StringIO(f"{'x' * 5000}\n"),
        tail=tail,
        emit=emitted.append,
    )

    pump.start()
    pump.finish()

    assert len(tail.snapshot()) == 3
    assert all(len(line) <= 800 for line in tail.snapshot())
    assert all(line.startswith("[child] ") for line in emitted)


def test_managed_child_never_uses_shell_and_reaps_after_term() -> None:
    process = _Process()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def popen(command: list[str], **kwargs):
        calls.append((command, kwargs))
        return process

    child = ManagedChild.start(
        name="test",
        prefix="test",
        command=["/venv/python", "-m", "module"],
        environment={"SAFE": "1"},
        emit=lambda _line: None,
        popen_factory=popen,
    )

    assert calls[0][1]["shell"] is False
    assert calls[0][1]["start_new_session"] is True
    assert child.stop(timeout=0.1) == -15
    assert process.terminate_calls == 1
    assert process.kill_calls == 0
    assert process.wait_calls == [0.1]


def test_managed_child_kills_only_after_bounded_termination_timeout() -> None:
    process = _Process(timeout_once=True)
    child = ManagedChild.start(
        name="test",
        prefix="test",
        command=["python"],
        environment={},
        emit=lambda _line: None,
        popen_factory=lambda *_args, **_kwargs: process,
    )

    assert child.stop(timeout=0.01) == -9
    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.wait_calls == [0.01, None]


def test_managed_child_signals_only_its_own_new_process_group() -> None:
    process = _Process()
    process.pid = 4242
    signals: list[tuple[int, int]] = []

    def signal_group(pid: int, signum: int) -> None:
        signals.append((pid, signum))
        process.returncode = -signum

    child = ManagedChild.start(
        name="test",
        prefix="test",
        command=["python"],
        environment={},
        emit=lambda _line: None,
        popen_factory=lambda *_args, **_kwargs: process,
        group_signaler=signal_group,
    )

    assert child.stop(timeout=0.1) == -signal.SIGTERM
    assert signals == [(4242, signal.SIGTERM)]
    assert process.terminate_calls == 0
    assert process.kill_calls == 0


def test_exited_leader_still_cleans_its_owned_process_group_and_is_reaped() -> None:
    process = _Process()
    process.pid = 4242
    process.returncode = 7
    signals: list[tuple[int, int]] = []

    child = ManagedChild.start(
        name="test",
        prefix="test",
        command=["python"],
        environment={},
        emit=lambda _line: None,
        popen_factory=lambda *_args, **_kwargs: process,
        group_signaler=lambda pid, signum: signals.append((pid, signum)),
    )

    assert child.stop(timeout=0.1) == 7
    assert signals == [(4242, signal.SIGTERM)]
    assert process.terminate_calls == 0
    assert process.kill_calls == 0
    assert process.wait_calls == [0]


def test_owned_descendant_group_escalates_after_bounded_term_wait() -> None:
    process = _Process()
    process.pid = 4242
    process.returncode = 7
    signals: list[tuple[int, int]] = []
    group_alive = True
    clock = 0.0

    def signal_group(pid: int, signum: int) -> None:
        nonlocal group_alive
        signals.append((pid, signum))
        if signum == signal.SIGKILL:
            group_alive = False

    def monotonic() -> float:
        return clock

    def sleep(seconds: float) -> None:
        nonlocal clock
        clock += seconds

    child = ManagedChild.start(
        name="test",
        prefix="test",
        command=["python"],
        environment={},
        emit=lambda _line: None,
        popen_factory=lambda *_args, **_kwargs: process,
        group_signaler=signal_group,
        group_probe=lambda _pid: group_alive,
        monotonic=monotonic,
        sleep=sleep,
    )

    assert child.stop(timeout=0.1) == 7
    assert signals == [
        (4242, signal.SIGTERM),
        (4242, signal.SIGKILL),
    ]
    assert clock == pytest.approx(0.1)
    assert process.wait_calls == [0]

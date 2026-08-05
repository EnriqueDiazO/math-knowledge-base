"""Unit tests for safe MongoDB service inspection and authorization."""

# ruff: noqa: D101, D102, D103, D107

from __future__ import annotations

import subprocess

import pytest

from mathmongo.mongodb_service import MongoServiceState
from mathmongo.mongodb_service import ensure_mongodb_running
from mathmongo.mongodb_service import inspect_mongodb_service

URI = "mongodb://alice:secret@localhost:27017/MathV0"
DATABASE = "MathV0"


class FakeSystemd:
    def __init__(
        self,
        state: str,
        *,
        load_state: str = "loaded",
        start_returncode: int = 0,
        start_stderr: str = "",
    ) -> None:
        self.state = state
        self.load_state = load_state
        self.start_returncode = start_returncode
        self.start_stderr = start_stderr
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, command: list[str], **kwargs):
        self.calls.append((command, kwargs))
        assert kwargs["shell"] is False
        assert kwargs["check"] is False
        if "show" in command:
            return subprocess.CompletedProcess(command, 0, f"{self.load_state}\n", "")
        if "is-active" in command:
            return subprocess.CompletedProcess(
                command,
                0 if self.state == "active" else 3,
                f"{self.state}\n",
                "",
            )
        if "start" in command:
            if self.start_returncode == 0:
                self.state = "active"
            return subprocess.CompletedProcess(
                command,
                self.start_returncode,
                "",
                self.start_stderr,
            )
        raise AssertionError(command)


def executable(name: str) -> str | None:
    return {
        "systemctl": "/usr/bin/systemctl",
        "sudo": "/usr/bin/sudo",
        "pkexec": "/usr/bin/pkexec",
    }.get(name)


@pytest.mark.parametrize(
    ("service_state", "reachable", "expected"),
    [
        ("active", True, MongoServiceState.ACTIVE_AND_REACHABLE),
        ("active", False, MongoServiceState.ACTIVE_BUT_UNREACHABLE),
        ("inactive", False, MongoServiceState.INACTIVE),
        ("failed", False, MongoServiceState.FAILED),
    ],
)
def test_inspection_combines_systemd_and_selected_database_ping(
    service_state: str,
    reachable: bool,
    expected: MongoServiceState,
) -> None:
    runner = FakeSystemd(service_state)
    probes: list[tuple[str, str]] = []

    status = inspect_mongodb_service(
        URI,
        DATABASE,
        runner=runner,
        mongo_probe=lambda uri, database: probes.append((uri, database)) or reachable,
        which=executable,
    )

    assert status.state is expected
    assert status.database == DATABASE
    assert status.safe_uri == "mongodb://localhost:27017/MathV0"
    assert "alice" not in repr(status)
    assert "secret" not in repr(status)
    assert probes == [(URI, DATABASE)]


def test_service_not_found_and_systemd_unavailable_are_distinct() -> None:
    missing = inspect_mongodb_service(
        URI,
        DATABASE,
        runner=FakeSystemd("unknown", load_state="not-found"),
        mongo_probe=lambda *_args: False,
        which=executable,
    )
    unavailable = inspect_mongodb_service(
        URI,
        DATABASE,
        runner=pytest.fail,
        mongo_probe=lambda *_args: False,
        which=lambda _name: None,
    )

    assert missing.state is MongoServiceState.SERVICE_NOT_FOUND
    assert unavailable.state is MongoServiceState.SYSTEMD_UNAVAILABLE


def test_auto_does_not_authorize_when_mongodb_is_already_reachable() -> None:
    runner = FakeSystemd("active")

    result = ensure_mongodb_running(
        mongo_uri=URI,
        database=DATABASE,
        authorization_mode="auto",
        interactive=True,
        runner=runner,
        mongo_probe=lambda *_args: True,
        which=executable,
    )

    assert result.ok and not result.changed
    assert all("sudo" not in command[0] and "pkexec" not in command[0] for command, _ in runner.calls)


@pytest.mark.parametrize(
    ("mode", "interactive", "graphical", "authorization"),
    [
        ("sudo", True, False, "/usr/bin/sudo"),
        ("pkexec", False, True, "/usr/bin/pkexec"),
        ("auto", True, False, "/usr/bin/sudo"),
        ("auto", False, True, "/usr/bin/pkexec"),
    ],
)
def test_authorization_is_used_only_for_an_inactive_service(
    mode: str,
    interactive: bool,
    graphical: bool,
    authorization: str,
) -> None:
    runner = FakeSystemd("inactive")

    result = ensure_mongodb_running(
        mongo_uri=URI,
        database=DATABASE,
        authorization_mode=mode,
        interactive=interactive,
        graphical=graphical,
        runner=runner,
        mongo_probe=lambda *_args: runner.state == "active",
        which=executable,
        sleep=lambda _delay: None,
    )

    assert result.ok and result.changed
    authorization_calls = [command for command, _kwargs in runner.calls if "start" in command]
    assert authorization_calls == [
        [authorization, "/usr/bin/systemctl", "start", "mongod"]
    ]


def test_noninteractive_auto_never_attempts_sudo_or_pkexec() -> None:
    runner = FakeSystemd("inactive")

    result = ensure_mongodb_running(
        mongo_uri=URI,
        database=DATABASE,
        authorization_mode="auto",
        interactive=False,
        runner=runner,
        mongo_probe=lambda *_args: False,
        which=executable,
    )

    assert not result.ok
    assert "no se intentó sudo" in result.message
    assert not any("start" in command for command, _kwargs in runner.calls)


@pytest.mark.parametrize("service_state", ["active", "activating", "failed"])
def test_authorization_is_never_used_unless_service_is_exactly_inactive(
    service_state: str,
) -> None:
    runner = FakeSystemd(service_state)

    result = ensure_mongodb_running(
        mongo_uri=URI,
        database=DATABASE,
        authorization_mode="sudo",
        interactive=True,
        runner=runner,
        mongo_probe=lambda *_args: False,
        which=executable,
    )

    assert not result.ok
    assert not any("start" in command for command, _kwargs in runner.calls)


def test_graphical_auto_without_pkexec_returns_terminal_guidance() -> None:
    runner = FakeSystemd("inactive")

    result = ensure_mongodb_running(
        mongo_uri=URI,
        database=DATABASE,
        authorization_mode="auto",
        interactive=False,
        graphical=True,
        runner=runner,
        mongo_probe=lambda *_args: False,
        which=lambda name: None if name == "pkexec" else executable(name),
    )

    assert not result.ok
    assert "sudo systemctl start mongod" in result.message
    assert not any("start" in command for command, _kwargs in runner.calls)


def test_cancelled_authorization_stops_without_retaining_a_password() -> None:
    runner = FakeSystemd(
        "inactive",
        start_returncode=126,
        start_stderr="Authentication dialog was dismissed password=hunter2",
    )

    result = ensure_mongodb_running(
        mongo_uri=URI,
        database=DATABASE,
        authorization_mode="pkexec",
        interactive=False,
        graphical=True,
        runner=runner,
        mongo_probe=lambda *_args: False,
        which=executable,
    )

    assert not result.ok and result.cancelled and not result.changed
    assert result.message == "Inicio cancelado: MongoDB continúa detenido."
    assert "hunter2" not in repr(result)
    assert "secret" not in repr(result)


def test_active_without_ping_times_out_without_a_second_authorization() -> None:
    runner = FakeSystemd("inactive")
    clock = iter([0.0, 0.0, 0.2, 0.2])

    result = ensure_mongodb_running(
        mongo_uri=URI,
        database=DATABASE,
        authorization_mode="sudo",
        interactive=True,
        runner=runner,
        mongo_probe=lambda *_args: False,
        which=executable,
        monotonic=lambda: next(clock),
        sleep=lambda _delay: None,
        startup_timeout=0.1,
    )

    assert not result.ok and result.changed
    assert "activo, pero MongoDB no responde" in result.message
    assert len([command for command, _kwargs in runner.calls if "start" in command]) == 1


def test_subprocess_stderr_and_uri_are_sanitized() -> None:
    class LeakyRunner(FakeSystemd):
        def __call__(self, command: list[str], **kwargs):
            result = super().__call__(command, **kwargs)
            if "is-active" in command:
                return subprocess.CompletedProcess(
                    command,
                    result.returncode,
                    result.stdout,
                    f"failed {URI} password=hunter2",
                )
            return result

    status = inspect_mongodb_service(
        URI,
        DATABASE,
        runner=LeakyRunner("inactive"),
        mongo_probe=lambda *_args: False,
        which=executable,
    )

    assert URI not in status.detail
    assert "alice" not in status.detail
    assert "secret" not in status.detail
    assert "hunter2" not in status.detail
    assert "password=<omitido>" in status.detail

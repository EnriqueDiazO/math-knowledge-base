"""Safety tests for the persistent, procfs-verified runtime controller."""

# ruff: noqa: D103

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from mathmongo import cli
from mathmongo.local_runtime import control
from mathmongo.local_runtime import state
from mathmongo.local_runtime.control import RuntimeController
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.local_runtime.state import ProcessIdentity
from mathmongo.local_runtime.state import RuntimeObservation
from mathmongo.local_runtime.state import RuntimeStateKind
from mathmongo.local_runtime.state import RuntimeStateStore
from mathmongo.local_runtime.state import build_runtime_record


def _environment(tmp_path: Path) -> dict[str, str]:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    return {
        "HOME": str(tmp_path),
        "XDG_RUNTIME_DIR": str(runtime),
    }


def _identity(pid: int, label: str) -> ProcessIdentity:
    return ProcessIdentity(
        pid=pid,
        start_ticks=pid * 10,
        command=("/venv/python", "-m", label),
        cwd="/repo",
    )


def _owned_observation() -> RuntimeObservation:
    supervisor = _identity(101, "mathmongo.local_runtime")
    streamlit = _identity(102, "streamlit")
    reader = _identity(103, "mathmongo.advanced_reader")
    return RuntimeObservation(
        RuntimeStateKind.OWNED,
        "owned",
        record={"runtime_id": "runtime-token"},
        supervisor=supervisor,
        streamlit=streamlit,
        advanced_reader=reader,
    )


def test_runtime_state_is_private_and_does_not_create_paths_on_read(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    store = RuntimeStateStore(environment)

    assert store.load() is None
    assert not store.directory.exists()

    record = build_runtime_record(
        settings=RuntimeSettings(database="runtime_test"),
        supervisor=_identity(1, "mathmongo.local_runtime"),
        streamlit=_identity(2, "streamlit"),
        advanced_reader=_identity(3, "mathmongo.advanced_reader"),
        repository=Path("/repo"),
    )
    store.write(record)

    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.directory.stat().st_mode & 0o777 == 0o700
    assert store.load() is not None


def test_observe_runtime_rejects_a_recycled_pid(monkeypatch, tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    store = RuntimeStateStore(environment)
    settings = RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766)
    supervisor = _identity(11, "mathmongo.local_runtime")
    streamlit = _identity(12, "streamlit")
    reader = _identity(13, "mathmongo.advanced_reader")
    record = build_runtime_record(
        settings=settings,
        supervisor=supervisor,
        streamlit=streamlit,
        advanced_reader=reader,
        repository=Path("/repo"),
    )
    store.write(record)
    recycled = ProcessIdentity(
        pid=streamlit.pid,
        start_ticks=streamlit.start_ticks + 1,
        command=streamlit.command,
        cwd=streamlit.cwd,
    )
    identities = {11: supervisor, 12: recycled, 13: reader}
    monkeypatch.setattr(state, "listening_pids", lambda port: (12,) if port == 18501 else (13,))
    monkeypatch.setattr(state, "inspect_process", lambda pid: identities.get(pid))
    monkeypatch.setattr(state, "_matches_supervisor", lambda *_args: True)
    monkeypatch.setattr(state, "_matches_streamlit", lambda *_args: True)
    monkeypatch.setattr(state, "_matches_reader", lambda *_args: True)

    assert state.observe_runtime(settings, store=store, repository=Path("/repo")).kind is RuntimeStateKind.STALE


def test_listener_from_this_test_process_is_foreign(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        settings = RuntimeSettings(
            database="runtime_test",
            streamlit_port=port,
            advanced_reader_port=port + 1 if port < 65535 else port - 1,
        )

        observation = state.observe_runtime(
            settings,
            store=RuntimeStateStore(environment),
            repository=Path.cwd(),
        )

    assert observation.kind is RuntimeStateKind.FOREIGN
    assert observation.streamlit is not None
    assert observation.streamlit.pid == os.getpid()


def test_start_never_spawns_when_a_foreign_listener_is_detected(monkeypatch, tmp_path: Path) -> None:
    controller = RuntimeController(
        RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri="mongodb://temporary:27017",
        environment=_environment(tmp_path),
    )
    foreign = RuntimeObservation(RuntimeStateKind.FOREIGN, "foreign")
    monkeypatch.setattr(controller, "status", lambda: foreign)
    spawned = False

    def fail_popen(*_args, **_kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("no spawn expected")

    controller._popen = fail_popen
    with pytest.raises(LocalRuntimeError, match="MathMongo no detuvo"):
        controller.start()
    assert spawned is False


def test_start_with_inactive_mongo_explains_the_manual_prerequisite(monkeypatch, tmp_path: Path) -> None:
    controller = RuntimeController(
        RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri="mongodb://temporary:27017",
        environment=_environment(tmp_path),
        mongo_probe=lambda *_args: False,
    )
    stopped = RuntimeObservation(RuntimeStateKind.STOPPED, "stopped")
    monkeypatch.setattr(controller, "status", lambda: stopped)

    with pytest.raises(LocalRuntimeError, match="No fue posible comunicarse"):
        controller.start()


def test_start_rejects_root_before_spawning(monkeypatch, tmp_path: Path) -> None:
    controller = RuntimeController(
        RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri="mongodb://temporary:27017",
        environment=_environment(tmp_path),
    )
    monkeypatch.setattr("mathmongo.launcher.os.geteuid", lambda: 0)
    controller._popen = lambda *_args, **_kwargs: pytest.fail("root must not spawn")

    with pytest.raises(LocalRuntimeError, match="no se ejecuta como root"):
        controller.start()


def test_stop_is_idempotent_and_never_signals_foreign_processes(monkeypatch, tmp_path: Path) -> None:
    controller = RuntimeController(
        RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri="mongodb://temporary:27017",
        environment=_environment(tmp_path),
    )
    stopped = RuntimeObservation(RuntimeStateKind.STOPPED, "stopped")
    monkeypatch.setattr(controller, "status", lambda: stopped)
    assert controller.stop().changed is False

    foreign = RuntimeObservation(RuntimeStateKind.FOREIGN, "foreign")
    monkeypatch.setattr(controller, "status", lambda: foreign)
    with pytest.raises(LocalRuntimeError, match="no tiene una identidad confirmada"):
        controller.stop()


def test_stop_sends_term_only_to_verified_supervisor(monkeypatch, tmp_path: Path) -> None:
    controller = RuntimeController(
        RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri="mongodb://temporary:27017",
        environment=_environment(tmp_path),
    )
    owned = _owned_observation()
    stopped = RuntimeObservation(RuntimeStateKind.STOPPED, "stopped")
    monkeypatch.setattr(controller, "status", lambda: owned)
    monkeypatch.setattr(controller, "_wait_until_stopped", lambda **_kwargs: stopped)
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(
        controller,
        "_signal_verified",
        lambda identity, signum: signals.append((identity.pid, signum)) or True,
    )

    assert controller.stop().changed is True
    assert signals == [(101, control.signal.SIGTERM)]


def test_restart_requires_explicit_orphan_recovery(monkeypatch, tmp_path: Path) -> None:
    controller = RuntimeController(
        RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri="mongodb://temporary:27017",
        environment=_environment(tmp_path),
    )
    orphan = RuntimeObservation(RuntimeStateKind.ORPHAN, "orphan")
    monkeypatch.setattr(controller, "status", lambda: orphan)

    with pytest.raises(LocalRuntimeError, match="recover-orphan"):
        controller.restart()


def test_restart_starts_when_runtime_is_already_stopped(monkeypatch, tmp_path: Path) -> None:
    controller = RuntimeController(
        RuntimeSettings(database="runtime_test", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri="mongodb://temporary:27017",
        environment=_environment(tmp_path),
    )
    stopped = RuntimeObservation(RuntimeStateKind.STOPPED, "stopped")
    expected = control.RuntimeAction(False, stopped, "started")
    monkeypatch.setattr(controller, "status", lambda: stopped)
    monkeypatch.setattr(controller, "start", lambda: expected)

    assert controller.restart() is expected


def test_runtime_status_cli_is_read_only_for_empty_xdg(monkeypatch, tmp_path: Path, capsys) -> None:
    environment = _environment(tmp_path)
    monkeypatch.setenv("HOME", environment["HOME"])
    monkeypatch.setenv("XDG_RUNTIME_DIR", environment["XDG_RUNTIME_DIR"])

    assert (
        cli.main(
            [
                "runtime",
                "status",
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

    assert "Runtime: stopped" in capsys.readouterr().out
    assert not (Path(environment["XDG_RUNTIME_DIR"]) / "mathmongo").exists()

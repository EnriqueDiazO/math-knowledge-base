"""Tests for the graphical MongoDB-first runtime launcher."""

# ruff: noqa: D103

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mathmongo.desktop_launch import launch_desktop_runtime
from mathmongo.desktop_launch import send_desktop_notification
from mathmongo.local_runtime.control import RuntimeAction
from mathmongo.local_runtime.models import LocalRuntimeError
from mathmongo.local_runtime.models import RuntimeSettings
from mathmongo.local_runtime.state import RuntimeObservation
from mathmongo.local_runtime.state import RuntimeStateKind
from mathmongo.mongodb_service import EnsureMongoResult
from mathmongo.mongodb_service import MongoServiceState
from mathmongo.mongodb_service import MongoServiceStatus

URI = "mongodb://alice:secret@localhost:27017/MathV0"


def mongo_result(*, ok: bool, message: str = "MongoDB ya está disponible.") -> EnsureMongoResult:
    status = MongoServiceStatus(
        MongoServiceState.ACTIVE_AND_REACHABLE if ok else MongoServiceState.INACTIVE,
        "active" if ok else "inactive",
        ok,
        "MathV0",
        "mongodb://localhost:27017/MathV0",
    )
    return EnsureMongoResult(ok, False, not ok, status, message)


def test_desktop_reuses_ensure_then_verified_runtime_and_opens_browser(tmp_path: Path) -> None:
    events: list[object] = []
    settings = RuntimeSettings(database="MathV0", streamlit_port=18501, advanced_reader_port=18766)
    observation = RuntimeObservation(RuntimeStateKind.OWNED, "owned")

    def ensure(**kwargs):
        events.append(("ensure", kwargs))
        return mongo_result(ok=True)

    class Controller:
        def __init__(self, received_settings, *, mongo_uri, environment):
            assert received_settings is settings
            assert mongo_uri == URI
            assert environment["STREAMLIT_SERVER_HEADLESS"] == "true"

        def start(self):
            events.append("runtime")
            return RuntimeAction(False, observation, "El runtime MathMongo ya está activo.")

    result = launch_desktop_runtime(
        settings,
        mongo_uri=URI,
        ensure=ensure,
        controller_factory=Controller,
        browser_open=lambda url, **_kwargs: events.append(("browser", url)) or True,
        notify=lambda message: events.append(("notify", message)),
        log_path_resolver=lambda: tmp_path / "desktop-launch.log",
    )

    assert result == 0
    assert events[0][0] == "ensure"
    assert events[0][1]["graphical"] is True
    assert events[0][1]["interactive"] is False
    assert events[1] == "runtime"
    assert events[2] == ("browser", "http://127.0.0.1:18501")
    log_text = (tmp_path / "desktop-launch.log").read_text(encoding="utf-8")
    assert "runtime MathMongo ya está activo" in log_text
    assert "alice" not in log_text
    assert "secret" not in log_text


def test_desktop_does_not_start_application_when_mongodb_fails(tmp_path: Path) -> None:
    notifications: list[str] = []

    result = launch_desktop_runtime(
        RuntimeSettings(database="MathV0", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri=URI,
        ensure=lambda **_kwargs: mongo_result(
            ok=False,
            message="Inicio cancelado: MongoDB continúa detenido.",
        ),
        controller_factory=lambda *_args, **_kwargs: pytest.fail("runtime must not start"),
        browser_open=lambda *_args, **_kwargs: pytest.fail("browser must not open"),
        notify=notifications.append,
        log_path_resolver=lambda: tmp_path / "desktop-launch.log",
    )

    assert result == 6
    assert notifications == ["Inicio cancelado: MongoDB continúa detenido."]


def test_desktop_rejects_root_before_ensure_or_log(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mathmongo.launcher.os.geteuid", lambda: 0)
    notifications: list[str] = []

    with pytest.raises(LocalRuntimeError, match="no se ejecuta como root"):
        launch_desktop_runtime(
            RuntimeSettings(database="MathV0", streamlit_port=18501, advanced_reader_port=18766),
            mongo_uri=URI,
            ensure=lambda **_kwargs: pytest.fail("ensure must not run as root"),
            notify=notifications.append,
            log_path_resolver=lambda: tmp_path / "unexpected.log",
        )

    assert not (tmp_path / "unexpected.log").exists()
    assert notifications == [
        "MathMongo no se ejecuta como root. Sólo `systemctl start mongod` puede elevarse."
    ]


def test_desktop_runtime_error_is_sanitized_logged_and_notified(tmp_path: Path) -> None:
    notifications: list[str] = []

    class FailingController:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            raise LocalRuntimeError(f"failed {URI} password=hunter2")

    result = launch_desktop_runtime(
        RuntimeSettings(database="MathV0", streamlit_port=18501, advanced_reader_port=18766),
        mongo_uri=URI,
        ensure=lambda **_kwargs: mongo_result(ok=True),
        controller_factory=FailingController,
        notify=notifications.append,
        log_path_resolver=lambda: tmp_path / "desktop-launch.log",
    )

    assert result == 6
    combined = "\n".join(notifications) + (tmp_path / "desktop-launch.log").read_text()
    assert URI not in combined
    assert "alice" not in combined
    assert "secret" not in combined
    assert "hunter2" not in combined


def test_notification_uses_argument_list_without_shell() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    send_desktop_notification(
        "MongoDB detenido",
        runner=runner,
        which=lambda _name: "/usr/bin/notify-send",
    )

    assert calls[0][0] == ["/usr/bin/notify-send", "MathMongo", "MongoDB detenido"]
    assert calls[0][1]["shell"] is False


def test_desktop_source_does_not_store_passwords_or_use_shell_true() -> None:
    source = (Path(__file__).resolve().parents[1] / "mathmongo" / "desktop_launch.py").read_text()

    assert "shell=True" not in source
    assert "password =" not in source.casefold()
    assert "write_text(mongo_uri" not in source

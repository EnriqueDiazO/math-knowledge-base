"""Focused launcher tests for the isolated S5A process."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mathmongo.advanced_reader import launcher
from mathmongo.advanced_reader.launcher import AdvancedReaderLaunchError
from mathmongo.advanced_reader.launcher import launch_advanced_reader
from mathmongo.config import AppConfig


class FakeAdmin:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def command(self, name: str) -> dict[str, int]:
        self.commands.append(name)
        return {"ok": 1}


class StrictDatabase:
    """Database token whose collections must remain unopened at launch time."""

    def __init__(self) -> None:
        self.collection_accesses: list[str] = []

    def __getitem__(self, name: str) -> Any:
        self.collection_accesses.append(name)
        raise AssertionError(f"unexpected collection access: {name}")


class FakeClient:
    def __init__(self, database: StrictDatabase) -> None:
        self.admin = FakeAdmin()
        self.database = database
        self.database_names: list[str] = []
        self.closed = False

    def __getitem__(self, name: str) -> StrictDatabase:
        self.database_names.append(name)
        return self.database

    def close(self) -> None:
        self.closed = True


def _successful_specs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        launcher.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(name=name),
    )


@pytest.mark.parametrize(
    "host",
    ["", "0.0.0.0", "127.0.0.2", "192.168.0.20", "reader.example"],
)
def test_launcher_rejects_non_loopback_before_port_or_database_access(host: str) -> None:
    calls: list[str] = []

    with pytest.raises(AdvancedReaderLaunchError, match="localhost|127.0.0.1"):
        launch_advanced_reader(
            host=host,
            port=8766,
            database_name="MathV0",
            mongo_uri="mongodb://never-used",
            log_level="info",
            client_factory=lambda *_args, **_kwargs: calls.append("client"),
            server_runner=lambda *_args, **_kwargs: calls.append("server"),
            port_check=lambda *_args: calls.append("port") or True,
        )

    assert calls == []


@pytest.mark.parametrize("port", [0, -1, 65536, True, 8766.0, "8766"])
def test_launcher_rejects_invalid_ports_without_starting_anything(port: object) -> None:
    calls: list[str] = []
    with pytest.raises(AdvancedReaderLaunchError, match="puerto"):
        launch_advanced_reader(
            host="127.0.0.1",
            port=port,  # type: ignore[arg-type]
            database_name="MathV0",
            mongo_uri="mongodb://never-used",
            log_level="info",
            client_factory=lambda *_args, **_kwargs: calls.append("client"),
            server_runner=lambda *_args, **_kwargs: calls.append("server"),
            port_check=lambda *_args: calls.append("port") or True,
        )
    assert calls == []


@pytest.mark.parametrize(
    "database_name",
    ["", "   ", "bad/name", "bad\\name", 'bad"name', "bad$name", "x" * 65],
)
def test_launcher_rejects_unsafe_database_names(database_name: str) -> None:
    with pytest.raises(AdvancedReaderLaunchError, match="base"):
        launch_advanced_reader(
            host="localhost",
            port=8766,
            database_name=database_name,
            mongo_uri="mongodb://never-used",
            log_level="info",
            client_factory=lambda *_args, **_kwargs: pytest.fail("client opened"),
            port_check=lambda *_args: True,
        )


def test_launcher_rejects_unknown_log_level_before_port_and_client() -> None:
    calls: list[str] = []
    with pytest.raises(AdvancedReaderLaunchError, match="log"):
        launch_advanced_reader(
            host="::1",
            port=8766,
            database_name=" MathV0 ",
            mongo_uri="mongodb://never-used",
            log_level="trace",
            client_factory=lambda *_args, **_kwargs: calls.append("client"),
            port_check=lambda *_args: calls.append("port") or True,
        )
    assert calls == []


def test_occupied_loopback_port_stops_before_mongo_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _successful_specs(monkeypatch)
    calls: list[tuple[str, int]] = []
    with pytest.raises(AdvancedReaderLaunchError, match="ocupado"):
        launch_advanced_reader(
            host="127.0.0.1",
            port=8766,
            database_name="MathV0",
            mongo_uri="mongodb://never-used",
            log_level="info",
            client_factory=lambda *_args, **_kwargs: pytest.fail("client opened"),
            port_check=lambda host, port: calls.append((host, port)) or False,
        )
    assert calls == [("127.0.0.1", 8766)]


def test_successful_launch_uses_explicit_app_loopback_and_bounded_mongo_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _successful_specs(monkeypatch)
    database = StrictDatabase()
    client = FakeClient(database)
    client_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    server_calls: list[tuple[Any, dict[str, Any]]] = []

    def client_factory(*args: Any, **kwargs: Any) -> FakeClient:
        client_calls.append((args, kwargs))
        return client

    def server_runner(app: Any, **kwargs: Any) -> None:
        server_calls.append((app, kwargs))

    result = launch_advanced_reader(
        host="localhost",
        port=8766,
        database_name=" MathV0 ",
        mongo_uri="mongodb://reader:secret@127.0.0.1:27017/private",
        log_level="warning",
        client_factory=client_factory,
        server_runner=server_runner,
        port_check=lambda host, port: (host, port) == ("localhost", 8766),
    )

    assert result == 0
    assert client_calls == [
        (
            ("mongodb://reader:secret@127.0.0.1:27017/private",),
            {"serverSelectionTimeoutMS": 2000, "connectTimeoutMS": 2000},
        )
    ]
    assert client.admin.commands == ["ping"]
    assert client.database_names == ["MathV0"]
    assert database.collection_accesses == []
    assert client.closed is True
    assert len(server_calls) == 1
    app, kwargs = server_calls[0]
    assert app.state.advanced_reader_dependencies.database_name == "MathV0"
    assert kwargs == {
        "host": "localhost",
        "port": 8766,
        "log_level": "warning",
        "access_log": False,
    }


def test_ctrl_c_returns_130_and_always_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _successful_specs(monkeypatch)
    client = FakeClient(StrictDatabase())

    def interrupted_runner(*_args: Any, **_kwargs: Any) -> None:
        raise KeyboardInterrupt

    result = launch_advanced_reader(
        host="127.0.0.1",
        port=8766,
        database_name="MathV0",
        mongo_uri="mongodb://127.0.0.1",
        log_level="info",
        client_factory=lambda *_args, **_kwargs: client,
        server_runner=interrupted_runner,
        port_check=lambda *_args: True,
    )

    assert result == 130
    assert client.closed is True


def test_infrastructure_failure_is_wrapped_without_uri_path_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _successful_specs(monkeypatch)
    mongo_uri = "mongodb://alice:super-secret@127.0.0.1:27017/private"
    local_path = str(tmp_path / "HOME/private/config.json")

    def failing_client(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(f"connect failed: {mongo_uri} at {local_path}")

    with pytest.raises(AdvancedReaderLaunchError) as caught:
        launch_advanced_reader(
            host="127.0.0.1",
            port=8766,
            database_name="MathV0",
            mongo_uri=mongo_uri,
            log_level="info",
            client_factory=failing_client,
            port_check=lambda *_args: True,
        )

    public = str(caught.value)
    assert public == "No se pudo iniciar el lector avanzado con la configuración local."
    for forbidden in (mongo_uri, "alice", "super-secret", local_path, str(tmp_path)):
        assert forbidden not in public


def test_main_never_prints_the_configured_mongo_uri(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_uri = "mongodb://alice:super-secret@localhost:27017/private"
    settings = AppConfig(
        mongo_uri=secret_uri,
        mongo_database="MathV0",
        advanced_reader_enabled=True,
        advanced_reader_host="127.0.0.1",
        advanced_reader_port=8766,
    )
    monkeypatch.setattr(launcher, "resolve_config", lambda **_kwargs: settings)

    def fail_launch(**kwargs: Any) -> int:
        assert kwargs["mongo_uri"] == secret_uri
        raise AdvancedReaderLaunchError("No se pudo iniciar el lector avanzado.")

    monkeypatch.setattr(launcher, "launch_advanced_reader", fail_launch)
    result = launcher.main([])
    captured = capsys.readouterr()

    assert result == 1
    assert captured.out == ""
    assert "No se pudo iniciar" in captured.err
    assert secret_uri not in captured.err
    assert "alice" not in captured.err
    assert "super-secret" not in captured.err


def test_launcher_source_has_no_browser_or_process_spawning_path() -> None:
    source_path = Path(launcher.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    }

    assert "webbrowser" not in imported_roots
    assert "subprocess" not in imported_roots
    assert "browser" not in source.casefold()
    assert "startfile" not in source.casefold()

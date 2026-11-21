"""Exercise process ownership, failure cleanup and safe coverage environments."""

from __future__ import annotations

import configparser
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pymongo.errors import ConnectionFailure

from scripts import quality
from scripts import quality_mongo


class OwnedProcess:
    """Record lifecycle operations without starting any real service."""

    def __init__(self):
        """Start with a live owned process and no cleanup actions."""
        self.pid = 24680
        self.exited = False
        self.actions = []
        self.timeout = False

    def poll(self):
        """Return an early-exit status when the scenario requests it."""
        return 1 if self.exited else None

    def terminate(self):
        """Record a termination of this owned process."""
        self.actions.append("terminate")

    def wait(self, *, timeout):
        """Simulate one failed graceful stop followed by successful kill cleanup."""
        self.actions.append(("wait", timeout))
        if self.timeout:
            self.timeout = False
            raise subprocess.TimeoutExpired("owned mongod", timeout)
        return 0

    def kill(self):
        """Record the forced stop of only this process."""
        self.actions.append("kill")


class MongoProbe:
    """Return bounded health/identity facts without opening MongoDB sockets."""

    def __init__(self, process):
        """Associate the server identity with the simulated process by default."""
        self.admin = self
        self.process = process
        self.pid = process.pid
        self.databases = ["admin", "config", "local"]
        self.closed = False
        self.close_error = False
        self.unready = False
        self.commands = []

    def command(self, name):
        """Expose just the ping and process identity used before any test write."""
        self.commands.append(name)
        if self.unready:
            raise ConnectionFailure("not ready")
        return {"ok": 1, "pid": self.pid}

    def list_database_names(self):
        """Expose explicitly configured database names for isolation checks."""
        return self.databases

    def close(self):
        """Record cleanup, including an optional failure while closing the client."""
        self.closed = True
        if self.close_error:
            raise OSError("client close failed")


@pytest.fixture
def owned_mongo(monkeypatch, tmp_path):
    """Replace external processes/clients while exercising real temporary-directory cleanup."""
    process = OwnedProcess()
    client = MongoProbe(process)
    created = []
    children = []
    monkeypatch.setattr(quality_mongo.shutil, "which", lambda _name: "/owned/mongod")
    monkeypatch.setattr(quality_mongo, "ROOT", tmp_path)
    def launch(command, **_kwargs):
        created.append(Path(command[command.index("--dbpath") + 1]).parent)
        return process
    def run(command, **kwargs):
        children.append((command, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(quality_mongo.subprocess, "Popen", launch)
    monkeypatch.setattr(quality_mongo.subprocess, "run", run)
    monkeypatch.setattr(quality_mongo, "MongoClient", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(quality_mongo.sys, "argv", ["quality_mongo.py"])
    return SimpleNamespace(process=process, client=client, created=created, children=children)


def test_mongo_tests_use_only_the_owned_server_and_private_paths(owned_mongo, monkeypatch):
    """Production URI/database/config must not reach the child test process."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://production.invalid:27017")
    monkeypatch.setenv("MONGODB_DB", "MathV0")
    monkeypatch.setenv("MONGO_URI", "mongodb://another-production.invalid")
    assert quality_mongo.main() == 0
    command, kwargs = owned_mongo.children[0]
    environment = kwargs["env"]
    assert environment["MONGODB_URI"].startswith("mongodb://127.0.0.1:")
    assert environment["MONGODB_DB"] == "mathmongo_audit_unused"
    assert "MONGO_URI" not in environment
    assert environment["MATHMONGO_RUN_MONGO_E2E"] == "1"
    assert set(quality_mongo.DEFAULT_TESTS) <= set(command)
    assert owned_mongo.client.closed
    assert owned_mongo.process.actions == ["terminate", ("wait", 20)]
    assert all(not path.exists() for path in owned_mongo.created)


def test_failed_client_construction_still_stops_the_owned_process(owned_mongo, monkeypatch):
    """A client-constructor failure must not leave mongod running on a deleted dbpath."""
    def fail_client(*_args, **_kwargs):
        raise OSError("client construction failed")
    monkeypatch.setattr(quality_mongo, "MongoClient", fail_client)
    with pytest.raises(OSError, match="construction"):
        quality_mongo.main()
    assert owned_mongo.process.actions == ["terminate", ("wait", 20)]
    assert owned_mongo.children == []
    assert all(not path.exists() for path in owned_mongo.created)


def test_client_close_failure_cannot_skip_process_cleanup(owned_mongo):
    """Releasing the owned process is mandatory even if client cleanup raises."""
    owned_mongo.client.close_error = True
    with pytest.raises(OSError, match="close failed"):
        quality_mongo.main()
    assert owned_mongo.process.actions == ["terminate", ("wait", 20)]


def test_another_servers_pid_blocks_all_test_writes(owned_mongo):
    """A loopback port collision must never turn into a user-Mongo fallback."""
    owned_mongo.client.pid += 1
    with pytest.raises(RuntimeError, match="owned|process|identity"):
        quality_mongo.main()
    assert owned_mongo.children == []
    assert owned_mongo.client.closed
    assert owned_mongo.process.actions[0] == "terminate"


def test_unexpected_existing_database_blocks_before_pytest(owned_mongo):
    """The isolation check is an ordinary runtime guard, also active under python -O."""
    owned_mongo.client.databases.append("MathV0")
    with pytest.raises(RuntimeError, match="database|fresh|empty"):
        quality_mongo.main()
    assert owned_mongo.children == []
    assert owned_mongo.client.closed


def test_early_exit_and_health_timeout_release_owned_resources(owned_mongo, monkeypatch):
    """No test starts when the owned service exits or never becomes healthy."""
    owned_mongo.process.exited = True
    with pytest.raises(RuntimeError, match="exited"):
        quality_mongo.main()
    assert owned_mongo.children == []
    owned_mongo.process.exited = False
    owned_mongo.client.unready = True
    clock = iter([0, 21])
    monkeypatch.setattr(quality_mongo.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="ready"):
        quality_mongo.main()
    assert owned_mongo.client.closed
    assert len(owned_mongo.process.actions) == 4


def test_test_failure_and_slow_shutdown_keep_the_failure_status(owned_mongo, monkeypatch):
    """A test failure cannot become success while the process is forcibly cleaned up."""
    owned_mongo.process.timeout = True
    monkeypatch.setattr(quality_mongo.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=7))
    assert quality_mongo.main() == 7
    assert owned_mongo.process.actions == ["terminate", ("wait", 20), "kill", ("wait", 5)]
    assert owned_mongo.client.closed


def test_missing_mongod_never_falls_back_to_an_existing_service(monkeypatch):
    """A missing executable is an explicit blocker instead of permission to use production."""
    monkeypatch.setattr(quality_mongo.shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit, match="no user MongoDB fallback"):
        quality_mongo.main()


@pytest.mark.parametrize("unit_status, mongo_status, expected_calls", [(4, 0, 1), (0, 5, 2), (0, 0, 4)])
def test_quality_runner_propagates_failures_and_combines_only_success(tmp_path, monkeypatch, unit_status, mongo_status, expected_calls):
    """Combine unit/E2E evidence only after successful, private child runs."""
    monkeypatch.setattr(quality, "ROOT", tmp_path)
    monkeypatch.setattr(quality.sys, "argv", ["quality.py", "--with-mongo", "-q"])
    (tmp_path / ".coveragerc").write_text("[run]\nrelative_files=True\nsource=.\nomit=tests/*\n mathdbmongo/*\npatch=subprocess\n")
    calls = []
    private = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        environment = kwargs["env"]
        private.append(Path(environment["XDG_DATA_HOME"]).parent)
        if "pytest" in command:
            (tmp_path / "evidence/sonar/coverage.xml").write_text("unit report")
            return SimpleNamespace(returncode=unit_status)
        if "run" in command:
            return SimpleNamespace(returncode=mongo_status)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(quality.subprocess, "run", run)
    assert quality.main() == (unit_status or mongo_status)
    assert len(calls) == expected_calls
    first, kwargs = calls[0]
    assert "--with-mongo" not in first and "-q" in first
    assert kwargs["env"]["MONGODB_DB"] == "mathmongo_audit_unit"
    assert kwargs["env"]["MATHMONGO_RUN_MONGO_E2E"] == "0"
    config = configparser.ConfigParser(interpolation=None)
    config.read(tmp_path / "evidence/sonar/coverage-runtime.ini")
    assert config.get("run", "source") == str(tmp_path)
    assert config.get("run", "omit").split() == [str(tmp_path / "tests/*"), str(tmp_path / "mathdbmongo/*")]
    assert config.get("run", "patch") == "subprocess"
    assert all(not p.exists() for p in private)
    if expected_calls == 4:
        assert calls[2][0][-2:] == ["combine", "--append"]
        assert calls[3][0][-1] == "xml"
        assert (tmp_path / "evidence/sonar/coverage-unit.xml").read_text() == "unit report"


def test_remaining_test_database_is_an_error_and_still_releases_only_owned_resources(owned_mongo, monkeypatch):
    """A child leaving a database behind cannot produce success or bypass process cleanup."""
    def child(_command, **_kwargs):
        owned_mongo.client.databases.append("mathmongo_test_leak")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(quality_mongo.subprocess, "run", child)
    with pytest.raises(RuntimeError, match="not removed"):
        quality_mongo.main()
    assert owned_mongo.client.closed
    assert owned_mongo.process.actions == ["terminate", ("wait", 20)]
    assert all(not path.exists() for path in owned_mongo.created)

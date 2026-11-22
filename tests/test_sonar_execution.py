"""Verify the pinned installer and scan orchestration using disposable artifacts."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from scripts import sonar


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Keep every installer and lifecycle artifact under pytest's private directory."""
    monkeypatch.setattr(sonar, "ROOT", tmp_path)
    infrastructure = tmp_path / "infra/sonarqube"
    infrastructure.mkdir(parents=True)
    monkeypatch.setattr(sonar, "INFRA", infrastructure)
    monkeypatch.setattr(sonar, "PRIVATE", infrastructure / "access.local.json")
    monkeypatch.setattr(sonar, "SCANNER", tmp_path / ".tools" / sonar.SCANNER_NAME / "bin/sonar-scanner")
    monkeypatch.setenv("SONAR_HOST_URL", "http://127.0.0.1:19000")
    monkeypatch.delenv("SONAR_TOKEN", raising=False)
    reference = {"mode": "PREVIOUS_VERSION", "date": "2026-11-21T16:46:16+0000"}
    (infrastructure / "reference.json").write_text(json.dumps(reference))
    return reference


def scanner_archive():
    """Build a benign executable fixture with the real archive layout and Unix modes."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name in ("bin/sonar-scanner", "jre/lib/jspawnhelper"):
            member = zipfile.ZipInfo(sonar.SCANNER_NAME + "/" + name)
            member.external_attr = (stat.S_IFREG | 0o755) << 16
            archive.writestr(member, "#!/bin/sh\nprintf 'fixture-scanner-version\\n'\n")
    return output.getvalue()


def test_pinned_installer_verifies_download_and_keeps_jre_executable(isolated, monkeypatch, capfd):
    """The authenticated archive must produce runnable scanner/JRE helpers, even on resume."""
    payload = scanner_archive()
    # Only this synthetic archive's checksum is substituted; production keeps its official pin.
    monkeypatch.setattr(sonar, "SCANNER_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(sonar.platform, "system", lambda: "Linux")
    monkeypatch.setattr(sonar.platform, "machine", lambda: "x86_64")
    downloads = []
    def download(url, *, timeout):
        downloads.append((url, timeout))
        return io.BytesIO(payload)
    monkeypatch.setattr(sonar, "urlopen", download)
    sonar.install_scanner()
    sonar.install_scanner()
    assert len(downloads) == 1
    assert downloads[0][0].startswith("https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/")
    assert downloads[0][1] == 120
    assert capfd.readouterr().out.count("fixture-scanner-version") == 2
    helper = sonar.SCANNER.parent.parent / "jre/lib/jspawnhelper"
    assert os.access(helper, os.X_OK)
    assert stat.S_IMODE(helper.stat().st_mode) == 0o755


def test_bad_checksum_retains_archive_without_extracting_or_executing(isolated):
    """A corrupted cached download cannot install or run anything."""
    download = sonar.ROOT / ".tools/downloads" / f"sonar-scanner-cli-{sonar.SCANNER_VERSION}-linux-x64.zip"
    download.parent.mkdir(parents=True)
    download.write_bytes(b"not the authenticated scanner")
    with pytest.raises(ValueError, match="checksum"):
        sonar.install_scanner()
    assert download.read_bytes() == b"not the authenticated scanner"
    assert not sonar.SCANNER.parent.exists()


def test_unsupported_architecture_does_not_download(isolated, monkeypatch):
    """An unsupported host is blocked before any network or disk download."""
    monkeypatch.setattr(sonar.platform, "machine", lambda: "aarch64")
    with pytest.raises(ValueError, match="x86_64"):
        sonar.install_scanner()
    assert not (sonar.ROOT / ".tools").exists()


def test_scan_generates_fresh_reports_keeps_label_out_of_version_and_retains_gate_failure(isolated, monkeypatch):
    """Old reports cannot survive failed generation, and a Gate error remains the exit status."""
    monkeypatch.setattr(sonar, "credentials", lambda: {"admin_password": "test-account"})
    monkeypatch.setattr(sonar, "token_auth", lambda: "Bearer test-token")
    python = sonar.ROOT / "evidence/sonar/coverage.xml"
    lcov = sonar.ROOT / "frontend/advanced-reader/coverage/lcov.info"
    task = sonar.ROOT / ".scannerwork/report-task.txt"
    for path in (python, lcov, task):
        path.parent.mkdir(parents=True)
        path.write_text("obsolete")
    monkeypatch.setattr(sonar, "api", lambda path, **_kwargs: {"status": "UP"} if path.endswith("status") else {"projectStatus": {"period": isolated}})
    calls = []
    published = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "--with-mongo" in command:
            assert not python.exists() and not lcov.exists()
            python.write_text('<coverage lines-valid="1" lines-covered="1"/>')
        elif command == ["npm", "run", "test:coverage"]:
            lcov.write_text("SF:src/app/App.tsx\nDA:1,1\nend_of_record\n")
        else:
            assert not task.exists()
            assert kwargs["env"]["SONAR_TOKEN"] == "test-token"
            assert kwargs["env"]["SONAR_HOST_URL"] == "http://127.0.0.1:19000"
            task.write_text("ceTaskId=new-task\n")
            return SimpleNamespace(returncode=3)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(sonar.subprocess, "run", run)
    monkeypatch.setattr(sonar, "install_scanner", lambda: None)
    monkeypatch.setattr(sonar, "snapshot", published.append)
    assert sonar.scan("followup-final") == 3
    assert len(calls) == 3 and published == ["followup-final"]
    assert all("projectVersion" not in str(command) for command, _kwargs in calls)
    assert calls[1][1]["cwd"] == sonar.ROOT / "frontend/advanced-reader"


def test_changed_reference_blocks_before_tests_or_upload(isolated, monkeypatch):
    """A changed date must not quietly reset the comparison."""
    monkeypatch.setattr(sonar, "credentials", lambda: {"admin_password": "test-account"})
    def api(path, **_kwargs):
        return {"status": "UP"} if path.endswith("status") else {"projectStatus": {"period": {**isolated, "date": "different"}}}
    monkeypatch.setattr(sonar, "api", api)
    with pytest.raises(ValueError, match="reference changed"):
        sonar.scan("followup-final")
    assert not (sonar.ROOT / "evidence").exists()


def test_report_failure_prevents_upload_and_preserves_child_failure(isolated, monkeypatch):
    """Report-generation failure must stop the scanner instead of uploading stale coverage."""
    monkeypatch.setattr(sonar, "credentials", lambda: {"admin_password": "test-account"})
    monkeypatch.setattr(sonar, "api", lambda path, **_kwargs: {"status": "UP"} if path.endswith("status") else {"projectStatus": {"period": isolated}})
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(9, command)
    monkeypatch.setattr(sonar.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError) as error:
        sonar.scan("followup-final")
    assert error.value.returncode == 9 and len(calls) == 1


@pytest.mark.parametrize("label", ["../final", "/tmp/elsewhere", "final.xml/child", "", "x" * 65])
def test_evidence_labels_cannot_escape_output_directory(label):
    """The artifact label never becomes an arbitrary path or scanner property."""
    with pytest.raises(argparse.ArgumentTypeError):
        sonar.evidence_label(label)


@pytest.mark.parametrize("command, expected", [("init", "initialize"), ("install-scanner", "install_scanner"), ("up", "up"), ("bootstrap", "bootstrap")])
def test_cli_dispatches_only_the_requested_lifecycle_action(isolated, monkeypatch, command, expected):
    """Each public CLI command selects exactly its supported lifecycle function."""
    called = []
    monkeypatch.setattr(sonar, expected, lambda: called.append(expected))
    monkeypatch.setattr(sonar.sys, "argv", ["sonar.py", command])
    assert sonar.main() == 0 and called == [expected]


def test_cli_down_preserves_volumes_and_status_has_no_credentials(isolated, monkeypatch, capsys):
    """Shutdown never adds -v; status does not need privileged account state."""
    calls = []
    monkeypatch.setattr(sonar.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    monkeypatch.setattr(sonar.sys, "argv", ["sonar.py", "down"])
    assert sonar.main() == 0
    assert calls[0][0][-1] == "down" and "-v" not in calls[0][0]
    assert calls[0][1]["check"] is True
    monkeypatch.setattr(sonar.sys, "argv", ["sonar.py", "status"])
    monkeypatch.setattr(sonar, "api", lambda _path: {"status": "UP"})
    assert sonar.main() == 0
    assert json.loads(capsys.readouterr().out) == {"status": "UP"}


def test_up_blocks_low_host_limit_before_starting_services(isolated, monkeypatch):
    """Host prerequisites are enforced without modifying sysctl or starting Docker services."""
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *args, **kwargs: "65530" if str(self) == "/proc/sys/vm/max_map_count" else original(self, *args, **kwargs))
    calls = []
    monkeypatch.setattr(sonar.subprocess, "run", lambda command, **kwargs: calls.append(command))
    with pytest.raises(ValueError, match="vm.max_map_count"):
        sonar.up()
    assert calls == [["docker", "info"]]
    assert stat.S_IMODE((sonar.INFRA / ".env").stat().st_mode) == 0o600


def test_up_waits_through_unavailability_and_never_removes_volumes(isolated, monkeypatch):
    """Readiness polling tolerates startup connection failures and accepts only UP."""
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *args, **kwargs: "524288" if str(self) == "/proc/sys/vm/max_map_count" else original(self, *args, **kwargs))
    class FreePort:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def connect_ex(self, _address):
            return 111
    monkeypatch.setattr(sonar.socket, "socket", FreePort)
    actions = []
    monkeypatch.setattr(sonar.subprocess, "run", lambda command, **kwargs: actions.append(command))
    statuses = iter([URLError("starting"), {"status": "STARTING"}, {"status": "UP"}])
    def api(_path):
        result = next(statuses)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(sonar, "api", api)
    monkeypatch.setattr(sonar.time, "sleep", lambda seconds: actions.append(seconds))
    sonar.up()
    assert actions[0] == ["docker", "info"]
    assert actions[1][-2:] == ["up", "-d"]
    assert actions[2:] == [3, 3]


def test_token_precedence_and_missing_credentials_are_explicit(isolated, monkeypatch):
    """Explicit tokens override saved tokens; missing access never sends an empty header."""
    sonar.write_private(sonar.PRIVATE, json.dumps({"url": sonar.local_url(), "token": "saved-test-token"}))
    assert sonar.token_auth() == "Bearer saved-test-token"
    monkeypatch.setenv("SONAR_TOKEN", "explicit-test-token")
    assert sonar.token_auth() == "Bearer explicit-test-token"
    monkeypatch.delenv("SONAR_TOKEN")
    sonar.PRIVATE.unlink()
    with pytest.raises(ValueError, match="No token"):
        sonar.token_auth()


@pytest.mark.parametrize("xml,lcov", [("<broken", "SF:src/a.ts\nDA:1,1\nend_of_record\n"), ('<coverage lines-valid="0"/>', "SF:src/a.ts\nDA:1,1\nend_of_record\n"), ('<coverage lines-valid="1"/>', "end_of_record\n")])
def test_invalid_coverage_is_a_controlled_error(xml, lcov, isolated, monkeypatch):
    """Malformed/empty reports must stop the scanner with a controlled error."""
    monkeypatch.setattr(sonar, "credentials", lambda: {"admin_password": "test-account"})
    monkeypatch.setattr(sonar, "token_auth", lambda: "Bearer test-token")
    monkeypatch.setattr(sonar, "api", lambda path, **_kwargs: {"status": "UP"} if path.endswith("status") else {"projectStatus": {"period": isolated}})
    monkeypatch.setattr(sonar, "install_scanner", lambda: None)
    calls = []
    def run(command, **_kwargs):
        calls.append(command)
        if "--with-mongo" in command:
            report = sonar.ROOT / "evidence/sonar/coverage.xml"
            report.parent.mkdir(parents=True)
            report.write_text(xml)
        elif command == ["npm", "run", "test:coverage"]:
            report = sonar.ROOT / "frontend/advanced-reader/coverage/lcov.info"
            report.parent.mkdir(parents=True)
            report.write_text(lcov)
        else:
            raise AssertionError("Scanner must not upload invalid coverage")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(sonar.subprocess, "run", run)
    with pytest.raises(ValueError, match="coverage|Coverage|LCOV"):
        sonar.scan("invalid-report")
    assert len(calls) == 2


def test_occupied_port_never_starts_or_stops_any_service(isolated, monkeypatch):
    """A listening foreign service is preserved instead of being replaced by Compose."""
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        monkeypatch.setenv("SONAR_HOST_URL", f"http://127.0.0.1:{listener.getsockname()[1]}")
        original = Path.read_text
        monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: "524288" if str(self) == "/proc/sys/vm/max_map_count" else original(self, *a, **k))
        calls = []
        monkeypatch.setattr(sonar.subprocess, "run", lambda command, **kwargs: calls.append(command))
        with pytest.raises(ValueError, match="Port occupied"):
            sonar.up()
        assert calls == [["docker", "info"]]
        assert listener.getsockname()[1] > 0


def test_startup_deadline_is_an_error_without_resetting_owned_volumes(isolated, monkeypatch):
    """A failed readiness deadline cannot trigger a reset or report successful startup."""
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: "524288" if str(self) == "/proc/sys/vm/max_map_count" else original(self, *a, **k))
    class FreePort:
        """Supply only the connection probe needed by this failure scenario."""
        def __enter__(self):
            """Enter the disposable probe."""
            return self
        def __exit__(self, *_args):
            """Release the disposable probe."""
            return None
        def connect_ex(self, _address):
            """Indicate that the requested port has no existing listener."""
            return 111
    monkeypatch.setattr(sonar.socket, "socket", FreePort)
    clock = iter([0, 601])
    monkeypatch.setattr(sonar.time, "monotonic", lambda: next(clock))
    calls = []
    monkeypatch.setattr(sonar.subprocess, "run", lambda command, **kwargs: calls.append(command))
    with pytest.raises(ValueError, match="600 seconds"):
        sonar.up()
    assert calls[0] == ["docker", "info"]
    assert calls[1][-2:] == ["up", "-d"]
    assert len(calls) == 2 and all("down" not in command and "-v" not in command for command in calls)

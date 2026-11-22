"""Verify credentials, real HTTP behavior and analysis consistency without real accounts."""

from __future__ import annotations

import json
import os
import stat
from urllib.error import HTTPError

import pytest
from sonar_http_support import SonarHttpServer

from scripts import sonar


@pytest.fixture
def installation(tmp_path, monkeypatch):
    """Redirect all private files and requests to one disposable local installation."""
    infrastructure = tmp_path / "infra/sonarqube"
    infrastructure.mkdir(parents=True)
    (infrastructure / "reference.json").write_text(json.dumps({"mode": "PREVIOUS_VERSION", "date": "2026-11-21T16:46:16+0000"}))
    monkeypatch.setattr(sonar, "ROOT", tmp_path)
    monkeypatch.setattr(sonar, "INFRA", infrastructure)
    monkeypatch.setattr(sonar, "PRIVATE", infrastructure / "access.local.json")
    monkeypatch.delenv("SONAR_TOKEN", raising=False)
    with SonarHttpServer() as server:
        monkeypatch.setenv("SONAR_HOST_URL", server.url)
        yield server


def account(server):
    """Persist credentials for an already initialized simulated account."""
    server.password = "test-account-password"
    server.project = True
    sonar.write_private(sonar.PRIVATE, json.dumps({"url": server.url, "admin_password": server.password, "token": "test-only-token"}))


def task_file():
    """Supply a known scanner task artifact without using a previous real scan."""
    task = sonar.ROOT / ".scannerwork/report-task.txt"
    task.parent.mkdir()
    task.write_text("ceTaskId=task-current\n")
    (sonar.ROOT / "sonar-project.properties").write_text("sonar.projectKey=mathmongo-local\n")


def test_bootstrap_changes_defaults_and_creates_only_the_scoped_project(installation, capsys):
    """A fresh setup must change defaults and persist a project-scoped token privately."""
    sonar.bootstrap()
    state = sonar.credentials()
    assert state["admin_password"] == installation.password != "admin"
    assert state["url"] == installation.url
    assert state["token"] == "test-project-analysis-token"
    assert stat.S_IMODE(sonar.PRIVATE.stat().st_mode) == 0o600
    token_calls = [call for call in installation.calls if call[1] == "/api/user_tokens/generate"]
    assert token_calls[0][2]["type"] == ["PROJECT_ANALYSIS_TOKEN"]
    assert token_calls[0][2]["projectKey"] == ["mathmongo-local"]
    output = capsys.readouterr().out
    assert state["admin_password"] not in output and state["token"] not in output
    before = sonar.PRIVATE.read_bytes()
    previous_posts = [c for c in installation.calls if c[0] == "POST"]
    sonar.bootstrap()
    assert sonar.PRIVATE.read_bytes() == before
    assert [c for c in installation.calls if c[0] == "POST"] == previous_posts


def test_interrupted_token_creation_resumes_without_resetting_password(installation):
    """Losing token creation must leave enough state to resume the same account."""
    installation.fail_token = True
    with pytest.raises(HTTPError) as error:
        sonar.bootstrap()
    assert error.value.code == 503
    password = sonar.credentials()["admin_password"]
    assert "token" not in sonar.credentials()
    sonar.bootstrap()
    assert sonar.credentials()["admin_password"] == password == installation.password
    assert sonar.credentials()["token"] == "test-project-analysis-token"
    assert len([c for c in installation.calls if c[1] == "/api/users/change_password"]) == 1


def test_existing_unknown_credentials_are_not_reset(installation):
    """A pre-existing account with different credentials must remain untouched."""
    account(installation)
    installation.password = "another-account-password"
    before = sonar.PRIVATE.read_bytes()
    with pytest.raises(ValueError, match="Existing credentials"):
        sonar.bootstrap()
    assert sonar.PRIVATE.read_bytes() == before
    assert not any(c[0] == "POST" for c in installation.calls)


def test_bootstrap_rejects_credentials_bound_to_another_instance(installation):
    """Changing the local endpoint cannot repurpose another instance's saved state."""
    state = {"url": "http://127.0.0.1:1", "admin_password": "previous-password", "token": "previous-token"}
    sonar.write_private(sonar.PRIVATE, json.dumps(state))
    with pytest.raises(ValueError, match="instance|URL|endpoint"):
        sonar.bootstrap()
    assert json.loads(sonar.PRIVATE.read_text()) == state
    assert not any(c[0] == "POST" for c in installation.calls)


def test_not_ready_or_forbidden_project_does_not_create_resources(installation):
    """Readiness and authorization failures must precede project/token mutations."""
    installation.status = "STARTING"
    with pytest.raises(ValueError, match="not ready"):
        sonar.bootstrap()
    assert not sonar.PRIVATE.exists()
    installation.status = "UP"
    account(installation)
    installation.forbidden_project = True
    with pytest.raises(HTTPError) as error:
        sonar.bootstrap()
    assert error.value.code == 403
    assert not any(c[0] == "POST" for c in installation.calls)


def test_api_never_follows_authenticated_redirects(installation):
    """Even a same-host redirect must not receive an Authorization header."""
    with pytest.raises(HTTPError) as error:
        sonar.api("/redirect", auth="Bearer test-only")
    assert error.value.code == 302
    assert [c[1] for c in installation.calls] == ["/redirect"]
    with pytest.raises(json.JSONDecodeError):
        sonar.api("/invalid-json")


def test_snapshot_paginates_and_uses_the_actual_analyzed_revision(installation, monkeypatch):
    """Evidence must identify server code, retain the Gate failure and include all issues."""
    account(installation)
    task_file()
    monkeypatch.setattr(sonar.subprocess, "check_output", lambda *_args, **_kwargs: "worktree-revision\n")
    sonar.snapshot("contract")
    payload = json.loads((sonar.ROOT / "evidence/sonar/contract-sonar.json").read_text())
    assert payload["revision"] == installation.revision
    assert payload["ce"]["task"]["analysisId"] == installation.analysis
    assert payload["gate"]["projectStatus"]["status"] == "ERROR"
    assert len(payload["issues"]) == 501
    pages = [c[4]["p"] for c in installation.calls if c[1] == "/api/issues/search"]
    assert pages == [["1"], ["2"]]
    text = json.dumps(payload)
    assert installation.password not in text and "test-only-token" not in text


@pytest.mark.parametrize("status", ["PENDING", "FAILED", "CANCELED"])
def test_snapshot_rejects_an_unprocessed_or_failed_task(installation, status):
    """A queued or failed compute task is never published as a processed result."""
    account(installation)
    task_file()
    installation.ce_status = status
    with pytest.raises(ValueError, match="processed"):
        sonar.snapshot("contract")
    assert not (sonar.ROOT / "evidence/sonar/contract-sonar.json").exists()


def test_snapshot_rejects_metrics_of_a_different_analysis(installation, monkeypatch):
    """Current project metrics cannot be attached to an older task's Gate."""
    account(installation)
    task_file()
    installation.latest_analysis = "other-analysis"
    monkeypatch.setattr(sonar.subprocess, "check_output", lambda *_args, **_kwargs: "worktree\n")
    with pytest.raises(ValueError, match="analysis|latest"):
        sonar.snapshot("contract")
    assert not (sonar.ROOT / "evidence/sonar/contract-sonar.json").exists()


def test_private_write_does_not_follow_a_symlink(tmp_path):
    """A misleading private-file link must not overwrite another file."""
    existing = tmp_path / "keep.json"
    existing.write_text("keep original")
    link = tmp_path / "private.json"
    link.symlink_to(existing)
    with pytest.raises((ValueError, OSError)):
        sonar.write_private(link, "new private data")
    assert existing.read_text() == "keep original"


def test_failed_private_publication_preserves_credentials(tmp_path, monkeypatch):
    """A disk/publication failure must leave the last recoverable state intact."""
    private = tmp_path / "private.json"
    private.write_text("original credentials")
    def fail_replace(*_args, **_kwargs):
        raise OSError("publication failed")
    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="publication"):
        sonar.write_private(private, "new credentials")
    assert private.read_text() == "original credentials"
    assert {p.name for p in tmp_path.iterdir()} == {"private.json"}


def test_main_does_not_print_private_http_response(installation, monkeypatch, capsys):
    """CLI failures must preserve a useful exit code without printing HTTP bodies."""
    account(installation)
    installation.password = "server-has-another-password"
    monkeypatch.setattr(sonar.sys, "argv", ["sonar.py", "bootstrap"])
    assert sonar.main() == 1
    output = capsys.readouterr()
    assert "server-has-another-password" not in output.err
    assert "private response" not in output.err

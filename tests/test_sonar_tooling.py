"""Prevent remote uploads, overwritten local credentials and stale scan evidence."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import sonar


@pytest.mark.parametrize("url", ["https://sonarcloud.io", "http://example.org:9000",
                               "http://admin:secret@127.0.0.1:9000", "http://127.0.0.1:9000/path"])
def test_scanner_rejects_nonlocal_or_credential_bearing_urls(monkeypatch, url):
    """Never send a project or token to an implicit remote destination."""
    monkeypatch.setenv("SONAR_HOST_URL", url)
    with pytest.raises(ValueError, match="SONAR_HOST_URL"):
        sonar.local_url()


def test_initialize_keeps_existing_private_configuration(tmp_path, monkeypatch):
    """Resuming the task must not rotate PostgreSQL's persisted password."""
    existing = tmp_path / ".env"
    existing.write_text("SONAR_DB_PASSWORD=existing-private-value\nSONAR_PORT=19001\n")
    monkeypatch.setattr(sonar, "INFRA", tmp_path)
    sonar.initialize()
    assert existing.read_text() == "SONAR_DB_PASSWORD=existing-private-value\nSONAR_PORT=19001\n"


def test_failed_scanner_does_not_publish_the_previous_analysis(tmp_path, monkeypatch):
    """A failed upload cannot be reported using a stale successful report-task."""
    task = tmp_path / ".scannerwork/report-task.txt"
    task.parent.mkdir()
    task.write_text("ceTaskId=previous-success\n")
    monkeypatch.setattr(sonar, "ROOT", tmp_path)
    monkeypatch.setattr(sonar, "install_scanner", lambda: None)
    monkeypatch.setattr(sonar, "credentials", lambda: {})
    monkeypatch.setattr(sonar, "check_reference", lambda *_args: None)
    monkeypatch.setattr(sonar, "token_auth", lambda: "Bearer test-only-token")
    monkeypatch.setattr(sonar, "local_url", lambda: "http://127.0.0.1:19000")
    monkeypatch.setattr(sonar, "api", lambda *_args, **_kwargs: {"status": "UP"})
    def run(command, **_kwargs):
        if "--with-mongo" in command:
            report = tmp_path / "evidence/sonar/coverage.xml"
            report.parent.mkdir(parents=True)
            report.write_text("<coverage />")
        elif command[:2] == ["npm", "run"]:
            report = tmp_path / "frontend/advanced-reader/coverage/lcov.info"
            report.parent.mkdir(parents=True)
            report.write_text("end_of_record")
        return SimpleNamespace(returncode=7 if command == [str(sonar.SCANNER)] else 0)
    monkeypatch.setattr(sonar.subprocess, "run", run)
    published = []
    monkeypatch.setattr(sonar, "snapshot", published.append)
    assert sonar.scan("final") == 7
    assert published == []

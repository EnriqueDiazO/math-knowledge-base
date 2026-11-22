"""Manage a dedicated local Community Build without printing private credentials."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import secrets
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler
from urllib.request import ProxyHandler
from urllib.request import Request
from urllib.request import build_opener
from urllib.request import urlopen
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra/sonarqube"
PRIVATE = INFRA / "access.local.json"
PROJECT = "mathmongo-local"
SCANNER_VERSION = "8.4.0.16527"
SCANNER_NAME = f"sonar-scanner-{SCANNER_VERSION}-linux-x64"
SCANNER = ROOT / ".tools" / SCANNER_NAME / "bin/sonar-scanner"
SCANNER_SHA256 = "2a28f118e2e9375dfd36eb27b803e1d37f93daba4db068aca6eef9853041bb24"


class NoRedirect(HTTPRedirectHandler):
    """Prevent authentication being forwarded away from the loopback service."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject redirects before credentials can leave the selected endpoint."""
        return None


def local_url() -> str:
    """Require a literal loopback URL; never fall back to SonarQube Cloud."""
    port = "19000"
    if (INFRA / ".env").exists():
        for line in (INFRA / ".env").read_text().splitlines():
            if line.startswith("SONAR_PORT="):
                port = line.partition("=")[2]
    url = os.environ.get("SONAR_HOST_URL", f"http://127.0.0.1:{port}").rstrip("/")
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("SONAR_HOST_URL must be http://127.0.0.1:PORT or http://[::1]:PORT")
    return url


def write_private(path: Path, content: str) -> None:
    """Publish mode-0600 secrets atomically, preserving recoverable state on failure."""
    if path.is_symlink():
        raise ValueError("Private configuration must not be a symlink")
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def credentials() -> dict:
    """Read local state without logging it."""
    state = json.loads(PRIVATE.read_text()) if PRIVATE.exists() else {}
    if state and state.get("url") != local_url():
        raise ValueError("Saved credentials belong to another instance URL")
    return state


def api(path: str, *, data: dict | None = None, auth: str | None = None) -> dict:
    """Call the supported local Web API using headers, not command-line secrets."""
    headers = {"Authorization": auth} if auth else {}
    request = Request(local_url() + path, headers=headers,
                      data=urlencode(data).encode() if data is not None else None)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else {}


def basic(password: str) -> str:
    """Encode admin credentials solely for a request header."""
    return "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()


def token_auth() -> str:
    """Prefer an explicit SONAR_TOKEN to a privately stored token."""
    token = os.environ.get("SONAR_TOKEN") or credentials().get("token")
    if not token:
        raise ValueError("No token: run make sonar-bootstrap or export SONAR_TOKEN")
    return "Bearer " + token


def compose(*arguments: str) -> None:
    """Run only this named Compose project; never remove volumes."""
    subprocess.run(["docker", "compose", "--project-directory", str(INFRA),
                    "-f", str(INFRA / "compose.yaml"), *arguments], check=True)


def initialize() -> None:
    """Prepare secrets without changing existing installations or credentials."""
    env_file = INFRA / ".env"
    if not env_file.exists():
        write_private(env_file, "SONAR_PORT=19000\nSONAR_DB_PASSWORD="
                      + secrets.token_urlsafe(36) + "\n")
    print("Private Compose configuration ready (existing files preserved).")


def install_scanner() -> None:
    """Install the pinned official native scanner in an isolated tools directory."""
    if SCANNER.exists():
        subprocess.run([str(SCANNER), "--version"], check=True)
        return
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("This pinned scanner installer supports Linux x86_64 only")
    filename = f"sonar-scanner-cli-{SCANNER_VERSION}-linux-x64.zip"
    download = ROOT / ".tools/downloads" / filename
    download.parent.mkdir(parents=True, exist_ok=True)
    if not download.exists():
        with urlopen("https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/"
                     + filename, timeout=120) as response:
            download.write_bytes(response.read())
    if hashlib.sha256(download.read_bytes()).hexdigest() != SCANNER_SHA256:
        raise ValueError("Scanner checksum mismatch; archive retained for inspection")
    with zipfile.ZipFile(download) as archive:
        archive.extractall(ROOT / ".tools")
        # zipfile does not preserve Unix modes, including jre/lib/jspawnhelper.
        # The pinned checksum above authenticates this exact local artifact.
        for entry in archive.infolist():
            mode = (entry.external_attr >> 16) & 0o777
            if mode:
                (ROOT / ".tools" / entry.filename).chmod(mode)
    subprocess.run([str(SCANNER), "--version"], check=True)


def up() -> None:
    """Enforce host requirements and a free port before starting our services."""
    initialize()
    subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True)
    if int(Path("/proc/sys/vm/max_map_count").read_text()) < 524288:
        raise ValueError("vm.max_map_count is below 524288; see docs/SONARQUBE.md")
    parsed = urlsplit(local_url())
    # An already responding instance must be identified by the operator, never reset.
    with socket.socket() as probe:
        if probe.connect_ex((parsed.hostname, parsed.port or 80)) == 0:
            raise ValueError("Port occupied: use sonar-status for this instance or choose a free SONAR_PORT")
    compose("up", "-d")
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            if api("/api/system/status").get("status") == "UP":
                print("SonarQube ready at " + local_url())
                return
        except (URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(3)
    raise ValueError("SonarQube did not become ready in 600 seconds; inspect Compose logs")


def bootstrap() -> None:
    """Initialize only an explicit new installation and preserve resumable access."""
    if api("/api/system/status").get("status") != "UP":
        raise ValueError("SonarQube is not ready")
    state = credentials()
    if not state:
        # Write the new password before changing it, so interruptions are recoverable.
        state = {"admin_password": secrets.token_urlsafe(36), "url": local_url()}
        write_private(PRIVATE, json.dumps(state, indent=2) + "\n")
    auth = basic(state["admin_password"])
    if not api("/api/authentication/validate", auth=auth).get("valid"):
        if not api("/api/authentication/validate", auth=basic("admin")).get("valid"):
            raise ValueError("Existing credentials are required; no account has been reset")
        api("/api/users/change_password", data={"login": "admin", "previousPassword": "admin",
                                              "password": state["admin_password"]}, auth=basic("admin"))
    try:
        api("/api/components/show?" + urlencode({"component": PROJECT}), auth=auth)
    except HTTPError as error:
        if error.code != 404:
            raise
        api("/api/projects/create", data={"project": PROJECT, "name": "MathMongo local"}, auth=auth)
    if not state.get("token"):
        result = api("/api/user_tokens/generate", data={"name": "mathmongo-local-" + secrets.token_hex(4),
                     "type": "PROJECT_ANALYSIS_TOKEN", "projectKey": PROJECT}, auth=auth)
        state["token"] = result["token"]
        write_private(PRIVATE, json.dumps(state, indent=2) + "\n")
    print("Project ready; admin password/token stored privately at infra/sonarqube/access.local.json")


def check_reference(auth: str, gate: dict | None = None) -> None:
    """Check, without changing, the effective reference pinned by this audit."""
    expected = json.loads((INFRA / "reference.json").read_text())
    if gate is None:
        gate = api("/api/qualitygates/project_status?projectKey=" + PROJECT, auth=auth)
    actual = gate["projectStatus"].get("period", {})
    if any(actual.get(key) != expected[key] for key in ("mode", "date")):
        raise ValueError("New-code reference changed; do not compare or publish this analysis")


def evidence_label(value: str) -> str:
    """Allow descriptive artifact labels without filesystem traversal or version changes."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value):
        raise argparse.ArgumentTypeError("Use a short filename-safe evidence label")
    return value


def snapshot(label: str) -> None:
    """Persist metrics, exact CE result, gate and issues after server processing."""
    evidence_label(label)
    # Project analysis tokens cannot read every administrative endpoint; use local admin
    # for evidence, while the scanner always receives the scoped analysis token.
    state = credentials()
    auth = basic(state["admin_password"]) if state.get("admin_password") else token_auth()
    task_file = ROOT / ".scannerwork/report-task.txt"
    task = dict(line.split("=", 1) for line in task_file.read_text().splitlines() if "=" in line)
    ce = api("/api/ce/task?" + urlencode({"id": task["ceTaskId"]}), auth=auth)
    if ce["task"]["status"] != "SUCCESS":
        raise ValueError("Server has not successfully processed this analysis")
    analyses = api("/api/project_analyses/search?" + urlencode({"project": PROJECT, "ps": 1}), auth=auth)
    latest = analyses["analyses"][0]
    if latest["key"] != ce["task"]["analysisId"]:
        raise ValueError("Task is not the latest analysis; current metrics cannot be attached")
    available = api("/api/metrics/search?ps=500", auth=auth)["metrics"]
    wanted = {"ncloc", "files", "coverage", "line_coverage", "lines_to_cover", "uncovered_lines",
              "duplicated_lines_density", "duplicated_blocks", "complexity", "cognitive_complexity",
              "bugs", "vulnerabilities", "code_smells", "security_hotspots", "sqale_index",
              "reliability_issues", "security_issues", "maintainability_issues"}
    keys = sorted(wanted.intersection(metric["key"] for metric in available))
    measures = api("/api/measures/component?" + urlencode({"component": PROJECT,
                   "metricKeys": ",".join(keys)}), auth=auth)
    gate = api("/api/qualitygates/project_status?" + urlencode({"analysisId": ce["task"]["analysisId"]}), auth=auth)
    check_reference(auth, gate)
    issues = []
    page = 1
    while True:
        result = api("/api/issues/search?" + urlencode({"componentKeys": PROJECT, "ps": 500, "p": page}), auth=auth)
        issues.extend(result["issues"])
        if len(issues) >= result["paging"]["total"]:
            break
        page += 1
    report = {"revision": latest.get("revision"),
              "worktree_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "ce": ce, "gate": gate, "measures": measures, "issues": issues,
              "profiles": api("/api/qualityprofiles/search?project=" + PROJECT, auth=auth),
              "hotspots": api("/api/hotspots/search?project=" + PROJECT + "&ps=100", auth=auth),
              "configuration_sha256": hashlib.sha256((ROOT / "sonar-project.properties").read_bytes()).hexdigest()}
    path = ROOT / "evidence/sonar" / f"{label}-sonar.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print("Evidence saved to " + str(path.relative_to(ROOT)))
    print("Quality Gate: " + gate["projectStatus"]["status"])


def check_generated_reports(python_report: Path, javascript_report: Path) -> None:
    """Reject malformed or empty coverage before any project upload."""
    try:
        root = ElementTree.parse(python_report).getroot()
    except ElementTree.ParseError:
        raise ValueError("Python coverage XML is malformed") from None
    if root.tag != "coverage" or int(root.get("lines-valid", "0")) <= 0:
        raise ValueError("Python coverage contains no executable lines")
    lcov = javascript_report.read_text()
    if not (lcov.startswith("SF:") or "\nSF:" in lcov) or "\nDA:" not in lcov or not lcov.rstrip().endswith("end_of_record"):
        raise ValueError("LCOV contains no valid source/line records")


def scan(label: str) -> int:
    """Generate coverage first, scan locally, then capture the processed result."""
    evidence_label(label)
    state = credentials()
    auth = basic(state["admin_password"]) if state.get("admin_password") else token_auth()
    if api("/api/system/status").get("status") != "UP":
        raise ValueError("SonarQube is not ready")
    check_reference(auth)
    python_report = ROOT / "evidence/sonar/coverage.xml"
    javascript_report = ROOT / "frontend/advanced-reader/coverage/lcov.info"
    for report in (python_report, javascript_report):
        report.unlink(missing_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/quality.py"), "--with-mongo", "--with-study-browser"], cwd=ROOT, check=True)
    subprocess.run(["npm", "run", "test:coverage"], cwd=ROOT / "frontend/advanced-reader", check=True)
    check_generated_reports(python_report, javascript_report)
    install_scanner()
    environment = dict(os.environ, SONAR_HOST_URL=local_url(), SONAR_TOKEN=token_auth().removeprefix("Bearer "))
    report_task = ROOT / ".scannerwork/report-task.txt"
    report_task.unlink(missing_ok=True)
    result = subprocess.run([str(SCANNER)], cwd=ROOT, env=environment, check=False)
    if not report_task.exists():
        print("Scanner produced no analysis task; no snapshot was published.", file=sys.stderr)
        return result.returncode or 1
    snapshot(label)
    return result.returncode


def main() -> int:
    """Expose deliberately small, explicit lifecycle commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "install-scanner", "up", "bootstrap", "scan", "snapshot", "status", "down"])
    parser.add_argument("--label", default="latest", type=evidence_label)
    args = parser.parse_args()
    try:
        local_url()
        if args.command == "scan":
            return scan(args.label)
        if args.command == "snapshot":
            snapshot(args.label)
        elif args.command == "status":
            print(json.dumps(api("/api/system/status")))
        elif args.command == "down":
            compose("down")
        else:
            {"init": initialize, "install-scanner": install_scanner,
             "up": up, "bootstrap": bootstrap}[args.command]()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        # HTTP responses may echo credentials; never print response bodies or requests.
        print(f"Sonar operation failed ({type(error).__name__}). See docs/SONARQUBE.md.", file=sys.stderr)
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

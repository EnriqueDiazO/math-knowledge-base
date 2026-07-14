"""Real-process E2E for the unified S5B.1 local runtime supervisor.

It validates the two real services, same-origin metadata/PDF delivery, ownership
semantics, signals, ports, Mongo isolation, and XDG cleanup. A Google Chrome
Playwright probe also verifies the painted PDF.js canvas/text layer and the
Streamlit Reading Space readiness/link flow.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler
from urllib.request import Request
from urllib.request import build_opener

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from advanced_reader_test_support import synthetic_text_pdf  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from mathmongo.reading_space.indexes import ReadingSpaceIndexManager  # noqa: E402
from mathmongo.source_catalog.models import Reference  # noqa: E402
from mathmongo.source_catalog.models import Source  # noqa: E402
from mathmongo.source_documents.service import DocumentOperationStatus  # noqa: E402
from mathmongo.source_documents.service import SourceDocumentService  # noqa: E402
from mathmongo.source_documents.storage import SourceDocumentBlobStore  # noqa: E402

PYTHON = REPOSITORY_ROOT / "mathdbmongo" / "bin" / "python"
MONGOD = shutil.which("mongod")
NODE = shutil.which("node")
CHROME = shutil.which("google-chrome")
BROWSER_PROBE = REPOSITORY_ROOT / "tests" / "local_runtime_browser_probe.mjs"
LOOPBACK = "127.0.0.1"
DEFAULT_PORTS = frozenset({8501, 8766})
ADVANCED_HEALTH_PATH = "/api/advanced-reader/health"
STREAMLIT_HEALTH_PATH = "/_stcore/health"
HTTP_OPENER = build_opener(ProxyHandler({}))
MONGO_URI_PATTERN = re.compile(r"mongodb(?:\+srv)?://[^\s'\"<>]+", re.IGNORECASE)


@dataclass
class OwnedProcess:
    """One process group created by this harness, never by the user."""

    label: str
    process: subprocess.Popen[str]
    process_group: int
    ports: tuple[int, ...]
    stdout: str = ""
    stderr: str = ""


def _free_port(used: set[int]) -> int:
    for _attempt in range(100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((LOOPBACK, 0))
            port = int(listener.getsockname()[1])
        if port not in used and port not in DEFAULT_PORTS:
            used.add(port)
            return port
    raise RuntimeError("Could not allocate a unique non-default loopback port")


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.15)
        return probe.connect_ex((LOOPBACK, port)) == 0


def _assert_port_free(port: int, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _port_open(port):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind((LOOPBACK, port))
                return
            except OSError:
                pass
        time.sleep(0.05)
    raise RuntimeError(f"Temporary loopback port {port} was not released")


def _base_url(port: int) -> str:
    return f"http://{LOOPBACK}:{port}"


def _read_response(request: str | Request, *, timeout: float = 0.75) -> tuple[int, bytes, dict]:
    with HTTP_OPENER.open(request, timeout=timeout) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise RuntimeError("Local runtime HTTP response exceeded the E2E bound")
        headers = {name.casefold(): value for name, value in response.headers.items()}
        return response.status, payload, headers


def _json_response(url: str, *, timeout: float = 0.75) -> tuple[int, dict[str, object]]:
    status, payload, _headers = _read_response(url, timeout=timeout)
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("Local runtime endpoint returned a non-object JSON payload")
    return status, decoded


def _process_exited(owned: OwnedProcess | None) -> bool:
    return owned is not None and owned.process.poll() is not None


def _safe_tail(owned: OwnedProcess, temporary_root: Path, *, lines: int = 12) -> str:
    text = "\n".join((owned.stdout + "\n" + owned.stderr).splitlines()[-lines:])
    text = MONGO_URI_PATTERN.sub("<redacted MongoDB URI>", text)
    text = text.replace(str(temporary_root), "<temporary runtime>")
    return text[-2000:]


def _wait_advanced_reader(
    port: int,
    database_name: str,
    *,
    process: OwnedProcess | None,
    temporary_root: Path,
    timeout: float = 25.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    url = _base_url(port) + ADVANCED_HEALTH_PATH
    while time.monotonic() < deadline:
        if _process_exited(process):
            assert process is not None
            _collect(process, timeout=0.1)
            raise RuntimeError(
                f"{process.label} exited before health: {_safe_tail(process, temporary_root)}"
            )
        try:
            status, payload = _json_response(url)
            if (
                status == 200
                and payload.get("status") == "ok"
                and payload.get("service") == "mathmongo-advanced-reader"
                and payload.get("database") == database_name
                and payload.get("frontend_ready") is True
            ):
                return payload
        except (OSError, URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(0.08)
    raise RuntimeError(f"Advanced Reader health did not become ready on port {port}")


def _wait_streamlit(
    port: int,
    *,
    process: OwnedProcess,
    temporary_root: Path,
    timeout: float = 45.0,
) -> str:
    deadline = time.monotonic() + timeout
    url = _base_url(port) + STREAMLIT_HEALTH_PATH
    while time.monotonic() < deadline:
        if _process_exited(process):
            _collect(process, timeout=0.1)
            raise RuntimeError(
                f"{process.label} exited before Streamlit health: "
                f"{_safe_tail(process, temporary_root)}"
            )
        try:
            status, payload, _headers = _read_response(url)
            body = payload.decode("utf-8", errors="replace").strip()
            if status == 200 and body.casefold() == "ok":
                return body
        except (OSError, URLError, HTTPError, TimeoutError):
            pass
        time.sleep(0.08)
    raise RuntimeError(f"Streamlit health did not become ready on port {port}")


def _wait_for_exit(owned: OwnedProcess, *, timeout: float) -> int:
    _collect(owned, timeout=timeout)
    return int(owned.process.returncode or 0)


def _collect(owned: OwnedProcess, *, timeout: float) -> None:
    try:
        stdout, stderr = owned.process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        raise
    owned.stdout = stdout or owned.stdout
    owned.stderr = stderr or owned.stderr


def _launch(
    label: str,
    command: list[str],
    *,
    environment: dict[str, str],
    ports: tuple[int, ...],
    capture_output: bool = True,
) -> OwnedProcess:
    if not command or any(not isinstance(item, str) for item in command):
        raise ValueError("E2E child commands must be non-empty argument lists")
    process = subprocess.Popen(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture_output else subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    return OwnedProcess(label, process, process.pid, ports)


def _mongod_command(db_path: Path, port: int) -> list[str]:
    if MONGOD is None:
        raise RuntimeError("mongod is required for isolated local-runtime E2E")
    return [
        MONGOD,
        "--dbpath",
        str(db_path),
        "--bind_ip",
        LOOPBACK,
        "--port",
        str(port),
        "--nounixsocket",
        "--quiet",
        "--setParameter",
        "diagnosticDataCollectionEnabled=false",
    ]


def _wait_mongo(
    client: MongoClient,
    process: OwnedProcess,
    temporary_root: Path,
    *,
    timeout: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.process.poll() is not None:
            _collect(process, timeout=0.1)
            raise RuntimeError(
                "Ephemeral mongod exited before ping: " f"{_safe_tail(process, temporary_root)}"
            )
        try:
            client.admin.command("ping")
            return
        except PyMongoError:
            time.sleep(0.08)
    raise RuntimeError("Ephemeral mongod did not become ready")


def _supervisor_command(database_name: str, streamlit_port: int, reader_port: int) -> list[str]:
    return [
        str(PYTHON),
        "-m",
        "mathmongo.local_runtime",
        "--database",
        database_name,
        "--streamlit-host",
        LOOPBACK,
        "--streamlit-port",
        str(streamlit_port),
        "--advanced-reader-host",
        LOOPBACK,
        "--advanced-reader-port",
        str(reader_port),
        "--log-level",
        "info",
    ]


def _reader_command(database_name: str, reader_port: int) -> list[str]:
    return [
        str(PYTHON),
        "-m",
        "mathmongo.advanced_reader",
        "--host",
        LOOPBACK,
        "--port",
        str(reader_port),
        "--database",
        database_name,
        "--log-level",
        "warning",
    ]


def _interrupt_supervisor(owned: OwnedProcess) -> int:
    if owned.process.poll() is not None:
        _collect(owned, timeout=0.1)
        raise RuntimeError(f"{owned.label} exited before the E2E SIGINT")
    owned.process.send_signal(signal.SIGINT)
    try:
        return _wait_for_exit(owned, timeout=20.0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{owned.label} did not finish its SIGINT shutdown") from exc


def _stop_direct_reader(owned: OwnedProcess) -> int:
    if owned.process.poll() is None:
        owned.process.send_signal(signal.SIGINT)
    try:
        return _wait_for_exit(owned, timeout=15.0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{owned.label} did not stop after SIGINT") from exc


def _force_cleanup(owned: OwnedProcess) -> None:
    if owned.process.poll() is None or any(_port_open(port) for port in owned.ports):
        try:
            os.killpg(owned.process_group, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            _collect(owned, timeout=5.0)
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(owned.process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        _collect(owned, timeout=5.0)
    except subprocess.TimeoutExpired:
        pass


def _assert_sigint_exit(label: str, return_code: int) -> None:
    if return_code != 130:
        raise RuntimeError(f"{label} returned {return_code} after SIGINT instead of 130")


def _validate_document_http(reader_port: int, document_id: str, pdf_size: int) -> dict[str, object]:
    base_url = _base_url(reader_port)
    status, metadata = _json_response(
        f"{base_url}/api/advanced-reader/documents/{document_id}",
        timeout=2.0,
    )
    if (
        status != 200
        or metadata.get("document_id") != document_id
        or metadata.get("kind") != "pdf"
        or metadata.get("integrity") != "ok"
        or not isinstance(metadata.get("version"), dict)
        or metadata["version"].get("size_bytes") != pdf_size
    ):
        raise RuntimeError("Advanced Reader metadata did not resolve the temporary PDF")

    reader_status, reader_html, _reader_headers = _read_response(
        f"{base_url}/reader?{urlencode({'document_id': document_id})}",
        timeout=2.0,
    )
    if reader_status != 200 or b'<div id="root"></div>' not in reader_html:
        raise RuntimeError("Advanced Reader same-origin reader entry did not load")

    pdf_request = Request(
        f"{base_url}/api/advanced-reader/documents/{document_id}/pdf",
        headers={"Range": "bytes=0-1023"},
    )
    pdf_status, pdf_prefix, pdf_headers = _read_response(pdf_request, timeout=2.0)
    if (
        pdf_status != 206
        or not pdf_prefix.startswith(b"%PDF-")
        or len(pdf_prefix) != min(1024, pdf_size)
        or pdf_headers.get("accept-ranges", "").casefold() != "bytes"
    ):
        raise RuntimeError("Advanced Reader did not serve the temporary PDF with byte ranges")
    return {
        "metadata": True,
        "reader_entry": True,
        "pdf_range": True,
    }


def _run_browser_probe(
    *,
    document_id: str,
    document_title: str,
    streamlit_port: int,
    reader_port: int,
    environment: dict[str, str],
    owned_processes: list[OwnedProcess],
) -> dict[str, object]:
    if NODE is None or CHROME is None or not BROWSER_PROBE.is_file():
        raise RuntimeError("Node, Google Chrome, and the browser probe are required")
    browser_environment = dict(environment)
    browser_environment.update(
        {
            "MATHMONGO_CHROME_PATH": CHROME,
            "MATHMONGO_LOCAL_RUNTIME_DOCUMENT_ID": document_id,
            "MATHMONGO_LOCAL_RUNTIME_DOCUMENT_TITLE": document_title,
            "MATHMONGO_LOCAL_RUNTIME_READER_URL": f"{_base_url(reader_port)}/",
            "MATHMONGO_LOCAL_RUNTIME_STREAMLIT_URL": f"{_base_url(streamlit_port)}/",
        }
    )
    probe = _launch(
        "local-runtime-browser-probe",
        [NODE, str(BROWSER_PROBE)],
        environment=browser_environment,
        ports=(),
    )
    owned_processes.append(probe)
    try:
        return_code = _wait_for_exit(probe, timeout=100.0)
    except subprocess.TimeoutExpired as exc:
        _force_cleanup(probe)
        raise RuntimeError("Local runtime browser probe timed out") from exc
    output_lines = [line for line in probe.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise RuntimeError("Local runtime browser probe emitted no JSON result")
    try:
        payload = json.loads(output_lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Local runtime browser probe emitted invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Local runtime browser probe result was not an object")
    reader = payload.get("reader")
    streamlit = payload.get("streamlit")
    if (
        return_code != 0
        or payload.get("ok") is not True
        or not isinstance(reader, dict)
        or reader.get("pdfjs_rendered") is not True
        or not isinstance(streamlit, dict)
        or streamlit.get("validated") is not True
    ):
        error = str(payload.get("error") or "browser_validation_failed")[:240]
        raise RuntimeError(f"Local runtime browser probe failed: {error}")
    return payload


def _scenario_start_both(
    *,
    database_name: str,
    document_id: str,
    document_title: str,
    pdf_size: int,
    streamlit_port: int,
    reader_port: int,
    environment: dict[str, str],
    temporary_root: Path,
    owned_processes: list[OwnedProcess],
) -> dict[str, object]:
    supervisor = _launch(
        "local-runtime-start-both",
        _supervisor_command(database_name, streamlit_port, reader_port),
        environment=environment,
        ports=(streamlit_port, reader_port),
    )
    owned_processes.append(supervisor)
    reader_health = _wait_advanced_reader(
        reader_port,
        database_name,
        process=supervisor,
        temporary_root=temporary_root,
    )
    streamlit_health = _wait_streamlit(
        streamlit_port,
        process=supervisor,
        temporary_root=temporary_root,
    )
    document_http = _validate_document_http(reader_port, document_id, pdf_size)
    browser = _run_browser_probe(
        document_id=document_id,
        document_title=document_title,
        streamlit_port=streamlit_port,
        reader_port=reader_port,
        environment=environment,
        owned_processes=owned_processes,
    )
    return_code = _interrupt_supervisor(supervisor)
    _assert_sigint_exit(supervisor.label, return_code)
    _assert_port_free(streamlit_port)
    _assert_port_free(reader_port)
    return {
        "reader_health": reader_health.get("database") == database_name,
        "streamlit_health": streamlit_health == "ok",
        **document_http,
        "browser": browser,
        "sigint_exit_code": return_code,
        "streamlit_port_released": True,
        "reader_port_released": True,
    }


def _scenario_reuse_reader(
    *,
    database_name: str,
    document_id: str,
    streamlit_port: int,
    reader_port: int,
    environment: dict[str, str],
    temporary_root: Path,
    owned_processes: list[OwnedProcess],
) -> dict[str, object]:
    reader = _launch(
        "compatible-reader",
        _reader_command(database_name, reader_port),
        environment=environment,
        ports=(reader_port,),
    )
    owned_processes.append(reader)
    _wait_advanced_reader(
        reader_port,
        database_name,
        process=reader,
        temporary_root=temporary_root,
    )
    original_reader_pid = reader.process.pid

    supervisor = _launch(
        "local-runtime-reuse-reader",
        _supervisor_command(database_name, streamlit_port, reader_port),
        environment=environment,
        ports=(streamlit_port,),
    )
    owned_processes.append(supervisor)
    _wait_streamlit(
        streamlit_port,
        process=supervisor,
        temporary_root=temporary_root,
    )
    _wait_advanced_reader(
        reader_port,
        database_name,
        process=supervisor,
        temporary_root=temporary_root,
    )
    metadata_status, metadata = _json_response(
        f"{_base_url(reader_port)}/api/advanced-reader/documents/{document_id}",
        timeout=2.0,
    )
    if metadata_status != 200 or metadata.get("document_id") != document_id:
        raise RuntimeError("Reused Advanced Reader did not expose the expected database")

    return_code = _interrupt_supervisor(supervisor)
    _assert_sigint_exit(supervisor.label, return_code)
    _assert_port_free(streamlit_port)
    if reader.process.poll() is not None or reader.process.pid != original_reader_pid:
        raise RuntimeError("Supervisor terminated the reused Advanced Reader")
    _wait_advanced_reader(
        reader_port,
        database_name,
        process=reader,
        temporary_root=temporary_root,
    )
    output = (supervisor.stdout + supervisor.stderr).casefold()
    reuse_marker = "reused" in output or "reutiliz" in output
    if not reuse_marker:
        raise RuntimeError("Supervisor did not label the compatible Reader as reused")

    reader_return_code = _stop_direct_reader(reader)
    _assert_port_free(reader_port)
    return {
        "reader_reused": True,
        "reuse_output_marker": True,
        "supervisor_sigint_exit_code": return_code,
        "reused_reader_survived": True,
        "streamlit_port_released": True,
        "reader_stopped_by_harness": True,
        "reader_exit_code": reader_return_code,
    }


def _scenario_database_mismatch(
    *,
    expected_database: str,
    wrong_database: str,
    streamlit_port: int,
    reader_port: int,
    environment: dict[str, str],
    temporary_root: Path,
    owned_processes: list[OwnedProcess],
) -> dict[str, object]:
    wrong_reader = _launch(
        "wrong-database-reader",
        _reader_command(wrong_database, reader_port),
        environment=environment,
        ports=(reader_port,),
    )
    owned_processes.append(wrong_reader)
    _wait_advanced_reader(
        reader_port,
        wrong_database,
        process=wrong_reader,
        temporary_root=temporary_root,
    )

    supervisor = _launch(
        "local-runtime-database-mismatch",
        _supervisor_command(expected_database, streamlit_port, reader_port),
        environment=environment,
        ports=(streamlit_port,),
    )
    owned_processes.append(supervisor)
    try:
        return_code = _wait_for_exit(supervisor, timeout=20.0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Database-mismatch supervisor did not block promptly") from exc
    if return_code == 0:
        raise RuntimeError("Database-mismatch supervisor returned success")
    if _port_open(streamlit_port):
        raise RuntimeError("Streamlit started despite an Advanced Reader database mismatch")
    if wrong_reader.process.poll() is not None:
        raise RuntimeError("Supervisor terminated the wrong-database Reader")
    _wait_advanced_reader(
        reader_port,
        wrong_database,
        process=wrong_reader,
        temporary_root=temporary_root,
    )
    output = supervisor.stdout + supervisor.stderr
    folded_output = output.casefold()
    if (
        expected_database not in output
        or wrong_database not in output
        or "advanced reader" not in folded_output
        or "ss -ltnp" not in folded_output
    ):
        raise RuntimeError("Database mismatch did not produce the actionable safe diagnostic")

    reader_return_code = _stop_direct_reader(wrong_reader)
    _assert_port_free(reader_port)
    _assert_port_free(streamlit_port)
    return {
        "blocked": True,
        "nonzero_exit_code": return_code,
        "streamlit_not_started": True,
        "wrong_reader_survived": True,
        "actionable_output": True,
        "reader_exit_code": reader_return_code,
    }


def _assert_safe_output(
    owned_processes: list[OwnedProcess],
    temporary_root: Path,
    mongo_uri: str,
) -> None:
    forbidden = (mongo_uri, str(temporary_root))
    for owned in owned_processes:
        output = owned.stdout + owned.stderr
        if any(value and value in output for value in forbidden):
            raise RuntimeError(f"{owned.label} exposed a URI or temporary XDG/HOME path")


def main() -> int:
    """Run the three real-process scenarios and emit one machine-readable result."""
    if not PYTHON.is_file():
        raise RuntimeError("The project virtualenv Python is required for local-runtime E2E")
    if MONGOD is None:
        raise RuntimeError("mongod is required for isolated local-runtime E2E")
    if NODE is None or CHROME is None or not BROWSER_PROBE.is_file():
        raise RuntimeError("Node, Google Chrome, and the browser probe are required")
    if importlib.util.find_spec("mathmongo.local_runtime") is None:
        raise RuntimeError("mathmongo.local_runtime is not implemented yet")

    token = os.urandom(8).hex()
    database_name = f"s5b1_e2e_{token}"
    wrong_database = f"s5b1_wrong_{token}"
    used_ports: set[int] = set(DEFAULT_PORTS)
    ports = {
        "mongo": _free_port(used_ports),
        "start_streamlit": _free_port(used_ports),
        "start_reader": _free_port(used_ports),
        "reuse_streamlit": _free_port(used_ports),
        "reuse_reader": _free_port(used_ports),
        "mismatch_streamlit": _free_port(used_ports),
        "mismatch_reader": _free_port(used_ports),
    }
    owned_processes: list[OwnedProcess] = []
    mongo_process: OwnedProcess | None = None
    client: MongoClient | None = None
    mongo_ready = False
    temporary_root: Path | None = None
    result: dict[str, object] | None = None
    cleanup_errors: list[str] = []

    try:
        with tempfile.TemporaryDirectory(prefix="mathmongo-local-runtime-e2e-") as temporary:
            temporary_root = Path(temporary)
            home = temporary_root / "home"
            xdg_data = temporary_root / "xdg-data"
            xdg_config = temporary_root / "xdg-config"
            xdg_cache = temporary_root / "xdg-cache"
            xdg_state = temporary_root / "xdg-state"
            xdg_runtime = temporary_root / "xdg-runtime"
            child_tmp = temporary_root / "tmp"
            mongo_data = temporary_root / "mongo-data"
            for directory in (
                home,
                xdg_data,
                xdg_config,
                xdg_cache,
                xdg_state,
                xdg_runtime,
                child_tmp,
                mongo_data,
            ):
                directory.mkdir(mode=0o700)

            mongo_uri = f"mongodb://{LOOPBACK}:{ports['mongo']}"
            environment = os.environ.copy()
            for name in (
                "DB_NAME",
                "MATHMONGO_E2E_MONGO_URI",
                "MONGO_DB",
                "MONGO_URI",
                "MONGODB_DB",
                "MONGODB_URI",
                "XDG_RUNTIME_DIR",
            ):
                environment.pop(name, None)
            environment.update(
                {
                    "HOME": str(home),
                    "XDG_DATA_HOME": str(xdg_data),
                    "XDG_CONFIG_HOME": str(xdg_config),
                    "XDG_CACHE_HOME": str(xdg_cache),
                    "XDG_STATE_HOME": str(xdg_state),
                    "XDG_RUNTIME_DIR": str(xdg_runtime),
                    "TMPDIR": str(child_tmp),
                    "MONGODB_URI": mongo_uri,
                    "MONGO_URI": mongo_uri,
                    "NO_PROXY": "127.0.0.1,localhost",
                    "no_proxy": "127.0.0.1,localhost",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "STREAMLIT_SERVER_HEADLESS": "true",
                    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
                }
            )

            mongo_process = _launch(
                "ephemeral-mongod",
                _mongod_command(mongo_data, ports["mongo"]),
                environment=environment,
                ports=(ports["mongo"],),
                capture_output=False,
            )
            owned_processes.append(mongo_process)
            client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=300,
                connectTimeoutMS=300,
            )
            try:
                _wait_mongo(client, mongo_process, temporary_root)
                mongo_ready = True
                database = client[database_name]
                source = Source(name=f"S5B.1 runtime source {token}")
                reference = Reference(
                    source_ids=[source.source_id],
                    title="S5B.1 runtime reference",
                )
                database["sources"].insert_one(source.model_dump(mode="python"))
                database["references"].insert_one(reference.model_dump(mode="python"))
                reading_indexes = ReadingSpaceIndexManager(database).apply()
                if not reading_indexes.initialized:
                    raise RuntimeError("Temporary Reading Space indexes were not initialized")
                synthetic_pdf = synthetic_text_pdf(padding_bytes=64_000)
                document_service = SourceDocumentService(
                    database,
                    storage=SourceDocumentBlobStore(xdg_data / "mathmongo"),
                )
                created = document_service.create_pdf_document(
                    source_id=source.source_id,
                    reference_id=reference.reference_id,
                    pdf_bytes=synthetic_pdf,
                    original_filename="s5b1-runtime.pdf",
                    title="S5B.1 unified local runtime PDF",
                )
                if created.status != DocumentOperationStatus.CREATED or created.value is None:
                    raise RuntimeError(f"Temporary PDF setup failed: {created.status.value}")
                document = created.value

                start_both = _scenario_start_both(
                    database_name=database_name,
                    document_id=document.document_id,
                    document_title=document.title,
                    pdf_size=len(synthetic_pdf),
                    streamlit_port=ports["start_streamlit"],
                    reader_port=ports["start_reader"],
                    environment=environment,
                    temporary_root=temporary_root,
                    owned_processes=owned_processes,
                )
                reuse_reader = _scenario_reuse_reader(
                    database_name=database_name,
                    document_id=document.document_id,
                    streamlit_port=ports["reuse_streamlit"],
                    reader_port=ports["reuse_reader"],
                    environment=environment,
                    temporary_root=temporary_root,
                    owned_processes=owned_processes,
                )
                mismatch = _scenario_database_mismatch(
                    expected_database=database_name,
                    wrong_database=wrong_database,
                    streamlit_port=ports["mismatch_streamlit"],
                    reader_port=ports["mismatch_reader"],
                    environment=environment,
                    temporary_root=temporary_root,
                    owned_processes=owned_processes,
                )
                isolated_databases = set(client.list_database_names())
                if database_name not in isolated_databases or "MathV0" not in isolated_databases:
                    raise RuntimeError(
                        "Streamlit databases were not confined to the ephemeral mongod"
                    )
                _assert_safe_output(owned_processes, temporary_root, mongo_uri)
                result = {
                    "ok": True,
                    "database_is_temporary": True,
                    "mongo": {
                        "ephemeral_instance": True,
                        "port": ports["mongo"],
                        "secondary_mathv0_isolated": True,
                    },
                    "ports": ports,
                    "default_ports_untouched": not (set(ports.values()) & DEFAULT_PORTS),
                    "start_both": start_both,
                    "reuse_reader": reuse_reader,
                    "database_mismatch": mismatch,
                    "browser": start_both["browser"],
                }
            finally:
                for owned in reversed(owned_processes):
                    if owned is mongo_process:
                        continue
                    try:
                        _force_cleanup(owned)
                    except Exception:  # pragma: no cover - defensive E2E cleanup
                        cleanup_errors.append(f"process_cleanup_failed:{owned.label}")
                if client is not None and mongo_ready:
                    try:
                        temporary_databases = (database_name, wrong_database, "MathV0")
                        for name in temporary_databases:
                            client.drop_database(name)
                        remaining = set(client.list_database_names())
                        for name in temporary_databases:
                            if name in remaining:
                                cleanup_errors.append(f"database_remained:{name}")
                    except PyMongoError:  # pragma: no cover - defensive E2E cleanup
                        cleanup_errors.append("database_cleanup_failed")
                if client is not None:
                    client.close()
                if mongo_process is not None:
                    try:
                        _force_cleanup(mongo_process)
                    except Exception:  # pragma: no cover - defensive E2E cleanup
                        cleanup_errors.append("process_cleanup_failed:ephemeral-mongod")
                for port in ports.values():
                    try:
                        _assert_port_free(port)
                    except Exception:  # pragma: no cover - defensive E2E cleanup
                        cleanup_errors.append(f"port_remained:{port}")
    finally:
        if temporary_root is not None and temporary_root.exists():
            cleanup_errors.append("temporary_xdg_home_remained")
        if cleanup_errors:
            raise RuntimeError("Local runtime E2E cleanup failed: " + ", ".join(cleanup_errors))

    if result is None:
        raise RuntimeError("Local runtime E2E did not produce a result")
    result["cleanup"] = {
        "databases_removed": True,
        "ephemeral_mongo_data_removed": True,
        "ports_released": True,
        "temporary_xdg_home_removed": True,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

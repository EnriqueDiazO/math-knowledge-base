"""One-shot real-Chrome S5A validation using only temporary Mongo/XDG state."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler
from urllib.request import build_opener

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT_VALUE = os.environ.get("MATHMONGO_E2E_PACKAGE_ROOT")
PACKAGE_ROOT = Path(PACKAGE_ROOT_VALUE).resolve() if PACKAGE_ROOT_VALUE else None
sys.path.insert(0, str(PACKAGE_ROOT or REPOSITORY_ROOT))

from advanced_reader_test_support import synthetic_text_pdf  # noqa: E402
from pymongo import MongoClient  # noqa: E402

import mathmongo  # noqa: E402
from mathmongo.advanced_reader.streamlit_link import build_advanced_reader_url  # noqa: E402
from mathmongo.document_page_maps.indexes import DocumentPageMapIndexManager  # noqa: E402
from mathmongo.document_page_maps.service import DocumentPageMapService  # noqa: E402
from mathmongo.document_page_maps.service import PageMapOperationStatus  # noqa: E402
from mathmongo.reading_space.indexes import ReadingSpaceIndexManager  # noqa: E402
from mathmongo.reading_space.service import ReadingOperationStatus  # noqa: E402
from mathmongo.reading_space.service import ReadingSpaceService  # noqa: E402
from mathmongo.source_catalog.models import Reference  # noqa: E402
from mathmongo.source_catalog.models import Source  # noqa: E402
from mathmongo.source_documents.service import DocumentOperationStatus  # noqa: E402
from mathmongo.source_documents.service import SourceDocumentService  # noqa: E402

MONGO_URI = os.environ.get("MATHMONGO_E2E_MONGO_URI", "mongodb://127.0.0.1:27017")
CHROME_PATH = os.environ.get("MATHMONGO_CHROME_PATH", "/usr/bin/google-chrome")
PYTHON = REPOSITORY_ROOT / "mathdbmongo" / "bin" / "python"
FRONTEND_ROOT = REPOSITORY_ROOT / "frontend" / "advanced-reader"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_health(base_url: str, process: subprocess.Popen[str]) -> dict[str, object]:
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 20
    url = f"{base_url}/api/advanced-reader/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Advanced Reader exited before health became ready")
        try:
            with opener.open(url, timeout=0.5) as response:
                payload = json.loads(response.read(4097).decode("utf-8"))
            if (
                response.status == 200
                and payload.get("status") == "ok"
                and payload.get("service") == "mathmongo-advanced-reader"
                and payload.get("frontend_ready") is True
            ):
                return payload
        except (OSError, URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.1)
    raise RuntimeError("Advanced Reader health did not become ready")


def _browser_summary(output: str) -> dict[str, object]:
    for line in reversed(output.splitlines()):
        if line.startswith("{"):
            payload = json.loads(line)
            if isinstance(payload, dict):
                return payload
    raise RuntimeError("The real-browser runner did not emit its JSON summary")


def _stop_server(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
    try:
        return process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.communicate(timeout=5)


def main() -> int:
    """Create, exercise, and fully remove one isolated S5A runtime fixture."""
    if not PYTHON.is_file() or not Path(CHROME_PATH).is_file():
        raise RuntimeError("Project Python and system Chrome are required for S5A E2E")
    package_origin = Path(mathmongo.__file__).resolve()
    if PACKAGE_ROOT is not None and not package_origin.is_relative_to(PACKAGE_ROOT):
        raise RuntimeError("Offline E2E did not import MathMongo from the installed wheel")

    token = os.urandom(8).hex()
    database_name = f"s5a_e2e_{token}"
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    client.admin.command("ping")
    database = client[database_name]
    process: subprocess.Popen[str] | None = None
    server_stdout = ""
    server_stderr = ""
    temporary_root: Path | None = None
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    managed_environment_keys = ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")
    original_environment = {key: os.environ.get(key) for key in managed_environment_keys}

    try:
        with tempfile.TemporaryDirectory(prefix="mathmongo-s5a-e2e-") as temporary:
            temporary_root = Path(temporary)
            home = temporary_root / "home"
            xdg_data = temporary_root / "xdg-data"
            xdg_config = temporary_root / "xdg-config"
            xdg_cache = temporary_root / "xdg-cache"
            home.mkdir(mode=0o700)
            environment = os.environ.copy()
            environment.update(
                {
                    "HOME": str(home),
                    "XDG_DATA_HOME": str(xdg_data),
                    "XDG_CONFIG_HOME": str(xdg_config),
                    "XDG_CACHE_HOME": str(xdg_cache),
                    "MATHMONGO_ADVANCED_READER_ENABLED": "1",
                    "MATHMONGO_ADVANCED_READER_URL": base_url,
                    "NO_PROXY": "127.0.0.1,localhost",
                    "no_proxy": "127.0.0.1,localhost",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            if PACKAGE_ROOT is not None:
                environment["PYTHONPATH"] = str(PACKAGE_ROOT)
            os.environ.update({key: environment[key] for key in managed_environment_keys})

            source = Source(name=f"S5A synthetic source {token}")
            reference = Reference(
                source_ids=[source.source_id],
                title="S5A synthetic reference",
            )
            database["sources"].insert_one(source.model_dump(mode="python"))
            database["references"].insert_one(reference.model_dump(mode="python"))

            document_service = SourceDocumentService(database)
            synthetic_pdf = synthetic_text_pdf()
            created = document_service.create_pdf_document(
                source_id=source.source_id,
                reference_id=reference.reference_id,
                pdf_bytes=synthetic_pdf,
                original_filename="s5a-synthetic.pdf",
                title="S5A synthetic Advanced Reader PDF",
            )
            if created.status != DocumentOperationStatus.CREATED or created.value is None:
                raise RuntimeError(f"Synthetic Document setup failed: {created.status.value}")
            document = created.value

            ReadingSpaceIndexManager(database).apply()
            reading_service = ReadingSpaceService(database)
            initial_state = reading_service.update_current_page(
                document.document_id,
                1,
                total_pages=3,
            )
            if initial_state.status != ReadingOperationStatus.SUCCESS:
                raise RuntimeError("Synthetic Reading State setup failed")

            DocumentPageMapIndexManager(database).apply()
            page_map = DocumentPageMapService(database).set_quick_rule(
                document.document_id,
                current_pdf_page=2,
            )
            if page_map.status != PageMapOperationStatus.SUCCESS:
                raise RuntimeError("Synthetic Page Map setup failed")

            process = subprocess.Popen(
                [
                    str(PYTHON),
                    "-m",
                    "mathmongo.advanced_reader",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--database",
                    database_name,
                    "--mongo-uri",
                    MONGO_URI,
                    "--log-level",
                    "warning",
                ],
                cwd=temporary_root if PACKAGE_ROOT is not None else REPOSITORY_ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            health = _wait_for_health(base_url, process)

            browser_environment = environment.copy()
            browser_environment.update(
                {
                    "MATHMONGO_ADVANCED_READER_E2E_URL": base_url,
                    "MATHMONGO_ADVANCED_READER_E2E_DOCUMENT_ID": document.document_id,
                    "MATHMONGO_ADVANCED_READER_E2E_EXPECTED_PAGES": "3",
                    "MATHMONGO_ADVANCED_READER_E2E_EXPECTED_PDF_SIZE": str(len(synthetic_pdf)),
                    "MATHMONGO_ADVANCED_READER_E2E_BOOK_LABEL": "Book page 1",
                    "MATHMONGO_ADVANCED_READER_E2E_SEARCH_TEXT": "searchable theorem",
                    "MATHMONGO_CHROME_PATH": CHROME_PATH,
                    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
                }
            )
            browser = subprocess.run(
                ["npm", "run", "test:e2e"],
                cwd=FRONTEND_ROOT,
                env=browser_environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            browser_result = _browser_summary(browser.stdout)
            if browser.returncode != 0 or browser_result.get("ok") is not True:
                raise RuntimeError(
                    "Real-browser validation failed: " + json.dumps(browser_result, sort_keys=True)
                )

            persisted = reading_service.get_reader_context(document.document_id)
            if (
                persisted.status != ReadingOperationStatus.SUCCESS
                or persisted.value is None
                or persisted.value.reading_state is None
                or persisted.value.reading_state.current_page != 2
            ):
                raise RuntimeError("S3 did not retain the explicitly saved browser position")

            reader_url = build_advanced_reader_url(
                document.document_id,
                base_url=base_url,
            )
            streamlit_url_ok = reader_url == (
                f"{base_url}/reader?document_id={document.document_id}"
            )
            fallback_source = (REPOSITORY_ROOT / "editor" / "pdf_preview.py").read_text(
                encoding="utf-8"
            )
            reading_source = (
                REPOSITORY_ROOT / "editor" / "reading_space" / "reader_page.py"
            ).read_text(encoding="utf-8")
            fallback_present = (
                "ui.pdf(" in fallback_source and "render_pdf_preview(" in reading_source
            )
            if not streamlit_url_ok or not fallback_present:
                raise RuntimeError("Streamlit URL or st.pdf fallback validation failed")

            summary = {
                "ok": True,
                "database": health.get("database") == database_name,
                "browser": browser_result,
                "reading_state_page": persisted.value.reading_state.current_page,
                "streamlit_url": streamlit_url_ok,
                "st_pdf_fallback": fallback_present,
                "package_origin": "installed_wheel" if PACKAGE_ROOT is not None else "checkout",
            }
            print(json.dumps(summary, sort_keys=True))
    finally:
        cleanup_errors: list[str] = []
        if process is not None:
            try:
                server_stdout, server_stderr = _stop_server(process)
            except Exception:  # pragma: no cover - defensive cleanup reporting
                cleanup_errors.append("server_stop_failed")
        try:
            client.drop_database(database_name)
            if database_name in client.list_database_names():
                cleanup_errors.append("temporary_database_remained")
        except Exception:  # pragma: no cover - defensive cleanup reporting
            cleanup_errors.append("temporary_database_cleanup_failed")
        finally:
            client.close()
        for key, value in original_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if "Traceback (most recent call last)" in server_stdout + server_stderr:
            cleanup_errors.append("backend_traceback_observed")
        if temporary_root is not None and temporary_root.exists():
            cleanup_errors.append("temporary_xdg_remained")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))
        except OSError:  # pragma: no cover - defensive cleanup reporting
            cleanup_errors.append("temporary_port_remained_bound")
        if cleanup_errors:
            raise RuntimeError("Advanced Reader E2E cleanup failed: " + ", ".join(cleanup_errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

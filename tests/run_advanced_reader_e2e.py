"""One-shot real-Chrome S5A/S5B validation using temporary Mongo/XDG state."""

from __future__ import annotations

import json
import os
import random
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
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
from editor.concept_linking.page_concepts import resolve_document_evidence  # noqa: E402
from editor.utils import db_export  # noqa: E402
from editor.utils import db_import  # noqa: E402
from mathmongo.advanced_reader.streamlit_link import build_advanced_reader_url  # noqa: E402
from mathmongo.document_page_maps.indexes import DocumentPageMapIndexManager  # noqa: E402
from mathmongo.document_page_maps.service import DocumentPageMapService  # noqa: E402
from mathmongo.document_page_maps.service import PageMapOperationStatus  # noqa: E402
from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager  # noqa: E402
from mathmongo.reading_annotations.models import DocumentAnnotation  # noqa: E402
from mathmongo.reading_annotations.service import ReadingAnnotationOperationStatus  # noqa: E402
from mathmongo.reading_annotations.service import ReadingAnnotationService  # noqa: E402
from mathmongo.reading_space.indexes import ReadingSpaceIndexManager  # noqa: E402
from mathmongo.reading_space.service import ReadingOperationStatus  # noqa: E402
from mathmongo.reading_space.service import ReadingSpaceService  # noqa: E402
from mathmongo.source_catalog.models import Reference  # noqa: E402
from mathmongo.source_catalog.models import Source  # noqa: E402
from mathmongo.source_documents.service import DocumentOperationStatus  # noqa: E402
from mathmongo.source_documents.service import SourceDocumentService  # noqa: E402
from mathmongo.source_documents.storage import SourceDocumentBlobStore  # noqa: E402

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


def _start_server(
    *,
    database_name: str,
    port: int,
    environment: dict[str, str],
    working_directory: Path,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
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
        cwd=working_directory,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _run_browser(environment: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], dict]:
    browser = subprocess.run(
        ["npm", "run", "test:e2e"],
        cwd=FRONTEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    try:
        summary = _browser_summary(browser.stdout)
    except (RuntimeError, json.JSONDecodeError) as exc:
        diagnostic = " ".join((browser.stdout + "\n" + browser.stderr).split())[-2_000:]
        raise RuntimeError(f"Real-browser runner emitted no summary: {diagnostic}") from exc
    return browser, summary


def main() -> int:
    """Exercise S5A/S5B, portability, and cleanup with isolated real services."""
    if not PYTHON.is_file() or not Path(CHROME_PATH).is_file():
        raise RuntimeError("Project Python and system Chrome are required for S5A/S5B E2E")
    package_origin = Path(mathmongo.__file__).resolve()
    if PACKAGE_ROOT is not None and not package_origin.is_relative_to(PACKAGE_ROOT):
        raise RuntimeError("Offline E2E did not import MathMongo from the installed wheel")

    token = os.urandom(8).hex()
    database_name = f"s5b_e2e_{token}"
    imported_database_name = f"s5b_e2e_imported_{token}"
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    client.admin.command("ping")
    database = client[database_name]
    imported_database = client[imported_database_name]
    process: subprocess.Popen[str] | None = None
    server_outputs: list[tuple[str, str]] = []
    temporary_root: Path | None = None
    port = _free_port()
    imported_port = _free_port()
    while imported_port == port:
        imported_port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    imported_base_url = f"http://127.0.0.1:{imported_port}"
    managed_environment_keys = ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME")
    original_environment = {key: os.environ.get(key) for key in managed_environment_keys}

    try:
        with tempfile.TemporaryDirectory(prefix="mathmongo-s5b-e2e-") as temporary:
            temporary_root = Path(temporary)
            home = temporary_root / "home"
            xdg_data = temporary_root / "xdg-data"
            imported_xdg_data = temporary_root / "imported-xdg-data"
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

            origin_blob_store = SourceDocumentBlobStore(xdg_data / "mathmongo")
            imported_blob_store = SourceDocumentBlobStore(imported_xdg_data / "mathmongo")
            db_export.LEGACY_PROJECT_ROOT = temporary_root / "absent-legacy-project"
            db_export.LOCAL_MEDIA_ROOT = temporary_root / "absent-local-media"
            db_import.DATA_DIR = imported_xdg_data / "mathmongo"

            source = Source(name=f"S5B synthetic source {token}")
            reference = Reference(
                source_ids=[source.source_id],
                title="S5B synthetic reference",
            )
            database["sources"].insert_one(source.model_dump(mode="python"))
            database["references"].insert_one(reference.model_dump(mode="python"))
            concept_id = f"s5b-e2e-{token}"
            concept_source = "S5B E2E"
            database["concepts"].insert_one(
                {
                    "id": concept_id,
                    "source": concept_source,
                    "name": "Concepto visual E2E",
                }
            )

            document_service = SourceDocumentService(database, storage=origin_blob_store)
            # PDF.js only issues its own range requests for a sufficiently large file.
            # Replace the helper's repetitive padding in-place with deterministic
            # high-entropy bytes so the same fixture also passes the importer's
            # compression-bomb guard during the S5B portability roundtrip.
            padding_size = 320_000
            synthetic_pdf = synthetic_text_pdf(padding_bytes=padding_size)
            zero_padding = b"0" * padding_size
            if synthetic_pdf.count(zero_padding) != 1:
                raise RuntimeError("Synthetic PDF padding layout changed unexpectedly")
            synthetic_pdf = synthetic_pdf.replace(
                zero_padding,
                random.Random(0x55B).randbytes(padding_size),
                1,
            )
            created = document_service.create_pdf_document(
                source_id=source.source_id,
                reference_id=reference.reference_id,
                pdf_bytes=synthetic_pdf,
                original_filename="s5b-synthetic.pdf",
                title="S5B synthetic Advanced Reader PDF",
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

            annotation_index_manager = ReadingAnnotationIndexManager(database)
            annotation_index_plan = annotation_index_manager.apply()
            if not annotation_index_plan.initialized:
                raise RuntimeError("Notes & Evidence indexes were not initialized explicitly")
            annotation_service = ReadingAnnotationService(
                database,
                documents=document_service.documents,
                sources=document_service.sources,
                references=document_service.references,
                index_manager=annotation_index_manager,
                document_service=document_service,
            )
            working_directory = temporary_root if PACKAGE_ROOT is not None else REPOSITORY_ROOT
            process = _start_server(
                database_name=database_name,
                port=port,
                environment=environment,
                working_directory=working_directory,
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
                    "MATHMONGO_ADVANCED_READER_E2E_UNDERLINE_TEXT": "gamma",
                    "MATHMONGO_ADVANCED_READER_E2E_CONCEPT_TEXT": "Concepto visual E2E",
                    "MATHMONGO_ADVANCED_READER_E2E_MODE": "full",
                    "MATHMONGO_CHROME_PATH": CHROME_PATH,
                    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
                }
            )
            browser, browser_result = _run_browser(browser_environment)
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

            highlight_id = browser_result.get("highlightAnnotationId")
            underline_id = browser_result.get("underlineAnnotationId")
            highlight_page = browser_result.get("highlightPage")
            underline_page = browser_result.get("underlinePage")
            if (
                not isinstance(highlight_id, str)
                or not isinstance(underline_id, str)
                or not isinstance(highlight_page, int)
                or not isinstance(underline_page, int)
                or highlight_page != 1
            ):
                raise RuntimeError("Browser did not return the two persisted visual identities")
            raw_annotations = list(
                database["document_annotations"].find({"document_id": document.document_id})
            )
            if {item.get("annotation_id") for item in raw_annotations} != {
                highlight_id,
                underline_id,
            }:
                raise RuntimeError("MongoDB visual Annotation identities differ from Chrome")
            visual_annotations: dict[str, DocumentAnnotation] = {}
            for annotation_id in (highlight_id, underline_id):
                loaded = annotation_service.get_annotation(annotation_id)
                if (
                    loaded.status != ReadingAnnotationOperationStatus.SUCCESS
                    or loaded.value is None
                    or loaded.value.schema_version != 2
                    or loaded.value.status.value != "active"
                    or loaded.value.visual_anchor is None
                ):
                    raise RuntimeError("Chrome did not persist a valid active schema-v2 visual")
                visual_annotations[annotation_id] = loaded.value
            highlight = visual_annotations[highlight_id]
            underline = visual_annotations[underline_id]
            if (
                highlight.kind.value != "highlight"
                or highlight.page_number != highlight_page
                or highlight.color_label != "green"
                or highlight.body != "Comentario visual E2E editado"
                or highlight.tags != ["e2e", "editado"]
                or underline.kind.value != "underline"
                or underline.page_number != underline_page
                or underline.color_label != "blue"
            ):
                raise RuntimeError(
                    "Visual presentation edits did not survive the browser lifecycle"
                )

            browser_evidence_id = browser_result.get("conceptEvidenceLinkId")
            evidence = (
                annotation_service.evidence.get_by_id(browser_evidence_id)
                if isinstance(browser_evidence_id, str)
                else None
            )
            if (
                evidence is None
                or evidence.annotation_id != highlight_id
                or evidence.concept_legacy_id != concept_id
                or evidence.concept_legacy_source != concept_source
                or evidence.link_type.value != "definition_source"
                or evidence.comment != "Definición visual confirmada E2E"
                or evidence.status.value != "active"
            ):
                raise RuntimeError("Chrome concept evidence did not retain the exact identities")
            streamlit_views = resolve_document_evidence(
                database,
                annotation_service,
                document_id=document.document_id,
                status=None,
                page=1,
                page_size=100,
            )
            streamlit_same_link = any(
                item.evidence_link_id == evidence.evidence_link_id
                and item.annotation_id == highlight_id
                and item.concept.identity == (concept_id, concept_source)
                and item.link_type == "definition_source"
                and item.comment == "Definición visual confirmada E2E"
                for item in streamlit_views
            )
            if not streamlit_same_link:
                raise RuntimeError("S4.3 did not resolve the Advanced Reader concept link")

            geometry_samples = browser_result.get("visualGeometry")
            if not isinstance(geometry_samples, dict) or not geometry_samples:
                raise RuntimeError("Browser did not expose measured visual geometry")
            measured_samples = [
                sample
                for sample in geometry_samples.values()
                if isinstance(sample, dict)
                and isinstance(sample.get("maxNormalizedDelta"), int | float)
                and isinstance(sample.get("maxPixelDelta"), int | float)
            ]
            if len(measured_samples) != len(geometry_samples):
                raise RuntimeError("A visual geometry phase did not produce a finite metric")
            max_normalized_delta = max(
                float(sample["maxNormalizedDelta"]) for sample in measured_samples
            )
            max_pixel_delta = max(float(sample["maxPixelDelta"]) for sample in measured_samples)

            server_outputs.append(_stop_server(process))
            process = None

            archive = db_export.export_database_to_zip(
                SimpleNamespace(db=database),
                temporary_root / "portable-backup",
                source_document_blob_store=origin_blob_store,
            )
            first_import = db_import.import_zip_into_database(
                archive,
                SimpleNamespace(db=imported_database),
                source_document_blob_store=imported_blob_store,
            )
            if (
                first_import.catalog_inserted.get("document_annotations") != 2
                or first_import.catalog_inserted.get("concept_evidence_links") != 1
                or first_import.source_document_blobs_created != 1
            ):
                raise RuntimeError("First portable import did not restore the complete S5B graph")
            imported_index_manager = ReadingAnnotationIndexManager(imported_database)
            import_index_plan = imported_index_manager.plan()
            if import_index_plan.conflicts or len(import_index_plan.missing) != len(
                import_index_plan.statuses
            ):
                raise RuntimeError("Import created or conflicted with Notes & Evidence indexes")

            second_import = db_import.import_zip_into_database(
                archive,
                SimpleNamespace(db=imported_database),
                source_document_blob_store=imported_blob_store,
            )
            if (
                second_import.catalog_inserted.get("document_annotations", 0) != 0
                or second_import.catalog_inserted.get("concept_evidence_links", 0) != 0
                or second_import.catalog_identical.get("document_annotations") != 2
                or second_import.catalog_identical.get("concept_evidence_links") != 1
                or second_import.source_document_blobs_identical != 1
            ):
                raise RuntimeError("Second portable import was not an exact no-op")

            restored_annotations = {
                item.get("annotation_id")
                for item in imported_database["document_annotations"].find(
                    {"document_id": document.document_id}
                )
            }
            restored_evidence = imported_database["concept_evidence_links"].find_one(
                {"evidence_link_id": evidence.evidence_link_id}
            )
            if (
                restored_annotations != {highlight_id, underline_id}
                or restored_evidence is None
                or restored_evidence.get("annotation_id") != highlight_id
            ):
                raise RuntimeError("Portable graph changed visual or evidence identities")

            imported_index_plan = imported_index_manager.apply()
            if not imported_index_plan.initialized:
                raise RuntimeError("Imported Notes & Evidence indexes were not applied explicitly")

            imported_environment = environment.copy()
            imported_environment.update(
                {
                    "XDG_DATA_HOME": str(imported_xdg_data),
                    "MATHMONGO_ADVANCED_READER_URL": imported_base_url,
                }
            )
            process = _start_server(
                database_name=imported_database_name,
                port=imported_port,
                environment=imported_environment,
                working_directory=working_directory,
            )
            imported_health = _wait_for_health(imported_base_url, process)
            imported_browser_environment = imported_environment.copy()
            imported_browser_environment.update(
                {
                    "MATHMONGO_ADVANCED_READER_E2E_URL": imported_base_url,
                    "MATHMONGO_ADVANCED_READER_E2E_DOCUMENT_ID": document.document_id,
                    "MATHMONGO_ADVANCED_READER_E2E_EXPECTED_PAGES": "3",
                    "MATHMONGO_ADVANCED_READER_E2E_EXPECTED_PDF_SIZE": str(len(synthetic_pdf)),
                    "MATHMONGO_ADVANCED_READER_E2E_MODE": "imported",
                    "MATHMONGO_ADVANCED_READER_E2E_HIGHLIGHT_ID": highlight_id,
                    "MATHMONGO_ADVANCED_READER_E2E_UNDERLINE_ID": underline_id,
                    "MATHMONGO_ADVANCED_READER_E2E_HIGHLIGHT_PAGE": str(highlight_page),
                    "MATHMONGO_ADVANCED_READER_E2E_UNDERLINE_PAGE": str(underline_page),
                    "MATHMONGO_CHROME_PATH": CHROME_PATH,
                    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
                }
            )
            imported_browser, imported_browser_result = _run_browser(imported_browser_environment)
            if imported_browser.returncode != 0 or imported_browser_result.get("ok") is not True:
                raise RuntimeError(
                    "Imported real-browser validation failed: "
                    + json.dumps(imported_browser_result, sort_keys=True)
                )

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
            if (
                health.get("database") != database_name
                or imported_health.get("database") != imported_database_name
            ):
                raise RuntimeError("An Advanced Reader server used the wrong temporary database")

            summary = {
                "ok": True,
                "database": True,
                "imported_database": True,
                "browser": browser_result,
                "imported_browser": imported_browser_result,
                "reading_state_page": persisted.value.reading_state.current_page,
                "visual_annotation_ids": [highlight_id, underline_id],
                "concept_evidence_annotation_id": evidence.annotation_id,
                "origin_reading_annotation_indexes": len(annotation_index_plan.present),
                "import_was_index_free": len(import_index_plan.missing),
                "imported_reading_annotation_indexes": len(imported_index_plan.present),
                "first_import_visuals": first_import.catalog_inserted.get("document_annotations"),
                "second_import_identical_visuals": second_import.catalog_identical.get(
                    "document_annotations"
                ),
                "max_visual_normalized_delta": max_normalized_delta,
                "max_visual_pixel_delta": max_pixel_delta,
                "streamlit_url": streamlit_url_ok,
                "st_pdf_fallback": fallback_present,
                "streamlit_s4_3_same_link": streamlit_same_link,
                "package_origin": "installed_wheel" if PACKAGE_ROOT is not None else "checkout",
            }
            print(json.dumps(summary, sort_keys=True))
    finally:
        cleanup_errors: list[str] = []
        if process is not None:
            try:
                server_outputs.append(_stop_server(process))
            except Exception:  # pragma: no cover - defensive cleanup reporting
                cleanup_errors.append("server_stop_failed")
        try:
            for temporary_database_name in (database_name, imported_database_name):
                client.drop_database(temporary_database_name)
                if temporary_database_name in client.list_database_names():
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
        combined_server_output = "".join(stdout + stderr for stdout, stderr in server_outputs)
        if "Traceback (most recent call last)" in combined_server_output:
            cleanup_errors.append("backend_traceback_observed")
        if temporary_root is not None and temporary_root.exists():
            cleanup_errors.append("temporary_xdg_remained")
        for temporary_port in (port, imported_port):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind(("127.0.0.1", temporary_port))
            except OSError:  # pragma: no cover - defensive cleanup reporting
                cleanup_errors.append("temporary_port_remained_bound")
        if cleanup_errors:
            raise RuntimeError("Advanced Reader E2E cleanup failed: " + ", ".join(cleanup_errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

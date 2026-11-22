"""Own MongoDB, FastAPI, browser and XDG files; never start Streamlit."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.service import SourceDocumentService
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from tests.advanced_reader_test_support import synthetic_text_pdf

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    """Choose a loopback port before starting a process and verifying ownership."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    """Exercise the autonomous build with real persistence and strict ownership."""
    browser = "firefox" if "--browser=firefox" in sys.argv else "chrome"
    evidence = ROOT / "evidence/sonar/independent-study" / browser
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="mathmongo-independent-") as temporary:
        work = Path(temporary)
        dbpath = work / "mongo"
        dbpath.mkdir()
        mongo_port = free_port()
        mongo = subprocess.Popen(
            [
                shutil.which("mongod") or "mongod",
                "--dbpath",
                str(dbpath),
                "--port",
                str(mongo_port),
                "--bind_ip",
                "127.0.0.1",
                "--nounixsocket",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        client = MongoClient(f"mongodb://127.0.0.1:{mongo_port}", serverSelectionTimeoutMS=150)
        app = None
        name = "mathmongo_independent_" + uuid4().hex
        log = (evidence / "backend.log").open("w")
        try:
            for _ in range(100):
                assert mongo.poll() is None
                try:
                    client.admin.command("ping")
                    break
                except ConnectionFailure:
                    time.sleep(0.1)
            assert client.admin.command("serverStatus")["pid"] == mongo.pid
            assert not (set(client.list_database_names()) - {"admin", "config", "local"})
            db = client[name]
            SourceCatalogIndexManager(db).apply()
            db.concepts.create_index([("id", 1), ("source", 1)], unique=True)
            db.latex_documents.create_index([("id", 1), ("source", 1)], unique=True)
            db.relations.create_index([("desde", 1), ("hasta", 1), ("tipo", 1)], unique=True)
            source = Source(name="Álgebra — biblioteca de prueba")
            db.sources.insert_one(source.model_dump(mode="python"))
            reference = Reference(
                source_ids=[source.source_id],
                title="Lectura de álgebra",
                authors=[{"family": "Noether"}],
                year=1930,
            )
            db.references.insert_one(reference.model_dump(mode="python"))
            storage = SourceDocumentBlobStore(work / "data/mathmongo")
            document = SourceDocumentService(db, storage=storage).create_pdf_document(
                source_id=source.source_id,
                reference_id=reference.reference_id,
                pdf_bytes=synthetic_text_pdf(padding_bytes=0),
                original_filename="owned.pdf",
                title="Lectura de álgebra para el recorrido",
            )
            assert document.completed
            app_port = free_port()
            while app_port == mongo_port:
                app_port = free_port()
            environment = dict(
                os.environ,
                PYTHONPATH=str(ROOT),
                MONGODB_URI=f"mongodb://127.0.0.1:{mongo_port}",
                MONGODB_DB=name,
                PLAYWRIGHT_BROWSERS_PATH=os.environ.get(
                    "PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache/ms-playwright")
                ),
                MATHMONGO_INDEPENDENT_URL=f"http://127.0.0.1:{app_port}",
                MATHMONGO_INDEPENDENT_EVIDENCE=str(evidence),
                MATHMONGO_STUDY_BROWSER=browser,
            )
            for alias in ("MONGO_URI", "MONGO_DB", "DB_NAME"):
                environment.pop(alias, None)
            for kind in ("CONFIG", "DATA", "STATE", "CACHE"):
                environment["XDG_" + kind + "_HOME"] = str(work / kind.lower())
            wrapper = work / "backend.py"
            wrapper.write_text(
                """import os, sys, json
from pathlib import Path
from pymongo import MongoClient
import uvicorn
from mathmongo.advanced_reader.app import create_app
from mathmongo.advanced_reader.dependencies import AdvancedReaderDependencies
from mathmongo.source_documents.storage import SourceDocumentBlobStore
client=MongoClient(os.environ['MONGODB_URI'])
dependencies=AdvancedReaderDependencies.from_database(client[os.environ['MONGODB_DB']], database_name=os.environ['MONGODB_DB'])
dependencies.document_service.storage=SourceDocumentBlobStore(Path(os.environ['XDG_DATA_HOME'])/'mathmongo')
Path(os.environ['MATHMONGO_INDEPENDENT_EVIDENCE']+'/ownership.json').write_text(json.dumps({'backend':'FastAPI','streamlit_imported':'streamlit' in sys.modules}))
uvicorn.run(create_app(dependencies),host='127.0.0.1',port="""
                + str(app_port)
                + """,access_log=False)
"""
            )
            app = subprocess.Popen(
                [sys.executable, str(wrapper)],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            for _ in range(100):
                assert app.poll() is None
                try:
                    with urlopen(
                        environment["MATHMONGO_INDEPENDENT_URL"] + "/api/advanced-reader/health",
                        timeout=1,
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            subprocess.run(
                ["node", "tests/independent-study-browser.mjs"],
                cwd=ROOT / "frontend/advanced-reader",
                env=environment,
                check=True,
                timeout=240,
            )
            notes = list(
                db.reading_notes.find(
                    {}, {"_id": 0, "title": 1, "body": 1, "document_id": 1, "tags": 1}
                )
            )
            assert len(notes) == 1, notes
            assert db.concepts.count_documents({}) == 1
            assert db.concept_evidence_links.count_documents({}) == 2
            assert db.document_annotations.count_documents({}) == 1
            (evidence / "persistence.json").write_text(
                json.dumps(
                    {
                        "notes": notes,
                        "concepts": 1,
                        "annotations": 1,
                        "evidence_links": 2,
                        "streamlit_started": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            print(json.dumps({"browser": browser, "status": "passed", "streamlit_started": False}))
        finally:
            if app is not None:
                app.terminate()
                try:
                    app.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    app.kill()
                    app.wait(timeout=5)
            log.close()
            client.drop_database(name)
            assert not (set(client.list_database_names()) - {"admin", "config", "local"})
            client.close()
            mongo.terminate()
            try:
                mongo.wait(timeout=20)
            except subprocess.TimeoutExpired:
                mongo.kill()
                mongo.wait(timeout=5)


if __name__ == "__main__":
    main()

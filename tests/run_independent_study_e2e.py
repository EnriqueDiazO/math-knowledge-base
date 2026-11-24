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
                MATHMONGO_PALETTE_SOURCE=source.source_id,
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
            if "--authoring" in sys.argv:
                if "--needs-preparation" in sys.argv:
                    # Simulate a compatible unprepared library only inside this
                    # PID-owned database. The application never drops indexes.
                    for collection, keys in [("sources", [("source_id", 1)]), ("references", [("reference_id", 1)]), ("concepts", [("id", 1), ("source", 1)]), ("latex_documents", [("id", 1), ("source", 1)]), ("relations", [("desde", 1), ("hasta", 1), ("tipo", 1)])]:
                        for index in db[collection].list_indexes():
                            if list(index["key"].items()) == keys and index.get("unique"):
                                db[collection].drop_index(index["name"])
                    environment["MATHMONGO_AUTHORING_PREPARE"] = "1"
                upload = work / "authoring.pdf"
                upload.write_bytes(synthetic_text_pdf(padding_bytes=0))
                environment["MATHMONGO_AUTHORING_PDF"] = str(upload)
                subprocess.run(["node", "tests/authoring-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=240)
                proof = json.loads((evidence / "authoring-browser.json").read_text())
                assert db.sources.count_documents({"source_id": proof["sourceId"]}) == 1
                assert db.concepts.count_documents({"source_id": proof["sourceId"]}) == 2
                assert db.references.count_documents({"source_ids": proof["sourceId"]}) == 1
                assert db.source_documents.count_documents({"source_id": proof["sourceId"]}) == 1
                assert db.relations.count_documents({"desde": proof["secondKey"], "hasta": proof["firstKey"], "tipo": "requiere_concepto"}) == 1
                assert db.sources.count_documents({"source_id": proof["webSourceId"]}) == 1
                assert db.references.find_one({"source_ids": proof["webSourceId"]})["doi"] is None
                print(json.dumps({"browser": browser, "authoring": "passed", "streamlit_started": False}))
            if "--notes" in sys.argv:
                assert "--authoring" in sys.argv, "Notes traversal requires the UI-created source"
                subprocess.run(["node", "tests/notes-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=240)
                proof = json.loads((evidence / "notes-browser.json").read_text())
                note = db.reading_notes.find_one({"note_id": proof["noteId"]})
                assert note["source_id"] == proof["sourceId"]
                assert note["body"] == "Cambio posterior de otra ventana."
                assert note["reference_locator"]["printed_page"] == "23"
                assert db.references.find_one({"reference_id": note["reference_id"]})["source_ids"] == [proof["sourceId"]]
                assert db.reading_notes.count_documents({}) == 2
                print(json.dumps({"browser": browser, "notes": "passed", "temporary_notes": 2}))
            if "--document-export" in sys.argv:
                assert "--authoring" in sys.argv, "Document authoring needs the UI-created Source"
                subprocess.run(["node", "tests/document-export-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=240)
                proof = json.loads((evidence / "document-export-browser.json").read_text())
                key = proof["key"]
                concept_id, legacy_source = key.rsplit("@",1)
                body = db.latex_documents.find_one({"id":concept_id,"source":legacy_source})["contenido_latex"]
                assert "Contexto corregido visualmente." in body and r"\begin{tikzpicture}" in body
                assert db.concepts.count_documents({"source_id":proof["sourceId"]}) == 3
                print(json.dumps({"browser":browser,"document_export":"passed","canonical_LaTeX":True}))
            if "--legacy" in sys.argv:
                import hashlib
                from bson import json_util

                copied = json_util.loads((ROOT / "evidence/sonar/fundamental-authoring/legacy-fixtures.json").read_text())
                manifest = []
                for item in copied:
                    identity = {key: item["metadata"][key] for key in ("id", "source")}
                    assert db.concepts.find_one(identity) is None
                    db.concepts.insert_one(item["metadata"].copy())
                    db.latex_documents.insert_one(item["latex"].copy())
                    manifest.append({"case":item["case"], "key":str(identity["id"])+"@"+identity["source"], "title":item["metadata"].get("titulo") or str(identity["id"]), "sha256":hashlib.sha256(item["latex"]["contenido_latex"].encode()).hexdigest()})
                manifest_path = work / "legacy-cases.json"
                manifest_path.write_text(json.dumps(manifest))
                environment["MATHMONGO_LEGACY_CASES"] = str(manifest_path)
                subprocess.run(["node", "tests/legacy-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=240)
                for item in copied:
                    identity = {key:item["metadata"][key] for key in ("id", "source")}
                    assert db.latex_documents.find_one(identity)["contenido_latex"] == item["latex"]["contenido_latex"]
                    current = db.concepts.find_one(identity)
                    assert all(current[key] == value for key,value in item["metadata"].items() if key not in {"ultima_actualizacion"})
                print(json.dumps({"browser":browser,"legacy":"passed","real_copies":len(copied),"MathV0_writes":0}))
            if "--palette" in sys.argv:
                # Seed visual examples only after checking the exact migration
                # checkpoint counts. These records live in this owned database.
                from types import SimpleNamespace

                from mathmongo.knowledge_map.service import KnowledgeMapService
                service = KnowledgeMapService(SimpleNamespace(db=db, concepts=db.concepts,
                    relations=db.relations, latex_documents=db.latex_documents))
                palette = json.loads((ROOT / "editor/ui/concept_types.json").read_text())
                for kind, values in palette.items():
                    result = service.execute({
                        "operation_id": str(uuid4()), "action": "create",
                        "source_id": source.source_id, "titulo": "Muestra · " + values["label"],
                        "tipo": kind, "contenido_latex": r"Una idea con $\frac{1}{2}$.",
                        "categorias": ["Álgebra"],
                    })
                    assert result["status"] == "saved", result
                subprocess.run(
                    ["node", "tests/concept-palette-browser.mjs"],
                    cwd=ROOT / "frontend/advanced-reader", env=environment,
                    check=True, timeout=180,
                )
                assert db.concepts.count_documents({}) == 9
                assert db.reading_notes.count_documents({}) == 1
                print(json.dumps({"browser": browser, "palette": "passed", "temporary_concepts": 9}))
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

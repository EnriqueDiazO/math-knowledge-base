"""Own MongoDB, FastAPI, browser and XDG files; never start Streamlit."""

from __future__ import annotations

import json
import os
import shutil
import signal
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


def assert_no_streamlit(evidence):
    """Distinguish the source wrapper's import observation from the isolated package probe."""
    proof = json.loads((evidence / "ownership.json").read_text())
    key = "streamlit_imported" if "streamlit_imported" in proof else "streamlit_available"
    assert proof[key] is False


def restart_owned_package(app, command, work, environment, log, database, evidence):
    """Restart only this test-owned process group and recover real persisted academic notes."""
    import hashlib
    from urllib.request import Request

    from bson import json_util

    def state_hash():
        records = {name: list(database[name].find().sort("_id", 1))
                   for name in sorted(database.list_collection_names())}
        return hashlib.sha256(json_util.dumps(records, sort_keys=True).encode()).hexdigest()

    before = state_hash()
    previous_pid = app.pid
    base = environment["MATHMONGO_INDEPENDENT_URL"]
    with urlopen(base + "/api/study/v1/context", timeout=5) as response:
        previous_context = json.load(response)
    os.killpg(app.pid, signal.SIGTERM)
    try:
        app.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(app.pid, signal.SIGKILL)
        app.wait(timeout=5)
    # AppImage's extraction parent can exit before the server child releases its
    # listening socket. Do not mistake that dying server's health for the new one.
    from urllib.parse import urlsplit
    address = urlsplit(base)
    closed = False
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((address.hostname, address.port), timeout=1):
                pass
        except ConnectionRefusedError:
            closed = True
            break
        time.sleep(0.1)
    if not closed:
        raise RuntimeError("Owned backend did not release its listening socket")
    restarted = subprocess.Popen(command, cwd=work, env=environment, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for _ in range(100):
            assert restarted.poll() is None
            try:
                with urlopen(base + "/api/advanced-reader/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        with urlopen(base + "/api/study/v1/context", timeout=5) as response:
            context = json.load(response)
        assert context["runtime_id"] != previous_context["runtime_id"], "Restart read the old backend"
        recovered = []
        for record in database.latex_notes.find():
            family = {"cornell_math_v1": "cornell", "cpi_v1": "cpi"}.get(record.get("note_format"))
            path = ("/structured/" + family if family else "/notebook") + "/" + str(record["_id"])
            request = Request(base + "/api/study/v1" + path,
                              headers={"X-MathMongo-Library": context["library_id"]})
            with urlopen(request, timeout=5) as response:
                note = json.load(response)
            assert note["latex_body"] == record.get("latex_body", "")
            recovered.append(str(record["_id"]))
        recovered_concepts = []
        for record in database.concepts.find():
            body = database.latex_documents.find_one({"id": record["id"], "source": record["source"]})
            if body is None:
                continue
            key = str(record["id"]) + "@" + record["source"]
            from urllib.parse import urlencode
            request = Request(base + "/api/study/v1/concepts/detail?" + urlencode({"key": key}),
                              headers={"X-MathMongo-Library": context["library_id"]})
            with urlopen(request, timeout=5) as response:
                current = json.load(response)
            assert current["contenido_latex"] == body["contenido_latex"]
            recovered_concepts.append(key)
        after = state_hash()
        assert before == after
        (evidence / "package-restart.json").write_text(json.dumps({
            "passed": True, "previous_pid": previous_pid, "restarted_pid": restarted.pid,
            "persistent_state_sha256": after, "recovered_notes": recovered, "recovered_concepts": recovered_concepts,
            "MathV0_writes": 0, "only_owned_processes_restarted": True,
            "old_socket_closed_before_start": closed,
            "previous_runtime_id": previous_context["runtime_id"],
            "restarted_runtime_id": context["runtime_id"],
        }, indent=2) + "\n")
        return restarted
    except BaseException:
        if restarted.poll() is None:
            os.killpg(restarted.pid, signal.SIGTERM)
        restarted.wait(timeout=15)
        raise


def main():
    """Exercise the autonomous build with real persistence and strict ownership."""
    browser = "firefox" if "--browser=firefox" in sys.argv else "chrome"
    appimage = next((Path(arg.partition("=")[2]).resolve(strict=True) for arg in sys.argv if arg.startswith("--appimage=")), None)
    evidence = ROOT / "evidence/sonar" / ("packaged-study" if appimage else "independent-study") / browser
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
                MATHMONGO_TEST_RUN_ID=str(uuid4()),
                MATHMONGO_TEST_REVISION=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
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
            command = ([str(appimage), "--appimage-extract-and-run", "--port", str(app_port),
                        "--database", name] if appimage else [sys.executable, str(wrapper)])
            if appimage:
                environment.pop("PYTHONPATH", None)
                probe = subprocess.run([str(appimage), "--appimage-extract-and-run", "--bundle-check"],
                                       cwd=work, env=environment, capture_output=True,
                                       text=True, check=True, timeout=30)
                package_proof = json.loads(probe.stdout)
                assert package_proof["streamlit_available"] is False
                (evidence / "ownership.json").write_text(json.dumps(package_proof, indent=2) + "\n")
            app = subprocess.Popen(
                command,
                cwd=work if appimage else ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
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
            if "--library" in sys.argv:
                upload = work / "library.pdf"
                upload.write_bytes(synthetic_text_pdf(padding_bytes=0))
                environment["MATHMONGO_AUTHORING_PDF"] = str(upload)
                subprocess.run(["node","tests/library-browser.mjs"],cwd=ROOT/"frontend/advanced-reader",env=environment,check=True,timeout=240)
                proof=json.loads((evidence/"library-browser.json").read_text())
                assert db.sources.find_one({"source_id":proof["sourceId"]})["name"]=="Fuente corregida y recuperable"
                assert set(db.references.find_one({"reference_id":proof["referenceId"]})["source_ids"])=={proof["sourceId"],proof["secondSourceId"]}
                assert db.references.count_documents({"source_ids":proof["sourceId"]})==2
                assert db.source_documents.find_one({"document_id":proof["documentId"]})["status"]=="active"
                assert db.reading_notes.find_one({"note_id":proof["noteId"]})["document_id"]==proof["documentId"]
                print(json.dumps({"browser":browser,"library":"passed","MathV0_writes":0}))
            if "--notebook" in sys.argv:
                historical = {"_id":"historical-diary", "title":"Diario histórico de prueba", "latex_body": "% preservar exactamente\n\\macroHistorica{α}\n\\begin{tikzpicture}\\draw (0,0)--(1,1);\\end{tikzpicture}\n", "unknown_metadata":{"preserve":[1,"two"]}, "image_ids":["shared-historical"]}
                db.latex_notes.insert_one(historical.copy())
                subprocess.run(["node","tests/notebook-browser.mjs"],cwd=ROOT/"frontend/advanced-reader",env=environment,check=True,timeout=240)
                proof=json.loads((evidence/"notebook-browser.json").read_text())
                note=db.latex_notes.find_one({"_id":proof["noteId"]})
                assert note["title"]=="Mi título tras conflicto" and note["project"]=="Proyecto de otra ventana"
                assert note["references"][0]["catalog_reference_id"]==proof["referenceId"]
                assert proof["protectedLatex"] in note["latex_body"]
                assert db.latex_notes.count_documents({})==2
                assert db.latex_notes.find_one({"_id":"historical-diary"})==historical
                assert_no_streamlit(evidence)
                print(json.dumps({"browser":browser,"notebook":"passed","exact_historical_source":True,"MathV0_writes":0}))
            if "--structured" in sys.argv:
                subprocess.run(["node", "tests/structured-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=300)
                proof = json.loads((evidence / "structured-browser.json").read_text())
                assert proof["passed"] and len(proof["cases"]) == 2
                for case in proof["cases"]:
                    note = db.latex_notes.find_one({"_id": case["noteId"]})
                    assert note["title"] == case["title"] == "Versión de otra ventana"
                    assert note[case["family"]]["template_id"] == case["template"]
                    assert len(note[case["family"]]["pages"]) == 1
                    assert case["protectedLatex"] in note["latex_body"]
                assert_no_streamlit(evidence)
                print(json.dumps({"browser": browser, "structured": "passed", "MathV0_writes": 0}))
            if "--math-tools" in sys.argv:
                subprocess.run(["node", "tests/math-tools-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=240)
            if "--note-actions" in sys.argv:
                # Real historical Cornell/Diario are read from the authoritative ZIP.
                # That backup predates CPI; its case remains explicitly synthetic.
                import hashlib
                from copy import deepcopy
                from zipfile import ZipFile

                from bson import json_util

                from editor.cpi.service import create_cpi_note
                from mathdatabase.mathmongo import MathMongo
                from tests.test_cpi_service import sample_document
                from tests.test_cpi_service import sample_metadata

                backup = Path.home() / ".local/share/mathmongo/backups/mathkb_export_20260712_073927.zip"
                with ZipFile(backup) as archive:
                    historical = json_util.loads(archive.read("mathkb_export_20260712_073927/collections/latex_notes.json"))
                copied = []
                for family, fmt in [("cornell", "cornell_math_v1"), ("diary", None)]:
                    original = next(row for row in historical if row.get("note_format") == fmt)
                    record = deepcopy(original)
                    db.latex_notes.insert_one(record)
                    copied.append({"family": family, "id": str(record["_id"]),
                                   "latex_sha256": hashlib.sha256(record.get("latex_body", "").encode()).hexdigest(),
                                   "provenance": "authoritative-private-backup", "bson_sha256": hashlib.sha256(json_util.dumps(original,sort_keys=True).encode()).hexdigest()})
                mongo_facade = MathMongo.from_database(db)
                from dataclasses import replace

                from PIL import Image
                shared_id = "lifecycle-shared-image"
                image_path = work / "data/mathmongo/media/images/note-actions.png"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (24, 16), "#197f96").save(image_path)
                document = sample_document()
                first_page = replace(document.pages[0], production=replace(document.pages[0].production, image_ids=(shared_id,)))
                document = replace(document, pages=(first_page, *document.pages[1:]))
                cpi_id = create_cpi_note(mongo_facade, sample_metadata(), document).inserted_id
                db.latex_notes.insert_one({"_id": "lifecycle-resource-keeper", "title": "Recurso compartido", "latex_body": "Conservar", "image_ids": [shared_id]})
                db.media_assets.insert_one({"asset_id": shared_id, "note_ids": [str(cpi_id), "lifecycle-resource-keeper"], "concept_ids": [], "path": "media/images/note-actions.png", "filename": "note-actions.png", "mime_type": "image/png", "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(), "size_bytes": image_path.stat().st_size})
                cpi = db.latex_notes.find_one({"_id": cpi_id})
                copied.append({"family": "cpi", "id": str(cpi_id),
                               "latex_sha256": hashlib.sha256(cpi["latex_body"].encode()).hexdigest(),
                               "provenance": "canonical-synthetic-no-cpi-in-private-backup", "resource_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest()})
                manifest = work / "note-actions-cases.json"
                manifest.write_text(json.dumps(copied))
                environment["MATHMONGO_NOTE_ACTIONS_CASES"] = str(manifest)
                subprocess.run(["node", "tests/note-actions-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=240)
                proof = json.loads((evidence / "note-actions-browser.json").read_text())
                assert proof["passed"] and len(proof["cases"]) == 3
                assert db.latex_notes.find_one({"_id": original["_id"]}) is None
                assert set(db.media_assets.find_one({"asset_id": shared_id})["note_ids"]) == {str(cpi_id), "lifecycle-resource-keeper"}
                assert hashlib.sha256(image_path.read_bytes()).hexdigest() == copied[-1]["resource_sha256"]
                (evidence / "note-actions-provenance.json").write_text(json.dumps(copied, indent=2))
                assert_no_streamlit(evidence)
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
            if "--clone-drafts" in sys.argv:
                identity = {"id": "clone-probe", "source": source.name}
                db.concepts.insert_one({**identity, "source_id": source.source_id,
                                        "titulo": "Documento de control de ventanas",
                                        "tipo": "definicion", "comentario": "", "categorias": []})
                db.latex_documents.insert_one({**identity, "contenido_latex": "Una idea matemática que permanece después de recargar.$\\frac{1}{2}$\n\n"})
                environment["MATHMONGO_CLONE_CONCEPT_KEY"] = identity["id"] + "@" + identity["source"]
                subprocess.run(["node", "tests/concept-cloned-window-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=180)
                environment["MATHMONGO_TEST_PROFILE"] = str(work / "cold-browser-profile")
                subprocess.run(["node", "tests/concept-cold-recovery-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=180)
            if "--latex-parity" in sys.argv:
                from tests.latex_parity_corpus import freeze_corpus
                manifest = freeze_corpus(work / "corpus")
                for item in manifest:
                    raw_source = item["provenance"].get("source", "Corpus propio")
                    existing = db.sources.find_one({"name": raw_source})
                    if existing is None:
                        related = Source(name=raw_source)
                        db.sources.insert_one(related.model_dump(mode="python"))
                        source_id = related.source_id
                    else:
                        source_id = existing["source_id"]
                    concept_id = "parity-case-" + str(item["case"])
                    identity = {"id": concept_id, "source": raw_source}
                    db.concepts.insert_one({**identity, "source_id": source_id,
                                            "titulo": item["title"], "tipo": "definicion",
                                            "categorias": ["Corpus LaTeX"], "comentario": "",
                                            "opaque_metadata": {"keep": [1,"á"]}})
                    db.latex_documents.insert_one({**identity, "contenido_latex": Path(item["path"]).read_bytes().decode("utf-8")})
                    item["key"] = concept_id + "@" + raw_source
                corpus_manifest = work / "corpus-browser.json"
                corpus_manifest.write_text(json.dumps(manifest, ensure_ascii=False))
                environment["MATHMONGO_LATEX_CORPUS"] = str(corpus_manifest)
            if "--latex-parity" in sys.argv:
                subprocess.run(["node", "tests/latex-parity-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=600)
                proof = json.loads((evidence / "latex-parity-browser.json").read_text())
                assert proof["passed"] and len(proof["cases"]) == 10
                for item in manifest:
                    concept_id, legacy = item["key"].rsplit("@", 1)
                    metadata = db.concepts.find_one({"id": concept_id, "source": legacy})
                    assert metadata["opaque_metadata"] == {"keep": [1,"á"]}
                assert_no_streamlit(evidence)
            if appimage or "--latex-parity" in sys.argv:
                app = restart_owned_package(app, command, work, environment, log, db, evidence)
                print(json.dumps({"browser": browser, "backend_restart": "passed", "packaged": bool(appimage), "MathV0_writes": 0}))
                if "--latex-parity" in sys.argv:
                    subprocess.run(["node", "tests/latex-parity-recovery-browser.mjs"], cwd=ROOT / "frontend/advanced-reader", env=environment, check=True, timeout=180)
        finally:
            if app is not None:
                if app.poll() is None:
                    os.killpg(app.pid, signal.SIGTERM)
                try:
                    app.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(app.pid, signal.SIGKILL)
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

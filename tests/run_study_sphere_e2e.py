"""Own the real study app, MongoDB and files; never treat MathV0 as disposable."""

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

from mathmongo.source_catalog.models import Source

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = r"""\begin{definition}{Slowly oscillating shift}
Ejemplo temporal para verificar la interfaz; no sustituye la nota original.
Sea $G$ un grupo y $H\subseteq G$. Una relación de estudio conecta estas ideas.
\[
\frac{1}{2}+\frac{2}{3}=\frac{7}{6}
\]
\begin{remark}{Interpretación}
La lectura conserva texto, fórmulas y bloques de resultado.
\end{remark}
\begin{itemize}
\item Primera observación con \textbf{énfasis}.
\item Segunda observación.
\end{itemize}
\end{definition}
\begin{verbatim}
print("Código auténtico: no es una fórmula")
\end{verbatim}
"""


def port():
    """Choose a free loopback port owned only after starting its process."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    """Run before/after scenarios on an isolated, short-lived application."""
    evidence = ROOT / "evidence/sonar/mandala-2026-11"
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    phase = "before" if "--before" in sys.argv else "after"
    room_scenario = "--room" in sys.argv
    browser_name = next((arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--browser=')), 'chrome')
    if browser_name not in {'chrome', 'firefox'}:
        raise ValueError('Choose chrome or firefox')
    if phase != 'before':
        evidence = evidence / ("room" if room_scenario else "bibliography") / browser_name
        evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="mathmongo-study-") as directory:
        work = Path(directory)
        dbpath = work / "db"
        dbpath.mkdir()
        mongo_port, app_port = port(), port()
        while app_port == mongo_port:
            app_port = port()
        uri = f"mongodb://127.0.0.1:{mongo_port}"
        name = "mathmongo_study_" + uuid4().hex
        env = dict(
            os.environ,
            MONGODB_URI=uri,
            MONGODB_DB=name,
            PYTHONPATH=str(ROOT),
            STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",
            MATHMONGO_ADVANCED_READER_ENABLED="0",
            MATHMONGO_ADVANCED_READER_URL=f"http://127.0.0.1:{port()}",
            PLAYWRIGHT_BROWSERS_PATH=os.environ.get('PLAYWRIGHT_BROWSERS_PATH', str(Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'ms-playwright')),
        )
        for alias in ("MONGO_URI", "MONGO_DB", "DB_NAME"):
            env.pop(alias, None)
        for kind in ("DATA", "STATE", "CACHE", "CONFIG"):
            env[f"XDG_{kind}_HOME"] = str(work / kind.lower())
        executable = shutil.which("mongod")
        if executable is None:
            raise RuntimeError("Owned mongod required")
        mongo = subprocess.Popen(
            [
                executable,
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
        client = MongoClient(uri, serverSelectionTimeoutMS=200)
        app = None
        advanced = None
        advanced_log = None
        try:
            for _ in range(100):
                if mongo.poll() is not None:
                    raise RuntimeError("Owned MongoDB exited")
                try:
                    client.admin.command("ping")
                    break
                except ConnectionFailure:
                    time.sleep(0.1)
            assert client.admin.command("serverStatus")["pid"] == mongo.pid
            assert not (set(client.list_database_names()) - {"admin", "local", "config"})
            db = client[name]
            source = Source(name="Fuente de estudio temporal")
            db.sources.insert_one(source.model_dump(mode="python"))
            from mathmongo.source_catalog.models import Reference
            existing_reference = Reference(title='Ficha local corregida de Nyaga', year=1977,
                doi='10.1007/BF01106749', source_ids=[source.source_id], bibtex={'key': 'NyagaClaveEstable'})
            db.references.insert_one(existing_reference.model_dump(mode='python'))
            fixtures = [
                (
                    "nota:slow",
                    "Slowly oscillating shift",
                    ["Análisis Funcional", "Geometría"],
                    SAMPLE,
                ),
                (
                    "nota:karlovich",
                    "Una relación de Karlovich con un nombre completo y legible",
                    ["Análisis Funcional"],
                    "Una nota temporal sobre $L^p$.",
                ),
                (
                    "nota:pommerenke",
                    "Otra relación de Pommerenke con un nombre completo",
                    ["Geometría"],
                    "Una curva temporal $\\Gamma$.",
                ),
                (
                    "nota:sin",
                    "Concepto sin clasificar",
                    [],
                    "Un ejemplo temporal sin área asignada.",
                ),
            ]
            for cid, title, categories, body in fixtures:
                db.concepts.insert_one(
                    {
                        "id": cid,
                        "source": source.name,
                        "source_id": source.source_id,
                        "titulo": title,
                        "tipo": "nota",
                        "categorias": categories,
                        "image_ids": ["shared-temporary"],
                        "custom": {"preserve": True},
                    }
                )
                db.latex_documents.insert_one(
                    {"id": cid, "source": source.name, "contenido_latex": body}
                )
            for index, (left, right, kind) in enumerate(
                [
                    ("nota:slow", "nota:karlovich", "requiere_concepto"),
                    ("nota:pommerenke", "nota:slow", "implica"),
                    ("nota:slow", "nota:karlovich", "contrasta_con"),
                ]
            ):
                db.relations.insert_one(
                    {
                        "desde": left + "@" + source.name,
                        "hasta": right + "@" + source.name,
                        "tipo": kind,
                        "descripcion": f"Relación temporal {index}",
                    }
                )
            private = ROOT / "evidence/sonar/mandala-2026-11/representative-private.json"
            if private.exists():
                from bson import json_util

                copied = json_util.loads(private.read_text())
                metadata = copied["metadata"]
                content = copied["content"][0]
                db.concepts.insert_one(metadata)
                db.latex_documents.insert_one(content)
            room_document = room_mark = None
            if room_scenario:
                from types import SimpleNamespace

                from advanced_reader_test_support import synthetic_text_pdf

                from mathmongo.knowledge_map.service import KnowledgeMapService
                from mathmongo.reading_annotations.indexes import ReadingAnnotationIndexManager
                from mathmongo.reading_annotations.service import ReadingAnnotationService
                from mathmongo.reading_space.indexes import ReadingSpaceIndexManager
                from mathmongo.source_documents.service import SourceDocumentService
                from mathmongo.source_documents.storage import SourceDocumentBlobStore
                ReadingAnnotationIndexManager(db).apply()
                ReadingSpaceIndexManager(db).apply()
                storage = SourceDocumentBlobStore(Path(env['XDG_DATA_HOME']) / 'mathmongo')
                created = SourceDocumentService(db, storage=storage).create_pdf_document(
                    source_id=source.source_id, reference_id=existing_reference.reference_id,
                    pdf_bytes=synthetic_text_pdf(padding_bytes=0), original_filename='room-owned.pdf',
                    title='Paper temporal de la habitación')
                assert created.value is not None, created
                room_document = created.value
                room_mark = ReadingAnnotationService(db).create_annotation(room_document.document_id,
                    reference_id=existing_reference.reference_id, kind='highlight', page_number=2,
                    page_label='xii', quote_text='searchable theorem beta').value
                assert room_mark is not None
                api = KnowledgeMapService(SimpleNamespace(db=db,concepts=db.concepts,latex_documents=db.latex_documents,relations=db.relations))
                other_source=Source(name='Segunda fuente temporal')
                db.sources.insert_one(other_source.model_dump(mode='python'))
                db.concepts.insert_one({'id':'nota:slow','source':other_source.name,'source_id':other_source.source_id,
                    'titulo':'Slowly oscillating shift','tipo':'nota','categorias':[]})
                db.latex_documents.insert_one({'id':'nota:slow','source':other_source.name,'contenido_latex':'Otra procedencia temporal.'})
                view_ids=[]
                room_goal=str(uuid4())
                for title,members in [('Análisis', ['nota:slow','nota:karlovich']),('Contrastes',['nota:slow','nota:pommerenke'])]:
                    uid=str(uuid4());view_ids.append(uid)
                    response=api.execute({'operation_id':str(uuid4()),'action':'save_view','map_uid':uid,'map_name':title,
                        'view_state':{'version':1,'members':[cid+'@'+source.name for cid in members]+(['nota:slow@'+other_source.name] if title=='Contrastes' else []),
                            'goals':[{'id':room_goal,'label':'¿Cómo se interpreta el pasaje?','point':[0.,0.,1.]}] if title=='Análisis' else []}})
                    assert response['status']=='saved',response
                response=api.execute({'operation_id':str(uuid4()),'action':'save_room','room_uid':str(uuid4()),
                    'room_state':{'version':1,'name':'Estudio temporal', 'document_id':room_document.document_id,'goal_view_uid':view_ids[0],'goal_id':room_goal,
                        'spheres':[{'view_uid':uid,'position':[.25+.5*i,.45]} for i,uid in enumerate(view_ids)]}})
                assert response['status']=='saved',response
            if room_scenario:
                advanced_port = port()
                advanced_url = f'http://127.0.0.1:{advanced_port}'
                env['MATHMONGO_ADVANCED_READER_ENABLED'] = '1'
                env['MATHMONGO_ADVANCED_READER_URL'] = advanced_url
                advanced_log = (evidence / 'advanced-reader.log').open('w')
                advanced = subprocess.Popen([sys.executable, '-m', 'mathmongo.advanced_reader',
                    '--mongo-uri', uri, '--database', name, '--host', '127.0.0.1', '--port', str(advanced_port)],
                    cwd=ROOT, env=env, stdout=advanced_log, stderr=advanced_log)
                for _ in range(100):
                    if advanced.poll() is not None:
                        raise RuntimeError('Owned advanced reader exited; inspect its private log')
                    try:
                        with urlopen(advanced_url + '/api/advanced-reader/health', timeout=.3):
                            break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Owned advanced reader failed to become ready')
            # Provider fixtures live only in this temporary app wrapper. Production
            # never exposes a mock/network override or a test database selector.
            wrapper = work / 'study_app.py'
            wrapper.write_text("""import runpy
import sys
sys.path.insert(0, """ + repr(str(ROOT / "editor")) + """)
from editor import knowledge_map
from mathmongo.bibliography_lookup.service import MetadataLookup
from tests.test_bibliography_lookup import CROSSREF, EDITION
from mathmongo.bibliography_lookup.transport import MetadataLookupError
class FixtureHTTP:
    def get(self, url, *, deadline):
        if '10.1007%2Fbf01106749' in url: return CROSSREF
        if '/isbn/' in url: return EDITION
        if '/authors/OL42A.json' in url: return {'name': 'Autora temporal'}
        if 'outage' in url: raise MetadataLookupError('unavailable')
        raise MetadataLookupError('not_found')
lookup = MetadataLookup(http=FixtureHTTP())
knowledge_map.metadata_lookup = lambda: lookup
# Lose one response after the canonical service committed it. This wrapper is
# temporary test code; retries must replay the operation ledger without duplication.
import streamlit as st
from mathmongo.knowledge_map.service import KnowledgeMapService
if not getattr(KnowledgeMapService, '_room_test_installed', False):
    def install(original):
        def execute(self, payload):
            result = original(self, payload)
            if payload.get('action') == 'save_note' and result.get('status') == 'saved' and not st.session_state.get('_room_lost_ack'):
                st.session_state['_room_lost_ack'] = True
                return {'operation_id': payload['operation_id'], 'status': 'uncertain', 'message': 'Respuesta perdida de prueba; reconciliar el mismo intento.'}
            return result
        return execute
    KnowledgeMapService.execute = install(KnowledgeMapService.execute)
    KnowledgeMapService._room_test_installed = True
runpy.run_path(""" + repr(str(ROOT / 'editor/editor_streamlit.py')) + """, run_name='__main__')
""")
            with (evidence / f"{phase}-application.log").open("w") as log:
                app = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "streamlit",
                        "run",
                        str(wrapper),
                        "--server.address=127.0.0.1",
                        f"--server.port={app_port}",
                        "--server.headless=true",
                        "--server.fileWatcherType=none",
                        "--browser.gatherUsageStats=false",
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                url = f"http://127.0.0.1:{app_port}"
                for _ in range(100):
                    try:
                        with urlopen(url + "/_stcore/health", timeout=0.3):
                            break
                    except OSError:
                        time.sleep(0.1)
                browser_env = dict(
                    env,
                    MATHMONGO_MAP_TEST_URL=url,
                    MATHMONGO_MAP_TEST_EVIDENCE=str(evidence),
                    MATHMONGO_STUDY_PHASE=phase,
                    MATHMONGO_STUDY_BROWSER=browser_name,
                    MATHMONGO_STUDY_SCENARIO="room" if room_scenario else "sphere",
                    MATHMONGO_ROOM_MARK_ID=room_mark.annotation_id if room_mark else "",
                    MATHMONGO_STUDY_PRIVATE_KEY=(str(metadata["id"]) + "@" + metadata["source"]) if private.exists() else "",
                )
                command = [
                    "node",
                    "node_modules/@playwright/test/cli.js",
                    "test",
                    "--config=tests/study-sphere-playwright.config.mjs",
                ]
                with (evidence / f"{phase}-browser.log").open("w") as browser_log:
                    result = subprocess.run(
                        command,
                        cwd=ROOT / "frontend/advanced-reader",
                        env=browser_env,
                        stdout=browser_log,
                        stderr=subprocess.STDOUT,
                        timeout=240,
                    )
                if result.returncode:
                    raise RuntimeError(f"{phase} browser failed; inspect private evidence")
                if room_scenario:
                    assert db.reading_notes.count_documents({"title":"Nota desde el paper"}) == 1
                    note=db.reading_notes.find_one({'title':'Nota desde el paper'})
                    concept=db.concepts.find_one({'titulo':'Concepto desde la nota'})
                    assert concept is not None and db.concepts.count_documents({'titulo':'Concepto desde la nota'})==1
                    key=concept['id']+'@'+concept['source']
                    assert sum(key in v['study_view']['members'] for v in db.knowledge_graph_maps.find({'study_view.version':1}))==2
                    assert sum(g.get('conceptKey')==key for v in db.knowledge_graph_maps.find({'study_view.version':1}) for g in v['study_view'].get('goals',[]))==1
                    assert note['reference_locator']['printed_page']=='xii' and note['reference_locator']['pdf_page']==2
                    assert db.concept_evidence_links.count_documents({'concept_legacy_id':concept['id'],'note_id':note['note_id']})==1
                    assert db.concept_evidence_links.count_documents({'concept_legacy_id':concept['id'],'annotation_id':room_mark.annotation_id})==1
                    assert 'searchable theorem beta' in note['body'] and '\\frac' in note['body']

                if phase == "after" and not room_scenario:
                    created = db.concepts.find_one({"titulo": "Concepto visual confirmado"})
                    assert created is not None
                    body = db.latex_documents.find_one(
                        {"id": created["id"], "source": created["source"]}
                    )["contenido_latex"]
                    assert "\\frac" in body and "pmatrix" in body
                    exported = {**created, 'contenido_latex': body}
                    exported.pop('_id', None)
                    (evidence / 'visual-concept.json').write_text(json.dumps(exported, default=str, ensure_ascii=False, indent=2)+'\n')
                    if '--export' in sys.argv:
                        export_code = (
                            'import json,sys;from pathlib import Path;from editor.pdf_export import generar_pdf_concepto,_generar_latex_content;'
                            'p=Path(sys.argv[1]);c=json.loads((p/"visual-concept.json").read_text());'
                            '(p/"visual-concept.tex").write_text(_generar_latex_content(c));'
                            'generar_pdf_concepto(c,sys.argv[2])'
                        )
                        subprocess.run([sys.executable, '-c', export_code, str(evidence), str(work / 'visual-concept.pdf')], cwd=ROOT, env=env, check=True, timeout=120)
                        shutil.copyfile(work / 'visual-concept.pdf', evidence / 'visual-concept.pdf')

                    assert created['reference_id'] == existing_reference.reference_id
                    assert created['reference_locator']['printed_page'] == '229'
                    assert created['reference_locator']['pdf_page'] == 3
                    assert db.references.count_documents({}) == 1
                    stored_reference = db.references.find_one({'reference_id': existing_reference.reference_id})
                    assert stored_reference['title'] == existing_reference.title
                    assert stored_reference['bibtex']['key'] == 'NyagaClaveEstable'
                    assert (
                        db.concepts.count_documents({"titulo": "Concepto visual confirmado"}) == 1
                    )
                    if private.exists():
                        assert (
                            db.latex_documents.find_one(
                                {"id": content["id"], "source": content["source"]}
                            )["contenido_latex"]
                            == content["contenido_latex"]
                        )
                    assert db.concepts.find_one({"id": "nota:slow"})["custom"] == {"preserve": True}
                    (evidence / "persistence.json").write_text(
                        json.dumps(
                            {
                                "concept_once": True,
                                "fraction_matrix_persisted": True,
                                "private_legacy_bytes_preserved": private.exists(),
                                "owned_database": True,
                            },
                            indent=2,
                        )
                        + "\n"
                    )
        finally:
            try:
                if app is not None:
                    app.terminate()
                    try:
                        app.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        app.kill()
                        app.wait(timeout=5)
                if advanced is not None:
                    advanced.terminate()
                    try:
                        advanced.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        advanced.kill()
                        advanced.wait(timeout=5)
                if advanced_log is not None:
                    advanced_log.close()
                client.drop_database(name)
                assert not (set(client.list_database_names()) - {"admin", "local", "config"})
            finally:
                client.close()
                mongo.terminate()
                try:
                    mongo.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    mongo.kill()
                    mongo.wait(timeout=5)


if __name__ == "__main__":
    main()

"""Exercise the actual MathMongo application with owned MongoDB/XDG/ports only."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from mathmongo.source_catalog.models import Source

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main() -> None:
    evidence = ROOT / 'evidence/sonar/sphere-2026-11'
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='mathmongo-map-browser-') as directory:
        work = Path(directory)
        dbpath = work / 'mongo'; dbpath.mkdir()
        mongo_port, web_port = free_port(), free_port()
        env = dict(os.environ)
        for k in ('MONGO_URI', 'MONGO_DB', 'DB_NAME'):
            env.pop(k, None)
        name = 'mathmongo_map_browser_' + uuid4().hex
        uri = f'mongodb://127.0.0.1:{mongo_port}'
        env.update(MONGODB_URI=uri, MONGODB_DB=name, PYTHONPATH=str(ROOT), STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
        for kind in ('CONFIG', 'DATA', 'CACHE', 'STATE'):
            env[f'XDG_{kind}_HOME'] = str(work / kind.lower())
        mongod = subprocess.Popen([shutil.which('mongod'), '--dbpath', str(dbpath), '--port', str(mongo_port), '--bind_ip', '127.0.0.1', '--nounixsocket'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = MongoClient(uri, serverSelectionTimeoutMS=150)
        app = None
        try:
            for _ in range(100):
                if mongod.poll() is not None:
                    raise RuntimeError('Owned MongoDB exited')
                try:
                    client.admin.command('ping'); break
                except ConnectionFailure:
                    time.sleep(.1)
            assert client.admin.command('serverStatus')['pid'] == mongod.pid
            database = client[name]
            source = Source(name='Mapa de prueba · Álgebra')
            database.sources.insert_one(source.model_dump(mode='python'))
            database.concepts.insert_one({'id': 'nota:semilla', 'source': source.name, 'source_id': source.source_id, 'titulo': 'Idea semilla', 'tipo': 'nota', 'categorias': [], 'image_ids': ['shared-test'], 'custom': {'preserve': True}})
            database.latex_documents.insert_one({'id': 'nota:semilla', 'source': source.name, 'contenido_latex': '$G$ es un grupo.'})
            with (evidence / 'application.log').open('w') as log:
                app = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', 'editor/editor_streamlit.py', '--server.address=127.0.0.1', f'--server.port={web_port}', '--server.headless=true', '--browser.gatherUsageStats=false'], cwd=ROOT, env=env, stdout=log, stderr=log)
                url = f'http://127.0.0.1:{web_port}'
                for _ in range(100):
                    if app.poll() is not None:
                        raise RuntimeError('Owned Streamlit exited; see private application.log')
                    try:
                        with urllib.request.urlopen(url + '/_stcore/health', timeout=.3):
                            break
                    except OSError:
                        time.sleep(.1)
                browser_env = dict(env, MATHMONGO_MAP_TEST_URL=url, MATHMONGO_MAP_TEST_EVIDENCE=str(evidence))
                browser_command = ['node', 'node_modules/@playwright/test/cli.js', 'test', '--config=tests/knowledge-map-playwright.config.mjs']
                result = subprocess.run(browser_command, cwd=ROOT / 'frontend/advanced-reader', env=browser_env, text=True, capture_output=True, timeout=180)
                (evidence / 'browser.log').write_text(result.stdout + result.stderr)
                if result.returncode:
                    raise RuntimeError('Browser verification failed; see private browser.log')
                created = database.concepts.find_one({'titulo': 'Grupo editado desde la esfera'})
                assert created is not None
                content = database.latex_documents.find_one({'id': created['id'], 'source': created['source']})
                assert content['contenido_latex'] == r'$G \times G \to G$; edición persistida.'
                assert database.relations.count_documents({}) == 2
                seed = database.concepts.find_one({'id': 'nota:semilla'})
                assert seed['image_ids'] == ['shared-test'] and seed['custom'] == {'preserve': True}
                summary = {'ok': True, 'concepts': database.concepts.count_documents({}), 'relations': database.relations.count_documents({}), 'persisted_content': True, 'extra_metadata_preserved': True, 'database_was_owned': True}
                (evidence / 'persistence.json').write_text(json.dumps(summary, indent=2) + '\n')
                print(result.stdout.strip()); print(json.dumps(summary))
                concepts = [{'id': f'nota:perf_{i}', 'source': source.name, 'tipo': 'nota', 'titulo': f'Concepto temporal {i}', 'categorias': []} for i in range(1000)]
                database.concepts.insert_many(concepts)
                database.latex_documents.insert_many([{'id': d['id'], 'source': source.name, 'contenido_latex': '$x$'} for d in concepts])
                edges = [{'desde': f"nota:perf_{i}@{source.name}", 'hasta': f"nota:perf_{i + step}@{source.name}", 'tipo': 'implica'} for step in (1, 2) for i in range(1000 - step)]
                database.relations.insert_many(edges)
                performance = subprocess.run(browser_command, cwd=ROOT / 'frontend/advanced-reader', env=dict(browser_env, MATHMONGO_MAP_TEST_MODE='performance'), text=True, capture_output=True, timeout=180)
                (evidence / 'performance.log').write_text(performance.stdout + performance.stderr)
                if performance.returncode:
                    raise RuntimeError('Real-browser performance verification failed; see private performance.log')
                print(performance.stdout.strip())
        finally:
            if app is not None:
                app.terminate()
                try:
                    app.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    app.kill(); app.wait(timeout=5)
            try:
                client.drop_database(name)
                assert not (set(client.list_database_names()) - {'admin', 'local', 'config'})
            finally:
                client.close()
                mongod.terminate()
                try:
                    mongod.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    mongod.kill(); mongod.wait(timeout=5)


if __name__ == '__main__':
    main()

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
            with (evidence / f"{phase}-application.log").open("w") as log:
                app = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "streamlit",
                        "run",
                        "editor/editor_streamlit.py",
                        "--server.address=127.0.0.1",
                        f"--server.port={app_port}",
                        "--server.headless=true",
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
                if phase == "after":
                    created = db.concepts.find_one({"titulo": "Concepto visual confirmado"})
                    assert created is not None
                    body = db.latex_documents.find_one(
                        {"id": created["id"], "source": created["source"]}
                    )["contenido_latex"]
                    assert "\\frac" in body and "pmatrix" in body
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

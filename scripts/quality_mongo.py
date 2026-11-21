"""Run opt-in E2E tests against an owned, disposable standalone mongod."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS = ["tests/test_audit_mongo_regressions.py", "tests/test_database_update_e2e.py",
                 "tests/test_fresh_database_lifecycle_e2e.py", "tests/test_legacy_concept_source_link_e2e.py"]


def main() -> int:
    """Keep every write away from the user's MongoDB process and filesystem."""
    executable = shutil.which("mongod")
    if executable is None:
        raise SystemExit("mongod is required; no user MongoDB fallback is permitted")
    with TemporaryDirectory(prefix="mathmongo-audit-mongo-") as directory:
        root = Path(directory)
        database_path = root / "db"
        database_path.mkdir()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        uri = f"mongodb://127.0.0.1:{port}"
        process = subprocess.Popen(
            [executable, "--dbpath", str(database_path), "--bind_ip", "127.0.0.1",
             "--port", str(port), "--nounixsocket", "--logpath", str(root / "mongod.log")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        client = MongoClient(uri, serverSelectionTimeoutMS=200, connectTimeoutMS=200)
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Owned mongod exited before becoming ready")
                try:
                    client.admin.command("ping")
                    break
                except ConnectionFailure:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Owned mongod did not become ready") from None
                    time.sleep(0.1)
            assert set(client.list_database_names()) <= {"admin", "config", "local"}
            print(f"Owned standalone MongoDB: {uri}; dbpath={database_path}", flush=True)
            environment = dict(os.environ)
            for name in ("MONGO_URI", "MONGO_DB", "DB_NAME"):
                environment.pop(name, None)
            environment.update(MONGODB_URI=uri, MONGODB_DB="mathmongo_audit_unused",
                               MATHMONGO_RUN_MONGO_E2E="1", MATHMONGO_RUN_FRESH_DB_E2E="1",
                               MATHMONGO_RUN_LEGACY_LINK_E2E="1")
            for kind in ("CONFIG", "DATA", "STATE", "CACHE"):
                environment[f"XDG_{kind}_HOME"] = str(root / kind.lower())
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-s",
                                     *(sys.argv[1:] or DEFAULT_TESTS)], cwd=ROOT,
                                    env=environment, check=False)
            remaining = set(client.list_database_names()) - {"admin", "config", "local"}
            if remaining:
                raise RuntimeError(f"Test databases were not removed: {sorted(remaining)}")
            return result.returncode
        finally:
            client.close()
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())

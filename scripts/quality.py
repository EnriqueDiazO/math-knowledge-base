"""Run the real Python suite with coverage and private, temporary application paths."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Keep unit checks independent from user MongoDB and XDG configuration."""
    (ROOT / "evidence/sonar").mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="mathmongo-quality-") as directory:
        environment = dict(os.environ)
        for kind in ("CONFIG", "DATA", "STATE", "CACHE"):
            environment[f"XDG_{kind}_HOME"] = str(Path(directory) / kind.lower())
        for name in ("MONGO_URI", "MONGO_DB", "DB_NAME"):
            environment.pop(name, None)
        environment.update(
            MONGODB_URI="mongodb://127.0.0.1:27999",
            MONGODB_DB="mathmongo_audit_unit",
            MATHMONGO_RUN_MONGO_E2E="0",
            MATHMONGO_RUN_FRESH_DB_E2E="0",
            MATHMONGO_RUN_LEGACY_LINK_E2E="0",
        )
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--cov", "--cov-report=xml",
             "--cov-report=term:skip-covered", "--junitxml=evidence/sonar/pytest.xml", *sys.argv[1:]],
            cwd=ROOT, env=environment, check=False,
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

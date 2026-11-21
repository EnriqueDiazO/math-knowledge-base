"""Run the real Python suite with coverage and private, temporary application paths."""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Keep unit checks independent from user MongoDB and XDG configuration."""
    (ROOT / "evidence/sonar").mkdir(parents=True, exist_ok=True)
    # coverage serializes source paths for children, but not relative omit paths.
    # Anchor the existing scope so a CLI changing cwd cannot measure the venv.
    configuration = configparser.ConfigParser(interpolation=None)
    with (ROOT / ".coveragerc").open() as handle:
        configuration.read_file(handle)
    configuration.set("run", "source", str(ROOT))
    original_omit = configuration.get("run", "omit").split()
    configuration.set("run", "omit", "\n".join(str(ROOT / pattern) for pattern in original_omit))
    runtime_config = ROOT / "evidence/sonar/coverage-runtime.ini"
    with runtime_config.open("w") as handle:
        configuration.write(handle)
    arguments = sys.argv[1:]
    with_mongo = "--with-mongo" in arguments
    arguments = [argument for argument in arguments if argument != "--with-mongo"]
    with TemporaryDirectory(prefix="mathmongo-quality-") as directory:
        environment = dict(os.environ)
        environment["COVERAGE_FILE"] = str(ROOT / ".coverage")
        environment["COVERAGE_RCFILE"] = str(runtime_config)
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
             "--basetemp", str(Path(directory) / "pytest"),
             "--cov-report=term:skip-covered", "--junitxml=evidence/sonar/pytest.xml", *arguments],
            cwd=ROOT, env=environment, check=False,
        )
        if result.returncode or not with_mongo:
            return result.returncode
        shutil.copyfile(ROOT / "evidence/sonar/coverage.xml", ROOT / "evidence/sonar/coverage-unit.xml")
        result = subprocess.run(
            [sys.executable, "-m", "coverage", "run", "--parallel-mode", "scripts/quality_mongo.py"],
            cwd=ROOT, env=environment, check=False,
        )
        if result.returncode:
            return result.returncode
        for command in (("combine", "--append"), ("xml",)):
            subprocess.run([sys.executable, "-m", "coverage", *command],
                           cwd=ROOT, env=environment, check=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

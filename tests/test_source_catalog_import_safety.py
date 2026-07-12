"""Regression coverage for side-effect-free Source Catalog imports."""

# ruff: noqa: D103

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _snapshot(roots: list[Path]) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if path.is_file():
                stat = path.stat()
                snapshot[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def test_source_catalog_imports_write_neither_home_checkout_nor_site_packages(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    checkout_roots = [project_root / "mathmongo/source_catalog"]
    site_roots: list[Path] = []
    for loaded_name in ("pydantic", "pymongo", "bson", "bibtexparser"):
        module = __import__(loaded_name)
        module_file = getattr(module, "__file__", None)
        if module_file:
            site_roots.append(Path(module_file).resolve().parent)
    checkout_before = _snapshot(checkout_roots)
    site_before = _snapshot(site_roots)

    working = tmp_path / "empty-cwd"
    working.mkdir()
    home = tmp_path / "home"
    xdg_paths = {
        "XDG_CONFIG_HOME": tmp_path / "config",
        "XDG_DATA_HOME": tmp_path / "data",
        "XDG_CACHE_HOME": tmp_path / "cache",
        "XDG_STATE_HOME": tmp_path / "state",
    }
    environment = os.environ.copy()
    python_path = os.pathsep.join(
        dict.fromkeys([str(project_root), *(str(root.parent) for root in site_roots)])
    )
    environment.update(
        {
            "HOME": str(home),
            "PYTHONPATH": python_path,
            "PYTHONDONTWRITEBYTECODE": "1",
            **{name: str(path) for name, path in xdg_paths.items()},
        }
    )
    code = (
        "import mathmongo.source_catalog; "
        "import mathmongo.source_catalog.bibtex; "
        "import mathmongo.source_catalog.duplicates; "
        "import mathmongo.source_catalog.indexes; "
        "import mathmongo.source_catalog.legacy; "
        "import mathmongo.source_catalog.models; "
        "import mathmongo.source_catalog.normalization; "
        "import mathmongo.source_catalog.repository; "
        "import mathmongo.source_catalog.service"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=working,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert list(working.iterdir()) == []
    assert not home.exists()
    assert all(not path.exists() for path in xdg_paths.values())
    assert _snapshot(checkout_roots) == checkout_before
    assert _snapshot(site_roots) == site_before

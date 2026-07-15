"""Focused import, build-artifact, and package-manifest tests for S5A."""

# ruff: noqa: D103

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 in the project environment.
    import tomli as tomllib


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPOSITORY_ROOT / "frontend" / "advanced-reader"
STATIC_ROOT = REPOSITORY_ROOT / "mathmongo" / "advanced_reader" / "static" / "advanced_reader"
PDFJS_VERSION = "6.1.200"
PDFJS_ASSET_INVENTORIES = {
    "cmaps": (169, "95e459bcb13faa8998861ebf9954a86ac2ec362342318cef04ad67d38bfcc4d7"),
    "standard_fonts": (
        16,
        "73e5de7c412df8ddaa70bad216fd9dc53b2af875cdbd0f8ece6ede4743a5ac9b",
    ),
    "iccs": (2, "8fd90bf5a81a9b10ea806bc1a50d878dc063e1439026a335853579e1ab544d3d"),
    "wasm": (11, "10c87199f10de4a521ef246d65adb3b011706c14e06f1de8ebb99b64dc4e85ed"),
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _filename_inventory_sha256(directory: Path) -> str:
    names = sorted(item.name for item in directory.iterdir())
    return hashlib.sha256(("\n".join(names) + "\n").encode()).hexdigest()


def test_advanced_reader_import_is_offline_and_creates_no_xdg_or_home_state(
    tmp_path: Path,
) -> None:
    isolated_home = tmp_path / "HOME must remain absent"
    data_home = tmp_path / "xdg data must remain absent"
    config_home = tmp_path / "xdg config must remain absent"
    cache_home = tmp_path / "xdg cache must remain absent"
    probe = """
import pathlib
import socket
import pymongo

def denied(*args, **kwargs):
    raise AssertionError("network access attempted during import")

socket.create_connection = denied
socket.socket = denied
pymongo.MongoClient = denied

import mathmongo.advanced_reader
import mathmongo.advanced_reader.app
import mathmongo.advanced_reader.dependencies
import mathmongo.advanced_reader.document_access
import mathmongo.advanced_reader.launcher
import mathmongo.advanced_reader.range_requests
import mathmongo.advanced_reader.routes
import mathmongo.advanced_reader.schemas
import mathmongo.advanced_reader.security

for value in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
    assert not pathlib.Path(__import__("os").environ[value]).exists(), value
print("offline-import-ok")
"""
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(isolated_home),
            "XDG_DATA_HOME": str(data_home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_CACHE_HOME": str(cache_home),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "offline-import-ok"
    assert completed.stderr == ""
    assert not isolated_home.exists()
    assert not data_home.exists()
    assert not config_home.exists()
    assert not cache_home.exists()


def test_python_package_declares_bounded_runtime_dependencies_and_static_assets() -> None:
    project = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    poetry = project["tool"]["poetry"]
    dependencies = poetry["dependencies"]
    include_entries = poetry["include"]

    assert dependencies["fastapi"] == ">=0.115,<1.0"
    assert dependencies["uvicorn"] == ">=0.34,<1.0"
    assert dependencies["python"] == ">=3.10,<3.14"
    assert {
        "path": "mathmongo/advanced_reader/static/**",
        "format": ["sdist", "wheel"],
    } in include_entries
    assert {
        "path": "docs/ADVANCED_READER_CONCEPT_LINKING_S5C.md",
        "format": ["sdist", "wheel"],
    } in include_entries


def test_python_package_contains_the_explicit_factory_and_module_launcher() -> None:
    package = REPOSITORY_ROOT / "mathmongo" / "advanced_reader"
    expected_modules = {
        "__init__.py",
        "__main__.py",
        "app.py",
        "concept_evidence.py",
        "concept_routes.py",
        "concept_schemas.py",
        "concept_search.py",
        "dependencies.py",
        "document_access.py",
        "launcher.py",
        "range_requests.py",
        "routes.py",
        "schemas.py",
        "security.py",
        "streamlit_link.py",
    }
    assert expected_modules <= {item.name for item in package.glob("*.py")}
    entrypoint = (package / "__main__.py").read_text(encoding="utf-8")
    assert "mathmongo.advanced_reader.launcher import main" in entrypoint
    assert "SystemExit(main())" in entrypoint

    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"(?m)^advanced-reader:\s*$", makefile)
    assert "mathdbmongo/bin/python -m mathmongo.advanced_reader" in makefile


def test_frontend_manifest_has_reproducible_pinned_runtime_and_build_commands() -> None:
    package = _load_json(FRONTEND_ROOT / "package.json")
    assert package["private"] is True
    assert package["type"] == "module"
    assert package["packageManager"] == "npm@11.12.1"
    assert package["dependencies"] == {
        "pdfjs-dist": "6.1.200",
        "react": "19.2.7",
        "react-dom": "19.2.7",
    }
    scripts = package["scripts"]
    for required in ("dev", "typecheck", "lint", "test", "build"):
        assert required in scripts
    assert "vite --host 127.0.0.1" in scripts["dev"]
    assert "vite build" in scripts["build"]
    assert "publish-build.mjs" in scripts["build"]
    for command in scripts.values():
        assert "npx " not in command
        assert "npm install" not in command


def test_npm_lock_matches_direct_dependencies_and_pins_registry_integrity() -> None:
    package = _load_json(FRONTEND_ROOT / "package.json")
    lock = _load_json(FRONTEND_ROOT / "package-lock.json")

    assert lock["lockfileVersion"] == 3
    root = lock["packages"][""]
    assert root["dependencies"] == package["dependencies"]
    assert root["devDependencies"] == package["devDependencies"]
    for name, version in package["dependencies"].items():
        locked = lock["packages"][f"node_modules/{name}"]
        assert locked["version"] == version

    registry_packages = [
        value
        for key, value in lock["packages"].items()
        if key and isinstance(value, dict) and "resolved" in value
    ]
    assert registry_packages
    for locked in registry_packages:
        assert str(locked["resolved"]).startswith("https://registry.npmjs.org/")
        assert str(locked.get("integrity", "")).startswith(("sha512-", "sha256-"))


def test_packaged_frontend_has_hashed_local_runtime_worker_and_notices() -> None:
    assert STATIC_ROOT.is_dir()
    index = STATIC_ROOT / "index.html"
    assert index.is_file()
    files = [item for item in STATIC_ROOT.rglob("*") if item.is_file()]
    assert files
    assert all(not item.is_symlink() for item in files)

    assets = STATIC_ROOT / "assets"
    javascript = sorted([*assets.glob("*.js"), *assets.glob("*.mjs")])
    stylesheets = sorted(assets.glob("*.css"))
    workers = [item for item in javascript if "worker" in item.name.casefold()]
    hashed_name = re.compile(r".+-[A-Za-z0-9_-]{8,}\.(?:css|m?js)$")
    assert javascript and stylesheets and workers
    assert all(hashed_name.fullmatch(item.name) for item in javascript + stylesheets)

    notices = STATIC_ROOT / "third-party"
    expected_notices = {
        "THIRD_PARTY_NOTICES.txt",
        "pdfjs-LICENSE.txt",
        "react-LICENSE.txt",
        "react-dom-LICENSE.txt",
    }
    assert expected_notices <= {item.name for item in notices.iterdir() if item.is_file()}

    html = index.read_text(encoding="utf-8")
    assert re.search(r'(?:src|href)="/assets/[^" ]+-[A-Za-z0-9_-]{8,}\.(?:css|m?js)"', html)
    assert '<script type="module"' in html
    assert "/src/" not in html
    assert "http://" not in html and "https://" not in html
    assert "file://" not in html and "mongodb://" not in html


def test_packaged_pdfjs_auxiliary_assets_are_local_versioned_and_allowlisted() -> None:
    assets = STATIC_ROOT / "assets"
    pdfjs_root = assets / f"pdfjs-{PDFJS_VERSION}"
    assert pdfjs_root.is_dir() and not pdfjs_root.is_symlink()
    assert {item.name for item in assets.iterdir() if item.is_dir()} == {pdfjs_root.name}
    assert {item.name for item in pdfjs_root.iterdir() if item.is_dir()} == set(
        PDFJS_ASSET_INVENTORIES
    )

    for directory_name, (expected_count, expected_digest) in PDFJS_ASSET_INVENTORIES.items():
        directory = pdfjs_root / directory_name
        entries = list(directory.iterdir())
        assert len(entries) == expected_count
        assert all(item.is_file() and not item.is_symlink() for item in entries)
        assert _filename_inventory_sha256(directory) == expected_digest

    wasm_names = {item.name for item in (pdfjs_root / "wasm").iterdir()}
    assert {
        "jbig2.wasm",
        "jbig2_nowasm_fallback.js",
        "openjpeg.wasm",
        "openjpeg_nowasm_fallback.js",
        "qcms_bg.wasm",
    } <= wasm_names
    assert all("quickjs" not in item.name.casefold() for item in pdfjs_root.rglob("*"))

    preparation = (FRONTEND_ROOT / "scripts" / "prepare-pdf-worker.mjs").read_text(encoding="utf-8")
    vite_configuration = (FRONTEND_ROOT / "vite.config.ts").read_text(encoding="utf-8")
    publisher = (FRONTEND_ROOT / "scripts" / "publish-build.mjs").read_text(encoding="utf-8")
    assert f'const PDFJS_VERSION = "{PDFJS_VERSION}"' in preparation
    assert f'const PDFJS_VERSION = "{PDFJS_VERSION}"' in publisher
    assert 'publicDir: "generated/public"' in vite_configuration


def test_packaged_frontend_publication_leaves_no_staging_or_backup_tree() -> None:
    static_parent = STATIC_ROOT.parent
    assert not tuple(static_parent.glob(f"{STATIC_ROOT.name}.publish-*"))
    assert not tuple(static_parent.glob(f"{STATIC_ROOT.name}.backup-*"))


def test_packaged_static_tree_excludes_development_user_and_sensitive_artifacts() -> None:
    forbidden_directory_names = {
        ".cache",
        ".git",
        ".vite",
        "coverage",
        "node_modules",
        "src",
        "tests",
    }
    forbidden_suffixes = {".env", ".log", ".map", ".pdf", ".zip"}
    forbidden_names = {"package.json", "package-lock.json", "tsconfig.json"}
    files: list[Path] = []
    for item in STATIC_ROOT.rglob("*"):
        assert item.name not in forbidden_directory_names
        if item.is_file():
            files.append(item)
            assert item.name not in forbidden_names
            assert item.suffix.casefold() not in forbidden_suffixes

    assert files
    runtime_files = [item for item in files if "third-party" not in item.parts]
    forbidden_fragments = (
        "cdn.jsdelivr.net",
        "cdnjs.cloudflare.com",
        "unpkg.com",
        "fonts.googleapis.com",
        "google-analytics.com",
        "segment.io",
        "mongodb://",
        "file://",
        "/home/",
        "c:\\users\\",
        "super-secret",
    )
    for item in runtime_files:
        if item.suffix.casefold() not in {".html", ".js", ".mjs", ".css", ".txt"}:
            continue
        content = item.read_text(encoding="utf-8", errors="ignore").casefold()
        for forbidden in forbidden_fragments:
            assert (
                forbidden not in content
            ), f"{forbidden!r} leaked into {item.relative_to(STATIC_ROOT)}"


def test_third_party_document_records_runtime_versions_licenses_and_offline_policy() -> None:
    document = (REPOSITORY_ROOT / "docs" / "THIRD_PARTY_ADVANCED_READER.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "FastAPI",
        "Uvicorn",
        "Starlette",
        "React",
        "React DOM",
        "pdfjs-dist",
        "19.2.7",
        "6.1.200",
        "Apache-2.0",
        "BSD-3-Clause",
        "MIT",
        "package-lock.json",
        "No se usa CDN",
        "node_modules",
    ):
        assert required in document

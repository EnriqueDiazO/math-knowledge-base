"""Build an offline React/Python AppDir, using explicit verified packaging tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging/react-appimage"
OWN_DIRECTORIES = {
    "mathmongo",
    "editor",
    "exporters_latex",
    "mathdatabase",
    "schemas",
    "parsers",
    "templates_latex",
    "assets/icons",
}
OWN_FILES = {"mathkb_config.py", "LICENSE"}
TOOL_SHA256 = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
RUNTIME_SHA256 = "617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46"


def verified_tool(path, expected):
    """Require pinned bytes before executing an external packaging program."""
    path = Path(path).resolve(strict=True)
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("La herramienta de empaquetado no coincide con la huella fijada.")
    return path


def copy_vendor(destination, versions):
    """Copy declared distributions and licenses, never scripts, pth hooks or user state."""
    for name, expected in versions.items():
        installed = distribution(name)
        if installed.version != expected:
            raise ValueError(f"Versión incompatible para {name}: se requiere {expected}.")
        for item in installed.files or ():
            relative = Path(str(item))
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or relative.suffix in {".pyc", ".pth"}
            ):
                continue
            source = Path(installed.locate_file(item))
            if source.is_file():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)


def copy_application(destination):
    """Allow only tracked source/resources; exclude evidence, credentials and databases."""
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    included = []
    for name in filter(None, names):
        if name not in OWN_FILES and not any(
            name.startswith(prefix + "/") for prefix in OWN_DIRECTORIES
        ):
            continue
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise ValueError("El recurso rastreado no es un archivo regular: " + name)
        if (
            source.suffix in {".pyc", ".zip", ".pdf", ".local", ".map"}
            or "__pycache__" in source.parts
        ):
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        included.append(name)
    return included


def prepare_appdir(destination, python_runtime):
    """Stage a new owned directory, retaining the existing application/service contracts."""
    if destination.exists():
        raise ValueError("El AppDir de destino ya existe; no se sobrescribió.")
    runtime = Path(python_runtime).resolve(strict=True)
    if (runtime / "pyvenv.cfg").exists() or not (runtime / "bin/python3.13").is_file():
        raise ValueError("Proporciona el runtime CPython portable 3.13, no un entorno virtual.")
    if any(
        path.is_symlink() and not path.resolve().is_relative_to(runtime)
        for path in runtime.rglob("*")
    ):
        raise ValueError("El runtime contiene enlaces fuera de su directorio; no es portable.")
    destination.mkdir(parents=True)
    shutil.copytree(
        runtime,
        destination / "python",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "site-packages"),
    )
    versions = json.loads((PACKAGING / "runtime.lock.json").read_text())
    copy_vendor(destination / "vendor", versions)
    included = copy_application(destination / "app")
    for name in ("AppRun", "bootstrap.py", "mathmongo-study.desktop"):
        shutil.copyfile(PACKAGING / name, destination / name)
    (destination / "AppRun").chmod(0o755)
    shutil.copyfile(ROOT / "assets/icons/mathmongo-256.png", destination / "mathmongo-study.png")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {
        "revision": revision,
        "python": sys.version.split()[0],
        "dependencies": versions,
        "mongo_management": "external",
        "application_files": included,
    }
    (destination / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    """Use existing destinations only as parents; no cleaning, installation or service changes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-runtime", required=True, type=Path)
    parser.add_argument("--appimagetool", required=True, type=Path)
    parser.add_argument("--runtime-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    tool = verified_tool(args.appimagetool, TOOL_SHA256)
    runtime = verified_tool(args.runtime_file, RUNTIME_SHA256)
    output = args.output.resolve()
    if output.exists():
        raise ValueError("La AppImage de destino ya existe; no se sobrescribió.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mathmongo-appimage-") as temporary:
        directory = Path(temporary) / "MathMongo.AppDir"
        prepare_appdir(directory, args.python_runtime)
        subprocess.run(
            [
                str(tool),
                "--appimage-extract-and-run",
                "--runtime-file",
                str(runtime),
                "--no-appstream",
                str(directory),
                str(output),
            ],
            env=dict(os.environ, ARCH="x86_64"),
            check=True,
            timeout=300,
        )
    print(
        json.dumps(
            {
                "path": str(output),
                "sha256": hashlib.file_digest(output.open("rb"), "sha256").hexdigest(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

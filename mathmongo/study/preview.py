"""Content-addressed figure previews; cache entries contain only disposable output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from exporters_latex import sandbox
from mathmongo.paths import get_cache_dir
from mathmongo.paths import validate_mutable_path
from mathmongo.study.document_export import compile_project
from mathmongo.study.document_export import compose_project

CACHE_BYTES = 256 * 1024 * 1024
CACHE_ENTRIES = 128


def valid_cached_output(path, magic):
    """A truncated or missing file is a cache miss, not a completed preview."""
    try:
        if not 0 < path.stat().st_size <= 16_777_216:
            return False
        with path.open("rb") as handle:
            return handle.read(len(magic)) == magic
    except OSError:
        return False


def atomic_output(path, content):
    """A killed compiler or concurrent request cannot publish a partial image."""
    validate_mutable_path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


class DocumentPreviews:
    """The library, engine, templates, macros and sandbox policy scope every key."""

    def __init__(self, library, *, root=None):
        """Construct without creating cache directories or compiling anything."""
        self.root = (root or get_cache_dir() / "document-previews") / hashlib.sha256(
            library.encode()
        ).hexdigest()

    def key(self, source, macros, *, kind="figure", title="Documento"):
        """Never reuse output after relevant source, template or compiler changes."""
        digest = hashlib.sha256(json.dumps([source, macros, kind, title]).encode())
        for path in [
            Path(__file__),
            Path(sandbox.__file__),
            Path(__file__).with_name("document_export.py"),
            Path(sandbox.__file__).with_name("unified_document.py"),
            *sorted(sandbox.TEMPLATES.glob("*.sty")),
            *sorted(sandbox.TEMPLATES.glob("*.cls")),
        ]:
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        engine = shutil.which("pdflatex")
        if engine:
            digest.update(Path(engine).read_bytes())
        return digest.hexdigest()

    def output(self, identifier, extension):
        """Only this library's hash filenames can be opened; no client paths."""
        if not re.fullmatch(r"[a-f0-9]{64}", identifier) or extension not in {"pdf", "png"}:
            raise ValueError("Invalid preview identity")
        return validate_mutable_path(self.root / f"{identifier}.{extension}")

    def create(self, source, macros="", *, refresh=False, kind="figure", title="Documento"):
        """Compile an explicit immutable draft snapshot, without publishing any record."""
        identifier = self.key(source, macros, kind=kind, title=title)
        png, pdf = self.output(identifier, "png"), self.output(identifier, "pdf")
        if (
            not refresh
            and valid_cached_output(png, b"\x89PNG\r\n\x1a\n")
            and valid_cached_output(pdf, b"%PDF-")
        ):
            return {
                "state": "ready",
                "preview_id": identifier,
                "cached": True,
                "message": "Vista previa recuperada. El código original se conserva.",
            }
        result = self._compile(source, macros, kind=kind, title=title)
        if result.status != "ready":
            return {
                "state": result.status,
                "message": result.message,
                "diagnostic": result.diagnostic,
            }
        self.root = validate_mutable_path(self.root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        atomic_output(pdf, result.pdf)
        atomic_output(png, result.png)
        self._prune({png, pdf})
        return {
            "state": "ready",
            "preview_id": identifier,
            "cached": False,
            "message": "Vista compilada de la instantánea solicitada. No se ha guardado el documento.",
        }

    @staticmethod
    def _compile(source, macros, *, kind, title):
        if kind == "document":
            bundle = compose_project([{"titulo": title, "contenido_latex": source}], title)
            return compile_project(bundle, raster=True)
        return sandbox.compile_document(
            "\n".join(
                [
                    r"\documentclass{article}",
                    r"\usepackage{notes}",
                    r"\usepackage{mathmongo-macros}",
                    r"\usepackage[active,tightpage]{preview}",
                    r"\PreviewEnvironment{tikzpicture}",
                    r"\setlength\PreviewBorder{4pt}",
                    macros,
                    r"\pagestyle{empty}",
                    r"\begin{document}",
                    source,
                    r"\end{document}",
                ]
            ),
            raster=True,
        )

    def _prune(self, retained):
        """Bound disposable outputs only; leave unrelated files and user documents alone."""
        files = [
            path
            for path in self.root.iterdir()
            if re.fullmatch(r"[a-f0-9]{64}\.(png|pdf)", path.name) and not path.is_symlink()
        ]
        files.sort(key=lambda path: path.stat().st_mtime)
        total = sum(path.stat().st_size for path in files)
        count = len(files)
        for path in files:
            if count <= CACHE_ENTRIES * 2 and total <= CACHE_BYTES:
                break
            if path not in retained:
                total -= path.stat().st_size
                path.unlink(missing_ok=True)
                count -= 1

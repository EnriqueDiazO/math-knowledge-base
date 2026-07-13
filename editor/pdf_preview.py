"""Shared validation, session lifecycle, and rendering for generated PDF previews."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mathmongo.paths import validate_mutable_path

PREVIEW_AUXILIARY_SUFFIXES = frozenset({".aux", ".fdb_latexmk", ".fls", ".log", ".out", ".toc"})
PDF_PREVIEW_NAMESPACES = frozenset(
    {
        "add_concept",
        "edit_concept",
        "cornell",
        "cpi",
        "reading_space",
        "source_document",
    }
)
PDF_SIGNATURE = b"%PDF-"


class PdfPreviewError(RuntimeError):
    """A generated PDF could not be safely prepared for the internal viewer."""

    def __init__(self, code: str, message: str):
        """Create an error with a stable machine-readable code and safe message."""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PdfPreviewPayload:
    """Immutable PDF data shared by the viewer and download control."""

    pdf_bytes: bytes
    sha256: str
    file_name: str
    context_identity: str


def _state_key(namespace: str) -> str:
    if namespace not in PDF_PREVIEW_NAMESPACES:
        raise ValueError(f"Unknown PDF preview namespace: {namespace}")
    return f"{_preview_key_prefix(namespace)}_current"


def _preview_key_prefix(namespace: str) -> str:
    """Keep Reading Space keys inside its literal session-state namespace."""
    if namespace not in PDF_PREVIEW_NAMESPACES:
        raise ValueError(f"Unknown PDF preview namespace: {namespace}")
    if namespace == "reading_space":
        return "reading_space_pdf_preview"
    return f"pdf_preview_{namespace}"


def pdf_preview_context(*parts: object) -> str:
    """Build an opaque, stable identity for one database/entity preview context."""
    encoded = "\x1f".join(str(part or "") for part in parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_path_within(path: str | Path, allowed_root: str | Path) -> Path:
    """Resolve ``path`` without allowing symlink or lexical escapes from ``allowed_root``."""
    root = Path(os.path.abspath(Path(allowed_root).expanduser()))
    candidate = Path(os.path.abspath(Path(path).expanduser()))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path must remain inside the allowed root") from exc

    current = root
    if current.is_symlink():
        raise ValueError("The allowed root cannot be a symbolic link")
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Symbolic links are not allowed in controlled paths")

    return validate_mutable_path(candidate, allowed_root=root)


def prepare_stable_preview(
    directory: Path,
    filename: str,
    *,
    allowed_root: str | Path,
) -> Path:
    """Prepare one controlled preview path, removing stale generated artifacts only."""
    filename_path = Path(filename)
    if (
        filename_path.parent != Path(".")
        or filename_path.name != filename
        or filename_path.suffix.lower() != ".pdf"
    ):
        raise ValueError("The preview filename must be a plain PDF filename")

    directory = resolve_path_within(directory, allowed_root)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    pdf_path = directory / filename

    # A failed compilation must never leave an earlier preview available.
    pdf_path.unlink(missing_ok=True)
    preview_stems = {pdf_path.stem, f"{pdf_path.stem}_fit"}
    for child in directory.iterdir():
        if (
            (child.is_file() or child.is_symlink())
            and child.suffix.lower() in PREVIEW_AUXILIARY_SUFFIXES
            and child.stem in preview_stems
        ):
            child.unlink()
    return pdf_path


def load_pdf_preview(
    pdf_path: str | Path,
    *,
    allowed_root: str | Path,
    file_name: str,
    context_identity: str,
) -> PdfPreviewPayload:
    """Read and validate a generated PDF exactly once from a controlled root."""
    try:
        path = resolve_path_within(pdf_path, allowed_root)
    except (OSError, ValueError) as exc:
        raise PdfPreviewError(
            "outside_controlled_root",
            "El PDF generado no está dentro de una ubicación controlada.",
        ) from exc

    safe_file_name = Path(file_name).name
    if safe_file_name != file_name or not safe_file_name.lower().endswith(".pdf"):
        raise PdfPreviewError("invalid_file_name", "El nombre de descarga del PDF no es válido.")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise PdfPreviewError("missing", "No se encontró el PDF generado.") from exc
    except OSError as exc:
        raise PdfPreviewError(
            "open_failed", "No se pudo abrir de forma segura el PDF generado."
        ) from exc

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PdfPreviewError(
                "not_regular", "El resultado generado no es un archivo PDF regular."
            )
        if before.st_size <= 0:
            raise PdfPreviewError("empty", "El PDF generado está vacío.")

        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except PdfPreviewError:
        raise
    except OSError as exc:
        raise PdfPreviewError("read_failed", "No se pudo leer el PDF generado.") from exc
    finally:
        os.close(descriptor)

    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise PdfPreviewError(
            "changed_during_read", "El PDF cambió mientras se preparaba la vista previa."
        )

    pdf_bytes = b"".join(chunks)
    if len(pdf_bytes) != before.st_size:
        raise PdfPreviewError("short_read", "No se pudo leer el PDF generado por completo.")
    if not pdf_bytes.startswith(PDF_SIGNATURE):
        raise PdfPreviewError(
            "invalid_header", "El archivo generado no tiene una cabecera PDF válida."
        )

    return PdfPreviewPayload(
        pdf_bytes=pdf_bytes,
        sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        file_name=safe_file_name,
        context_identity=context_identity,
    )


def clear_pdf_preview(state: Any, namespace: str) -> None:
    """Remove the current preview for exactly one flow namespace."""
    state.pop(_state_key(namespace), None)


def store_pdf_preview(state: Any, namespace: str, payload: PdfPreviewPayload) -> None:
    """Replace the current preview for exactly one flow namespace."""
    state[_state_key(namespace)] = payload


def get_pdf_preview(
    state: Any,
    namespace: str,
    *,
    context_identity: str,
) -> PdfPreviewPayload | None:
    """Return the current preview, invalidating stale database/entity contexts."""
    key = _state_key(namespace)
    payload = state.get(key)
    if not isinstance(payload, PdfPreviewPayload) or payload.context_identity != context_identity:
        state.pop(key, None)
        return None
    return payload


def generate_pdf_preview(
    state: Any,
    namespace: str,
    *,
    generator: Callable[[], str | Path],
    allowed_root: str | Path,
    file_name: str,
    context_identity: str,
) -> PdfPreviewPayload:
    """Clear stale state, generate, validate, and publish one preview payload."""
    clear_pdf_preview(state, namespace)
    pdf_path = generator()
    payload = load_pdf_preview(
        pdf_path,
        allowed_root=allowed_root,
        file_name=file_name,
        context_identity=context_identity,
    )
    store_pdf_preview(state, namespace, payload)
    return payload


def render_pdf_preview(
    ui: Any,
    state: Any,
    namespace: str,
    *,
    context_identity: str,
    height: int = 800,
) -> bool:
    """Render a persistent internal PDF viewer and an exact-byte download control."""
    payload = get_pdf_preview(
        state,
        namespace,
        context_identity=context_identity,
    )
    if payload is None:
        return False

    key_suffix = hashlib.sha256(
        f"{namespace}:{payload.context_identity}:{payload.sha256}".encode("ascii")
    ).hexdigest()[:16]
    component_missing = (
        getattr(ui, "__name__", "") == "streamlit"
        and importlib.util.find_spec("streamlit_pdf") is None
    )
    try:
        if component_missing:
            raise ModuleNotFoundError("streamlit_pdf")
        ui.pdf(
            payload.pdf_bytes,
            height=height,
            key=f"{_preview_key_prefix(namespace)}_viewer_{key_suffix}",
        )
    except Exception:
        ui.error(
            "No se pudo cargar el visor PDF interno. Instala la dependencia oficial "
            "con `pip install 'streamlit[pdf]'` y reinicia MathMongo. "
            "La descarga sigue disponible."
        )

    ui.download_button(
        "Descargar PDF",
        data=payload.pdf_bytes,
        file_name=payload.file_name,
        mime="application/pdf",
        key=f"{_preview_key_prefix(namespace)}_download_{key_suffix}",
    )
    if ui.button(
        "Cerrar vista previa",
        key=f"{_preview_key_prefix(namespace)}_close_{key_suffix}",
    ):
        clear_pdf_preview(state, namespace)
        ui.rerun()
    return True

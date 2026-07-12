"""Shared lifecycle and browser-opening helpers for local PDF previews."""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable
from pathlib import Path

from mathmongo.paths import validate_mutable_path

PREVIEW_AUXILIARY_SUFFIXES = frozenset(
    {".aux", ".fdb_latexmk", ".fls", ".log", ".out", ".toc"}
)


def resolve_path_within(path: str | Path, allowed_root: str | Path) -> Path:
    """Resolve ``path`` without allowing symlink or lexical escapes from ``allowed_root``."""
    root = Path(os.path.abspath(Path(allowed_root).expanduser()))
    candidate = Path(os.path.abspath(Path(path).expanduser()))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path must remain inside the allowed root: {root}") from exc

    current = root
    if current.is_symlink():
        raise ValueError(f"The allowed root cannot be a symbolic link: {root}")
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Symbolic links are not allowed in controlled paths: {current}")

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


def open_local_pdf(
    pdf_path: str | Path,
    *,
    opener: Callable[[str], object] = webbrowser.open_new_tab,
) -> bool:
    """Request non-blocking browser opening for an existing local PDF."""
    path = Path(pdf_path).resolve()
    if not path.is_file():
        return False
    try:
        return bool(opener(path.as_uri()))
    except Exception:
        return False

"""Shared lifecycle and browser-opening helpers for local PDF previews."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from pathlib import Path

PREVIEW_AUXILIARY_SUFFIXES = frozenset(
    {".aux", ".fdb_latexmk", ".fls", ".log", ".out", ".toc"}
)


def prepare_stable_preview(directory: Path, filename: str) -> Path:
    """Prepare one controlled preview path, removing stale generated artifacts only."""
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    pdf_path = directory / filename
    if pdf_path.suffix.lower() != ".pdf" or pdf_path.parent != directory:
        raise ValueError("The preview filename must be a plain PDF filename")

    # A failed compilation must never leave an earlier preview available.
    pdf_path.unlink(missing_ok=True)
    for child in directory.iterdir():
        if child.is_file() and child.suffix.lower() in PREVIEW_AUXILIARY_SUFFIXES:
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

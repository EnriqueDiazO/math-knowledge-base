"""Update a generated Quarto build without mutating packaged resources on import."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import yaml

from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


def update_quarto_yml(
    carpeta_base: str | Path | None = None,
    *,
    titulo: str = "Base de Conocimiento Matemática",
) -> Path:
    """Write ``_quarto.yml`` only in an explicit or configured export build."""
    if carpeta_base is None:
        base = get_exports_dir(
            configured=resolve_config().export_directory
        ) / "quarto"
    else:
        base = resolve_home_path(carpeta_base)
    base = validate_mutable_path(base)
    if not base.is_dir():
        raise FileNotFoundError(f"Quarto build directory not found: {base}")

    chapters = ["index.qmd"]
    for subdirectory in sorted(base.iterdir()):
        if subdirectory.is_dir():
            files = sorted(subdirectory.glob("*.qmd"))
            chapters.extend(str(path.relative_to(base)) for path in files)

    payload = {
        "project": {"type": "book"},
        "book": {
            "title": titulo,
            "author": "Enrique Díaz Ocampo",
            "chapters": chapters,
        },
        "format": {
            "html": {"theme": "cosmo", "toc": True},
            "pdf": {"documentclass": "article"},
        },
    }
    output = base / "_quarto.yml"
    output.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return output


def main(argv: Sequence[str] | None = None) -> int:
    """Update the configured Quarto index from command-line arguments."""
    parser = argparse.ArgumentParser(description="Actualiza el índice de un build Quarto.")
    parser.add_argument("--base", help="Directorio de build; relativo a HOME si no es absoluto.")
    args = parser.parse_args(argv)
    print(f"✅ Archivo actualizado: {update_quarto_yml(args.base)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

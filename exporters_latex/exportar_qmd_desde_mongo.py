"""Legacy QMD exporter with explicit MongoDB access and XDG-safe output."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from slugify import slugify

from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


def _output_root(base_dir: str | Path | None = None) -> Path:
    if base_dir is None:
        settings = resolve_config()
        candidate = get_exports_dir(
            configured=settings.export_directory
        ) / "quarto" / "legacy_qmd"
    else:
        candidate = resolve_home_path(base_dir)
    return validate_mutable_path(candidate)


def crear_qmd(concepto: dict, base_dir: str | Path | None = None) -> Path:
    """Create one QMD file under a controlled export directory."""
    tipo_raw = concepto.get("tipo", "otros")
    tipo = str(tipo_raw[0] if isinstance(tipo_raw, list) else tipo_raw).lower().replace(" ", "_")
    directory = _output_root(base_dir) / f"{tipo}s"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    titulo = concepto.get("titulo", "sin_titulo")
    contenido_latex = concepto.get("contenido_latex", "").strip()
    referencia = concepto.get("referencia", "N/A")
    comentario = concepto.get("comentario", "")
    concepto_id = concepto.get("id", "")
    filename = directory / f"{slugify(f'{tipo}_{titulo}')[:60]}.qmd"

    sections = [
        f"# {titulo}",
        f"**ID:** `{concepto_id}`",
        f"**Tipo:** {tipo}",
    ]
    if referencia and referencia != "N/A":
        sections.append(f"**Referencia:** {referencia}")
    if comentario:
        sections.append(f"**Comentario:** {comentario}")
    sections.extend(
        [
            "## Contenido (renderizado)\n\n$$\n" + contenido_latex + "\n$$",
            "## Código fuente LaTeX\n\n```latex\n" + contenido_latex + "\n```",
        ]
    )
    filename.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    return filename


def main(argv: Sequence[str] | None = None) -> int:
    """Export MongoDB concepts to QMD files from explicit command-line options."""
    from pymongo import MongoClient

    settings = resolve_config()
    parser = argparse.ArgumentParser(description="Exporta conceptos MongoDB a QMD.")
    parser.add_argument("--mongo-uri", default=settings.mongo_uri)
    parser.add_argument("--db", default=settings.mongo_database)
    parser.add_argument("--collection", default="collection")
    parser.add_argument("--output", help="Destino; relativo a HOME si no es absoluto.")
    args = parser.parse_args(argv)

    client = MongoClient(args.mongo_uri)
    try:
        collection = client[args.db][args.collection]
        for concepto in collection.find():
            if concepto.get("contenido_latex"):
                print(f"✅ Generado: {crear_qmd(concepto, args.output)}")
    finally:
        client.close()
    return 0


class ExportadorQuarto:
    def __init__(self, base_quarto_dir: str):
        pass

    def exportar_conceptos(self, conceptos: list[object]) -> None:
        pass

    def actualizar_archivo_yml(self) -> None:
        pass


if __name__ == "__main__":
    raise SystemExit(main())

"""Legacy QMD exporter with explicit MongoDB access and XDG-safe output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Sequence
from pathlib import Path
from tempfile import NamedTemporaryFile

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
    if isinstance(tipo_raw, list) and not tipo_raw:
        raise ValueError("tipo must contain a category")
    tipo = str(tipo_raw[0] if isinstance(tipo_raw, list) else tipo_raw).lower().replace(" ", "_")
    if re.fullmatch(r"[\w-]+", tipo) is None:
        raise ValueError("tipo must be a plain category without path separators")
    root = _output_root(base_dir)
    directory = validate_mutable_path(root / f"{tipo}s", allowed_root=root)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    titulo = concepto.get("titulo", "sin_titulo")
    contenido_latex = concepto.get("contenido_latex", "").strip()
    referencia = concepto.get("referencia", "N/A")
    comentario = concepto.get("comentario", "")
    concepto_id = concepto.get("id", "")
    identity = hashlib.sha256(json.dumps(
        [concepto_id, concepto.get("source", "")], ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    marker = f"<!-- mathmongo-qmd-identity:{identity} -->\n"
    filename = validate_mutable_path(
        directory / f"{slugify(f'{tipo}_{titulo}')[:60]}.qmd",
        allowed_root=directory,
    )

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
    content = marker + "\n\n".join(sections) + "\n"
    try:
        _publish_owned_qmd(filename, content, marker)
    except FileExistsError:
        # Equal titles (including source-scoped IDs) retain separate documents.
        # Unmarked legacy output cannot safely be claimed or overwritten.
        filename = validate_mutable_path(
            filename.with_stem(filename.stem + "-" + identity), allowed_root=directory,
        )
        _publish_owned_qmd(filename, content, marker)
    return filename


def _publish_owned_qmd(filename: Path, content: str, marker: str) -> None:
    """Publish privately without replacing another identity or an unmarked file."""
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=filename.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, filename)
        except FileExistsError:
            validate_mutable_path(filename, allowed_root=filename.parent)
            with filename.open(encoding="utf-8") as existing:
                if existing.readline() != marker:
                    raise FileExistsError("QMD destination belongs to another or unknown identity") from None
            os.replace(temporary, filename)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Export MongoDB concepts to QMD files from explicit command-line options."""
    from pymongo import MongoClient

    settings = resolve_config()
    parser = argparse.ArgumentParser(description="Exporta conceptos MongoDB a QMD.")
    parser.add_argument("--mongo-uri", default=settings.mongo_uri)
    parser.add_argument("--db", default=settings.mongo_database)
    parser.add_argument("--collection", default="concepts")
    parser.add_argument("--output", help="Destino; relativo a HOME si no es absoluto.")
    args = parser.parse_args(argv)

    client = MongoClient(args.mongo_uri)
    try:
        database = client[args.db]
        collection = database[args.collection]
        for concepto in collection.find():
            if args.collection == "concepts" and not concepto.get("contenido_latex"):
                latex = database["latex_documents"].find_one(
                    {"id": concepto.get("id"), "source": concepto.get("source")}
                )
                concepto = {**concepto, "contenido_latex": (latex or {}).get("contenido_latex", "")}
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

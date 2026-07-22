#!/usr/bin/env python3
"""Idempotently seed the COCID Drive/Docs Cornell and CPI tutorial notes."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections.abc import Callable
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps
from pymongo import MongoClient

from editor.cornell.models import DEFAULT_TEMPLATE_ID as CORNELL_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.persistence import build_cornell_note_document
from editor.cpi.models import DEFAULT_TEMPLATE_ID as CPI_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.persistence import build_cpi_note_document
from editor.utils.media_assets import media_path_exists
from editor.utils.media_assets import resolve_media_asset_path
from editor.utils.media_assets import reusable_media_asset
from editor.utils.media_assets import save_media_asset
from editor.utils.media_assets import synchronize_note_media_references
from mathmongo.config import resolve_config
from mathmongo.paths import find_symlink_component
from mathmongo.paths import get_backups_dir
from mathmongo.paths import get_home_dir
from mathmongo.paths import get_runtime_dir
from mathmongo.paths import validate_mutable_path
from scripts.build_cocid_drive_docs_tutorial_assets import ASSET_SPECS
from scripts.build_cocid_drive_docs_tutorial_assets import build_assets

CORNELL_SEED_ID = "cocid_google_drive_docs_cornell_v1"
CPI_SEED_ID = "cocid_google_drive_docs_cpi_v1"
SEED_IDS = (CORNELL_SEED_ID, CPI_SEED_ID)
TUTORIAL_ASSET_TAGS = ["COCID", "tutorial", "Google Drive", "Google Docs"]
LOGO_FILENAMES = (
    "cocid_logo_transparent_2400.png",
    "cocid_watermark_transparent_2400_alpha10.png",
)


def find_cocid_logo(*, repository_root: Path, home: Path | None = None) -> Path | None:
    """Find the preferred local COCID logo without network access."""
    user_home = home or get_home_dir()
    roots = (repository_root, user_home / "Downloads", user_home / "Descargas")
    for filename in LOGO_FILENAMES:
        for root in roots:
            candidate = root / filename
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
    return None


def _gallery(command: str, items: list[tuple[str, str, str]], *, columns: int) -> str:
    blocks: list[str] = []
    width = 0.48 if columns == 2 else 0.31
    for index, (asset_id, title, caption) in enumerate(items):
        blocks.append(
            "\n".join(
                (
                    rf"\begin{{minipage}}[t]{{{width:.2f}\linewidth}}",
                    r"\centering",
                    rf"\textbf{{{title}}}\\[1mm]",
                    rf"\{command}[0.98]{{{asset_id}}}\\[1mm]",
                    rf"{{\scriptsize {caption}}}",
                    r"\end{minipage}",
                )
            )
        )
        if index + 1 < len(items):
            blocks.append(r"\hfill" if (index + 1) % columns else r"\par\vspace{2mm}\noindent")
    return r"\par\vspace{2mm}\noindent" + "\n".join(blocks)


def _horizontal_figure(command: str, asset_id: str, title: str, caption: str) -> str:
    """Render one short landscape-region figure beside its caption."""
    return "\n".join(
        (
            r"\par\vspace{1mm}\noindent",
            r"\begin{minipage}[c]{0.22\linewidth}\centering",
            rf"\{command}[0.98]{{{asset_id}}}",
            r"\end{minipage}\hfill",
            r"\begin{minipage}[c]{0.74\linewidth}",
            rf"\textbf{{{title}}}\\[1mm]{{\scriptsize {caption}}}",
            r"\end{minipage}",
        )
    )


def build_cornell_tutorial_document(
    asset_ids: Mapping[str, str],
    watermark_asset_id: str,
) -> CornellDocument:
    """Build the required concise two-page Cornell tutorial."""
    drive_gallery = _gallery(
        "cornellimage",
        [
            (asset_ids[name], ASSET_SPECS[name]["title"], ASSET_SPECS[name]["caption"])
            for name in (
                "drive_01_nuevo.png",
                "drive_02_crear_carpeta.png",
                "drive_03_subir_archivo.png",
            )
        ],
        columns=2,
    )
    docs_gallery = _gallery(
        "cornellimage",
        [
            (asset_ids[name], ASSET_SPECS[name]["title"], ASSET_SPECS[name]["caption"])
            for name in (
                "docs_01_crear_y_renombrar.png",
                "docs_02_barra_de_herramientas.png",
                "docs_03_compartir_permisos.png",
            )
        ],
        columns=2,
    )
    pages = (
        CornellPage(
            page_id="drive",
            order=1,
            cue=CornellRegion(
                heading="Preguntas clave",
                latex=(
                    r"\begin{itemize}\setlength\itemsep{2mm}"
                    r"\item ¿Qué es Mi unidad?"
                    r"\item ¿Dónde se encuentra Nuevo?"
                    r"\item ¿Cómo creo una carpeta?"
                    r"\item ¿Cómo subo un archivo?"
                    r"\item ¿Cómo organizo lo que subí?"
                    r"\end{itemize}"
                ),
            ),
            main=CornellRegion(
                heading="Google Drive: crear y organizar",
                latex=(
                    r"\begin{enumerate}\setlength\itemsep{1mm}"
                    r"\item Abre Google Drive y ubica \textbf{Mi unidad}."
                    r"\item Pulsa \textbf{+ Nuevo} y elige \textbf{Nueva carpeta}."
                    r"\item Escribe un nombre breve, por ejemplo: \texttt{COCID\_Curso\_Datos}."
                    r"\item Para agregar un archivo, usa \textbf{+ Nuevo > Subir archivo}."
                    r"\item Muévelo a la carpeta correcta y verifica su nombre."
                    r"\item Separa proyectos, materiales y entregables con subcarpetas."
                    r"\end{enumerate}"
                    + drive_gallery
                ),
                image_ids=tuple(
                    asset_ids[name]
                    for name in (
                        "drive_01_nuevo.png",
                        "drive_02_crear_carpeta.png",
                        "drive_03_subir_archivo.png",
                    )
                ),
            ),
            summary=CornellRegion(
                heading="Resumen de Drive",
                latex=(
                    "Drive concentra, organiza y comparte archivos. La práctica esencial es crear "
                    "una estructura sencilla, usar nombres claros y revisar en qué carpeta queda "
                    "cada documento."
                ),
            ),
        ),
        CornellPage(
            page_id="docs",
            order=2,
            cue=CornellRegion(
                heading="Preguntas clave",
                latex=(
                    r"\begin{itemize}\setlength\itemsep{2mm}"
                    r"\item ¿Cómo creo un documento?"
                    r"\item ¿Dónde cambio su nombre?"
                    r"\item ¿Para qué sirve la barra de herramientas?"
                    r"\item ¿Qué permiso debo asignar al compartir?"
                    r"\end{itemize}"
                ),
            ),
            main=CornellRegion(
                heading="Google Docs: crear, editar y compartir",
                latex=(
                    r"\begin{enumerate}\setlength\itemsep{1mm}"
                    r"\item Crea un documento en blanco desde Docs o desde \textbf{+ Nuevo}."
                    r"\item Renómbralo en la parte superior antes de comenzar."
                    r"\item Usa la barra para títulos, negritas, listas y alineación."
                    r"\item Pulsa \textbf{Compartir} para añadir personas o copiar un enlace."
                    r"\item Elige: \textbf{Lector} consulta; \textbf{Comentador} comenta; "
                    r"\textbf{Editor} modifica."
                    r"\item Verifica el nombre y el permiso antes de enviar el enlace."
                    r"\end{enumerate}"
                    + docs_gallery
                ),
                image_ids=tuple(
                    asset_ids[name]
                    for name in (
                        "docs_01_crear_y_renombrar.png",
                        "docs_02_barra_de_herramientas.png",
                        "docs_03_compartir_permisos.png",
                    )
                ),
            ),
            summary=CornellRegion(
                heading="Resumen de Docs",
                latex=(
                    "Docs permite redactar y colaborar en línea. El flujo básico es crear, "
                    "renombrar, editar, compartir y confirmar los permisos."
                ),
            ),
        ),
    )
    return CornellDocument(
        schema_version=1,
        template_id=CORNELL_TEMPLATE_ID,
        pages=pages,
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id=watermark_asset_id,
            opacity=0.07,
            scale=0.70,
            position="center",
            all_pages=True,
        ),
    )


def build_cpi_tutorial_document(
    asset_ids: Mapping[str, str],
    watermark_asset_id: str,
) -> CpiDocument:
    """Build the required concise one-page CPI tutorial."""
    comprehension_names = ("drive_01_nuevo.png", "docs_02_barra_de_herramientas.png")
    production_names = (
        "drive_02_crear_carpeta.png",
        "drive_03_subir_archivo.png",
        "docs_01_crear_y_renombrar.png",
    )
    integration_names = ("docs_03_compartir_permisos.png",)
    page = CpiPage(
        page_number=1,
        comprehension=CpiRegion(
            heading="Comprensión",
            latex=(
                "Reconocer la función de cada herramienta y sus elementos básicos.\n\n"
                r"\textbf{Drive} almacena y organiza; \textbf{Docs} crea y edita en línea. "
                r"Conceptos: Mi unidad, carpeta, documento, compartir y los roles Lector, "
                r"Comentador y Editor."
                + _gallery(
                    "cpiimage",
                    [
                        (asset_ids[name], ASSET_SPECS[name]["title"], ASSET_SPECS[name]["caption"])
                        for name in comprehension_names
                    ],
                    columns=2,
                )
            ),
            image_ids=tuple(asset_ids[name] for name in comprehension_names),
        ),
        production=CpiRegion(
            heading="Producción",
            latex=(
                r"\textbf{Práctica:}\begin{enumerate}\setlength\itemsep{0.5mm}"
                r"\item Crea \texttt{COCID\_Practica}."
                r"\item Sube un PDF."
                r"\item Crea \texttt{Minuta\_COCID\_AAAA-MM-DD}."
                r"\item Agrega un título y tres puntos."
                r"\item Comparte como Comentador."
                r"\item Copia y prueba el enlace."
                r"\end{enumerate}"
                + _gallery(
                    "cpiimage",
                    [
                        (asset_ids[name], ASSET_SPECS[name]["title"], ASSET_SPECS[name]["caption"])
                        for name in production_names
                    ],
                    columns=3,
                )
            ),
            image_ids=tuple(asset_ids[name] for name in production_names),
        ),
        integration=CpiRegion(
            heading="Integración",
            latex=(
                r"\textbf{Flujo:} Drive guarda y organiza; Docs permite redactar; Compartir "
                r"controla el acceso. \textbf{Comprueba:} carpeta correcta, nombre claro, "
                r"contenido presente, permiso adecuado y enlace probado."
                + _horizontal_figure(
                    "cpiimage",
                    asset_ids[integration_names[0]],
                    ASSET_SPECS[integration_names[0]]["title"],
                    ASSET_SPECS[integration_names[0]]["caption"],
                )
            ),
            image_ids=tuple(asset_ids[name] for name in integration_names),
        ),
    )
    return CpiDocument(
        schema_version=1,
        template_id=CPI_TEMPLATE_ID,
        pages=(page,),
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id=watermark_asset_id,
            opacity=0.07,
            scale=0.70,
            position="center",
            all_pages=True,
        ),
    )


def _safe_backup_asset(asset: Mapping[str, Any]) -> tuple[str, bytes] | None:
    if not media_path_exists(dict(asset)):
        return None
    source = resolve_media_asset_path(dict(asset))
    if find_symlink_component(source) is not None:
        raise ValueError(f"Refusing symlinked focal backup asset: {asset.get('asset_id')}")
    safe_name = Path(str(asset.get("filename") or "asset.bin")).name
    return f"media/{asset.get('asset_id')}/{safe_name}", source.read_bytes()


def create_focal_backup(db: Any, output_dir: str | Path | None = None) -> Path:
    """Back up only prior tutorial notes and their referenced assets before seeding."""
    notes = list(db["latex_notes"].find({"seed_id": {"$in": list(SEED_IDS)}}))
    asset_ids = list(
        dict.fromkeys(
            str(asset_id)
            for note in notes
            for asset_id in note.get("image_ids", [])
            if str(asset_id or "").strip()
        )
    )
    assets = list(db["media_assets"].find({"asset_id": {"$in": asset_ids}})) if asset_ids else []
    backup_root = validate_mutable_path(
        Path(output_dir) if output_dir is not None else get_backups_dir() / "cocid_tutorial"
    )
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    destination = validate_mutable_path(
        backup_root / f"cocid_tutorial_focal_{timestamp}.zip",
        allowed_root=backup_root,
    )
    metadata = {
        "format": "cocid_tutorial_focal_backup_v1",
        "database_name": str(getattr(db, "name", "")),
        "created_at": datetime.now(timezone.utc),
        "seed_ids": list(SEED_IDS),
        "note_count": len(notes),
        "asset_count": len(assets),
    }
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "metadata.json",
            bson_json_dumps(metadata, json_options=CANONICAL_JSON_OPTIONS, ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "latex_notes.json",
            bson_json_dumps(notes, json_options=CANONICAL_JSON_OPTIONS, ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "media_assets.json",
            bson_json_dumps(assets, json_options=CANONICAL_JSON_OPTIONS, ensure_ascii=False, indent=2),
        )
        for asset in assets:
            payload = _safe_backup_asset(asset)
            if payload is not None:
                archive.writestr(*payload)
    destination.chmod(0o600)
    return destination


def _import_asset(db: Any, path: Path, *, tags: list[str], description: str) -> dict[str, Any]:
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    existing = reusable_media_asset(db, sha256=sha256, size_bytes=len(data))
    if existing is not None:
        return dict(existing)
    return save_media_asset(
        db,
        filename=path.name,
        data=data,
        mime_type="image/png",
        tags=tags,
        description=description,
    )


def _upsert_seed_note(db: Any, *, seed_id: str, note: Mapping[str, Any]) -> tuple[Any, str]:
    collection = db["latex_notes"]
    existing = collection.find_one({"seed_id": seed_id})
    now = datetime.now(timezone.utc)
    replacement = deepcopy(dict(note))
    replacement["seed_id"] = seed_id
    replacement["updated_at"] = now
    if existing is None:
        replacement["created_at"] = now
        result = collection.insert_one(replacement)
        return result.inserted_id, "created"
    replacement["_id"] = existing["_id"]
    replacement["created_at"] = existing.get("created_at", now)
    collection.replace_one({"_id": existing["_id"], "seed_id": seed_id}, replacement)
    return existing["_id"], "updated"


def seed_tutorial(
    db: Any,
    *,
    assets_dir: Path,
    logo_path: Path,
    backup_dir: Path | None = None,
    asset_importer: Callable[..., dict[str, Any]] = _import_asset,
    backup_creator: Callable[..., Path] = create_focal_backup,
) -> dict[str, Any]:
    """Create or update only the two stable tutorial notes in the selected database."""
    if not logo_path.is_file() or logo_path.is_symlink():
        raise FileNotFoundError(f"COCID logo not found or unsafe: {logo_path}")
    missing = [name for name in ASSET_SPECS if not (assets_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Tutorial assets missing: {', '.join(missing)}")

    counts_before = {
        "latex_notes": db["latex_notes"].count_documents({}),
        "media_assets": db["media_assets"].count_documents({}),
        "cornell_math_v1": db["latex_notes"].count_documents({"note_format": "cornell_math_v1"}),
        "cpi_v1": db["latex_notes"].count_documents({"note_format": "cpi_v1"}),
    }
    backup_path = backup_creator(db, backup_dir) if backup_dir is not None else backup_creator(db)

    logical_assets: dict[str, str] = {}
    for filename, spec in ASSET_SPECS.items():
        asset = asset_importer(
            db,
            assets_dir / filename,
            tags=[*TUTORIAL_ASSET_TAGS, "microcaptura", filename.removesuffix(".png")],
            description=spec["alt_text"],
        )
        logical_assets[filename] = str(asset["asset_id"])
    logo_asset = asset_importer(
        db,
        logo_path,
        tags=["COCID", "watermark", "identidad visual"],
        description="Logotipo COCID transparente usado como marca de agua.",
    )
    watermark_id = str(logo_asset["asset_id"])

    cornell_document = build_cornell_tutorial_document(logical_assets, watermark_id)
    cpi_document = build_cpi_tutorial_document(logical_assets, watermark_id)
    cornell_metadata = {
        "seed_id": CORNELL_SEED_ID,
        "title": "Tutorial breve: Google Drive y Google Docs",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "project": "COCID — Herramientas digitales",
        "context": "capacitación",
        "tags": ["COCID", "Google Drive", "Google Docs", "colaboración", "alfabetización digital"],
    }
    cpi_metadata = {
        "seed_id": CPI_SEED_ID,
        "title": "Google Drive y Docs: comprender, producir e integrar",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "project": "COCID — Herramientas digitales",
        "context": "capacitación",
        "tags": ["COCID", "Google Drive", "Google Docs", "CPI", "colaboración"],
    }
    results: dict[str, dict[str, str]] = {}
    for seed_id, note in (
        (CORNELL_SEED_ID, build_cornell_note_document(cornell_metadata, cornell_document)),
        (CPI_SEED_ID, build_cpi_note_document(cpi_metadata, cpi_document)),
    ):
        previous = db["latex_notes"].find_one({"seed_id": seed_id}) or {}
        note_id, action = _upsert_seed_note(db, seed_id=seed_id, note=note)
        synchronize_note_media_references(
            db,
            note_id=str(note_id),
            previous_asset_ids=tuple(previous.get("image_ids", ())),
            current_asset_ids=tuple(note.get("image_ids", ())),
        )
        results[seed_id] = {"note_id": str(note_id), "action": action}

    return {
        "database_name": str(getattr(db, "name", "")),
        "counts_before": counts_before,
        "backup_path": str(backup_path),
        "assets": logical_assets,
        "watermark_asset_id": watermark_id,
        "notes": results,
    }


def parse_args() -> argparse.Namespace:
    """Parse explicit optional paths while retaining selected-database defaults."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--logo", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    """Generate local assets and seed the currently selected Mongo database."""
    args = parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    logo_path = args.logo or find_cocid_logo(repository_root=repository_root)
    if logo_path is None:
        expected = ", ".join(LOGO_FILENAMES)
        raise SystemExit(f"No se encontró el logotipo COCID. Archivos esperados: {expected}")
    assets_dir = args.assets_dir or get_runtime_dir() / "cocid_drive_docs_tutorial_assets"
    build_assets(assets_dir)
    config = resolve_config()
    client = MongoClient(config.mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        db = client[config.mongo_database]
        result = seed_tutorial(
            db,
            assets_dir=assets_dir,
            logo_path=logo_path,
            backup_dir=args.backup_dir,
        )
    finally:
        client.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Instala (opcionalmente) el modo Cuaderno en la base MongoDB.

Este script crea colecciones, validadores (JSON Schema) e índices mínimos para:
  - worklog_entries
  - backlog_items
  - weekly_reviews
  - deliverables
  - latex_notes
  - knowledge_graph_maps
  - media_assets

Cornell matemático usa la colección existente latex_notes. No existe una
colección cornell_notes separada; las notas Cornell se distinguen por
note_format="cornell_math_v1" y guardan su estructura canónica en
cornell.schema_version, cornell.template_id y cornell.pages. Ejecuta este
script con el mismo --db seleccionado en la aplicación (por ejemplo MathV0).

Uso:
  python scripts/install_cuaderno_mode.py
  python scripts/install_cuaderno_mode.py --status
  python scripts/install_cuaderno_mode.py --mongo-uri mongodb://127.0.0.1:27017 --db mathmongo

Variables de entorno (opcionales):
  - MONGODB_URI / MONGO_URI
  - MONGODB_DB / MONGO_DB / DB_NAME
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from pymongo import ASCENDING
from pymongo import DESCENDING
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from pymongo.errors import PyMongoError

PROJECT_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_PATH))

from mathkb_config import MEDIA_ASSETS_COLLECTION  # noqa: E402
from mathkb_config import MEDIA_IMAGES_DIR  # noqa: E402
from mathkb_config import MEDIA_ROOT  # noqa: E402
from mathkb_config import PROJECT_ROOT  # noqa: E402

REQUIRED_COLLECTIONS = [
    "worklog_entries",
    "backlog_items",
    "weekly_reviews",
    "deliverables",
    "latex_notes",
    "knowledge_graph_maps",
    MEDIA_ASSETS_COLLECTION,
]

CORNELL_NOTE_FORMAT = "cornell_math_v1"
CORNELL_LATEX_NOTE_INDEXES = [
    ([("note_format", ASCENDING)], "latex_note_format"),
    ([("note_format", ASCENDING), ("date", DESCENDING)], "latex_note_format_date_desc"),
    ([("note_format", ASCENDING), ("project", ASCENDING)], "latex_note_format_project"),
    ([("note_format", ASCENDING), ("context", ASCENDING)], "latex_note_format_context"),
]


def _env_first(*keys: str) -> str | None:
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return None


def _get_client(uri: str) -> MongoClient:
    return MongoClient(uri, serverSelectionTimeoutMS=3000)


def _ensure_media_directories() -> None:
    media_root = PROJECT_ROOT / MEDIA_ROOT
    media_images_dir = PROJECT_ROOT / MEDIA_IMAGES_DIR
    media_images_dir.mkdir(parents=True, exist_ok=True)

    gitkeep = media_images_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")

    gitignore = media_images_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n!.gitkeep\n", encoding="utf-8")

    try:
        display_path = media_root.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        display_path = media_root.as_posix()
    print(f"✅ Directorio de medios listo: {display_path}")


def _ensure_collection(db, name: str, validator: dict[str, Any]) -> None:
    existing = set(db.list_collection_names())
    if name not in existing:
        db.create_collection(name)
        print(f"✅ Creada colección: {name}")
    # Aplica/actualiza validador
    try:
        db.command(
            "collMod",
            name,
            validator=validator,
            validationLevel="moderate",
        )
    except PyMongoError as e:
        # collMod puede fallar en algunos clusters con permisos limitados
        print(f"⚠️  No se pudo aplicar validador a {name}: {e}")


def _worklog_validator() -> dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["date", "block", "project", "task", "status", "iso_year", "iso_week", "created_at", "updated_at"],
            "properties": {
                "date": {"bsonType": "string", "description": "YYYY-MM-DD"},
                "block": {"enum": ["AM", "PM", "Noche"]},
                "start_time": {"bsonType": ["string", "null"]},
                "end_time": {"bsonType": ["string", "null"]},
                "hours": {"bsonType": ["double", "int", "long", "decimal", "null"], "minimum": 0},
                "project": {"bsonType": "string"},
                "module": {"bsonType": ["string", "null"]},
                "task": {"bsonType": "string"},
                "description_evidence": {"bsonType": ["string", "null"]},
                "status": {"enum": ["Planificado", "En progreso", "Hecho", "Bloqueado", "Cancelado"]},
                "deliverable_id": {"bsonType": ["objectId", "null"]},
                "evidence_url": {"bsonType": ["string", "null"]},
                "next_step": {"bsonType": ["string", "null"]},
                "tags": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "iso_year": {"bsonType": ["int", "long"]},
                "iso_week": {"bsonType": ["int", "long"]},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }


def _backlog_validator() -> dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["project", "task", "priority", "status", "owner", "created_at", "updated_at"],
            "properties": {
                "project": {"bsonType": "string"},
                "module": {"bsonType": ["string", "null"]},
                "task": {"bsonType": "string"},
                "description": {"bsonType": ["string", "null"]},
                "priority": {"enum": ["Alta", "Media", "Baja"]},
                "estimate_hours": {"bsonType": ["double", "int", "long", "decimal", "null"], "minimum": 0},
                "owner": {"bsonType": "string"},
                "target_date": {"bsonType": ["string", "null"], "description": "YYYY-MM-DD"},
                "status": {"enum": ["Todo", "Doing", "Done", "Blocked", "Canceled"]},
                "linked_worklog_ids": {"bsonType": ["array"], "items": {"bsonType": "objectId"}},
                "linked_note_ids": {"bsonType": ["array"], "items": {"bsonType": "objectId"}},
                "linked_commits": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "tags": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }


def _weekly_validator() -> dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["iso_year", "iso_week", "created_at", "updated_at"],
            "properties": {
                "iso_year": {"bsonType": ["int", "long"]},
                "iso_week": {"bsonType": ["int", "long"]},
                "weekly_objectives": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "wins": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "blocks_risks": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "plan_next_week": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "real_hours": {"bsonType": ["double", "int", "long", "decimal", "null"], "minimum": 0},
                "tasks_completed_count": {"bsonType": ["int", "long", "null"], "minimum": 0},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }


def _deliverables_validator() -> dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["date", "project", "deliverable", "type", "url_or_path", "created_at", "updated_at"],
            "properties": {
                "date": {"bsonType": "string", "description": "YYYY-MM-DD"},
                "project": {"bsonType": "string"},
                "deliverable": {"bsonType": "string"},
                "type": {"enum": ["reporte", "codigo", "dataset", "presentacion", "evidencia", "otro"]},
                "url_or_path": {"bsonType": "string"},
                "notes": {"bsonType": ["string", "null"]},
                "linked_worklog_ids": {"bsonType": ["array"], "items": {"bsonType": "objectId"}},
                "linked_note_ids": {"bsonType": ["array"], "items": {"bsonType": "objectId"}},
                "linked_commits": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }

def _cornell_region_validator() -> dict[str, Any]:
    return {
        "bsonType": "object",
        "required": ["heading", "latex", "image_ids"],
        "properties": {
            "heading": {"bsonType": "string"},
            "latex": {"bsonType": "string"},
            "image_ids": {"bsonType": ["array"], "items": {"bsonType": "string"}},
        },
    }


def _cornell_page_validator() -> dict[str, Any]:
    region = _cornell_region_validator()
    return {
        "bsonType": "object",
        "required": ["page_id", "order", "cue", "main", "summary"],
        "properties": {
            "page_id": {"bsonType": "string"},
            "order": {"bsonType": ["int", "long"], "minimum": 1},
            "cue": region,
            "main": region,
            "summary": region,
            "source_refs": {"bsonType": ["array"], "items": {"bsonType": "object"}},
        },
    }


def _cornell_document_validator() -> dict[str, Any]:
    return {
        "bsonType": "object",
        "required": ["schema_version", "template_id", "pages"],
        "properties": {
            "schema_version": {"bsonType": ["int", "long"], "minimum": 1},
            "template_id": {"bsonType": "string"},
            "pages": {"bsonType": ["array"], "items": _cornell_page_validator()},
            "attribution": _cornell_attribution_validator(),
            "watermark": _cornell_watermark_validator(),
        },
    }


def _cornell_attribution_validator() -> dict[str, Any]:
    return {
        "bsonType": "object",
        "properties": {
            "enabled": {"bsonType": "bool"},
            "mode": {"enum": ["auto", "custom"]},
            "text": {"bsonType": "string"},
            "author": {"bsonType": "string"},
            "course": {"bsonType": "string"},
            "year": {"bsonType": "string"},
            "position": {"enum": ["center", "bottom_right", "top_right"]},
        },
    }


def _cornell_watermark_validator() -> dict[str, Any]:
    return {
        "bsonType": "object",
        "properties": {
            "enabled": {"bsonType": "bool"},
            "type": {"enum": ["text", "image"]},
            "text": {"bsonType": "string"},
            "image_id": {"bsonType": "string"},
            "opacity": {"bsonType": ["double", "int", "long", "decimal"]},
            "scale": {"bsonType": ["double", "int", "long", "decimal"]},
            "position": {"enum": ["center", "bottom_right", "top_right"]},
        },
    }


def _latex_notes_validator() -> dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["title", "date", "latex_body"],
            "properties": {
                "title": {"bsonType": "string"},
                "date": {"bsonType": "string", "description": "YYYY-MM-DD"},
                "project": {"bsonType": ["string", "null"]},
                "context": {"enum": ["estudio", "debug", "lectura", "idea", "reflexion"]},
                "note_format": {"enum": [CORNELL_NOTE_FORMAT]},
                "latex_body": {"bsonType": "string"},
                "cornell": _cornell_document_validator(),
                "image_ids": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "tags": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }


def _knowledge_graph_maps_validator() -> dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "graph_state", "created_at", "updated_at"],
            "properties": {
                "map_uid": {"bsonType": ["string", "null"]},
                "name": {"bsonType": "string"},
                "description": {"bsonType": ["string", "null"]},
                "tags": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "filters": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "sources": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                        "concept_types": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                        "relation_types": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                        "max_depth": {"bsonType": ["int", "long", "double", "null"]},
                    },
                },
                "graph_state": {"bsonType": "object"},
                "sync_settings": {
                    "bsonType": ["object", "null"],
                    "properties": {
                        "suppress_new_nodes_prompt": {"bsonType": ["bool", "null"]},
                        "ignored_concept_ids": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                        "removed_node_ids": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                        "manually_removed_node_ids": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                        "last_sync_check_at": {"bsonType": ["date", "string", "null"]},
                        "auto_include_source_new_nodes": {"bsonType": ["bool", "null"]},
                    },
                },
                "source": {"bsonType": ["string", "null"]},
                # JSON exports restore datetimes as ISO strings, so both forms are accepted.
                "created_at": {"bsonType": ["date", "string"]},
                "updated_at": {"bsonType": ["date", "string"]},
            },
        }
    }


def _media_assets_validator() -> dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["asset_id", "filename", "storage_type", "path", "created_at", "updated_at"],
            "properties": {
                "asset_id": {"bsonType": "string"},
                "filename": {"bsonType": "string"},
                "original_filename": {"bsonType": ["string", "null"]},
                "mime_type": {"bsonType": ["string", "null"]},
                "storage_type": {"enum": ["local"]},
                "path": {"bsonType": "string"},
                "size_bytes": {"bsonType": ["int", "long"]},
                "sha256": {"bsonType": ["string", "null"]},
                "concept_ids": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "note_ids": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "tags": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "description": {"bsonType": ["string", "null"]},
                "created_at": {"bsonType": ["date", "string"]},
                "updated_at": {"bsonType": ["date", "string"]},
            },
        }
    }


def _ensure_indexes(db) -> None:
    def _safe_create_index(col, keys, *, name: str, unique: bool = False) -> None:
        """Crea un índice de forma idempotente.

        Si ya existe un índice con las mismas keys (aunque tenga otro nombre), no falla.
        Si unique=True y el índice existente no es unique, NO lo acepta silenciosamente
        (deja que MongoDB lance el error) para evitar inconsistencias.
        """
        try:
            for ix in col.list_indexes():
                ix_keys = list(ix.get("key", {}).items())
                if ix_keys == list(keys):
                    if unique and not ix.get("unique", False):
                        break
                    return
            col.create_index(keys, name=name, unique=unique)
        except OperationFailure as e:
            # 85 = IndexOptionsConflict / Index already exists with different name/options
            if getattr(e, "code", None) == 85:
                return
            raise

    # worklog
    _safe_create_index(
        db["worklog_entries"],
        [("date", DESCENDING), ("created_at", DESCENDING)],
        name="date_created_desc",
    )
    _safe_create_index(
        db["worklog_entries"],
        [("project", ASCENDING), ("date", DESCENDING)],
        name="project_date_desc",
    )
    _safe_create_index(
        db["worklog_entries"],
        [("iso_year", ASCENDING), ("iso_week", ASCENDING), ("project", ASCENDING)],
        name="iso_year_week_project",
    )

    # backlog
    _safe_create_index(
        db["backlog_items"],
        [("project", ASCENDING), ("status", ASCENDING), ("priority", ASCENDING)],
        name="project_status_priority",
    )
    _safe_create_index(
        db["backlog_items"],
        [("updated_at", DESCENDING)],
        name="updated_at_desc",
    )

    # weekly reviews
    _safe_create_index(
        db["weekly_reviews"],
        [("iso_year", ASCENDING), ("iso_week", ASCENDING)],
        name="iso_year_week_unique",
        unique=True,
    )

    # deliverables
    _safe_create_index(
        db["deliverables"],
        [("date", DESCENDING), ("project", ASCENDING)],
        name="date_desc_project",
    )

    # latex notes
    _safe_create_index(
        db["latex_notes"],
        [("date", DESCENDING), ("updated_at", DESCENDING)],
        name="date_desc_updated_desc",
    )
    _safe_create_index(
        db["latex_notes"],
        [("project", ASCENDING), ("date", DESCENDING)],
        name="latex_project_date_desc",
    )
    for keys, name in CORNELL_LATEX_NOTE_INDEXES:
        _safe_create_index(db["latex_notes"], keys, name=name)

    # knowledge graph maps
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("name", ASCENDING)],
        name="kg_maps_name",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("updated_at", DESCENDING)],
        name="kg_maps_updated_at_desc",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("created_at", DESCENDING)],
        name="kg_maps_created_at_desc",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("tags", ASCENDING)],
        name="kg_maps_tags",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("filters.sources", ASCENDING)],
        name="kg_maps_filter_sources",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("filters.concept_types", ASCENDING)],
        name="kg_maps_filter_concept_types",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("filters.relation_types", ASCENDING)],
        name="kg_maps_filter_relation_types",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("source", ASCENDING)],
        name="kg_maps_source",
    )
    _safe_create_index(
        db["knowledge_graph_maps"],
        [("map_uid", ASCENDING)],
        name="kg_maps_map_uid",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("asset_id", ASCENDING)],
        name="media_assets_asset_id",
        unique=True,
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("path", ASCENDING)],
        name="media_assets_path",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("filename", ASCENDING)],
        name="media_assets_filename",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("storage_type", ASCENDING)],
        name="media_assets_storage_type",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("mime_type", ASCENDING)],
        name="media_assets_mime_type",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("concept_ids", ASCENDING)],
        name="media_assets_concept_ids",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("note_ids", ASCENDING)],
        name="media_assets_note_ids",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("tags", ASCENDING)],
        name="media_assets_tags",
    )
    _safe_create_index(
        db[MEDIA_ASSETS_COLLECTION],
        [("created_at", DESCENDING)],
        name="media_assets_created_at_desc",
    )


def _latex_notes_validator_supports_cornell(db) -> bool:
    try:
        validator = db["latex_notes"].options().get("validator", {})
    except (AttributeError, PyMongoError):
        return False
    properties = validator.get("$jsonSchema", {}).get("properties", {})
    cornell = properties.get("cornell", {})
    cornell_properties = cornell.get("properties", {})
    return (
        properties.get("note_format", {}).get("enum") == [CORNELL_NOTE_FORMAT]
        and cornell.get("required") == ["schema_version", "template_id", "pages"]
        and "pages" in cornell_properties
    )


def _latex_notes_has_cornell_indexes(db) -> bool:
    try:
        indexes = list(db["latex_notes"].list_indexes())
    except PyMongoError:
        return False
    index_keys = {tuple(index.get("key", {}).items()) for index in indexes}
    return all(tuple(keys) in index_keys for keys, _name in CORNELL_LATEX_NOTE_INDEXES)


def status(db) -> int:
    """Print installation status for Cuaderno collections and Cornell support."""
    existing = set(db.list_collection_names())
    print("Colecciones:")
    ok = True
    for c in REQUIRED_COLLECTIONS:
        if c in existing:
            print(f"  - {c}: OK")
        else:
            print(f"  - {c}: MISSING")
            ok = False
    print("Medios:")
    media_images_dir = PROJECT_ROOT / MEDIA_IMAGES_DIR
    if media_images_dir.exists():
        print(f"  - {MEDIA_IMAGES_DIR.as_posix()}: OK")
    else:
        print(f"  - {MEDIA_IMAGES_DIR.as_posix()}: MISSING")
        ok = False
    print("Cornell:")
    cornell_collection = "latex_notes" in existing
    cornell_validator = cornell_collection and _latex_notes_validator_supports_cornell(db)
    cornell_indexes = cornell_collection and _latex_notes_has_cornell_indexes(db)
    if cornell_collection:
        print("  - latex_notes: OK")
    else:
        print("  - latex_notes: MISSING")
    if cornell_validator:
        print("  - validador cornell_math_v1: OK")
    else:
        print("  - validador cornell_math_v1: MISSING")
        ok = False
    if cornell_indexes:
        print("  - índices Cornell: OK")
    else:
        print("  - índices Cornell: MISSING")
        ok = False
    return 0 if ok else 2


def install(db) -> int:
    """Install Cuaderno collections, validators, indexes, and Cornell support."""
    _ensure_media_directories()
    _ensure_collection(db, "worklog_entries", _worklog_validator())
    _ensure_collection(db, "backlog_items", _backlog_validator())
    _ensure_collection(db, "weekly_reviews", _weekly_validator())
    _ensure_collection(db, "deliverables", _deliverables_validator())
    _ensure_collection(db, "latex_notes", _latex_notes_validator())
    _ensure_collection(db, "knowledge_graph_maps", _knowledge_graph_maps_validator())
    _ensure_collection(db, MEDIA_ASSETS_COLLECTION, _media_assets_validator())
    _ensure_indexes(db)
    print("✅ Cuaderno instalado (colecciones + validadores + índices + media/images + Cornell en latex_notes).")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the Cuaderno installer CLI."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="Solo imprime si existen las colecciones requeridas.")
    ap.add_argument("--mongo-uri", default=_env_first("MONGODB_URI", "MONGO_URI") or "mongodb://127.0.0.1:27017")
    ap.add_argument("--db", default=_env_first("MONGODB_DB", "MONGO_DB", "DB_NAME") or "mathmongo")
    args = ap.parse_args(argv)

    try:
        client = _get_client(args.mongo_uri)
        # ping rápido
        client.admin.command("ping")
    except Exception as e:
        print(f"❌ No se pudo conectar a MongoDB: {e}")
        return 2

    db = client[args.db]

    try:
        if args.status:
            return status(db)
        return install(db)
    except Exception as e:
        print(f"❌ Error en instalación: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

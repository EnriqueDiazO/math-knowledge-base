#!/usr/bin/env python3
"""Instala (opcionalmente) el modo Cuaderno en la base MongoDB.

Este script crea colecciones, validadores (JSON Schema) e índices mínimos para:
  - worklog_entries
  - backlog_items
  - weekly_reviews
  - deliverables

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
from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, OperationFailure


REQUIRED_COLLECTIONS = [
    "worklog_entries",
    "backlog_items",
    "weekly_reviews",
    "deliverables",
    "latex_notes",
]


def _env_first(*keys: str) -> Optional[str]:
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return None


def _get_client(uri: str) -> MongoClient:
    return MongoClient(uri, serverSelectionTimeoutMS=3000)


def _ensure_collection(db, name: str, validator: Dict[str, Any]) -> None:
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


def _worklog_validator() -> Dict[str, Any]:
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


def _backlog_validator() -> Dict[str, Any]:
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


def _weekly_validator() -> Dict[str, Any]:
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


def _deliverables_validator() -> Dict[str, Any]:
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




def _latex_notes_validator() -> Dict[str, Any]:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["title", "date", "latex_body", "created_at", "updated_at"],
            "properties": {
                "title": {"bsonType": "string"},
                "date": {"bsonType": "string", "description": "YYYY-MM-DD"},
                "project": {"bsonType": ["string", "null"]},
                "context": {"enum": ["estudio", "debug", "lectura", "idea", "reflexion"]},
                "latex_body": {"bsonType": "string"},
                "tags": {"bsonType": ["array"], "items": {"bsonType": "string"}},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
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
    name="project_date_desc",
)


def status(db) -> int:
    existing = set(db.list_collection_names())
    print("Colecciones:")
    ok = True
    for c in REQUIRED_COLLECTIONS:
        if c in existing:
            print(f"  - {c}: OK")
        else:
            print(f"  - {c}: MISSING")
            ok = False
    return 0 if ok else 2


def install(db) -> int:
    _ensure_collection(db, "worklog_entries", _worklog_validator())
    _ensure_collection(db, "backlog_items", _backlog_validator())
    _ensure_collection(db, "weekly_reviews", _weekly_validator())
    _ensure_collection(db, "deliverables", _deliverables_validator())
    _ensure_collection(db, "latex_notes", _latex_notes_validator())
    _ensure_indexes(db)
    print("✅ Cuaderno instalado (colecciones + validadores + índices).")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
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

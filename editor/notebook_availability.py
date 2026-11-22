"""Notebook availability; extracted without import-time rendering."""

from __future__ import annotations


def _cuaderno_is_installed(conn) -> bool:
    """Detecta si el modo cuaderno está instalado en la DB actual.

    Se considera instalado si existen las 4 colecciones base.
    """
    try:
        if conn is None:
            return False
        mongo_db = getattr(conn, "db", None)
        if mongo_db is None:
            return False
        names = set(mongo_db.list_collection_names())
        required = {
            "worklog_entries",
            "backlog_items",
            "weekly_reviews",
            "deliverables",
            "latex_notes",
            "knowledge_graph_maps",
            "media_assets",
        }
        return required.issubset(names)
    except Exception:
        return False

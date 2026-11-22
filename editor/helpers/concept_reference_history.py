"""Concept reference history; extracted without import-time rendering."""

from __future__ import annotations


def _normalize_ref_dict(ref: dict) -> dict:
    """Normaliza la referencia para soportar:
    - esquema nuevo: tipo_referencia, issbn
    - esquema viejo: tipo, isbn
    - citekey opcional.
    """  # noqa: D205
    if not isinstance(ref, dict):
        return {}

    # soporta ambos nombres de campo
    tipo = ref.get("tipo_referencia") or ref.get("tipo")
    issbn = ref.get("issbn") or ref.get("isbn")  # tu modelo usa issbn

    out = dict(ref)
    if tipo is not None:
        out["tipo_referencia"] = tipo
    if issbn is not None:
        out["issbn"] = issbn

    return out


def load_last_reference_by_source(db, source: str) -> dict | None:
    """
    Busca el último concepto (fecha_creacion DESC) del mismo source
    que tenga un campo 'referencia' utilizable.
    """  # noqa: D205, D212
    if not source or not isinstance(source, str) or not source.strip():
        return None

    query = {
        "source": source,
        "referencia": {"$exists": True, "$ne": None},
    }
    projection = {"referencia": 1, "id": 1, "titulo": 1, "fecha_creacion": 1, "_id": 0}

    doc = db.concepts.find_one(query, projection=projection, sort=[("fecha_creacion", -1)])
    if not doc:
        return None

    ref = _normalize_ref_dict(doc.get("referencia") or {})
    # “utilizable” = al menos autor o fuente o citekey (ajústalo si quieres)
    if not (ref.get("autor") or ref.get("fuente") or ref.get("citekey")):
        return None

    # (opcional) Adjunta metadatos para debug
    ref["__from_concept_id"] = doc.get("id")
    ref["__from_concept_title"] = doc.get("titulo")
    ref["__from_concept_date"] = doc.get("fecha_creacion")

    return ref



# Page configuration

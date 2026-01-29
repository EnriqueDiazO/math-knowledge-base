import re

def upsert_concept_metadata(db, concept_id: str, source: str, concepto_dict: dict) -> None:
    """
    Persist concept metadata using the current upsert behavior.

    NOTE: This mirrors the existing logic exactly and is intentionally naive.
    It will be refined in later refactors to avoid silent overwrites.
    """
    db.concepts.update_one(
        {"id": concept_id, "source": source},
        {"$set": concepto_dict},
        upsert=True,
    )


def concept_exists(db, concept_id: str, source: str) -> bool:
    """
    Check whether a concept with the given (id, source) already exists.

    This performs a lightweight existence check against the concepts collection.
    """
    return db.concepts.count_documents(
        {"id": concept_id, "source": source},
        limit=1
    ) > 0


def insert_concept_metadata(db, concept_id: str, source: str, concepto_dict: dict) -> None:
    """
    Insert concept metadata using insert-only semantics.

    Assumes a preflight check has already ensured (id, source) does not exist.
    This function does NOT perform upserts.
    """
    doc = dict(concepto_dict)
    doc["id"] = concept_id
    doc["source"] = source
    db.concepts.insert_one(doc)


def insert_concept_with_latex_atomic(
    db,
    concept_id: str,
    source: str,
    concepto_dict: dict,
    contenido_latex: str,
    now,
) -> None:
    """
    Best-effort atomic insert across concepts and latex_documents.

    Strategy:
    1) Insert metadata into concepts (insert-only)
    2) Insert LaTeX into latex_documents (insert-only)
    3) If step (2) fails, rollback step (1)
    """
    doc = dict(concepto_dict)
    doc["id"] = concept_id
    doc["source"] = source

    try:
        db.concepts.insert_one(doc)
        db.latex_documents.insert_one(
            {
                "id": concept_id,
                "source": source,
                "contenido_latex": contenido_latex,
                "fecha_creacion": now,
                "ultima_actualizacion": now,
            }
        )
    except Exception:
        db.concepts.delete_one({"id": concept_id, "source": source})
        raise


def semantic_duplicate_exists(db, titulo, tipo, source):
    if not titulo:
        return False
    return db.concepts.find_one({
        "source": source,
        "tipo": tipo,
        "titulo": {
            "$regex": f"^{re.escape(titulo.strip())}$",
            "$options": "i"
        }
    }) is not None

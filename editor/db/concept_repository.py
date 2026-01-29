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

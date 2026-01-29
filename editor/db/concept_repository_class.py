from mathdatabase.mathmongo import MathMongo
from editor.db.concept_repository import (
    insert_concept_metadata,
    insert_concept_with_latex_atomic,
    concept_exists,
    semantic_duplicate_exists,
)

class ConceptRepository:
    """
    Thin OO wrapper around existing procedural DB functions.

    MVP-R1: this class introduces a DB boundary without changing behavior.
    """

    def __init__(self):
        self.mongo = MathMongo()
        self.db = self.mongo.db

    def concept_exists(self, concept_id: str, source: str) -> bool:
        return concept_exists(self.db, concept_id, source)

    def insert_concept_metadata(self, concept_id, source, concepto_dict):
        return insert_concept_metadata(self.db, concept_id, source, concepto_dict)

    def insert_concept_with_latex_atomic(
        self, concept_id, source, concepto_dict, contenido_latex, now
    ):
        return insert_concept_with_latex_atomic(
            self.db, concept_id, source, concepto_dict, contenido_latex, now
        )

    def semantic_duplicate_exists(self, titulo, tipo, source):
        return semantic_duplicate_exists(self.db, titulo, tipo, source)

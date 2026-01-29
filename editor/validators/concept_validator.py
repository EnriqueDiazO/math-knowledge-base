"""
Centralized validation logic for concept creation and editing.

MVP-R2: structure only, no behavior change.
"""

from typing import List
from typing import List
from editor.db.concept_repository import semantic_duplicate_exists

def validate_new_concept_identity(
    db,
    concept_id: str,
    source: str,
) -> List[str]:
    """
    Validate uniqueness of (concept_id, source) for new concept creation.

    Returns a list of error messages.
    Empty list means validation passed.

    MVP-R2: mirrors existing behavior exactly.
    """
    errors: List[str] = []

    if db.concepts.count_documents(
        {"id": concept_id, "source": source},
        limit=1,
    ) > 0:
        errors.append("❌ Concept already exists")

    return errors


def validate_semantic_duplicate(
    db,
    titulo: str,
    concept_type: str,
    source: str,
) -> List[str]:
    """
    Validate semantic duplication by (titulo, tipo, source).

    Mirrors existing behavior exactly.
    Returns a list of error messages.
    """
    errors: List[str] = []

    if titulo and semantic_duplicate_exists(db, titulo, concept_type, source):
        errors.append("❌ Ya existe un concepto con el mismo TITULO y tipo desde este source.")
        errors.append("💡 Usa un ID distinto solo si el concepto es realmente diferente, o edita el existente.")

    return errors


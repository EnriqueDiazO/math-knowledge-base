from schemas.schemas import ConceptoBase


def build_concept_metadata(concepto: ConceptoBase) -> dict:
    """
    Build the metadata dictionary for a ConceptoBase instance,
    excluding large LaTeX content and None fields.

    This function is pure and has no side effects.
    """
    return concepto.model_dump(
        mode="python",
        exclude={"contenido_latex"},
        exclude_none=True,
    )

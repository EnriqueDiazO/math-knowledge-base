"""Preserve required-nullable bibliography contracts rather than relaxing validation."""

import pytest
from pydantic import ValidationError

from schemas.schemas import Referencia
from schemas.schemas import RelationEnriched

REFERENCE_FIELDS = ("tipo_referencia", "autor", "fuente", "anio", "tomo", "edicion", "paginas", "capitulo", "seccion", "editorial", "doi", "url", "issbn")


@pytest.mark.parametrize("model,field", [(Referencia, field) for field in REFERENCE_FIELDS] + [(RelationEnriched, "desde_ref"), (RelationEnriched, "hasta_ref")])
def test_nullable_fields_accept_explicit_null_but_reject_missing_keys(model, field):
    """A nullable value is valid; omitting a required contract field remains an error."""
    payload = {name: None for name in REFERENCE_FIELDS} if model is Referencia else {
        "relation": {"desde_id": "a", "desde_source": "S", "hasta_id": "b", "hasta_source": "S", "tipo": "equivalente"},
        "desde_ref": None, "hasta_ref": None,
    }
    validated = model.model_validate(payload)
    assert getattr(validated, field) is None
    incomplete = dict(payload)
    del incomplete[field]
    with pytest.raises(ValidationError) as error:
        model.model_validate(incomplete)
    assert any(item["loc"] == (field,) and item["type"] == "missing" for item in error.value.errors())

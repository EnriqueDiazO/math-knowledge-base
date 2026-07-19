"""Compatibility tests for the embedded concept Reference contract."""

# ruff: noqa: D103

from __future__ import annotations

from editor.helpers.concept_builders import build_concept_metadata
from schemas.schemas import ConceptoBase
from schemas.schemas import Referencia


def _legacy_reference(**changes: object) -> dict[str, object]:
    reference: dict[str, object] = {
        "tipo_referencia": "libro",
        "autor": "N.I. Muskhelishvili",
        "fuente": "Singular Integral Equations",
        "anio": 1946,
        "tomo": None,
        "edicion": None,
        "paginas": None,
        "capitulo": None,
        "seccion": None,
        "editorial": None,
        "doi": None,
        "url": None,
        "issbn": None,
    }
    reference.update(changes)
    return reference


def test_legacy_reference_without_citekey_keeps_its_historical_serialization() -> None:
    historical = _legacy_reference()

    reference = Referencia.model_validate(historical)

    assert reference.model_dump(mode="python", exclude_none=True) == {
        "tipo_referencia": "libro",
        "autor": "N.I. Muskhelishvili",
        "fuente": "Singular Integral Equations",
        "anio": 1946,
    }


def test_citekey_survives_reference_and_add_concept_metadata_builder() -> None:
    reference = Referencia.model_validate(
        _legacy_reference(citekey="Muskhelishvili1946")
    )
    concept = ConceptoBase(
        id="def:singular_integral_equations",
        tipo="definicion",
        contenido_latex=r"\mathcal{S}\varphi",
        categorias=["Analysis"],
        source="Singular Integral Equations",
        referencia=reference,
    )

    serialized_reference = reference.model_dump(mode="python", exclude_none=True)
    metadata = build_concept_metadata(concept)

    assert reference.citekey == "Muskhelishvili1946"
    assert serialized_reference["citekey"] == "Muskhelishvili1946"
    assert metadata["referencia"]["citekey"] == "Muskhelishvili1946"


def test_none_citekey_is_omitted_by_existing_exclude_none_flow() -> None:
    reference = Referencia.model_validate(_legacy_reference(citekey=None))
    concept = ConceptoBase(
        id="def:legacy_without_key",
        tipo="definicion",
        contenido_latex="x=x",
        categorias=[],
        source="Legacy",
        referencia=reference,
    )

    assert "citekey" not in reference.model_dump(mode="python", exclude_none=True)
    assert "citekey" not in build_concept_metadata(concept)["referencia"]

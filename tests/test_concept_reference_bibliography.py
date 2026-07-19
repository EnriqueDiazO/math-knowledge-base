"""Pure bibliography normalization tests for Add Concept."""

# ruff: noqa: D103

from __future__ import annotations

from pathlib import Path

import pytest

from editor.helpers.bibliographic_reference import normalize_bibliographic_entry
from mathmongo.source_catalog.bibtex import parse_bibtex_file_content
from mathmongo.source_catalog.bibtex import parse_bibtex_paste

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "bibliography"
    / "muskhelishvili_minimal.bib"
)


def _one(raw: str) -> dict:
    parsed = parse_bibtex_paste(raw)
    assert parsed.errors == ()
    assert len(parsed.candidates) == 1
    return parsed.candidates[0]


def test_muskhelishvili_fixture_normalizes_to_the_concept_form_contract() -> None:
    parsed = parse_bibtex_file_content(FIXTURE.read_bytes())

    normalized = normalize_bibliographic_entry(parsed.candidates[0])

    assert parsed.errors == ()
    assert normalized.reference == {
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
        "citekey": "Muskhelishvili1946",
    }
    assert normalized.warnings == ()


@pytest.mark.parametrize(
    ("entry_type", "expected"),
    (
        ("book", "libro"),
        ("article", "articulo"),
        ("manual", "libro"),
        ("phdthesis", "tesis"),
        ("mastersthesis", "tesina"),
        ("misc", "miscelanea"),
        ("online", "pagina_web"),
    ),
)
def test_exact_bibtex_type_mappings(entry_type: str, expected: str) -> None:
    candidate = _one(f"@{entry_type}{{key, title={{Title}}}}")

    normalized = normalize_bibliographic_entry(candidate)

    assert normalized.reference["tipo_referencia"] == expected


@pytest.mark.parametrize(
    "entry_type",
    (
        "inbook",
        "incollection",
        "inproceedings",
        "proceedings",
        "conference",
        "techreport",
        "unpublished",
        "unknownkind",
    ),
)
def test_types_without_a_legacy_equivalent_use_misc_with_a_warning(
    entry_type: str,
) -> None:
    candidate = _one(f"@{entry_type}{{key, title={{Title}}}}")

    normalized = normalize_bibliographic_entry(candidate)

    assert normalized.reference["tipo_referencia"] == "miscelanea"
    assert any(entry_type in warning for warning in normalized.warnings)


def test_article_maps_supported_fields_and_omits_unrepresentable_journal() -> None:
    candidate = _one(
        """@article{mendez2026,
          author={Méndez, Ana and {World Health Organization}},
          title={Álgebra y análisis}, year={2026},
          journal={Revista Matemática}, volume={4}, number={2},
          pages={11--29}, doi={https://doi.org/10.1000/ABC.123},
          url={https://example.test/paper}, isbn={978-0-306-40615-7}
        }"""
    )

    normalized = normalize_bibliographic_entry(candidate)

    assert normalized.reference == {
        "tipo_referencia": "articulo",
        "autor": "Ana Méndez; World Health Organization",
        "fuente": "Álgebra y análisis",
        "anio": 2026,
        "tomo": "4",
        "edicion": None,
        "paginas": "11-29",
        "capitulo": None,
        "seccion": "2",
        "editorial": None,
        "doi": "10.1000/abc.123",
        "url": "https://example.test/paper",
        "issbn": "978-0-306-40615-7",
        "citekey": "mendez2026",
    }
    assert any("journal" in warning for warning in normalized.warnings)


def test_incollection_uses_title_and_author_without_inventing_editor_or_booktitle() -> None:
    candidate = _one(
        """@incollection{chapter,
          author={Ada Lovelace}, editor={Charles Babbage},
          title={A chapter}, booktitle={Collected Works},
          publisher={Example Press}, chapter={3}, pages={40--50}
        }"""
    )

    normalized = normalize_bibliographic_entry(candidate)

    assert normalized.reference["autor"] == "Ada Lovelace"
    assert normalized.reference["fuente"] == "A chapter"
    assert normalized.reference["editorial"] == "Example Press"
    assert normalized.reference["capitulo"] == "3"
    assert normalized.reference["paginas"] == "40-50"
    assert any("booktitle" in warning for warning in normalized.warnings)
    assert any("editor" in warning for warning in normalized.warnings)


def test_editor_and_booktitle_are_deterministic_fallbacks_when_primary_fields_are_absent() -> None:
    candidate = _one(
        "@incollection{fallback, editor={Doe, Jane}, booktitle={Collected Works}}"
    )

    normalized = normalize_bibliographic_entry(candidate)

    assert normalized.reference["autor"] == "Jane Doe"
    assert normalized.reference["fuente"] == "Collected Works"


def test_missing_optional_fields_are_none_and_missing_title_or_author_do_not_raise() -> None:
    title_only = normalize_bibliographic_entry(_one("@misc{title, title={Only title}}"))
    author_only = normalize_bibliographic_entry(
        _one("@misc{author, author={Only Author}}")
    )

    assert title_only.reference["autor"] is None
    assert title_only.reference["editorial"] is None
    assert author_only.reference["fuente"] is None
    assert author_only.reference["anio"] is None
    assert all("tipo_referencia" in item.reference for item in (title_only, author_only))


def test_case_unicode_braces_multiple_authors_and_string_year_are_preserved() -> None:
    candidate = _one(
        """@BOOK{unicode,
          AUTHOR={{Institut de Mathématiques} and García, Zoë},
          TITLE={{Équations singulières}}, YEAR={1946}
        }"""
    )

    normalized = normalize_bibliographic_entry(candidate)

    assert normalized.reference["tipo_referencia"] == "libro"
    assert normalized.reference["autor"] == "Institut de Mathématiques; Zoë García"
    assert normalized.reference["fuente"] == "Équations singulières"
    assert normalized.reference["anio"] == 1946


def test_date_can_supply_a_year_when_year_is_absent() -> None:
    normalized = normalize_bibliographic_entry(
        _one("@online{dated, title={Dated}, date={2025-03-17}}")
    )

    assert normalized.reference["anio"] == 2025


def test_section_has_priority_over_number_and_reports_the_collapsed_number() -> None:
    candidate = _one(
        "@misc{located, title={Located}, section={S2}, number={7}}"
    )

    normalized = normalize_bibliographic_entry(candidate)

    assert normalized.reference["seccion"] == "S2"
    assert any("number" in warning for warning in normalized.warnings)


def test_multiple_entries_and_duplicate_keys_remain_explicit_candidates() -> None:
    parsed = parse_bibtex_paste(
        "@book{same, title={First}}\n@article{same, title={Second}}"
    )

    normalized = [normalize_bibliographic_entry(item) for item in parsed.candidates]

    assert parsed.errors == ()
    assert len(normalized) == 2
    assert [item.reference["fuente"] for item in normalized] == ["First", "Second"]
    assert [item.reference["citekey"] for item in normalized] == ["same", "same"]


@pytest.mark.parametrize(
    ("raw", "code"),
    (
        ("", "empty_input"),
        ("not a bibliography", "unexpected_text"),
        ("@book{broken, title={Never closed}", "unclosed_entry"),
    ),
)
def test_empty_and_invalid_inputs_return_structured_errors(raw: str, code: str) -> None:
    parsed = parse_bibtex_paste(raw)

    assert parsed.candidates == ()
    assert parsed.errors[0]["code"] == code

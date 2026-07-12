"""Tests for pure, multi-entry Source catalog BibTeX previews."""

# ruff: noqa: D103

from __future__ import annotations

import builtins
import hashlib

from mathmongo.source_catalog.bibtex import MAX_BIBTEX_EXTRA_FIELDS
from mathmongo.source_catalog.bibtex import MAX_BIBTEX_EXTRA_TOTAL_CHARS
from mathmongo.source_catalog.bibtex import MAX_BIBTEX_EXTRA_VALUE_CHARS
from mathmongo.source_catalog.bibtex import parse_bibtex_file_content
from mathmongo.source_catalog.bibtex import parse_bibtex_paste
from mathmongo.source_catalog.models import Reference

SINGLE_ENTRY = """@Article{Méndez2026,
  author = {Méndez, Ana and {World Health Organization}},
  title = {Álgebra y análisis},
  year = {2026},
  journal = {Revista Matemática},
  volume = {4},
  number = {2},
  doi = {https://doi.org/10.1000/ABC.123},
  isbn = {978-0-306-40615-7},
  url = {https://example.test/paper},
  note = {Imported from a reference manager},
  custom-field = {preserve me}
}"""


def test_paste_one_entry_maps_identity_raw_hash_and_known_fields() -> None:
    result = parse_bibtex_paste(SINGLE_ENTRY)

    assert result.errors == ()
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    reference = candidate["reference_data"]
    bibtex = reference["bibtex"]

    assert candidate["entry_index"] == 1
    assert candidate["entry_type"] == "article"
    assert candidate["citekey"] == "Méndez2026"
    assert candidate["raw"] == SINGLE_ENTRY
    assert candidate["raw_sha256"] == hashlib.sha256(SINGLE_ENTRY.encode()).hexdigest()
    assert bibtex["key"] == "Méndez2026"
    assert bibtex["entry_type"] == "article"
    assert bibtex["raw"] == SINGLE_ENTRY
    assert bibtex["raw_sha256"] == candidate["raw_sha256"]
    assert bibtex["extra"] == {"custom-field": "preserve me"}
    assert reference["reference_type"] == "article"
    assert reference["title"] == "Álgebra y análisis"
    assert reference["year"] == 2026
    assert reference["year_raw"] == "2026"
    assert reference["journal"] == "Revista Matemática"
    assert reference["volume"] == "4"
    assert reference["number"] == "2"
    assert reference["doi"] == "https://doi.org/10.1000/ABC.123"
    assert reference["isbn"] == ["978-0-306-40615-7"]
    assert reference["url"] == "https://example.test/paper"
    assert reference["provenance"]["import_method"] == "bibtex_paste"


def test_multiple_entries_preserve_order_and_structured_or_literal_authors() -> None:
    second = """@book{Knuth1984,
  author = {Donald E. Knuth and de la Cruz, Juana},
  title = {The TeXbook},
  year = {circa 1984},
  publisher = {Addison-Wesley}
}"""
    result = parse_bibtex_paste(f"{SINGLE_ENTRY}\n\n% between entries\n{second}\n")

    assert result.errors == ()
    assert [item["citekey"] for item in result.candidates] == [
        "Méndez2026",
        "Knuth1984",
    ]
    first_authors = result.candidates[0]["reference_data"]["authors"]
    assert first_authors == [
        {"family": "Méndez", "given": "Ana", "literal": None, "orcid": None},
        {
            "family": None,
            "given": None,
            "literal": "World Health Organization",
            "orcid": None,
        },
    ]
    second_reference = result.candidates[1]["reference_data"]
    assert second_reference["authors"] == [
        {
            "family": "Knuth",
            "given": "Donald E.",
            "literal": None,
            "orcid": None,
        },
        {
            "family": "de la Cruz",
            "given": "Juana",
            "literal": None,
            "orcid": None,
        },
    ]
    assert second_reference["year"] is None
    assert second_reference["year_raw"] == "circa 1984"


def test_already_read_file_content_supports_multiple_entries_and_string_macros() -> None:
    content = b"""@string{journalName = "Journal of Tests"}
@article{one, title={One}, journal=journalName, url={https://one.test}}
@online{two, title={Two}, url={https://two.test}}
"""

    result = parse_bibtex_file_content(content)

    assert result.errors == ()
    assert result.ignored_directives == ("string",)
    assert len(result.candidates) == 2
    assert result.candidates[0]["reference_data"]["journal"] == "Journal of Tests"
    assert result.candidates[1]["reference_data"]["reference_type"] == "web"
    assert all(
        candidate["reference_data"]["provenance"]["import_method"] == "bib_file"
        for candidate in result.candidates
    )


def test_a_delimited_bad_entry_reports_its_error_without_losing_the_next_entry() -> None:
    content = """@article{, title={Missing key}}
@misc{good-key, doi={10.1234/only-identity}}
"""

    result = parse_bibtex_paste(content)

    assert len(result.errors) == 1
    assert result.errors[0]["entry_index"] == 1
    assert result.errors[0]["code"] == "parse_error"
    assert result.errors[0]["raw"] == "@article{, title={Missing key}}"
    assert [candidate["citekey"] for candidate in result.candidates] == ["good-key"]
    assert result.candidates[0]["entry_index"] == 2
    assert result.candidates[0]["reference_data"]["doi"] == "10.1234/only-identity"
    validated = Reference.model_validate(result.candidates[0]["reference_data"])
    assert validated.doi == "10.1234/only-identity"
    assert validated.title is None


def test_unclosed_entry_has_entry_scoped_raw_and_sha256() -> None:
    raw = "@article{broken, title={Never closed}"

    result = parse_bibtex_paste(raw)

    assert result.candidates == ()
    assert len(result.errors) == 1
    error = result.errors[0]
    assert error["entry_index"] == 1
    assert error["code"] == "unclosed_entry"
    assert error["raw"] == raw
    assert error["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


def test_unknown_extra_fields_are_bounded_and_report_truncation() -> None:
    extras = ",\n".join(
        f"  unknown{index} = {{{'x' * (MAX_BIBTEX_EXTRA_VALUE_CHARS + 20)}}}"
        for index in range(MAX_BIBTEX_EXTRA_FIELDS + 5)
    )
    raw = f"@misc{{bounded,\n  url={{https://example.test}},\n{extras}\n}}"

    result = parse_bibtex_paste(raw)

    assert result.errors == ()
    candidate = result.candidates[0]
    extra = candidate["reference_data"]["bibtex"]["extra"]
    assert len(extra) <= MAX_BIBTEX_EXTRA_FIELDS
    assert sum(len(value) for value in extra.values()) <= MAX_BIBTEX_EXTRA_TOTAL_CHARS
    assert all(len(value) <= MAX_BIBTEX_EXTRA_VALUE_CHARS for value in extra.values())
    assert candidate["warnings"]
    assert candidate["reference_data"]["provenance"]["warnings"] == candidate["warnings"]


def test_file_content_decode_error_is_structured_and_hashes_original_bytes() -> None:
    content = b"\xff\xfe\xfa"

    result = parse_bibtex_file_content(content)

    assert result.candidates == ()
    assert len(result.errors) == 1
    assert result.errors[0]["code"] == "decode_error"
    assert result.errors[0]["content_sha256"] == hashlib.sha256(content).hexdigest()


def test_preview_functions_never_open_or_write_files(monkeypatch) -> None:
    def unexpected_open(*args, **kwargs):
        raise AssertionError("BibTeX preview attempted filesystem I/O")

    monkeypatch.setattr(builtins, "open", unexpected_open)

    paste_result = parse_bibtex_paste("@misc{paste, url={https://paste.test}}")
    file_result = parse_bibtex_file_content(
        b"@misc{file, doi={10.1234/file-only}}"
    )

    assert paste_result.errors == ()
    assert file_result.errors == ()
    assert paste_result.candidates[0]["citekey"] == "paste"
    assert file_result.candidates[0]["citekey"] == "file"

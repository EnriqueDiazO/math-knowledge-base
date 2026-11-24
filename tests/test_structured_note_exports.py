"""Structured document bundles must compile with the same isolated React runner."""

from importlib import import_module

import pytest

from editor.note_export import build_note_latex_bundle
from mathmongo.study.document_export import compile_project


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_portable_structured_project_compiles_in_the_existing_namespace(tmp_path, family):
    """A canonical region document must not depend on resources outside its bundle."""
    helpers = import_module("tests.test_" + family + "_service")
    persistence = import_module("editor." + family + ".persistence")
    note = getattr(persistence, "build_" + family + "_note_document")(
        helpers.sample_metadata(), helpers.sample_document()
    )
    bundle = build_note_latex_bundle(note)
    result = compile_project(bundle)
    assert result.status == "ready", result.diagnostic
    assert result.pdf.startswith(b"%PDF-")
    (tmp_path / (family + ".pdf")).write_bytes(result.pdf)

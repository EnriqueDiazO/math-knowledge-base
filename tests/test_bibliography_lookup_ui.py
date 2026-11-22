"""Real widget reruns preserve corrected proposals when a later provider lookup fails."""

from __future__ import annotations

import json
import textwrap

from streamlit.testing.v1 import AppTest


def test_online_capture_failure_keeps_identifier_corrections_and_edition(tmp_path):
    """Exercise actual Streamlit widgets; use saved provider data, never user DB/network."""
    app_file = tmp_path / "lookup_app.py"
    app_file.write_text(
        textwrap.dedent("""
        import streamlit as st
        from editor.source_catalog.lookup_ui import render_lookup
        from mathmongo.bibliography_lookup.service import LookupResult
        from mathmongo.bibliography_lookup.adapters import Proposal
        from mathmongo.source_catalog.models import Reference
        class API:
            def identifier(self, query):
                if query == 'network-error':
                    return LookupResult('unavailable', query)
                if query == 'missing':
                    return LookupResult('not_found', query)
                return LookupResult('partial', query, candidates=(Proposal(Reference(
                    title='Propuesta parcial', year=2006, edition='Traducción española',
                    authors=[{'family':'Autora', 'orcid':'0000-0002-1825-0097'}],
                    bibtex={'key':'ClaveFija', 'extra':{'translator':'Traductora'}})),))
        ref = render_lookup(st, key_prefix='test_lookup', api=API())
        if ref:
            st.json(ref.model_dump(mode='json'))
    """)
    )
    app = AppTest.from_file(str(app_file)).run()

    def text(label):
        return next(item for item in app.text_input if item.label == label)

    def button(label):
        return next(item for item in app.button if item.label == label)

    text("Pegar DOI o ISBN").input("9780140328721")
    button("Buscar referencia").click().run()
    assert not app.exception
    result = json.loads(app.json[0].value)
    assert result["edition"] == "Traducción española" and result["year"] == 2006
    text("Title").input("Corrección personal").run()
    assert json.loads(app.json[0].value)["title"] == "Corrección personal"
    assert json.loads(app.json[0].value)["authors"][0]["orcid"] == "0000-0002-1825-0097"
    for failure in ("network-error", "missing"):
        text("Pegar DOI o ISBN").input(failure)
        button("Buscar referencia").click().run()
        assert not app.exception
        assert text("Pegar DOI o ISBN").value == failure
        assert text("Title").value == "Corrección personal"
        assert json.loads(app.json[0].value)["edition"] == "Traducción española"
        assert any("propuesta anterior" in caption.value for caption in app.caption)

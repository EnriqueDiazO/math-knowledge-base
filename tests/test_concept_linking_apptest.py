"""Real Streamlit rerun coverage for the guided direct-page flow."""

from __future__ import annotations

import textwrap
from pathlib import Path

from streamlit.testing.v1 import AppTest

from editor.concept_linking.state import ACTIVE
from editor.concept_linking.state import MODE
from editor.concept_linking.state import PARTIAL_TARGET_ID
from editor.reading_space.state import PENDING_WORKSPACE_TAB


def test_guided_page_flow_confirms_once_across_real_streamlit_reruns(tmp_path: Path) -> None:
    app_file = tmp_path / "concept_linking_app.py"
    app_file.write_text(
        textwrap.dedent(
            """
            from types import SimpleNamespace

            import streamlit as st

            from editor.concept_linking.linking_wizard import render_linking_wizard
            from editor.concept_linking.state import ACTIVE
            from editor.concept_linking.state import start_wizard
            from editor.concept_linking.view_models import ConceptLinkingContext


            class Cursor(list):
                def sort(self, *_args, **_kwargs):
                    return self

                def skip(self, count):
                    return Cursor(self[count:])

                def limit(self, count):
                    return Cursor(self[:count])


            class Concepts:
                document = {
                    "id": "metric-spherical",
                    "source": "Pommerenke1991",
                    "titulo": "Métrica esférica",
                    "tipo": "Definición",
                    "categorias": ["Análisis complejo"],
                    "tags": ["frontera"],
                }

                def find(self, _query, _projection):
                    return Cursor([dict(self.document)])

                def find_one(self, query, _projection):
                    if query == {"id": self.document["id"], "source": self.document["source"]}:
                        return dict(self.document)
                    return None


            class Database:
                def __init__(self):
                    self.concepts = Concepts()

                def __getitem__(self, name):
                    if name != "concepts":
                        raise KeyError(name)
                    return self.concepts


            class EvidenceRepository:
                def count_by_concept(self, *_args, **_kwargs):
                    return int(st.session_state.get("fake_link_count", 0))

                @staticmethod
                def _link():
                    values = st.session_state.get("fake_existing_link")
                    if not values:
                        return None
                    return SimpleNamespace(
                        **values,
                        status=SimpleNamespace(value="active"),
                    )

                def find_exact(self, _candidate):
                    return self._link()

                def get_by_id(self, evidence_link_id):
                    link = self._link()
                    return link if link and link.evidence_link_id == evidence_link_id else None


            class Service:
                def __init__(self):
                    self.evidence = EvidenceRepository()

                def create_concept_evidence_link(self, **values):
                    st.session_state["fake_link_count"] = int(
                        st.session_state.get("fake_link_count", 0)
                    ) + 1
                    st.session_state["fake_link_values"] = {
                        "link_type": values["link_type"],
                        "comment": values["comment"],
                        "page_number": values["page_number"],
                    }
                    st.session_state["fake_existing_link"] = {
                        "evidence_link_id": "ev_fake",
                        "concept_legacy_id": values["concept_legacy_id"],
                        "concept_legacy_source": values["concept_legacy_source"],
                        "source_id": values["source_id"],
                        "reference_id": values["reference_id"],
                        "document_id": values["document_id"],
                        "annotation_id": values["annotation_id"],
                        "note_id": values["note_id"],
                        "page_number": values["page_number"],
                        "link_type": values["link_type"],
                        "comment": values["comment"],
                    }
                    return SimpleNamespace(
                        completed=True,
                        status=SimpleNamespace(value="success"),
                        value=SimpleNamespace(evidence_link_id="ev_fake"),
                    )


            database = Database()
            service = Service()
            context = ConceptLinkingContext(
                database_name="temporary_s4_3",
                document_id="doc_123e4567-e89b-42d3-a456-426614174000",
                document_title="Boundary Behaviour of Conformal Maps",
                document_kind="pdf",
                source_id="src_123e4567-e89b-42d3-a456-426614174000",
                source_name="Pommerenke1991BoundaryBehaviourConformalMaps",
                reference_id=None,
                reference_title="Boundary Behaviour of Conformal Maps",
                pdf_page=9,
                book_page_label="1",
                reading_status="in_progress",
            )
            if not st.session_state.get("fake_booted"):
                start_wizard(st.session_state, context)
                st.session_state["fake_booted"] = True
            render_linking_wizard(
                st,
                database,
                service,
                context=context,
                document_evidence=(),
                quick_sections=(),
                actions_enabled=True,
            )
            st.metric("Asociaciones guardadas", st.session_state.get("fake_link_count", 0))
            if st.session_state.get("fake_link_values"):
                st.write(st.session_state["fake_link_values"])
            """
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file)).run()
    assert not app.exception
    assert app.metric[0].value == "0"
    next(item for item in app.text_input if item.label == "Buscar concepto").input("Métrica")
    app.run()

    next(button for button in app.button if button.label == "Seleccionar").click()
    app.run()
    # The selection is recorded during the button run; exercise the following
    # clean rerun to verify that only the compact selected-concept card remains.
    app.run()
    details = next(item for item in app.expander if item.label == "Ver detalles")
    assert details.proto.expanded is False
    editable_labels = {
        item.label
        for collection in (app.text_input, app.text_area, app.selectbox, app.radio)
        for item in collection
    }
    for internal_label in (
        "document_id",
        "source_id",
        "reference_id",
        "annotation_id",
        "note_id",
        "evidence_link_id",
        "concept_legacy_id",
        "concept_legacy_source",
        "user_scope",
    ):
        assert internal_label not in editable_labels
    assert not app.dataframe
    relation = next(item for item in app.selectbox if item.label == "Tipo de relación")
    relation.select("definition_source")
    next(
        item for item in app.text_area if item.label == "¿Por qué esta evidencia es relevante?"
    ).input("Aquí se introduce la métrica usada en la frontera.")
    app.run()

    rendered_context = " ".join(item.value for item in (*app.caption, *app.markdown))
    assert "Boundary Behaviour of Conformal Maps" in rendered_context
    assert "Book page 1 · PDF page 9" in rendered_context
    assert "Fuente de definición" in rendered_context

    save = next(button for button in app.button if button.label == "Guardar asociación")
    assert save.disabled is False
    save.click()
    app.run()

    assert not app.exception
    assert app.metric[0].value == "1"
    assert any("Evidencia guardada" in item.value for item in app.success)
    assert app.session_state["fake_link_values"] == {
        "link_type": "definition_source",
        "comment": "Aquí se introduce la métrica usada en la frontera.",
        "page_number": 9,
    }


def test_partial_annotation_survives_real_reruns_and_retry_does_not_recreate_it(
    tmp_path: Path,
) -> None:
    annotation_id = "ann_123e4567-e89b-42d3-a456-426614174001"
    app_file = tmp_path / "concept_linking_partial_app.py"
    app_file.write_text(
        textwrap.dedent(
            f"""
            from types import SimpleNamespace

            import streamlit as st

            from editor.concept_linking.linking_wizard import render_linking_wizard
            from editor.concept_linking.state import start_wizard
            from editor.concept_linking.view_models import ConceptLinkingContext


            ANNOTATION_ID = {annotation_id!r}


            class Cursor(list):
                def sort(self, *_args, **_kwargs):
                    return self

                def skip(self, count):
                    return Cursor(self[count:])

                def limit(self, count):
                    return Cursor(self[:count])


            class Concepts:
                document = {{
                    "id": "metric-spherical",
                    "source": "Pommerenke1991",
                    "titulo": "Métrica esférica",
                    "tipo": "Definición",
                }}

                def find(self, _query, _projection):
                    return Cursor([dict(self.document)])

                def find_one(self, query, _projection):
                    expected = {{"id": self.document["id"], "source": self.document["source"]}}
                    return dict(self.document) if query == expected else None


            class Database:
                def __init__(self):
                    self.concepts = Concepts()

                def __getitem__(self, name):
                    if name != "concepts":
                        raise KeyError(name)
                    return self.concepts


            class EvidenceRepository:
                def count_by_concept(self, *_args, **_kwargs):
                    return 0

                def find_exact(self, _candidate):
                    return None


            class Service:
                def __init__(self):
                    self.evidence = EvidenceRepository()

                @staticmethod
                def annotation():
                    return SimpleNamespace(
                        annotation_id=ANNOTATION_ID,
                        document_id="doc_123e4567-e89b-42d3-a456-426614174000",
                        source_id="src_123e4567-e89b-42d3-a456-426614174000",
                        reference_id=None,
                        kind=SimpleNamespace(value="highlight"),
                        status=SimpleNamespace(value="active"),
                        page_number=9,
                        quote_text="spherical metric",
                        body="A logical highlight",
                        tags=("boundary",),
                    )

                def create_annotation(self, *_args, **_kwargs):
                    st.session_state["fake_annotation_count"] = int(
                        st.session_state.get("fake_annotation_count", 0)
                    ) + 1
                    return SimpleNamespace(
                        completed=True,
                        status=SimpleNamespace(value="success"),
                        value=self.annotation(),
                    )

                def get_annotation(self, annotation_id, *, user_scope):
                    assert annotation_id == ANNOTATION_ID and user_scope == "local"
                    return SimpleNamespace(completed=True, value=self.annotation())

                def list_annotation_evidence(self, *_args, **_kwargs):
                    return SimpleNamespace(
                        completed=True,
                        value=SimpleNamespace(items=(), total=0),
                    )

                def create_concept_evidence_link(self, **_values):
                    attempts = int(st.session_state.get("fake_link_attempts", 0)) + 1
                    st.session_state["fake_link_attempts"] = attempts
                    if attempts == 1:
                        return SimpleNamespace(
                            completed=False,
                            status=SimpleNamespace(value="error"),
                            value=None,
                        )
                    st.session_state["fake_link_count"] = 1
                    return SimpleNamespace(
                        completed=True,
                        status=SimpleNamespace(value="success"),
                        value=SimpleNamespace(evidence_link_id="ev_fake_retry"),
                    )


            context = ConceptLinkingContext(
                database_name="temporary_s4_3",
                document_id="doc_123e4567-e89b-42d3-a456-426614174000",
                document_title="Boundary Behaviour of Conformal Maps",
                document_kind="pdf",
                source_id="src_123e4567-e89b-42d3-a456-426614174000",
                source_name="Pommerenke1991BoundaryBehaviourConformalMaps",
                reference_id=None,
                reference_title=None,
                pdf_page=9,
                book_page_label="1",
                reading_status="in_progress",
            )
            if not st.session_state.get("fake_booted"):
                start_wizard(st.session_state, context)
                st.session_state["fake_booted"] = True
            render_linking_wizard(
                st,
                Database(),
                Service(),
                context=context,
                document_evidence=(),
                quick_sections=(),
                actions_enabled=True,
            )
            st.metric("Annotations", st.session_state.get("fake_annotation_count", 0))
            st.metric("Link attempts", st.session_state.get("fake_link_attempts", 0))
            st.metric("Links", st.session_state.get("fake_link_count", 0))
            """
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file)).run()
    next(item for item in app.text_input if item.label == "Buscar concepto").input("Métrica")
    app.run()
    next(button for button in app.button if button.label == "Seleccionar").click()
    app.run()
    app.run()

    next(item for item in app.radio if item.label == "Tipo de evidencia").set_value("annotation")
    app.run()
    next(item for item in app.radio if item.label == "Evidencia disponible").set_value("new")
    app.run()
    next(item for item in app.text_area if item.label == "Cita").input("spherical metric")
    next(item for item in app.selectbox if item.label == "Tipo de relación").select(
        "definition_source"
    )
    next(
        item for item in app.text_area if item.label == "¿Por qué esta evidencia es relevante?"
    ).input("La cita introduce la métrica.")
    app.run()
    next(button for button in app.button if button.label == "Guardar asociación").click()
    app.run()

    assert not app.exception
    assert [item.value for item in app.metric] == ["1", "1", "0"]
    assert app.session_state[MODE] == "annotation"
    assert app.session_state[PARTIAL_TARGET_ID] == annotation_id
    assert any("La anotación se guardó" in item.value for item in app.warning)
    selected_preview = " ".join(item.value for item in (*app.caption, *app.markdown))
    assert "spherical metric" in selected_preview
    assert "A logical highlight" in selected_preview
    assert "Book page 1 · PDF page 9" in selected_preview
    assert "Tags: boundary" in selected_preview
    assert "Estado: active" in selected_preview
    retry = next(button for button in app.button if button.label == "Reintentar vínculo")
    assert retry.disabled is False

    retry.click()
    app.run()

    assert not app.exception
    assert [item.value for item in app.metric] == ["1", "2", "1"]
    assert any("Evidencia guardada" in item.value for item in app.success)
    assert PARTIAL_TARGET_ID not in app.session_state
    assert ACTIVE not in app.session_state


def test_duplicate_card_persists_and_its_navigation_runs_on_a_later_rerun(
    tmp_path: Path,
) -> None:
    app_file = tmp_path / "concept_linking_duplicate_app.py"
    app_file.write_text(
        textwrap.dedent(
            """
            from types import SimpleNamespace

            import streamlit as st

            from editor.concept_linking.linking_wizard import render_linking_wizard
            from editor.concept_linking.state import start_wizard
            from editor.concept_linking.view_models import ConceptLinkingContext


            class Cursor(list):
                def sort(self, *_args, **_kwargs):
                    return self

                def skip(self, count):
                    return Cursor(self[count:])

                def limit(self, count):
                    return Cursor(self[:count])


            class Concepts:
                document = {
                    "id": "metric-spherical",
                    "source": "Pommerenke1991",
                    "titulo": "Métrica esférica",
                    "tipo": "Definición",
                }

                def find(self, _query, _projection):
                    return Cursor([dict(self.document)])

                def find_one(self, query, _projection):
                    expected = {"id": self.document["id"], "source": self.document["source"]}
                    return dict(self.document) if query == expected else None


            class Database:
                def __init__(self):
                    self.concepts = Concepts()

                def __getitem__(self, name):
                    if name != "concepts":
                        raise KeyError(name)
                    return self.concepts


            class EvidenceRepository:
                @staticmethod
                def link():
                    return SimpleNamespace(
                        evidence_link_id="ev_existing",
                        concept_legacy_id="metric-spherical",
                        concept_legacy_source="Pommerenke1991",
                        source_id="src_123e4567-e89b-42d3-a456-426614174000",
                        reference_id=None,
                        document_id="doc_123e4567-e89b-42d3-a456-426614174000",
                        annotation_id=None,
                        note_id=None,
                        page_number=9,
                        link_type=SimpleNamespace(value="definition_source"),
                        comment="Existing relation",
                        status=SimpleNamespace(value="active"),
                    )

                def count_by_concept(self, *_args, **_kwargs):
                    return 1

                def find_exact(self, _candidate):
                    return self.link()

                def get_by_id(self, evidence_link_id):
                    return self.link() if evidence_link_id == "ev_existing" else None


            class Service:
                def __init__(self):
                    self.evidence = EvidenceRepository()

                def create_concept_evidence_link(self, **_values):
                    st.session_state["unexpected_writes"] = int(
                        st.session_state.get("unexpected_writes", 0)
                    ) + 1
                    raise AssertionError("an exact duplicate must not be written")


            context = ConceptLinkingContext(
                database_name="temporary_s4_3",
                document_id="doc_123e4567-e89b-42d3-a456-426614174000",
                document_title="Boundary Behaviour of Conformal Maps",
                document_kind="pdf",
                source_id="src_123e4567-e89b-42d3-a456-426614174000",
                source_name="Pommerenke1991BoundaryBehaviourConformalMaps",
                reference_id=None,
                reference_title=None,
                pdf_page=9,
                book_page_label="1",
                reading_status="in_progress",
            )
            if not st.session_state.get("fake_booted"):
                start_wizard(st.session_state, context)
                st.session_state["fake_booted"] = True
            render_linking_wizard(
                st,
                Database(),
                Service(),
                context=context,
                document_evidence=(),
                quick_sections=(),
                actions_enabled=True,
            )
            st.metric("Escrituras inesperadas", st.session_state.get("unexpected_writes", 0))
            """
        ),
        encoding="utf-8",
    )

    app = AppTest.from_file(str(app_file)).run()
    next(item for item in app.text_input if item.label == "Buscar concepto").input("Métrica")
    app.run()
    next(button for button in app.button if button.label == "Seleccionar").click()
    app.run()
    app.run()
    next(item for item in app.selectbox if item.label == "Tipo de relación").select(
        "definition_source"
    )
    app.run()
    next(button for button in app.button if button.label == "Guardar asociación").click()
    app.run()

    assert not app.exception
    assert app.metric[0].value == "0"
    assert any("ya está asociado" in item.value for item in app.warning)
    assert any(button.label == "Abrir evidencia" for button in app.button)

    app.run()
    next(button for button in app.button if button.label == "Guardar asociación").click()
    app.run()
    assert not app.exception
    assert app.metric[0].value == "0"

    next(button for button in app.button if button.label == "Abrir evidencia").click()
    app.run()
    assert not app.exception
    assert app.session_state[PENDING_WORKSPACE_TAB] == "Workspace"


__all__ = []

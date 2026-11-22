"""The retained browse page uses the same guarded deletion as editing."""

from uuid import uuid4

import pytest

from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service
from tests.test_legacy_page_behaviors import app_for

owned_client = _owned_client
service = _service


@pytest.mark.parametrize("has_evidence", [False, True])
def test_browse_uses_shared_deletion_and_blocks_linked_research(
    service, tmp_path, monkeypatch, has_evidence
):
    """Use the actual browse action to retain research or remove observed edges."""
    first = service.execute(create(service))["key"]
    other = service.execute(create(service, titulo="Otro concepto"))["key"]
    for origin, target in [(first, other), (other, first)]:
        service.execute(
            {"operation_id": str(uuid4()), "action": "connect", "key": origin, "target": target}
        )
    concept = service.find(first)
    service.db.reading_notes.insert_one({"note_id": "retained", "body": "Trabajo conservado"})
    if has_evidence:
        service.db.concept_evidence_links.insert_one(
            {
                "concept_legacy_id": concept["id"],
                "concept_legacy_source": concept["source"],
                "note_id": "retained",
            }
        )
    app = app_for(service, tmp_path, monkeypatch, "concepts")
    assert not app.exception
    expander = next(
        item for item in app.expander if item.label.startswith(concept["titulo"] + " (")
    )
    next(button for button in expander.button if button.label == "Eliminar concepto…").click().run(
        timeout=30
    )
    assert not app.exception
    if has_evidence:
        assert not any(button.label == "Confirmar eliminación" for button in app.button)
        assert any("vínculos de procedencia" in item.value for item in app.warning)
        assert service.find(first) == concept
        assert service.db.relations.count_documents({}) == 2
    else:
        next(
            item
            for item in app.text_input
            if item.label == "Escribe el nombre del concepto para confirmar"
        ).input(concept["titulo"]).run(timeout=30)
        next(
            button for button in app.button if button.label == "Confirmar eliminación"
        ).click().run(timeout=30)
        assert not app.exception
        assert service.find(first) is None
        assert service.db.relations.count_documents({}) == 0
    assert service.find(other) is not None
    assert (
        service.db.reading_notes.find_one({"note_id": "retained"})["body"] == "Trabajo conservado"
    )
    app.session_state.context.db.client.close()

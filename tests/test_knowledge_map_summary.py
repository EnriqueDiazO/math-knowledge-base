"""Navigation projects metadata without fetching full mathematical documents."""

from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service


def test_summary_does_not_read_latex_and_compatibility_snapshot_preserves_it(service, monkeypatch):
    """Only opening content should pay for large bodies; old consumers retain parity."""
    content = r"\begin{definition}{Texto original} G \end{definition}" * 1000
    created = service.execute(create(service, contenido_latex=content))
    collection_type = type(service.mongo.latex_documents)
    original = collection_type.find

    def projected(collection, *args, **kwargs):
        assert collection.name != "latex_documents", "Summary requested complete content"
        return original(collection, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(collection_type, "find", projected)
        summary = service.graph(include_content=False)
    assert summary["nodes"][0]["key"] == created["key"]
    assert summary["nodes"][0]["contenido_latex"] == ""
    assert summary["nodes"][0]["revision"] == ""
    assert service.graph()["nodes"][0]["contenido_latex"] == content

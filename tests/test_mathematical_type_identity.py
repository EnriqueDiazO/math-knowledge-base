"""The eight LaTeX families remain real canonical concepts, not colored copies."""

import json
from pathlib import Path

import pytest

from tests.test_knowledge_map_service import create
from tests.test_knowledge_map_service import owned_client as _owned_client
from tests.test_knowledge_map_service import service as _service

owned_client = _owned_client
service = _service
PALETTE = json.loads(
    (Path(__file__).resolve().parents[1] / "editor/ui/concept_types.json").read_text()
)


@pytest.mark.parametrize("kind", PALETTE)
def test_mathematical_family_round_trip_uses_one_canonical_identity(service, kind):
    """Verify mathematical family round trip uses one canonical identity."""
    latex = rf"\begin{{cth{kind}}}{{Título propio}}Una idea $\frac{{1}}{{2}}$.\end{{cth{kind}}}"
    intent = create(service, tipo=kind, titulo=PALETTE[kind]["label"], contenido_latex=latex)
    saved = service.execute(intent)
    assert saved["status"] == "saved", saved
    original = service.find(saved["key"])
    assert original["tipo"] == kind
    assert service.latex(original)["contenido_latex"] == latex
    assert service.execute(intent)["key"] == saved["key"]
    assert service.db.concepts.count_documents({}) == 1
    node = service.graph(include_content=False)["nodes"][0]
    assert node["tipo"] == kind and node["key"] == saved["key"]
    assert node["contenido_latex"] == ""

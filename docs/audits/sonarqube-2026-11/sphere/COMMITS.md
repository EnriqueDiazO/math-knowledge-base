# Commits de funcionalidad

Rama derivada del checkpoint `de166650`; todo local, sin push ni merge.

| Commit | Cambio | Pruebas/contrato |
|---|---|---|
| `77b9a656` | feat(map): persist validated recoverable concept and relation intentions | `tests/test_knowledge_map_service.py` |
| `411db6bc` | feat(map): integrate an editable S2 canvas with the existing knowledge graph | `frontend/advanced-reader/tests/knowledge-map.test.ts`; `tests/test_knowledge_map_bridge.py` |
| `07684bb3` | test(map): exercise real application persistence and measured canvas workloads | `frontend/advanced-reader/tests/knowledge-map-browser.mjs`; `tests/run_knowledge_map_e2e.py` |
| `8e826658` | fix(map): preserve partial edit drafts through explicit conflict review | `frontend/advanced-reader/tests/knowledge-map-browser.mjs`; `frontend/advanced-reader/tests/knowledge-map.test.ts` |
| `74331518` | fix(map): retain referenced metadata and reconcile interrupted creations safely | `tests/test_knowledge_map_service.py` |
| `a30264f4` | refactor(map): preserve identity ordering and run browser checks in the test lifecycle | `frontend/advanced-reader/tests/knowledge-map-browser.mjs`; `frontend/advanced-reader/tests/knowledge-map-playwright.config.mjs`; `frontend/advanced-reader/tests/knowledge-map.test.ts`; `tests/run_knowledge_map_e2e.py` |
| `dd5316cc` | test(map): document contracts and capture the completed responsive layout | `frontend/advanced-reader/tests/knowledge-map-browser.mjs`; `tests/run_knowledge_map_e2e.py`; `tests/test_knowledge_map_bridge.py`; `tests/test_knowledge_map_service.py` |
| `f5ddb587` | test(map): verify offline reconciliation and narrow contextual editing | `frontend/advanced-reader/tests/knowledge-map-browser.mjs`; `tests/test_knowledge_map_service.py` |

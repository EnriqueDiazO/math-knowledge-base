# Cobertura nueva por archivo

Referencia conservada: PREVIOUS_VERSION / 2026-11-21T16:46:16+0000.
Análisis final: f62b032f-c663-4c1c-97a2-c57a555387c0; revisión 8723ab2ba555f414e9d840e5e4701254062cf89f.

| Archivo | Líneas cubiertas | Sin cubrir | Condiciones cubiertas | Sin cubrir | Líneas sin cubrir |
|---|---:|---:|---:|---:|---|
| editor/db/concept_repository.py | 6 | 0 | 0 | 0 | — |
| editor/interactive_graph.py | 11 | 0 | 0 | 0 | — |
| editor/note_branding.py | 2 | 0 | 0 | 0 | — |
| editor/source_catalog/shared.py | 1 | 0 | 0 | 0 | — |
| editor/utils/media_assets.py | 2 | 0 | 0 | 0 | — |
| exporters_latex/exportar_qmd_desde_mongo.py | 13 | 1 | 0 | 0 | 33 |
| frontend/advanced-reader/scripts/prepare-pdf-worker.mjs | 0 | 1 | 0 | 0 | 14 |
| frontend/advanced-reader/scripts/publish-build.mjs | 0 | 1 | 0 | 0 | 8 |
| frontend/advanced-reader/src/app/App.tsx | 2 | 0 | 2 | 0 | — |
| frontend/advanced-reader/src/pdf/PdfJsController.ts | 1 | 0 | 0 | 0 | — |
| parsers/markdownparser.py | 3 | 0 | 0 | 0 | — |
| parsers/yaml_latex_parser.py | 2 | 0 | 0 | 0 | — |
| scripts/export_knowledge_graph.py | 28 | 1 | 0 | 0 | 43 |
| scripts/quality.py | 43 | 1 | 0 | 0 | 70 |
| scripts/quality_mongo.py | 68 | 1 | 0 | 0 | 77 |
| scripts/sonar.py | 233 | 11 | 0 | 0 | 107,108,109,110,166,177,279,289,311,313,331 |
| visualizations/grafoconocimiento.py | 5 | 0 | 0 | 0 | — |

Total: **420/437 líneas y 2/2 condiciones**; (420+2)/(437+2)=**96,1%**.

NEW_COVERAGE.csv conserva además cada línea cubierta. El detalle de lineHits,
conditions y coveredConditions de la API está en final-line-coverage.json local.

## Déficit residual demostrado

- scripts/sonar.py: 11 líneas. token_auth (107–110) fue usado por el comando real
  fuera del proceso medido y sustituido por dobles en tests de scan; faltan pruebas
  focalizadas de precedencia/ausencia de token. 166/177 son puerto ocupado y timeout
  total de arranque; 279/289 readiness y reporte malformado; 311/313 despacho CLI
  scan/snapshot (sus funciones sí se prueban); 331 entrada __main__ fuera de coverage.
- quality.py: 70, entrada __main__ del runner padre fuera de coverage; main sí está
  verificado. quality_mongo.py: 77, falta simular que un hijo deja bases sin retirar.
- export_knowledge_graph.py: 43, entrada __main__; el E2E invoca main desde un hijo
  e inspecciona salida/DB. QMD: 33, lista tipo vacía; hay pruebas de tipos/rutas
  inválidos pero no de esa entrada concreta.
- prepare-pdf-worker.mjs:14 y publish-build.mjs:8: scripts Node fuera del LCOV de
  Vitest/src; se verificaron operativamente en la fase anterior, no se afirma
  cobertura V8 de esos dos scripts. Permanecen incluidos en Sonar.

Tooling de auditoría exacto (sonar/quality/quality_mongo): 344/357 líneas nuevas,
13 sin cubrir; representa 13/17=76,5% del déficit residual, frente a 214/247=86,6%
antes. Dos de esas 13 son entradas padre __main__ sin instrumentación en este job.
Los dos scripts de build agregan otros dos huecos instrumentales. Los huecos
restantes son pruebas focalizadas pendientes; no bloquean el umbral conservado.

# Diagnóstico previo a nuevas pruebas

Fecha: 2026-11-21. Rama audit/sonarqube-2026-11 limpia al inicio; HEAD ecc3df0b, sin avances posteriores que preservar. Se reutilizan los once commits y toda su evidencia. No se añadieron pruebas antes de este diagnóstico.

Análisis consultado en el servidor: `f7d5bcc2-691b-4a6e-ae2b-91d8f759911e`; revisión `4b8cb48c5c0b21cf09c2f7f02f7fc7b8f248e391`; fecha API 2026-11-21T17:30:35Z; CE SUCCESS. El commit ecc3df0b sólo añadió documentación.

## Condiciones y referencia

Gate ERROR: new_coverage 31.2 < 80; new_duplicated_lines_density 0.0 <= 3; new_violations 0 <= 0. API new_code_periods/show: PREVIOUS_VERSION, heredado; periodo efectivo del Gate: 2026-11-21T16:46:16+0000. Las líneas nuevas provienen del SCM posterior a esa fecha, no de todo el árbol.

ProjectVersion del análisis: `not provided`. Makefile pasa SONAR_LABEL a --label; sonar.scan no pasa projectVersion al scanner y snapshot sólo usa el label en el nombre del JSON. Cambiar baseline/final/latest no crea una versión ni reinicia la referencia. Se conservará exactamente este periodo.

## Desglose por archivo (API, antes de cambios)

| Archivo | Líneas cubiertas | Sin cubrir | Condiciones nuevas | Sin cubrir |
|---|---:|---:|---:|---:|
| editor/db/concept_repository.py | 5 | 1 | 0 | 0 |
| editor/interactive_graph.py | 9 | 0 | 0 | 0 |
| editor/utils/media_assets.py | 2 | 0 | 0 | 0 |
| exporters_latex/exportar_qmd_desde_mongo.py | 7 | 7 | 0 | 0 |
| frontend/advanced-reader/scripts/prepare-pdf-worker.mjs | 0 | 1 | 0 | 0 |
| frontend/advanced-reader/scripts/publish-build.mjs | 0 | 1 | 0 | 0 |
| frontend/advanced-reader/src/app/App.tsx | 0 | 2 | 0 | 0 |
| frontend/advanced-reader/src/pdf/PdfJsController.ts | 0 | 1 | 0 | 0 |
| parsers/markdownparser.py | 3 | 0 | 0 | 0 |
| parsers/yaml_latex_parser.py | 2 | 0 | 0 | 0 |
| scripts/export_knowledge_graph.py | 9 | 20 | 0 | 0 |
| scripts/quality.py | 0 | 20 | 0 | 0 |
| scripts/quality_mongo.py | 0 | 63 | 0 | 0 |
| scripts/sonar.py | 70 | 131 | 0 | 0 |
| visualizations/grafoconocimiento.py | 5 | 0 | 0 | 0 |

Total: 112/359 líneas cubiertas, 247 sin cubrir; 0 condiciones nuevas. Python no tenía branch=True y los reportes importados no medían condiciones. El 31.2% es 112/359, no una mezcla de líneas y condiciones en este análisis.

Tooling de análisis/verificación, definido como sonar.py + quality.py + quality_mongo.py: 284/359 líneas nuevas (79.1%); 70 cubiertas y 214/247 sin cubrir (86.6%). Export_knowledge_graph.py es un CLI funcional de la app, contabilizado por separado: 29 nuevas, 9 cubiertas y 20 sin cubrir. Los 13 huecos restantes corresponden a QMD/rollback/frontend.

## Números exactos de línea en la revisión analizada

**editor/db/concept_repository.py**: cubiertas 75–78, 86. Sin cubrir 82.

**editor/interactive_graph.py**: cubiertas 8, 256–258, 411, 445, 505–507. Sin cubrir —.

**editor/utils/media_assets.py**: cubiertas 329, 349. Sin cubrir —.

**exporters_latex/exportar_qmd_desde_mongo.py**: cubiertas 6, 32, 35–38, 46. Sin cubrir 33, 78, 84–85, 87–88, 91.

**frontend/advanced-reader/scripts/prepare-pdf-worker.mjs**: cubiertas —. Sin cubrir 14.

**frontend/advanced-reader/scripts/publish-build.mjs**: cubiertas —. Sin cubrir 8.

**frontend/advanced-reader/src/app/App.tsx**: cubiertas —. Sin cubrir 368–369.

**frontend/advanced-reader/src/pdf/PdfJsController.ts**: cubiertas —. Sin cubrir 51.

**parsers/markdownparser.py**: cubiertas 117–119. Sin cubrir —.

**parsers/yaml_latex_parser.py**: cubiertas 28–29. Sin cubrir —.

**scripts/export_knowledge_graph.py**: cubiertas 3, 5–6, 8–11, 14, 42. Sin cubrir 16–22, 24, 26, 28, 30–35, 37–39, 43.

**scripts/quality.py**: cubiertas —. Sin cubrir 3, 5–9, 11, 14, 16–23, 30, 35, 38–39.

**scripts/quality_mongo.py**: cubiertas —. Sin cubrir 3, 5–12, 14–15, 17–18, 22, 24–35, 40–58, 62–65, 68, 70–73, 75–81, 84–85.

**scripts/sonar.py**: cubiertas 3, 5–26, 28–35, 38, 41, 46, 48–55, 57, 61, 69, 74, 85, 90, 98, 104, 106–107, 110, 113, 140, 165, 194, 234, 236–245, 250, 278. Sin cubrir 43, 58, 63–66, 71, 76–77, 79–82, 87, 92–95, 100, 108, 115–124, 126–130, 133–137, 142–143, 145–147, 149–162, 167–170, 172–178, 180–187, 189–191, 198–206, 210–211, 213–222, 227–231, 246–247, 252–265, 267, 269, 271–275, 279.

**visualizations/grafoconocimiento.py**: cubiertas 19, 21, 869–870, 1051. Sin cubrir —.

## Causas diferenciadas y evidencia

- Importación Python correcta: final-native-scan.log registra Parsing report evidence/sonar/coverage.xml, sin Cannot resolve. baseline-coverage.xml y final-coverage.xml contienen rutas relativas inequívocas. La API settings/values muestra defaults heredados de servidor, no los overrides efectivos enviados por sonar-project.properties. No se cambiarán esos defaults para arreglar un problema inexistente.
- Instrumentación incompleta: pytest-cov 7 eliminó el arranque automático en procesos hijos. .coveragerc no tenía patch=subprocess; los E2E se lanzaron separadamente sin coverage run. Por eso calidad_mongo y partes del export/rollback, aunque probadas operacionalmente, no contribuyen al XML. Se corregirá el arranque/combination de datos por proceso, preservando alcance de fuentes y medición de líneas.
- Reporte JS ausente: npm test ejecutaba Vitest sin cobertura, no existe LCOV y no había sonar.javascript.lcov.reportPaths. Los tests sí pasan pero Sonar ve cero hits JS. Se generará e importará LCOV con proveedor compatible con Vitest instalado. Se documentará el cambio de alcance instrumental, sin excluir fuentes del scanner.
- Pruebas ausentes: seis tests del tooling verificaban URLs, preservar .env y reporte obsoleto, pero no cubrían bootstrap HTTP, permisos/instalación, fallos del proceso/daemon, paginación y consistencia de snapshots, limpieza de recursos ni propagación de errores. Son casos nuevos relevantes; medir lo ya ejecutado no sustituye esas pruebas.

Fuentes primarias de instrumentación: [pytest-cov 7](https://pytest-cov.readthedocs.io/en/latest/subprocess-support.html), [coverage 7.16.2](https://coverage.readthedocs.io/en/7.16.2/subprocess.html), [LCOV/Sonar](https://docs.sonarsource.com/sonarqube-community-build/analyzing-source-code/test-coverage/javascript-typescript-test-coverage).

El JSON detallado local before-line-coverage.json permite comprobar cada línea contra el servidor. Las evidencias previas se preservan sin sobrescribir baseline/final; las nuevas usan followup-* y directorio de fase.

## Error de rutas descubierto al habilitar hijos

El primer smoke de instrumentación aprobó 28 tests, pero se interrumpió durante el
reporte porque un hijo con cwd distinto interpretaba los omit relativos contra ese
cwd y entraba al venv. No es un resultado de calibración aprobado. Coverage 7.16.2
serializa source/data_file absolutos para sus hijos, pero no omit (config.py,
SERIALIZE_ABSPATH). Se genera coverage-runtime.ini desde .coveragerc anclando source
y los mismos diez omit a ROOT. No se añade ninguna exclusión. El smoke corregido
aprueba 28 unitarios y 9 E2E; el XML no contiene tests/venv/.tools y sí los módulos
propios. Esta normalización es parte de la reparación instrumental, no del Gate.

LCOV inicial de los 107 tests existentes: líneas 1266/1508 (83.95%), ramas 736/1063
(69.23%). Sonar conservará todos sus archivos fuente; los scripts de build que no
entran en ese reporte no se excluyen del análisis ni de su denominador de cobertura.

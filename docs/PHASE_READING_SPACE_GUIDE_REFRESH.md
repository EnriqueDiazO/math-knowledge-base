# Reading Space Guide Refresh

## A. Baseline

- Repositorio: `math-knowledge-base`
- Rama inicial: `main`
- HEAD inicial: `dd2251d1fcc35144113896b1e3bc5f1fc9bdf29c`
- `origin/main` inicial: `0924de5960f07f119fc4d223dec66926b5ad3430`
- Diferencia inicial: 0 detrás, 1 delante
- Worktree y staging iniciales: limpios
- Tag anotado: `v0.13.0-managed-source-workflow`
- Objeto del tag: `75097ac327929aabe3fc0516e0610fe27a95d371`
- Commit apuntado por el tag: `0924de5960f07f119fc4d223dec66926b5ad3430`
- No existía comando documentado ni target reproducible para construir esta guía.

PDF anterior:

- 62 páginas A4
- 6,848,375 bytes
- SHA-256 `fa9346a7481962c1b9fc241f4d83386c321f813f37b70f1c453f8f80492b7e83`
- PDF 1.4, tagged, texto seleccionable y fuentes incrustadas

## B. Fuente canónica

- Markdown: `docs/user-guide/GUIA_READING_SPACE_MATHMONGO.md`
- PDF: `docs/user-guide/GUIA_READING_SPACE_MATHMONGO.pdf`
- Assets: `docs/user-guide/images/`
- Assets principales nuevos: `docs/user-guide/images/reading-space-v013/`

La fuente canónica fue identificada antes de editar. No se creó una guía paralela ni se cambió el nombre del PDF.

## C. Contenido actualizado

La guía quedó organizada en 18 secciones numeradas:

1. Introducción
2. Requisitos
3. Flujo general
4. Base activa
5. Crear una Source
6. Añadir un concepto nuevo
7. Abrir Reading Space
8. Leer en Advanced Reader
9. Crear anotaciones y evidence
10. Trabajar en Cuaderno
11. Promover desde Cuaderno
12. Editar conceptos
13. Conceptos legacy
14. Document Builder y Knowledge Maps
15. Exportación y respaldo
16. Problemas frecuentes
17. Limitaciones v0.13.0
18. Buenas prácticas

Se añadieron o ampliaron de forma material:

- verificación de la base real y cambio seguro;
- alta de Source, Reference y PDF;
- contrato `source` + `source_id` para Concepts nuevos;
- identidad `id@source` para datos legacy;
- flujo Reading Space completo;
- Advanced Reader y mapeo de páginas;
- annotations, Reading Notes y evidence;
- Cuaderno contextual y promoción desde el Diario LaTeX;
- identidad inmutable en Edit Concept;
- enlace explícito de un Concept legacy;
- Document Builder, Knowledge Graph, Knowledge Maps y Page Map;
- respaldo, exportación, importación y diagnóstico;
- limitaciones exactas de v0.13.0.

Se retiraron la narrativa y los start-flows visuales de la versión anterior que ya no representaban la interfaz administrada actual. No se eliminó ninguna sección obligatoria del alcance solicitado.

La guía enlaza:

- `docs/MANAGED_SOURCE_WORKFLOW.md`
- `docs/RELEASE_NOTES_v0.13.0_MANAGED_SOURCE_WORKFLOW.md`
- `docs/VERSION_CLOSURE_MANAGED_SOURCE_WORKFLOW.md`

## D. Capturas reemplazadas

Se capturaron 12 pantallas reales de la aplicación y se validaron individualmente:

1. `01_active_database.png`
2. `02_add_source.png`
3. `03_source_details.png`
4. `04_add_concept.png`
5. `05_reading_space.png`
6. `06_advanced_reader.png`
7. `07_evidence_link.png`
8. `08_cuaderno.png`
9. `09_cuaderno_promote.png`
10. `10_edit_concept.png`
11. `11_legacy_link.png`
12. `12_document_builder_or_graph.png`

Condiciones comunes:

- 1600 × 1000, RGB;
- tema oscuro consistente;
- mismo runtime y misma base temporal;
- viewport de la aplicación, sin escritorio ni chrome del navegador;
- sin popups, notificaciones, datos personales o rutas privadas;
- contenido completamente sintético.

El baseline contenía 50 PNG rastreados. Se eliminaron únicamente ocho capturas obsoletas y sin referencia documental:

- `docs/user-guide/images/01_inicio.png`
- `docs/user-guide/images/start-flows/case1_01_base_vacia.png`
- `docs/user-guide/images/start-flows/case1_02_add_source.png`
- `docs/user-guide/images/start-flows/case1_03_source_guardada.png`
- `docs/user-guide/images/start-flows/case1_05_add_concept.png`
- `docs/user-guide/images/start-flows/case2_01_source_pdf.png`
- `docs/user-guide/images/start-flows/case2_04_add_concept.png`
- `docs/user-guide/images/start-flows/case3_01_source_conceptos.png`

Las otras 42 capturas históricas se conservaron deliberadamente. Con las 12 nuevas, el directorio queda con 54 PNG rastreados. No hubo borrado masivo.

## E. Base temporal

- Nombre: `MathMongoReadingSpaceGuide_9b11e538`
- Verificación previa: ausente y distinto de `MathV0` y `mathmongo`
- Source: `GuiaAlgebraLineal`
- Reference: “Introducción al álgebra lineal”, “Autor de ejemplo”, 2026, sin ISBN
- PDF: cuatro páginas A4 sintéticas
- Concepts gestionados: `espacio_vectorial`, `base_vectorial`, `transformacion_lineal`
- Concept legacy: `subespacio_legacy@ReferenciaLegacyDemo`
- Annotation: una
- Reading Note: una
- Evidence link: uno
- Nota del Diario LaTeX: una

Antes de eliminarla se comprobaron 18 colecciones y estos conteos principales: 1 Source, 1 Reference, 1 Source Document, 4 Concepts, 1 Annotation, 1 Reading Note, 1 evidence link y 1 nota LaTeX.

La base fue eliminada y se verificó que ya no aparecía en `list_database_names()`. `MathV0` no se abrió para escritura, no recibió backfill y no fue objetivo de migración.

## F. Flujo documentado

El flujo final documenta:

`Base activa → Add Source → Reference/Document → Add Concept → Biblioteca → Leer → Advanced Reader → Annotation/Reading Note → Evidence → Cuaderno → Promote → Edit Concept → Legacy Link → Document Builder/Maps → Export/Backup`.

Cada figura tiene introducción, caption/alt, puntos a observar y siguiente acción. Se diferencia el Cuaderno contextual de Reading Space del Diario LaTeX experimental.

## G. Construcción del PDF

Se creó el script autorizado `scripts/build_reading_space_guide.sh` con alcance exclusivo a la fuente y el PDF canónicos.

Comando:

```bash
scripts/build_reading_space_guide.sh
```

El script:

- valida fuente, assets, enlaces, Python, Pandoc y Chrome;
- usa sólo temporales bajo `/tmp`;
- genera HTML autocontenido con Pandoc;
- imprime a PDF con Chrome headless;
- evita resolución de red durante el build;
- verifica firma y tamaño del PDF temporal;
- publica por rename atómico sólo tras éxito completo;
- limpia temporales con traps y retorna error ante fallos.

Incidencias encontradas y corregidas:

1. Pandoc requería `--resource-path` para resolver assets independientemente del directorio de ejecución.
2. Chrome resolvía los enlaces relativos contra `/tmp`; el HTML temporal ahora los reescribe al tag estable sin modificar los enlaces locales del Markdown.

Resultado final:

- 21 páginas A4
- 1,647,527 bytes
- SHA-256 `9f8cc7515d941ff8512dbb07c82252665a58b3b02fa6d07252043212e7ce1f36`
- sin warnings de Pandoc o Chrome que afecten el artefacto

## H. Validación visual

Validación técnica:

- `pdfinfo`: 21 páginas A4, PDF 1.4, tagged;
- `pdffonts`: todas las fuentes incrustadas;
- `pdftotext`: texto seleccionable, 605 líneas y 3,919 palabras;
- `pdfinfo -url`: tres enlaces HTTPS al tag estable, ninguna ruta temporal;
- `pdftoppm -png -r 120`: 21 renders RGB de 992 × 1404.

Validación visual:

- páginas 1–9 inspeccionadas en contact sheet;
- páginas 10–18 inspeccionadas en contact sheet;
- páginas 19–21 inspeccionadas en contact sheet;
- capturas finales inspeccionadas también a 1600 × 1000;
- sin clipping horizontal o vertical;
- sin tablas, listas, encabezados o footers cortados;
- sin páginas ausentes;
- sin capturas ilegibles;
- sin información personal.

La página 1 contiene el índice; la portada y el comienzo del contenido están en la página 2. La página 21 conserva espacio en blanco final normal, no contenido cortado.

## I. Archivos modificados

Checkpoint 1:

- fuente Markdown canónica;
- `SCREENSHOT_PLAN.md`;
- 12 PNG nuevos;
- script de build autorizado;
- ocho eliminaciones de imágenes justificadas.

Checkpoint 2:

- PDF canónico;
- `docs/GUIA_READING_SPACE_MATHMONGO_BUILD.md`;
- `docs/PHASE_READING_SPACE_GUIDE_REFRESH.md`.

No se modificó código funcional, configuración de producto, esquema, versión, tests, migraciones o archivos de release.

## J. Commits

1. `207c7c8b4f05aa449608dd3040fc3c5ef32646c9` — `docs(reading): refresh Reading Space guide and screenshots`
2. `docs(pdf): rebuild Reading Space guide` — commit que incorpora el PDF final, BUILD y este reporte.

No se hizo push.

## K. Limpieza

- Se detuvieron únicamente los procesos iniciados por la fase.
- PIDs comprobados como detenidos: Streamlit `196821`, Advanced Reader `196811`, Chrome de captura `197966`.
- Puertos comprobados como libres: 8502, 8767 y 9223.
- Se eliminó `MathMongoReadingSpaceGuide_9b11e538`.
- Se eliminó el PDF demo temporal.
- Se eliminaron perfiles de Chrome, HTML, logs, renders y contact sheets temporales.
- Se verificó que no existía la carpeta de salida escrita en el formulario de Document Builder.
- Se eliminaron 30 directorios `__pycache__`/`.pytest_cache` fuera del virtualenv; no se tocaron dependencias instaladas.
- No quedaron directorios `/tmp/mathmongo-reading-guide-build.*`.
- Se conservaron todos los 12 assets finales usados por la guía.

## L. Limitaciones

Limitaciones de producto documentadas:

- Delete Concept no es integral.
- Browse Concepts y algunos flujos Quarto pueden mostrar IDs duplicados o ambiguos.
- Los diagnósticos de portabilidad de enlaces siguen incompletos.
- La eliminación física tiene límites frente a concurrencia.
- Change Source no está implementado.

Limitaciones de construcción:

- `qpdf` no estaba disponible; se usó la batería requerida de Poppler, apertura, render completo y extracción de texto.
- El PDF no está linearizado (`Optimized: no`), lo cual no afecta lectura local ni validación.
- Los enlaces del PDF necesitan acceso a GitHub cuando el lector intenta abrirlos; el build no usa red.
- El checksum corresponde al artefacto final registrado; regeneraciones de Chrome pueden variar en metadatos.
- Se conservaron 42 PNG históricos para respetar la prohibición de borrado masivo.

## M. Estado Git final

Al cerrar el segundo checkpoint:

- rama: `main`;
- `origin/main...HEAD`: 0 detrás, 3 delante;
- worktree y staging: limpios;
- dos commits documentales nuevos después del baseline funcional;
- tag `v0.13.0-managed-source-workflow` intacto en el objeto `75097ac327929aabe3fc0516e0610fe27a95d371` y el commit `0924de5960f07f119fc4d223dec66926b5ad3430`;
- sin procesos, bases o temporales de la fase;
- sin datos personales;
- sin cambios de código funcional o versión;
- sin migración ni backfill;
- sin push.

Las capturas son reales, pero todos sus datos son sintéticos. No se modificó ningún Concept existente ni se creó una Source fuera de la base demo temporal.

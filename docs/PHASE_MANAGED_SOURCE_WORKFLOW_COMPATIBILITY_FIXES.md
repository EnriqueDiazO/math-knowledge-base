# Managed Source Workflow Compatibility Fixes

## A. Objetivo

Esta fase corrige exclusivamente los cinco hallazgos de severidad alta de la
auditoría de compatibilidad del flujo de Sources administradas: promoción desde
Cuaderno, guardas de borrado de Source, arranque sobre la base configurada y
aislamiento por base de Document Builder y Knowledge Graph/Maps.

No se implementó Change Source ni se amplió el alcance a migraciones,
backfills, cambios de identidad, import/export/update de bases, relaciones,
media, evidence links o índices.

## B. Baseline

El trabajo comenzó en `main`, con `HEAD` y `origin/main` en
`434aa015675ede163b4c3be2c5d4884645c3be69`. El worktree y el staging estaban
limpios, y la divergencia inicial era `0 0`.

El baseline de regresión documentado era:

- 1400 pruebas aprobadas;
- 53 omitidas;
- 4 fallos XDG conocidos y preexistentes.

## C. H-01 Cuaderno Promote

La promoción de una nota ya no acepta `source` como texto libre. La pantalla
carga únicamente Sources administradas activas, muestra `Source.name` y
conserva `source_id` como valor estable de la selección. Un catálogo vacío o un
fallo al cargarlo bloquea la promoción.

La Source seleccionada se rehidrata inmediatamente antes de validar e insertar.
El concepto y su documento LaTeX se insertan atómicamente con el mismo snapshot
`source` y el mismo `source_id`. El flujo no crea, renombra ni modifica Sources;
Add Source continúa siendo el único creador interactivo de Sources.

## D. H-02 Source Delete Guard

`SourceRepository.deletion_blockers` comprueba ahora vínculos modernos por
`source_id` tanto en `concepts` como en `latex_documents`, además de las guardas
legacy exactas ya existentes. Los bloqueos modernos son independientes de
renombres, archivado y snapshots históricos de `source`.

El borrado físico conserva la doble inspección: presenta blockers y vuelve a
consultarlos inmediatamente antes de `delete_one`. Una dependencia creada entre
ambas inspecciones produce `PhysicalDeletionBlockedError`; no hay cascada,
upsert ni eliminación de dependencias. Por ello ningún borrado permitido por
este flujo deja un `source_id` colgante.

## E. H-03 Startup y base activa

El bootstrap registra y selecciona sólo la URI y la base resueltas por
configuración. Se eliminó la construcción incondicional de una conexión literal
`MathV0`; por tanto tampoco se inicializan índices de una base adicional no
seleccionada.

`MathV0` sólo se abre si es la base configurada explícitamente. Las conexiones
adicionales siguen requiriendo la acción explícita `Add Connection` del sidebar.

## F. H-04 Document Builder

Se definió un database scope token estable y opaco a partir de la etiqueta de
conexión y el nombre real de la base. Document Builder usa la estrategia de
invalidación completa al cambiar dicho token.

Antes de consultar conceptos de la base nueva se limpian selección, orden,
filtros, validación, reporte, controles, preview, resultados, mensajes, errores,
flags de exportación y claves de widgets del Builder. Volver a una base anterior
no restaura estado eliminado. El contexto de conexión y base se muestra junto al
documento, y la identidad `id@source` no cambió. El Builder continúa siendo de
sólo lectura respecto de MongoDB.

## G. H-05 Knowledge Graph y Maps

Knowledge Graph/Maps reutiliza exactamente el database scope token del Builder.
El cambio de scope limpia, antes de leer `knowledge_graph_maps`, todo el estado
de creación, HTML, estadísticas, configuración visual, formularios, conceptos y
relaciones seleccionados, edición, `graph_state`, repair/save, preview, export y
widgets `knowledge_graph_*`/`kg_*`.

Además, la identidad de un mapa cargado combina database scope, `_id` y
`map_uid`. Editar, guardar, sincronizar o reparar requiere que esa identidad
corresponda al mapa recargado desde la base activa. Así, clones con el mismo
`_id`, el mismo `map_uid` o ambos no reutilizan posiciones, aristas ni estado de
otra base. La limpieza del switch sólo modifica `session_state`: no escribe
`knowledge_graph_maps`, Sources, concepts ni relations.

## H. Invariantes preservadas

- Add Source sigue siendo el único flujo interactivo que crea Sources.
- Todo concepto nuevo promovido desde Cuaderno guarda `source` y `source_id`.
- Los conceptos legacy siguen siendo válidos dentro de su propia base.
- `id`, `source` e `id@source` no cambian.
- Edit Concept no crea ni cambia Sources.
- Vincular un legacy continúa añadiendo únicamente `source_id`.
- No se implementó Change Source, Repair link, Synchronize snapshot ni unlink.
- No se ejecutó migración ni backfill.
- No se modificaron conceptos existentes ni datos reales.
- No se modificaron índices, relaciones, media ni evidence links.
- No se modificaron los flujos de import/export/update de bases.

## I. Pruebas por checkpoint

- H-01: la fase roja demostró 2 fallos; la validación focalizada final aprobó 30
  pruebas.
- H-02: la fase roja demostró 4 fallos; la validación focalizada final aprobó 98
  pruebas.
- H-03: 63 pruebas aprobadas y 1 omitida.
- H-04: 49 pruebas focalizadas de Builder, PDF, startup y scope aprobadas.
- H-05: 94 pruebas focalizadas de Graph/Maps, backup, session state y contratos
  relacionados aprobadas.
- Matriz integral focalizada con el runner del repositorio: 364 aprobadas, 2
  omitidas y 1 warning de serialización Pydantic.

Los E2E Mongo opt-in de base nueva y legacy link se mantuvieron desactivados.
Todas las pruebas de persistencia añadidas usan fakes/spies y no una base real.

## J. Regresión completa

La regresión efectiva se ejecutó una vez con el entorno oficial del repositorio,
`mathdbmongo/bin/python -m pytest -q`, y los E2E Mongo opt-in desactivados.
Resultado:

- 1432 pruebas aprobadas;
- 53 omitidas;
- 4 fallos;
- 7 warnings;
- duración: 65.85 segundos.

Los cuatro fallos son exactamente los XDG preexistentes del baseline: tres en
`tests/test_xdg_media_paths.py` y uno en
`tests/test_xdg_mutable_guards.py`. La fase añade 32 pruebas aprobadas frente al
baseline y cero fallos nuevos.

Una invocación inicial con el `pytest` global no llegó a ejecutar pruebas porque
ese intérprete carecía de FastAPI. No se instaló ni modificó ninguna dependencia;
la corrida efectiva usó el entorno definido por el repositorio.

## K. Archivos modificados

Código de producción:

- `editor/cuaderno_page.py`;
- `editor/database_connections.py`;
- `editor/database_scope.py`;
- `editor/document_builder.py`;
- `editor/editor_streamlit.py`;
- `mathmongo/source_catalog/repository.py`.

Pruebas:

- `tests/test_cuaderno_managed_source_promotion.py`;
- `tests/test_database_connection_bootstrap.py`;
- `tests/test_document_builder_database_scope.py`;
- `tests/test_knowledge_graph_database_scope.py`;
- `tests/test_source_catalog_repository.py`;
- `tests/test_source_catalog_service.py`.

Documentación:

- `docs/PHASE_MANAGED_SOURCE_WORKFLOW_COMPATIBILITY_FIXES.md`.

## L. Commits

- `69980467 fix(cuaderno): require managed source for promotion`;
- `8ebf8fa4 fix(sources): block deletion with managed concept links`;
- `79b515b1 fix(startup): avoid implicit MathV0 initialization`;
- `fd3eda8a fix(builder): isolate document state by database`;
- `1a8250da fix(graphs): isolate knowledge map state by database`;
- `docs: record managed source compatibility fixes` (este documento).

No se hizo push.

## M. Datos y bases

No se modificó MongoDB real, no se escribió en `MathV0` y no se inicializó una
base adicional. No se ejecutaron migraciones, backfills, importaciones,
exportaciones ni updates de bases. Tampoco se modificaron conceptos reales,
Sources, relaciones, media, evidence links o índices reales.

## N. Limitaciones

Esta fase no resuelve los hallazgos medios o bajos de la auditoría ni implementa
Change Source. Los cuatro fallos XDG conocidos siguen presentes y quedan fuera
de alcance. Ruff conserva deuda previa en tres archivos legacy modificados por
necesidad (`cuaderno_page.py`, `document_builder.py` y `editor_streamlit.py`),
pero la comparación contra `origin/main` confirma cero findings nuevos.

No se ejecutaron E2E contra MongoDB; la evidencia de esta fase es determinista y
se basa en pruebas unitarias, de UI estática y fakes/spies.

## O. Próxima fase

El siguiente trabajo requiere un prompt separado para revisar el cierre de
versión del Managed Source Workflow y decidir explícitamente qué hallazgos
medios/bajos se aceptan o pasan a una fase posterior. No debe iniciarse Change
Source, una migración o un backfill sin esa autorización nueva.

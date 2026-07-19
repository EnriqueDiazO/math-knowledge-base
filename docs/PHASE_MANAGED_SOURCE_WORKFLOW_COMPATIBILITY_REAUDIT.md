# Managed Source Workflow Compatibility Re-Audit

Fecha de la reauditoría: 2026-07-18.

Alcance: revalidación documental, de código, pruebas y evidencia MongoDB de solo
lectura posterior a los cinco fixes de compatibilidad. No se modificó código ni
pruebas, no se habilitó ningún E2E opt-in y el único artefacto creado por esta
fase es este informe.

## A. Estado Git y entorno

La puerta de entrada se ejecutó antes de cualquier otra acción y pasó completa.

| Comprobación | Resultado |
|---|---|
| Repositorio solicitado y `git rev-parse --show-toplevel` | `/home/enriquedo/PersonalProjects/math-knowledge-base` |
| Rama | `main` |
| HEAD inicial | `9e6ce098963c64a12d18909dc23dd6cedb41d1ac` (`docs: record managed source compatibility fixes`) |
| Worktree inicial | limpio |
| Staging inicial | vacío |
| `origin/main...HEAD` | `0 0` |
| Tags sobre HEAD | ninguno |
| Sistema | Linux `6.8.0-124-generic` x86_64 |
| Python del entorno | 3.10.12 |
| pytest | 8.4.2 |

El historial inmediato contenía, en orden, `9e6ce098`, `1a8250da`, `fd3eda8a`,
`79b515b1`, `8ebf8fa4`, `69980467` y el baseline auditado `434aa015`.

Se leyeron completos los ocho documentos exigidos: la auditoría anterior, el
registro de fixes y los contratos de Source Link, Add Concept, Edit Concept,
preservación de identidad, fresh database y legacy link.

## B. Baseline de fixes

Los mensajes de commit se usaron sólo para trazabilidad; el estado se determinó
inspeccionando el código real en HEAD y ejecutando las pruebas.

| Hallazgo | Commit | Archivos funcionales | Pruebas añadidas | Resultado de la reauditoría |
|---|---|---|---|---|
| H-01 | `69980467 fix(cuaderno): require managed source for promotion` | `editor/cuaderno_page.py` | `tests/test_cuaderno_managed_source_promotion.py` | **CORREGIDO** |
| H-02 | `8ebf8fa4 fix(sources): block deletion with managed concept links` | `mathmongo/source_catalog/repository.py` | `tests/test_source_catalog_repository.py`, `tests/test_source_catalog_service.py` | **CORREGIDO** |
| H-03 | `79b515b1 fix(startup): avoid implicit MathV0 initialization` | `editor/database_connections.py`, `editor/editor_streamlit.py` | `tests/test_database_connection_bootstrap.py` | **CORREGIDO** |
| H-04 | `fd3eda8a fix(builder): isolate document state by database` | `editor/database_scope.py`, `editor/document_builder.py`, `editor/editor_streamlit.py` | `tests/test_document_builder_database_scope.py` | **CORREGIDO** |
| H-05 | `1a8250da fix(graphs): isolate knowledge map state by database` | `editor/database_scope.py`, `editor/editor_streamlit.py` | `tests/test_knowledge_graph_database_scope.py` | **CORREGIDO** |

`9e6ce098` sólo añadió `docs/PHASE_MANAGED_SOURCE_WORKFLOW_COMPATIBILITY_FIXES.md`;
no alteró la implementación validada.

## C. H-01 Cuaderno Promote

| Campo de trazabilidad | Evidencia en HEAD |
|---|---|
| Hallazgo original | Cuaderno → Diario LaTeX → Promover aceptaba un Source textual libre y producía concepto/LaTeX legacy sin `source_id`. |
| Commit correctivo | `69980467` |
| Archivos modificados | `editor/cuaderno_page.py`; `tests/test_cuaderno_managed_source_promotion.py` |
| Helpers utilizados | `SourceRepository`, `load_active_sources`, `source_labels`, `resolve_active_source`, `can_save_with_managed_source`, `insert_concept_with_latex_atomic` |
| Pruebas añadidas | Siete pruebas para UI sin texto libre, catálogo vacío/error, selección activa, Source sin conceptos, exclusión legacy, rehidratación, persistencia simétrica y cambio de base: `tests/test_cuaderno_managed_source_promotion.py:95-196`. |
| Antes | Un `text_input` aceptaba un snapshot arbitrario y `ConceptoBase` no llevaba vínculo administrado. |
| Ahora | El repositorio se liga a `notes_col.database`, lista sólo Sources activas, usa `source_id` como valor, rehidrata al submit y copia `name` + `source_id` a ambos documentos. |
| Evidencia principal | `editor/cuaderno_page.py:1449-1466`, `1530-1598`, `1824-1855`, `1875-1919`; helper compartido en `editor/helpers/managed_source_selection.py:14-73`; persistencia en `editor/db/concept_repository.py:42-78`. |
| Riesgo residual | La cobertura combina helpers/fakes con aserciones estructurales de la rama Streamlit; no es una prueba browser E2E. La key incluye el nombre real de base y el submit siempre rehidrata contra el repositorio actual. |
| Estado | **CORREGIDO** |

Checklist de revalidación:

| # | Condición | Resultado | Evidencia |
|---:|---|:---:|---|
| 1–3 | Sin input libre, `Custom` ni `New source name` | Sí | `editor/cuaderno_page.py:1530-1598`; prueba `:95-106` |
| 4–6 | Sources activas de la base actual, valor `source_id`, `name` sólo como label/snapshot | Sí | `editor/cuaderno_page.py:1457-1466`, `1571-1598` |
| 7–8 | Source sin conceptos aparece; cadena sólo legacy no aparece | Sí | `tests/test_cuaderno_managed_source_promotion.py:118-127` |
| 9–10 | Catálogo vacío o fallido bloquea | Sí | `editor/cuaderno_page.py:1561-1569`, `1824-1829`; prueba `:108-137` |
| 11 | Rehidratación inmediata antes de guardar | Sí | `editor/cuaderno_page.py:1837-1855` |
| 12–14 | `source` y `source_id` iguales en `concepts`/`latex_documents` | Sí | `editor/cuaderno_page.py:1875-1919`; prueba `:153-183` |
| 15–16 | No crea Sources ni infiere por nombre | Sí | no hay write de Source en la rama; prueba spy `:64-70`, `:183` |
| 17 | Cambio de base reconstruye opciones | Sí | repositorio construido desde la base de la nota y key con base `:1457-1463`, `:1571-1584`; prueba `:186-196` |

Las dos rutas activas de persistencia MongoDB de conceptos son Add Concept y
esta promoción; ambas exigen Source administrada. `interface.py:50-145` y
`editor/interface.py:50-143` aún reciben “Fuente” textual, pero son generadores
standalone de archivos Markdown/YAML locales: no importan un cliente MongoDB, no
escriben `concepts` y no están conectados al menú Streamlit. No constituyen una
ruta activa de alta en la base administrada.

## D. H-02 Source Delete Guard

| Campo de trazabilidad | Evidencia en HEAD |
|---|---|
| Hallazgo original | El borrado físico sólo bloqueaba References y snapshots legacy; un vínculo moderno podía quedar colgante tras rename o snapshot distinto. |
| Commit correctivo | `8ebf8fa4` |
| Archivos modificados | `mathmongo/source_catalog/repository.py`; pruebas de repository y service |
| Helpers/comandos | `SourceRepository.deletion_blockers`, `SourceRepository.physical_delete_if_unused`, `SourceCatalogService.inspect_source_deletion`, `delete_source_if_unused`, error tipado `PhysicalDeletionBlockedError` |
| Pruebas añadidas | Concepto moderno con snapshot histórico, LaTeX moderno huérfano, ambos blockers, rename/archive, igualdad exacta y dependencia aparecida después del preview: `tests/test_source_catalog_repository.py:386-472`, `tests/test_source_catalog_service.py:324-334`. |
| Antes | No se consultaban `concepts.source_id` ni `latex_documents.source_id`. |
| Ahora | Ambos se cuentan por igualdad exacta, se conservan blockers de Reference y texto legacy y el repository repite la inspección justo antes de borrar. |
| Evidencia principal | `mathmongo/source_catalog/repository.py:401-448`; `mathmongo/source_catalog/service.py:649-693`; UI `editor/source_catalog/edit_source_page.py:972-1032`. |
| Riesgo residual | MongoDB no ofrece FK entre colecciones. Existe una ventana concurrente estricta entre el último `count_documents` y `delete_one`; el flujo normal mitiga archivando primero, impidiendo nuevas selecciones activas, y revalidando de nuevo al ejecutar. Una garantía linealizable requeriría transacción/estado de eliminación coordinado y queda documentada para estabilización posterior. |
| Estado | **CORREGIDO** respecto del defecto original y del race preview→submit exigido |

Checklist de revalidación:

| Condición | Resultado y evidencia |
|---|---|
| `concepts.source_id` y `latex_documents.source_id` bloquean y se reportan por separado | Sí; `repository.py:407-421`, pruebas `:386-440` |
| References y vínculos legacy textuales siguen bloqueando | Sí; `repository.py:422-439`, prueba `tests/test_source_catalog_repository.py:360-383` |
| Snapshot distinto, rename y Source archivada no evaden el vínculo moderno | Sí; pruebas `:386-402`, `:443-458` |
| Servicio/repository revalidan al ejecutar | Sí; `service.py:665-686`, `repository.py:442-447`; prueba de segunda inspección `service.py` test `:324-334` |
| Dependencia aparecida después del preview | Bloqueada por la segunda inspección probada |
| Sin cascade ni borrado de concepto/LaTeX | Sí; la única mutación es `sources.delete_one` en `repository.py:447` |
| Sin similitud ni upsert | Sí; texto legacy usa `$in` exacto y la operación es `delete_one`; prueba de nombre similar `:461-472` |
| No deja vínculo moderno colgante en el flujo serializado comprobado | Sí; todo vínculo presente en la inspección final bloquea. Se acepta la salvedad concurrente anterior como riesgo residual. |

No se encontró otro bypass de producción al borrado: la UI llama al servicio y
éste llama a `physical_delete_if_unused`.

## E. H-03 Startup y MathV0

| Campo de trazabilidad | Evidencia en HEAD |
|---|---|
| Hallazgo original | El bootstrap añadía una conexión literal `MathV0`; construirla ejecutaba `ensure_indexes` aunque otra base estuviera configurada. |
| Commit correctivo | `79b515b1` |
| Archivos modificados | `editor/database_connections.py`, `editor/editor_streamlit.py`; prueba nueva de bootstrap |
| Helper nuevo | `initialize_configured_connection` |
| Pruebas añadidas | Configurada única, MathV0 sólo configurada, cambio de config sin arrastre, ausencia literal en bootstrap y Add Connection explícito: `tests/test_database_connection_bootstrap.py:38-92`. |
| Antes | Dos constructores automáticos: configuración actual y literal personal. |
| Ahora | La primera sesión resuelve config y registra/selecciona una sola URI/base. Otras conexiones sólo nacen tras el botón Add Connection. |
| Evidencia principal | `editor/database_connections.py:27-38`; `editor/editor_streamlit.py:1098-1149`, `1181-1211`; config `mathmongo/config.py:21-23`, `125-190`. |
| Riesgo residual | `MathMongo.__init__` conserva `ensure_indexes` (`mathdatabase/mathmongo.py:57-71`), por lo que la base configurada o una conexión añadida explícitamente sí se inicializan. Es una acción seleccionada/configurada, no una base adicional oculta. |
| Estado | **CORREGIDO** |

La búsqueda global de `MathV0`, `add_connection`, `MathMongo(`,
`ensure_indexes` y `mongo_database` separó:

- bootstrap activo: sin nombre literal, sólo configuración;
- config: default portable `mathmongo`, precedencia CLI > entorno > archivo >
  default (`mathmongo/config.py:125-190`);
- launcher: hace `ping` y falla limpiamente si MongoDB está detenido
  (`mathmongo/launcher.py:59-71`, `114-142`);
- `Makefile:13`: `DATABASE ?= MathV0`, default visible y sobreescribible de
  tareas locales, no conexión oculta del bootstrap;
- documentación, ejemplos, pruebas y guardas E2E: menciones no activas;
- import/update: `MathV0` aparece como nombre explícito protegido/seleccionable,
  no como inicialización de arranque.

Una base nueva vacía puede ser la única conexión. Cambiar la configuración en
una sesión nueva construye sólo la nueva base; la prueba spy lo confirma sin
abrir MongoDB.

## F. H-04 Document Builder

| Campo de trazabilidad | Evidencia en HEAD |
|---|---|
| Hallazgo original | Claves globales conservaban una selección `X@S`; al cambiar de base se resolvía contra la base nueva. |
| Commit correctivo | `fd3eda8a` |
| Archivos modificados | `editor/database_scope.py`, `editor/document_builder.py`, `editor/editor_streamlit.py`; prueba nueva de scope |
| Helpers nuevos | `database_scope_token`, `sync_document_builder_scope`; prefijos `document_builder_` y `doc_` |
| Pruebas añadidas | Token conexión+base, limpieza exhaustiva, mismo scope, retorno A→B→A, misma identidad en B sin consultas, moderno/legacy read-only y orden sync→read: `tests/test_document_builder_database_scope.py:69-162`. |
| Antes | El estado no incluía base; `_concepts_for_keys` interpretaba lo retenido con el `db` actual. |
| Ahora | Se calcula SHA-256 estable de conexión+base, se elimina todo estado Builder al cambiar y la sincronización ocurre antes de `distinct` o resolución. |
| Evidencia principal | `editor/database_scope.py:10-41`; `editor/editor_streamlit.py:1232-1241`, `5923-5930`; `editor/document_builder.py:161-200`. |
| Riesgo residual | El aislamiento invalida en lugar de mantener espacios por base, por diseño. Exportar genera archivos fuera de MongoDB; Builder continúa siendo MongoDB read-only. |
| Estado | **CORREGIDO** |

La limpieza por prefijo cubre selección/orden (`items`), filtros, reportes de
validación, preview, resultado generado, errores/mensajes, flags de exportación,
botones y keys dinámicas `doc_*`. La prueba construye ese conjunto completo en
`tests/test_document_builder_database_scope.py:47-66` y exige que sólo sobreviva
estado ajeno al Builder en `:79-90`.

Se verificó además:

- la conexión forma parte del token, incluso con el mismo nombre real de base;
- A→B elimina `X@S` antes de cualquier lectura de B (`:115-129`);
- volver a A no restaura el estado eliminado (`:103-112`);
- el encabezado muestra conexión y base (`editor/document_builder.py:180-181`);
- conceptos modernos y legacy resuelven dentro de su propia base por el par
  histórico (`tests/test_document_builder_database_scope.py:132-149`);
- no existen llamadas MongoDB de escritura en `editor/document_builder.py`.

## G. H-05 Knowledge Graph y Maps

| Campo de trazabilidad | Evidencia en HEAD |
|---|---|
| Hallazgo original | Estado global de grafo/mapa sobrevivía al switch; un `_id` igual podía reutilizar posiciones/aristas de A y reparar/guardar B. |
| Commit correctivo | `1a8250da` |
| Archivos modificados | `editor/database_scope.py`, `editor/editor_streamlit.py`; prueba nueva de scope de grafos |
| Helpers nuevos | `sync_knowledge_graph_scope`, `knowledge_map_session_identity`, `mark_knowledge_map_loaded`, `knowledge_map_is_loaded`; prefijos `knowledge_graph_` y `kg_` |
| Pruebas añadidas | Limpieza exhaustiva, mismo scope, retorno, identidad scope+`_id`+`map_uid`, homónimos no listos, switch sin writes y orden/guards estructurales: `tests/test_knowledge_graph_database_scope.py:76-167`. |
| Antes | Sólo cambiar `_id` reinicializaba el editor; scope, conexión y `map_uid` no protegían el estado. |
| Ahora | Se limpia antes de leer mapas; un documento se carga sólo bajo identidad compuesta y repair/save exigen `map_state_ready`. |
| Evidencia principal | `editor/database_scope.py:13-16`, `44-93`; `editor/editor_streamlit.py:4610-4640`, `4984-5029`, `5040-5056`, `5223-5247`, `5337-5352`, `5685-5773`. |
| Riesgo residual | Las pruebas de switch son puras/estructurales, no dos servidores MongoDB concurrentes. Los inserts/duplicate/delete de mapas nuevos se apoyan en que el scope se limpió antes de listar y renderizar la base actual. |
| Estado | **CORREGIDO** |

La invalidación cubre conceptos y relaciones seleccionados, HTML, estadísticas,
controles visuales/physics, formularios, `_id`, identidad cargada (que incluye
`map_uid`), `graph_state`, posiciones x/y, aristas, repair/save, preview/export,
mensajes y todas las keys dinámicas `kg_*`. La matriz concreta está en
`tests/test_knowledge_graph_database_scope.py:35-73`.

La secuencia segura es:

1. calcular el scope de conexión+base;
2. `sync_knowledge_graph_scope` antes de acceder a
   `knowledge_graph_maps` (`editor/editor_streamlit.py:4618-4639`);
3. cargar el mapa de la base actual y marcar identidad
   scope+`_id`+`map_uid` (`:4984-5016`);
4. derivar `map_state_ready` (`:5024-5029`);
5. bloquear auto-repair, repair manual, preferencia de sync y guardado mientras
   no esté listo (`:5040-5048`, `:5230-5239`, `:5337-5344`, `:5687-5691`).

El switch puro sólo cambia `session_state`; el write spy confirma cero writes a
maps, Sources, concepts y relations (`tests/test_knowledge_graph_database_scope.py:140-154`).

## H. Contratos generales

| Contrato | Resultado | Evidencia |
|---|:---:|---|
| Add Source es el único creador interactivo de documentos `sources` | Sí | UI tipada y confirmación de base en `editor/source_catalog/add_source_page.py:115-248`; única llamada de producción de catálogo a `create_source` desde `editor/source_catalog/workflows.py:92`. Import/update/migration son operaciones explícitas, no creación interactiva por inferencia. |
| Add Source está ligado a una base explícita y a `Source` tipada | Sí | contexto inmutable en `editor/source_catalog/shared.py:39-105`; formulario/preview en `add_source_page.py:125-221`. |
| Add Concept lista sólo Sources activas por ID | Sí | `editor/editor_streamlit.py:1857-1925`. |
| Add Concept rehidrata y persiste `source` + `source_id` | Sí | `editor/editor_streamlit.py:2416-2443`, `2471-2483`; insert simétrico `editor/db/concept_repository.py:42-78`. |
| Edit Concept preserva `id`, `source`, `source_id` y permite legacy | Sí | identidad capturada `editor/editor_streamlit.py:2743-2746`, UI inmutable `:2844-2862`, cambios sin identidad y servicio `:3367-3433`; validación `editor/db/concept_edit_service.py:108-154`, `448-501`. |
| Legacy Link sólo añade `source_id` al par exacto | Sí | UI rehidrata Source activa `editor/editor_streamlit.py:2872-3005`; servicio sólo `$set source_id` en concepto/LaTeX y preserva dependencias `editor/db/concept_source_link_service.py:349-487`. |
| No hay inferencia automática por nombre | Sí | selección y rehidratación usan ID; legacy text sólo es snapshot y blocker exacto. |
| Los fixes no introdujeron regresiones en estos contratos | Sí | los commits H-03/H-04/H-05 no tocaron servicios de concepto; las suites enfocadas y completa conservaron el baseline. |

## I. Conceptos legacy y modernos

El contrato dual continúa siendo:

```json
{"id": "...", "source": "Snapshot textual", "source_id": "src_..."}
```

para un concepto moderno, y:

```json
{"id": "...", "source": "Snapshot textual"}
```

para uno legacy.

`ConceptoBase` mantiene `source` obligatorio y `source_id` opcional
(`schemas/schemas.py:131-160`). Las lecturas, relaciones, media, Builder,
Browse, Edit y evidence siguen resolviendo la identidad histórica por
`(id, source)` o `id@source`; no exigen migración. Add Concept y Cuaderno crean
el contrato moderno. Edit ordinario mantiene presencia/ausencia y valor del
vínculo; Legacy Link es la única acción que lo añade explícitamente.

La evidencia fresh-database previa sigue vigente y sus pruebas permanecieron
omitidas por opt-in, como exigía esta fase. La suite unitaria sí cubrió creación,
edición y link moderno/legacy.

## J. Portabilidad

Export, import y database update serializan/aplican documentos crudos, por lo
que conservan tanto la ausencia legacy como `source_id` moderno. No hay
resolución ni reparación por nombre. Las pruebas de backup/update seleccionadas
pasaron salvo los tres fallos XDG baseline descritos más adelante.

Permanece M-03: los preflight validan Sources/References, Source Documents,
lectura/evidence y endpoints `id@source`, pero no correlacionan el
`concepts.source_id` con `latex_documents.source_id` y `sources.source_id`.
Evidencia: `editor/utils/db_export.py:450-625`,
`editor/utils/db_import.py:1590-1685`,
`editor/utils/db_update.py:1097-1232`. Una inconsistencia existente se conserva
sin inferir ni modificar, pero tampoco se reporta.

## K. Relaciones, media y evidence

| Dominio | Contrato revalidado | Resultado |
|---|---|:---:|
| Relaciones | Endpoints `id@source`; Edit y Legacy Link no los reescriben; Builder y update consultan el par. | Intacto |
| Knowledge Maps | Estado portable crudo y aislamiento nuevo por base; H-05 impide reutilizar estado de sesión. | Intacto |
| Media | `media_assets.concept_ids` conserva `id@source`; creación/link/edición ordinaria no remapean. | Intacto |
| Evidence | `concept_legacy_id` + `concept_legacy_source`; `source_id` del evidence corresponde a la Source de la evidencia, no sustituye identidad conceptual. | Intacto |
| Lectura | Source Documents, annotations, notes, reading state y page maps mantienen IDs explícitos y preflight propios. | Intacto |

La única salvedad es M-01: Delete Concept no aplica una política integral para
estas dependencias. No es una regresión de los cinco fixes.

## L. Estado observado de MathV0

La inspección usó `MongoClient` directo con `retryWrites=False` y lectura
`SecondaryPreferred`. No se instanció `MathMongo`. Sólo se ejecutaron `ping`,
`list_collection_names`, `count_documents`, `find` y `list_indexes`. No se
imprimió contenido matemático.

| Dominio | Observación de solo lectura |
|---|---:|
| Sources | 17, todas activas; 17 IDs únicos no vacíos |
| References | 21; 21 asociaciones; 0 colgantes |
| Concepts | 186 legacy, 0 modernos, 0 IDs inválidos/colgantes, 0 pares duplicados |
| LaTeX | 187 legacy, 0 modernos, 0 IDs inválidos/colgantes, 0 pares duplicados |
| Pares concepto/LaTeX | 186 coincidentes; 1 LaTeX huérfano preexistente; 0 mismatches de `source_id` |
| Relaciones | 136; 0 endpoints inválidos o colgantes |
| Knowledge Graph Maps | 2 mapas; 62 nodos; 39 aristas |
| Media | 10 assets; 2 asociaciones conceptuales; 0 colgantes |
| Evidence | 6 links; 0 conceptos colgantes |
| Lectura | 3 annotations, 3 notes, 3 Source Documents, 2 reading states, 0 page maps |

Prueba de inmutabilidad:

| Snapshot | Antes | Después |
|---|---|---|
| Colecciones | `c0ff79ce50d3bfbf626ade69e9d3d95e994a1b033f15199674c384f47fee1694` | igual |
| Conteos | `6293411e6ee4af2120c440905c50e732ff8be9674781be71de6e168487e0c895` | igual |
| Índices | `4f3395d27307044cb92cae4f77d2054292e3d32d20af39659c026dac3a64194a` | igual |
| Identidades/vínculos proyectados | `96b712941ac3835e122cad659639d4f1e32d3eb5808a05704e64e5cf1cf382a1` | igual |
| Agregado | `40b09b7e572ee8214436a525ac1b2867f6e04e46eccca13aac1324447e41b02c` | igual |

`snapshots_equal = true`.

## M. Pruebas enfocadas

Se ejecutó con `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `-q` y los
tres opt-ins Mongo E2E ausentes. La selección incluyó Cuaderno, repository y
service de Source Catalog, Add Source, Add Concept, Edit Concept, legacy link,
startup/config/CLI/launcher, scopes, Builder, PDF, Knowledge Graph, backup,
import/update, page maps, media, lectura y evidence.

Resultado:

| Métrica | Valor |
|---|---:|
| Passed | 536 |
| Skipped | 3 |
| Failed | 3 |
| Warnings | 7 |
| Duración | 4.78 s |

Los tres fallos son baseline conocido en `tests/test_xdg_media_paths.py`:

1. `test_database_export_rejects_symlinked_output_destinations[zip_path]`;
2. `test_database_export_publication_race_never_overwrites_symlink_target`;
3. `test_database_export_detects_same_inode_mutation_after_publication`.

Los tres fallan porque el fake `_FixedExportDatetime` no implementa `now`,
mientras `editor/utils/db_export.py:647` lo llama. No están relacionados con
H-01…H-05. Hubo un warning de deprecación Starlette/httpx y seis warnings de
serialización Pydantic ya conocidos. `git diff --check` fue limpio después de
las pruebas.

## N. Regresión completa

Se ejecutó exactamente una vez:

```text
PYTHONDONTWRITEBYTECODE=1 mathdbmongo/bin/python -m pytest \
  -p no:cacheprovider -q
```

Resultado:

| Métrica | Baseline esperado | Observado | Comparación |
|---|---:|---:|---|
| Passed | 1432 | 1432 | igual |
| Skipped | 53 | 53 | igual |
| Failed | 4 | 4 | igual |
| Warnings | 7 | 7 | igual |
| Duración | — | 65.74 s | informativa |

Además de los tres fallos XDG de media anteriores, se reprodujo el baseline
`tests/test_xdg_mutable_guards.py::test_editor_streamlit_backup_and_import_staging_are_guarded`.
No hubo fallos nuevos ni cambio de naturaleza.

## O. Hallazgos críticos

Ninguno. No hay pérdida masiva, corrupción cross-database demostrada ni bypass
de identidad activo después de los fixes.

## P. Hallazgos altos

Ninguno. H-01, H-02, H-03, H-04 y H-05 pasan como **CORREGIDO**. Los cuatro
fallos de regresión son baseline XDG y no están relacionados con esta fase.

## Q. Hallazgos medios y bajos

| ID | ¿Sigue? | Severidad actual | Riesgo real / reproducción | Workaround | ¿Bloquea? | Destino |
|---|:---:|---|---|---|:---:|---|
| M-01 Delete Concept secuencial e incompleto | Sí | MEDIO | Edit borra concept, LaTeX y relations secuencialmente; Browse sólo concept/LaTeX (`editor/editor_streamlit.py:3546-3568`, `3846-3850`). Puede dejar huérfanos o estado parcial. | No borrar desde esas rutas si existen dependencias; backup y revisión manual. | No por sí solo | Definir política block/cascade y transacción/compensación posterior. |
| M-02 Browse/Quarto colapsa a `id` | Sí | MEDIO | `X@A` y `X@B` pueden compartir selección/keys; mapa label→ID y filtro por ID en `editor/editor_streamlit.py:3625-3672`, widgets `3827-3849`. | Exportar por Source sin IDs repetidos o usar Builder, que sí usa `id@source`. | No | Corregir con identidad compuesta y prueba dedicada. |
| M-03 Portabilidad no reporta link colgante/inconsistente | Sí | MEDIO | Conserva payload raw, pero no correlaciona concepto/LaTeX/Source. | Auditar links antes de export/update; no usar nombre para reparar. | No | Añadir preflight exacto en export/import/update. |
| M-04 Cobertura transversal insuficiente | Parcialmente | BAJO residual | Ya existen pruebas dirigidas para Cuaderno, delete, startup, Builder A→B y KG A→B. Falta browser E2E multibase y cobertura del gap M-03. | Suites enfocadas + full regression; E2E opt-in en entorno aislado cuando corresponda. | No | Completar durante estabilización, no en esta auditoría. |
| L-01 `DocumentoLatex` no declara `source_id` | Sí | BAJO | `schemas/schemas.py:231-235`; una futura ruta basada en `model_dump` podría perderlo. Hoy insert/raw portability lo conserva. | Mantener persistencia explícita/raw actual. | No | Añadir campo y round-trip cuando se toque el esquema. |

Riesgo aceptado adicional: la ventana concurrente final `count_documents` →
`sources.delete_one` descrita en H-02 no tiene FK/transacción. No reproduce el
defecto original secuencial y se mitiga con archive-first, pero conviene cerrar
la garantía linealizable en una estabilización futura.

Los MEDIO/BAJO son separables del cierre del workflow administrado y pueden
documentarse para una versión posterior.

## R. Criterios de cierre

| # | Criterio | Sí/No | Evidencia/conclusión |
|---:|---|:---:|---|
| 1 | ¿H-01 está corregido? | **Sí** | Selector administrado, rehidratación y persistencia simétrica. |
| 2 | ¿H-02 está corregido? | **Sí** | Blockers modernos en ambos documentos y doble inspección; salvedad concurrente documentada. |
| 3 | ¿H-03 está corregido? | **Sí** | Sólo conexión configurada en bootstrap. |
| 4 | ¿H-04 está corregido? | **Sí** | Scope conexión+base e invalidación antes de leer. |
| 5 | ¿H-05 está corregido? | **Sí** | Scope compartido, identidad de mapa compuesta y guards de escritura. |
| 6 | ¿Add Source es el único creador interactivo de Sources? | **Sí** | Portabilidad/migración son explícitas; otras pantallas no insertan Sources. |
| 7 | ¿Todo concepto nuevo persistido en MongoDB usa Source administrada? | **Sí** | Add Concept y Cuaderno lo exigen. |
| 8 | ¿Add Concept sólo selecciona Sources existentes? | **Sí** | Activas, por ID, rehidratadas al submit. |
| 9 | ¿Edit Concept preserva identidad? | **Sí** | `id`, `source`, presencia/valor de `source_id` inmutables. |
| 10 | ¿Legacy link sólo añade `source_id`? | **Sí** | Concepto+LaTeX exactos, sin mover dependencias. |
| 11 | ¿Conceptos modernos funcionan en una base nueva? | **Sí** | Contrato unitario y lifecycle E2E previo; sin dependencia de MathV0. |
| 12 | ¿Conceptos legacy continúan funcionando? | **Sí** | Lecturas y edición no exigen `source_id`; MathV0 lo confirma. |
| 13 | ¿No existe dependencia activa hardcodeada de MathV0? | **Sí** | Sólo default configurable/ejemplos/pruebas/operaciones explícitas. |
| 14 | ¿Document Builder no mezcla bases? | **Sí** | Selección se invalida antes de cualquier lectura. |
| 15 | ¿Knowledge Graph/Maps no mezcla bases? | **Sí** | Estado completo se invalida y mapa se recarga por identidad compuesta. |
| 16 | ¿Source delete no deja vínculos modernos colgantes? | **Sí** | Todo vínculo visible en la inspección final bloquea; limitación de concurrencia estricta aceptada. |
| 17 | ¿Export/import/update conserva `source_id`? | **Sí** | Payload crudo; M-03 afecta diagnóstico, no preservación. |
| 18 | ¿Relaciones permanecen intactas? | **Sí** | Identidad histórica no cambia. |
| 19 | ¿Media permanece intacta? | **Sí** | `id@source` no cambia; snapshot real sin dangling links. |
| 20 | ¿Evidence links permanecen intactos? | **Sí** | Par legacy no cambia; snapshot real sin dangling links. |
| 21 | ¿Los hallazgos medios pueden aceptarse documentalmente? | **Sí** | Tienen workaround, no son regresión de H-01…H-05 y no requieren Change Source. |
| 22 | ¿Existen defectos críticos? | **No** | Ninguno identificado. |
| 23 | ¿Existen defectos altos? | **No** | Los cinco anteriores están corregidos; no hubo fallo nuevo. |
| 24 | ¿Puede cerrarse una versión estable sin Change Source? | **Sí** | Edición ordinaria y link preservan identidad; relocalización no es requisito del contrato actual. |

## S. Recomendación final

**B. LISTO CON LIMITACIONES DOCUMENTADAS**

Los cinco blockers altos originales están corregidos, MongoDB permaneció
inmutable y la regresión coincide exactamente con el baseline. Se elige B, y no
un cierre sin salvedades, por M-01, M-02, M-03, los fallos XDG baseline, la
cobertura E2E residual y la limitación concurrente documentada de physical
delete.

## T. Limitaciones aceptadas

1. Delete Concept no es transaccional ni integral (M-01).
2. Browse/Quarto no usa identidad compuesta en todas sus selecciones/keys
   (M-02); Builder es el workaround seguro para IDs repetidos.
3. Portabilidad conserva pero no diagnostica `source_id` conceptual colgante o
   distinto entre concepto y LaTeX (M-03).
4. Las nuevas pruebas de scope son deterministas y suficientes para el fix,
   pero no sustituyen un browser E2E multibase.
5. `DocumentoLatex` aún no modela `source_id` (L-01).
6. Physical delete revalida inmediatamente, pero una garantía concurrente
   absoluta requeriría coordinación transaccional; archive-first es la práctica
   operativa aceptada.
7. Permanecen cuatro fallos XDG baseline y siete warnings conocidos.
8. No se implementaron Change Source, Repair Link, Synchronize Snapshot,
   unlink ni `concept_uid`; ninguno es requisito para el contrato cerrado.

## U. Próxima fase

La próxima fase autorizable es:

`VERSION-CLOSURE-MANAGED-SOURCE-WORKFLOW`

Esta reauditoría no autoriza fixes de deuda media/baja dentro de su propio
alcance. Durante toda la fase:

- no se modificó MongoDB;
- no se creó ninguna Source;
- no se modificó código ni pruebas;
- no se ejecutó migración ni backfill;
- no se implementó Change Source ni otra relocalización/reparación;
- no se modificaron conceptos existentes;
- no se hizo push.

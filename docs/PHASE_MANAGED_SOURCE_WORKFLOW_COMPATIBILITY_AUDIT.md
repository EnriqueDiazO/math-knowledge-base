# Managed Source Workflow Compatibility Audit

Fecha de auditoría: 2026-07-18

Fase: `MANAGED-SOURCE-WORKFLOW-COMPATIBILITY-AUDIT`

Alcance: auditoría documental y verificaciones de solo lectura; no incluye correcciones.

## A. Estado Git y entorno

El baseline se comprobó antes de inspeccionar el código o MongoDB:

| Comprobación | Resultado |
|---|---|
| Repositorio | `/home/enriquedo/PersonalProjects/math-knowledge-base` |
| Rama | `main` |
| HEAD inicial | `90f58cc06a7591f7a9c05b2c9115a0913793ce61` — `feat(ui): link legacy concepts from Edit Concept` |
| Historial requerido | presentes `c2c3ef75`, `810fbec2`, `1b8df663`, `6a2136af` y `83f8fb51` |
| Worktree/staging iniciales | limpios |
| `origin/main...HEAD` inicial | `0 0` |
| Tag en HEAD | ninguno |

La inspección se hizo sobre ese estado. El único cambio producido por esta fase es este reporte documental.

## B. Contratos auditados

Contrato moderno:

```json
{"id": "...", "source": "Snapshot textual", "source_id": "src_..."}
```

Contrato legacy:

```json
{"id": "...", "source": "Snapshot textual"}
```

Conclusiones contractuales:

- La identidad histórica y operativa de un concepto continúa siendo el par exacto `(id, source)`, serializado como `id@source` donde la aplicación necesita una clave (`schemas/schemas.py:131-160`, `mathdatabase/mathmongo.py:407-492`).
- `source_id` es un vínculo administrado opcional, no parte de la identidad histórica y no autoriza inferencias por nombre (`editor/db/concept_source_link_service.py:18-156`).
- El `source` textual es un snapshot. El flujo ordinario de edición no cambia `id`, `source` ni la presencia/valor de `source_id` (`editor/db/concept_edit_service.py:117-202`, `editor/db/concept_edit_service.py:448-501`).
- Un vínculo legacy sólo puede añadir `source_id` al par exacto de documentos `concepts`/`latex`, con preflight, CAS e idempotencia; no reescribe dependencias (`editor/db/concept_source_link_service.py:450-487`).
- Los campos extra de los documentos Mongo se conservan en exportación/importación/update mediante documentos crudos. No se exige migrar una base legacy para abrirla (`editor/utils/db_export.py:627-853`, `editor/utils/db_import.py:2419-2830`, `editor/utils/db_update.py:1850-1986`).

Se leyeron completos los siete contratos y reportes previos indicados en el prompt. La evidencia previa reutilizada se identifica expresamente en las secciones N, O y Q.

## C. Matriz arquitectónica

Leyenda: L = lectura, E = escritura; “Source” en la columna de creación significa un documento de la colección `sources`, no el snapshot textual del concepto.

| # | Área y código principal | Persistencia e identidad | L/E y creación de Source | Riesgo legacy / moderno | Compatibilidad y pruebas |
|---:|---|---|---|---|---|
| 1 | Add Source: `editor/source_catalog/add_source_page.py:116-260`; `editor/source_catalog/workflows.py:84-101`; `mathmongo/source_catalog/service.py:279-309` | repositorios `sources` y `references`; Source por `source_id` | L/E; **sí**, creador interactivo autorizado | legacy: ninguno; moderno: duplicado sólo tras confirmación explícita | Compatible. `tests/test_source_catalog_add_ui.py:107-169`, `tests/test_source_catalog_ui_workflows.py:71-144`, `tests/test_source_catalog_service.py:155-226` |
| 2 | Edit/Analyze Source: `editor/source_catalog/edit_source_page.py:218-410`, `editor/source_catalog/edit_source_page.py:689-825`, `editor/source_catalog/edit_source_page.py:910-1032` | `SourceRepository`/`ReferenceRepository`, identidad estable `source_id`; inspección textual legacy | L/E; no crea Source, actualiza/archiva/borra una existente | legacy: el bloqueo por snapshot existe; moderno: el borrado omite el vínculo directo | **No plenamente compatible** por H-02. `tests/test_source_catalog_repository.py:357-383`, `tests/test_source_catalog_edit_analysis.py:694-832` |
| 3 | Add Concept: `editor/editor_streamlit.py:1852-1927`, `editor/editor_streamlit.py:2420-2491`; helper `editor/helpers/managed_source_selection.py:14-73` | `concepts` y `latex`; par `(id, source)` y `source_id` validado | L/E; no crea Source | legacy: no lo crea; moderno: conserva ID y snapshot seleccionados | Compatible. `tests/test_add_concept_managed_source_selection.py:126-284`, `tests/test_concept_source_link_contract.py:65-152` |
| 4 | Edit Concept: `editor/editor_streamlit.py:2628-3580`; `editor/db/concept_edit_service.py:117-202`, `editor/db/concept_edit_service.py:448-501` | `concepts`/`latex` por par exacto; preserva `source_id`; vínculos dependientes usan `id@source` | L/E; no crea Source | legacy y moderno preservados; link legacy es acción separada | Compatible en edición ordinaria. `tests/test_edit_concept_identity_preservation.py:261-571` |
| 5 | Browse Concepts: rama activa `editor/editor_streamlit.py:3582-3855` | `concepts`, `latex`, `media`; detalle por `(id, source)`; exportación Quarto reduce selección a `id` | L y E sólo al borrar; no crea Source | ambos se muestran; IDs repetidos entre Sources pueden colisionar en selección/widgets | Compatible para lectura, **parcial** para selección/exportación por M-02. No hay test dedicado de Browse con ID duplicado |
| 6 | Explore Concepts: no existe como pantalla independiente en el menú activo (`editor/editor_streamlit.py:1285-1298`); la exploración está repartida entre Browse (`editor/editor_streamlit.py:3582-3855`) y Knowledge Graph (`editor/editor_streamlit.py:4612-4831`) | consultas a `concepts`/`relations`; relaciones como `id@source`; `source_id` no es filtro obligatorio | L, y E de mapas sólo en Graph; no crea Source | ambos contratos legibles | Compatible dentro de una base; hereda H-05 en Graph. Cobertura indirecta `tests/test_legacy_concept_source_link_service.py:219-276` |
| 7 | Delete Concept: ramas inline `editor/editor_streamlit.py:3548-3568`, `editor/editor_streamlit.py:3831-3852` | borra por `(id, source)` en `concepts`/`latex`; una ruta también `relations` | E; no crea Source | igual para ambos; limpieza incompleta y no atómica | **Parcial**, M-01. No hay prueba integral de dependencias huérfanas |
| 8 | Relaciones: UI `editor/editor_streamlit.py:3858-4526`; repositorio `mathdatabase/mathmongo.py:407-492` | endpoints exactos `id@source`; valida conceptos por `(id, source)` | L/E en `relations`; no crea Source | `source_id` adicional es irrelevante; legacy y moderno compatibles | Compatible. `tests/test_legacy_concept_source_link_service.py:219-276`, `tests/test_edit_concept_identity_preservation.py:482-493` |
| 9 | Knowledge Graph: `editor/editor_streamlit.py:4620-4831`; sync `editor/utils/knowledge_graph_sync.py:282-359`, `editor/utils/knowledge_graph_sync.py:610-669` | lee `concepts`/`relations`, nodos `id@source`; guarda `graph_state` en `knowledge_graph_maps` | L/E de mapas; no crea Source | ambos contratos compatibles dentro de una base; estado de sesión no aislado | **No compatible al cambiar de base**, H-05. Las pruebas de link sólo demuestran ausencia de reescritura (`tests/test_legacy_concept_source_link_service.py:219-276`); no prueban el switch |
| 10 | Knowledge Maps guardados: `editor/editor_streamlit.py:4833-5040`, `editor/editor_streamlit.py:5695-5733`; `editor/utils/knowledge_graph_sync.py:888-1025` | `knowledge_graph_maps`; `_id`/`map_uid`, nodos `id@source`, posiciones en `graph_state` | L/E; no crea Source | `source_id` no rompe el esquema; `_id` repetido entre clones puede reutilizar estado ajeno | Compatible en una base; **no** entre bases, H-05. Portabilidad indirecta `tests/test_source_catalog_backup.py:309-423`; sin test funcional de mapas/switch |
| 11 | Media assets: `editor/utils/media_assets.py:33-35`, `editor/utils/media_assets.py:119-244`; UI `editor/editor_streamlit.py:664-748` | `media_assets`, clave de concepto `id@source`; archivos XDG | L/E; no crea Source | ambos contratos iguales para media | Compatible. `tests/test_xdg_media_paths.py:22-224`, `tests/test_source_catalog_backup.py:424-719` |
| 12 | Lectura avanzada: `LegacyConceptChoice`/picker `editor/reading_annotations/concept_picker.py:33-250`; servicios create/link `mathmongo/reading_annotations/service.py:1326-1522` | colecciones de lectura; vínculo a concepto por `concept_legacy_id` + `concept_legacy_source` | L/E de anotaciones/notas; no crea Source | selector lee ambos; el `source_id` de evidence/source-document es otro dominio | Compatible. `tests/test_reading_annotations_core.py:488-852`, `tests/test_advanced_reader_concept_linking.py:263-421` |
| 13 | Evidence links: `mathmongo/reading_annotations/models.py:555-620`, `mathmongo/reading_annotations/service.py:1326-1522` | `concept_evidence_links`; concepto por par legacy exacto y evidencia por su propio `source_id` | L/E; no crea Source Catalog Source | ambos contratos conceptuales; no confundir los dos usos de `source_id` | Compatible. `tests/test_reading_annotations_core.py:534-650`, `tests/test_advanced_reader_concept_linking.py:263-421`, `tests/test_reading_annotations_portability.py:364-884` |
| 14 | Cornell: `editor/cornell/service.py:20-95`, `editor/cornell/service.py:117-219` | `latex_notes` y media por `note_id`; no identifica conceptos | L/E; no crea Source | sin efecto por contrato legacy/moderno | Compatible. `tests/test_cornell_service.py:1-240`, `tests/test_cornell_persistence.py:84-209` |
| 15 | CPI: CRUD `editor/cpi/service.py:16-75`; `render_cpi_page` `editor/cpi/streamlit_page.py:1693-1715` | `latex_notes`; identidad de nota, no de concepto | L/E; no crea Source | sin efecto por `source_id` conceptual | Compatible. `tests/test_cpi_service.py:1-170`, `tests/test_cpi_persistence.py:1-180` |
| 16 | Document Builder: `editor/document_builder.py:30-90`, `editor/document_builder.py:160-173`, `editor/document_builder.py:238-268`, `editor/document_builder.py:307-327`, `editor/document_builder.py:419-490` | lee `concepts`, `latex`, `relations`; selección `id@source`; retiene documento crudo (incluido `source_id`) | L; exporta archivos, no Mongo; no crea Source | ambos funcionan dentro de una base; selección global se reinterpreta en la base siguiente | **No compatible al cambiar de base**, H-04. Sin tests funcionales dedicados |
| 17 | PDF preview/exportaciones: `editor/pdf_export.py:925-997`; export page `editor/editor_streamlit.py:5886-6040`; Browse `editor/editor_streamlit.py:3627-3674` | lee concepto/LaTeX por `(id, source)`; salida de archivo; export Quarto desde Browse reduce a `id` | L y archivos; no crea Source | PDF normal compatible; Quarto ambiguo con IDs repetidos | Compatible salvo M-02. Preview: `tests/test_pdf_preview.py:65-397`, `tests/test_generated_pdf_preview_flows.py:76-219`; no hay prueba Quarto de ID duplicado |
| 18 | `import_zip_into_database`: `editor/utils/db_import.py:2419-2830` | todas las colecciones del archivo; documentos crudos; Sources explícitas por `source_id` | E explícita en base destino; puede restaurar Sources del archivo, no crear por inferencia | preserva legacy/moderno; no reporta link conceptual colgante/inconsistente | Compatible en preservación, validación **parcial** M-03. `tests/test_source_catalog_backup.py:224-1390`, `tests/test_source_catalog_import_safety.py:26-85` |
| 19 | Database update: `_query`/validadores `editor/utils/db_update.py:787-905`; `apply_database_update` `editor/utils/db_update.py:1850-1986`; rollback `editor/utils/db_update.py:2039-2090` | colecciones del archivo; concepto por `(id, source)`; payload crudo | E explícita tras plan/backup; Sources sólo si vienen en archivo | conserva `source_id`; no infiere por nombre; mismo gap de link | Compatible en preservación, validación **parcial** M-03. `tests/test_database_update.py:344-1020`, E2E previo |
| 20 | Backups: `export_database_to_zip` `editor/utils/db_export.py:627-853`; `_create_preupdate_backup` `editor/utils/db_update.py:1768-1800` | dump crudo de colecciones, manifest y blobs/media | L Mongo/E archivos; no crea Source en vivo | preserva ausencia/presencia de `source_id`; no valida link conceptual | Compatible en round-trip, validación **parcial** M-03. `tests/test_source_catalog_backup.py:224-1390`, `tests/test_database_update.py:687-936` |
| 21 | Instalación/configuración: `mathmongo/config.py:21-58`, `mathmongo/config.py:125-190`; CLI `mathmongo/cli.py:36-83` | configuración XDG; base predeterminada configurable `mathmongo` | no escribe Sources; la app sí abre además MathV0 al iniciar | instalación no migra una base vieja; apertura oculta de MathV0 rompe aislamiento | **No plenamente compatible**, H-03. `tests/test_mathmongo_config.py:32-127`, `tests/test_mathmongo_cli.py:1-148` |
| 22 | Launcher de escritorio: `mathmongo/desktop.py:115-202`; `mathmongo/launcher.py:59-71`, `mathmongo/launcher.py:114-175` | archivo `.desktop`, logs XDG; ping Mongo prearranque | E sólo archivos locales; no crea Source | independiente de contrato conceptual; informa Mongo detenido | Compatible por sí solo. `tests/test_mathmongo_desktop.py:43-193`, `tests/test_mathmongo_launcher.py:41-186` |
| 23 | Selección de base activa: `DatabaseManager`/bootstrap `editor/editor_streamlit.py:1091-1158`, switch `editor/editor_streamlit.py:1190-1238`; `build_catalog_context` `editor/source_catalog/shared.py:68-105` | `MathMongo` por conexión; repositorios ligados a base explícita | constructor puede crear índices; no crea Source | catálogo sí queda ligado a base; se instancia MathV0 aunque no sea activa | **No compatible**, H-03. Scope del catálogo: `tests/test_source_catalog_ui_scope.py:289-362`; no cubre la conexión literal |
| 24 | Cambio de base durante sesión: switch `editor/editor_streamlit.py:1190-1202`; `sync_database_state`/reading `editor/editor_streamlit.py:1237-1255` | cambia conexión actual; sólo Source Catalog/reading sincronizan namespace | L/E posteriores usan nueva base; no crea Source | Builder/KG retienen estado de la base anterior | **No compatible**, H-04/H-05. No hay cobertura de sesión cruzada para Builder/KG |

Resultado de la matriz: la presencia de `source_id` es compatible con la mayoría de consumidores. Los bloqueos no son una necesidad de `Change Source`; son rutas de creación/eliminación incompletas, dependencia de base y aislamiento de sesión.

## D. Escritores de Sources

### Inventario de producción

| Escritor | Operación y alcance | Clasificación |
|---|---|---|
| Add Source → `execute_add_source` → `SourceCatalogService.create_source` → `SourceRepository.insert` (`editor/source_catalog/add_source_page.py:116-260`, `editor/source_catalog/workflows.py:84-101`, `mathmongo/source_catalog/service.py:279-309`, `mathmongo/source_catalog/repository.py:196-203`) | `insert_one` de una Source validada en la base explícita; References asociadas por flujo explícito | creación interactiva autorizada |
| Edit/Archive/Delete Source (`editor/source_catalog/edit_source_page.py:218-410`, `editor/source_catalog/edit_source_page.py:689-825`, `editor/source_catalog/edit_source_page.py:910-1032`; `mathmongo/source_catalog/repository.py:227-365`, `mathmongo/source_catalog/repository.py:401-433`) | actualiza, archiva o elimina una entidad seleccionada por `source_id`; no hace upsert | administración autorizada del Source Catalog; H-02 afecta el guard de borrado |
| Bootstrap de migración (`mathmongo/source_catalog_migration/bootstrap.py:911-980`) | crea catálogo únicamente en una migración invocada explícitamente | escritor no interactivo autorizado por herramienta; **no ejecutado** |
| Importación (`editor/utils/db_import.py:2670-2830`) | restaura documentos `sources` y `references` explícitos contenidos en un archivo | restauración autorizada; no infiere Sources desde `concepts.source` |
| Database update/rollback (`editor/utils/db_update.py:1908-1986`, `editor/utils/db_update.py:2039-2090`) | aplica/revierte documentos explícitos según plan y backup | actualización administrada; no infiere por nombre |
| Fixtures/tests | escriben dobles o bases de test aisladas | fuera de producción |

No se encontró llamada de producción adicional a `SourceRepository.insert`. Add Concept, Edit Concept, Browse, Concept Linking, Knowledge Graph, media, lectura, Cornell, CPI y Document Builder no escriben `sources` ni `references`. Tampoco se encontró fallback silencioso por igualdad/similitud de nombre: la importación/update usan documentos de catálogo explícitos y el legacy link exige un `source_id` activo seleccionado (`editor/db/concept_source_link_service.py:450-487`).

Matiz importante: Cuaderno “Promover” crea un **snapshot textual libre** en un concepto pero no crea un documento `sources`. Por ello no contradice literalmente el inventario de escritores de la colección, aunque sí viola el contrato de que los conceptos nuevos sean modernos y que ninguna pantalla activa acepte Source libre; véase H-01.

Los índices de catálogo sólo se inicializan desde la acción confirmada y acotada a la base activa (`editor/source_catalog/shared.py:232-337`). No se ejecutó esa acción ni se cambió índice alguno en esta auditoría.

## E. Identidad de conceptos

### Guardado ordinario

- `ConceptoBase` admite `source_id` opcional junto a `id` y `source` (`schemas/schemas.py:131-160`).
- Add Concept construye snapshot e ID administrado a partir de la misma Source activa (`editor/helpers/concept_builders.py:4-15`) y el repositorio los persiste en ambos documentos (`editor/db/concept_repository.py:42-78`).
- Edit Concept carga la selección por par exacto y registra si originalmente existía `source_id` (`editor/editor_streamlit.py:2640-2766`). El servicio compara identidad antes de escribir y preserva los tres campos (`editor/db/concept_edit_service.py:117-202`, `editor/db/concept_edit_service.py:448-501`).
- Relaciones, media, Builder y nodos de mapas continúan usando el par histórico o `id@source`; agregar un campo no altera esa identidad.

### Vinculación legacy

El servicio carga exactamente `concepts` y `latex` por `(id, source)`, exige Source activa por ID, hace preflight de ambos documentos y sólo añade el mismo `source_id`. Usa transacción cuando está disponible y compensación/CAS cuando no; las repeticiones son idempotentes (`editor/db/concept_source_link_service.py:18-156`, `editor/db/concept_source_link_service.py:450-487`). Las pruebas verifican que relaciones, mapas y media no se reescriban.

### Riesgo de esquema latente

`DocumentoLatex` no declara `source_id` (`schemas/schemas.py:231-235`). Hoy no hay pérdida demostrada: el insert atómico copia el campo explícitamente y export/import/update escriben el documento crudo; incluso el validador de update valida un modelo pero aplica el payload original (`editor/utils/db_update.py:859-905`, `editor/utils/db_update.py:1931-1969`). Se clasifica como deuda BAJA porque una futura ruta basada en `model_dump()` sí podría descartarlo.

## F. Add Source

Add Source es el único creador **interactivo** de documentos Source. El flujo:

1. exige contexto de base explícito;
2. construye y valida `Source` con `source_id` generado, `name_normalized`, aliases normalizados, tipo, estado activo y timestamps (`mathmongo/source_catalog/models.py:223-301`);
3. presenta ID/nombre/tipo/aliases/status y evidencia de duplicado, y exige confirmación antes de continuar (`editor/source_catalog/add_source_page.py:146-178`);
4. exige confirmación exacta de la base activa e inserta sin upsert; un fallo posterior de Reference conserva la Source y se informa como resultado parcial, sin rollback destructivo (`editor/source_catalog/add_source_page.py:195-248`, `editor/source_catalog/workflows.py:84-101`);
5. conserva el `source_id` seleccionado y ofrece navegar al Source recién creado en Edit/Analyze (`editor/source_catalog/add_source_page.py:235-260`);
6. no depende de nombres ni contenido de MathV0.

La creación de índices de Source Catalog es una acción separada, explícitamente confirmada y segura para una base vacía (`editor/source_catalog/shared.py:232-337`). El índice `sources_source_id_unique` impone unicidad (`mathmongo/source_catalog/indexes.py:69-86`). Mongo crea la colección al inicializar sus índices/inserir el primer documento; no se exige una Source preexistente. Add Source sí permanece deshabilitado hasta que el usuario confirme esa inicialización (`editor/source_catalog/add_source_page.py:201-219`). No existe migración automática al abrir una base legacy.

## G. Add Concept

El flujo principal Add Concept es compatible:

- no usa `concepts.distinct("source")` para elegir la Source de un concepto nuevo; obtiene todas las Sources activas, incluso sin conceptos, del repositorio ligado a la base actual (`editor/helpers/managed_source_selection.py:14-30`, `editor/editor_streamlit.py:1859-1869`);
- muestra un selector cuyo valor interno es `source_id` y cuya etiqueta es `Source.name`; no contiene `(Custom...)`, `New source name` ni campo libre (`editor/helpers/managed_source_selection.py:38-50`, `editor/editor_streamlit.py:1885-1927`);
- deshabilita el guardado cuando falta o se invalida la selección y rehidrata la Source antes de persistir (`editor/editor_streamlit.py:2420-2445`);
- guarda `source` como snapshot y `source_id` como vínculo en `concepts` y `latex` (`editor/editor_streamlit.py:2470-2491`, `editor/db/concept_repository.py:42-78`).

Si el catálogo está vacío muestra “Crea primero una Source desde Add Source” y no permite guardar (`editor/editor_streamlit.py:1894-1902`). Una cadena que sólo existe como `concepts.source` legacy no aparece porque las opciones provienen exclusivamente del repositorio. Al cambiar de base, el rerun reconstruye `catalog_context` y la lista desde la conexión actual; el selector usa el namespace de Source Catalog (`editor/editor_streamlit.py:1190-1202`, `editor/editor_streamlit.py:1237-1255`, `editor/editor_streamlit.py:1904-1913`).

Sin embargo, Add Concept no es la única pantalla activa que crea conceptos. Cuaderno → Promover tiene un `st.text_input("Source")`, acepta cualquier texto no vacío y llama al mismo insert atómico sin `source_id` (`editor/cuaderno_page.py:1482-1486`, `editor/cuaderno_page.py:1541-1545`, `editor/cuaderno_page.py:1771-1846`). Es el defecto demostrado H-01.

## H. Edit Concept

La edición ordinaria preserva identidad. La UI selecciona el par exacto; el servicio no permite cambiar `id`, `source` ni `source_id`, actualiza `concepts`/`latex` de forma coordinada y no toca relaciones, mapas, media ni evidence (`editor/editor_streamlit.py:2640-2766`, `editor/db/concept_edit_service.py:117-202`, `editor/db/concept_edit_service.py:448-501`).

Para un concepto legacy, “Link to managed Source” es una acción explícita y separada. Sólo añade `source_id`; no cambia el snapshot, no resuelve por nombre y no implementa Change Source, Repair link, Synchronize snapshot ni unlink (`editor/db/concept_source_link_service.py:450-487`).

## I. Browse, Delete y navegación

Browse consulta conceptos sin exigir `source_id`, por lo que muestra legacy y modernos. Para detalle, LaTeX y media usa `(id, source)` (`editor/editor_streamlit.py:3582-3855`). Dos problemas preexistentes quedan documentados:

- la selección Quarto crea un mapa etiqueta→`id` y después incluye por ID, no por par; conceptos con el mismo ID en Sources distintas pueden seleccionarse juntos o sobrescribir etiquetas. Las keys de botones también usan sólo `id` (`editor/editor_streamlit.py:3627-3674`, `editor/editor_streamlit.py:3831-3848`), M-02;
- Delete Concept ejecuta borrados secuenciales. Edit borra `concepts`, `latex`, `relations`; Browse sólo `concepts` y `latex`. No existe transacción ni limpieza integral de mapas/media/evidence (`editor/editor_streamlit.py:3548-3568`, `editor/editor_streamlit.py:3848-3852`), M-01.

Ninguno depende de `source_id` para poder leer un concepto legacy. No se hizo ningún borrado durante la auditoría.

## J. Relaciones y Concept Linking

`MathMongo` valida ambos extremos con `(id, source)` y persiste endpoints `id@source` (`mathdatabase/mathmongo.py:407-492`). Un campo `source_id` adicional no cambia esas consultas. El legacy link no reescribe relaciones, y las pruebas de contrato lo verifican.

No se encontró fallback de nombre para resolver endpoints ni modificación ordinaria de `id@source`. El borrado parcial descrito en M-01 sí puede dejar dependencias sin limpieza, pero es un riesgo preexistente distinto del contrato administrado.

## K. Knowledge Maps y Knowledge Graphs

Los nodos y aristas usan `id@source`; el sync recupera conceptos por `id` y `source`, conserva el `graph_state` y sus posiciones, y no necesita `source_id` (`editor/utils/knowledge_graph_sync.py:282-359`, `editor/utils/knowledge_graph_sync.py:417-590`, `editor/utils/knowledge_graph_sync.py:610-669`). Export/import preserva mapas como documentos crudos. Dentro de una sola base, ambos contratos funcionan.

La vinculación legacy no reescribe `knowledge_graph_maps`, por lo que no mueve posiciones x/y, no duplica nodos ni elimina aristas (`tests/test_legacy_concept_source_link_service.py:219-276`). Los helpers que proyectan metadatos de nodo pueden omitir `source_id`, pero sólo construyen/copias de visualización: no reemplazan el documento `concepts`, no cambian la key y no causan pérdida en Mongo (`editor/utils/knowledge_graph_sync.py:417-590`). JSON/HTML/PyVis consumen campos conocidos y toleran que el documento conceptual tenga el campo adicional.

El bloqueo H-05 es de contexto de sesión: el selector de base sólo cambia la conexión y rerun; los keys de Knowledge Graph no incluyen base. En edición, el estado se recarga sólo si cambia `_id`; dos bases clonadas pueden compartir `_id`. El estado de A puede entonces repararse o guardarse en B (`editor/editor_streamlit.py:1190-1202`, `editor/editor_streamlit.py:4742-4823`, `editor/editor_streamlit.py:4957-5037`, `editor/editor_streamlit.py:5712-5733`).

## L. Media, Evidence y lectura

- Media enlaza conceptos con `id@source`, y sus lecturas/detach usan ambos componentes (`editor/utils/media_assets.py:33-35`, `editor/utils/media_assets.py:119-244`).
- El selector de lectura conserva `concept_legacy_id` y `concept_legacy_source`; sus cajas de texto son filtros, no creación de Source (`editor/reading_annotations/concept_picker.py:33-182`, `editor/reading_annotations/concept_picker.py:187-250`).
- Evidence verifica la existencia del concepto por el par histórico. `ConceptEvidenceLink.source_id` identifica el documento de evidencia, no la Source administrada del concepto (`mathmongo/reading_annotations/models.py:555-620`, `mathmongo/reading_annotations/service.py:1326-1522`).
- Cornell y CPI persisten notas canónicas en `latex_notes` y media por `note_id`; no reescriben conceptos ni Sources (`editor/cornell/service.py:20-95`, `editor/cpi/service.py:16-75`).

No se observó incompatibilidad causada por `concepts.source_id` en estas áreas. En MathV0 los dos vínculos conceptuales de media y los evidence links observados no tenían endpoints huérfanos.

## M. Document Builder

Builder carga y ordena por keys `id@source`, recupera exactamente el par, adjunta LaTeX y mantiene el documento crudo, por lo que tolera la ausencia o presencia de `source_id` (`editor/document_builder.py:39-90`, `editor/document_builder.py:238-268`). No escribe MongoDB.

No obstante, sus keys de `st.session_state` son globales y se inicializan una vez. Tras cambiar de base, la lista de keys seleccionada no se elimina ni se namespacea; `_concepts_for_keys` resuelve esas mismas keys contra la conexión nueva (`editor/document_builder.py:30-31`, `editor/document_builder.py:81-90`, `editor/document_builder.py:160-173`, `editor/document_builder.py:307-327`, `editor/document_builder.py:419-490`). Si B contiene el mismo `id@source`, el documento se genera silenciosamente con el concepto de B aunque la selección se hizo en A. Es H-04.

## N. Exportación, importación y database update

El registro de colecciones portables incluye catálogo, conceptos, LaTeX, relaciones, mapas, media y lectura (`mathkb_config.py:65-119`).

- Export serializa documentos Mongo crudos, manifest, media y blobs; no filtra `source_id` (`editor/utils/db_export.py:627-853`).
- Import restaura tipos y documentos crudos, valida relaciones y catálogos, y sólo inserta Sources explícitas del archivo (`editor/utils/db_import.py:2419-2830`).
- Update identifica conceptos por `(id, source)`, valida payloads, crea backup antes de aplicar y escribe el documento entrante sin reconstruirlo desde un modelo (`editor/utils/db_update.py:787-905`, `editor/utils/db_update.py:1768-1800`, `editor/utils/db_update.py:1908-1986`).
- Recovery revierte las operaciones registradas usando el backup (`editor/utils/db_update.py:2039-2090`).

El E2E de ciclo de vida previo demostró export→import→update con conceptos modernos y catálogo (`tests/test_fresh_database_lifecycle_e2e.py:237-352`). En esta auditoría no se habilitaron E2E opt-in ni se escribió una base real.

Un archivo legacy sin `source_id` sigue siendo aceptado y un update idéntico es no-op. Tampoco existe reparación por nombre. Sin embargo, los preflight de relaciones portables validan References, Source Documents, lectura/evidence y endpoints `id@source`, pero no comprueban el vínculo administrado de `concepts.source_id`/`latex.source_id` contra `sources` ni la igualdad entre el par (`editor/utils/db_export.py:450-625`, `editor/utils/db_import.py:1590-1676`, `editor/utils/db_update.py:1097-1232`). Por tanto, un link conceptual colgante o inconsistente se preserva pero no se reporta: M-03.

## O. Instalación y base nueva

La configuración soporta una base nueva propia: el default empaquetado es `mathmongo`, puede cambiarse por archivo/entorno/CLI y el launcher informa claramente si MongoDB no responde (`mathmongo/config.py:21-58`, `mathmongo/config.py:125-190`, `mathmongo/cli.py:36-83`, `mathmongo/launcher.py:59-71`, `mathmongo/launcher.py:114-175`). La instalación de escritorio sólo crea archivos de integración XDG y no importa backups personales (`mathmongo/desktop.py:115-202`).

Hay, sin embargo, una dependencia oculta de MathV0. `DatabaseManager.add_connection` construye `MathMongo`, cuyo constructor llama `ensure_indexes`; al inicializar la sesión, la app añade la base configurada y después añade incondicionalmente otra conexión a la base literal `MathV0` (`editor/editor_streamlit.py:1091-1158`, `mathdatabase/mathmongo.py:53-70`, `mathdatabase/mathmongo.py:95-167`). Aunque la conexión activa siga siendo la configurada, esa construcción puede materializar colecciones/índices en MathV0. Es H-03.

El valor configurable `DATABASE=MathV0` de flujos locales/Makefile (`Makefile:13-19`) es un default visible y sustituible; no es por sí solo el defecto. El problema bloqueante es instanciar una base adicional no seleccionada.

## P. Estado observado de MathV0

Se inspeccionó MathV0 estrictamente en modo read-only lógico mediante `ping`, `list_collection_names`, `find`, `aggregate`, `count_documents` y `list_indexes`, con `retryWrites=False` y preferencia secundaria. No se construyó `MathMongo`, no se llamó `ensure_indexes` y no se usó ningún componente capaz de crear índices. No se imprimió contenido matemático completo.

Resumen agregado:

| Entidad/validación | Resultado |
|---|---:|
| Colecciones | 19 |
| Sources | 17 activas, 0 archivadas |
| References | 21 |
| Concepts | 186 legacy, 0 modernos, 0 `source_id` nulos/inválidos/colgantes |
| LaTeX | 187 legacy, 0 modernos, 0 `source_id` nulos/inválidos/colgantes |
| Pares duplicados | 0 en concepts, 0 en latex |
| Integridad concept/LaTeX | 0 concepts sin LaTeX; 1 LaTeX sin concept |
| Inconsistencia `source_id` entre pares | 0 |
| Relaciones | 136; 0 endpoints colgantes |
| Mapas | 2; 62 nodos y 39 aristas |
| Media | 10 assets; 2 vínculos conceptuales; 0 colgantes |
| Evidence | 6; 0 conceptos o Sources de evidencia colgantes |
| Lectura | 3 annotations, 3 notes, 3 source documents, 2 reading states, 0 page maps |

El orphan LaTeX es una condición preexistente y no fue modificado. Dado que no hay conceptos modernos en MathV0, la falla H-02 no se manifiesta en esta muestra; se demuestra por la consulta incompleta del código y su reproducción determinista.

Prueba de no escritura:

| Snapshot mínimo | Antes | Después |
|---|---|---|
| hash de lista de colecciones | `c0ff79ce50d3bfbf626ade69e9d3d95e994a1b033f15199674c384f47fee1694` | igual |
| hash de conteos por colección | `6293411e6ee4af2120c440905c50e732ff8be9674781be71de6e168487e0c895` | igual |
| hashes de identidades relevantes | concepts, latex, sources, references, relations, maps, media, evidence y lectura | todos iguales |
| comparación integral del snapshot | `snapshots_equal: true` | `true` |

## Q. Cobertura de pruebas

### Ejecución enfocada

Se ejecutaron 50 archivos existentes relacionados con Source Catalog, Add Source, Add Concept, contratos, Edit/Link, portabilidad, update, grafos/mapas, relaciones, media, lectura/evidence, Cornell/CPI, PDF y instalación/launcher. Resultado:

```text
708 passed, 3 skipped, 3 failed, 6 warnings in 21.69s
```

Los tres fallos son:

1. `tests/test_xdg_media_paths.py::test_database_export_rejects_symlinked_output_destinations[zip_path]`
2. `tests/test_xdg_media_paths.py::test_database_export_publication_race_never_overwrites_symlink_target`
3. `tests/test_xdg_media_paths.py::test_database_export_detects_same_inode_mutation_after_publication`

Los tres fallan antes del escenario auditado en `editor/utils/db_export.py:647` porque el doble `_FixedExportDatetime` no expone `.now`. Pertenecen al baseline XDG ya conocido, no son una regresión de managed Sources. Los 3 skips corresponden a E2E opt-in no habilitados, como exigía el alcance.

No se repitió la suite completa: la fase anterior ya registró `1400 passed, 53 skipped, 4 failed`; sus cuatro fallos XDG son baseline conocido, y ejecutar de nuevo no aportaba evidencia frente a los bloqueos HIGH demostrados. No se ejecutó Ruff global.

### Matriz de cobertura

| Área | Pruebas existentes / cubierto | No cubierto | Riesgo / prioridad |
|---|---|---|---|
| Source Catalog / Add Source | `tests/test_source_catalog_repository.py:187-486`, `tests/test_source_catalog_service.py:155-314`, `tests/test_source_catalog_ui_workflows.py:71-144`, `tests/test_source_catalog_add_ui.py:107-244`: CRUD, duplicados, base explícita, archive/delete textual | blocker de borrado por `concepts.source_id` y rename sin alias | ALTO / P0 |
| Add Concept y contrato | `tests/test_add_concept_managed_source_selection.py:126-284`, `tests/test_concept_source_link_contract.py:65-152`: Source activa, revalidación, ambos documentos | Cuaderno → Promover como segundo creador de conceptos | ALTO / P0 |
| Edit preservation | `tests/test_edit_concept_identity_preservation.py:261-571`: par e identidad inmutables, coordinación | no gap bloqueante observado | BAJO / P3 |
| Legacy link | `tests/test_legacy_concept_source_link_service.py:284-525`, `tests/test_edit_concept_legacy_source_link_ui.py:1-193`: sólo añade ID, CAS, compensación, dependencias intactas | interacción con borrado posterior de Source | ALTO / P0 |
| Fresh DB / legacy E2E | `tests/test_fresh_database_lifecycle_e2e.py:96-352`, `tests/test_legacy_concept_source_link_e2e.py:1-201` | opt-in no ejecutado en esta auditoría | MEDIO / P2; evidencia previa suficiente |
| Export/import | `tests/test_source_catalog_backup.py:224-1390`, `tests/test_source_catalog_import_safety.py:26-85`, `tests/test_xdg_media_paths.py:242-450`: documentos crudos, catálogo, blobs | no valida `concepts.source_id`/`latex.source_id` contra catálogo/par; fallos XDG baseline | MEDIO / P1 (M-03) |
| Database update/recovery | `tests/test_database_update.py:344-1020`, `tests/test_database_update_e2e.py:86-224`: identidad, backup, apply/rollback | mismo gap de validación del link administrado | MEDIO / P1 (M-03) |
| Relaciones | `tests/test_legacy_concept_source_link_service.py:219-276`, `tests/test_edit_concept_identity_preservation.py:482-493`: endpoints/dependencias no reescritos | delete integral | MEDIO / P2 |
| Knowledge Graph/Maps | `tests/test_source_catalog_backup.py:309-423` preserva mapas; tests de link prohíben reescritura | no hay prueba funcional de sync/switch A→B con mismo `_id` | ALTO / P0 |
| Media | `tests/test_xdg_media_paths.py:22-224`, `tests/test_source_catalog_backup.py:424-719`: rutas y portabilidad; link prohíbe reescritura | cleanup al borrar concepto | MEDIO / P2 |
| Evidence/lectura | `tests/test_reading_annotations_core.py:534-650`, `tests/test_reading_annotations_portability.py:364-884`, `tests/test_advanced_reader_concept_linking.py:263-421`: par legacy y portabilidad | cleanup al borrar concepto | MEDIO / P2 |
| Document Builder | cobertura indirecta de navegación/exportadores | no hay test funcional de legacy/moderno ni cambio A→B con mismo `id@source` | ALTO / P0 |
| Cornell/CPI/PDF | `tests/test_cornell_service.py:1-240`, `tests/test_cpi_service.py:1-170`, `tests/test_generated_pdf_preview_flows.py:76-219`: persistencia/preview | Cuaderno promote no cubierto funcionalmente; sólo preview XDG | ALTO / P0 para promote |
| Instalación/launcher | `tests/test_mathmongo_config.py:32-127`, `tests/test_mathmongo_desktop.py:43-193`, `tests/test_mathmongo_launcher.py:41-186`: config, XDG, Mongo detenido | arranque no debe tocar una base literal no seleccionada | ALTO / P0 |

## R. Hallazgos

No se identificó ningún hallazgo CRÍTICO. Se identificaron cinco ALTO, cuatro MEDIO y uno BAJO.

### H-01 — Cuaderno crea conceptos legacy desde Source libre

- **Severidad/tipo:** ALTO; defecto demostrado; bloquea cierre.
- **Flujo:** Cuaderno → Diario LaTeX → Promover.
- **Evidencia:** deriva un default del proyecto o `Diario LaTeX`, presenta `st.text_input("Source")`, valida sólo texto no vacío y construye `ConceptoBase` sin `source_id` antes del insert atómico (`editor/cuaderno_page.py:1482-1486`, `editor/cuaderno_page.py:1541-1545`, `editor/cuaderno_page.py:1771-1846`).
- **Reproducción segura propuesta:** en una base de test con catálogo activo, abrir Promover, escribir un nombre que no exista y crear. Los documentos nuevos quedan con `(id, source)` y sin `source_id`; no ejecutar contra MathV0.
- **Riesgo:** una pantalla activa sigue creando snapshots arbitrarios y conceptos legacy, incumpliendo el flujo moderno principal.
- **Recomendación:** sustituir el input por selector de Sources activas de la base, revalidar al submit y guardar snapshot+ID en ambos documentos.
- **Archivos mínimos:** `editor/cuaderno_page.py`; helper/repository existente; tests funcionales de Cuaderno promote.

### H-02 — El borrado físico de Source no bloquea vínculos modernos

- **Severidad/tipo:** ALTO; defecto demostrado en código con reproducción determinista; bloquea cierre.
- **Flujo:** Source Catalog → Edit/Analyze → physical delete.
- **Evidencia:** `deletion_blockers` sólo cuenta References por `source_ids` y conceptos por texto entre nombre actual/`legacy.source_strings`; no consulta `concepts.source_id` (ni `latex.source_id`). Luego borra tras repetir la misma inspección incompleta (`mathmongo/source_catalog/repository.py:401-433`, `mathmongo/source_catalog/service.py:649-693`, UI `editor/source_catalog/edit_source_page.py:972-1032`).
- **Reproducción segura propuesta:** en una base aislada, crear Source S y concepto moderno; renombrar S sin conservar alias, de modo que el snapshot histórico ya no coincida; inspeccionar/borrar S. El vínculo `source_id` no bloquea y queda colgante. Alternativamente, vincular explícitamente un legacy cuyo snapshot difiera.
- **Riesgo:** dangling `source_id` en conceptos/LaTeX y pérdida del catálogo al que apuntan.
- **Recomendación:** bloquear por `concepts.source_id == source_id` y por el par de LaTeX; revalidar inmediatamente antes de delete y cubrir rename/snapshot distinto.
- **Archivos mínimos:** `mathmongo/source_catalog/repository.py`, `mathmongo/source_catalog/service.py`, tests de repository/service/UI.

### H-03 — La app instancia MathV0 aunque no sea la base configurada

- **Severidad/tipo:** ALTO; defecto demostrado; bloquea cierre.
- **Flujo:** instalación limpia/arranque/selección de base.
- **Evidencia:** la sesión añade “MathMongo (Current)” y después una conexión literal `MathV0` (`editor/editor_streamlit.py:1091-1158`). Construir `MathMongo` llama `ensure_indexes`, que puede crear colecciones/índices (`mathdatabase/mathmongo.py:53-70`, `mathdatabase/mathmongo.py:95-167`).
- **Reproducción segura propuesta:** con servidor Mongo de test vacío y config apuntando a `freshdb`, iniciar la app y listar bases/índices; aparece actividad en MathV0 aun sin seleccionarla. No realizar contra la MathV0 real.
- **Riesgo:** escritura oculta en base ajena, dependencia del nombre personal y violación del aislamiento de instalación/base activa.
- **Recomendación:** instanciar únicamente la base configurada; ofrecer conexiones adicionales sólo mediante acción explícita y sin constructor con efectos secundarios sobre bases no activas.
- **Archivos mínimos:** `editor/editor_streamlit.py`, posiblemente `mathdatabase/mathmongo.py`, tests de startup/configuración.

### H-04 — Document Builder reinterpreta selección al cambiar de base

- **Severidad/tipo:** ALTO; defecto demostrado por flujo de estado; bloquea cierre.
- **Flujo:** Document Builder + switch de base.
- **Evidencia:** los state keys no incluyen base y la selección persiste (`editor/document_builder.py:30-31`, `editor/document_builder.py:160-173`, `editor/document_builder.py:238-268`). Tras el rerun, `_concepts_for_keys` consulta la conexión actual (`editor/document_builder.py:81-90`); el switch no limpia ese estado (`editor/editor_streamlit.py:1190-1202`).
- **Reproducción segura propuesta:** bases aisladas A/B con el mismo `id@source` y contenido distinto; seleccionar en A, cambiar a B y generar. El resultado toma el documento de B bajo una selección originada en A.
- **Riesgo:** mezcla silenciosa de bases en un documento/exportación.
- **Recomendación:** namespacear por identidad de conexión+database o invalidar toda selección/validación/documento al cambiar la base; mostrar contexto de base en el resultado.
- **Archivos mínimos:** `editor/document_builder.py`, `editor/editor_streamlit.py`, test de sesión A→B.

### H-05 — Knowledge Graph/Maps conserva estado de otra base

- **Severidad/tipo:** ALTO; defecto demostrado por flujo de estado; bloquea cierre.
- **Flujo:** nuevo mapa y edición de mapa tras switch de base.
- **Evidencia:** HTML/stats/form/graph edit state usan keys globales (`editor/editor_streamlit.py:4620-4786`). Edición sólo reinicializa si cambia el `_id`, no si cambia la base (`editor/editor_streamlit.py:4957-5005`); un estado retenido puede repararse automáticamente o guardarse en la colección actual (`editor/editor_streamlit.py:5014-5037`, `editor/editor_streamlit.py:5712-5733`).
- **Reproducción segura propuesta:** clonar mapas A→B conservando `_id`, abrir edición en A, cambiar a B y abrir el mapa homónimo; el guard reutiliza el estado de A. Reparar o guardar escribe B con ese estado.
- **Riesgo:** mezcla y sobrescritura de graph state entre bases.
- **Recomendación:** incluir conexión/base en todas las keys o invalidar estado completo en switch; impedir reparación/guardado hasta recargar el documento de la base actual.
- **Archivos mínimos:** `editor/editor_streamlit.py`, helpers de sincronización de estado y tests de switch.

### M-01 — Delete Concept es secuencial e incompleto

- **Severidad/tipo:** MEDIO; defecto preexistente demostrado; bloquea cierre: no por sí solo.
- **Evidencia/reproducción:** borrar un concepto con dependencias desde Browse/Edit; una ruta omite relaciones y ambas omiten mapas/media/evidence. Si falla el segundo delete, tampoco hay compensación (`editor/editor_streamlit.py:3548-3568`, `editor/editor_streamlit.py:3848-3852`).
- **Riesgo/recomendación:** huérfanos o borrado parcial. Definir política explícita (bloquear/cascade), preflight y transacción/compensación. Archivos: página y servicios de dependencias.

### M-02 — Browse/Quarto y widget keys colapsan identidad a `id`

- **Severidad/tipo:** MEDIO; defecto demostrado por código; bloquea cierre: no por sí solo.
- **Evidencia/reproducción:** con dos conceptos `X@A` y `X@B`, seleccionar uno en Quarto; el filtro por `id` puede incluir ambos. Las keys de acciones también colisionan (`editor/editor_streamlit.py:3627-3674`, `editor/editor_streamlit.py:3831-3848`).
- **Riesgo/recomendación:** export/acción ambigua. Usar el par exacto o una key estructurada; añadir cobertura de IDs repetidos.

### M-03 — Portabilidad no reporta links administrados colgantes o inconsistentes

- **Severidad/tipo:** MEDIO; falta de validación demostrada; bloquea cierre: no por sí sola.
- **Flujo:** export, import y database update.
- **Evidencia/reproducción:** los validadores recorren Sources/References/lectura/evidence y relaciones, pero no correlacionan `concepts.source_id`, `latex.source_id` y `sources.source_id` (`editor/utils/db_export.py:450-625`, `editor/utils/db_import.py:1590-1676`, `editor/utils/db_update.py:1097-1232`). En un archivo sintético de test, un concepto moderno con ID ausente o un par concept/LaTeX con IDs diferentes supera esa comprobación y se copia sin inferencia ni reparación.
- **Riesgo/recomendación:** la portabilidad conserva fielmente una inconsistencia preexistente sin avisar. Añadir preflight que acepte pares ambos-legacy, exija igualdad ambos-modernos y resuelva exactamente el ID en catálogo; nunca reparar por nombre. Archivos: los tres módulos de portabilidad y pruebas enfocadas.

### M-04 — Cobertura funcional insuficiente en flujos transversales

- **Severidad/tipo:** MEDIO; gap demostrado; bloquea cierre: no por sí solo, pero permitió H-01/H-04/H-05 y M-03.
- **Evidencia:** no hay prueba funcional de Cuaderno promote con Source administrada, de Builder A→B, ni de KG A→B; la prueba de Cuaderno localizada cubre preview/PDF, no persistencia (`tests/test_xdg_mutable_guards.py:132-161`).
- **Recomendación:** añadir pruebas dirigidas junto con los fixes HIGH, no durante esta auditoría.

### L-01 — `DocumentoLatex` no modela `source_id`

- **Severidad/tipo:** BAJO; riesgo razonable/ deuda técnica, no pérdida actual; no bloquea cierre.
- **Evidencia:** `schemas/schemas.py:231-235`; las rutas actuales preservan el raw payload (`editor/db/concept_repository.py:42-78`, `editor/utils/db_update.py:859-905`).
- **Riesgo/recomendación:** una futura serialización por modelo podría descartarlo. Incorporar el campo y una prueba de round-trip cuando se toque ese esquema.

## S. Criterios de cierre

| # | Criterio | Sí/No | Evidencia/conclusión |
|---:|---|:---:|---|
| 1 | ¿Add Source es el único creador interactivo de Sources? | **Sí** | único creador de documentos `sources`; import/update/migration son explícitos. H-01 crea un snapshot libre, no una Source documental |
| 2 | ¿Add Concept sólo selecciona Sources existentes? | **Sí** | su flujo propio lo hace; el bloqueo está en otro creador de conceptos (Cuaderno) |
| 3 | ¿Edit Concept preserva identidad? | **Sí** | preserva `id`, `source`, `source_id` |
| 4 | ¿Legacy link sólo añade `source_id`? | **Sí** | preflight/CAS/transacción-compensación, sin dependencias |
| 5 | ¿Conceptos modernos funcionan en base nueva? | **Sí** | unitarias y E2E previo de fresh database |
| 6 | ¿Conceptos legacy siguen funcionando? | **Sí** | lecturas no exigen `source_id`; MathV0 es íntegramente legacy |
| 7 | ¿Export/import conserva `source_id`? | **Sí** | documentos crudos y E2E previo |
| 8 | ¿Database update conserva `source_id`? | **Sí** | valida y aplica payload original; E2E previo |
| 9 | ¿Knowledge Maps permanecen intactos? | **No** | contrato de campo sí; el switch de base puede reutilizar/guardar estado ajeno (H-05) |
| 10 | ¿Relaciones permanecen intactas? | **Sí** | endpoints `id@source`; legacy link no las toca |
| 11 | ¿Media permanece intacta? | **Sí** | clave `id@source`; presencia de `source_id` no cambia lookup |
| 12 | ¿Evidence links permanecen intactos? | **Sí** | vínculo conceptual por par histórico |
| 13 | ¿Document Builder funciona con ambos contratos? | **No** | dentro de una base sí, pero no es seguro tras switch (H-04) |
| 14 | ¿No hay dependencia hardcodeada de MathV0? | **No** | conexión literal e inicialización con efectos secundarios, H-03 |
| 15 | ¿No existen escrituras indebidas en `sources`? | **Sí** | inventario sólo contiene catálogo y portabilidad/migración explícitas; no hubo escritura en auditoría |
| 16 | ¿Puede cerrarse una versión estable sin implementar Change Source? | **No** | Change Source no es requisito, pero los cinco HIGH sí impiden el cierre |
| 17 | ¿Existen defectos críticos o altos que bloqueen el cierre? | **Sí** | 0 CRÍTICOS, 5 ALTOS |

## T. Recomendación final

**D. BLOQUEADO POR HALLAZGOS ALTOS**

No se recomienda `VERSION-CLOSURE-MANAGED-SOURCE-WORKFLOW`. El contrato básico `source`/`source_id` funciona en edición, link y portabilidad, pero cinco defectos demostrados rompen requisitos explícitos: creación moderna desde toda pantalla activa, integridad del vínculo al borrar Source, independencia de MathV0 y aislamiento de bases en Builder/Knowledge Graph.

## U. Limitaciones aceptadas

Estas observaciones no requieren por sí solas ampliar la fase actual:

- `source` sigue siendo snapshot histórico; no se sincroniza automáticamente al renombrar una Source.
- No existen Change Source, Repair link, Synchronize snapshot ni unlink; esta auditoría no los considera necesarios para corregir los HIGH.
- MathV0 contiene sólo conceptos legacy; sigue siendo una base válida sin migración automática.
- Existe un documento LaTeX huérfano preexistente en MathV0; no fue creado ni modificado aquí.
- Los E2E opt-in no se habilitaron; se reutilizó la evidencia de fases previas y las suites unitarias enfocadas.
- Los fallos XDG actuales pertenecen al baseline conocido y deben tratarse fuera del contrato managed Source.
- M-01, M-02, M-03, M-04 y L-01 son deuda separable, aunque conviene resolver los MEDIO antes o durante una estabilización posterior.

Los cinco HIGH no son limitaciones aceptables para cierre.

## V. Próxima fase

Antes de una nueva auditoría deben implementarse exclusivamente estos fixes mínimos, en este orden:

1. **Cuaderno promote:** seleccionar/revalidar una Source administrada activa y persistir `source` + `source_id` en ambos documentos; añadir prueba funcional.
2. **Source delete guard:** bloquear por `concepts.source_id` y `latex.source_id`, revalidar antes de borrar y cubrir snapshot distinto/rename sin alias.
3. **Arranque/base activa:** eliminar la instanciación incondicional de MathV0; abrir sólo la base configurada y hacer explícita cualquier conexión adicional.
4. **Estado dependiente de base:** namespacear o limpiar íntegramente Document Builder y Knowledge Graph/Maps al cambiar de conexión/base; probar identidades y `_id` iguales entre A/B y ausencia de escrituras automáticas cruzadas.

Prompt requerido: `MANAGED-SOURCE-WORKFLOW-COMPATIBILITY-FIXES`.

Después de esos fixes debe repetirse esta auditoría. Sólo si la nueva recomendación es A o B podrá seguir `VERSION-CLOSURE-MANAGED-SOURCE-WORKFLOW`.

Confirmaciones de alcance: no se modificó MongoDB, no se creó ninguna Source, no se modificó código ni pruebas, no se ejecutó migración, no se hizo backfill, no se implementó Change Source, no se modificaron conceptos existentes, no se cambió ningún índice y no se hizo push.

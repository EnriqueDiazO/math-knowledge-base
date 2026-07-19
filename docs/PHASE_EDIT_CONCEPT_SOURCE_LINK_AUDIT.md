# Edit Concept Source Link Audit

Auditoría documental de `SOURCE-INTEGRATION-S3-AUDIT`. El alcance es exclusivamente
el flujo actual de **Edit Concept**, su dependencia de la identidad histórica
`(id, source)` y el diseño de una integración futura con Sources administradas. No
se implementó la solución ni se modificó MongoDB.

## A. Estado Git y entorno

Baseline verificado antes de cualquier cambio:

| Comprobación | Resultado |
| --- | --- |
| Repositorio | `/home/enriquedo/PersonalProjects/math-knowledge-base` |
| `git rev-parse --show-toplevel` | `/home/enriquedo/PersonalProjects/math-knowledge-base` |
| Rama | `main` |
| HEAD | `6a2136af7901f5d20a0913c13768d19ab1b7740f` |
| Commit esperado | `6a2136af feat(ui): select managed sources in Add Concept` |
| `origin/main...HEAD` | `0 0` |
| Worktree inicial | limpio |
| Base de datos inspeccionada | `MathV0`, sólo lectura |

Los cinco commits iniciales fueron:

```text
6a2136af (HEAD -> main, origin/main, origin/HEAD) feat(ui): select managed sources in Add Concept
83f8fb51 feat(concepts): add optional managed source linkage
19c86838 docs: audit Add Concept source integration
d4151312 (tag: v0.11.2-pre-reading-workflow) fix(import): refine safe database update workflow
c0322239 (tag: v0.12.0-pre-safe-database-update, origin/backup/database-update-c0322239) feat(import): update existing databases safely
```

Se leyeron primero los contratos requeridos:

- `docs/PHASE_SOURCE_ADD_CONCEPT_INTEGRATION_AUDIT.md`;
- `docs/PHASE_SOURCE_LINK_CONTRACT.md`;
- `docs/PHASE_ADD_CONCEPT_MANAGED_SOURCE_SELECTION.md`.

El contrato heredado es deliberado: `source_id` representa el vínculo administrado
opcional y `source` continúa siendo un snapshot requerido y parte de la identidad
compatible. **Add Source** es el único flujo autorizado para crear Sources.

## B. Flujo actual de Edit Concept

### B.1 Trazado con archivo y líneas

| Paso | Implementación actual |
| --- | --- |
| Router | Rama `elif page == "✏️ Edit Concept"` en `editor/editor_streamlit.py:2623-2629`. |
| Base activa | Exige `db` y muestra `current_db` en `editor/editor_streamlit.py:2627-2631`. |
| Filtros de selección | Keys namespaced en `editor/editor_streamlit.py:2636-2640`; Sources obtenidas con `db.concepts.distinct("source")` en `2641-2646`; tipos con `distinct("tipo")` en `2647-2654`. |
| Navegación desde Source Catalog | Consume una identidad legacy exacta y ajusta filtros en `editor/editor_streamlit.py:2636-2664`; resuelve por igualdad de `id` y `source` en `2714-2727`. |
| Consulta de conceptos | Construye un query opcional por `source` y `tipo`, y ejecuta `db.concepts.find(query)` en `editor/editor_streamlit.py:2688-2696`. |
| Selector | Construye etiquetas y un mapa a documentos completos en `editor/editor_streamlit.py:2702-2712`; usa `selectbox` en `2731-2737`. |
| Identidad de selección | Tupla `(selected_concept["id"], selected_concept["source"])` en `editor/editor_streamlit.py:2742-2752`. |
| Carga de LaTeX | `find_one({"id": ..., "source": ...})` en `editor/editor_streamlit.py:2754-2759`. |
| Estado del formulario | Copia `id`, `source`, LaTeX y demás campos a `st.session_state` en `editor/editor_streamlit.py:2761-2829`; fuerza `st.rerun()` al cambiar de concepto. |
| Formulario de identidad | `ID` y `Source` son dos `text_input` editables en `editor/editor_streamlit.py:2838-2842`. El tipo queda de sólo lectura en `2851-2852`. |
| Opción Custom | No hay una opción llamada `Custom`, pero el `text_input` de Source acepta cualquier texto y por tanto es funcionalmente más permisivo que Custom. |
| Key del editor LaTeX | Se deriva de `edit_id@edit_source` en `editor/editor_streamlit.py:3043-3055`. |
| Media durante la edición | El gestor se invoca con los valores editables `concept_id` y `source`, antes de guardar, en `editor/editor_streamlit.py:3061-3068`. |
| Construcción del update | Diccionario raw `concept_data` en `editor/editor_streamlit.py:3173-3234`; contiene `source`, pero no contiene `source_id`. |
| Update de `concepts` | `update_one` filtrado por el `id` y `source` originales, con `$set: concept_data`, en `editor/editor_streamlit.py:3236-3240`. |
| Update de `latex_documents` | Segundo `update_one` por el mismo par original; sólo cambia contenido y fecha, no `id`, `source` ni `source_id`, en `editor/editor_streamlit.py:3241-3251`. |
| Resultado | Muestra éxito sin inspeccionar `matched_count`/`modified_count` en `editor/editor_streamlit.py:3253-3257`. |
| Reset/rerun | Reset sólo hace `st.rerun()` en `editor/editor_streamlit.py:3327-3329`; el guardado no fuerza rerun. |
| Eliminación | Borra secuencialmente concepto, LaTeX y relaciones usando la identidad original en `editor/editor_streamlit.py:3344-3362`. |
| Validadores | `editor/validators/concept_validator.py:11-53` sólo expone validadores de creación para `(id, source)` y duplicado semántico. Edit Concept no los llama. |
| Repositorio | `editor/db/concept_repository.py:3-91` contiene helpers de alta y rollback best-effort, pero Edit Concept no los usa. |
| Modelo | `ConceptoBase` declara `source` requerido y `source_id` opcional en `schemas/schemas.py:131-160`. `DocumentoLatex` declara `id`, `source` y contenido, pero no `source_id`, en `schemas/schemas.py:231-235`. |
| Pruebas actuales | No existe una prueba funcional del botón **Update Concept** ni del movimiento de identidad. `tests/test_concept_source_link_contract.py` cubre el contrato de creación; otras suites cubren Add Concept, estado UI y consumidores adyacentes. |

### B.2 Flujo efectivo

```text
Streamlit UI
  -> concepts.distinct("source") para filtrar documentos legacy
  -> concepts.find(query) y selección por (id, source)
  -> latex_documents.find_one por (id, source)
  -> session_state edit_*
  -> inputs de ID y Source como texto libre
  -> diccionario raw concept_data
  -> concepts.update_one por la identidad original
  -> latex_documents.update_one por la identidad original
  -> mensaje de éxito sin comprobar resultados
```

No hay paso real de modelo, validación de Source Catalog ni repositorio entre la UI
y MongoDB. El flujo es **UI → diccionario raw → PyMongo directo**. Tampoco consulta
la colección `sources`, no distingue activa/archivada/inexistente y no crea ni
actualiza Sources.

### B.3 Efecto de omitir `source_id`

MongoDB no elimina un campo omitido de `$set`. Por ello:

- al editar un concepto vinculado sin cambiar Source, el `source_id` ya existente
  en `concepts` se conserva accidentalmente, no por un contrato explícito;
- el `source_id` ya existente en `latex_documents` también se conserva porque el
  segundo update no lo toca;
- un concepto legacy sigue legacy;
- si se cambia el texto `source`, el concepto conserva el `source_id` anterior,
  aunque el snapshot ya represente otra Source;
- el documento LaTeX conserva además su `id`, `source` y `source_id` anteriores.

## C. Identidad histórica `(id, source)`

### C.1 Dependencias encontradas

La pareja no es sólo una clave de búsqueda de Edit Concept:

- **Índices:** `concepts` y `latex_documents` tienen índice único sobre
  `(id, source)`; `mathdatabase/mathmongo.py:105-115`.
- **Ingesta y lectura:** los upserts, getters y updates LaTeX usan la pareja en
  `mathdatabase/mathmongo.py:179-263`.
- **Edición, navegación, exportación y eliminación:** Edit Concept usa la pareja
  en `editor/editor_streamlit.py:2636-3362`; Browse/Quarto vuelven a buscar o
  borrar por ella en `editor/editor_streamlit.py:3370-3641`.
- **Relaciones:** verifican ambos conceptos por la pareja y almacenan endpoints
  como `id@source` en `mathdatabase/mathmongo.py:406-455`; sus lectores vuelven a
  separar y resolver esos strings en `460-529`.
- **Índice de relaciones:** `(desde, hasta, tipo)` es único en
  `mathdatabase/mathmongo.py:116-120`; mover un endpoint también puede colisionar.
- **Grafos:** las keys y nodos se construyen como `id@source` en
  `editor/utils/knowledge_graph_sync.py:51-127`, y el estado guardado en
  `knowledge_graph_maps` contiene nodos, aristas y listas de keys dependientes.
  `editor/interactive_graph.py` también resuelve conceptos por esa identidad.
- **Media:** `media_assets.concept_ids` almacena `id@source` y el concepto se
  busca por la pareja en `editor/utils/media_assets.py:139-166`, `182-193` y
  `218-244`.
- **Concept linking:** los resúmenes, selecciones y búsquedas exactas usan la
  pareja en `editor/concept_linking/concept_search.py:20-182` y en
  `mathmongo/advanced_reader/concept_search.py`.
- **Evidencia de lectura:** `ConceptEvidenceLink` conserva
  `concept_legacy_id` y `concept_legacy_source` en
  `mathmongo/reading_annotations/models.py:555-600`; los repositorios y paneles
  resuelven el concepto con esos campos. Su `source_id` identifica la Source del
  contexto de evidencia y no debe reescribirse automáticamente al mover un
  concepto.
- **Document builder:** conserva keys de concepto y carga LaTeX por `id/source`
  en `editor/document_builder.py:34-113` y sus consumidores posteriores.
- **Import/export:** la portabilidad de evidencia exige una coincidencia única de
  `(concept_legacy_id, concept_legacy_source)` en
  `editor/utils/db_export.py:435-495`; import resuelve la misma pareja en
  `editor/utils/db_import.py:2099-2129`.
- **Actualización de bases:** `concepts` y `latex_documents` declaran
  `("id", "source")` como identidad primaria en
  `editor/utils/db_update.py:86-103`; las relaciones se validan como endpoints
  `id@source` en `editor/utils/db_update.py:1088-1193`.
- **Backups:** exportan los documentos completos y por ello preservan
  `source_id`, pero la reconciliación posterior continúa identificando conceptos
  y LaTeX por `(id, source)`.

Los campos bibliográficos embebidos en el concepto se mueven con el propio
documento. En cambio, `references.source_ids` del Source Catalog representa la
asociación bibliográfica con Sources y no una referencia a la identidad de un
concepto; una relocalización de concepto no debe modificarla.

### C.2 Respuestas de identidad

1. **¿Cambiar `source` cambia identidad?** Sí. Actualmente altera una columna del
   índice único, la clave de LaTeX y múltiples referencias `id@source`.
2. **¿El update actual modifica ambos documentos?** No. Modifica `source`/`id`
   sólo en `concepts`; el update de LaTeX sólo cambia contenido y timestamp.
3. **¿Puede dejar un LaTeX huérfano?** Sí. Tras mover exitosamente el concepto,
   el LaTeX permanece en la pareja antigua.
4. **¿Puede crear duplicados?** Los índices únicos reales impiden dos documentos
   con el mismo par, pero no impiden el estado partido entre collections. En una
   base sin esos índices el código no hace preflight y sí podría producir
   duplicidad o ambigüedad.
5. **¿Qué ocurre si existe el mismo `id` en la Source destino?** Si existe el par
   exacto en `concepts`, el primer update colisiona con el índice único. Si sólo
   existe en `latex_documents`, el primer update puede tener éxito y el estado
   queda partido; el segundo update ni siquiera intenta mover el LaTeX.
6. **¿Qué rollback usa Edit Concept?** Ninguno. El helper de alta no utilizado
   borra por `(id, source)` en `editor/db/concept_repository.py:73-78`, pero no
   compensa una edición.
7. **¿Qué otros documentos conservan `source`?** Relaciones, media assets,
   evidence links y mapas de conocimiento conservan la identidad exacta; sesiones
   de Document Builder y otros consumidores mantienen keys derivadas.
8. **¿Puede añadirse `source_id` sin cambiar identidad histórica?** Sí. Un `$set`
   explícito de `source_id` en el concepto y su LaTeX, dejando `id` y `source`
   idénticos, vincula el registro sin relocalizarlo. Incluso si `Source.name`
   difiere del snapshot, la diferencia puede mostrarse y sincronizarse después.
9. **¿Debe hacerse autoritativo `source_id` ahora?** No para la identidad global.
   Debe ser autoritativo para seleccionar la Source administrada, pero los índices
   y consumidores actuales todavía requieren el snapshot `source`.
10. **¿Quién seguirá necesitando `source`?** Índices, LaTeX, relaciones, grafos,
    media, concept linking, evidence links, import/export, database update,
    navegación legacy y backups compatibles.

## D. Persistencia en concepts

`ConceptoBase` ya admite `source_id`, pero Edit Concept no instancia el modelo. El
documento actualizado se arma manualmente y contiene el `source` que el usuario
escriba. Consecuencias:

- no hay validación de que `source` sea el snapshot de una Source administrada;
- no hay validación de existencia ni `status` de `source_id`;
- no hay selección por `source_id`;
- no hay detección previa del par destino;
- no se exige que la identidad original siga existiendo;
- no se comprueba que `matched_count == 1`;
- un guardado no relacionado conserva `source_id`, pero sólo por la semántica de
  `$set` parcial;
- un cambio de texto puede dejar `{source_id: A, source: "B"}` sin advertencia.

La operación usa el documento seleccionado como filtro original, lo cual evita que
la edición cambie silenciosamente el selector en mitad del request, pero no ofrece
control de concurrencia. Dos sesiones pueden sobrescribir metadatos con last-write
wins.

## E. Persistencia en latex_documents

El alta coordinada actual sí copia `source_id` a LaTeX cuando existe
(`editor/db/concept_repository.py:42-78`). Edit Concept, en cambio:

- busca LaTeX por el par original;
- actualiza sólo `contenido_latex` y `ultima_actualizacion`;
- no mueve `id` ni `source`;
- no añade, cambia ni repara `source_id`;
- no usa transacción;
- no compensa si falla el segundo update;
- no inspecciona el resultado y puede mostrar éxito con cero coincidencias.

Además, `DocumentoLatex` no declara todavía `source_id`. El pipeline de database
update valida los campos conocidos pero conserva el documento raw, por lo que el
campo puede viajar en backups; aun así, el contrato de esquema debería hacerse
explícito antes de implementar cambios coordinados.

## F. Estado real de MathV0

### F.1 Método de sólo lectura

Se usó un `MongoClient` directo con `retryWrites=False`, preferencia secundaria y
operaciones exclusivamente `ping`, `hello`, `find`, agregación de conteos y
`list_indexes`. No se instanció `MathMongo`, porque su inicialización puede crear
índices. Las proyecciones se limitaron a `_id`, campos identitarios, `source_id`,
status y referencias necesarias para los conteos. No se imprimió contenido LaTeX
ni matemático.

Se tomó un SHA-256 de cada snapshot proyectado, ordenado y canonicalizado, antes y
después de la inspección.

### F.2 Conteos

| Medida | Resultado |
| --- | ---: |
| Documentos en `concepts` | 186 |
| Conceptos con campo `source_id` | 0 |
| Conceptos con `source_id` no vacío | 0 |
| Conceptos legacy | 186 |
| Documentos en `latex_documents` | 187 |
| LaTeX con campo `source_id` | 0 |
| LaTeX con `source_id` no vacío | 0 |
| Pares concepto/LaTeX coincidentes | 186 |
| Pares con el mismo estado de `source_id` | 186; ambos ausentes |
| Discrepancias de `source_id` en pares | 0 |
| Pares duplicados en `concepts` | 0 |
| Pares duplicados en `latex_documents` | 0 |
| IDs repetidos entre Sources distintas | 0 |
| Máximo de Sources para un mismo ID | 1 |
| LaTeX huérfanos | 1 |
| Conceptos sin LaTeX | 0 |
| Sources administradas | 17 |
| Sources activas | 17 |
| Sources archivadas | 0 |
| Links con `source_id` inexistente | 0, no hay links |
| Snapshots distintos de `Source.name` | 0, no hay links |
| Links hacia Sources archivadas | 0, no hay links |
| Relaciones | 136; 272 endpoints legacy |
| Evidence links con identidad legacy | 6 |

Los índices reales de `concepts` y `latex_documents` incluyen `_id_` y el índice
único `id_1_source_1`. No se observó `setName` en `hello`; por tanto, este despliegue
local no debe asumirse transaccional y el fallback compensatorio es un requisito
operativo, no sólo teórico.

### F.3 Prueba de no escritura

| Colección proyectada | SHA-256 antes | SHA-256 después |
| --- | --- | --- |
| `concepts` | `bef9b944bd4390e8b41297221ccc6210ab73cdb125c0f4c5cd62855468c9873f` | `bef9b944bd4390e8b41297221ccc6210ab73cdb125c0f4c5cd62855468c9873f` |
| `latex_documents` | `75d92075c6f469be66012913abd1ef69df8b090e5669f05a7529bd764f6117b6` | `75d92075c6f469be66012913abd1ef69df8b090e5669f05a7529bd764f6117b6` |
| `sources` | `f38e898fd4707491d95de185dd4ee59616e4e87b80bd19de691207457bcd98a1` | `f38e898fd4707491d95de185dd4ee59616e4e87b80bd19de691207457bcd98a1` |
| `relations` | `180a0448dfe6b637a9e6f6b9ddb3751ce2093bf25c26701df09cb92971e0971f` | `180a0448dfe6b637a9e6f6b9ddb3751ce2093bf25c26701df09cb92971e0971f` |
| `concept_evidence_links` | `fa945d68eea1481506faeece864028bab5f98fb525510fa42dce5abc86a2ff08` | `fa945d68eea1481506faeece864028bab5f98fb525510fa42dce5abc86a2ff08` |

Los conteos y los cinco hashes coinciden. La auditoría no escribió en MongoDB.

## G. Conceptos legacy

Un concepto `{source: "Python"}` sin `source_id` debe:

1. seguir apareciendo, abriendo y guardando campos no relacionados;
2. conservar exactamente el snapshot `source` al guardar;
3. no recibir `source_id` automáticamente;
4. mostrar estado **Legacy — not linked to a managed Source**;
5. ofrecer una acción separada **Link to an existing managed Source**;
6. listar únicamente Sources administradas existentes y activas, identificadas
   internamente por `source_id`;
7. añadir el `source_id` coordinadamente a `concepts` y `latex_documents`, sin
   cambiar `id` ni `source`;
8. no crear, upsertar ni inferir una Source por nombre.

Vincular y sincronizar snapshot deben ser acciones distintas. Así un legacy puede
vincularse de forma segura aunque su texto histórico no sea idéntico al nombre
actual. La UI debe mostrar ambas cadenas y pedir una segunda acción explícita si el
usuario quiere relocalizar el snapshot.

## H. Conceptos vinculados

### H.1 Source activa

Para `{source: "Python", source_id: "src_..."}` con Source existente y activa:

- el formulario normal muestra la Source administrada como contexto, no como
  `text_input` libre;
- editar título, categorías, LaTeX, referencias o metadatos preserva exactamente
  `source` y `source_id` en ambos documentos;
- el payload de campos no relacionados no debe incluir cambios de vínculo;
- la asociación sólo cambia mediante una acción explícita y confirmada;
- no se escribe en `sources`.

### H.2 Guardar sin cambiar Source

El caso no-op del vínculo debe tratar `source` y `source_id` como valores
precondicionados, no como valores reconstruidos desde la UI. El servicio debe
comparar la identidad esperada y rechazar una edición stale; nunca debe sincronizar
el snapshot como efecto lateral de guardar otro campo.

## I. Sources renombradas, archivadas o inexistentes

### I.1 Source renombrada

Si `source_id` resuelve una Source cuyo `name` ya difiere de `concept.source`:

- se conserva el snapshot antiguo en cualquier guardado ordinario;
- se muestra una advertencia con snapshot y nombre actual;
- se ofrece **Synchronize Source snapshot** como acción explícita;
- esa sincronización se trata como relocalización de identidad completa, no como
  un `$set` de conveniencia.

La sincronización automática es riesgosa: editar un comentario movería LaTeX,
relaciones, media, evidence links y grafos, podría colisionar con índices y volvería
impredecible un guardado aparentemente inocuo.

### I.2 Source archivada

Un vínculo existente hacia una Source archivada sigue siendo una asociación
histórica válida. Se permiten cambios no relacionados y se preserva el vínculo.
Una Source archivada no aparece como nuevo destino ni para Add Concept ni para un
nuevo link. La UI muestra el status y ofrece cambiar o reparar hacia una Source
activa; no reactiva ni desvincula automáticamente.

### I.3 `source_id` inexistente

La UI debe mostrar un error persistente: **Managed Source is unavailable; the
stored link was preserved.** Se permiten ediciones no relacionadas siempre que
preserven exactamente el `source_id` dangling y el snapshot. Las acciones de link,
sync o cambio quedan bloqueadas hasta una reparación explícita hacia una Source
activa. Está prohibido resolver silenciosamente por igualdad o similitud de nombre.

La reparación de asociación puede cambiar sólo `source_id` y conservar la identidad
histórica. Cambiar además el snapshot requiere la operación de relocalización.

## J. Riesgos de cambiar Source

El comportamiento actual tiene estos riesgos concretos:

1. **LaTeX huérfano:** `concepts` cambia de pareja y `latex_documents` permanece
   en la anterior.
2. **Concepto sin LaTeX resoluble:** las pantallas que buscan el nuevo par no
   encuentran contenido, aunque el documento viejo siga existiendo.
3. **Vínculo incoherente:** el viejo `source_id` queda asociado al nuevo texto
   `source`.
4. **Colisión de concepto:** el índice único puede rechazar el primer update.
5. **Colisión independiente de LaTeX:** un documento destino puede bloquear una
   relocalización coordinada después de haber cambiado el concepto.
6. **Relaciones rotas:** `desde`/`hasta` continúan apuntando a `id@source` viejo;
   reescribirlos sin preflight puede colisionar con el índice único de relaciones.
7. **Media desacoplada:** `media_assets.concept_ids` conserva la key vieja. Además,
   el gestor actual recibe el ID/Source editables antes del guardado, de modo que
   puede operar contra una identidad todavía inexistente o ajena.
8. **Evidence links rotos:** `concept_legacy_source` sigue apuntando al snapshot
   anterior.
9. **Mapas inconsistentes:** nodos, aristas y listas de keys guardadas retienen la
   identidad anterior. Los filtros amplios por Source no pueden reescribirse
   mecánicamente sin afectar la semántica de otros conceptos.
10. **Import/export ambiguo:** los validadores de portabilidad y database update
    siguen reconciliando por `(id, source)`.
11. **Éxito falso:** no se comprueban resultados de los dos updates.
12. **Parcialidad no recuperada:** no existe transacción ni compensación.
13. **Concurrencia:** no hay compare-and-set, revision ni hash esperado.
14. **ID también editable:** cambiar simultáneamente `id` amplía la misma
    relocalización y multiplica los consumidores afectados.

La recomendación es hacer `id` inmutable durante una operación de Source. Un cambio
de ID, si se desea en el futuro, debe ser otra operación explícita de identidad.

## K. Alternativas

| Opción | Compatibilidad y datos legacy | Integridad, duplicados y rollback | UX, migración, import/export y pruebas | Evaluación |
| --- | --- | --- | --- | --- |
| 1. Conservar vínculo y no permitir cambiar Source | Máxima compatibilidad; legacy sigue legacy. | Muy bajo riesgo; no mueve claves ni exige rollback distribuido. | UX limitada pero predecible; sin migración; import/export sin cambios; pruebas simples de preservación. | **Recomendada como primera entrega.** |
| 2. Cambiar hacia una Source administrada y actualizar `source_id + source` | Compatible sólo si se preservan todos los consumidores legacy. | Alto riesgo de colisión y parcialidad; exige preflight, transacción o compensación y reescritura exacta de dependencias. | UX potente pero debe ser acción confirmada; sin migración global; import/export y pruebas requieren ampliación. | **Recomendada después del servicio atómico completo.** |
| 3. Bloquear campos no relacionados de legacy hasta vincular | Rompe compatibilidad con los 186 conceptos actuales. | Reduce estados nuevos, pero convierte un vínculo opcional en bloqueo y empuja a migraciones apresuradas. | Mala UX; fuerza trabajo de migración; import/export legacy queda incómodo; muchas pruebas de bloqueo. | **Rechazada.** |
| 4. Permitir editar legacy y ofrecer link explícito | Conserva compatibilidad y evita backfill. | Añadir sólo `source_id` no mueve `(id, source)`; aun así debe coordinar concepto/LaTeX y compensar el segundo update. | UX clara; selección por `source_id`; sin creación ni migración; backups preservan ambos campos; pruebas acotadas. | **Recomendada.** |
| 5. Sincronizar snapshot automáticamente | Cambia datos históricos durante ediciones no relacionadas. | Puede mover identidad y chocar con conceptos, LaTeX, relaciones y grafos sin intención del usuario; rollback complejo. | UX sorpresiva; parece migración implícita; altera reconciliación import/export; matriz de pruebas muy amplia. | **Rechazada.** |
| 6. Sincronizar sólo mediante acción explícita | Preserva snapshots hasta consentimiento. | Permite preflight y operación coordinada; los conflictos se muestran antes de escribir. | UX explicable con diff y confirmación; sin backfill; import/export se valida por la nueva key; pruebas deterministas. | **Recomendada tras la fase de preservación/link.** |

La combinación recomendada es **1 + 4** inicialmente y **2 + 6** cuando exista la
operación de identidad completa. `source_id` es autoritativo para la asociación
administrada; `source` sigue siendo el snapshot compatible y no cambia por editar
un campo ajeno.

## L. Arquitectura recomendada

### L.1 Separación de comandos

Definir tres comandos de dominio, ninguno con acceso para crear Sources:

1. `update_concept_fields(original_identity, expected_link, changes)`: sólo campos
   no identitarios; preserva `id`, `source` y `source_id` mediante compare-and-set.
2. `link_existing_managed_source(original_identity, expected_source_id,
   target_source_id)`: añade o repara `source_id` en concepto y LaTeX, pero preserva
   `id` y `source`.
3. `relocate_concept_source(original_identity, expected_source_id,
   target_source_id)`: cambia el vínculo y el snapshot, y reescribe de forma
   coordinada todas las referencias exactas a la identidad.

La UI carga Sources con el repositorio de Source Catalog, presenta sólo activas
como nuevos destinos y envía siempre `source_id`. El nombre mostrado nunca se usa
como identificador de selección. Edit Concept no recibe un método `create`,
`insert`, `upsert` o `rename` de Sources.

### L.2 Presentación de estados

| Estado | Guardado normal | Acción disponible |
| --- | --- | --- |
| Vinculado + activo + snapshot actual | Permitido, preservación exacta | Change managed Source |
| Vinculado + activo + snapshot antiguo | Permitido, preservación exacta + warning | Synchronize snapshot / Change managed Source |
| Vinculado + archivado | Permitido, preservación exacta + status | Change to active Source |
| Vinculado + inexistente | Permitido sólo para campos no relacionados + error | Repair link to active Source |
| Legacy | Permitido, sin migración | Link to an existing managed Source |

### L.3 Límites

- Ninguna acción escribe en `sources`.
- Ninguna selección acepta nombres nuevos o fallback por nombre.
- No se ejecuta backfill ni se recorren otros conceptos.
- Un comando sólo modifica el concepto seleccionado y documentos que lo
  referencian exactamente.
- Backups históricos y exports ya generados no se reescriben.
- La identidad de Source Catalog no sustituye todavía el índice histórico.

## M. Diseño de operación atómica

### M.1 Entrada y precondiciones

La operación de relocalización recibe:

- base activa explícita;
- `operation_id` idempotente;
- `_id` del concepto y del LaTeX leídos;
- `old_id`, `old_source` y `expected_source_id` —incluido `null`—;
- `target_source_id`;
- revision, timestamp o hash esperado de ambos documentos;
- actor y motivo de auditoría.

Precondiciones:

1. `old_id` no cambia dentro de esta operación.
2. Existe exactamente un concepto con `_id` y `(old_id, old_source)` esperados.
3. Existe exactamente un LaTeX contraparte. Si falta, se devuelve
   `REPAIR_REQUIRED`; no se crea silenciosamente.
4. Ambos contienen el `source_id` esperado o su ausencia esperada.
5. Ningún dato cambió desde la pantalla de confirmación.
6. La operación no está ya completada ni en recuperación.

### M.2 Source destino y conflictos

Se lee `sources` por `target_source_id`:

- debe existir exactamente una;
- debe tener status activo para un nuevo vínculo o cambio;
- su nombre normalizado y su `source_id` estable determinan el destino;
- nunca se hace upsert, rename, reactivate ni insert.

Antes de escribir se comprueba que `(old_id, target.name)` no exista en
`concepts` ni `latex_documents`, salvo que sea el mismo documento/origen. También
se detectan:

- relaciones que, tras reemplazar un endpoint, colisionarían por
  `(desde, hasta, tipo)`;
- media assets que ya contengan simultáneamente la key vieja y nueva;
- evidence links duplicados o ambiguos;
- nodos/aristas de mapas cuya estructura no pueda parchearse de forma inequívoca;
- mapas con filtros amplios por Source que requieran una decisión semántica.

Ante cualquier conflicto se aborta antes de la primera escritura y se presenta el
inventario al usuario. No se fusionan ni borran datos automáticamente.

### M.3 Plan exacto de actualización

Con `new_key = old_id + "@" + target.name`, el plan contiene:

1. `concepts`: update condicional por `_id`, old pair, expected link y revision;
   `$set {source: target.name, source_id: target.source_id, ...timestamp}`.
2. `latex_documents`: update condicional por `_id`, old pair, expected link y
   revision; `$set {source: target.name, source_id: target.source_id,
   ultima_actualizacion: now}` sin alterar el contenido.
3. `relations`: reemplazar sólo endpoints cuyo valor sea exactamente `old_key`.
4. `media_assets`: reemplazar sólo elementos `concept_ids == old_key`, conservando
   `asset_id`, archivo y demás asociaciones.
5. `concept_evidence_links`: cambiar únicamente `concept_legacy_source` de links
   cuyo par legacy exacto sea el origen. Su `source_id` de evidencia permanece
   intacto.
6. `knowledge_graph_maps`: cambiar nodos y aristas que referencien exactamente la
   key; actualizar listas de keys de sync. Un filtro amplio por Source no se
   reemplaza globalmente: el preflight exige confirmación específica o bloquea.
7. Estado de sesión UI: después del commit, remapear o limpiar keys del concepto,
   media, PDF y Document Builder, y hacer rerun cargando la nueva identidad.

El plan no cambia `references`, otras Sources, otros conceptos, backups ni exports.
Cada patch se construye sobre `_id` concretos inventariados, nunca sobre un regex o
un nombre de Source general.

### M.4 Camino transaccional

Cuando el despliegue soporte transacciones:

1. iniciar sesión y `with_transaction` con read/write concern apropiados;
2. repetir dentro de la transacción las precondiciones y conflictos sensibles;
3. ejecutar updates condicionales en el orden del plan;
4. exigir los `matched_count` y conteos exactos previstos;
5. validar que el par nuevo resuelve concepto y LaTeX y que no queda ninguna
   referencia inventariada con `old_key`;
6. registrar el resultado de auditoría dentro de la misma transacción;
7. confirmar; cualquier excepción aborta todo.

No se usa delete + insert. Actualizar campos sobre documentos identificados por
`_id` conserva metadatos, evita ventanas de desaparición y deja que los índices
únicos protejan el destino.

### M.5 Fallback compensatorio

Como MathV0 no puede asumirse transaccional, el fallback debe ser explícito:

1. guardar en un journal de operación el plan, hashes y snapshots mínimos de todos
   los documentos afectados antes de escribir;
2. adquirir un estado `PREPARED` por `operation_id` único;
3. aplicar cada update con compare-and-set por `_id` más valores esperados;
4. tras cada éxito, registrar el paso y su hash post-update;
5. si falla un paso, compensar en orden inverso usando `_id` y el estado post-update
   exacto como filtro;
6. nunca ejecutar `delete_many`, borrar por un par que podría pertenecer a otro
   documento ni hacer upsert durante compensación;
7. verificar hashes e identidades al terminar.

Resultados estructurados:

- `COMPLETED`: todos los pasos y postcondiciones correctos;
- `NOOP_ALREADY_COMPLETED`: reintento con el mismo `operation_id` y estado final;
- `CONFLICT`: no hubo escrituras;
- `FAILED_COMPENSATED`: hubo pasos, todos restaurados y verificados;
- `PARTIAL_RECOVERY_REQUIRED`: una compensación compare-and-set no coincidió; se
  bloquean reintentos ciegos y se entrega el journal para recuperación manual.

Esto evita borrar datos ajenos: la compensación sólo puede revertir el documento
que todavía conserva exactamente el estado que la propia operación escribió. Si
otra sesión lo cambió, se detiene en lugar de sobrescribirla.

### M.6 Idempotencia, auditoría y UI

El `operation_id` debe asociarse al hash de intención
`old_identity + expected_link + target_source_id`. Un reintento:

- devuelve el resultado almacenado si está completo;
- reanuda o compensa sólo los pasos journalizados si está preparado;
- rechaza reutilizar el ID con otra intención;
- reconoce un estado final completamente aplicado como no-op exitoso.

La auditoría registra actor, database, timestamp, identidad vieja/nueva,
`source_id` viejo/nuevo, conteos por colección, hashes, camino transaction/fallback
y estado final. No registra cuerpos LaTeX ni contenido matemático.

Mensajes de UI mínimos:

- preflight: **This changes the historical concept identity and N dependent
  records. No Source will be created.**;
- conflicto: colección, identidad destino y acción requerida, sin escribir;
- éxito: vieja/nueva identidad y conteos actualizados;
- compensado: aviso de que no quedó cambio persistente;
- recuperación parcial: error bloqueante con `operation_id`, pasos aplicados y
  enlace al procedimiento de recuperación.

## N. Pruebas faltantes

No se escribieron pruebas en esta fase. La implementación futura necesita, como
mínimo:

1. **Editar vinculado sin cambiar Source:** modifica un campo no relacionado y
   verifica ambos documentos.
2. **Conservar `source_id`:** guarda un concepto vinculado y compara exactamente
   el valor antes/después en concepto y LaTeX.
3. **Conservar snapshot:** con `Source.name` renombrado, un guardado ordinario no
   cambia `concept.source` ni `latex.source`.
4. **Legacy sin `source_id`:** abre, edita y guarda sin añadir el campo ni fallar.
5. **Link legacy explícito:** selecciona una Source activa por ID, añade
   `source_id` a ambos documentos y preserva `(id, source)`.
6. **Cambio hacia Source activa:** confirmación explícita, snapshot nuevo y todas
   las dependencias exactas remapeadas.
7. **Source inexistente:** target ID desconocido devuelve conflicto sin escrituras.
8. **Source archivada:** vínculo existente editable; archivada ausente de nuevos
   destinos; cambio nuevo rechazado.
9. **Source renombrada:** resuelve por ID estable y muestra nombre actual más
   snapshot histórico.
10. **Snapshot desactualizado:** warning presente; no sync automático; acción sync
    explícita disponible.
11. **Conflicto de ID en destino:** preflight detecta concepto o LaTeX destino y
    ninguna colección cambia.
12. **Update coordinado:** transacción actualiza `concepts`, `latex_documents`,
    relaciones, media, evidence links y mapas, con conteos exactos.
13. **Fallo del segundo update:** simula fallo de LaTeX después del concepto y
    valida abort transaccional o inicio de compensación.
14. **Rollback/compensación:** revierte en orden inverso por `_id` + estado esperado
    y nunca borra un documento ajeno concurrente.
15. **Reintento idempotente:** mismo `operation_id` devuelve no-op/completa sin
    duplicar updates; intención distinta se rechaza.
16. **Cambio de base:** las opciones y escrituras quedan en la base activa; se
    limpia session state al cambiar de database.
17. **Ninguna escritura en `sources`:** spy/fake falla si recibe insert, update,
    replace, delete o upsert.
18. **Ninguna creación de Source:** texto desconocido no es aceptado y no aparece
    un camino Custom.
19. **Import/export:** linked y legacy round-trip conservan `source_id`; evidencia,
    LaTeX y pair identity validan tras una relocalización.
20. **Selección por `source_id`:** dos nombres similares/renombrados no cambian el
    target; el ID, no la etiqueta, gobierna la acción.

Pruebas adicionales recomendables: media operada antes de guardar, colisión de
relaciones, mapa con filtro amplio, evidence `source_id` preservado, LaTeX ausente,
`matched_count == 0`, concurrencia stale, compensación que encuentra un cambio
ajeno y mensajes de recuperación parcial.

## O. Archivos potencialmente afectados

La futura implementación —no esta auditoría— probablemente afecte:

- `editor/editor_streamlit.py`: UI, estados, selector administrado, confirmación y
  rerun;
- `editor/db/concept_repository.py`: comandos coordinados o fachada al nuevo
  servicio;
- `editor/validators/concept_validator.py`: precondiciones y conflictos de edición;
- `schemas/schemas.py`: contrato explícito de `source_id` en LaTeX y resultados;
- `mathdatabase/mathmongo.py`: operaciones de identidad y consumidores legacy;
- `editor/utils/media_assets.py`: remapeo exacto de `concept_ids`;
- `editor/utils/knowledge_graph_sync.py` y `editor/interactive_graph.py`: rekey de
  nodos/aristas y validación de mapas;
- `editor/concept_linking/concept_search.py` y
  `editor/reading_annotations/concept_picker.py`: resolución posterior al cambio;
- `mathmongo/reading_annotations/models.py`, repository/service y paneles de
  evidencia: actualización de la pareja legacy, no de su Source de evidencia;
- `editor/document_builder.py`: keys de sesión y carga posterior;
- `editor/utils/db_export.py`, `editor/utils/db_import.py` y
  `editor/utils/db_update.py`: portabilidad de linked/legacy y validación de la
  identidad nueva;
- nuevas pruebas funcionales de Edit Concept y ampliaciones a las suites de
  contrato, portabilidad, relaciones, media, grafos y evidencia.

No se recomienda modificar índices en la siguiente implementación inicial. Antes
de tocar cada archivo se debe reducir el alcance al comando correspondiente; esta
lista es un mapa de impacto, no autorización para un cambio masivo.

## P. Validaciones

Validaciones ejecutadas sin Ruff global ni suite completa:

- baseline Git y worktree: correctos;
- inspección MongoDB read-only con hashes antes/después: correcta;
- compilación en memoria de 13 archivos inspeccionados con `python3`: correcta;
- suites enfocadas de contrato, Add Concept, legacy repository, estado UI y
  concept linking: **98 passed**, 5 warnings Pydantic ya existentes;
- corrida ampliada que añadió `tests/test_database_update.py`: **122 passed, 2
  failed**. Ambos fallos ocurren al importar `parsers/yaml_latex_parser.py` porque
  el entorno carece de `rapidfuzz`; no son aserciones de Source ni de Edit Concept
  y no se corrigieron, según el alcance de auditoría;
- no existe una suite funcional actual de Edit Concept que pueda ejecutarse;
- `python` no está seleccionado en pyenv; la compilación se repitió correctamente
  con `python3`;
- revisión pre-commit: `git diff --check` sin errores, estructura A–Q completa y
  diff del único archivo inspeccionado.

No se ejecutó Ruff global ni la suite completa, y no se arreglaron fallos ajenos.

## Q. Estado Git final

En la revisión pre-commit, el único archivo nuevo es
`docs/PHASE_EDIT_CONCEPT_SOURCE_LINK_AUDIT.md` y `git diff --check` no reporta
errores. El cierre exige staging exclusivo de este reporte, validación cached y
worktree limpio después del commit; esas comprobaciones se informan también en la
entrega final. No se hará push.

## Recomendación concreta de implementación por fases

1. **S3-B — Preservación:** convertir Source/ID en contexto no editable durante el
   guardado normal, preservar exactamente `source`/`source_id`, comprobar resultados
   y añadir pruebas funcionales. Legacy continúa editable.
2. **S3-C — Link administrado sin relocalización:** implementar la acción explícita
   para vincular o reparar `source_id` en concepto + LaTeX, seleccionando sólo
   Sources activas existentes y conservando `(id, source)`. Sin creación, migración
   ni backfill.
3. **S3-D — Relocalización atómica:** implementar el servicio inventariado en M,
   primero con transacción y fallback compensatorio probado, incluyendo relaciones,
   media, evidence links y mapas. Mantener el cambio bloqueado si una dependencia
   no puede remapearse sin ambigüedad.
4. **S3-E — Snapshot explícito y portabilidad:** habilitar **Synchronize Source
   snapshot** sobre el mismo servicio, validar import/export/database update y
   liberar el cambio de Source sólo después de superar toda la matriz de pruebas.

Esta secuencia evita una migración implícita de los 186 conceptos legacy, mantiene
Add Source como único creador de Sources y no hace autoritativo `source_id` para
consumidores que todavía dependen de `(id, source)`.

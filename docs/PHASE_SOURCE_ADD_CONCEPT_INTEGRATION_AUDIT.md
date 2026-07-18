# Source Integration Audit

Fecha de auditoría: 2026-07-18
Alcance: auditoría de solo lectura de la integración entre `Add Concept` y
`Edit / Analyze Source` en `MathV0`. No se implementó ninguna corrección ni se
modificaron datos de MongoDB.

## A. Estado Git y entorno

### Repositorio y Git inicial

| Dato | Valor observado |
|---|---|
| `pwd` | `/home/enriquedo/PersonalProjects/math-knowledge-base` |
| raíz real | `/home/enriquedo/PersonalProjects/math-knowledge-base` |
| rama | `main` |
| HEAD | `d4151312219d8fe3da31e716b081bbd7e6093072` |
| upstream | `origin/main` |
| divergencia | 0 behind, 0 ahead |
| `git status --short` | limpio |
| staged | ninguno |
| untracked | ninguno |

Últimos cinco commits al comenzar:

1. `d4151312219d8fe3da31e716b081bbd7e6093072` — 2026-07-18T14:55:26-06:00 — `fix(import): refine safe database update workflow`
2. `c0322239a5d86ac74b5bf40d55418a42b2dd4a31` — 2026-07-18T13:48:33-06:00 — `feat(import): update existing databases safely`
3. `6dd75f59b8512530949d91b7dc470848b41bdc8b` — 2026-07-18T11:46:02-06:00 — `fix(ui): support legacy Streamlit tab signatures`
4. `8c789add046c4a73d1b2abac589e73f8a4a4c6ea` — 2026-07-18T11:16:13-06:00 — `docs: add visual MathMongo reading workflow guide`
5. `0b64ae539ecb0b2009fb5a9be5aa3305146c4f50` — 2026-07-15T20:59:47-06:00 — `feat: simplify MathMongo reading workflow`

No había cambios ajenos que proteger. No se cambió de rama ni se limpió el
worktree.

### Python y dependencias

| Dato | Valor observado |
|---|---|
| `python` del shell | shim `/home/enriquedo/.pyenv/shims/python`, sin versión pyenv activa; invocarlo falla |
| intérprete del proyecto | `/home/enriquedo/PersonalProjects/math-knowledge-base/mathdbmongo/bin/python` |
| Python | 3.10.12 |
| `VIRTUAL_ENV` | no definido en el shell; el proyecto usa explícitamente `mathdbmongo/bin/python` |
| Streamlit | 1.59.2 |
| PyMongo | 4.17.0 |

El repositorio declara Python `>=3.10,<3.14`, Streamlit `^1.35` y PyMongo
`^4.6` en `pyproject.toml:25-30`. El `Makefile` activa `mathdbmongo` para los
comandos históricos y usa directamente ese intérprete para el runtime en
`Makefile:8-10,47-63`.

### Configuración MongoDB efectiva

La resolución de configuración sigue prioridad CLI explícita > entorno >
archivo de usuario > defaults (`mathmongo/config.py:125-190`). En el shell de
auditoría:

- no estaban definidas `MONGODB_URI`, `MONGO_URI`, `MONGODB_DB`, `MONGO_DB` ni
  `DB_NAME`;
- no existe `/home/enriquedo/.config/mathmongo/config.json`;
- URI resuelta, con credenciales ocultas si las hubiera:
  `mongodb://localhost:27017`;
- base resuelta fuera del launcher: `mathmongo`;
- el launcher del repositorio usa `DATABASE ?= MathV0` y exporta
  `MONGODB_DB="$(DATABASE)"` a Streamlit (`Makefile:13,55-61`).

La UI construye una conexión configurada y además una conexión explícita a
`MathV0` (`editor/editor_streamlit.py:1130-1150`). La base seleccionada en la
sesión se conserva en `db_manager`, y tanto `Add Concept` como el catálogo usan
ese mismo objeto `db` (`editor/editor_streamlit.py:1182-1194,1229-1241`). Para
el síntoma reportado y para las consultas de esta auditoría, la base efectiva
es `MathV0`.

## B. Flujo actual de Add Concept

### Trazado UI → modelo → repositorio → MongoDB

1. La página real es la rama `elif page == "➕ Add Concept"` de
   `editor/editor_streamlit.py:1844-1849`; no es una página del paquete nuevo
   `editor/source_catalog`.
2. El selector se renderiza en `editor/editor_streamlit.py:1867-1880`.
   Consulta `db.concepts.distinct("source")`, no `db["sources"]`, filtra sólo
   cadenas no vacías y ante cualquier excepción sustituye silenciosamente la
   lista por `[]`.
3. El `selectbox` y el `text_input` no declaran `key`; por tanto no hay una
   clave de `session_state` explícita y estable definida por la aplicación.
   Streamlit genera su identidad interna a partir del widget. La opción produce
   exactamente la cadena `"(Custom...)"`; al elegirla, `source` recibe
   directamente el valor de `st.text_input("New source name", ...)`.
4. El nombre custom no se normaliza ni se aplica `.strip()`. La única validación
   UI específica es su truthiness junto con ID y contenido LaTeX
   (`editor/editor_streamlit.py:2371-2376`). Después se valida duplicado por
   `(id, source)` y duplicado semántico por `(titulo, tipo, source)` en
   `editor/validators/concept_validator.py:11-53`. No se consulta el catálogo,
   no se exige `source_id`, no se revisan nombres normalizados y no se ejecuta
   el detector de duplicados de Sources.
5. El documento se construye con `"source": source` y sin `source_id` en
   `editor/editor_streamlit.py:2397-2416`. Puede incorporar referencia,
   contexto docente y metadatos técnicos en
   `editor/editor_streamlit.py:2418-2458`.
6. `ConceptoBase` declara sólo `source: str`; no declara `source_id`
   (`schemas/schemas.py:131-159`). Su configuración no usa `extra="forbid"`,
   por lo que añadir ingenuamente un campo extra al constructor no sería una
   forma segura de persistir el vínculo: el modelo debe ampliarse de manera
   explícita.
7. `build_concept_metadata()` serializa el modelo excluyendo
   `contenido_latex` y campos `None` (`editor/helpers/concept_builders.py:4-15`).
8. El único servicio de persistencia llamado es
   `insert_concept_with_latex_atomic(...)` en
   `editor/editor_streamlit.py:2460-2482`. No se construye `Source`, no se llama
   `SourceCatalogService.create_source()` y no se usa `SourceRepository`.
9. El repositorio ejecuta `insert_one` en `concepts` con `id` y `source`, seguido
   de otro `insert_one` en `latex_documents`, también con `id` y `source`
   (`editor/db/concept_repository.py:42-72`). La colección `sources` no aparece
   en este flujo.
10. Si cualquiera de los dos inserts falla, el `except` ejecuta
    `concepts.delete_one({"id": concept_id, "source": source})` y relanza
    (`editor/db/concept_repository.py:73-75`). Es un rollback best-effort, no una
    transacción MongoDB. La UI captura cualquier excepción y muestra
    `Error saving concept: ...` (`editor/editor_streamlit.py:2484-2488`).
11. No hay `st.cache_data`, `st.cache_resource` ni invalidación de caché en este
    flujo. Después de guardar correctamente sólo muestra success y balloons;
    no limpia el formulario, no navega, no llama `st.rerun()` y no refresca un
    catálogo administrado.

Conclusión del trazado: `(Custom...)` significa exclusivamente “usar una nueva
cadena legacy como `concept.source`”. No significa “crear una Source
administrada”. Incluso las opciones “existentes” proceden de los conceptos y
no del catálogo; por ejemplo, una Source administrada sin conceptos no aparece
como opción normal de `Add Concept`.

## C. Flujo actual de Edit / Analyze Source

### Trazado UI → repositorio → MongoDB

1. El router invoca `render_edit_source_page(catalog_context)` en
   `editor/editor_streamlit.py:1317-1334`. El contexto extrae la base PyMongo
   real del mismo objeto seleccionado y crea `SourceRepository(database)` con
   esa base (`editor/source_catalog/shared.py:68-105`).
2. La página real está en
   `editor/source_catalog/edit_source_page.py:1035-1095`. Muestra la base real,
   inspecciona colecciones/índices sin escribir y luego llama
   `_render_source_search()`.
3. `_render_source_search()` está en
   `editor/source_catalog/edit_source_page.py:218-284`. Los filtros default son:
   búsqueda vacía, status `All`, Source type `All`, tag vacío, página 1. Los
   status permitidos por la UI son `All`, `active` y `archived`; los tipos son
   `All` más todos los valores de `SourceType`.
4. Con defaults se llama `SourceRepository.list(page=1, page_size=20,
   status=None, source_type=None, tag=None)`. Por ello la consulta Mongo efectiva
   es `{}`: no excluye archivadas, tipos, tags ni documentos recientes.
5. `SourceRepository` usa exclusivamente la colección `sources` de la base
   recibida (`mathmongo/source_catalog/repository.py:164-200`). El listado hace
   `count_documents(query)` y
   `find(query).sort(...).skip(...).limit(...)` en
   `mathmongo/source_catalog/repository.py:148-161`.
6. El listado normal se ordena por `updated_at DESC, source_id ASC`; la búsqueda
   por `name_normalized ASC, source_id ASC`
   (`mathmongo/source_catalog/repository.py:239-301`). El máximo del repositorio
   es 100 y esta UI fija 20 (`mathmongo/source_catalog/repository.py:29-31,71-76`;
   `editor/source_catalog/edit_source_page.py:246-252`).
7. La búsqueda regex, escapada y case-insensitive, cubre `source_id`, `name`,
   `aliases.value`, `source_type`, `tags` y `status`
   (`mathmongo/source_catalog/repository.py:265-301`). No existe un criterio
   oculto de exclusión.
8. Cada documento se hidrata y valida como `Source`; se elimina sólo `_id` y se
   añaden zonas UTC a datetimes BSON devueltos naive por el cliente
   (`mathmongo/source_catalog/repository.py:112-145`). Un documento incompleto o
   incompatible hace fallar la página completa; no se omite silenciosamente.
   La UI lo convierte en `Database error searching Sources` y no muestra filas
   (`editor/source_catalog/edit_source_page.py:253-261`).
9. Las filas exponen `source_id`, `name`, `source_type` bajo la etiqueta `type`,
   aliases, tags, status y updated_at
   (`editor/source_catalog/edit_source_page.py:178-190`).
10. Los botones se construyen exactamente como
    `Select {source.name} ({source.source_id})`, con key namespaced por
    `source_id`; al pulsar se guarda `SELECTED_SOURCE_ID` y se ejecuta rerun
    (`editor/source_catalog/edit_source_page.py:264-283`).

La tabla no consulta `concepts.source`. El acceso a conceptos legacy sólo ocurre
después de seleccionar una Source, usando coincidencias exactas contra
`Source.name` y `Source.legacy.source_strings`
(`mathmongo/source_catalog/legacy_repository.py:73-76,100-112`).

## D. Colecciones y esquemas reales

### Colecciones

- conceptos legacy: `MathV0.concepts`;
- contenido LaTeX: `MathV0.latex_documents`;
- catálogo administrado: `MathV0.sources`;
- referencias administradas: `MathV0.references`.

`MathMongo` enlaza `concepts` y `latex_documents` al construir la conexión
(`mathdatabase/mathmongo.py:58-69`). El catálogo usa repositorios separados y
explícitamente scoped a la base activa. Ambos sistemas coexisten; no hay una
fachada que integre `Add Concept` con `SourceCatalogService`.

### Contrato real de Source

El modelo administrado es estricto (`extra="forbid"`) y contiene:

```text
schema_version=1
source_id="src_<uuid4>"
name
name_normalized
aliases=[{value, normalized}]
source_type
description
language
tags=[]
status="active" | "archived"
rights_default={copyright_status, redistribution, license, notes}
legacy={source_strings, migration_batch_id}
created_at, updated_at, archived_at
```

Referencias: `mathmongo/source_catalog/models.py:145-180,223-301`. El campo real
es `source_type`, no `type`. El repositorio inserta el modelo completo en
`sources` sin upsert (`mathmongo/source_catalog/repository.py:196-203`). Los
índices aprobados están en `mathmongo/source_catalog/indexes.py:69-106`,
incluyendo unique `source_id`, nombres/aliases normalizados, status+tipo, tags y
updated_at.

La migración legacy creó una Source por cadena exacta, conservó esa cadena como
`name` y en `legacy.source_strings`, y no fusionó variantes normalizadas
(`mathmongo/source_catalog_migration/source_planner.py:23-87`;
`mathmongo/source_catalog_migration/bootstrap.py:170-190`). No añadió
`source_id` a conceptos.

### Comparación de contratos

| Campo | Add Concept | Documento de concepto | Colección `sources` | Edit / Analyze Source | Compatibilidad | Riesgo |
|---|---|---|---|---|---|---|
| `source` | cadena del selector/text input | requerido, snapshot legacy | no es campo raíz | no lo lista; sólo lo resuelve después por mapping legacy | compatible sólo por igualdad exacta | alto: no es identidad estable |
| `source_id` | no existe | modelo y datos actuales no lo contienen | requerido `src_<uuid4>` | identidad de selección y edición | incompatible actualmente | crítico: no hay vínculo autoritativo |
| `name` | no se consulta | no existe | requerido y limpiado | nombre visible | mapeable a `source` por igualdad exacta | alto ante rename/espacios/Unicode |
| `name_normalized` | no se calcula | no existe | derivado | usado para ordenar búsquedas | no integrado | duplicados silenciosos desde Add Concept |
| `source_type` | no existe | no existe | enum, default `other` | filtro y columna `type` | no necesario para concepto, sí para alta administrada | una autocreación debe decidir default explícito |
| `aliases` | no se consulta | no existe | objetos `{value, normalized}` | buscables/visibles | Add Concept no los resuelve | una alias puede crear otra cadena legacy |
| `tags` | no existe | no existe | lista | filtro/búsqueda | independiente | no causa el síntoma con defaults |
| `status` | no existe | no existe | `active`/`archived` | default `All` | independiente | no causa el síntoma actual |
| `legacy.source_strings` | no se consulta | `source` puede coincidir | mapping exacto conservado | une conceptos después de seleccionar | puente parcial | no se actualiza al crear conceptos |
| timestamps | `datetime.now()` en concepto | BSON datetime | UTC-aware en modelo/BSON date | `updated_at` ordena listado | tipos compatibles, semántica distinta | bajo para el síntoma |

Los formatos planteados se resuelven así:

- A (`{"source": "Nombre"}`) es el contrato real de conceptos y de Add
  Concept.
- B (`{"source_id": ..., "source": ...}`) es la dirección compatible
  recomendada, pero no es hoy el contrato de `ConceptoBase` ni aparece en los
  186 conceptos de `MathV0`.
- C es conceptualmente correcto, pero el campo real se llama `source_type`,
  incluye `schema_version`, normalizaciones, rights y legacy, y `aliases` son
  objetos tipados.

## E. Evidencia obtenida de MongoDB

### Método seguro

Se usó PyMongo directamente con `retryWrites=False` y preferencia de lectura
`SecondaryPreferred`. Se evitó instanciar `MathMongo`, porque su constructor
llama `ensure_indexes()` y podría crear índices
(`mathdatabase/mathmongo.py:58-72,93-175`). Las únicas operaciones fueron
`ping`, `list_collection_names`, `count_documents`, `find`, `sort` y
`list_indexes`/inspección de status.

Se tomaron conteos y hashes SHA-256 de proyecciones mínimas de `sources` y
`concepts` antes y después. Coincidieron exactamente:

- `sources`: 17; hash
  `d5721fadd98ab7d46bcf0b07a4f3b432dcf0adc7eb0ebb7c3a2fec51683c83ac`;
- `concepts`: 186; hash
  `28f5bc80b7ee169ccbf2712f76332ae5db8aede678d801b7e835c838c56edc7d`;
- `latex_documents`: 187;
- snapshot inalterado: sí.

### Resultado

1. MongoDB estaba disponible en `mongodb://localhost:27017` y `MathV0` era
   accesible.
2. `sources` contiene exactamente 17 documentos. La llamada real del
   repositorio que usa la UI devolvió `total=17`, página 1 de 1 y las 17 filas.
3. Nombres exactos:
   `ADR`, `APIs-Servicios`, `Bioinformática`,
   `BottcherKarlovich1997`,
   `Digital_Processing_Speech_Signal_Rabiner_1978_PretticeHall`,
   `HID-Pairing-Rec`, `IAIngenieria`,
   `Karlovich2017_Haseman_BVP_SO_Shifts`,
   `Linux-Display-Control-Recipe`,
   `Pommerenke1991BoundaryBehaviourConformalMaps`,
   `Principles_Mathematical_Analysis_Rudin_1964_McGraw-Hill`,
   `ProGit2024`, `Python`,
   `Real_Complex_Analysis_Rudin_1987_McGraw-Hill`,
   `Signals_Systems_Willsky_1996_PrenticeHall`, `SourceTest` y `VoiceTools`.
4. Las 17 están `active`; no hay archivadas. Tipos: 16 `other` y una `corpus`
   (`SourceTest`).
5. No hay Sources sin `source_id` ni sin `name`.
6. No hay `source_id` duplicados, nombres exactos duplicados ni colisiones tras
   normalizar mayúsculas, espacios, puntuación/acentos y Unicode con la función
   real del dominio.
7. Los 17 documentos validan completos como `Source`; no hay esquema
   incompatible. Los 15 índices aprobados de Sources/References están presentes
   y sin conflictos.
8. `created_at` y `updated_at` son BSON datetimes en las 17 Sources; no son
   cadenas. `archived_at` es `null` en las 17. PyMongo los devuelve naive por
   default y el repositorio los hidrata como UTC, comportamiento cubierto por
   `tests/test_source_catalog_repository.py:407-426`.
9. `concepts` contiene 186 documentos y 16 valores distintos de `source`. Los
   186 tienen `source` pero ninguno tiene `source_id`.
10. No hay conceptos con `source_id` inexistente porque no hay ningún concepto
    con `source_id`.
11. No hay valores actuales de `concepts.source` fuera de
    `Source.name`/`legacy.source_strings`: la migración cubre las 16 cadenas
    históricas exactas. Por tanto no se puede identificar, sin inventarlo, el
    nombre custom introducido por el usuario.
12. La Source más reciente es `SourceTest`, creada y actualizada el
    `2026-07-18T23:17:19.586Z`; es válida, activa, aparece primera en la consulta
    de UI y no tiene conceptos legacy asociados. No hay otra Source reciente
    oculta.
13. El concepto más recientemente actualizado en `MathV0` data del
    `2026-07-09T13:41:21.850` y pertenece a
    `BottcherKarlovich1997`. No hay un concepto reciente que corresponda al
    intento reportado. Esto impide afirmar que ese guardado concreto terminó
    correctamente; tampoco prueba un fallo del flujo.
14. La base default `mathmongo` existe pero tiene 0 conceptos, 0 documentos
    LaTeX y ninguna colección `sources`/`references`. No contiene el supuesto
    guardado accidental.
15. Hay un orphan histórico en `latex_documents`:
    `id_examples_001@BottcherKarlovich1997`, fechado 2026-01-22. No hay conceptos
    actuales sin documento LaTeX. Por antigüedad y Source no está relacionado
    con el intento descrito, pero documenta deuda de consistencia preexistente.

Respuesta a “¿el documento creado desde Add Concept quedó únicamente dentro del
concepto?”: el código demuestra que un guardado exitoso dejaría el nombre en
`concepts.source` y `latex_documents.source`, nunca en `sources`. La base actual
no contiene un valor de concepto fuera del catálogo ni un concepto reciente,
por lo que el intento particular no puede localizarse ni confirmarse en los
datos existentes.

## F. Caché y estado de Streamlit

No se encontraron usos de `st.cache_data` ni `st.cache_resource` en el
repositorio. La lista del catálogo se consulta de nuevo en cada ejecución de la
página; no tiene TTL ni función decorada. Por eso una Source válida creada en
`sources` puede aparecer en el siguiente rerun sin invalidación especial.

El estado relevante es:

- `DatabaseManager` vive en `st.session_state` y conserva conexiones/selección
  (`editor/editor_streamlit.py:1082-1150`).
- Cambiar de base actualiza el objeto seleccionado y llama `st.rerun()`
  (`editor/editor_streamlit.py:1182-1194`).
- El catálogo guarda sus widgets bajo `source_catalog_*`; al cambiar identidad
  real de conexión/base elimina sólo ese estado namespaced
  (`editor/source_catalog/state.py:12-20,67-99`).
- Los filtros de Edit Source tienen keys namespaced, incluida la página
  (`editor/source_catalog/edit_source_page.py:218-252`).
- Seleccionar una Source guarda su `source_id` y llama rerun
  (`editor/source_catalog/edit_source_page.py:264-283`).
- Los widgets principales de Source en Add Concept carecen de key explícita y
  no comparten el namespace del catálogo.
- Guardar un concepto no llama rerun ni solicita navegación a Edit Source.

Clasificación de escenarios:

| Escenario | Resultado de auditoría |
|---|---|
| Source no creada | confirmado por diseño para `(Custom...)` |
| Source creada con esquema incorrecto | descartado en los 17 documentos actuales |
| Source creada pero filtrada | descartado: defaults generan `{}` y las 17 son activas/válidas |
| Source creada pero lista en caché | descartado: no hay caché y la consulta directa devuelve 17 |
| Source creada en otra base | descartado para `mathmongo`; ambos flujos usan el mismo `db` seleccionado en cada rerun |
| UI desincronizada | no explica el caso: el catálogo lee en vivo; sólo falta integración semántica |

Existe un riesgo menor de estado de paginación si el usuario queda en una página
que deja de existir tras cambios, porque no hay clamp automático. No aplica al
caso actual: 17 resultados, page size 20, página 1.

## G. Cobertura de pruebas

### Cubierto

- contrato, normalización, IDs, status y timestamps de `Source`:
  `tests/test_source_catalog_models.py`;
- aislamiento entre bases, insert, conflictos, búsqueda escapada, paginación,
  filtros, vínculos legacy e índices explícitos:
  `tests/test_source_catalog_repository.py:184-265,357-383,407-426`;
- servicio de creación/edición y protección contra duplicados:
  `tests/test_source_catalog_service.py`;
- formulario y flujo **Add Source**, incluido alta sin Reference y resultado
  parcial seguro:
  `tests/test_source_catalog_add_ui.py:106-179,234-245` y
  `tests/test_source_catalog_ui_workflows.py:53-150`;
- listado de Edit Source con filtros, paginación server-side y Sources
  archivadas visibles:
  `tests/test_source_catalog_edit_analysis.py:295-329`;
- limpieza de estado por cambio de base y navegación por `source_id`:
  `tests/test_source_catalog_ui_state.py:186-259`;
- compatibilidad legacy, migración, bootstrap, import/export y seguridad del
  catálogo en las familias `tests/test_source_catalog_*`.

### No cubierto

No hay pruebas funcionales de la rama legacy `Add Concept` que ejerciten:

- el selector `(Custom...)`;
- `New source name`;
- el documento exacto enviado a `insert_concept_with_latex_atomic`;
- la ausencia/presencia de alta en `sources`;
- persistencia de `source_id` en conceptos;
- integración Add Concept → Edit / Analyze Source;
- aparición de una Source administrada sin conceptos en el selector de Add
  Concept;
- limpieza de formulario, rerun o mensajes después de guardar;
- fallos parciales reales entre `concepts` y `latex_documents`.

No existe una prueba que demuestre que `(Custom...)` crea una Source
administrada, porque el código no lo hace. Tampoco existe una prueba que
demuestre que una nueva cadena de Add Concept aparece en Edit / Analyze Source.

Pruebas mínimas faltantes:

1. prueba pura del resolver selección administrada/custom;
2. prueba de contrato de concepto dual `source_id` + `source` snapshot;
3. prueba de nombre normalizado/alias/duplicado antes de crear una Source;
4. prueba de éxito integrada en base fake/temporal: Source creada, concepto
   vinculado, lista actualizada;
5. pruebas de resultados parciales Source-creada/concepto-fallido y viceversa,
   sin rollback destructivo;
6. prueba de compatibilidad con concepto legacy sin `source_id`;
7. round-trip de import/export con conceptos legacy y vinculados;
8. prueba Streamlit de cambio de base y navegación posterior al alta.

## H. Causa raíz

**Categoría A. Add Concept guarda únicamente texto legacy.**

La causa demostrada no es caché ni filtrado: hay dos subsistemas separados.
`Add Concept` usa `concepts.distinct("source")`, construye un `ConceptoBase` con
`source` textual y sólo inserta en `concepts`/`latex_documents`. `Edit / Analyze
Source` consulta exclusivamente `sources` y exige documentos `Source` tipados
con `source_id`. Ninguna llamada conecta ambos flujos.

La evidencia MongoDB es coherente con ese contrato: 186/186 conceptos tienen
`source` sin `source_id`; las 17 Sources son válidas, visibles y no filtradas;
la llamada real de UI devuelve las 17; `mathmongo` está vacío. La ausencia de un
valor unmatched y de un concepto reciente significa que no se puede atribuir
un documento al intento concreto ni clasificarlo como “Add Concept intenta
crear Source y falla”. No hay tal intento en el código.

### Reproducción mínima sin escribir datos

Reproducción observacional con el estado existente:

1. Estado inicial: `MathV0.sources=17`, `MathV0.concepts=186`; la UI de Edit
   Source lista 17/17.
2. En Add Concept, el selector se llena desde los 16 valores distintos de
   `concepts.source`, no desde las 17 Sources. `SourceTest`, que no tiene
   conceptos, no puede entrar por la lista de existentes y requiere Custom.
3. Cualquier concepto existente muestra el resultado real del contrato: su
   documento contiene `source` y carece de `source_id`.
4. `sources` permanece como colección independiente; las asociaciones de esos
   186 conceptos sólo se infieren por igualdad exacta con el mapping legacy.
5. Edit Source sigue mostrando exclusivamente los 17 documentos administrados.
6. El contrato se rompe exactamente entre
   `editor/editor_streamlit.py:2409,2473-2482` y
   `mathmongo/source_catalog/repository.py:164-200`: el primero nunca invoca el
   segundo.

No se ejecutó la acción de guardar porque habría insertado datos reales. Para
una futura reproducción ejecutable hace falta una base MongoDB temporal con
índices de catálogo, un nombre fixture único y un concepto fixture mínimo. La
aserción del comportamiento actual debe comprobar que `concepts` y
`latex_documents` aumentan, mientras `sources` no cambia y Edit Source no puede
listar ese nombre. Después, la prueba de la corrección deberá exigir creación o
selección explícita de Source, `source_id` persistido y `source` snapshot.

## I. Riesgos de compatibilidad

1. Los 186 conceptos actuales carecen de `source_id`; hacer obligatorio el
   campo rompería lectura/importación legacy.
2. La identidad histórica y varios índices/repositorios usan `(id, source)`.
   Sustituir abruptamente `source` por ID rompería edición, LaTeX, relaciones y
   exportadores.
3. Renombrar una Source administrada no debe reescribir silenciosamente el
   snapshot histórico; `source_id` debe ser autoritativo y `source` legible.
4. Resolver por nombre debe considerar `name_normalized`, aliases y
   `legacy.source_strings`, pero nunca fusionar automáticamente candidatos
   fuertes/posibles sin decisión humana.
5. Una autocreación con defaults implícitos puede producir `source_type=other`,
   rights desconocidos y duplicados que luego exigen curación.
6. La creación cruza al menos `sources`, `concepts` y `latex_documents`; un
   rollback que borre por una clave no poseída puede eliminar datos de una
   carrera. Los resultados parciales deben ser explícitos y recuperables.
7. `ConceptoBase` debe ampliarse explícitamente; confiar en un campo extra
   `source_id` puede descartarlo durante `model_dump`.
8. Export/import ya incluyen el catálogo opcional cuando existe
   (`editor/utils/db_export.py:672-749`) y validan Sources con Pydantic
   (`editor/utils/db_import.py:1463-1488`), pero el contrato de concepto sigue
   siendo `(id, source)` (`editor/utils/db_export.py:486-495`). Un cambio dual
   exige round-trip y validación de referencias sin invalidar archivos antiguos.
9. El orphan LaTeX histórico confirma que las invariantes entre colecciones no
   deben suponerse perfectas durante un backfill.

## J. Alternativas de corrección

| Opción | Ventajas | Desventajas | Compatibilidad | Duplicados | Conceptos existentes | Import/export | Complejidad de pruebas | Recomendación |
|---|---|---|---|---|---|---|---|---|
| 1. Mantener Custom como texto legacy y aclararlo | cambio mínimo; no altera datos ni servicios | mantiene dos catálogos desconectados y no ofrece identidad estable | máxima con comportamiento actual | alta; sólo ayuda de texto | sin impacto | sin cambio | baja | sólo mitigación temporal y honesta |
| 2. Custom crea automáticamente una Source | flujo rápido y la tabla puede verla | efecto lateral implícito; hay que decidir tipo/rights, resolver carreras y resultados parciales | buena si se conserva `source`; mala si se reemplaza | media/alta sin duplicate gate explícito | no los migra | añade Sources a exports; debe validar conceptos duales | alta | no preferida como acción implícita |
| 3. Eliminar creación textual y obligar Add Source | contrato claro; reutiliza flujo robusto y duplicate preview | más navegación y fricción; el usuario puede perder el borrador | alta si conceptos legacy siguen legibles | baja | sin impacto inmediato | catálogo ya soportado | media | alternativa segura de transición |
| 4. Flujo explícito `Create managed Source` dentro de Add Concept, guardar `source_id` y conservar `source` snapshot | intención visible, identidad estable, compatibilidad legacy y retorno al formulario | mayor trabajo de UI/orquestación y manejo parcial | máxima con modelo dual opcional | baja si reutiliza normalización y confirmación | se conservan; backfill separado y opcional | requiere round-trip dual y soporte de archivos antiguos | alta, pero verificable | **recomendada** |

La opción 4 evita que el texto custom parezca una Source sin serlo y permite
mantener dos acciones distintas: seleccionar una Source existente o crear una
administrada con confirmación. Durante transición, `source_id` debe ser opcional
en lectura, obligatorio para conceptos nuevos vinculados, y `source` debe
conservarse como snapshot legible y como compatibilidad con los consumidores
actuales.

## K. Plan recomendado por fases

1. **Contrato y pruebas puras.** Aprobar el modelo dual
   `source_id: str | None` + `source: str`, reglas de snapshot y resolución de
   nombres. Añadir tests antes de escrituras.
2. **Resolver/seleccionar sin mutar.** Hacer que Add Concept lea Sources activas
   o todas según decisión UX, por `source_id`, con búsqueda y duplicate preview;
   mantener una opción legacy claramente etiquetada si todavía se necesita.
3. **Creación explícita administrada.** Reutilizar `Source`,
   `SourceCatalogService` y su gate de duplicados dentro de un subflujo
   `Create managed Source`, con base real visible y confirmación.
4. **Persistencia dual del concepto.** Extender `ConceptoBase` y repositorio para
   guardar `source_id` autoritativo más `source` snapshot. Conservar unicidad
   legacy hasta diseñar una migración de índices compatible.
5. **Resultados parciales y refresco.** Definir estados Source creada/concepto
   fallido, concepto guardado/LaTeX fallido y reintento idempotente; nunca borrar
   una Source válida como rollback automático. Tras éxito, limpiar sólo el
   estado del formulario, rerun y ofrecer abrir la Source.
6. **Portabilidad.** Actualizar validaciones de export/import/update para aceptar
   ambos formatos, rechazar `source_id` colgantes en documentos nuevos y seguir
   importando archivos legacy sin el campo.
7. **Backfill separado.** Auditar y proponer una migración reversible para los
   186 conceptos sólo después de aprobar mapping exacto. No mezclarla con el
   cambio UI ni ejecutarla sobre `MathV0` sin autorización específica, backup y
   dry-run.

## L. Archivos que probablemente tendrían que cambiar

No se modificó ninguno en esta fase. Candidatos para una implementación futura:

- `editor/editor_streamlit.py` — selector, subflujo explícito, mensajes y rerun;
- `schemas/schemas.py` — `source_id` opcional y contrato dual del concepto;
- `editor/db/concept_repository.py` — invariantes y resultados parciales;
- `editor/helpers/concept_builders.py` — serialización del vínculo;
- `editor/source_catalog/shared.py` y/o un nuevo helper pequeño — contexto de
  catálogo reutilizable sin duplicar lógica;
- `editor/source_catalog/source_form.py`, `workflows.py` o
  `add_source_page.py` — reutilización controlada de creación/duplicate gate;
- `mathmongo/source_catalog/repository.py` y/o `service.py` — sólo si se necesita
  una resolución exacta por nombre/alias que hoy no existe como operación
  pública específica;
- `editor/utils/db_export.py`, `db_import.py` y `db_update.py` — portabilidad e
  integridad del vínculo dual;
- nuevos tests de Add Concept y ajustes puntuales en las familias
  `tests/test_source_catalog_*`.

No se recomienda introducir una migración en esos mismos cambios.

## M. Pruebas que deberían añadirse

1. `Custom legacy text` claramente no crea Source cuando esa modalidad esté
   permitida.
2. `Create managed Source` crea exactamente un documento Source válido y
   persiste su ID en el concepto.
3. Seleccionar Source existente conserva ID y snapshot de nombre.
4. Exact/strong/possible duplicates exigen las mismas decisiones que Add Source.
5. Alias, espacios, case y Unicode no crean duplicados silenciosos.
6. Source archivada: política explícita para selección/reactivación.
7. Fallo de creación de Source no inserta concepto.
8. Source creada y concepto fallido produce resultado parcial recuperable, sin
   delete automático de Source.
9. Fallo de LaTeX conserva las invariantes acordadas sin borrar datos ajenos.
10. Al éxito, rerun/listado muestra la Source y preserva la base activa.
11. Cambio de base borra selección de Source y nunca reutiliza un ID de otra
    base.
12. Conceptos legacy sin `source_id` siguen abriendo, editando y exportando.
13. Import/export/update round-trip de conceptos legacy y duales.
14. Backfill fixture exacto, ambiguo y colgante; siempre dry-run primero.

## N. Validaciones ejecutadas

| Validación | Resultado |
|---|---|
| disponibilidad MongoDB | PASS (`ping`) |
| inspección de 17 Sources con modelo real | PASS; 17 válidas |
| consulta real `SourceRepository.list(page=1,page_size=20)` | PASS; total 17, pages 1 |
| snapshot antes/después de lectura | PASS; conteos y hashes idénticos |
| compilación Python sin escritura | PASS; 293 archivos compilados en memoria |
| pytest enfocado en Source Catalog | PASS; 390 passed, 50 skipped en 2.88 s |
| pytest completo | FAIL baseline; 1322 passed, 51 skipped, 4 failed en 66.50 s |
| Ruff global sin `--fix` | FAIL baseline; 2222 incidencias, 398 auto-fixables |
| `git diff --check` antes y después del reporte | PASS |
| conteos MongoDB al cierre | sin cambio: Sources 17, concepts 186, latex_documents 187 |

No se ejecutó `python -m compileall` porque escribiría `__pycache__`/`.pyc` en
contra de la restricción de crear únicamente este reporte. Se usó `compile()` en
memoria sobre todos los `.py` del repositorio, sin escribir bytecode.

No se ejecutó `make lint` porque el target aplica `ruff check . --fix`
(`Makefile:70-71`) y modificaría código. Se ejecutó el equivalente no mutante
`mathdbmongo/bin/ruff check .`.

Los cuatro fallos de suite completa son preexistentes y no relacionados con
Sources:

- tres casos de `tests/test_xdg_media_paths.py:238-350` parchean
  `db_export.datetime` con `_FixedExportDatetime`, pero
  `editor/utils/db_export.py:647` ahora llama `datetime.now(timezone.utc)` y el
  fake no define `now`;
- `tests/test_xdg_mutable_guards.py:83-102` busca literalmente
  `runtime_root = validate_mutable_path(get_runtime_dir())`, texto ausente en la
  implementación actual.

Los skips incluyen E2E Mongo protegido por variable de entorno y fixtures
autoritativos opcionales. No se activó `MATHMONGO_RUN_MONGO_E2E`; ninguna prueba
escribió en MongoDB real. No hay workflow de CI bajo `.github` en este checkout.

## O. Estado Git final

La verificación final observó rama `main`, el mismo HEAD, divergencia 0/0,
ningún archivo staged y exactamente este reporte nuevo como untracked:

```text
?? docs/PHASE_SOURCE_ADD_CONCEPT_INTEGRATION_AUDIT.md
```

No se modificaron archivos de código, tests, configuración ni datos. No se hizo
commit ni push.

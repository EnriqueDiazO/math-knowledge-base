# Managed Source Workflow Version Closure

## A. Versión

- Versión del proyecto: `0.13.0`.
- Fuente canónica: `version` en `[tool.poetry]` de `pyproject.toml`.
- Tag anotado de cierre: `v0.13.0-managed-source-workflow`.
- Recomendación autoritativa: **B. LISTO CON LIMITACIONES DOCUMENTADAS**.

`mathmongo.__version__` y `mathmongo --version` consumen la metadata instalada y
usan la versión de Poetry como fallback en un checkout. La instalación editable
se refrescó sin dependencias y ambas rutas reportaron `0.13.0`; no se añadió una
segunda fuente de versión.

## B. Alcance

Esta versión cierra el workflow que parte de una Source administrada y llega a
la creación, promoción, edición y vinculación explícita de conceptos. Incluye
protección de delete, soporte de base nueva y aislamiento de UI entre bases.

El cierre sólo modifica metadata de versión y documentación. No añade funciones,
no corrige deuda media/baja y no modifica import, export, update, esquemas,
índices, servicios, UI o tests.

## C. Commits incluidos

### 1. Auditoría inicial

- **Commit:** `19c86838`.
- **Objetivo:** auditar la integración de Sources en Add Concept antes de
  modificar el contrato.
- **Archivos principales:**
  `docs/PHASE_SOURCE_ADD_CONCEPT_INTEGRATION_AUDIT.md`.
- **Pruebas añadidas:** ninguna; fue una fase documental.
- **Invariantes:** lectura/auditoría sin writes ni cambio de identidad.
- **Limitaciones:** Add Concept aún aceptaba el origen legacy y no persistía el
  vínculo administrado.

### 2. Contrato dual `source` + `source_id`

- **Commit:** `83f8fb51`.
- **Objetivo:** permitir `source_id` opcional sin sustituir el `source` legacy.
- **Archivos principales:** `schemas/schemas.py`,
  `editor/db/concept_repository.py` y
  `docs/PHASE_SOURCE_LINK_CONTRACT.md`.
- **Pruebas añadidas:** `tests/test_concept_source_link_contract.py`.
- **Invariantes:** persistencia simétrica en `concepts` y `latex_documents`;
  consultas, rollback e identidad continúan basados en `(id, source)`.
- **Limitaciones:** sin migración, backfill o administración del vínculo en UI.

### 3. Add Concept

- **Commit:** `6a2136af`.
- **Objetivo:** seleccionar una Source activa existente por `source_id` y guardar
  su nombre como snapshot.
- **Archivos principales:** `editor/editor_streamlit.py`,
  `editor/helpers/managed_source_selection.py` y
  `docs/PHASE_ADD_CONCEPT_MANAGED_SOURCE_SELECTION.md`.
- **Pruebas añadidas:**
  `tests/test_add_concept_managed_source_selection.py`.
- **Invariantes:** Add Source sigue siendo el creador; no hay texto libre,
  inferencia por nombre ni writes a `sources` desde Add Concept.
- **Limitaciones:** los conceptos legacy permanecen sin migrar y Edit Concept se
  abordó por separado.

### 4. Edit Concept preservation

- **Commits:** `b6ba6733`, `1b8df663`.
- **Objetivo:** auditar Edit Concept y preservar identidad y campos no editables
  durante updates ordinarios.
- **Archivos principales:**
  `docs/PHASE_EDIT_CONCEPT_SOURCE_LINK_AUDIT.md`,
  `editor/db/concept_edit_service.py`, `editor/editor_streamlit.py` y
  `docs/PHASE_EDIT_CONCEPT_IDENTITY_PRESERVATION.md`.
- **Pruebas añadidas:**
  `tests/test_edit_concept_identity_preservation.py`.
- **Invariantes:** `id`, `source`, presencia/valor de `source_id`, `_id` e
  identidad `id@source` permanecen estables; no se rekeyean dependencias.
- **Limitaciones:** edición ordinaria no es Change Source ni reparación de link.

### 5. Fresh database lifecycle

- **Commit:** `810fbec2`.
- **Objetivo:** validar el contrato moderno y legacy en una base temporal nueva,
  incluida edición y portabilidad.
- **Archivos principales:**
  `tests/test_fresh_database_lifecycle_e2e.py`,
  `docs/PHASE_FRESH_DATABASE_LIFECYCLE_E2E.md`,
  `editor/db/concept_edit_service.py` y `mathdatabase/mathmongo.py`.
- **Pruebas añadidas:** E2E fresh database opt-in y casos adicionales de edición.
- **Invariantes:** base temporal única, cleanup en `finally`, ninguna dependencia
  de una base de usuario y compatibilidad `id@source`.
- **Limitaciones:** la prueba requiere opt-in MongoDB y permanece skipped en la
  suite ordinaria.

### 6. Legacy linking

- **Commits:** `c2c3ef75`, `90f58cc0`.
- **Objetivo:** vincular explícitamente un concepto legacy a una Source activa
  existente desde una acción separada de Edit Concept.
- **Archivos principales:** `editor/db/concept_source_link_service.py`,
  `editor/editor_streamlit.py` y
  `docs/PHASE_LINK_LEGACY_CONCEPT_TO_MANAGED_SOURCE.md`.
- **Pruebas añadidas:** `tests/test_legacy_concept_source_link_service.py`,
  `tests/test_edit_concept_legacy_source_link_ui.py` y
  `tests/test_legacy_concept_source_link_e2e.py`.
- **Invariantes:** sólo se añade `source_id` al par exacto de concepto/LaTeX;
  `id`, `source`, `_id`, contenido y dependencias no cambian.
- **Limitaciones:** sin Change Source, Repair Link, Synchronize Snapshot, unlink,
  `concept_uid`, migración o backfill.

### 7. Auditoría integral

- **Commit:** `434aa015`.
- **Objetivo:** auditar compatibilidad transversal del workflow y clasificar
  riesgos antes de estabilizarlo.
- **Archivos principales:**
  `docs/PHASE_MANAGED_SOURCE_WORKFLOW_COMPATIBILITY_AUDIT.md`.
- **Pruebas añadidas:** ninguna; consolidó evidencia existente y detectó H-01 a
  H-05.
- **Invariantes:** no hubo writes, migraciones ni cambios funcionales.
- **Limitaciones:** quedaron cinco hallazgos altos que exigían corrección antes
  del cierre.

### 8. Fixes H-01 a H-05

- **Commits:** `69980467` (Cuaderno), `8ebf8fa4` (Source delete), `79b515b1`
  (startup), `fd3eda8a` (Document Builder), `1a8250da` (Knowledge Graph/Maps) y
  `9e6ce098` (registro documental).
- **Objetivo:** exigir Source administrada al promover; bloquear delete con
  links modernos; evitar inicialización implícita; aislar Builder y Graph/Maps
  por conexión + base.
- **Archivos principales:** `editor/cuaderno_page.py`,
  `mathmongo/source_catalog/repository.py`,
  `editor/database_connections.py`, `editor/database_scope.py`,
  `editor/document_builder.py`, `editor/editor_streamlit.py` y el documento de
  fixes.
- **Pruebas añadidas:**
  `tests/test_cuaderno_managed_source_promotion.py`, casos de delete en
  `tests/test_source_catalog_repository.py` y
  `tests/test_source_catalog_service.py`,
  `tests/test_database_connection_bootstrap.py`,
  `tests/test_document_builder_database_scope.py` y
  `tests/test_knowledge_graph_database_scope.py`.
- **Invariantes:** Add Source sigue siendo el único creador; `id@source` no se
  modifica; un switch de base no escribe ni reutiliza estado previo.
- **Limitaciones:** delete físico conserva una ventana concurrente estricta;
  aislamiento browser E2E multibase queda pendiente.

### 9. Reauditoría

- **Commit:** `2787f9e3`.
- **Objetivo:** verificar H-01…H-05, los contratos transversales, el baseline y
  las limitaciones residuales.
- **Archivos principales:**
  `docs/PHASE_MANAGED_SOURCE_WORKFLOW_COMPATIBILITY_REAUDIT.md`.
- **Pruebas añadidas:** ninguna; volvió a ejecutar selección enfocada y una
  regresión completa.
- **Invariantes:** MongoDB inmutable, cero hallazgos críticos/altos y baseline
  sin regresiones nuevas.
- **Limitaciones:** M-01, M-02, M-03, M-04, L-01, XDG, warnings y ventana de
  delete se aceptaron documentalmente.

## D. Contratos cerrados

1. Add Source es el único creador interactivo de Sources.
2. Add Concept y Cuaderno Promote seleccionan Sources administradas activas.
3. Los conceptos modernos guardan `source` + `source_id`; los legacy continúan
   válidos sin migración.
4. Edit Concept preserva `id`, `source` y `source_id`.
5. Legacy Link sólo añade `source_id` y no cambia `id@source`.
6. Source Delete bloquea References y vínculos modernos visibles, sin cascade.
7. Startup no inicializa una base adicional implícitamente.
8. Document Builder y Knowledge Graph/Maps aíslan estado por conexión + base.
9. Export/import/update conservan la forma moderna o legacy sin inferir Sources.
10. Change Source no es requisito para este contrato y no fue implementado.

## E. Validaciones enfocadas

La selección incluyó metadata/CLI, Add Source, Add Concept, Cuaderno Promote,
Edit preservation, legacy link, Source delete, startup, scopes, Document Builder,
Knowledge Graph/Maps, config y launchers. También incluyó ambos E2E con sus
variables expresamente ausentes.

```text
243 passed, 2 skipped, 6 warnings in 1.45s
```

Los dos skips corresponden exactamente a fresh database E2E y legacy link E2E.
`mathmongo.__version__` y `mathmongo --version` reportaron `0.13.0` después de
refrescar la instalación editable. `git diff --check` fue limpio.

No se modificó Python, por lo que no correspondían compilación en memoria ni
Ruff.

## F. Regresión final

Se ejecutó exactamente una regresión completa durante el cierre:

```text
PYTHONDONTWRITEBYTECODE=1 mathdbmongo/bin/python -m pytest \
  -p no:cacheprovider -q
```

Resultado:

```text
4 failed, 1432 passed, 53 skipped, 7 warnings in 65.53s
```

Coincide exactamente con el baseline autorizado. Los tres fallos de
`tests/test_xdg_media_paths.py` y el fallo de
`tests/test_xdg_mutable_guards.py` son los cuatro XDG conocidos; no hubo fallos
nuevos ni cambio de naturaleza.

## G. E2E existentes

- `tests/test_fresh_database_lifecycle_e2e.py` cubre una base temporal vacía,
  Source, concepto moderno, Edit, export/import, legacy y cleanup.
- `tests/test_legacy_concept_source_link_e2e.py` cubre creación aislada de
  Source, par legacy, vínculo, idempotencia, dependencias y cleanup.

Ambos E2E tienen evidencia previa habilitada en sus fases originales. Durante
este cierre no se habilitaron: quedaron skipped y no ejecutaron writes MongoDB.

## H. Reauditoría

La reauditoría `2787f9e3` confirmó que H-01, H-02, H-03, H-04 y H-05 están
corregidos; que los contratos modernos y legacy permanecen compatibles; y que
la regresión coincide con el baseline. Su decisión autoritativa es:

**B. LISTO CON LIMITACIONES DOCUMENTADAS**

## I. Hallazgos críticos y altos

- Hallazgos críticos: **0**.
- Hallazgos altos: **0**.
- H-01 a H-05: **CORREGIDOS**.

Los fallos XDG existentes no pertenecen a este workflow y no se corrigieron en
esta fase.

## J. Limitaciones aceptadas

- **M-01:** Delete Concept es secuencial y no cubre integralmente dependencias.
- **M-02:** Browse/Quarto puede colapsar el mismo `id` entre Sources.
- **M-03:** portabilidad conserva, pero no diagnostica todos los links
  administrados colgantes o inconsistentes.
- **M-04:** queda pendiente cobertura browser E2E multibase.
- **L-01:** `DocumentoLatex` no modela `source_id` explícitamente.
- El physical Source delete tiene una ventana concurrente estricta entre el
  último blocker check y el delete.
- Permanecen cuatro fallos XDG baseline y siete warnings conocidos.
- No se implementaron Change Source, Repair Link, Synchronize Snapshot, unlink
  ni `concept_uid`.

Estas limitaciones no se reinterpretan como corregidas y no bloquean la
recomendación B bajo los workarounds documentados.

## K. Archivos de usuario

- `docs/MANAGED_SOURCE_WORKFLOW.md`: guía práctica para instalaciones nuevas y
  bases legacy.
- `docs/RELEASE_NOTES_v0.13.0_MANAGED_SOURCE_WORKFLOW.md`: cambios, pruebas,
  limitaciones, upgrade y trazabilidad Git.
- `README.md`: enlaces mínimos a ambos documentos.
- `CHANGELOG.md`: entrada breve `0.13.0` en el formato existente.

## L. Upgrade Notes

No existe migración automática ni backfill. Las bases legacy siguen siendo
válidas y no es obligatorio vincular todos sus conceptos. Para conceptos nuevos,
Add Concept y Cuaderno Promote requieren una Source administrada activa.

Antes de actualizar u operar sobre catálogo/contenido se recomienda un backup
verificable, confirmar la base activa y preferir archive-first antes del delete
físico de una Source.

## M. Git y tag

El cierre se realiza en `main` mediante un único commit documental/metadata con
mensaje:

```text
docs(release): close managed source workflow version
```

El tag anotado `v0.13.0-managed-source-workflow` apunta a ese commit con mensaje
`v0.13.0: managed source workflow`. Commit y tag son locales; el push queda
pendiente de revisión manual.

## N. Datos y seguridad

No se modificó MongoDB real. La comprobación ligera usó `MongoClient` directo,
`retryWrites=False` y preferencia de lectura secundaria; no instanció
`MathMongo`. El `ping` fue correcto y la base configurada fue `mathmongo`.

La lista de bases tuvo 8 entradas antes y después y permaneció idéntica. El
monitor observó sólo `ping`, `listDatabases` y `endSessions`, con cero comandos
de escritura. Los opt-ins fresh database, legacy link y Mongo E2E estaban
deshabilitados.

No se creó ninguna Source, no se modificaron conceptos existentes, no se ejecutó
migración o backfill y no se cambiaron índices. La instalación editable local se
refrescó únicamente para leer la nueva metadata; no cambió datos ni archivos
rastreados adicionales.

## O. Trabajo futuro

Una fase posterior e independiente puede abordar M-01, identidad compuesta en
Browse/Quarto, diagnósticos de portabilidad, browser E2E multibase, el modelo
`DocumentoLatex`, la garantía concurrente del delete y los fallos XDG.

Change Source, Repair Link, Synchronize Snapshot, unlink y `concept_uid`
requieren contratos y auditorías propios. Ninguno se anticipó en este cierre.

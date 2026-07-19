# Link Legacy Concept to Managed Source

## Objetivo

Permitir que una persona vincule explícitamente un concepto legacy con una
Source administrada existente desde Edit Concept. La operación sólo añade el
mismo `source_id` a `concepts` y `latex_documents`.

## Arquitectura

Add Source crea Sources. Edit Concept sólo vincula una Source existente. La UI
selecciona por `source_id`, rehidrata la Source activa en la base actual y llama
al servicio de dominio. El servicio es la única frontera de escritura del link.

## Concepto legacy

Un concepto legacy conserva `id` y el snapshot histórico obligatorio `source`,
pero el campo `source_id` está ausente tanto en `concepts` como en
`latex_documents`. La ausencia es distinta de un campo presente con `null`.

## Concepto vinculado

Un concepto vinculado conserva su identidad histórica y tiene el mismo
`source_id` en ambos documentos. Repetir la operación con el mismo destino es
un no-op verificado (`already_linked`). Cambiar, reparar o eliminar ese vínculo
no forma parte de esta fase.

## Identidad preservada

Sólo se añadió `source_id`. No cambió `id`, no cambió `source` y no cambió la
clave `id@source`. Tampoco cambiaron `_id`, el contenido LaTeX ni el resto de los
campos de los dos documentos.

## Snapshot histórico

`source` sigue siendo un snapshot histórico inmutable. La Source administrada
puede tener otro `name`; el servicio nunca compara, infiere ni copia nombres.
Una diferencia de nombres se presenta en la UI antes de confirmar el vínculo.

## Servicio de vinculación

`link_concept_to_existing_managed_source` recibe la base explícita, `(id,
source)`, el estado esperado y `target_source_id`. Busca la Source únicamente
por ID, exige estado `active`, carga exactamente el concepto y su LaTeX, y usa
compare-and-set con `upsert=False`. No elimina ni recrea documentos y nunca
escribe en `sources`.

Los resultados estructurados distinguen éxito, idempotencia, destino ausente o
inactivo, documentos ausentes, estado stale, discrepancia, conflicto con otro
vínculo, fallo compensado y recuperación parcial requerida.

## Transacción y compensación

Cuando el backend declara soporte, las dos escrituras se ejecutan en una
transacción. En fallback, el servicio verifica cada estado final. Si falla la
segunda escritura, compensa únicamente con `$unset: {"source_id": ""}` sobre
el concepto que todavía coincide exactamente con el estado escrito por la
operación. Una interferencia concurrente produce
`partial_recovery_required`; nunca se presenta como éxito ambiguo.

## UI explícita

Edit Concept muestra **Link to an existing managed Source** sólo si `source_id`
está ausente. El selector contiene IDs de Sources activas de la base actual,
usa nombres sólo como etiquetas y no acepta texto libre. Antes de habilitar el
botón separado exige confirmar el snapshot, la Source seleccionada, el ID de
destino y que el concepto no se moverá. Inmediatamente antes de vincular se
rehidrata la Source por ID.

El botón ordinario **Update Concept** sigue llamando únicamente a su servicio de
edición y no ejecuta la vinculación.

## Comportamiento sin Sources

Si no existen Sources activas, la UI indica que primero debe crearse una desde
Add Source y mantiene bloqueada la acción. Un error de catálogo se presenta con
un mensaje seguro y también bloquea el vínculo.

## Manejo de errores

Cada estado del servicio tiene un mensaje específico. Sólo `success` y
`already_linked` limpian el estado namespaced de los widgets y hacen un rerun.
Los destinos ausentes/inactivos, documentos ausentes, estados inconsistentes,
conflictos y fallos compensatorios no muestran confirmación de éxito.

## Protección de Knowledge Maps y dependencias

La identidad `(id, source)` permanece igual, por lo que los Knowledge Maps no
se rekeyean. La operación no lee ni escribe `relations`,
`knowledge_graph_maps`, `media_assets` ni `concept_evidence_links`. No se
modificaron grafos, relaciones, media, evidence links, import, export ni update.

## Archivos modificados

- `editor/db/concept_source_link_service.py`
- `editor/editor_streamlit.py`
- `tests/test_legacy_concept_source_link_service.py`
- `tests/test_edit_concept_legacy_source_link_ui.py`
- `tests/test_legacy_concept_source_link_e2e.py`
- `docs/PHASE_LINK_LEGACY_CONCEPT_TO_MANAGED_SOURCE.md`

## Pruebas

Las pruebas unitarias cubren éxito legacy, snapshot diferente, destino ausente
o archivado, documentos ausentes, idempotencia, conflicto, discrepancias
incluido `null`, CAS concurrente, `modified_count == 0`, transacción,
compensación, ausencia de upsert, cero escrituras fuera de alcance y aislamiento
de base. Las pruebas de UI comprueban visibilidad, IDs internos, Sources activas,
confirmación, separación del guardado ordinario, mensajes y limpieza por base.

## E2E temporal

`tests/test_legacy_concept_source_link_e2e.py` se habilita sólo con
`MATHMONGO_RUN_LEGACY_LINK_E2E=1`. Crea una base MongoDB temporal única, crea
una Source con el servicio real, inserta el par legacy, vincula, verifica
identidad, dependencias, inmutabilidad de la Source e idempotencia, y elimina la
base en `finally`. Sin la variable queda `skipped`. No usa MathV0.

## Validaciones

La fase ejecuta pruebas enfocadas, Ruff sólo sobre Python modificado,
compilación en memoria, `git diff --check` y una regresión completa controlada.
La validación enfocada terminó con 115 pruebas pasadas y dos E2E opt-in
omitidos; el E2E nuevo habilitado terminó con una prueba pasada. La regresión
completa terminó con 1400 pruebas pasadas, 53 omitidas y los cuatro fallos XDG
del baseline conocido, sin fallos nuevos.

Ruff pasa en los archivos Python nuevos. El chequeo completo del archivo
monolítico `editor_streamlit.py` conserva los mismos 27 hallazgos preexistentes
que `HEAD` (docstrings, whitespace, orden histórico de imports y `E741`); no se
usó `--fix` ni se modificaron esas líneas ajenas.

No se modificó MongoDB real: las únicas escrituras E2E autorizadas ocurren en
una base temporal creada y eliminada por la propia prueba. No se creó ninguna
Source fuera de esa base temporal, no hubo migración ni backfill y no se
modificaron conceptos existentes.

## Limitaciones

No se implementó Change Source. No se implementó Repair link. No se implementó
Synchronize snapshot. No se implementó unlink, `concept_uid`, migración ni
backfill. Un `source_id: null` presente se trata como estado inválido y no como
concepto legacy vinculable.

## Próxima fase

Una fase posterior, con contrato y auditoría independientes, podrá estudiar la
reparación de vínculos dangling o el cambio explícito de Source sin alterar la
identidad histórica. Esta fase no anticipa esas decisiones.

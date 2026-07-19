# Edit Concept Update Feedback

## A. Síntoma

Después de pulsar **Update Concept**, la actualización coordinada de `concepts`
y `latex_documents` podía completarse correctamente, pero la confirmación no
permanecía visible en la interfaz.

## B. Causa raíz

La causa fue una combinación de mensaje transitorio y recarga de estado. La
rama `success` ejecutaba `st.success()` y acto seguido `st.rerun()`, sin guardar
el mensaje en `session_state`. Además, la limpieza de la marca de selección
forzaba una recarga del formulario y un segundo rerun antes de volver a una zona
estable de la página.

La causa se clasificó como **F: combinación de A y C**, con la ubicación al
final del formulario como factor secundario.

## C. Flujo anterior

1. La UI construía exclusivamente los campos editables.
2. `update_concept_fields_preserving_identity` coordinaba la escritura.
3. Un resultado `success` producía un `st.success()` transitorio.
4. La UI eliminaba la marca de selección y llamaba `st.rerun()`.
5. El siguiente render recargaba el formulario y volvía a llamar `st.rerun()`.
6. No existía ningún mensaje persistente que renderizar después de la recarga.

## D. Flujo corregido

1. El servicio devuelve el mismo resultado estructurado que antes.
2. Cada estado se convierte en feedback explícito.
3. Sólo `success` puede crear un flash persistente.
4. El flash se almacena antes de limpiar la marca de selección y antes del
   primer rerun.
5. La recarga del formulario ocurre sin consumir el flash.
6. En el siguiente render estable, el mensaje aparece antes del encabezado del
   formulario y se elimina inmediatamente después de renderizarse.

## E. Flash message

El estado usa el namespace `edit_concept_update_feedback_`. El flash contiene:

```python
{
    "level": "success",
    "message": "Concepto actualizado correctamente: def_001 — SourceTest.",
    "concept_id": "def_001",
    "source": "SourceTest",
    "database_scope": "...",
}
```

El mensaje sobrevive ambos reruns, se muestra una sola vez y no usa esperas ni
`time.sleep()`. Un update válido sin modificaciones también es éxito cuando los
dos documentos tienen `matched_count == 1`; en ese caso se informa que el
contenido persistido ya era idéntico.

## F. Aislamiento por base

El helper conserva el database scope activo y descarta cualquier flash pendiente
si éste cambia. Un mensaje producido en la base A nunca se renderiza en la base
B.

## G. Aislamiento por concepto

Antes de mostrar un mensaje se comparan `concept_id` y el snapshot histórico
`source`. Un cambio de concepto o de Source descarta el flash y evita atribuir
el resultado a otra identidad.

## H. Estados de error

- `concept_not_found`: error; no se guardó ningún cambio.
- `latex_not_found`: error de inconsistencia; no se informa éxito.
- `stale_identity`: advertencia que solicita recargar.
- `failed_compensated`: error que confirma que la actualización fue revertida.
- `partial_recovery_required`: error bloqueante que requiere recuperación.
- excepción inesperada: mensaje seguro; el formulario no se limpia ni se hace
  rerun.

Sólo `ConceptEditStatus.SUCCESS` genera confirmación persistente. El servicio de
persistencia y su interpretación de `matched_count`/`modified_count` no fueron
modificados.

## I. Pruebas

Se añadieron 18 pruebas específicas que cubren persistencia a través de reruns,
posición estable, consumo único, texto, no-op, todos los estados del servicio,
excepción segura, aislamiento por base/concepto/Source, identidad inmutable y
ausencia de escrituras fuera del servicio permitido.

La validación enfocada terminó con `104 passed, 1 skipped`. Ruff pasó en todo el
Python modificado, usando únicamente las exclusiones auditadas de deuda legacy
para `editor_streamlit.py`; la compilación AST y `git diff --check` también
pasaron.

La única regresión amplia terminó con `1512 passed, 53 skipped, 4 failed`. Los
cuatro fallos son exactamente los fallos XDG preexistentes del baseline; no hubo
fallos nuevos.

## J. Validación manual

Se ejecutó un flujo aislado con una base y una UI falsas, totalmente en memoria:

1. se actualizaron el concepto y su documento LaTeX;
2. se verificó el contenido recargado;
3. el flash atravesó dos ciclos de rerun simulados;
4. apareció una sola vez;
5. no reapareció en el siguiente render;
6. se eliminó al cambiar de database scope.

No se abrió ninguna conexión a MongoDB y no se modificó MathV0 ni conceptos
reales.

## K. Archivos modificados

- `editor/editor_streamlit.py`
- `editor/edit_concept_feedback.py`
- `tests/test_edit_concept_update_feedback.py`
- `docs/PHASE_EDIT_CONCEPT_UPDATE_FEEDBACK.md`

## L. Limitaciones

Esta fase corrige exclusivamente el feedback de **Update Concept**. No cambia
el servicio de persistencia, la identidad `id`/`source`/`source_id`, Sources,
Change Source, otras páginas, relaciones, media, evidence links, import/export,
índices, migraciones, backfills, versión ni tags.

# Edit Concept Identity Preservation

## Objetivo

Hacer seguro el guardado ordinario de **Edit Concept** sin ampliar el alcance de
administración de Sources. La edición permite cambiar contenido y metadatos, pero
protege como inmutables:

- `id`;
- `source`;
- `source_id`, incluida su ausencia en conceptos legacy;
- la clave histórica derivada `id@source`.

Esta fase no mueve conceptos, no crea Sources y no migra datos existentes.

## Riesgo anterior

Edit Concept mostraba `ID` y `Source` como `st.text_input` editables. El botón de
guardado construía un documento raw con esos valores y ejecutaba dos updates
secuenciales:

1. `concepts` recibía el posible `id`/`source` nuevo;
2. `latex_documents` sólo recibía contenido y timestamp sobre la identidad vieja.

No se comprobaba `matched_count`, no existía preflight de ambos documentos y se
mostraba éxito incluso si LaTeX no se encontraba. Un cambio de Source podía dejar
un LaTeX huérfano y romper relaciones, media, evidence links y mapas que conservan
`id@source`.

## Identidad protegida

La UI obtiene una sola vez del documento seleccionado:

```text
original_concept_id = selected_concept["id"]
original_source = selected_concept["source"]
original_source_id = selected_concept.get("source_id")
```

ID y snapshot Source se presentan como código de sólo lectura. El `source_id`, si
existe, también se muestra como contexto inmutable. Ninguno se reconstruye desde
widgets, `Source.name` o texto introducido por el usuario.

El servicio rechaza cualquier `changes` que incluya `id`, `source` o `source_id`.
Los filtros de preflight y compare-and-set continúan usando la pareja original
`(id, source)` y el documento original completo.

## Conceptos legacy

Un concepto sin campo `source_id`:

- continúa abriendo y guardando campos no identitarios;
- conserva exactamente `id` y `source`;
- no recibe `source_id: null` ni un vínculo inferido;
- exige que el `latex_document` contraparte tampoco tenga `source_id`;
- muestra **Legacy concept — not linked to a managed Source.**

No hay migración, backfill, lookup por nombre ni acción de link en esta fase.

## Conceptos vinculados

Un concepto con `source_id`:

- conserva el mismo valor en `concepts` y `latex_documents`;
- no consulta el catálogo para reconstruir o sincronizar el vínculo;
- conserva su snapshot aunque la Source administrada haya sido renombrada;
- sigue permitiendo edición ordinaria si la Source está archivada o ya no existe;
- devuelve `stale_identity` antes de escribir si concepto y LaTeX no conservan el
  vínculo esperado.

Por ello, un guardado ordinario no sincroniza automáticamente `source` con
`Source.name`.

## Guardado seguro

El servicio nuevo
`update_concept_fields_preserving_identity(...)` recibe la identidad original,
el `source_id` esperado, cambios no identitarios, contenido LaTeX y timestamp.

Su flujo es:

1. rechazar campos identitarios o no permitidos;
2. leer exactamente el concepto por `(id, source)`;
3. leer el LaTeX contraparte por la misma pareja;
4. validar la presencia/ausencia y valor exacto de `source_id` en ambos;
5. construir `$set` sólo con campos editables, contenido y timestamp;
6. actualizar con filtros compare-and-set basados en los documentos originales;
7. exigir `matched_count == 1` en concepto y LaTeX;
8. aceptar `modified_count == 0` como éxito válido cuando el documento sí
   coincidió y ya tenía el valor solicitado;
9. devolver un resultado estructurado; la UI muestra éxito únicamente para
   `success`;
10. limpiar la identidad seleccionada y hacer rerun después del éxito para volver
    a cargar el documento persistido.

No se usa upsert, delete + insert ni escritura en otra colección.

Cuando el cliente declara soporte transaccional —o su topología es replica set,
sharded o load-balanced— ambos updates se ejecutan con `with_transaction`. En un
backend sin transacciones se usa:

- preflight de ambos documentos antes de escribir;
- compare-and-set del concepto;
- compare-and-set del LaTeX;
- compensación inversa del concepto filtrada por el estado exacto que escribió la
  operación, si falla el segundo update.

La compensación nunca borra ni sobrescribe un documento que ya cambió de nuevo.

## Manejo de inconsistencias

Resultados expuestos:

| Estado | Significado y respuesta UI |
| --- | --- |
| `success` | Ambos documentos alcanzaron el estado solicitado; se muestra éxito y se recarga. |
| `concept_not_found` | El concepto falta en preflight; no se escribe LaTeX. |
| `latex_not_found` | Falta la contraparte antes del primer update; el concepto no se escribe. |
| `stale_identity` | El vínculo cambió o el compare-and-set del concepto obtuvo cero matches. |
| `failed_compensated` | Falló la operación coordinada, pero la transacción abortó o el concepto fue restaurado. |
| `partial_recovery_required` | El estado final no pudo verificarse o compensarse sin riesgo; se prohíbe afirmar éxito. |

Una excepción ambigua del segundo update se verifica con una lectura. Si ambos
documentos ya tienen el estado final, puede reportarse éxito verificado; si LaTeX
sigue original, se compensa el concepto. Cualquier tercer estado se reporta como
recuperación parcial requerida.

## Archivos modificados

- `editor/editor_streamlit.py`: contexto inmutable, llamada al servicio, mensajes
  por resultado y rerun seguro.
- `editor/db/concept_edit_service.py`: servicio transaccional/compensatorio nuevo.
- `tests/test_edit_concept_identity_preservation.py`: pruebas con fakes y contrato
  estático de la rama UI.
- `docs/PHASE_EDIT_CONCEPT_IDENTITY_PRESERVATION.md`: este documento.

No se modificaron Add Concept, Add Source, Edit Source, mapas, grafos, relaciones,
media, evidence links, Document Builder, import/export/update, migraciones,
índices ni schemas.

## Pruebas

La puerta roja inicial produjo el error esperado:

```text
ModuleNotFoundError: No module named 'editor.db.concept_edit_service'
```

Después de implementar:

- suite nueva de Edit Concept: `25 passed`;
- suite enfocada combinada: `90 passed`, 5 warnings Pydantic preexistentes;
- regresión controlada única: `1366 passed, 51 skipped, 4 failed`.

Los cuatro fallos de regresión son exactamente el baseline XDG conocido:

- tres casos de `tests/test_xdg_media_paths.py` relacionados con el fake
  `_FixedExportDatetime`;
- un caso de `tests/test_xdg_mutable_guards.py` que busca un guard legacy ausente.

No hubo fallos nuevos. Las pruebas nuevas cubren legacy, linked, campos prohibidos,
UI inmutable, Source renombrada/archivada/inexistente, documentos faltantes,
`matched_count == 0`, `modified_count == 0`, transacción, fallo del segundo update,
compensación, parcialidad, estado de sesión y ausencia de escrituras en colecciones
dependientes.

## Validaciones

- Ruff de `editor/db/concept_edit_service.py` y de la prueba nueva: limpio.
- Ruff de `editor/editor_streamlit.py`: 27 hallazgos preexistentes; HEAD tenía 28,
  por lo que esta fase no añadió deuda Ruff.
- Compilación en memoria de los tres Python modificados: correcta.
- `git diff --check`: correcto en la Puerta F y se repite antes del commit.
- No se generaron caches ni bytecode; pytest se ejecutó con
  `PYTHONDONTWRITEBYTECODE=1` y `-p no:cacheprovider`.
- No se instanció ningún componente contra MathV0 ni se hicieron escrituras en
  MongoDB real.

ID, `source` y `source_id` son inmutables durante el guardado ordinario. Editar
contenido no cambia Knowledge Maps, claves `id@source`, relaciones, media ni
evidence links.

## Limitaciones

- Todavía no se implementó **Link to existing managed Source**.
- Todavía no se implementó **Repair managed Source link**.
- Todavía no se implementó **Change Source**.
- Todavía no se implementó **Synchronize Source snapshot**.
- Todavía no se implementó `concept_uid`.
- No existe relocalización de conceptos ni remapeo de dependencias.
- No se creó ninguna Source.
- No se modificó MongoDB real ni ningún concepto existente.
- No hubo migración ni backfill.
- El fallback no oculta un estado ambiguo: devuelve
  `partial_recovery_required` para recuperación explícita.

## Próxima fase

Implementar **Link to an existing managed Source** como una acción separada que
añada `source_id` a concepto y LaTeX sin cambiar `id` ni el snapshot `source`. Debe
seleccionar únicamente una Source activa existente, no crear Sources y conservar
la relocalización y sincronización de snapshot para fases posteriores.

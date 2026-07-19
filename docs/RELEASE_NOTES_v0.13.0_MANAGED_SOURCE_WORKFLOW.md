# v0.13.0 — Managed Source Workflow

## Highlights

La versión cierra el flujo de Sources administradas con la recomendación
**B. LISTO CON LIMITACIONES DOCUMENTADAS**. Add Source, Add Concept, Cuaderno,
Edit Concept, legacy linking y Source deletion comparten ahora un contrato
trazable sin cambiar la identidad histórica `id@source`.

La reauditoría final registró cero hallazgos críticos y cero hallazgos altos. Los
cinco hallazgos altos previos, H-01 a H-05, quedaron corregidos y cubiertos por
pruebas dirigidas.

## Managed Sources

**Add Source** permanece como el único creador interactivo de Sources. Cada
operación está ligada a una base explícita, usa modelos tipados, revisa
duplicados y mantiene estados `active`/`archived`. Add Concept, Cuaderno y Edit
Concept sólo consumen Sources existentes; nunca las crean por inferencia.

## Modern and Legacy Concepts

El contrato moderno persiste `source` como snapshot textual y `source_id` como
vínculo estable tanto en `concepts` como en `latex_documents`. El contrato
legacy, con `source` y sin `source_id`, continúa siendo válido y no requiere
migración.

Ambos contratos conservan `id@source`, que sigue siendo la identidad usada por
relaciones, Knowledge Maps, media y evidence links.

## Add Concept

Add Concept lista únicamente Sources activas de la base actual, selecciona por
`source_id` y rehidrata la Source inmediatamente antes de guardar. Sin Sources
activas, el formulario bloquea el guardado y remite a Add Source; no ofrece texto
libre.

## Cuaderno Promote

Promover una nota a concepto exige una Source administrada activa. El flujo
guarda simétricamente `source` + `source_id` y ya no acepta un origen libre para
conceptos nuevos.

## Edit Concept

La edición ordinaria preserva `id`, `source`, la presencia/ausencia y el valor de
`source_id`. Cambiar contenido no mueve el concepto ni reescribe relaciones,
Knowledge Maps u otras dependencias basadas en `id@source`.

## Legacy Linking

Edit Concept ofrece una acción separada para vincular un concepto legacy a una
Source activa existente. La operación sólo añade el mismo `source_id` al par
exacto de concepto y LaTeX, con compare-and-set, transacción cuando el backend la
admite y compensación controlada en fallback.

No cambia `id`, `source`, `_id`, contenido ni dependencias. Repetir el mismo
vínculo es idempotente. Cambiar, reparar o quitar vínculos queda fuera de esta
versión.

## Source Deletion Safety

El borrado físico de una Source se bloquea si permanecen References,
`concepts.source_id` o `latex_documents.source_id` vinculados. El guard se
revalida inmediatamente antes de borrar y no ejecuta cascade. La práctica
recomendada sigue siendo archive-first.

## Fresh Database Support

El lifecycle E2E de base nueva valida una base temporal inicialmente vacía:
creación de Source, concepto moderno, contrato dual, edición, exportación,
importación, compatibilidad legacy y cleanup. La prueba es opt-in, no usa una
base de usuario y permanece omitida cuando su variable no está habilitada.

## Multiple Database Isolation

El startup ya no inicializa `MathV0` implícitamente: sólo abre la base
configurada. Document Builder y Knowledge Graph/Maps aíslan el estado por
conexión + base y lo invalidan antes de leer un nuevo scope, evitando que
selecciones, documentos o mapas de una base se interpreten en otra.

## Export, Import and Update

Export, import y database update conservan documentos legacy y modernos,
incluida la presencia o ausencia de `source_id`. No crean Sources a partir de
nombres ni reparan vínculos automáticamente. La identidad histórica y los
payloads de relaciones, mapas, media y evidence permanecen sin cambios.

## Testing

El baseline autorizado antes de este cierre es:

```text
1432 passed, 53 skipped, 4 failed, 7 warnings
```

Los cuatro fallos son el baseline XDG conocido: tres en
`tests/test_xdg_media_paths.py` y uno en
`tests/test_xdg_mutable_guards.py`. El resultado final esperado para este cierre
era el mismo número y naturaleza de fallos, sin fallos nuevos. La única regresión
completa ejecutada durante el cierre observó exactamente `1432 passed, 53
skipped, 4 failed, 7 warnings`; por tanto, coincidió con lo esperado y no añadió
fallos.

Existe un E2E opt-in para el lifecycle de base nueva y otro para el vínculo
legacy. Ambos crean bases temporales aisladas y hacen cleanup; en la validación
ordinaria permanecen skipped porque no se habilitan sus variables MongoDB.

La reauditoría posterior a H-01…H-05 obtuvo `1432 passed, 53 skipped, 4 failed,
7 warnings`, verificó los contratos modernos/legacy y concluyó con cero
hallazgos críticos y cero hallazgos altos.

La selección enfocada del cierre obtuvo `243 passed, 2 skipped, 6 warnings`.
Los dos skips fueron precisamente los E2E fresh database y legacy link sin sus
opt-ins.

## Known Limitations

- **M-01:** Delete Concept sigue siendo secuencial y no cubre integralmente
  todas las dependencias.
- **M-02:** Browse/Quarto puede colapsar conceptos con el mismo `id` en Sources
  distintas.
- **M-03:** portabilidad conserva `source_id`, pero no diagnostica todos los
  vínculos administrados colgantes o inconsistentes.
- **M-04:** queda pendiente cobertura browser E2E multibase.
- **L-01:** `DocumentoLatex` no declara `source_id` explícitamente en el modelo,
  aunque las rutas actuales lo preservan.
- Permanecen cuatro fallos XDG baseline y siete warnings conocidos.
- Existe una ventana concurrente estricta entre el último blocker check y el
  delete físico de Source; archive-first es la práctica operativa recomendada.
- Change Source no está implementado. Tampoco se implementaron Repair Link,
  Synchronize Snapshot, unlink ni `concept_uid`.

## Upgrade Notes

- No hay migración automática ni backfill.
- Las bases legacy siguen siendo válidas y sus conceptos funcionan sin
  `source_id`.
- No es obligatorio vincular todos los conceptos legacy.
- Se recomienda un backup verificable antes de actualizar o ejecutar
  operaciones importantes.
- Add Concept y Cuaderno Promote exigen una Source administrada activa para cada
  concepto nuevo.
- Revisa la base activa antes de crear, editar, vincular, archivar o borrar.

## Git History

- `19c86838` — auditoría inicial de integración de Sources en Add Concept.
- `83f8fb51` — contrato dual opcional `source` + `source_id`.
- `6a2136af` — selección de Source administrada en Add Concept.
- `b6ba6733`, `1b8df663` — auditoría de Edit Concept y preservación de identidad.
- `810fbec2` — lifecycle E2E para una base nueva.
- `c2c3ef75`, `90f58cc0` — servicio y UI de vínculo legacy explícito.
- `434aa015` — auditoría integral de compatibilidad.
- `69980467` — Source administrada obligatoria en Cuaderno Promote.
- `8ebf8fa4` — guard de borrado para vínculos modernos.
- `79b515b1` — startup sin inicialización implícita de `MathV0`.
- `fd3eda8a` — aislamiento de Document Builder por conexión y base.
- `1a8250da` — aislamiento de Knowledge Graph/Maps por conexión y base.
- `9e6ce098` — registro de fixes H-01…H-05.
- `2787f9e3` — reauditoría final del workflow.

# Managed Source Workflow

## 1. Propósito

Este flujo mantiene un catálogo explícito de Sources por base de datos y lo usa
para identificar el origen de cada concepto nuevo. Una Source administrada tiene
un `source_id` estable; el concepto conserva además `source`, un snapshot textual
compatible con la identidad histórica `id@source`.

La guía sirve tanto para una instalación nueva como para una base legacy. No
requiere migrar los conceptos existentes.

## 2. Flujo recomendado

```text
Create or select database
          ↓
      Add Source
          ↓
Add Concept or Cuaderno Promote
          ↓
     Edit Concept
          ↓
 Optional legacy linking
```

Antes de crear contenido, comprueba la conexión y la base activa que muestra la
interfaz. Crea o selecciona una Source allí y después registra el concepto.

## 3. Add Source

**Add Source** es el único creador interactivo de documentos del catálogo de
Sources. La pantalla está ligada a la base activa, muestra esa base antes de
guardar y exige confirmación explícita del destino.

Una Source nueva empieza con estado `active`. Las Sources que ya no deben
ofrecerse para contenido nuevo pueden archivarse; `archived` conserva el registro
y sus vínculos. La vista previa revisa coincidencias exactas, fuertes y posibles.
Si se desea conservar una Source separada pese a esas coincidencias, la persona
debe confirmarlo; el sistema no fusiona duplicados automáticamente.

Las References son opcionales. Se pueden capturar manualmente, importar desde
BibTeX o asociar a la Source mediante el flujo explícito del catálogo. Si una
acción de Reference falla después de crear la Source, la Source se conserva y el
resultado parcial se informa para corregirlo desde **Edit / Analyze Source**.

**Add Concept** y **Cuaderno Promote** nunca crean Sources. Si falta la Source
necesaria, vuelve primero a **Add Source**.

## 4. Add Concept

**Add Concept** lista únicamente Sources con estado `active` en la base actual.
La selección usa internamente `source_id`; el nombre visible sólo es una etiqueta
y los nombres repetidos se distinguen con información adicional.

Al guardar, la Source se vuelve a consultar por su identidad administrada y debe
seguir existiendo y activa. El concepto persiste:

- `source`: nombre de la Source en el momento de crear el concepto, como snapshot
  textual compatible;
- `source_id`: vínculo estable a la Source administrada.

Los dos campos se guardan simétricamente en el concepto y en su documento LaTeX.
Si la base no contiene Sources activas, no se ofrece texto libre y el guardado
queda bloqueado con la indicación de crear primero una Source.

## 5. Cuaderno Promote

Al promover una nota de Cuaderno a concepto se debe elegir una Source
administrada activa de la base actual. El flujo no acepta un nombre de Source
como texto libre ni infiere una Source desde contenido previo.

Antes de persistir, la selección se rehidrata por `source_id`. El concepto
promovido guarda el par `source` + `source_id` con el mismo contrato de **Add
Concept**.

## 6. Edit Concept

Durante una edición ordinaria, `id`, `source` y `source_id` son identidad
inmutable. Se puede cambiar el contenido editable, pero la operación no mueve el
concepto a otra Source ni reescribe su snapshot histórico.

Como `id@source` permanece estable, las relaciones, Knowledge Maps, asociaciones
de media y evidence links que usan esa identidad no necesitan rekey ni
migración. **Update Concept** tampoco crea, cambia ni elimina vínculos de Source.

## 7. Conceptos legacy

Un concepto legacy tiene `id` y `source`, pero no contiene `source_id`. Sigue
siendo válido, legible y editable; la aplicación no lo migra automáticamente.

Desde **Edit Concept** se puede ejecutar, por separado, **Link to an existing
managed Source**. Esta acción selecciona una Source activa existente por
`source_id`, muestra cualquier diferencia entre el nombre actual y el snapshot
histórico y exige confirmación explícita.

El vínculo sólo añade el mismo `source_id` al concepto y a su documento LaTeX.
No cambia `id`, `source`, `_id`, contenido, relaciones ni la identidad
`id@source`. No permite cambiar, reparar o quitar un vínculo existente.

No es obligatorio vincular todos los conceptos legacy para seguir usándolos.

## 8. Delete Source

La práctica recomendada es **archive first**: archiva la Source y verifica sus
usos antes de considerar un borrado físico. Archivar la retira de los selectores
de contenido nuevo sin perder su identidad.

El borrado físico se bloquea cuando existen References asociadas, conceptos con
`concepts.source_id` o documentos LaTeX con `latex_documents.source_id`. Los
blockers se vuelven a comprobar justo antes del borrado. No existe cascade: la
operación no elimina ni modifica References, conceptos o LaTeX para liberar una
Source.

## 9. Bases múltiples

El startup abre sólo la conexión y base configuradas. Cualquier conexión o base
adicional se selecciona de forma explícita; abrir la aplicación no debe
inicializar otra base implícitamente.

Document Builder y Knowledge Graph/Maps calculan su scope con conexión + base.
Al cambiar de scope limpian selecciones, previews, mapas cargados y controles
relacionados antes de leer la base nueva. Volver a una base anterior no restaura
automáticamente el estado invalidado.

Comprueba siempre la base activa antes de crear, vincular, archivar, editar o
borrar.

## 10. Exportación e importación

Las bases pueden contener a la vez conceptos modernos (`source` + `source_id`) y
legacy (sólo `source`). Export, import y database update conservan el documento
crudo, incluida la presencia o ausencia de `source_id`.

Estas operaciones no inventan Sources ni reparan vínculos a partir del nombre.
La ausencia de `source_id` en un concepto legacy se conserva como ausencia; un
vínculo moderno se conserva por su ID explícito.

## 11. Limitaciones conocidas

- **Delete Concept no integral:** sus rutas actuales son secuenciales y no
  cubren de forma transaccional todas las dependencias.
- **Browse/Quarto e IDs repetidos:** conceptos con el mismo `id` en Sources
  distintas pueden colapsar en algunas selecciones; usa Document Builder para
  trabajar con la identidad compuesta.
- **Diagnóstico incompleto en portabilidad:** export/import/update conservan
  `source_id`, pero no reportan todos los vínculos colgantes o inconsistentes
  entre Source, concepto y LaTeX.
- **Modelo LaTeX:** `DocumentoLatex` todavía no declara `source_id`
  explícitamente, aunque las rutas actuales lo preservan.
- **Ventana concurrente de delete físico:** existe una ventana estricta entre la
  última comprobación de blockers y el borrado físico de la Source.
- **Baseline XDG:** permanecen cuatro fallos conocidos, tres en
  `tests/test_xdg_media_paths.py` y uno en
  `tests/test_xdg_mutable_guards.py`.
- **Change Source no implementado:** la versión no mueve conceptos entre Sources.

## 12. Flujo que no debe utilizarse

No se debe:

- escribir una Source como texto libre para crear un concepto nuevo;
- cambiar manualmente `source` o `source_id` en almacenamiento;
- editar la identidad histórica `id@source`;
- intentar borrar una Source mientras tenga vínculos;
- mover conceptos entre Sources como parte de una edición ordinaria.

No uses nombres coincidentes para inferir o reparar vínculos. Si una operación no
está expuesta como acción explícita del flujo, no la sustituyas con una edición
manual de MongoDB.

## 13. Recuperación y seguridad

Haz un backup verificable antes de importaciones, updates, borrados u operaciones
importantes. Prefiere archivar una Source y revisar sus vínculos antes del
borrado físico.

No ejecutes migraciones o backfills sin una fase separada, un dry-run revisado y
un plan de recuperación. Antes de confirmar cualquier escritura, verifica la
conexión y base activas en la interfaz. Si un resultado es parcial o bloqueado,
detente, conserva el backup y corrige únicamente mediante un flujo explícito y
auditable.

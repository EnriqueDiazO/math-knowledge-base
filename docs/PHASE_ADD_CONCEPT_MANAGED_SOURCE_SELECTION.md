# Managed Source Selection in Add Concept

## Objetivo

Hacer que los conceptos nuevos seleccionen una Source administrada activa y
persistan su identidad estable junto con un snapshot textual compatible.

## Arquitectura

Add Source crea y administra Sources. Add Concept solamente selecciona Sources
existentes. Add Concept usa el `SourceRepository` ligado a la base activa y no
escribe en la colección `sources`.

## Flujo legacy eliminado

El selector de conceptos nuevos ya no usa:

- `concepts.distinct("source")`;
- `(Custom...)`;
- `New source name`.

Add Concept ya no acepta nombres de Source como texto libre.

## Flujo nuevo

1. El contexto del catálogo proporciona el repositorio de la base activa.
2. Se listan todas las páginas de Sources con `status="active"`.
3. El selectbox conserva `source_id` como valor interno y muestra `Source.name`.
4. Los nombres duplicados se distinguen con tipo e identificador abreviado.
5. Antes de guardar se rehidrata la Source por ID y se comprueba que siga
   existiendo y activa.

## Contrato source + source_id

Cada concepto nuevo recibe:

- `source_id = selected_source.source_id`, como identidad estable;
- `source = selected_source.name`, como snapshot textual compatible.

El contrato previo de persistencia replica ambos campos en `concepts` y
`latex_documents`.

## Comportamiento sin Sources

Cuando la base activa no contiene Sources activas, no se renderiza una entrada
de texto y el guardado queda deshabilitado. La UI muestra:

> No hay Sources disponibles. Crea primero una Source desde Add Source.

## Comportamiento ante errores

Un fallo al listar o rehidratar el catálogo se presenta como error seguro. No
se sustituye por valores de `concepts.source`, texto libre ni una Source creada
automáticamente, y el concepto no puede guardarse.

## Compatibilidad legacy

Los conceptos existentes sin `source_id` siguen validando y siendo legibles.
La identidad histórica `(id, source)` no cambia. Sus cadenas legacy no se
ofrecen para crear conceptos nuevos salvo que exista una Source administrada
activa correspondiente.

## Archivos modificados

- `editor/editor_streamlit.py`
- `editor/helpers/managed_source_selection.py`
- `tests/test_add_concept_managed_source_selection.py`
- `docs/PHASE_ADD_CONCEPT_MANAGED_SOURCE_SELECTION.md`

## Pruebas

Las pruebas cubren origen administrado, filtro activo, paginación, Sources sin
conceptos, exclusión de cadenas exclusivamente legacy, etiquetas duplicadas,
selección y rehidratación por `source_id`, snapshot de nombre, catálogo vacío,
errores de lectura, cambio de base, ausencia de texto libre, bloqueo de
guardado y ausencia de escrituras en Sources.

## Validaciones

- Pruebas nuevas: `14 passed`.
- Pruebas enfocadas: `94 passed`.
- Compilación en memoria de los tres Python modificados: correcta.
- `git diff --check`: correcto.
- Ruff no añadió hallazgos: los 28 reportados en `editor_streamlit.py` son los
  mismos de `HEAD`; los dos Python nuevos están limpios.
- Suite completa: `1343 passed, 51 skipped, 4 failed`. Los cuatro fallos son
  los mismos del baseline y no están relacionados con Sources.

## Limitaciones

- No se creó ninguna Source ni se modificó MongoDB real.
- No se ejecutaron migraciones ni backfill y no se modificaron conceptos
  existentes.
- Edit Concept todavía no administra plenamente el vínculo.
- Importación y exportación requieren una fase posterior de revisión.
- Add Source y Edit / Analyze Source no fueron modificados.

## Próxima fase

Diseñar la administración del vínculo en Edit Concept y revisar el round-trip
de importación/exportación para conceptos legacy y vinculados.

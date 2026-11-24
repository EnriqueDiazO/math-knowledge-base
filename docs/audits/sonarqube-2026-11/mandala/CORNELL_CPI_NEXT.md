# Cornell y CPI: siguiente corte vertical implementable

Este documento delimita la continuación de Cuaderno tras el núcleo Diario de
`f81f7479`/`ffeff389`. Cornell y CPI **no tienen aún un editor React**. Se conserva
su implementación histórica; no están listos para retirar Streamlit.

## Contratos recuperados

Ambos viven en `latex_notes` y reutilizan el CRUD de `MathMongo`. La fábrica
`from_database` permite usarlo sin abrir conexiones, preparar índices ni iniciar
Streamlit. El formato se decide por `note_format`, nunca por el aspecto del texto.

| Actividad | Modelo canónico y almacenamiento | Operaciones existentes que deben migrarse |
|---|---|---|
| Cornell | `CornellDocument`, `cornell_math_v1`, campo `cornell`, páginas con `page_id`/`order`, regiones `cue`/`main`/`summary`, `source_refs`, branding y watermark | Crear, recuperar, editar y ordenar páginas, duplicar, borrar con confirmación contextual, asociar medios, analizar ajuste, proponer división por overflow, aceptar/rechazar la propuesta, promover contenido y exportar proyectos/PDF |
| CPI | `CpiDocument`, `cpi_v1`, campo `cpi`, páginas con `page_number`, regiones `comprehension`/`production`/`integration`, branding y watermark | Crear, recuperar, editar y ordenar páginas, duplicar, borrar, asociar medios, comprobar ajuste/regiones, exportar el documento y sus proyectos |

Los servicios `editor.cornell.service` y `editor.cpi.service` regeneran
`latex_body` desde la estructura. En estos formatos ese cuerpo es una proyección;
editar sólo esa proyección pierde la organización de las regiones. Por eso el
adaptador Diario los rechaza sin escribir. Las funciones de persistencia,
generación y exportación siguen siendo canónicas; no crear otros renderizadores.

`tests/test_notebook_structured_contracts.py` caracteriza ambos servicios con
Mongo temporal real: alta, apertura, edición, identidad, campos desconocidos,
origen seed, duplicación y desvinculación de medios compartidos al borrar sólo
una nota. Los archivos compartidos permanecen. Se mantienen además los 57 casos
anteriores de servicio/persistencia/empaquetado; no se suman como pruebas nuevas.
Estos fixtures son sintéticos y no sustituyen los documentos históricos privados.

## Primer recorrido: Cornell de una página

1. Rutas de actividad dedicadas `/api/study/v1/cornell` y vista
   `/study/notebook/cornell`. Usar los mismos guards de biblioteca/origen y
   contratos de error. No registrar un CRUD arbitrario de colecciones.
2. Crear un documento canónico de una página. Reutilizar el editor matemático
   actual en la región seleccionada; conservar las demás regiones fuera del
   editor activo. Identificar página y región explícitamente para que MathLive
   inserte en el lugar correcto. No construir un segundo editor Tiptap.
3. Borrador durable por biblioteca/nota/página/región, con ID de intento estable.
   Conservar snapshot del editor, LaTeX protegido y asociaciones. Guardar usa el
   servicio Cornell y recupera del backend lo efectivamente persistido.
4. Antes de exponer edición HTTP, extender la persistencia canónica estructurada
   con CAS opcional sobre la instantánea BSON completa. Los servicios antiguos
   leen y actualizan sin revisión esperada: reutilizarlos directamente aún deja
   una carrera. Añadir regresión de dos escritores antes de conectar el botón.
   No reescribir documentos ni imponer una migración global de revisiones.
5. Recargar y editar sólo `main`; comprobar `cue`, `summary`, `source_refs`, medios,
   identidades y metadatos desconocidos. El render de un formato no puede guardar
   sobre otro. Confirmaciones ligadas a identidad y biblioteca, no al índice de
   una fila filtrable.
6. Preparar el bundle con `build_note_latex_bundle`; compilar sus archivos con el
   aislamiento ya usado por React. Comprobar recursos de la plantilla histórica
   y ajuste de regiones. No llamar desde HTTP a los lanzadores antiguos de TeX
   sin su adaptación al sandbox. Descargar TEX debe funcionar aunque falte una
   herramienta de compilación.
7. Verificar crear → guardar → recargar → editar una región → PDF en Chrome y
   Firefox y Mongo propio; hash de las regiones restantes, texto y raster del
   PDF, reporte de ajuste y comportamiento cuando una región desborda.

Después se incorporan duplicación/reordenación de páginas, medios y propuestas
de división. Las propuestas de overflow son operaciones con aceptación explícita;
no reducirlas a una plantilla visual. Antes de borrar, reutilizar la orquestación
de referencias de medios y comprobar fallos parciales; no purgar recursos porque
una sola nota deje de referenciarlos.

## CPI después del corte Cornell

Reutilizar transporte, borrador por región, revisión y selección del editor.
Conservar modelos, geometría, rótulos y exportadores CPI. Las zonas Comprensión,
Producción e Integración tienen significado propio; sus colores no representan
tipos matemáticos. Comprobar la plantilla clásica y la opción híbrida existente,
preservando la selección explícita y los paquetes/macros de los documentos.

## Otras actividades pendientes

Worklog, Backlog, Weekly y Deliverables mantienen sus entidades y operaciones en
el Cuaderno histórico. Promoción a concepto, calendario/timeline, gestión completa
de medios, preferencias editoriales y eliminación del Diario siguen pendientes
de adaptación React. Su existencia no queda sustituida por el listado Diario ni
por una nota de lectura. No hay retiradas autorizadas por este checkpoint.

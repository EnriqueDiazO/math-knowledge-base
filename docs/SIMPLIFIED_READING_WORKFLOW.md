# Flujo simplificado de lectura

## Navegación

Reading Space presenta cuatro destinos principales, siempre en este orden:

1. **Biblioteca**
2. **Leer**
3. **Cuaderno**
4. **Conocimiento**

Sin un documento seleccionado, la entrada es Biblioteca. Con una selección
activa, la entrada es Leer. La selección se conserva al revisar las otras
vistas. Page Map, mantenimiento, índices y diagnósticos viven en el menú
secundario **Configuración** y no compiten con el flujo de lectura.

## Biblioteca

Biblioteca reúne el historial reciente y el catálogo. Si existe una lectura
reciente, **Continuar leyendo** aparece primero; después se ofrece una búsqueda
simple por título, filtros secundarios dentro de **Más filtros** y tarjetas de
documento. Las tarjetas muestran únicamente título, fuente o autor legible,
referencia, formato PDF/web, estado, última página o fecha y la acción
**Leer/Continuar**. No muestran tablas, IDs ni estado de índices.

## Leer

Leer mantiene el documento como elemento principal. Un PDF muestra resumen,
página/progreso y **Abrir lector avanzado** como acción primaria. El visor
`st.pdf`, su descarga verificada y la apertura local permanecen disponibles
como alternativa. Un documento web conserva metadata, URL, registro explícito
de apertura y las notas/asociaciones compatibles, sin simular páginas PDF.

La captura Streamlit está junto a la lectura. **Nota rápida** empieza por un
único cuerpo; título, tipo, rango y etiquetas quedan en **Más opciones**. El
título se deriva de la primera línea cuando no se personaliza. Los formularios
persisten mediante los servicios existentes de Notes & Evidence.

## Cuaderno y Conocimiento

Cuaderno es una superficie de revisión de highlights, underlines, anotaciones y
ReadingNotes, agrupadas por documento/página mediante los componentes
existentes. La creación no se duplica aquí.

Conocimiento revisa conceptos de la página y del documento, evidencia y marcas
pendientes. **Ir a la marca** devuelve a Leer sin mostrar el wizard, IDs, JSON o
paginación técnica. La asociación se inicia en el contexto de lectura.

## Panel contextual del Advanced Reader

El inspector derecho sustituye su contenido en vez de acumular secciones:

- **Lectura:** página, conteo de marcas y conceptos, Nota rápida y Revisar
  marcas.
- **Texto seleccionado:** fragmento, página, Highlight, Underline y Cancelar.
- **Confirmación de marca:** fragmento, página, Guardar y Cancelar; color,
  comentario y etiquetas quedan en Más opciones.
- **Marca guardada:** confirmación, Asociar concepto, Añadir nota y Seguir
  leyendo.
- **Asociación:** buscador, tarjetas, concepto seleccionado, relación default,
  Guardar y Cancelar en una sola operación.
- **Concepto asociado:** concepto, relación, fragmento, página y Volver a leer.

Los paneles de revisión avanzada siguen disponibles tras **Revisar marcas**,
pero no se montan en el estado normal. Cambiar o cancelar una operación no
modifica página, zoom, rotación ni datos persistentes.

## Accesibilidad y responsive

Las superficies, tarjetas, formularios y estados usan variables de tema en
light/dark mode. Hay foco visible, estados disabled legibles y confirmaciones
textuales que no dependen sólo del color. A 1100, 900 y 700 px el PDF conserva
el espacio principal; miniaturas e inspector se convierten en paneles
plegables, los botones envuelven y los formularios pasan a una columna.

## Configuración y limitaciones

Configuración permanece cerrada por defecto y abre Page Map, Mantenimiento o
Diagnósticos avanzados sólo por acción explícita. Las tablas técnicas no se
renderizan en Biblioteca ni Leer.

Esta reorganización no cambia modelos, colecciones, campos, IDs, repositorios,
índices, export/import, blobs, PDF.js ni seguridad. Advanced Reader no posee un
endpoint de ReadingNote: para respetar el límite de no cambiar backend, su
entrada **Nota rápida** guía al flujo persistente de Leer y no simula una
escritura. Las notas se guardan en Streamlit. Tampoco se añaden OCR, búsqueda
semántica, embeddings ni extracción persistente.

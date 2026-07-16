# Reading Space polish y etiquetas de página — S4.2

S4.2 convierte Reading Space en una mesa de lectura centrada en el documento,
la página y la captura de conocimiento. El cambio conserva los contratos S2,
S3 y S4, pero reduce el aspecto de pantalla de diagnóstico que tenía el lector.

## Organización visual

Reading Space se divide en las pestañas **Workspace**, **Documents**, **Recent**,
**Notes**, **Evidence**, **Page Map** y **Maintenance**. Con un Document
seleccionado, la vista inicial es Workspace; sin selección, es Documents.
Las pestañas son stateful y lazy en Streamlit 1.55: sólo la pestaña activa
ejecuta sus consultas y formularios. Si un PDF ya está abierto, su media
verificado permanece registrado al cambiar de pestaña para evitar invalidar el
visor durante la navegación.

Workspace conserva los layouts **Split workspace** y **Stacked layout**. En el
layout por defecto, el lector permanece a la izquierda y Quick Annotation,
Quick Reading Note y las anotaciones agrupadas por página quedan a la derecha.
Documents contiene filtros y selección; Recent contiene aperturas recientes;
Notes y Evidence ofrecen vistas filtrables del Document y Source actuales.

El encabezado compacto presenta título, Source, Reference, estado de lectura,
página física y página lógica. La metadata visible del Reader se muestra como
una tarjeta de Document. El diccionario técnico completo dejó de aparecer en el
flujo normal y está disponible únicamente en **Technical details**, colapsado.

## PDF page y Book page

`current_page` sigue siendo la página física del PDF y continúa persistiendo por
el servicio S3 sólo al pulsar **Save PDF page**. La página impresa se calcula a
partir de la colección `document_page_maps` y se presenta, por ejemplo, como:

```text
Book page 1 · PDF page 9 of 306
```

Un `DocumentPageMap` pertenece a un único PDF Document y su Source inmutable.
Contiene reglas no solapadas y overrides manuales. Los estilos admitidos son
`arabic`, `roman_lower`, `roman_upper` y `literal`; un override siempre gana a
una regla. Sólo puede existir un mapa activo por `(user_scope, document_id)`.
Los IDs, timestamps, lifecycle y validaciones son persistentes, sin guardar
bytes ni paths.

La acción **Set as Book page 1** crea o reemplaza la regla sencilla “PDF N =
Book 1”. Page Map permite además crear reglas con inicio y fin opcional, añadir
prefijos, guardar overrides, archivar/reactivar el mapa y resetearlo con
confirmación explícita. Estas etiquetas son metadata manual: no mueven el
scroll interno de `st.pdf`.

## Controles del lector

Sobre el PDF aparecen PDF page, Book page y estado, junto con **Previous**,
**Next**, **Save PDF page**, **Set as Book page 1**, **Quick note** y **Quick
annotation**. Previous/Next sólo actualizan el valor manual de la página;
guardar es una acción independiente. El visor sigue usando `st.pdf(...,
height=800)` y conserva la descarga verificada por SHA-256.

## Notes & Evidence

Las anotaciones se agrupan por `Book page X · PDF page N` cuando existe un mapa,
y por `PDF page N` cuando no existe. Notes presenta páginas equivalentes y las
tarjetas de Evidence muestran concepto, source legacy, título resuelto, origen,
tipo de vínculo y etiqueta de página. Los formularios siguen creando
anotaciones lógicas y ReadingNotes manuales; no existe overlay sobre el PDF.

## Estado compacto y Maintenance

Las vistas normales muestran resúmenes `Catalog ready`, `Reading Space ready` y
`Notes & Evidence ready` o una alerta compacta si falta inicialización. Las
tablas `collection / index / state / detail`, los conflictos y los formularios
de inicialización están en Maintenance o en expanders cerrados de diagnóstico.
Add Source y Edit / Analyze Source comparten **Advanced catalog diagnostics** y
conservan la confirmación por nombre real de la base. Ninguna vista inicializa
índices de forma automática.

Cuaderno conserva toda su persistencia y UI; S4.2 elimina únicamente la leyenda
experimental que anunciaba fases futuras.

## Backup portable

Los exports nuevos pueden incluir
`collections/document_page_maps.json` en Extended JSON canónico. Import valida
Document, Source, IDs, timestamps y unicidad activa antes de escribir. Un
segundo import idéntico es no-op; los conflictos de ID o identidad activa se
bloquean. Los archivos históricos S2/S3/S4 sin Page Maps siguen siendo válidos.
El flujo nuevo no incluye bytes ni crea índices Page Map durante importación.

## Límites de S4.2

S4.2 no implementa PDF.js propio, JavaScript, OCR, extracción de texto,
embeddings, scraping ni overlay visual. No cambia Concepts legacy,
`source_documents`, `document_reading_state`, annotations, notes, evidence o
blobs existentes. El scroll y zoom del documento continúan siendo capacidades
nativas del visor de Streamlit.

La experiencia guiada posterior para asociar conceptos con estas evidencias se
documenta en [Asociación guiada de conceptos — S4.3](CONCEPT_LINKING_UX_S4_3.md).

## Navegación simplificada posterior

La organización de siete pestañas fue sustituida por **Biblioteca**, **Leer**,
**Cuaderno** y **Conocimiento**. Documents y Recent se integran en Biblioteca;
Workspace pasa a Leer; Notes y la revisión de anotaciones pasan a Cuaderno; la
revisión conceptual pasa a Conocimiento. Page Map y Maintenance se conservan
en **Configuración**, fuera de la navegación primaria. El contrato de página,
`st.pdf`, Notes & Evidence y Page Map no cambia. Véase
[Flujo simplificado de lectura](SIMPLIFIED_READING_WORKFLOW.md).

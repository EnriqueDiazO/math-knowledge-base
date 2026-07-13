# S4: anotaciones de lectura y evidencia conceptual

## Alcance

S4 añade una capa de trabajo intelectual sobre los Source Documents persistentes.
Permite guardar anotaciones manuales, subrayados lógicos, notas de lectura y
vínculos trazables hacia conceptos legacy. Todo el contenido S4 es metadata de
usuario: no altera el PDF, la Source, la Reference, el estado de lectura ni el
concepto enlazado.

Las responsabilidades permanecen separadas:

- S2 administra `source_documents`, integridad y blobs PDF;
- S3 administra `document_reading_state`, aperturas, estado y página actual;
- S4 administra anotaciones, notas y evidencia conceptual.

## Arquitectura

El dominio vive en `mathmongo.reading_annotations` y recibe siempre una base
MongoDB explícita. Contiene modelos estrictos, tres repositorios, un servicio de
aplicación y un plan de índices independiente. Importar sus módulos no conecta a
MongoDB, no crea colecciones, no crea directorios y no instala índices.

La UI vive en `editor.reading_annotations`. Reading Space sólo incorpora una
llamada mínima al panel **Notes & Evidence** para el Document seleccionado. El
panel usa IDs y metadata; no recibe ni conserva bytes del PDF.

## Colecciones y modelos

S4 crea tres colecciones independientes:

```text
document_annotations
reading_notes
concept_evidence_links
```

### `DocumentAnnotation`

Una anotación pertenece a un Document y a la Source autoritativa de ese
Document. Puede guardar página o etiqueta de página, una cita pegada manualmente,
comentario, color nominal y tags. Los tipos soportados son `highlight`,
`underline`, `comment`, `bookmark` y `question`.

`comment` y `question` requieren cuerpo; los demás tipos permiten un cuerpo
vacío. El número de página, cuando existe, es un entero positivo. Archivar
conserva la anotación y fija `archived_at`; reactivar la devuelve a `active`.

Los highlights y underlines son lógicos: describen Document, página y texto
citado, pero no almacenan coordenadas ni una selección binaria y no se dibujan
sobre el visor.

### `ReadingNote`

Una nota puede pertenecer al Document actual o sólo a una Source. También puede
referenciar una Reference compatible. Guarda título, cuerpo de texto, tags, tipo
y un rango opcional de páginas. Los tipos son `summary`, `idea`, `proof`,
`definition`, `question`, `todo`, `bibliography` y `general`.

Título y cuerpo son obligatorios. Si existen ambas páginas, el inicio no puede
ser posterior al final. El cuerpo se conserva como texto del usuario: MathMongo
no lo interpreta como HTML, no ejecuta Markdown y no compila LaTeX.

### `ConceptEvidenceLink`

Un vínculo identifica un concepto legacy mediante el par exacto
`(concept_legacy_id, concept_legacy_source)`. Su objetivo es exactamente uno de:

- una `DocumentAnnotation`;
- una `ReadingNote`;
- un Document directo con número de página.

Los tipos disponibles son `definition_source`, `theorem_source`,
`proof_source`, `example_source`, `motivation`, `citation`, `question` y
`related_context`. El servicio comprueba que el concepto exista y que Source,
Reference, Document, Annotation y Note sean coherentes. El vínculo sólo guarda
la identidad legacy: nunca actualiza `concepts` ni le agrega campos.

## Repositorios, búsqueda e índices

`AnnotationRepository`, `ReadingNoteRepository` y
`ConceptEvidenceRepository` son lazy y no crean índices. Ofrecen inserción,
consulta paginada, actualización de campos controlados, archivado y reactivación;
no exponen `$set` arbitrario y nunca borran físicamente.

La búsqueda se limita a metadata S4: título, cuerpo, cita manual, tags e identidad
del concepto. Las consultas tienen longitud acotada, escapan cualquier regex,
aplican paginación en MongoDB y usan un orden estable. No inspeccionan el PDF.

`ReadingAnnotationIndexManager` sólo aplica el plan aprobado tras una acción UI
explícita y confirmada. El plan contiene identidades únicas y accesos por
Document, Source, Reference, estado, tipo, tags, concepto y objetivo de evidencia.
Construir repositorios, abrir la app o importar un backup nunca instala índices
S4.

## Servicio

`ReadingAnnotationService` coordina las tres colecciones con Sources,
References, Source Documents y conceptos legacy. Antes de escribir valida:

- Source y Document existentes;
- Document activo para altas y cambios normales;
- Reference asociada a la Source y, cuando corresponde, al Document;
- asociación de Annotation o Note con el mismo contexto;
- existencia del concepto legacy;
- identidad de evidencia no duplicada;
- disponibilidad de los índices S4 aprobados.

Los resultados son tipados como `success`, `not_found`, `archived`,
`invalid_state`, `conflict`, `blocked` o `error`. Las lecturas de registros
archivados siguen disponibles; archivar nunca elimina contenido relacionado.

## UI Notes & Evidence

Reading Space muestra el panel para el Document seleccionado. Incluye:

- lista y filtros de anotaciones;
- lista y filtros de notas;
- formularios de alta y edición;
- archivado y reactivación;
- selector metadata-only de conceptos legacy;
- creación y listado de evidencia;
- navegación al Document y página sugerida.

En PDFs, la página actual S3 se usa únicamente como sugerencia editable. La cita
se pega manualmente. En recursos web no aparecen controles de página específicos
del PDF y pueden crearse comentarios o notas generales.

Las claves de sesión usan exclusivamente `reading_annotations_*`. Un cambio de
base, Source, Document, Annotation, Note o concepto limpia el contexto S4
incompatible. La sesión no guarda clientes, bases, paths, HTML, blobs ni bytes.

## Navegación

Una Annotation o ReadingNote ligada a Document puede seleccionar ese Document en
Reading Space. Si contiene página, la UI la propone en el campo manual de S3; no
intenta controlar el scroll de `st.pdf`. La evidencia permite volver a su
Annotation, Note o Document y muestra siempre la identidad legacy del concepto.

No se construyen rutas absolutas, `file://` ni aperturas mediante `webbrowser`.

## Backup portable

El backup añade opcionalmente:

```text
collections/document_annotations.json
collections/reading_notes.json
collections/concept_evidence_links.json
```

Las tres colecciones usan Extended JSON canónico y conservan `_id`, IDs de
dominio y timestamps. El import valida primero Sources, References, Documents,
estado S3, anotaciones, notas, conceptos y evidencia; sólo después escribe en el
orden de dependencia. Una importación idéntica posterior es no-op y cualquier
conflicto de ID o identidad exacta bloquea antes de escribir.

Los ZIP históricos y los backups S2/S3 sin colecciones S4 siguen siendo válidos.
El import no instala índices S4 y el estado S4 no contiene PDFs ni otros blobs.

## Seguridad y pruebas

Las pruebas usan bases fake o MongoDB temporal, XDG temporal, PDFs sintéticos y
conceptos temporales. Cubren modelos, repositorios, servicio, índices explícitos,
UI, navegación, búsqueda, portabilidad e idempotencia. La validación runtime
ejercita creación, edición, archivado/reactivación, evidencia, export/import y
cleanup sin tocar datos reales.

Las comprobaciones estáticas impiden introducir clientes de red, rutas locales,
PDF.js, OCR, extracción de texto o embeddings en los módulos S4. Wheel y sdist se
inspeccionan para excluir blobs, previews, PDFs, ZIPs, caches y datos del usuario.

## Limitaciones y fases futuras

S4 no implementa selección automática de texto, overlay visual sobre PDF,
coordenadas precisas, PDF.js, OCR, extracción de texto, búsqueda dentro del PDF,
embeddings ni scraping. Tampoco modifica `concepts`: `ConceptEvidenceLink` sólo
referencia conceptos legacy existentes.

Una fase futura podría añadir selección y geometría visual mediante un visor
especializado, pero deberá preservar las identidades lógicas y las barreras de
seguridad definidas aquí.

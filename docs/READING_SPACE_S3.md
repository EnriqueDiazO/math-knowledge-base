# S3: espacio de lectura avanzado para Source Documents

## Alcance

S3 añade **Reading Space** como página principal de MathMongo. La página navega
los Documents persistentes de S2, recuerda el progreso local y abre un único PDF
por vez mediante el visor interno compartido. S2 continúa siendo la autoridad
sobre metadata, asociaciones, integridad y blobs; S3 sólo describe la actividad
de lectura.

S3 no crea anotaciones, subrayados, notas de lectura, `ReadingNote` ni
`ConceptEvidenceLink`. Tampoco extrae texto, ejecuta OCR, crea embeddings,
implementa búsqueda dentro del PDF o modifica `concepts`. Esas capacidades no
forman parte de esta fase y las anotaciones/evidencia quedan reservadas para S4.

## Arquitectura

El dominio vive en `mathmongo.reading_space`, separado de
`mathmongo.source_documents`:

- modelos estrictos para estado, filtros y resultados;
- repositorio de `document_reading_state`;
- repositorio read-only para consultar Documents con su estado efectivo;
- servicio que coordina Sources, References y el servicio seguro de S2;
- plan de índices S3 explícito e independiente.

La UI vive en `editor.reading_space`. El router monolítico sólo incorpora la
opción de navegación y despacha al renderer. Importar módulos no conecta a
MongoDB, no crea colecciones, no aplica índices y no crea directorios.

## Modelo `document_reading_state`

Cada documento puede tener como máximo un estado por `(user_scope,
document_id)`. En S3 el scope de usuario es `local`. La colección guarda:

- `schema_version`;
- `reading_state_id` con formato `read_<uuid4>`;
- `document_id`, `source_id` y `reference_id` opcional;
- `user_scope` y `status`;
- `current_page` y `total_pages` opcionales;
- primera/última apertura y finalización;
- contador de aperturas y tags de lectura;
- timestamps UTC de creación y actualización.

Los estados válidos son `unread`, `in_progress`, `completed` y `deferred`.
Las páginas, si existen, comienzan en 1 y la página actual no puede superar el
total. `completed_at` sólo puede conservarse en estado `completed`. El modelo
rechaza campos extra y nunca admite bytes, paths, HTML, texto extraído,
selecciones o anotaciones.

`source_id` y `reference_id` son copias controladas para validar asociación y
filtrar. El servicio exige que coincidan con el Source Document autoritativo;
no se escriben dentro de Source, Reference ni Concept.

## Repositorios e índices

`ReadingStateRepository` recibe una base explícita y ofrece upsert controlado,
consulta por Document, recientes, lista por Source, actualización de página y
estado, registro de apertura, reset y conteos. No acepta `$set` arbitrario, no
materializa la colección al construirse y no borra Documents ni blobs.

La lista global usa un repositorio read-only con `$lookup` entre
`source_documents` y el estado `local`. Un Document sin fila persistida se
presenta como `unread` sin crearla. Los filtros y la paginación se ejecutan en
MongoDB y la proyección no contiene bytes ni paths.

El plan de índices incluye identidades únicas para `reading_state_id` y
`(user_scope, document_id)`, más accesos por Source/status, última apertura,
Reference y actualización. Consultar el plan es read-only. Sólo una acción
explícita y confirmada de la UI lo aplica; abrir la app, construir un repositorio
o importar un backup nunca aplica índices S3.

## Reading Space UI

La página contiene:

- filtros por Source, Reference, tipo y estado documental, estado de lectura,
  tags y título;
- orden por recientes, título, Source o estado;
- lista metadata-only con acciones de apertura, completed, deferred y reset;
- historial **Recent Documents**;
- resumen compacto por Source;
- panel PDF o web para el Document seleccionado;
- estado explícito de los índices S3 y su inicialización confirmada.

El estado de sesión usa exclusivamente claves `reading_space_*`. Cambiar de
base, scope, Source o Document invalida el target y el preview correspondiente.
No se guardan clientes, bases, servicios, paths ni lotes de blobs en la sesión;
sólo pueden permanecer temporalmente los bytes del PDF actualmente abierto.

Desde **Edit / Analyze Source → Documents**, la acción **Open in Reading
Space** transfiere únicamente los IDs lógicos y solicita navegación. No lee el
blob ni abre una URL desde la página Source.

## Estado de lectura, página y recientes

Abrir un PDF activo comprueba primero la integridad S2, recupera sus bytes
verificados y sólo después registra la apertura. La primera apertura fija
`first_opened_at`; cada apertura incrementa `open_count` y actualiza
`last_opened_at`. La primera lectura y una lectura deferred pasan a
`in_progress`; reabrir una completada conserva su finalización.

**Current page** es un entero guardado explícitamente. No intenta sincronizarse
con el scroll del componente PDF. Funciona con `total_pages=null` y aparece en
la lista y en recientes. Marcar completed establece `completed_at`; deferred lo
limpia. Reset elimina sólo el estado S3 y vuelve al estado efectivo `unread`.

Recent Documents lista las últimas aperturas del scope local. Omite estados cuyo
Document ya no existe y advierte/bloquea la apertura normal de Documents
archivados. El resumen de Source calcula total, PDF, web, los cuatro estados y
la última apertura sin modificar Source ni Document.

## PDF reader

S3 reutiliza `SourceDocumentService` para integridad y lectura, y el ciclo de
`editor.pdf_preview` para el visor. Los bytes verificados se entregan a:

```python
st.pdf(pdf_bytes, height=800)
```

El botón de descarga recibe exactamente el mismo objeto de bytes. La identidad
del preview incluye base, scope, Source, Document, versión y SHA. No se copia el
PDF a runtime, no se crea otro blob y no se usan `file://`, `webbrowser`,
`Path.as_uri`, iframes, HTML o PDF.js propio.

## Web reader

Seleccionar un Document web sólo muestra metadata, URL raw/normalizada y estado.
La apertura se registra mediante una confirmación explícita; después se revela
el botón de enlace externo. El backend no realiza requests, scraping, preview
remoto, descarga, resolución DOI ni captura de página.

## Backup portable

El backup añade opcionalmente:

```text
collections/document_reading_state.json
```

Se usa Extended JSON canónico y se conservan `_id`, `reading_state_id`, IDs y
timestamps. Antes de escribir, el import valida el Document asociado, la
coincidencia de Source/Reference y las identidades `reading_state_id` y
`(user_scope, document_id)`. Una segunda importación idéntica es no-op y un
conflicto bloquea. El import no crea índices S3 y no añade blobs.

Los ZIP históricos y los ZIP S2 sin reading state siguen siendo compatibles.
Session state, PDFs adicionales, previews, anotaciones y notas nunca se
exportan.

## Seguridad, pruebas y validación

Las pruebas S3 usan bases fake o temporales, XDG temporal, Sources/References
fake y PDFs sintéticos. Cubren modelo, repositorios, índices explícitos,
servicio, filtros, navegación, visor/descarga, web sin red, recientes, resumen,
estado de sesión y portabilidad. Las comprobaciones estáticas impiden introducir
aperturas locales, clientes HTTP, anotaciones o escritura de bytes en MongoDB.

La validación final se ejecuta con bases MongoDB, XDG, puerto Streamlit y
artefactos de build temporales. Debe demostrar apertura PDF/web, progreso,
recentes, entrada desde Source, export/import idempotente, wheel/sdist completos
y cleanup, además de comparar los fingerprints de las bases, blobs y ZIP reales
antes y después.

## Limitaciones

- La página guardada es metadata manual y no controla el scroll real de
  `st.pdf`.
- No se descarga ni se previsualiza contenido web remoto.
- Sólo existe el scope de usuario local en S3.
- No hay reemplazo/versionado de PDF ni borrado físico de blobs.
- No hay anotaciones, subrayados, notas, OCR, extracción de texto, búsqueda
  interna ni enlaces de evidencia a conceptos.

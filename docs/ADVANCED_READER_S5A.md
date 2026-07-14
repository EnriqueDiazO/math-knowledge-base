# Lector PDF avanzado aislado — S5A

## Objetivo y estado de la fase

S5A incorpora un prototipo de lectura especializado, servido como aplicación
web local independiente de Streamlit. Su propósito es demostrar que PDF.js
puede ofrecer navegación real, miniaturas, búsqueda, text layer y selección de
texto sin duplicar el dominio ni el almacenamiento de MathMongo.

S5A no reemplaza todavía el Reading Space. La aplicación principal continúa
siendo Streamlit, `st.pdf` permanece como visor y fallback, y el lector avanzado
se abre únicamente mediante una acción explícita para Documents PDF. Esta fase
no implementa anotación visual persistente ni asociación de conceptos desde el
nuevo frontend.

Este documento describe el contrato esperado de S5A. Los resultados de pruebas,
E2E, build y empaquetado deben registrarse en el reporte de validación de la fase;
no se presuponen aquí.

## Arquitectura híbrida

```text
Streamlit / Reading Space
        │
        │ URL local con document_id únicamente
        ▼
Advanced Reader (127.0.0.1:8766)
  ├── React + TypeScript + PDF.js
  ├── API HTTP same-origin
  └── assets compilados locales
        │
        │ contratos de transporte acotados
        ▼
Servicios existentes de MathMongo
  ├── SourceDocumentService / storage S2
  ├── ReadingSpaceService S3
  ├── DocumentPageMapService
  └── repositorios Source / Reference read-only
        │
        ├── MongoDB existente
        └── blobs XDG content-addressed existentes
```

El frontend no conoce MongoDB, rutas XDG, `logical_path`, HOME, credenciales ni
paths de blobs. Solicita un Document exclusivamente por `document_id`; la API
resuelve y valida todo acceso. Frontend y API comparten origen en producción, no
se habilita CORS global y no hay recursos remotos en runtime.

La implementación se mantiene aislada en dos raíces:

```text
mathmongo/advanced_reader/                 API, launcher y seguridad
mathmongo/advanced_reader/static/
  advanced_reader/                        build de producción versionado
frontend/advanced-reader/                 fuente React/TypeScript y tests
```

No existía un frontend reutilizable en el repositorio al iniciar S5A. El HTML y
JavaScript previos estaban embebidos en vistas Python y no constituían una
arquitectura Node compartible.

## Entorno auditado

El entorno de trabajo de S5A dispone de:

| Herramienta | Versión auditada |
| --- | --- |
| Python de `mathdbmongo` | 3.10.12 |
| Streamlit | 1.59.2 |
| Node | 24.15.0 |
| npm | 11.12.1 |
| Corepack | 0.34.6 |
| Google Chrome del sistema | 149.0.7827.102 |
| FastAPI | 0.139.0 |
| Uvicorn | 0.51.0 |
| Starlette | 1.3.1 |

Las dependencias frontend directas quedan fijadas por `package-lock.json`:
React y React DOM 19.2.7, `pdfjs-dist` 6.1.200, Vite 8.1.4 y
TypeScript 6.0.3. El inventario completo, incluidas dependencias de pruebas,
licencias y fuentes, está en
[`THIRD_PARTY_ADVANCED_READER.md`](THIRD_PARTY_ADVANCED_READER.md).

No se instala ninguna herramienta global. Playwright, cuando se usa para E2E,
debe apuntar al Chrome ya instalado y no descargar Chromium, Firefox o WebKit.

## Backend preservado

S5A añade transporte HTTP y composición; no cambia:

- modelos Pydantic, IDs o schemas persistentes;
- colecciones, índices ni migraciones;
- `Source`, `Reference`, `SourceDocument` o `DocumentVersion`;
- `DocumentReadingState` o `DocumentPageMap`;
- `DocumentAnnotation`, `ReadingNote` o `ConceptEvidenceLink`;
- documentos legacy de `concepts`;
- deduplicación SHA, layout de blobs, export/import o manifiestos.

No se crea una colección para PDFs, selecciones, texto extraído, búsqueda o
progreso. La única escritura permitida es guardar una PDF page mediante
`ReadingSpaceService.update_current_page(...)`. Metadata, Page Map e integridad
son consultas read-only; importar la app no conecta y consultar health sólo
ejecuta un ping read-only. Ninguna de esas acciones crea directorios,
colecciones o índices.

## Launcher y configuración

El servidor se inicia explícitamente:

```bash
mathdbmongo/bin/python -m mathmongo.advanced_reader \
  --host 127.0.0.1 \
  --port 8766 \
  --database MathV0 \
  --log-level info
```

También puede usarse `make advanced-reader`. `make run` conserva su semántica y
no se inicia ni se detiene ningún proceso desde Streamlit.

Opciones mínimas:

- `--host`: sólo `127.0.0.1`, `localhost` o `::1`; `0.0.0.0` y hosts remotos se
  rechazan;
- `--port`: entero entre 1 y 65535, con default 8766;
- `--database`: base explícita o la configurada por MathMongo;
- `--mongo-uri`: override opcional resuelto por la configuración existente y
  siempre redactado en errores;
- `--log-level`: nivel Uvicorn permitido y acotado.

La configuración tipada usa `advanced_reader_enabled`,
`advanced_reader_host`, `advanced_reader_port` y
`advanced_reader_public_url`. El default público es
`http://127.0.0.1:8766`; `MATHMONGO_ADVANCED_READER_URL` puede cambiar esa base
para el enlace de Streamlit, pero sólo se aceptan URLs HTTP de loopback sin
credenciales, query ni fragmento.

El launcher no abre navegador, no imprime la URI MongoDB, HOME, rutas XDG o
bytes del PDF y termina normalmente con `Ctrl+C`.

## API HTTP

Todas las rutas de datos viven bajo `/api/advanced-reader`. Las respuestas JSON
son modelos de transporte con campos extra prohibidos; nunca serializan modelos
Mongo completos.

| Método y ruta | Función | Escritura |
| --- | --- | --- |
| `GET /health` | estado acotado y disponibilidad del build | no |
| `GET /documents/{document_id}` | metadata, integridad y capacidades | no |
| `GET /documents/{document_id}/pdf` | PDF verificado con Range | no |
| `GET /documents/{document_id}/reading-state` | estado S3 efectivo | no |
| `PUT /documents/{document_id}/reading-state/page` | guardar PDF page | sólo S3 |
| `GET /documents/{document_id}/page-label?pdf_page=N` | etiqueta Page Map | no |

### Health

La respuesta no inspecciona ni expone infraestructura innecesaria:

```json
{
  "status": "ok",
  "service": "mathmongo-advanced-reader",
  "database": "MathV0",
  "frontend_ready": true
}
```

No contiene hostname, PID, versiones internas, URI ni filesystem. La ausencia
del build estático se expresa con `frontend_ready=false` o con el error tipado
`frontend_not_built` al solicitar una ruta de frontend; nunca provoca un build
implícito.

### Metadata del Document

`GET /documents/{document_id}` valida el ID, existencia, estado activo,
`kind=pdf`, Source, Reference opcional, versión actual e integridad antes de
responder. El contrato incluye:

- `document_id`, título, kind y status;
- nombre e ID lógico de Source;
- título e ID lógico de Reference cuando exista;
- `version_id`, SHA-256, tamaño y nombre original proyectado como texto;
- estado de lectura efectivo y página actual;
- Book page actual cuando Page Map pueda resolverla;
- capacidades realmente implementadas.

No incluye `logical_path`, path absoluto, HOME, URI, bytes, descripción extensa
ni documento Mongo crudo. Un Document web produce `document_not_pdf`; la API no
abre su URL ni realiza requests externos.

Las capacidades S5A son explícitas:

```json
{
  "page_navigation": true,
  "thumbnails": true,
  "zoom": true,
  "rotate": true,
  "text_search": true,
  "text_selection": true,
  "temporary_selection_geometry": true,
  "persistent_highlights": false,
  "persistent_underlines": false,
  "concept_linking": false
}
```

### Reading State

El frontend guarda posición sólo al pulsar **Guardar posición**:

```http
PUT /api/advanced-reader/documents/doc_.../reading-state/page
Content-Type: application/json

{"pdf_page": 9}
```

`pdf_page` es un entero desde 1 y, cuando el total es conocido, no puede
superarlo. Book page nunca se interpreta como `current_page`. La API llama al
servicio S3; no hace `$set`, no autoescribe durante scroll y no crea un estado
paralelo. `reading_position_saved` se emite sólo después de un resultado
exitoso.

### Page Map

`GET /documents/{document_id}/page-label?pdf_page=9` delega en
`DocumentPageMapService.compute_page_label(...)`:

```json
{
  "pdf_page": 9,
  "book_page_label": "1",
  "display_label": "Book page 1 · PDF page 9"
}
```

Sin Page Map activo, el endpoint responde de forma utilizable con
`book_page_label=null` y `display_label="PDF page 9"`. No inicializa índices,
crea mapas ni bloquea el lector. En navegación, la UI establece primero esa
etiqueta PDF de fallback y consulta Page Map después; si la consulta falla,
conserva `PDF page N` y la lectura continúa. No inventa una Book page, no muestra
un error global por metadata auxiliar y no intenta reparar o crear el mapa.

### Errores

Los errores usan un envelope acotado con `code`, mensaje seguro y request ID;
no incluyen traceback, query, ruta, URI o contenido:

```json
{
  "error": {
    "code": "document_not_pdf",
    "message": "The selected Document is not a PDF.",
    "request_id": "opaque-request-id"
  }
}
```

Códigos públicos: `invalid_document_id`, `document_not_found`,
`document_archived`, `document_not_pdf`, `integrity_error`, `blob_missing`,
`invalid_range`, `multiple_ranges_not_supported`, `page_invalid`,
`database_unavailable`, `frontend_not_built` e `internal_error`. Los mensajes
son estables y no reproducen excepciones internas.

## Entrega segura del PDF y HTTP Range

`GET /documents/{document_id}/pdf` nunca acepta un path. La API obtiene la
versión actual del Document, deriva el blob exclusivamente desde su SHA y aplica
las garantías S2 antes de enviar headers:

1. ID, Document activo, Source y `kind=pdf` válidos.
2. Versión actual y `logical_path` canónico coherentes con el SHA.
3. Todos los componentes dentro del root XDG controlado y sin symlinks.
4. Hoja regular, permisos y tamaño esperados.
5. cabecera `%PDF-` y SHA-256 coincidente, calculado por bloques sin cargar el
   archivo completo en memoria;
6. descriptor estable y comprobación de identidad/tamaño alrededor de la
   lectura para detectar sustituciones cuando el sistema lo permita.

Sin `Range`, la respuesta es `200`. Con un único rango válido es `206`. Se
admiten `bytes=start-end`, `bytes=start-` y `bytes=-suffix`. Rangos fuera de
límite o sintácticamente inválidos devuelven `416 invalid_range`; una lista de
rangos devuelve `416 multiple_ranges_not_supported`. En ambos casos se usa
`Content-Range: bytes */<size>` cuando el tamaño es conocido.

Headers de éxito:

- `Content-Type: application/pdf`;
- `Content-Disposition: inline; filename="<nombre-saneado>"`;
- `Accept-Ranges: bytes`;
- `Content-Length` exacto;
- `Content-Range` en 206;
- `ETag` fuerte derivado del SHA-256;
- `X-Content-Type-Options: nosniff`;
- `Cache-Control: no-store, private`.

La lectura se transmite en bloques acotados y cierra el descriptor en éxito,
cancelación o error. No usa `file://`, redirect local, `Path.as_uri()` ni una
copia temporal del PDF. Los detalles y el modelo de amenazas están en
[`ADVANCED_READER_SECURITY.md`](ADVANCED_READER_SECURITY.md).

Range evita materializar el archivo completo en memoria, pero no convierte la
verificación en una operación proporcional al rango: cada `GET` o `HEAD` vuelve
a recorrer el PDF completo para comprobar SHA-256 antes de enviar la respuesta.
S5A tampoco configura un límite explícito de concurrencia ni un timeout de
lectura en la aplicación/Uvicorn. Finalmente, si el archivo cambia durante el
streaming y la comprobación final lo detecta después de enviar los headers, el
servidor puede cortar la conexión, pero ya no puede responder con un envelope
JSON `integrity_error`.

La política de caché del proceso local distingue rutas: `/` y `/reader` usan
`no-cache`; `/assets/` usa `public, max-age=31536000, immutable` porque los
nombres están versionados por hash; toda ruta `/api/`, incluido el PDF y sus
respuestas 206, usa `no-store, private`.

## Frontend React/TypeScript

La URL canónica es:

```text
http://127.0.0.1:8766/reader?document_id=doc_...
```

El único contexto aceptado por query es un `document_id` válido. Metadata, PDF,
estado y Page Map se obtienen mediante rutas relativas same-origin. No existe un
input para URL, path local, Mongo URI o host.

La pantalla distingue `loading`, `ready`, error documental, error de
integridad, API no disponible y Document web no soportado. Nunca deja un canvas
vacío sin explicación.

### Layout y accesibilidad

El layout tiene tres áreas, con sidebar e inspector ocultables:

```text
┌──────────────────────────────────────────────────────────────┐
│ Toolbar fija                                                 │
├───────────────┬──────────────────────────┬───────────────────┤
│ Miniaturas    │ PDF + text layer         │ Document/selección│
└───────────────┴──────────────────────────┴───────────────────┘
```

La toolbar ofrece sidebar, anterior/siguiente, primera/última, input y total de
páginas, zoom, tamaño real, fit width, fit page, rotación en ambos sentidos,
búsqueda y guardado explícito. Los límites y capabilities controlan `disabled`.
Los controles tienen nombre accesible, foco visible y navegación por teclado;
la UI evita scroll horizontal global y adapta los paneles a pantallas estrechas.

PDF page y Book page nunca se mezclan. La página visible informada por PDF.js es
la fuente de verdad del frontend; cada cambio actualiza toolbar, miniatura,
inspector y consulta de Page Map, sin persistir automáticamente.

### PDF.js

`pdfjs-dist` se empaqueta localmente junto con su worker. El frontend habilita:

- visor y event bus de PDF.js;
- thumbnails;
- link service restringido;
- text layer seleccionable;
- annotation layer con `AnnotationMode.ENABLE`, sin `ENABLE_FORMS`, y editor de
  anotaciones en `AnnotationEditorType.NONE`;
- find controller para búsqueda en memoria.

El worker no se obtiene de CDN. `getDocument` fija `isEvalSupported=false`,
`enableXfa=false` y `stopAtErrors=true`. La aplicación no crea ni entrega un
scripting manager al viewer, por lo que el soporte de scripting presente en la
dependencia no queda conectado a la instancia S5A. Los formularios interactivos
no se renderizan porque no se usa `AnnotationMode.ENABLE_FORMS`.

El link service usa `externalLinkEnabled=false`, `externalLinkTarget=NONE` y
`enableAutoLinking=false`; el viewer cancela además clicks no internos. La
resolución de attachments se sustituye por una operación sin contenido y la UI
no ofrece descarga o ejecución. CSP mantiene scripts, worker y conexiones en el
mismo origen, bloquea objetos y formularios, y no habilita `unsafe-eval`.

Éste es hardening por configuración y defensa en profundidad, no una afirmación
de seguridad absoluta frente a PDFs maliciosos. Las pruebas funcionales y E2E
sintéticas no sustituyen un corpus hostil ni eliminan el riesgo residual de
PDF.js o del navegador.

### Navegación, zoom, rotación y búsqueda

Anterior/siguiente, primera/última, input y click de miniatura validan el rango
`1..total_pages`. Zoom usa límites seguros e informa escala; fit width, fit page
y tamaño real son modos diferenciados. La rotación se normaliza a
`0|90|180|270` y actualiza miniaturas, text layer y selección.

La búsqueda usa exclusivamente el find controller en memoria: siguiente,
anterior, estado buscando/sin resultados y contador cuando PDF.js lo entrega.
La query no sale del navegador, no se registra, no se indexa y no se persiste.

## Selección textual efímera

La text layer permite seleccionar texto de una sola página. El frontend
normaliza whitespace, limita el texto y convierte los rectángulos visibles a
coordenadas `[0,1]` relativas a la página. No conserva coordenadas de pantalla
ni viewport absoluto.

El inspector muestra texto, PDF page, Book page, número de rectángulos y estado.
Sus únicas acciones son **Limpiar selección** y **Mostrar detalles técnicos**.
No ofrece guardar highlight, subrayar, crear Annotation ni asociar concepto.

Una selección multipágina conserva sólo un preview textual acotado, marca
`cross_page=true`, avisa al usuario y no produce geometría utilizable. Si no se
puede determinar la página, no se inventa: la geometría se descarta.

Toda selección vive en memoria del navegador. No se envía a la API, MongoDB,
logs, analytics, clipboard ni session state persistente. Su schema detallado y
ciclo de vida están en
[`ADVANCED_READER_EVENT_CONTRACT.md`](ADVANCED_READER_EVENT_CONTRACT.md).

## Integración con Streamlit

Reading Space mantiene `st.pdf`, descarga y controles existentes. Para un
Document PDF activo añade **Abrir lector avanzado**, que construye:

```text
<base-validada>/reader?document_id=<id-codificado>
```

No añade database, Source, Reference, Mongo URI ni path. El link no abre una
pestaña sin acción del usuario y nunca inicia el servidor. Un health check corto
muestra disponible, no iniciado o timeout; un Document web aparece como no
compatible. Si el servicio no está activo se muestra:

> Ejecuta `make advanced-reader` en otra terminal.

La indisponibilidad del prototipo no degrada el lector Streamlit.

## Build, paquete y ejecución instalada

El frontend dispone de scripts `dev`, `typecheck`, `lint`, `test` y `build`.
`npm ci` usa el lockfile; no se usa `npx` para descargar herramientas ni se
requiere `node_modules` en runtime. Vite genera nombres con hash y publica de
forma explícita en el directorio estático del paquete Python.

Secuencia de build:

```bash
cd frontend/advanced-reader
npm ci
npm run typecheck
npm run lint
npm run test
npm run build
```

Después, Poetry construye wheel y sdist fuera del checkout. Ambos deben incluir
API, launcher, HTML, JS, CSS, worker PDF.js y notices/licencias. Deben excluir
`node_modules`, source maps no aprobados, PDFs, blobs, `.env`, cachés, logs,
bases y paths de usuario.

La instalación offline se valida desde el wheel con `--no-index --no-deps` en
un target temporal. Desde esa instalación se importa la factory sin conexión,
se inicia el servidor con HOME/XDG y Mongo temporales, se consulta health, se
carga el frontend y se sirve exclusivamente un PDF sintético temporal. El
runtime no debe escribir dentro del paquete instalado.

## Estrategia de pruebas

La cobertura prevista se divide en:

- Python: imports sin conexión, factory inyectada, metadata y errores acotados,
  integridad, symlink/path traversal, streaming completo, las tres formas de
  Range, 416, headers, estado S3 y Page Map opcional;
- frontend: estados, toolbar, navegación, miniaturas, zoom/fit/rotación,
  búsqueda, metadata, selección y ausencia de acciones persistentes;
- seguridad estática: entrypoint propio sin sinks HTML ni telemetría, bundle sin
  URI/path local, CDN, ejecución dinámica, endpoints analytics, PDFs, source
  maps o datos de usuario; los chunks de terceros se inspeccionan por separado;
- navegador real: Chrome del sistema, Mongo/XDG/PDF sintéticos, requests Range,
  búsqueda y selección reales, guardado/recarga de posición, consola y red;
- regresión: Source Documents, Reading Space, Page Map, PDF preview, S4.3 y
  fallback `st.pdf`;
- distribución: contenido de wheel/sdist, rebuild desde sdist e instalación
  offline temporal.

Los tests unitarios pueden acotar PDF.js con mocks, pero la prueba de text layer,
selección y Range no se declara demostrada hasta observarla en el navegador
real. Todos los procesos, puertos, bases, XDG y perfiles de Chrome temporales se
eliminan al terminar.

## Limitaciones de S5A

- No hay highlights ni underlines persistentes.
- No hay overlays persistentes ni rehidratación visual.
- No se modifica el PDF ni se escriben anotaciones PDF estándar.
- No se crean `DocumentAnnotation`, `ReadingNote` o `ConceptEvidenceLink`.
- No hay Concept Linking dentro del lector avanzado.
- La selección sólo se inspecciona en memoria.
- No hay OCR, extracción persistente, índice, embeddings o búsqueda semántica.
- No hay scraping ni requests a Documents web.
- No hay cuentas, colaboración, nube, telemetría o analytics.
- El servidor sólo escucha en loopback y no ofrece acceso remoto.
- `st.pdf` continúa disponible y es el fallback estable.

## Continuidad después de S5A

S5B requiere una decisión separada antes de persistir cualquier representación
visual: identidad de versión, geometría canónica, lifecycle, rehidratación,
portabilidad y compatibilidad con rotación/zoom. S5A no anticipa ese schema ni
crea una colección provisional.

La asociación de una selección visual con conceptos queda explícitamente para
S5C. Hasta entonces S4.3 continúa siendo el flujo estable de Concept Linking y
opera desde el Reading Space existente.

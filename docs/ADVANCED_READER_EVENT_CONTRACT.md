# Contrato de eventos del Advanced Reader — S5A

## Alcance

Este contrato define los eventos efímeros del frontend del lector avanzado.
Los eventos coordinan componentes React, PDF.js, toolbar e inspector dentro de
la misma aplicación. No son analytics, no constituyen una API pública remota y
no se envían automáticamente al backend.

En S5A sólo la acción que termina en `reading_position_saved` provoca una
escritura: un `PUT` explícito que delega en `ReadingSpaceService`. Emitir un
evento no persiste por sí mismo. Todos los demás eventos permanecen en memoria
del navegador y se descartan al recargar, cerrar o cambiar de Document.

## Envelope y reglas comunes

Todo evento pertenece a la unión discriminada `AdvancedReaderEventV1` y contiene:

| Campo | Tipo | Regla |
| --- | --- | --- |
| `schema_version` | literal `1` | obligatorio; otra versión se rechaza |
| `event_type` | string enum | uno de los diez tipos definidos abajo |
| `document_id` | string | ID de dominio validado; nunca `_id` Mongo |
| `version_id` | string o `null` | versión PDF validada; null sólo antes de cargarla |

Reglas globales:

- el objeto debe ser JSON-serializable y no contener valores no finitos;
- se prohíben campos extra en los límites entre módulos;
- ningún evento contiene URI, path, `logical_path`, HOME, credenciales, bytes,
  documento Mongo, Source/Reference completos o stack trace;
- ningún payload supera 64 KiB serializado;
- no se escribe en `localStorage`, `sessionStorage`, IndexedDB, cookies, URL,
  clipboard o logs de producción;
- no existe un collector, endpoint de telemetría ni envío a terceros;
- al cambiar de Document se descartan cola, búsqueda y selección actuales.

Los handlers pueden usar los eventos para actualizar estado React. No deben
reenviarlos como `postMessage` a otro origen ni convertirlos en eventos DOM
globales con datos sensibles.

## Resumen de privacidad y persistencia

| Evento | Puede contener texto del PDF | Backend | Persistencia permitida |
| --- | --- | --- | --- |
| `document_loaded` | no | ninguna | ninguna |
| `document_load_failed` | no | ninguna | ninguna |
| `page_changed` | no | lectura Page Map opcional | ninguna |
| `zoom_changed` | no | ninguna | ninguna |
| `rotation_changed` | no | ninguna | ninguna |
| `search_started` | query local acotada | ninguna | ninguna |
| `search_result` | no | ninguna | ninguna |
| `text_selection` | sí, acotado | prohibido | ninguna |
| `selection_cleared` | no | ninguna | ninguna |
| `reading_position_saved` | no | PUT S3 explícito | sólo `current_page` S3 |

La query y el texto seleccionado son datos potencialmente sensibles. No se
incluyen en logs, mensajes de error, request IDs ni detalles técnicos por
defecto. El inspector técnico puede mostrar el payload de selección únicamente
por acción explícita y dentro del navegador.

## `document_loaded`

Se emite una vez que metadata y PDF.js han validado el Document y conocen el
total de páginas.

```json
{
  "schema_version": 1,
  "event_type": "document_loaded",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "total_pages": 306,
  "initial_pdf_page": 9
}
```

| Campo específico | Tipo y límites |
| --- | --- |
| `total_pages` | entero `>=1` dentro del rango seguro de JavaScript |
| `initial_pdf_page` | entero `1..total_pages` |

No contiene título, SHA, filename, Source ni Reference. Es local y no se
persiste. Si PDF.js no completa la carga, se emite `document_load_failed` en su
lugar. Este evento confirma estructura y total de páginas, no que un canvas ya
tenga píxeles: la preparación visual termina sólo después de un
`pagerendered` comprobado.

## `document_load_failed`

Representa un fallo esperado y saneado durante metadata, integridad o carga
PDF.js.

```json
{
  "schema_version": 1,
  "event_type": "document_load_failed",
  "document_id": "doc_...",
  "version_id": null,
  "error_code": "integrity_error"
}
```

`error_code` sólo puede ser un código público de la API o uno de
`api_unavailable`, `pdfjs_load_error`, `page_render_failed` y
`unsupported_document`. `page_render_failed` puede seguir a
`document_loaded`: significa que la estructura se cargó, pero ninguna página
ha superado la comprobación visual. No se incluye `Error.message`, response body
crudo, traceback, URL completa o path. El evento sirve para seleccionar un
estado visible; no se registra ni persiste.

## `page_changed`

Se emite cuando PDF.js confirma que la página visible cambió, incluida la carga
inicial.

```json
{
  "schema_version": 1,
  "event_type": "page_changed",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "pdf_page": 9,
  "total_pages": 306,
  "book_page_label": "1",
  "origin": "thumbnail"
}
```

| Campo específico | Tipo y límites |
| --- | --- |
| `pdf_page` | entero `1..total_pages` |
| `total_pages` | entero `>=1` |
| `book_page_label` | string `<=64` o `null`; texto plano |
| `origin` | `initial`, `toolbar`, `page_input`, `thumbnail`, `keyboard`, `pdfjs` |

La Book page se obtiene read-only y puede llegar después como actualización del
estado de UI; nunca sustituye `pdf_page`. El evento no guarda posición. Si hay
una selección de otra página, el cambio emite además `selection_cleared`.

## `zoom_changed`

```json
{
  "schema_version": 1,
  "event_type": "zoom_changed",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "scale": 1.25,
  "mode": "custom"
}
```

`scale` es finito y permanece entre los límites operativos del visor; el
contrato S5A usa `0.25..5.0`. `mode` es `custom`, `actual_size`, `fit_width` o
`fit_page`. Zoom no modifica geometría normalizada ya calculada ni produce una
escritura.

## `rotation_changed`

```json
{
  "schema_version": 1,
  "event_type": "rotation_changed",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "rotation": 90,
  "direction": "clockwise"
}
```

`rotation` debe ser `0`, `90`, `180` o `270`; `direction` es `clockwise` o
`counterclockwise`. La rotación actualiza canvas, text layer y thumbnails. Una
selección previa se limpia antes de presentar geometría bajo otra rotación.

## `search_started`

```json
{
  "schema_version": 1,
  "event_type": "search_started",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "query": "compactness",
  "case_sensitive": false,
  "whole_words": false,
  "direction": "next"
}
```

La query se recorta, conserva texto plano y tiene un máximo de 256 caracteres
Unicode. Una query vacía cancela búsqueda y no emite este evento. `direction`
es `next` o `previous`. `whole_words` sólo se activa si el find controller de la
versión PDF.js lo soporta de forma estable.

Aunque aparece en el evento local para coordinar el controlador, `query` no se
envía a la API, no se imprime, no se guarda ni se usa para construir un índice.

## `search_result`

```json
{
  "schema_version": 1,
  "event_type": "search_result",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "status": "found",
  "current_match": 2,
  "total_matches": 8
}
```

`status` es `searching`, `found`, `not_found` o `cancelled`.
`current_match` y `total_matches` son enteros no negativos o `null` cuando
PDF.js todavía no entrega conteos. Si ambos existen, `current_match` está entre
1 y `total_matches`. El evento no repite la query ni fragmentos encontrados.

## `text_selection`

Este evento es el único que puede contener contenido del PDF. Es estrictamente
efímero.

```json
{
  "schema_version": 1,
  "event_type": "text_selection",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "pdf_page": 9,
  "selected_text": "Every compact subset...",
  "rects_normalized": [
    {
      "x": 0.12,
      "y": 0.31,
      "width": 0.42,
      "height": 0.03
    }
  ],
  "rotation": 0,
  "scale": 1.25,
  "cross_page": false,
  "geometry_status": "valid"
}
```

### Texto

- se toma únicamente de un `Selection` contenido en la text layer del visor;
- se normalizan secuencias de whitespace a un espacio y se aplica `trim`;
- el máximo es 4096 caracteres Unicode después de normalizar;
- una selección vacía emite `selection_cleared`, no `text_selection`;
- no se interpreta como HTML y nunca se inserta con `dangerouslySetInnerHTML`.

### Geometría

Cada rectángulo contiene números finitos:

```text
0 <= x <= 1
0 <= y <= 1
0 < width <= 1
0 < height <= 1
x + width <= 1
y + height <= 1
```

La lista contiene como máximo 64 rectángulos no vacíos. Se obtiene al
intersectar `Range.getClientRects()` con el rectángulo de la página que contiene
la text layer y normalizar:

```text
x      = (rect.left - page.left) / page.width
y      = (rect.top  - page.top)  / page.height
width  = rect.width  / page.width
height = rect.height / page.height
```

Los resultados se recortan a `[0,1]`; se descartan rectángulos fuera de página,
no finitos o de área cero. No se conservan `clientX`, `screenX`, dimensiones de
ventana, posición global, scroll ni rectángulos DOM absolutos. `rotation` usa el
mismo enum del visor y `scale` es sólo contexto técnico, no una coordenada.

### Selección multipágina o no resoluble

Una selección que toca más de una página usa:

```json
{
  "pdf_page": null,
  "rects_normalized": [],
  "cross_page": true,
  "geometry_status": "cross_page"
}
```

Puede conservar el preview textual acotado para mostrar la advertencia, pero no
produce geometría reutilizable. Si no se puede resolver ninguna página se usa
`pdf_page=null`, lista vacía, `cross_page=false` y
`geometry_status="unresolved"`. Nunca se asigna la página visible por
conveniencia.

### Privacidad y lifecycle

El payload sólo vive en estado React del Document y versión actuales. Se limpia
al pulsar el botón, cambiar de página/rotación/Document, cargar otra versión,
fallar el visor, desmontar el componente o recargar. Está prohibido enviarlo a
la API, MongoDB, errores, logs, analytics, crash reports o clipboard.

## `selection_cleared`

```json
{
  "schema_version": 1,
  "event_type": "selection_cleared",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "reason": "user"
}
```

`reason` es `user`, `empty`, `page_change`, `rotation_change`,
`document_change`, `version_change`, `load_failure` o `unmount`. No contiene el
texto eliminado ni geometría. El handler borra todas las referencias al payload
anterior.

## `reading_position_saved`

Se emite después de que el usuario pulse **Guardar posición** y el PUT S3
termine correctamente:

```json
{
  "schema_version": 1,
  "event_type": "reading_position_saved",
  "document_id": "doc_...",
  "version_id": "dver_...",
  "pdf_page": 9,
  "reading_status": "in_progress"
}
```

`pdf_page` es la página visible validada. `reading_status` es uno de los estados
S3 devueltos por el servicio. El evento no contiene Book page, selección, query,
URI ni respuesta backend cruda.

La persistencia permitida es exclusivamente `DocumentReadingState.current_page`
y los campos S3 que el servicio existente gestione como consecuencia válida.
Se prohíbe escribir selección, geometría, zoom, rotación, búsqueda o UI state.
Un PUT fallido muestra un error tipado y no emite este evento.

## Compatibilidad y evolución

S5A acepta únicamente `schema_version=1`. Un consumidor debe ignorar de forma
segura un `event_type` desconocido y rechazar un shape conocido inválido sin
rellenar campos. Cambiar semántica, límites o coordenadas requiere una nueva
versión de schema.

S5B no puede convertir estos eventos en persistencia sin definir antes un
contrato de dominio independiente. S5C será la primera fase que podrá diseñar
una interacción explícita entre selección y conceptos; el evento S5A no crea ni
anticipa un `ConceptEvidenceLink`.

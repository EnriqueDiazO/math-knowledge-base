# Anotaciones visuales persistentes — S5B

## Decisión de dominio

S5B extiende de forma aditiva `DocumentAnnotation`; no crea una colección
paralela. `document_annotations` y `annotation_id` siguen siendo la colección y
la identidad autoritativas. Por ello una marca visual conserva exactamente los
campos lógicos ya usados por Reading Space y S4.3: cita, comentario, tags,
color, página, Source, Reference y lifecycle.

`ReadingNote`, `ConceptEvidenceLink`, `concepts`, Source, Reference,
SourceDocument, ReadingState, Page Map, el PDF y el layout de blobs no cambian.
Un `ConceptEvidenceLink` continúa apuntando al mismo `annotation_id`.

## Compatibilidad de schema

| Schema | `visual_anchor` | Uso |
| --- | --- | --- |
| `schema_version=1` | ausente o `null` | anotación lógica histórica |
| `schema_version=2` | opcional | anotación lógica nueva o marca visual |
| `schema_version=2` con anchor | obligatorio para dibujar | highlight/underline persistente |

Los registros v1 no se migran ni se reescriben automáticamente. Las altas
lógicas existentes continúan usando v1. Una anotación v1 sigue apareciendo en
Streamlit, puede archivarse/reactivarse y puede vincularse con conceptos, pero
el Advanced Reader la clasifica como `logical_only` y no crea un overlay.

Cuando una anotación v2 contiene anchor:

- `kind` es `highlight` o `underline`;
- `page_number` existe y coincide con `visual_anchor.pdf_page`;
- `quote_text` es texto Unicode normalizado, no vacío y de hasta 4096
  caracteres;
- `visual_anchor.text_sha256` es el SHA-256 UTF-8 de esa cita normalizada;
- el color pertenece a `yellow`, `green`, `blue`, `pink` o `purple`.

Los modelos son cerrados: campos extra, IDs no canónicos, números no finitos y
combinaciones inconsistentes se rechazan antes de escribir.

## `VisualAnnotationAnchor`

El anchor inmutable contiene únicamente identidad de versión y geometría:

```text
anchor_schema_version = 1
version_id             = dver_<uuid4>
document_sha256        = 64 hex lowercase
pdf_page               = entero >= 1
coordinate_space       = normalized_unrotated_crop_box
capture_rotation       = 0 | 90 | 180 | 270
rects                   = 1..64 NormalizedVisualRect
text_sha256             = 64 hex lowercase
created_from            = pdfjs_text_selection
```

Cada rectángulo guarda `x`, `y`, `width` y `height` finitos en `[0,1]`, con
ancho y alto positivos y sin salir de la página (tolerancia numérica acotada de
`1e-9`). El anchor no repite la cita y no contiene zoom, escala, viewport,
device pixel ratio, scroll, coordenadas de pantalla, selectores DOM, HTML,
bytes, rutas ni datos Mongo crudos.

## Geometría canónica

La persistencia usa el CropBox sin rotación visual, origen superior izquierdo y
coordenadas normalizadas. Antes del POST, el frontend convierte los rectángulos
observados bajo la rotación actual a
`normalized_unrotated_crop_box`. La conversión inversa reconstruye el overlay
para el viewport vigente.

Las transformaciones están definidas para 0°, 90°, 180° y 270° y se prueban de
ida y vuelta. Zoom, actual size, fit width, fit page y resize sólo cambian la
proyección; nunca alteran el anchor persistido. Una selección multipágina,
vacía, no resuelta o con más de 64 rectángulos no se puede guardar.

## Selección y confirmación

`text_selection` sigue siendo un evento local y efímero. Una selección válida
muestra controles Highlight/Underline, color y cancelar, tanto junto a la
selección como en el inspector. Elegir el tipo abre una confirmación con cita,
página PDF, Book page cuando exista, comentario y tags.

Sólo **Guardar** crea una solicitud S5B. El frontend genera una vez el
`annotation_id`, transforma la geometría, envía el POST y espera
`success`/`identical`. Después dibuja el overlay y limpia la selección, sin
recargar el PDF, cambiar página/zoom/rotación ni guardar ReadingState. Cancelar,
navegar o emitir el evento por sí solos no escriben.

## Highlight, underline y overlay

Cada página tiene una `visualAnnotationLayer` entre canvas y text layer. Sus
elementos son absolutos, se reconstruyen desde el anchor y usan
`pointer-events: none`, de modo que no ocultan ni bloquean una selección futura.
El PDF y PDF.js no se modifican.

- Highlight usa un fondo semitransparente por rectángulo.
- Underline dibuja una línea inferior por rectángulo, sin unir renglones.
- La paleta nominal se resuelve a CSS controlado; no se aceptan valores CSS,
  hex libres, `url(...)`, `var(...)` ni HTML enviados por el cliente.

Al renderizar, hacer zoom, rotar o cambiar el tamaño, la capa vuelve a proyectar
los rectángulos canónicos. Las anotaciones archivadas y las incompatibles con
la versión actual no producen overlay.

## Servicio, API y lifecycle

`ReadingAnnotationService` expone operaciones específicas de creación, listado,
consulta, edición de presentación, archivado y reactivación. Antes de crear
comprueba Document PDF activo, Source/Reference, versión y SHA actuales,
integridad del blob, página, cita, geometría y readiness de los índices S5B.

La creación es idempotente: el mismo `annotation_id` con el mismo contenido
devuelve `identical`; el mismo ID con datos distintos devuelve `conflict`. El
PATCH sólo puede cambiar tipo highlight/underline, color, comentario y tags. No
puede cambiar identidad, Document, versión, SHA, página, cita o geometría. Para
cambiar la selección se archiva la anotación y se crea otra.

Archivar no borra. Oculta el overlay activo pero conserva metadata y cualquier
`ConceptEvidenceLink`. Reactivar vuelve a mostrarlo sólo cuando la versión es
compatible. No existe endpoint DELETE ni escritura dentro del PDF.

Las rutas viven bajo `/api/advanced-reader`. Las listas son paginadas, pueden
filtrar página/status/tipo y devuelven una proyección acotada sin `_id`, paths,
blobs o documentos Source/Reference completos.

## Compatibilidad de versión

El estado visual calculado es:

- `exact`: `document_id`, `version_id`, SHA, página y geometría coinciden;
- `version_mismatch`: el anchor pertenece a otra versión válida;
- `invalid_geometry`: no es seguro proyectarlo;
- `logical_only`: no hay anchor.

Sólo `exact` se dibuja. Un mismatch conserva la anotación lógica y muestra
“Anotación visual asociada a otra versión del PDF.” No hay retarget, búsqueda de
texto similar ni relocation automática.

## Índices y Maintenance

El plan explícito añade:

```text
document_annotations_document_page_status
  document_id ASC, page_number ASC, status ASC, updated_at DESC

document_annotations_visual_version_sha
  visual_anchor.version_id ASC, visual_anchor.document_sha256 ASC
```

Construir modelos/repositorios/app, abrir Streamlit o Advanced Reader e importar
un ZIP no aplica índices. Maintenance muestra readiness compacto; la tabla
técnica permanece dentro de diagnósticos avanzados. Aplicar el plan exige pulsar
el botón, escribir el nombre real de la base y marcar la confirmación. Hasta que
todo el plan esté listo, las capabilities persistentes permanecen `false` y las
escrituras visuales se bloquean; las lecturas seguras continúan disponibles.

## Streamlit y S4.3

Reading Space sigue usando `st.pdf` como fallback y no intenta dibujar la
geometría. Las anotaciones visuales aparecen junto con las lógicas, con badge
**Marca visual**, cita, página, comentario, tags y acciones de
archivado/reactivación. Los rectángulos no se muestran por defecto; los detalles
técnicos cerrados sólo resumen versión, espacio, rotación y cantidad.

Como la marca es un `DocumentAnnotation` normal, S4.3 la incluye en pendientes
de vincular y crea `ConceptEvidenceLink` con el mismo `annotation_id`. S5B no
busca conceptos ni crea vínculos desde el Advanced Reader.

## Portabilidad

El formato de backup exterior continúa siendo compatible. Extended JSON
canónico conserva schema v2, anchor, rectángulos, versión, SHA, espacio de
coordenadas, rotación y hash de cita. Export e import vuelven a validar el modelo
cerrado y las relaciones Source/Reference/Document.

Para un anchor, la versión referenciada debe existir dentro del PDF del mismo
Document y su SHA debe coincidir. La validación examina todas las versiones, no
exige que sea la actual: una marca histórica válida puede importarse y quedará
en `version_mismatch` hasta abrir su versión. Un ZIP v1 sigue siendo válido. Un
segundo import idéntico es no-op; igual `annotation_id` con contenido diferente
bloquea todo el import antes de escribir. El import no instala índices de
anotaciones visuales.

## Privacidad y seguridad

Antes de Guardar, texto y geometría sólo viven en memoria. Después de la
confirmación, `quote_text` y `visual_anchor` se almacenan en MongoDB porque son
la anotación solicitada por el usuario. No se guardan zoom, scroll, pantalla,
DOM, analytics ni telemetría; no se modifica el PDF.

Frontend y API funcionan same-origin sobre loopback. POST, PATCH, archive y
reactivate exigen JSON, origen/Fetch Metadata compatibles y body acotado. Los
schemas rechazan campos extra y la API no confía en IDs, hashes, páginas,
rectángulos ni colores del navegador. Logs y errores saneados no contienen
cita, comentario, rectángulos, paths, URI Mongo ni SHA completo.

## Pruebas

La cobertura S5B separa:

- modelos v1/v2, hash, IDs, límites, campos extra y geometría no finita;
- transformaciones 0/90/180/270, round-trip, zoom, fit y resize;
- repositorio/servicio/API, idempotencia, conflictos, integridad, readiness,
  same-origin y límites de request;
- frontend, confirmación, overlays, filtros, edición, lifecycle y mismatch;
- Streamlit, badge, fallback, S4.3 y Maintenance explícito;
- export/import v2, versión histórica, no-op, conflictos previos a escritura y
  ausencia de índices automáticos;
- navegador real y comparación geométrica/pixel sobre PDF y bases temporales.

Las pruebas persistentes usan MongoDB, XDG y PDFs sintéticos temporales. No
crean anotaciones en Documents reales.

La comparación E2E limita simultáneamente el desvío a `0.005` en coordenadas
normalizadas y `3.25` píxeles CSS. El margen cubre únicamente redondeo
subpíxel de PDF.js entre zoom, fit y rotación; ambos límites impiden aceptar
una deriva proporcional. Si la text layer cambia su fragmentación tras una
búsqueda o recarga, se compara además la unión de rectángulos y se exige una
diferencia de cobertura no mayor que `0.06`, sin alterar el anchor persistido.

## Limitaciones y S5C

S5B no ofrece selección multipágina, rectángulos manuales, freehand, OCR,
extracción persistente, embeddings, scraping, colaboración, nube, PDF aplanado,
anotaciones PDF embebidas ni relocation entre versiones. `st.pdf` no muestra
overlays.

S5C queda reservado al flujo explícito selección visual →
`DocumentAnnotation` → Guided Concept Linking → `ConceptEvidenceLink`. S5B no
asocia conceptos automáticamente.

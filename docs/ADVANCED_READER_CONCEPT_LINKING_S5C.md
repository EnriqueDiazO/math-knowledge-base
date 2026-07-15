# Asociación de conceptos en Advanced Reader — S5C

## Objetivo y backend preservado

S5C permite asociar un highlight o underline persistente con un concepto legacy
existente. La relación autoritativa continúa siendo
`ConceptEvidenceLink → DocumentAnnotation → visual_anchor`; la evidencia visual
se identifica por `annotation_id` y el concepto por el par exacto
`(concept_legacy_id, concept_legacy_source)`.

No se añadió colección, modelo de vínculo ni representación persistente de
frontend. `DocumentAnnotation`, `ConceptEvidenceLink`, Source, Reference,
SourceDocument, Page Map y `concepts` mantienen sus contratos. El PDF, blobs y
`visual_anchor` no cambian al asociar o cambiar el lifecycle de un vínculo.

## Arquitectura

FastAPI separa schemas acotados, búsqueda read-only, joins proyectados y rutas
same-origin en `mathmongo/advanced_reader/concept_*.py`. La búsqueda reutiliza
el parser y la proyección aprobada de S4.3. Todos los POST delegan en
`ReadingAnnotationService`; rutas y React nunca escriben MongoDB directamente.

React separa etiquetas, wizard y resúmenes en `src/concepts/`. Los drafts viven
sólo en memoria y se limpian al cambiar Document, versión o Annotation. No se
usa localStorage, sessionStorage, cookies o URL para drafts.

## Flujo highlight → concepto y wizard

S5B guarda primero la `DocumentAnnotation`. Después S5C muestra “Marca visual
guardada” con **Asociar concepto** y **Seguir leyendo**, sin abrir el wizard. La
acción también aparece en tarjetas activas con anchor exacto.

El wizard conserva PDF, página, zoom, rotación, sidebar, inspector y overlay:

1. **Concepto**: búsqueda y selección de tarjeta legacy.
2. **Relación**: tipo, comentario opcional y preview de la Annotation.
3. **Confirmar**: resumen de concepto, marca, Document, Source, Reference y Page
   Map opcional; sólo **Guardar** persiste.

El `evidence_link_id` se crea una vez al iniciar confirmación. Un fallo conserva
draft e ID para Reintentar. El backend devuelve `identical` para el mismo ID y
contenido y conflicto para el mismo ID con contenido distinto. Guardar queda
deshabilitado durante la solicitud.

## Búsqueda y concept cards

`GET /api/advanced-reader/concepts/search` busca en ID, título/nombre, source,
tipo, categorías y tags. Recorta la query, exige 1–160 caracteres, escapa regex,
pagina con límite máximo 50 y ordena por source/ID. Su proyección excluye `_id`,
LaTeX, imágenes, relaciones y documentos Mongo completos.

`GET /api/advanced-reader/concepts/detail` resuelve una identidad compuesta
exacta. Las tarjetas muestran título, tipo, categorías/tags, Source legacy y
conteos disponibles; no renderizan HTML o LaTeX.

## Contexto automático y tipos

El wizard muestra tipo, cita, color, comentario, PDF page y Book page de la
Annotation; título, Source y Reference del Document; y título, tipo y Source
legacy del concepto. IDs quedan en detalles técnicos cerrados.

Se usan exclusivamente los ocho valores existentes:

- Fuente de definición (`definition_source`)
- Fuente de teorema (`theorem_source`)
- Fuente de prueba (`proof_source`)
- Fuente de ejemplo (`example_source`)
- Motivación (`motivation`)
- Cita (`citation`)
- Pregunta (`question`)
- Contexto relacionado (`related_context`)

`related_context` es el default visual pero se confirma explícitamente; no hay
inferencia automática ni sugerencias semánticas.

## Annotation evidence API y creación

`GET/POST /visual-annotations/{annotation_id}/concept-evidence` consulta o crea
vínculos de una marca. El POST acepta únicamente `evidence_link_id`, identidad
legacy, `link_type` y `comment`. El servicio obtiene Source y Reference desde la
Annotation; Document y PDF page se derivan del mismo target indirecto sin añadir
campos incompatibles a `ConceptEvidenceLink`.

Antes de escribir valida índices, Annotation visual/activa, Document PDF/activo,
versión y SHA actuales, Source, Reference, concepto exacto y tipo. Una Annotation
lógica, archivada o `version_mismatch` no recibe vínculos nuevos. Un concepto
ausente en un vínculo histórico conserva su identidad y usa
`concept_not_found`; el vínculo no se borra.

## Lifecycle

`POST /concept-evidence/{evidence_link_id}/archive` y `/reactivate` reutilizan
S4; no existe DELETE. Archivar sólo cambia el vínculo: no archiva la Annotation,
oculta el overlay o modifica el concepto. Reactivar valida concepto y target. Si
la Annotation está archivada, se bloquea hasta reactivarla mediante S5B.

## Conceptos asociados, página y documento

**Conceptos asociados** aparece bajo cada tarjeta visual con tipo, comentario,
estado y Source legacy. **Conceptos en esta página** incluye únicamente vínculos
dirigidos a Annotations visuales activas de la PDF page actual. **Conceptos del
documento** agrupa por identidad legacy y resume highlights, underlines, páginas
y tipos. Los endpoints son paginados y no cargan PDF o blobs.

**Marcas sin concepto** contiene Annotations visuales activas sin ningún vínculo
activo. Desaparecen tras el primero y reaparecen si todos se archivan.

El panel PDF.js muestra evidencia visual, no toda la evidencia S4. ReadingNotes,
targets Document+page y Annotations lógicas continúan en Streamlit S4.3.

## Navegación, Page Map y mismatch

**Ir a la marca** navega a la PDF page y pide foco temporal al overlay. No cambia
zoom/rotación, no altera Book page y no guarda ReadingState. En
`version_mismatch` conserva navegación lógica y vínculos históricos, pero
bloquea asociaciones nuevas.

Page Map es read-only y opcional. Si resuelve, muestra Book page; si falta o
falla, conserva PDF page. S5C no crea reglas ni aplica índices.

## Integración S4.3 y portabilidad

No hay bridge: Streamlit y Advanced Reader leen `concept_evidence_links`. Un
vínculo creado, archivado o reactivado aparece con el mismo `evidence_link_id`,
`annotation_id`, identidad, tipo, comentario y estado en ambas UIs.

El backup existente ya conserva esos campos. S5C no añade metadata frontend; un
segundo import idéntico sigue siendo no-op.

## Capabilities

Metadata expone `concept_search`, `annotation_concept_links`,
`concept_link_archive`, `concept_link_reactivate` y `concept_linking`. La
búsqueda puede permanecer read-only. Escritura sólo es true si Notes & Evidence,
visual annotations, consulta legacy y el servicio están listos. No se aplican
índices automáticamente. Sin readiness, Guardar queda deshabilitado y se indica
inicializar Notes & Evidence desde Maintenance.

## Seguridad y privacidad

El servidor sigue en loopback, valida Host/same-origin y no habilita CORS
wildcard. Los POST requieren JSON, Origin/Fetch Metadata compatible, schemas sin
extras y body máximo 64 KiB. IDs, comentarios, queries y respuestas se acotan.
El frontend usa rutas relativas y desconoce MongoDB, XDG y paths.

No se persisten query, resultados, conceptos vistos, zoom, rotación o UI state.
Los logs no incluyen query, comentario, cita, geometría, texto PDF, contenido de
concepto, URI, path o SHA completo. Sólo una confirmación persiste campos ya
existentes de `ConceptEvidenceLink`.

## Pruebas y E2E

Las pruebas focales cubren proyección/regex/identidad, derivación, idempotencia,
duplicados, lifecycle, same-origin, capabilities, wizard, resultados parciales,
paneles y navegación. El E2E usa Mongo/XDG/Source/Reference/PDF/conceptos
temporales, puertos alternos y Chrome real; comprueba overlays, recarga, vínculo
exacto, lifecycle, compatibilidad Streamlit, portabilidad, red local y cleanup.

## Limitaciones y plan posterior

S5C no crea/edita conceptos, no vincula selecciones efímeras, no crea
ReadingNotes, no cubre Documents web e implementa cero OCR, extracción
persistente, embeddings, scraping, colaboración, nube o IA. `st.pdf` permanece
como fallback. Nuevos targets o automatización requieren otra fase y contrato.

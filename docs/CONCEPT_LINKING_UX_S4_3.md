# Asociación guiada de conceptos — S4.3

S4.3 convierte la operación técnica de crear un `ConceptEvidenceLink` en una
acción de lectura comprensible:

> Este concepto aparece aquí.

Antes de esta fase, Notes & Evidence ya permitía crear anotaciones, notas y
vínculos, pero el flujo exponía demasiado pronto identidades internas y
formularios separados. La experiencia guiada parte del Document abierto y de
la ubicación actual, deja que el usuario elija un concepto y explica qué clase
de evidencia está registrando antes de guardar.

## Backend preservado

S4.3 es composición de UI sobre contratos existentes. No cambia modelos
Pydantic, IDs, colecciones, índices, migraciones, export/import, blobs ni los
documentos legacy de `concepts`. En particular:

- el concepto continúa identificado por el par exacto `(id, source)`;
- `DocumentAnnotation`, `ReadingNote` y `ConceptEvidenceLink` conservan sus
  campos y semántica;
- las escrituras pasan exclusivamente por `ReadingAnnotationService`;
- Source, Reference, SourceDocument, ReadingState y Page Map sólo aportan el
  contexto que ya poseen;
- el vínculo no modifica el concepto, el PDF ni la evidencia elegida.

La relación persistente sigue siendo:

```text
Concept
   │
   ▼
ConceptEvidenceLink
   │
   ├── Document + page
   ├── DocumentAnnotation
   └── ReadingNote
```

El paquete de UI `editor/concept_linking/` separa estado de sesión, resolución
de contexto, búsqueda legacy, view-models efímeros, tarjetas, wizard, resúmenes
y navegación. Ninguno de esos view-models se persiste o participa en un export.
Los módulos reciben de forma explícita el contexto y los servicios activos; no
abren conexiones MongoDB al importarse.

## Contexto automático

El Reader ya resuelve el Document, su Source, su Reference opcional y el estado
de lectura. S4.3 toma de ese contexto:

- nombre y tipo del Document;
- nombre visible de la Source;
- título visible de la Reference, o **Sin Reference asociada**;
- PDF page capturada al abrir el wizard;
- Book page calculada, cuando existe Page Map;
- estado de lectura y `user_scope` local;
- IDs internos necesarios para llamar al servicio.

La tarjeta **Contexto actual** muestra nombres y páginas. Los IDs sólo aparecen
en **Detalles técnicos**, cerrado por defecto. El usuario nunca captura
`document_id`, `source_id`, `reference_id`, `annotation_id`, `note_id`,
`evidence_link_id`, `concept_legacy_id`, `concept_legacy_source` ni
`user_scope`.

Si la página del Reader cambia mientras el wizard está abierto, la página
capturada no cambia silenciosamente: la UI avisa y permite conservarla o tomar
la nueva página. Cambiar de base, scope, Source o Document invalida el draft;
cambiar de pestaña o de layout dentro del mismo Document no lo borra.

## Búsqueda de conceptos

La búsqueda reutiliza los límites y la validación de identidad del selector
legacy, ampliando sólo los campos de metadata requeridos por S4.3. Consulta
únicamente metadata proyectada y busca por:

- ID;
- `titulo`, `title`, `nombre` o `name` histórico;
- `source` legacy;
- `tipo`;
- `categorias`;
- `tags`, cuando existan.

El texto tiene longitud máxima, toda expresión regular se escapa, los resultados
se paginan y limitan, y el orden es estable. La proyección excluye `_id`, LaTeX,
blobs y cuerpos extensos. La selección conserva sin normalizar el par exacto
`(id, source)`; nunca elige un concepto por similitud ni crea uno nuevo.

Los accesos **Conceptos recientes**, **usados en este documento**, **usados en
esta Source** y **vinculados en la página actual** se construyen con consultas
read-only acotadas. Las identidades se deduplican antes de renderizar.

## Tarjetas de concepto

Los resultados se presentan como tarjetas, no como documentos MongoDB ni como
una tabla cruda. Cada tarjeta prioriza:

- título o nombre principal;
- tipo;
- categorías y tags resumidos;
- Source legacy;
- ID como detalle secundario;
- conteo de evidencias sólo cuando puede obtenerse con una consulta acotada;
- acción **Seleccionar**.

La tarjeta **Concepto seleccionado** añade los conteos disponibles para el
Document y la página actuales. No ejecuta LaTeX, no renderiza HTML crudo y no
carga descripciones extensas. Como las páginas legacy existentes de edición y
navegación también ofrecen acciones de escritura, S4.3 no las presenta como una
vista read-only: **Ver detalles** permanece en una tarjeta local y segura.

## Wizard guiado

La acción principal es **Asociar concepto a esta página** para PDFs. El wizard
mantiene cuatro etapas visibles:

```text
1 Concepto → 2 Evidencia → 3 Contexto → 4 Confirmar
```

1. **Concepto** busca y selecciona una identidad legacy exacta.
2. **Evidencia** elige página directa, Annotation o ReadingNote.
3. **Contexto** elige un `EvidenceLinkType` con etiqueta humana y permite
   explicar opcionalmente por qué la evidencia es relevante.
4. **Confirmar** muestra concepto, Document, Source, Reference, ubicación,
   origen y tipo antes de habilitar **Guardar asociación**.

Cancelar limpia sólo el draft conceptual. Guardar requiere el botón explícito,
comprueba primero la identidad exacta existente y limpia el wizard tras el
resultado; así un rerun normal no repite la escritura. El flujo conserva el
PDF, Document, pestaña y layout, y actualiza las tarjetas tras el resultado
tipado del servicio.

### Página directa

Es el modo predeterminado para un PDF. Llama al servicio con el Document y la
PDF page capturados, sin `annotation_id` ni `note_id`. Persiste el tipo elegido
y el comentario opcional; no crea una Annotation o ReadingNote auxiliar.

### Annotation

El usuario puede elegir una Annotation activa compatible del mismo Document o
crear una nueva con los campos existentes: kind, cita, body, tags y página
sugerida. En el segundo caso se ejecutan dos acciones explícitas:

1. crear `DocumentAnnotation` con el servicio existente;
2. crear el vínculo dirigido a su `annotation_id`.

Las tarjetas abrevian cita y body, muestran rango, tags y estado, y destacan
**Sin concepto asociado** cuando no existe ningún vínculo conceptual.

### ReadingNote

El usuario puede elegir una ReadingNote compatible o crear una con title,
note_type, body, rango de páginas y tags. La composición guarda primero la nota
y después crea el vínculo dirigido a `note_id`. El body de la nota no se copia
al `comment`; el comentario explica la relación conceptual.

## Tipo de evidencia

La UI traduce los valores existentes sin cambiar el enum:

| Etiqueta | Valor persistido |
| --- | --- |
| Fuente de definición | `definition_source` |
| Fuente de teorema | `theorem_source` |
| Fuente de prueba | `proof_source` |
| Fuente de ejemplo | `example_source` |
| Motivación | `motivation` |
| Cita | `citation` |
| Pregunta | `question` |
| Contexto relacionado | `related_context` |

El tipo no se infiere ni confirma automáticamente.

## Resúmenes visuales

### Conceptos en esta página

Agrupa los vínculos activos y archivados cuya página directa, Annotation o rango
de ReadingNote alcanza la PDF page actual. Incluir archivados permite ofrecer
**Reactivar** sin ocultarlos. Cuando Page Map está disponible, cada grupo usa
**Book page X · PDF page N**. Las tarjetas muestran concepto, tipo de evidencia
humanizado, origen, preview, comentario abreviado y estado.

### Conceptos del documento

Agrupa una página acotada y seleccionable de evidencia del Document por
identidad de concepto. Resume número de evidencias, páginas y tipos, y permite
expandir la evidencia o abrir su página lógica. No carga el PDF ni materializa
blobs para construir el resumen.

### Pendientes de vincular

Lista Annotations y ReadingNotes activas sin `ConceptEvidenceLink`, agrupadas
por página. **Asociar concepto** abre el wizard con el target preseleccionado,
mantiene el Document y continúa en la etapa de búsqueda de concepto.

### Evidencias conocidas

Al seleccionar un concepto, una consulta paginada muestra evidencia en el
Document actual, en la Source actual y en otros Documents. Cada item resuelve
de forma acotada nombres visibles de Document, Source y Reference, además de
página, origen, tipo y comentario. No carga PDFs, blobs ni documentos MongoDB
completos.

## Resultados parciales y duplicados

Los modos compuestos no hacen rollback destructivo. Si se crea una Annotation
o ReadingNote y luego falla el vínculo, la UI conserva el elemento, informa el
resultado parcial, lo muestra en **Pendientes de vincular** y ofrece
**Reintentar vínculo**. El reintento reutiliza el ID ya creado y no vuelve a
insertar la Annotation o Note.

Antes de insertar, el servicio sigue siendo la autoridad para `find_exact` y
la identidad de duplicado. Un vínculo exacto existente se muestra como tarjeta
navegable y queda disponible en los resúmenes de evidencia en vez de duplicarse.
La UI distingue
un mismo target con igual tipo, un mismo target con distinto tipo y targets
Annotation/ReadingNote diferentes; no crea una identidad paralela para resolver
conflictos.

Los vínculos pueden archivarse o reactivarse mediante las operaciones
existentes. Como el backend no permite editar la identidad o el target, cambiar
esos datos requiere archivar el vínculo anterior y confirmar uno nuevo.

## Page Map opcional

Page Map sólo mejora las etiquetas. Si no existe, falla o no tiene índices
listos, la asociación continúa con PDF page. La UI muestra una advertencia
discreta y no inicializa índices, no redirige obligatoriamente a Maintenance y
no modifica `document_page_maps`.

## Documents web: limitación explícita

El contrato actual de `ConceptEvidenceLink` exige que un target directo tenga
simultáneamente `document_id` y `page_number`. Un Document web no tiene página;
por tanto, **el backend actual no puede representar un vínculo directo al
recurso web**.

S4.3 preserva ese contrato y no inventa una segunda representación. En un
Document web, **Asociar concepto a este recurso** abre el flujo guiado, pero
ofrece solamente los targets válidos existentes:

- una DocumentAnnotation sin página;
- una ReadingNote sin páginas.

No se fabrica `page_number`, no se usa una Annotation oculta para fingir un
target directo y no se cambia el modelo. Habilitar en el futuro un target web
directo exige una decisión de backend y queda fuera de S4.3. La UI tampoco hace
requests HTTP, abre URLs automáticamente ni realiza scraping.

## Session state y seguridad

Todo el draft usa claves `concept_linking_*` y guarda sólo escalares o
identidades lógicas acotadas. Nunca retiene Database, MongoClient, servicios,
bytes, paths, cuerpos completos de conceptos o listas sin límite.

Si Notes & Evidence aún no está inicializado, la búsqueda y las tarjetas siguen
disponibles en modo read-only; sólo se deshabilita la confirmación de escritura
y se remite de forma compacta a Maintenance.

Las protecciones de S4.3 incluyen:

- consultas legacy proyectadas, escapadas, paginadas y limitadas;
- ninguna escritura directa a `concepts`, Sources, References, Documents,
  ReadingState, Page Maps o blobs;
- ninguna inicialización automática de índices;
- texto plano para cita, notas y comentarios;
- detalles técnicos colapsados;
- ausencia de `file://`, `Path.as_uri`, `webbrowser`, HTML ejecutable, PDF.js,
  OCR, extracción de texto, embeddings y scraping.

## Pruebas

Las pruebas focales combinan helpers puros, render con UI/servicios fake y un
ciclo real de Streamlit `AppTest`. Cubren:

- búsqueda por todos los campos aprobados, regex literal, límites, proyección,
  paginación, tarjetas y persistencia de selección;
- lifecycle del wizard, captura de Document/página, Page Map opcional,
  cancelación, escritura única y limpieza por cambio de contexto;
- página directa, Annotation existente/nueva y ReadingNote existente/nueva;
- resultados parciales y reintento sin recrear el target;
- duplicados, resúmenes por página/Document/concepto y pendientes;
- PDF visible, pestaña y layout conservados tras reruns;
- Document web sin controles de página y sin target directo ficticio;
- ausencia de escrituras directas y de APIs de red, filesystem o visor nuevo.

La validación end-to-end usa MongoDB y XDG temporales, conceptos legacy
sintéticos y Documents PDF/web temporales. Comprueba conteos exactos en las
colecciones S4 y elimina base, blobs temporales, proceso y puerto al terminar;
las bases reales se comparan antes/después y deben conservar fingerprints
idénticos.

Como `editor` ya está incluido por Poetry, el subpaquete nuevo no requiere
cambiar `pyproject.toml`. Wheel y sdist se inspeccionan para confirmar que la UI
está incluida y que una instalación offline no escribe en checkout,
`site-packages`, HOME o XDG durante imports aislados.

## Límites y futuro

S4.3 no crea conceptos, no fusiona identidades, no modifica LaTeX y no ofrece
búsqueda semántica. El visor continúa siendo `st.pdf`: no hay selección de
texto, coordenadas, highlights visuales, overlays, OCR ni extracción.

Un visor PDF.js con text layer y geometría podría permitir selección visual en
una fase futura. Requerirá un diseño de seguridad, empaquetado offline y
contratos propios; no forma parte de S4.3.

## Continuidad con S5A

S5A añade un lector PDF.js avanzado y aislado, sin reemplazar este flujo. S4.3
continúa siendo la asociación estable de conceptos; integrar una selección
visual del nuevo lector con conceptos queda expresamente para S5C.

## Continuidad con S5B

Una marca S5B es el mismo `DocumentAnnotation` que ya consume el wizard. Por
ello aparece en **Pendientes de vincular**, conserva cita/página/comentario/tags
y puede recibir un `ConceptEvidenceLink` dirigido a su `annotation_id`, sin
adaptador ni duplicación de evidencia. Streamlit la distingue con **Marca
visual** y sigue ofreciendo el flujo S4.3.

S5B no añade búsqueda de conceptos ni creación de vínculos al Advanced Reader.
El flujo integrado selección visual → marca → asociación guiada queda reservado
para S5C.

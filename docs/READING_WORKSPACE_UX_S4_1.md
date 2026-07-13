# S4.1: Reading Workspace UX

## Problema UX original

S4 añadió anotaciones, Reading Notes y evidencia conceptual al Reading Space,
pero el flujo inicial era principalmente vertical: filtros, tablas de Documents,
Recent Documents, lector y panel intelectual aparecían uno después de otro. Al
leer un PDF, el usuario tenía que desplazarse entre el documento y los
formularios, y podía perder de vista el contexto de lectura al crear o consultar
una anotación.

S4.1 reorganiza esa experiencia sin cambiar los modelos, repositorios, servicios,
colecciones ni el backup de S2–S4. Cuando hay un Document abierto, el centro de la
página pasa a ser un **Reading Workspace**: el lector y las herramientas de
trabajo intelectual permanecen visibles en la misma ejecución de Streamlit.

## Disposición del Reading Workspace

El workspace ofrece dos modos persistidos únicamente en session state:

- **Split**: presenta el lector en la columna principal y Notes & Evidence en la
  columna lateral. Es el modo indicado para pantallas anchas y permite consultar
  o crear registros sin ocultar el PDF.
- **Stacked**: coloca el lector primero y las herramientas debajo. Conserva todas
  las acciones y resulta más cómodo en ventanas estrechas.

El modo Split usa columnas nativas de Streamlit con separación amplia. No usa
HTML de layout, iframes ni componentes externos. Cambiar entre Split y Stacked no
abre de nuevo el Document, no registra otra apertura, no descarta el preview PDF
y no modifica el estado de lectura.

Cuando todavía no hay un Document seleccionado, Reading Space conserva el flujo
de selección: filtros y listado aparecen en la parte superior. Cuando ya existe
una selección, el Reading Workspace aparece primero y las herramientas de cambio
de contexto quedan recogidas en:

- **Change Document**, para filtros y listado de Documents;
- **Recent Documents**, para el historial reciente.

Así, una rerun durante la lectura vuelve a mostrar primero el PDF o el recurso
web y sus herramientas, no una tabla de selección extensa.

## Flujo rápido de anotación

**Quick Annotation** es un formulario compacto asociado al Document actual. Sus
campos visibles son:

- tipo: `highlight`, `underline`, `comment`, `bookmark` o `question`;
- página opcional para PDFs;
- cita manual;
- comentario o cuerpo;
- tags;
- acción de alta.

En un PDF, la página actual de S3 se usa como sugerencia inicial. **Use current
page** recupera esa sugerencia sin persistirla automáticamente en
`document_reading_state`; **Clear form** elimina sólo el draft del formulario. En
un Document web no se fabrican campos de página.

Para `highlight` y `underline`, la cita manual es el dato principal y el
comentario puede quedar vacío. Para `comment` y `question`, el cuerpo es el dato
principal y continúa siendo obligatorio por el contrato S4. La interfaz identifica
estas entradas como anotaciones lógicas: no hay selección automática de texto,
coordenadas ni overlay sobre el PDF.

Tras una creación correcta, el workspace:

1. muestra el resultado tipado del servicio;
2. limpia el draft Quick Annotation;
3. actualiza la lista agrupada;
4. conserva el Document seleccionado y el preview PDF abierto;
5. permanece en Reading Space.

Los errores de validación o de índices se muestran sin limpiar el contexto de
lectura ni intentar escribir por otra vía.

## Flujo rápido de Reading Note

**Quick Reading Note** permite crear una nota ligada al Document actual o sólo a
su Source. Incluye título, tipo, cuerpo, asociación al Document, rango de páginas
opcional, Reference opcional cuando corresponda, tags y acción de alta.

Para PDFs, el usuario puede usar la página actual como `page_start`; `page_end`
es opcional. Para Documents web, los controles de página permanecen ocultos. Al
guardar, se limpia únicamente el draft de la nota, se mantiene abierto el
Document y la nueva nota aparece en su grupo correspondiente. Las notas
source-only siguen siendo datos S4 y no se convierten implícitamente en notas de
otro Document.

## Anotaciones agrupadas por página

Las anotaciones dejan de presentarse como una tabla plana. El workspace las
agrupa por página y reserva **No page** para las entradas generales:

```text
Page 12
  [highlight] cita abreviada…
  [comment] comentario abreviado…

Page 13
  …

No page
  …
```

Cada tarjeta muestra tipo, cita y cuerpo abreviados, tags, estado e identidad
lógica suficiente para ejecutar las acciones controladas:

- abrir o sugerir la página;
- editar;
- archivar o reactivar;
- vincular a un concepto legacy.

Abrir una página selecciona el mismo Document y encola una sugerencia para el
campo manual `current_page`. La sugerencia se aplica antes de crear el widget en
la siguiente rerun y se acota a `total_pages` cuando S3 conoce ese total. No
guarda la página por sí sola y no intenta sincronizar el scroll interno de
`st.pdf`.

## Concept Evidence como tarjetas

Concept Evidence conserva el modelo S4 y mejora solamente su presentación. El
selector de concepto consulta metadata legacy acotada y proyectada. Las tarjetas
de vínculos existentes indican el origen:

- Annotation;
- Reading Note;
- Document y página directos.

Cada tarjeta muestra el ID y Source legacy del concepto, su título cuando está
disponible, el tipo y estado del vínculo y las acciones aplicables: abrir el
target lógico, volver al Document o página y archivar/reactivar Evidence. Un
vínculo de una nota source-only sigue pudiendo administrarse desde esa nota,
aunque no tenga navegación a Document.

La UI nunca modifica `concepts` ni añade `source_id` o `reference_id` a un
concepto. Cuando no existe una vista de concepto apropiada, muestra su identidad
legacy en modo de sólo lectura.

## Navegación y agrupación del trabajo

Los recorridos rápidos esperados son:

1. seleccionar un Document y abrir el lector;
2. elegir Split o Stacked;
3. crear una Annotation o Reading Note sin cerrar el lector;
4. consultar las anotaciones por página;
5. vincular una Annotation o Note a un concepto;
6. regresar a la página sugerida mediante IDs lógicos;
7. cambiar de Document desde el expander cuando termine el bloque de lectura.

La navegación usa únicamente Source ID, Document ID y, cuando existe, página.
Nunca construye rutas locales, `file://` ni aperturas mediante `webbrowser`.

## Session state

S4.1 reutiliza exclusivamente los namespaces `reading_space_*` y
`reading_annotations_*`. El estado transitorio se limita a:

- modo Split o Stacked;
- drafts Quick Annotation y Quick Reading Note;
- selección lógica de Annotation, Note o concepto; las acciones de Evidence usan
  su ID lógico en keys de widget y no conservan el vínculo como objeto;
- sugerencias de página pendientes para la siguiente rerun.

Cambiar de Document elimina drafts incompatibles. Cambiar de Source, base o
endpoint limpia el contexto S4.1 antes de reutilizar widgets. Las sugerencias de
página se consumen antes de instanciar `current_page`, evitando modificar la key
de un widget ya creado.

Session state no guarda MongoClient, Database, rutas absolutas, HTML, listas sin
límite, blobs ni copias adicionales del PDF. El único payload PDF transitorio es
el preview verificado que ya administra S3; S4.1 no crea otro.

## Contratos que permanecen sin cambios

S4.1 es una mejora de UX. No cambia:

- `DocumentAnnotation`, `ReadingNote` o `ConceptEvidenceLink`;
- `source_documents`, `document_reading_state` ni las tres colecciones S4;
- las reglas de Source, Reference, Document, usuario local o concepto legacy;
- la inicialización explícita de índices S3/S4;
- el formato, orden o validaciones de export/import;
- la integridad, almacenamiento y descarga de blobs PDF.

Las acciones continúan pasando por los servicios tipados. Abrir el workspace o
cambiar de layout es de sólo lectura y no materializa colecciones ni índices.

## Compatibilidad con Streamlit 1.55

La implementación usa APIs nativas disponibles en Streamlit 1.55.0. En
particular:

- `st.columns(..., gap="large")` para Split;
- `width="stretch"` o `width="content"` en APIs que admiten `width`;
- forms y callbacks con keys estables y namespaced;
- cambios de session state efectuados antes de instanciar el widget afectado;
- reruns explícitas sólo después de completar una acción.

No debe reintroducirse `use_container_width=`. La prueba estática
`tests/test_streamlit_width_deprecation.py` analiza todo el código Python
ejecutable bajo `editor`, por lo que incluye automáticamente cualquier módulo
S4.1 nuevo.

## Seguridad y limitaciones

El Reading Workspace no implementa ni utiliza:

- PDF.js propio, iframe o componente externo;
- HTML crudo para layout o contenido de usuario;
- selección automática, coordenadas u overlay visual;
- OCR o extracción de texto;
- búsqueda dentro del PDF;
- embeddings;
- requests HTTP o scraping;
- `file://`, `Path.as_uri` o `webbrowser`;
- escritura de bytes PDF en MongoDB.

`quote_text`, bodies y comentarios son texto introducido por el usuario. El PDF
permanece bajo los contratos S2/S3 y la página sigue siendo metadata manual; una
sugerencia de página no controla el scroll real del visor.

## Expectativas de validación

Las pruebas UI focales deben demostrar, como mínimo:

- presencia del Reading Workspace con un Document abierto;
- disponibilidad de Split y Stacked;
- PDF y Quick Annotation en la misma ejecución;
- uso, limpieza y conservación de `current_page` sin persistencia implícita;
- altas de highlight, underline, comment y Reading Note sin cerrar el PDF;
- ausencia de controles de página en web;
- agrupación Page/No page y navegación lógica;
- tarjetas Evidence con origen y lifecycle;
- Change Document y Recent Documents en expanders durante la lectura;
- limpieza de drafts al cambiar Document o base;
- ausencia de APIs y funcionalidades prohibidas.

La validación AppTest o runtime usa MongoDB, XDG y puerto temporales. Debe abrir
PDF y web, alternar ambos layouts, ejercitar Quick forms y Evidence, revisar logs
sin tracebacks ni el warning de `use_container_width`, y limpiar todos los
recursos temporales al finalizar. Ninguna validación debe escribir en MathV0 ni
en los blobs reales del usuario.

## Continuidad

S4.2 continúa este trabajo con tabs, controles de página y Page Maps manuales,
además del pulido visual de diagnósticos y Cuaderno. La organización vigente y
sus límites están documentados en `docs/READING_SPACE_POLISH_S4_2.md`.

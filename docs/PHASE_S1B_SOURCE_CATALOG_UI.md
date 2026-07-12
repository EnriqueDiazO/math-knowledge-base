# Fase S1B — Interfaz del catálogo Source/Reference

## Alcance

S1B añade la interfaz Streamlit del catálogo implementado en S1A. La fase se
limita a `Source`, `Reference`, BibTeX, administración explícita de índices y
lectura diagnóstica de conceptos legacy. No cambia el contrato histórico de los
conceptos ni crea vínculos nuevos dentro de ellos.

La navegación principal incorpora:

- `➕ Add Source`;
- `✏️ Edit / Analyze Source`.

Las páginas usan `SourceCatalogService`, `SourceRepository`,
`ReferenceRepository`, `SourceCatalogIndexManager` y los modelos tipados de
`mathmongo.source_catalog`. La UI no replica normalización, reglas de
duplicados, parsing BibTeX, validación bibliográfica ni reglas de borrado.

## Navegación e integración

Las dos páginas del catálogo se insertan juntas después de Dashboard sin
eliminar las opciones existentes. `editor/editor_streamlit.py` conserva la
responsabilidad de seleccionar la conexión activa, construir el contexto del
catálogo y despachar a los renderers; los formularios y flujos viven fuera del
archivo monolítico.

La navegación programática usa una solicitud pendiente que se aplica antes de
crear el widget lateral. Esto permite:

- abrir en Edit / Analyze una Source recién creada;
- abrir un concepto legacy existente mediante Edit Concept;
- evitar mutar la clave de un widget después de haberlo instanciado.

El handoff hacia Edit Concept conserva la identidad legacy completa `(id,
source)`. No usa sólo `id`, no realiza búsqueda aproximada y no modifica el
concepto al abrirlo.

## Arquitectura de UI

El paquete `editor.source_catalog` separa responsabilidades:

| Módulo | Responsabilidad |
|---|---|
| `state.py` | Claves namespaced, cambio de base, navegación pendiente, mensajes y tokens one-shot |
| `shared.py` | Contexto explícito, banner de base, estado de índices, resultados tipados y redacción de errores |
| `source_form.py` | Draft tipado para los campos editables de Source |
| `reference_form.py` | Draft tipado de Reference, autores, fechas e invariantes BibTeX |
| `bibtex_ui.py` | Paste/upload, preview puro, errores por entrada, selección y edición |
| `reference_actions.py` | Decisión explícita entre crear una Reference o asociar una existente |
| `workflows.py` | Orquestación parcial segura de Source y References |
| `add_source_page.py` | Página Add Source |
| `edit_source_page.py` | Búsqueda, edición, References, diagnóstico y acciones |
| `legacy_concepts.py` | Tabla paginada y read-only de conceptos exactos |
| `data_quality.py` | Diagnóstico básico y acotado de una Source |

`mathmongo.source_catalog.legacy_repository` es el adaptador core de lectura de
conceptos legacy. Recibe una base explícita y sólo usa operaciones de lectura.
Los módulos visuales no acceden directamente a `db.sources` ni
`db.references`.

### Extensiones core justificadas

Aunque S1B es una fase de UI, algunas responsabilidades no debían quedar
implementadas dentro de Streamlit. Las extensiones core se mantuvieron
acotadas a:

- `legacy_repository.py`, como adaptador tipado, paginado y estrictamente de
  lectura para la colección histórica `concepts`;
- `quality.py`, con la regla pura y tipada de completitud bibliográfica;
- proyecciones y búsquedas candidatas limitadas en los repositorios;
- protección de duplicados y conservación opcional del nombre anterior como
  alias en las operaciones de actualización del servicio.

Estas extensiones reutilizan las colecciones e invariantes de S1A, evitan
duplicar reglas de dominio o consultas MongoDB en la capa visual y no añaden
colecciones, migraciones ni escrituras automáticas.

## Base activa e invariantes de seguridad

La etiqueta de conexión y el nombre real de MongoDB son datos diferentes. El
contexto de página conserva ambos y muestra siempre:

- la etiqueta seleccionada por el usuario;
- `Database.name`, que es el nombre real y autoritativo;
- el estado de las colecciones e índices del catálogo.

Los repositorios, el servicio y el gestor de índices reciben la misma instancia
explícita de `Database`. Las páginas:

- no crean `MongoClient`;
- no vuelven a resolver la base desde la configuración default;
- no cambian automáticamente de conexión;
- no escriben simultáneamente en dos bases;
- no guardan clientes, bases o servicios dentro de `session_state`;
- muestran el nombre real de la base en las confirmaciones de escritura.

Si no existe una conexión activa utilizable, el contexto falla cerrado. Cambiar
la etiqueta o la base real invalida únicamente el estado S1B antes de procesar
navegación, previews o confirmaciones pendientes.

## Catalog Status e índices explícitos

Ambas páginas muestran `Catalog Status`. La sección presenta:

- existencia de `sources` y `references`;
- índices presentes, faltantes y conflictivos;
- plan resultante;
- base real a la que se aplicaría el plan.

Consultar estado y plan no crea colecciones ni índices. `apply()` sólo se llama
desde la acción `Initialize catalog indexes`, después de escribir exactamente
el nombre real de la base y confirmar la operación. Un token de operación evita
reprocesar el mismo submit por un rerun, y `apply()` conserva la idempotencia de
S1A.

El botón de submit queda habilitado cuando existe un plan aplicable; el texto y
checkbox de confirmación se validan después del submit. Un submit incompleto
muestra una advertencia y realiza cero escrituras. Este patrón evita bloquear el
ciclo de formularios de Streamlit y se usa también en las confirmaciones finales
de alta, edición, archivo, desvinculación y borrado.

No existe inicialización automática al importar módulos, abrir la página o
cambiar de conexión. Add Source deshabilita la persistencia mientras el plan no
esté completamente inicializado y sin conflictos.

## Add Source

### Información básica

El formulario permite editar:

- nombre obligatorio;
- descripción visible;
- tipo de Source;
- idioma;
- aliases;
- tags;
- estado de copyright, política de redistribución, licencia y notas de
  derechos.

El estado inicial es `active`. El `source_id` lo genera el modelo, se muestra en
el preview y no es editable.

### Preview de duplicados

El draft se valida antes de consultar candidatos. La UI separa evidencia
`exact`, `strong`, `possible` y `weak`. Las coincidencias exactas, fuertes o
posibles requieren una decisión explícita para crear una Source separada; una
sugerencia exclusivamente débil se muestra pero no bloquea el flujo.

Cambiar los campos básicos invalida el preview almacenado y exige generarlo de
nuevo. La comprobación del servicio se repite al persistir.

Las decisiones de permitir un duplicado están ligadas al fingerprint del draft
concreto que se mostró. Cambiar el contenido editable produce otra identidad de
decisión y obliga a confirmar de nuevo; el fingerprint no contiene el raw
BibTeX, IDs generados ni timestamps.

### References opcionales

La Source puede guardarse sin Reference. También se ofrecen:

- alta manual;
- paste BibTeX;
- upload de contenido `.bib` ya leído por Streamlit.

Cuando existe un candidato duplicado, el usuario elige entre asociar una
Reference existente o crear deliberadamente una separada. No hay fusión
automática.

### Persistencia y resultados parciales

El resumen muestra el `source_id`, la base real y el número de acciones de
Reference. La escritura exige confirmación explícita y usa un token one-shot.
El flujo persiste primero la Source y después procesa cada Reference
seleccionada.

La confirmación final se comprueba después de pulsar el submit. Marcarla no es
un requisito para habilitar el botón, pero un submit sin ella no entra al flujo
de persistencia.

Si una Reference falla después de crear la Source:

- la Source se conserva;
- cada resultado se informa por separado;
- no se borran entidades preexistentes;
- no se intenta un rollback destructivo;
- se ofrece continuar desde Edit / Analyze Source.

## Edit / Analyze Source

### Búsqueda y selección

La búsqueda usa el repositorio S1A y se ejecuta server-side. Admite texto,
estado `active/archived/all`, tipo y tag, con páginas de tamaño limitado y orden
estable. Un listado vacío usa `list()`; una búsqueda textual usa el regex
escapado y limitado del repositorio.

### Overview y edición

El overview muestra identidad estable, nombre, tipo, idioma, aliases, tags,
descripción, derechos, estado, timestamps y conteos de References y conceptos
legacy.

La edición conserva `source_id`. Si cambia el nombre aparece la opción
`Preserve previous name as alias`. Nombre y aliases vuelven a pasar por preview
de duplicados y por la validación del servicio antes de escribir.

### Secciones

La página carga de forma selectiva:

- `Overview & Edit`;
- `References`;
- `Concepts — Legacy Read Only`;
- `Data Quality`;
- `Actions`.

Los formularios, previews y detalles se organizan como secciones hermanas. No
se renderiza ningún `expander` dentro de otro `expander`, incluida la adición de
References desde Edit / Analyze.

Las acciones permiten archivar, reactivar, inspeccionar borrado físico y borrar
sólo cuando `inspect_source_deletion` lo autoriza. La confirmación de borrado
muestra base real, ID, nombre, conteos, blockers y consecuencia, y exige volver
a escribir el `source_id`.

## Editor de Reference

El formulario manual cubre tipo, autores estructurados o literales, título,
año normalizado e histórico, journal, publisher, volume, number, edition, ISBN,
DOI, URL, fecha de acceso, idioma, notas y citekey.

La identidad bibliográfica sigue las reglas S1A: una Reference puede ser válida
sólo por DOI, ISBN, URL o citekey; no se inventan autor o editorial. Las fechas
de acceso se convierten a UTC y los ISBN legacy inválidos muestran sus warnings.

Editar conserva `reference_id`. El raw BibTeX y su SHA-256 se mantienen salvo
que el usuario habilite y aporte un reemplazo explícito. Antes de actualizar se
excluye la propia Reference del preview de duplicados.

La decisión sobre un candidato duplicado queda asociada al fingerprint del
draft editado. Si cambian los campos bibliográficos relevantes, la decisión
anterior deja de ser aplicable.

Cuando una Reference tiene varias `source_ids`, la UI muestra todas las
asociaciones y exige confirmar que la edición afecta a todas. Las acciones
distinguen:

- archivar/reactivar;
- desvincular sólo de la Source seleccionada;
- eliminar físicamente una Reference ya desvinculada únicamente cuando el
  servicio no reporta blockers.

## BibTeX

El flujo acepta una o varias entradas pegadas o un archivo `.bib` leído en
memoria. El preview no escribe y presenta:

- errores individuales;
- ENTRYTYPE y citekey;
- autores, título, año, DOI e ISBN;
- selección parcial de entradas;
- formulario normalizado editable por entrada;
- candidatos duplicados y decisión explícita;
- SHA-256 del raw.

El raw completo no se muestra por defecto. Sólo se ofrece un fragmento acotado
y redactado dentro de un expander. Cambiar el input invalida el preview; un
rerun ajeno no lo pierde si el contenido conserva el mismo digest.

La UI expone como máximo 25 entradas por lote BibTeX. Si el input contiene más,
informa el límite y deja el resto fuera de ese lote; no crea widgets ni acciones
de persistencia sin cota. Las decisiones de duplicado se ligan tanto al digest
de la entrada como al fingerprint de su draft editable.

No existe integración OAuth o API directa con Mendeley. El flujo soportado es
Copy BibTeX/paste o export/upload `.bib`.

## Conceptos legacy — sólo lectura

Los conceptos asociados se obtienen únicamente por igualdad exacta con:

- `Source.name`;
- `Source.legacy.source_strings`.

Los aliases no se incluyen porque el modelo S1A no permite marcarlos como
legacy. No se usa normalización débil, acentos, puntuación ni fuzzy matching.

El adaptador aplica count y paginación server-side, proyección, orden estable,
límite de página y búsqueda escapada. Los filtros disponibles son tipo,
presencia de referencia y texto sobre metadata acotada. La tabla expone ID,
título, tipo, categorías, presencia de referencia, páginas, capítulo, sección,
última actualización y source exacta.

La proyección solicita sólo esos campos escalares y localizadores necesarios;
no carga el objeto completo de `referencia` ni campos grandes no solicitados.
El tamaño de página y la longitud de búsqueda también tienen límites core.

La vista no ejecuta update, delete, create ni índices, y no añade `source_id`,
`reference_id` o `concept_uid` a los conceptos. `Open concept` sólo encola la
identidad exacta `(id, source)` para el mecanismo Edit Concept existente.

## Data Quality básico

El diagnóstico se limita a la Source seleccionada. Informa:

- Source sin References;
- candidatos duplicados de Source;
- References incompletas según su tipo;
- DOI, ISBN o citekey repetidos;
- References archivadas todavía asociadas;
- References compartidas;
- conceptos legacy sin referencia;
- conceptos con el nombre exacto actual que aún no aparece en
  `legacy.source_strings`.

El detalle bibliográfico inspecciona como máximo 100 References y marca cuando
el escaneo fue truncado; el conteo total sigue siendo server-side. No se
implementaron analytics globales ni acciones masivas.

La consulta de calidad usa una proyección dedicada que excluye `bibtex.raw` y
`notes`. La regla de campos incompletos por tipo vive en
`mathmongo.source_catalog.quality`, no en el renderer, y no persiste cambios.

## Session state y reruns

Todas las claves nuevas usan el prefijo `source_catalog_`. El estado centraliza:

- identidad de conexión y base real;
- página pendiente y Source seleccionada;
- target legacy pendiente;
- previews y selección BibTeX;
- filtros y secciones;
- confirmaciones;
- mensajes posteriores a rerun;
- tokens de operaciones completadas.

Un cambio de base elimina sólo claves del catálogo y conserva el estado de las
otras páginas. Las solicitudes pendientes se consumen una vez antes de crear el
widget de navegación. Los tokens de operación evitan repetir una escritura por
rerun y los flujos de alta limpian sus drafts después de una persistencia
exitosa.

Las confirmaciones destructivas o de persistencia se evalúan después del
submit. Las decisiones que dependen del contenido usan fingerprints del draft,
por lo que un rerun conserva una decisión sólo mientras el draft correspondiente
no cambie.

## Manejo de errores

Los resultados tipados distinguen éxito, warning, conflicto, bloqueo, not found
y error. La presentación:

- no muestra traceback;
- redacta URI MongoDB, credenciales y valores de entrada Pydantic;
- limita la longitud del diagnóstico;
- no imprime cuerpos BibTeX completos;
- no expone datos de otra base.

Las páginas no añaden logs fuera del contrato XDG de L2 ni escriben archivos en
HOME, checkout o `site-packages`.

## Pruebas automatizadas

Las pruebas S1B usan UI y servicios falsos, repositorios/fakes aislados y
funciones puras. No requieren MongoDB real. La cobertura focal incluye:

- navegación y preservación de páginas existentes;
- etiqueta frente a nombre real de base;
- limpieza de estado al cambiar de base;
- navegación pendiente y protección contra doble submit;
- status de índices sin escritura y apply confirmado;
- Source sin Reference y Reference manual válida sólo por DOI;
- asociación de una Reference existente;
- resultado parcial sin rollback;
- autores estructurados/literales y fechas UTC;
- conservación de `reference_id` y raw BibTeX;
- paste múltiple, upload ya leído, error individual y selección parcial;
- persistencia de preview entre reruns e invalidación al cambiar input;
- límite de 25 entradas por lote BibTeX en la UI;
- decisiones de duplicado ligadas al fingerprint del draft;
- confirmaciones evaluadas después del submit y ausencia de expanders anidados;
- redacción de URI/credenciales;
- proyección de calidad sin raw BibTeX ni notas;
- conceptos legacy exactos, aislamiento entre dos bases, count, proyección,
  paginación acotada y ausencia de mutación;
- lectura estática del router sin importar ni ejecutar
  `editor/editor_streamlit.py`.

Resultados automatizados finales verificados:

- ejecución focal S1B: `152 passed in 1.53s`;
- suite completa: `493 passed in 54.48s`.

Además, un `AppTest` real de Streamlit con dependencias fake cubre el formulario
de índices: un submit sin confirmación conserva el contador de apply en cero,
la confirmación válida aplica una vez y el rerun posterior no repite la acción.
No usa MongoDB real ni importa la aplicación monolítica.

La pasada estática final quedó verificada: compileall terminó con código cero y
su bytecode se redirigió a un directorio temporal; Ruff quedó limpio en los
módulos/tests del catálogo; el monolito conservó sus 27 diagnósticos históricos
frente a HEAD y añadió cero; `git diff --check` terminó limpio. No se modificó
ninguna dependencia, por lo que no aplicó reconstruir wheel o sdist.

## Validación manual no visual y validación visual

Se completó una validación manual no visual y aislada en la base temporal
`mathmongo_s1b_validation_20260712T070844Z_f567396e`. La evidencia registrada
incluye:

- inicialización de los 15 índices aprobados;
- creación e inspección de 2 Sources y 2 References;
- conservación del raw BibTeX y verificación de su SHA-256;
- rename con identidad estable y conservación del nombre anterior como alias;
- archive y reactivate;
- conflicto por duplicado;
- blocker de borrado y cleanup posterior;
- eliminación de la base temporal al finalizar.

Como controles de aislamiento, los fingerprints antes/después de `MathV0` y
`mathmongo` permanecieron iguales para cada base. El conteo de `MathV0`
permaneció en 186 antes y después y la base siguió sin colecciones `sources` o
`references`.

Durante este protocolo no se abrió un navegador ni se inició una instancia
temporal de Streamlit. Por tanto, la validación visual de layout y comportamiento
interactivo en navegador sigue pendiente; no se presenta la validación manual
no visual como sustituto de esa revisión.

## Limitaciones

- La calidad detallada de References está acotada a 100 registros por Source.
- El upload se procesa como contenido ya leído; no existe almacenamiento de
  archivos Source en S1B.
- Los aliases no tienen una marca `legacy`, por lo que no participan en la
  consulta de conceptos históricos.
- No existe merge de Sources o References.
- La consistencia Source + varias References se informa como resultado parcial,
  no como transacción MongoDB multi-entidad.
- El editor actual de conceptos conserva su identidad histórica `(id, source)`;
  S1B sólo navega hacia él.
- No se añadió un sistema nuevo de export/import en la UI. Los mecanismos core
  S1A permanecen disponibles sin reinterpretar ZIP legacy.
- La verificación visual sigue pendiente hasta ejecutar una sesión aislada en
  navegador.

## Fuera de alcance

S1B no implementa:

- Documents ni colecciones de archivos Source;
- upload, descarga o almacenamiento PDF;
- visor PDF;
- anotaciones, ReadingNote o ConceptEvidenceLink;
- `concept_uid`;
- cambios en Add Concept o integración bibliográfica automática con conceptos;
- migración o backfill de MathV0;
- modificación masiva de conceptos;
- merge de Sources/References;
- Mendeley API;
- búsqueda o analytics globales completos;
- conversión automática de ZIP legacy a catálogo.

## Plan posterior

Una fase S1C puede endurecer ergonomía, accesibilidad, validación visual y
controles operativos sin ampliar el modelo. S2 queda reservado para Documents,
almacenamiento XDG, ingestión segura, hashes, versionado, rights y reconciliación
entre MongoDB y filesystem. El visor PDF y las anotaciones continúan en fases
posteriores según el plan aprobado en S0.

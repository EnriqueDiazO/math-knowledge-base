# Fase S0: auditoría de Sources, referencias, documentos, visor y anotaciones

## 1. Resumen ejecutivo

Esta fase fue exclusivamente de auditoría y diseño. No se implementaron pantallas, colecciones, esquemas, migraciones, visor, carga de archivos ni anotaciones.

El modelo actual no tiene una entidad Source. El nombre de Source es una cadena obligatoria dentro de cada concepto y forma parte de su identidad efectiva: (id, source). Esa cadena también se copia en documentos LaTeX, relaciones, medios, exportaciones y estados de grafos. Renombrarla hoy no es una operación local y puede desalinear datos.

La arquitectura elegida para las fases futuras es un modelo híbrido con entidades principales en colecciones separadas:

- sources;
- references;
- source_documents;
- annotations;
- reading_notes;
- concept_evidence_links.

Cada entidad usará un ID lógico estable, prefijado y basado en UUID v4. Los nombres visibles no serán identidad ni parte autoritativa de una ruta. Los subdocumentos sólo se embeben cuando están naturalmente acotados, como alias de Source, versiones de un Document y selectores de una Annotation.

Para el escenario local se recomienda almacenar archivos administrados bajo XDG Data y mantener sus metadatos en MongoDB. GridFS no será el backend del MVP. Los recursos web serán válidos sin archivo local. El PDF original será inmutable.

Para el visor de sólo lectura se recomienda, en S3, el elemento oficial st.pdf con una versión mínima de Streamlit que lo soporte y su extra PDF, sujeto a aprobación de dependencia. Para anotaciones se recomienda posteriormente un componente propio basado en PDF.js, con comunicación bidireccional y una capa de anotaciones externa. El visor o una librería de terceros nunca será la fuente autoritativa de las anotaciones.

La base configurada por defecto, mathmongo, contiene cero conceptos, pero no representa por sí sola el uso histórico. La ampliación de sólo lectura confirmó que MathV0 existe en el mismo servidor y contiene 186 conceptos, 16 Sources y 145 referencias embebidas. MathV0 confirma deuda legacy real y pasa a ser el inventario de referencia de S0; la arquitectura debe conservar compatibilidad aunque la base predeterminada esté vacía.

## 2. Estado actual

### 2.1 Base Git verificada

| Comprobación | Resultado |
|---|---|
| Directorio de trabajo | /home/enriquedo/PersonalProjects/math-knowledge-base |
| Toplevel Git | /home/enriquedo/PersonalProjects/math-knowledge-base |
| Rama | main |
| HEAD | 6faefa1fa4b42d220a6a6239aa3b5dc5ea331bff |
| Commit esperado | 6faefa1f feat: separate MathMongo data with XDG paths |
| Working tree inicial | limpio |
| Staging inicial | vacío |

Los cinco commits iniciales fueron:

1. 6faefa1f feat: separate MathMongo data with XDG paths
2. 8e5d0c7f feat: add Linux desktop launcher and icon
3. dd0a906e feat: add installable MathMongo entry point
4. 283ae6d6 fix: open Cornell and CPI PDF previews
5. 71a024da Fix error to import images to Cornell

### 2.2 Procesos heredados

No se observó un proceso pytest ni un proceso de build. Sí existía antes de S0 un launcher MathMongo, PID 7883, y su proceso Streamlit, PID 7893, en el puerto configurado 8501. S0 no inició, detuvo, reinició ni modificó esos procesos. Esta es una desviación explícita respecto de la ausencia solicitada, no una ausencia falsamente confirmada.

MongoDB también estaba ejecutándose como servicio. Sólo se lo consultó mediante un cliente directo de lectura; no se instanció MathMongo porque su constructor llama ensure_indexes y puede crear índices.

### 2.3 Contrato L2

Se leyó completo docs/PHASE_L2_XDG_PATHS_AND_SAFE_MIGRATION.md. Este diseño hereda como invariantes:

- recursos instalados y site-packages son de sólo lectura;
- importar módulos no crea directorios ni escribe datos;
- configuración en XDG Config, datos persistentes en XDG Data, temporales en XDG Runtime o Cache, y logs en XDG State;
- exportaciones explícitas bajo Documents/MathMongo;
- rutas de MongoDB lógicas y portables;
- rechazo de symlinks, escapes y destinos dentro del paquete instalado;
- directorios privados 0700 y archivos privados 0600;
- nombres temporales impredecibles;
- importación, exportación, backup y migración conservadores;
- compatibilidad con wheel, futura AppImage y launcher gráfico;
- ninguna migración MongoDB automática al iniciar.

L2 no se modificó.

### 2.4 Dependencias y versión observada

pyproject.toml declara Python 3.10+, Pydantic 2, PyMongo, Streamlit ^1.35, bibtexparser y streamlit-ace. No declara una librería de parsing PDF ni el extra PDF de Streamlit. El entorno auditado tiene Streamlit 1.55.0; expone st.pdf y Components v2, pero no tiene instalado streamlit-pdf. No se instaló ninguna dependencia durante S0.

### 2.5 Modelo real de conceptos

ConceptoBase, en schemas/schemas.py:131-159, declara:

- id y tipo;
- titulo y tipo_titulo;
- contenido_latex y categorias;
- datos de algoritmo;
- comentario;
- una referencia embebida opcional;
- contexto docente y metadatos técnicos;
- fechas;
- source como cadena obligatoria;
- alias_previos_pendientes e image_ids.

El contenido LaTeX se excluye de concepts y se guarda en latex_documents con la misma identidad (id, source). Add Concept valida con Pydantic; Edit Concept hace un $set de un diccionario sin volver a validar. Imports y datos legacy pueden añadir variaciones. Por tanto, el esquema declarado y el realmente persistible no son equivalentes.

### 2.6 Base configurada, seleccionada y utilizada

resolve_config aplica esta precedencia:

1. valores explícitos recibidos por código/CLI;
2. entorno: MONGODB_DB, MONGO_DB o DB_NAME para la base;
3. config XDG config.json;
4. default mathmongo.

El CLI del launcher sólo acepta address, port y browser; no ofrece un argumento de base. Los procesos heredados 7883 y 7893 no tenían variables de entorno de base ni URI, y no existía config XDG. Por tanto, su base configurada era mathmongo.

La UI, por cada sesión Streamlit, crea:

- MathMongo (Current), apuntando a la base resuelta, mathmongo en este proceso;
- MathV0, apuntando explícitamente a MathV0 con el mismo cliente configurado;
- conexiones adicionales que el usuario puede añadir en session_state.

La selección inicial del código es MathMongo (Current). El selectbox de la barra lateral puede cambiar current_connection a MathV0 u otra conexión y hace rerun. Esa selección es por sesión de navegador, no global al PID.

El log heredado confirma inicialización de conexiones a mathmongo y MathV0, dos veces cada una, pero no registra los cambios del selectbox. En consecuencia:

- base configurada por defecto: mathmongo, confirmada;
- selección inicial de una nueva sesión: MathMongo (Current), confirmada por código;
- base realmente activa en una sesión ya abierta del proceso: no verificable de forma segura desde fuera;
- base histórica MathV0: existente, accesible y con datos, confirmada.

Las entidades nuevas siempre deberán quedar acotadas a la base activa y la UI deberá mostrar el nombre real de la base, no sólo la etiqueta de conexión, antes de cualquier escritura.

## 3. Matriz de uso de source y áreas relacionadas

| Área | Modelo actual | Dependencias | Riesgo | Cambio futuro |
|---|---|---|---|---|
| Source | Cadena dentro de concepts | Todo el modelo de conceptos | Crítico | Entidad sources con source_id estable |
| Lista de Sources | concepts.distinct("source") repetido | Dashboard, Add, Edit, Browse, export y grafos | Alto | Repositorio de Sources y consultas únicas |
| new_source_name | No existe como símbolo; “New source name” asigna directamente a source | Add Concept, editor/editor_streamlit.py:1742-1749 | Medio | Add Source explícito; no crear catálogo como efecto colateral |
| Identidad de concepto | (id, source) e id@source | Índices, relaciones, media y grafos | Crítico | concept_uid estable; conservar clave legacy durante transición |
| Add Concept | Opción custom introduce una cadena nueva | Pydantic, concepts, latex_documents y media | Alto | Elegir source_id; alta de Source separada |
| Edit Concept | ID y Source son editables | Varias colecciones no coordinadas | Crítico | No renombrar identidad legacy desde el formulario; servicio explícito posterior |
| Browse Mathematical Concepts | Filtro distinct, regex del usuario y materialización completa | concepts, latex_documents y Quarto | Alto | Paginación server-side, regex escapada y evidencia visible |
| Dashboard | Cuenta strings distintas | concepts y agregaciones ad hoc | Medio | Métricas del catálogo y calidad documental |
| Reference | Un diccionario embebido por concepto | Add/Edit, PDF, Quarto y graph tooltip | Crítico | references normalizadas y links por reference_id |
| Botón referencia anterior | Copia el último dict de igual source | fecha_creacion y session_state compartido | Alto | Seleccionar Reference existente sin duplicarla |
| BibTeX | Archivo .bib, una entrada, mapeo parcial | bibtexparser y estado de formulario | Crítico | Pegar/archivo/múltiples, raw + normalizado y deduplicación |
| Citekey | Comentado en UI pero ausente de Pydantic | Add, Edit y Quarto | Alto | bibtex.key como campo declarado de Reference |
| LaTeX | Metadata y contenido en colecciones separadas | (id, source) | Alto | concept_uid y vínculo de evidencia independiente |
| Relations | Extremos serializados id@source | Regex y parsing con @ | Crítico | Extremos por concept_uid; etiqueta legacy separada |
| Knowledge graphs | Source repetida en filtros, nodos, mapas y extremos | concepts, relations, knowledge_graph_maps | Crítico | source_id/concept_uid y graph_state versionado |
| Media assets | concept_ids contiene id@source | XDG media, concepts y notes | Alto | IDs estables; Document no debe reutilizar este modelo sin endurecerlo |
| PDF preview | Genera un PDF y pide abrir file URI en navegador | LaTeX, runtime y navegador externo | Medio | Visor interno read-only para documentos fuente |
| PDF export | Compila contenido propio a PDF | pdflatex, templates y XDG exports | Medio | Mantener separado de documentos fuente y de PDF anotado |
| Document Builder | Compone conceptos de una Source en un PDF | concepts, latex_documents y relations | Alto | Resolver por source_id y concept_uid |
| Quarto | Genera QMD y references.bib desde referencias embebidas | citekey, source e id | Alto | Consumir Reference normalizada; no duplicar bibliografía |
| Cornell | latex_notes con payload cornell; source_refs libre por página | media, render LaTeX y Cuaderno | Medio/alto | ReadingNote tipada; conservar source_refs legacy |
| CPI | latex_notes con payload cpi, sin procedencia tipada | media, render LaTeX y Cuaderno | Medio | ReadingNote y evidencia tipadas |
| DB export/import | JSON de todas las colecciones y árbol media | lista de colecciones y XDG Data | Alto | Manifiesto versionado, checksums y políticas de inclusión |
| Backups | ZIP JSON + media; cleanup backups separados | XDG Data y Documents | Alto | Backup coordinado de MongoDB y archivos Source |
| Índices | Inicialización dentro de MathMongo.__init__ | Apertura de app e import | Alto | Inicialización/migración explícita y verificable |
| Interfaces CLI | interface.py y editor/interface.py divergen | Pydantic y rutas por nombre sanitizado | Alto legacy | Consolidar o retirar; nunca usar nombre visible como identidad |

## 4. Inventario MongoDB de sólo lectura

### 4.1 Alcance, método y tres estados de base

La primera lectura se realizó el 2026-07-12T04:59:32Z y la ampliación de MathV0 el 2026-07-12T05:10:52Z. Se usó PyMongo 4.15.1 directamente, con secondaryPreferred y retryWrites=False. Las operaciones fueron ping, list_database_names, list_collection_names, count_documents, find e index_information; las normalizaciones y fingerprints se calcularon client-side.

No se llamó create_index, no se instanció MathMongo y no se ejecutó ninguna escritura. No se imprimieron URI, credenciales, IDs de documentos ni cuerpos LaTeX.

Deben distinguirse tres estados:

| Estado | Resultado confirmado |
|---|---|
| Base configurada por defecto | mathmongo; no había config XDG ni variables MongoDB de proceso |
| Base histórica encontrada | MathV0; existe, es accesible y contiene el corpus legacy |
| Base activa de la sesión del navegador | No pudo determinarse sin intervenir session_state del Streamlit heredado |

El código inicia cada sesión con mathmongo, pero crea también una conexión a MathV0 y permite cambiarla en la barra lateral. Que el log muestre ambas conexiones no demuestra cuál estaba seleccionada por el navegador.

### 4.2 Bases no administrativas encontradas

| Base | Colecciones y conteos básicos |
|---|---|
| MathV0 | backlog_items 3; concepts 186; deliverables 2; knowledge_graph_maps 2; latex_documents 187; latex_notes 34; media_assets 10; relations 136; weekly_reviews 0; worklog_entries 5 |
| mathmongo | backlog_items 1; concepts 0; deliverables 0; knowledge_graph_maps 0; latex_documents 0; latex_notes 5; media_assets 0; relations 0; statements 0; weekly_reviews 1; worklog_entries 1 |
| db_ph | audiofiles 9; comparisons 0; cvc_sequences 916; phonemes 5320; speakers 14; utterances 253; words 1643 |
| penitentiaries | Action 7; Case 2; Chunk 1; Country 1; Dependency 1; Location 1; PIN 1000; Penitentiary 1; Profile 1; ReceivedAudio 0; ReceivedTranscription 0; RelationCasePIN 1; Speaker 2; State 32; TransmittedAudio 0; TransmittedTranscription 0; UploadedFile 2; User 1 |
| waveform_lab | audios 13; jobs 60; segments 2502; transcriptions 0 |

Sólo mathmongo y MathV0 fueron tratadas como bases candidatas de MathMongo. No se infirió el propósito, propietario ni compatibilidad de las otras tres bases.

### 4.3 Base configurada mathmongo

Los resultados exclusivos de mathmongo son:

| Indicador | Resultado |
|---|---:|
| concepts | 0 |
| Sources distintas | 0 |
| referencias/citekeys/DOI/ISBN | 0 |
| rutas PDF o URL reconocibles en concepts | 0 |
| localizadores documentales en concepts | 0 |

Sus colecciones pobladas observadas fueron backlog_items 1, latex_notes 5, weekly_reviews 1 y worklog_entries 1. Existe un worklog_entries.evidence_url no vacío, pero es un string corto sin esquema, host, forma de ruta ni extensión PDF; su valor no se imprimió.

Estos ceros describen únicamente mathmongo. No son evidencia global de ausencia de Sources, referencias, documentos o deuda legacy.

### 4.4 Base histórica MathV0: colecciones y esquema de conceptos

MathV0 es accesible y contiene:

| Colección | Documentos |
|---|---:|
| backlog_items | 3 |
| concepts | 186 |
| deliverables | 2 |
| knowledge_graph_maps | 2 |
| latex_documents | 187 |
| latex_notes | 34 |
| media_assets | 10 |
| relations | 136 |
| weekly_reviews | 0 |
| worklog_entries | 5 |

No existen las colecciones futuras sources, references, source_documents, annotations, reading_notes ni concept_evidence_links.

Campos top-level reales de concepts:

| Campo | Presente | Observación |
|---|---:|---|
| _id, id, source, tipo, titulo, tipo_titulo | 186 cada uno | núcleo de identidad/presentación |
| categorias | 186 | 170 no vacías |
| es_algoritmo, contexto_docente, metadatos_tecnicos | 186 cada uno | estructura actual |
| fecha_creacion, ultima_actualizacion | 186 cada uno | timestamps |
| referencia | 145 | todos los valores observados son objetos no vacíos |
| comentario | 135 | 124 no vacíos |
| contenido_latex | 53 | copia legacy adicional al contenido separado |
| pasos_algoritmo | 53 | 2 no vacíos |
| alias_previos_pendientes | 33 | 4 no vacíos |
| image_ids | 17 | 2 no vacíos |
| citekey | 16 | 1 no vacío |

La presencia de contenido_latex en 53 concepts y 187 latex_documents confirma heterogeneidad histórica del esquema.

### 4.5 MathV0: Sources y calidad de nombres

Los 186 conceptos tienen source string no vacío:

- missing: 0;
- null: 0;
- blank: 0;
- no string: 0;
- conceptos sin Source utilizable: 0;
- Sources exactas: 16.

| Source | Conceptos |
|---|---:|
| ADR | 1 |
| APIs-Servicios | 2 |
| Bioinformática | 4 |
| BottcherKarlovich1997 | 51 |
| Digital_Processing_Speech_Signal_Rabiner_1978_PretticeHall | 4 |
| HID-Pairing-Rec | 18 |
| IAIngenieria | 16 |
| Karlovich2017_Haseman_BVP_SO_Shifts | 15 |
| Linux-Display-Control-Recipe | 6 |
| Pommerenke1991BoundaryBehaviourConformalMaps | 9 |
| Principles_Mathematical_Analysis_Rudin_1964_McGraw-Hill | 15 |
| ProGit2024 | 15 |
| Python | 15 |
| Real_Complex_Analysis_Rudin_1987_McGraw-Hill | 5 |
| Signals_Systems_Willsky_1996_PrenticeHall | 9 |
| VoiceTools | 1 |

No se encontraron grupos de variantes entre esos 16 valores al normalizar:

- mayúsculas/minúsculas, trim y espacios repetidos;
- acentos;
- puntuación.

Esto sólo indica que no hay variantes detectadas en el conjunto actual de MathV0. No convierte los nombres en IDs estables ni permite fusionarlos automáticamente.

### 4.6 MathV0: referencias y campos bibliográficos

Hay 145 conceptos con referencia como objeto no vacío y 41 sin el campo referencia. No se observaron referencias string, null o diccionarios vacíos.

| Subcampo de referencia | Presente | No vacío | Tipo observado |
|---|---:|---:|---|
| tipo_referencia | 145 | 145 | string |
| fuente | 145 | 145 | string |
| anio | 143 | 143 | int |
| autor | 140 | 140 | string |
| issbn | 119 | 102 | string/None; no se observó isbn correcto |
| paginas | 117 | 112 | string/None |
| editorial | 111 | 104 | string/None |
| tomo | 105 | 73 | string/None |
| capitulo | 98 | 91 | string/None |
| url | 89 | 52 | string/None |
| seccion | 78 | 40 | string/None |
| edicion | 57 | 28 | string/None |
| doi | 55 | 15 | string/None |
| citekey | 14 | 1 | string/None |

No se observó un campo con BibTeX original ni una entrada BibTeX textual. Los años bibliográficos son 143 enteros no vacíos; dos referencias no tienen anio.

Duplicados calculados sin imprimir metadata completa:

| Criterio | Resultado |
|---|---|
| Referencia normalizada completa, incluyendo locator | 41 fingerprints distintos; 19 grupos repetidos; 123 conceptos dentro de grupos; grupo máximo 21 |
| Identidad bibliográfica, ignorando locator | 20 identidades; 13 grupos repetidos; 138 conceptos dentro de grupos; grupo máximo 51 |
| Heurística de identidad | DOI, después ISBN, después citekey, después autor/título-año y URL; sólo diagnóstico, no regla de fusión |

La normalización completa elimina diferencias irrelevantes como null frente a ausente y whitespace; por eso no equivale a comparar bytes BSON. Los fingerprints son diagnósticos client-side y no se guardaron.

Citekeys:

- citekey top-level está presente en 16 conceptos, pero sólo uno es no vacío;
- referencia.citekey está presente en 14 referencias, pero sólo uno es no vacío;
- ambos valores no vacíos corresponden al mismo concepto y al mismo valor lógico;
- citekeys lógicos distintos: 1;
- duplicados entre conceptos: 0.

DOI:

- valores no vacíos: 15;
- DOI normalizados distintos: 1;
- el único grupo, 10.1007/978-3-319-49182, aparece en 15 conceptos.

ISBN/issbn:

- valores no vacíos: 102;
- normalizados distintos: 6;
- grupos duplicados: 5;
- conceptos en grupos duplicados: 101;
- frecuencias: 9783764354596, 51; 9780070856134, 15; 9783319491806, 15; 9781484200773, 13; 9783642081293, 7.

Estas repeticiones son el caso real que justifica extraer Reference de Concept. No autorizan una fusión automática: localizadores y metadata pueden diferir.

### 4.7 MathV0: URL, PDF, localizadores y texto histórico

| Indicador en concepts/referencia | Resultado |
|---|---:|
| referencia.url no vacía | 52 conceptos |
| URL de referencia que termina en PDF | 1 concepto |
| paginas no vacía | 112 conceptos |
| paginas con literal N/A | 13 |
| paginas aparentemente útiles | 99 |
| capitulo no vacío | 91 conceptos |
| seccion no vacía | 40 conceptos |
| campo equation/ecuacion localizador | 0 |
| campo theorem/teorema localizador | 0 |

Valores de páginas y frecuencias, sin contenido del concepto:

- 1: 21; 7: 18; 463–500: 15; N/A: 13; 5: 10; 337: 9;
- 8: 5; 11: 4; 3 y 6: 3 cada uno; 4: 2;
- 1-2, 3-4, 4-7, 12, 14, 16, 19, 23 y xxvii: 1 cada uno.

Capítulos: 1 en 81 conceptos, 10 en 9 y Foreword en 1.

Secciones: 10 valores distintos en 40 conceptos. Incluyen 1. Introduction en 11, comandos HID en 8, Some Basic Facts en 7, Introduction en 5 y otros valores con frecuencias menores. El valor !. Introduction aparece tres veces y es un caso de calidad a revisar, no a corregir automáticamente.

No hay localizador explícito de ecuación o teorema. Sí hay contenido matemático:

- 9 latex_documents vinculables a conceptos contienen marcadores equation, align, eqref o tag;
- 3 copias legacy concept.contenido_latex contienen esos marcadores;
- 5 latex_notes y los 2 snapshots de knowledge_graph_maps también contienen marcadores de ecuación.

Referencias históricas en texto libre:

- concepts.referencia siempre es objeto, no texto libre;
- latex_documents: 3 documentos con cite, 1 con thebibliography/bibitem y 6 con DOI textual; las categorías pueden solaparse;
- latex_notes: 3 con cite, 2 con bibliografía, 1 con encabezado de referencia y 1 con DOI textual; las categorías pueden solaparse;
- los 2 knowledge_graph_maps duplican resúmenes de referencia dentro de graph_state;
- no se detectaron entradas BibTeX ni ISBN textual.

No se imprimió ningún fragmento. Las coincidencias son regex diagnósticas y pueden omitir formatos no estándar.

### 4.8 MathV0: colecciones acopladas y uso de id@source

latex_documents:

- 187 documentos;
- los 186 concepts tienen contraparte por (id, source);
- existe 1 latex_document huérfano adicional, bajo BottcherKarlovich1997;
- índice único (id, source);
- 9 contienen marcadores de ecuación;
- 3 contienen cite y al menos 1 contiene una bibliografía explícita.

relations:

- 136 documentos;
- índice único (desde, hasta, tipo);
- el modelo y los repositorios actuales serializan cada extremo como id@source.

knowledge_graph_maps:

- 2 documentos;
- contienen filtros/source y snapshots graph_state con Source e información de referencias repetida;
- map_uid no es único;
- nodos y extremos usan la identidad compuesta definida por el código.

media_assets:

- 10 documentos;
- los 10 son image/png, storage_type local y rutas lógicas/relativas .png;
- PDF assets: 0;
- asset_id es único; concept_ids indexa la clave compuesta usada por el código.

Usos legacy de id@source confirmados por código y por la presencia de sus colecciones consumidoras:

1. identidad e índices de concepts y latex_documents;
2. extremos desde/hasta de relations;
3. media_assets.concept_ids;
4. IDs de nodos/aristas y filtros de knowledge_graph_maps.

No se imprimieron endpoints ni estados de grafo y no se verificó en S0 la integridad individual de cada una de las 136 relaciones, 10 asociaciones media o 2 snapshots. La migración necesitará un auditor específico sobre una copia aislada.

### 4.9 Índices relevantes de MathV0

- concepts: único (id, source).
- latex_documents: único (id, source).
- relations: único (desde, hasta, tipo).
- knowledge_graph_maps: created_at, updated_at, name, tags, filtros de Sources/tipos, source y map_uid; ninguno único.
- media_assets: asset_id único; concept_ids, note_ids, path, filename, MIME, storage_type, tags y created_at.
- latex_notes: date/updated_at, project/date, note_format y compounds por format/context/date/project.
- weekly_reviews: único (iso_year, iso_week).
- backlog_items, deliverables y worklog_entries: índices parciales operativos por proyecto, estado y fecha.

### 4.10 Inventario confirmado y datos no verificables

Confirmado:

- mathmongo es la base configurada y tiene concepts=0;
- MathV0 existe y tiene el corpus de 186 conceptos;
- sus conteos, Sources, campos, duplicados, localizadores e índices anteriores;
- no se hicieron escrituras MongoDB.

No pudo verificarse:

- qué base estaba seleccionada en la sesión concreta del navegador;
- un snapshot transaccional, porque el Streamlit heredado siguió activo;
- si los conteos cambiaron después del timestamp;
- la integridad de cada endpoint id@source;
- el significado de bases locales ajenas a MathMongo;
- archivos externos detrás de las URL o backups/exports que no están en MongoDB.

La deuda legacy de MathV0 es real aunque su calidad de source strings sea actualmente consistente.

## 5. Modelo conceptual

### 5.1 Source

Unidad lógica de estudio o procedencia: libro, artículo, tesis, web, documentación, curso, corpus, informe, proyecto o colección. Puede existir sin Reference, Document o Concept.

Cardinalidades:

- una Source tiene cero o muchas References;
- una Source tiene cero o muchos Documents;
- una Source tiene cero o muchas ReadingNotes;
- una Source se vincula con cero o muchos Concepts mediante ConceptEvidenceLink o por asociación de catálogo.

### 5.2 Reference

Registro bibliográfico global y reutilizable. Puede asociarse con varias Sources sin duplicar metadatos. Conserva entrada BibTeX original y representación normalizada.

### 5.3 Document

Recurso consultable concreto. Tipos mínimos: pdf, web, supplementary_pdf, preprint, image, text y other. Pertenece a una Source autoritativa y puede enlazarse opcionalmente con una Reference. Una Source web sin archivo es válida.

### 5.4 Annotation

Marca localizada y no destructiva dentro de una versión exacta de un Document: highlight, text_note, area_note o bookmark.

### 5.5 ReadingNote

Nota amplia de lectura. Puede apuntar simultáneamente a Source, Reference, Document, Annotation y Concept. Cornell y CPI pueden integrarse gradualmente como formatos especializados, sin reinterpretar project como Source.

### 5.6 ConceptEvidenceLink

Entidad autoritativa de procedencia entre un concepto y evidencia documental. Separa la bibliografía global del localizador concreto que justifica un concepto.

### 5.7 Identidad e integridad

- IDs de dominio: strings con prefijo y UUID v4, por ejemplo src_, ref_, doc_, ann_, note_ y ev_.
- MongoDB puede conservar su _id interno; todas las relaciones de dominio usan los IDs explícitos.
- Timestamps: BSON datetime en UTC y schema_version entero.
- No hay hard delete en el flujo normal; se usa status y timestamps de archivado.
- MongoDB no ofrece foreign keys. Repositorios de aplicación validan referencias, y un auditor de integridad reporta huérfanos.
- Renombrar Source sólo cambia name y aliases; source_id y rutas permanecen estables.

## 6. Decisión de colecciones

### 6.1 Alternativas

| Criterio | A: References/Documents embebidos | B: colecciones separadas | C: híbrido |
|---|---|---|---|
| Tamaño documental | Crece sin límite práctico por Source | Pequeño por entidad | Pequeño; arrays acotados |
| Cardinalidad | Mala para Documents/Annotations | Natural para uno-a-muchos | Natural |
| Consultas | Una lectura de Source, pero arrays costosos | Requiere joins de aplicación | Consultas claras y resúmenes opcionales |
| Actualizaciones | Contención sobre un documento grande | Independientes | Independientes en entidades principales |
| Índices | Limitados dentro de arrays anidados | Precisos por colección | Precisos |
| Export/import | Un árbol grande y frágil | Manifiesto por entidad | Manifiesto claro |
| Migración | Fácil al inicio, difícil al crecer | Explícita pero controlable | Controlable |
| Integridad | Atomicidad local, referencias duplicadas | Integridad de aplicación | Integridad de aplicación |
| Edición | Formulario único, conflictos grandes | Pantallas por recurso | Buena |
| Escalabilidad | Mala para anotaciones | Buena | Buena |
| Backup | Simple sólo mientras sea pequeño | Archivos + colecciones | Archivos + colecciones |
| Legacy | Invita a seguir embebiendo referencia | Permite dual-read | Permite dual-read y subdocumentos acotados |

### 6.2 Arquitectura elegida

Se elige C, modelo híbrido, con las seis colecciones principales separadas. Sólo se embeben:

- aliases y preferencias acotadas en Source;
- raw/normalized de una misma Reference;
- versiones de archivo, normalmente pocas, en Document;
- selectores de una Annotation;
- targets tipados de una ReadingNote.

No se embeben listas completas de References, Documents, Annotations ni Concepts dentro de Source. No se replica una Reference completa en Concept.

references usa source_ids para asociación muchos-a-muchos. source_documents mantiene un source_id autoritativo y un reference_id opcional. concept_evidence_links es la única relación autoritativa concepto-evidencia; linked_concept_ids en Annotation, si se materializa, será un cache reconstruible.

## 7. Esquemas propuestos

Los siguientes son contratos de diseño, no esquemas creados en S0.

### 7.1 Source

~~~json
{
  "schema_version": 1,
  "source_id": "src_<uuid4>",
  "name": "Nombre visible",
  "name_normalized": "nombre visible",
  "aliases": [
    {"value": "Alias preservado", "normalized": "alias preservado"}
  ],
  "source_type": "book|article|thesis|web|documentation|course|corpus|report|project|bibliographic_collection|other",
  "description": "",
  "language": null,
  "tags": [],
  "status": "active|archived",
  "rights_default": {
    "copyright_status": "unknown|copyrighted|public_domain|licensed",
    "redistribution": "ask|include|metadata_only|exclude",
    "license": null,
    "notes": null
  },
  "legacy": {
    "source_strings": [],
    "migration_batch_id": null
  },
  "created_at": "<UTC>",
  "updated_at": "<UTC>"
}
~~~

Normalización para búsqueda: Unicode NFKC, trim, colapso de whitespace y casefold. Una clave adicional sin acentos/puntuación sólo servirá para sugerir posibles duplicados; nunca fusionará automáticamente.

### 7.2 Reference

~~~json
{
  "schema_version": 1,
  "reference_id": "ref_<uuid4>",
  "source_ids": ["src_<uuid4>"],
  "reference_type": "book|article|thesis|web|report|proceedings|chapter|course|misc",
  "bibtex": {
    "key": null,
    "key_normalized": null,
    "entry_type": null,
    "raw": null,
    "raw_sha256": null
  },
  "authors": [
    {"family": "", "given": "", "literal": null, "orcid": null}
  ],
  "title": "",
  "year": null,
  "year_raw": null,
  "journal": null,
  "publisher": null,
  "volume": null,
  "number": null,
  "edition": null,
  "isbn": [],
  "doi": null,
  "doi_normalized": null,
  "url": null,
  "accessed_at": null,
  "language": null,
  "notes": null,
  "fingerprints": {
    "author_title_year": null,
    "isbn_normalized": []
  },
  "provenance": {
    "import_method": "manual|bibtex_paste|bib_file|legacy",
    "imported_at": "<UTC>"
  },
  "status": "active|archived|needs_review",
  "created_at": "<UTC>",
  "updated_at": "<UTC>"
}
~~~

DOI conserva el valor original y uno normalizado sin doi:, protocolo ni host doi.org. ISBN conserva valores originales y normalizados, con validación de checksum. BibTeX key se preserva exactamente y se normaliza sólo para detección.

### 7.3 Document

~~~json
{
  "schema_version": 1,
  "document_id": "doc_<uuid4>",
  "source_id": "src_<uuid4>",
  "reference_id": "ref_<uuid4>|null",
  "document_type": "pdf|web|supplementary_pdf|preprint|image|text|other",
  "title": "",
  "language": null,
  "current_version": 1,
  "versions": [
    {
      "version": 1,
      "original_filename": "nombre proporcionado.pdf",
      "stored_filename": "original.pdf",
      "logical_path": "sources/src_x/documents/doc_y/versions/000001/original.pdf",
      "mime_declared": "application/pdf",
      "mime_detected": "application/pdf",
      "size_bytes": 0,
      "sha256": "",
      "page_count": null,
      "pdf_version": null,
      "pdf_metadata": {},
      "origin": {
        "kind": "upload|download|local_import|generated",
        "original_url": null,
        "doi": null,
        "downloaded_at": null,
        "uploaded_at": "<UTC>"
      },
      "rights": {
        "copyright_status": "unknown",
        "redistribution": "ask",
        "license": null,
        "restrictions": null
      },
      "status": "pending|available|quarantined|missing|superseded",
      "supersedes_version": null,
      "created_at": "<UTC>"
    }
  ],
  "web": {
    "url": null,
    "url_normalized": null,
    "domain": null,
    "accessed_at": null,
    "quoted_fragment": null,
    "section": null,
    "anchor": null,
    "link_status": "unchecked|ok|redirected|broken",
    "last_checked_at": null,
    "snapshot_document_id": null
  },
  "status": "active|archived",
  "created_at": "<UTC>",
  "updated_at": "<UTC>"
}
~~~

Invariantes:

- pdf y variantes PDF requieren al menos una versión available;
- web requiere URL http/https y no requiere archivo;
- cada versión es inmutable;
- reemplazar añade una versión, nunca sobrescribe bytes;
- Annotation fija document_id, version y SHA-256;
- original_filename nunca participa en una ruta.

### 7.4 Annotation

~~~json
{
  "schema_version": 1,
  "annotation_id": "ann_<uuid4>",
  "document_id": "doc_<uuid4>",
  "document_version": 1,
  "document_sha256": "",
  "page_index": 0,
  "page_label": "1",
  "annotation_type": "highlight|text_note|area_note|bookmark",
  "selected_text": null,
  "selectors": {
    "text_quote": {"exact": null, "prefix": null, "suffix": null},
    "text_position": {
      "start": null,
      "end": null,
      "extraction_sha256": null
    },
    "geometry": {
      "coordinate_space": "normalized_unrotated_crop_box",
      "page_rotation": 0,
      "rects": [],
      "polygons": [],
      "pdf_points": []
    }
  },
  "color": "#FFF59D",
  "comment": null,
  "tags": [],
  "author_local": "local",
  "linked_concept_ids": [],
  "status": "active|orphaned|archived|deleted",
  "resolution": {
    "state": "exact|relocated|ambiguous|orphaned",
    "resolved_against_version": 1,
    "method": "sha256|quote|position|geometry|manual",
    "resolved_at": null
  },
  "created_at": "<UTC>",
  "updated_at": "<UTC>"
}
~~~

### 7.5 ReadingNote

~~~json
{
  "schema_version": 1,
  "reading_note_id": "note_<uuid4>",
  "note_format": "plain|markdown|cornell_math_v1|cpi_v1",
  "title": "",
  "body": "",
  "targets": {
    "source_id": "src_<uuid4>|null",
    "reference_id": "ref_<uuid4>|null",
    "document_id": "doc_<uuid4>|null",
    "document_version": null,
    "annotation_ids": [],
    "concept_uids": []
  },
  "locator": {
    "page_index": null,
    "page_label": null,
    "chapter": null,
    "section": null
  },
  "tags": [],
  "status": "draft|active|archived|deleted",
  "created_at": "<UTC>",
  "updated_at": "<UTC>"
}
~~~

### 7.6 ConceptEvidenceLink

~~~json
{
  "schema_version": 1,
  "evidence_link_id": "ev_<uuid4>",
  "concept_uid": "concept_<uuid4>|null",
  "legacy_concept_key": {
    "id": "def:grupo_001",
    "source": "Nombre legacy"
  },
  "source_id": "src_<uuid4>",
  "reference_id": "ref_<uuid4>|null",
  "document_id": "doc_<uuid4>|null",
  "document_version": null,
  "document_sha256": null,
  "annotation_ids": [],
  "locator": {
    "page_index": null,
    "page_label": null,
    "chapter": null,
    "section": null,
    "equation": null,
    "theorem": null
  },
  "quoted_text": null,
  "location_note": null,
  "status": "active|superseded|orphaned|deleted",
  "created_at": "<UTC>",
  "updated_at": "<UTC>"
}
~~~

concept_uid deberá añadirse gradualmente a concepts en una fase futura. legacy_concept_key permite vincular un concepto antes del backfill y no debe ser la identidad final.

### 7.7 Propiedad de los datos

| Dato | Entidad autoritativa |
|---|---|
| Autores, título, año, revista, editorial, DOI, ISBN | Reference |
| Archivo, hash, MIME, páginas, versión, URL y derechos | Document |
| Selección, geometría, página exacta, comentario de marca | Annotation |
| Página/capítulo/sección/ecuación usada por un concepto | ConceptEvidenceLink |
| Nota extensa y reflexión | ReadingNote |
| Nombre, alias, tipo y política default | Source |

## 8. Almacenamiento XDG

### 8.1 Alternativas

| Opción | Ventajas | Costes/riesgos | Decisión |
|---|---|---|---|
| XDG Data + MongoDB | Simple, auditable, compatible con visor local, wheel y backup | Coordinación entre DB y filesystem | Elegida |
| GridFS | Un backend MongoDB y streaming por chunks | DB pesada, backup más lento, integración de visor y derechos más compleja | No para MVP |
| Completamente externo | No duplica archivos | Rutas rotas, permisos, symlinks y baja portabilidad | Sólo puntero legacy explícito |
| Híbrido | Permite web y excepciones externas | Más estados | Política elegida: managed local por default, web sin archivo |

### 8.2 Estructura

~~~text
$XDG_DATA_HOME/mathmongo/
├── sources/
│   └── <source_id>/
│       └── documents/
│           └── <document_id>/
│               └── versions/
│                   └── 000001/
│                       └── original.pdf
├── quarantine/
└── backups/
~~~

Rutas lógicas guardadas en MongoDB comienzan en sources/... y nunca incluyen HOME, XDG Data ni una ruta absoluta. Los nombres visibles no forman directorios.

Runtime y cache:

~~~text
$XDG_RUNTIME_DIR/mathmongo/document_ingest/<token-aleatorio>/
$XDG_CACHE_HOME/mathmongo/pdf_text/<sha256>/
$XDG_STATE_HOME/mathmongo/logs/
$DOCUMENTS/MathMongo/source_exports/
~~~

### 8.3 Ingesta y deduplicación

Flujo futuro:

1. Crear staging privado con nombre aleatorio dentro de runtime.
2. Leer por chunks, aplicar límite y calcular SHA-256 durante la copia.
3. Rechazar archivo vacío, symlink, path traversal y nombre no confiable.
4. Validar extensión sólo como señal; verificar MIME/cabecera y parseabilidad.
5. Buscar el hash en source_documents.
6. Si ya existe en la misma Source, ofrecer reutilizar Document y no copiar.
7. Si existe en otra Source, advertir y exigir elección: asociación bibliográfica o copia intencional; nunca fusionar procedencia sin revisión.
8. Copiar a un archivo .partial impredecible en el filesystem final, chmod 0600, flush y fsync.
9. Hacer os.replace dentro del mismo filesystem y fsync del directorio cuando sea razonable.
10. Marcar la versión available en MongoDB.

No existe transacción atómica entre MongoDB y filesystem. Se usa estado pending, operación idempotente y reconciliación de pendientes/huérfanos. Un fallo después de copiar no publica el archivo al visor hasta que el metadata sea available.

### 8.4 Límites y validación

Recomendación inicial: 250 MiB por upload, configurable y con un máximo duro aprobado antes de S2. La lectura siempre será streaming; no se cargará el PDF completo en memoria para validar o hashear.

Para PDF:

- cabecera %PDF- dentro del prefijo permitido;
- parser que pueda leer estructura y número de páginas;
- MIME detectado application/pdf;
- límites de páginas, objetos y tiempo de parsing;
- nunca ejecutar JavaScript, adjuntos ni acciones del PDF;
- no invocar herramientas con shell=True.

La selección concreta de parser backend es una decisión humana pendiente porque el proyecto no tiene hoy una dependencia PDF.

### 8.5 Versionado, cuarentena y limpieza

- original.pdf es inmutable.
- Reemplazar crea versions/000002 y conserva 000001.
- La versión nueva sólo se vuelve current tras validación.
- Archivo inválido: borrar por default; cuarentena opcional privada, nunca servida y con retención limitada.
- Limpieza valida contención y symlinks con la política L2.
- No se siguen links ni se borra un fallback histórico.
- Web no crea directorio hasta que exista un snapshot explícito.

## 9. Visor PDF

### 9.1 Estado actual

editor/pdf_preview.py sólo prepara rutas controladas y abre un PDF local existente mediante file URI en una pestaña del navegador. Add/Edit Concept, Cornell y CPI generan PDFs propios por LaTeX. No existe un visor de documentos fuente, navegación controlada, selección de texto ni eventos de anotación.

### 9.2 Comparación

| Alternativa | Navegación/zoom/búsqueda | Selección/coordenadas | Eventos a Python | Offline/empaquetado | Seguridad/mantenimiento |
|---|---|---|---|---|---|
| st.pdf oficial | Adecuado para lectura | No es API de anotación | No suficiente | Extra empaquetable; acepta path/bytes | Menor mantenimiento propio |
| PDF.js en componente propio | Completo y controlable | Text layer y geometría | Sí | Assets vendorizados en wheel/AppImage | Mayor superficie y mantenimiento |
| iframe/HTML con visor nativo | Depende del navegador | Sin contrato estable | Prácticamente no | Problemas con file URL/base64 | Inconsistente; difícil CSP |
| Componente Streamlit de tercero | Variable | Variable | Variable | Nueva dependencia | Requiere auditoría de salud/licencia |
| Abrir navegador externo | Visor maduro del usuario | Fuera de MathMongo | No | Sí | Fallback, no cumple integración |
| Componente bidireccional | Completo | Completo | Sí | Sí si se empaqueta | Requiere protocolo y pruebas |

La documentación oficial indica que st.pdf existe desde Streamlit 1.49, acepta path, bytes y file-like, y requiere el extra streamlit[pdf]: https://docs.streamlit.io/develop/api-reference/media/st.pdf

PDF.js ofrece core, display layer y viewer; Mozilla recomienda el viewer como punto de partida, no copiarlo sin adaptación: https://mozilla.github.io/pdf.js/getting_started/

Components v2 es el mecanismo moderno recomendado por Streamlit para callbacks y estado bidireccional: https://docs.streamlit.io/develop/concepts/custom-components/overview

### 9.3 Recomendación A: MVP read-only

Usar st.pdf en S3, después de:

- elevar y fijar la versión mínima de Streamlit a una versión probada con st.pdf;
- añadir explícitamente el extra PDF;
- comprobar funcionamiento completamente offline en wheel y AppImage;
- entregar sólo paths XDG validados o bytes de un Document available;
- conservar “Abrir externamente” como fallback;
- no aceptar URL remota directamente en el visor del MVP.

Alcance: abrir, desplazarse, zoom/búsqueda que ofrezca el viewer y descargar sólo si la política de derechos lo permite. No promete callback de página, selección ni anotación.

### 9.4 Recomendación B: anotaciones

Construir en S4 un componente propio con PDF.js vendorizado y fijado, una capa overlay y Components v2. El protocolo emitirá:

- document_id, version y hash;
- page_index/page_label;
- cambio de página;
- selección textual con quote y posición;
- rectángulos/polígonos normalizados;
- zoom y rotación sólo como estado de vista;
- eventos create/update/delete sin guardar automáticamente cada movimiento.

PDF.js se aislará en un contexto sandboxed o componente con CSP estricta. Sólo leerá bytes locales autorizados; se bloquearán acciones, formularios activos, scripts, adjuntos y navegación externa automática. Los assets JS deben formar parte del wheel/AppImage, sin CDN.

### 9.5 Rendimiento y accesibilidad

- Render lazy de páginas visibles; no renderizar todo un PDF grande a alta resolución.
- Cache por SHA-256, versión de PDF.js y parámetros de extracción.
- Debounce de eventos para evitar un rerun de Streamlit por cada movimiento.
- Toolbar accesible por teclado, foco visible, labels ARIA, contraste y zoom del navegador.
- Conservar texto seleccionable cuando exista; para PDF escaneado, informar que OCR está fuera del MVP.
- En pantallas estrechas, apilar visor y notas.

## 10. Anotaciones no destructivas

### 10.1 Comparación de selectores

| Selector | Ventaja | Debilidad |
|---|---|---|
| Coordenadas absolutas | Precisas para exportar a PDF | Dependientes de CropBox, rotación y unidades |
| Coordenadas normalizadas | Sobreviven zoom y viewport | No sobreviven remaquetación/versiones por sí solas |
| TextQuoteSelector | Reubica texto por exact/prefix/suffix | Ambiguo si la cita se repite |
| TextPositionSelector | Compacto y determinista en una extracción | Cambia con el extractor o una versión nueva |
| Híbrido | Múltiples estrategias de resolución | Más metadata |

Se elige el modelo híbrido del esquema Annotation.

### 10.2 Convención geométrica

- page_index es cero-based e interno.
- page_label es la etiqueta visible.
- x/y normalizados están en [0,1], origen superior izquierdo.
- El espacio canónico es el CropBox sin rotación visual.
- Se guarda la rotación declarada de página.
- rects conserva selecciones multilínea; polygons cubre area notes.
- pdf_points opcional facilita una exportación posterior.
- Las coordenadas de pantalla y el zoom nunca se persisten como evidencia.

### 10.3 Resolución al cambiar PDF

1. Si SHA-256 coincide, selector exact.
2. Si cambia la versión, buscar exact+prefix+suffix en la misma etiqueta/página.
3. Si hay una coincidencia única, recalcular posición/geometría y marcar relocated.
4. Si hay varias, usar posición y proximidad geométrica sólo para sugerir.
5. Si no hay una coincidencia inequívoca, marcar ambiguous u orphaned.
6. Nunca retarget automático silencioso; la resolución manual queda auditada.

### 10.4 Exportación anotada

~~~text
PDF original inmutable
        +
annotations externas, fijadas a versión/hash
        ↓
copia temporal validada
        ↓
PDF anotado exportado a Documents/MathMongo
~~~

La copia puede aplanar highlights/notas o mantener anotaciones PDF según la futura librería. Nunca modifica el original y siempre declara el hash/version de origen en el manifiesto.

## 11. Notas de lectura

ReadingNote contiene reflexión amplia, no una marca geométrica. Puede nacer desde una Source, Reference, Document, página o Annotation.

Reglas:

- body se trata como texto/Markdown no confiable;
- HTML arbitrario no se ejecuta;
- página y targets son opcionales;
- una nota puede vincular varios conceptos;
- borrar/archivar el documento no destruye la nota;
- Cornell/CPI conservan su payload legacy y pueden añadir targets tipados;
- latex_notes.project no se convierte automáticamente en source_id;
- Cornell source_refs se preserva hasta una migración humana.

Flujo C, crear nota desde página:

1. El Reader entrega document_id, versión, page_index y page_label.
2. El formulario permite título, body y tags.
3. La nota recibe Source/Reference del Document, sin copiar bibliografía.
4. Puede añadir conceptos existentes.
5. Guardar crea ReadingNote; no altera PDF.

## 12. Vínculos con conceptos

### 12.1 Crear concepto desde una selección

1. Capturar selección y crear Annotation draft.
2. Abrir formulario Add Concept prellenado con selected_text como contexto, no como contenido final automático.
3. Seleccionar Source ya resuelta y Reference del Document.
4. Crear concepto.
5. Crear ConceptEvidenceLink y activar Annotation.
6. Si falla el concepto, la Annotation queda draft; no hay rollback destructivo de datos ajenos.

### 12.2 Vincular selección a concepto existente

Buscar por concept_uid; durante transición mostrar también id@source. Crear ConceptEvidenceLink. Annotation.linked_concept_ids puede actualizarse como cache, pero el link es autoritativo.

### 12.3 Abrir concepto en documento y página

Edit Concept consulta concept_evidence_links, el usuario elige evidencia y el Reader abre document_id/version/page_index. Si la versión falta, se muestra el snapshot del locator y un estado missing/orphaned; no se salta silenciosamente al PDF actual.

### 12.4 Evidencia en Edit Concept

Panel futuro:

- Source y Reference resumidas;
- Document, versión/hash y derechos;
- página/capítulo/sección/ecuación;
- cita y comentario;
- Annotation asociada;
- acciones Abrir, desvincular, reemplazar locator y crear ReadingNote.

### 12.5 Conceptos de una Source

Consulta primaria por concept_evidence_links.source_id, complementada temporalmente por concepts.source_id o el mapping legacy. No se infiere por similitud de nombre.

## 13. Mendeley y BibTeX

### 13.1 Flujo elegido para MVP

Mendeley Reference Manager → Copy BibTeX → pegar en MathMongo, sin API obligatoria.

También se permite cargar .bib, listar entradas y seleccionar una o varias.

Etapas:

1. Parsear sin guardar.
2. Mostrar errores por entrada.
3. Preservar el texto original y su SHA-256.
4. Mapear ENTRYTYPE, autores, title, year, journal, publisher, volume, number, edition, ISBN, DOI, URL y notas.
5. Mostrar candidatos duplicados.
6. Permitir editar el formulario normalizado.
7. Guardar sólo tras confirmación.
8. Asociar la Reference con una o varias Sources.

### 13.2 Detección de duplicados

Orden de evidencia:

1. DOI normalizado exacto.
2. ISBN válido normalizado exacto.
3. BibTeX key normalizada dentro del contexto de importación/Source.
4. autor+título+año normalizados.
5. similitud difusa sólo como sugerencia.

DOI/ISBN exactos pueden bloquear un alta accidental, pero nunca fusionan automáticamente metadata contradictoria. Autor/título/año nunca fusiona sin revisión.

### 13.3 Defectos actuales que S1 debe cubrir

- _bib_to_referencia no devuelve tipo_referencia, pero la UI lo indexa: el botón falla con KeyError.
- Sólo se carga archivo, no pegado.
- Sólo una entrada.
- ENTRYTYPE se ignora.
- BibTeX original se pierde.
- isbn e issn se colapsan en issbn.
- citekey se descarta en Add porque no existe en Pydantic, pero Edit puede persistirlo con $set raw.
- Una referencia sólo con DOI/ISBN/URL/citekey se descarta porque Add/Edit exigen autor o fuente.
- El botón anterior inventa 2024 cuando falta año y no continúa buscando si el último dict no es utilizable.

### 13.4 Integración directa futura

No forma parte del MVP. Sólo se evaluará si aporta sincronización real que BibTeX no cubra. Requeriría OAuth, almacenamiento seguro de tokens, límites/API de Mendeley, resolución de conflictos y una política de privacidad. Debe ser un adaptador opcional, nunca requisito del catálogo.

## 14. Compatibilidad legacy

### 14.1 Principios

- Migración explícita; nunca al importar módulos ni al abrir la app.
- Comandos futuros status, dry-run y apply.
- status y dry-run no escriben.
- snapshot/backup antes de apply.
- idempotencia por migration_id y fingerprint.
- no borrar source, referencia, citekey, issbn ni localizadores legacy al inicio.
- no fusionar nombres similares sin decisión humana.
- conflictos registrados y reanudables.

### 14.2 Transición propuesta

1. Inventariar por base y exportar snapshot.
2. Generar candidatos exactos de source strings.
3. Crear mapping revisable string exacto → source_id.
4. Crear Sources sólo tras aprobación.
5. Añadir source_id a conceptos gradualmente y conservar source.
6. Crear References desde referencia embebida sólo con una tabla de conflictos.
7. Añadir reference_id sin borrar referencia.
8. Convertir páginas/capítulos/secciones a ConceptEvidenceLink cuando exista Document; antes, conservar locator legacy.
9. Introducir concept_uid y migrar relaciones/media/mapas por fases.
10. Retirar lectura legacy sólo después de backups, métricas de cobertura y aprobación.

### 14.3 Nombres similares

Se generan grupos de revisión por:

- trim/whitespace;
- casefold;
- acentos;
- puntuación.

Cada string original permanece distinto hasta que el usuario seleccione:

- mismo Source y alias;
- Sources distintas;
- posponer.

### 14.4 Rutas antiguas

Una ruta absoluta legacy sólo se registra como external_legacy y nunca se copia automáticamente. Una importación explícita valida archivo, symlinks, hash y destino XDG. Si falta, se conserva metadata con status missing.

### 14.5 Situación de las bases auditadas

La base configurada mathmongo tiene concepts=0 y un dry-run limitado a ella produciría cero candidatos de Source/Reference/Document. MathV0, en cambio, contiene 186 conceptos, 16 Sources, 145 referencias embebidas, localizadores, relaciones, mapas y media legacy. Por ello:

- MathV0 es el corpus histórico relevante para diseñar y validar la transición;
- ningún dry-run sobre mathmongo demuestra que la migración global sea innecesaria;
- toda prueba de migración debe ejecutarse sobre una copia aislada y autorizada de MathV0;
- la base MathV0 original nunca debe usarse para ensayos destructivos;
- exports, backups y otras instalaciones siguen fuera del inventario MongoDB confirmado.

## 15. Búsqueda e índices

### 15.1 Estrategia

- Igualdad sobre IDs y campos normalizados.
- Regex sólo cuando sea necesaria, siempre con re.escape y longitud límite.
- Paginación server-side por sort estable + último valor/ID; evitar materializar toda la colección.
- Un text index por colección cuando aporte valor.
- PDF full-text fuera del MVP: no guardar cuerpos completos en MongoDB.
- Si el corpus lo exige, índice local SQLite FTS5 por SHA/version bajo XDG Data, reconstruible desde Documents; no se adopta antes de medir.

### 15.2 Índices propuestos

Todos los índices nuevos se crearán mediante una migración explícita, nunca desde un constructor.

sources:

- unique source_id;
- name_normalized;
- aliases.normalized;
- (status, source_type);
- tags;
- text sobre name, aliases.value y description.

references:

- unique reference_id;
- source_ids;
- bibtex.key_normalized;
- doi_normalized;
- fingerprints.isbn_normalized;
- fingerprints.author_title_year;
- (year, title);
- text sobre title, authors.literal/family, journal, publisher y notes.

source_documents:

- unique document_id;
- (source_id, status, updated_at desc);
- reference_id;
- document_type;
- versions.sha256;
- web.url_normalized;
- (source_id, reference_id, document_type).

annotations:

- unique annotation_id;
- (document_id, document_version, page_index, status);
- linked_concept_ids;
- tags;
- updated_at desc;
- text combinado selected_text, comment y tags.

reading_notes:

- unique reading_note_id;
- targets.source_id;
- targets.reference_id;
- targets.document_id;
- targets.annotation_ids;
- targets.concept_uids;
- (status, updated_at desc);
- text sobre title, body y tags.

concept_evidence_links:

- unique evidence_link_id;
- (concept_uid, status, updated_at desc);
- (source_id, status);
- reference_id;
- (document_id, document_version, locator.page_index);
- annotation_ids;
- índice parcial de legacy_concept_key.id + legacy_concept_key.source mientras dure la transición.

### 15.3 Unicidad bibliográfica

Los índices DOI, ISBN y BibTeX empiezan no únicos para admitir inventario legacy y conflictos. Después de revisar calidad se podrá aprobar un unique partial index para DOI normalizado. ISBN y citekey no se vuelven únicos globalmente sin una política humana.

## 16. Analytics

Métricas futuras:

- Sources totales, activas y archivadas;
- Sources con/sin Documents;
- Sources con/sin References;
- Documents por tipo y estado;
- Documents no leídos;
- Documents sin Concepts;
- Concepts sin evidencia;
- Annotations sin Concept;
- ReadingNotes recientes;
- References más utilizadas;
- páginas más citadas;
- actividad de lectura por día/Source;
- completitud bibliográfica;
- Documents missing/quarantined;
- links y annotations orphaned;
- duplicados de hash, DOI, ISBN y citekey pendientes;
- cobertura de source_id/reference_id/concept_uid durante migración.

Completitud bibliográfica se calcula por tipo, no con un único porcentaje: por ejemplo, libro espera autores/título/año/editorial; artículo espera autores/título/año/journal; web espera título/URL/fecha de consulta.

Los conteos se obtienen mediante pipelines y páginas limitadas. Un cache de resumen puede añadirse después, con generated_at y capacidad de reconstrucción; nunca será fuente autoritativa.

## 17. Exportación, importación y backups

### 17.1 A. Backup local completo

- MongoDB y archivos XDG administrados.
- Privado, cifrable por herramienta externa y no destinado a redistribución.
- Manifiesto con schema_version, base, timestamp inicio/fin, IDs, rutas relativas, tamaño y SHA-256.
- En replica set, usar snapshot/read concern apropiado; en standalone, declarar best-effort y detectar cambios durante copia.
- Incluir derechos y estados.
- Verificar checksums después de escribir.

### 17.2 B. Exportación portable

~~~text
manifest.json
entities/
  sources.jsonl
  references.jsonl
  source_documents.jsonl
  annotations.jsonl
  reading_notes.jsonl
  concept_evidence_links.jsonl
files/
  sources/<source_id>/documents/<document_id>/versions/...
checksums.sha256
~~~

- Extended JSON o codec tipado para no perder BSON.
- Sin credenciales, HOME, rutas absolutas ni config real.
- IDs preservados.
- Conflictos: identical, skip, import_as_new, missing o manual.
- ZIP validado contra ZIP slip, bombas, symlinks y duplicados de nombre.
- PDFs se incluyen sólo según la política de derechos elegida.

### 17.3 C. Exportación bibliográfica

BibTeX y, posteriormente, CSL-JSON. Usa Reference normalizada, conserva citekey aprobado y permite incluir el raw original. No incluye archivos.

### 17.4 D. PDF anotado

Genera una copia desde una versión exacta y sus Annotations. Incluye manifiesto/hash de origen. Nunca sobrescribe el original.

### 17.5 E. Conceptos sin redistribuir PDF

Incluye conceptos, References, Source, ConceptEvidenceLinks, localizadores y opcionalmente citas permitidas. Document aparece como metadata_only/excluded y el archivo no se empaqueta. Se advierte si quoted_text puede infringir una política.

### 17.6 Compatibilidad con export actual

El export actual serializa todas las colecciones existentes a JSON y copia media legacy/XDG. No conserva genéricamente todos los tipos BSON, no tiene checksums de contenido ni política de derechos. El importer crea colecciones y hace replace/upsert por _id en una base que la UI pretende nueva.

El formato futuro tendrá un número de versión propio. Los ZIP actuales entran por un adaptador legacy y un preview/dry-run; nunca se reinterpretan automáticamente como el nuevo esquema. EXPORT_COLLECTIONS/IMPORT_COLLECTIONS deberán ampliarse sólo en la fase que cree cada colección.

## 18. Seguridad y privacidad

### 18.1 Threat model

| Amenaza | Impacto | Mitigación |
|---|---|---|
| PDF malicioso/corrupto | Exploit del parser, DoS | PDF.js/parser fijados y actualizados, sandbox, límites, timeout, cuarentena |
| Nombre malicioso | Traversal o UI injection | Ignorar para storage; preservar sólo como metadata escapada |
| Path traversal | Escritura/lectura fuera de XDG | IDs generados, validate_mutable_path y contención léxica |
| Symlink/hardlink inesperado | Escape o reemplazo | Rechazo de componentes symlink, O_NOFOLLOW/O_EXCL cuando exista, stat antes/después |
| ZIP slip/bomba | Escape o agotamiento | Paths normalizados, límites de entradas/tamaño/ratio, no extractall |
| MIME falso | Parseo indebido | Cabecera, MIME detectado y parser; extensión no autoritativa |
| Archivo enorme | Memoria/disco/CPU | Streaming, cuotas, máximo por archivo y total |
| Scripts/acciones PDF | Navegación/ejecución | Deshabilitar JavaScript, launch actions, adjuntos y formularios activos |
| Enlace externo | Tracking, SSRF o phishing | No fetch automático; confirmación; sólo http/https; protección SSRF en snapshots |
| HTML no confiable | XSS | No unsafe_allow_html con nombres/notas; escape y sanitización |
| Extracción de texto | DoS o fuga a terceros | Local, proceso sin shell, límites y cache privado |
| Annotation maliciosa | XSS/LaTeX injection | Texto plano, límites, escape contextual en HTML/LaTeX/CSV |
| BibTeX malicioso | Inyección y datos gigantes | Límites por entrada/campo, parser seguro, escape al exportar |
| Credenciales | Exposición en logs/ZIP | Redacción L2; nunca exportar config/entorno |
| Rutas absolutas | Fuga de username y no portabilidad | Sólo logical_path |
| PDF protegido redistribuido | Riesgo legal/privacidad | rights.redistribution, default ask/exclude, preview del manifiesto |

### 18.2 Riesgos actuales relevantes

- Dashboard interpola datos de conceptos en unsafe_allow_html.
- Browse y varias consultas de Source usan regex sin escape.
- id@source es ambiguo si un componente contiene @.
- MathMongo.__init__ asegura/crea índices.
- save_media_asset valida tamaño/extensión pero escribe directamente, no verifica cabecera/MIME y no deduplica antes de copiar.
- Import ZIP lee miembros completos en memoria y debe endurecer límites antes de reutilizarse para Documents.

### 18.3 Recursos web y SSRF

El MVP registra URL sin descargar. Un snapshot futuro:

- resuelve DNS y bloquea loopback, link-local, redes privadas y metadata endpoints;
- revalida cada redirect;
- limita redirects, bytes, tiempo y MIME;
- no transmite cookies/credenciales;
- guarda fecha, URL final y hash;
- respeta derechos y robots/política aprobada.

## 19. UX propuesta

Streamlit rerun ejecuta la página completa. Las vistas deben usar claves estables por ID/version, cargas lazy, formularios para commits y eventos del viewer debounced.

### 19.1 Add Source

~~~text
┌──────────────────────── Add Source ────────────────────────┐
│ Name*             [                              ]          │
│ Type              [Book ▼]   Language [      ]             │
│ Aliases           [                              ]          │
│ Description       [                              ]          │
│ Tags              [                              ]          │
│ Rights default    [Ask before portable export ▼]           │
├─────────────────────────────────────────────────────────────┤
│ Optional reference                                        │
│ [Paste BibTeX] [Upload .bib] [Manual]                      │
│ Duplicate candidates / normalized preview                 │
├─────────────────────────────────────────────────────────────┤
│ Documents are optional. [Save Source] [Cancel]             │
└─────────────────────────────────────────────────────────────┘
~~~

S1 no muestra upload de Document; sólo anticipa que la Source es válida sin archivo.

### 19.2 Edit / Analyze Source

~~~text
[Overview] [References] [Documents] [Reader & Notes]
[Concepts] [Analytics] [Data Quality] [Actions]

Overview: nombre, alias, tipo, tags, derechos, resumen
Actions: archive, export, revisar conflictos; no hard delete
~~~

Para evitar ejecutar todas las pestañas en cada rerun, usar un selector de sección y render lazy cuando el volumen crezca.

### 19.3 Documents

~~~text
Documents for <Source>
[Add PDF] [Add web resource] [Add other file]

Type | Title | Reference | Version | Pages | Size | Status | Rights | Actions
PDF  | ...   | ...       | v2      | 340   | ...  | ready  | ask   | Open...

Duplicate SHA warning / missing files / quarantined versions
~~~

### 19.4 PDF Reader & Notes

~~~text
┌───────────────┬────────────────────────────┬───────────────────┐
│ Documents     │ PDF Viewer                 │ Notes             │
│               │                            │                   │
│ Main PDF      │ Page / Zoom / Search       │ Annotations       │
│ Preprint      │                            │ Reading notes     │
│ Supplement    │ Selected text              │ Linked concepts   │
└───────────────┴────────────────────────────┴───────────────────┘
~~~

Desktop: st.columns aproximadas [1, 3, 1.3]. El panel del viewer conserva una altura controlada. En móvil: selector Document, viewer y panel Notes apilados. S3 oculta herramientas de anotación. S4 usa Guardar/Cancelar y no escribe por cada drag.

### 19.5 Source Concepts

~~~text
Filters: type | evidence status | document | reference | page | tag

Concept | Type | Evidence count | Primary document/page | Status | Open
...     | ...  | 2              | Main PDF p. 17       | linked | →

[Create concept] [Review concepts without evidence] [Export]
~~~

### 19.6 Global Source Analytics

~~~text
Sources  Documents  References  Concepts without evidence
[  42 ]  [  78   ] [   55    ] [          19           ]

Completeness by Source     Documents by status
Recent reading activity   Duplicate/conflict queue
Pages most cited          Sources missing documents
~~~

### 19.7 Data Quality

Colas separadas:

- posibles Sources duplicadas;
- referencias DOI/ISBN/citekey en conflicto;
- archivos missing/quarantined;
- anotaciones orphaned;
- conceptos legacy sin source_id/concept_uid;
- evidencia sin Document.

Ninguna acción masiva se ejecuta sin preview, selección y confirmación.

## 20. Plan de implementación por fases

### S1 — Source catalog and references

Alcance:

- sources y references;
- IDs, repositorios, Add Source y Edit/Analyze básico;
- paste/.bib, selección múltiple, preview y deduplicación;
- asociación Source–Reference;
- lectura legacy sin migrar.

Fuera de alcance: archivos, visor, anotaciones, evidencia y migración masiva.

Archivos esperados: schemas de Source/Reference, repositorios DB, módulos UI, editor_streamlit como routing, db_export/import y pruebas.

Pruebas: normalización, IDs, BibTeX raw/normalized, duplicados, permisos de edición, repositorios sin side effects y export/import de las dos colecciones.

Validación manual: crear Source vacía, web sin PDF, pegar BibTeX de Mendeley, revisar conflicto y renombrar sin romper Reference.

Riesgos: divergencia Pydantic/raw, estado Streamlit y política de unicidad.

Criterio de aceptación: Source independiente, renombrable por ID, Reference no duplicada por concepto y sin tocar conceptos legacy automáticamente.

Commit sugerido: feat: add source catalog and bibliographic references

### S2 — Source documents and XDG storage

Alcance:

- source_documents;
- storage XDG, upload PDF/other y web resources;
- hash, versionado, rights, dedupe, estados y reconciliación;
- backup/export/import inicial.

Fuera de alcance: viewer interno, annotations y extracción full-text.

Archivos esperados: mathmongo/paths.py, schemas Document, storage/repository/service, UI Documents, export/import, threat-validation helpers y tests.

Pruebas: symlinks/traversal, 0600/0700, tamaño, MIME/header, hash, duplicado, atomic replace, crash states, web-only, wheel read-only y ZIP seguro.

Validación manual: PDF válido, corrupto, duplicado, reemplazo v2, URL-only y archivo missing.

Riesgos: atomicidad DB/filesystem, parser PDF y consumo de disco.

Criterio de aceptación: originales inmutables bajo XDG, rutas lógicas, ninguna escritura en checkout/site-packages y backup verificable.

Commit sugerido: feat: add source documents with XDG storage

### S3 — Read-only PDF viewer

Alcance:

- st.pdf dentro de la vista Reader;
- selección de Document/version, fallback externo y política de descarga;
- empaquetado offline y manejo de PDFs grandes.

Fuera de alcance: callbacks de página, highlight, notas y modificación PDF.

Archivos esperados: vista reader, adaptación de Document service, pyproject para versión/extra aprobados, tests y recursos sólo si son necesarios.

Pruebas: path XDG, missing/quarantine, permisos, versión, wheel offline, gran tamaño y no exposición de URL remota.

Validación manual: navegación/zoom/búsqueda disponibles, múltiples PDFs, fallback y layout móvil.

Riesgos: elevar Streamlit y dependencia streamlit-pdf.

Criterio de aceptación: PDF local se lee dentro de MathMongo sin escribirlo ni cargar recursos de CDN.

Commit sugerido: feat: add read-only source PDF viewer

### S4 — External annotations and reading notes

Alcance:

- componente PDF.js bidireccional;
- annotations y reading_notes;
- selectores híbridos, CRUD, tags y resolución por versión;
- no destructive overlay.

Fuera de alcance: crear conceptos, links de evidencia y PDF anotado final.

Archivos esperados: componente frontend vendorizado, wrapper Python, schemas/repositorios, UI Notes, assets de PDF.js y pruebas JS/Python.

Pruebas: zoom/rotación, multilínea, quote/position/geometry, reruns, XSS, versión cambiada, orphan y accesibilidad.

Validación manual: seleccionar texto, area note, bookmark, reload y PDF v2.

Riesgos: protocolo JS–Python, CSP, tamaño de assets y mantenimiento PDF.js.

Criterio de aceptación: anotaciones externas sobreviven rerun/zoom y el original conserva el mismo SHA-256.

Commit sugerido: feat: add external PDF annotations and reading notes

### S5 — Concept evidence links

Alcance:

- concept_uid gradual;
- concept_evidence_links;
- crear/vincular concepto desde selección;
- evidencia en Edit Concept y deep-open a Document/version/page.

Fuera de alcance: migración masiva automática, búsqueda full-text y export PDF anotado.

Archivos esperados: schema/repository/service, integración Add/Edit Concept, reader callbacks, graph adapters y pruebas.

Pruebas: legacy key, id colisionado en Sources, link múltiple, delete/archive, open page, fallo parcial e integridad.

Validación manual: flujos A–F de S0.12.

Riesgos: identidad distribuida actual y mapas/media legacy.

Criterio de aceptación: un concepto abre evidencia exacta y una Reference no se copia dentro del concepto.

Commit sugerido: feat: link concepts to documentary evidence

### S6 — Search, analytics, export and migration

Alcance:

- índices aprobados y paginación;
- búsqueda/analytics/data quality;
- backup/portable/BibTeX/PDF anotado;
- status/dry-run/apply de transición legacy.

Fuera de alcance: Mendeley API obligatoria y servicio externo de búsqueda.

Archivos esperados: migrations versionadas, search/analytics services, export manifests, annotator exporter, UI Data Quality y tests end-to-end.

Pruebas: idempotencia, conflictos, checksums, derechos, ZIP slip/bomb, datos ausentes, backups legacy y rollback operativo documentado.

Validación manual: dry-run sin escrituras, apply sobre copia, re-run no-op, portable sin PDF protegido y restore completo.

Riesgos: consistencia snapshot, librería de escritura PDF y casos legacy no vistos en mathmongo.

Criterio de aceptación: migración revisable/idempotente, búsquedas paginadas y exports verificables sin credenciales ni rutas absolutas.

Commit sugerido: feat: add source search analytics export and legacy migration

## 21. Riesgos abiertos

1. MathV0 confirma casos legacy reales: 186 conceptos, 145 referencias embebidas y múltiples consumidores de id@source. La lectura fue puntual, no un snapshot, y las pruebas deben usar fixtures más una copia aislada autorizada.
2. Edit Concept permite hoy reidentificar parcialmente un concepto y puede corromper relaciones entre colecciones.
3. El rollback manual de Add puede borrar un documento preexistente si una carrera hace fallar insert_one antes de que este flujo sea propietario del registro.
4. Los nombres con @ o regex rompen el modelo id@source y consultas no escapadas.
5. Los citekeys y referencias reales varían según se use Add, Edit o import.
6. Source/Reference/Document requieren integridad de aplicación porque MongoDB no tiene foreign keys.
7. MongoDB standalone limita transacciones/snapshots coordinados con archivos.
8. El parser PDF y la librería de exportación anotada aún no están elegidos.
9. st.pdf exige elevar el mínimo práctico y añadir un extra.
10. Components v2 y PDF.js aumentan superficie frontend y tamaño de wheel/AppImage.
11. Derechos de PDFs y citas no pueden inferirse automáticamente.
12. Un índice text de MongoDB no cubre el contenido completo de PDFs grandes.
13. Import/export actual no tiene límites suficientes para reutilizarlo sin endurecimiento con archivos grandes.
14. El Streamlit heredado siguió activo durante S0; no se observó actividad de escritura atribuida a S0, pero la consulta Mongo no es un snapshot aislado del proceso.

## 22. Decisiones pendientes de aprobación humana

La arquitectura no queda abierta; las siguientes son gates de implementación:

1. Aprobar IDs prefijados UUID v4 y concept_uid gradual.
2. Aprobar references globales con source_ids y Documents con un source_id autoritativo.
3. Aprobar límite inicial de upload de 250 MiB y cuota total.
4. Elegir parser PDF backend y su política de actualización/sandbox.
5. Aprobar Streamlit mínimo y el extra streamlit[pdf] para S3.
6. Aprobar PDF.js vendorizado, licencia, CSP y diseño de aislamiento para S4.
7. Elegir librería para generar copias PDF anotadas.
8. Aprobar política default de derechos: ask para backup portable y descarga.
9. Aprobar una copia aislada de MathV0 para pruebas de migración; nunca usar la base original para pruebas destructivas.
10. Revisar manualmente el mapping de nombres Source antes de cualquier apply.
11. Definir retención de versiones antiguas y cuarentena.
12. Definir umbral medido para adoptar SQLite FTS5 u otro índice de contenido.

Hasta esas aprobaciones, S1 no debe comenzar.

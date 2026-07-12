# Fase S1A — Source Catalog Core y referencias bibliográficas

## Alcance

S1A incorpora el núcleo de dominio y persistencia para `Source` y `Reference` sin
alterar el modelo histórico de conceptos. El catálogo vive en las colecciones
separadas `sources` y `references`, siempre dentro de la base MongoDB que el
llamador entrega explícitamente.

Esta fase cubre modelos, normalización, repositorios, reglas de negocio,
previsualización/importación BibTeX seleccionada, diagnóstico de duplicados,
archivado/reactivación, eliminación física protegida, gestión explícita de
índices y compatibilidad con los respaldos existentes.

## Decisiones implementadas

- Los identificadores de dominio son `src_<uuid4>` y `ref_<uuid4>`; un cambio de
  nombre nunca cambia `source_id`.
- `Reference` es global y mantiene una lista deduplicada de `source_ids`.
- Archivar es la baja normal. El borrado físico exige que no haya vínculos
  actuales, coincidencias legacy ni blockers futuros suministrados al servicio.
- DOI, ISBN, citekey y fingerprints son evidencia de duplicado, no instrucciones
  de fusión.
- Ningún constructor se conecta a MongoDB ni selecciona `mathmongo` o `MathV0`.
- Los índices sólo cambian mediante una llamada explícita a `apply()`.

## Modelos

`mathmongo.source_catalog.models` contiene modelos Pydantic v2 con campos
cerrados, enums tipados y datetimes UTC conscientes de zona horaria.

`Source` contiene nombre visible y normalizado, aliases estructurados, tipo,
descripción, idioma, tags, estado, derechos predeterminados, metadata legacy y
timestamps. Los aliases se deduplican por su forma normalizada y nunca repiten
el nombre principal.

`Reference` contiene asociaciones a Sources, tipo bibliográfico, BibTeX
preservado, autores estructurados o literales, campos editoriales, DOI, ISBN,
URL, fingerprints, procedencia, estado y timestamps. Una referencia es válida
si tiene al menos una señal de identidad bibliográfica; no se exigen autor ni
editorial de forma artificial. El contrato nuevo no usa `issbn`.

## Normalización

La normalización está centralizada en funciones puras. Los nombres aplican NFKC,
trim, colapso de whitespace y `casefold`. DOI elimina protocolo, host y prefijos;
ISBN conserva el original y calcula forma normalizada y checksum ISBN-10/13;
citekey conserva el valor original y usa una clave separada para comparación.

URL, autores, títulos y el fingerprint autor+título+año también se normalizan sin
I/O. La clave sin acentos o puntuación sólo se emplea para sugerencias débiles.
Un ISBN histórico inválido se conserva y queda marcado para revisión.

## Repositorios

`SourceRepository` y `ReferenceRepository` reciben una base MongoDB explícita.
Encapsulan inserción, lectura, actualización controlada, listado, búsqueda,
paginación, conteo, archivado, reactivación, asociación y diagnóstico de
duplicados. Los regex procedentes del usuario se escapan y limitan; la
paginación también está limitada y todos los órdenes tienen desempate por ID.

Las escrituras no permiten cambiar IDs y traducen carreras de clave duplicada a
conflictos de repositorio sin reemplazar datos. La eliminación física vuelve a
comprobar sus precondiciones en el repositorio.

## Servicio

`SourceCatalogService` concentra creación, rename opcionalmente conservando el
nombre anterior como alias, actualización, archivado, reactivación, asociación,
inspección de eliminación, borrado protegido, preview BibTeX e importación de
candidatos seleccionados. Sus resultados tipados distinguen éxito, advertencia,
conflicto, bloqueo y error.

El servicio comprueba que cada `source_id` relacionado exista en la misma base.
No crea Sources implícitamente, no toca conceptos y no fusiona registros. Puede
recibir detectores de vínculos futuros, que se consultan antes de permitir un
borrado físico.

## BibTeX

El parser usa `bibtexparser`, ya declarado por el proyecto. Acepta texto pegado o
contenido de archivo ya leído, separa múltiples entradas, presenta errores por
entrada y no persiste nada durante el preview. Cuando una entrada puede
delimitarse, conserva su raw y SHA-256, `ENTRYTYPE`, citekey exacta, autores y
campos conocidos. Los campos desconocidos se guardan en un bloque `extra`
acotado.

Sólo la importación explícita de candidatos seleccionados llega al servicio de
escritura. La UI histórica de Add Concept y su botón de referencia no se
modificaron en S1A.

## Detección de duplicados

La evidencia se clasifica como igualdad exacta, duplicado fuerte, posible o
coincidencia débil. El orden aplicado es DOI normalizado, ISBN válido, citekey en
contexto, fingerprint autor+título+año y, finalmente, clave de sugerencia.
Ningún nivel produce merge automático.

## Índices explícitos

`SourceCatalogIndexManager` expone `status()`, `plan()` y `apply()`. El plan cubre
los IDs únicos y los campos de consulta aprobados de ambas colecciones. DOI,
ISBN y citekey son deliberadamente no únicos. `apply()` es idempotente y sólo se
ejecuta por invocación explícita; ni imports, repositorios, Streamlit ni
`MathMongo.__init__` lo llaman.

## Compatibilidad legacy

Los adaptadores legacy son puros y de sólo lectura. Extraen el string `source`
exacto de un concepto y convierten una referencia embebida en preview,
conservando `issbn`, citekey y valores históricos. Páginas, capítulo y sección se
separan como locators en vez de mezclarse con la bibliografía global.

S1A no añade `source_id` ni `reference_id` a conceptos, no cambia `id@source`, no
renombra datos históricos y no escribe relaciones, mapas, medios, notas ni
documentos LaTeX.

## Exportación e importación

Los respaldos reconocen `sources` y `references`, pero sólo los incluyen cuando
la colección existe. Un ZIP histórico que no las contiene sigue siendo válido y
no provoca su creación vacía.

La importación conserva IDs y restaura los timestamps del catálogo. Antes de
escribir, compara cada ID de dominio: un documento idéntico se informa y omite;
un documento diferente se informa como conflicto y bloquea la importación del
catálogo sin sobrescribirlo. No se reinterpretan conceptos legacy y aún no se
incluyen documentos ni archivos físicos de Source.

## Pruebas

Las pruebas S1A usan bases falsas aisladas y directorios temporales. Cubren
modelos, normalización, rename, estados, búsquedas escapadas, paginación,
asociaciones, borrado protegido, evidencia de duplicados, BibTeX múltiple,
compatibilidad legacy, ciclo explícito de índices, aislamiento entre bases y
export/import. También verifican imports sin efectos laterales y ausencia de
escrituras en HOME, checkout y `site-packages`.

## Limitaciones

- No hay merge de Sources o References; cualquier consolidación exige una fase
  posterior y una decisión explícita.
- No se ejecutan índices automáticamente. Un operador debe revisar `plan()` y
  llamar `apply()` sobre la base elegida.
- No hay migración automática de los 186 conceptos históricos de `MathV0`.
- Los vínculos futuros sólo bloquean borrado cuando su detector se inyecta al
  servicio; no se inventan consultas sobre esquemas aún inexistentes.

## Fuera de alcance

S1A no implementa Add/Edit Source completo, cambios en Add Concept, PDFs,
Document, visor, anotaciones, ReadingNote, Mendeley, migraciones, edición de
conceptos legacy ni escrituras en `MathV0`.

## Plan S1B

S1B podrá construir la UI Add/Edit Source sobre este servicio, con selección
explícita de base activa, preview de duplicados, confirmaciones de archivado y
flujo controlado para aplicar índices. La transición de conceptos legacy deberá
mantener `id@source` y los strings actuales hasta que exista una migración
aislada, versionada, reversible y aprobada.

# Fase S1C1 — Planificador del catálogo Source legacy

## Objetivo y alcance

S1C1 incorpora una frontera de sólo lectura para inspeccionar el export legacy de
`MathV0`, construir un plan determinista para el catálogo de Sources y References y,
cuando el operador lo autoriza expresamente, comparar ese snapshot con la base viva.
El ZIP es la única fuente autoritativa del plan: una diferencia con MongoDB se reporta
como *drift* y nunca se corrige mezclando datos de ambas fuentes.

Esta fase cubre lectura segura, inventario, candidatos, separación de bibliografía y
localizadores, bindings, conflictos, cola de revisión, reportes y comparación viva.
No implementa `apply`, no crea IDs finales, no escribe MongoDB, no modifica el ZIP y
no cambia la UI ni los consumidores legacy.

## Puerta inicial de Git

La implementación comenzó en el repositorio esperado, sobre `main`, con HEAD
`ebb8d046838e0038e92990a4a6bc4d1cac27e515` (`fix: replace deprecated Streamlit
container width arguments`). El staging estaba vacío, no había procesos heredados de
pytest o build y el único archivo no rastreado era
`mathkb_export_20260712_073927.zip`. Ese ZIP se trató como entrada de usuario
autorizada: no se movió, editó ni añadió a Git.

## Snapshot autoritativo

La entrada utilizada fue:

- archivo: `mathkb_export_20260712_073927.zip`;
- tamaño: 7,202,896 bytes;
- SHA-256:
  `9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8`;
- modificación: `2026-07-12T07:39:28.691511047-06:00`;
- exportación declarada: `2026-07-12T07:39:27.161327Z`;
- formato inferido por layout: `mathkb_legacy_export`;
- versión: `unversioned` (la metadata no declara una versión de formato).

La metadata y los miembros coinciden exactamente:

| Colección | Documentos |
|---|---:|
| `concepts` | 186 |
| `latex_documents` | 187 |
| `relations` | 136 |
| `knowledge_graph_maps` | 2 |
| `media_assets` | 10 |
| `latex_notes` | 34 |
| `backlog_items` | 3 |
| `deliverables` | 2 |
| `worklog_entries` | 5 |
| `weekly_reviews` | 0 |

El inventario del archivo contiene 29 miembros: 26 archivos regulares y tres
directorios, con 9,999,843 bytes sin comprimir, 7,196,738 bytes comprimidos y un
ratio máximo de 8.736501. No contiene colecciones `sources` ni `references`.

## Arquitectura

La lógica vive fuera de Streamlit y de `MathMongo.__init__`:

```text
mathmongo/source_catalog_migration/
├── __init__.py
├── canonical.py
├── cli.py
├── inventory.py
├── live_compare.py
├── locator.py
├── models.py
├── planner.py
├── reference_planner.py
├── report.py
├── source_planner.py
└── zip_reader.py

mathmongo/migrate_source_catalog.py
```

`zip_reader` valida y carga el export sin extraerlo; `inventory` cuenta conceptos y
consumidores; los planners de Source y Reference son funciones puras; `locator`
separa ubicación y bibliografía; `planner` arma bindings e invariantes;
`live_compare` encapsula la única lectura opcional de MongoDB; `report` limita la
salida y protege sus rutas; y `cli` mantiene separados `status`, `dry-run` y
`compare-live`. La detección de conflictos forma parte del planner de References,
sin una capa de persistencia.

S1C1 reutiliza las funciones puras de S1A para normalizar Source, DOI, ISBN,
citekey, autores, títulos y URL, además del fingerprint autor+título+año. En cambio,
no instancia los modelos persistentes `Source` o `Reference` ni invoca el adaptador
legacy o el detector de duplicados de S1A: esas rutas pueden generar IDs y timestamps
o incorporar semántica propia de entidades ya persistibles. Un dry-run debe ser
repetible, conservar el raw legacy y producir sólo claves candidatas derivadas del
contenido; por eso usa modelos inmutables específicos de S1C1.

## CLI

Los tres comandos soportados son:

```bash
ZIP=/home/enriquedo/PersonalProjects/math-knowledge-base/mathkb_export_20260712_073927.zip

python -m mathmongo.migrate_source_catalog status --input-zip "$ZIP"
python -m mathmongo.migrate_source_catalog dry-run --input-zip "$ZIP"
python -m mathmongo.migrate_source_catalog compare-live \
  --input-zip "$ZIP" \
  --database MathV0 \
  --allow-live-read
```

Las opciones comunes incluyen `--output-format text|json`, `--output PATH`,
`--fail-on-input-change`, `--database-name` y límites acotados para miembros,
tamaño y ratio del ZIP. Sin `--output`, el único destino es stdout. Con `--output`,
la ruta se resuelve mediante la política segura existente, se rechazan checkout,
`site-packages`, symlinks y archivos preexistentes; los directorios nuevos se crean
con modo `0700` y el reporte, de forma exclusiva, con `0600`.

`compare-live` exige tanto el nombre exacto `MathV0` como
`--allow-live-read`. `apply` se rechaza con código de uso y explica que pertenece a
S1C2. Los códigos específicos de comparación son 3 para drift ZIP–snapshot y 4 para
cambios concurrentes detectados entre las lecturas viva inicial y final.

## Seguridad del ZIP

El lector falla cerrado antes de planificar. Verifica que la entrada sea un archivo
regular y no un symlink; registra dispositivo, inode, tamaño, mtime y SHA-256 antes
y después de la lectura; y vuelve a comprobar su identidad antes de emitir el
reporte. La opción `--fail-on-input-change` queda expuesta como contrato, aunque
S1C1 aplica siempre esa protección.

La tabla central del ZIP se valida miembro por miembro contra:

- rutas absolutas, componentes `..`, separadores no portables y nombres no
  canónicos;
- duplicados byte a byte y duplicados tras normalización NFC;
- cifrado, symlinks y entradas Unix no regulares;
- métodos de compresión distintos de Stored y Deflate;
- miembros, tamaños individuales, tamaño agregado y ratios excesivos;
- CRC inválido, JSON mal formado, layout o miembros inesperados;
- conteos de colecciones y nombres/tamaños de media distintos de la metadata.

Los límites predeterminados son 1,000 miembros, 64 MiB por miembro, 512 MiB en
total y ratio 100. Aun si el operador solicita más, los máximos absolutos son 10,000
miembros, 256 MiB por miembro, 1 GiB total y ratio 200. La lectura normal ocurre en
memoria y no usa `extractall()`. El helper disponible para una necesidad futura crea
un temporal externo `0700` y lo elimina también tras una excepción.

El ZIP suministrado pasó la validación estructural y de CRC: no se observaron rutas
inseguras, duplicados, cifrado, symlinks, entradas no regulares, miembros
inesperados ni discrepancias de metadata.

## Modelo y determinismo del plan

Los resultados son modelos Pydantic estrictos, inmutables y cerrados. Un plan
incluye `schema_version=1`, `planner_version=s1c1-v1`, `input_snapshot`, resumen,
candidatos Source y Reference, bindings, review items, conflictos, consumidores,
invariantes, comparación live opcional, `generated_at` y un hash semántico.

Las claves `source_candidate_key`, `reference_candidate_key` y
`binding_candidate_key` son SHA-256 completos derivados del contenido canónico,
del namespace `mathmongo.source-catalog-migration` y de la versión del planner. No
son `source_id`, `reference_id` ni UUID v4. El payload semántico excluye
`generated_at`, el propio hash y `live_comparison`, por lo que esas observaciones no
cambian el plan originado en el ZIP.

Dos construcciones directas del mismo snapshot produjeron el mismo payload
semántico y el mismo SHA-256:
`e91599d50c58bb88014911590d34c9f0fc46b1c989dec8f3f25fed007a33b44f`.

Las obligaciones comprobadas incluyen conteos esperados, unicidad de claves legacy
y bindings, ausencia de conceptos perdidos o duplicados, localizadores excluidos de
los fingerprints bibliográficos, conflictos no absorbidos, ausencia de IDs finales
y ZIP inalterado. Todas pasaron para este snapshot.

## Regla central: deduplicar References, no conceptos

S1C1 puede agrupar observaciones bibliográficas que representan la misma obra, pero
nunca agrupa conceptos. Compartir Source, Reference, DOI, ISBN, citekey, página,
capítulo o sección no convierte dos conceptos en duplicados. Tampoco se inspecciona
contenido matemático para curarlos.

Por ello, los 186 conceptos conservan su identidad exacta `(id, source)` y cada uno
aparece una vez en `concept_bindings`, incluso cuando varios bindings comparten la
misma Reference candidata y el mismo locator.

## Source candidates

Los candidatos Source se derivan exclusivamente de `concepts.source`. Cada string
exacto produce una candidata distinta; la normalización se utiliza sólo como
diagnóstico y nunca convierte guiones, underscores, ortografía o nombres similares
en una fusión. El nombre visible propuesto y `legacy_source_strings` conservan el
valor exacto, mientras `source_type="other"` es sólo una sugerencia.

El snapshot produjo 16 Source candidates que cubren los 186 conceptos. Cada
candidata informa conteos con y sin Reference, References relacionadas, estadísticas
de localizadores, forma normalizada, advertencias y estado de revisión. No se
infirió ninguna Source desde referencias, tags, categorías o proyectos.

## Bibliografía, localizadores y Reference candidates

Cada referencia embebida se divide sin pérdida entre bibliografía global y ubicación
específica del concepto. DOI, ISBN/`issbn`, citekey top-level y embebida, autores,
título/fuente, año, editorial, volumen, edición, URL, tipo y campos desconocidos se
conservan en sus formas raw y normalizadas. Ausente y `null` siguen siendo estados
diagnósticos distintos. Las candidatas enumeran además todas las `legacy_keys` que
las sustentan. Si conviven aliases de un mismo campo, cada nombre y valor original se
preserva y una discrepancia normalizada se marca como conflicto de aliases, sin
elegir silenciosamente un valor. Un tipo legacy no reconocido se conserva en
`unknown_reference_type`, se propone como `other` y obliga a revisión.

`paginas`, `capitulo`, `seccion`, `ecuacion`/`equation`, `teorema`/`theorem` y notas
claramente localizadoras se guardan en `LegacyLocator` y nunca entran al fingerprint
bibliográfico. Valores históricos como `N/A`, páginas romanas, rangos y capturas
sospechosas se preservan y producen flags, no correcciones destructivas. El mapa
`raw_alias_values` conserva todos los aliases de locator presentes, incluso si dos
aliases del mismo campo contienen valores distintos; ese caso también se señala para
revisión.

La agrupación aplica, en orden, DOI válido, ISBN válido, citekey compatible,
autor+título+año y fingerprint bibliográfico exacto sin localizadores. La similitud
débil no fusiona. Antes de unir grupos, el planner comprueba metadata compatible; una
contradicción conserva grupos separados y crea un conflicto revisable.

Resultados reales de las 145 referencias embebidas:

| Regla determinante | Candidatas | Conceptos cubiertos |
|---|---:|---:|
| DOI válido exacto | 1 | 15 |
| ISBN válido exacto | 5 | 87 |
| citekey compatible | 1 | 1 |
| autor + título + año | 10 | 36 |
| fingerprint bibliográfico exacto | 3 | 6 |
| **Total** | **20** | **145** |

Las 20 candidatas quedaron `safe_exact`: 13 grupos repetidos cubren 138 conceptos,
siete grupos son unitarios y el grupo mayor contiene 51 conceptos. Se preservaron 24
variantes raw: 16 candidatas tienen una variante y cuatro tienen dos; en estas
últimas, la diferencia observada fue únicamente `null` frente a ausente. Los tipos
bibliográficos propuestos fueron diez `book`, ocho `web`, un `article` y un `thesis`;
son propuestas para revisión, no entidades persistidas.

También se calcularon dos sugerencias `weak_title_similarity` entre pares de
candidatas. Son avisos de similitud débil para revisión humana: no fusionaron grupos,
no redujeron las 20 candidatas y no cambiaron sus bindings.

Entre las 145 observaciones, 133 tienen al menos un locator con valor y 12 no tienen
ninguno. La presencia raw, incluyendo `null` explícito, fue:

| Campo | Con valor | `null` explícito | Ausente |
|---|---:|---:|---:|
| páginas | 112 | 5 | 28 |
| capítulo | 91 | 7 | 47 |
| sección | 40 | 38 | 67 |
| ecuación | 0 | 0 | 145 |
| teorema | 0 | 0 | 145 |

El conjunto de candidatas conserva 48 variantes de locator.

## Bindings, revisión y conflictos

El plan contiene 186 bindings para 186 claves `(id, source)` únicas: 145 apuntan a
una Reference candidata y 41 conservan `reference_candidate_key=null`. Cada binding
incluye la Source candidata exacta, el locator raw, flags y estado de revisión. No se
perdió ni duplicó ningún concepto y no se generaron IDs de dominio finales.

La cola real contiene cinco review items agregados de calidad de locator:

- dos items por rangos de páginas;
- uno por `N/A` en páginas;
- uno por página romana;
- uno por una sección con captura sospechosa.

En total, 32 bindings llevan al menos uno de esos flags: 18 rangos, 13 valores `N/A`,
tres secciones sospechosas y una página romana; un binding puede llevar más de un
flag. Esto no contradice que las 20 agrupaciones bibliográficas sean `safe_exact`.
Cada item ofrece para una fase futura `accept_as_one_reference`, `keep_separate`,
`choose_canonical_metadata` o `defer`; S1C1 no ejecuta ninguna decisión.

El snapshot produjo cero conflictos bibliográficos. El modelo sigue representando
coincidencias y contradicciones, DOI/ISBN/citekeys normalizados, Sources afectadas,
variantes acotadas y localizadores. Si una futura entrada presenta DOI o ISBN común
con metadata contradictoria, o citekeys incompatibles, los grupos permanecen
separados y la discrepancia se reporta en vez de fusionarse.

## Consumidores legacy

El inventario transversal es sólo informativo:

| Consumidor | Documentos | Usos legacy detectados |
|---|---:|---:|
| `latex_documents` | 187 | 186 pares `(id, source)`; una huérfana |
| `relations` | 136 | 272 endpoints `id@source` válidos |
| `knowledge_graph_maps` | 2 | 244 pares y 465 tokens `id@source` válidos |
| `media_assets` | 10 | 2 vínculos `id@source` válidos |
| `latex_notes` | 34 | 0 pares y 0 tokens detectados |

S1C1 no modifica ninguna de estas colecciones. La declaración del plan limita el
bootstrap de S1C2 a `sources`, `references` y un manifiesto de migración; todavía no
autoriza cambios en conceptos, documentos LaTeX, relaciones, mapas, media o notas.

## Comparación live de sólo lectura

La comparación usa PyMongo directamente y nunca instancia `MathMongo`. Sólo después
de validar `--allow-live-read` y el nombre exacto `MathV0` resuelve la URI desde la
configuración existente; aplica timeouts acotados, `retryWrites=False` y redacta
credenciales en errores.

Se permiten `ping`, listado de bases y colecciones, conteos, `find` con proyección y
listado de índices. Se captura antes y después el conjunto de colecciones, los
conteos, fingerprints canónicos de las seis colecciones acopladas y la definición de
sus índices. La igualdad de ambos estados detecta cambios concurrentes. Para medir
drift ZIP–MathV0 se comparan además:

- el hash del conjunto `(id, source)`;
- strings Source exactos y sus conteos;
- partición de conceptos con y sin Reference;
- multiconjuntos hash de referencias raw y de bibliografía sin locator;
- esos mismos fingerprints vinculados a cada `legacy_key`, para detectar que una
  referencia se desplazó entre conceptos aunque el multiconjunto global no cambie;
- conteos de consumidores legacy;
- ausencia observada de `sources` y `references`.

La lectura falla cerrada si una colección relevante supera 10,000 documentos, si el
total canónico proyectado supera 256 MiB o si una colección expone más de 1,024
índices. Tanto `count_documents` como los cursores usan `maxTimeMS=10000`; el socket
y la conexión también tienen timeouts acotados. La proyección excluye sólo un campo
guardia reservado que S1C1 nunca persiste, de modo que el fingerprint de integridad
cubre los campos legacy presentes y futuros sin publicar sus cuerpos.

El plan conserva `writes_attempted=0`; no expone credenciales ni cuerpos de
documentos. Si hay drift, el plan del ZIP no cambia y el comando termina con estado
no exitoso.

La ejecución real de `compare-live` terminó con código 0. No hubo drift concurrente
ni drift entre el ZIP y `MathV0`; `writes_attempted` fue 0 y `sources` y `references`
estaban ausentes antes y después. Resultaron verdaderas las cinco comparaciones:
claves de conceptos, conteos Source exactos, partición con/sin Reference,
fingerprints de References y conteos de consumidores.

Los conteos vivos fueron `concepts=186`, `latex_documents=187`, `relations=136`,
`knowledge_graph_maps=2`, `media_assets=10` y `latex_notes=34`. Los fingerprints
antes y después fueron idénticos:

| Estado live | SHA-256 antes = después |
|---|---|
| `concepts` | `0dad2af834fb76dbc3acfa2a83c5d25c59fe7bfb1f2dc2a03671ea7de8571d62` |
| `latex_documents` | `ee482ca36dad3de6e2ba115e31e3e3c86173e1889707b7a5cb1dd835bf9f48f1` |
| `relations` | `f26395f9c19ab59aba458f20aa163119e699a38be3bc3e1e28c30ffb9b4eb5eb` |
| `knowledge_graph_maps` | `70f5858f52c92192a31b37419c36dade03eb379c3a3ec60b1f9a7e34d4f5b4d8` |
| `media_assets` | `c8d00f53501bcf4219235b02deb294ca9c50522b08288137ab276ce099d5cca9` |
| `latex_notes` | `3fe473bee427e36b0d9f35dc0e9eaf424fd45b26fbabbbab34a7799aaf95e309` |
| Definiciones de índices | `7ad09e42af9e9bd8ceec44dd17f6d5141c6a0ea716b404485876e62cd8074316` |

## Resultados reales resumidos

| Métrica | Resultado |
|---|---:|
| Conceptos | 186 |
| Source candidates | 16 |
| Conceptos con Reference | 145 |
| Conceptos sin Reference | 41 |
| Reference candidates calculadas | 20 |
| Concept bindings | 186 |
| Conflictos bibliográficos | 0 |
| Review items | 5 |
| Sugerencias débiles sin fusión | 2 |
| `compare-live` | exit 0; sin drift; cero escrituras |
| Invariantes del plan | todas aprobadas |
| SHA-256 semántico | `e91599d50c58bb88014911590d34c9f0fc46b1c989dec8f3f25fed007a33b44f` |

El plan completo y los reportes detallados no se versionan; cualquier salida
persistente debe quedar fuera del checkout y con modo `0600`.

## Pruebas y validación

Las pruebas se dividen en tres archivos focales:

- `tests/test_source_catalog_migration_zip.py`: ZIP válido y casos adversariales de
  rutas, enlaces, duplicados, metadata, CRC/identidad, límites y temporales;
- `tests/test_source_catalog_migration_planner.py`: Sources exactas, agrupación y
  conflictos de References, localizadores, raw, determinismo, bindings e invariantes;
- `tests/test_source_catalog_migration_cli_live.py`: comandos, formatos, permisos de
  output, rechazo de `apply`, redacción y un Mongo falso que prohíbe escrituras.

Las pruebas automatizadas no dependen de MongoDB real. La validación operativa del
ZIP real se mantiene separada e incluye `status`, dos `dry-run`, comparación del
payload semántico y `compare-live` autorizado. La suite completa, `compileall`, Ruff
diferencial y `git diff --check` forman parte de la puerta final, no del motor de
migración. Las pruebas focales terminaron con `87 passed`; la única ejecución de la
suite completa terminó con `581 passed` en 56.41 segundos. `compileall`, Ruff sobre
todos los archivos diferenciales, `ruff format --check` y `git diff --check`
terminaron sin diagnósticos.

## Limitaciones y decisiones pendientes

- S1C1 propone agrupaciones; no crea, fusiona, archiva ni edita Sources o References.
- No hay `apply`, rollback ni manifiesto persistido en esta fase.
- Los tipos bibliográficos, `source_type`, nombres visibles y metadata canónica son
  propuestas, no decisiones humanas aplicadas.
- Los cinco items de locator requieren aceptar, corregir más adelante o diferir su
  tratamiento sin alterar el raw legacy.
- Las dos sugerencias débiles mantienen sus candidatas separadas; una persona puede
  descartarlas o considerarlas durante la revisión sin que S1C1 aplique una fusión.
- Cero conflictos en este snapshot no elimina la obligación de revisar conflictos en
  otros exports.
- Si la comparación viva detecta drift, una persona debe decidir si se genera un
  nuevo export o se difiere S1C2; S1C1 nunca reconcilia automáticamente.
- No se auditan ni migran contenido matemático, PDFs, documentos físicos,
  anotaciones, conceptos duplicados ni la UI.

## Alcance de S1C2

S1C2 podrá tomar un plan revisado y diseñar un bootstrap explícito, versionado e
idempotente que cree únicamente `sources`, `references` y un manifiesto. Deberá
asignar IDs de dominio finales en ese momento, registrar la identidad del ZIP y del
plan, comprobar drift otra vez y exigir autorización de escritura inequívoca.

Incluso en S1C2, ese bootstrap inicial no modificará `concepts`,
`latex_documents`, `relations`, `knowledge_graph_maps`, `media_assets` ni
`latex_notes`; tampoco reemplazará `id@source`, añadirá bindings persistentes,
fusionará conceptos o implementará Documents/PDF. Esas transiciones requieren fases
posteriores y contratos separados.

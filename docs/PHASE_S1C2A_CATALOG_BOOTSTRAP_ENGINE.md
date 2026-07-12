# Fase S1C2A — Motor de bootstrap del catálogo legacy

## Objetivo

S1C2A implementa el motor que podrá materializar el Source Catalog de S1A a
partir del plan inmutable de S1C1. La escritura queda limitada a una copia
aislada y compatible de `MathV0`: crea un manifiesto durable, asigna una sola vez
los IDs finales, aplica explícitamente los índices aprobados, inserta Sources y
References, verifica el resultado y permite reanudar una ejecución interrumpida
sin regenerar identidades ni borrar datos confirmados.

La fase implementó la interfaz `apply`, pero toda su validación se hizo con
fakes/dobles deterministas. **S1C2A jamás ejecutó `apply` contra un MongoDB real,
jamás se conectó a MongoDB para escribir y no creó bases, Sources, References,
índices ni manifiestos reales.** Tampoco modificó `MathV0` ni `mathmongo`.

## Contrato autoritativo y conteos exactos

El motor acepta un solo snapshot y un solo plan:

| Contrato | Valor exacto |
|---|---|
| ZIP | `mathkb_export_20260712_073927.zip` |
| Tamaño del ZIP | 7,202,896 bytes |
| ZIP SHA-256 | `9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8` |
| Planner | `s1c1-v1` |
| Plan semántico SHA-256 | `e91599d50c58bb88014911590d34c9f0fc46b1c989dec8f3f25fed007a33b44f` |

Los conteos que forman parte del preflight y del manifiesto son:

| Resultado S1C1 | Conteo exacto |
|---|---:|
| Conceptos | 186 |
| Source candidates | 16 |
| Conceptos con Reference | 145 |
| Conceptos sin Reference | 41 |
| Reference candidates | 20 |
| References `safe_exact` | 20 |
| Bindings del plan | 186 |
| Conflictos bibliográficos | 0 |
| Review items de locator | 5 |
| Sugerencias débiles | 2 |
| Conceptos fusionados | 0 |
| IDs finales preexistentes | 0 |

La copia futura también debe coincidir documento por documento con las diez
colecciones legacy del ZIP:

| Colección legacy | Documentos |
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

El hash de decisiones no es una tercera constante global: se calcula a partir
del archivo humano completo, se liga al ZIP y al plan exactos, y luego se
persiste y reporta como `decisions_sha256`. Cambiar cualquier decisión vuelve
incompatible un manifiesto ya preparado.

## Arquitectura y frontera de escritura

La implementación queda fuera de Streamlit y de `MathMongo.__init__`:

```text
mathmongo/source_catalog_migration/
├── decisions.py      # entrada humana tipada, carga segura y hash canónico
├── apply_safety.py   # autorización y preflight puro/read-only
├── manifest.py       # asignación UUID, modelo durable y persistencia CAS
├── bootstrap.py      # conversión, reconciliación y state machine
├── apply_result.py   # outcomes y reportes acotados/redactados
└── cli.py            # decisions-template, apply-status y apply
```

El motor reutiliza `Source`, `Reference`, sus repositorios,
`SourceCatalogService`, `SourceCatalogIndexManager` y el plan S1C1. La única
frontera de escritura permitida es:

- documentos en `sources`, `references` y
  `source_catalog_migration_manifest`;
- los 15 índices aprobados de `sources` y `references`.

La selección de una base, repositorio, manifiesto o administrador de índices no
hace I/O por sí sola. El manifiesto usa su clave estable como `_id`, y todas sus
actualizaciones posteriores son compare-and-set por estado y revisión.

## Fuera de alcance

S1C2A no modifica ninguna colección legacy, ningún `source`, `referencia` o
`id@source`, ni crea `source_id`, `reference_id`, `concept_uid` o bindings en
conceptos. No fusiona conceptos ni corrige páginas, capítulos, secciones, nombres,
ortografía o localizadores.

Tampoco incorpora `concept_evidence_links`, Documents, PDFs, visor, anotaciones,
ReadingNotes ni rollback destructivo. No ofrece `--force`,
`--allow-production-write`, `--skip-drift-check` o `--ignore-conflicts`, y el
motor nunca llama `drop_database`.

## Decisiones humanas

`DecisionSet` es un modelo estricto, inmutable y versionado con
`schema_version=1`. Contiene los hashes completos del ZIP y del plan,
`accept_all_safe_exact`, una lista opcional de candidatas aceptadas y mapas
candidate-keyed para sugerencias débiles y revisiones de locator. No admite
campos desconocidos ni contiene IDs finales.

La plantilla generada es deliberadamente incompleta: usa `null` para decisiones
pendientes y no autoriza silenciosamente nada. Para este snapshot, un archivo
aplicable debe:

- aceptar exactamente las 20 References `safe_exact`, ya sea mediante
  `accept_all_safe_exact=true` o enumerándolas todas;
- cubrir exactamente las dos sugerencias débiles con `keep_separate`;
- cubrir exactamente los cinco review items de locator con `defer`;
- no mencionar claves desconocidas, candidatas no `safe_exact` ni review items
  no soportados.

El hash de decisiones usa JSON canónico y es independiente del orden de arrays y
objetos. El lector acepta sólo JSON UTF-8 en un archivo regular estable, rechaza
symlinks, claves JSON duplicadas, constantes no JSON y cambios durante la
lectura; su límite normal es 256 KiB y el máximo absoluto es 1 MiB.

## IDs finales

Las identidades finales siguen el contrato S1A:

- `src_<uuid4>` para Source;
- `ref_<uuid4>` para Reference;
- `mig_<uuid4>` para la migración.

Después del preflight y antes de cualquier entidad de catálogo se asignan los
mapas completos de las 16 Sources y las 20 References, en orden estable de
candidate key. Una sola marca UTC, truncada a milisegundos, sirve como
`created_at` de la asignación y como timestamp de todas las entidades derivadas.

Los mapas se insertan en el manifiesto `prepared` antes de Sources o References.
Una carrera de inserción tiene un solo ganador por `_id`: el proceso perdedor
carga el manifiesto ganador, comprueba todos los contratos y reconstruye el
catálogo esperado con sus UUID. Ningún rerun genera un segundo mapa y las
candidate keys nunca se usan como IDs de dominio.

## Manifiesto durable

La colección es `source_catalog_migration_manifest`. Su `manifest_key` se deriva
de `manifest_schema_version`, tipo de migración, target exacto, ZIP SHA-256 y plan
SHA-256. Excluye deliberadamente decisiones, UUID, timestamps, HOME y rutas; las
decisiones diferentes se detectan después como incompatibilidad sobre la misma
identidad estable.

El manifiesto conserva:

- versión, clave, `migration_id`, tipo, target, planner y los tres hashes de
  autoridad;
- mapas completos candidate key → UUID y conteos esperados;
- hashes por entidad Source y Reference, y hashes de evidencia por Reference;
- resúmenes acotados de evidencia legacy no representable en `Reference`;
- estado, timestamps, contadores creados/idénticos, intentos y reanudaciones;
- plan/resultado de índices y hash de su estado final;
- hashes de invariantes legacy antes y después;
- revisión CAS y hasta 20 errores redactados de 320 caracteres como máximo.

No almacena URI, credenciales, rutas absolutas, cuerpos de conceptos, LaTeX ni
variantes bibliográficas raw completas. Las validaciones exigen cobertura exacta
entre mapas y hashes, UUID v4 canónicos, timestamps UTC coherentes y progreso que
no exceda 16/20.

## State machine

El camino normal es monotónico:

```text
prepared
   → applying_indexes
   → applying_sources
   → applying_references
   → verifying
   → applied
```

`failed` conserva un fallo transitorio y es reanudable. Al reintentar, el motor
vuelve a verificar autoridad, target, manifiesto, legacy, catálogo e índices antes
de continuar. `blocked` es cerrado: una inconsistencia de seguridad, contenido o
conflicto no se adopta ni se sobrescribe. `applied` también es terminal para
escrituras; un rerun sólo reconcilia y verifica.

Cada transición persiste `revision` y `last_updated_at` mediante CAS. Las
transiciones normales no pueden retroceder. El inicio incrementa `attempts`, una
reentrada compatible incrementa `resume_count`, y `started_at`/`completed_at`
son set-once.

## Preflight

La CLI valida primero, sin leer configuración ni construir un cliente, todas las
afirmaciones de escritura. Después el motor exige explícitamente:

1. nombre y confirmación exactos del target aislado;
2. ZIP y plan con los dos hashes autoritativos;
3. hash semántico recalculado, `s1c1-v1`, invariantes S1C1, conteos exactos y cero
   conflictos;
4. decisiones completas ligadas al mismo ZIP y plan;
5. handle de base cuyo nombre coincide con el target autorizado;
6. cero o un manifiesto compatible para ese target;
7. dos capturas read-only consecutivas del legacy, iguales entre sí y al ZIP en
   conteos y fingerprints;
8. estabilidad de los índices legacy y cero escrituras reportadas;
9. ausencia física de `sources` y `references` para el primer apply, o presencia
   respaldada por el manifiesto compatible para una reanudación.

No se confía en un booleano agregado. Se comprueban por separado
`snapshot_drift=false`, `live_database_drift=false`, `writes_attempted=0`, los
conteos/fingerprints, la estabilidad de índices y la ausencia física inicial del
catálogo. Cada captura limita a 10,000 documentos por colección, 256 MiB de JSON
canónico total, 1,024 índices por colección y 10 segundos por operación de lectura.

Los hashes de las colecciones y los índices legacy se guardan antes del apply. En
la verificación se realizan otras dos capturas estables y se exige que el agregado
final sea idéntico al inicial.

## Seguridad del target

Se rechazan incondicionalmente, sin distinguir mayúsculas, `MathV0`, `mathmongo`,
`admin`, `config` y `local`. Sólo se aceptan nombres con sufijo no vacío y uno de
estos prefijos exactos:

- `MathV0_s1c2_validation_`;
- `mathmongo_s1c2_validation_`.

`apply` exige simultáneamente `--allow-isolated-write`,
`--confirm-database` igual byte a byte al target, ambos hashes completos y el
archivo de decisiones válido. La CLI sólo abre una base ya existente, comprueba
su nombre de nuevo, usa timeouts acotados y `retryWrites=False`; no crea ni elimina
la copia. `apply-status` exige `--allow-live-read` y la misma política de nombres
aislados.

Estas guardas hacen que la interfaz sea apta para el futuro arnés controlado, no
una autorización para ejecutarla durante S1C2A. En esta fase no hubo conexión de
escritura real ni intento de apply real.

## Conversión Source

Cada candidata produce una `Source` S1A con:

- `source_id` tomado del manifiesto;
- `name` igual al string legacy exacto y `name_normalized` calculado por el
  modelo S1A;
- `source_type=other`, `status=active`, aliases vacíos y defaults conservadores
  de derechos;
- `legacy.source_strings` con las variantes exactas aprobadas y
  `legacy.migration_batch_id` con el `migration_id`;
- `created_at` y `updated_at` iguales al timestamp persistido de la asignación.

No se embellecen nombres, no se sustituyen underscores o guiones, no se crean
aliases por similitud y no se asocian conceptos. El catálogo esperado contiene
exactamente 16 Sources.

## Conversión Reference

Cada una de las 20 candidatas aceptadas produce una `Reference` S1A cuyo
`reference_id` y `source_ids` salen de los mapas persistidos. La conversión pasa
por el modelo S1A el tipo propuesto, citekey, autores, título, `year`/`year_raw`,
journal, publisher, volumen, número, edición, ISBN, DOI, URL, idioma y notas; el
modelo calcula sus formas normalizadas y fingerprints.

La procedencia usa `import_method=legacy`, `imported_at` estable y advertencias
no localizadoras. Las 20 candidatas autoritativas son `safe_exact`, por lo que
quedan `active`; el conversor conserva `needs_review` para una clasificación no
exacta, aunque el preflight S1C2A rechaza ese tipo de plan.

Páginas, capítulos, secciones y demás locators no entran en `Reference`, en su
identidad ni en sus advertencias de procedencia. Las dos sugerencias débiles
permanecen separadas. Antes de insertar, un duplicado Source inesperado bloquea;
para Reference bloquean las clases exact, strong y possible, mientras una
sugerencia weak no fusiona ni impide conservar las candidatas aprobadas.

Cuando S1A no puede representar la forma legacy completa, el motor calcula un
hash de evidencia que incluye variantes raw, campos desconocidos, locators,
estadísticas y warnings. MongoDB recibe sólo ese digest y un resumen acotado con
conteo de variantes, nombres de campos y limitaciones. El raw original permanece
intacto en las colecciones legacy.

## Índices

El flujo llama explícitamente `plan()`, bloquea cualquier conflicto, llama
`apply()` y vuelve a verificar que no queden conflictos ni índices ausentes. Son
15 especificaciones: seis para Sources y nueve para References.

| Colección | Nombre estable | Claves | Unique |
|---|---|---|---|
| `sources` | `sources_source_id_unique` | `source_id ASC` | sí |
| `sources` | `sources_name_normalized` | `name_normalized ASC` | no |
| `sources` | `sources_aliases_normalized` | `aliases.normalized ASC` | no |
| `sources` | `sources_status_source_type` | `status ASC, source_type ASC` | no |
| `sources` | `sources_tags` | `tags ASC` | no |
| `sources` | `sources_updated_at` | `updated_at DESC` | no |
| `references` | `references_reference_id_unique` | `reference_id ASC` | sí |
| `references` | `references_source_ids` | `source_ids ASC` | no |
| `references` | `references_bibtex_key_normalized` | `bibtex.key_normalized ASC` | no |
| `references` | `references_doi_normalized` | `doi_normalized ASC` | no |
| `references` | `references_isbn_normalized` | `fingerprints.isbn_normalized ASC` | no |
| `references` | `references_author_title_year` | `fingerprints.author_title_year ASC` | no |
| `references` | `references_year_title` | `year DESC, title ASC` | no |
| `references` | `references_status` | `status ASC` | no |
| `references` | `references_updated_at` | `updated_at DESC` | no |

El SHA-256 canónico de esas especificaciones es
`a7251e3c231c6656f182bed38df73f402d712691d59fef5f30d6b5a185980b91`; el
estado final con las 15 presentes exactamente es
`c071a1b0fbbb5dcb0ae0472a44d449b787edea50f8e5442b432820dc956afb42`.
El manifiesto `prepared` ya nace con 15 esperados, 15 ausentes y el hash del
plan, antes de tocar índices o entidades. Después distingue aplicados, ya
presentes, ausentes y conflictos, y guarda el hash observado incluso cuando
bloquea; el resultado público refleja la misma evidencia. Un rerun no duplica
índices.

## Idempotencia y reconciliación

Antes de continuar, el motor enumera como máximo los 16 `source_id` y los 20
`reference_id` previstos. Rechaza IDs externos, duplicados o mal formados. Cada
entidad existente se hidrata con su repositorio y se compara mediante el hash de
su modelo S1A completo:

- mismo ID y mismo contenido: se cuenta como `identical` y se omite;
- mismo ID y contenido diferente: se bloquea sin overwrite;
- entidad confirmada por el manifiesto pero ausente: se bloquea;
- catálogo parcial sin manifiesto compatible: se bloquea en preflight.

Tras una primera ejecución completa, la segunda reutiliza UUID y timestamps,
verifica entidades, índices e invariantes y retorna `already_applied` con cero
inserciones. `identical` describe una reanudación de un manifiesto aún no marcado
`applied` cuyo catálogo completo ya era idéntico; `resumed` indica que el rerun
completó trabajo pendiente.

## Reanudación e interrupciones

El progreso se confirma en el manifiesto después de cada Source y Reference. Si
el proceso cae después de la inserción pero antes de actualizar el contador, la
reconciliación del siguiente intento descubre la entidad idéntica y no la repite.
Los índices se vuelven a planificar/aplicar de forma idempotente y sólo se crean
las entidades pendientes.

No hay transacción multi-documento ni rollback automático. La recuperación se
basa en el mapa durable, hashes por entidad, counters, estado/revisión CAS y
reconciliación. Una carrera posterior a la creación del manifiesto pierde el CAS
de forma segura y requiere recargar/reintentar; nunca reemplaza el estado ganador.

## Fallos y conflictos

Los outcomes tipados son `prepared`, `applied`, `resumed`, `already_applied`,
`identical`, `blocked`, `conflict` y `failed`. Un fallo operativo inesperado deja
`failed` y una siguiente ejecución puede reanudar. Drift, autoridad incompatible
y entidades inesperadas o distintas producen el outcome `blocked`; conflictos
de duplicados o índices producen `conflict`. En ambos casos, un manifiesto
compatible ya adoptado queda en el estado durable `blocked`. Un fallo de
preflight anterior a su creación no materializa un manifiesto.

La excepción es un manifiesto ajeno o incompatible: se reporta `blocked`, pero
nunca se adopta ni se modifica su estado, revisión, errores o mapas.

No se borra lo ya confirmado ni se eliminan índices o manifiestos. Los mensajes
persistidos y reportados colapsan whitespace, acotan tamaño y redactan URI,
credenciales y rutas locales. El resultado público incluye como máximo ocho
errores seguros, hashes, conteos, estado, invariantes y una siguiente acción, pero
nunca documentos o bibliografía raw extensa.

## CLI

La CLI conserva `status`, `dry-run` y `compare-live`, y añade:

```bash
python -m mathmongo.migrate_source_catalog decisions-template \
  --input-zip mathkb_export_20260712_073927.zip \
  --output /ruta/privada/decisions.json

python -m mathmongo.migrate_source_catalog apply-status \
  --database MathV0_s1c2_validation_<sufijo> \
  --allow-live-read

python -m mathmongo.migrate_source_catalog apply \
  --input-zip mathkb_export_20260712_073927.zip \
  --decisions /ruta/privada/decisions.json \
  --database MathV0_s1c2_validation_<sufijo> \
  --allow-isolated-write \
  --confirm-database MathV0_s1c2_validation_<sufijo> \
  --expected-zip-sha 9b8660712171c7ab6db6fb3148deac23921330e1a640615ae6ae36c97e2165c8 \
  --expected-plan-sha e91599d50c58bb88014911590d34c9f0fc46b1c989dec8f3f25fed007a33b44f
```

`decisions-template` no accede a configuración ni MongoDB. `apply-status` omite
los mapas de IDs, hashes por entidad y raw bibliográfico. `apply` valida la
autorización antes de abrir el ZIP, y valida ZIP, plan, decisiones e identidad
estable del archivo antes de leer configuración o conectar.

Las salidas son texto o JSON acotados. Los códigos específicos son 0 para
resultados satisfactorios/idempotentes, 2 para uso sin la puerta explícita de
escritura, 5 para `blocked`, 6 para `conflict` y 1 para `failed` u otro error.

## Pruebas

Las pruebas S1C2A usan exclusivamente dobles Mongo deterministas. Esos fakes
distinguen obtener un handle de materializar una colección, hacen round-trip BSON
de documentos y timestamps, implementan índices y CAS, registran el orden de cada
operación, rechazan escrituras legacy y ofrecen failpoints sólo para simular
carreras, drift e interrupciones.

La cobertura focal verifica:

- hashes, conteos, invariantes, conflictos y decisiones incompletas/desconocidas;
- todas las bases prohibidas, ambos prefijos aislados, flags y confirmación;
- UUID v4, persistencia del mapa antes de entidades, carreras y compatibilidad;
- estados/transiciones CAS, errores acotados y redacción;
- conversión exacta de 16 Sources y 20 References, source IDs, DOI/ISBN/citekey,
  provenance, ausencia de locators y separación weak;
- plan/apply/status de los 15 índices, idempotencia y conflictos;
- segunda ejecución no-op, entidades idénticas, contenido diferente y reanudación
  después de Sources o References parciales;
- cero escrituras en las diez colecciones legacy y ausencia de conceptos,
  bindings, Documents/PDFs o efectos laterales de import;
- CLI con factories inyectados, salidas acotadas y autorización previa a
  configuración/cliente.

La prueba integral del motor en
`tests/test_source_catalog_migration_bootstrap.py` contiene 24 escenarios y su
ejecución focal terminó con `24 passed`. Cubre la conversión 16/20, orden de
persistencia, apply completo, segundo apply read-only, dos puntos de
interrupción, carreras de manifiesto, entidad y CAS, colaboradores ligados a la
base incorrecta, contenido divergente, catálogo parcial sin manifiesto,
conflicto de índice y construcción sin efectos laterales. Las pruebas
complementarias de decisiones, manifiesto, seguridad y CLI cubren las puertas
puras y los reportes; la CLI también recorre el motor real sobre el fake y
demuestra un segundo apply sin escrituras.

Ninguna prueba usa `mongomock` como sustituto ambiguo ni abre un cliente PyMongo
real. La suite completa y las validaciones estáticas de cierre pertenecen a la
evidencia del commit; este documento no convierte una prueba fake en afirmación
de compatibilidad operacional con un servidor real.

## Limitaciones

- La integración con permisos, topología, versión y fallos de red de un MongoDB
  real no se validó en S1C2A.
- El motor no crea ni destruye la copia aislada; ese ciclo de vida pertenece al
  arnés S1C2B.
- No hay transacción global. La consistencia se obtiene con manifiesto CAS,
  verificación por entidad e idempotencia.
- Las únicas decisiones soportadas son aceptar las 20 `safe_exact`, mantener
  separadas las dos sugerencias weak y diferir los cinco locators. Otro plan
  requiere una fase y contrato nuevos.
- `Reference` no almacena locators ni toda la forma raw legacy. La evidencia no
  representable queda como hash/resumen, mientras el documento legacy original
  permanece sin cambios.
- No existen todavía vínculos persistidos entre conceptos y el nuevo catálogo.
- `blocked` no se fuerza ni se desbloquea; la recuperación prevista es inspeccionar
  evidencia y usar una copia aislada nueva.

## Plan para S1C2B

S1C2B podrá construir un arnés separado que cree una copia descartable con uno de
los prefijos permitidos, restaure exactamente el ZIP, prepare decisiones humanas
explícitas y ejecute por primera vez el `apply` real con los hashes completos.
Deberá capturar evidencia antes/después de las diez colecciones legacy, validar
16 Sources, 20 References, 15 índices y un manifiesto `applied`, y demostrar un
segundo apply sin escrituras nuevas.

Ese arnés también deberá probar interrupción/reanudación en copias descartables,
recoger logs redactados, confirmar que `MathV0` y `mathmongo` permanecen intactas
y eliminar exclusivamente la base temporal que él mismo haya creado. La
creación, ejecución real y eliminación de esa copia no forman parte de S1C2A y no
se realizaron en esta fase.

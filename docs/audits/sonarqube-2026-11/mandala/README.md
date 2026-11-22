# Editor visual y esfera de estudio — continuación

Decisión vigente: **frontend React independiente**, según
[INTERFACE_DECISION.md](INTERFACE_DECISION.md). La revisión concreta del encargo
y los checkpoints están en [FRONTEND_MIGRATION_REVIEW.md](FRONTEND_MIGRATION_REVIEW.md).
Las decisiones anteriores de esta bitácora se conservan como historia del trabajo.

Partida comprobada: `cf1ffc9c`, rama `feature/knowledge-sphere-2026-11`, árbol
limpio. Se conserva el checkpoint y la auditoría previa; no se reinicia su revisión.

## Evidencia e implementación por lotes

1. El Canvas conserva altura 470 fija y su ResizeObserver sólo cambia anchura.
   La ficha limita el contenido a 180 px y el editor se aloja en aside de 300 px.
   No hay renderizador matemático web ni editor documental visual: los avanzados
   actuales usan ACE y LaTeX canónico; Cornell/CPI aportan contratos de entornos
   y exportación PDF reutilizables, no un editor WYSIWYG.
2. No se atribuye un fallo de guardado al textarea sin reproducirlo. Se ejecuta
   el harness existente antes de cambios, con MongoDB, puertos y archivos propios.
3. Se localizó «Slowly oscillating shift» en el ZIP ya autorizado: copia privada,
   sin publicar su cuerpo. Contiene definition con título obligatorio entre llaves,
   arrays con columnas TeX avanzadas y figura TikZ. Debe preservarse íntegramente;
   las construcciones no soportadas se mostrarán localmente con acceso a fuente.
4. Orden: documento visual y borradores → espacio/lectura → arrastre/relaciones →
   vistas guardadas/áreas/pendientes → verificación real y comparación de calidad.

Las regiones usarán únicamente categorías elegidas explícitamente como áreas en
la vista. No se inferirán temas de autores ni se creará una taxonomía automática.
Los pendientes serán marcadores explícitos de estudio, no conceptos vacíos.


## Continuación obligatoria de mantenibilidad

La solicitud consolidada del 21 de noviembre mantiene abierto el inventario de
todo el código propio. Gate OK no significa revisión manual completa. Se recuperó
el análisis b4e0c8a8 sobre f5ddb587: 32 avisos abiertos S6903; los demás 70 registros
de incidencias devueltos por la API son históricos cerrados o falsos positivos
individuales, y no se cuentan como deuda abierta. Instalación y referencia sin cambios.

El commit a1442700 centraliza 32 llamadas UTC naive en cinco módulos, manteniendo
fechas BSON naive y sufijo ISO Z. No migra fechas ni aplica timezone local. Las
33 pruebas focalizadas pasan. La comparación Sonar del lote se registrará al
terminar sus verificaciones y procesamiento.

El recorrido Chrome del editor ya pasa con fuentes de red externas bloqueadas:
prosa, fracción y matriz visuales; borrador incompleto, recarga, recuperación,
corrección y un único guardado. La causa de escritura inerte fue la eliminación
de contenteditable por DOMPurify en el marcado interno de MathLive. Se permite
específicamente ese atributo sin aceptar HTML crudo del documento. La selección
de plantillas usa el campo insertado, no un foco anterior pendiente de MathLive.
Firefox y el recorrido completo de habitación siguen por verificar.

La validación ampliada inicial dio 1970 aprobadas, 2 fallos de expectativas de
configuración y 9 E2E opt-in omitidos. Las expectativas se actualizaron conservando
versiones fijadas y ubicación del tema; no se retiraron comprobaciones funcionales.
Las ejecuciones focalizadas posteriores se registran separadas de esa integral.


## Segundo cierre de lote (antes del anexo DOI/ISBN)

Código: `3348b7534a88c951aa8a09b3d72ec13ff865cea8`; análisis
`0bfc6727-9caa-437b-96b9-3061fe04fb99`, CE SUCCESS, **Gate OK**.
Cobertura nueva **86,0 %** (antes 73,0), general **69,5 %** (antes 68,8);
duplicación general **1,6 %** (antes 1,8), nueva 0,0; avisos nuevos 0.
Bugs, vulnerabilidades y code smells abiertos: 0. Los 32 S6903 heredados se
resolvieron con el adaptador UTC, no con supresiones. Se mantiene la misma
referencia PREVIOUS_VERSION de 2026-11-21T16:46:16+0000 y los umbrales 80/3/0.

El primer déficit se localiza en BATCH1_COVERAGE.csv: sobre todo controles y
Canvas, y módulos nuevos de disposición, áreas, lectura y MathLive sin pruebas
unitarias instrumentadas suficientes. Los recorridos de navegador existentes
no alimentaban el LCOV de Vitest; no se afirmó que todas sus líneas estuvieran
cubiertas sólo por haberlos ejecutado. Se añadieron comprobaciones de resultado
para lectura completa/segura, geometría, áreas, fijación/deshacer, objetivos,
versiones guardadas y recuperación/aislamiento de borradores. MathLive detectó
además un fallo real: acepta algunos grupos incompletos; se comprueban argumentos
y llaves sin simplificar expresiones.

El segundo lote archiva XML, LCOV, resumen y huellas en evidencia privada por
etiqueta antes de subirlos. El scanner confirmó ambas importaciones. Su fuente
propia y su configuración estaban en el commit indicado; el diff adicional sólo
contenía documentación. Se conserva la métrica local Python separada de Sonar,
que combina lenguajes y condiciones.

CPI: `a8c88c85`, tres gestores consolidados, de 1707 a 1485 líneas físicas
(helpers incluidos), sin borrar capacidades. Las 9 nuevas pruebas de
caracterización pasan antes y después; 67 regresiones CPI aprobadas. No se
cuentan como 222 líneas eliminadas de producto: son duplicación consolidada.
Las retiradas/regeneraciones de bundles se cuentan aparte.

Pendientes de entrega: habitación y recorrido completo; referencia bibliográfica
por DOI/ISBN; inventario final por estado/huella y decisiones de grandes módulos;
comparación PDF, verificación completa de interacción y análisis Sonar de los
próximos lotes/final. Este Gate no se presenta como cierre de esas tareas.


## Lote Mathfield y anexo bibliográfico

Se conserva la misma rama y la referencia de código nuevo. Commits locales por
alcance: afac9e33 (licencias de dependencias de ejecución), 1dda293a (Mathfield),
bd4a997c (catálogo/adaptadores y protección de referencias), 2be90ea2
(interfaz/citas/exportación), bbf8eba4 (normalización de avisos redistribuidos).
No hay push ni merge. El cambio de helper applySavedView sólo evita identificar
por error una función de modelo como React Hook; no es una ruta retirada.

La integral Python produjo 2040 aprobadas / 3 fallidas / 9 omitidas inicialmente.
Los fallos eran un hash deliberadamente congelado antes del anexo, un doble de UI
que carecía de expander y una frontera histórica S1B que prohibía incluso leer
notas/evidencia para proteger su referencia. Se actualizó el contrato conservando
el hash de los otros tres dominios y comprobando que el nuevo método sólo lee.
Las 74 pruebas de esos módulos pasan; los nueve casos omitidos se ejecutan y pasan
en el runner Mongo propio. Dos casos nuevos comprueban procedencia DOI/ISBN en
BSON; el resto de verificaciones afectadas se repite por archivo modificado,
purgando primero sus hits de cobertura. Los cohortes reconciliados suman 2054
IDs Python comprobados, sin pruebas privadas bloqueadas. No se suman las
repeticiones de 74/51/17/12 casos como si fueran pruebas diferentes.

Cobertura local de este corte: Python 31848/45644 = 69,77 %; frontend V8
2982/3727 = 80,01 % de líneas. Sonar añade condiciones JS y tiene otro alcance;
estas cifras no sustituyen su cobertura nueva. Se han archivado XML/LCOV y sus
hashes antes del envío de análisis, con revisión exacta bbf8eba4. CE terminó SUCCESS; [resultado íntegro](BATCH3_RESULTS.json). El lote anterior mantiene Gate OK, 86,0 % nueva,
69,5 % general y cero bugs/vulnerabilidades/avisos abiertos.

No se eliminan capacidades del catálogo ni los editores avanzados. Se conserva
el estado canónico Source/Reference/SourceDocument/ReadingNote. DocumentCitation
extrae una responsabilidad de ciclo de vida del coordinador y bibliography.ts
atiende sólo la ficha y sus respuestas. Ambos módulos se cuentan como código
nuevo/extraído, no como reducción neta. El bundle anterior se sustituye por uno
regenerado (98 % similar), sin atribuirlo a eliminación de código propio.

[Anexo y verificaciones](BIBLIOGRAPHY_ANNEX.md),
[decisión de interfaz](INTERFACE_DECISION.md),
[archivos grandes](LARGE_FILES.md) y [registro completo](REVIEW_REGISTER.csv)
quedan acumulados. La habitación, las pruebas pendientes de escena/PDF y los
lotes de mantenibilidad del resto del repositorio siguen activos.


### Sonar del lote bibliográfico procesado

Análisis `6707a6ca-73e4-4754-98bb-890f0221b408`, revisión
`bbf8eba44cbb5b27db90ca7b219a7bd2862b4907`. Gate **OK**:
85,5 % nueva (mínimo 80), duplicación nueva 0,0 % (máximo 3) y cero incidencias
nuevas (máximo 0). General 70,6 %, líneas 70,8 %, duplicación general 1,5 %;
cero bugs, vulnerabilidades, code smells y hotspots abiertos en el código analizado.
No significa que todos los pendientes manuales estén cerrados.

Se conserva PREVIOUS_VERSION, 2026-11-21T16:46:16+0000, exactamente igual al
lote anterior. Misma configuración SHA-256 y mismos perfiles/configuración de
reglas; la comparación de respuestas de perfiles omite únicamente lastUsed,
que el servidor actualiza al ejecutar cada análisis. No se modifica ese campo
ni ninguna regla. Se importaron XML y LCOV sin avisos de rutas no resueltas;
los reportes exactos quedaron archivados con hashes antes del envío.

[BATCH3_COVERAGE.csv](BATCH3_COVERAGE.csv) desglosa los 76 archivos que contribuyen:
3999 líneas nuevas, 465 sin cubrir; 1122 condiciones nuevas, 279 sin cubrir.
Sonar combina 4377/5121 elementos = 85,5 %. La mayor deuda de cobertura nueva
está en Canvas, coordinador, document-editor, codec y el UI de catálogo. Las
pruebas reales de navegador verifican comportamiento pero no se atribuyen al
LCOV de Vitest. No hay reportes omitidos ni una exclusión nueva para ocultar ese
déficit; las ramas aún no instrumentadas o verificadas se mantienen visibles.

Comando completo reproducible, con la misma referencia validada por el script:

```bash
SONAR_LABEL=study-repeat-20261122 make sonar-scan
```

SONAR_LABEL sólo nombra evidencias. No cambia sonar.projectVersion ni el período.
El comando recompone cobertura en entornos propios y espera CE/Quality Gate.
Para este lote se reutilizaron las cohortes válidas y se ejecutó el scanner sobre
los XML/LCOV actualizados y archivados, sin repetir toda la integral sin necesidad.


## Habitación integrada y lote de mantenibilidad fuera de interfaz

[Guía, regresiones y límites](STUDY_ROOM.md). La rama continúa siendo
feature/knowledge-sphere-2026-11; no hay push ni merge. El anexo de DOI/ISBN no
reinicia el trabajo. Se conserva la referencia Sonar y la instalación persistente.

Verificación integral posterior a la integración: **2050 aprobadas / 9 omitidas /
0 fallidas**, 2059 recogidas. El runner Mongo propio ejecuta esas mismas nueve:
**9 aprobadas / 0 fallidas**. Resultado conjunto: 2059 IDs Python verificados,
sin sumar repeticiones de módulos como casos distintos. El primer intento tenía
un fallo de huella histórica por la extracción autorizada en bootstrap; el
segundo integral ya pasa tras revisar y actualizar esa huella. Las otras
protecciones históricas permanecen. Frontend: **209 pruebas aprobadas**, build,
TypeScript y ESLint verificados. Las pruebas privadas del ZIP siguen pasando.

Commits de alcance: 6fd10d39 corrige el argumento obligatorio de caja al exportar;
3a6ad16e lleva azul compartido al lector PDF; 8bb810e7 consolida comprobaciones
de completitud manteniendo las cuatro barreras; df3a22f2 integra la habitación y
separa el diálogo/controles; 6f711d2e y bcf09619 verifican recursos propios,
respuesta perdida y movimiento; 7d08c699 publica el runtime reconstruido.
Las salidas generadas se cuentan aparte y no son eliminaciones de producto.

El inventario se actualiza a 328 módulos mantenidos / 200 archivos de pruebas.
Hay veinte propios actuales de más de mil líneas, todos con decisión registrada;
component.ts pasa a 927 contando además las extracciones de 398 y 132. Continúa
el inventario del resto del repositorio: cero incidencias automáticas no equivale
a revisión manual terminada.


### Análisis final procesado y alcance de las verificaciones

[FINAL_STUDY_RESULTS.json](FINAL_STUDY_RESULTS.json): análisis
ce5ea5f2-3ad3-49a8-8da5-9b9c5cadade9, fuente be6d6c9d, CE SUCCESS, Gate **OK**.
General **70,9 %**, nueva **82,3 %**, duplicación nueva **0,0 %**, incidencias
nuevas **0**; cero bugs/vulnerabilidades/code smells abiertos. El lote
bibliográfico anterior tenía 70,6 % general y 85,5 % nueva con un alcance de
código nuevo menor. La referencia, perfiles, umbrales y exclusiones se conservan.
La nueva cobertura se desglosa por archivo en FINAL_STUDY_COVERAGE.csv.

El primer análisis de habitación tenía Gate ERROR únicamente por el comparador
de IDs; se corrigió con compareKeys, sin supresión. Se encontró además una
diferencia demostrada de instrumentación: el XML fresco de pytest no recogía
la entrada Streamlit ejecutada por el navegador. La integración de cobertura
subprocess aporta 790 líneas medidas antes ausentes (540 de la entrada), sin
retocar alcance. El diagnóstico y las cifras intermedias están en STUDY_ROOM.md.
Cobertura local final Python 70,16 %, V8 líneas 79,00 %: no se equiparan a Sonar.

Tras la integral y el runner Mongo se añaden tres regresiones del tooling; pasan
las 45 del grupo afectado y 14 contratos HTTP. Total reconciliado **2062 IDs
Python distintos**; la última integral completa era 2050 aprobadas/9 omitidas/0
fallidas y esas nueve pasan aparte. Frontend: 209 aprobadas. Los recorridos
Chrome/Firefox verifican además editar el concepto en una esfera y leer el
cambio desde la otra, con un único registro. Ruff queda en 2155 avisos, agrupados
en RUFF_CURRENT.csv. El Gate aprobado no cierra esa deuda ni el inventario manual.

La repetición del benchmark después de las verificaciones da 8,515 ms de media,
máximo 12 ms, frente a 7,87/12,5 anteriores. La primera medida concurrente
10,56/28,9 también se conserva. No se afirma mejora ni FPS sostenidos.

Se conserva el resto de pendientes de LARGE_FILES.md y STUDY_ROOM.md, incluyendo
paginación del snapshot y composición de módulos heredados. No quedan bloqueos
por el ZIP privado. Los commits 02693cfd y bc2a26d5 completan el comparador y la
instrumentación reproducible; los demás commits de este lote están arriba.


El ajuste visual final be6d6c9d retira espacio vacío del teclado mediante
geometrychange/boundingRect públicos. Pasa la regresión nueva y las cuatro
distribuciones en ambos navegadores. Se conserva el análisis previo de habitación
en ROOM_RESULTS.json; FINAL_STUDY_RESULTS.json corresponde al último Mathfield.
No se reutiliza el Gate anterior como si hubiese analizado ese cambio.


| Corte comparable | General Sonar | Nueva Sonar | Gate | Incidencias nuevas |
|---|---:|---:|---|---:|
| Bibliografía, bbf8eba4 | 70,6 % | 85,5 % | OK | 0 |
| Habitación inicial, bcf09619 | 69,4 % | 81,8 % | ERROR | 1 |
| Final Mathfield, be6d6c9d | 70,9 % | 82,3 % | OK | 0 |

La comparación conserva referencia y configuración, pero el código nuevo crece:
5121 elementos medidos en bibliografía frente a 6439 al final. El porcentaje
nuevo no compara el mismo conjunto de líneas sin esa salvedad. La cobertura
local V8 pasa de 2982/3727 a 3473/4396 líneas, al incorporar la habitación.

En el grupo del coordinador, 1236 líneas previas pasan a **1457** al contar
927 + 398 + 132: hay 221 líneas netas añadidas en ese grupo. El beneficio es
separar ciclo de documento y controles de visibilidad; no una reducción cosmética
ni una eliminación de 309 líneas de producto.

### Lectura, extracción y cambio a frontend independiente

Se mantienen rama `feature/knowledge-sphere-2026-11`, instalación y commits.
`1b8e8ead` implementa preparación S3/S4 explícita y no destructiva, con estados
separados de pendiente compatible, permisos/conexión no comprobables y conflicto.
Reutiliza los managers aprobados y vuelve a leer sus planes antes de habilitar
escritura. `08dd5d96` la integra en Lectura, retiene el borrador al fallar el
guardado y permite leer PDF verificado sin registrar posición cuando no se puede
escribir. Abrir Lectura o Diagnóstico no aplica ese mantenimiento. La inspección
de MathV0 fue exclusivamente de lectura; no se preparó la base habitual.

El análisis de ese lote, `14fc0f8a-09c7-41ba-8fe3-d6fd44c9ff0b`, terminó en
CE SUCCESS / Gate OK, **71,1 % general / 82,6 % nueva**. Las cinco pruebas
AppTest cubren preparación, permisos, incompatibilidad, diagnóstico sin cambios y
guardado fallido con reintento que conserva texto y confirma un registro real.

El encargo posterior sustituye Streamlit por React como interfaz principal.
Ya existen React/Vite, FastAPI y el lector HTTP; la habitación conserva TS/CCv2.
La revisión documenta su desacoplamiento, contratos de contexto/revisión/
idempotencia, transferencia explícita de borradores entre orígenes y el primer
recorrido fuente → pasaje → nota → concepto → esfera → origen. La aplicación
independiente completa todavía está pendiente. No se construye una segunda
navegación completa en Streamlit ni se presenta una maqueta como migración.

`203dd6cd` conserva la extracción iniciada: **5744 → 29 líneas** en el entry;
**6134 en el conjunto relacionado**, 390 netas añadidas al contar las ubicaciones
extraídas. Veinte páginas y siete grupos de helpers se conservan, con contexto
explícito, importación de la página activa y sin renderizar al importarse.
No se retiraron flujos avanzados ni modelos Cornell/CPI. Se eliminó una variable
intermedia sin consumidores locales y bindings de imports sobrantes tras separar
dependencias; no se eliminaron validaciones ni pruebas. `42ff4eb5` limpia dos
bindings obsoletos de los tests adaptados.

La integral de este corte dio **2068 aprobadas / 9 omitidas / 1 fallida** de
2078 casos. El único fallo era el destino de una comprobación estática de gráficos
(tres en Inicio y uno en Relaciones); corregido, sus cinco casos pasan. Las nueve
omitidas pasan en el Mongo propio. Cinco regresiones nuevas de dispatch/contexto
e importación también pasan. Se reconcilian **2083 IDs Python distintos**
verificados; no se afirma otra integral monolítica posterior. La última repetición
de los contratos afectados da **13 aprobadas**. Chrome recorre el editor y la
habitación tras extraer; las verificaciones frontend previas siguen válidas para
su código intacto, sin sustituir el futuro recorrido React autónomo.

Sonar de la extracción: [NAVIGATION_RESULTS.json](NAVIGATION_RESULTS.json),
análisis `0aa030c7-75e7-4ccb-91eb-f21d04ef7949`, fuente `203dd6cd`, CE SUCCESS,
**Gate ERROR** sólo por cobertura nueva **63,6 % < 80**. General **71,2 %**,
duplicación nueva **0,17408 % ≤ 3**, incidencias nuevas **0**. Misma referencia
PREVIOUS_VERSION `2026-11-21T16:46:16+0000`, perfiles y exclusiones intactos.
No se utiliza el Gate anterior como si hubiese validado las nuevas ubicaciones.

Los archivos trasladados entran completos en código nuevo. Aportan 3145 líneas
medibles, 2420 sin cubrir. Se cotejó el XML con Sonar en los 32 módulos y coincide
exactamente: **0 líneas faltantes por importación demostradas** en ese conjunto.
El déficit corresponde a flujos heredados poco ejercitados, sobre todo mapas,
relaciones y formularios de conceptos. Véanse [NAVIGATION_COVERAGE.csv](NAVIGATION_COVERAGE.csv)
y [NAVIGATION_REPORT_IMPORT.json](NAVIGATION_REPORT_IMPORT.json). No se cambia
periodo, umbral ni alcance. Python local: 32537/46156 = **70,49 %**.

La reproducción aislada [DELETION_BEFORE.json](DELETION_BEFORE.json) ejecuta las
sentencias reales de borrado extraídas, sin simular su confirmación visual.
Edición deja 0 relaciones y exploración 1; ambas dejan 1 evidencia al concepto
eliminado. Referencia, medio compartido y otro concepto se conservan. El servicio
común, sus fallos parciales y la confirmación ligada a contexto/revisión quedan
pendientes antes de exponer el borrado en React; no se anuncia una corrección.

Inventario actualizado: 363 archivos mantenidos, 203 de pruebas, veinte propios
de más de mil líneas con decisiones conservadas. El nuevo módulo histórico de
mapas mide 1381 y sigue pendiente de migración. Ruff: **2161 avisos**, incluidos
1437 E101 del literal JS heredado; la revisión del resto del repositorio sigue
abierta. AppImage permanece pendiente. Todos los commits son locales, sin push
ni merge.

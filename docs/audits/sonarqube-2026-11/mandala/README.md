# Editor visual y esfera de estudio — continuación

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

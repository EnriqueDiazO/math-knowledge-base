# Cornell, CPI y herramientas matemáticas: checkpoint del 24 de noviembre de 2026

Se continúa desde `278b420c`, en `feature/knowledge-sphere-2026-11`, inicialmente
limpia. Se conservan todos los commits anteriores y la instalación Sonar existente.
No hay push, merge, reinstalación, cambio de credenciales ni escritura en MathV0.

## Capacidades implementadas

Desde **Cuaderno → Cornell / CPI** se puede crear, buscar, abrir, editar regiones,
guardar, recargar y exportar TEX/PDF sin Streamlit. Cornell conserva preguntas,
desarrollo y síntesis; CPI conserva Comprensión, Producción e Integración. No son
plantillas del Diario ni colecciones nuevas. Se reutilizan modelos, servicios y
`latex_notes`, la fachada MathMongo, el editor Tiptap/MathLive, catálogo y bundles.

Las tres regiones tienen cuerpos LaTeX independientes. Sólo la región seleccionada
ocupa el editor. Los borradores y snapshots se aíslan por biblioteca, familia,
nota, página y región. Se puede añadir, duplicar, reordenar y retirar páginas del
borrador, con confirmación para retirarlas. **Retirar una página no borra archivos
físicos ni equivale a eliminar una nota.** Se preservan metadatos opacos por página.
Cornell conserva `page_id`; CPI conserva su contrato `page_number`, con orígenes
explícitos para distinguir propiedad y posición cuando se reordena.

La referencia del catálogo se inserta deliberadamente como cita LaTeX editable en
la región activa. Los `source_refs` históricos permanecen; esta inserción no se
presenta como una migración completa del administrador de asociaciones históricas.

Rutas nuevas: `/study/notebook/{cornell|cpi}` y
`/api/study/v1/structured/{cornell|cpi}`. El prefijo HTTP común comparte guardas y
transporte, con sólo dos familias explícitas. Las rutas directas propuestas en
`CORNELL_CPI_NEXT.md` no llegaron a publicarse: no se añaden alias duplicados.
El listado pagina veinte resúmenes y obtiene cuerpos únicamente al abrirlos.
No se hicieron afirmaciones de mejora de latencia sin un benchmark equivalente.

## Integridad y regresiones demostradas

| Problema | Evidencia anterior | Corrección / comprobación |
|---|---|---|
| Actualización estructurada sobrescribe otra escritura | Cuatro casos reales fallan antes (`structured-atomicity-before.log`) | Una instantánea BSON y CAS; sin transacciones incompatibles con Mongo standalone |
| Guardar sin cambios regenera fuente histórica | Misma cohorte negativa | Escritura mínima; conserva fuente divergente, desconocidos, defaults ausentes y timestamps |
| PDF Cornell depende de `lineas.png` exterior | Cornell falla en sandbox; CPI pasa (`structured-export-before.log`) | Bundle canónico incluye el recurso propio; ambos compilan sin relajar aislamiento |
| Reordenar páginas CPI idénticas pierde propiedad de metadatos | Regresión real con dos páginas y campos opacos distintos | Orígenes explícitos y huella del intento; replay exacto, rechazo de un orden obsoleto |
| Orden físico histórico diferente del académico | Dos regresiones con BSON invertido | Presentación ordenada; no-op conserva el documento Mongo íntegro |
| ACK perdido / compensación de referencias de medios incompleta | Mongo real, fallo inyectado sólo al actualizar registro de medios | ID de creación único; reconciliación reintentable conserva las referencias de otras notas y nunca purga bytes |
| Escritor aparece después del CAS | Dos pruebas de confirmación tardía | Relectura real; conflicto en vez de anunciar el contenido solicitado como guardado |
| Fuente histórica no coincide con sus regiones | Pruebas de no-op, cambio de título y edición de región | Metadata/no-op permitidos; regeneración incompatible rechazada; TEX mantiene la fuente original |
| Una región desborda o no compila | TeX real en namespace, con contenidos extensos y macro ausente | Informe de ajuste y error accionable; PDF bloqueado; fuente, nota y TEX conservados |

El ajuste usa la geometría, medición y escalas mínimas canónicas, dentro del
compilador restringido existente. Un trabajo acotado por página evita perder
mediciones por truncamiento del log. No se llama desde HTTP al `pdflatex` legado
fuera del sandbox. Exportar sigue siendo una operación separada de guardar.

Pruebas focalizadas finales de ramas: persistencia compartida **98 % combinado**,
layout **100 %**, dominio estructurado **100 %**, adaptadores HTTP **100 %**.
La tabla exacta y denominadores están en el JSON local de cobertura de ramas.
No se mezcla ese archivo con el XML Python comparable de líneas.

## Selección de Matchaio y compatibilidad LaTeX

La auditoría y matriz están en [MATCHAIO_REVIEW.md](MATCHAIO_REVIEW.md). Se ejecutan
31 pruebas de Matchaio en copia temporal, sin modificar su repositorio, copiar
código ni incorporar dependencias. Tres mejoras propias sobre MathLive:

1. Inserción localizada y selección: `replaceAll` borraba `a+b` al añadir una raíz.
   La prueba real falla antes y pasa con `replaceSelection`. Historial explícito
   de la fórmula, separado del historial Tiptap del texto.
2. Paleta buscable de trece estructuras, con operadores, delimitadores, sistemas y
   alineación. No sustituye el teclado MathLive. Herramientas secundarias acotadas
   para conservar visible el documento; fuente y construcciones protegidas siguen
   disponibles.
3. Matrices configurables de 1–8 filas/columnas, `pmatrix`, `bmatrix` o `vmatrix`,
   con ceros editables y rechazo de parámetros inválidos sin tocar la fórmula.

Se comprueban matriz 3×2, expresiones anidadas y selección de subexpresión,
deshacer/rehacer, fuente ↔ visual, TikZ y entorno personalizado definido, persistencia
y PDF con las plantillas reales. La modificación intencional de una fórmula conocida
puede adoptar el formato serializado de MathLive; eso no autoriza normalizar los
fragmentos no editados. En una copia histórica con sintaxis particular se modifica
una sola fórmula **mediante fuente**, comprobando igualdad exacta del resto. No se
declara reversible visualmente cualquier TeX. Las cinco copias reales conservan
su fuente exacta en la cohorte de no-op anterior a ese experimento explícito.

## Calidad y distribución

Referencia preservada: `PREVIOUS_VERSION`, `2026-11-21T16:46:16+0000`.
SHA256 de `sonar-project.properties` sin cambios:
`84aec1246aae6a1a3949f786449faf9c19a10894cfcb044adcf81866f18f08a6`.
`SONAR_LABEL` sigue nombrando evidencias y no configura una versión del proyecto.

Línea base: análisis `b4ddd3bd-402b-4ab7-80b3-df8231fcc998`, fuente `a6d77fdb`,
**76,0 % general / 80,6 % nueva, Gate OK**. El análisis intermedio
`54e6847a-86d7-4bc2-a573-63d2226071cd`, fuente `c2d3427d`, mide
**76,2 % / 81,3 %**, pero Gate ERROR por un único `typescript:S9011`:
botón de búsqueda sin `type="submit"`. Se corrige y prueba; no se suprime la regla.
El cierre procesado y sus condiciones exactas se detallan abajo; el error intermedio
queda conservado como evidencia, sin presentarlo como el estado vigente.

La medición global Python conserva su alcance y formato de líneas. Las condiciones
Sonar corresponden al frontend instrumentado. Vitest y Chrome se unen verificando
hashes de artefactos publicados/mapas/fuentes; no se acreditan datos de una cohorte
fallida ni se alteran denominadores. El 95 % general/nuevo **sigue pendiente**;
`COVERAGE_95_PLAN.md` mantiene el inventario de riesgos y la brecha cuantificada.

Se construyó y verificó una AppImage nueva con el constructor, runtime y diecinueve
distribuciones fijadas existentes. La imagen inicial `f00aa5ac` permanece íntegra. El paquete usa
MongoDB y LaTeX del anfitrión, con `bwrap`/`prlimit` y navegador externos. No es
autónomo, no administra mongod, no necesita Streamlit y mantiene perfiles XDG fuera
del ejecutable. El artefacto y las pruebas empaquetadas constan en el cierre siguiente.

## Paridad restante y punto de reanudación

**Completado el núcleo delimitado; Cornell y CPI completos siguen parciales.**
Faltan gestión visual integral de medios y asociaciones, preferencias/editorial de
marca de agua y atribución, duplicación/borrado de nota completa con fallos parciales,
y aceptación de propuestas de división por desbordamiento. Se conservan los servicios
y páginas anteriores. Worklog, Backlog, Weekly y Deliverables siguen pendientes,
al igual que transferencias y administración avanzadas de la matriz histórica.

`editor/editor_streamlit.py` permanece en **21 líneas**. Los veinte archivos propios
de más de mil líneas conservan sus hashes del inventario anterior: se reutilizan
sus revisiones y decisiones, sin declararlos eliminables por este checkpoint.
No se retira código de producto. Los cambios de nombres/bajas de bundles generados
son publicación de assets, no eliminación de capacidades. Los módulos nuevos,
pruebas y salida generada se cuentan separadamente en el cierre.


## Resultado del servidor y comparación

Análisis final **`68db7833-292e-46f7-8b7b-93e7998ded5e`**, revisión exacta
**`0e08a639578546f0fbcd5375be299efdffef4163`**, CE **SUCCESS**.
Snapshot local: `evidence/sonar/cornell-cpi-delivery-sonar.json`.
El resumen versionado está en `CORNELL_CPI_RESULTS.json`.
Los únicos cambios posteriores a la construcción `098cab43` son pruebas y este
registro: los archivos de producción son idénticos. La fuente analizada se
registra con su SHA completo, sin atribuirle commits posteriores de documentación.

| Medida comparable | Línea base | Cierre |
|---|---:|---:|
| Cobertura general | 76,0 % | **76,4 %** |
| Cobertura nueva | 80,6 % | **81,7 %** |
| Líneas generales cubiertas / medibles | 41 478 / 54 185 | 42 202 / 54 922 |
| Condiciones generales cubiertas / medibles | 3093 / 4461 | 3353 / 4743 |
| Líneas nuevas cubiertas / medibles | 9744 / 11 739 | 10 487 / 12 489 |
| Condiciones nuevas cubiertas / medibles | 2342 / 3252 | 2602 / 3534 |
| Gate oficial | OK | **OK** |

Condiciones oficiales: cobertura nueva ≥80 % (**81,7**), duplicación nueva ≤3 %
(**0,09069**), incidencias nuevas ≤0 (**0**). CE debe ser `SUCCESS`; el snapshot
comprueba que el `analysisId` y la revisión sean los del análisis procesado.
Se mantiene el inventario de incidencias heredadas: cero nuevas no significa
que toda la deuda del proyecto esté resuelta.

La aceptación adicional del **95 % general y nuevo no se alcanza**. Quedan
14 110 observaciones generales y 2934 nuevas sin cubrir. A denominador fijo
faltan **11 127** y **2133** observaciones cubiertas, respectivamente. No son
números de pruebas ni una estimación de horas. El JSON conserva los veinticinco
archivos con mayor déficit de cada alcance y `COVERAGE_95_PLAN.md` su prioridad.

| Módulo del lote | Sonar combinado | Condiciones JS / medición Python separada |
|---|---:|---|
| `formula-tools.ts` | 99,2 % | JS: 25/26 |
| `structured-state.ts` | 100 % | JS: 62/62 |
| `StructuredReferences.tsx` | 100 % | JS: 12/12 |
| `StructuredFields.tsx` | 98,0 % | JS: 19/20 |
| `StructuredPages.tsx` | 95,2 % | JS: 28/30 |
| `StructuredWorkspace.tsx` | 92,0 % | JS: 100/118; pendientes de recuperación/estado en el coordinador |
| Persistencia estructurada Python | 98,3 % de líneas | Local separado: 58/59 líneas, 29/30 ramas |
| Dominio estructurado Python | 100 % de líneas | Local separado: 124/124 líneas, 32/32 ramas |
| HTTP estructurado Python | 100 % de líneas | Local separado: 88/88 líneas, 8/8 ramas |
| Ajuste aislado Python | 100 % de líneas | Local separado: 32/32 líneas, 6/6 ramas |

No se mezclan las ramas Python con un XML de líneas para aumentar la cobertura
comparable. La rama faltante de persistencia corresponde a retirar una clave conocida durante la
fusión de diccionarios; se conserva identificada en el JSON de ramas.

### Importación e instrumentación comprobadas

Se importan `evidence/sonar/coverage.xml` y
`frontend/advanced-reader/coverage/lcov.info`; las rutas analizadas coinciden con
las fuentes. El XML Python nativo mide **36 227/50 508 (71,73 %)**. Sonar mide
para Python propio **36 227/47 745 (75,88 %)**: las 2763 líneas adicionales del
XML pertenecen a tres copias/sondas locales de evidencia y al módulo Python de
`node_modules/flatted`, fuera del alcance Sonar vigente. Cada archivo Python
analizado coincide exactamente con el XML. No hay cobertura perdida al importar
ni cambios de exclusiones en este lote. El detalle de las cuatro rutas está en
`report_scopes` del JSON.

LCOV de unidades: **5038/6441 líneas y 3140/4743 condiciones**. Con los nueve
recorridos Chrome válidos: **5336/6441 y 3353/4743**, incremento observado de
**298 líneas y 213 condiciones**. Firefox comprueba comportamiento; no aporta
hits V8. Sonar también considera **723 líneas sólo presentes en BRDA** (639
cubiertas) y trece líneas de configuración no incluidas en LCOV. Por eso registra
7177 líneas JS y 5975 cubiertas. La unión DA/BRDA reconcilia exactamente todos
los archivos LCOV con Sonar; no se corrige el informe ni se cambian denominadores.

De las observaciones sin cubrir, seis archivos concretos de tooling/configuración
suman **532 generales y 98 nuevas**. Los helpers `prepare-pdf-worker` y
`publish-build` se ejecutan como CLI fuera de V8 y no tienen hits; tampoco se
pueden dar por probadas sus ramas negativas. Sus 426 observaciones generales
sin cubrir representan sólo **tres líneas nuevas**. Los otros 95 nuevos huecos
son merge de cobertura (78), builder AppImage (15) y Vite (2).
El tooling representa **3,34 %** de las 2934 observaciones nuevas sin cubrir;
no explica genéricamente la brecha restante. No se excluyen estos archivos.

## Verificaciones y experimentos

- **Python:** 2200 aprobadas en la integral, nueve optativas omitidas allí y
  aprobadas después con Mongo propio; cinco regresiones de confirmación y dos de
  límites añadidas después: **2216 pruebas distintas aprobadas, cero fallidas**.
  Las ejecuciones focalizadas repetidas no se suman. Los cincuenta casos del ZIP
  privado están incluidos, sin sustitutos inventados. Las 53 omisiones iniciales
  de la auditoría antigua fueron 50 por ese ZIP ausente y tres optativas de aquel
  corte; las nueve optativas actuales son otro conjunto recuperado y ejecutado.
  ZIP disponible: `~/.local/share/mathmongo/backups/mathkb_export_20260712_073927.zip`.
- **Frontend:** **348 pruebas / 45 archivos, cero fallos**. Antes del lote: 297.
  Incluyen metadata parcial, fechas, orden, reintento exacto, borrador, cuota,
  límite de páginas, error HTTP y respuesta tardía. Se mantienen las pruebas
  existentes del editor, exportaciones y borrado de compatibilidad.
- **Matchaio:** 31 pruebas en una copia temporal, seis archivos; no se incluyen
  en las cifras de MathMongo ni en su cobertura.
- **Navegadores:** nueve cohortes por navegador tanto desde código fuente como
  desde la AppImage, **36 cohortes aprobadas**, además del ensayo A–H focalizado.
  Chrome y Firefox reales, sin Streamlit; tamaños 1440×1080 y 480×900, zoom 100 %,
  foco de teclado real, fuentes MathLive y fórmulas renderizadas.
- **Herramientas:** TypeScript, ESLint y Ruff focalizado aprobados. Los avisos
  Starlette/TestClient sobre httpx quedan registrados, sin una actualización
  masiva de dependencias ajena al alcance.

| Experimento | Comportamiento comprobado en ambos navegadores |
|---|---|
| A | Matriz 3×2 configurable → LaTeX `bmatrix`; dimensión 9 rechazada sin mutación |
| B | Seleccionar `b` en `a+b+c` → `a+\sqrt{b}+c`; fracción, índices, sumatorio, norma, deshacer/rehacer y flecha de teclado |
| C | `ClipboardEvent` con LaTeX sobre el receptor real de MathLive → selección y envoltura con norma |
| D | TikZ y entorno desconocido protegido ya presentes → insertar integral → fuente protegida idéntica |
| E | Copia histórica real → cambiar una sola fórmula en modo fuente → igualdad exacta del resto |
| F | Fuente ↔ visual repetidos → cuerpo completo idéntico |
| G | Guardado Mongo real y recarga → mismo cuerpo canónico; conflictos/replays probados por separado |
| H | PDF con plantillas reales → cabecera PDF válida, texto extraído correcto y comprobación visual |

El pegado automatizado no toca el portapapeles del escritorio. Chrome conserva
los datos del constructor `ClipboardEvent`; Firefox los descarta para eventos
sintéticos. El harness proporciona el `DataTransfer` al evento en Firefox y
registra ese hecho: sigue ejecutándose el handler real de MathLive, sin simular
el editor ni el backend. No se presenta como prueba de permisos del portapapeles
del sistema operativo. Tampoco se atribuye esa diferencia del harness al producto.

Ejemplos generados y comprobados:

```latex
\begin{bmatrix}0&0\\0&0\\0&0\end{bmatrix}
a+\sqrt{b}+c
\frac{a_{i}+\sqrt{b}}{1+x^2}+\sum_{n=1}^3n
```

Las cinco copias históricas abarcan macros, TikZ/PGFPlots y entornos semánticos.
Las cohortes no-op comprueban los cuerpos exactos; la prueba E es una edición
intencional posterior en Mongo temporal. No se declara que MathLive pueda editar
visualmente todo TeX. Se mantienen `concept`, `definition`, `remark`, `reference`,
macros desconocidas y bloques protegidos, los ocho tipos y sus alias/colores.
No se modifica `miestilo.sty` ni la exportación original para adaptar el navegador.

### Evidencias locales

Bajo `evidence/sonar/cornell-cpi-2026-11-24/`:

- `quality-final.log`, `confirmation.log`, `limits.log`, `coverage-closure.log`:
  resultados Python y frontend; `structured-branches-confirmed.log` mide ramas.
- `validated-{chrome,firefox}.log`: nueve cohortes fuente completas.
- `package-validated-{chrome,firefox}.log`: nueve cohortes empaquetadas y reinicio.
- `full-{source,packaged}-{chrome,firefox}/`: manifiestos del recorrido completo,
  conservados antes de ensayos focalizados. Cada resultado tiene run_id y revisión.
  Fuente usa harness `098cab43`; paquete usa harness `301c8677` sobre la imagen
  de producción `098cab43`. El SHA del harness no se confunde con el del payload.
- `paste-final-{chrome,firefox}.log` y `paste-source-{chrome,firefox}/`: C/D
  reforzados, cinco no-op históricos y edición de una fórmula.
- `paste-packaged-{chrome,firefox}.log` y `paste-packaged-{chrome,firefox}/`:
  mismo ensayo contra la imagen final; se conserva por separado del recorrido
  completo de cinco notas tras reiniciar.
- `citation-before.log` y `citation-after.log`: dos regresiones antes/después
  para evitar anuncio de cita insertada en una región que ya cambió.

Capturas reales: `evidence/sonar/independent-study/chrome/` contiene
`structured-cornell-visual-math-tikz.png`, `structured-cpi-visual-math-tikz.png`,
`structured-{cornell,cpi}-saved-recovered.png`, sus variantes estrechas,
`math-tools-matrix-nested-tikz.png` y `math-tools-palette-narrow.png`.
Las mismas operaciones se capturan en Firefox y en `packaged-study`.
PDF comprobados: `cornell-classic.pdf`, `cpi-hybrid.pdf`, `math-tools.pdf`.
La última página mixta fue rasterizada e inspeccionada en
`cornell-cpi-2026-11-24/math-tools-final-pdf.png`: norma, matriz, integral, TikZ
y texto protegido aparecen sin pérdida.
Las capturas son del producto ejecutándose, no maquetas. Las evidencias y datos
privados no se añaden a Git; los resúmenes sin credenciales sí se versionan.

## AppImage y arranque

Artefacto final: `dist/MathMongo-098cab43-experimental-x86_64.AppImage`,
**39 873 016 bytes**, SHA256
`6779d1a5f73655231b5dddf49ef7ed83b5a8a1ee7bf48aaafd768f3e5a5a8631`.
Frente al inicial `f00aa5ac`: **+77 824 bytes (0,20 %)**; original conservado,
SHA256 `ec8ca4cfacb9a605fbaab4713a0439a550d7236619e322de19d18f99fd472e05`.
Cero dependencias nuevas, mismas diecinueve distribuciones Python.
No se atribuye todo el incremento a las herramientas matemáticas: incluye Cornell/CPI.

```bash
dist/MathMongo-098cab43-experimental-x86_64.AppImage \
  --appimage-extract-and-run --port 8766 --database mathmongo_prueba_personal
```

Abrir `http://127.0.0.1:8766/study`. La base explícita del ejemplo es distinta de
MathV0; el arranque manual necesita MongoDB ya accesible. Alternativa desde fuente:

```bash
.venv/bin/python -m mathmongo.advanced_reader \
  --host 127.0.0.1 --port 8766 --database mathmongo_prueba_personal
```

La validación empaquetada arranca desde un directorio temporal ajeno al repo,
sin PYTHONPATH/venv/Streamlit; obtiene `streamlit_available=false` del propio
`--bundle-check`. Tras nueve cohortes se detiene sólo el grupo del backend propio,
se lanza otro PID y se recuperan **cinco notas**. El hash de todas las colecciones
coincide antes/después, en ambos navegadores. El mongod y sus recursos también
pertenecen al test. La imagen no se presenta como autónoma ni estable; MongoDB,
navegador, herramientas y paquetes LaTeX del anfitrión siguen siendo necesarios.

## Commits, arquitectura y siguiente lote

La relación completa SHA/asunto está en `code_commits` del JSON. Hitos verificables:

| Alcance / commit | Regresión o verificación |
|---|---|
| `0707405c` persistencia estructurada | Cuatro fallos previos; no-op exacto y carrera CAS con Mongo real |
| `4d31109e` bundle Cornell | PDF portátil que antes fallaba por `lineas.png` |
| `ec057832` dominio/HTTP/layout | Reintento, metadatos opacos, medios compartidos y overflow aislado |
| `c0dbeb22`, `811d112e` Cornell/CPI React | Región, borrador, orden histórico y recuperación tras recargar |
| `697c9eb8` auditoría Matchaio | Revisión sin cambios y 31 pruebas aisladas |
| `cc4d08fc` MathLive | Fallo previo `replaceAll`; selección, historial, paleta y matrices |
| `d7a411e0` calidad | Botón submit explícito; S9011 corregido sin supresión |
| `31d99bc9` citas asíncronas | Región/página/contexto correctos; sin falsos mensajes de inserción |
| `914fdf66`, `9814f890` cobertura | Confirmación tardía, exportación fallida, errores y recuperación |
| `ca06a6bc`, `301c8677` AppImage | Reinicio propio y evidencia runtime obtenida del paquete real |
| `098cab43` publicación | Bundle de producción usado por la AppImage y los recorridos completos |
| `0e08a639` ensayo LaTeX | Pegado por handler real y estructura insertada con TikZ ya presente |

Contabilidad de código entre `278b420c` y `9814f890`: mantenido **+2154/−29**,
pruebas **+2494/−3**, generado **+61 218/−61 072**. El último ensayo añade
**54/−4** exclusivamente en el harness, sin cambiar el producto. No hay ficheros
mantenidos eliminados, capacidades retiradas ni traslados ocultos. Las líneas
reemplazadas de contratos/plantillas no se presentan como código obsoleto
eliminado. Los assets se cuentan aparte por hash/publicación.

Se añadieron responsabilidades coherentes de persistencia, dominio/adaptador HTTP,
medición TeX, estado y presentación regional; no un segundo editor ni guardado.
El coordinador React nuevo mide 447 líneas y concentra la orquestación del flujo;
se mantiene bajo revisión en lugar de declararlo perfecto por pasar el Gate.
Los veinte archivos propios >1000 líneas conservan sus revisiones previas por
hash; tabla y decisiones en `LARGE_FILES.md`, inventario en el JSON. La entrada
ya medía 21 líneas al comenzar y conserva 21: esta entrega no se atribuye una
reducción hecha antes. Ningún módulo nuevo de producción supera mil líneas.

**Próximo lote delimitado:** medios/asociaciones Cornell/CPI y operación de
borrado/duplicación de nota completa mediante servicios canónicos, con regresiones
de recursos compartidos y compensación antes de exponer controles. Después,
Worklog/Backlog/Weekly/Deliverables y promociones según la matriz histórica.
En paralelo: déficit de pruebas del coordinador y contratos de riesgo pendientes
antes de avanzar a helpers de construcción. No rebajar la aceptación interna del
95 % ni cerrar la mantenibilidad por el Gate oficial. No retirar todavía Streamlit.

[PARITY_V014.md](PARITY_V014.md) distingue capacidad implementada, comprobada sin
Streamlit y todavía no lista para retirar. La secuencia de regeneración/análisis
con referencia constante está en [REPEAT_REACT_ANALYSIS.md](REPEAT_REACT_ANALYSIS.md).

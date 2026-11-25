# Comparación observada y migración de Cuaderno — 24 de noviembre de 2026

Se continúa en `feature/knowledge-sphere-2026-11` desde **07ebdd52**, inicialmente
limpio. Se conservaron los commits y la extracción de compatibilidad; la entrada
`editor/editor_streamlit.py` continúa en **21 líneas**. No push, merge, nuevas
AppImages ni funciones nuevas de la esfera. Este checkpoint **no cierra la
migración completa**: la matriz vigente acredita **124/277 operaciones**, frente
a 110/277 al abrir el lote. Conserva 68 parciales, 1 implementada sin prueba y
84 ausentes; esenciales 119/215. No se cuentan menús como operaciones terminadas.

## Instancias y equivalencia

Las instancias del usuario se identificaron, sin detenerlas:

| Aplicación | URL | PID inicial | Comando/configuración comprobados |
|---|---|---:|---|
| Streamlit | http://127.0.0.1:8501 | 12165 | `mathdbmongo/bin/python -m streamlit run editor/editor_streamlit.py --server.address 127.0.0.1 --server.port 8501`; MathV0 |
| React/FastAPI | http://127.0.0.1:8766/study | 12152 | `mathdbmongo/bin/python -m mathmongo.advanced_reader --host 127.0.0.1 --port 8766 --database MathV0 --log-level info` |

Sus procesos anteriores no recargan automáticamente Python. La publicación
actualiza los archivos estáticos compartidos, pero no convierte ese backend
antiguo en el backend nuevo. La negociación `capabilities` evita peticiones a
operaciones nuevas que esa instancia todavía no ofrece. **No se declara que
8766 ejecuta los servicios nuevos.** Para observar el recorrido completo actual
se usaron dos instancias propias, que permanecen accesibles para revisión:

- React actual: **http://127.0.0.1:56385/study**.
- Streamlit de comparación: **http://127.0.0.1:35301**.

`evidence/sonar/cpi-five-images-2026-11-24/owned-comparison.json` registra PID,
inicio del proceso, puerto, comando, entorno XDG, Mongo y rutas de recursos.
El mongod propio escucha en loopback/puerto aleatorio y tiene dbpath bajo `/tmp`.
Se copió una selección equivalente de registros auténticos, conservando IDs y
bytes multimedia en dos árboles separados: no es una copia íntegra de MathV0.
Los nuevos registros de prueba se identifican como «Comparación». Se comprueba
el PID real del mongod antes de escribir; no hay fallback a 27017. Los originales
sólo se leen. Abrir vistas no aplica mantenimiento silencioso.

Las capturas comparativas usan ventana **1440×1000**, mismo caso y zoom. Firefox
100 % tiene DPR 1; al 70 % nativo Firefox informa DPR 0,697674 e innerWidth 2064
por redondeo del navegador. Se usó un perfil temporal propio y teclado; no se
modificó el perfil del usuario. Las primeras capturas CPI denominadas «70» usaban
emulación CSS y están identificadas como tal; **no acreditan zoom nativo**.
La comparación final de las tres pantallas utiliza `screens-*-firefox-{100,70}`.
El vídeo aportado se examinó: en su fotograma de 3 s Firefox muestra **80 %**.

## Menú real y correspondencia

Se grabó el desplegable real, sus veinte destinos y los seis subapartados de
Cuaderno; después se abrieron los otros diecisiete destinos históricos. Los
formularios y controles observados quedan en capturas y snapshots accesibles.
Abrir una pantalla sólo acredita inspección, no una escritura o exportación.

| Destino Streamlit | Acceso visible React | Estado y diferencia concreta |
|---|---|---|
| Inicio | Estudio → Inicio | Resumen real acotado, borradores y accesos. Se mantiene el contexto activo; no equivale a toda la administración histórica. |
| Cuaderno | Cuaderno → Cuaderno; actividades en menú y barra propia | Antes sólo abría Diario. Se añaden cuatro actividades persistentes y Kanban; permanecen pendientes específicos abajo. |
| Cornell | Cuaderno → Cornell | Reubicada, antes poco visible dentro de Diario. Acceso directo y editor existente conservados. |
| CPI | Cuaderno → CPI | Acceso directo; recursos y exportación corregidos sobre el caso auténtico. |
| Add Source | Administración → Añadir fuente; Biblioteca → Añadir fuente | Creación existente, recorrido funcional reutilizado. |
| Edit Source | Biblioteca → ficha/lista → Editar o Abrir fuente | Edición existente. El enlace contextual abre ahora la sección correcta. |
| Reading Space | Biblioteca → fuente → Documentos → abrir documento | Reubicada; lector/notas/pasajes conservan sus servicios. Falta un catálogo global de documentos equivalente. |
| Documentos | Estudio → Documentos y lectura → fuente → Documentos | Acceso reconocible al flujo existente. Listado global y algunas operaciones históricas aún parciales. |
| Nuevo concepto | Conocimiento → Nuevo concepto | Editor existente; no se reconstruye. |
| Editar concepto | Conocimiento → Conceptos → concepto → Editar concepto | Recorrido Campos comprobado; mantiene la identidad histórica. |
| Conceptos | Conocimiento → Conceptos | Búsqueda, lectura y acciones existentes; contexto lateral opcional. |
| Relaciones | Conocimiento → Relaciones, o concepto → contexto/relaciones | Reubicadas en espacios/contexto; el gestor global histórico no tiene paridad completa. |
| Grafo de conocimiento | Conocimiento → Espacios | Grafo existente conservado. No se añadieron proyección ni gestos nuevos. |
| Habitación de estudio | Conocimiento → Espacios | Reubicada parcialmente; no se afirma equivalencia de todas las operaciones históricas. |
| Exportar | Conocimiento → Exportar conceptos; selección o lectura → TEX/PDF | Exportación actual operativa. Constructor completo, Quarto y opciones masivas siguen en inventario. |
| Exportar base | Sin acción React equivalente completa | No migrada; no se añade un enlace vacío. |
| Importar base | Sin acción React equivalente completa | No migrada; se conservan preflight, autorizaciones y servicios históricos. |
| Mantenimiento | Ajustes/Diagnóstico sólo cubren preparación acotada | Parcial: no sustituyen limpieza, reparación, migración ni mantenimiento general. |
| Configuración | Administración → Ajustes | Tema y preferencias operativos; administrador de conexiones/cambio de base pendientes. |
| Diagnóstico | Administración → Diagnóstico | Abre la sección secundaria de Ajustes. El diagnóstico técnico completo histórico sigue parcial. |
| Base activa / conexiones (barra lateral) | Contexto activo visible → Ajustes | La base configurada se muestra. React todavía no permite cambiarla ni gestionar perfiles: no se da por migrado por mostrar su nombre. |

Clips: `menus-before/streamlit-menu.webm` (menú completo, ~1 s),
`menus-before/react-menu.webm` (siete accesos anteriores),
`notebook-after-{chrome,firefox}/menu.webm` (grupos y accesos actuales).
Los demás destinos se conservan en `historical-destinations/*.webm` y su
`destinations.json`, sin ejecutar importación o reparación para fotografiarlas.

## Cuaderno: operaciones y límites

| Actividad | Implementado y comprobado desde el menú | Pendientes que impiden declarar paridad completa |
|---|---|---|
| Worklog | Crear, recuperar, editar fecha/bloque/horas/estado/proyecto/evidencia, búsqueda básica y selección CSV | Fechas/filtros avanzados, borrado contextual, crear desde Backlog, CSV de consulta completa entre páginas |
| Backlog | Crear, editar, recuperar, prioridad/estado/responsable/estimación/fecha objetivo/etiquetas, selección CSV | Filtros avanzados y CSV de consulta completa. La supuesta eliminación histórica requiere corregir su fundamento en la matriz. |
| Weekly Review | Semana ISO válida, cuatro reflexiones, recuperación/edición, métricas recalculadas, overrides separados, selección CSV | Borrado, limpiar/descartar borrador válido, desgloses y controles históricos secundarios |
| Deliverables | Crear, editar, recuperar y selección CSV; conservar vínculos y commits ajenos | Gestionar asociaciones Worklog/Diario desde UI, filtro por tipo y consulta CSV completa; fundamento de borrado histórico |
| Kanban | Mismo Backlog, cambio de estado explícito, recarga y conservación de done_at | Historial visible y prueba de todos los filtros/páginas |
| Diario → Nueva nota / Buscar | Editor y guardado existentes; filtros compartidos extraídos del Streamlit actual | Metadatos/editoriales completos, medios y otras filas pendientes |
| Diario → Timeline | Acceso y lista ordenada por fecha | Agrupación y controles de timeline históricos |
| Diario → Calendario | Acceso y filtros año/mes | Cuadrícula y navegación por día |
| Diario → Proyectos | Acceso y filtro por proyecto | Resúmenes agregados y gestión completa de proyectos |
| Diario → Exportar | Cada entrada conserva TEX/PDF del editor existente | Exportación conjunta y opciones editoriales masivas |
| Diario → Promover | Identificado explícitamente como pendiente | Selección de fragmento, metadatos, concepto y procedencia histórica; no se sustituye por crear un concepto sin trazabilidad |

Los modelos y colecciones históricos se conservan. No se genera UI a partir de
registros Mongo arbitrarios: hay cuatro contratos de campos explícitos. Se
reutilizan guardas HTTP, borradores por biblioteca, reloj UTC, digest BSON y CAS.
Una sola lectura proporciona revisión/transición y predicado de escritura; los
campos desconocidos y vínculos se conservan. Creaciones con UUID toleran respuestas
perdidas; revisiones nuevas usan identidad de semana estable sin transacciones,
compatible con MongoDB standalone. Cambiar una tarea Done no mueve done_at;
reabrirla lo limpia. Editar notas de un entregable no elimina commits adicionales.
Guardar una revisión recalcula horas/tareas, sin mezclar métricas manuales.

Los formularios no ofrecen borrados nuevos sin completar sus contratos y
confirmaciones. La inspección de los formularios/callbacks de Backlog/Deliverables
en ambas versiones no acredita el borrado supuesto en el inventario inicial.
La duda queda visible, con IDs y denominador conservados; no se inventa un flujo
histórico ni se elimina código para mejorar el porcentaje.

### Vídeo revisado y resultado

Los clips de cada actividad duran aproximadamente 3–6 s y guardan eventos con
marcas precisas en `browser.json`. Son automatizados; las capturas estáticas
permiten leer cada estado sin depender de la velocidad del clip.

- `menus-before/streamlit-diario.webm`, **8,9 s**: Promover muestra la selección
  de nota y su contexto. Se cotejó su fotograma: una lista React no lo sustituye.
- `notebook-after-chrome/backlog.webm`, aproximadamente **1,5 s**: fallo de red
  deliberado; contenido conservado, aviso de reintento, ningún éxito anunciado.
  El reintento crea un único registro real, que se vuelve a abrir al recargar.
- `notebook-after-firefox/weekly.webm`, aproximadamente **2,4 s**: revisión
  recuperada, métricas automáticas separadas, campos persistidos y semana fijada.
- `notebook-after-{chrome,firefox}/{worklog,backlog,weekly,deliverables}.webm`:
  creación → recarga → edición → segunda recarga → CSV del registro exacto.
- `notebook-after-{chrome,firefox}/kanban.webm`: el cambio Done persiste tras
  recargar y sigue correspondiendo al mismo Backlog.

Se examinaron fotogramas extraídos con ffmpeg, no sólo resultados de código:
`review-{diary-promote,backlog-failure,weekly-saved,maintenance}.png`.
Las marcas exactas de una repetición pueden variar; manda su `browser.json`.

## Inicio, Biblioteca y Campos

| Pantalla | Antes y después (misma ventana/caso) | Conservación y mejora |
|---|---|---|
| Inicio | `screens-before/after-firefox-{100,70}/react-home.png`; `streamlit-home.png` | Contexto y accesos; añade consultas reales de resúmenes y borradores existentes sin cargar todos los cuerpos LaTeX. Fallo de permisos no aparece como cero actividad. |
| Biblioteca | `react-library.png`, `react-library-compact.png`, `streamlit-library.png` | Fichas/lista usan mismos registros y acciones. Título bibliográfico prioritario, nombre histórico secundario, autores/año reales cuando existen. Conserva búsqueda/tipo/estado/paginación y añade selección/detalle. |
| Campos | `react-campos.png`, `react-campos-clean.png`, `streamlit-campos.png` | Título/acciones/contenido agrupados, lectura de fórmulas y contexto ocultable/ajustable, referencia histórica conservada. MathLive usa read-only real; el editor mantiene sus controles. |

Las rutas de los directorios son `screens-before-firefox-100`, etc. Las vistas
y paneles se conservan después de recargar mediante preferencias de presentación
separadas de los borradores. Se reutilizan React 19, CSS existente y componentes
propios; no se añadió una biblioteca de UI. Tema oscuro original por defecto;
claro opcional usa neutrales y acentos adaptados conservando las ocho familias
matemáticas y los colores LaTeX de exportación.

Campos se abrió desde el menú, se editó únicamente el comentario de la copia,
se guardó, recargó y se descargaron TEX/PDF en ambos navegadores. Su LaTeX antes y
después conserva SHA **847e7a78821b4cc6e4a9edffb6e70a9b7197c22760b6f443a77ae069c41492e2**;
la referencia e identidad también permanecen. Evidencia: `campos-{chrome,firefox}`.
Los intentos que guardaron antes de esperar la inspección de preparación fueron
rechazados y conservaron el borrador; el recorrido correcto espera ese resultado
y usa Preparar biblioteca, sólo en la copia temporal compatible.

Patrones concretos consultados: [Zotero 7](https://www.zotero.org/blog/zotero-7/)
para detalle con secciones replegables/densidad; [Paperpile](https://paperpile.com/h/view-navigate-library/)
para lista bibliográfica y selección; [Obsidian](https://obsidian.md/help/tabs)
para continuidad entre paneles; [sidebar](https://ui.shadcn.com/blocks/sidebar) y
[paneles ajustables](https://ui.shadcn.com/docs/components/base/resizable)
para grupos y ajuste accesible. Se implementaron sobre la base existente.

## CPI y expresividad LaTeX

[CPI_RESOURCE_CHECKPOINT.md](CPI_RESOURCE_CHECKPOINT.md) documenta causa,
regresión antes/después, recursos auténticos y staging. `after-{chrome,firefox}`
contiene nuevas descargas tras guardar/recargar, con cinco imágenes y marca de
agua; sus seis píxeles fuente y cinco leyendas se cotejan en
`pdf-verification.json`. `portable-recompiled.pdf/png` proviene exclusivamente del
ZIP descargado y el compilador aislado, sin rutas originales. La revisión visual
comprueba proporciones, leyendas, distribución y marca de agua; no sólo un conteo.

Las catorce cohortes mantienen creación visual → LaTeX/PDF; cinco históricos
sin cambios con fuente exacta; documentos mixtos/TikZ; diez construcciones
complejas; recuperación fría; clones; recursos compartidos y errores de borrado.
No se sustituyó LaTeX canónico por HTML ni se normalizaron macros desconocidas.

## Verificación y calidad

La batería final dio **2256 aprobadas, 9 omitidas, 0 fallidas**, en 411,31 s.
Las nueve omitidas son integraciones optativas con mongod: seis regresiones de
rollback/recursos/exportación, actualización de base, ciclo de base nueva y
vínculo histórico. Se ejecutaron aparte: **9 aprobadas**. Total de pruebas Python
distintas aprobadas: **2265**. Los casos que requieren el ZIP privado ya se
resuelven; no son estas nueve omisiones.

Frontend: **406 pruebas aprobadas**, TypeScript y ESLint correctos; Ruff sin
avisos en los archivos nuevos/afectados comprobados. Pruebas focalizadas durante
el desarrollo; integral en checkpoints. El primer integral falló por una búsqueda
`023` que coincidía también con un UUID aleatorio. Se cambió sólo la consulta del
test al título completo; no se cambió el buscador. El primer retest E2E asumía
un nombre fijo de imagen en ZIP: ahora coteja SHA y la referencia real de main.tex,
conservando la verificación del recurso y PDF. Los fallos previos quedan en logs.

**Catorce cohortes funcionales por navegador**, sin Streamlit. Las nuevas
actividades se verifican además con clips y Mongo temporal en Chrome y Firefox.
V8 sólo se recoge de Chrome. El merge verifica hash de JS observado/publicado/
mapeado y fuente original; conserva el denominador de Vitest y compatibilidad de
ramas. No se acredita cobertura de casos fallidos ni de bundles anteriores.
Python combina el integral con ejecuciones aprobadas; se excluyen expresamente
los dos archivos del runner Chrome fallido (`python-coverage-provenance.json`).

El primer análisis procesado sobre `33c43042` fue
**861de980-45f8-45d5-9460-d5b7167bf5c4**: general **76,7 %**, nueva **81,9 %**,
Gate **ERROR** por **34 avisos nuevos** (32 aserciones fuera de un caso y dos
botones de formulario sin type explícito). Cobertura ≥80 y duplicación nueva
≤3 sí cumplían. Se corrigieron mediante casos `node:test` reales y botones
submit explícitos; no se cambiaron perfil, regla, exclusión, referencia ni umbral.
El análisis final del primer checkpoint, **36d724af-791c-47f4-9013-c7e7fe16bce8**,
revisión **6a950695**, terminó CE SUCCESS y Gate **OK**: general **76,7 %**, nueva
**81,9 %**, duplicación nueva **0,14448 %**, incidencias nuevas **0**. Las tres
condiciones originales cumplen. Frente a la referencia anterior 76,6/82,2, la
cobertura general sube 0,1 puntos y la nueva baja 0,3 al ampliar el alcance;
no se presenta el porcentaje como si el denominador fuese fijo.

Observaciones nuevas cubiertas **14953/18262**; condiciones nuevas **3167/4300**
y generales **3918/5509**. Faltan **2396** observaciones nuevas y **11348** generales
para 95 % a denominador fijo. XML Python local, con su alcance completo, mide
aproximadamente **72 %**; no es el mismo denominador de Sonar (56333 líneas y
5509 condiciones, incluyendo JS/TS). Vitest: 5514/7084 líneas y 3620/5509 ramas;
tras V8 compatible: **5872/7084 líneas y 3918/5509 ramas**, +358/+298 reales.
Desglose exacto por archivo: `sonar-coverage-breakdown.json/csv` en la evidencia.
Los mayores déficits incluyen knowledge_graph.py, canvas.ts y contratos heredados;
el Gate no sustituye el plan de cobertura ni el resto del inventario.

Referencia constante: PREVIOUS_VERSION **2026-11-21T16:46:16+0000**;
`sonar-project.properties` SHA
**84aec1246aae6a1a3949f786449faf9c19a10894cfcb044adcf81866f18f08a6**.
El objetivo 95 % permanece abierto: superar el Gate no lo sustituye. Se mantiene
el inventario general y la revisión de archivos grandes.

## Commits y continuación

- `878116ec`: recursos y exportación CPI/Cornell, galería y regresiones.
- `1b405639`: operaciones Cuaderno, modelos, persistencia y filtros compartidos.
- `6aaaaaab`: Inicio/Biblioteca/Campos, navegación, preferencias y publicación.
- `33c43042`: grabaciones reproducibles y regresiones de exportación/búsqueda.
- `ee275ee3`: corrección de los 34 avisos demostrados por el primer análisis.
- Documentación/matriz y análisis final: checkpoint posterior.

No se retiraron flujos, servicios ni datos históricos. Se trasladaron la
consulta pura de Diario y la responsabilidad de lectura del concepto; los
bundles de hash anterior se sustituyen por los de la compilación reproducible.
Las cifras físicas separan fuente mantenida, pruebas y salida generada; véase
la actualización de LARGE_FILES.md. No se interpreta el bundle como complejidad
eliminada. Los módulos extraídos también se contabilizan.

Prioridad siguiente: Promover con trazabilidad y exportación conjunta del Diario;
calendario/proyectos; completar filtros, asociaciones y borrados aplicables de
Cuaderno; administrador de conexiones/cambio de base; transferencias y
mantenimiento con sus autorizaciones. Permanecen también filas de medios,
constructor, relaciones y exportaciones del resto del repositorio. No se elimina
Streamlit mientras existan esas dependencias.

## Anexo recibido durante el cierre: nuevo lote en curso

El usuario añadió dos casos antes de la entrega: Diario
`6a81d4fb010f2a0daff07fb5` y Cornell `6a4d7d2b467f981c3741eb8c`.
Se preserva el checkpoint anterior, pero su Gate **no acredita código posterior**.
El lote adicional conserva la fuente y los recursos de las dos notas en copias
coherentes. El diagnóstico inicial demuestra auxiliares bloqueados por el sandbox
(`main.lof`, después `main.lot` y `main.listing`), no un fallo de la fuente LaTeX.
Esta entrada sí utiliza sus 33 imágenes: 13 capturefig y 10 capturepair. Cornell
almacena cue/main/summary; la UI previa alternaba una única superficie. El lote
recupera tres editores simultáneos sin cambiar el modelo. La entrega y análisis
posteriores deben incluir sus regresiones y evidencias específicas.

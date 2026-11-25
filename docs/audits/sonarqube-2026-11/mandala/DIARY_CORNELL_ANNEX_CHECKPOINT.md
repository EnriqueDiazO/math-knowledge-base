# Diario y Cornell: incidencias auténticas y cierre del lote

Continuación del [checkpoint de navegación](NAVIGATION_COMPARISON_CHECKPOINT.md),
sin reiniciar la migración. Rama `feature/knowledge-sphere-2026-11`; se conservan
los commits anteriores y los procesos del usuario en 8501/8766. Sin push/merge,
AppImages nuevas ni exploraciones nuevas de la esfera.

## Contextos y revisiones

Las escrituras se realizan exclusivamente en MongoDB propio, puerto 43037,
PID/dbpath verificados, bases y directorios de medios independientes:

- React: `mathmongo_cpi_react_3936f6a0580f4b298ac255a6b9b09d33`, puerto 56385.
- Streamlit: `mathmongo_cpi_streamlit_8cbf1be677bc4c28a3b6b2e2b91f4421`, puerto 35301.

Se clonaron las dos notas y sus recursos conservando identidades, campos y rutas
lógicas. Las rutas físicas sólo cambian de raíz XDG. El primer clon convirtió
las rutas lógicas relativas de las imágenes del Diario en absolutas: eso causó
una referencia doble `media/images/images/` propia del fixture. Se corrigió la
copia para reproducir el registro real; no se cambió el exportador para ocultar
ese error de preparación del ensayo.

Se levantó además el backend actual sobre MathV0 en **http://127.0.0.1:8768**.
El proceso anterior 8766 sigue funcionando: comparte los estáticos publicados,
pero su Python cargado no incorpora automáticamente las correcciones. En 8768
se hicieron únicamente GET y exportaciones del Diario, más lectura de Cornell.
No se prepararon índices, guardaron notas ni ejecutaron pruebas con escritura
sobre MathV0. Las huellas BSON finales de ambas notas coinciden íntegramente con
las iniciales (`original-annex-records-unchanged.json`).

| Caso | Identidad | Revisión BSON original |
| --- | --- | --- |
| Diario | `6a81d4fb010f2a0daff07fb5` | `f2619be0c49f47c64e44c07c4db5b601c149a25fae5ad03650f68385665bf02c` |
| Cornell | `6a4d7d2b467f981c3741eb8c` | `e8c1c0c16c37ff4c438c84afbd5a0454ab19a6fac971de630ae593e57bfad659` |

Los registros privados, TEX, PDF, medios, logs y vídeos están bajo
`evidence/sonar/cpi-five-images-2026-11-24/`, excluido de Git. Las notas completas
no se incorporan al código versionado. Los resultados del ensayo identifican
sus revisiones modificadas de comparación en `browser.json`.

## A. Diario: causa y corrección

La entrada «Instalación de R e IRkernel en Windows: JupyterLab y rehash de
pyenv-win» tiene LaTeX libre, sin formato Cornell/CPI. El botón exporta la
versión guardada; no publica ni sustituye un borrador. Su cuerpo canónico tiene
SHA256 `379bdeef015811e5222b5abbf1fcedc1f721ba639293d60b7270277351b2283d`.

El primer fallo real es **`/inputs/main.tex:80: I can't write on file main.lof`**,
al ejecutar `\listoffigures`. El aislamiento permitía seis nombres auxiliares,
pero no `.lof`, `.lot` ni `.listing`. Después de habilitar los dos primeros,
el entorno válido `algoritmo`, de tcolorbox, necesitaba `main.listing` en la
línea 364. No era un error en la fuente ni la falta de una imagen. Se amplió la
lista exacta a esos tres archivos, conservando bubblewrap, entradas de sólo
lectura, ausencia de red, `-no-shell-escape`, límites de recursos y máximo de
pasadas. No se habilitó escritura arbitraria en directorios.

Hay **33 asociaciones, 33 recursos disponibles y 33 imágenes referenciadas**:
13 llamadas `\capturefig` y diez `\capturepair`. Buscar sólo `\includegraphics`
habría omitido las macros reales. Se verificaron bytes en el ZIP y píxeles RGB
extraídos del PDF frente a los originales. El PDF resultante tiene **46 páginas**.
La exportación nativa de Streamlit de esta misma copia también tiene 46 páginas
y su texto normalizado coincide con el generado por React. Se revisaron páginas
1, 8, 15, 30 y 46; el proyecto descargado recompila en un directorio limpio.

El aviso previo prometía detalles que no se exponían por HTTP. Ahora el resultado
del compilador conserva su log, el adaptador HTTP transmite el diagnóstico y
`ExportActions` permite abrir **Detalles de compilación** y descargar el registro.
Un caso fallido deliberado, exclusivamente temporal, verifica el aviso y la
descarga sin anunciar un PDF inexistente. La respuesta sigue siendo error 422.

Archivos: `exporters_latex/sandbox.py`, `mathmongo/study/notebook_routes.py`,
`structured_routes.py`, errores/esquemas HTTP y
`frontend/advanced-reader/src/study/ExportActions.tsx`, `api.ts`,
`export-actions.css`. La revisión `dfcd2a54` agrupa la corrección y regresiones.

Evidencia local:

- `diary-ui-before-chrome/`: clic real de 8766, 422 y detalles ausentes.
- `diary-annex-reproduced-before/`: TEX, recursos y primer error bajo la lista
  original de auxiliares, reproducida sin restablecer código ni datos.
- `diary-ui-after-{chrome,firefox}/`: PDF, recarga sin cambios, segundo PDF y ZIP.
- `diary-ui-actual-chrome/`: el mismo recorrido de sólo exportación sobre MathV0
  en 8768; revisión guardada idéntica antes/después.
- `diary-artifact-verification.json`, `diary-native-react-text.json`,
  `diary-portable-compile.log` y `diary-visible-diagnostics.png`.
- Entregables: `diary-ui-actual-chrome/Diario-1.pdf` y `Diario.zip`.

La exportación CPI compartida volvió a pasar después del cambio de aislamiento;
se preserva la verificación previa de las cinco capturas y marca de agua. No se
reescribe su documento para satisfacer el ensayo del Diario.

## B. Cornell: tres regiones y edición independiente

El modelo ya contenía `cue`, `main`, `summary` dentro de cada página. Streamlit
los edita mediante Cue/Main/Summary LaTeX; la nota indicada conserva sus títulos
«Preguntas  principales», «Python: lenguaje, entorno y ecosistema para el análisis
de datos» y «Observaciones». React alternaba las tres regiones en **un único
editor** mediante un selector: no faltaban los datos, faltaba la presentación
simultánea solicitada. No se cambia el esquema ni se divide texto por heurísticas.

`CornellRegions.tsx` monta tres instancias del editor existente, con etiquetas
permanentes **Ideas y preguntas / Desarrollo / Síntesis** y sus títulos propios.
En escritorio cue/main comparten una fila y summary ocupa la siguiente; en
ventana estrecha se apilan. Cada instancia conserva contenido inicial, selección,
deshacer, foco, viewport y herramientas. `StructuredWorkspace` recoge las tres
instantáneas al guardar y conserva los campos no reconocidos del documento.
Cambiar la región activa no desmonta los editores.

Las citas se insertan en la selección del editor activo, también en código
fuente, en lugar de reconstruir todo el editor. Las cargas diferidas de
CodeMirror conservan la petición de foco; los otros dos editores no lo roban al
restaurarse. Una regresión adicional detectó que una cita y el cambio inmediato
de modo fuente podían agruparse en la historia: `closeHistory` delimita la cita
como una operación de deshacer independiente. La prueba verifica que deshacer
retira sólo la cita y conserva el texto corregido y la fracción; rehacer la repone.

Revisiones: **`f2508e71`**, tres editores, selección/código y regresiones;
**`ebeb7e1c`**, deshacer independiente, grabaciones con cobertura y publicación.
No se sustituye Tiptap/MathLive ni se introduce otro sistema de guardado.

Recorrido Chrome y Firefox sobre la copia de la nota:

1. Cargar los tres cuerpos históricos y añadir marcadores distintos.
2. Modificar sólo cue, guardar/recargar y comparar main/summary exactamente.
3. Repetir para main y después summary, verificando las otras regiones.
4. Insertar `\frac{a}{b}` y una referencia real del catálogo en Desarrollo;
   deshacer/rehacer la cita sin alterar fórmula ni las otras dos regiones.
5. Recargar un borrador local sin publicar: la revisión del backend permanece
   intacta. Guardarlo después explícitamente y volver a abrirlo.
6. Descargar PDF y TEX; verificar tres regiones, títulos, fórmula y cita;
   recompilar el ZIP en limpio. Comprobar apilado a 600 px.

Los marcadores de ensayo se construyen desde la captura original y se sustituyen
entre pasadas. Los primeros reintentos acumulaban párrafos de prueba y activaron
correctamente la protección contra recorte (escala 0,737, inferior a 0,8). Se
acotó el fixture; no se bajó la escala ni se retiró contenido histórico.

Evidencia local: `cornell-ui-before-chrome/` reproduce el único editor sobre la
revisión original; `cornell-native-same-note.*` registra los tres campos de
Streamlit; `cornell-current-original-*` compara React actual con el mismo
contenido sin guardar. `cornell-ui-after-{chrome,firefox}/` contiene vídeos,
capturas, revisiones, PDF, ZIP, recompilación y las comprobaciones independientes.
En el clip Chrome: cue 3,24 s, main 4,82 s, summary 6,45 s, fórmula/cita 8,58 s,
borrador 10,18 s, PDF 14,48 s, pantalla estrecha 15,26 s. Son tiempos aproximados
de los eventos registrados, no evidencia de operaciones no ejecutadas.

## Verificaciones, comparación Sonar y pendientes

Python integral: **2260 aprobadas, 9 omitidas, 0 fallidas**. Las nueve son las
integraciones optativas con MongoDB y se ejecutaron aparte: **9 aprobadas**;
total **2269 pruebas distintas aprobadas**. Las pruebas históricas del ZIP
privado ya están disponibles; estas omisiones no son las antiguas 50 del ZIP.
Frontend: **410 aprobadas**, TypeScript y ESLint sin errores. Catorce cohortes
por navegador en Chrome/Firefox, sin iniciar Streamlit; los ensayos comparativos
utilizan adicionalmente el Streamlit propio. Las pruebas de aislamiento de
LaTeX y los contratos HTTP del legado permanecen activas.

La matriz conserva **124/277 verificadas**: estas correcciones fortalecen casos
ya contabilizados y no añaden puntos por botones, regiones o repeticiones.
Se actualizan especialmente diary-13/14 y cornell-05/06/08/17/18 con regresiones
y evidencias. Permanecen parciales Timeline, Calendario y Proyectos; pendientes
Promover, exportación masiva, asociaciones/medios y controles administrativos.
El inventario completo sigue siendo la referencia; no se retira Streamlit.

Sonar final procesado: **`e54ea8aa-d49f-402b-a97f-8cb0d674e01a`**, revisión
**`ebeb7e1c4cf2ef6d9fa518b4272c83c7e29b0841`**, CE SUCCESS y **Gate OK**.
XML Python y LCOV se importaron sin errores (sensores y rutas registrados en
`evidence/sonar/annex-final-2026-11-25/sonar-scan.log`).

| Medida | Referencia anterior c1a29eb5 | Checkpoint 6a950695 | Anexo ebeb7e1c |
| --- | ---: | ---: | ---: |
| Cobertura general Sonar | 76,6 % | 76,7 % | **76,7 %** |
| Cobertura nueva Sonar | 82,2 % | 81,9 % | **82,0 %** |
| Observaciones nuevas cubiertas/total | — | 14953/18262 | **15059/18369** |
| Condiciones nuevas cubiertas/total | 2915/3898 | 3167/4300 | **3208/4342** |
| Incidencias nuevas | 0 | 0 | **0** |
| Gate | OK | OK | **OK** |

Condiciones exactas finales: cobertura nueva 82,0 ≥80; duplicación nueva
0,14202 ≤3 %; incidencias nuevas 0 ≤0. Los 189 registros históricos de incidencias
se conservan: 161 FIXED y 28 FALSE_POSITIVE anteriores, ninguna abierta. No se
introducen supresiones ni se reclasifican incidencias para aprobar este lote.

Se conserva la referencia PREVIOUS_VERSION
`2026-11-21T16:46:16+0000` y el SHA de configuración
`84aec1246aae6a1a3949f786449faf9c19a10894cfcb044adcf81866f18f08a6`.
El denominador aumenta 107 observaciones y se cubren 106 adicionales; no se
presentan los porcentajes como si el alcance fuese fijo. Quedan **3310**
observaciones nuevas sin cubrir; faltan **2392** para alcanzar el 95 % a
denominador fijo. En general faltan **11344**. El tooling (`scripts/` e `infra/`)
explica **44/3310, 1,33 %**, del déficit nuevo: no es su causa general.

| Archivo | Líneas nuevas cubiertas/total | Condiciones nuevas cubiertas/total | Observaciones nuevas sin cubrir |
| --- | ---: | ---: | ---: |
| `editor/app_pages/knowledge_graph.py` | 451/714 | 0/0 | 263 |
| `frontend/advanced-reader/src/knowledge-map/canvas.ts` | 368/433 | 168/242 | 139 |
| `frontend/advanced-reader/src/knowledge-map/component.ts` | 420/478 | 169/245 | 134 |
| `frontend/advanced-reader/src/knowledge-map/room.ts` | 407/461 | 142/195 | 107 |
| `editor/app_pages/concept_edit.py` | 265/366 | 0/0 | 101 |
| `editor/app_pages/concepts.py` | 67/161 | 0/0 | 94 |
| `frontend/advanced-reader/src/study/StudyApp.tsx` | 66/103 | 30/76 | 83 |
| `frontend/advanced-reader/src/knowledge-map/document-editor.ts` | 260/298 | 108/150 | 80 |

El componente nuevo CornellRegions alcanza 100 % en el alcance Sonar; quedan
ramas concretas en StructuredWorkspace (26 observaciones nuevas), ExportActions
(6), aislamiento (6) y source-loader (4). El desglose completo es
`evidence/sonar/annex-final-2026-11-25/sonar-coverage-breakdown.json/csv`.

La cobertura local Python es **36795/51560 líneas, 71,36 %**; Sonar incluye otro
alcance y las condiciones JS/TS. Vitest observa 5571/7137 líneas y 3664/5551 ramas.
El merge con **22 recorridos Chrome aprobados** (14 cohortes, seis actividades,
dos casos del anexo) aporta 353 líneas y 295 ramas reales: **5924/7137** y
**3959/5551**. Conserva denominadores e identidades AST de las ramas y coteja
fuentes/mapas/bundle publicado. Firefox comprueba comportamiento y no aporta V8.
Una recogida auxiliar terminó con SIGTERM después de publicar su resultado;
se repitió aisladamente y se utiliza sólo el reintento con salida 0. No se
combina cobertura de ejecuciones fallidas ni de fuentes anteriores.

La meta del 95 % permanece pendiente.
Comandos reproducibles: [REPEAT_REACT_ANALYSIS.md](REPEAT_REACT_ANALYSIS.md).

No se elimina código histórico, documentos, validaciones ni pruebas. La nueva
responsabilidad de presentar las regiones queda en CornellRegions; el punto de
entrada Streamlit conserva 21 líneas. Los bundles anteriores se sustituyen por
la salida reproducible de compilación y se contabilizan como generados.

Contabilidad del anexo `296c5e4c..ebeb7e1c`: fuente mantenida **+335/−33**, pruebas
**+762/−62**, salida generada **+3339/−3310** líneas físicas Git. Las bajas de
pruebas corresponden a adaptar los consumidores a tres editores y sustituir sus
consultas globales por la región activa; las aserciones de comportamiento se
conservan y amplían. CornellRegions suma 75 líneas y su CSS 53: ambos se cuentan.
No se atribuyen las bajas de bundles a simplificación del código mantenido.
De los veinte módulos propios de más de mil líneas, diecinueve conservan su hash
de 07ebdd52 y Cuaderno mantiene la extracción ya revisada; no crece ninguno en
este anexo (`annex-final-2026-11-25/repository-inventory.csv`). Se corrige además
el campo histórico previous_summary de la matriz recuperándolo de Git 07ebdd52:
había copiado el resumen actual 124 donde correspondía el anterior 110.

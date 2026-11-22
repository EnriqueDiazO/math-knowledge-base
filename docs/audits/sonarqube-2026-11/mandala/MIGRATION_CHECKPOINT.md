# Checkpoint de React independiente y de identidad visual

Se conserva `feature/knowledge-sphere-2026-11`, todos los commits anteriores y
la extracción de compatibilidad. No hay push ni merge. La aplicación principal
es React servido por el FastAPI existente. Este checkpoint no autoriza retirar
las funciones heredadas cuya paridad continúa pendiente.

## Arranque y primer recorrido

```bash
.venv/bin/python -m mathmongo.advanced_reader --port 8766
```

Abrir `http://127.0.0.1:8766/study`. Reutiliza la conexión configurada en el
backend; no inicia Streamlit ni envía credenciales Mongo al navegador. Si el
puerto está ocupado, elegir otro puerto local. La muestra visual está en
`/study/settings/appearance`.

**Verificado autónomamente:** Biblioteca → fuente → documento PDF → selección
de pasaje → editor visual amplio → borrador recuperable al recargar → nota
guardada → publicación explícita como concepto → esfera → concepto → mismo
pasaje/página PDF. Chrome y Firefox usan MongoDB standalone con PID, dbpath,
puertos y base propios, además de XDG temporal. Se conserva la nota después de
perder deliberadamente la primera respuesta HTTP; el reintento utiliza la misma
operación y sólo persiste una nota. Las fórmulas y el teclado MathLive funcionan
sin diálogo.

El runner exige 1 nota, 1 concepto, 1 anotación y 2 evidencias en el primer
recorrido. La fase visual añade después ocho conceptos temporales y comprueba
que su borrador no genera una segunda nota. Los procesos y datos temporales se
retiran al finalizar; no usa ni prepara MathV0. Las capturas de cada paso y los
resultados JSON se conservan en `evidence/sonar/independent-study/`.

## Correcciones y contratos comprobados

| Commit local | Cambio | Regresión / evidencia |
|---|---|---|
| `0a7ca8fb` | Una sola instantánea de contenido para revisión, `before_latex` y CAS de edición. Proyección de resúmenes sin leer todos los documentos LaTeX. | `test_study_edit_snapshot.py`: antes sobrescribía contenido concurrente; después devuelve parcial y lo conserva. `test_knowledge_map_summary.py`: cero lecturas a LaTeX en resumen, detalle íntegro a demanda. Logs before/after en `/tmp/study-concurrency-*.log`. |
| `b3c0090a`, `0f6b9920` | Biblioteca/contexto/notas/conceptos/operaciones HTTP sobre servicios existentes, preparación explícita, límites y errores comprensibles. | `test_study_http.py`: preparación sin cambios silenciosos, ámbito/revisión, rechazo de origen, JSON y tamaño, búsqueda bibliográfica previa a paginar, lectura exacta y operación idempotente. |
| `9a7c3f1d`, `da3ba3c0` | Shell React y rutas durables, editor amplio y borradores, publicación y regreso al PDF; distribución offline y carga diferida. | `study-workspace.test.tsx`, `document-page-surface.test.ts`, recorridos Chrome/Firefox. La comparación de hostname de MathLive es una excepción de inspección de destinos revisada, no una solicitud CDN permitida. |
| `259a11d0` | Un único borrado recuperable usado por Edición y Exploración. | `test_concept_deletion.py`, `test_concept_deletion_app.py`, `test_browse_deletion_contract.py`: dos sentidos de relación, evidencia/esferas como bloqueo, contexto y confirmación, fallos parciales y carreras. Reproducción anterior: `DELETION_BEFORE.json`. |
| `eb71c60a` | Entry de compatibilidad de 21 líneas; elimina bootstrap de ruta redundante y corrige un binding local. | Contratos de importación/contexto/dispatch. Conserva las veinte páginas extraídas y sus consumidores. |
| `da446f3d` | Edición heredada admite `tipo_aplicacion=None` de conceptos canónicos; no entrega None a multiselect. | `test_legacy_page_behaviors.py`: creación/duplicado, edición que conserva identidad y campos desconocidos; duplicar/renombrar/generar/importar mapas sin copiar conceptos. |
| `8a75b50a` | La prueba de empaquetado distingue la comparación de hostname revisada de un destino remoto real. | Diez contratos de empaquetado; prueba de destinos sigue rechazando URLs externas y variantes no revisadas. |
| `30e2f76e` | Observación se incorpora a los siete tipos admitidos por el contrato canónico. | Ocho casos de `test_mathematical_type_identity.py`: persistencia exacta, reintento y resumen. |
| `43aee63b`, `bdeec336` | Identidad xcolor centralizada, aliases, muestras, grupos de herramientas y superficies; corrección de LF involuntario al abrir MathLive. | `concept-types.test.ts`, muestra real y colores calculados en ambos navegadores. [VISUAL_IDENTITY.md](VISUAL_IDENTITY.md). |
| `0f83c1cb`, `73129f44`, `5d902eb7` | Recorrido visual y aserciones dentro de casos Node nombrados; búsqueda con submit explícito. | Sonar detectó 47 aserciones fuera de caso y un botón sin tipo; el análisis posterior los deja en cero, sin supresión ni cambio de reglas. |
| `1eb1f33f` | Imports ordenados y contratos documentados; dos regresiones del borrado desde la página Exploración real. | Lote afectado: 57 casos aprobados. Consumidores del router: 167 aprobados. Ruff no añade avisos nuevos en esos módulos. |
| `40e6538c`, `8dbd6234` | En estrecho, herramientas en una fila y guardado sin solapamiento; borde doble de Proposición con prioridad CSS correcta. | Chrome/Firefox exigen barra < 110 px y acciones después del editor; 58 px medidos en ambos. Se comprueba también el borde doble calculado. |

El borrado conserva Sources, References, notas, documentos y bytes de medios.
La evidencia intelectual o pertenencia explícita a una esfera bloquean el
borrado y ofrecen una salida concreta. Sólo retira relaciones BSON observadas;
una relación cambiada concurrentemente queda para revisión. Los medios pierden
exclusivamente la referencia al concepto borrado; no se aplica una purga de
archivos. El registro durable permite reanudar si la fila de concepto ya no
está. Las carreras con nuevas relaciones/evidencias compensan únicamente la
inserción propia, comprobada mediante CAS. **React todavía no expone borrar**:
no se conectó una escritura nueva antes de comprobar el contrato compartido.

## Matriz de migración al cerrar este lote

| Capacidad | Implementado | Verificado sin Streamlit | Listo para retirar el legado |
|---|---|---|---|
| Arranque, navegación, contexto y atrás/recarga | Sí | Chrome/Firefox + HTTP | No: conexiones/perfiles y recuperación entre orígenes pendientes. |
| Biblioteca, búsqueda por bibliografía y fuente exacta | Sí, paginación de fuentes | Sí, incluidas identidades fuera de la primera página | No: creación/importación y gestión completa de fuentes pendiente. |
| PDF, pasaje y nota visual recuperable | Sí | Sí: pérdida de respuesta, recuperación y guardado real | No: completar todos los atajos de anotación y cambios de versión. |
| Preparación compatible de notas/subrayados | Sí, sobre comprobaciones canónicas | HTTP y contratos de permisos/incompatibilidad; interacción real con biblioteca pendiente/preparada | No: selector de otra conexión/biblioteca y sus estados completos pendientes en React. |
| Publicación explícita y procedencia | Sí | Sí: nota/anotación → concepto → origen | No: edición/conflictos de todas las fichas y evidencia pendientes. |
| Esfera, selección, lectura y leyenda semántica | Sí | Sí, sobre conceptos compartidos | No: revisar paridad de todas las acciones del coordinador. |
| Borrado común | Servicio y dos páginas heredadas | Servicio standalone; UI de compatibilidad con AppTest | No: no está expuesto en React. |
| Edición canónica de conceptos y relaciones | Servicios disponibles | CAS/resumen y contratos heredados comprobados | No: interfaz React de edición completa pendiente; “Editar ficha” aún abre lectura. |
| Exportación, medios, DOI/ISBN y referencias completas | Servicios/exportadores conservados | Pruebas anteriores y suite de este corte | No: paridad de pantallas y transferencias pendiente. |
| Cuaderno, Cornell/CPI, tareas y revisiones | Modelos y legado conservados | Verificaciones anteriores válidas | No: migración de estas capacidades pendiente. |
| Identidad matemática | Editor, lectura, etiquetas, previsualizaciones, nodos y leyenda | Ocho tipos, teclado, fórmulas y ventanas ancha/estrecha | No: por sí sola no demuestra la paridad funcional del editor completo. |

No se anuncia cierre de la migración ni retirada de Streamlit/CCv2. Los
borradores de un origen anterior no se pueden leer automáticamente desde el
nuevo puerto: se mantiene su descarga, y falta el flujo explícito de importación
validada. No se mezclan identidades ni se borra su archivo local.

## Verificación y límites

La integral disponible de este corte contiene **2115 casos: 2106 aprobados,
9 omitidos, 0 fallidos**; los nueve opt-in Mongo pasan después en standalone
propio. Los 50 casos históricos del ZIP privado se ejecutan en la integral;
no se sustituyeron por el PDF sintético de navegación. El ZIP esperado sigue
siendo `mathkb_export_20260712_073927.zip`, originalmente en
`~/.local/share/mathmongo/backups/`. La copia local autorizada y sus evidencias
anteriores se conservan fuera de Git.

Tras ordenar imports y documentar contratos, se actualizó exclusivamente la
cobertura de los cuatro módulos Python afectados mediante pruebas de esos
flujos; se conservó el resto de las mediciones válidas. Dos casos adicionales
ejercitan el borrado real desde Exploración con/sin evidencia. El resultado
exacto de esa ejecución y la conciliación de casos figuran en
`REACT_CHECKPOINT_RESULTS.json`.

Frontend: **224 pruebas aprobadas**, ESLint sin avisos, typecheck y build
correctos. Los recorridos reales se ejecutan como casos Node nombrados. Una
repetición de Firefox se bloqueó al capturar el diagnóstico de un fallo; la
causa original no quedó recuperada en aquella ejecución. Se corrigió la captura
para conservar primero el error original; el reintento completo pasa. No se
presenta ese fallo como una corrección funcional del navegador.

La auditoría de dependencias anterior sigue aplicando: no se modificaron los
manifiestos ni lockfiles de ejecución. Ruff conserva sus reglas y sus deudas
heredadas; se retiraron los avisos introducidos en los módulos de esta fase,
sin autofix global sobre el JavaScript incrustado de PyVis.

La cobertura local Python, la cobertura V8 y la de Sonar tienen denominadores
distintos. La tabla y el desglose por archivo del análisis procesado final están
en `REACT_CHECKPOINT_RESULTS.json` y `REACT_NEW_COVERAGE.csv`. El Gate ERROR no
se oculta con un éxito anterior ni se interpreta como auditoría cerrada.

Para repetir con la referencia conservada:

```bash
make sonar-scan SONAR_LABEL=react-identity-repeat
```

`SONAR_LABEL` nombra los artefactos; **no** modifica `sonar.projectVersion`.
`scripts/sonar.py` verifica antes y después la referencia fijada en
`infra/sonarqube/reference.json`: PREVIOUS_VERSION,
`2026-11-21T16:46:16+0000`. Mantiene perfil, umbrales y exclusiones. El comando
genera las coberturas, espera al servidor y conserva también un Gate ERROR.
Las repeticiones del análisis final de este lote reutilizan reportes válidos y
comprueban sus hashes, en lugar de volver a ejecutar verificaciones intactas.

### Comparación medida

| Medida | Tras extracción | Checkpoint React |
|---|---:|---:|
| Cobertura general Sonar | 71,2 % | 73,0 % |
| Cobertura nueva Sonar | 63,6 % | 69,7 % |
| Incidencias nuevas | 0 | 0 |
| Quality Gate | ERROR | ERROR: cobertura nueva < 80 % |

La revisión y el identificador exactos del último análisis procesado están en
`REACT_CHECKPOINT_RESULTS.json`. La referencia sigue siendo PREVIOUS_VERSION
`2026-11-21T16:46:16+0000`. Hash de propiedades en ambos extremos:
`84aec1246aae6a1a3949f786449faf9c19a10894cfcb044adcf81866f18f08a6`.
El análisis intermedio encontró 48 avisos nuevos; los dos posteriores al cambio
de casos Node y botón explícito los dejan en cero, sin marcar falsos positivos.

Análisis final **`7bfb0b4c-d4cd-4de8-a534-807e97244eab`**, revisión
**`8dbd6234944e6f39cbadf91b59c44b1fb3173ead`**, CE SUCCESS, sin avisos de
procesamiento. Condiciones: cobertura nueva **69,7 < 80 (ERROR)**, duplicación
nueva **0,14364 ≤ 3 (OK)**, incidencias nuevas **0 ≤ 0 (OK)**. El commit documental
posterior sólo añade evidencias y registros, sin cambiar el código analizado.

El código nuevo contiene **9020 líneas y 1940 condiciones medibles**: faltan
2646 líneas y 678 condiciones. Son 7636 observaciones cubiertas de 10960
(69,7 % redondeado). Para llegar al 80 % con ese denominador harían falta al
menos **1132 observaciones adicionales cubiertas**. No se rebajó el umbral.

| Archivo / principal déficit | Líneas nuevas sin cubrir | Condiciones nuevas sin cubrir |
|---|---:|---:|
| editor/app_pages/relations.py | 402 | 0 |
| editor/app_pages/knowledge_graph.py | 286 | 0 |
| editor/app_pages/home.py | 272 | 0 |
| knowledge-map/room.ts | 157 | 100 |
| knowledge-map/canvas.ts | 65 | 74 |
| knowledge-map/component.ts | 58 | 78 |
| editor/maintenance_page.py | 118 | 0 |
| knowledge-map/document-editor.ts | 55 | 49 |
| editor/app_pages/concept_edit.py | 101 | 0 |
| editor/app_pages/concepts.py | 97 | 0 |
| study/StudyApp.tsx | 48 | 48 |
| editor/app_pages/export.py | 87 | 0 |

El CSV recoge los **153 archivos contribuyentes**, con líneas/condiciones
medibles y sus cantidades sin cubrir. Los cuatro recorridos de mapas redujeron
su déficit desde 661 hasta 286 líneas; Edición, de 345 a 101; Exploración, de
148 a 97. Relaciones continúa pendiente: estos avances no sustituyen su revisión.

Se cotejó el XML importado con Sonar para **26 módulos Python** (páginas
extraídas, servicios nuevos, mapa y borrado): **0 discrepancias** de líneas
medibles/sin cubrir. El scanner confirma lectura del XML y del LCOV, y el
servidor termina CE SUCCESS sin avisos. No hay evidencia de un reporte rechazado
ni de un problema de resolución de rutas en ese conjunto. El déficit heredado
de importación ya había dado cero discrepancias en los 32 módulos de extracción.

El LCOV actual procede de **Vitest**, no de las capturas E2E. Por ejemplo,
StudyApp mantiene 48 líneas y 48 condiciones nuevas sin cubrir en ese reporte,
aunque el recorrido principal del shell esté comprobado en navegador. No se
atribuyen esas 96 observaciones enteras al tooling: también incluyen rutas de
fallo y ramas que el recorrido no demuestra. Falta instrumentar el E2E para
cuantificar su intersección exacta y combinarla mediante mapas de fuente; no se
inventaron hits a partir de capturas ni se modificaron exclusiones. Los tests
unitarios, los contratos HTTP y la ejecución real se presentan por separado.

Python local final: **33958 / 46465 = 73,08 %**, sin colección de ramas Python.
V8 local: **3681 / 4817 = 76,41 % de líneas**, **1995 / 3149 = 63,35 % de ramas**.
Sonar combina otro alcance de fuentes/lenguajes y condiciones: su 73,0 % no es
un redondeo de ninguna de esas dos cifras. Los XML/LCOV y sus hashes quedan
archivados con la revisión, para mantener una base comparable.

La conciliación de JUnit reúne **2117 IDs distintos**: 2108 aprobados y 9 opt-in
omitidos en las ejecuciones generales/afectadas; esos mismos nueve pasan en el
Mongo propio. Resultado conciliado: **2117 verificados, 0 fallidos, 0 pendientes
por omisión**. No se afirma una segunda integral monolítica de 2117 casos:
la integral fue 2115, el lote afectado 57 y la comprobación del router 167;
se descontaron repeticiones. Ruff queda en **2156 avisos heredados** y conserva
las mismas reglas. Se verificó también que los avisos de schemas.py son los
mismos que antes de añadir Observación.

`REACT_TEXT_DELTA.json` distingue fuente, pruebas, recursos y generados desde
`6132704a`. Son recuentos textuales de Git, no funciones eliminadas. Los helpers
CAS/huella se trasladaron a `mathmongo/concurrency.py` conservando sus imports
de compatibilidad. El mapa de colores duplicado se sustituyó por la tabla
semántica compartida; todos sus consumidores se construyeron y probaron. El
bootstrap de ruta redundante se retiró tras verificar la importación instalada.
No se eliminan flujos, documentos ni datos; los cambios masivos de bundles
son regeneración, no una reducción de código mantenido.

## Pendientes concretos

1. Recuperar cobertura del código extraído que permanece poco ejercitado,
   especialmente mapas, relaciones y variantes de formularios; priorizar
   resultados persistidos y recursos/fallos, no ejecución vacía de líneas.
2. Terminar la paridad de edición/relaciones/exportaciones, bibliografía,
   organización y Cornell/CPI antes de retirar páginas o dependencias.
3. Revisión coherente del recibo y lectura posterior de nota si un segundo
   escritor la cambia entre ambas respuestas; mantener borrador y revisión
   vinculados al mismo contenido. El CAS impide sobrescritura inadvertida,
   pero falta completar esa experiencia de conflicto.
4. Acotar el catálogo de conceptos en servidor: el resumen ya no lee todos
   los LaTeX, pero `/overview` todavía devuelve el conjunto de metadatos.
   La lista de documentos por fuente conserva límite 100 sin paginación UI.
5. Completar foco explícito del subrayado y aviso ante otra versión del PDF al
   regresar al pasaje; está comprobada la página y procedencia originales.
6. Integrar el atajo de nota de una anotación ya guardada con el editor amplio;
   la selección nueva ya recorre ese flujo. El atajo histórico conserva su UI.
7. Prueba de cambio entre dos bibliotecas con identidades coincidentes desde
   un selector React; HTTP ya rechaza ámbito incorrecto y respuestas antiguas.
8. Preparación de publicación de conceptos sobre bases totalmente vírgenes,
   reutilizando el contrato existente de índices sin mantenimiento silencioso.
9. Continuar el inventario y las decisiones de los veinte archivos de más de
   mil líneas. Un Gate aprobado futuro tampoco cerrará esas revisiones.

No queda bloqueo por ausencia del ZIP privado en este checkpoint. Los pendientes
de paridad se identifican como trabajo no implementado, no como pruebas privadas
supuestamente aprobadas.

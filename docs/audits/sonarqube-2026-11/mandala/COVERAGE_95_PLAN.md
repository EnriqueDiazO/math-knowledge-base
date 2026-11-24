# Objetivo interno 95 %: riesgo y línea base antes de añadir pruebas

Checkpoint recuperado: HEAD `278b420c`, limpio, rama conservada. Sonar confirmado
por API: análisis `b4ddd3bd-402b-4ab7-80b3-df8231fcc998`, fuente `a6d77fdb`,
76,0 % general, 80,6 % nueva y Gate OK. Los umbrales oficiales siguen en 80 %, 3 %
y cero incidencias nuevas; la aceptación interna pide **95 % general y nueva**.
No se cambia referencia PREVIOUS_VERSION ni perfil, reglas, exclusiones o umbrales.

General: 58 646 observaciones de línea/condición, 14 075 sin cubrir. Sin añadir
código harían falta al menos **11 143 observaciones adicionales** para 95 %.
Código nuevo: 14 991 observaciones, 2905 sin cubrir; faltan al menos **2156**.
Los denominadores cambiarán al implementar capacidades; no se presentan estas
estimaciones como una promesa de cumplimiento en un único checkpoint.

El XML Python importado actualmente mide líneas; las 4461 condiciones de Sonar
proceden del frontend JS/TS (69,3 % cubiertas). No atribuirlas a ramas Python.
Se añadirán mediciones de ramas de las fronteras críticas por separado para
identificar decisiones sin verificar, distinguiéndolas de los informes comparables
importados. No mezclar archivos de datos de coverage incompatibles.

| Prioridad / módulo | General / nueva actuales | Riesgo y pruebas requeridas | Consumidores conservados |
|---|---|---|---|
| P0 Cornell/CPI y latex_notes | 81,46/100 %; 77,10/97,06 % | Revisión leída dos veces, escritura sin CAS, estructuras/campos desconocidos, errores y reintentos; Mongo real y preservación exacta antes de HTTP | Servicios canónicos, UI antigua y exportadores; aún no retirables |
| P0 MathMongo | 59,26/100 % | CRUD, identidad histórica, permisos/ACK y actualización concurrente de estructuras; fábrica sin inicialización | Diario, Cornell/CPI y compatibilidad |
| P0 catálogo/documentos | 87,02/93,58 %; 86,17/87,10 % | Referencias compartidas, bajas parciales, versiones, recursos/rutas, errores de almacenamiento | React, lector y servicios históricos |
| P0 notas/evidencia | 82,28/85,71 % | CAS, interrupciones, evidencia exclusiva, pérdida de respuesta, aislamiento por biblioteca | React, lector y promociones |
| P0 medios/importación/restauración | editor/utils 79,68/91,67 % | Referencias de todos los formatos, symlinks, plan obsoleto, fallo parcial y restauración; no sólo mocks | Notas/conceptos, ZIP privado y administración |
| P0 compilador aislado | 91,43/91,43 % | Procesos limitados, errores, rutas, macros/TikZ/PGFPlots, recursos ausentes y salida incompleta | Preview y exportación HTTP |
| P1 editor y HTTP de estudio | backend 92,51/92,51 % | Payload inválido, respuesta tardía, borrador, revisión, error de red y guardado confirmado | React independiente y AppImage |
| P1 exportadores/renderizadores | latex_compile 74,03 % legado | Exportación por regiones y ajuste/overflow; conservar estructura y dependencias sin relajar aislamiento | Cornell/CPI, Diario y compatibilidad |
| P1 interfaz aún antigua | Cuaderno 7,1 %; document_builder 14,0 % | Operaciones reales y sus consumidores; migrar sin omitir trabajo/tareas/exportaciones | Navegación histórica sigue vigente |
| P2 construcción/frontend tooling | prepare-pdf-worker y publish-build 0 % en Sonar | Publicación atómica, archivos esperados, hashes, fallos y preservación de recursos | Builds y AppImage; no excluir para subir porcentaje |
| P2 auxiliares y entradas antiguas | varios 0–25 % | Auditar llamadas/configuración/importaciones antes de retirar; pruebas con resultados verificables | CLI, escritorio y compatibilidad por comprobar |

Orden: asegurar persistencia estructurada → Cornell vertical con regiones y
exportación → CPI con operaciones propias → demás actividades independientes
viables → UX/estabilidad → AppImage actualizada. Cada corte mide sus módulos,
recorre Chrome/Firefox y espera Sonar procesado. No se declara 95 % hasta que el
servidor confirme ambos valores sobre la fuente correspondiente.

Datos iniciales por archivo y funciones críticas: evidencia local
`evidence/sonar/cornell-cpi-2026-11-24/initial-*`. Matriz de paridad y revisiones
anteriores se conservan. Todas las escrituras de prueba usarán Mongo/PID/base,
recursos y XDG temporales propios. No se escribe sobre MathV0.


## Cierre medido del 24 de noviembre: 95 % todavía pendiente

Análisis procesado `68db7833-292e-46f7-8b7b-93e7998ded5e`, revisión
`0e08a639578546f0fbcd5375be299efdffef4163`. Referencia PREVIOUS_VERSION de
2026-11-21T16:46:16+0000 y configuración conservadas. Gate oficial **OK**:
81,7 ≥80 de cobertura nueva, 0,09069 ≤3 de duplicación y cero incidencias nuevas.
No se confunde este resultado con la aceptación interna del 95 %.

| Alcance | Antes | Después | Observaciones / faltantes | Adicionales para 95 % a denominador fijo |
|---|---:|---:|---:|---:|
| General | 76,0 % | 76,4 % | 59 665 / 14 110 | **11 127** |
| Nuevo | 80,6 % | 81,7 % | 16 023 / 2934 | **2133** |

El intermedio `54e6847a-86d7-4bc2-a573-63d2226071cd` tuvo Gate ERROR por un botón
sin tipo submit (S9011). Se corrigió en `d7a411e0` y no se suprimió la incidencia.
Los análisis posteriores quedaron aprobados. Las 348 pruebas frontend y 2216
Python distintas verificadas añaden contratos: fuente original/no-op, CAS, replay,
fallo parcial de medios, confirmación posterior a escritura, límite/modelo,
regiones/borrador, respuesta tardía, medición aislada y exportación fallida.
No se suman las repeticiones focalizadas al número de pruebas distintas.

Nuevas fronteras Python: persistencia 58/59 líneas y 29/30 ramas; dominio 124/124
y 32/32; HTTP 88/88 y 8/8; layout 32/32 y 6/6. Es una medición de ramas separada,
no se importa como si fuera el XML comparable de líneas. `formula-tools.ts`
alcanza 99,2 % combinado, estado estructurado y citas 100 %, campos 98,0 %, listado
95,2 % y coordinador 92,0 %. El coordinador sigue por debajo de la aceptación
interna y conserva cinco líneas y dieciocho condiciones sin observar.

### Déficit restante por archivo

Se muestran los diez primeros del código nuevo. El JSON versionado conserva
los veinticinco primeros de cada alcance, con líneas/condiciones por separado.

| Archivo | Cobertura nueva | Líneas nuevas sin cubrir | Condiciones nuevas sin cubrir |
|---|---:|---:|---:|
| `editor/app_pages/knowledge_graph.py` | 63.2 % | 263 | 0 |
| `frontend/advanced-reader/src/knowledge-map/canvas.ts` | 79.4 % | 65 | 74 |
| `frontend/advanced-reader/src/knowledge-map/component.ts` | 81.5 % | 58 | 76 |
| `frontend/advanced-reader/src/knowledge-map/room.ts` | 83.7 % | 54 | 53 |
| `editor/app_pages/concept_edit.py` | 72.4 % | 101 | 0 |
| `editor/app_pages/concepts.py` | 41.6 % | 94 | 0 |
| `frontend/advanced-reader/src/study/StudyApp.tsx` | 48.3 % | 41 | 50 |
| `frontend/advanced-reader/scripts/merge-browser-coverage.mjs` | 49.7 % | 37 | 41 |
| `frontend/advanced-reader/src/knowledge-map/document-editor.ts` | 81.1 % | 36 | 41 |
| `frontend/advanced-reader/src/study/ConceptPages.tsx` | 42.4 % | 40 | 32 |

La mayor deuda general sigue en Cuaderno de compatibilidad (2036 líneas sin
cubrir), Cornell legado (319), pdf_export (298), document_builder (276), CPI legado
(274), grafo de compatibilidad (263), publicación (227), sincronización de grafo
(224), importación (212) y notas/evidencia (200). Reutilizar caracterizaciones y
probar efectos reales al migrar sus operaciones; no borrar sus denominadores
mientras sus consumidores sigan vigentes.

### Tooling e importación: cuantificación, no atribución genérica

Los seis archivos identificados de tooling/configuración tienen 532 observaciones
generales y **98 nuevas** sin cubrir: merge 78 nuevas, builder AppImage 15,
prepare-pdf-worker 1, publish-build 2, Vite 2, Playwright 0. Son **3,34 %** del
déficit nuevo; no explican las otras 2836 observaciones sin cubrir. Los helpers
CLI no quedan instrumentados por V8 al construir, y además faltan pruebas de
sus fallos: ejecutar el camino satisfactorio no acredita las condiciones negativas.

Todas las rutas de Python analizadas coinciden con el XML. Python nativo
71,73 % incluye 2763 líneas sin cubrir de copias/sondas y flatted fuera del alcance
Sonar inalterado; Python propio Sonar mide 75,88 %. La diferencia es de alcance,
no de importación fallida. LCOV combinado mide 5336/6441 líneas y 3353/4743
condiciones. Los 723 números de línea sólo presentes en BRDA y trece líneas de
configuración fuera del LCOV explican exactamente la diferencia con Sonar JS.
No se alteran informes, exclusiones ni denominadores para mejorar el porcentaje.

### Siguiente avance verificable

Primero completar recuperación/estado del coordinador y los contratos de
medios/asociaciones Cornell/CPI con Mongo temporal; después duplicación/borrado
contextual y tareas de Cuaderno con sus fallos parciales. Atender las operaciones
heredadas que sigan disponibles, incluidos exportadores y recursos. Para tooling,
crear casos de publicación/merge con salidas y errores comprobables y capturar
sus procesos de manera compatible con el LCOV vigente, sin atribuir hits manuales.
Seguir con lotes separados y medición procesada; la brecha de 11 127/2133 no se
oculta tras los módulos nuevos de alta cobertura.

`CORNELL_CPI_RESULTS.json` conserva datos y `CORNELL_CPI_CHECKPOINT.md` el informe.
`REPEAT_REACT_ANALYSIS.md` reproduce nueve cohortes y el análisis con la misma
referencia. No se retira Streamlit ni se declara alcanzado el objetivo global.

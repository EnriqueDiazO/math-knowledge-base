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

## Cierre de autoría completa y editoriales (24 de noviembre)

La medición vigente se conserva en LATEX_AUTHORING_RESULTS.json; sustituye
las cifras anteriores como estado actual, sin borrar su historial.
Análisis `05caf8eb-bca8-40dd-a7ef-abaacf2721cd`, fuente `24c4e115`, CE SUCCESS,
**76,5 % general / 82,0 % nueva, Gate OK**, nuevas incidencias 0. Referencia,
perfil/reglas y configuración SHA siguen iguales. Condiciones nuevas 2808/3775;
generales 3559/4984. No son ramas Python: el XML comparable mide líneas.

General: 60 303 observaciones, 14 167 sin cubrir; faltan **11 152** para 95 % a
denominador fijo. Nuevo: 16 661 observaciones, 2994 sin cubrir; faltan **2161**.
El aumento de código cambia los denominadores: conservar el porcentaje redondeado
no significa que no se haya ejecutado código nuevo. Frente al checkpoint recuperado
se añadieron 581 observaciones generales cubiertas y 578 nuevas cubiertas.
La ausencia de algunas ramas de compatibilidad y del coordinador no se oculta.

Fuente especializada 99,2 %, carga diferida 95,3 %, completado/estilos/diagnóstico
100 %, preferencias editoriales 100 %. Coordinadores ConceptWorkspace 81,9 % y
StructuredWorkspace 91,7 % conservan riesgos por probar; no se declaran al 95 %.
Dos regresiones relevantes cerraron nueve condiciones: notas antiguas sin ajustes
no deben materializar defaults al abrir y un parámetro vacío no debe reemplazar
un valor válido por NaN. Chrome añade 322 líneas/231 condiciones reales a Vitest.
No se acreditan cohortes fallidas ni se vuelven a mapear fuentes modificadas.

Diez rutas de tooling (incluidos cuatro .d.mts sin decisiones ejecutables) suman
82 observaciones nuevas sin cubrir, **2,74 % de las 2994**: merge-browser-coverage
37 líneas/41 condiciones; prepare-pdf-worker 1 línea; publish-build 2 líneas;
runtime-notices 1 condición. No explican los 2161 adicionales necesarios para 95 %.
Los primeros déficits siguen en conocimiento/gráficos, ConceptPages/StudyApp y
compatibilidad; el JSON lista veinticinco por cada alcance. Priorizar contratos
que permanecerán, sin dedicar toda la migración al código antiguo ni retirarlo
antes de demostrar sus consumidores. Umbrales oficiales intactos.

## Recuperación funcional por operaciones — 24 de noviembre

Medición vigente: **FUNCTIONAL_MIGRATION_RESULTS.json**, análisis
`e6830f9b-bc15-4a3e-a835-7d00d73293c1`, revisión `c1a29eb5`, CE SUCCESS.
**76,6 % general / 82,2 % nueva, Gate OK**, incidencias nuevas cero. Frente al
anterior 76,5/82,0 se cubren 355 observaciones generales y 386 nuevas más, con
crecimiento del denominador. Objetivo interno 95 **todavía no alcanzado**:

| Alcance | Cubiertas / medibles | Sin cubrir | Adicionales para 95 a denominador fijo |
|---|---:|---:|---:|
| General | 46491 / 60695 | 14204 | **11170** |
| Nuevo | 14053 / 17090 | 3037 | **2183** |

La brecha absoluta sube 18/22; el aumento porcentual no equivale a una reducción
absoluta con nuevo código. Priorizar los contratos de integridad, concurrencia,
recursos y operaciones que se migren. No posponer las 167 operaciones sin paridad
completa para dedicar el lote a cobertura del editor o a empaquetar.

Nuevo servicio de acciones 91,0 %, helper nativo 94,6 %, payload 94,7 %, estado y
acciones React 85,7 %; structured_notes/structured_routes 100 %, páginas de formato
96,0 %. Ramas defensivas de recibos/confirmaciones, respuestas anómalas, cancelación
y errores de persistencia siguen mereciendo pruebas de comportamiento. Los
principales déficits heredados/nuevos siguen en knowledge_graph, canvas/component/
room, concept_edit/concepts y StudyApp; veinticinco por alcance en el JSON.

Tooling comparable: **82/3037 = 2,70 %** de observaciones nuevas sin cubrir, los
mismos diez archivos. No es una explicación del resto. No cambia referencia,
umbrales, reglas, exclusiones o supresiones. El XML importado tiene 2865 líneas
fuera de Sonar; Python propio **75,96 %**, XML bruto **71,67 %**. LCOV Chrome real
aporta **322 líneas/234 condiciones** sobre Vitest, sin aumentar denominadores;
**802 números de línea BRDA sin DA +13 líneas de configuración** explican la
diferencia de alcance JavaScript. Cero discrepancias por archivo entre Sonar y
DA∪BRDA. No hay cobertura inventada ni importación ausente.

El siguiente avance útil acompaña medios/asociaciones de Diario/Cornell/CPI y
sus fallos parciales, después las tareas históricas del Cuaderno. Se mantiene
la matriz exhaustiva y los contratos legados sin retirarlos. Repetición fuente,
catorce cohortes actuales: REPEAT_REACT_ANALYSIS.md. Nuevas AppImages suspendidas.

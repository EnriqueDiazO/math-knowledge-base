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

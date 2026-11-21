# Correcciones y pruebas de regresión

Se conservaron los commits de la fase anterior. Las siguientes evidencias son
locales en evidence/sonar/followup-2026-11; los logs anteriores no se sobrescribieron.
Los dobles HTTP usan un listener loopback efímero y estado en memoria; las pruebas
de procesos no contactan un MongoDB del usuario. Los E2E reales usan el standalone
propio con PID comprobado, dbpath/XDG temporales y limpieza de sus bases.

| Commit de esta fase | Comportamiento comprobado | Antes / después |
|---|---|---|
| 392e8569 | Medición de subprocesos y combinación E2E; rutas absolutas equivalentes para los mismos omit; LCOV V8 con Vitest 4.1.12 | Suite existente y 9 E2E pasan; calibración Sonar 51,7%, sin añadir pruebas |
| 45300f68 | Publicación privada atómica/0600, rechazar symlink y URL ajena, preservar credenciales ante error, snapshot de revisión del servidor/latest, paginación de 501 issues y recuperación tras 503 | sonar-contract-before.log: 5 fallos/9 aprobadas; contratos corregidos incluidos en contracts-after.log |
| 45300f68 | Terminar proceso propio si falla constructor/cierre del cliente, comprobar PID/base vacía antes de escribir, propagar fallos y kill tras timeout, entorno sin credenciales/base habitual, --basetemp privado | process-contract-before.log: 4 fallos/7 aprobadas; contracts-after.log conjunto 25 aprobadas |
| fe093394 | Input Pydantic que imita delimitadores no aparece en diagnóstico; TIFF disfrazado se rechaza antes de decodificar | input-boundaries-before.log: 2 fallos/2 aprobadas; después 43 aprobadas con branding/UI existentes |
| 0c455575 | Instalador auténtico por hash, ejecutables/JRE, rechazo de archivo corrupto/arquitectura distinta, arranque/sondeo, reporte nuevo obligatorio, fallos hijos y Gate no ocultados, referencia fijada, label seguro sin projectVersion | tooling-regressions.log: 49 aprobadas; make sonar-scan ejecutado completo al cierre |
| 8723ab2b | Helper de estilo PyVis conserva physics/interaction/edges y argumento profile; se usa el JSON real ya existente | graph-style-before.log: 2 fallos; graph-style-after.log: 28 aprobadas, incluidos guardas XDG y serialización HTML |

Los fallos anteriores se registraron antes de cada corrección. No todos representan
bugs independientes: varias aserciones demuestran distintas consecuencias de un
mismo contrato. Los fixtures de instalador sustituyen únicamente el hash del ZIP
sintético en el test; el instalador real conserva el hash oficial fijado y no usa
ese archivo sintético. Las pruebas verifican efectos, permisos, secuencia de
mutaciones, archivos preservados, configuración resultante y recursos liberados.

## Relación con las correcciones funcionales previas

| Commit conservado | Regresión / evidencia que sigue ejecutándose |
|---|---|
| 87ed3bed | test_audit_data_safety.py y test_audit_mongo_regressions.py: duplicado conserva todos los campos, fallo de segunda escritura compensa sólo metadatos nuevos y no elimina reemplazo concurrente; imagen compartida concepto/nota persiste hasta la última referencia |
| bea2fe74 / 4b8cb48c | test_audit_legacy_parsers.py: referencia Markdown corta, campos opcionales, matemáticas/BibTeX, YAML mapping y rutas QMD/symlinks |
| f8be5bfa | Vitest PdfJsController y App: capability de miniaturas aplicada dentro del callback, conservando comportamiento de render |
| 68165817 | Contratos de entorno/packaging, suite Python, nueve E2E y 107 Vitest; runtime/Chrome de la fase anterior reutilizado porque esta fase no cambia versiones runtime ni el bundle |
| 3f0daf49 | test_real_export_commands_read_the_selected_database_without_writing: CLI grafo/QMD usa la base explícita, genera HTML/QMD esperados y no cambia documentos Mongo |
| 8f18a79a | test_graph_script_serialization.py y test_audit_legacy_parsers.py: serialización segura, tipos lista, título opcional, fallback y HTML sin inyección |

La cobertura del CLI export_knowledge_graph pasa de 9/29 líneas nuevas a 28/29 por
medir su ejecución real en hijos; no se atribuye a una nueva prueba de esta fase.
Rollback y QMD también reciben la medición de sus regresiones E2E preexistentes.

## Reutilización y regeneración final

La suite inicial de esta fase dio 1830 aprobadas/59 omitidas y nueve E2E aprobados.
Tras el cambio final de grafos se ejecutaron los 28 tests afectados. El candidato
Sonar superó el Gate, pero su XML combinaba datos anteriores/posteriores al movimiento
de líneas de ese archivo. Se conservó como candidate-* y no se usa como cierre.
Se ejecutó después el comando integrado completo sobre HEAD estable para regenerar
coverage desde cero. Esa repetición se debe a la invalidez del XML para el archivo
movido y valida además la nueva orquestación real; no se repitieron pruebas de
navegador/build ni instalaciones que permanecían válidas.

No se eliminaron módulos/dependencias en esta fase. Se retiró la rama idéntica del
helper roto y se trasladó su JSON sin cambiar opciones. Las eliminaciones previas
siguen justificadas en FINDINGS.md y COMMITS.md.

# Entrega local: auditoría cerrada y esfera editable

Rama: `feature/knowledge-sphere-2026-11`. Punto de partida: checkpoint
`de166650` en `audit/sonarqube-2026-11`. Los cinco criterios se acreditaron
[antes de implementar la esfera](../closure/CHECKPOINT.md). Main conserva
`1bc8026f`; no hubo push, merge, reset destructivo ni pruebas contra la base habitual.

Código final analizado: **f5ddb5875de80533c8aeeb675bc5d167486ac4f6**.
Análisis **b4e0c8a8-bc12-42c9-bbbb-16cd239f059a**, procesamiento **SUCCESS**,
**Quality Gate OK**. El commit posterior de entrega sólo incorpora documentación,
CSV, resúmenes JSON y capturas de datos sintéticos.

## Comparación verificable

| Control | Cierre anterior 8723ab2b | Checkpoint 3d6e0021 | Esfera f5ddb587 |
|---|---:|---:|---:|
| Análisis | f62b032f-c663-4c1c-97a2-c57a555387c0 | 35032b37-475f-4c41-a9d5-6ca23bfb3506 | b4e0c8a8-bc12-42c9-bbbb-16cd239f059a |
| Python local | 65.94% | 29929/44454 = 67.33% | 30919/44712 = **69.15%** |
| Cobertura general Sonar | 66.4% | 67.5% | **69.6%** |
| Cobertura nueva Sonar | 96.1% | 97.9% | **95.2%** |
| Líneas nuevas cubiertas/medibles | 420/437 | 539/551 | **1119/1151** |
| Condiciones nuevas cubiertas/medibles | 2/2 | 12/12 | **293/332** |
| Bugs / vulnerabilidades | 14 / 3 | 0 / 0 | **0 / 0** |
| Avisos Sonar restantes | 61 | 32 | **32, los mismos datetime.utcnow** |
| Paquetes Python afectados, perfil activo | 7 | 0 | 0, dependencias conservadas |
| npm, prod/dev/optional/peer | 0 | 0 | 0, mismo lockfile/alcance |
| Ruff 0.4.10, mismas reglas | 2157 | 2156 | **2155** |

Gate final: cobertura nueva >=80% (**95.2**), duplicación nueva <=3% (**0.0**),
violaciones nuevas <=0 (**0**). Se mantuvo PREVIOUS_VERSION con fecha efectiva
`2026-11-21T16:46:16+0000`, sin cambiar periodo, perfiles, reglas, exclusiones,
supresiones ni umbrales. SONAR_LABEL nombra artefactos; no configura projectVersion,
que sigue sin proporcionarse. No se presupuso análisis multirrama Community.

La general de Sonar combina Python y JavaScript/TypeScript, líneas y condiciones;
Python local sólo mide líneas de su alcance. Sonar presenta además 69.7% de líneas.
No son porcentajes intercambiables. La nueva 95.2% es
(1119+293)/(1151+332)=95.21%. [COVERAGE.csv](COVERAGE.csv) localiza las 32 líneas y
39 condiciones nuevas sin cubrir, incluidos los huecos anteriores del tooling;
no se añadieron exclusiones para retirarlos. Las explicaciones de 65.8% preliminar,
64.12% baseline y del antiguo déficit de 31.2% se conservan en
[followup/CLARIFICATIONS.md](../followup/CLARIFICATIONS.md) y los documentos de esa fase.

El scanner confirmó la importación de `evidence/sonar/coverage.xml` y
`frontend/advanced-reader/coverage/lcov.info`, sin avisos de rutas sin resolver.
[RESULTS.json](RESULTS.json) registra denominadores y hashes de los reportes importados.
La cobertura del proceso real de Streamlit se añadió mediante coverage subprocess:
antes de esa ejecución, 30169/44703=67.49%; después, 30914/44712=69.14% (cambió también
la implementación de recuperación y su denominador). Las dos regresiones finales
cubrieron cinco líneas adicionales: 30919/44712. No se atribuye toda la diferencia
al tooling. Al mover líneas se purgó exclusivamente el dato de cobertura de
`service.py` y `concept_repository.py` antes de medirlos de nuevo.

## Verificaciones exactas

- Suite integral: **1967 passed, 9 skipped, 0 failed/errors**, 197.44 s.
  Los nueve son E2E opt-in; después **9 passed**, 7.92 s, en mongod propio.
  Se conserva el log íntegro `full-suite.log`; no se presenta el JUnit de una
  ejecución focalizada posterior como si fuera el de esta integral.
- Después de reforzar recuperación: **40 passed**, de los cuales 39 ya existían
  en la integral y uno era nuevo. Se repitieron además **6 E2E reales** de rollback,
  imágenes y exportaciones afectados por el parámetro opcional del repositorio;
  son un subconjunto de los nueve anteriores, no seis casos únicos adicionales.
- Dos regresiones nuevas finales: **2 passed** — desconexión del driver con lectura
  también fallida y reintento único; edición de contenido legado inline sin perder
  metadata ni identidad. Total reconciliado: **1970 casos unitarios únicos +9 E2E
  únicos =1979 Python aprobados**, cero casos únicos obligatorios pendientes.
- **132 Vitest passed** (110 del checkpoint +22 del mapa), TypeScript, ESLint y
  build completo pasan. Los recursos del lector anterior son idénticos al checkpoint.
- **2 ejecuciones Playwright/Chrome reales aprobadas**, una de flujo completo y otra de
  carga: crear, conectar existente, editar, recargar, vecino, crear conectado,
  plano/esfera, teclado, arrastre de ratón, eventos táctiles CDP, anchura 420 px,
  editar/cancelar borrador móvil, abrir editor existente y volver conservando selección.
  Después se consultó MongoDB para comprobar contenido, identidades y relaciones.
- **0 page errors**. El ensayo bloqueó toda solicitud externa. Los únicos errores
  de consola fueron ERR_FAILED de los iconos Material preexistentes del host:
  dos intentos bloqueados en el flujo y uno en la carga, documentados en JSON.
  El mapa no carga recursos remotos y siguió funcionando con esos iconos bloqueados.
- Carga final: **1003 nodos, 1999 aristas, 20 cuadros medidos**, Chrome
  158.0.8127.36/Linux, DPR1, 1440x1100 y movimiento reducido. Media **7.87 ms**,
  mínimo 5.80, máximo 12.50 por dibujo Canvas. La primera implementación medía
  34.37 ms de media; agrupar trazos redujo el coste sin retirar aristas. Son tiempos
  de dibujo de ese ensayo, no FPS completos ni una garantía para otros equipos.
- pip check y poetry check --lock pasan (Poetry conserva avisos de formato legado).
  Wheel temporal: manifest CCv2 y dos recursos del mapa incluidos, sin ZIP privado
  ni credenciales. No se cambió ninguna versión de dependencia durante la esfera.
- Ruff: cero avisos en los módulos/pruebas Python nuevos. El total existente baja
  un I001 en concept_repository.py; [RUFF.csv](RUFF.csv) conserva el desglose.
  No se aplicó una limpieza mecánica de los 2155 avisos heredados.

El corpus autoritativo ya está verificado: las 50 omisiones históricas únicas
pasaron con los bytes aprobados del ZIP del respaldo XDG del usuario. También
participaron en la integral de esta fase. Los 53 iniciales eran 50 ZIP+3 E2E;
los 59 anteriores eran 50 ZIP+9 E2E. El archivo privado y su copia 0600 siguen
fuera de Git. No se sustituyeron sus datos por fixtures sintéticos.

## Cambios, regresiones y commits

[COMMITS.md](COMMITS.md) relaciona los ocho commits de esta fase con sus pruebas.

- `77b9a656`: intenciones estrictas, modelos existentes y ledger durable por UUID;
  creación, duplicados, vínculos dirigidos y edición con hash BSON/CAS.
- `411db6bc`: componente CCv2 generado a partir del template oficial y adaptado al
  toolchain existente, proyecciones unitarias S²/Plano y editor contextual.
- `07684bb3`: harness real de aplicación, persistencia y carga, con recursos propios.
- `8e826658`: revisión explícita de edición parcial; cerrar el borrador conserva
  las escrituras confirmadas y no promete un rollback inexistente.
- `74331518`: ante fallo de contenido, el modo recuperable conserva metadata que
  otro flujo pudo modificar/referenciar. El reintento reconoce la identidad original
  incluso tras renombrar la Source. El modo legado mantiene su compensación auditada.
- `a30264f4`: orden por identidad independiente del locale, orden humano en español,
  casos de un nodo/etiquetas y navegador dentro del ciclo real de Playwright.
- `dd5316cc`: contratos documentados y espera de la transición responsive para capturas.
- `f5ddb587`: regresiones de desconexión, contenido legado y editor móvil sin enviar.

El primer análisis de la esfera falló exclusivamente por 17 observaciones nuevas:
cuatro ordenaciones sin comparador y 13 aserciones fuera del ciclo de un caso de
Playwright. Se corrigieron sin marcar falsos positivos ni alterar las reglas.
Los 14 bugs y los siete paquetes pendientes anteriores se resolvieron antes del
checkpoint: consultar [resoluciones](../closure/CHECKPOINT.md),
[avisos Python](../closure/PYTHON_ADVISORIES.csv),
[entorno reproducible](../closure/ENVIRONMENT.md) y
[commits de auditoría](../closure/COMMITS.md). Se conservan el inventario original,
sus disposiciones Sonar individuales y el addendum de 50 archivos revisados.
[INVENTORY.csv](INVENTORY.csv) añade los archivos de esta funcionalidad con su hash
y tipo de comprobación, sin sustituir ese inventario previo.

Las retiradas previas justificadas permanecen en esos informes. En la esfera se
reemplazaron únicamente bundles propios regenerados y trazados redundantes por
cuadro; no se retiraron formularios, exportadores, mapas guardados ni recursos
compartidos. El HTML PyVis y los snapshots guardados conservan su contrato; la
nueva pareja Plano/Esfera muestra el grafo vivo y sus escrituras confirmadas.

## Modelo y errores

[README.md](README.md) detalla el modelo y las decisiones. Ningún hover, giro,
zoom, filtro, búsqueda o cancelación previa al envío escribe en MongoDB. La cámara,
los filtros y los borradores son presentación por pestaña; no son relaciones.
Las aristas se leen/escriben en `relations`, y el contenido en `latex_documents`.
Se conservan id/source, referencias, imágenes y campos no editados.

El navegador comunica intenciones por CCv2; sólo el backend usa la conexión activa.
La creación reutiliza Source activa, ConceptoBase, validación semántica e insert
existente. Un UUID repetido reconcilia, uno con otro payload se rechaza y un lease
activo responde pendiente. La edición compara ambos documentos y usa CAS de BSON
completo. Se mantiene MongoDB standalone, sin transacciones de replica set.

Si «crear conectado» falla parcialmente, no se borra el concepto: se identifica
la parte persistida y se recupera el mismo intento. Si falla contenido tras cambiar
la ficha, se conserva el borrador, se reconcilia o se revisa la versión actual
explícitamente. Una edición ajena nunca se sobrescribe para ocultar el conflicto.

## Abrir y repetir

```bash
# Entorno cualificado ya disponible en .venv (Python 3.13.16)
poetry install --with build
make run DATABASE=MathV0
```

Usar el nombre de la base que se quiera abrir; MathV0 es el predeterminado actual
del Makefile. Navegación → **Grafo de conocimiento → Esfera editable**. Seleccionar
una Source administrada activa; crear aquí, guardar, elegir «Conectar con…», tipo
/sentido/destino y guardar; «Editar ficha» permite cambiar el contenido. Recargar
conserva la selección/vista por pestaña y vuelve a leer los valores persistidos.
«Plano» usa el mismo grafo. «Abrir nota / edición avanzada» reutiliza la ruta real.

```bash
# Verificación completa sin escribir en la base habitual
.venv/bin/python tests/run_knowledge_map_e2e.py
# Python+E2E aislados, Vitest con cobertura, scanner y espera del Gate
make sonar-scan SONAR_LABEL=sphere-repeat
```

El segundo comando conserva y comprueba la misma referencia. Para incluir también
los hits del navegador en otra medición, después del comando anterior:

```bash
COVERAGE_RCFILE="$PWD/evidence/sonar/coverage-runtime.ini" \
COVERAGE_FILE="$PWD/.coverage" \
.venv/bin/python -m coverage run --parallel-mode tests/run_knowledge_map_e2e.py
.venv/bin/python -m coverage combine --append
.venv/bin/python -m coverage xml
```

Para importar ese XML enriquecido hay que volver a ejecutar el scanner, sin
regenerar los reportes. [REPEAT.md](REPEAT.md) contiene el recorrido completo y el
comando exacto del scanner, con el token sólo en el entorno y la misma referencia.

## Capturas y límites del perfil

Todas las capturas contienen exclusivamente la base sintética temporal:
[crear](images/02-created.png), [editar y conexión](images/03-edited.png),
[recargar y persistir](images/04-reloaded.png), [plano](images/05-flat.png),
[420 px](images/06-narrow.png), [editor móvil](images/06-narrow-editor.png),
[carga de 1003 nodos](images/07-performance.png).

La ficha muestra LaTeX literal seguro; los renderizadores existentes se usan en
la edición/lectura avanzada. Las posiciones se conservan por pestaña, no entre
equipos. La captura breve mantiene la codificación legada id@source: una Source
con @ en su nombre requiere los formularios existentes. No se modifican esas
Sources automáticamente. Varias esferas y colaboración simultánea son extensiones;
no se implantaron como requisitos de esta entrega. Se verificó Chrome y táctil
emulado; no se afirma una matriz completa de navegadores/dispositivos físicos.

Persisten 32 avisos de API datetime.utcnow y el inventario de estilo Ruff, con su
clasificación previa. No hay bugs/vulnerabilidades Sonar ni avisos conocidos de
paquetes en el perfil cualificado. Streamlit emite además un diagnóstico para
websockets16.1/uvicorn0.51 detrás de reverse proxies con cabeceras no ASCII: el
perfil comprobado es loopback directo y los handshakes reales pasaron. Ese modo
con proxy requeriría actualizar/validar el transporte antes de ofrecerlo; no se
presenta como un despliegue probado ni se acepta su riesgo por el usuario.

El servidor Sonar y vm.max_map_count=524288 persistente se conservaron; no hubo
reinstalación ni nuevo sudo. No queda una omisión obligatoria causada por el ZIP.
Los límites anteriores describen el perfil y la compatibilidad de esta primera
esfera; los casos de regresión y los controles de cierre están ejecutados.

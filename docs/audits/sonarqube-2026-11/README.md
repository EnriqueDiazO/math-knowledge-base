# Auditoría MathMongo / SonarQube — 2026-11-21

Registro acumulativo. Rama `audit/sonarqube-2026-11`; origen `main`,
`1bc8026f01c8f6470c7ce6a887df89fa6cd9ab2f`. Árbol inicialmente limpio.
No hay AGENTS.md aplicable en el repositorio ni sus directorios superiores.
No se usa worktree: se revisa el árbol real, incluidos los recursos publicados.

## Alcance y protección

875 archivos versionados al inicio; 377 Python (133 en tests), interfaz Streamlit,
lector React/TypeScript/PDF.js, API FastAPI, CLI/runtime, MongoDB, catálogo de fuentes,
notas Cornell/CPI, exportación LaTeX/Quarto/PDF, portabilidad y migraciones.
Entorno existente `mathdbmongo` (Python 3.10), Poetry/pip, constraints docentes.
Se usa Ruff 0.4.10 sin `--fix` para conservar una línea base. `make run` se conserva.
Skill aplicada: `.agents/skills/developing-with-streamlit/SKILL.md` y referencias
best-practices/session-state. No se reescribirá navegación ni estilos sin evidencia.

MongoDB: precedencia CLI > entorno > configuración XDG > defaults.
`make run` selecciona MathV0; el default de CLI es mathmongo. Nunca se utilizarán
estas bases para escribir en pruebas. Las tres pruebas Mongo pytest son opt-in y
crean nombres temporales; se revisaron sus guardas y limpieza. La suite inicial
se ejecuta sin opt-in, con XDG temporal y URI a puerto sin servidor; las pruebas
unitarias utilizan dobles de repositorios/colecciones. Para E2E se arrancará un
mongod independiente con dbpath temporal, puerto local libre y nombres explícitos.
No se arranca ni se modifica el servicio MongoDB del usuario.

## Infraestructura verificada

Ubuntu 22.04.5 LTS, amd64, RAM 31 GiB (24 GiB disponibles), disco 1.1 TiB libre.
Docker 29.1.3 y Compose v5.0.1 instalados; daemon detenido/socket ausente.
No hay listeners en 9000, 8501, 8766 ni 27017 durante la inspección inicial.
fs.file-max=9223372036854775807; nofile=1048576; nproc=126433: suficientes.
vm.max_map_count=65530: insuficiente; mínimo oficial 524288.
`sudo -n true` exige contraseña. Se solicitó iniciar Docker y elevar temporalmente
el único límite insuficiente. No se cambió el host ni se deshabilitó ningún check.

Versiones elegidas tras consulta oficial: Community Build 26.11.0.134175,
scanner CLI 8.4.0.16527; PostgreSQL 17 (compatibilidad oficial 15–18).
Se fijará también el patch de PostgreSQL tras verificar el tag oficial.
Java local 11 no se utilizará: el scanner nativo incluye su JRE.

Fuentes oficiales consultadas el 2026-11-21:
- https://docs.sonarsource.com/sonarqube-community-build/server-installation/pre-installation/linux
- https://docs.sonarsource.com/sonarqube-community-build/server-installation/server-host-requirements
- https://docs.sonarsource.com/sonarqube-community-build/server-installation/installing-the-database
- https://docs.sonarsource.com/sonarqube-community-build/server-installation/from-docker-image/set-up-and-start-container
- https://docs.sonarsource.com/sonarqube-community-build/analyzing-source-code/scanners/sonarscanner
- https://docs.sonarsource.com/sonarqube-community-build/analyzing-source-code/test-coverage/python-test-coverage
- https://github.com/SonarSource/docker-sonarqube/releases
- https://docs.docker.com/engine/install/ubuntu/

## Checkpoint

Inspección inicial completa. Instalado pytest-cov 7.0.0 como herramienta de pruebas
(antes ausente); no se cambian dependencias runtime. Siguiente paso: suite/cobertura
inicial, controles frontend, instalación scanner y configuración Compose. Análisis
Sonar inicial/final dependientes del servicio Docker y del ajuste del host.

## Fase instalación / línea base

El usuario inició Docker y aplicó vm.max_map_count=524288. Docker reactivó servicios
preexistentes de otros proyectos, entre ellos MinIO en 9000–9001: no se tocaron.
Se confirmó ausencia de contenedores/imágenes/volúmenes Sonar previos; se creó
Compose `mathmongo-sonar`, PostgreSQL 17.12-bookworm y panel loopback 19000.
Scanner oficial descargado y verificado (--version), separado en `.tools`.
Servidor reportó UP en versión 26.11.0.134175; admin/admin cambiado y proyecto/token
creados por Web API. Secretos privados 0600, ignorados por Git, nunca en salida.
Los valores anteriores del host y su reversión figuran en docs/SONARQUBE.md.

Baseline previa a modificaciones de aplicación:
- Python: 1748 passed, 53 skipped, 9 warnings, 130.41 s; 43083 statements,
  14755 no cubiertos (65.75%, mostrado como 66%). Sin fallos de pruebas.
- pip check: sin dependencias rotas.
- Frontend: typecheck y ESLint aprobados; 11 archivos / 107 tests Vitest aprobados.
- Ruff existente: 2165 avisos (1437 E101, 119 UP006, 115 W293, 106 D103, etc.).
  Se conserva el control sin autofix masivo.
- Poetry check --lock: fallo previo confirmado, lock desactualizado respecto a
  pyproject. Se revisará sin actualizar mayores fuera del alcance declarado.
- Análisis Sonar inicial en curso, configuración ya fijada en sonar-project.properties.

Hallazgos confirmados pendientes de lote: rollback de inserción elimina metadatos
preexistentes si insert_one falla; detach de medios decide borrar usando listas
inversas sin comprobar referencias reales (aunque ya existe helper más seguro);
parser Markdown acepta 3 campos de referencia pero accede a 6 (IndexError);
exportador QMD legado usa tipo sin sanear como directorio y no valida rutas finales.

## Línea base cerrada (configuración corregida)

Compute Engine SUCCESS, analysisId y revisión exactos en baseline-sonar.json.
La aplicación analizada corresponde a `1bc8026`; sólo se añadieron infraestructura,
configuración y documentación propias de la tarea antes de ese análisis (commit
posterior `8c60d64e`). No había cambios de usuario. El primer ensayo de cobertura
usaba múltiples roots de paquetes y causó 5 rutas ambiguas. Se cambió a `source=.`
y `include_namespace_packages=True`, se volvió a generar cobertura con la misma
suite y se verificó que TODOS los 244 Python propios aparecen con ruta inequívoca.
El último log baseline importa coverage.xml sin errores de resolución. Esa es la
línea base válida; los ensayos incompletos no se usan para comparar.

1748 passed, 53 skipped, 9 warnings, 125.55 s. Cobertura local corregida: 28330 de
44180 statements, 64.12%. La diferencia frente al ensayo 65.75%/66% no es una
regresión: se incorporaron módulos antes omitidos por namespaces y las herramientas
nuevas. Sonar agrega código frontend sin reporte JS y usa su propia definición de
líneas ejecutables; su porcentaje se registra por separado en COMPARISON.md.
El hash de sonar-project.properties y los perfiles/rules permanecen fijados para
comparar. Gate inicial OK con las condiciones predeterminadas; se conserva sin
rebajar umbrales. Los issues completos están en evidence/sonar/baseline-sonar.json.

53 omisiones previas: 50 requieren un ZIP autoritativo privado aprobado ausente;
3 son E2E opt-in de MongoDB. No faltan herramientas LaTeX: pdflatex/xelatex/lualatex,
Quarto, ChkTeX, pdfinfo y Chrome están disponibles y las pruebas PDF se ejecutaron.
Los 3 E2E se ejecutarán aparte contra mongod temporal. No se inventa el ZIP privado:
las pruebas sintéticas de import/export y migraciones sí se ejecutan.

## Reproducción de los defectos de datos

Se añadió un runner con mongod **standalone** propio, dbpath XDG temporal y puerto
loopback aleatorio: scripts/quality_mongo.py. Nunca usa ni arranca MongoDB habitual.
Las bases tienen prefijo mathmongo_audit_ + UUID y se eliminan al terminar; sólo se
termina el PID de mongod creado por el runner. Datos preexistentes de usuario no
son accesibles desde esa instancia. Evidencia antes: mongo-regressions-before.log,
4 fallos y 1 control aprobado: el duplicado borraba el concepto original; una
compensación borraba el reemplazo de otro escritor; dos casos borraban imágenes
compartidas (concepto–concepto y concepto–nota). La prueba de fallo de segunda
escritura ya revertía el alta nueva y conservaba la otra identidad.

Corrección rollback: primera inserción fuera del try de compensación, y filtro de
rollback limitado al _id real insertado, además de id/source. Mantiene MongoDB
standalone: no requiere replica set ni transacciones. Se verifican íntegramente
campos adicionales, arrays, identidad Mongo y documentos LaTeX anteriores. La
compensación sigue siendo best effort: no ofrece atomicidad distribuida ni puede
resolver una desconexión con resultado de escritura desconocido.

Corrección medios: ambos detach delegan en delete_media_asset_if_unreferenced,
que comprueba concept_ids, note_ids, concepts.image_ids y latex_notes.image_ids.
Se revisaron Cornell/CPI: sus adaptadores persistence agregan imágenes de regiones,
bloques y marca de agua al image_ids canónico de latex_notes. Source Documents PDF
usan blob store independiente; anotaciones/reading_notes enlazan IDs de documento,
no media_assets. Las notas pendientes sin guardar no son referencias persistidas.
La última referencia conserva el contrato opt-in delete_if_unreferenced (False por
defecto); sólo el último detach con permiso explícito borra registro y fichero.
No se migra ni modifica ningún dato existente.

Verificación lote de datos: rollback real aislado: 3 passed; regresiones reales
completas después: 5 passed (antes 4 failed / 1 passed). Pruebas unitarias y de
integración pertinentes: 55 passed, 6 warnings previos de serialización Pydantic.
Logs: rollback-real-after.log, mongo-regressions-{before,after}.log y
data-fixes-tests.log. No se modificaron pruebas preexistentes para aprobar el lote.

## Parser y exportación legados

Entrada mínima Markdown que fallaba antes:

    # Note

    **Referencia**: Author, 2026, Book

    $$x=1$$

Antes: IndexError al acceder a partes[3] tras aceptar len(partes)>=3; no devolvía
ningún concepto. Esperado/ahora: referencia {autor: Author, año: 2026, obra: Book},
contenido_latex='x=1'. Capítulo, página y bibkey se conservan cuando se suministran
(4, 5 o 6 campos). Se mantienen nombres históricos, año entero, IDs, tipo, fórmulas,
BibTeX y comportamiento de referencias inválidas; no se rediseña el parser.
Se añadieron casos matemáticos fracción/alpha y entorno aligned multilínea.

Otros defectos delimitados: YAML vacío/lista/escalar pasaba como metadata y fallaba
más tarde al desestructurar el mapping; ahora ValueError en el límite del parser.
El exportador QMD podía escapar del destino mediante tipo absoluto/../ o seguir
symlinks de carpeta/fichero. Valida categoría y todas las rutas descendientes con
la misma guarda mutable del proyecto. Tipos legítimos conservan directorio y nombre
(ejemplo teoremas/teorema-title.qmd). No se alteró la política de refrescar archivos
exportados con el mismo título: colisiones entre conceptos distintos se registran
como deuda que requiere definir una identidad de archivo compatible.

Evidencia antes (unitarias nuevas): 16 failed / 5 passed. Después: 23 passed en
regresiones de parser/paths y tests XDG preexistentes. Logs en regressions-before.log
y parsers-after.log. Ruff en el módulo QMD conserva 4 docstrings faltantes de la
clase stub preexistente ExportadorQuarto: no se ocultan ni se elimina esa API pública.

## Carrera de estado del lector (hallazgo al validar dependencias)

La suite frontend expuso dos veces un fallo intermitente preexistente: el evento
`document_loaded` podía anunciar el documento con miniaturas no permitidas aún
visibles (`aria-hidden=false`). La prueba existente events.test.tsx: uses metadata
capabilities... ya caracteriza el contrato y no se relajó. La restricción se
aplicaba en un useEffect posterior a la publicación de metadata, con un render
intermedio inconsistente. Se aplica ahora en el mismo callback que carga metadata,
antes de publicarla. Se elimina ese efecto duplicado; se conserva la preferencia
persistida del panel y se evita un render adicional. Evidencia de fallos previos en
frontend-security-checks.log de los ensayos; el resultado final se registra al
cerrar el lote. No se mezclará este cambio de estado con el commit de dependencias.

Resultado tras corregir la carrera: typecheck + ESLint + 107 tests frontend
aprobados; build/publish con los controles de inventario y privacidad aprobado.
Transcripción del fallo observado antes: events.test.tsx:283 esperaba
aria-hidden="true" en "Miniaturas PDF" y recibió "false". El test aislado pasaba,
pero falló dos veces en la suite completa, por lo que no se aceptó como ruido.
El log frontend-security-checks.log conserva el resultado final del mismo control.

## Dependencias y empaquetado

Se cerró el fallo previo Poetry y se actualizaron dependencias con advisories dentro
de versiones compatibles (sin saltos mayores). Alcance, versiones, evidencia y
pendientes están en DEPENDENCIES.md. pip check aprobado; poetry check --lock ya no
falla (conserva warnings de deprecación). TypeScript/ESLint, 107 tests y build/publish
frontend aprobados; 12 tests Python de empaquetado/constraints aprobados. No se
eliminó código de app para reducir advertencias. Los reemplazos de recursos generados
se documentan en DELETIONS.md y se verifican con las pruebas de manifiesto.

## Revisión restante y simplificaciones

Sonar S3923 detectó dos ramas literalmente idénticas en validate_concept_from_mongo;
se sustituyen por su consulta común. Se conserva el contrato de id/source, LaTeX,
resultado y excepciones, probado con la suite existente. Se retira el segundo import
idéntico de List (el primero permanece), el import os redundante del wrapper de app,
la asignación local fullscreen_key que sólo aparecía en un bloque comentado, y un
cálculo de title no usado en Quarto (_file_stem ya calcula el mismo título puro).
No se elimina ninguna función ni API pública. 50 tests de validación/compilación,
grafo y edición de identidad aprobados tras este lote (refactor-tests.log).

El E2E del runtime completo sí se ejecutó y detectó un harness desactualizado:
buscaba Navigation/Documents/Workspace/Open y tarjetas en expanders; la UI real ya
usa Navegación/Biblioteca/Leer y tarjetas container con claves estables. Se actualiza
sólo el probe, manteniendo sus comprobaciones de apertura, vínculo document-only,
render PDF real, worker local, aislamiento y limpieza. Primer fallo se conserva en
runtime-e2e-obsolete-selectors.log. Se añadió espera explícita a la URL destino de
la nueva pestaña, evitando leer su URL antes de la navegación efectiva.
Los 8 E2E Mongo (5 nuevos + 3 existentes) ya pasan con el nuevo PyMongo en standalone,
portabilidad/edición y comprobación de restauración incluidas (final-mongo-e2e.log).

Comprobación persistencia host: el usuario ejecutó sonar_persist_host.sh tras
inspección de todos los directorios sysctl. Se leyó el archivo creado y se comprobó
vm.max_map_count=524288; no se tocaron otros valores. Reversión exacta en SONARQUBE.md.
La herramienta scanner recibió una regresión adicional: un fallo de upload podía
reutilizar un report-task.txt anterior al capturar métricas. Ahora elimina sólo ese
artefacto generado antes de cada scanner y se niega a publicar snapshot si no hay
una tarea nueva. Test antes: 1 failed / 5 passed; después 6 passed.

En el Makefile se confirmaron dos rutas inexistentes: export/... y grafo_interactivo/...
`make export` ahora usa el módulo QMD real con la base DATABASE explícita y une
concepts/latex_documents por id/source; antes ni siquiera arrancaba. `make grafo`
usa un CLI pequeño sobre GrafoConocimiento existente, con lecturas Mongo y destino
XDG validado. Una prueba sobre Mongo real comprueba contenido matemático, HTML y
que no cambie ninguna colección ni documento. 6 regresiones reales aprobadas.
No cambia `make run` ni el formato de los datos. Los dos comandos cierran sus clientes.

El harness runtime también exigía crear MathV0 aunque el bootstrap actual selecciona
sólo la base explícita. Se sustituyó esa expectativa obsoleta por una comprobación
más estricta: la instancia temporal sólo puede contener admin/config/local y las
dos bases UUID del escenario, y debe existir la base esperada. No se omite ninguna
prueba ni se permite usar una conexión externa. Se conserva el fallo del harness en
runtime-e2e-obsolete-default-database.log. Las aserciones de pintura real de canvas,
PDF/text layer, worker local, URL exacta y liberación de puertos permanecen activas.

Runtime completo final: OK en Chrome real; arranque integrado, salud, PDF range,
canvas pintado y text layer, navegación Streamlit → lector, worker local, cero
peticiones remotas/errores de página. Reutilización de lector existente conservó
su proceso; selección de base incompatible bloqueó Streamlit sin matar el lector.
Limpieza de bases, dbpath, XDG y todos los puertos temporales comprobada. Puertos
predeterminados del usuario intactos. Evidencia JSON: final-runtime-e2e.log.

Instalación del scanner desde extracción nueva verificada (SHA256, --version y
permiso ejecutable de jre/lib/jspawnhelper). El instalador ahora conserva modos Unix
de todos los miembros del ZIP fijado; antes zipfile no garantizaba ese ejecutable.

E2E ampliado del lector, con el runner aislado --reader-browser: OK tanto en origen
como tras exportar/importar a otra base temporal. Probó búsqueda, selección,
miniaturas, zoom/rotación, guardado de página, highlight/underline, edición,
archivo/reactivación y vínculos de conceptos; luego rehidratación de geometría y
reimportación idempotente. Tolerancias geométricas originales se conservaron.
Sin errores de consola/página ni solicitudes remotas fallidas. Los abortos de fetch
al cambiar de página/documento se registran aparte y son cancelaciones esperadas.
Evidencia: final-reader-browser-e2e.log. El reporte local no se agrega artificialmente
al XML de cobertura unitario para mejorar sus porcentajes.

Estado antes de verificación global: todos los lotes funcionales probados y
commiteados; controles del tooling aprobados (15 tests incluyendo Makefile y pins),
instalación editable actualizada y pip check aprobado. Se inicia ahora suite con
cobertura + análisis final con exactamente el mismo sonar-project.properties.

## Revisión profunda de HTML de grafos

Se confirmó una inyección HTML/JavaScript que el scanner no detectó: el bootstrap
sólo escapaba el cierre literal </script> en minúsculas, pero HTML reconoce también
</ScRiPt>. Un campo de estado con ese texto creaba un segundo script. Prueba antes:
1 failed / 1 control passed en graph-security-before.log. Ahora el JSON embebido
escapa delimitadores HTML por Unicode, conservando el valor tras JSON.parse, fórmulas
y Unicode originales. Los presets de layout usan el mismo serializador.

La vista previa pequeña y los tooltips del grafo de relaciones interpolaban campos
sin escape; se aplica escape HTML a título, tipo, fuente, IDs, comentario y relación.
Tres regresiones adicionales fallaron antes: la preview aceptaba script, y grafos
con tipo como lista (formato real del schema) fallaban con TypeError. Se normaliza
el primer tipo y se admite titulo=None con fallback al ID. El fallback tras fallo
PyVis tampoco definía tipo_rel cuando no había aristas; ahora muestra Sin relaciones.
Se conserva la selección por id/source sin modificar los documentos almacenados.

La generación usaba show(notebook=True) antes de write_html: requería un template
notebook ajeno a Streamlit y podía abrir navegador. Se usa una sola escritura HTML
con notebook=False/open_browser=False y recursos PyVis inline. Las pruebas ejercitan
PyVis real, metadata canónica, títulos opcionales, tooltip y ambos fallbacks.
Después: 12 passed (graph-security-after.log), sin ejecutar los payloads sintéticos.

Este hallazgo invalidó el primer ensayo final mientras estaba terminando; se conserva
como intermediate-*. No se usa para la comparación. El Gate de ese ensayo fallaba
únicamente por new_coverage=28.3% frente al 80% predeterminado, sin nuevas violaciones.
No se cambiarán reglas, umbrales ni exclusiones para ocultar la cobertura del tooling.
Se repite la suite/análisis tras este lote para analizar la revisión definitiva.

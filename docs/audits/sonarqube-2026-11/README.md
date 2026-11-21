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

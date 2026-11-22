# SonarQube Community Build local

Instancia exclusiva del proyecto: <http://127.0.0.1:19000>.
No se usa SonarQube Cloud ni funciones de ramas/PR de ediciones comerciales.
La rama de trabajo se analiza como proyecto único `mathmongo-local`.

## Requisitos e instalación

Versiones fijadas: SonarQube `26.11.0.134175-community`, PostgreSQL
`17.12-bookworm`, SonarScanner CLI nativo `8.4.0.16527` (Linux x86_64, JRE propio).
Docker/Compose existentes en la auditoría: 29.1.3 / v5.0.1. Para otras arquitecturas
instalar el scanner oficial correspondiente y revisar el instalador de este repo.
El checksum SHA256 fijado en `scripts/sonar.py` corresponde al ZIP descargado del
servidor oficial; es una fijación local del artefacto, no una firma del proveedor.

Usar Python del proyecto e instalar las herramientas de desarrollo:

```bash
mathdbmongo/bin/python -m pip install -r requirements-dev.txt
make sonar-init
make sonar-install-scanner
make sonar-up
make sonar-bootstrap
make sonar-status
```

Antes de `up`, comprobar Docker, memoria (mínimo 4 GiB, preferible 8 GiB), disco
(30 GiB y más de 10% libre), puertos y los límites del host. La configuración
Compose conserva activos los checks de Elasticsearch, usa nofile=131072 y
nproc=8192, no publica PostgreSQL y sólo publica Sonar en loopback.

```bash
docker info
docker compose version
free -h
df -h .
ss -ltn
sysctl vm.max_map_count fs.file-max
ulimit -n
ulimit -u
```

En este host sólo fue necesario iniciar Docker y elevar vm.max_map_count de
65530 a 524288; el usuario ejecutó ambos comandos con sudo. El ajuste es temporal:

```bash
sudo systemctl start docker
sudo sysctl -w vm.max_map_count=524288
```

Después de reiniciar el host, repetir el segundo comando si el valor es inferior.
Para hacerlo persistente, crear **sin sobrescribir archivos existentes** una entrada
`vm.max_map_count=524288` en `/etc/sysctl.d/90-mathmongo-sonar.conf`, después de
revisar posibles ajustes existentes. No bajar un valor que ya sea suficiente.
Para revertir exclusivamente el ajuste de esta auditoría: detener primero nuestros
servicios y ejecutar `sudo sysctl -w vm.max_map_count=65530`. Si se creó el archivo
opcional, retirar sólo esa entrada. No detener Docker si otros proyectos lo usan.
La persistencia aplicada después por el usuario se documenta al final de esta guía;
no se modificaron los demás límites.

El puerto 9000 está ocupado por MinIO de otro proyecto; se eligió 19000 libre.
Para otra instalación cambiar `SONAR_PORT` en el `.env` privado antes de `up`.
No detener procesos ajenos. `up` rechaza puertos ocupados; usar `status` si ya corre.
No reutilizar volúmenes de otra instancia ni cambiar contraseñas de PostgreSQL
sobre volúmenes inicializados: requiere una operación administrativa específica.

## Acceso y secretos

`make sonar-init` crea `infra/sonarqube/.env` privado (0600) sin sobrescribirlo.
`sonar-bootstrap`, después de comprobar el arranque, cambia admin/admin y crea el
proyecto y un token de análisis limitado al proyecto mediante Web API soportada.
La contraseña nueva y el token quedan en `infra/sonarqube/access.local.json` (0600),
ignorado por Git. Abrir ese archivo sólo localmente para consultar la contraseña;
usuario del panel: `admin`. No pegar sus contenidos en informes, chats o commits.
Si ya existen credenciales privadas se conservan. Para una instancia preexistente
sin esos archivos, usar sus credenciales reales; nunca reinicializar su base.

El scanner recibe `SONAR_TOKEN` y `SONAR_HOST_URL` explícitos en su entorno; no usa
secretos en argumentos. Se puede suministrar un token mediante `SONAR_TOKEN`.
El script sólo admite direcciones HTTP de loopback literales y desactiva proxies
y redirecciones en sus peticiones API autenticadas.
No ejecutar `docker compose config` sin `--quiet` al compartir la salida: contiene
la contraseña interpolada. Los informes no incluyen credenciales.

## Repetir pruebas y análisis

```bash
make test-coverage
make sonar-scan SONAR_LABEL=latest
```

`sonar-scan` vuelve a ejecutar la suite real y genera `evidence/sonar/coverage.xml`
antes del scanner; detiene el proceso si fallan las pruebas. XDG es temporal,
los E2E Mongo quedan desactivados y la URI de la suite apunta a un puerto sin
servidor. No se usa MathV0 ni la configuración XDG del usuario. Los E2E completos
son una verificación adicional con mongod/dbpath/base temporales identificados.

El scanner nativo accede al servidor desde el propio host. No intervienen redes
bridge ni rutas de cobertura diferentes entre contenedor y host. `.coveragerc`
genera rutas relativas al repositorio. La propiedad
`sonar.python.coverage.reportPaths` importa el XML. Buscar en la salida el sensor
Cobertura y las advertencias de archivos no resueltos. El análisis espera al
Compute Engine y al Quality Gate; un Gate fallido conserva su código de salida
no cero. `snapshot` consulta el análisis exacto mediante ceTaskId/analysisId:

```bash
mathdbmongo/bin/python scripts/sonar.py snapshot --label latest
```

Las evidencias completas (logs, XML, JSON de métricas/issues/hotspots/perfiles)
quedan en `evidence/sonar/`, ignorado por Git. Los resúmenes revisables y el
inventario están en `docs/audits/sonarqube-2026-11/`.

## Alcance y exclusiones

Se analiza desde `.`: todo el Python propio, frontend TypeScript/React, scripts,
configuración y pruebas. `tests/` y los dos directorios de pruebas frontend se
clasifican como tests y se excluyen exclusivamente de fuentes. No hay módulos
propios omitidos para reducir avisos. Las exclusiones explícitas abarcan entornos,
cachés, herramientas descargadas, salidas de documentos, datos de usuario y
artefactos generados. `mathmongo/advanced_reader/static/` es el bundle publicado
con React/PDF.js y recursos externos: sus fuentes propias están en `frontend/`.
`quarto_book_build/` es una salida Quarto con bibliotecas de terceros. Se mantienen
ambos en disco/Git; no se editan ni se eliminan durante la auditoría.
Los archivos no compatibles con el scanner se inventarían y revisan según formato
(documentación, plantillas, shell, contratos de recursos y empaquetado).

No cambiar reglas, umbrales, supresiones ni exclusiones entre baseline y final.
La cobertura de Sonar excluye código test por diseño; no necesariamente coincide
con el porcentaje redondeado de pytest-cov. El primer análisis no tiene baseline
de código nuevo: un Gate inicial aprobado no implica ausencia de deuda histórica.

## Detener conservando los datos

```bash
make sonar-down
make sonar-up
make sonar-status
```

`down` sólo elimina contenedores/red de `mathmongo-sonar`. Conserva los cuatro
volúmenes `mathmongo-sonar_postgres_data`, `_sonar_data`, `_sonar_extensions` y
`_sonar_logs`, además de los archivos privados. No usar `down -v` ni comandos prune.

## Verificación MongoDB independiente

```bash
make test-mongo-e2e
```

Requiere `mongod` instalado. El runner crea un standalone propio con dbpath temporal,
puerto loopback libre y bases con nombres explícitos. Rechaza usar un servicio
alternativo si mongod no existe; detiene sólo el proceso que creó. Ejecuta también
los tres E2E previamente omitidos. Las pruebas de rollback registran el estado de
metadatos/LaTeX antes y después, y las de imágenes prueban referencias concepto y nota.
Las pruebas de exportación comprueban que no se escriba en ninguna colección.

## Persistencia del ajuste Linux, aplicada en esta auditoría

Se revisaron `/etc/sysctl.conf`, `/etc/sysctl.d/`, `/usr/lib/sysctl.d/` y
`/run/sysctl.d/`; no había otra declaración vm.max_map_count. El usuario ejecutó:

```bash
sudo bash scripts/sonar_persist_host.sh
```

Se comprobó el resultado: `/etc/sysctl.d/90-mathmongo-sonar.conf` contiene
`vm.max_map_count=524288`; el valor vivo coincide. El script no sobrescribe archivos
existentes ni baja límites suficientes. Para revertir esta configuración específica,
después de detener SonarQube y comprobar que no la requieren otros servicios:

```bash
sudo rm -i /etc/sysctl.d/90-mathmongo-sonar.conf
sudo sysctl -w vm.max_map_count=65530
```

65530 era el valor **original**, anterior al primer ajuste manual; el comentario del
archivo refleja 524288 porque el ajuste temporal ya estaba aplicado al crearlo.

La comprobación de navegador ampliada del lector también puede ejecutarse con el
mismo aislamiento Mongo/XDG:

```bash
mathdbmongo/bin/python scripts/quality_mongo.py --reader-browser
mathdbmongo/bin/python tests/run_local_runtime_e2e.py
```

Requieren Node, las dependencias frontend instaladas, Chrome y mongod. El segundo
harness administra su propia instancia MongoDB, puertos y procesos del runtime.

## Repetir el cierre con la misma referencia de código nuevo

Desde esta rama y la instancia local ya inicializada:

```bash
make sonar-scan SONAR_LABEL=followup-final
```

El comando comprueba el periodo efectivo contra `infra/sonarqube/reference.json`:
PREVIOUS_VERSION, 2026-11-21T16:46:16+0000. No lo establece ni modifica. Aborta si
la referencia cambió, antes de generar/subir un análisis o publicar una comparación.
Este archivo fija la referencia de **esta auditoría**; una instalación nueva sin
ese historial necesita establecer/documentar su propia línea base, no reutilizar
sus porcentajes como comparables. No cambiarlo para eludir el Gate de esta instancia.

SONAR_LABEL sólo nombra el JSON (evidence/sonar/followup-final-sonar.json); no pasa
sonar.projectVersion, que permanece `not provided`. Se admiten etiquetas cortas de
letras/números/guiones, sin rutas. Elegir otra etiqueta segura para conservar otra
instantánea; las versiones/historial del proyecto Sonar permanecen iguales.

El comando genera desde cero XML Python con pytest-cov y patch=subprocess, ejecuta
los nueve E2E en el mongod temporal propio, combina los datos y genera LCOV V8 con
los 107 tests Vitest. Requiere mongod y dependencias npm ya instaladas. Las mismas
fuentes/omit se anclan al ROOT para los hijos que cambian cwd; no se amplían
exclusiones. Falla si falla la generación, falta un reporte o el scanner no produce
una tarea nueva. Conserva el estado no cero del scanner/Gate y espera CE antes de
capturar evidencia. El snapshot identifica la revisión analizada por el servidor,
separa HEAD local y rechaza mezclar métricas actuales con una tarea antigua.

Los runners fijan --basetemp y XDG bajo directorios privados temporales. MongoDB
comprueba PID del servidor y ausencia de bases de usuario antes de permitir pytest;
el cierre del proceso ocurre incluso si falla el cliente. No usar la URI habitual
para estos tests. Las 50 pruebas del corpus privado siguen omitidas sin el ZIP que
se detalla en docs/audits/sonarqube-2026-11/followup/CLARIFICATIONS.md.

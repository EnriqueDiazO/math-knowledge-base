# Repetir con la misma referencia de Sonar

Requisitos ya preparados: `.venv` CPython 3.13.16, mongod, Chrome/Node y el scanner
fijado. El ZIP autoritativo `mathkb_export_20260712_073927.zip` debe seguir como
copia privada 0600 en la raíz; el original está en el respaldo XDG indicado por el
usuario. Nunca usar una base habitual como sustituto de los harness temporales.
El servidor dedicado debe estar UP; `make sonar-up` reutiliza sus volúmenes si se
necesita arrancarlo, sin reinicialización.

Recorrido habitual (suite Python+Mongo, Vitest, scanner, procesamiento y snapshot):

```bash
make sonar-scan SONAR_LABEL=sphere-repeat
```

Para repetir también la medición del proceso real de Streamlit sin hacer primero
un análisis intermedio:

```bash
.venv/bin/python scripts/quality.py --with-mongo
npm --prefix frontend/advanced-reader run test:coverage
COVERAGE_RCFILE="$PWD/evidence/sonar/coverage-runtime.ini" \
COVERAGE_FILE="$PWD/.coverage" \
.venv/bin/python -m coverage run --parallel-mode tests/run_knowledge_map_e2e.py
.venv/bin/python -m coverage combine --append
.venv/bin/python -m coverage xml
.venv/bin/python - <<'PY'
import os
import subprocess

from scripts.sonar import (
    ROOT, SCANNER, api, basic, check_generated_reports, check_reference,
    credentials, local_url, snapshot, token_auth,
)

if api('/api/system/status').get('status') != 'UP':
    raise SystemExit('SonarQube no está listo')
check_reference(basic(credentials()['admin_password']))
check_generated_reports(
    ROOT / 'evidence/sonar/coverage.xml',
    ROOT / 'frontend/advanced-reader/coverage/lcov.info',
)
(ROOT / '.scannerwork/report-task.txt').unlink(missing_ok=True)
result = subprocess.run(
    [str(SCANNER)],
    cwd=ROOT,
    env=dict(os.environ, SONAR_HOST_URL=local_url(),
             SONAR_TOKEN=token_auth().removeprefix('Bearer ')),
    check=False,
)
if not (ROOT / '.scannerwork/report-task.txt').exists():
    raise SystemExit(result.returncode or 1)
snapshot('sphere-browser-repeat')
raise SystemExit(result.returncode)
PY
```

Ejecutar cada paso sólo si el anterior pasa. No imprimir credenciales ni poner el
token en argumentos del scanner. La etiqueta sólo nombra el JSON local. No añadir
projectVersion, branch.name ni cambiar `infra/sonarqube/reference.json`.
El snapshot comprueba la tarea, su revisión y la referencia efectiva antes de
publicarse. Conservar el snapshot de checkpoint y el de entrega antes de otro
análisis: el servidor Community muestra la última rama analizada en el mismo
proyecto, mientras estas evidencias locales conservan las comparaciones.

Una ejecución de sólo `tests/run_knowledge_map_e2e.py` genera evidencia visual y
verifica persistencia; no importa cobertura por sí misma. `snapshot` tampoco
lanza ni importa un análisis. Los comandos anteriores distinguen explícitamente
medir → combinar → generar reportes → analizar → esperar → registrar.

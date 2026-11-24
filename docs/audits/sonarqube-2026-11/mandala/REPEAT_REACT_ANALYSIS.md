# Repetir el checkpoint React conservando la referencia Sonar

Ejecutar desde la raíz, con el entorno y las versiones fijadas del proyecto,
Docker/Sonar ya activos y mongod/Chrome/Firefox/TeX disponibles. Estos comandos
no preparan ni escriben en la biblioteca habitual. No usar las evidencias de un
recorrido fallido ni combinar coberturas de archivos cuyo texto haya cambiado.

## Regenerar informes comparables

```bash
.venv/bin/python -m scripts.quality --with-mongo --with-study-browser
(cd frontend/advanced-reader && npm run test:coverage && npm run build && MATHMONGO_BROWSER_COVERAGE=1 ./node_modules/.bin/vite build)
CHECKPOINT_EVIDENCE=$(mktemp -d "$PWD/evidence/sonar/repeat-react-XXXXXX")
mkdir "$CHECKPOINT_EVIDENCE/chrome" "$CHECKPOINT_EVIDENCE/firefox"
COVERAGE_RCFILE="$PWD/evidence/sonar/coverage-runtime.ini" \
COVERAGE_FILE="$CHECKPOINT_EVIDENCE/chrome/.coverage" \
MATHMONGO_COLLECT_BROWSER_COVERAGE=1 \
.venv/bin/python -m coverage run --parallel-mode tests/run_independent_study_e2e.py \
  --browser=chrome --authoring --notes --document-export --legacy
COVERAGE_RCFILE="$PWD/evidence/sonar/coverage-runtime.ini" \
COVERAGE_FILE="$CHECKPOINT_EVIDENCE/firefox/.coverage" \
.venv/bin/python -m coverage run --parallel-mode tests/run_independent_study_e2e.py \
  --browser=firefox --authoring --notes --document-export --legacy
.venv/bin/python -m coverage combine --append "$CHECKPOINT_EVIDENCE/chrome" "$CHECKPOINT_EVIDENCE/firefox"
.venv/bin/python -m coverage xml
(cd frontend/advanced-reader && node scripts/merge-browser-coverage.mjs \
  ../../evidence/sonar/independent-study/chrome/coverage-reading.json \
  ../../evidence/sonar/independent-study/chrome/coverage-authoring.json \
  ../../evidence/sonar/independent-study/chrome/coverage-notes.json \
  ../../evidence/sonar/independent-study/chrome/coverage-document-export.json \
  ../../evidence/sonar/independent-study/chrome/coverage-legacy.json)
```

Detener la secuencia si falla cualquier comando. `test:coverage` se ejecuta
**antes** de los mapas privados y E2E porque limpia su directorio. El merge
comprueba código observado/publicado/mapeado y conserva los denominadores de
unidades; no fusiona posiciones de ramas incompatibles. Firefox verifica el
comportamiento; el LCOV de navegador se obtiene de Chrome.

En esta entrega final también se ha verificado el paquete independiente real,
con `--appimage=...` y evidencia en `packaged-study`; el backend de ese paquete
no incluye coverage. Su ejecución no se suma automáticamente al XML Python.
La corrección de captura se mide con sus 22 pruebas focalizadas y se conserva
la observación válida del resto de módulos desde el checkpoint integral.
Una reconstrucción completa desde los comandos anteriores vuelve a observar
el backend actual sin necesidad de unir líneas desplazadas de informes viejos.

## Analizar los informes generados, sin volver a borrarlos

```bash
.venv/bin/python - <<'PY'
import os
import subprocess
from scripts.sonar import (
    ROOT, SCANNER, basic, check_generated_reports, check_reference,
    credentials, local_url, snapshot, token_auth,
)
check_reference(basic(credentials()['admin_password']))
check_generated_reports(
    ROOT/'evidence/sonar/coverage.xml',
    ROOT/'frontend/advanced-reader/coverage/lcov.info',
)
revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
result = subprocess.run(
    [str(SCANNER), '-Dsonar.scm.revision='+revision],
    cwd=ROOT,
    env=dict(os.environ, SONAR_HOST_URL=local_url(),
             SONAR_TOKEN=token_auth().removeprefix('Bearer ')),
    check=False,
)
snapshot('repeat-react')
raise SystemExit(result.returncode)
PY
```

La configuración ya espera el procesamiento del servidor. `snapshot` exige CE
SUCCESS y el analysisId más reciente antes de atribuir métricas/revisión al
resultado. Exit 3 del scanner con Gate ERROR no significa que se haya rechazado
la importación; comprobar CE y condiciones exactas del informe generado.

Referencia: PREVIOUS_VERSION de `2026-11-21T16:46:16+0000`. No se pasa una versión
nueva, se cambia el periodo ni se añaden exclusiones. `SONAR_LABEL` en los
comandos del proyecto sólo nombra evidencias; no cambia `sonar.projectVersion`.
`python -m scripts.sonar scan --label ...` regenera informes Python/Vitest:
es válido para su alcance documentado, pero no conserva por sí solo el merge
Chrome. La secuencia de arriba evita perder esas observaciones.

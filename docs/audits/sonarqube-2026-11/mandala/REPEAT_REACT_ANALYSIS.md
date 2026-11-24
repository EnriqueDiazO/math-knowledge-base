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
  --browser=chrome --authoring --notes --document-export --legacy --library --notebook
COVERAGE_RCFILE="$PWD/evidence/sonar/coverage-runtime.ini" \
COVERAGE_FILE="$CHECKPOINT_EVIDENCE/firefox/.coverage" \
.venv/bin/python -m coverage run --parallel-mode tests/run_independent_study_e2e.py \
  --browser=firefox --authoring --notes --document-export --legacy --library --notebook
.venv/bin/python -m coverage combine --append "$CHECKPOINT_EVIDENCE/chrome" "$CHECKPOINT_EVIDENCE/firefox"
.venv/bin/python -m coverage xml
(cd frontend/advanced-reader && node scripts/merge-browser-coverage.mjs \
  ../../evidence/sonar/independent-study/chrome/coverage-reading.json \
  ../../evidence/sonar/independent-study/chrome/coverage-authoring.json \
  ../../evidence/sonar/independent-study/chrome/coverage-notes.json \
  ../../evidence/sonar/independent-study/chrome/coverage-document-export.json \
  ../../evidence/sonar/independent-study/chrome/coverage-legacy.json \
  ../../evidence/sonar/independent-study/chrome/coverage-library.json \
  ../../evidence/sonar/independent-study/chrome/coverage-notebook.json)
```

Detener la secuencia si falla cualquier comando. `test:coverage` se ejecuta
**antes** de los mapas privados y E2E porque limpia su directorio. El merge
comprueba código observado/publicado/mapeado y conserva los denominadores de
unidades; no fusiona posiciones de ramas incompatibles. Firefox verifica el
comportamiento; el LCOV de navegador se obtiene de Chrome.

En el corte anterior también se verificó el paquete independiente real,
con `--appimage=...` y evidencia en `packaged-study`; el backend de ese paquete
no incluye coverage. Su ejecución no se suma automáticamente al XML Python.
La secuencia actual incluye los siete recorridos independientes, Biblioteca y
Diario entre ellos. La integral incluye las caracterizaciones de las páginas
retenidas y de los contratos Cornell/CPI. Se requiere el ZIP privado histórico
ya disponible y las copias locales verificadas para la cohorte `--legacy`.
Una reconstrucción completa desde estos comandos vuelve a observar el backend
actual sin unir líneas desplazadas de informes viejos. El paquete AppImage
anterior se conserva: no contiene automáticamente las funcionalidades nuevas.

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

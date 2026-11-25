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
  --browser=chrome --authoring --notes --document-export --legacy --library --notebook --structured --math-tools --clone-drafts --latex-parity --note-actions
COVERAGE_RCFILE="$PWD/evidence/sonar/coverage-runtime.ini" \
COVERAGE_FILE="$CHECKPOINT_EVIDENCE/firefox/.coverage" \
.venv/bin/python -m coverage run --parallel-mode tests/run_independent_study_e2e.py \
  --browser=firefox --authoring --notes --document-export --legacy --library --notebook --structured --math-tools --clone-drafts --latex-parity --note-actions
.venv/bin/python -m coverage combine --append "$CHECKPOINT_EVIDENCE/chrome" "$CHECKPOINT_EVIDENCE/firefox"
.venv/bin/python -m coverage xml
(cd frontend/advanced-reader && \
  MATHMONGO_STUDY_BROWSER=chrome MATHMONGO_COLLECT_BROWSER_COVERAGE=1 node tests/notebook-comparison-browser.mjs && \
  MATHMONGO_STUDY_BROWSER=chrome MATHMONGO_COLLECT_BROWSER_COVERAGE=1 node tests/annex-cornell-browser.mjs && \
  MATHMONGO_STUDY_BROWSER=chrome MATHMONGO_COLLECT_BROWSER_COVERAGE=1 node tests/annex-diary-browser.mjs)
(cd frontend/advanced-reader && node scripts/merge-browser-coverage.mjs \
  ../../evidence/sonar/independent-study/chrome/coverage-reading.json \
  ../../evidence/sonar/independent-study/chrome/coverage-authoring.json \
  ../../evidence/sonar/independent-study/chrome/coverage-notes.json \
  ../../evidence/sonar/independent-study/chrome/coverage-document-export.json \
  ../../evidence/sonar/independent-study/chrome/coverage-legacy.json \
  ../../evidence/sonar/independent-study/chrome/coverage-library.json \
  ../../evidence/sonar/independent-study/chrome/coverage-notebook.json \
  ../../evidence/sonar/independent-study/chrome/coverage-structured.json \
  ../../evidence/sonar/independent-study/chrome/coverage-math-tools.json \
  ../../evidence/sonar/independent-study/chrome/coverage-concept-clone.json \
  ../../evidence/sonar/independent-study/chrome/coverage-concept-cold-recovery.json \
  ../../evidence/sonar/independent-study/chrome/coverage-latex-parity.json \
  ../../evidence/sonar/independent-study/chrome/coverage-latex-recovery.json \
  ../../evidence/sonar/independent-study/chrome/coverage-note-actions.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/notebook-after-chrome/coverage-notebook-menu.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/notebook-after-chrome/coverage-notebook-worklog.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/notebook-after-chrome/coverage-notebook-backlog.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/notebook-after-chrome/coverage-notebook-deliverables.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/notebook-after-chrome/coverage-notebook-weekly.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/notebook-after-chrome/coverage-notebook-kanban.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/cornell-ui-after-chrome/coverage-annex-cornell.json \
  ../../evidence/sonar/cpi-five-images-2026-11-24/diary-ui-after-chrome/coverage-annex-diary.json)
```

Detener la secuencia si falla cualquier comando. `test:coverage` se ejecuta
**antes** de los mapas privados y E2E porque limpia su directorio. El merge
comprueba código observado/publicado/mapeado y conserva los denominadores de
unidades; no fusiona posiciones de ramas incompatibles. Firefox verifica el
comportamiento; el LCOV de navegador se obtiene de Chrome.

Los tres drivers comparativos adicionales requieren las copias coherentes y
medios del checkpoint descritos en `cpi-five-images-2026-11-24/owned-comparison.json`.
Antes de ejecutarlos, verificar PID/start_ticks de mongod y backend, dbpath,
puerto y nombres de bases temporales. No sustituir sus URL por MathV0: Cornell
y las actividades guardan registros de ensayo. El driver del Diario sólo lee y
exporta. Si esas copias ya no existen tras un reinicio, reconstruirlas desde las
capturas privadas conservando rutas lógicas y medios; no omitir los errores ni
atribuir sus observaciones a un recorrido no ejecutado. Las catorce cohortes del
runner se preparan solas y siguen siendo reproducibles sin estas copias.

El checkpoint actual recoge **catorce cohortes desde fuente**, sin generar ni
probar otra AppImage. Las nueve originales son lectura, autoría, notas,
exportación, históricos, Biblioteca, Diario, Cornell/CPI y herramientas
matemáticas. Se conservan ventana clonada, cierre/reapertura, diez documentos
complejos y recuperación tras reiniciar el backend propio. La nueva cohorte
`--note-actions` verifica copia/borrado de nota completa, recursos compartidos,
exportación y filtros recuperables. Sus casos históricos requieren el ZIP
privado ya localizado; CPI es un fixture canónico identificado, porque ese ZIP
no contiene CPI. La integral Python incluye caracterizaciones del legado.

Durante el desarrollo pueden ejecutarse las diez primeras cohortes y las
cuatro de autoría en llamadas separadas al mismo runner: se combinan sólo
observaciones aprobadas del mismo código publicado y mapeado. El runner añade
lectura como comprobación base en cada llamada; no duplica su crédito de cobertura.
Al regenerar el bundle se reobservan las cohortes necesarias para producir un
LCOV comparable; su evidencia funcional anterior no se descarta. No se acredita
cobertura antigua contra fuentes o hashes nuevos.

Las AppImages y sus verificaciones anteriores siguen documentadas en
LATEX_AUTHORING_CHECKPOINT.md; no contienen automáticamente los cambios de este
lote. Se conserva su infraestructura. Su generación y nuevas pruebas quedan
suspendidas hasta alcanzar la paridad acordada.

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

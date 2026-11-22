# Entorno cualificado y dependencias

Perfil elegido: CPython 3.13.16 ya instalado mediante uv; se creó .venv separado.
No se reinstaló Python ni se alteró mathdbmongo/Python 3.10, Pyenv global o servicios
ajenos. El proyecto declara >=3.11.5,<3.14 por los requisitos de las correcciones;
la cualificación de esta fase se realizó en 3.13.16, no se inventa una matriz
completa de ejecuciones 3.11/3.12. Python 3.10 terminó soporte en octubre de 2026.

Fuentes oficiales consultadas:
[estado Python](https://devguide.python.org/versions/),
[soporte Pillow](https://pillow.readthedocs.io/en/stable/installation/python-support.html),
[Pillow 13](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html),
[Streamlit 1.67](https://pypi.org/pypi/streamlit/1.67.0/json),
[pytest](https://docs.pytest.org/en/stable/changelog.html),
[uv](https://docs.astral.sh/uv/guides/install-python/).
La metadata exacta de PyPI se conserva en el directorio local de evidencia.

| Lote | Antes | Seleccionado | Razón / verificación |
|---|---|---|---|
| Imágenes/UI | Pillow 12.3, Streamlit 1.59.2, streamlit-pdf 1.0.8 | 13.0.0 / 1.67.0 / 2.1.0 | Streamlit anterior impedía Pillow 13 (<13); el nuevo exige componente PDF >=2.1. Carga PNG/WebP, transparencia, branding, PDF/preview, AppTest y Chrome. |
| Red | dnspython 2.8, Tornado 6.5.9 | 2.9.2 / 6.6.1 | Correcciones requieren Python >=3.11. Configuración/health, driver y procesos reales; Jupyter conserva Tornado corregido. |
| Pruebas/HTML | pytest 8.4.2, SoupSieve 2.10 | 9.0.3 / 4.1.3 | Versión mínima corregida del major pytest, conservando plugins verificados; exportación notebook/selección HTML y suite real. |
| Instalación | pip 22.0.2, setuptools 59.6 | 26.3 / 84.2.1 | Grupo build opcional fijado en Poetry; wheel real y exclusión de privados comprobados. |

Se conservan los demás pins compatibles. nbconvert 7.17.1, nbformat 5.10.4 y
BeautifulSoup4 4.15.0 ya estaban en el lock/perfil como transitivas y ahora se
explicitan como imports de la verificación en ambos mecanismos de desarrollo.
No se actualizaron por esa declaración.

Auditoría completa: antes 178 entradas de paquetes, 177 públicos y el propio
mathmongo sin correspondencia PyPI; ahora 160 entradas, **159 públicos auditados**
y el mismo paquete propio no publicado. Cero avisos en la consulta del perfil nuevo.
Los siete paquetes afectados siguen presentes: su reducción a cero corresponde a
correcciones de versión, no a quitarlos de la auditoría. Los 64 avisos únicos/76
entradas previas se conservan por alias en PYTHON_ADVISORIES.csv.

El perfil nuevo tiene 19 nombres menos y uno más: desaparecen transitivas antiguas
de Streamlit/Python y extras preexistentes no declarados (por ejemplo Selenium,
Trio, tk, build). No se desinstalaron del entorno anterior. ipython-pygments-lexers
se incorpora por la resolución compatible con el intérprete nuevo. Las consultas
se aplican a todo lo instalado en cada perfil, sin filtros de severidad.

npm audit usa el mismo alcance completo prod/dev/optional/peer que el antecedente
21 a cero; package-lock no cambia en esta fase. El último JSON da cero. El cambio
de instrumentación incluye scripts MJS en V8 y está cuantificado en CHECKPOINT;
no cambia el alcance de paquetes ni las exclusiones de fuentes Sonar.

## Reproducir el perfil actual

Con Poetry 2.1.2 y Python 3.13 disponible, desde un checkout sin otro .venv:

```bash
uv venv --python 3.13.16 .venv
poetry env use .venv/bin/python
poetry install --with build
.venv/bin/python -m pip check
poetry check --lock
make test-coverage
make test-mongo-e2e
```

El lock fija el conjunto; requirements*.txt siguen siendo la entrada pip compatible,
con las dependencias de verificación declaradas. Para la reproducción exacta de
este perfil completo se usa Poetry, que incluye también las herramientas Jupyter.
Makefile usa VENV_DIR=.venv; se puede seleccionar explícitamente otro directorio.
Los harness ejecutan el mismo sys.executable con el que se invocaron.

El ZIP se mantiene fuera de Git. Se verifica antes del cierre con la constante
AUTHORITATIVE_ZIP_SHA256, sin regenerarlo ni sustituir el corpus. Las pruebas
escriben en fakes o mongod propio con PID/dbpath/puertos comprobados y XDG temporal.

## Referencia anterior y vuelta atrás

Los commits anteriores y mathdbmongo permanecen intactos. Para investigar la
referencia, crear un worktree aparte en 41c25714 y ejecutar allí el Python 3.10
anterior con PYTHONPATH apuntando a ese worktree y el runner de calidad de esa
revisión. No usar su console script editable desde otro checkout sin fijar la
ruta de fuentes. No cambiar el intérprete/lock de la rama activa para comparar.

La referencia anterior omitía 50 pruebas del ZIP; al suministrárselo reproduce el
fallo del hash semántico, no una suite histórica completamente aprobada. El plan
s1c1-v2 tiene un hash nuevo documentado; las autorizaciones v1 no se adoptan como
v2. No se cambiaron esquemas/IDs de registros existentes ni se aplicó una migración
a la base habitual. Para retirar un lote, usar git revert en una rama revisada,
resolver dependencias y repetir las verificaciones afectadas; no reset/clean.

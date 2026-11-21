# Dependencias revisadas

Entorno original: Python 3.10.12; pip/Poetry con pyproject, poetry.lock y constraints;
Node 24.15.0 / npm 11.12.1 con package-lock.json. pip check inicial y posterior:
sin incompatibilidades. Se conserva soporte Python >=3.10,<3.14 y React 19.

## Defectos confirmados y cambios

`poetry check --lock` fallaba antes: el lock contenía pandas 3.0.3 aunque la app
exigía >=2.3,<2.4. Se regeneró conservando los demás paquetes cuando eran compatibles;
pandas queda en 2.3.3, como el entorno docente ya verificado. No se migró el formato
Poetry ni se hizo una actualización general. pytest-cov/coverage quedan declarados
en ambos mecanismos de desarrollo. Se conservaron avisos de deprecación de Poetry.

Se consultó la base pública de avisos con npm audit y pip-audit 2.10.1, este último
en `.tools/python-audit` separado. Los informes completos están en evidence/sonar.
Los avisos de dependencia no equivalen a explotación confirmada en esta aplicación.
No se enviaron fuentes a esos servicios; se consultaron nombres/versiones públicas.

Cambios Python compatibles, fijados tanto en pyproject/lock como en constraints:

| Paquete | Antes | Después |
|---|---|---|
| PyMongo | 4.17.0 | 4.18.3 |
| certifi | 2026.6.17 | 2026.11.20 |
| GitPython | 3.1.51 | 3.2.1 |
| urllib3 | 2.7.0 | 2.8.0 |
| Tornado | 6.5.7 | 6.5.9 |
| mistune | 3.3.3 | 3.3.4 |
| jupyter-server | 2.20.0 | 2.21.0 |
| JupyterLab | 4.6.1 | 4.6.4 |
| notebook | 7.6.0 | 7.6.3 |
| soupsieve | 2.8.4 | 2.10.0 |

El rango PyMongo pasa a >=4.18.3,<4.19; tests de entorno y matriz de compatibilidad
reflejan la corrección. Los pins transitivos son deliberados controles de seguridad:
corresponden a dependencias ya instaladas/requeridas por Streamlit o Jupyter.
No se añaden paquetes nuevos al conjunto runtime por esos pins. La suite y los
E2E se repiten porque el driver Mongo y Tornado sí afectan flujos de la aplicación.

Frontend: PDF.js 6.1.200 -> 6.2.108, Vite 8.1.4 -> 8.1.6, Vitest 4.1.10 -> 4.1.12,
ESLint 10.7.0 -> 10.15.0 y typescript-eslint 8.64.0 -> 8.73.0. `npm audit fix` sin
`--force` actualizó transitivas permitidas por sus rangos; React y TypeScript se
conservaron. npm audit: 21 paquetes afectados (8 high, 13 moderate) -> 0.

Aviso PDF.js: [advisory del mantenedor](https://github.com/mozilla/pdf.js/security/advisories/GHSA-hq66-cqwq-w95j).
La app ya bloqueaba evaluación/XFA y usaba CSP; no se afirma que el exploit fuese
aplicable tal cual. Se elimina la versión afectada como defensa adicional. El build
publicado se regeneró con los scripts existentes, sin CDN, conservando los controles
de recursos/privacidad. Los cuatro inventarios de nombres de CMaps/fuentes/ICC/WASM
son idénticos (169/16/2/11); sólo cambia el namespace de versión y los binarios que
el proveedor cambió. Tests mantienen validación de versión, licencias, allowlist,
rutas locales, ausencia de QuickJS y referencias correctas del nuevo index.html.

## Pendientes deliberados (sin ocultar avisos)

pip-audit sobre TODO el entorno: 146 entradas en 15 paquetes -> 76 entradas en
7 paquetes. Algunas entradas son alias/duplicados de un mismo advisory; no son
146 ni 76 vulnerabilidades independientes. Se conserva JSON sin filtros.

| Paquete restante | Motivo para no forzar la actualización |
|---|---|
| Pillow 12.3.0 | Los avisos requieren 13.0.0, actualización mayor; necesita cualificar carga de imágenes, render y generación de documentos. |
| dnspython 2.8.0 | La corrección completa 2.9.2 declara Python >=3.11; mantener Python 3.10 impide aplicarla. Afecta especialmente URI mongodb+srv; los E2E usan loopback sin SRV. |
| Tornado 6.5.9 | Quedan avisos cuya corrección 6.6.1 declara Python >=3.11. Streamlit sigue limitado a loopback; esto no demuestra que todos los avisos sean inaplicables. |
| pytest 8.4.2 | Corrección reportada en 9.0.3, mayor de una herramienta de pruebas; requiere validar plugins/contratos de la suite. |
| soupsieve 2.10.0 | Avisos restantes requieren 3.x/4.x. Es transitoria de herramientas HTML/Jupyter; no hay import directo de la app. |
| pip 22.0.2 / setuptools 59.6.0 | Herramientas antiguas preexistentes del venv, no empaquetadas por la app. Se propone renovar el entorno de construcción por separado y repetir instalación limpia. |

No se añadieron ignores, supresiones ni excepciones de advisories. La propuesta
concreta es cualificar Python 3.11+ y Pillow 13 con una nueva matriz/entorno y validar
notebooks/herramientas mayores antes de cambiar la instalación docente. Estos
pendientes impiden afirmar que todo el entorno esté libre de vulnerabilidades.

## Evidencias y repetición

```bash
mathdbmongo/bin/python -m pip check
PATH="$PWD/mathdbmongo/bin:$PATH" poetry check --lock
cd frontend/advanced-reader
npm ci
npm audit --json
npm run typecheck
npm run lint
npm test
npm run build
```

Para la auditoría Python adicional, desde la raíz:

```bash
python3 -m venv .tools/python-audit
.tools/python-audit/bin/pip install pip-audit==2.10.1
.tools/python-audit/bin/pip-audit --path mathdbmongo/lib/python3.10/site-packages --format=json
```

Ese último comando devuelve no cero mientras existan avisos. El servicio público
puede actualizar sus datos: conservar fecha y versiones al comparar.

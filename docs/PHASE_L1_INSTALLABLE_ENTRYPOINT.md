# Fase L1: punto de entrada instalable de MathMongo

## Objetivo y estado anterior

L1 proporciona un único arranque instalable mediante `mathmongo` y `python -m mathmongo`, sin reescribir Streamlit ni implementar todavía el instalador Linux. Antes, `run_gui.py` ejecutaba `editor/editor_streamlit.py` mediante una ruta relativa al directorio actual, duplicaba comprobaciones y no propagaba el retorno de Streamlit. `app/main.py` importa toda la UI y por ello no es adecuado como CLI: importar la aplicación activa efectos Streamlit. `interface.py` es una interfaz de terminal histórica y separada.

## Arquitectura seleccionada

Se creó el paquete `mathmongo`, distinto del módulo existente `mathdatabase.mathmongo`. El nombre coincide intencionalmente con la distribución Poetry y no sustituye ningún import existente.

```text
console script / python -m mathmongo / run_gui.py
                    |
                    v
            mathmongo.cli:main
                    |
                    v
       mathmongo.launcher:launch_mathmongo
          | validaciones y resolución
          v
sys.executable -m streamlit run <ruta instalada>
```

`argparse` evita añadir dependencias. `launcher.py` concentra resolución, validación de dirección/puerto, comprobación de Streamlit y MongoDB, construcción del comando, ejecución y códigos de salida. Los imports de CLI no importan Streamlit, PyMongo ni la UI. `subprocess.run` conserva stdout/stderr, facilita pruebas e informa el código de salida; Ctrl+C se traduce a 130. No se usa `shell=True`.

## Comandos

```bash
mathmongo
mathmongo --help
mathmongo --version
mathmongo run
mathmongo run --port 8502
mathmongo run --address 127.0.0.1
mathmongo run --no-browser
python -m mathmongo
```

El comando sin subcomando equivale a `run`. `--no-browser` añade la opción oficial de Streamlit `--server.headless true`.

## Resolución de rutas y recursos

El lanzador usa `importlib.util.find_spec("editor")` y la ubicación instalada real del paquete, nunca `Path.cwd()`. Por tanto funciona desde `/tmp`, rutas con espacios o el directorio personal después de instalar la distribución. No importa `editor_streamlit.py` durante la resolución.

Poetry incluye ahora `mathmongo`, el módulo superior `mathkb_config.py` y `templates_latex/**` en wheel y sdist. Los paquetes `editor`, Cornell, CPI, exportadores, esquemas y visualizaciones ya estaban declarados. La inspección del wheel confirmó `editor/editor_streamlit.py`, estilos, clases, plantilla CPI e imagen Cornell. Los recursos siguen junto al código instalado; la migración de datos/runtime a XDG queda para L2 y fases posteriores.

## Streamlit, dirección y puerto

El comando usa el mismo intérprete que ejecuta MathMongo:

```text
sys.executable -m streamlit run APP --server.address localhost --server.port 8501
```

Sólo se aceptan `localhost`, `127.0.0.1` y `::1`; `0.0.0.0` y direcciones externas se rechazan. La estrategia L1 para un puerto ocupado es fallar claramente y sugerir `--port`; no se selecciona otro silenciosamente, no se reutiliza un servidor y no se mata ningún proceso.

## MongoDB y LaTeX

Se conserva MongoDB local en `mongodb://localhost:27017`, sin instalar, arrancar, detener, migrar ni modificar bases. Antes de Streamlit se ejecuta `ping` con timeout; un fallo produce mensaje legible y código 1. La URI comunicada no contiene credenciales. La configuración completa se pospone.

LaTeX no es prerrequisito de arranque. No se comprueba ni instala `pdflatex`; los flujos PDF mantienen su diagnóstico cuando realmente lo necesitan.

## Compatibilidad con run_gui.py

`run_gui.py` permanece disponible y delega en `mathmongo.cli.main`, eliminando la ruta relativa y la duplicación. Ya no ofrece el prompt interactivo para continuar sin MongoDB: la política solicitada para L1 es fallo no interactivo y código distinto de cero.

## Empaquetado y versión

`pyproject.toml` declara:

```toml
[tool.poetry.scripts]
mathmongo = "mathmongo.cli:main"
```

La versión instalada procede de metadata generada desde `tool.poetry.version`. En un checkout todavía no instalado, se lee esa misma entrada de `pyproject.toml`; no existe una segunda constante de versión.

Se construyeron `mathmongo-0.1.0-py3-none-any.whl` y el sdist. En un venv temporal fuera del repositorio se instaló el wheel con `--no-deps` y pasaron `mathmongo --help`, `mathmongo --version`, `python -m mathmongo --help`, `python -m mathmongo --version` y la resolución de aplicación/recursos. `--no-deps` evitó red y fue suficiente para validar empaquetado; el servidor no se inició.

## Pruebas

Las pruebas cubren ayuda/versión, comando implícito y explícito, opciones, `sys.executable`, lista sin shell, loopback, puerto, cwd independiente, espacios, aplicación/Streamlit/MongoDB ausentes, puerto ocupado, retorno del proceso, Ctrl+C, ejecutor inyectable, imports sin efectos y wrapper histórico. La suite completa protege conceptos, Cornell, CPI, MongoDB y PDFs.

## Limitaciones y trabajo pospuesto

No se realizó validación gráfica ni se arrancó un servidor real. La ejecución completa requiere instalar las dependencias declaradas y disponer de MongoDB local. La divergencia general entre `requirements.txt` y Poetry permanece fuera de L1.

Para L2 o fases posteriores quedan deliberadamente: XDG; migración de runtime, medios y exportaciones; backups coordinados; migraciones de esquema; `mathmongo doctor`; instalación/configuración avanzada de MongoDB o TeX Live; credenciales; `.desktop` e icono; instalador Bash; actualizador/desinstalador; `.deb`; AppImage; Windows y macOS.

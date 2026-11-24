# MathMongo Estudio — AppImage experimental x86_64

La primera imagen integra el frontend React publicado, CPython portable 3.13.16,
los servicios FastAPI y 19 distribuciones Python fijadas en `runtime.lock.json`.
Reutiliza `mathmongo.advanced_reader.launcher`: no inicia Streamlit ni otro backend.
No instala servicios ni cambia sysctl. La información mutable sigue la política
XDG existente, fuera del ejecutable. El terminal debe permanecer abierto;
Ctrl+C detiene este servidor. La ventana nativa de escritorio sigue pendiente.

**MongoDB es externo:** tiene que estar instalado y accesible con la configuración
o URI elegidas. Este paquete no arranca, administra ni incluye un mongod.
Para compilar PDF necesita las herramientas del host `pdflatex`, `pdftoppm`,
`bwrap`, `prlimit` y los paquetes TeX del documento. Sin el aislamiento requerido,
la compilación informa que no está disponible; nunca usa una salida sin sandbox.
No necesita Docker, Sonar, npm, Node, un venv o herramientas de desarrollo para
usarse. El navegador sigue siendo externo.

Artefacto local probado:

```
dist/MathMongo-187a5a9c-experimental-x86_64.AppImage
sha256 90788e8c254872c3ff6eee9d04f01b270b9bee8495febb37685db4fd837c675a
```

Payload y frontend construidos en `187a5a9c`, con Biblioteca, Diario, núcleo
Cornell/CPI, preferencias editoriales y fuente LaTeX completa. Tamaño: 40 114 680 bytes;
se conservan las diecinueve distribuciones Python fijadas. El frontend incluye
los ocho módulos mínimos CodeMirror/Lezer y sus licencias, cargados bajo demanda.
Las imágenes `098cab43` y `f00aa5ac` permanecen intactas, con sus SHA256 anteriores; las imágenes de
checkpoints previos tampoco se sobrescribieron. No se distribuye todavía
como versión estable ni se afirma compatibilidad con otras distribuciones Linux.
Se comprobó desde un directorio temporal distinto del repositorio, con intérprete
`-I -B`, sin PYTHONPATH del repositorio, venv, ni Streamlit disponible.

Desde la raíz del repositorio, usando la configuración Mongo existente:

```bash
dist/MathMongo-187a5a9c-experimental-x86_64.AppImage --appimage-extract-and-run --port 8766
```

Abrir `http://127.0.0.1:8766/study`. Para elegir explícitamente una biblioteca,
añadir `--database nombre_de_tu_base`. La opción `--bundle-check` sólo comprueba
el contenido/las dependencias del paquete; no conecta ni prepara MongoDB.
Se probó la modalidad de extracción y ejecución sin exigir FUSE. No se cambia
HOME ni se añaden configuraciones del usuario a la imagen.

Desde Cuaderno se accede a Cornell y CPI. Los núcleos nuevos permiten edición por
región, recuperación, páginas, pie/marca de texto y TEX/PDF; las operaciones avanzadas
siguen delimitadas en `docs/audits/sonarqube-2026-11/mandala/LATEX_AUTHORING_CHECKPOINT.md`.
No se presentan los formatos completos como totalmente migrados.

Se ejecutaron trece cohortes por navegador, Chrome y Firefox, contra MongoDB
temporal real desde este paquete. Después se detuvo únicamente el grupo del
backend propio y se verificó el cierre de su socket antes del nuevo arranque.
El runtime nuevo recuperó cinco notas y veintidós conceptos; el hash del estado
Mongo completo coincidió antes/después. Streamlit no está disponible en el runtime.
Las capturas, resultados con run_id y pruebas de reinicio están conservadas en
`evidence/sonar/latex-parity-2026-11-24/package-final-{chrome,firefox}/`.
La imagen intermedia `79ca36f7` conserva un fallo de accesibilidad y no es la
entrega recomendada; tampoco se sobrescribió para ocultarlo.

## Construcción reproducible con las herramientas ya verificadas

```bash
.venv/bin/python -m scripts.build_react_appimage \
  --python-runtime /home/enriquedo/.local/share/uv/python/cpython-3.13.16-linux-x86_64-gnu \
  --appimagetool .tools/appimage/appimagetool-1.9.1-x86_64.AppImage \
  --runtime-file .tools/appimage/runtime-x86_64 \
  --output .tools/appimage/MathMongo-nueva-experimental-x86_64.AppImage
```

El destino debe ser nuevo. No borra AppDirs/imágenes previos ni descarga o
instala dependencias. Copia únicamente recursos rastreados de directorios
permitidos, conserva licencias de dependencias y rechaza symlinks propios,
hooks pth y runtimes enlazados fuera de su directorio. Excluye pruebas, ZIP/PDF,
evidencias, credenciales, perfiles y bases de datos. El manifiesto contiene la
revisión y el inventario de recursos/dependencias. El primer intento detectó
la falta del pyproject raíz para recuperar la versión; `11dfe468` lo corrigió.

Herramientas consultadas/obtenidas de sus fuentes oficiales:
[AppDir y AppRun](https://docs.appimage.org/packaging-guide/manual.html),
[appimagetool 1.9.1](https://github.com/AppImage/appimagetool/releases/tag/1.9.1),
[type2-runtime](https://github.com/AppImage/type2-runtime/releases/tag/continuous).
Las huellas publicadas por la API de releases se contrastaron antes de ejecutar:

- appimagetool: `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`.
- runtime: `617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46`.

El runtime continuous puede cambiar en origen; el constructor exige estos bytes
exactos. Conservar las copias verificadas locales. No sustituye silenciosamente
una versión nueva ni promete que una descarga futura mutable coincida.

## Pruebas del artefacto

```bash
.venv/bin/python tests/run_independent_study_e2e.py \
  --appimage=dist/MathMongo-187a5a9c-experimental-x86_64.AppImage \
  --browser=chrome --authoring --notes --document-export --legacy \
  --library --notebook --structured --math-tools --clone-drafts --latex-parity
```

Repetir con `--browser=firefox`. Cada ejecución es dueña del PID/dbpath/puerto
Mongo, base UUID, perfil del navegador, FastAPI y directorios XDG temporales.
Se comprobaron pasaje→nota→concepto→esfera→origen, autoría/bibliografía/PDF,
notas concurrentes, compilación antes de guardar, IDs optativos y cinco cuerpos
históricos exactos, el corpus de diez casos, clon/cierre de ventanas y recuperación
tras reinicio. El caso helicoidal requiere sus definiciones originales para PDF;
su cuerpo se conserva íntegro. Evidencia separada de los ensayos desde código fuente en
`evidence/sonar/packaged-study/{chrome,firefox}`.

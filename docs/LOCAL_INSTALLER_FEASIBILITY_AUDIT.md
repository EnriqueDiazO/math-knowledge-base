# Auditoría de viabilidad de instalador local MathMongo

## Resumen ejecutivo y criterio final

**Criterio: viable con prerrequisitos.** MathMongo puede ofrecer primero un instalador Linux de usuario basado en script + entorno virtual administrado, pero todavía no tiene un comando instalable, configuración unificada, migraciones/versionado de esquema ni separación entre código y datos. MongoDB y TeX Live son los principales prerrequisitos externos. No se recomienda aún `.deb` ni AppImage.

## Estado actual, estructura y arranque

La aplicación Streamlit principal es `editor/editor_streamlit.py`; `run_gui.py` comprueba dependencias y MongoDB y ejecuta `python -m streamlit run editor/editor_streamlit.py --server.port 8501 --server.address localhost`. `app/main.py` importa la aplicación, mientras `interface.py` es una interfaz CLI antigua dependiente de VS Code. El proyecto Poetry se llama `mathmongo` 0.1.0, requiere Python `^3.10`; no declara `console_scripts`, `__main__.py` ni versión máxima probada. `requirements.txt` diverge del `pyproject.toml` (incluye `tk`, omite versiones y pandas no está declarado explícitamente pese a importarse).

Paquetes Python principales: Streamlit, PyMongo, Pydantic, pandas (transitivo/no declarado), NetworkX, Matplotlib, Jinja2, PyYAML, Typer, PyVis, python-slugify, markdown-it-py, RapidFuzz, bibtexparser, streamlit-ace y Plotly. Varias restricciones usan `*` o rangos amplios; no hay lockfile observado.

Binarios externos: `pdflatex` es el motor efectivo de conceptos, Cornell, CPI, notas y validación; `chktex` y `lacheck` son opcionales para lint; Quarto se usa en exportaciones específicas; `pdfinfo`/`pdftotext` aparecen en pruebas. Los scripts de acceso directo e instalación de ChkTeX/Quarto son auxiliares, no un instalador integral. No se encontró uso de `xelatex`, `lualatex` o `latexmk` para el flujo productivo.

## Persistencia y rutas

Hoy `PROJECT_ROOT` contiene código y estado. Deben persistir MongoDB (`concepts`, `relations`, `latex_documents`, `knowledge_graph_maps`, `media_assets`, `latex_notes`, worklogs/backlog/reviews/deliverables), `media/images`, plantillas personalizadas si se habilitan, exportaciones y respaldos. `runtime/`, PDFs de preview, auxiliares y cachés son regenerables. Posiciones/configuración de grafos están en `knowledge_graph_maps`; imágenes pueden combinar metadatos MongoDB con archivos locales, por lo que respaldo/restauración debe ser atómico entre ambos.

Propuesta futura: aplicación en un venv versionado bajo `~/.local/share/mathmongo/app/`; configuración/URI en `~/.config/mathmongo/`; datos de archivos en `~/.local/share/mathmongo/data/`; runtime en `~/.cache/mathmongo/`; logs en `~/.local/state/mathmongo/`; exportaciones configurables en Documentos. Actualizar debe instalar una versión nueva, ejecutar migraciones comprobables y cambiar un enlace `current` sólo tras éxito. Desinstalar debe retirar lanzador, venv y `.desktop`, conservando datos/configuración por defecto y ofreciendo borrado explícito separado.

La búsqueda sistemática no encontró rutas absolutas reales `/home/enriquedo` o `/home/enrique` en código; sólo un ejemplo negativo en documentación. Hallazgos importantes: muchas rutas derivan de `PROJECT_ROOT`; `Path.home()/math_knowledge_pdfs` está codificada como exportación; `data/` en la CLI antigua depende del cwd. Los `localhost:27017`, `8501` y rutas de runtime son valores por defecto configurables pendientes, no rutas específicas de equipo.

## MongoDB

La base predeterminada es `mathmongo`, URI `mongodb://localhost:27017` (también `127.0.0.1`). `MathMongo.ensure_indexes()` crea índices únicos para conceptos `(id, source)`, documentos LaTeX `(id, source)` y relaciones `(desde, hasta, tipo)`, además de índices de mapas y recursos. `scripts/install_cuaderno_mode.py` inicializa colecciones adicionales y acepta variables `MONGODB_URI`/`MONGO_URI` y `MONGODB_DB`/`MONGO_DB`/`DB_NAME`, pero la UI no centraliza esa configuración.

- A, exigir MongoDB activo: menor complejidad, pero instalación manual y soporte distro-específico.
- B, instalarlo: exige privilegios/repositorios, aumenta mantenimiento y riesgo de interferir con instancias existentes.
- C, instancia embebida administrada: aislamiento y UX mejores, pero gran responsabilidad de procesos, puertos, upgrades, backups y recuperación.
- D, local o externo configurable: mejor destino; para v1 combinarlo con A, detectando y explicando el prerrequisito.

Recomendación v1: opción D con MongoDB preinstalado/externo, autenticación opcional y diagnóstico; no instalar ni administrar el daemon. Antes de migraciones, backup verificable. Nunca borrar una base al desinstalar.

## LaTeX

Todo el PDF productivo usa `pdflatex` con estilos locales y paquetes TeX diversos; una instalación mínima puede fallar por paquetes no incluidos. TeX Live completo simplifica compatibilidad pero ocupa varios GB y no debe instalarse silenciosamente. V1 debe detectar `pdflatex`, compilar un documento diagnóstico y mostrar paquetes faltantes con instrucciones por distribución; ofrecer instalación opcional explícita después. ChkTeX/lacheck, Quarto y utilidades Poppler no son obligatorios para arrancar.

Un futuro `mathmongo doctor` debe comprobar Python/venv, imports y versiones, MongoDB/conectividad/permisos/índices, `pdflatex` y paquetes, binarios opcionales, escritura en XDG, puerto disponible, navegador y coherencia entre recursos MongoDB y archivos.

## Seguridad

| Riesgo | Severidad | Observación y acción |
|---|---|---|
| LaTeX con entrada del usuario | Alta | Puede leer/escribir o consumir recursos; usar timeouts ya existentes, directorio confinado, límites y revisar opciones de TeX. |
| MongoDB sin credenciales por defecto | Alta | Mantener sólo loopback, soportar URI protegida y no registrar secretos. |
| Datos MongoDB + imágenes no transaccionales | Alta | Backup conjunto, manifiesto y restauración primero en staging. |
| Dependencias sin fijar/requirements divergente | Alta | Fuente única, lock y hashes antes de instalar. |
| URI MongoDB editable | Media | Validar/esconder credenciales y permisos de configuración 0600. |
| Puerto Streamlit | Media | Ya usa `localhost`; mantener loopback, elegir puerto libre y no usar `0.0.0.0` por defecto. |
| Apertura `file://` | Media | Limitar a PDFs generados bajo runtime; nunca aceptar una ruta arbitraria desde el cliente. |
| Subprocesos externos | Media | El código revisado usa listas sin `shell=True`; mantenerlo y validar nombres/rutas. |
| Importación/restauración | Alta | Validar ZIP, traversal, tamaño y esquema; requerir confirmación y backup. |
| Permisos XDG/logs | Media | Directorios 0700, archivos sensibles 0600 y redacción de secretos. |

## Estrategia recomendada

Primera entrega: instalador Bash de usuario pequeño que detecte Python 3.10+, cree un venv, instale desde artefacto/lock, escriba configuración XDG, ejecute `mathmongo doctor`, y cree opcionalmente `.desktop` e icono. El paquete futuro debe añadir `mathmongo` y `python -m mathmongo`, lanzar Streamlit con ruta absoluta al recurso, elegir puerto loopback libre, controlar PID/instancia, abrir navegador, capturar logs y manejar señales. El `.desktop` ejecutaría el comando sin terminal y remitiría errores al log/una UI de diagnóstico.

## Matriz de bloqueos

| Componente | Estado actual | Bloqueo | Severidad | Acción propuesta |
|---|---|---|---|---|
| Paquete Python | Poetry parcial | Sin entry point/lock coherente | Alta | Consolidar dependencias y añadir CLI/`__main__` |
| Streamlit | Lanzador funcional | Ruta relativa, puerto fijo | Media | Lanzador robusto, puerto libre, PID y logs |
| MongoDB | Local por defecto, índices parciales automáticos | Config dispersa, sin migraciones/backups integrados | Alta | Config única, doctor y esquema versionado |
| LaTeX | `pdflatex` funcional | Paquetes/sistema no diagnosticados | Alta | Detector y compilación de prueba |
| Persistencia | Mezclada con repo | Actualización puede pisar estado | Crítica | Separación XDG y migración conservadora |
| Recursos multimedia | Disco + MongoDB | Consistencia de backup | Alta | Manifiesto y backup/restauración conjunta |
| Seguridad | Loopback y subprocess list | TeX/credenciales/importación | Alta | Threat model y pruebas adversariales |
| Desktop | Script aislado existente | Sin CLI estable ni icono empaquetado | Media | Añadir tras estabilizar lanzador |

## Viabilidad, alcance mínimo y pruebas limpias

No hay bloqueo conceptual para Linux; es razonable limitar v1 a una distribución documentada y ampliar después. Automatizable: venv, Python deps, configuración, índices idempotentes, diagnóstico, acceso directo y lanzamiento. Manual en v1: instalar/activar MongoDB y TeX Live, decidir URI/credenciales y autorizar migraciones/restauraciones. Riesgo de datos actual: medio-alto hasta separar persistencia y versionar migraciones.

Una máquina limpia debe probar instalación sin privilegios, rutas con espacios/no ASCII, MongoDB ausente/presente/protegido/remoto, LaTeX ausente/paquetes faltantes, puerto ocupado, reinicio, dos instancias, backup/restauración, upgrade/downgrade rechazado, desinstalación conservadora y todos los flujos PDF/medios/grafos.

## Hoja de ruta

- L0: auditoría (este documento) y especificación de `doctor`.
- L1: paquete instalable, `mathmongo` y `python -m mathmongo`.
- L2: instalador Linux de usuario con venv y configuración XDG.
- L3: configuración, diagnóstico e inicialización versionada de MongoDB.
- L4: detección y diagnóstico de LaTeX/paquetes.
- L5: `.desktop`, icono, logs y desinstalador conservador.
- L6: matriz CI/manual en instalaciones Linux limpias.
- L7: backups, migraciones, actualización atómica y rollback de aplicación.
- L8: evaluar `.deb`; AppImage sólo si se resuelve la integración de servicios/TeX.

Complejidad cualitativa: L1–L2 media; L3–L4 media-alta; L5 media; L6–L7 alta; L8 alta. Los problemas posponibles son empaquetados nativos, MongoDB administrado y TeX Live automático; no son posponibles la separación de datos, dependencias reproducibles, diagnóstico y seguridad de migración.

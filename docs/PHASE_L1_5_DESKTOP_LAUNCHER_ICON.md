# Fase L1.5: acceso directo Linux e icono

## Estado anterior y auditoría

El único instalador existente era `scripts/make_desktop_shortcut.sh`. Generaba `mathmongodb-run.desktop` directamente en `$HOME/Desktop` o `$HOME/Escritorio`, tomaba el repositorio desde `pwd` y ejecutaba `bash -lc 'make start && make run'`. Esto dependía del nombre/layout del checkout, activaba indirectamente `mathdbmongo`, abría una terminal (`Terminal=true`) y declaraba `Icon=utilities-terminal`. No instalaba una aplicación XDG ni un icono propio; esa configuración explica tanto el nombre “MathMongoDB (run)” como el icono genérico.

La búsqueda no encontró otro script competidor ni un logo oficial inequívoco. Las imágenes de `media/images` son contenido persistente del usuario y no deben reutilizarse como identidad de la aplicación.

## Decisión y arquitectura

El script histórico se conserva como wrapper compatible. Toda la lógica vive una sola vez en `mathmongo.desktop`, empaquetada para funcionar desde wheel:

```text
scripts/make_desktop_shortcut.sh
        -> mathmongo-desktop
        -> fallback: python3 -m mathmongo.desktop
```

Sin argumentos mantiene la compatibilidad anterior: instala el lanzador y crea una copia en el escritorio. Para instalar sólo en el menú se usa `--no-desktop`. No se reimplementó el launcher Streamlit: el `Exec` invoca el comando L1 `mathmongo run`.

## Icono

La fuente maestra original está en `assets/icons/mathmongo.svg`. Combina un libro/notas, una pila de datos y un sigma geométrico, sin texto, emojis, marcas externas, fuentes ni recursos remotos. Está diseñado con contraste azul, blanco y ámbar para tamaños pequeños y temas claros/oscuros.

`assets/icons/mathmongo-256.png` se generó a 256×256 desde el SVG usando ImageMagick disponible en el entorno. ImageMagick no es dependencia runtime.

## Archivo desktop

La entrada estable se llama `mathmongo.desktop` y contiene:

```ini
[Desktop Entry]
Type=Application
Name=MathMongo
GenericName=Math Knowledge Base
Comment=Mathematical knowledge base with MongoDB, LaTeX and Streamlit
Exec="/ruta/absoluta/bin/mathmongo" run --desktop-launch
Icon=mathmongo
Terminal=false
StartupNotify=true
Categories=Education;Science;Office;
Keywords=mathematics;knowledge;MongoDB;LaTeX;Streamlit;
```

La ruta del ejecutable se escapa conforme al campo `Exec`; no hay shell, `source`, venv hardcoded ni parámetros arbitrarios. `--desktop-launch` conserva el mismo launcher y habilita logs XDG para una ejecución sin terminal. Se omite `TryExec`: GTK no interpreta comillas en ese campo de forma portable, por lo que una ruta con espacios ocultaría la aplicación aunque `Exec` fuera válido.

## Resolución del ejecutable

El orden es:

1. `--executable`;
2. `MATHMONGO_EXECUTABLE`;
3. `command -v mathmongo` mediante `shutil.which`;

La ruta se resuelve como absoluta, debe ser archivo ejecutable y debe responder exitosamente a `--help`, que no inicia Streamlit.

## Rutas XDG

Con `${XDG_DATA_HOME:-$HOME/.local/share}` como base:

- `applications/mathmongo.desktop`;
- `icons/hicolor/scalable/apps/mathmongo.svg`;
- `icons/hicolor/256x256/apps/mathmongo.png`.

El escritorio opcional se obtiene con `xdg-user-dir DESKTOP`; si falta o devuelve vacío, se usa `$HOME/Desktop`. Sólo la copia del escritorio recibe permiso ejecutable. `gio metadata::trusted` se intenta de forma no fatal cuando existe. También son no fatales las actualizaciones de las cachés de aplicaciones/iconos.

No se usa `sudo` ni se escribe en `/usr/share`.

## Comandos probados

Desde un wheel instalado:

```bash
mathmongo-desktop --install --no-desktop
mathmongo-desktop --install --desktop
mathmongo-desktop --install --desktop --dry-run
mathmongo-desktop --install --executable /ruta/al/bin/mathmongo
mathmongo-desktop --uninstall
mathmongo-desktop --uninstall --dry-run
```

Wrapper histórico desde un checkout:

```bash
scripts/make_desktop_shortcut.sh --install --desktop
scripts/make_desktop_shortcut.sh --uninstall
```

Instalar dos veces reemplaza los mismos archivos estables; no crea duplicados. Desinstalar repetidamente es seguro.

## Alcance de la desinstalación

Sólo elimina el `.desktop` de applications, la copia opcional del escritorio, el SVG y el PNG instalados por esta integración. No elimina entorno, código, configuración, logs, MongoDB, conceptos, Cornell, CPI, grafos, imágenes, PDFs, backups ni exportaciones. Los cachés generales generados por el escritorio no se eliminan porque pueden pertenecer a otras aplicaciones.

## Dry-run y pruebas

Dry-run valida el ejecutable y muestra ejecutable, applications, iconos, launcher, escritorio, `Exec` y acciones, pero no crea directorios ni archivos. Las pruebas usan HOME/XDG temporales, herramientas simuladas y ejecutables falsos; no inician Streamlit ni abren navegador.

Se cubren resolución explícita/entorno/PATH, rutas con espacios y Unicode, XDG, xdg-user-dir y fallback, campos desktop, iconos, permisos, instalación/desinstalación idempotente, preservación de datos ajenos, dry-run, ausencia de shell/rutas del equipo y compatibilidad del wrapper. Una instalación real en XDG temporal fue aceptada por `desktop-file-validate`; éste sólo emitió una sugerencia no fatal por las múltiples categorías solicitadas.

## Validación manual y limitaciones

No se contó con validación visual de una sesión de escritorio: no se afirma que GNOME/KDE haya mostrado visualmente el icono ni que el clic haya abierto el navegador. `Terminal=false` puede enviar errores al journal de la sesión; la infraestructura completa de logs queda para L2. La metadata de confianza depende del escritorio y `gio` puede no soportarla en todos los sistemas.

## Relación con L2

L1.5 dejó lista la integración de escritorio reutilizable por el futuro instalador. L2 añadió XDG para datos, runtime y logs, y reutiliza `mathmongo-desktop` con `--desktop-launch`. Siguen pospuestos el instalador Bash integral, `doctor`, MongoDB/TeX Live, actualizaciones, desinstalación general, `.deb` y AppImage.

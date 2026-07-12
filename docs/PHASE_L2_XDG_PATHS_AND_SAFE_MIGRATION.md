# Fase L2: rutas XDG y migración segura

## 1. Objetivo y arquitectura anterior

L2 separa recursos instalados de configuración, datos, runtime, caché, estado y exportaciones. Antes, `PROJECT_ROOT` cumplía simultáneamente funciones de raíz de recursos y escritura: importar `mathkb_config` creaba `runtime`, exports y logs; importar `editor.pdf_export` creaba `exported_notes/_build`. En un wheel, esas rutas son `site-packages`.

## 2. Matriz de rutas auditadas

| Ruta anterior | Consumidor | Tipo | Persistente | Destino L2 | Riesgo anterior |
|---|---|---|---:|---|---|
| `templates_latex`, `quarto_book`, `assets/icons`, `editor/data` | renderers/UI | Recurso read-only | No | paquete instalado | Escritura accidental crítica |
| `media/images` | medios, Cornell/CPI, DB export/import | Dato | Sí | `$XDG_DATA_HOME/mathmongo/media/images` | Pérdida al actualizar wheel |
| `runtime/*preview*`, split, builds LaTeX | Cornell/CPI/PDF | Runtime | No | `$XDG_RUNTIME_DIR/mathmongo` o caché | Escritura en repo/site-packages |
| `runtime/cornell_exports`, `cpi_exports` | proyectos/ZIP staging | Runtime exportable | Potencial | runtime nuevo; migración conservadora a data/projects | Mezcla con previews |
| `runtime/cleanup_backups` | mantenimiento | Backup | Sí | data/backups | Posible única copia |
| `runtime/logs` | mantenimiento | Estado/log | No | state/logs | Crecimiento y wheel read-only |
| `exported*`, `exportados` | PDFs/TEX | Exportación | Sí | Documents/MathMongo | Dependencia del checkout |
| `~/math_knowledge_pdfs` | conceptos | Exportación | Sí | export configurable/concepts | Ruta fija |
| `~/mathkb_backups` | backup DB | Backup | Sí | data/backups | Ruta fija |
| `~/math_knowledge_graphs` | grafo legacy | Runtime | No | runtime/knowledge_graphs | HOME no XDG |
| grafos root | mantenimiento | Histórico | Sí | data/graphs/legacy por copia | El flujo anterior movía/borraba origen |
| `/tmp/mathkb_*.pdf`, uploads ZIP | Cuaderno/import | Runtime | No | runtime/pdf_preview, runtime/imports | Colisión/ruta no controlada |
| `reports`, `quarto_book_build`, `data`, `plantillas`, `md_files` | herramientas | Estado/export/dato histórico | Sí | state, exports o data | cwd/repo |
| `.git`, venvs, caches, dist/build, auxiliares TeX | desarrollo/runtime | Exclusión | No | no migrar | Copia masiva peligrosa |

Las fixtures y documentación que mencionan rutas antiguas se conservan como evidencia, no como destinos de escritura.

## 3. Clasificación de recursos

Permanecen read-only en el wheel: estilos `.sty`, clases `.cls`, plantilla CPI, `lineas.png`, plantilla Quarto, iconos, código, esquemas y formatos base. Se copian sólo a un build/runtime o export explícito. `PROJECT_ROOT` queda como compatibilidad para recursos y fallback histórico, nunca como raíz general de escritura.

## 4. Esquema XDG y módulo central

`mathmongo.paths` es side-effect-free y expone funciones tipadas. Respeta variables XDG absolutas y rechaza valores XDG relativos usando el fallback seguro. Las demás rutas relativas de usuario se anclan explícitamente a `HOME`, nunca al cwd; `validate_mutable_path()` impide escribir dentro del árbol instalado y rechaza symlinks de hoja, intermedios o ancestros antes de resolver la ruta:

```text
config  ${XDG_CONFIG_HOME:-~/.config}/mathmongo
data    ${XDG_DATA_HOME:-~/.local/share}/mathmongo
cache   ${XDG_CACHE_HOME:-~/.cache}/mathmongo
state   ${XDG_STATE_HOME:-~/.local/state}/mathmongo
runtime ${XDG_RUNTIME_DIR}/mathmongo, si es válido/propio/escribible
        o ${XDG_CACHE_HOME:-~/.cache}/mathmongo/runtime
```

`ensure_user_directories()` es la única inicialización general explícita; importar el módulo no crea nada. Los directorios controlados usan modo 0700 cuando el sistema lo permite. La inicialización de configuración corrige también un directorio preexistente más permisivo.

## 5. Configuración

Se usa `config.json` en config XDG porque el proyecto soporta Python 3.10 y `tomllib` sólo está en 3.11. No se agregó dependencia. `initialize_config()` crea explícitamente el archivo 0600; `load_config()` sólo lee.

Campos: versión, URI/base Mongo, export directory, address/port Streamlit y navegador. Precedencia:

1. CLI explícita;
2. entorno (`MONGODB_URI`, `MONGO_URI`, `MONGODB_DB`, `MONGO_DB`, `DB_NAME` y variables `MATHMONGO_*`);
3. config JSON;
4. defaults existentes (`mongodb://localhost:27017`, `mathmongo`, `localhost:8501`).

Las URI se redactan antes de errores/logs; una URI malformada falla cerrada como `<redacted MongoDB URI>`. La UI enmascara el campo URI y sanea errores conocidos antes de mostrarlos o persistirlos. No se escriben credenciales completas.

## 6. Datos persistentes y compatibilidad

Nuevos medios se escriben sólo en `data/media/images`, conservando en Mongo la ruta lógica portable `media/images/<archivo>`. Para lectura se prueba XDG y luego el checkout histórico. Las rutas absolutas antiguas se convierten primero a su cola lógica `media/...`; si no existe copia XDG ni legacy, todavía se admite el archivo absoluto histórico existente. Un borrado nunca elimina el fallback histórico ni un absoluto antiguo. Las copias LaTeX y backups DB fusionan legacy y XDG, prevaleciendo XDG, y omiten raíces, ancestros e hijos symlink. Los snippets nuevos usan siempre la ruta lógica cuando puede recuperarse de una ruta absoluta histórica.

La UI, Cornell, CPI y Cuaderno usan el resolver común. Import DB restaura medios bajo data XDG; export DB incluye ambos árboles. MongoDB, documentos y colecciones no se migran ni modifican por L2.

## 7. Runtime y caché

Cornell usa `runtime/cornell_preview/cornell_preview.pdf`, split bajo `runtime/cornell/split` y staging editable bajo `runtime/cornell/editable_projects`. CPI usa `runtime/cpi_preview/cpi_preview.pdf` y su staging equivalente. Builds LaTeX, ChkTeX, preflight, imports y preview de fragmentos usan subdirectorios controlados. Los nombres de preview permanecen estables. La limpieza valida contención, no escanea raíces symlink, rechaza escapes y nunca resuelve un enlace candidato hacia su objetivo. Sólo elimina auxiliares del preview objetivo y su variante `_fit`. Los proyectos editables sólo reemplazan un directorio que tenga metadata regular del mismo formato MathMongo; un directorio ajeno se conserva y produce error. Sus ZIP rechazan enlaces tanto en la hoja de salida como dentro del proyecto.

Los grafos HTML temporales pasan a `runtime/knowledge_graphs`; `GrafoConocimiento.exportar_html()` ya no escribe al cwd por defecto.

## 8. Logs y estado

Ejecución en terminal conserva stdout/stderr. El `.desktop` añade `--desktop-launch`: `streamlit.log` se escribe en state/logs, modo 0600, y se conserva un `.1` al superar 1 MB. Fallos de preflight del launcher se registran en `launcher.log`, sin URI con credenciales. Los reportes LaTeX también pasan a state.

## 9. Exportaciones

La ruta se configura mediante config/`MATHMONGO_EXPORT_DIRECTORY`. Default: `xdg-user-dir DOCUMENTS/MathMongo`, con fallback `$HOME/Documents/MathMongo`. Rutas configuradas o introducidas como relativas se resuelven contra HOME, nunca cwd. Conceptos, notas, documentos, Quarto, backups y grafos tienen subdirectorios separados y sólo se crean al exportar. Quarto sólo reemplaza builds con un marcador propio regular; rechaza symlinks en destino, marcador o templates y destinos dentro del paquete. El export DB no reutiliza un staging ni ZIP preexistente.

## 10. Migración segura

Comandos implementados:

```bash
python -m mathmongo.migrate_xdg --status --legacy-root /ruta/al/checkout
python -m mathmongo.migrate_xdg --dry-run --legacy-root /ruta/al/checkout
python -m mathmongo.migrate_xdg --copy --legacy-root /ruta/al/checkout
```

La política es copiar + verificar SHA-256/tamaño + conservar origen. No sobrescribe contenido distinto; registra `conflict`. Si dos fuentes apuntan al mismo destino, hashes distintos bloquean ambas como conflicto y hashes iguales se consolidan en una sola copia, conservando el segundo origen como `duplicate` en el manifiesto. Es reanudable e idempotente y escribe un manifiesto 0600 en `state/migrations/xdg-migration-v1.json` sólo con `--copy`. Dry-run/status no escriben. Se excluyen symlinks y raíces con ancestros symlink, `.git`, venvs por nombre o `pyvenv.cfg`, caches con variantes por guion/guion bajo, dist/build, previews, auxiliares TeX, `.bak`, swaps y nombres terminados en `~`. Runtime valioso histórico (proyectos, backups y grafos legacy) se clasifica explícitamente; MongoDB nunca se toca.

## 11. Acceso directo Linux

Nombre, icono, XDG applications y `Terminal=false` se conservan. Únicamente se añadió la señal `--desktop-launch` para logs. `gtk-launch mathmongo` sigue usando el mismo entry point L1.

## 12. Empaquetado e instalación aislada

Wheel/sdist contienen sólo código y recursos base: iconos, templates LaTeX, Quarto y formatos. No contienen `media`, runtime, previews, configuración real, logs, backups ni exports. Las rutas mutables derivan exclusivamente de HOME/XDG del proceso, no de la ubicación del wheel.

La validación aislada instala el wheel sin red, usa HOME/XDG temporales, comprueba CLI/recursos, inicialización, config, runtime, log/export simulados y dry-run. El árbol `site-packages` se inspecciona para confirmar que no recibe archivos mutables.

## 13. Pruebas

Se prueban XDG custom, Unicode/espacios, runtime válido/fallback, imports sin mkdir, permisos, configuración/precedencia/redacción, exports configurables, medios relativos y absolutos XDG-first/legacy, export/import DB con Mongo falso, Cornell/CPI runtime, contención por symlink, preservación de proyectos ajenos, logs privados, migración dry/copy/idempotencia/colisiones/manifiesto/exclusiones y regresiones L1/L1.5/PDF/Mongo/Cornell/CPI.

## 14. Limitaciones, riesgos y tareas pospuestas

La migración de archivos no es un backup transaccional con MongoDB. Los proyectos antiguos dentro de runtime se copian conservadoramente, pero requieren revisión humana. `config.json` puede contener una URI aportada por el usuario; se protege con 0600, pero un almacén de secretos queda fuera de L2. La migración desde wheel requiere `--legacy-root` porque site-packages no permite inferir el checkout anterior de forma segura.

Quedan para L3: instalador Linux de usuario, `doctor`, instalación/detección guiada de MongoDB/TeX Live, backup coordinado, migraciones Mongo versionadas, actualizador/desinstalador, rollback, `.deb` y AppImage. Windows/macOS permanecen fuera de alcance.

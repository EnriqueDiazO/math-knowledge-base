# Implementación del tutorial COCID de Google Drive y Google Docs

## Estado inicial y puerta de auditoría

- Fecha de inicio: 2026-07-21 (America/Mexico_City).
- Repositorio real: `/home/enriquedo/PersonalProjects/math-knowledge-base`.
- Rama inicial: `main`.
- HEAD inicial: `c05be19a` (`fix(ui): persist Edit Concept update feedback`).
- Estado Git inicial: `## main...origin/main`; árbol limpio.
- `git diff --check`: sin incidencias.
- Historial inicial:
  - `c05be19a fix(ui): persist Edit Concept update feedback`
  - `2b6f939f feat(ui): import and paste references in Add Concept`
  - `43fe01b5 fix(bibliography): normalize BibTeX reference fields`
  - `4f0c7776 docs(pdf): rebuild Reading Space guide`
  - `207c7c8b docs(reading): refresh Reading Space guide and screenshots`
- Procesos coincidentes con Streamlit, pytest, Poetry o LaTeX: ninguno visible.
- Puertos 8501–8503: la consulta `ss` no pudo abrir netlink dentro del sandbox; no se detuvo ningún proceso.
- No se hizo pull, fetch, cambio de rama, reset, checkout, clean ni stash.

## Base seleccionada y activos COCID

La configuración XDG selecciona la base `mathmongo` en el MongoDB local. Una consulta de solo lectura confirmó:

- `latex_notes`: 5 documentos.
- `media_assets`: 0 documentos.
- `cornell_math_v1`: 0 documentos.
- `cpi_v1`: 0 documentos.

Se encontraron los dos activos solicitados en `~/Descargas`:

- `cocid_logo_transparent_2400.png`: 2400 × 2400, RGBA, alfa 0–255, 1,646,802 bytes.
- `cocid_watermark_transparent_2400_alpha10.png`: 2400 × 2400, RGBA, alfa 0–26, 1,521,243 bytes.

Se usará el logotipo de opacidad completa, pues permite controlar una sola vez la opacidad efectiva desde el contrato portable. La ruta de origen nunca se persistirá.

## Arquitectura reconstruida

### Cornell

La entrada de UI es `render_cornell_page()` en `editor/cornell/streamlit_page.py`. El estado editable conserva metadatos, `CornellDocument`, página seleccionada, nota seleccionada, dirty flag y navegación pendiente. Crear, editar y borrar delega en `editor/cornell/service.py`, que usa el CRUD existente de `MathMongo` para la colección compartida `latex_notes`. `editor/cornell/persistence.py` deriva siempre `latex_body` y `image_ids` del documento canónico y no confía en un cuerpo enviado por la UI.

Contrato actual persistido:

- `note_format = "cornell_math_v1"`.
- Metadatos normales: `title`, `date`, `project`, `context`, `tags`, `image_ids`, timestamps.
- `cornell.schema_version`, `cornell.template_id` y `cornell.pages`.
- Cada página contiene `page_id`, `order`, `cue`, `main`, `summary` y `source_refs`.
- Cada región contiene `heading`, `latex` e `image_ids` lógicos.
- `cornell.attribution` y `cornell.watermark` son opcionales para lectura legacy.

Las operaciones de página normalizan orden y conservan atribución y watermark. La eliminación de una nota no elimina medios. La duplicación disponible hoy es de páginas; no existe aún un servicio explícito para duplicar una nota completa.

### CPI

La entrada es `render_cpi_page()` en `editor/cpi/streamlit_page.py`. Sigue el mismo patrón de estado y CRUD mediante `editor/cpi/service.py` y `editor/cpi/persistence.py`.

Contrato actual persistido:

- `note_format = "cpi_v1"`.
- Los mismos metadatos normales de `latex_notes`.
- `cpi.schema_version`, `cpi.template_id` y `cpi.pages`.
- Cada página contiene `page_number` y las regiones `comprehension`, `production`, `integration`.
- Cada región contiene `heading`, `latex` e `image_ids` lógicos.
- CPI reutiliza los contratos opcionales `CornellAttribution` y `CornellWatermark`.

### Medios

`editor/utils/media_assets.py` guarda bytes bajo XDG Data (`LOCAL_MEDIA_IMAGES_DIR`) y persiste en `media_assets` un `asset_id` UUID, nombre seguro, MIME, SHA-256, tamaño, ruta relativa a XDG Data, referencias lógicas y descripción. Cornell y CPI guardan solamente `asset_id` en regiones y en `image_ids`. Los renderers resuelven el activo, rechazan `..`, validan extensiones y copian a un directorio controlado de compilación. El borrado físico solo ocurre al pedirlo explícitamente y cuando `concept_ids` y `note_ids` están vacíos.

Deficiencias encontradas:

- subir una marca desde la UI actual escribe archivo y documento `media_assets` antes de guardar la nota;
- un activo faltante hace fallar la preparación completa del render/proyecto en lugar de omitir solo la marca;
- la asociación de un activo subido para una nota nueva no se completa después de obtener el `_id`;
- el modelo no tiene `all_pages` y usa `scale` como relación de ancho sin nombrar esa semántica;
- PNG/SVG están permitidos en la UI de marca, pero no WebP;
- los rangos son opacidad 0–1 y escala 0.05–2, más amplios que el contrato solicitado.

### PDF, vista previa y proyectos

`editor/cornell/renderer.py` y `editor/cpi/renderer.py` generan documentos LaTeX de página completa con TikZ. La marca se dibuja primero dentro del `tikzpicture` overlay y las regiones se dibujan después, por lo que queda detrás. El mismo bloque se genera para cada página. La previsualización compartida en `editor/pdf_preview.py` valida ubicación XDG Runtime, firma `%PDF-`, contexto de sesión y expiración; no existe una vista previa HTML/MathJax independiente para Cornell o CPI.

`editor/cornell/project_export.py` y `editor/cpi/project_export.py` generan un proyecto LaTeX editable, copian cada imagen requerida una sola vez bajo `images/`, guardan metadatos lógicos y crean ZIP sin symlinks. No existe importador de esos proyectos editables. El backup/restauración de base en `editor/utils/db_export.py` y `editor/utils/db_import.py` ya incluye `latex_notes`, `media_assets` y archivos de medios con rutas relativas, inventario exacto y remapeo seguro de colisiones. Las exportaciones legacy sin branding siguen siendo válidas porque el campo es opcional.

## Reproducción de excepciones Streamlit

Se ejecutaron aplicaciones mínimas con `streamlit.testing.v1.AppTest` y una base falsa sin escrituras.

Secuencia:

1. abrir una nota Cornell nueva;
2. añadir una página;
3. ir a anterior y siguiente;
4. duplicar una página;
5. eliminar la copia;
6. repetir la secuencia en CPI.

Con una adaptación temporal exclusivamente en `/tmp` para el argumento de ancho, no hubo excepción en ningún rerun. En particular, no se reprodujo `check_session_state_rules`. Las claves principales observadas fueron `cornell_title`, `cornell_cue_heading`, `cornell_main_heading`, `cornell_summary_heading` y sus equivalentes CPI. El historial contiene `43851d43 fix(cornell): stabilize note navigation and editing`, que ya introdujo navegación pendiente y sincronización antes de instanciar widgets; no se atribuye una nueva causa sin evidencia.

Sí se reprodujo una excepción bloqueante antes de renderizar cualquier editor con el entorno instalado:

- Tipo: `TypeError`.
- Mensaje Cornell: `ButtonMixin.button() got an unexpected keyword argument 'width'`.
- Mensaje CPI: idéntico.
- Widget: botón `Nueva nota Cornell` / `Nueva nota CPI`.
- Clave: automática (`None`).
- Estado relevante: vista inicial `Nueva nota`, documento nuevo, índice de página 0, sin nota seleccionada.
- Causa: el entorno ejecuta Streamlit 1.47.1, mientras el lock fija 1.59.2 y el código usa la API nueva `width="stretch"`; `pyproject.toml` aún declara compatibilidad desde 1.35.

La corrección mínima será encapsular botones stretch en un helper compatible con ambas APIs y añadir una prueba AppTest de creación y reruns. No se hará una corrección especulativa de `check_session_state_rules` si no puede reproducirse.

Baseline focal previo a cambios: 177 pruebas pasaron y 3 fallaron en `tests/test_xdg_media_paths.py`. Los tres fallos son preexistentes y comparten una fixture `_FixedExportDatetime` que no implementa el nuevo uso de `datetime.now()` en `editor/utils/db_export.py`; no están relacionados con Cornell, CPI ni branding.

## Propuesta mínima de branding portable

Se conservará `cornell.watermark` / `cpi.watermark` como ubicación compatible y se evolucionará su versión implícita sin convertir notas legacy:

```json
{
  "enabled": true,
  "type": "image",
  "image_id": "uuid-logico",
  "opacity": 0.07,
  "scale": 0.70,
  "position": "center",
  "all_pages": true
}
```

`scale` seguirá siendo el nombre persistido por compatibilidad, documentado y validado como relación del ancho de página. Al leer datos antiguos, `all_pages` será `true`; al faltar todo el campo, el watermark completo queda desactivado y no cambia la apariencia. Los activos se compartirán por `asset_id` y SHA-256; duplicar una nota conservará la referencia lógica, y eliminar una nota solo quitará su referencia, nunca borrará un activo aún usado.

La UI mantendrá bytes de una carga nueva en un borrador de sesión aislado por formato e identidad de nota. La escritura de archivo/DB se hará solamente dentro de Guardar. Quitar o restablecer modificará solo el borrador hasta guardar. Los widgets usarán claves derivadas de tipo de nota + identidad de nota + campo; la identidad `new` tendrá un nonce estable de sesión.

En render, una referencia de marca ausente se excluirá con diagnóstico controlado, sin ocultar faltantes de imágenes de contenido. La marca se renderizará detrás del contenido, centrada, con opacidad y ancho validados; `all_pages=false` la limitará a la primera página.

Los proyectos LaTeX incluirán contrato, manifiesto de activos con SHA-256 y copia lógica única. El ciclo de backup/import general conservará el documento y activo sin ruta absoluta; se agregará una validación focal de round-trip.

## Archivos previstos

Archivos de código a modificar:

- `editor/cornell/models.py`
- `editor/cornell/identity.py`
- `editor/cornell/media.py`
- `editor/cornell/renderer.py`
- `editor/cornell/project_export.py`
- `editor/cornell/service.py`
- `editor/cornell/streamlit_page.py`
- `editor/cpi/identity.py`
- `editor/cpi/media.py`
- `editor/cpi/renderer.py`
- `editor/cpi/project_export.py`
- `editor/cpi/service.py`
- `editor/cpi/streamlit_page.py`
- `editor/utils/media_assets.py`
- `scripts/install_cuaderno_mode.py`

Archivos nuevos previstos:

- `editor/streamlit_compat.py`
- `editor/note_branding.py`
- `scripts/build_cocid_drive_docs_tutorial_assets.py`
- `scripts/seed_cocid_drive_docs_tutorial.py`
- `tests/test_note_branding.py`
- `tests/test_cocid_drive_docs_tutorial.py`
- evidencias no privadas bajo `docs/evidence/cocid_drive_docs_tutorial/`.

Pruebas existentes que se ampliarán solo cuando corresponda:

- `tests/test_cornell_persistence.py`
- `tests/test_cpi_persistence.py`
- `tests/test_cornell_renderer.py`
- `tests/test_cpi_renderer.py`
- `tests/test_cornell_project_export.py`
- `tests/test_cpi_project_export.py`
- `tests/test_cornell_streamlit_helpers.py`
- `tests/test_cpi_streamlit_helpers.py`
- `tests/test_cuaderno_cornell_install.py`

Este inventario podrá reducirse si una capa compartida cubre el comportamiento sin duplicación; no se modificarán `schemas/schemas.py`, `editor/pdf_export.py`, `editor/pdf_preview.py`, `editor/utils/db_export.py` ni `editor/utils/db_import.py` salvo que una prueba focal demuestre una carencia concreta.

## Implementación y validación final

### Resultado implementado

Cornell y CPI comparten ahora un editor compacto `Identidad visual / marca de agua`. La carga acepta PNG/WebP, valida bytes con Pillow, convierte WebP a PNG portable y mantiene los bytes únicamente en `st.session_state` hasta Guardar. La vista previa usa un fondo de cuadros. Los controles permiten activar, seleccionar imagen/texto, opacidad, tamaño, posición, todas las páginas, quitar y restablecer.

El contrato final persistido bajo `cornell.watermark` o `cpi.watermark` es:

```json
{
  "enabled": true,
  "type": "image",
  "text": "",
  "image_id": "90c6d483-f5be-4ba5-b5ee-3b8261851846",
  "opacity": 0.07,
  "scale": 0.70,
  "position": "center",
  "all_pages": true
}
```

Los límites persistidos siguen siendo amplios —opacidad 0–1 y escala 0.05–2— para no invalidar notas previas; la UI recomienda 0.06–0.09 y 0.68–0.74. Una nota sin `watermark` sigue creando `CornellWatermark()` desactivado y conserva su apariencia. `all_pages` toma `true` al leer un contrato anterior que no lo tenga.

El renderer copia el logo mediante el inventario lógico de medios y lo dibuja primero en el overlay TikZ. Las regiones se dibujan después; por tanto, la marca queda detrás de texto e imágenes. `all_pages=false` la limita a la primera hoja. Una marca sin registro o sin archivo genera un warning y se omite; una imagen de contenido ausente sigue siendo un error claro. Las rutas con espacios funcionan, los escapes `..` y componentes symlink se rechazan.

Los exportadores de proyecto Cornell/CPI incluyen la configuración, una entrada por activo con rol, `asset_id`, SHA-256, tamaño, MIME y ruta relativa, y una sola copia física por imagen. El dispatcher `NoteProjectExport` propaga warnings. El export/import general de base sigue siendo el restaurador canónico de notas y medios; no fue necesario modificar su contrato.

Se agregó una sintaxis compatible opcional `\cornellimage[ratio]{asset_id}` / `\cpiimage[ratio]{asset_id}` para galerías compactas. Las referencias antiguas sin ratio conservan exactamente su ancho anterior.

### Causa raíz de Streamlit y correcciones

La auditoría inicial reprodujo `TypeError: ButtonMixin.button() got an unexpected keyword argument 'width'` en Streamlit 1.47.1. `editor/streamlit_compat.py` selecciona `width="stretch"` o `use_container_width=True` según la firma instalada.

La validación real encontró además la secuencia exacta del traceback originalmente descrito:

1. abrir la nota Cornell sembrada;
2. cambiar Opacidad de 0.07 a 0.08;
3. pulsar Guardar;
4. al recolectar el estado del rerun, el checkbox de marca ya no encontraba su clave.

Excepción completa relevante: `KeyError: 'st.session_state has no key "$$ID-…-cornell_branding_f971dcee4b1b_enabled"'`. La causa era `sync_branding_state()` al final de Guardar: borraba claves después de que los widgets habían sido instanciados en el mismo run. Guardar conserva ahora las claves del run actual; el documento guardado inicializa el scope siguiente. También se eliminaron combinaciones `value/index` + clave ya inicializada, que producían el aviso `The widget with key … was created with a default value but also had its value set via the Session State API.`

La validación CPI descubrió y corrigió otro fallo de exportación: `NoteProjectExport` no exponía `warnings`, aunque el editor los recorría. El wrapper los propaga ahora. Las regresiones AppTest cubren apertura, cambio de página, duplicar/eliminar página, Guardar y ausencia de warnings de defaults.

### Ciclo de vida y compatibilidad

- Duplicar una nota Cornell/CPI crea un documento nuevo, conserva branding y comparte los mismos `asset_id`; no duplica bytes.
- Eliminar una nota retira su `note_id` de cada activo, pero nunca borra el archivo. El borrado físico auxiliar verifica referencias en activos, `concepts` y `latex_notes`.
- Guardar sincroniza referencias previas/actuales después de persistir la nota.
- `seed_id` se preserva al editar una nota tutorial desde la UI, pero no se copia al duplicarla.
- Cambiar de nota o formato limpia el scope de branding y usa claves derivadas de formato + hash de identidad.
- La infraestructura no escribe al importar módulos; XDG Data guarda medios/backups, XDG Runtime guarda previews/proyectos temporales y el directorio configurado `Documentos/MathMongo` recibe las exportaciones explícitas.
- El validador activo de `latex_notes` se amplió solamente para admitir el contexto `capacitación`. El instalador declarativo contiene el mismo valor para instalaciones futuras.

### Microcapturas y seed

`scripts/build_cocid_drive_docs_tutorial_assets.py` genera sin red seis PNG 1600 × 900 y un manifiesto accesible:

- `drive_01_nuevo.png`
- `drive_02_crear_carpeta.png`
- `drive_03_subir_archivo.png`
- `docs_01_crear_y_renombrar.png`
- `docs_02_barra_de_herramientas.png`
- `docs_03_compartir_permisos.png`

Todas usan interfaz simplificada, español, fondo claro, alto contraste, máximo dos indicadores, leyenda de una línea, texto `Vista ilustrativa` y ninguna cuenta o dato real. El texto alternativo queda en `media_assets.description`; el PDF actual no es un PDF etiquetado.

`scripts/seed_cocid_drive_docs_tutorial.py` busca primero el logo de opacidad completa, genera los activos en Runtime, crea backup focal antes de escribir, reutiliza bytes por SHA-256 y hace upsert solo por `seed_id`. Una nota ajena que solo coincida por título no se toca.

Base seleccionada: `mathmongo`.

- Cornell: `cocid_google_drive_docs_cornell_v1`, `_id=6a601ff5fb83da1079c63363`.
- CPI: `cocid_google_drive_docs_cpi_v1`, `_id=6a601ff5fb83da1079c63364`.
- Logo: `asset_id=90c6d483-f5be-4ba5-b5ee-3b8261851846`.
- Conteo inicial: 5 `latex_notes`, 0 `media_assets`.
- Conteo final: 7 `latex_notes`, 7 `media_assets`.
- Segunda ejecución: ambas acciones `updated`, mismos IDs de notas y activos.
- Backup focal final validado: `/home/enriquedo/.local/share/mathmongo/backups/cocid_tutorial/cocid_tutorial_focal_20260722T014633_247865Z.zip`; contiene exactamente 2 notas, 7 documentos de activo y 7 archivos, sin ruta absoluta.

La nota Cornell tiene dos páginas con las preguntas, pasos, tres microcapturas por página y resúmenes solicitados. La nota CPI tiene una página: Comprensión asocia 2 imágenes, Producción 3 e Integración 1. Ambas usan contexto `capacitación`, metadatos COCID y branding 0.07/0.70/centro/todas las páginas.

### Exportación, importación y PDF

Exportaciones explícitas:

- Cornell PDF: `/home/enriquedo/Documentos/MathMongo/notes/cocid_drive_docs_tutorial/cornell_runtime/cocid_drive_docs_cornell.pdf`.
- CPI PDF: `/home/enriquedo/Documentos/MathMongo/notes/cocid_drive_docs_tutorial/cpi_runtime/cocid_drive_docs_cpi.pdf`.
- ZIP Cornell: `Tutorial_breve_Google_Drive_y_Google_Docs.zip`.
- ZIP CPI: `Google_Drive_y_Docs_comprender_producir_e_integrar.zip`.

`pdfinfo` confirmó Cornell: 2 páginas Letter vertical, 2,381,277 bytes; CPI: 1 página Letter horizontal, 2,377,124 bytes. `pdftotext` recuperó títulos, pasos, roles y leyendas esperados. `pdftoppm -png -r 150` produjo las evidencias. El preflight reportó todas las regiones `FIT`, `required_scale=1.0`, sin overflow. La revisión visual confirmó microcapturas dentro de sus bloques, sin recorte, y logo visible/discreto detrás de todo.

Los dos ZIP tienen 7 entradas de manifiesto y 7 imágenes físicas únicas; no contienen `/home/`, nombres absolutos, `..` ni symlinks. Un round-trip del exportador/importador general desde `mathmongo` hacia `cocid_roundtrip_9d06edaf2b4a` restauró 2 tutoriales y 7 activos, conservó el mismo branding y cero rutas absolutas. La base temporal se eliminó al terminar.

### Validación de Streamlit

Se inició únicamente una sesión de prueba en `127.0.0.1:8502` y un Chrome headless con perfil temporal. Se validó con AppTest y navegador:

- abrir Cornell y CPI;
- cambiar/guardar opacidad 0.08 y restaurar/guardar 0.07;
- cambiar página Cornell;
- generar preview PDF;
- exportar proyecto editable y preparar descarga;
- duplicar cada nota real, comprobar 7 referencias compartidas y eliminar solo la copia;
- confirmar que quedan 7 notas y 7 activos;
- confirmar ausencia de traceback y del warning de default duplicado.

La sesión 8502, DevTools y Chrome se detuvieron. El perfil temporal Chrome de 150 MB se eliminó de forma no recuperable. No existía una sesión de usuario visible en 8501 y no se detuvo ninguna.

Evidencias en `docs/evidence/cocid_drive_docs_tutorial/`:

- `cornell_editor.png`
- `cornell_pdf_page_1.png`
- `cornell_pdf_page_2.png`
- `cpi_editor.png`
- `cpi_pdf.png`
- `branding_controls.png`

### Pruebas

- `py_compile` sobre todos los Python cambiados: OK.
- Ruff sobre todos los Python cambiados: OK.
- Suite focal final: **251 passed** en 53.38 s.
- `tests/test_xdg_media_paths.py`: **14 passed, 3 failed**, exactamente los tres fallos baseline preexistentes por `_FixedExportDatetime` sin `.now()`; ningún archivo de esa ruta fue modificado.
- Suite completa con el Python del sistema: no llegó a ejecución, pues la colección se interrumpió con 12 errores por dependencia `fastapi` ausente. Poetry tampoco tiene un entorno resoluble en esta máquina (`pyenv` devuelve 127). No se instalaron dependencias ni se atribuyen estos errores a la tarea.
- `git diff --check`: OK.

### Archivos

Nuevos principales:

- `editor/streamlit_compat.py`
- `editor/note_branding.py`
- `scripts/build_cocid_drive_docs_tutorial_assets.py`
- `scripts/seed_cocid_drive_docs_tutorial.py`
- `scripts/cocid_tutorial_streamlit_validation.py`
- `tests/test_note_branding.py`
- `tests/test_cpi_images.py`
- `tests/test_cocid_tutorial_seed.py`
- este informe y las seis evidencias PNG.

Se modificaron las capas Cornell/CPI de modelo, identidad, medios, persistencia, render, proyecto, servicio y Streamlit; además `editor/utils/media_assets.py`, `editor/note_export.py`, `scripts/install_cuaderno_mode.py` y las pruebas focales correspondientes. No se modificaron los importadores generales, `editor/pdf_preview.py`, `editor/pdf_export.py` ni esquemas de conceptos.

### Commits y limitaciones

Commits separados creados antes del commit tutorial:

- `e79d6388 fix(notes): stabilize Cornell and CPI editor state`
- `35913b83 feat(notes): add portable watermark branding`
- `c54b7d9e fix(notes): preserve editor state across saves`
- `feat(tutorial): add COCID Drive and Docs learning notes` (commit que contiene esta sección, scripts, seed y evidencias).

Limitaciones conocidas: el PDF generado por pdfTeX no está etiquetado, aunque el alt se conserva en el modelo de medios; los ZIP de proyecto son proyectos LaTeX editables, mientras el round-trip a Mongo usa el export/import de base ya existente. Una mejora posterior recomendable es un importador de proyecto editable que reconstruya una sola nota y remapee sus activos sin requerir un backup de base.

### Estado final

La instantánea Git exacta posterior al último commit se entrega en el mensaje final, ya que un commit no puede incluir de forma autorreferencial su propio hash. Antes del commit tutorial: rama `main`, tres commits por delante de `origin/main`, sin errores de whitespace.

Confirmaciones:

- No se hizo push.
- No se detuvo una sesión Streamlit del usuario.
- No se sobrescribieron notas ajenas.
- No se persistieron rutas absolutas en MongoDB, PDFs o paquetes exportados.

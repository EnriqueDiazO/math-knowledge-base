# Auditoría y corrección de vista previa PDF Cornell/CPI

## Flujo anterior y causa raíz

El punto de entrada operativo es `editor/editor_streamlit.py` (lanzado por `run_gui.py`); `app/main.py` es un adaptador alternativo. Add Concept y Edit Concept construyen los datos en `editor/editor_streamlit.py` y comparten `generar_y_abrir_pdf_desde_formulario()` de `editor/pdf_export.py`. Esta función genera con `pdflatex`, comprueba el resultado y llama `webbrowser.open_new_tab()` con una URL local. No existe un servidor HTTP para PDFs ni JavaScript/HTML de apertura.

Cornell y CPI viven en `editor/cornell/streamlit_page.py` y `editor/cpi/streamlit_page.py`; sus renderers son `editor/cornell/renderer.py` y `editor/cpi/renderer.py`. Ambos generaban correctamente y ofrecían `st.download_button`, pero nunca invocaban la apertura. Además usaban el ID de nota como nombre de salida, permitiendo múltiples PDFs en la carpeta de preview.

## Decisión técnica y flujo final

`editor/pdf_preview.py` concentra responsabilidades comunes:

- prepara una carpeta controlada y una ruta estable;
- elimina el PDF previo antes de compilar, evitando reutilizarlo si falla LaTeX;
- limpia sólo auxiliares conocidos (`.aux`, `.log`, `.out`, `.toc`, `.fls`, `.fdb_latexmk`) dentro de esa carpeta;
- valida que el PDF nuevo exista;
- genera una URI segura mediante `Path.resolve().as_uri()` y solicita apertura no bloqueante con `webbrowser.open_new_tab()`.

Cornell siempre usa `runtime/cornell_streamlit_preview/cornell_preview.pdf`; CPI usa `runtime/cpi_streamlit_preview/cpi_preview.pdf`. Tras un render exitoso se valida el archivo, se solicita la apertura y se conserva `Descargar PDF`. El mensaje distingue entre solicitud aceptada y navegador sin confirmación. Si falla el render o falta el archivo, no hay apertura. Conceptos conservan su flujo, pero ahora también validan existencia y usan `Path.as_uri()` para rutas con espacios.

No se sirve el sistema de archivos por HTTP, no se añadió JavaScript, HTML ni dependencia. La limitación heredada es que `file://` se abre en el navegador del proceso servidor; esto es apropiado para la aplicación local Linux planteada, no para despliegue remoto.

## Archivos modificados y ciclo de vida

- `editor/pdf_preview.py`: utilidad común nueva.
- `editor/pdf_export.py`: URI segura y validación para Add/Edit Concept.
- `editor/cornell/streamlit_page.py`: preview estable, apertura y descarga.
- `editor/cpi/streamlit_page.py`: preview estable, apertura y descarga.
- `tests/test_pdf_preview.py`: ruta estable, espacios, archivo ausente, aislamiento y limpieza.

La limpieza no toca exportaciones, datos MongoDB, imágenes persistentes ni directorios fuera de los dos previews. Los recursos de render (`.tex`, estilos e imágenes necesarias) se reutilizan; auxiliares y el PDF se regeneran. Los renderers ya eliminan PDF obsoleto en overflow; la preparación común amplía la garantía a cualquier fallo posterior.

## Pruebas y limitaciones

Las pruebas unitarias inyectan el abridor, evitando automatización frágil del navegador. Cubren apertura sólo con archivo real, URI con espacios, rechazo de escape de directorio y limpieza segura. Las suites Cornell/CPI y conceptos verifican que los renderers y exportación preexistentes continúan funcionando. La apertura visual real requiere una sesión gráfica y debe verificarse manualmente en Add Concept, Edit Concept, Cornell y CPI.

# CPI: recursos reales en las exportaciones React — 24/25 noviembre 2026

Se conserva la rama `feature/knowledge-sphere-2026-11`, desde `07ebdd52` limpio.
Los procesos originales 8501/8766 y MathV0 se inspeccionaron en lectura; los
recorridos con escritura usan un mongod independiente, dos bases y dos árboles
XDG/medios en `/tmp`. Inventario, versiones, PID y hashes:
`evidence/sonar/cpi-five-images-2026-11-24/{host-readonly,owned-comparison,activity-input-provenance}.json`.
Es una selección equivalente de registros y recursos, no una copia completa de MathV0.

El caso auténtico es «Google Drive y Docs: comprender, producir e integrar»,
`cpi_v1`, con cinco capturas y una marca de agua. Antes, la descarga React
reproducía los marcadores `Imagen CPI: []0.7`/`[]0.98` del PDF aportado, aunque
los seis originales existían. La descarga Streamlit sí mostraba las imágenes.
La prueba `tests/test_structured_image_bundles.py` produjo **dos fallos antes**
de corregir el generador (`images-before.log`). No era un problema de archivos
perdidos: el ZIP recibía bytes, pero el generador y la medición CPI no recibían
`asset_paths_by_id`. La macro de reserva de un argumento consumía el corchete
de la anchura opcional como contenido.

Se reutilizan los preparadores nativos CPI/Cornell para materializar recursos
seguros y entregar las mismas rutas relativas a generación, medición y bundle.
El fondo histórico Cornell también se conserva. El contenido LaTeX original
sigue en `content/body.tex`; no se convierte a HTML ni se normalizan macros.
PDF opera sobre una única instantánea, sin volver a leer la nota durante la
resolución de imágenes. La regresión concurrente cambia el documento después
de abrirlo y comprueba que se exporta la instantánea observada.

La galería nueva obtiene únicamente recursos referenciados por la nota abierta,
con los controles de biblioteca/ruta existentes. No acepta una ruta del cliente
ni expone rutas del host. Los fallos conservan el documento y dan HTTP 422,
no un PDF anunciado como correcto con imágenes sustituidas por texto.
La prueba en navegador descubrió que la CSP bloqueaba imágenes `blob:` locales:
se permite ese esquema únicamente en `img-src`; scripts, conexiones, frames y
objetos mantienen sus restricciones. Los URLs se revocan al cerrar la galería.

Evidencia real en `evidence/sonar/cpi-five-images-2026-11-24/`:

- `before-firefox/`: captura Streamlit y descargas React defectuosas.
- `fixed-pdf-firefox/`: descarga corregida y comparación visual con Streamlit.
- `after-{firefox,chrome}/`: galería, guardado de metadatos, recarga/reapertura,
  PDF y ZIP descargados desde los controles reales de React; `browser.json`
  distingue recorridos aprobados y fallidos. Los errores previos se conservan
  en los logs; no dan crédito de cobertura.
- `pdf-verification.json`: cotejo de los píxeles RGB de los seis recursos,
  cinco leyendas originales, ausencia de marcadores y geometría del PDF.
- `portable-recompiled.pdf/png`: compilación del ZIP descargado en directorio
  limpio, usando el sandbox canónico bubblewrap, sin rutas originales ni red.

El primer test HTTP detectó que faltaba el fondo Cornell; se corrigió y el
retest de HTTP/compatibilidad dio **21 aprobadas**. Los tests nuevos comprueban
ámbito, falta de recursos, instantánea concurrente, conservación de fuente,
previsualización bajo demanda y liberación de URLs. El resumen integral y Sonar
se añaden al checkpoint de navegación; estos resultados no cierran el resto de
la migración. No se generó ni arrancó otra AppImage.

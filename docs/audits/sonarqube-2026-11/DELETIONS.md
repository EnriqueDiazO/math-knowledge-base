# Registro de eliminaciones y reemplazos

No se retiraron funciones/clases públicas, datos, colecciones, pruebas válidas ni
dependencias runtime. No se usaron reset/clean/prune ni borrados globales.

| Elemento retirado | Evidencia y referencias comprobadas | Verificación |
|---|---|---|
| Segundo `from typing import List` de concept_validator | Import idéntico consecutivo; todas las anotaciones siguen resolviendo el primer List; no cambia exportaciones ni session_state | Suite de edición/validación y análisis AST |
| Import os de app/main | Wrapper sin usos de ese import; editor ya importa su propio os. No cambia entrada ni imports condicionales | Compilación/AST, runtime desde entrada mantenida |
| Local fullscreen_key | Sólo interpolación pura; la única referencia era un bloque comentado. Sin callbacks/registro/widgets activos | Búsqueda código/tests/docs y pruebas de grafo |
| Local title en export_concepts de Quarto | Resultado no leído; _safe_title es puro y _file_stem ya obtiene el título | Exportación/paths y suite existente |
| Rama duplicada de validate_concept_from_mongo | Ambos cuerpos ejecutaban la misma consulta con id/source, sin otros efectos | 50 tests pertinentes y suite global |
| useEffect tardío de capabilities | Restricción aplicada ahora en el mismo callback de metadata, antes del primer render cargado | Test existente de metadata capabilities, 107 frontend |
| net.show previo a write_html | API instalada PyVis 0.3.2 usa notebook=True por defecto y podía abrir navegador; Streamlit necesita sólo el HTML | PyVis real con metadata canónica y ambos fallbacks |
| report-task.txt anterior | Artefacto generado por scanner, identificado por ruta propia; nunca datos del usuario | Test de fallo de upload impide snapshot antiguo |

Antes de retirar código se buscaron referencias en fuentes, tests, documentación,
configuración, entradas CLI, navegación y claves de sesión. Los retiros son imports
redundantes, locales puros o ramas cuya responsabilidad está preservada. No se toma
la ausencia de referencias como prueba suficiente para eliminar APIs legadas.

## Recursos publicados reconstruidos

El commit 68165817 sustituye el bundle de PDF.js afectado por una actualización
compatible. El manifiesto completo de cada ruta anterior/nueva está en
[replaced-assets.json](replaced-assets.json): 197 movimientos de contenido idéntico,
un bundle de entrada renombrado con cambios, tres bajas, tres altas y dos manifiestos
actualizados. Las bajas son el worker anterior, el runtime JS anterior y qcms WASM
anterior; sus reemplazos están publicados y referenciados desde el nuevo índice.

Evidencia de prescindibilidad de las versiones anteriores: búsqueda de consumidores
activos, actualización coordinada de PDFJS_VERSION y rutas del worker/recursos,
validación del árbol de salida por publish-build, pruebas de empaquetado, licencias
y manifiestos, build limpio, npm ci y ejecución Chrome del lector. El anterior
namespace sólo queda citado en documentos históricos; no es una ruta activa.
Los 198 recursos oficiales conservan allowlists de nombres/contadores; los textos
de licencia acompañan su nuevo namespace. No se eliminaron las bibliotecas externas
Quarto, lib/, datos locales o recursos cuya prescindibilidad no se demostró.

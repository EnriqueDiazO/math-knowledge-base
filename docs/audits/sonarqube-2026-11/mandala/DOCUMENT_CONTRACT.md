# Contrato documental del editor híbrido

LaTeX es canónico. Tiptap JSON conserva selección, estructura editable y
proveniencia del borrador; HTML sólo presenta ese documento. `DocumentEditor.value()`
serializa la misma fuente utilizada por operaciones HTTP y exportadores. El modo
Fuente LaTeX entrega directamente el texto completo, sin convertirlo a HTML.

## Recorrido de datos comprobado

1. La inserción visual crea nodos `resultBlock`, `semanticBlock`, `formula`, listas,
   párrafos o `sourceBlock`, con atributos y contenido Tiptap explícitos.
2. `document.serialize()` genera LaTeX. Un bloque importado conserva `raw` y una
   firma de sus datos: si permanece intacto, devuelve literalmente ese `raw`.
   La firma incluye ahora el destino de los enlaces, además de su tipo.
3. La intención durable contiene `contenido_latex`; el servicio de conceptos
   guarda ese texto en `latex_documents`. Las notas guardan su cuerpo LaTeX en
   `reading_notes.body`. Ninguno guarda HTML como documento canónico.
4. Al abrir, `parseDocument()` reconstruye el árbol acotado. Se conserva la fuente
   que no comprende. `DocumentSurface` no destruye el editor cuando únicamente
   cambia la preparación de la misma biblioteca/runtime; una regresión lo comprueba.
5. La exportación usa los renderizadores de fragmentos, maestro y ZIP portables
   existentes. Añade las dependencias reales de `notes.sty` cuando corresponda.
   Los documentos completos reconocidos conservan su maestro y preámbulo; no
   reciben otro documentclass ni un encabezado derivado de metadatos.

## Bloques y serialización

| Representación visual | LaTeX canónico | Contrato/dependencia |
|---|---|---|
| Definición, Teorema, Corolario, Lema, Proposición, Ejemplo, Nota, Observación | Entorno correspondiente con argumento obligatorio `{título}`; nuevo bloque sin título usa `{}` | `miestilo.sty` y `coloredtheorem.sty`; se conservan alias. `remark` significa Nota. |
| Demostración | `\begin{proof}…\end{proof}` | amsthm; no se inventa argumento obligatorio. Las variantes originales con opciones se protegen. |
| Contexto, Lectura, Exploración, Hipótesis, Conexiones, Reflexión, Decisión, Preguntas abiertas, Técnica, Próximos pasos | Entornos sin argumentos obligatorios declarados en `editor/ui/document_blocks.json` | Cada entrada se coteja en pruebas con `templates_latex/notes.sty`. |
| Fórmula en línea/en bloque | `$…$` / `\[…\]` | MathLive conserva su LaTeX y fuentes; matemáticas desconocidas originales se protegen. |
| Prosa, negrita y énfasis | Texto escapado, `\textbf{…}`, `\emph{…}` | Los comandos conocidos se presentan legiblemente; la fuente importada intacta no se normaliza. |
| Enlace académico | `\href{destino}{texto}` / fuente original de `\url` | Navegación sólo HTTP(S), sin credenciales ni caracteres de control. HTML pegado usa la misma validación. |
| Lista y código | itemize/enumerate y verbatim | Adaptador acotado; no se declara interpretación general de TeX. |
| LaTeX avanzado protegido | Fuente literal del bloque | Puede añadirse y modificarse explícitamente. No se ejecuta como HTML. |
| Bibliografía/localizadores | IDs y localizadores canónicos, más representación bibliográfica del exportador existente | Una cita no cambia la ficha bibliográfica ni crea un entorno inexistente. |

Las plantillas consultadas no declaran automáticamente entornos llamados
`concept` o `reference`. No se generan esos wrappers como sustitución de los
reales. Se conservan cuando aparecen en un documento histórico; su compilación
necesita las definiciones/macros del documento original. El modo de fuente y los
bloques protegidos permiten introducir construcciones sin herramienta visual.

Una edición de una parte reconstruye esa parte comprendida. Las construcciones
protegidas y los bloques originales vecinos permanecen literales. No se prometen
edición visual completa de preámbulos, macros arbitrarias, tablas avanzadas,
algoritmos, entornos personalizados o todas las formas de listas/referencias.
Se distinguen almacenamiento sin pérdida, edición visual y dependencias de TeX.

## Compilación y recursos

`exporters_latex/sandbox.py` reutiliza `run_latex_until_stable()` y la clasificación
canónica de resultados. Bubblewrap elimina red, acceso al perfil del anfitrión y
variables de entorno; todos los directorios son de sólo lectura. Sólo seis archivos
de salida conocidos se montan para escritura. Prlimit limita CPU, memoria,
descriptores, procesos y cada archivo a 16 MiB; el runner limita tiempo y pasadas.
Se usa `-no-shell-escape`. No hay alternativa automática sin aislamiento.

La vista TikZ compila un fragmento, con recorte preview, no todo el documento al
abrirlo. La caché distingue biblioteca, fuente, macros, plantillas, binario TeX,
composición y política de aislamiento. Publica archivos atómicos, rechaza salidas
truncadas y poda sólo sus propios resultados reconocidos. La fuente nunca se poda.
Las pruebas incluyen denegación real de lectura/escritura del host, eliminación
de credenciales del proceso, red loopback del host inaccesible y fallo de publicación.

## Verificaciones documentales

- Nuevos bloques visuales anidados y fórmulas → MongoDB temporal → TEX/PDF real.
- Cinco copias reales: John McCarthy, Arco en el plano complejo, Antecedentes de
  la IA, Instalación/configuración de MkDocs y Sistema de Control de Versiones
  Locales. Chrome/Firefox comparan SHA256 antes/después de un guardado sin cambios;
  el backend también coteja los metadatos originales y la identidad.
- Documento mixto visual/TikZ/macros → edición de un párrafo → ZIP cuyo cuerpo
  coincide exactamente con MongoDB → PDF compilado. Se inspecciona el PDF con
  pdfinfo, pdftotext y rasterización, además de comprobar cabeceras.
- Documento completo con preámbulo propio → una sola clase, fuente íntegra en el
  ZIP y compilación; la combinación de varios maestros completos se rechaza
  con una acción concreta para exportarlos por separado.

La recuperación del 24 de noviembre detectó una diferencia importante: las
capturas anteriores de ampliación mostraban una imagen rota. El PNG compilaba,
pero `img-src` no admitía el blob usado por el adaptador. `5acbc7d9` utiliza el
PNG data: ya admitido por la política, mantiene CSP y exige píxeles decodificados
antes de ampliar. Las evidencias anteriores de presencia de un elemento no se
consideran prueba de una figura visible. Cada resultado nuevo incluye ejecución,
revisión y estado, también en fallos, para evitar reutilizar un éxito antiguo.

## Pendientes explícitos al recuperar

La visualización compilada del documento completo durante la escritura, antes
de guardar, y la omisión editorial predeterminada de IDs técnicos pertenecen al
siguiente checkpoint del encargo de reanudación. La exportación ya compilada y
las vistas de figuras no se confunden con ese modo de borrador. Los medios
adjuntos externos y macros auxiliares de documentos particulares siguen sujetos
a su incorporación portable y autorización, sin acceso libre al sistema anfitrión.

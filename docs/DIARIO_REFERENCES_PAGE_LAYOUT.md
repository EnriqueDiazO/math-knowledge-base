# Referencias, encabezado, pie e índice en Notas de Diario

Esta función pertenece exclusivamente a las notas libres de **Cuaderno →
Diario** (`note_format` ausente, vacío o `freeform`). Las notas Cornell y CPI
conservan sus modelos, pantallas, persistencia y exportadores propios.

## Edición

Los mismos controles aparecen al crear una nota y al editar una existente:

- **Metadatos académicos y PDF**: institución, programa, asignatura, semana,
  sesión, título corto, tema, objetivo, actividad, autoría, versión, idioma,
  asunto y palabras clave PDF. El título completo, la fecha, el proyecto, el
  contexto y los tags siguen teniendo como fuente de verdad los campos
  principales de la nota.
- **Encabezado, pie y página de contenido**: activación, seis posiciones,
  primera página, número de página, título/profundidad/posición del índice y
  una vista previa textual.
- **Referencias bibliográficas**: alta manual o instantánea de una Reference
  existente del catálogo, edición gradual, orden mediante Subir/Bajar y
  eliminación con confirmación.

Todos los campos bibliográficos son opcionales durante la edición. Una entrada
sin título se guarda como borrador y muestra una advertencia, pero no crea un
`\bibitem`. Una entrada con título se puede exportar parcialmente sin inventar
los datos que falten. DOI y URL se validan de forma tolerante: un formato dudoso
no bloquea el guardado.

Cada referencia tiene un `reference_id` UUID estable. Las claves de widgets se
derivan de ese ID, no de la posición, por lo que reordenar no mezcla datos. Una
referencia seleccionada del catálogo guarda `catalog_reference_id` y una
instantánea editable; el catálogo no se modifica. Una referencia manual sólo
vive dentro de la nota.

## Tres conceptos distintos

- **Metadatos académicos** describen la nota y alimentan el bloque visual,
  `\hypersetup`, encabezados y pies.
- **Fuentes de construcción** siguen siendo contenido narrativo del cuerpo si
  el autor decide documentarlas; el modelo actual de Diario no posee una
  entidad estructurada independiente para ellas.
- **Referencias bibliográficas formales** son la colección ordenada
  `references` y se exportan al final mediante `thebibliography`.

No se transforma silenciosamente una fuente narrativa en bibliografía ni se
crea una Source/Reference canónica al escribir una referencia manual.

## Tokens de encabezado y pie

Se admiten estos tokens:

```text
{institution} {program} {course_code} {course_name}
{week} {session} {short_title} {title}
{author} {date} {page}
```

Los valores predeterminados de una nota nueva derivan de sus metadatos:

- izquierda del encabezado: `{institution} · {course_code}`;
- derecha del encabezado: `{week} · {short_title}`;
- izquierda del pie: `{course_name}`;
- derecha del pie: `{author}`;
- número de página: activado en el centro del pie mediante la opción tipada.

`short_title` usa el título completo como fallback. Un campo vacío produce
texto vacío. Un token desconocido se omite y genera una advertencia. Aunque se
escriba `{page}` más de una vez, el exportador emite un solo `\thepage` por
estilo de página. Los textos ordinarios se escapan después de resolver tokens.

La primera página puede usar el mismo estilo, un estilo simple o quedar sin
encabezado/pie. Las aperturas de capítulos y las páginas de Contenido y
Referencias conservan el estilo configurado.

## Página de contenido

`show_table_of_contents` está desactivado por defecto para mantener el aspecto
de las notas antiguas. Cuando se activa, `toc_title` vale `Contenido` si se deja
vacío y `toc_depth` cubre únicamente la estructura real de `notes.cls`:

- `0`: capítulos;
- `1`: capítulos y secciones;
- `2`: capítulos, secciones y subsecciones.

La posición puede ser después del título o después del bloque de metadatos. El
exportador emite una sola vez `\tableofcontents`, configura `tocdepth` y utiliza
el mecanismo nativo de LaTeX. `\notetitle` ya incorpora el título de la nota con
`\addcontentsline`; Referencias hace lo mismo sin duplicar su encabezado. En el
cuerpo LaTeX, una sección manual sin numeración que deba aparecer en el índice
debe acompañarse de su `\addcontentsline` correspondiente.

## Persistencia y compatibilidad

`latex_notes` continúa siendo la fuente de verdad. No existe tarea de migración,
recorrido de colección ni normalización masiva para esta función.

- Cargar una nota antigua crea defaults sólo en memoria y no escribe MongoDB.
- Guardarla sin cambiar las opciones nuevas no añade `academic_metadata`,
  `page_layout`, `table_of_contents`, `references` ni `note_schema_version`.
- En una nota existente, los escalares modificados se guardan mediante paths
  puntuales de `$set`; por ejemplo, activar el índice produce
  `table_of_contents.show_table_of_contents`.
- La lista `references` sólo se reemplaza cuando cambió su contenido u orden.
- La actualización usa `update_one` con el `_id` de la nota seleccionada. No
  reemplaza documentos completos, no usa operaciones masivas y conserva campos
  históricos desconocidos, incluidos datos extra dentro de instantáneas.
- Una nota nueva sí inserta su configuración explícita junto con el resto del
  documento.

Cerrar y reabrir la aplicación reconstruye los controles desde MongoDB; Session
State sólo mantiene el borrador durante los reruns actuales.

## Exportación LaTeX, PDF y ZIP

El exportador de Diario genera:

- `\hypersetup` con título, autor, asunto y palabras clave;
- `fancyhdr` con `\fancyhf{}`, seis posiciones y primera página explícita;
- un bloque `notemeta` alimentado por los mismos metadatos;
- la página de contenido nativa cuando está activada;
- una sección Referencias única y ordenada, con DOI/URL clicables;
- escape de `&`, `%`, `_`, `#`, `$`, llaves, barra inversa, `~` y `^` en todos
  los campos ordinarios. El cuerpo sigue siendo LaTeX escrito por el usuario.

El ZIP conserva `main.tex`, `content/body.tex`, estilos, macros, imágenes,
metadatos e instrucciones. La bibliografía está incorporada en `main.tex`, por
lo que no necesita BibLaTeX, Biber ni un archivo `.bib` adicional.

Para resolver títulos y números de página del índice, compile al menos dos
veces desde la raíz extraída del ZIP:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```


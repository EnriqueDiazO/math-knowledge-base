# Add Concept Reference Import

## A. Problema

Add Concept permitía seleccionar una entrada de un archivo `.bib`, pero el botón
`Usar esta entrada` intentaba leer `tipo_referencia` de un diccionario que nunca
contenía esa clave. Una entrada BibTeX válida terminaba mostrando
`No se pudo leer el .bib: 'tipo_referencia'`.

La misma pantalla tampoco ofrecía el pegado BibTeX disponible en Add Source y
usaba claves globales `edit_ref_*`, compartidas accidentalmente con Edit Concept.

## B. Causa raíz

El parser local de Add Concept devolvía directamente la estructura de
`bibtexparser`: tipo en `ENTRYTYPE`, citekey en `ID` y campos bibliográficos con
nombres BibTeX. Su adaptador `_bib_to_referencia` copiaba algunos campos, pero no
producía `tipo_referencia`. La UI accedía después a esa clave con indexación
obligatoria.

La implementación elimina ese parser duplicado. Archivo y pegado usan ahora las
funciones puras de `mathmongo.source_catalog.bibtex`, compartidas con Add Source,
y un adaptador único genera siempre el contrato del formulario de concepto.

## C. Contrato bibliográfico normalizado

El destino conserva exclusivamente los campos admitidos por la referencia
embebida del concepto:

```text
tipo_referencia, autor, fuente, anio, tomo, edicion, paginas,
capitulo, seccion, editorial, doi, url, issbn, citekey
```

Los opcionales ausentes son `None` en el contrato y se presentan vacíos en los
widgets. `citekey` es opcional y se omite junto con los demás `None` mediante el
builder vigente con `exclude_none=True`.

La prioridad de adaptación es:

- `title` para `fuente`; si falta, `booktitle`, `journal` y `publisher`, en ese
  orden;
- `author` para `autor`; `editor` sólo es fallback cuando falta author;
- `year`, o el año inicial de `date`, para `anio`;
- `volume`, `edition`, `pages` y `chapter` para sus campos legacy;
- `section`, y después `number`/`issue`, para `seccion`;
- `publisher` para `editorial`;
- `isbn`, o `issn` si no hay ISBN, para el campo histórico `issbn`;
- DOI sin prefijos repetidos, URL y citekey para sus campos existentes.

## D. Mapping de tipos BibTeX

| Tipo BibTeX | Tipo del concepto |
|---|---|
| `book`, `booklet`, `manual` | `libro` |
| `article` | `articulo` |
| `phdthesis`, `thesis` | `tesis` |
| `mastersthesis` | `tesina` |
| `online`, `electronic`, `web`, `www` | `pagina_web` |
| `misc` | `miscelanea` |
| `inbook`, `incollection` | `miscelanea`, con aviso |
| `inproceedings`, `proceedings`, `conference` | `miscelanea`, con aviso |
| `techreport`, `report` | `miscelanea`, con aviso |
| `unpublished` o desconocido | `miscelanea`, con aviso |

No se crearon categorías internas. `miscelanea` es el fallback existente.

## E. Carga de archivo `.bib`

El uploader acepta un archivo `.bib` ya cargado, aplica los límites compartidos
de Add Source, analiza todas sus entradas y muestra un selector `Citekey — Title`.
Sólo `Usar esta entrada` reemplaza el estado del formulario. Parsear o seleccionar
no escribe datos.

El fixture rastreable es:

```bibtex
@book{Muskhelishvili1946,
   author = {N.I. Muskhelishvili},
   title = {Singular Integral Equations},
   year = {1946}
}
```

Su resultado es `libro`, `N.I. Muskhelishvili`,
`Singular Integral Equations`, `1946` y `Muskhelishvili1946`. Los demás campos
quedan vacíos y no aparece ningún `KeyError` por `tipo_referencia`.

## F. Pegado de referencia

`Pegar referencia o entrada BibTeX` conserva el texto en un `text_area` y sólo lo
procesa al pulsar `Analizar referencia`. Una entrada válida única puebla el
formulario; varias entradas requieren selección y un segundo botón explícito.

Add Source soporta pegado de una o varias entradas BibTeX, pero no contiene un
parser de citas libres APA, Chicago u otros estilos. Esta fase conserva esa misma
limitación: un texto que no sea BibTeX se mantiene visible y genera un error claro
sin alterar los valores manuales.

## G. Formulario manual

Existe un solo formulario de destino. Los valores importados, pegados, cargados
desde el concepto anterior o introducidos manualmente terminan en las mismas
claves y siguen siendo editables antes de guardar.

El cambio de schema se limita a `citekey: str | None = None` en `Referencia`.
No se renombró `issbn` ni se añadieron campos para journal, number, editor,
booktitle, raw BibTeX, ENTRYTYPE, idioma o notas.

## H. Estado y precedencia

Todas las claves empiezan con `add_concept_reference_`. La identidad de estado
incluye base activa, `source_id` y el ID del concepto.

- Un parseo exitoso reemplaza los campos sólo después de la acción explícita.
- Un parseo fallido no modifica campos ni borra el texto pegado.
- Las ediciones manuales posteriores tienen prioridad.
- Cambiar de base, Source o concepto limpia el estado bibliográfico de ese scope.
- `Limpiar formulario de referencia` es la acción explícita de limpieza.
- Cargar o analizar nunca dispara `Save Concept`.

## I. Manejo de errores

El parser devuelve códigos estructurados para entrada vacía, texto inesperado,
entrada sin cerrar, error de decodificación y error de parseo. La UI distingue
errores de archivo, errores del texto pegado, entradas incompletas, tipos sin
equivalencia exacta y fallos internos de contrato.

Los campos BibTeX sin representación propia se omiten. Cuando contienen
información que no pudo mapearse, la UI muestra un aviso en vez de almacenarla
bajo un nombre nuevo.

## J. Compatibilidad con Add Source

Add Source continúa usando `parse_bibtex_file_content` y `parse_bibtex_text` a
través de su servicio existente. No se modificaron sus páginas, formularios,
modelos, repositorios, asociaciones ni operaciones de persistencia.

Add Concept reutiliza el mismo parser y el helper acotado de lectura de uploads;
sólo el adaptador final al contrato legacy del concepto es específico de esta UI.

## K. Pruebas

Las pruebas cubren:

- fixture Muskhelishvili y persistencia de citekey;
- referencias legacy sin citekey y omisión de `citekey=None`;
- mappings exactos, fallback y avisos;
- article, incollection, tesis, web, Unicode, braces y autores múltiples;
- campos ausentes, entradas inválidas, vacías, múltiples y citekeys repetidos;
- archivo, pegado, selector, botón, preview y campos editables;
- fallo no destructivo, limpieza explícita y aislamiento de estado;
- ausencia de escrituras y de mutaciones de Sources;
- compatibilidad con las pruebas bibliográficas de Add Source.

Las pruebas de UI usan fakes en memoria y no conectan con MongoDB.

## L. Validaciones

Se ejecutan pruebas focalizadas del parser, Add Source, Add Concept, schema,
builder de conceptos y session state; Ruff sólo sobre Python modificado, con
exclusiones explícitas para deuda preexistente de archivos legacy; compilación
AST en memoria; `git diff --check`; y una regresión amplia final.

La regresión completa terminó con `1494 passed, 53 skipped` y los mismos cuatro
fallos XDG ya conocidos, sin fallos nuevos introducidos por estos checkpoints.

## M. Archivos modificados

- `schemas/schemas.py`
- `editor/helpers/bibliographic_reference.py`
- `editor/concept_reference_form.py`
- `editor/editor_streamlit.py`
- `tests/fixtures/bibliography/muskhelishvili_minimal.bib`
- `tests/test_concept_reference_bibliography.py`
- `tests/test_concept_reference_schema.py`
- `tests/test_add_concept_reference_import_ui.py`
- `docs/PHASE_ADD_CONCEPT_REFERENCE_IMPORT.md`

## N. Limitaciones

- No se interpretan citas bibliográficas textuales libres porque Add Source no
  ofrece actualmente ese parser.
- El contrato legacy sólo tiene `fuente`; journal y booktitle no pueden
  conservarse simultáneamente con un title principal.
- `seccion` recibe section o, si falta, number/issue; ambos no pueden almacenarse
  por separado.
- No se conserva raw BibTeX ni ENTRYTYPE dentro del concepto.
- No se consultan DOI, ISBN, Crossref ni servicios de red.

## O. Próxima fase

Una fase futura puede evaluar un parser textual explícito o ampliar el modelo
bibliográfico legacy. Eso requeriría su propio contrato, compatibilidad de
exportación y autorización de schema; queda deliberadamente fuera de este
cambio.

Esta fase no modifica MathV0, MongoDB real, conceptos existentes, Sources,
import/export general de bases, migraciones, backfills, índices, versión ni tags.

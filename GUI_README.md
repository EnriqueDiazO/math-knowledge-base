# Math Knowledge Base - GUI Guide

This file documents the Streamlit interface in `editor/editor_streamlit.py` and the Notebook/Cuaderno page in `editor/cuaderno_page.py`.

## Quick Start

Start MongoDB and run the GUI from the repository root:

```bash
make start
source mathdbmongo/bin/activate
streamlit run editor/editor_streamlit.py
```

Equivalent project command:

```bash
make run
```

The app opens at:

```text
http://localhost:8501
```

Before using the full Notebook and map-saving workflow, initialize the target MongoDB database:

```bash
python scripts/install_cuaderno_mode.py --mongo-uri mongodb://127.0.0.1:27017 --db MathV0
```

Use the same `--db` value as the database selected in the sidebar.

## Sidebar

The sidebar controls the active database connection and the main page.

Database connection panel:

- Current database name.
- Connection status.
- Switch Database selector.
- Add New Database:
  - Display name.
  - MongoDB URI.
  - Database name.
- Test Connection button.

Navigation pages:

- Dashboard.
- Add Concept.
- Edit Concept.
- Browse Concepts.
- Manage Relations.
- Knowledge Graph.
- Document Builder.
- Export.
- Database Export.
- Database Import.
- Settings.
- Cuaderno, when the Notebook collections are installed.

## Dashboard

The dashboard summarizes the active database.

Main fields and controls:

- All sources toggle/checkbox.
- Source multiselect when all sources is disabled.
- Summary metrics:
  - concepts,
  - relations,
  - sources,
  - categories.
- Recent concepts table.
- Concept type distribution.
- Top categories.
- Relation/source visual summaries.

## Add Concept

The Add Concept page creates a new mathematical concept and its LaTeX document.

Concept type:

- Concept Type:
  - `definicion`
  - `teorema`
  - `proposicion`
  - `corolario`
  - `lema`
  - `ejemplo`
  - `nota`

Basic information:

- ID.
- Source:
  - existing source selector,
  - custom source option,
  - new source name.
- Existing IDs for selected source, read-only helper list.
- Title.
- Title Type.
- Add New Category.
- Categories multiselect.

LaTeX content:

- ACE LaTeX editor.
- Helper buttons for:
  - definition,
  - theorem,
  - proof,
  - example,
  - lemma,
  - proposition,
  - corollary,
  - remark,
  - equation,
  - align,
  - matrix,
  - cases,
  - itemize,
  - enumerate,
  - description,
  - quote,
  - code listing,
  - directory tree.
- Mathematical symbol helpers:
  - sum, product, integral, partial,
  - infinity, arrows, membership,
  - subset, union, intersection, empty set,
  - for all, exists, therefore, because.
- Greek letter helpers:
  - alpha, beta, gamma, delta,
  - epsilon, theta, lambda, mu,
  - pi, sigma, tau, phi,
  - chi, psi, omega, Gamma.
- Insert at Cursor.
- Clear pending insertion.

Algorithm information:

- Is this an algorithm?
- Algorithm Steps.

Reference information:

- Load previous reference from the same source.
- Optional `.bib` uploader.
- BibTeX entry selector.
- Use selected BibTeX entry.
- Reference Type.
- Author.
- Source/Title.
- Year.
- Volume.
- Edition.
- Pages.
- Chapter.
- Section.
- Publisher.
- DOI.
- URL.
- ISBN.
- Citekey.

Teaching context:

- Context Level.
- Formality Degree.

Technical metadata:

- Uses Formal Notation.
- Includes Proof.
- Is Operational Definition.
- Is Fundamental Concept.
- Required Previous Concepts.
- Includes Example.
- Is Self-Contained.
- Presentation Type.
- Symbolic Level.
- Application Type.

Other fields and actions:

- Comment.
- Save Concept.
- Generate and open PDF, when available in the current form flow.

## Edit Concept

The Edit Concept page loads and updates an existing concept. It mirrors the Add Concept structure, with edit-state versions of the same fields:

- concept identity and source,
- title and title type,
- categories,
- LaTeX editor and helper toolbar,
- algorithm fields,
- reference fields,
- teaching context,
- technical metadata,
- comments.

Main actions:

- Load selected concept.
- Save changes.
- Generate and open PDF.
- Delete concept, when enabled by the current edit flow.

## Browse Concepts

Browse Concepts is for inspection, filtering, and quick actions.

Typical controls:

- Source filter.
- Concept type filter.
- Text search.
- Category filters.
- Result limit.
- Expandable concept cards.
- LaTeX preview.
- Metadata display.
- Relation/context display when available.
- Quick actions such as edit, PDF/export, or delete depending on the selected concept.

## Manage Relations

Manage Relations creates and reviews semantic links between concepts.

Relation fields:

- Source concept.
- Target concept.
- Relation type.
- Justification or notes, when shown by the relation workflow.
- Relation validation guidance for:
  - `equivalente`
  - `implica`
  - `requiere_concepto`
  - `deriva_de`
  - `inspirado_en`
  - `contrasta_con`
  - `contradice`
  - `contra_ejemplo`

Main actions:

- Add relation.
- Browse existing relations.
- Filter relations.
- Delete or update relation entries when available.

## Knowledge Graph

The Knowledge Graph page visualizes concepts and relations using an interactive network.

### Nuevo mapa

Generation fields:

- Select Sources.
- Select Concept Types.
- Select Relation Types.
- Max Depth.
- Generate Graph.

Save generated map fields:

- Nombre del mapa.
- Descripcion.
- Tags, separated by commas.
- Estado JSON actual del grafo.
- Guardar mapa generado.

The saved document is stored in `knowledge_graph_maps` with:

- `name`
- `description`
- `tags`
- `filters.sources`
- `filters.concept_types`
- `filters.relation_types`
- `filters.max_depth`
- `graph_state`
- `source`
- `map_uid`
- `created_at`
- `updated_at`

### Mapas guardados

List and filter fields:

- Buscar por nombre.
- Filtrar por tag.
- Filtrar por fuente.
- Filtrar por tipo.

Actions:

- Ver.
- Editar.
- Duplicar.
- Confirmar eliminacion.
- Eliminar.

### Editar mapa

Edit metadata and rebuild the map from filters while preserving existing positions where possible.

Fields:

- Mapa para editar.
- Nombre del mapa.
- Descripcion.
- Tags.
- Fuentes.
- Tipos de concepto.
- Tipos de relacion.
- Max depth.
- Estado JSON actual del grafo.

Action:

- Guardar cambios del mapa.

### Exportar / importar

Fields and actions:

- Mapa para exportar.
- Descargar JSON guardado.
- Descargar HTML restaurado.
- Nombre del mapa importado.
- Descripcion.
- Tags.
- Estado JSON.
- Importar estado JSON.

### In-Graph Controls

The rendered graph panel includes browser-side controls for:

- physics parameters,
- activation/freezing/resetting physics,
- fixing and releasing selected nodes,
- separating nodes by type/source/component,
- edge style and curvature,
- label alignment,
- node label size,
- edge label size,
- current HTML download,
- current graph-state JSON copy/download.

## Document Builder

Document Builder assembles selected concepts into larger documents.

Common controls:

- Source and concept selection.
- Document ordering.
- Preview.
- Export or build action.
- LaTeX/PDF oriented output controls, depending on the selected builder mode.

## Export

The Export page exports concepts and sources to LaTeX/PDF-oriented outputs.

Fields and actions:

- Source selector.
- Concept/type selector, depending on mode.
- Output directory.
- Export selected source/concept.
- Bulk export all sources.
- Progress bar and status text.

## Database Export

Creates a read-only ZIP backup of the active MongoDB database.

Fields and actions:

- Export database.
- Download ZIP.

The ZIP includes every collection in the active database and expected project collections even when empty, including `knowledge_graph_maps`.

## Database Import

Imports a ZIP backup into a new MongoDB database.

Fields and actions:

- Upload database export `.zip`.
- Preview exported timestamp.
- Preview collection names and document counts.
- New database name.
- Import into new database.

The import flow is conservative: it does not overwrite an existing active database automatically.

## Settings

Settings shows database and application maintenance controls.

Fields and actions:

- Connected database status.
- Total Concepts.
- Total Relations.
- Sources.
- Categories.
- Clear All Data.
- Confirm Clear All.
- Cancel.
- Rebuild Indexes.
- Application version.
- Author/license information.

Rebuild Indexes includes indexes for:

- `concepts`
- `latex_documents`
- `relations`
- `knowledge_graph_maps`

## Cuaderno

Cuaderno appears only after its MongoDB collections are installed.

Install for the active database:

```bash
python scripts/install_cuaderno_mode.py --mongo-uri mongodb://127.0.0.1:27017 --db MathV0
```

Check status for that same active database:

```bash
python scripts/install_cuaderno_mode.py --status --mongo-uri mongodb://127.0.0.1:27017 --db MathV0
```

Cornell notes use the existing `latex_notes` collection, not a separate `cornell_notes` collection. They are distinguished by `note_format = "cornell_math_v1"` and keep their canonical structure in `cornell.schema_version`, `cornell.template_id`, `cornell.pages`, `cornell.attribution`, and `cornell.watermark`. The installer is idempotent and adds the Cornell indexes `latex_note_format`, `latex_note_format_date_desc`, `latex_note_format_project`, and `latex_note_format_context` when missing.

Cornell supports per-region images, optional footer attribution, and text or image watermarks. Editable Cornell project export creates a self-contained folder with `Notas.tex`, `Izquierda.tex`, `Derecha.tex`, `Abajo.tex`, `A.tex`, `B.tex`, `C.tex`, `contenido/pagina_NNN/`, `images/`, `metadata.json`, and `README.md`. Compile the regional documents first, then `Notas.tex`. Cleanup of generated projects should keep source `.tex`, metadata, README, required images such as `lineas.png`, and final `Notas.pdf` when present; remove only LaTeX auxiliaries and selected regenerable intermediate PDFs.

### Diary Notes

New note fields:

- Titulo.
- Fecha.
- Proyecto.
- Contexto.
- Tags.
- LaTeX note body.
- Vista previa simple.

Edit note fields:

- Titulo.
- Fecha.
- Proyecto.
- Contexto.
- Tags.
- LaTeX note body.

Actions:

- Guardar nota.
- Guardar cambios.
- Cancelar.
- Borrar definitivamente.
- Descargar TEX.
- Descargar PDF.

Search/filter fields:

- Texto en titulo o cuerpo.
- Proyecto.
- Contexto.
- Desde.
- Hasta.
- Tags.
- Limite.
- Ano.
- Mes.
- Actualizadas recientemente.

Project/timeline/calendar fields:

- Notas a cargar.
- Ano.
- Mes.
- Dia con notas.
- Ver notas del proyecto.

### LaTeX Tools in Cuaderno

Diary LaTeX helper buttons include:

- Definicion.
- Teorema.
- Lema.
- Proposicion.
- Corolario.
- Prueba.
- Ejemplo.
- Nota/Remark.
- Ecuacion.
- Align.
- Matrix.
- Cases.
- Itemize.
- Enumerate.
- Description.
- Codigo/listing.
- DirTree.
- Common symbols and semantic snippets.

### Worklog

Create fields:

- Date.
- Block: AM, PM, Noche.
- Hours.
- Status.
- Project.
- Module.
- Task.
- Next step.
- Descripcion/Evidencia.
- Evidence URL/path.
- Tags.

Edit fields:

- Date.
- Status.
- Project.
- Module.
- Task.
- Descripcion/Evidencia.

Export/filter fields:

- Export mode.
- Desde.
- Hasta.
- Limite.
- Project.
- Status.
- Texto search.
- Row selection.

Actions:

- Add Worklog Entry.
- Guardar cambios.
- Crear Worklog Entry desde Backlog.
- Borrar definitivamente.
- Descargar CSV.

### Backlog

Create fields:

- Project.
- Module.
- Owner.
- Priority: Alta, Media, Baja.
- Status: Todo, Doing, Done, Blocked, Canceled.
- Task.
- Description.
- Estimate hours.
- Set target date.
- Target date.
- Tags.

Filter/export fields:

- Project.
- Status.
- Priority.
- Desde.
- Hasta.
- Limite.
- Owner.
- Texto search.
- Row selection.

Edit fields:

- Status.
- Priority.
- Owner.
- Task.
- Description.
- Tags.

Actions:

- Guardar backlog item.
- Guardar cambios.
- Descargar CSV.

### Weekly Review

Core fields:

- ISO Year.
- ISO Week.
- Weekly objectives.
- Wins.
- Blocks/Risks.
- Plan next week.

Derived metrics:

- Real hours worked.
- Tasks completed.
- Activity summary.

Override fields:

- Override metrics checkbox.
- Real hours override.
- Tasks completed override.

Export/filter fields:

- Export mode.
- Desde.
- Hasta.
- Limite.
- ISO Year.
- ISO Week.
- Texto search.
- Row selection.

Actions:

- Nueva Weekly Review.
- Recargar desde BD.
- Guardar Weekly Review.
- Cargar en editor.
- Borrar Weekly Review.
- Descargar CSV.

### Deliverables

Create fields:

- Fecha.
- Proyecto.
- Type:
  - reporte
  - codigo
  - dataset
  - presentacion
  - evidencia
  - otro
- Deliverable nombre.
- Ruta/URL.
- Commit ref.
- Tags.
- Notas.

Filter/export fields:

- Project filter.
- Type filter.
- Limit.
- Desde.
- Hasta.
- Proyecto.
- Texto search.
- Row selection.

Edit fields:

- Fecha.
- Proyecto.
- Type.
- Deliverable nombre.
- Ruta/URL.
- Commit ref.
- Tags.
- Notas.

Actions:

- Guardar entregable.
- Cargar.
- Guardar cambios.
- Descargar CSV.

### Kanban

Kanban fields and actions:

- Project selector.
- Refresh.
- Status selector per card.
- Apply status change.

## Troubleshooting

MongoDB is not connected:

```bash
sudo systemctl start mongod
sudo systemctl status mongod
```

Cuaderno does not appear:

```bash
python scripts/install_cuaderno_mode.py --mongo-uri mongodb://127.0.0.1:27017 --db <ACTIVE_DB_NAME>
```

PDF export fails:

```bash
pdflatex --version
```

Quarto export fails:

```bash
quarto --version
quarto check
```

Port 8501 is busy:

```bash
streamlit run editor/editor_streamlit.py --server.port 8502
```

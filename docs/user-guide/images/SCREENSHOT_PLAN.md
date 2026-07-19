# Screenshot plan — Reading Space guide refresh

- Phase: `READING-SPACE-GUIDE-REFRESH`
- Target version: `0.13.0`
- Temporary database: `MathMongoReadingSpaceGuide_9b11e538`
- Database safety check: absent before use; name differs from `MathV0` and `mathmongo`
- Data policy: synthetic content only; no personal data, real bibliography, or real identifiers
- Visual baseline: MathMongo dark theme, 1600 × 1000 CSS-pixel viewport, device scale factor 1, browser zoom 100%
- Capture boundary: rendered application viewport only; no desktop, browser chrome, notifications, or unrelated applications
- Asset directory: `docs/user-guide/images/reading-space-v013/`

The twelve captures use the same temporary database and synthetic corpus. The Source is `GuiaAlgebraLineal` (book; tags `demo`, `algebra-lineal`, `reading-space`), its Reference is “Introducción al álgebra lineal” by “Autor de ejemplo” (2026, without ISBN), and the managed Concepts are `espacio_vectorial`, `base_vectorial`, and `transformacion_lineal`. A separate unlinked legacy pair is used only to demonstrate the explicit linking workflow.

| # | Filename | Guide section | Page / route | Initial state | Action shown | Synthetic data | Exact region | Caption | Alt text | Resolution | Status |
|---:|---|---|---|---|---|---|---|---|---|---|---|
| 01 | `reading-space-v013/01_active_database.png` | 4. Base activa | Sidebar + home | App connected directly to the temporary database | Verify the visible database identity before writing | Empty/seeded temporary database only | Full 1600 × 1000 app viewport, sidebar and connection card visible | Confirmación de la base temporal activa antes de editar | Barra lateral de MathMongo mostrando la conexión y la base temporal activa | 1600 × 1000 | validated |
| 02 | `reading-space-v013/02_add_source.png` | 5. Crear una Source | `➕ Add Source` | Catalog indexes ready; no form submission in progress | Fill the Source form and display the review-ready values | `GuiaAlgebraLinealNueva`, book, demo tags | Full app viewport with form header and identity fields visible | Alta de una Source gestionada con nombre, tipo y etiquetas sintéticas | Formulario Add Source completado para GuiaAlgebraLinealNueva | 1600 × 1000 | validated |
| 03 | `reading-space-v013/03_source_details.png` | 5. Crear una Source | `📚 Sources` → Analyze/Edit | Source, Reference, and PDF document already created | Inspect source identity, reference, and attached document | Synthetic Source/Reference/demo PDF | Full app viewport centered on identity and document summary | Detalle de la Source creada, su referencia y el documento PDF asociado | Vista de detalle de GuiaAlgebraLineal con referencia y documento | 1600 × 1000 | validated |
| 04 | `reading-space-v013/04_add_concept.png` | 6. Añadir un concepto nuevo | `➕ Add Concept` | Managed Source active and selectable | Show the required Source selection and concept fields before saving | `concepto_demo_nuevo` alongside the existing managed concepts | Full app viewport with Source selector, stable identity and editor fields | Un concepto nuevo nace asociado a una Source gestionada | Formulario Add Concept con Source gestionada y concepto sintético | 1600 × 1000 | validated |
| 05 | `reading-space-v013/05_reading_space.png` | 7. Abrir Reading Space | `📖 Reading Space` | Source document and reading indexes ready | Filter/select the Source and show the library document card | One synthetic 4-page PDF | Full app viewport with Reading Space tabs and document list | Biblioteca de Reading Space filtrada por la Source de demostración | Reading Space con GuiaAlgebraLineal y su documento disponible | 1600 × 1000 | validated |
| 06 | `reading-space-v013/06_advanced_reader.png` | 8. Leer en Advanced Reader | `/reader?document_id=…` | Advanced Reader bound to the same temporary database | Open the PDF at its definition/equation page | Synthetic PDF page 2 | Full Advanced Reader viewport, toolbar and PDF canvas visible | Lectura avanzada del PDF sin salir del contexto documental | Advanced Reader mostrando una página del PDF sintético | 1600 × 1000 | validated |
| 07 | `reading-space-v013/07_evidence_link.png` | 9. Crear anotaciones y evidence | Reading Space workspace | Existing synthetic annotation loaded | Show annotation metadata and its link to a managed Concept | Page-2 highlight linked to `espacio_vectorial` | Full app viewport focused on Annotations/Evidence panel | Una anotación de lectura enlazada como evidencia de un concepto | Panel de anotaciones con evidencia enlazada a espacio_vectorial | 1600 × 1000 | validated |
| 08 | `reading-space-v013/08_cuaderno.png` | 10. Trabajar en Cuaderno | `📖 Reading Space` → Cuaderno | Reading note exists for the selected document | Show the note workspace with page/document context | Synthetic note “Ideas sobre bases” | Full app viewport focused on Cuaderno tab and note card | El Cuaderno conserva notas dentro del contexto de lectura | Cuaderno de Reading Space con una nota sintética del documento | 1600 × 1000 | validated |
| 09 | `reading-space-v013/09_cuaderno_promote.png` | 11. Promover desde Cuaderno | `🧪 Cuaderno` | Cuaderno mode installed only in the temporary database; synthetic fragment ready | Display the Promote-to-Concept controls and managed Source target | Fragment “Criterio de base” → `base_vectorial_desde_cuaderno` | Full app viewport with promotion controls and Source selection | Promoción explícita de un fragmento del Cuaderno a concepto gestionado | Controles de promoción desde Cuaderno hacia un ID nuevo | 1600 × 1000 | validated |
| 10 | `reading-space-v013/10_edit_concept.png` | 12. Editar conceptos | `✏️ Edit Concept` | Managed concept exists with stable ID and `source_id` | Show editable content alongside immutable identity | `espacio_vectorial` | Full app viewport with identity notice and editable fields | Edit Concept mantiene inmutables la identidad y la Source | Edición de espacio_vectorial con identidad gestionada visible | 1600 × 1000 | validated |
| 11 | `reading-space-v013/11_legacy_link.png` | 13. Conceptos legacy | Legacy Read Only → `✏️ Edit Concept` | One exact legacy concept/LaTeX pair has no `source_id`; it was opened from the Source legacy list | Select the active managed Source and show the guarded Link action without executing it | `subespacio_legacy` / `ReferenciaLegacyDemo` | Full app viewport focused on immutable legacy identity and link controls | Enlace explícito de un par legacy a una Source existente | Edit Concept mostrando el par legacy exacto y el botón para enlazarlo | 1600 × 1000 | validated |
| 12 | `reading-space-v013/12_document_builder_or_graph.png` | 14. Document Builder y Knowledge Maps | `📄 Document Builder` | Three managed synthetic concepts available | Select concepts and display the modular document preview/list | Three demo concepts from one Source | Full app viewport with selection and build controls visible | Document Builder reutiliza conceptos gestionados para una salida modular | Document Builder con conceptos sintéticos seleccionables | 1600 × 1000 | validated |

## Validation checklist

For every final PNG:

- [x] The visible database is `MathMongoReadingSpaceGuide_9b11e538` or the view is demonstrably tied to that same runtime.
- [x] The image contains only synthetic data defined above.
- [x] No browser/desktop chrome, personal data, popup, warning toast, or unrelated application is visible.
- [x] Text is legible at the guide's PDF width and the crop includes the action described by its caption.
- [x] Theme, viewport, scale factor, and zoom match the visual baseline.
- [x] The guide introduces the image, states what to observe, and gives the next action.

The contact sheet and all twelve full-resolution PNGs were inspected. Every final asset passed the checklist above.

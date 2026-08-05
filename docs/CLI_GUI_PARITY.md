# Matriz de paridad GUI–CLI

Auditoría realizada antes de implementar comandos académicos. `READY_SERVICE`
significa que el CLI puede reutilizar una capa de dominio existente; no autoriza
MongoDB directo desde un handler. `NEEDS_EXTRACTION` indica lógica actualmente
atada a una página Streamlit que debe extraerse antes de exponer escritura.

| Área | Operación GUI | UI | Servicio / repositorio canónico | Mongo / XDG | Confirmación | Comando CLI v1 | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Runtime/config | Diagnóstico de configuración | `mathmongo/cli.py` | `resolve_config`, `RuntimeController` | XDG runtime | No | `config`, `doctor`, `runtime *` | READY_SERVICE / READ_ONLY |
| Runtime/config | Inicio, cierre y reinicio local | `Makefile` | `RuntimeController` | XDG runtime, procesos locales | identidad confirmada | `runtime start/stop/restart` | SAFE_WRITE |
| Backup | Respaldo/validación portable | páginas Settings y utilidades | `mathmongo.backup` | lectura Mongo, ZIP XDG | salida explícita | `backup` | READY_SERVICE |
| Sources | Listar, buscar, mostrar | Add/Edit Source | `SourceCatalogService`, `SourceRepository` | `sources` | No | `source list/search/show` | READY_SERVICE / READ_ONLY |
| Sources | Crear | Add Source | `SourceCatalogService.create_source` | `sources` | vista previa, duplicados, base exacta | `source add` | SAFE_WRITE |
| Sources | Editar | Edit Source | `SourceCatalogService.update_source` | `sources` | preview, duplicados | `source edit` | SAFE_WRITE |
| References | Listar, buscar, mostrar | Add/Edit Source | `SourceCatalogService`, `ReferenceRepository` | `references` | No | `reference list/search/show` | READY_SERVICE / READ_ONLY |
| References | Crear, editar, asociar Source | Add/Edit Source | `create_reference`, `update_reference` | `references` | duplicados, Source existente | `reference add/edit` | SAFE_WRITE |
| Documents | Listar y metadatos | `source_catalog/document_ui.py` | `SourceDocumentService`, repository | `source_documents` | No | `document list/show` | READY_SERVICE / READ_ONLY |
| Documents | Adjuntar PDF | `source_catalog/document_ui.py` | `SourceDocumentService`, `SourceDocumentBlobStore` | `source_documents`, blobs XDG | hash, PDF, duplicados, base | `document attach` | MULTISTEP_WRITE |
| Documents | Verificar y descargar | Document UI / Reader | `inspect_document`, `document_pdf_payload` | lectura blobs XDG | No | `document verify/export` | READY_SERVICE / READ_ONLY |
| Reading Space | Listar y mostrar estado | `reading_space/reader_page.py` | `ReadingSpaceService` | documentos y `document_reading_state` | No | `reading list/show` | READY_SERVICE / READ_ONLY |
| Reading Space | Progreso/estado | Reader | `ReadingSpaceService` | `document_reading_state` | expected version si existe | `reading progress` | SAFE_WRITE |
| Concepts | Listar, buscar, mostrar | `editor_streamlit.py`, `concept_linking` | repositorio legacy de conceptos | `concepts`, `latex_documents` | No | `concept list/search/show` | NEEDS_EXTRACTION |
| Concepts | Crear | Nuevo concepto | `insert_concept_with_latex_atomic` | `concepts`, `latex_documents` | preview | `concept add` | NEEDS_EXTRACTION |
| Concepts | Editar | Editar concepto | `update_concept_fields_preserving_identity` | `concepts`, `latex_documents` | compare-and-set disponible | `concept edit` | READY_SERVICE |
| Relaciones | Listar | Relaciones/Grafo | consultas UI directas | `relations` | No | `concept relation list` | NEEDS_EXTRACTION |
| Relaciones | Añadir, editar, retirar | Relaciones | lógica directa en `editor_streamlit.py` | `relations` | preview / retiro explícito | `concept relation add/remove` | NEEDS_EXTRACTION |
| Cuaderno | Listar, mostrar, cuerpo | `cuaderno_page.py` | consultas de página directas | `latex_notes` | No | `note list/show/body` | NEEDS_EXTRACTION |
| Cuaderno | Crear y editar | `cuaderno_page.py` | CRUD de página directo | `latex_notes` | preview | `note create/edit` | NEEDS_EXTRACTION |
| Cuaderno | Exportar TEX ZIP/PDF | `note_export.py` | `export_note_tex`, `export_note_pdf` | archivos de exportación | ruta explícita | `note export` | READY_SERVICE |
| Cornell | Listar y mostrar | `cornell/streamlit_page.py` | `list_cornell_notes`, `get_cornell_note` | `latex_notes` | No | `cornell list/show` | READY_SERVICE / READ_ONLY |
| Cornell | Crear y editar metadatos | Cornell | `create_cornell_note`, `update_cornell_note` | `latex_notes` | preview | `cornell create/edit` | READY_SERVICE |
| Cornell | Añadir, editar, retirar página | Cornell | modelos `CornellDocument` + `update_cornell_note` | `latex_notes` | retiro con confirmación | `cornell page *` | NEEDS_EXTRACTION |
| Cornell | Adjuntar media | Cornell | `upload_cornell_region_image`, `save_media_asset` | `media_assets`, XDG media | hash/MIME/región | `cornell media attach` | NEEDS_EXTRACTION |
| Cornell | PDF y proyecto TEX ZIP | Cornell | renderer y `export_cornell_project` | exportación | ruta explícita | `cornell export` | READY_SERVICE |
| CPI | Listar y mostrar | `cpi/streamlit_page.py` | `list_cpi_notes`, `get_cpi_note` | `latex_notes` | No | `cpi list/show` | READY_SERVICE / READ_ONLY |
| CPI | Crear y editar metadatos | CPI | `create_cpi_note`, `update_cpi_note` | `latex_notes` | preview | `cpi create/edit` | READY_SERVICE |
| CPI | Añadir, editar, retirar página | CPI | modelos `CpiDocument` + `update_cpi_note` | `latex_notes` | retiro con confirmación | `cpi page *` | NEEDS_EXTRACTION |
| CPI | Adjuntar media | CPI | `save_media_asset`, UI wiring | `media_assets`, XDG media | hash/MIME/región | `cpi media attach` | NEEDS_EXTRACTION |
| CPI | PDF y proyecto TEX ZIP | CPI | renderer y `export_cpi_project` | exportación | ruta explícita | `cpi export` | READY_SERVICE |
| Media | Guardar, asociar, desacoplar | Cuaderno/Cornell/CPI | `editor.utils.media_assets` | `media_assets`, XDG media | hash/MIME | comandos de nota | NEEDS_EXTRACTION |
| Exportaciones globales | Exportar base/importar/migrar | Settings/Import | backup/importadores | Mongo/ZIP | alto riesgo | `backup` solamente | DEFERRED |

## Exclusiones v1

- Borrado masivo, `Clear All Data`, `dropDatabase`, migraciones y cambios de
  índices/validadores reales.
- Importador ZIP Cornell/CPI, sincronización externa, Waveform Lab y edición de
  audio.
- Restauración/importación de bases y cualquier operación sobre la base
  `mathmongo`.

## Consecuencia de la auditoría

La primera entrega del CLI sólo puede declarar paridad de escritura para
Sources, References, Documents, Reading Space, Cornell/CPI de documento entero
y exportadores ya aislados. Concepts, relations y Cuaderno necesitan una capa
de servicio extraída; las páginas Cornell/CPI y media necesitan adaptadores
puros de mutación de página antes de poder garantizar preview, concurrencia y
reporte parcial.

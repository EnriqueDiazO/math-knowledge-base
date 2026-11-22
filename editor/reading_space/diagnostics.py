"""Explicit diagnosis destination; opening it performs inspections, never repairs."""

from editor.reading_annotations import render_notes_evidence_maintenance
from editor.reading_space.page_map_panel import render_page_map_maintenance
from editor.reading_space.reader_page import _render_index_status
from editor.source_catalog.shared import render_catalog_status
from mathmongo.document_page_maps.service import DocumentPageMapService
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_space.service import ReadingSpaceService


def render_reading_diagnostics(context, *, ui=None):
    """Keep existing explicit confirmations and conflict-blocking procedures."""
    if ui is None:
        import streamlit as ui
    ui.title('Diagnóstico de la biblioteca')
    ui.caption(f'Biblioteca activa: {context.database_name}. Consultar esta página no aplica cambios.')
    ui.info('La preparación compatible crea sólo lo que falta. Los conflictos y duplicados necesitan revisión; aquí no se sustituyen índices ni se migran datos automáticamente.')
    with ui.expander('Catálogo y referencias', expanded=False):
        render_catalog_status(ui, context, allow_index_initialization=True)
    with ui.expander('Posición e historial de lectura', expanded=False):
        _render_index_status(ui, context, ReadingSpaceService(context.database), maintenance=True)
    with ui.expander('Notas y subrayados', expanded=False):
        render_notes_evidence_maintenance(context, ui=ui, service=ReadingAnnotationService(context.database))
    with ui.expander('Numeración de documentos', expanded=False):
        render_page_map_maintenance(ui, context, DocumentPageMapService(context.database))

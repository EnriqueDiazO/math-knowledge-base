"""Streamlit UI for manual reading annotations and legacy concept evidence."""

from editor.reading_annotations.annotation_panel import render_evidence_tab
from editor.reading_annotations.annotation_panel import render_notebook_tab
from editor.reading_annotations.annotation_panel import render_notes_and_evidence_panel
from editor.reading_annotations.annotation_panel import render_notes_evidence_maintenance
from editor.reading_annotations.annotation_panel import render_notes_tab
from editor.reading_annotations.annotation_panel import render_workspace_notes_panel

__all__ = [
    "render_evidence_tab",
    "render_notes_and_evidence_panel",
    "render_notes_evidence_maintenance",
    "render_notes_tab",
    "render_notebook_tab",
    "render_workspace_notes_panel",
]

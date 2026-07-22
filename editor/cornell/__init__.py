"""Cornell-format math note rendering helpers."""

from editor.cornell.models import CORNELL_NOTE_FORMAT
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.models import build_cornell_math_v1_payload
from editor.cornell.models import build_footer_text
from editor.cornell.models import generate_latex_body
from editor.cornell.persistence import build_cornell_note_document
from editor.cornell.persistence import extract_cornell_document
from editor.cornell.persistence import is_cornell_note
from editor.cornell.project_export import CornellProjectExportResult
from editor.cornell.project_export import export_cornell_project
from editor.cornell.renderer import CornellRenderResult
from editor.cornell.renderer import generate_cornell_document_tex
from editor.cornell.renderer import generate_cornell_tex
from editor.cornell.renderer import measure_cornell_page_fit
from editor.cornell.renderer import render_cornell_document
from editor.cornell.renderer import render_cornell_pdf
from editor.cornell.service import create_cornell_note
from editor.cornell.service import delete_cornell_note
from editor.cornell.service import duplicate_cornell_note
from editor.cornell.service import get_cornell_note
from editor.cornell.service import list_cornell_notes
from editor.cornell.service import update_cornell_note

__all__ = [
    "CORNELL_NOTE_FORMAT",
    "DEFAULT_TEMPLATE_ID",
    "CornellDocument",
    "CornellAttribution",
    "CornellPage",
    "CornellProjectExportResult",
    "CornellRegion",
    "CornellRenderResult",
    "CornellWatermark",
    "build_cornell_math_v1_payload",
    "build_cornell_note_document",
    "build_footer_text",
    "create_cornell_note",
    "delete_cornell_note",
    "duplicate_cornell_note",
    "extract_cornell_document",
    "export_cornell_project",
    "generate_cornell_document_tex",
    "generate_cornell_tex",
    "generate_latex_body",
    "get_cornell_note",
    "is_cornell_note",
    "list_cornell_notes",
    "measure_cornell_page_fit",
    "render_cornell_document",
    "render_cornell_pdf",
    "update_cornell_note",
]

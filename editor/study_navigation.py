"""Logical room navigation through canonical reading services; no document copies."""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from pymongo.errors import PyMongoError

from editor.reading_annotations.state import open_document_at_page
from editor.reading_annotations.state import select_annotation
from editor.reading_annotations.state import select_note
from editor.reading_space.state import queue_current_page_value
from editor.reading_space.state import request_reading_space_navigation
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.source_documents.repository import SourceDocumentRepository

STUDY_ROOM_NAV_LABEL = 'Habitación de estudio'
ROOM_RETURN = 'mathmongo_room_return'


def add_study_room_navigation(options: list[str]) -> list[str]:
    """Keep all existing pages and insert the study entrance beside its graph."""
    if STUDY_ROOM_NAV_LABEL in options:
        return list(options)
    updated = list(options)
    anchor = updated.index('🗺️ Grafo de conocimiento') + 1 if '🗺️ Grafo de conocimiento' in updated else len(updated)
    updated.insert(anchor, STUDY_ROOM_NAV_LABEL)
    return updated


def open_room_source(state: MutableMapping[str, Any], database, payload: dict) -> bool:
    """Validate exact IDs/associations before queuing the existing reader and locator."""
    if not isinstance(payload, dict) or not isinstance(payload.get('document_id'), str):
        return False
    try:
        document = SourceDocumentRepository(database).get_by_id(payload['document_id'])
        if document is None or document.status.value != 'active':
            return False
        page = None
        reading = ReadingAnnotationService(database)
        if payload.get('annotation_id'):
            result = reading.get_annotation(payload['annotation_id'])
            mark = result.value if result.completed else None
            if mark is None or mark.document_id != document.document_id or mark.source_id != document.source_id or mark.status.value != 'active':
                return False
            page = mark.page_number
        if payload.get('note_id'):
            result = reading.get_note(payload['note_id'])
            note = result.value if result.completed else None
            if note is None or note.document_id != document.document_id or note.source_id != document.source_id or note.status.value != 'active':
                return False
            if page is None:
                page = note.page_start
        open_document_at_page(state, source_id=document.source_id, document_id=document.document_id, page_number=page)
        # Reading Space's queue survives the S4 context reset on first entry
        # after a reload; S4's page suggestion alone is cleared by that reset.
        if page is not None and document.kind.value == 'pdf':
            queue_current_page_value(state, document_id=document.document_id, page_number=page)
        if payload.get('annotation_id'):
            select_annotation(state, payload['annotation_id'])
        elif payload.get('note_id'):
            select_note(state, payload['note_id'])
        request_reading_space_navigation(state, source_id=document.source_id,
            document_id=document.document_id, kind=document.kind.value)
        state[ROOM_RETURN] = True
        return True
    except (ValueError, TypeError, PyMongoError):
        return False

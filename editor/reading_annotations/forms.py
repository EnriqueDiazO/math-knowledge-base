"""Plain-text Streamlit forms for S4 annotations and reading notes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from editor.reading_annotations.state import state_key
from editor.source_catalog.shared import split_values

ANNOTATION_KINDS = ("highlight", "underline", "comment", "bookmark", "question")
NOTE_TYPES = (
    "summary",
    "idea",
    "proof",
    "definition",
    "question",
    "todo",
    "bibliography",
    "general",
)


@dataclass(frozen=True, slots=True)
class AnnotationDraft:
    """Sanitized widget values for one logical/manual annotation."""

    kind: str
    page_number: int | None
    page_label: str | None
    quote_text: str | None
    body: str
    color_label: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReadingNoteDraft:
    """Sanitized widget values for one plain-text reading note."""

    title: str
    note_type: str
    body: str
    document_id: str | None
    reference_id: str | None
    page_start: int | None
    page_end: int | None
    tags: tuple[str, ...]


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _reference_label(reference: Any) -> str:
    return str(
        getattr(reference, "title", None)
        or getattr(getattr(reference, "bibtex", None), "key", None)
        or getattr(reference, "reference_id", "Reference")
    )


def reference_options(references: tuple[Any, ...] | list[Any]) -> tuple[tuple[str, str], ...]:
    """Return bounded logical Reference IDs and labels for a selectbox."""
    return tuple(
        (str(reference.reference_id), f"{_reference_label(reference)} ({reference.reference_id})")
        for reference in references
        if isinstance(getattr(reference, "reference_id", None), str)
    )


def _select_reference(
    ui: Any,
    *,
    options: tuple[tuple[str, str], ...],
    key: str,
    default_id: str | None,
) -> str | None:
    labels = {reference_id: label for reference_id, label in options}
    identities = ("", *labels)
    try:
        default_index = identities.index(default_id or "")
    except ValueError:
        default_index = 0
    selected = ui.selectbox(
        "Reference (optional)",
        options=identities,
        index=default_index,
        format_func=lambda value: "No Reference" if not value else labels.get(value, value),
        key=key,
    )
    return str(selected) if selected else None


def render_annotation_form(
    ui: Any,
    *,
    document_id: str,
    is_pdf: bool,
    suggested_page: int | None,
    form_key: str,
    initial: Any | None = None,
    submit_label: str = "Add Annotation",
    actions_enabled: bool = True,
) -> AnnotationDraft | None:
    """Render an annotation form; web Documents never receive PDF page controls."""
    initial_kind = str(
        getattr(getattr(initial, "kind", None), "value", None)
        or getattr(initial, "kind", "highlight")
    )
    try:
        kind_index = ANNOTATION_KINDS.index(initial_kind)
    except ValueError:
        kind_index = 0
    initial_page = getattr(initial, "page_number", None)
    page_default = initial_page or suggested_page or 1
    with ui.form(key=state_key(form_key, document_id)):
        kind = ui.selectbox(
            "Annotation kind",
            options=ANNOTATION_KINDS,
            index=kind_index,
            key=state_key(form_key, "kind", document_id),
        )
        page_number: int | None = None
        page_label: str | None = None
        if is_pdf:
            attach_page = ui.checkbox(
                "Attach to PDF page",
                value=initial_page is not None or suggested_page is not None,
                key=state_key(form_key, "attach_page", document_id),
            )
            if attach_page:
                page_number = int(
                    ui.number_input(
                        "Page number",
                        min_value=1,
                        value=int(page_default),
                        step=1,
                        key=state_key(form_key, "page", document_id),
                        width="stretch",
                    )
                )
                page_label = _optional_text(
                    ui.text_input(
                        "Page label (optional)",
                        value=str(getattr(initial, "page_label", None) or ""),
                        key=state_key(form_key, "page_label", document_id),
                    )
                )
        quote_text = _optional_text(
            ui.text_area(
                "Quoted text (manual, optional)",
                value=str(getattr(initial, "quote_text", None) or ""),
                key=state_key(form_key, "quote", document_id),
            )
        )
        body = str(
            ui.text_area(
                "Comment",
                value=str(getattr(initial, "body", "") or ""),
                key=state_key(form_key, "body", document_id),
            )
            or ""
        ).strip()
        color_label = _optional_text(
            ui.text_input(
                "Color label (optional)",
                value=str(getattr(initial, "color_label", None) or ""),
                key=state_key(form_key, "color", document_id),
            )
        )
        tags_value = ui.text_input(
            "Tags (comma separated)",
            value=", ".join(getattr(initial, "tags", ()) or ()),
            key=state_key(form_key, "tags", document_id),
        )
        submitted = ui.form_submit_button(
            submit_label,
            key=state_key(form_key, "submit", document_id),
            disabled=not actions_enabled,
        )
    if not submitted:
        return None
    return AnnotationDraft(
        kind=str(kind),
        page_number=page_number,
        page_label=page_label,
        quote_text=quote_text,
        body=body,
        color_label=color_label,
        tags=tuple(split_values(str(tags_value or ""))),
    )


def render_note_form(
    ui: Any,
    *,
    source_id: str,
    document_id: str,
    is_pdf: bool,
    suggested_page: int | None,
    references: tuple[Any, ...] | list[Any],
    form_key: str,
    initial: Any | None = None,
    submit_label: str = "Add Reading Note",
    actions_enabled: bool = True,
) -> ReadingNoteDraft | None:
    """Render a plain-text note that can target Document, Source, or Reference."""
    del source_id  # The Source identity is supplied directly to the domain service.
    initial_document_id = getattr(initial, "document_id", document_id)
    initial_type = str(
        getattr(getattr(initial, "note_type", None), "value", None)
        or getattr(initial, "note_type", "general")
    )
    try:
        type_index = NOTE_TYPES.index(initial_type)
    except ValueError:
        type_index = NOTE_TYPES.index("general")
    initial_page_start = getattr(initial, "page_start", None)
    initial_page_end = getattr(initial, "page_end", None)
    with ui.form(key=state_key(form_key, document_id)):
        title = str(
            ui.text_input(
                "Title",
                value=str(getattr(initial, "title", "") or ""),
                key=state_key(form_key, "title", document_id),
            )
            or ""
        ).strip()
        note_type = ui.selectbox(
            "Note type",
            options=NOTE_TYPES,
            index=type_index,
            key=state_key(form_key, "type", document_id),
        )
        body = str(
            ui.text_area(
                "Body (plain text)",
                value=str(getattr(initial, "body", "") or ""),
                key=state_key(form_key, "body", document_id),
            )
            or ""
        ).strip()
        link_document = ui.checkbox(
            "Link to current Document",
            value=initial_document_id is not None,
            key=state_key(form_key, "link_document", document_id),
        )
        reference_id = _select_reference(
            ui,
            options=reference_options(references),
            key=state_key(form_key, "reference", document_id),
            default_id=getattr(initial, "reference_id", None),
        )
        page_start: int | None = None
        page_end: int | None = None
        if is_pdf and link_document:
            attach_pages = ui.checkbox(
                "Attach PDF page range",
                value=initial_page_start is not None,
                key=state_key(form_key, "attach_pages", document_id),
            )
            if attach_pages:
                start_default = initial_page_start or suggested_page or 1
                end_default = initial_page_end or start_default
                page_start = int(
                    ui.number_input(
                        "Page start",
                        min_value=1,
                        value=int(start_default),
                        step=1,
                        key=state_key(form_key, "page_start", document_id),
                        width="stretch",
                    )
                )
                page_end = int(
                    ui.number_input(
                        "Page end",
                        min_value=1,
                        value=int(end_default),
                        step=1,
                        key=state_key(form_key, "page_end", document_id),
                        width="stretch",
                    )
                )
        tags_value = ui.text_input(
            "Tags (comma separated)",
            value=", ".join(getattr(initial, "tags", ()) or ()),
            key=state_key(form_key, "tags", document_id),
        )
        submitted = ui.form_submit_button(
            submit_label,
            key=state_key(form_key, "submit", document_id),
            disabled=not actions_enabled,
        )
    if not submitted:
        return None
    return ReadingNoteDraft(
        title=title,
        note_type=str(note_type),
        body=body,
        document_id=document_id if link_document else None,
        reference_id=reference_id,
        page_start=page_start,
        page_end=page_end,
        tags=tuple(split_values(str(tags_value or ""))),
    )


__all__ = [
    "ANNOTATION_KINDS",
    "NOTE_TYPES",
    "AnnotationDraft",
    "ReadingNoteDraft",
    "reference_options",
    "render_annotation_form",
    "render_note_form",
]

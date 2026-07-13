"""Legacy concept evidence controls for annotations and reading notes."""

from __future__ import annotations

from typing import Any

from editor.reading_annotations.concept_picker import get_legacy_concept_choice
from editor.reading_annotations.concept_picker import render_concept_picker
from editor.reading_annotations.panel_utils import enum_value
from editor.reading_annotations.panel_utils import render_result
from editor.reading_annotations.panel_utils import result_items
from editor.reading_annotations.panel_utils import result_ok
from editor.reading_annotations.state import open_document_at_page
from editor.reading_annotations.state import select_annotation
from editor.reading_annotations.state import select_note
from editor.reading_annotations.state import state_key

EVIDENCE_LINK_TYPES = (
    "definition_source",
    "theorem_source",
    "proof_source",
    "example_source",
    "motivation",
    "citation",
    "question",
    "related_context",
)


def render_link_form(
    ui: Any,
    database: Any,
    service: Any,
    *,
    source_id: str,
    reference_id: str | None,
    annotation_id: str | None = None,
    note_id: str | None = None,
    actions_enabled: bool,
) -> None:
    """Link exactly one annotation or note to a selected legacy concept."""
    if (annotation_id is None) == (note_id is None):
        raise ValueError("Evidence UI requires exactly one annotation_id or note_id")
    subject_type = "annotation" if annotation_id is not None else "note"
    subject_id = annotation_id or note_id or ""
    ui.caption(f"Link this {subject_type} to a legacy concept (read-only).")
    concept = render_concept_picker(
        ui,
        database,
        subject_key=f"{subject_type}_{subject_id}",
        compact=True,
    )
    with ui.form(key=state_key("evidence_form", subject_type, subject_id)):
        link_type = ui.selectbox(
            "Evidence link type",
            options=EVIDENCE_LINK_TYPES,
            key=state_key("evidence_type", subject_type, subject_id),
        )
        comment = str(
            ui.text_area(
                "Evidence comment (optional)",
                key=state_key("evidence_comment", subject_type, subject_id),
            )
            or ""
        ).strip()
        submitted = ui.form_submit_button(
            "Link to Concept",
            key=state_key("evidence_submit", subject_type, subject_id),
            disabled=not actions_enabled or concept is None,
        )
    if not submitted or concept is None:
        return
    result = service.create_concept_evidence_link(
        concept_legacy_id=concept.concept_id,
        concept_legacy_source=concept.concept_source,
        source_id=source_id,
        reference_id=reference_id,
        document_id=None,
        annotation_id=annotation_id,
        note_id=note_id,
        page_number=None,
        link_type=str(link_type),
        comment=comment or None,
    )
    if render_result(ui, result, success="Concept evidence linked."):
        ui.rerun()


def evidence_origin(item: Any) -> str:
    """Return the explicit logical origin of one evidence link."""
    if item.annotation_id:
        return f"Annotation · {item.annotation_id}"
    if item.note_id:
        return f"Reading Note · {item.note_id}"
    page = f" · page {item.page_number}" if item.page_number is not None else ""
    return f"Document{page} · {item.document_id}"


def _legacy_titles(database: Any, items: tuple[Any, ...]) -> dict[tuple[str, str], str]:
    """Resolve bounded projected titles without retaining concepts in session state."""
    titles: dict[tuple[str, str], str] = {}
    for item in items:
        identity = (item.concept_legacy_id, item.concept_legacy_source)
        if identity in titles:
            continue
        try:
            concept = get_legacy_concept_choice(
                database,
                concept_id=identity[0],
                concept_source=identity[1],
            )
        except Exception:
            concept = None
        titles[identity] = concept.title if concept is not None else ""
    return titles


def evidence_rows(
    items: tuple[Any, ...] | list[Any],
    *,
    legacy_titles: dict[tuple[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    """Build compact display-only rows from evidence metadata."""
    titles = legacy_titles or {}
    return [
        {
            "concept": f"{item.concept_legacy_id} [{item.concept_legacy_source}]",
            "legacy_title": titles.get((item.concept_legacy_id, item.concept_legacy_source), ""),
            "type": enum_value(item.link_type),
            "origin": evidence_origin(item),
            "status": enum_value(item.status),
            "comment": item.comment,
            "evidence_link_id": item.evidence_link_id,
        }
        for item in items
    ]


def render_subject_evidence(
    ui: Any,
    database: Any,
    service: Any,
    *,
    annotation_id: str | None,
    note_id: str | None,
    manage_lifecycle: bool = False,
    actions_enabled: bool = False,
) -> None:
    """Show evidence already linked to exactly one annotation or note."""
    if (annotation_id is None) == (note_id is None):
        raise ValueError("Subject evidence requires exactly one annotation or note")
    if annotation_id is not None:
        result = service.list_annotation_evidence(
            annotation_id,
            status=None,
            page=1,
            page_size=50,
        )
    else:
        result = service.list_note_evidence(note_id, status=None, page=1, page_size=50)
    if not result_ok(result):
        render_result(ui, result, success="Linked evidence loaded.")
        return
    items = result_items(result)
    if items:
        ui.caption("Existing concept evidence")
        ui.dataframe(
            evidence_rows(items, legacy_titles=_legacy_titles(database, items)),
            width="stretch",
            hide_index=True,
        )
        if manage_lifecycle:
            for item in items:
                ui.caption(
                    f"{item.evidence_link_id} · {item.concept_legacy_id} "
                    f"[{item.concept_legacy_source}]"
                )
                _render_evidence_lifecycle(
                    ui,
                    service,
                    item,
                    actions_enabled=actions_enabled,
                )


def _render_evidence_lifecycle(
    ui: Any,
    service: Any,
    item: Any,
    *,
    actions_enabled: bool,
) -> None:
    """Render one archive/reactivate action with a globally stable S4 key."""
    status = enum_value(item.status)
    if status == "archived":
        clicked = ui.button(
            "Reactivate evidence",
            key=state_key("reactivate_evidence", item.evidence_link_id),
            disabled=not actions_enabled,
        )
        if clicked and render_result(
            ui,
            service.reactivate_evidence_link(item.evidence_link_id),
            success="Evidence link reactivated.",
        ):
            ui.rerun()
    else:
        clicked = ui.button(
            "Archive evidence",
            key=state_key("archive_evidence", item.evidence_link_id),
            disabled=not actions_enabled,
        )
        if clicked and render_result(
            ui,
            service.archive_evidence_link(item.evidence_link_id),
            success="Evidence link archived.",
        ):
            ui.rerun()


def _open_evidence_target(ui: Any, service: Any, item: Any) -> None:
    """Resolve a logical evidence target and navigate without URLs or paths."""
    target = None
    if item.annotation_id:
        result = service.get_annotation(item.annotation_id, user_scope="local")
        if result_ok(result):
            target = result.value
            select_annotation(ui.session_state, item.annotation_id)
    elif item.note_id:
        result = service.get_note(item.note_id, user_scope="local")
        if result_ok(result):
            target = result.value
            select_note(ui.session_state, item.note_id)
    elif item.document_id:
        target = item
    if target is None or not getattr(target, "document_id", None):
        ui.warning("This evidence target is not linked to a Document.")
        return
    page = (
        getattr(target, "page_number", None)
        or getattr(target, "page_start", None)
        or getattr(item, "page_number", None)
    )
    open_document_at_page(
        ui.session_state,
        source_id=target.source_id,
        document_id=target.document_id,
        page_number=page,
    )
    ui.rerun()


def render_document_evidence(
    ui: Any,
    database: Any,
    service: Any,
    *,
    document_id: str,
    actions_enabled: bool,
) -> None:
    """List and lifecycle-manage bounded evidence links for the Document."""
    result = service.list_document_evidence(document_id, status=None, page=1, page_size=50)
    if not result_ok(result):
        render_result(ui, result, success="Concept evidence loaded.")
        return
    items = result_items(result)
    ui.subheader("Concept Evidence")
    if not items:
        ui.caption("No concept evidence linked to this Document.")
        return
    titles = _legacy_titles(database, items)
    ui.dataframe(
        evidence_rows(items, legacy_titles=titles),
        width="stretch",
        hide_index=True,
    )
    for item in items:
        status = enum_value(item.status)
        legacy_title = titles.get((item.concept_legacy_id, item.concept_legacy_source), "")
        title = legacy_title or item.concept_legacy_id
        with ui.expander(f"{title} · {evidence_origin(item)}", expanded=False):
            ui.write(
                {
                    "concept_legacy_id": item.concept_legacy_id,
                    "concept_legacy_source": item.concept_legacy_source,
                    "link_type": enum_value(item.link_type),
                    "comment": item.comment,
                    "annotation_id": item.annotation_id,
                    "note_id": item.note_id,
                    "document_id": item.document_id,
                    "page_number": item.page_number,
                    "status": status,
                }
            )
            target_label = (
                "Open Annotation"
                if item.annotation_id
                else "Open Note"
                if item.note_id
                else "Open in Reading Space"
            )
            if ui.button(
                target_label,
                key=state_key("open_evidence_target", item.evidence_link_id),
                width="content",
            ):
                _open_evidence_target(ui, service, item)
            _render_evidence_lifecycle(
                ui,
                service,
                item,
                actions_enabled=actions_enabled,
            )


__all__ = [
    "EVIDENCE_LINK_TYPES",
    "evidence_origin",
    "evidence_rows",
    "render_document_evidence",
    "render_link_form",
    "render_subject_evidence",
]

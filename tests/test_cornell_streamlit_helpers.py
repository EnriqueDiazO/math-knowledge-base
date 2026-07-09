"""Tests for pure Cornell Streamlit helper functions."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from editor.cornell.content_blocks import split_region_to_fit
from editor.cornell.layout import RegionFitResult
from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.models import CornellWatermark
from editor.cornell.streamlit_page import SESSION_DIRTY
from editor.cornell.streamlit_page import SESSION_DOCUMENT
from editor.cornell.streamlit_page import SESSION_FIT_DIAGNOSTICS
from editor.cornell.streamlit_page import SESSION_FLASH_MESSAGE
from editor.cornell.streamlit_page import SESSION_NOTE_ID
from editor.cornell.streamlit_page import SESSION_PAGE_INDEX
from editor.cornell.streamlit_page import SESSION_PENDING_DELETE_NOTE_ID
from editor.cornell.streamlit_page import SESSION_PENDING_LATEX_INSERT
from editor.cornell.streamlit_page import SESSION_PENDING_NOTE_ID
from editor.cornell.streamlit_page import SESSION_PENDING_VIEW
from editor.cornell.streamlit_page import SESSION_RENDERED_PAGE_ID
from editor.cornell.streamlit_page import SESSION_SPLIT_PROPOSAL
from editor.cornell.streamlit_page import SESSION_VIEW
from editor.cornell.streamlit_page import SESSION_VIEW_SELECTOR
from editor.cornell.streamlit_page import VIEW_EDIT_NOTES
from editor.cornell.streamlit_page import VIEW_EXPLORE_NOTES
from editor.cornell.streamlit_page import VIEW_NEW_NOTE
from editor.cornell.streamlit_page import add_page
from editor.cornell.streamlit_page import apply_loaded_note_state
from editor.cornell.streamlit_page import apply_pending_latex_insert
from editor.cornell.streamlit_page import apply_pending_view_state
from editor.cornell.streamlit_page import apply_split_proposal_to_state
from editor.cornell.streamlit_page import cancel_cornell_note_delete
from editor.cornell.streamlit_page import clear_deleted_note_state
from editor.cornell.streamlit_page import confirm_cornell_note_delete
from editor.cornell.streamlit_page import consume_pending_note_id
from editor.cornell.streamlit_page import delete_page
from editor.cornell.streamlit_page import duplicate_page
from editor.cornell.streamlit_page import normalize_page_orders
from editor.cornell.streamlit_page import queue_cornell_navigation
from editor.cornell.streamlit_page import queue_latex_insert
from editor.cornell.streamlit_page import request_cornell_note_delete
from editor.cornell.streamlit_page import valid_page_index
from editor.cornell.ui_helpers import ALL_LABEL
from editor.cornell.ui_helpers import DEFAULT_NOTE_CONTEXTS
from editor.cornell.ui_helpers import LATEX_SNIPPET_GROUPS
from editor.cornell.ui_helpers import NEW_PROJECT_LABEL
from editor.cornell.ui_helpers import NO_PROJECT_LABEL
from editor.cornell.ui_helpers import append_latex_snippet
from editor.cornell.ui_helpers import existing_note_contexts_from_values
from editor.cornell.ui_helpers import filter_cornell_notes_for_explorer
from editor.cornell.ui_helpers import note_page_count
from editor.cornell.ui_helpers import project_selector_choices
from editor.cornell.ui_helpers import resolve_project_choice


def page(page_id: str, order: int, heading: str | None = None) -> CornellPage:
    label = heading or page_id
    return CornellPage(
        page_id=page_id,
        order=order,
        cue=CornellRegion(heading=f"Cue {label}", latex=f"Cue body {label}"),
        main=CornellRegion(heading=f"Main {label}", latex=f"Main body {label}"),
        summary=CornellRegion(heading=f"Summary {label}", latex=f"Summary body {label}"),
    )


def document(*pages: CornellPage) -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=pages,
    )


def identity_document(*pages: CornellPage) -> CornellDocument:
    return CornellDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=pages,
        attribution=CornellAttribution(enabled=True, text="© 2026 Enrique"),
        watermark=CornellWatermark(enabled=True, type="text", text="COCID"),
    )


def empty_page(page_id: str = "empty", order: int = 2) -> CornellPage:
    return CornellPage(
        page_id=page_id,
        order=order,
        cue=CornellRegion(heading="Ideas principales", latex=""),
        main=CornellRegion(heading="Tema", latex=""),
        summary=CornellRegion(heading="Observaciones", latex=""),
    )


def split_source_page() -> CornellPage:
    return CornellPage(
        page_id="split-p1",
        order=1,
        cue=CornellRegion(heading="Cue", latex="Cue"),
        main=CornellRegion(
            heading="Main",
            latex=(
                "\\begin{definition}{A}\nA\n\\end{definition}\n"
                "\\begin{proposition}{B}\nB\n\\end{proposition}"
            ),
        ),
        summary=CornellRegion(heading="Summary", latex="Summary"),
    )


def fit_ok(page: CornellPage, region_name: str) -> RegionFitResult:
    return RegionFitResult(
        region=region_name,
        natural_width=100,
        natural_height=100,
        available_width=100,
        available_height=100,
        required_scale=1.0,
        applied_scale=1.0,
        status="FIT",
    )


def test_normalize_page_orders_sorts_and_renumbers() -> None:
    normalized = normalize_page_orders(document(page("p3", 30), page("p1", 10), page("p2", 20)))

    assert [(page.page_id, page.order) for page in normalized.ordered_pages()] == [
        ("p1", 1),
        ("p2", 2),
        ("p3", 3),
    ]


def test_add_page_inserts_after_selected_page() -> None:
    updated, selected = add_page(document(page("p1", 1), page("p2", 2)), selected_index=0)

    pages = updated.ordered_pages()
    assert selected == 1
    assert len(pages) == 3
    assert pages[0].page_id == "p1"
    assert pages[1].page_id not in {"p1", "p2"}
    assert [page.order for page in pages] == [1, 2, 3]


def test_page_operations_preserve_material_identity() -> None:
    original = identity_document(page("p1", 1), page("p2", 2))

    added, _ = add_page(original, selected_index=0)
    duplicated, _ = duplicate_page(original, selected_index=0)
    deleted, _ = delete_page(original, selected_index=0)

    assert added.attribution == original.attribution
    assert added.watermark == original.watermark
    assert duplicated.attribution == original.attribution
    assert duplicated.watermark == original.watermark
    assert deleted.attribution == original.attribution
    assert deleted.watermark == original.watermark


def test_duplicate_page_copies_content_with_new_page_id() -> None:
    updated, selected = duplicate_page(document(page("p1", 1, "original")), selected_index=0)

    pages = updated.ordered_pages()
    assert selected == 1
    assert len(pages) == 2
    assert pages[0].page_id == "p1"
    assert pages[1].page_id != "p1"
    assert pages[1].main.heading == pages[0].main.heading
    assert [page.order for page in pages] == [1, 2]


def test_delete_page_removes_selected_and_keeps_valid_selection() -> None:
    updated, selected = delete_page(
        document(page("p1", 1), page("p2", 2), page("p3", 3)),
        selected_index=1,
    )

    assert selected == 1
    assert [page.page_id for page in updated.ordered_pages()] == ["p1", "p3"]
    assert [page.order for page in updated.ordered_pages()] == [1, 2]


def test_delete_last_page_selects_previous_remaining_page() -> None:
    updated, selected = delete_page(
        document(page("p1", 1), page("p2", 2), page("p3", 3)),
        selected_index=2,
    )

    assert selected == 1
    assert [page.page_id for page in updated.ordered_pages()] == ["p1", "p2"]


def test_delete_only_page_keeps_one_page() -> None:
    original = document(page("p1", 1))

    updated, selected = delete_page(original, selected_index=0)

    assert selected == 0
    assert updated == original


def test_queue_open_note_does_not_modify_widget_selector_key() -> None:
    state = {
        SESSION_VIEW: VIEW_EXPLORE_NOTES,
        SESSION_VIEW_SELECTOR: VIEW_EXPLORE_NOTES,
    }

    queue_cornell_navigation(state, view=VIEW_EDIT_NOTES, note_id="note-1")

    assert state[SESSION_VIEW_SELECTOR] == VIEW_EXPLORE_NOTES
    assert state[SESSION_VIEW] == VIEW_EXPLORE_NOTES
    assert state[SESSION_PENDING_VIEW] == VIEW_EDIT_NOTES
    assert state[SESSION_PENDING_NOTE_ID] == "note-1"


def test_pending_navigation_is_applied_before_selector() -> None:
    state = {
        SESSION_VIEW: VIEW_EXPLORE_NOTES,
        SESSION_VIEW_SELECTOR: VIEW_EXPLORE_NOTES,
        SESSION_PENDING_VIEW: VIEW_EDIT_NOTES,
    }

    applied = apply_pending_view_state(state)

    assert applied == VIEW_EDIT_NOTES
    assert state[SESSION_VIEW] == VIEW_EDIT_NOTES
    assert state[SESSION_VIEW_SELECTOR] == VIEW_EDIT_NOTES
    assert SESSION_PENDING_VIEW not in state


def test_open_note_pending_id_is_consumed_once() -> None:
    state = {SESSION_PENDING_NOTE_ID: "note-2"}

    assert consume_pending_note_id(state) == "note-2"
    assert consume_pending_note_id(state) is None


def test_edit_navigation_targets_edit_view() -> None:
    state = {}

    queue_cornell_navigation(state, view=VIEW_EDIT_NOTES, note_id="note-3")

    assert apply_pending_view_state(state) == VIEW_EDIT_NOTES


def test_invalid_pending_navigation_falls_back_to_new_note() -> None:
    state = {SESSION_PENDING_VIEW: "Vista inexistente"}

    assert apply_pending_view_state(state) == VIEW_NEW_NOTE
    assert state[SESSION_VIEW] == VIEW_NEW_NOTE


def test_valid_page_index_clamps_out_of_range_values() -> None:
    doc = document(page("p1", 1), page("p2", 2))

    assert valid_page_index(doc, -10) == 0
    assert valid_page_index(doc, 99) == 1
    assert valid_page_index(doc, "bad") == 0


def test_loading_note_clears_previous_note_state() -> None:
    state = {
        SESSION_NOTE_ID: "old",
        SESSION_PAGE_INDEX: 99,
        SESSION_DIRTY: True,
        "cornell_title": "Vieja",
        "cornell_main_latex": "contenido anterior",
    }
    note = {
        "_id": "new",
        "title": "Nueva",
        "date": "2026-07-07",
        "project": "Algebra",
        "context": "estudio",
        "tags": ["matrices"],
    }
    doc = document(page("new-p1", 1, "nueva"), page("new-p2", 2, "segunda"))

    apply_loaded_note_state(state, note_id="new", note=note, document=doc)

    assert state[SESSION_NOTE_ID] == "new"
    assert state[SESSION_PAGE_INDEX] == 0
    assert state[SESSION_DIRTY] is False
    assert state[SESSION_RENDERED_PAGE_ID] == "new-p1"
    assert state["cornell_title"] == "Nueva"
    assert state["cornell_main_latex"] == "Main body nueva"


def test_loading_second_note_does_not_mix_documents() -> None:
    state = {}
    first = document(page("first-p1", 1, "first"))
    second = document(page("second-p1", 1, "second"))

    apply_loaded_note_state(state, note_id="first", note={"title": "First"}, document=first)
    apply_loaded_note_state(state, note_id="second", note={"title": "Second"}, document=second)

    current = state[SESSION_DOCUMENT]
    assert state[SESSION_NOTE_ID] == "second"
    assert [page.page_id for page in current.ordered_pages()] == ["second-p1"]
    assert state["cornell_cue_latex"] == "Cue body second"


def test_split_button_apply_updates_state_and_selects_destination() -> None:
    source = split_source_page()
    proposal = split_region_to_fit(source, "main", fit_ok, new_page_id="split-p2")
    doc = document(source, empty_page("existing-empty", 2))
    state = {
        SESSION_DOCUMENT: doc,
        SESSION_PAGE_INDEX: 0,
        SESSION_DIRTY: False,
        SESSION_FIT_DIAGNOSTICS: {"fit_report": "stale"},
        SESSION_SPLIT_PROPOSAL: proposal,
    }

    updated = apply_split_proposal_to_state(state, doc, 0, proposal)

    pages = updated.ordered_pages()
    assert state[SESSION_DOCUMENT] == updated
    assert state[SESSION_PAGE_INDEX] == 1
    assert state[SESSION_DIRTY] is True
    assert SESSION_FIT_DIAGNOSTICS not in state
    assert SESSION_SPLIT_PROPOSAL not in state
    assert [page.page_id for page in pages] == ["split-p1", "existing-empty"]
    assert pages[0].main.latex + pages[1].main.latex == source.main.latex
    assert pages[0].main.latex == proposal.kept_latex
    assert pages[1].main.latex == proposal.moved_latex


def test_project_selector_uses_history_and_no_project_option() -> None:
    choices, index = project_selector_choices([" Algebra ", "Geometry", "algebra"], "")

    assert choices == [NO_PROJECT_LABEL, NEW_PROJECT_LABEL, "Algebra", "Geometry"]
    assert index == 0


def test_project_selector_selects_existing_project() -> None:
    choices, index = project_selector_choices(["Algebra", "Geometry"], "geometry")

    assert choices[index] == "Geometry"


def test_project_selector_supports_new_project() -> None:
    choices, index = project_selector_choices(["Algebra"], "Topology")

    assert choices[index] == NEW_PROJECT_LABEL
    assert resolve_project_choice(NEW_PROJECT_LABEL, "  Topology  Seminar ") == "Topology Seminar"


def test_resolve_no_project_choice() -> None:
    assert resolve_project_choice(NO_PROJECT_LABEL, "Ignored") == ""


def test_contexts_are_compatible_with_diario_defaults() -> None:
    contexts = existing_note_contexts_from_values(["seminario", "estudio"])

    assert list(DEFAULT_NOTE_CONTEXTS) == contexts[: len(DEFAULT_NOTE_CONTEXTS)]
    assert "seminario" in contexts


def test_date_string_persists_as_iso_format() -> None:
    selected = date(2026, 7, 7)

    assert selected.isoformat() == "2026-07-07"


def test_insert_snippet_in_cue_preserves_existing_content() -> None:
    snippet = LATEX_SNIPPET_GROUPS[0].snippets[0].snippet

    assert append_latex_snippet("cue previo", snippet).startswith("cue previo\n\\begin{definition}")


def test_insert_snippet_in_main_preserves_existing_content() -> None:
    snippet = LATEX_SNIPPET_GROUPS[1].snippets[2].snippet

    assert append_latex_snippet("main previo\n", snippet) == "main previo\n" + snippet


def test_insert_snippet_in_summary_preserves_existing_content() -> None:
    snippet = LATEX_SNIPPET_GROUPS[4].snippets[0].snippet

    assert "summary previo" in append_latex_snippet("summary previo", snippet)


def test_insert_snippet_does_not_erase_empty_region() -> None:
    snippet = LATEX_SNIPPET_GROUPS[3].snippets[0].snippet

    assert append_latex_snippet("", snippet) == snippet + "\n"


def test_pending_latex_insert_updates_target_and_clears_queue() -> None:
    state = {"cornell_main_latex": "main previo"}

    queue_latex_insert(state, latex_key="cornell_main_latex", snippet="\\cornellimage{asset-1}")
    applied = apply_pending_latex_insert(state)

    assert applied is True
    assert state["cornell_main_latex"] == "main previo\n\\cornellimage{asset-1}\n"
    assert SESSION_PENDING_LATEX_INSERT not in state


def cornell_note(
    note_id: str,
    *,
    title: str,
    project: str,
    context: str,
    date_value: str = "2026-07-07",
) -> dict:
    doc = document(page("p1", 1), page("p2", 2))
    return {
        "_id": note_id,
        "note_format": "cornell_math_v1",
        "title": title,
        "date": date_value,
        "project": project,
        "context": context,
        "latex_body": f"{title} body",
        "cornell": doc.to_dict(),
    }


@dataclass(frozen=True, slots=True)
class FakeDeleteResult:
    deleted_count: int


class FakeDeleteDb:
    def __init__(self, note: dict | None, *, deleted_count: int = 1) -> None:
        self.note = note
        self.deleted_count = deleted_count
        self.get_ids: list[str] = []
        self.delete_ids: list[str] = []

    def get_notebook_note_by_id(self, note_id: str) -> dict | None:
        self.get_ids.append(str(note_id))
        if self.note is not None and str(self.note.get("_id")) == str(note_id):
            return dict(self.note)
        return None

    def delete_notebook_note(self, note_id: str) -> FakeDeleteResult:
        self.delete_ids.append(str(note_id))
        return FakeDeleteResult(deleted_count=self.deleted_count)


def test_delete_confirmation_request_and_cancel_do_not_touch_storage() -> None:
    state: dict = {}

    request_cornell_note_delete(state, "note-1")

    assert state[SESSION_PENDING_DELETE_NOTE_ID] == "note-1"
    cancel_cornell_note_delete(state, "other-note")
    assert state[SESSION_PENDING_DELETE_NOTE_ID] == "note-1"
    cancel_cornell_note_delete(state, "note-1")
    assert SESSION_PENDING_DELETE_NOTE_ID not in state


def test_confirm_delete_uses_note_id_verifies_result_and_clears_current_state() -> None:
    note = cornell_note("note-1", title="Cornell Algebra", project="Algebra", context="estudio")
    db = FakeDeleteDb(note)
    state = {
        SESSION_NOTE_ID: "note-1",
        SESSION_PENDING_NOTE_ID: "note-1",
        SESSION_PENDING_DELETE_NOTE_ID: "note-1",
        SESSION_FIT_DIAGNOSTICS: {"stale": True},
        SESSION_SPLIT_PROPOSAL: object(),
    }

    status = confirm_cornell_note_delete(state, db, "note-1")

    assert status == "deleted"
    assert db.get_ids == ["note-1"]
    assert db.delete_ids == ["note-1"]
    assert state[SESSION_NOTE_ID] is None
    assert state[SESSION_DIRTY] is False
    assert SESSION_PENDING_NOTE_ID not in state
    assert SESSION_PENDING_DELETE_NOTE_ID not in state
    assert SESSION_FIT_DIAGNOSTICS not in state
    assert SESSION_SPLIT_PROPOSAL not in state
    assert state[SESSION_FLASH_MESSAGE]["level"] == "success"


def test_confirm_delete_missing_note_updates_list_without_delete_call() -> None:
    db = FakeDeleteDb(None)
    state = {SESSION_PENDING_DELETE_NOTE_ID: "missing-note"}

    status = confirm_cornell_note_delete(state, db, "missing-note")

    assert status == "missing"
    assert db.get_ids == ["missing-note"]
    assert db.delete_ids == []
    assert SESSION_PENDING_DELETE_NOTE_ID not in state
    assert state[SESSION_FLASH_MESSAGE]["level"] == "warning"


def test_confirm_delete_rejects_unexpected_deleted_count() -> None:
    note = cornell_note("note-1", title="Cornell Algebra", project="Algebra", context="estudio")
    db = FakeDeleteDb(note, deleted_count=2)

    with pytest.raises(RuntimeError, match="se esperaba exactamente 1"):
        confirm_cornell_note_delete({}, db, "note-1")


def test_clear_deleted_note_state_keeps_other_open_note() -> None:
    state = {
        SESSION_NOTE_ID: "open-note",
        SESSION_PENDING_DELETE_NOTE_ID: "deleted-note",
        SESSION_FIT_DIAGNOSTICS: {"kept": True},
    }

    clear_deleted_note_state(state, "deleted-note")

    assert state[SESSION_NOTE_ID] == "open-note"
    assert SESSION_PENDING_DELETE_NOTE_ID not in state
    assert state[SESSION_FIT_DIAGNOSTICS] == {"kept": True}


def test_explorer_filters_only_cornell_notes() -> None:
    notes = [
        cornell_note("1", title="Cornell Algebra", project="Algebra", context="estudio"),
        {"_id": "legacy", "title": "Legacy", "latex_body": "Legacy body"},
    ]

    filtered = filter_cornell_notes_for_explorer(notes)

    assert [note["_id"] for note in filtered] == ["1"]
    assert note_page_count(filtered[0]) == 2


def test_explorer_filters_by_project_and_context() -> None:
    notes = [
        cornell_note("1", title="Algebra", project="Algebra", context="estudio"),
        cornell_note("2", title="Debug", project="Algebra", context="debug"),
        cornell_note("3", title="Geometry", project="Geometry", context="estudio"),
    ]

    filtered = filter_cornell_notes_for_explorer(
        notes,
        project="Algebra",
        context="estudio",
    )

    assert [note["_id"] for note in filtered] == ["1"]


def test_explorer_filters_text_and_date() -> None:
    notes = [
        cornell_note("1", title="Matrices", project="", context="estudio", date_value="2026-07-07"),
        cornell_note("2", title="Topologia", project="", context="estudio", date_value="2026-07-08"),
    ]

    filtered = filter_cornell_notes_for_explorer(
        notes,
        text="matrices",
        project=ALL_LABEL,
        context=ALL_LABEL,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 7),
    )

    assert [note["_id"] for note in filtered] == ["1"]


def test_explorer_filters_no_project() -> None:
    notes = [
        cornell_note("1", title="Sin proyecto", project="", context="estudio"),
        cornell_note("2", title="Con proyecto", project="Algebra", context="estudio"),
    ]

    filtered = filter_cornell_notes_for_explorer(notes, project=NO_PROJECT_LABEL)

    assert [note["_id"] for note in filtered] == ["1"]

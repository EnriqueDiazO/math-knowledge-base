"""Tests for pure Cornell Streamlit helper functions."""

# ruff: noqa: D103

from __future__ import annotations

from editor.cornell.models import DEFAULT_TEMPLATE_ID
from editor.cornell.models import CornellDocument
from editor.cornell.models import CornellPage
from editor.cornell.models import CornellRegion
from editor.cornell.streamlit_page import add_page
from editor.cornell.streamlit_page import delete_page
from editor.cornell.streamlit_page import duplicate_page
from editor.cornell.streamlit_page import normalize_page_orders


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

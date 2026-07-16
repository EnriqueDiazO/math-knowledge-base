"""Focused UI, context, search, grouping, and safety tests for S4.3."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

import ast
import hashlib
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from editor.concept_linking.concept_cards import LINK_TYPE_LABELS
from editor.concept_linking.concept_cards import human_link_type
from editor.concept_linking.concept_cards import render_concept_card
from editor.concept_linking.concept_search import CONCEPT_PROJECTION
from editor.concept_linking.concept_search import MAX_PAGE
from editor.concept_linking.concept_search import MAX_PAGE_SIZE
from editor.concept_linking.concept_search import MAX_QUERY_LENGTH
from editor.concept_linking.concept_search import get_concept
from editor.concept_linking.concept_search import get_concepts
from editor.concept_linking.concept_search import search_concepts
from editor.concept_linking.context import render_context_card
from editor.concept_linking.context import resolve_linking_context
from editor.concept_linking.document_concepts import group_document_evidence
from editor.concept_linking.document_concepts import render_known_concept_evidence
from editor.concept_linking.navigation import open_evidence
from editor.concept_linking.page_concepts import evidence_for_page
from editor.concept_linking.page_concepts import render_evidence_card
from editor.concept_linking.page_concepts import resolve_document_evidence
from editor.concept_linking.panel import _launch_button
from editor.concept_linking.state import ACTIVE
from editor.concept_linking.state import ACTIVE_CONTEXT
from editor.concept_linking.state import COMMENT
from editor.concept_linking.state import DOCUMENT_ID
from editor.concept_linking.state import DUPLICATE_LINK_ID
from editor.concept_linking.state import LINK_TYPE
from editor.concept_linking.state import MODE
from editor.concept_linking.state import PARTIAL_MESSAGE
from editor.concept_linking.state import PARTIAL_TARGET_ID
from editor.concept_linking.state import PARTIAL_TARGET_KIND
from editor.concept_linking.state import PDF_PAGE
from editor.concept_linking.state import RECENT_CONCEPTS
from editor.concept_linking.state import SEARCH_QUERY
from editor.concept_linking.state import SELECTED_CONCEPT_KEY
from editor.concept_linking.state import SESSION_PREFIX
from editor.concept_linking.state import STEP
from editor.concept_linking.state import TARGET_ID
from editor.concept_linking.state import TARGET_KIND
from editor.concept_linking.state import cancel_wizard
from editor.concept_linking.state import change_concept
from editor.concept_linking.state import decode_concept_identity
from editor.concept_linking.state import recent_identities
from editor.concept_linking.state import remember_concept
from editor.concept_linking.state import select_concept
from editor.concept_linking.state import start_wizard
from editor.concept_linking.state import state_key
from editor.concept_linking.state import sync_context
from editor.concept_linking.unlinked_items import find_unlinked_items
from editor.concept_linking.unlinked_items import render_unlinked_items
from editor.concept_linking.view_models import ConceptLinkingContext
from editor.concept_linking.view_models import ConceptSummary
from editor.concept_linking.view_models import EvidenceView
from editor.concept_linking.view_models import UnlinkedItem
from editor.reading_annotations.state import SELECTED_ANNOTATION_ID
from editor.reading_annotations.state import SELECTED_NOTE_ID
from editor.reading_space.state import PENDING_WORKSPACE_TAB
from editor.reading_space.state import WORKSPACE_TAB
from editor.reading_space.state import migrate_legacy_workspace_tab
from editor.reading_space.state import state_key as reading_state_key
from mathmongo.reading_annotations.models import ConceptEvidenceLink

ROOT = Path(__file__).resolve().parents[1]
CONCEPT_MODULES = tuple(sorted((ROOT / "editor" / "concept_linking").glob("*.py")))


class FakeCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = [dict(item) for item in documents]
        self.operations: list[tuple[str, Any]] = []

    def sort(self, specification: list[tuple[str, int]]):
        self.operations.append(("sort", tuple(specification)))
        for field, direction in reversed(specification):
            self.documents.sort(
                key=lambda item: str(item.get(field, "")),
                reverse=direction < 0,
            )
        return self

    def skip(self, amount: int):
        self.operations.append(("skip", amount))
        self.documents = self.documents[amount:]
        return self

    def limit(self, amount: int):
        self.operations.append(("limit", amount))
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


def _matches_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict) and "$regex" in expected:
        flags = re.IGNORECASE if "i" in str(expected.get("$options", "")) else 0
        pattern = re.compile(str(expected["$regex"]), flags)
        values = actual if isinstance(actual, list | tuple | set) else (actual,)
        return any(pattern.search(str(value or "")) is not None for value in values)
    return actual == expected


def _matches(document: dict[str, Any], selector: dict[str, Any]) -> bool:
    alternatives = selector.get("$or")
    if isinstance(alternatives, list):
        return any(_matches(document, clause) for clause in alternatives)
    return all(
        _matches_value(document.get(field), expected) for field, expected in selector.items()
    )


class FakeConceptCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.find_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.find_one_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.cursors: list[FakeCursor] = []
        self.write_calls: list[str] = []

    def find(self, selector: dict[str, Any], projection: dict[str, Any]):
        self.find_calls.append((selector, projection))
        cursor = FakeCursor([item for item in self.documents if _matches(item, selector)])
        self.cursors.append(cursor)
        return cursor

    def find_one(self, selector: dict[str, Any], projection: dict[str, Any]):
        self.find_one_calls.append((selector, projection))
        return next((dict(item) for item in self.documents if _matches(item, selector)), None)

    def _forbidden_write(self, name: str) -> None:
        self.write_calls.append(name)
        raise AssertionError(f"S4.3 must not call concepts.{name}")

    def insert_one(self, *_args: Any, **_kwargs: Any) -> None:
        self._forbidden_write("insert_one")

    def update_one(self, *_args: Any, **_kwargs: Any) -> None:
        self._forbidden_write("update_one")

    def update_many(self, *_args: Any, **_kwargs: Any) -> None:
        self._forbidden_write("update_many")

    def replace_one(self, *_args: Any, **_kwargs: Any) -> None:
        self._forbidden_write("replace_one")

    def delete_one(self, *_args: Any, **_kwargs: Any) -> None:
        self._forbidden_write("delete_one")

    def delete_many(self, *_args: Any, **_kwargs: Any) -> None:
        self._forbidden_write("delete_many")


class FakeDatabase:
    def __init__(self, concepts: list[dict[str, Any]]) -> None:
        self.concepts = FakeConceptCollection(concepts)

    def __getitem__(self, name: str) -> FakeConceptCollection:
        assert name == "concepts"
        return self.concepts


class FakeUI:
    def __init__(self, *, clicked: set[str] | None = None) -> None:
        self.clicked = set(clicked or ())
        self.session_state: dict[str, Any] = {}
        self.messages: list[tuple[str, Any, tuple[str, ...]]] = []
        self.expanders: list[tuple[str, bool]] = []
        self.buttons: list[tuple[str, str, bool]] = []
        self._scope: list[str] = []
        self.reruns = 0

    def _message(self, kind: str, value: Any) -> None:
        self.messages.append((kind, value, tuple(self._scope)))

    def subheader(self, value: Any) -> None:
        self._message("subheader", value)

    def header(self, value: Any) -> None:
        self._message("header", value)

    def caption(self, value: Any) -> None:
        self._message("caption", value)

    def write(self, value: Any) -> None:
        self._message("write", value)

    def info(self, value: Any) -> None:
        self._message("info", value)

    def warning(self, value: Any) -> None:
        self._message("warning", value)

    def success(self, value: Any) -> None:
        self._message("success", value)

    def error(self, value: Any) -> None:
        self._message("error", value)

    def code(self, value: Any, **_kwargs: Any) -> None:
        self._message("code", value)

    @contextmanager
    def container(self, **_kwargs: Any):
        self._scope.append("container")
        try:
            yield self
        finally:
            self._scope.pop()

    @contextmanager
    def expander(self, label: str, *, expanded: bool = False, **_kwargs: Any):
        self.expanders.append((label, expanded))
        self._scope.append(f"expander:{label}")
        try:
            yield self
        finally:
            self._scope.pop()

    def button(self, label: str, *, key: str, disabled: bool = False, **_kwargs: Any) -> bool:
        self.buttons.append((label, key, disabled))
        return not disabled and (label in self.clicked or key in self.clicked)

    def number_input(self, label: str, *, value: int, **_kwargs: Any) -> int:
        self._message("number_input", label)
        return value

    def rerun(self) -> None:
        self.reruns += 1

    def main_text(self) -> str:
        return " ".join(
            str(value)
            for _kind, value, scope in self.messages
            if not any(item.startswith("expander:") for item in scope)
        )

    def expander_text(self, label: str) -> str:
        marker = f"expander:{label}"
        return " ".join(str(value) for _kind, value, scope in self.messages if marker in scope)


def _linking_context(*, kind: str = "pdf", page: int | None = 9) -> ConceptLinkingContext:
    return ConceptLinkingContext(
        database_name="math",
        document_id="doc-current",
        document_title="Boundary Behaviour of Conformal Maps",
        document_kind=kind,
        source_id="src-current",
        source_name="Pommerenke 1991",
        reference_id="ref-current",
        reference_title="Boundary Behaviour of Conformal Maps",
        pdf_page=page if kind == "pdf" else None,
        book_page_label="1" if kind == "pdf" and page == 9 else None,
        reading_status="in_progress",
        web_url="https://example.test/resource" if kind == "web" else None,
    )


def _concept(
    concept_id: str = "concept-internal-id",
    source: str = "Pommerenke1991",
    title: str = "Métrica esférica",
) -> ConceptSummary:
    return ConceptSummary(
        concept_id=concept_id,
        concept_source=source,
        title=title,
        concept_type="Definición",
        categories=("Análisis complejo",),
        tags=("frontera",),
        evidence_count=3,
    )


def _evidence(
    evidence_id: str,
    concept: ConceptSummary,
    *,
    origin: str,
    page: int | None,
    page_end: int | None = None,
    link_type: str = "definition_source",
) -> EvidenceView:
    target_id = f"target-{evidence_id}"
    return EvidenceView(
        evidence_link_id=evidence_id,
        concept=concept,
        link_type=link_type,
        link_type_label=human_link_type(link_type),
        origin_kind=origin,
        origin_label={
            "page": "Página directa",
            "annotation": "Cita o anotación",
            "note": "Nota de lectura",
        }[origin],
        source_id="src-current",
        reference_id="ref-current",
        document_id="doc-current",
        annotation_id=target_id if origin == "annotation" else None,
        note_id=target_id if origin == "note" else None,
        pdf_page=page,
        pdf_page_end=page_end,
        book_page_label=str(page - 8) if isinstance(page, int) else None,
        excerpt="Texto matemático abreviado",
        comment="Explica por qué esta evidencia importa.",
        status="active",
    )


def test_state_namespace_sync_selection_and_cancel_are_isolated() -> None:
    state: dict[str, Any] = {
        "reading_annotations_quick_note_body_doc-current": "keep",
        state_key("stale"): "discard",
    }
    database = object()

    assert not sync_context(
        state,
        connection_label="local",
        database_name="math",
        database=database,
        user_scope="local",
        source_id="src-current",
        document_id="doc-current",
    )
    assert state["reading_annotations_quick_note_body_doc-current"] == "keep"
    assert state_key("stale") not in state
    assert isinstance(state[ACTIVE_CONTEXT], str)

    context = _linking_context()
    start_wizard(state, context, target_kind="annotation", target_id="ann-1")
    state[LINK_TYPE] = "citation"
    state[COMMENT] = "old relation"
    state[PARTIAL_TARGET_KIND] = "annotation"
    state[PARTIAL_TARGET_ID] = "ann-partial"
    state[PARTIAL_MESSAGE] = "retry"

    assert select_concept(state, "C-1", "Legacy Source")
    assert state[STEP] == 2
    assert decode_concept_identity(state[SELECTED_CONCEPT_KEY]) == ("C-1", "Legacy Source")
    assert LINK_TYPE not in state and COMMENT not in state
    assert PARTIAL_TARGET_ID not in state and PARTIAL_MESSAGE not in state
    assert not select_concept(state, "C-1", "Legacy Source")

    state[LINK_TYPE] = "motivation"
    state[COMMENT] = "draft"
    change_concept(state)
    assert SELECTED_CONCEPT_KEY not in state
    assert state[STEP] == 1
    assert state[TARGET_KIND] == "annotation" and state[TARGET_ID] == "ann-1"

    cancel_wizard(state)
    assert ACTIVE not in state and DOCUMENT_ID not in state and PDF_PAGE not in state
    assert state["reading_annotations_quick_note_body_doc-current"] == "keep"
    assert ACTIVE_CONTEXT in state
    assert all(not str(key).startswith(SESSION_PREFIX) or key == ACTIVE_CONTEXT for key in state)


def test_context_change_clears_only_concept_linking_state_and_not_tab_or_layout() -> None:
    first_database = object()
    state: dict[str, Any] = {
        "reading_space_workspace_tabs": "Concepts",
        "reading_space_workspace_layout": "Split workspace",
    }
    sync_context(
        state,
        connection_label="local",
        database_name="math",
        database=first_database,
        user_scope="local",
        source_id="src-1",
        document_id="doc-1",
    )
    state[state_key("draft")] = "keep while context is stable"

    assert not sync_context(
        state,
        connection_label="local",
        database_name="math",
        database=first_database,
        user_scope="local",
        source_id="src-1",
        document_id="doc-1",
    )
    assert state[state_key("draft")] == "keep while context is stable"

    assert sync_context(
        state,
        connection_label="local",
        database_name="math",
        database=first_database,
        user_scope="local",
        source_id="src-1",
        document_id="doc-2",
    )
    assert state_key("draft") not in state
    assert state["reading_space_workspace_tabs"] == "Concepts"
    assert state["reading_space_workspace_layout"] == "Split workspace"

    state[state_key("draft")] = "database-bound"
    assert sync_context(
        state,
        connection_label="local",
        database_name="math",
        database=object(),
        user_scope="local",
        source_id="src-1",
        document_id="doc-2",
    )
    assert state_key("draft") not in state


def test_read_only_search_can_launch_before_notes_evidence_is_initialized() -> None:
    context = _linking_context()
    ui = FakeUI(clicked={context.action_label})

    assert _launch_button(
        ui,
        context,
        actions_enabled=False,
        location="test",
    )
    assert ui.session_state[ACTIVE]
    assert ui.session_state[DOCUMENT_ID] == context.document_id
    assert ui.session_state[PENDING_WORKSPACE_TAB] == "Conocimiento"
    assert "La búsqueda está disponible" in ui.main_text()


@pytest.mark.parametrize("changed_field", ("database", "user_scope", "source_id", "document_id"))
def test_sync_invalidates_every_required_logical_context_change(changed_field: str) -> None:
    database = object()
    values: dict[str, Any] = {
        "connection_label": "local",
        "database_name": "math",
        "database": database,
        "user_scope": "local",
        "source_id": "src-1",
        "document_id": "doc-1",
    }
    state: dict[str, Any] = {"unrelated": "keep"}
    sync_context(state, **values)
    state[state_key("draft")] = "discard"
    changed = dict(values)
    changed[changed_field] = object() if changed_field == "database" else f"new-{changed_field}"

    assert sync_context(state, **changed)
    assert state_key("draft") not in state
    assert state["unrelated"] == "keep"
    assert ACTIVE_CONTEXT in state


def test_recent_concepts_are_primitive_bounded_deduplicated_and_most_recent_first() -> None:
    state: dict[str, Any] = {}
    for index in range(15):
        remember_concept(state, f"C-{index}", f"Source-{index % 2}")
    remember_concept(state, "C-5", "Source-1")

    identities = recent_identities(state)
    assert len(identities) == 12
    assert identities[0] == ("C-5", "Source-1")
    assert len(set(identities)) == len(identities)
    assert all(isinstance(value, str) for value in state[RECENT_CONCEPTS])

    state[RECENT_CONCEPTS] = ["invalid", 42, *state[RECENT_CONCEPTS]]
    assert recent_identities(state) == identities


def test_wizard_captures_page_without_storing_view_model_or_following_live_changes() -> None:
    state: dict[str, Any] = {}
    context = _linking_context(page=9)
    start_wizard(state, context)

    assert state[DOCUMENT_ID] == "doc-current"
    assert state[PDF_PAGE] == 9
    assert context not in state.values()
    changed_context = replace(context, pdf_page=14, book_page_label="6")
    assert changed_context.pdf_page == 14 and state[PDF_PAGE] == 9

    start_wizard(state, changed_context, target_kind="note", target_id="note-7", pdf_page=11)
    assert state[PDF_PAGE] == 11
    assert state[MODE] == "note" and state[TARGET_ID] == "note-7"


class FakePageMapService:
    def __init__(self, *, status: str = "success", label: str | None = "1", raises: bool = False):
        self.status = status
        self.label = label
        self.raises = raises
        self.calls: list[tuple[str, int, str]] = []

    def compute_page_label(self, document_id: str, pdf_page: int, *, user_scope: str):
        self.calls.append((document_id, pdf_page, user_scope))
        if self.raises:
            raise RuntimeError("page map unavailable")
        return SimpleNamespace(
            completed=self.status == "success",
            status=SimpleNamespace(value=self.status),
            value=(
                SimpleNamespace(book_page_label=self.label) if self.status == "success" else None
            ),
        )


def _reader(*, kind: str, page: int | None, with_reference: bool = True) -> Any:
    document = SimpleNamespace(
        document_id=f"doc-{kind}",
        source_id="src-1",
        reference_id="ref-1" if with_reference else None,
        title="Visible Document",
        kind=SimpleNamespace(value=kind),
        web=(
            SimpleNamespace(url_normalized="https://math.example.test/resource")
            if kind == "web"
            else None
        ),
    )
    return SimpleNamespace(
        document=document,
        source=SimpleNamespace(name="Visible Source"),
        reference=(
            SimpleNamespace(reference_id="ref-1", title="Visible Reference")
            if with_reference
            else None
        ),
        reading_state=SimpleNamespace(current_page=page),
        effective_status=SimpleNamespace(value="in_progress"),
    )


def test_pdf_context_prefers_live_page_and_uses_optional_page_map() -> None:
    reader = _reader(kind="pdf", page=4)
    session_state = {reading_state_key("current_page", "doc-pdf"): 9}
    page_maps = FakePageMapService(label="1")

    context = resolve_linking_context(
        SimpleNamespace(database_name="math"),
        reader,
        session_state=session_state,
        page_map_service=page_maps,
    )

    assert context.document_title == "Visible Document"
    assert context.source_name == "Visible Source"
    assert context.reference_title == "Visible Reference"
    assert context.pdf_page == 9 and context.book_page_label == "1"
    assert context.location_label == "Book page 1 · PDF page 9"
    assert context.action_label == "+ Asociar concepto a esta página"
    assert context.page_map_warning is None
    assert page_maps.calls == [("doc-pdf", 9, "local")]


@pytest.mark.parametrize("status", ["not_found", "conflict", "error"])
def test_pdf_context_page_map_absence_or_error_never_blocks_pdf_page(status: str) -> None:
    page_maps = FakePageMapService(status=status, label=None)
    context = resolve_linking_context(
        SimpleNamespace(database_name="math"),
        _reader(kind="pdf", page=7),
        session_state={},
        page_map_service=page_maps,
    )

    assert context.pdf_page == 7
    assert context.book_page_label is None
    assert context.location_label == "PDF page 7"
    if status == "not_found":
        assert context.page_map_warning is None
    else:
        assert context.page_map_warning == "No se pudo calcular Book page; se usará PDF page."


def test_pdf_context_page_map_exception_degrades_to_a_discreet_warning() -> None:
    context = resolve_linking_context(
        SimpleNamespace(database_name="math"),
        _reader(kind="pdf", page=7),
        session_state={},
        page_map_service=FakePageMapService(raises=True),
    )
    assert context.location_label == "PDF page 7"
    assert context.page_map_warning == "No se pudo calcular Book page; se usará PDF page."


def test_web_context_has_no_page_map_or_pdf_page_and_uses_visible_resource_copy() -> None:
    class PageMapMustNotRun:
        def compute_page_label(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("Page Map must not run for web Documents")

    context = resolve_linking_context(
        SimpleNamespace(database_name="math"),
        _reader(kind="web", page=None, with_reference=False),
        session_state={reading_state_key("current_page", "doc-web"): 99},
        page_map_service=PageMapMustNotRun(),
    )

    assert not context.is_pdf
    assert context.pdf_page is None and context.book_page_label is None
    assert context.reference_title is None
    assert context.location_label == "Recurso web · math.example.test"
    assert context.action_label == "+ Asociar concepto a este recurso"


CONCEPT_DOCUMENTS = [
    {
        "id": "C-ID-42",
        "source": "Pommerenke1991",
        "titulo": "Métrica esférica",
        "tipo": "Definición",
        "categorias": ["Análisis complejo"],
        "tags": ["frontera"],
        "latex": "large body must not be projected",
    },
    {
        "id": "C-THEOREM",
        "source": "Caratheodory1913",
        "title": "Extensión al borde",
        "type": "Teorema",
        "categories": ["Topología"],
        "tags": ["compactness"],
        "body": "large body must not be projected",
    },
    {
        "id": "C-LITERAL",
        "source": "RegexBook",
        "name": "Literal .* token",
        "tipo": "Ejemplo",
        "categorias": [],
        "tags": [],
    },
]


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("C-ID-42", "C-ID-42"),
        ("esférica", "C-ID-42"),
        ("Pommerenke1991", "C-ID-42"),
        ("Teorema", "C-THEOREM"),
        ("Topología", "C-THEOREM"),
        ("compactness", "C-THEOREM"),
    ],
)
def test_search_covers_id_title_source_type_category_and_tag(query: str, expected_id: str) -> None:
    database = FakeDatabase(CONCEPT_DOCUMENTS)
    result = search_concepts(database, query)

    assert [item.concept_id for item in result] == [expected_id]
    assert database.concepts.find_calls[-1][1] == CONCEPT_PROJECTION
    assert database.concepts.write_calls == []


def test_search_escapes_regex_and_projects_only_bounded_metadata() -> None:
    database = FakeDatabase(CONCEPT_DOCUMENTS)
    result = search_concepts(database, ".*")

    assert [item.concept_id for item in result] == ["C-LITERAL"]
    selector, projection = database.concepts.find_calls[-1]
    assert {clause[next(iter(clause))]["$regex"] for clause in selector["$or"]} == {re.escape(".*")}
    assert projection == CONCEPT_PROJECTION
    assert projection["_id"] == 0
    assert "latex" not in projection and "body" not in projection
    assert not hasattr(result[0], "latex") and not hasattr(result[0], "body")


def test_search_has_stable_server_side_pagination_and_hard_limits() -> None:
    documents = [
        {"id": "C-3", "source": "B", "title": "shared"},
        {"id": "C-2", "source": "A", "title": "shared"},
        {"id": "C-1", "source": "A", "title": "shared"},
        {"id": "C-0", "source": "C", "title": "shared"},
    ]
    database = FakeDatabase(documents)

    result = search_concepts(database, "shared", page=2, page_size=2)

    assert [(item.concept_source, item.concept_id) for item in result] == [
        ("B", "C-3"),
        ("C", "C-0"),
    ]
    assert database.concepts.cursors[-1].operations == [
        ("sort", (("source", 1), ("id", 1))),
        ("skip", 2),
        ("limit", 2),
    ]

    search_concepts(database, "shared", page_size=MAX_PAGE_SIZE + 100)
    assert database.concepts.cursors[-1].operations[-1] == ("limit", MAX_PAGE_SIZE)

    for invalid_page in (0, MAX_PAGE + 1, True):
        with pytest.raises(ValueError, match="page"):
            search_concepts(database, "shared", page=invalid_page)  # type: ignore[arg-type]
    for invalid_size in (0, True):
        with pytest.raises(ValueError, match="page_size"):
            search_concepts(database, "shared", page_size=invalid_size)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=str(MAX_QUERY_LENGTH)):
        search_concepts(database, "x" * (MAX_QUERY_LENGTH + 1))


def test_exact_and_batch_concept_reads_preserve_composite_identity_without_writes() -> None:
    database = FakeDatabase(CONCEPT_DOCUMENTS)
    exact = get_concept(database, "C-ID-42", "Pommerenke1991")
    batch = get_concepts(
        database,
        (
            ("C-THEOREM", "Caratheodory1913"),
            ("C-ID-42", "Pommerenke1991"),
            ("C-THEOREM", "Caratheodory1913"),
        ),
    )

    assert exact is not None and exact.identity == ("C-ID-42", "Pommerenke1991")
    assert [item.identity for item in batch] == [
        ("C-THEOREM", "Caratheodory1913"),
        ("C-ID-42", "Pommerenke1991"),
    ]
    assert database.concepts.find_one_calls[-1][1] == CONCEPT_PROJECTION
    assert database.concepts.find_calls[-1][1] == CONCEPT_PROJECTION
    assert database.concepts.write_calls == []


def test_batch_concept_resolution_covers_a_full_bounded_document_evidence_page() -> None:
    documents = [
        {"id": f"C-{index:03d}", "source": "Legacy", "title": f"Concept {index}"}
        for index in range(100)
    ]
    database = FakeDatabase(documents)

    result = get_concepts(
        database,
        tuple((item["id"], item["source"]) for item in documents),
        limit=100,
    )

    assert len(result) == 100
    assert result[-1].display_title == "Concept 99"
    assert database.concepts.cursors[-1].operations[-1] == ("limit", 100)


def test_search_reuses_legacy_identity_validation_for_control_characters() -> None:
    database = FakeDatabase([{"id": "unsafe\x1fid", "source": "Legacy", "title": "Unsafe concept"}])

    assert search_concepts(database, "Unsafe") == ()


@pytest.mark.parametrize("internal", tuple(LINK_TYPE_LABELS))
def test_relationship_types_are_humanized_without_changing_internal_value(internal: str) -> None:
    label = human_link_type(internal)
    assert label == LINK_TYPE_LABELS[internal]
    assert label and "_" not in label


def test_concept_and_context_cards_keep_internal_ids_in_closed_details() -> None:
    ui = FakeUI()
    concept = _concept(concept_id="TECH-CONCEPT-ID")
    context = _linking_context()

    render_concept_card(ui, concept, card_key="card")
    render_context_card(ui, context)

    main = ui.main_text()
    assert "Métrica esférica" in main
    assert "Definición" in main and "Análisis complejo" in main
    assert "Pommerenke1991" in main
    assert "TECH-CONCEPT-ID" not in main
    assert "doc-current" not in main and "src-current" not in main
    assert "TECH-CONCEPT-ID" in ui.expander_text("Detalles del concepto")
    assert "doc-current" in ui.expander_text("Detalles técnicos")
    assert ("Detalles del concepto", False) in ui.expanders
    assert ("Detalles técnicos", False) in ui.expanders


def test_evidence_card_is_humanized_and_hides_all_target_ids_by_default() -> None:
    ui = FakeUI()
    item = _evidence(
        "ev-technical",
        _concept(concept_id="CONCEPT-TECH"),
        origin="annotation",
        page=9,
    )
    service = SimpleNamespace()

    render_evidence_card(ui, service, item, actions_enabled=False, card_key="card")

    main = ui.main_text()
    assert "Métrica esférica" in main
    assert "Fuente de definición" in main
    assert "Cita o anotación" in main
    assert "Book page 1 · PDF page 9" in main
    for internal in ("ev-technical", "target-ev-technical", "CONCEPT-TECH", "doc-current"):
        assert internal not in main
        assert internal in ui.expander_text("Detalles técnicos")


def test_archiving_remains_available_when_only_new_writes_are_blocked() -> None:
    active_ui = FakeUI()
    render_evidence_card(
        active_ui,
        SimpleNamespace(),
        _evidence("ev-active", _concept(), origin="page", page=9),
        actions_enabled=False,
        archive_enabled=True,
        card_key="active",
    )
    assert next(item for item in active_ui.buttons if item[0] == "Archivar")[2] is False

    archived_ui = FakeUI()
    archived = replace(
        _evidence("ev-archived", _concept(), origin="page", page=9),
        status="archived",
    )
    render_evidence_card(
        archived_ui,
        SimpleNamespace(),
        archived,
        actions_enabled=False,
        archive_enabled=True,
        card_key="archived",
    )
    assert next(item for item in archived_ui.buttons if item[0] == "Reactivar")[2] is True


class EvidenceService:
    def __init__(self, links: tuple[Any, ...], annotation: Any, note: Any) -> None:
        self.links = links
        self.annotation = annotation
        self.note = note
        self.annotation_calls = 0
        self.note_calls = 0

    def list_document_evidence(self, document_id: str, **kwargs: Any):
        assert document_id == "doc-current"
        assert kwargs["page_size"] == 100
        return SimpleNamespace(
            completed=True,
            value=SimpleNamespace(items=self.links, total=len(self.links)),
        )

    def get_annotation(self, annotation_id: str, *, user_scope: str):
        self.annotation_calls += 1
        assert annotation_id == "ann-1" and user_scope == "local"
        return SimpleNamespace(completed=True, value=self.annotation)

    def get_note(self, note_id: str, *, user_scope: str):
        self.note_calls += 1
        assert note_id == "note-1" and user_scope == "local"
        return SimpleNamespace(completed=True, value=self.note)


def _raw_link(
    evidence_id: str,
    concept_id: str,
    concept_source: str,
    *,
    annotation_id: str | None = None,
    note_id: str | None = None,
    page: int | None = None,
) -> Any:
    return SimpleNamespace(
        evidence_link_id=evidence_id,
        concept_legacy_id=concept_id,
        concept_legacy_source=concept_source,
        source_id="src-current",
        reference_id="ref-current",
        document_id="doc-current" if annotation_id is None and note_id is None else None,
        annotation_id=annotation_id,
        note_id=note_id,
        page_number=page,
        link_type="definition_source" if note_id is None else "related_context",
        comment="A bounded explanation",
        status="active",
    )


def test_evidence_resolution_and_page_filter_cover_direct_annotation_and_note_range() -> None:
    database = FakeDatabase(
        [
            {"id": "C-A", "source": "Legacy-A", "title": "Concept A", "tipo": "Definición"},
            {"id": "C-B", "source": "Legacy-B", "title": "Concept B", "tipo": "Teorema"},
        ]
    )
    links = (
        _raw_link("ev-page", "C-A", "Legacy-A", page=9),
        _raw_link("ev-ann", "C-A", "Legacy-A", annotation_id="ann-1"),
        _raw_link("ev-note", "C-B", "Legacy-B", note_id="note-1"),
    )
    annotation = SimpleNamespace(
        document_id="doc-current",
        page_number=9,
        quote_text="A quoted definition",
        body="",
    )
    note = SimpleNamespace(
        document_id="doc-current",
        page_start=8,
        page_end=11,
        title="Reading range",
        body="Context across pages",
    )
    service = EvidenceService(links, annotation, note)

    resolved = resolve_document_evidence(
        database,
        service,
        document_id="doc-current",
        status=None,
        page=1,
        page_size=100,
        page_labeler=lambda page: str(page - 8),
    )
    by_id = {item.evidence_link_id: item for item in resolved}

    assert by_id["ev-page"].origin_kind == "page"
    assert by_id["ev-page"].pdf_page == 9
    assert by_id["ev-ann"].origin_kind == "annotation"
    assert by_id["ev-ann"].excerpt == "A quoted definition"
    assert by_id["ev-note"].origin_kind == "note"
    assert (by_id["ev-note"].pdf_page, by_id["ev-note"].pdf_page_end) == (8, 11)
    assert by_id["ev-note"].excerpt == "Reading range: Context across pages"
    assert by_id["ev-note"].link_type_label == "Contexto relacionado"
    assert service.annotation_calls == 1 and service.note_calls == 1
    assert by_id["ev-page"].concept.document_evidence_count == 2
    assert by_id["ev-ann"].concept.document_evidence_count == 2

    assert {item.evidence_link_id for item in evidence_for_page(resolved, 9)} == {
        "ev-page",
        "ev-ann",
        "ev-note",
    }
    assert [item.evidence_link_id for item in evidence_for_page(resolved, 10)] == ["ev-note"]
    assert evidence_for_page(resolved, None) == resolved


def test_document_grouping_uses_exact_concept_identity_and_deduplicates_pages() -> None:
    first = _concept("C-1", "Legacy-A", "Same visible title")
    second = _concept("C-1", "Legacy-B", "Same visible title")
    evidence = (
        _evidence("ev-1", first, origin="page", page=9),
        _evidence("ev-2", first, origin="annotation", page=9, link_type="citation"),
        _evidence("ev-3", second, origin="note", page=10, page_end=12),
    )

    groups = group_document_evidence(evidence)

    assert [group.concept.identity for group in groups] == [
        ("C-1", "Legacy-A"),
        ("C-1", "Legacy-B"),
    ]
    assert len(groups[0].evidence) == 2
    assert groups[0].pages == ("Book page 1 · PDF page 9",)
    assert groups[0].link_types == ("Fuente de definición", "Cita")
    assert groups[1].pages == ("Book page 2 · PDF page 10",)


def test_known_evidence_is_paginated_humanized_and_resolves_book_page_ranges() -> None:
    item = _raw_link("ev-note", "C-A", "Legacy-A", note_id="note-1")
    note = SimpleNamespace(
        document_id="doc-current",
        page_start=9,
        page_end=11,
    )

    class Repository:
        def __init__(self, value: Any) -> None:
            self.value = value

        def get_by_id(self, _identity: str) -> Any:
            return self.value

    class Service:
        documents = Repository(SimpleNamespace(title="Visible Document"))
        sources = Repository(SimpleNamespace(name="Visible Source"))
        references = Repository(SimpleNamespace(title="Visible Reference"))

        def list_concept_evidence(self, *_args: Any, **kwargs: Any):
            assert kwargs == {"status": None, "page": 1, "page_size": 20}
            return SimpleNamespace(
                completed=True,
                value=SimpleNamespace(items=(item,), total=1, pages=1),
            )

        def get_note(self, note_id: str, *, user_scope: str):
            assert note_id == "note-1" and user_scope == "local"
            return SimpleNamespace(completed=True, value=note)

    ui = FakeUI()
    render_known_concept_evidence(
        ui,
        Service(),
        _concept("C-A", "Legacy-A", "Métrica esférica"),
        current_document_id="doc-current",
        current_source_id="src-current",
        page_labeler=lambda page: str(page - 8),
    )

    main = ui.main_text()
    assert "1 evidencias · página 1 de 1" in main
    assert "Visible Document" in main
    assert "Source: Visible Source" in main
    assert "Reference: Visible Reference" in main
    assert "Book page 1 · PDF page 9 – Book page 3 · PDF page 11" in main
    assert "Contexto relacionado" in main


class PendingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.annotations = (
            SimpleNamespace(
                schema_version=2,
                annotation_id="ann-unlinked",
                kind="highlight",
                quote_text="spherical metric",
                body="",
                page_number=9,
                tags=("geometry",),
                status="active",
                visual_anchor=SimpleNamespace(pdf_page=9),
            ),
            SimpleNamespace(
                annotation_id="ann-linked",
                kind="comment",
                quote_text="already linked",
                body="",
                page_number=3,
                tags=(),
                status="active",
            ),
        )
        self.notes = (
            SimpleNamespace(
                note_id="note-unlinked",
                note_type="definition",
                title="Métrica cordal",
                body="Transformaciones and a useful range",
                page_start=5,
                page_end=7,
                tags=("mobius",),
                status="active",
            ),
        )

    @staticmethod
    def _page(items: tuple[Any, ...]):
        return SimpleNamespace(completed=True, value=SimpleNamespace(items=items, total=len(items)))

    def list_document_annotations(self, _document_id: str, **kwargs: Any):
        self.calls.append(("annotations", kwargs))
        return self._page(self.annotations)

    def list_document_notes(self, _document_id: str, **kwargs: Any):
        self.calls.append(("notes", kwargs))
        return self._page(self.notes)

    def list_annotation_evidence(self, annotation_id: str, **_kwargs: Any):
        total = 1 if annotation_id == "ann-linked" else 0
        return SimpleNamespace(completed=True, value=SimpleNamespace(items=(), total=total))

    def list_note_evidence(self, _note_id: str, **_kwargs: Any):
        return SimpleNamespace(completed=True, value=SimpleNamespace(items=(), total=0))


def test_pending_items_include_visual_annotations_and_are_sorted_by_page() -> None:
    service = PendingService()
    items = find_unlinked_items(
        service,
        document_id="doc-current",
        page_labeler=lambda page: f"B-{page}",
        limit=100,
    )

    assert [(item.target_kind, item.target_id) for item in items] == [
        ("note", "note-unlinked"),
        ("annotation", "ann-unlinked"),
    ]
    assert items[0].location_label == "Book page B-5 · PDF page 5"
    assert items[1].excerpt == "spherical metric"
    assert items[1].target_id == "ann-unlinked"
    assert all(item.status == "active" for item in items)
    assert {name for name, _kwargs in service.calls} == {"annotations", "notes"}
    for _name, kwargs in service.calls:
        assert kwargs["status"] == "active"
        assert kwargs["page"] == 1 and kwargs["page_size"] == 50


def test_pending_items_include_unlinked_source_only_notes_for_partial_recovery() -> None:
    class SourcePendingService(PendingService):
        def list_source_notes(self, source_id: str, **kwargs: Any):
            assert source_id == "src-current"
            assert kwargs["source_only"] is True and kwargs["status"] == "active"
            return self._page(
                (
                    SimpleNamespace(
                        note_id="note-source-only",
                        note_type="idea",
                        title="Source insight",
                        body="A partial target without a Document",
                        page_start=None,
                        page_end=None,
                        tags=("source",),
                        status="active",
                    ),
                )
            )

    items = find_unlinked_items(
        SourcePendingService(),
        document_id="doc-current",
        source_id="src-current",
    )

    source_item = next(item for item in items if item.target_id == "note-source-only")
    assert source_item.location_label == "Sin página"
    assert source_item.excerpt == "A partial target without a Document"


def test_pending_card_launches_preselected_wizard_without_touching_other_drafts() -> None:
    item = UnlinkedItem(
        target_kind="note",
        target_id="note-unlinked",
        item_type="definition",
        title="Métrica cordal",
        excerpt="A bounded reading note",
        pdf_page=5,
        book_page_label="B-5",
        tags=("mobius",),
        status="active",
    )
    click_key = state_key("link_pending", "note", "note-unlinked")
    ui = FakeUI(clicked={click_key})
    ui.session_state["reading_annotations_quick_note_body_doc-current"] = "keep"

    render_unlinked_items(
        ui,
        (item,),
        context=_linking_context(),
        actions_enabled=True,
    )

    assert "Pendientes de vincular" in ui.main_text()
    assert "Sin concepto asociado" in ui.main_text()
    assert ui.session_state[ACTIVE]
    assert ui.session_state[TARGET_KIND] == "note"
    assert ui.session_state[TARGET_ID] == "note-unlinked"
    assert ui.session_state[PDF_PAGE] == 5
    assert ui.session_state[PENDING_WORKSPACE_TAB] == "Conocimiento"
    assert ui.session_state["reading_annotations_quick_note_body_doc-current"] == "keep"
    assert ui.reruns == 1


def test_evidence_navigation_keeps_notes_tab_and_supports_source_only_notes() -> None:
    annotation = _evidence("ev-ann", _concept(), origin="annotation", page=9)
    annotation_ui = FakeUI()
    assert open_evidence(annotation_ui, annotation)
    assert annotation_ui.session_state[PENDING_WORKSPACE_TAB] == "Cuaderno"
    assert annotation_ui.session_state[SELECTED_ANNOTATION_ID] == annotation.annotation_id

    source_note = replace(
        _evidence("ev-note", _concept(), origin="note", page=None),
        document_id=None,
    )
    note_ui = FakeUI()
    assert open_evidence(note_ui, source_note)
    assert note_ui.session_state[PENDING_WORKSPACE_TAB] == "Cuaderno"
    assert note_ui.session_state[SELECTED_NOTE_ID] == source_note.note_id

    direct_ui = FakeUI()
    assert open_evidence(direct_ui, _evidence("ev-page", _concept(), origin="page", page=9))
    assert direct_ui.session_state[PENDING_WORKSPACE_TAB] == "Leer"


def test_legacy_evidence_tab_state_migrates_before_tabs_are_created() -> None:
    state = {WORKSPACE_TAB: "Evidence", PENDING_WORKSPACE_TAB: "Evidence"}

    assert migrate_legacy_workspace_tab(state)
    assert state[WORKSPACE_TAB] == "Conocimiento"
    assert state[PENDING_WORKSPACE_TAB] == "Conocimiento"
    assert not migrate_legacy_workspace_tab(state)


def test_every_public_state_key_constant_uses_the_s4_3_namespace() -> None:
    keys = (
        ACTIVE_CONTEXT,
        ACTIVE,
        STEP,
        DOCUMENT_ID,
        DUPLICATE_LINK_ID,
        PDF_PAGE,
        SELECTED_CONCEPT_KEY,
        MODE,
        TARGET_KIND,
        TARGET_ID,
        LINK_TYPE,
        COMMENT,
        SEARCH_QUERY,
        PARTIAL_TARGET_KIND,
        PARTIAL_TARGET_ID,
        PARTIAL_MESSAGE,
        RECENT_CONCEPTS,
    )
    assert all(key.startswith(SESSION_PREFIX) for key in keys)
    assert state_key("widget", "doc") == "concept_linking_widget_doc"


def test_all_s4_3_widget_keys_are_explicitly_namespaced() -> None:
    widget_methods = {
        "button",
        "checkbox",
        "form",
        "form_submit_button",
        "number_input",
        "pills",
        "radio",
        "segmented_control",
        "selectbox",
        "text_area",
        "text_input",
    }
    allowed_names = {
        "key",
        "ACTIVE",
        "COMMENT",
        "LINK_TYPE",
        "MODE",
        "SEARCH_QUERY",
    }
    violations: list[str] = []
    for path in CONCEPT_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                not isinstance(node, ast.Call)
                or getattr(node.func, "attr", "") not in widget_methods
            ):
                continue
            key = next((item.value for item in node.keywords if item.arg == "key"), None)
            valid = (
                isinstance(key, ast.Call)
                and isinstance(key.func, ast.Name)
                and key.func.id == "state_key"
            ) or (isinstance(key, ast.Name) and key.id in allowed_names)
            if not valid:
                violations.append(f"{path.name}:{node.lineno}")
    assert violations == []


def test_s4_3_modules_have_no_network_files_pdfjs_ocr_embeddings_or_scraping() -> None:
    forbidden_imports = {
        "aiohttp",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "tempfile",
        "urllib.request",
        "webbrowser",
    }
    forbidden_attributes = {
        "as_uri",
        "html",
        "iframe",
        "markdown",
        "urlopen",
    }
    forbidden_text = re.compile(
        r"file://|https?://|pdf(?:\.|_)?js|\bocr\b|\bembeddings?\b|\bscrap(?:e|ing|er)\b",
        re.IGNORECASE,
    )
    violations: list[str] = []
    for path in CONCEPT_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_imports:
                        violations.append(f"{path.name}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = str(node.module or "")
                if module in forbidden_imports:
                    violations.append(f"{path.name}:{node.lineno}: from {module}")
            elif isinstance(node, ast.Attribute) and node.attr in forbidden_attributes:
                violations.append(f"{path.name}:{node.lineno}: {node.attr}")
            elif isinstance(node, ast.Name) and node.id == "MongoClient":
                violations.append(f"{path.name}:{node.lineno}: MongoClient")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if forbidden_text.search(node.value):
                    violations.append(f"{path.name}:{node.lineno}: forbidden content")
    assert CONCEPT_MODULES
    assert violations == []


def test_s4_3_never_writes_directly_to_legacy_concepts() -> None:
    forbidden_methods = {
        "bulk_write",
        "delete_many",
        "delete_one",
        "find_one_and_delete",
        "find_one_and_replace",
        "find_one_and_update",
        "insert_many",
        "insert_one",
        "replace_one",
        "update_many",
        "update_one",
    }
    violations: list[str] = []
    for path in CONCEPT_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in forbidden_methods
            ):
                violations.append(f"{path.name}:{node.lineno}:{node.func.attr}")
    assert violations == []


def test_s5b_preserves_unrelated_domain_models_and_concept_evidence_contract() -> None:
    expected = {
        "mathmongo/source_catalog/models.py": "89c96e73bf223ab0df24fb7063821b26c340a0af33579e5c4bfca9d3dfe84213",
        "mathmongo/document_page_maps/models.py": "ddfabe3efbd843bcb9accf93ae6f64cbf0844291aa852bfd947e2720455923af",
        "mathmongo/source_documents/models.py": "84c88b00198e7c91b92bf3f994442b3897a792149467f715db058ea38609b54f",
        "mathmongo/reading_space/models.py": "32a0636f12085102dc5a0896a6f506416f9304031ed0c03d9f60ff3daab3ef2b",
    }
    observed = {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in expected
    }
    assert observed == expected
    assert tuple(ConceptEvidenceLink.model_fields) == (
        "schema_version",
        "evidence_link_id",
        "concept_legacy_id",
        "concept_legacy_source",
        "source_id",
        "reference_id",
        "document_id",
        "annotation_id",
        "note_id",
        "page_number",
        "link_type",
        "status",
        "comment",
        "created_at",
        "updated_at",
        "archived_at",
    )


def test_s4_3_preserves_every_existing_migration_module() -> None:
    expected_files = {
        "mathmongo/migrate_xdg.py": "b672667ccc65a8b1635bcde8982a63b234f2b0018ce9b72a5e0b79ba415bf8dc",
        "mathmongo/migrate_source_catalog.py": "07ec524cc76cab2907b2e99c0e590dd4e8cb4ba9082b331a4bcbdd8f2985df47",
    }
    assert {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in expected_files
    } == expected_files

    digest = hashlib.sha256()
    migration_root = ROOT / "mathmongo" / "source_catalog_migration"
    for path in sorted(migration_root.glob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}\n".encode())
    assert digest.hexdigest() == "bdfd877a1f11c81d1d4c7995d6697a1cceba891a427a22c48c0ed72c255fb150"

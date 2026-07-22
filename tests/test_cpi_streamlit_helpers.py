"""Tests for CPI Streamlit helper rendering."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from editor.cornell.models import CornellAttribution
from editor.cornell.models import CornellWatermark
from editor.cpi.models import DEFAULT_TEMPLATE_ID
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion
from editor.cpi.streamlit_page import SESSION_DIRTY
from editor.cpi.streamlit_page import SESSION_DOCUMENT
from editor.cpi.streamlit_page import SESSION_NOTE_ID
from editor.cpi.streamlit_page import SESSION_PAGE_INDEX
from editor.cpi.streamlit_page import _document_with_identity_from_inputs
from editor.cpi.streamlit_page import _render_page_editor
from editor.cpi.streamlit_page import _sync_identity_state_values
from editor.cpi.streamlit_page import add_page
from editor.cpi.streamlit_page import delete_page
from editor.cpi.streamlit_page import duplicate_page
from editor.note_branding import branding_key
from editor.note_branding import sync_branding_state


class FakeColumn:
    def __init__(self, app: FakeStreamlit) -> None:
        self.app = app

    def __enter__(self) -> FakeColumn:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def button(self, label: str, **kwargs):
        return self.app.button(label, **kwargs)


class FakeContext:
    def __enter__(self) -> FakeContext:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeCollection:
    def find(self, query):
        return []


class FakeDb:
    def __getitem__(self, name: str) -> FakeCollection:
        return FakeCollection()


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = {}
        self.expanders: list[str] = []
        self.file_uploader_keys: list[str] = []

    def expander(self, label: str, expanded: bool = False):
        self.expanders.append(label)
        return FakeContext()

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeColumn(self) for _ in range(count)]

    def selectbox(self, label: str, options, **kwargs):
        return options[0]

    def button(self, label: str, **kwargs):
        return False

    def file_uploader(self, label: str, **kwargs):
        self.file_uploader_keys.append(str(kwargs.get("key")))
        return None

    def text_input(self, *args, **kwargs):
        return ""

    def text_area(self, *args, **kwargs):
        return ""

    def subheader(self, *args, **kwargs) -> None:
        return None

    def caption(self, *args, **kwargs) -> None:
        return None

    def warning(self, *args, **kwargs) -> None:
        return None


def test_cpi_page_editor_renders_three_independent_image_managers(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    page = CpiPage(
        page_number=1,
        comprehension=CpiRegion(heading="Comprensión", latex="", image_ids=("img-comp",)),
        production=CpiRegion(heading="Producción", latex="", image_ids=()),
        integration=CpiRegion(heading="Integración", latex="", image_ids=("img-int-a", "img-int-b")),
    )
    document = CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=(page,),
    )
    fake_st.session_state.update(
        {
            SESSION_DOCUMENT: document,
            SESSION_PAGE_INDEX: 0,
            SESSION_NOTE_ID: None,
            SESSION_DIRTY: False,
        }
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "streamlit",
        SimpleNamespace(
            session_state=fake_st.session_state,
            expander=fake_st.expander,
            columns=fake_st.columns,
            selectbox=fake_st.selectbox,
            button=fake_st.button,
            file_uploader=fake_st.file_uploader,
            text_input=fake_st.text_input,
            text_area=fake_st.text_area,
            subheader=fake_st.subheader,
            caption=fake_st.caption,
            warning=fake_st.warning,
        ),
    )

    _render_page_editor(FakeDb(), page, 0)

    assert "Comprensión · Imágenes: 1" in fake_st.expanders
    assert "Producción · Imágenes: 0" in fake_st.expanders
    assert "Integración · Imágenes: 2" in fake_st.expanders
    assert "cpi_page_1_1_comprehension_media_upload" in fake_st.file_uploader_keys
    assert "cpi_page_1_1_production_media_upload" in fake_st.file_uploader_keys
    assert "cpi_page_1_1_integration_media_upload" in fake_st.file_uploader_keys


def identity_document(*pages: CpiPage) -> CpiDocument:
    return CpiDocument(
        schema_version=1,
        template_id=DEFAULT_TEMPLATE_ID,
        pages=pages or (
            CpiPage(
                page_number=1,
                comprehension=CpiRegion(heading="Comprensión", latex=""),
                production=CpiRegion(heading="Producción", latex=""),
                integration=CpiRegion(heading="Integración", latex=""),
            ),
        ),
        attribution=CornellAttribution(
            enabled=True,
            mode="custom",
            text="Material CPI",
            position="top_right",
        ),
        watermark=CornellWatermark(
            enabled=True,
            type="image",
            image_id="watermark-logo",
            opacity=0.12,
            scale=0.35,
            position="bottom_right",
        ),
    )


def test_page_operations_preserve_cpi_material_identity() -> None:
    page_1 = CpiPage(
        page_number=1,
        comprehension=CpiRegion(heading="Comprensión", latex="p1"),
        production=CpiRegion(heading="Producción", latex="p1"),
        integration=CpiRegion(heading="Integración", latex="p1"),
    )
    page_2 = CpiPage(
        page_number=2,
        comprehension=CpiRegion(heading="Comprensión", latex="p2"),
        production=CpiRegion(heading="Producción", latex="p2"),
        integration=CpiRegion(heading="Integración", latex="p2"),
    )
    original = identity_document(page_1, page_2)

    added, _added_index = add_page(original, 0)
    duplicated, _duplicate_index = duplicate_page(original, 0)
    deleted, _deleted_index = delete_page(original, 0)

    assert added.attribution == original.attribution
    assert added.watermark == original.watermark
    assert duplicated.attribution == original.attribution
    assert duplicated.watermark == original.watermark
    assert deleted.attribution == original.attribution
    assert deleted.watermark == original.watermark


def test_cpi_identity_state_and_inputs_use_cpi_keys(monkeypatch) -> None:
    document = identity_document()
    state = {}
    _sync_identity_state_values(state, document)
    sync_branding_state(
        state,
        note_type="cpi",
        note_id=None,
        watermark=document.watermark,
    )
    state.update(
        {
            "cpi_attribution_mode": "Automático",
            "cpi_attribution_text": "Texto inactivo",
            "cpi_attribution_author": "Enrique Díaz Ocampo",
            "cpi_attribution_course": "Python",
            "cpi_attribution_year": "2026",
            "cpi_attribution_position": "Inferior derecha",
            branding_key("cpi", None, "type"): "Texto",
            branding_key("cpi", None, "text"): "COCID",
            branding_key("cpi", None, "image_id"): "",
            branding_key("cpi", None, "opacity"): 0.08,
            branding_key("cpi", None, "scale"): 0.5,
            branding_key("cpi", None, "position"): "Centro",
        }
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "streamlit",
        SimpleNamespace(session_state=state),
    )

    updated = _document_with_identity_from_inputs(document)

    assert "cornell_attribution_enabled" not in state
    assert updated.attribution.mode == "auto"
    assert updated.attribution.author == "Enrique Díaz Ocampo"
    assert updated.attribution.course == "Python"
    assert updated.attribution.year == "2026"
    assert updated.attribution.position == "bottom_right"
    assert updated.watermark.type == "text"
    assert updated.watermark.text == "COCID"
    assert updated.watermark.opacity == 0.08
    assert updated.watermark.scale == 0.5
    assert updated.watermark.position == "center"


def test_editor_navigation_shows_cpi_icon_but_routes_to_cpi() -> None:
    source = (Path(__file__).resolve().parents[1] / "editor" / "editor_streamlit.py").read_text(
        encoding="utf-8",
    )

    assert 'CPI_NAV_LABEL = "🧩 CPI"' in source
    assert 'page = "CPI" if selected_page == CPI_NAV_LABEL else selected_page' in source
    assert 'elif page == "CPI":' in source

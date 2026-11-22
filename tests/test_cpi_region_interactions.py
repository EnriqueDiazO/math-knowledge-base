"""Characterize all three image regions before consolidating their renderers."""

import sys
from types import SimpleNamespace

import pytest
from test_cpi_streamlit_helpers import FakeDb
from test_cpi_streamlit_helpers import FakeStreamlit

from editor.cpi import streamlit_page as page_ui
from editor.cpi.models import CpiDocument
from editor.cpi.models import CpiPage
from editor.cpi.models import CpiRegion


class RerunSignal(BaseException):
    """Match Streamlit's non-Exception control transfer after a confirmed action."""


class RegionUI(FakeStreamlit):
    """Click exactly one region's control and record user-visible output."""

    def __init__(self, target):
        """Retain all original UI keys as part of the compatibility contract."""
        super().__init__()
        self.target = target
        self.messages = []

    def button(self, label, **kwargs):
        """Select by stable widget identity rather than translated label."""
        return kwargs.get("key") == self.target

    def file_uploader(self, *args, **kwargs):
        """Supply owned in-memory bytes, never a user's file."""
        super().file_uploader(*args, **kwargs)
        return SimpleNamespace(
            name="temporary.png", type="image/png", getvalue=lambda: b"owned fixture"
        )

    def success(self, value):
        """Capture the successful association status."""
        self.messages.append(value)

    def error(self, value):
        """Make swallowed action failures visible to the test."""
        pytest.fail(value)

    def markdown(self, *args, **kwargs):
        """Do not render asset metadata as executable HTML."""

    def code(self, *args, **kwargs):
        """The generated reference is verified in the session state below."""

    def rerun(self):
        """Stop immediately after the action, as the real application does."""
        raise RerunSignal


@pytest.mark.parametrize("region", ["comprehension", "production", "integration"])
@pytest.mark.parametrize("action", ["save", "insert", "remove"])
def test_region_actions_preserve_other_regions_and_stable_keys(monkeypatch, region, action):
    """Upload, insert and detach target one region and retain every other field."""
    regions = {
        name: CpiRegion(heading=name, latex="Original " + name, image_ids=("existing",))
        for name in page_ui.REGION_LABELS
    }
    page = CpiPage(page_number=1, **regions)
    document = CpiDocument(schema_version=1, template_id=page_ui.DEFAULT_TEMPLATE_ID, pages=(page,))
    suffix = action if action == "save" else action + "_existing"
    ui = RegionUI(f"cpi_page_1_1_{region}_media_{suffix}")
    ui.session_state.update(
        {
            page_ui.SESSION_DOCUMENT: document,
            page_ui.SESSION_NOTE_ID: "note",
            page_ui.SESSION_DIRTY: False,
            f"cpi_{region}_latex": "Texto conservado",
        }
    )
    monkeypatch.setitem(sys.modules, "streamlit", ui)
    monkeypatch.setattr(page_ui, "_render_latex_tools", lambda: None)
    monkeypatch.setattr(page_ui, "_document_from_inputs", lambda: document)
    monkeypatch.setattr(page_ui, "media_path_exists", lambda _asset: False)
    monkeypatch.setattr(
        page_ui,
        "media_collection",
        lambda _db: SimpleNamespace(
            find=lambda _query: [
                {"asset_id": "existing", "filename": "temporary.png", "path": "temporary.png"}
            ]
        ),
    )
    saved = []
    monkeypatch.setattr(
        page_ui,
        "save_media_asset",
        lambda _db, **kwargs: saved.append(kwargs) or {"asset_id": "new"},
    )
    with pytest.raises(RerunSignal):
        page_ui._render_page_editor(FakeDb(), page, 0)
    assert ui.session_state[page_ui.SESSION_DIRTY] is True
    updated = ui.session_state[page_ui.SESSION_DOCUMENT].pages[0]
    for name in regions:
        if name != region:
            assert getattr(updated, name) == regions[name]
    if action == "insert":
        assert (
            ui.session_state[f"cpi_{region}_latex"]
            == "Texto conservado\n" + page_ui.cpi_image_reference("existing") + "\n"
        )
        assert updated == page and saved == []
    else:
        assert getattr(updated, region).image_ids == (
            ("existing", "new") if action == "save" else ()
        )
        assert getattr(updated, region).latex == regions[region].latex
        assert len(saved) == (1 if action == "save" else 0)

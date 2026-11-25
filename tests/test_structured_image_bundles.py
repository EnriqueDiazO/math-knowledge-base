"""Portable academic images must be rendered, not replaced by placeholder macros."""

import io
import zipfile
from copy import deepcopy
from dataclasses import replace
from importlib import import_module

import pytest
from PIL import Image

from editor.note_export import build_note_latex_bundle


def image_note(tmp_path, family):
    """Use the canonical format with an inline ratio and a separate associated image."""
    helpers = import_module("tests.test_" + family + "_service")
    models = import_module("editor." + family + ".models")
    persistence = import_module("editor." + family + ".persistence")
    document = helpers.sample_document()
    key = "production" if family == "cpi" else "main"
    page = document.ordered_pages()[0]
    region = replace(
        getattr(page, key),
        latex="Antes\\n\\" + family + "image[0.7]{inline-image}\\nDespués",
        image_ids=("associated-image",),
    )
    document = replace(document, pages=(replace(page, **{key: region}),))
    note = getattr(persistence, "build_" + family + "_note_document")(
        helpers.sample_metadata(), document
    )
    assert note["latex_body"] == models.generate_latex_body(document)
    assets = {}
    for index, identity in enumerate(("inline-image", "associated-image")):
        path = tmp_path / (identity + ".png")
        Image.new("RGB", (32 + index, 18), ("#197f96", "#b44464")[index]).save(path)
        assets[identity] = {"asset_id": identity, "filename": path.name, "path": str(path)}
    return note, assets


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_portable_images_resolve_optional_width_and_keep_original_source(tmp_path, family):
    """The exported main actually includes both resources; the authored body stays exact."""
    note, assets = image_note(tmp_path, family)
    original = deepcopy(note)
    bundle = build_note_latex_bundle(note, assets_by_id=assets)
    with zipfile.ZipFile(io.BytesIO(bundle.zip_bytes)) as archive:
        main = archive.read(next(n for n in archive.namelist() if n.endswith("/main.tex"))).decode()
        body = archive.read(
            next(n for n in archive.namelist() if n.endswith("/content/body.tex"))
        ).decode()
        assert r"\resizebox{0.7\linewidth}{!}{\includegraphics{images/" in main
        assert main.count(r"\includegraphics{images/") >= 2
        assert str(tmp_path) not in main
        assert body == original["latex_body"]
        assert len([n for n in archive.namelist() if "/images/" in n and n.endswith(".png")]) >= 2
    assert note == original


@pytest.mark.parametrize("family", ["cornell", "cpi"])
def test_required_image_missing_or_symlink_is_actionable_and_does_not_mutate_source(
    tmp_path, family
):
    """Neither missing bytes nor a symlink may silently turn into a successful placeholder PDF."""
    from editor.structured_note_resources import StructuredNoteResourceError

    note, assets = image_note(tmp_path, family)
    original = deepcopy(note)
    path = tmp_path / "inline-image.png"
    path.unlink()
    with pytest.raises(StructuredNoteResourceError, match="inline-image"):
        build_note_latex_bundle(note, assets_by_id=assets)
    path.symlink_to(tmp_path / "associated-image.png")
    with pytest.raises(StructuredNoteResourceError, match="vuelve a asociar"):
        build_note_latex_bundle(note, assets_by_id=assets)
    assert note == original

"""Tests for the shared internal PDF preview lifecycle."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from editor.pdf_preview import PdfPreviewError
from editor.pdf_preview import PdfPreviewPayload
from editor.pdf_preview import clear_pdf_preview
from editor.pdf_preview import generate_pdf_preview
from editor.pdf_preview import get_pdf_preview
from editor.pdf_preview import load_pdf_preview
from editor.pdf_preview import pdf_preview_context
from editor.pdf_preview import prepare_stable_preview
from editor.pdf_preview import render_pdf_preview
from editor.pdf_preview import store_pdf_preview

VALID_PDF = b"%PDF-1.7\ninternal preview\n%%EOF\n"


class FakeUi:
    def __init__(self, *, pdf_error: bool = False, close: bool = False) -> None:
        self.pdf_error = pdf_error
        self.close = close
        self.pdf_calls: list[tuple[bytes, dict]] = []
        self.download_calls: list[dict] = []
        self.errors: list[str] = []
        self.reruns = 0

    def pdf(self, data: bytes, **kwargs) -> None:
        self.pdf_calls.append((data, kwargs))
        if self.pdf_error:
            raise RuntimeError("component unavailable")

    def download_button(self, _label: str, **kwargs) -> None:
        self.download_calls.append(kwargs)

    def button(self, label: str, **_kwargs) -> bool:
        return self.close and label == "Cerrar vista previa"

    def error(self, message: str) -> None:
        self.errors.append(message)

    def rerun(self) -> None:
        self.reruns += 1


def _load(tmp_path: Path, data: bytes = VALID_PDF) -> PdfPreviewPayload:
    pdf = tmp_path / "preview with spaces.pdf"
    pdf.write_bytes(data)
    return load_pdf_preview(
        pdf,
        allowed_root=tmp_path,
        file_name="preview.pdf",
        context_identity=pdf_preview_context("db", "entity"),
    )


def test_prepare_stable_preview_removes_stale_pdf_and_auxiliaries(tmp_path: Path) -> None:
    preview_dir = tmp_path / "runtime with spaces"
    preview_dir.mkdir()
    for name in (
        "cornell_preview.pdf",
        "cornell_preview.aux",
        "cornell_preview.log",
        "cornell_preview_fit.log",
    ):
        (preview_dir / name).write_bytes(b"old")
    export = preview_dir / "user-export.zip"
    export.write_bytes(b"keep")
    unrelated_log = preview_dir / "unrelated.log"
    unrelated_log.write_bytes(b"keep-log")

    result = prepare_stable_preview(
        preview_dir,
        "cornell_preview.pdf",
        allowed_root=tmp_path,
    )

    assert result == preview_dir.resolve() / "cornell_preview.pdf"
    assert not result.exists()
    assert not (preview_dir / "cornell_preview.aux").exists()
    assert not (preview_dir / "cornell_preview.log").exists()
    assert not (preview_dir / "cornell_preview_fit.log").exists()
    assert export.exists()
    assert unrelated_log.read_bytes() == b"keep-log"


def test_load_pdf_preview_returns_exact_bytes_and_sha_from_one_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    real_open = os.open

    def counted_open(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr(os, "open", counted_open)

    payload = _load(tmp_path)

    assert calls == 1
    assert payload.pdf_bytes == VALID_PDF
    assert payload.sha256 == hashlib.sha256(VALID_PDF).hexdigest()
    assert payload.file_name == "preview.pdf"


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "empty"),
        (b"not a pdf", "invalid_header"),
    ],
)
def test_load_pdf_preview_rejects_empty_or_invalid_files(
    tmp_path: Path,
    data: bytes,
    code: str,
) -> None:
    with pytest.raises(PdfPreviewError) as error:
        _load(tmp_path, data)

    assert error.value.code == code


def test_load_pdf_preview_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PdfPreviewError) as error:
        load_pdf_preview(
            tmp_path / "missing.pdf",
            allowed_root=tmp_path,
            file_name="missing.pdf",
            context_identity="context",
        )

    assert error.value.code == "missing"


def test_load_pdf_preview_rejects_non_regular_file(tmp_path: Path) -> None:
    directory = tmp_path / "directory.pdf"
    directory.mkdir()

    with pytest.raises(PdfPreviewError) as error:
        load_pdf_preview(
            directory,
            allowed_root=tmp_path,
            file_name="directory.pdf",
            context_identity="context",
        )

    assert error.value.code == "not_regular"


def test_load_pdf_preview_rejects_symlink_leaf(tmp_path: Path) -> None:
    target = tmp_path / "target.pdf"
    target.write_bytes(VALID_PDF)
    alias = tmp_path / "alias.pdf"
    alias.symlink_to(target)

    with pytest.raises(PdfPreviewError) as error:
        load_pdf_preview(
            alias,
            allowed_root=tmp_path,
            file_name="alias.pdf",
            context_identity="context",
        )

    assert error.value.code == "outside_controlled_root"


def test_load_pdf_preview_rejects_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(VALID_PDF)

    with pytest.raises(PdfPreviewError) as error:
        load_pdf_preview(
            outside,
            allowed_root=root,
            file_name="outside.pdf",
            context_identity="context",
        )

    assert error.value.code == "outside_controlled_root"


def test_preview_filename_cannot_escape_controlled_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="plain PDF filename"):
        prepare_stable_preview(
            tmp_path,
            "../outside.pdf",
            allowed_root=tmp_path,
        )


def test_preview_directory_symlink_cannot_escape_allowed_root(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    outside = tmp_path / "outside"
    runtime.mkdir()
    outside.mkdir()
    unrelated = outside / "unrelated.log"
    unrelated.write_bytes(b"must survive")
    (runtime / "cornell_preview").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="Symbolic links"):
        prepare_stable_preview(
            runtime / "cornell_preview",
            "cornell_preview.pdf",
            allowed_root=runtime,
        )

    assert unrelated.read_bytes() == b"must survive"
    assert not (outside / "cornell_preview.pdf").exists()


def test_preview_rejects_a_symlink_ancestor_of_a_missing_allowed_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    allowed = alias / "runtime"

    with pytest.raises(ValueError, match="Symbolic links"):
        prepare_stable_preview(
            allowed / "cornell_preview",
            "cornell_preview.pdf",
            allowed_root=allowed,
        )

    assert not (outside / "runtime").exists()


def test_preview_rejects_the_installed_package_tree() -> None:
    project_root = Path(__file__).resolve().parents[1]
    preview = project_root / "templates_latex" / "forbidden_preview.pdf"

    with pytest.raises(ValueError, match="installed MathMongo package"):
        prepare_stable_preview(
            project_root / "templates_latex",
            preview.name,
            allowed_root=project_root,
        )

    assert not preview.exists()


def test_preview_state_is_namespaced_replaced_and_invalidated(tmp_path: Path) -> None:
    state: dict = {}
    add_payload = _load(tmp_path)
    cornell_payload = PdfPreviewPayload(
        pdf_bytes=VALID_PDF + b"cornell",
        sha256="cornell-sha",
        file_name="cornell.pdf",
        context_identity="cornell-context",
    )
    store_pdf_preview(state, "add_concept", add_payload)
    store_pdf_preview(state, "cornell", cornell_payload)

    assert (
        get_pdf_preview(
            state,
            "add_concept",
            context_identity=add_payload.context_identity,
        )
        is add_payload
    )
    assert (
        get_pdf_preview(
            state,
            "add_concept",
            context_identity="different-database-or-entity",
        )
        is None
    )
    assert (
        get_pdf_preview(
            state,
            "cornell",
            context_identity="cornell-context",
        )
        is cornell_payload
    )

    clear_pdf_preview(state, "cornell")
    assert state == {}


def test_generation_failure_clears_stale_preview(tmp_path: Path) -> None:
    state: dict = {}
    store_pdf_preview(state, "cpi", _load(tmp_path))

    with pytest.raises(RuntimeError, match="compile failed"):
        generate_pdf_preview(
            state,
            "cpi",
            generator=lambda: (_ for _ in ()).throw(RuntimeError("compile failed")),
            allowed_root=tmp_path,
            file_name="cpi.pdf",
            context_identity="context",
        )

    assert get_pdf_preview(state, "cpi", context_identity="context") is None


def test_internal_viewer_persists_and_downloads_the_exact_same_bytes(tmp_path: Path) -> None:
    state: dict = {}
    payload = _load(tmp_path)
    store_pdf_preview(state, "edit_concept", payload)
    ui = FakeUi()

    assert render_pdf_preview(
        ui,
        state,
        "edit_concept",
        context_identity=payload.context_identity,
    )

    assert ui.pdf_calls[0][0] is payload.pdf_bytes
    assert ui.pdf_calls[0][1]["height"] == 800
    assert ui.pdf_calls[0][1]["key"].startswith("pdf_preview_edit_concept_viewer_")
    assert ui.download_calls[0]["data"] is payload.pdf_bytes
    assert ui.download_calls[0]["file_name"] == "preview.pdf"
    assert ui.errors == []
    assert ui.reruns == 0


def test_component_failure_keeps_exact_download_and_reports_action(tmp_path: Path) -> None:
    state: dict = {}
    payload = _load(tmp_path)
    store_pdf_preview(state, "cornell", payload)
    ui = FakeUi(pdf_error=True)

    assert render_pdf_preview(
        ui,
        state,
        "cornell",
        context_identity=payload.context_identity,
    )

    assert "streamlit[pdf]" in ui.errors[0]
    assert ui.download_calls[0]["data"] is payload.pdf_bytes


def test_missing_component_keeps_download_and_reports_install_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state: dict = {}
    payload = _load(tmp_path)
    store_pdf_preview(state, "cornell", payload)
    ui = FakeUi()
    ui.__name__ = "streamlit"
    monkeypatch.setattr("editor.pdf_preview.importlib.util.find_spec", lambda _name: None)

    assert render_pdf_preview(
        ui,
        state,
        "cornell",
        context_identity=payload.context_identity,
    )

    assert ui.pdf_calls == []
    assert "streamlit[pdf]" in ui.errors[0]
    assert ui.download_calls[0]["data"] is payload.pdf_bytes


def test_close_clears_only_current_namespace_and_reruns(tmp_path: Path) -> None:
    state: dict = {}
    payload = _load(tmp_path)
    store_pdf_preview(state, "cpi", payload)
    store_pdf_preview(state, "add_concept", payload)
    ui = FakeUi(close=True)

    assert render_pdf_preview(
        ui,
        state,
        "cpi",
        context_identity=payload.context_identity,
    )

    assert get_pdf_preview(state, "cpi", context_identity=payload.context_identity) is None
    assert (
        get_pdf_preview(
            state,
            "add_concept",
            context_identity=payload.context_identity,
        )
        is payload
    )
    assert ui.reruns == 1

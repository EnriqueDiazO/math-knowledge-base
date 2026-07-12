"""Focused controller tests for generated Cornell and CPI PDF previews."""

# ruff: noqa: D101,D102,D103,D105,D107

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from editor.pdf_preview import PdfPreviewPayload
from editor.pdf_preview import get_pdf_preview
from editor.pdf_preview import store_pdf_preview

VALID_PDF = b"%PDF-1.7\ncontroller preview\n%%EOF\n"


class FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeStreamlit:
    def __init__(self, session_state: dict) -> None:
        self.session_state = session_state
        self.successes: list[str] = []
        self.errors: list[str] = []
        self.codes: list[str] = []

    def success(self, message: str) -> None:
        self.successes.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def expander(self, *_args, **_kwargs):
        return FakeContext()

    def code(self, value: str, **_kwargs) -> None:
        self.codes.append(value)


class ReadOnlyFakeDatabase:
    name = "MathV0"

    def __getattr__(self, name: str):
        if name in {"insert_one", "update_one", "delete_one", "replace_one"}:
            raise AssertionError("PDF preview must not write MongoDB")
        raise AttributeError(name)


@pytest.mark.parametrize(
    ("module_name", "namespace", "note_key", "renderer_name", "filename"),
    [
        (
            "editor.cornell.streamlit_page",
            "cornell",
            "cornell_note_id",
            "render_cornell_document",
            "cornell_preview.pdf",
        ),
        (
            "editor.cpi.streamlit_page",
            "cpi",
            "cpi_note_id",
            "render_cpi_document",
            "cpi_preview.pdf",
        ),
    ],
)
def test_note_preview_controller_publishes_valid_pdf_without_database_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    namespace: str,
    note_key: str,
    renderer_name: str,
    filename: str,
) -> None:
    module = __import__(module_name, fromlist=["unused"])
    state = {note_key: "note-1"}
    fake_st = FakeStreamlit(state)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setattr(module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(module, "_document_from_inputs", lambda: object())
    monkeypatch.setattr(module, "_render_fit_report", lambda _diagnostics: None)

    def render(_document, output_dir, output_name, *, db):
        assert db.name == "MathV0"
        path = Path(output_dir) / f"{output_name}.pdf"
        path.write_bytes(VALID_PDF)
        return SimpleNamespace(
            success=True,
            status="success_with_warnings",
            pdf_path=path,
            diagnostics={"warnings": ["non-fatal"]},
            message="",
        )

    monkeypatch.setattr(module, renderer_name, render)

    module._preview_pdf(ReadOnlyFakeDatabase())

    context = module._current_pdf_preview_context(ReadOnlyFakeDatabase())
    payload = get_pdf_preview(state, namespace, context_identity=context)
    assert payload is not None
    assert payload.pdf_bytes == VALID_PDF
    assert payload.file_name == filename
    assert fake_st.successes == ["PDF generado y disponible en la vista previa."]
    assert fake_st.errors == []


@pytest.mark.parametrize(
    ("module_name", "namespace", "note_key", "renderer_name"),
    [
        (
            "editor.cornell.streamlit_page",
            "cornell",
            "cornell_note_id",
            "render_cornell_document",
        ),
        (
            "editor.cpi.streamlit_page",
            "cpi",
            "cpi_note_id",
            "render_cpi_document",
        ),
    ],
)
def test_note_preview_failure_never_reuses_stale_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    namespace: str,
    note_key: str,
    renderer_name: str,
) -> None:
    module = __import__(module_name, fromlist=["unused"])
    state = {note_key: "note-2"}
    fake_st = FakeStreamlit(state)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setattr(module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(module, "_document_from_inputs", lambda: object())
    monkeypatch.setattr(module, "_render_fit_report", lambda _diagnostics: None)
    monkeypatch.setattr(
        module,
        renderer_name,
        lambda *_args, **_kwargs: SimpleNamespace(
            success=False,
            pdf_path=tmp_path / "missing.pdf",
            diagnostics={"fatal_errors": ["bad latex"]},
            message="No se pudo generar el PDF.",
        ),
    )
    stale = PdfPreviewPayload(
        pdf_bytes=VALID_PDF,
        sha256="stale",
        file_name="stale.pdf",
        context_identity=module._current_pdf_preview_context(ReadOnlyFakeDatabase()),
    )
    store_pdf_preview(state, namespace, stale)

    module._preview_pdf(ReadOnlyFakeDatabase())

    context = module._current_pdf_preview_context(ReadOnlyFakeDatabase())
    assert get_pdf_preview(state, namespace, context_identity=context) is None
    assert fake_st.successes == []
    assert fake_st.errors == [
        "No se pudo generar el PDF. Revisa el contenido LaTeX y vuelve a intentarlo."
    ]


@pytest.mark.parametrize(
    ("module_name", "namespace", "note_key", "apply_name", "document_factory"),
    [
        (
            "editor.cornell.streamlit_page",
            "cornell",
            "cornell_note_id",
            "apply_loaded_note_state",
            "make_blank_document",
        ),
        (
            "editor.cpi.streamlit_page",
            "cpi",
            "cpi_note_id",
            "apply_loaded_note_state",
            "make_blank_document",
        ),
    ],
)
def test_loading_another_note_clears_only_its_preview_namespace(
    module_name: str,
    namespace: str,
    note_key: str,
    apply_name: str,
    document_factory: str,
) -> None:
    module = __import__(module_name, fromlist=["unused"])
    payload = PdfPreviewPayload(VALID_PDF, "sha", "preview.pdf", "old")
    state = {note_key: "old"}
    store_pdf_preview(state, namespace, payload)
    other_namespace = "cpi" if namespace == "cornell" else "cornell"
    store_pdf_preview(state, other_namespace, payload)

    getattr(module, apply_name)(
        state,
        note_id="new",
        note=None,
        document=getattr(module, document_factory)(),
    )

    assert get_pdf_preview(state, namespace, context_identity="old") is None
    assert get_pdf_preview(state, other_namespace, context_identity="old") is payload

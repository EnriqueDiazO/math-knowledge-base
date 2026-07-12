"""Focused tests for persistence-free S1B Reference and BibTeX UI helpers."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import hashlib
from contextlib import nullcontext
from datetime import timezone
from typing import Any

import pytest

from editor.source_catalog.bibtex_ui import MAX_BIBTEX_UI_ENTRIES
from editor.source_catalog.bibtex_ui import MAX_BIBTEX_UPLOAD_BYTES
from editor.source_catalog.bibtex_ui import BibTeXSelection
from editor.source_catalog.bibtex_ui import render_bibtex_input
from editor.source_catalog.bibtex_ui import selected_bibtex_references
from editor.source_catalog.bibtex_ui import uploaded_bibtex_bytes
from editor.source_catalog.reference_form import authors_to_text
from editor.source_catalog.reference_form import build_reference_from_form
from editor.source_catalog.reference_form import parse_accessed_at
from editor.source_catalog.reference_form import parse_authors_text
from editor.source_catalog.reference_form import render_reference_form
from editor.source_catalog.state import draft_fingerprint
from editor.source_catalog.state import state_key
from mathmongo.source_catalog.bibtex import MAX_BIBTEX_TEXT_CHARS
from mathmongo.source_catalog.bibtex import parse_bibtex_file_content
from mathmongo.source_catalog.bibtex import parse_bibtex_text
from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source


class FakeUploadedFile:
    def __init__(self, value: bytes, name: str = "references.bib") -> None:
        self._value = value
        self.name = name

    def getvalue(self) -> bytes:
        return self._value


class FakeUI:
    def __init__(
        self,
        *,
        values: dict[str, Any] | None = None,
        clicked: set[str] | None = None,
        uploaded: Any = None,
    ) -> None:
        self.values = dict(values or {})
        self.clicked = set(clicked or set())
        self.uploaded = uploaded
        self.session_state: dict[str, Any] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.captions: list[str] = []
        self.code_values: list[str] = []
        self.widget_keys: list[str] = []

    def _widget_value(self, key: str, default: Any) -> Any:
        self.widget_keys.append(key)
        value = self.values.get(key, self.session_state.get(key, default))
        self.session_state[key] = value
        return value

    def selectbox(self, _label, options, *, key, index=0, **_kwargs):
        return self._widget_value(key, list(options)[index])

    def text_input(self, _label, *, key, value="", **_kwargs):
        return self._widget_value(key, value)

    def text_area(self, _label, *, key, value="", **_kwargs):
        return self._widget_value(key, value)

    def checkbox(self, _label, *, key, value=False, **_kwargs):
        return bool(self._widget_value(key, value))

    def multiselect(self, _label, *, options, key, default=(), **_kwargs):
        value = self._widget_value(key, list(default))
        return [item for item in value if item in options]

    def file_uploader(self, _label, *, key, **_kwargs):
        self.widget_keys.append(key)
        return self.uploaded

    def button(self, _label, *, key, **_kwargs):
        self.widget_keys.append(key)
        return key in self.clicked

    def expander(self, *_args, **_kwargs):
        return nullcontext()

    def dataframe(self, *_args, **_kwargs) -> None:
        return None

    def caption(self, value, **_kwargs) -> None:
        self.captions.append(str(value))

    def warning(self, value, **_kwargs) -> None:
        self.warnings.append(str(value))

    def error(self, value, **_kwargs) -> None:
        self.errors.append(str(value))

    def success(self, *_args, **_kwargs) -> None:
        return None

    def markdown(self, *_args, **_kwargs) -> None:
        return None

    def write(self, *_args, **_kwargs) -> None:
        return None

    def code(self, value, **_kwargs) -> None:
        self.code_values.append(str(value))


class PreviewOnlyService:
    def __init__(self) -> None:
        self.preview_calls: list[tuple[str | bytes, bool]] = []
        self.duplicate_calls: list[Reference] = []
        self.write_calls = 0

    def preview_bibtex(self, content, *, from_file=False):
        self.preview_calls.append((content, from_file))
        if from_file:
            return parse_bibtex_file_content(content)
        return parse_bibtex_text(content)

    def detect_reference_duplicates(self, reference, *, import_context=None):
        assert import_context and import_context.startswith("bibtex-entry:")
        self.duplicate_calls.append(reference)
        return []

    def create_reference(self, *_args, **_kwargs):
        self.write_calls += 1
        raise AssertionError("BibTeX preview attempted a write")


def test_author_text_roundtrip_keeps_structured_and_literal_names() -> None:
    parsed = parse_authors_text(
        "Lovelace | Ada\nliteral: World Health Organization\nHistorical Author"
    )

    assert parsed == [
        {"family": "Lovelace", "given": "Ada", "literal": None},
        {"family": None, "given": None, "literal": "World Health Organization"},
        {"family": None, "given": None, "literal": "Historical Author"},
    ]
    reference = Reference(title="Names", authors=parsed)
    assert authors_to_text(reference.authors) == (
        "Lovelace | Ada\nliteral: World Health Organization\nliteral: Historical Author"
    )


def test_build_reference_supports_complete_manual_fields_and_utc_accessed_at() -> None:
    source = Source(name="Article")
    reference = build_reference_from_form(
        {
            "reference_type": "article",
            "authors_text": "Bastos | M. Amélia\nliteral: Research Group",
            "title": "Fredholmness",
            "year": "2026",
            "year_raw": "published 2026",
            "journal": "Integral Equations",
            "publisher": "Springer",
            "volume": "98",
            "number": "1",
            "edition": "First",
            "isbn_text": "978-0-306-40615-7",
            "doi": "https://doi.org/10.1007/example",
            "url": "https://example.test/article",
            "accessed_at": "2026-07-11T18:30:00-06:00",
            "language": "en",
            "notes": "Reviewed",
            "bibtex_key": "Bastos2026",
        },
        source_ids=[source.source_id],
    )

    assert reference.source_ids == [source.source_id]
    assert reference.reference_type.value == "article"
    assert reference.authors[0].family == "Bastos"
    assert reference.authors[1].literal == "Research Group"
    assert reference.year == 2026
    assert reference.year_raw == "published 2026"
    assert reference.isbn == ["978-0-306-40615-7"]
    assert reference.bibtex.key == "Bastos2026"
    assert reference.accessed_at.tzinfo == timezone.utc
    assert reference.accessed_at.hour == 0
    assert reference.accessed_at.minute == 30


def test_edit_preserves_reference_id_and_bibtex_raw_until_explicit_replacement() -> None:
    raw = "@article{stable, title={Original}}"
    initial = Reference(
        title="Original",
        bibtex={
            "key": "stable",
            "entry_type": "article",
            "raw": raw,
            "extra": {"legacy": "preserved until replacement"},
        },
    )

    edited = build_reference_from_form(
        {"title": "Edited", "bibtex_key": "stable-edited"},
        initial=initial,
        reference_id=initial.reference_id,
    )
    replaced = build_reference_from_form(
        {
            "title": "Edited again",
            "bibtex_key": "new",
            "replace_bibtex_raw": True,
            "bibtex_entry_type": "book",
            "bibtex_raw": "@book{new, title={Edited again}}",
        },
        initial=edited,
    )

    assert edited.reference_id == initial.reference_id
    assert edited.bibtex.raw == raw
    assert edited.bibtex.raw_sha256 == initial.bibtex.raw_sha256
    assert replaced.reference_id == initial.reference_id
    assert replaced.bibtex.raw != raw
    assert replaced.bibtex.entry_type == "book"
    assert replaced.bibtex.extra == {}
    with pytest.raises(ValueError, match="reference_id cannot change"):
        build_reference_from_form(
            {"title": "No"},
            initial=initial,
            reference_id=Reference(title="Other").reference_id,
        )


def test_reference_form_returns_validation_errors_without_persistence() -> None:
    ui = FakeUI()

    draft = render_reference_form(ui, key_prefix="manual")

    assert draft.valid is False
    assert draft.reference is None
    assert any("requires title" in error for error in draft.errors)
    assert ui.widget_keys
    assert all(key.startswith("source_catalog_") for key in ui.widget_keys)


def test_uploaded_bibtex_bytes_accepts_only_bounded_already_read_bib_files() -> None:
    content = b"@misc{file, doi={10.1000/file}}"

    assert uploaded_bibtex_bytes(FakeUploadedFile(content)) == content
    with pytest.raises(ValueError, match=".bib extension"):
        uploaded_bibtex_bytes(FakeUploadedFile(content, name="references.txt"))

    class DeclaredOversize:
        name = "too-large.bib"
        size = MAX_BIBTEX_UPLOAD_BYTES + 1

        def getvalue(self):
            raise AssertionError("oversized upload must be rejected before materialization")

    with pytest.raises(ValueError, match="exceeds"):
        uploaded_bibtex_bytes(DeclaredOversize())


def test_oversized_paste_is_rejected_before_hash_or_service_preview() -> None:
    prefix = "oversized"
    ui = FakeUI(
        values={
            state_key(prefix, "bibtex_mode"): "Paste BibTeX",
            state_key(prefix, "bibtex_paste"): "x" * (MAX_BIBTEX_TEXT_CHARS + 1),
        },
        clicked={state_key(prefix, "bibtex_preview_button")},
    )
    service = PreviewOnlyService()

    selection = render_bibtex_input(ui, service, key_prefix=prefix)

    assert selection.preview is None
    assert service.preview_calls == []
    assert any("character limit" in error for error in ui.errors)


def test_bibtex_paste_preview_multiple_error_and_partial_selection_never_writes() -> None:
    prefix = "paste"
    content = """@article{, title={Missing key}}
@misc{one, doi={10.1000/one}}
@book{two, title={Two}, author={{Example Organization}}}
"""
    ui = FakeUI(
        values={
            state_key(prefix, "bibtex_mode"): "Paste BibTeX",
            state_key(prefix, "bibtex_paste"): content,
            state_key(prefix, "bibtex_selected_entries"): [3],
        },
        clicked={state_key(prefix, "bibtex_preview_button")},
    )
    service = PreviewOnlyService()

    selection = render_bibtex_input(ui, service, key_prefix=prefix)

    assert selection.selected_entry_indices == (3,)
    assert len(selection.drafts) == 1
    assert selection.drafts[0].reference.title == "Two"
    assert selection.drafts[0].reference.bibtex.key == "two"
    assert selection.drafts[0].reference.bibtex.raw.startswith("@book")
    assert any("Entry 1" in error for error in selection.errors)
    assert len(service.preview_calls) == 1
    assert service.write_calls == 0
    assert all(key.startswith("source_catalog_") for key in ui.widget_keys)


def test_bibtex_ui_caps_one_render_batch_without_losing_preview_count() -> None:
    prefix = "bounded_batch"
    content = "\n".join(
        f"@misc{{entry{index}, title={{Entry {index}}}}}"
        for index in range(MAX_BIBTEX_UI_ENTRIES + 5)
    )
    ui = FakeUI(
        values={
            state_key(prefix, "bibtex_mode"): "Paste BibTeX",
            state_key(prefix, "bibtex_paste"): content,
        },
        clicked={state_key(prefix, "bibtex_preview_button")},
    )

    selection = render_bibtex_input(ui, PreviewOnlyService(), key_prefix=prefix)

    assert selection.preview is not None
    assert len(selection.preview.candidates) == MAX_BIBTEX_UI_ENTRIES + 5
    assert len(selection.drafts) == MAX_BIBTEX_UI_ENTRIES
    assert any("Only the first" in warning for warning in ui.warnings)


def test_bibtex_preview_survives_unrelated_rerun_but_not_changed_input() -> None:
    prefix = "rerun"
    paste_key = state_key(prefix, "bibtex_paste")
    ui = FakeUI(
        values={
            state_key(prefix, "bibtex_mode"): "Paste BibTeX",
            paste_key: "@misc{one, title={One}}",
        },
        clicked={state_key(prefix, "bibtex_preview_button")},
    )
    service = PreviewOnlyService()

    first = render_bibtex_input(ui, service, key_prefix=prefix)
    ui.clicked.clear()
    unchanged = render_bibtex_input(ui, service, key_prefix=prefix)
    ui.values[paste_key] = "@misc{two, title={Two}}"
    changed = render_bibtex_input(ui, service, key_prefix=prefix)

    assert first.preview is not None
    assert unchanged.preview is first.preview
    assert len(service.preview_calls) == 1
    assert changed.preview is None
    assert any("input changed" in caption for caption in ui.captions)


def test_bibtex_upload_preview_uses_service_file_mode_and_scopes_selected_reference() -> None:
    prefix = "upload"
    content = b"@misc{upload, url={https://example.test/resource}}"
    ui = FakeUI(
        values={state_key(prefix, "bibtex_mode"): "Upload .bib"},
        clicked={state_key(prefix, "bibtex_preview_button")},
        uploaded=FakeUploadedFile(content),
    )
    service = PreviewOnlyService()

    selection = render_bibtex_input(ui, service, key_prefix=prefix)
    source = Source(name="Web")
    references = selected_bibtex_references(selection, source_ids=[source.source_id])

    assert service.preview_calls == [(content, True)]
    assert selection.ready
    assert references[0].source_ids == [source.source_id]
    assert references[0].bibtex.raw == content.decode()
    assert service.write_calls == 0


def test_bibtex_raw_snippet_redacts_uri_userinfo_and_secret_assignments() -> None:
    prefix = "redacted"
    content = """@misc{private,
  url={https://alice:private-pass@example.test/resource},
  note={token=private-token},
  api_key={private-api-key},
  file={/home/alice/Documents/private-paper.pdf}
}
"""
    raw_hash = hashlib.sha256(content.rstrip().encode()).hexdigest()[:12]
    ui = FakeUI(
        values={
            state_key(prefix, "bibtex_mode"): "Paste BibTeX",
            state_key(prefix, "bibtex_paste"): content,
            state_key(prefix, "bibtex_show_raw", 1, raw_hash): True,
        },
        clicked={state_key(prefix, "bibtex_preview_button")},
    )

    selection = render_bibtex_input(ui, PreviewOnlyService(), key_prefix=prefix)

    assert selection.preview is not None
    rendered_raw = "\n".join(ui.code_values)
    assert "alice" not in rendered_raw
    assert "private-pass" not in rendered_raw
    assert "private-token" not in rendered_raw
    assert "private-api-key" not in rendered_raw
    assert "/home/alice" not in rendered_raw
    assert "<redacted>" in rendered_raw


def test_possible_duplicate_requires_explicit_decision_before_selection_is_ready() -> None:
    class PossibleDuplicateService(PreviewOnlyService):
        def detect_reference_duplicates(self, reference, *, import_context=None):
            self.duplicate_calls.append(reference)
            return [
                DuplicateMatch(
                    entity_id="existing-reference",
                    classification=DuplicateClassification.POSSIBLE,
                )
            ]

    prefix = "possible"
    raw = "@misc{x, title={Possible}}"
    raw_hash = hashlib.sha256(raw.encode()).hexdigest()[:12]
    common_values = {
        state_key(prefix, "bibtex_mode"): "Paste BibTeX",
        state_key(prefix, "bibtex_paste"): raw,
    }
    blocked_ui = FakeUI(
        values=common_values,
        clicked={state_key(prefix, "bibtex_preview_button")},
    )
    blocked = render_bibtex_input(
        blocked_ui,
        PossibleDuplicateService(),
        key_prefix=prefix,
    )
    candidate_fingerprint = draft_fingerprint(blocked.drafts[0].reference)
    confirmed_ui = FakeUI(
        values={
            **common_values,
            state_key(
                prefix,
                "bibtex_allow_duplicate",
                1,
                raw_hash,
                candidate_fingerprint,
            ): True,
        },
        clicked={state_key(prefix, "bibtex_preview_button")},
    )
    confirmed = render_bibtex_input(
        confirmed_ui,
        PossibleDuplicateService(),
        key_prefix=prefix,
    )

    assert blocked.ready is False
    assert blocked.drafts[0].allow_duplicate is False
    with pytest.raises(ValueError, match="requires a duplicate decision"):
        selected_bibtex_references(blocked)
    assert confirmed.ready is True
    assert confirmed.drafts[0].allow_duplicate is True


def test_bibtex_preview_errors_redact_mongodb_uri_and_credentials() -> None:
    class FailingService(PreviewOnlyService):
        def preview_bibtex(self, content, *, from_file=False):
            raise RuntimeError(
                "failed mongodb://alice:secret@example.test/catalog password=hunter2"
            )

    prefix = "redact"
    ui = FakeUI(
        values={
            state_key(prefix, "bibtex_mode"): "Paste BibTeX",
            state_key(prefix, "bibtex_paste"): "@misc{x, title={X}}",
        },
        clicked={state_key(prefix, "bibtex_preview_button")},
    )

    selection = render_bibtex_input(ui, FailingService(), key_prefix=prefix)

    rendered = " ".join([*ui.errors, *selection.errors]).casefold()
    assert "mongodb://" not in rendered
    assert "alice" not in rendered
    assert "secret" not in rendered
    assert "hunter2" not in rendered
    assert "<redacted" in rendered


def test_parse_accessed_at_accepts_date_and_normalizes_offsets() -> None:
    assert parse_accessed_at("2026-07-12").tzinfo == timezone.utc
    shifted = parse_accessed_at("2026-07-11T23:00:00-06:00")
    assert shifted.isoformat() == "2026-07-12T05:00:00+00:00"


def test_selected_bibtex_references_rejects_invalid_selected_draft() -> None:
    selection = BibTeXSelection()
    assert selected_bibtex_references(selection) == ()

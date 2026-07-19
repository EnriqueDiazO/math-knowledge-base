"""UI and state contract for Add Concept bibliography imports."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import ast
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

import pytest

import editor.concept_reference_form as reference_form

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "editor" / "editor_streamlit.py"
FORM = ROOT / "editor" / "concept_reference_form.py"
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "bibliography"
    / "muskhelishvili_minimal.bib"
)


class RerunRequestedError(RuntimeError):
    pass


class _Context(AbstractContextManager):
    def __init__(self, ui: FakeUI) -> None:
        self.ui = ui

    def __enter__(self) -> FakeUI:
        return self.ui

    def __exit__(self, *_args: object) -> None:
        return None


class FakeUploadedFile:
    name = "ref.bib"

    def __init__(self, value: bytes) -> None:
        self._value = value
        self.size = len(value)
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._value) - self._position
        start = self._position
        self._position = min(len(self._value), self._position + size)
        return self._value[start : self._position]

    def tell(self) -> int:
        return self._position

    def seek(self, position: int) -> None:
        self._position = position


class FakeUI:
    def __init__(
        self,
        *,
        state: dict[str, Any] | None = None,
        values: dict[str, Any] | None = None,
        clicked: set[str] | None = None,
        uploaded: FakeUploadedFile | None = None,
    ) -> None:
        self.session_state = state if state is not None else {}
        self.values = values or {}
        self.clicked = clicked or set()
        self.uploaded = uploaded
        self.labels: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.successes: list[str] = []
        self.infos: list[str] = []
        self.previews: list[Any] = []
        self.widget_keys: list[str] = []
        self.write_calls = 0

    def _value(self, key: str, default: Any) -> Any:
        self.widget_keys.append(key)
        if key in self.values:
            self.session_state[key] = self.values[key]
        elif key not in self.session_state:
            self.session_state[key] = default
        return self.session_state[key]

    def expander(self, label: str, **_kwargs: Any) -> _Context:
        self.labels.append(label)
        return _Context(self)

    def columns(self, count: int) -> tuple[_Context, ...]:
        return tuple(_Context(self) for _ in range(count))

    def markdown(self, value: str, **_kwargs: Any) -> None:
        self.labels.append(value)

    def caption(self, value: str) -> None:
        self.labels.append(value)

    def write(self, value: Any) -> None:
        self.previews.append(value)

    def json(self, value: Any) -> None:
        self.previews.append(value)

    def error(self, value: str) -> None:
        self.errors.append(value)

    def warning(self, value: str) -> None:
        self.warnings.append(value)

    def success(self, value: str) -> None:
        self.successes.append(value)

    def info(self, value: str) -> None:
        self.infos.append(value)

    def button(self, label: str, *, key: str, **_kwargs: Any) -> bool:
        self.labels.append(label)
        self.widget_keys.append(key)
        return key in self.clicked

    def file_uploader(self, label: str, *, key: str, **_kwargs: Any) -> Any:
        self.labels.append(label)
        self.widget_keys.append(key)
        return self.uploaded

    def selectbox(
        self,
        label: str,
        options: list[Any] | tuple[Any, ...],
        *,
        key: str,
        index: int | None = 0,
        **_kwargs: Any,
    ) -> Any:
        self.labels.append(label)
        default = None if index is None else options[index]
        return self._value(key, default)

    def text_input(
        self,
        label: str,
        *,
        key: str,
        value: str = "",
        **_kwargs: Any,
    ) -> str:
        self.labels.append(label)
        return self._value(key, value)

    def text_area(
        self,
        label: str,
        *,
        key: str,
        value: str = "",
        **_kwargs: Any,
    ) -> str:
        self.labels.append(label)
        return self._value(key, value)

    def number_input(
        self,
        label: str,
        *,
        key: str,
        value: int | None = None,
        **_kwargs: Any,
    ) -> int | None:
        self.labels.append(label)
        return self._value(key, value)

    def rerun(self) -> None:
        raise RerunRequestedError


def _render(ui: FakeUI, *, database: str = "db-a", source: str = "src-a", concept: str = "c-a"):
    return reference_form.render_concept_reference_form(
        ui,
        database_scope=database,
        source_id=source,
        concept_id=concept,
    )


def _complete_rerun(ui: FakeUI):
    ui.clicked.clear()
    return _render(ui)


def _manual_reference() -> dict[str, Any]:
    return {
        "tipo_referencia": "libro",
        "autor": "Manual Author",
        "fuente": "Manual Title",
        "anio": 2001,
        "tomo": None,
        "edicion": None,
        "paginas": None,
        "capitulo": None,
        "seccion": None,
        "editorial": None,
        "doi": None,
        "url": None,
        "issbn": None,
        "citekey": "Manual2001",
    }


def test_file_fixture_button_populates_one_editable_form_without_writing() -> None:
    ui = FakeUI(
        clicked={reference_form.state_key("use_file_entry")},
        uploaded=FakeUploadedFile(FIXTURE.read_bytes()),
    )

    with pytest.raises(RerunRequestedError):
        _render(ui)
    draft = _complete_rerun(ui)

    assert draft == {
        "tipo_referencia": "libro",
        "autor": "N.I. Muskhelishvili",
        "fuente": "Singular Integral Equations",
        "anio": 1946,
        "tomo": None,
        "edicion": None,
        "paginas": None,
        "capitulo": None,
        "seccion": None,
        "editorial": None,
        "doi": None,
        "url": None,
        "issbn": None,
        "citekey": "Muskhelishvili1946",
    }
    assert ui.write_calls == 0
    assert any("Revisa los campos antes de guardar" in item for item in ui.successes)


def test_file_with_multiple_entries_requires_and_honors_explicit_selection() -> None:
    raw = b"@book{one,title={One}}\n@article{two,title={Two}}"
    ui = FakeUI(
        values={reference_form.state_key("file_entry"): 2},
        clicked={reference_form.state_key("use_file_entry")},
        uploaded=FakeUploadedFile(raw),
    )

    with pytest.raises(RerunRequestedError):
        _render(ui)
    draft = _complete_rerun(ui)

    assert draft["tipo_referencia"] == "articulo"
    assert draft["fuente"] == "Two"
    assert draft["citekey"] == "two"


def test_paste_single_bibtex_analyzes_and_populates_without_save() -> None:
    paste_key = reference_form.state_key("paste")
    ui = FakeUI(
        values={paste_key: FIXTURE.read_text(encoding="utf-8")},
        clicked={reference_form.state_key("analyze_paste")},
    )

    with pytest.raises(RerunRequestedError):
        _render(ui)
    draft = _complete_rerun(ui)

    assert draft["citekey"] == "Muskhelishvili1946"
    assert draft["fuente"] == "Singular Integral Equations"
    assert ui.session_state[paste_key].startswith("@book")
    assert ui.write_calls == 0


def test_multiple_pasted_entries_are_not_applied_until_use_button() -> None:
    paste_key = reference_form.state_key("paste")
    raw = "@book{one,title={One}}\n@article{two,title={Two}}"
    ui = FakeUI(
        values={
            paste_key: raw,
            reference_form.state_key("paste_entry"): 2,
        },
        clicked={reference_form.state_key("analyze_paste")},
    )

    first = _render(ui)

    assert first["fuente"] is None
    assert "Selecciona entrada pegada" in ui.labels
    ui.clicked = {reference_form.state_key("use_paste_entry")}
    with pytest.raises(RerunRequestedError):
        _render(ui)
    final = _complete_rerun(ui)
    assert final["fuente"] == "Two"


def test_failed_paste_preserves_text_manual_fields_and_manual_citekey() -> None:
    state: dict[str, Any] = {}
    reference_form.sync_reference_scope(
        state,
        database_scope="db-a",
        source_id="src-a",
        concept_id="c-a",
    )
    reference_form.apply_reference_to_state(state, _manual_reference())
    paste_key = reference_form.state_key("paste")
    ui = FakeUI(
        state=state,
        values={paste_key: "Ordinary citation text that Add Source cannot parse"},
        clicked={reference_form.state_key("analyze_paste")},
    )

    draft = _render(ui)

    assert draft["autor"] == "Manual Author"
    assert draft["fuente"] == "Manual Title"
    assert draft["citekey"] == "Manual2001"
    assert ui.session_state[paste_key].startswith("Ordinary citation")
    assert any("No se pudo analizar" in item for item in ui.errors)


def test_invalid_bib_file_reports_decode_error_without_changing_manual_fields() -> None:
    state: dict[str, Any] = {}
    reference_form.sync_reference_scope(
        state,
        database_scope="db-a",
        source_id="src-a",
        concept_id="c-a",
    )
    reference_form.apply_reference_to_state(state, _manual_reference())
    ui = FakeUI(state=state, uploaded=FakeUploadedFile(b"\xff\xfe\xfa"))

    draft = _render(ui)

    assert draft["fuente"] == "Manual Title"
    assert draft["citekey"] == "Manual2001"
    assert any("decode_error" in item for item in ui.errors)
    assert any("No se pudo leer el .bib" in item for item in ui.errors)


def test_unknown_type_preview_uses_fallback_and_shows_normalizer_warning() -> None:
    ui = FakeUI(
        values={
            reference_form.state_key("paste"): "@techreport{r,title={Report}}"
        },
        clicked={reference_form.state_key("analyze_paste")},
    )

    with pytest.raises(RerunRequestedError):
        _render(ui)
    draft = _complete_rerun(ui)

    assert draft["tipo_referencia"] == "miscelanea"
    assert any("techreport" in item for item in ui.warnings)
    assert any(
        isinstance(preview, dict) and preview.get("fuente") == "Report"
        for preview in ui.previews
    )


def test_imported_result_remains_manually_editable() -> None:
    ui = FakeUI(
        clicked={reference_form.state_key("use_file_entry")},
        uploaded=FakeUploadedFile(FIXTURE.read_bytes()),
    )
    with pytest.raises(RerunRequestedError):
        _render(ui)
    ui.clicked.clear()
    ui.values[reference_form.state_key("autor")] = "Edited Author"
    ui.values[reference_form.state_key("citekey")] = "Edited1946"

    draft = _render(ui)

    assert draft["autor"] == "Edited Author"
    assert draft["citekey"] == "Edited1946"


def test_clear_is_explicit_and_removes_form_and_paste_but_keeps_scope() -> None:
    state: dict[str, Any] = {}
    reference_form.sync_reference_scope(
        state,
        database_scope="db-a",
        source_id="src-a",
        concept_id="c-a",
    )
    reference_form.apply_reference_to_state(state, _manual_reference())
    state[reference_form.state_key("paste")] = "@book{x,title={X}}"
    scope = state[reference_form.state_key("scope")]
    ui = FakeUI(
        state=state,
        clicked={reference_form.state_key("clear")},
    )

    with pytest.raises(RerunRequestedError):
        _render(ui)
    draft = _complete_rerun(ui)

    assert draft["autor"] is None
    assert draft["citekey"] is None
    assert ui.session_state[reference_form.state_key("paste")] == ""
    assert ui.session_state[reference_form.state_key("scope")] == scope


@pytest.mark.parametrize(
    ("changed", "value"),
    (("database_scope", "db-b"), ("source_id", "src-b"), ("concept_id", "c-b")),
)
def test_database_source_or_concept_change_clears_reference_state(
    changed: str,
    value: str,
) -> None:
    state: dict[str, Any] = {}
    reference_form.sync_reference_scope(
        state,
        database_scope="db-a",
        source_id="src-a",
        concept_id="c-a",
    )
    reference_form.apply_reference_to_state(state, _manual_reference())
    identity = {
        "database_scope": "db-a",
        "source_id": "src-a",
        "concept_id": "c-a",
    }
    identity[changed] = value

    changed_scope = reference_form.sync_reference_scope(state, **identity)

    assert changed_scope is True
    assert reference_form.reference_from_state(state)["citekey"] is None
    assert reference_form.reference_from_state(state)["fuente"] is None


def test_same_scope_keeps_manual_reference() -> None:
    state: dict[str, Any] = {}
    reference_form.sync_reference_scope(
        state,
        database_scope="db-a",
        source_id="src-a",
        concept_id="c-a",
    )
    reference_form.apply_reference_to_state(state, _manual_reference())

    changed = reference_form.sync_reference_scope(
        state,
        database_scope="db-a",
        source_id="src-a",
        concept_id="c-a",
    )

    assert changed is False
    assert reference_form.reference_from_state(state)["citekey"] == "Manual2001"


def test_apply_is_atomic_when_reference_type_is_invalid() -> None:
    state: dict[str, Any] = {"unrelated": "keep"}
    invalid = {**_manual_reference(), "tipo_referencia": "invented"}

    with pytest.raises(ValueError, match="Reference type"):
        reference_form.apply_reference_to_state(state, invalid)

    assert state == {"unrelated": "keep"}


def test_reference_content_detection_ignores_default_type_but_accepts_citekey() -> None:
    empty = {key: None for key in _manual_reference()}
    empty["tipo_referencia"] = "libro"

    assert reference_form.concept_reference_has_content(empty) is False
    assert reference_form.concept_reference_has_content(
        {**empty, "citekey": "OnlyKey"}
    ) is True


def test_every_widget_key_is_namespaced_and_required_labels_are_visible() -> None:
    ui = FakeUI()

    _render(ui)

    assert ui.widget_keys
    assert all(key.startswith("add_concept_reference_") for key in ui.widget_keys)
    rendered = " ".join(ui.labels)
    for label in (
        "Add / Edit Reference",
        "Importar .bib",
        "Pegar referencia o entrada BibTeX",
        "Editar manualmente",
        "Reference Type",
        "Author",
        "Source/Title",
        "Citekey",
    ):
        assert label in rendered


def test_form_uses_shared_add_source_parser_without_database_service(monkeypatch) -> None:
    calls: list[str] = []
    actual = reference_form.parse_bibtex_paste

    def tracking_parser(content: str):
        calls.append(content)
        return actual(content)

    monkeypatch.setattr(reference_form, "parse_bibtex_paste", tracking_parser)
    ui = FakeUI(
        values={reference_form.state_key("paste"): "@book{x,title={X}}"},
        clicked={reference_form.state_key("analyze_paste")},
    )

    with pytest.raises(RerunRequestedError):
        _render(ui)

    assert calls == ["@book{x,title={X}}"]


def test_form_module_has_no_mongodb_write_or_managed_source_mutation_path() -> None:
    source = FORM.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FORM))

    assert "insert_one(" not in source
    assert "update_one(" not in source
    assert "delete_one(" not in source
    assert "create_source(" not in source
    assert "source_repository" not in source
    assert all(
        not (isinstance(node, ast.ImportFrom) and "repository" in (node.module or ""))
        for node in ast.walk(tree)
    )


def test_add_concept_uses_component_and_persists_the_confirmed_reference_contract() -> None:
    source = APP.read_text(encoding="utf-8")
    start = source.index('elif page == "➕ Add Concept":')
    end = source.index('\nelif page == "✏️ Edit Concept":', start)
    branch = source[start:end]

    assert "render_concept_reference_form(" in branch
    assert "concept_reference_has_content(reference_data)" in branch
    assert 'concept_data["referencia"] = reference_data' in branch
    assert '"citekey": ref_citekey if ref_citekey else None' in branch
    assert 'ref_dict["tipo_referencia"]' not in branch
    assert "_parse_bibtex(" not in branch


def test_add_concept_import_does_not_change_managed_source_contract() -> None:
    source = APP.read_text(encoding="utf-8")
    start = source.index('elif page == "➕ Add Concept":')
    end = source.index('\nelif page == "✏️ Edit Concept":', start)
    branch = source[start:end]

    assert '"source": source' in branch
    assert '"source_id": source_id' in branch
    assert "catalog_context.source_repository" in branch
    assert "source_repository.insert(" not in branch
    assert "source_repository.update(" not in branch

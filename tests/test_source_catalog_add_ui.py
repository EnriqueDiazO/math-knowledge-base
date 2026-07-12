"""Focused pure/fake tests for the S1B Add Source form and decisions."""

# ruff: noqa: D101,D102,D103

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from editor.source_catalog.reference_actions import render_reference_save_plan
from editor.source_catalog.reference_form import build_reference_from_form
from editor.source_catalog.source_form import build_source_from_form
from editor.source_catalog.source_form import render_source_form
from editor.source_catalog.state import SESSION_PREFIX
from editor.source_catalog.workflows import allow_source_creation
from editor.source_catalog.workflows import duplicate_confirmation_required
from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.models import CopyrightStatus
from mathmongo.source_catalog.models import RedistributionPolicy
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.models import SourceType


class _SourceFormUI:
    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        self.overrides = overrides or {}
        self.widget_keys: list[str] = []
        self.captions: list[str] = []

    def _value(self, label: str, default: Any) -> Any:
        return self.overrides.get(label, default)

    def caption(self, value: object) -> None:
        self.captions.append(str(value))

    def markdown(self, _value: object) -> None:
        return None

    def text_input(
        self,
        label: str,
        *,
        value: Any,
        key: str,
        **_kwargs: Any,
    ) -> Any:
        self.widget_keys.append(key)
        return self._value(label, value)

    def text_area(
        self,
        label: str,
        *,
        value: Any,
        key: str,
        **_kwargs: Any,
    ) -> Any:
        self.widget_keys.append(key)
        return self._value(label, value)

    def selectbox(
        self,
        label: str,
        options: list[str],
        *,
        index: int,
        key: str,
    ) -> Any:
        self.widget_keys.append(key)
        return self._value(label, options[index])


class _ReferencePlanUI:
    def __init__(self) -> None:
        self.widget_keys: list[str] = []
        self.selected_index: int | None = None
        self.checkbox_count = 0

    def selectbox(
        self,
        _label: str,
        options: list[str],
        *,
        index: int,
        format_func: Any,
        key: str,
    ) -> str:
        del format_func
        self.widget_keys.append(key)
        self.selected_index = index
        return options[index]

    def checkbox(self, _label: str, *, key: str) -> bool:
        self.widget_keys.append(key)
        self.checkbox_count += 1
        return False


def _match(classification: DuplicateClassification, entity_id: str) -> DuplicateMatch:
    return DuplicateMatch(entity_id=entity_id, classification=classification)


def test_minimal_source_form_builds_an_unsaved_active_source() -> None:
    source = build_source_from_form({"name": "Minimal Source"})

    assert source.name == "Minimal Source"
    assert source.source_id.startswith("src_")
    assert source.source_type == SourceType.OTHER
    assert source.status == SourceStatus.ACTIVE
    assert source.aliases == []
    assert source.tags == []


def test_empty_source_name_is_rejected_before_any_workflow() -> None:
    with pytest.raises(ValidationError, match="name cannot be empty"):
        build_source_from_form({"name": "  \n  "})


def test_aliases_tags_and_rights_are_delegated_to_the_domain_model() -> None:
    source = build_source_from_form(
        {
            "name": "Catalog Source",
            "description": "  A   display description ",
            "source_type": "book",
            "language": " es ",
            "aliases_text": "Primary Alias, primary alias\nHistorical Alias",
            "tags_text": "analysis, Analysis\noperator theory",
            "copyright_status": "licensed",
            "redistribution": "include",
            "license": " CC-BY-4.0 ",
            "rights_notes": " Preserve attribution ",
        }
    )

    assert source.source_type == SourceType.BOOK
    assert source.description == "A display description"
    assert source.language == "es"
    assert [alias.value for alias in source.aliases] == [
        "Primary Alias",
        "Historical Alias",
    ]
    assert source.tags == ["analysis", "operator theory"]
    assert source.rights_default.copyright_status == CopyrightStatus.LICENSED
    assert source.rights_default.redistribution == RedistributionPolicy.INCLUDE
    assert source.rights_default.license == "CC-BY-4.0"
    assert source.rights_default.notes == "Preserve attribution"


def test_edit_builder_preserves_source_id_and_ignores_an_injected_id_field() -> None:
    original = build_source_from_form({"name": "Before"})
    injected_id = build_source_from_form({"name": "Unrelated"}).source_id

    edited = build_source_from_form(
        {
            "source_id": injected_id,
            "name": "After",
            "source_type": "article",
        },
        initial=original,
    )

    assert edited.source_id == original.source_id
    assert edited.source_id != injected_id
    assert edited.created_at == original.created_at
    assert edited.name == "After"
    assert edited.source_type == SourceType.ARTICLE


def test_exact_duplicate_requires_confirmation_but_weak_only_does_not() -> None:
    exact = [_match(DuplicateClassification.EXACT, "src_exact")]
    weak = [_match(DuplicateClassification.WEAK, "src_weak")]

    assert duplicate_confirmation_required(exact) is True
    assert allow_source_creation(exact, confirmed=False) is False
    assert allow_source_creation(exact, confirmed=True) is True
    assert duplicate_confirmation_required(weak) is False
    assert allow_source_creation(weak, confirmed=False) is True


def test_reference_plan_prefers_existing_for_exact_and_new_for_weak() -> None:
    reference = build_reference_from_form({"doi": "10.1000/example"})
    exact_ui = _ReferencePlanUI()
    weak_ui = _ReferencePlanUI()

    exact_plan, exact_ready = render_reference_save_plan(
        exact_ui,
        key_prefix="add_exact",
        label="exact Reference",
        reference=reference,
        duplicates=(_match(DuplicateClassification.EXACT, "ref_existing"),),
    )
    weak_plan, weak_ready = render_reference_save_plan(
        weak_ui,
        key_prefix="add_weak",
        label="weak Reference",
        reference=reference,
        duplicates=(_match(DuplicateClassification.WEAK, "ref_suggestion"),),
    )

    assert exact_ready is True
    assert exact_plan is not None
    assert exact_plan.existing_reference_id == "ref_existing"
    assert exact_ui.selected_index == 1
    assert exact_ui.checkbox_count == 0
    assert weak_ready is True
    assert weak_plan is not None
    assert weak_plan.candidate == reference
    assert weak_plan.allow_duplicate is True
    assert weak_ui.selected_index == 0
    assert weak_ui.checkbox_count == 0
    assert all(
        key.startswith(SESSION_PREFIX) for key in [*exact_ui.widget_keys, *weak_ui.widget_keys]
    )


def test_manual_reference_can_be_valid_with_doi_as_its_only_identity() -> None:
    reference = build_reference_from_form(
        {
            "reference_type": "article",
            "doi": " HTTPS://doi.org/10.1000/Only.Identity ",
        }
    )

    assert reference.title is None
    assert reference.authors == []
    assert reference.isbn == []
    assert reference.doi == "HTTPS://doi.org/10.1000/Only.Identity"
    assert reference.doi_normalized == "10.1000/only.identity"


def test_render_source_form_uses_only_namespaced_keys_and_no_editable_id() -> None:
    ui = _SourceFormUI({"Name *": "Rendered Minimal"})

    draft = render_source_form(ui, key_prefix="add_source")

    assert draft.valid is True
    assert draft.source is not None
    assert draft.source.name == "Rendered Minimal"
    assert ui.widget_keys
    assert all(key.startswith(SESSION_PREFIX) for key in ui.widget_keys)
    assert all("source_id" not in key for key in ui.widget_keys)
    assert any("not editable" in caption for caption in ui.captions)

"""Focused S1B tests for edit/analyze safety and bounded diagnostics."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

from editor.source_catalog import data_quality
from editor.source_catalog import edit_source_page
from editor.source_catalog.edit_source_page import _association_rows
from editor.source_catalog.edit_source_page import _execute_write_once
from editor.source_catalog.edit_source_page import _reference_plan_digest
from editor.source_catalog.legacy_concepts import legacy_table_rows
from editor.source_catalog.workflows import ReferenceSavePlan
from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateEvidence
from mathmongo.source_catalog.duplicates import DuplicateEvidenceType
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import PageResult
from mathmongo.source_catalog.service import CatalogResult
from mathmongo.source_catalog.service import CatalogResultStatus
from mathmongo.source_catalog.service import DeletionInspection


class _MessageUI:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}
        self.messages: list[tuple[str, str]] = []

    def _record(self, level: str, value: object) -> None:
        self.messages.append((level, str(value)))

    def info(self, value: object) -> None:
        self._record("info", value)

    def success(self, value: object) -> None:
        self._record("success", value)

    def warning(self, value: object) -> None:
        self._record("warning", value)

    def error(self, value: object) -> None:
        self._record("error", value)


class _ActionUI(_MessageUI):
    def __init__(
        self,
        *,
        submitted: set[str] | None = None,
        clicked: set[str] | None = None,
        typed_text: str = "",
        confirmed: bool = True,
        checkbox_values: dict[str, bool] | None = None,
        radio_value: str = "Manual",
    ) -> None:
        super().__init__()
        self.submitted = submitted or set()
        self.clicked = clicked or set()
        self.typed_text = typed_text
        self.confirmed = confirmed
        self.checkbox_values = checkbox_values or {}
        self.radio_value = radio_value
        self.checkbox_labels: list[str] = []
        self.submit_disabled: dict[str, bool] = {}

    def subheader(self, value: object) -> None:
        self._record("subheader", value)

    def write(self, value: object) -> None:
        self._record("write", value)

    def form(self, **_kwargs: Any):
        return nullcontext(self)

    def checkbox(self, label: str, **_kwargs: Any) -> bool:
        self.checkbox_labels.append(label)
        return self.checkbox_values.get(label, self.confirmed)

    def radio(self, _label: str, _options: Any, **_kwargs: Any) -> str:
        return self.radio_value

    def form_submit_button(self, label: str, *, disabled: bool = False) -> bool:
        self.submit_disabled[label] = disabled
        return label in self.submitted and not disabled

    def button(self, label: str, **_kwargs: Any) -> bool:
        return label in self.clicked

    def text_input(self, _label: str, **_kwargs: Any) -> str:
        return self.typed_text


class _SearchUI(_MessageUI):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []

    def subheader(self, value: object) -> None:
        self._record("subheader", value)

    def columns(self, count: int):
        return [nullcontext(self) for _ in range(count)]

    def text_input(self, label: str, **_kwargs: Any) -> str:
        return "operator" if label == "Tag" else ""

    def selectbox(self, label: str, _options, **_kwargs: Any) -> str:
        return "archived" if label == "Status" else "book"

    def number_input(self, _label: str, **_kwargs: Any) -> int:
        return 3

    def caption(self, value: object) -> None:
        self._record("caption", value)

    def dataframe(self, rows, **_kwargs: Any) -> None:
        self.rows = list(rows)

    def button(self, _label: str, **_kwargs: Any) -> bool:
        return False


def test_execute_write_once_blocks_rerun_and_sanitizes_failures() -> None:
    ui = _MessageUI()
    calls = 0

    def action() -> CatalogResult[bool]:
        nonlocal calls
        calls += 1
        return CatalogResult(CatalogResultStatus.SUCCESS, value=True, persisted=True)

    first = _execute_write_once(
        ui,
        operation="archive_source_id",
        token="db:archive:id:v1",
        action=action,
        success="archived",
    )
    second = _execute_write_once(
        ui,
        operation="archive_source_id",
        token="db:archive:id:v1",
        action=action,
        success="archived",
    )

    assert first is not None and first.persisted
    assert second is None
    assert calls == 1

    def unsafe_failure() -> None:
        raise RuntimeError("mongodb://alice:secret@localhost/catalog password=hunter2")

    _execute_write_once(
        ui,
        operation="unsafe",
        token="unsafe-token",
        action=unsafe_failure,
        success="never",
    )
    rendered = " ".join(message for _level, message in ui.messages)
    assert "alice" not in rendered
    assert "secret" not in rendered
    assert "hunter2" not in rendered
    assert "<redacted MongoDB URI>" in rendered


def test_reference_batch_digest_is_stable_and_never_contains_raw() -> None:
    raw = "@article{stable, title={Private raw body}}"
    first = Reference(title="Stable", bibtex={"key": "stable", "raw": raw})
    second = Reference(title="Stable", bibtex={"key": "stable", "raw": raw})
    changed = Reference(
        title="Stable",
        bibtex={"key": "stable", "raw": raw.replace("Private", "Changed")},
    )

    first_digest = _reference_plan_digest(
        "src_target",
        [ReferenceSavePlan(label="entry", candidate=first)],
    )
    second_digest = _reference_plan_digest(
        "src_target",
        [ReferenceSavePlan(label="entry", candidate=second)],
    )
    changed_digest = _reference_plan_digest(
        "src_target",
        [ReferenceSavePlan(label="entry", candidate=changed)],
    )

    assert first.reference_id != second.reference_id
    assert first_digest == second_digest
    assert changed_digest != first_digest
    assert len(first_digest) == 64
    assert "Private raw body" not in first_digest


def test_shared_reference_rows_show_every_association_and_missing_source() -> None:
    first = Source(name="First")
    second = Source(name="Second").archived()
    reference = Reference(
        title="Shared",
        source_ids=[first.source_id, second.source_id, Source(name="Missing").source_id],
    )
    records = {first.source_id: first, second.source_id: second}
    requested: list[tuple[str, ...]] = []

    def get_by_ids(source_ids):
        requested.append(tuple(source_ids))
        return tuple(records[source_id] for source_id in source_ids if source_id in records)

    context = SimpleNamespace(source_repository=SimpleNamespace(get_by_ids=get_by_ids))

    rows = _association_rows(context, reference)

    assert [row["source_id"] for row in rows] == reference.source_ids
    assert rows[0] == {
        "source_id": first.source_id,
        "name": "First",
        "status": "active",
    }
    assert rows[1]["status"] == "archived"
    assert rows[2]["name"] == "<missing Source>"
    assert requested == [tuple(reference.source_ids)]


def test_uninitialized_page_propagates_read_only_guard(monkeypatch) -> None:
    source = Source(name="Read only")
    captured: list[bool] = []
    ui = _MessageUI()
    ui.title = lambda _value: None
    ui.divider = lambda: None
    ui.selectbox = lambda *_args, **_kwargs: "Overview & Edit"
    context = SimpleNamespace()

    monkeypatch.setattr(edit_source_page, "render_active_database", lambda *_args: None)
    monkeypatch.setattr(
        edit_source_page,
        "render_catalog_status",
        lambda *_args: SimpleNamespace(initialized=False),
    )
    monkeypatch.setattr(edit_source_page, "_render_source_search", lambda *_args: source)
    monkeypatch.setattr(edit_source_page, "_render_overview_header", lambda *_args: None)
    monkeypatch.setattr(
        edit_source_page,
        "_render_source_editor",
        lambda *_args, writes_enabled: captured.append(writes_enabled),
    )

    edit_source_page.render_edit_source_page(context, ui=ui)

    assert captured == [False]
    assert any("writes are disabled" in message for _level, message in ui.messages)


def test_source_editor_cannot_reach_service_when_writes_disabled(monkeypatch) -> None:
    source = Source(name="Protected")
    service = SimpleNamespace(
        detect_source_duplicates=lambda *_args, **_kwargs: [],
        update_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("write must remain unreachable")
        ),
    )
    context = SimpleNamespace(service=service)
    ui = _MessageUI()
    ui.form = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("write form must not render")
    )
    monkeypatch.setattr(
        edit_source_page,
        "render_source_form",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=True,
            source=source,
            errors=(),
        ),
    )
    monkeypatch.setattr(edit_source_page, "render_duplicate_preview", lambda *_args: None)

    edit_source_page._render_source_editor(
        ui,
        context,
        source,
        writes_enabled=False,
    )

    assert any("Read-only" in message for _level, message in ui.messages)


def test_source_search_is_server_paged_and_keeps_archived_sources_visible() -> None:
    archived = Source(name="Archived", source_type="book").archived()
    calls: list[dict[str, Any]] = []

    def list_sources(**kwargs: Any) -> PageResult[Source]:
        calls.append(kwargs)
        return PageResult((archived,), page=3, page_size=20, total=41)

    repository = SimpleNamespace(
        list=list_sources,
        search=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("empty search must use list")
        ),
        get_by_id=lambda _source_id: None,
    )
    ui = _SearchUI()

    selected = edit_source_page._render_source_search(
        ui,
        SimpleNamespace(source_repository=repository),
    )

    assert selected is None
    assert calls == [
        {
            "page": 3,
            "page_size": 20,
            "status": "archived",
            "source_type": "book",
            "tag": "operator",
        }
    ]
    assert ui.rows[0]["source_id"] == archived.source_id
    assert ui.rows[0]["status"] == "archived"
    assert any("41 Sources · page 3" in message for _level, message in ui.messages)


def test_source_rename_keeps_id_and_wires_optional_previous_alias(monkeypatch) -> None:
    source = Source(name="Before")
    candidate = source.renamed("After")
    calls: list[tuple[str, dict[str, Any], bool, bool]] = []

    def update_source(
        source_id: str,
        changes: dict[str, Any],
        *,
        preserve_previous_name_as_alias: bool,
        allow_duplicate: bool,
    ) -> CatalogResult[Source]:
        calls.append(
            (
                source_id,
                changes,
                preserve_previous_name_as_alias,
                allow_duplicate,
            )
        )
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=candidate,
            persisted=True,
        )

    service = SimpleNamespace(
        detect_source_duplicates=lambda *_args, **_kwargs: [],
        update_source=update_source,
    )
    context = SimpleNamespace(database_name="isolated_s1b", service=service)
    ui = _ActionUI(submitted={"Save Source changes"})
    monkeypatch.setattr(
        edit_source_page,
        "render_source_form",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=True,
            source=candidate,
            errors=(),
        ),
    )
    monkeypatch.setattr(edit_source_page, "render_duplicate_preview", lambda *_args: None)

    for _ in range(2):
        edit_source_page._render_source_editor(
            ui,
            context,
            source,
            writes_enabled=True,
        )

    assert len(calls) == 1
    source_id, changes, preserve_old, allow_duplicate = calls[0]
    assert source_id == source.source_id
    assert changes["name"] == "After"
    assert preserve_old is True
    assert allow_duplicate is False
    assert any("Preserve previous name as alias" in label for label in ui.checkbox_labels)


def test_source_update_submit_is_not_deadlocked_by_inner_confirmation(monkeypatch) -> None:
    source = Source(name="Unconfirmed")
    update_calls: list[str] = []
    context = SimpleNamespace(
        database_name="isolated_s1b",
        service=SimpleNamespace(
            detect_source_duplicates=lambda *_args, **_kwargs: [],
            update_source=lambda source_id, *_args, **_kwargs: update_calls.append(source_id),
        ),
    )
    ui = _ActionUI(submitted={"Save Source changes"}, confirmed=False)
    monkeypatch.setattr(
        edit_source_page,
        "render_source_form",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=True,
            source=source,
            errors=(),
        ),
    )
    monkeypatch.setattr(edit_source_page, "render_duplicate_preview", lambda *_args: None)

    edit_source_page._render_source_editor(
        ui,
        context,
        source,
        writes_enabled=True,
    )

    assert ui.submit_disabled["Save Source changes"] is False
    assert update_calls == []
    assert any("Confirm the Source update" in message for _level, message in ui.messages)


def test_reference_update_submit_is_not_deadlocked_by_inner_confirmation(
    monkeypatch,
) -> None:
    source = Source(name="Owner")
    reference = Reference(title="Unconfirmed", source_ids=[source.source_id])
    update_calls: list[str] = []
    context = SimpleNamespace(
        database_name="isolated_s1b",
        source_repository=SimpleNamespace(get_by_ids=lambda _source_ids: (source,)),
        service=SimpleNamespace(
            detect_reference_duplicates=lambda *_args, **_kwargs: [],
            update_reference=lambda reference_id, *_args, **_kwargs: update_calls.append(
                reference_id
            ),
        ),
    )
    ui = _ActionUI(submitted={"Save Reference changes"}, confirmed=False)
    monkeypatch.setattr(
        edit_source_page,
        "render_reference_form",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=True,
            reference=reference,
            errors=(),
        ),
    )
    monkeypatch.setattr(edit_source_page, "render_duplicate_preview", lambda *_args: None)

    edit_source_page._render_reference_editor(
        ui,
        context,
        reference,
        writes_enabled=True,
    )

    assert ui.submit_disabled["Save Reference changes"] is False
    assert update_calls == []
    assert any("Confirm the Reference update" in message for _level, message in ui.messages)


def test_add_reference_uses_no_outer_expander_and_validates_confirmation_after_submit(
    monkeypatch,
) -> None:
    source = Source(name="Owner")
    reference = Reference(title="Draft", source_ids=[source.source_id])
    write_calls: list[str] = []
    context = SimpleNamespace(
        database_name="isolated_s1b",
        service=SimpleNamespace(
            detect_reference_duplicates=lambda *_args, **_kwargs: [],
        ),
    )
    confirmation_label = "Confirm 1 Reference action(s) in isolated_s1b"
    ui = _ActionUI(
        submitted={"Save selected Reference actions"},
        checkbox_values={
            "Show Add Reference controls": True,
            confirmation_label: False,
        },
    )
    monkeypatch.setattr(
        edit_source_page,
        "render_reference_form",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=True,
            reference=reference,
            errors=(),
        ),
    )
    monkeypatch.setattr(edit_source_page, "render_duplicate_preview", lambda *_args: None)
    monkeypatch.setattr(
        edit_source_page,
        "render_reference_save_plan",
        lambda *_args, **_kwargs: (
            ReferenceSavePlan(label="manual", candidate=reference),
            True,
        ),
    )
    monkeypatch.setattr(
        edit_source_page,
        "execute_reference_plans",
        lambda *_args, **_kwargs: write_calls.append("write"),
    )

    edit_source_page._render_add_reference(
        ui,
        context,
        source,
        writes_enabled=True,
    )

    assert ui.submit_disabled["Save selected Reference actions"] is False
    assert write_calls == []
    assert any("Confirm the Reference actions" in message for _level, message in ui.messages)


def test_shared_reference_archive_names_database_and_is_rerun_safe() -> None:
    source = Source(name="Selected")
    other = Source(name="Other")
    reference = Reference(
        title="Shared",
        source_ids=[source.source_id, other.source_id],
    )
    calls: list[str] = []

    def archive(reference_id: str) -> CatalogResult[Reference]:
        calls.append(reference_id)
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=reference.archived(),
            persisted=True,
        )

    context = SimpleNamespace(
        database_name="isolated_s1b",
        service=SimpleNamespace(archive_reference=archive),
    )
    ui = _ActionUI(submitted={"Archive Reference"})

    edit_source_page._render_reference_actions(
        ui,
        context,
        source,
        reference,
        writes_enabled=True,
    )
    edit_source_page._render_reference_actions(
        ui,
        context,
        source,
        reference,
        writes_enabled=True,
    )

    assert calls == [reference.reference_id]
    confirmation = " ".join(ui.checkbox_labels)
    assert "isolated_s1b" in confirmation
    assert "all 2 Source associations" in confirmation


def test_reference_archive_submit_is_enabled_but_unconfirmed_action_never_writes() -> None:
    source = Source(name="Selected")
    reference = Reference(title="Unconfirmed", source_ids=[source.source_id])
    archive_calls: list[str] = []
    context = SimpleNamespace(
        database_name="isolated_s1b",
        service=SimpleNamespace(
            archive_reference=lambda reference_id: archive_calls.append(reference_id),
        ),
    )
    ui = _ActionUI(submitted={"Archive Reference"}, confirmed=False)

    edit_source_page._render_reference_actions(
        ui,
        context,
        source,
        reference,
        writes_enabled=True,
    )

    assert ui.submit_disabled["Archive Reference"] is False
    assert archive_calls == []
    assert any("Confirm Reference archive" in message for _level, message in ui.messages)


def test_disassociate_exposes_detached_reference_for_guarded_delete() -> None:
    source = Source(name="Selected")
    reference = Reference(title="Only", source_ids=[source.source_id])
    detached = reference.disassociated_from(source.source_id)
    calls: list[tuple[str, str]] = []

    def disassociate(reference_id: str, source_id: str) -> CatalogResult[Reference]:
        calls.append((reference_id, source_id))
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=detached,
            persisted=True,
        )

    context = SimpleNamespace(
        database_name="isolated_s1b",
        service=SimpleNamespace(disassociate_reference=disassociate),
    )
    ui = _ActionUI(submitted={"Unlink from this Source"})

    edit_source_page._render_reference_actions(
        ui,
        context,
        source,
        reference,
        writes_enabled=True,
    )

    assert calls == [(reference.reference_id, source.source_id)]
    assert (
        ui.session_state[edit_source_page.state_key("detached_reference_id")]
        == reference.reference_id
    )
    assert "isolated_s1b" in " ".join(ui.checkbox_labels)


def test_detached_reference_delete_requires_service_approval_and_typed_id() -> None:
    reference = Reference(title="Detached")
    delete_calls: list[str] = []

    def delete(reference_id: str) -> CatalogResult[bool]:
        delete_calls.append(reference_id)
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=True,
            persisted=True,
        )

    context = SimpleNamespace(
        database_name="isolated_s1b",
        reference_repository=SimpleNamespace(get_by_id=lambda _reference_id: reference),
        service=SimpleNamespace(
            inspect_reference_deletion=lambda reference_id: DeletionInspection(
                entity_id=reference_id,
                exists=True,
                allowed=True,
            ),
            delete_reference_if_unused=delete,
        ),
    )
    ui = _ActionUI(
        submitted={"Physically delete unused Reference"},
        typed_text=reference.reference_id,
    )
    ui.session_state[edit_source_page.state_key("detached_reference_id")] = reference.reference_id

    edit_source_page._render_detached_reference(ui, context, writes_enabled=True)

    assert delete_calls == [reference.reference_id]
    assert edit_source_page.state_key("detached_reference_id") not in ui.session_state
    rendered = " ".join(message for _level, message in ui.messages)
    assert "isolated_s1b" in rendered
    assert reference.reference_id in rendered


def test_detached_reference_delete_validates_typed_id_after_enabled_submit() -> None:
    reference = Reference(title="Detached")
    delete_calls: list[str] = []
    context = SimpleNamespace(
        database_name="isolated_s1b",
        reference_repository=SimpleNamespace(get_by_id=lambda _reference_id: reference),
        service=SimpleNamespace(
            inspect_reference_deletion=lambda reference_id: DeletionInspection(
                entity_id=reference_id,
                exists=True,
                allowed=True,
            ),
            delete_reference_if_unused=lambda reference_id: delete_calls.append(reference_id),
        ),
    )
    ui = _ActionUI(
        submitted={"Physically delete unused Reference"},
        typed_text="wrong-reference-id",
    )
    ui.session_state[edit_source_page.state_key("detached_reference_id")] = reference.reference_id

    edit_source_page._render_detached_reference(ui, context, writes_enabled=True)

    assert ui.submit_disabled["Physically delete unused Reference"] is False
    assert delete_calls == []
    assert any("exact Reference ID" in message for _level, message in ui.messages)


def test_source_archive_and_reactivate_are_confirmed_and_rerun_safe() -> None:
    source = Source(name="Lifecycle")
    archived = source.archived()
    calls: list[tuple[str, str]] = []

    def archive(source_id: str) -> CatalogResult[Source]:
        calls.append(("archive", source_id))
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=archived,
            persisted=True,
        )

    def reactivate(source_id: str) -> CatalogResult[Source]:
        calls.append(("reactivate", source_id))
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=source,
            persisted=True,
        )

    context = SimpleNamespace(
        database_name="isolated_s1b",
        service=SimpleNamespace(
            archive_source=archive,
            reactivate_source=reactivate,
        ),
    )
    archive_ui = _ActionUI(submitted={"Archive Source"})
    reactivate_ui = _ActionUI(submitted={"Reactivate Source"})

    for _ in range(2):
        edit_source_page._render_source_actions(
            archive_ui,
            context,
            source,
            writes_enabled=True,
        )
        edit_source_page._render_source_actions(
            reactivate_ui,
            context,
            archived,
            writes_enabled=True,
        )

    assert calls == [
        ("archive", source.source_id),
        ("reactivate", source.source_id),
    ]
    assert "isolated_s1b" in " ".join(archive_ui.checkbox_labels)
    assert "isolated_s1b" in " ".join(reactivate_ui.checkbox_labels)


def test_source_archive_submit_is_enabled_but_unconfirmed_action_never_writes() -> None:
    source = Source(name="Unconfirmed")
    archive_calls: list[str] = []
    context = SimpleNamespace(
        database_name="isolated_s1b",
        service=SimpleNamespace(
            archive_source=lambda source_id: archive_calls.append(source_id),
        ),
    )
    ui = _ActionUI(submitted={"Archive Source"}, confirmed=False)

    edit_source_page._render_source_actions(
        ui,
        context,
        source,
        writes_enabled=True,
    )

    assert ui.submit_disabled["Archive Source"] is False
    assert archive_calls == []
    assert any("Confirm Source archive" in message for _level, message in ui.messages)


def test_source_physical_delete_stays_blocked_until_inspection_allows(
    monkeypatch,
) -> None:
    source = Source(name="Delete candidate")
    delete_calls: list[str] = []

    def delete(source_id: str) -> CatalogResult[bool]:
        delete_calls.append(source_id)
        return CatalogResult(
            CatalogResultStatus.SUCCESS,
            value=True,
            persisted=True,
        )

    service = SimpleNamespace(
        archive_source=lambda _source_id: None,
        inspect_source_deletion=lambda source_id: DeletionInspection(
            entity_id=source_id,
            exists=True,
            allowed=False,
            blockers=("references:1",),
        ),
        delete_source_if_unused=delete,
    )
    context = SimpleNamespace(database_name="isolated_s1b", service=service)
    blocked_ui = _ActionUI(
        submitted={"Physically delete unused Source"},
        clicked={"Inspect physical deletion"},
        typed_text=source.source_id,
    )
    monkeypatch.setattr(edit_source_page, "_overview_counts", lambda *_args: (1, 0))

    edit_source_page._render_source_actions(
        blocked_ui,
        context,
        source,
        writes_enabled=True,
    )

    assert delete_calls == []
    assert any("references:1" in message for _level, message in blocked_ui.messages)

    service.inspect_source_deletion = lambda source_id: DeletionInspection(
        entity_id=source_id,
        exists=True,
        allowed=True,
    )
    allowed_ui = _ActionUI(
        submitted={"Physically delete unused Source"},
        clicked={"Inspect physical deletion"},
        typed_text=source.source_id,
    )
    allowed_ui.session_state[edit_source_page.SELECTED_SOURCE_ID] = source.source_id

    edit_source_page._render_source_actions(
        allowed_ui,
        context,
        source,
        writes_enabled=True,
    )

    assert allowed_ui.submit_disabled["Physically delete unused Source"] is False
    assert delete_calls == [source.source_id]
    assert edit_source_page.SELECTED_SOURCE_ID not in allowed_ui.session_state


class _ReferenceRepository:
    def __init__(self, references: tuple[Reference, ...], total: int) -> None:
        self.references = references
        self.total = total

    def count(self, *, source_id: str) -> int:
        del source_id
        return self.total

    def list(self, **_kwargs) -> PageResult[Reference]:
        return PageResult(self.references, page=1, page_size=100, total=self.total)

    def list_quality_candidates(self, **_kwargs) -> PageResult[Reference]:
        return PageResult(self.references, page=1, page_size=100, total=self.total)


class _QualityService:
    def __init__(self, source_match: DuplicateMatch, reference_id: str) -> None:
        self.source_match = source_match
        self.reference_id = reference_id

    def detect_source_duplicates(self, _source, *, exclude_source_id: str):
        assert exclude_source_id
        return [self.source_match]

    def detect_reference_duplicates(self, reference, *, exclude_reference_id: str):
        assert exclude_reference_id == reference.reference_id
        if reference.reference_id != self.reference_id:
            return []
        return [
            DuplicateMatch(
                entity_id=Reference(title="Other").reference_id,
                classification=DuplicateClassification.STRONG,
                evidence=[
                    DuplicateEvidence(evidence_type=DuplicateEvidenceType.DOI),
                    DuplicateEvidence(evidence_type=DuplicateEvidenceType.ISBN),
                    DuplicateEvidence(evidence_type=DuplicateEvidenceType.BIBTEX_KEY),
                ],
            )
        ]


def test_data_quality_reports_required_source_local_indicators(monkeypatch) -> None:
    source = Source(
        name="Current",
        legacy={"source_strings": ["Historical"]},
    )
    incomplete = Reference(
        reference_type="article",
        title="Incomplete",
        source_ids=[source.source_id, Source(name="Other").source_id],
    )
    repeated = Reference(
        title="Repeated",
        doi="10.1000/repeated",
        isbn=["978-0-306-40615-7"],
        bibtex={"key": "RepeatedKey"},
        source_ids=[source.source_id],
    ).archived()
    source_match = DuplicateMatch(
        entity_id=Source(name="Candidate").source_id,
        classification=DuplicateClassification.POSSIBLE,
    )

    class _LegacyRepository:
        def __init__(self, _database) -> None:
            pass

        def count(self, selected_source: Source, *, has_reference=None) -> int:
            if has_reference is False:
                return 2
            if not selected_source.legacy.source_strings:
                return 3
            return 5

    monkeypatch.setattr(data_quality, "LegacyConceptRepository", _LegacyRepository)
    context = SimpleNamespace(
        database=object(),
        reference_repository=_ReferenceRepository((incomplete, repeated), total=101),
        service=_QualityService(source_match, repeated.reference_id),
    )

    summary = data_quality.inspect_source_quality(context, source)

    assert summary.reference_count == 101
    assert summary.source_duplicates == (source_match,)
    assert summary.incomplete_reference_ids == (incomplete.reference_id,)
    assert summary.repeated_doi_reference_ids == (repeated.reference_id,)
    assert summary.repeated_isbn_reference_ids == (repeated.reference_id,)
    assert summary.repeated_citekey_reference_ids == (repeated.reference_id,)
    assert summary.archived_associated_reference_ids == (repeated.reference_id,)
    assert summary.shared_reference_ids == (incomplete.reference_id,)
    assert summary.legacy_concept_count == 5
    assert summary.legacy_without_reference_count == 2
    assert summary.exact_name_not_declared_count == 3
    assert summary.reference_scan_truncated is True


def test_legacy_table_rows_expose_only_projected_read_only_fields() -> None:
    item = SimpleNamespace(
        id="concept-id",
        title="Title",
        type="teorema",
        categories=("A", "B"),
        has_reference=True,
        pages="10-12",
        chapter="3",
        section="2.1",
        updated_at=None,
        source="Exact Source",
    )
    page = SimpleNamespace(items=(item,))

    rows = legacy_table_rows(page)

    assert rows == [
        {
            "id": "concept-id",
            "title": "Title",
            "type": "teorema",
            "categories": "A, B",
            "reference": "yes",
            "pages": "10-12",
            "chapter": "3",
            "section": "2.1",
            "updated_at": None,
            "source": "Exact Source",
        }
    ]
    assert "latex" not in rows[0]

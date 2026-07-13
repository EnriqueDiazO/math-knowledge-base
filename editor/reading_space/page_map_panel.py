"""Streamlit controls for manual PDF-page to book-page labels."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from editor.reading_space.state import state_key
from editor.source_catalog.shared import safe_error_message
from mathmongo.document_page_maps.models import PageLabelStyle
from mathmongo.document_page_maps.models import compute_book_page_label
from mathmongo.document_page_maps.service import DocumentPageMapService

USER_SCOPE = "local"


def _ok(result: Any) -> bool:
    return bool(getattr(result, "completed", False))


def _render_result(ui: Any, result: Any, *, success: str) -> bool:
    if _ok(result):
        ui.success(success)
        return True
    message = safe_error_message(getattr(result, "message", "") or "Page Map action failed.")
    status = str(getattr(getattr(result, "status", None), "value", getattr(result, "status", "")))
    if status in {"not_found", "archived"}:
        ui.warning(message)
    else:
        ui.error(message)
    return False


def current_book_page(
    service: DocumentPageMapService,
    document_id: str,
    pdf_page: int,
) -> str | None:
    """Return one computed label for compact read-only display."""
    result = service.compute_page_label(document_id, pdf_page, user_scope=USER_SCOPE)
    if not _ok(result) or result.value is None:
        return None
    return result.value.book_page_label


def page_labeler(
    service: DocumentPageMapService,
    document_id: str,
) -> Callable[[int], str | None]:
    """Load one active map and build a cached pure resolver for S4 cards."""
    current = service.get_page_map(document_id, user_scope=USER_SCOPE)
    page_map = current.value if _ok(current) else None
    cache: dict[int, str | None] = {}

    def resolve(pdf_page: int) -> str | None:
        if pdf_page not in cache:
            cache[pdf_page] = (
                compute_book_page_label(page_map, pdf_page) if page_map is not None else None
            )
        return cache[pdf_page]

    return resolve


def set_current_as_book_page_one(
    ui: Any,
    service: DocumentPageMapService,
    *,
    document_id: str,
    pdf_page: int,
) -> bool:
    """Create or replace the simple PDF N = Book 1 rule."""
    result = service.set_quick_rule(
        document_id,
        current_pdf_page=pdf_page,
        user_scope=USER_SCOPE,
    )
    return _render_result(ui, result, success=f"PDF page {pdf_page} is now Book page 1.")


def _rule_rows(page_map: Any) -> list[dict[str, Any]]:
    return [
        {
            "PDF start": rule.pdf_start_page,
            "PDF end": rule.pdf_end_page or "—",
            "Book start": rule.label_start,
            "Style": str(getattr(rule.label_style, "value", rule.label_style)),
            "Prefix": rule.label_prefix or "",
            "Rule ID": rule.rule_id,
        }
        for rule in page_map.rules
    ]


def _override_rows(page_map: Any) -> list[dict[str, Any]]:
    return [
        {"PDF page": item.pdf_page, "Book page": item.book_page_label}
        for item in page_map.manual_overrides
    ]


def render_page_map_panel(
    ui: Any,
    service: DocumentPageMapService,
    *,
    document: Any,
    current_pdf_page: int,
    book_page_label: str | None,
    actions_enabled: bool,
) -> None:
    """Render quick/manual rules, overrides, lifecycle, and explicit reset."""
    document_id = document.document_id
    ui.header("Page Map")
    ui.caption(f"Document: {document.title} ({document_id})")
    ui.caption(f"Current PDF page {current_pdf_page} · Book page {book_page_label or '—'}")
    ui.info("Page labels are manual metadata. They do not control the internal PDF scroll.")
    current = service.get_page_map(document_id, user_scope=USER_SCOPE)
    page_map = current.value if _ok(current) else None
    current_status = str(
        getattr(getattr(current, "status", None), "value", getattr(current, "status", ""))
    )
    if page_map is None and current_status != "not_found":
        ui.error(
            safe_error_message(
                getattr(current, "message", "") or "Could not load this Document Page Map."
            )
        )
        return
    if ui.button(
        "Set current PDF page as Book page 1",
        key=state_key("page_map_quick", document_id),
        disabled=not actions_enabled,
        width="stretch",
    ):
        if set_current_as_book_page_one(
            ui,
            service,
            document_id=document_id,
            pdf_page=current_pdf_page,
        ):
            ui.rerun()

    with ui.expander("Add page-label rule", expanded=False):
        with ui.form(key=state_key("page_map_rule_form", document_id)):
            left, right = ui.columns(2, gap="small")
            with left:
                pdf_start = int(
                    ui.number_input(
                        "PDF start page",
                        min_value=1,
                        value=current_pdf_page,
                        step=1,
                        key=state_key("page_map_rule_pdf_start", document_id),
                    )
                )
                pdf_end_text = ui.text_input(
                    "PDF end page (optional)",
                    key=state_key("page_map_rule_pdf_end", document_id),
                )
            with right:
                style = ui.selectbox(
                    "Book label style",
                    options=tuple(item.value for item in PageLabelStyle),
                    key=state_key("page_map_rule_style", document_id),
                )
                label_start_text = ui.text_input(
                    "Book label start",
                    value="1",
                    key=state_key("page_map_rule_label_start", document_id),
                )
            prefix = ui.text_input(
                "Label prefix (optional)",
                key=state_key("page_map_rule_prefix", document_id),
            )
            submitted = ui.form_submit_button(
                "Add rule",
                disabled=not actions_enabled,
                width="stretch",
            )
        if submitted:
            try:
                pdf_end = int(pdf_end_text) if str(pdf_end_text).strip() else None
                label_start: int | str = (
                    str(label_start_text).strip()
                    if style == PageLabelStyle.LITERAL.value
                    else int(label_start_text)
                )
            except (TypeError, ValueError):
                ui.warning("PDF end and non-literal Book labels must be valid integers.")
            else:
                result = service.add_rule(
                    document_id,
                    pdf_start_page=pdf_start,
                    pdf_end_page=pdf_end,
                    label_start=label_start,
                    label_style=style,
                    label_prefix=str(prefix).strip() or None,
                    user_scope=USER_SCOPE,
                )
                if _render_result(ui, result, success="Page-label rule added."):
                    ui.rerun()

    with ui.expander("Add or replace a manual override", expanded=False):
        with ui.form(key=state_key("page_map_override_form", document_id)):
            override_page = int(
                ui.number_input(
                    "PDF page",
                    min_value=1,
                    value=current_pdf_page,
                    step=1,
                    key=state_key("page_map_override_pdf", document_id),
                )
            )
            override_label = ui.text_input(
                "Book page label",
                key=state_key("page_map_override_label", document_id),
            )
            submitted = ui.form_submit_button(
                "Save override",
                disabled=not actions_enabled,
                width="stretch",
            )
        if submitted:
            result = service.upsert_override(
                document_id,
                pdf_page=override_page,
                book_page_label=str(override_label).strip(),
                user_scope=USER_SCOPE,
            )
            if _render_result(ui, result, success="Manual page override saved."):
                ui.rerun()

    if page_map is None:
        ui.caption("No active Page Map exists for this Document.")
        archived = service.list_page_maps(
            document_id,
            status="archived",
            page=1,
            page_size=20,
            user_scope=USER_SCOPE,
        )
        archived_items = tuple(getattr(getattr(archived, "value", None), "items", ()))
        for item in archived_items:
            if ui.button(
                f"Reactivate Page Map {item.page_map_id}",
                key=state_key("page_map_reactivate", item.page_map_id),
                disabled=not actions_enabled,
            ):
                result = service.reactivate_page_map(item.page_map_id)
                if _render_result(ui, result, success="Page Map reactivated."):
                    ui.rerun()
        return

    if page_map.rules:
        ui.subheader("Active rules")
        ui.dataframe(_rule_rows(page_map), width="stretch", hide_index=True)
    if page_map.manual_overrides:
        ui.subheader("Manual overrides")
        ui.dataframe(_override_rows(page_map), width="stretch", hide_index=True)

    lifecycle, reset = ui.columns(2, gap="small")
    with lifecycle:
        if ui.button(
            "Archive Page Map",
            key=state_key("page_map_archive", document_id),
            disabled=not actions_enabled,
            width="stretch",
        ):
            result = service.archive_page_map(page_map.page_map_id)
            if _render_result(ui, result, success="Page Map archived."):
                ui.rerun()
    with reset:
        with ui.popover("Reset Page Map", width="stretch"):
            confirmation = ui.text_input(
                "Type the Document ID to clear all rules and overrides",
                key=state_key("page_map_reset_confirmation", document_id),
            )
            if ui.button(
                "Confirm reset",
                key=state_key("page_map_reset", document_id),
                disabled=not actions_enabled or confirmation != document_id,
                width="stretch",
            ):
                result = service.reset_page_map(document_id, user_scope=USER_SCOPE)
                if _render_result(ui, result, success="Page Map reset."):
                    ui.rerun()


def render_page_map_maintenance(
    ui: Any,
    context: Any,
    service: DocumentPageMapService,
) -> bool:
    """Render Page Map index rows and explicit initialization in Maintenance only."""
    try:
        statuses = tuple(service.index_manager.status())
        plan = service.index_manager.plan()
    except Exception as exc:
        ui.error(f"Could not inspect Page Map indexes: {safe_error_message(exc)}")
        return False
    initialized = bool(getattr(plan, "initialized", False))
    conflicts = tuple(getattr(plan, "conflicts", ()))
    if initialized:
        ui.success(f"✅ Page Map ready on {context.database_name}.")
    elif conflicts:
        ui.error("Page Map index conflicts require review.")
    else:
        ui.warning("Page Map needs initialization before writes are enabled.")
    with ui.expander("Advanced Page Map diagnostics", expanded=False):
        rows = [
            {
                "collection": "document_page_maps",
                "index": item.spec.name,
                "state": str(getattr(item.state, "value", item.state)),
                "detail": item.detail,
            }
            for item in statuses
        ]
        ui.dataframe(rows, width="stretch", hide_index=True)
        with ui.form(key=state_key("page_map_initialize_form")):
            confirmation = ui.text_input(
                "Type the real database name to initialize Page Map indexes",
                key=state_key("page_map_initialize_database"),
            )
            confirmed = ui.checkbox(
                f"I confirm applying only S4.2 Page Map indexes in {context.database_name}",
                key=state_key("page_map_initialize_confirm"),
            )
            submitted = ui.form_submit_button(
                "Initialize Page Map indexes",
                disabled=initialized or bool(conflicts),
            )
        if submitted:
            if not confirmed or str(confirmation or "").strip() != context.database_name:
                ui.warning("Initialization requires the exact database name and confirmation.")
            else:
                try:
                    applied = service.index_manager.apply()
                except Exception as exc:
                    ui.error(f"Could not initialize Page Map indexes: {safe_error_message(exc)}")
                else:
                    initialized = bool(getattr(applied, "initialized", True))
                    if initialized:
                        ui.success("Page Map indexes initialized.")
    return initialized


__all__ = [
    "current_book_page",
    "page_labeler",
    "render_page_map_maintenance",
    "render_page_map_panel",
    "set_current_as_book_page_one",
]

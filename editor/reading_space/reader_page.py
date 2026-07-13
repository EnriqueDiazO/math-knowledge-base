"""Dedicated Streamlit page for persistent, annotation-free Document reading."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any

from editor.pdf_preview import PdfPreviewPayload
from editor.pdf_preview import get_pdf_preview
from editor.pdf_preview import pdf_preview_context
from editor.pdf_preview import render_pdf_preview
from editor.pdf_preview import store_pdf_preview
from editor.reading_space.document_picker import render_document_picker
from editor.reading_space.filters import Choice
from editor.reading_space.filters import render_filters
from editor.reading_space.recent_reads import render_recent_documents
from editor.reading_space.state import CONFIRMED_WEB_DOCUMENT_ID
from editor.reading_space.state import PDF_PREVIEW_NAMESPACE
from editor.reading_space.state import READER_SUBJECT
from editor.reading_space.state import SELECTED_DOCUMENT_ID
from editor.reading_space.state import SELECTED_SOURCE_ID
from editor.reading_space.state import apply_pending_current_page_widget_clears
from editor.reading_space.state import apply_pending_document_widget_clears
from editor.reading_space.state import clear_reader_preview
from editor.reading_space.state import consume_pending_target
from editor.reading_space.state import queue_current_page_widget_clear
from editor.reading_space.state import select_document
from editor.reading_space.state import select_source
from editor.reading_space.state import state_key
from editor.reading_space.state import sync_source_filter
from editor.reading_space.state import sync_user_scope
from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import render_active_database
from editor.source_catalog.shared import safe_error_message
from mathmongo.reading_space.service import ReaderContext
from mathmongo.reading_space.service import ReadingOperationStatus
from mathmongo.reading_space.service import ReadingServiceResult
from mathmongo.reading_space.service import ReadingSpaceService
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus

USER_SCOPE = "local"
DOCUMENT_PAGE_SIZE = 20
RECENT_PAGE_SIZE = 10


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _result_ok(result: ReadingServiceResult) -> bool:
    return bool(getattr(result, "completed", False))


def _render_result(ui: Any, result: ReadingServiceResult, *, success: str) -> None:
    message = safe_error_message(getattr(result, "message", "") or success)
    status = _status_value(getattr(result, "status", "error"))
    if status == ReadingOperationStatus.SUCCESS.value:
        ui.success(message)
    elif status in {
        ReadingOperationStatus.NOT_FOUND.value,
        ReadingOperationStatus.ARCHIVED.value,
    }:
        ui.warning(message)
    else:
        ui.error(message)


def _source_choices(ui: Any, context: CatalogUIContext) -> list[Choice]:
    try:
        page = context.source_repository.list(page=1, page_size=100)
    except Exception as exc:
        ui.error(f"No se pudieron cargar las Sources: {safe_error_message(exc)}")
        return []
    sources = list(page.items)
    selected = ui.session_state.get(SELECTED_SOURCE_ID)
    if isinstance(selected, str) and all(item.source_id != selected for item in sources):
        try:
            exact = context.source_repository.get_by_id(selected)
        except Exception:
            exact = None
        if exact is not None:
            sources.append(exact)
    if page.total > len(page.items):
        ui.warning("Se muestran las 100 Sources más recientes en el filtro.")
    return [(item.source_id, f"{item.name} ({item.source_id})") for item in sources]


def _reference_choices(ui: Any, context: CatalogUIContext) -> list[Choice]:
    source_id = ui.session_state.get(state_key("filter_source"))
    try:
        page = context.reference_repository.list(
            source_id=source_id if isinstance(source_id, str) else None,
            page=1,
            page_size=100,
        )
    except Exception as exc:
        ui.error(f"No se pudieron cargar las References: {safe_error_message(exc)}")
        return []
    if page.total > len(page.items):
        ui.warning("Se muestran las 100 References más recientes en el filtro.")
    return [
        (
            item.reference_id,
            f"{item.title or item.bibtex.key or 'Untitled'} ({item.reference_id})",
        )
        for item in page.items
    ]


def _index_rows(statuses: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for status in statuses:
        spec = getattr(status, "spec", None)
        rows.append(
            {
                "collection": getattr(spec, "collection", "document_reading_state"),
                "index": getattr(spec, "name", ""),
                "state": _status_value(getattr(status, "state", "unknown")),
                "detail": getattr(status, "detail", ""),
            }
        )
    return rows


def _render_index_status(ui: Any, context: CatalogUIContext, service: ReadingSpaceService) -> bool:
    """Inspect indexes read-only and apply them only after explicit confirmation."""
    ui.subheader("Reading Space Status")
    try:
        statuses = tuple(service.index_manager.status())
        plan = service.index_manager.plan()
    except Exception as exc:
        ui.error(f"No se pudo inspeccionar Reading Space: {safe_error_message(exc)}")
        return False
    initialized = bool(getattr(plan, "initialized", False))
    conflicts = tuple(getattr(plan, "conflicts", ()))
    if initialized:
        ui.success(f"Reading Space inicializado en {context.database_name}.")
    elif conflicts:
        ui.error("Los índices de Reading Space tienen conflictos; no se aplicarán cambios.")
    else:
        ui.info("Reading Space no inicializado. Abrir esta página no crea índices.")
    ui.dataframe(_index_rows(statuses), width="stretch", hide_index=True)
    with ui.form(key=state_key("initialize_indexes_form")):
        confirmation = ui.text_input(
            "Escribe el nombre real de la base para inicializar Reading Space",
            key=state_key("initialize_indexes_database"),
        )
        confirmed = ui.checkbox(
            f"Confirmo aplicar sólo los índices S3 en {context.database_name}",
            key=state_key("initialize_indexes_confirm"),
        )
        submitted = ui.form_submit_button(
            "Initialize Reading Space indexes",
            disabled=initialized or bool(conflicts),
        )
    if not submitted:
        return initialized
    if not confirmed or str(confirmation or "").strip() != context.database_name:
        ui.warning("La inicialización requiere el nombre exacto de la base y confirmación.")
        return False
    try:
        applied = service.index_manager.apply()
    except Exception as exc:
        ui.error(f"No se pudieron inicializar los índices: {safe_error_message(exc)}")
        return False
    initialized = bool(getattr(applied, "initialized", True))
    if initialized:
        ui.success("Reading Space indexes initialized.")
    return initialized


def _subject(context: CatalogUIContext, reader: ReaderContext) -> dict[str, str]:
    document = reader.document
    if document.pdf is None:
        raise ValueError("El ReaderContext no contiene un PDF.")
    version = document.pdf.current_version
    database_identity = str(
        context.database_name
        + ":"
        + str(context.database is not None and id(context.database) or "")
    )
    return {
        "database": database_identity,
        "user_scope": USER_SCOPE,
        "source_id": document.source_id,
        "document_id": document.document_id,
        "version_id": version.version_id,
        "sha256": version.sha256,
    }


def _subject_identity(subject: dict[str, str]) -> str:
    return pdf_preview_context(
        subject["database"],
        subject["user_scope"],
        subject["source_id"],
        subject["document_id"],
        subject["version_id"],
        subject["sha256"],
    )


def _open_pdf(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    document_id: str,
) -> ReaderContext | None:
    clear_reader_preview(ui.session_state)
    result = service.open_document(document_id, user_scope=USER_SCOPE)
    if not _result_ok(result) or result.value is None:
        _render_result(ui, result, success="PDF abierto.")
        return None
    reader = result.value
    payload = reader.pdf_payload
    if payload is None:
        ui.error("El servicio no devolvió bytes para el PDF abierto.")
        return None
    subject = _subject(context, reader)
    observed_sha = hashlib.sha256(payload.pdf_bytes).hexdigest()
    if payload.sha256 != subject["sha256"] or observed_sha != subject["sha256"]:
        ui.error("La identidad SHA-256 del PDF abierto no coincide.")
        return None
    store_pdf_preview(
        ui.session_state,
        PDF_PREVIEW_NAMESPACE,
        PdfPreviewPayload(
            pdf_bytes=payload.pdf_bytes,
            sha256=payload.sha256,
            file_name=payload.file_name,
            context_identity=_subject_identity(subject),
        ),
    )
    ui.session_state[READER_SUBJECT] = subject
    _render_result(ui, result, success="PDF abierto en Reading Space.")
    return reader


def _run_state_action(
    ui: Any,
    result: ReadingServiceResult,
    *,
    success: str,
) -> bool:
    _render_result(ui, result, success=success)
    return _result_ok(result)


def _render_reading_state_actions(
    ui: Any,
    service: ReadingSpaceService,
    reader: ReaderContext,
    *,
    actions_enabled: bool,
    show_page_controls: bool = True,
) -> None:
    document_id = reader.document.document_id
    reading = reader.reading_state
    if show_page_controls:
        current_page = getattr(reading, "current_page", None) or 1
        total_pages = getattr(reading, "total_pages", None)
        kwargs: dict[str, Any] = {
            "min_value": 1,
            "value": int(current_page),
            "step": 1,
            "key": state_key("current_page", document_id),
            "width": "stretch",
        }
        if isinstance(total_pages, int):
            kwargs["max_value"] = total_pages
        entered_page = int(ui.number_input("Current page", **kwargs))
        if ui.button(
            "Save current page",
            key=state_key("save_page", document_id),
            disabled=not actions_enabled,
        ):
            _run_state_action(
                ui,
                service.update_current_page(
                    document_id,
                    entered_page,
                    user_scope=USER_SCOPE,
                    total_pages=total_pages,
                ),
                success="Current page saved.",
            )
    if ui.button(
        "Completed",
        key=state_key("reader_completed", document_id),
        disabled=not actions_enabled,
    ):
        _run_state_action(
            ui,
            service.mark_completed(document_id, user_scope=USER_SCOPE),
            success="Document marked completed.",
        )
    if ui.button(
        "Deferred",
        key=state_key("reader_deferred", document_id),
        disabled=not actions_enabled,
    ):
        _run_state_action(
            ui,
            service.mark_deferred(document_id, user_scope=USER_SCOPE),
            success="Document marked deferred.",
        )
    if ui.button(
        "Reset",
        key=state_key("reader_reset", document_id),
        disabled=not actions_enabled or reading is None,
    ):
        reset = _run_state_action(
            ui,
            service.reset_reading_state(document_id, user_scope=USER_SCOPE),
            success="Reading state reset.",
        )
        if reset:
            queue_current_page_widget_clear(ui.session_state, document_id)
            ui.rerun()


def _render_pdf_reader(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    reader: ReaderContext,
    *,
    actions_enabled: bool,
) -> None:
    document = reader.document
    version = document.pdf.current_version
    integrity = reader.integrity
    subject = ui.session_state.get(READER_SUBJECT)
    expected = _subject(context, reader)
    if subject != expected:
        clear_reader_preview(ui.session_state)
        subject = None
    verified_payload = get_pdf_preview(
        ui.session_state,
        PDF_PREVIEW_NAMESPACE,
        context_identity=_subject_identity(expected),
    )
    integrity_ok = bool(getattr(integrity, "ok", False) or verified_payload is not None)
    ui.write(
        {
            "title": document.title,
            "source": reader.source.name if reader.source is not None else document.source_id,
            "reference": (
                reader.reference.title or reader.reference.reference_id
                if reader.reference is not None
                else None
            ),
            "filename": version.original_filename,
            "size_bytes": version.size_bytes,
            "sha256": version.sha256[:16],
            "integrity": "ok" if integrity_ok else "not verified or invalid",
            "reading_status": _status_value(reader.effective_status),
        }
    )
    _render_reading_state_actions(
        ui,
        service,
        reader,
        actions_enabled=actions_enabled,
    )
    if ui.button(
        "Open PDF",
        key=state_key("reader_open_pdf", document.document_id),
        disabled=not actions_enabled or document.status == DocumentStatus.ARCHIVED,
    ):
        opened = _open_pdf(ui, context, service, document.document_id)
        if opened is not None:
            subject = ui.session_state.get(READER_SUBJECT)
    if isinstance(subject, dict):
        rendered = render_pdf_preview(
            ui,
            ui.session_state,
            PDF_PREVIEW_NAMESPACE,
            context_identity=_subject_identity(subject),
            height=800,
        )
        if not rendered:
            ui.session_state.pop(READER_SUBJECT, None)


def _render_web_reader(
    ui: Any,
    service: ReadingSpaceService,
    reader: ReaderContext,
    *,
    actions_enabled: bool,
) -> None:
    clear_reader_preview(ui.session_state)
    document = reader.document
    web = document.web
    reading = reader.reading_state
    ui.write(
        {
            "title": document.title,
            "source": reader.source.name if reader.source is not None else document.source_id,
            "reference": (
                reader.reference.title or reader.reference.reference_id
                if reader.reference is not None
                else None
            ),
            "url_normalized": web.url_normalized,
            "url_raw": web.url_raw,
            "accessed_at": getattr(web, "accessed_at", None),
            "description": document.description,
            "reading_status": _status_value(reader.effective_status),
            "last_opened_at": getattr(reading, "last_opened_at", None),
            "open_count": getattr(reading, "open_count", 0),
        }
    )
    _render_reading_state_actions(
        ui,
        service,
        reader,
        actions_enabled=actions_enabled,
        show_page_controls=False,
    )
    if ui.button(
        "Register opening",
        key=state_key("register_web_open", document.document_id),
        disabled=not actions_enabled or document.status == DocumentStatus.ARCHIVED,
    ):
        result = service.open_document(document.document_id, user_scope=USER_SCOPE)
        if _run_state_action(ui, result, success="Web opening registered."):
            ui.session_state[CONFIRMED_WEB_DOCUMENT_ID] = document.document_id
    if ui.session_state.get(CONFIRMED_WEB_DOCUMENT_ID) == document.document_id:
        ui.link_button(
            "Open external resource",
            web.url_normalized,
            width="content",
        )


def _render_reader_panel(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    *,
    actions_enabled: bool,
) -> None:
    ui.subheader("Reader")
    document_id = ui.session_state.get(SELECTED_DOCUMENT_ID)
    if not isinstance(document_id, str):
        ui.info("Open a Document from the list or Recent Documents.")
        return
    result = service.get_reader_context(document_id, user_scope=USER_SCOPE)
    if not _result_ok(result) or result.value is None:
        clear_reader_preview(ui.session_state)
        _render_result(ui, result, success="Reader loaded.")
        return
    reader = result.value
    if reader.document.kind == DocumentKind.PDF:
        _render_pdf_reader(
            ui,
            context,
            service,
            reader,
            actions_enabled=actions_enabled,
        )
    else:
        _render_web_reader(
            ui,
            service,
            reader,
            actions_enabled=actions_enabled,
        )


def _render_summary(ui: Any, service: ReadingSpaceService, source_id: str | None) -> None:
    if source_id is None:
        return
    result = service.get_source_reading_summary(source_id, user_scope=USER_SCOPE)
    if not _result_ok(result) or result.value is None:
        _render_result(ui, result, success="Source summary loaded.")
        return
    summary = result.value
    ui.subheader("Source Reading Summary")
    fields = (
        "total_documents",
        "pdf_documents",
        "web_documents",
        "unread",
        "in_progress",
        "completed",
        "deferred",
        "last_opened_at",
    )
    ui.write({field: getattr(summary, field, None) for field in fields})


def _recent_page(result: ReadingServiceResult) -> Any:
    value = result.value
    if hasattr(value, "items"):
        return value
    items = tuple(value or ())
    return SimpleNamespace(items=items, page=1, pages=1 if items else 0, total=len(items))


def render_reading_space_page(
    context: CatalogUIContext,
    *,
    ui: Any | None = None,
    service: ReadingSpaceService | None = None,
) -> None:
    """Render S3 filters, metadata lists, history, reader, and reading state."""
    if ui is None:
        import streamlit as ui

    reading_service = service or ReadingSpaceService(context.database)
    ui.title("📖 Reading Space")
    render_active_database(ui, context)
    sync_user_scope(ui.session_state, USER_SCOPE)
    target = consume_pending_target(ui.session_state)
    if target is not None:
        select_source(ui.session_state, target["source_id"])
        select_document(ui.session_state, target["document_id"])
        ui.session_state[state_key("filter_source")] = target["source_id"]
    apply_pending_document_widget_clears(ui.session_state)
    apply_pending_current_page_widget_clears(ui.session_state)

    actions_enabled = _render_index_status(ui, context, reading_service)
    ui.divider()
    filters = render_filters(
        ui,
        sources=_source_choices(ui, context),
        references=_reference_choices(ui, context),
    )
    sync_source_filter(ui.session_state, filters.source_id)
    page_number = int(
        ui.number_input(
            "Documents page",
            min_value=1,
            value=1,
            step=1,
            key=state_key("documents_page"),
            width="stretch",
        )
    )

    if target is not None and target["kind"] == "pdf" and actions_enabled:
        _open_pdf(ui, context, reading_service, target["document_id"])

    list_result = reading_service.list_readable_documents(
        filters=filters,
        user_scope=USER_SCOPE,
        page=page_number,
        page_size=DOCUMENT_PAGE_SIZE,
    )
    if not _result_ok(list_result) or list_result.value is None:
        _render_result(ui, list_result, success="Documents loaded.")
    else:

        def open_item(item: Any) -> None:
            document = item.document
            select_source(ui.session_state, document.source_id)
            select_document(ui.session_state, document.document_id)
            if document.kind == DocumentKind.PDF:
                _open_pdf(ui, context, reading_service, document.document_id)

        def complete_item(item: Any) -> None:
            _run_state_action(
                ui,
                reading_service.mark_completed(item.document.document_id, user_scope=USER_SCOPE),
                success="Document marked completed.",
            )

        def defer_item(item: Any) -> None:
            _run_state_action(
                ui,
                reading_service.mark_deferred(item.document.document_id, user_scope=USER_SCOPE),
                success="Document marked deferred.",
            )

        def reset_item(item: Any) -> None:
            document_id = item.document.document_id
            reset = _run_state_action(
                ui,
                reading_service.reset_reading_state(
                    document_id,
                    user_scope=USER_SCOPE,
                ),
                success="Reading state reset.",
            )
            if reset:
                queue_current_page_widget_clear(ui.session_state, document_id)
                ui.rerun()

        render_document_picker(
            ui,
            list_result.value,
            actions_enabled=actions_enabled,
            on_open=open_item,
            on_completed=complete_item,
            on_deferred=defer_item,
            on_reset=reset_item,
        )

    _render_summary(ui, reading_service, filters.source_id)
    ui.subheader("Recent Documents")
    recent_result = reading_service.list_recent_documents(
        user_scope=USER_SCOPE,
        page=1,
        page_size=RECENT_PAGE_SIZE,
    )
    if not _result_ok(recent_result):
        _render_result(ui, recent_result, success="Recent Documents loaded.")
    else:

        def open_recent(item: Any) -> None:
            document = item.document
            select_source(ui.session_state, document.source_id)
            select_document(ui.session_state, document.document_id)
            if document.kind == DocumentKind.PDF:
                _open_pdf(ui, context, reading_service, document.document_id)

        render_recent_documents(
            ui,
            _recent_page(recent_result),
            actions_enabled=actions_enabled,
            on_open=open_recent,
        )

    _render_reader_panel(
        ui,
        context,
        reading_service,
        actions_enabled=actions_enabled,
    )


__all__ = ["render_reading_space_page"]

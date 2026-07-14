"""Dedicated Streamlit page for persistent Document reading."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any

from editor.concept_linking import render_concepts_tab
from editor.concept_linking import render_workspace_concept_panel
from editor.concept_linking.state import sync_context as sync_concept_linking_context
from editor.pdf_preview import PdfPreviewPayload
from editor.pdf_preview import get_pdf_preview
from editor.pdf_preview import pdf_preview_context
from editor.pdf_preview import render_pdf_preview
from editor.pdf_preview import store_pdf_preview
from editor.reading_annotations import render_evidence_tab  # noqa: F401  # Test seam.
from editor.reading_annotations import render_notes_and_evidence_panel as _render_s4_panel
from editor.reading_annotations import render_notes_evidence_maintenance
from editor.reading_annotations import render_notes_tab
from editor.reading_annotations import render_workspace_notes_panel
from editor.reading_annotations.state import apply_pending_page_suggestion
from editor.reading_annotations.state import sync_database_context as sync_s4_database_context
from editor.reading_space.document_picker import render_document_picker
from editor.reading_space.filters import Choice
from editor.reading_space.filters import render_filters
from editor.reading_space.page_map_panel import current_book_page
from editor.reading_space.page_map_panel import page_labeler
from editor.reading_space.page_map_panel import render_page_map_maintenance
from editor.reading_space.page_map_panel import render_page_map_panel
from editor.reading_space.page_map_panel import set_current_as_book_page_one
from editor.reading_space.recent_reads import render_recent_documents
from editor.reading_space.state import CONFIRMED_WEB_DOCUMENT_ID
from editor.reading_space.state import PDF_PREVIEW_NAMESPACE
from editor.reading_space.state import READER_SUBJECT
from editor.reading_space.state import SELECTED_DOCUMENT_ID
from editor.reading_space.state import SELECTED_SOURCE_ID
from editor.reading_space.state import WORKSPACE_FOCUS
from editor.reading_space.state import WORKSPACE_TAB
from editor.reading_space.state import WORKSPACE_TABS
from editor.reading_space.state import apply_pending_current_page_value
from editor.reading_space.state import apply_pending_current_page_widget_clears
from editor.reading_space.state import apply_pending_document_widget_clears
from editor.reading_space.state import apply_pending_workspace_tab
from editor.reading_space.state import clear_reader_preview
from editor.reading_space.state import consume_pending_target
from editor.reading_space.state import migrate_legacy_workspace_tab
from editor.reading_space.state import queue_current_page_value
from editor.reading_space.state import queue_current_page_widget_clear
from editor.reading_space.state import queue_workspace_tab
from editor.reading_space.state import select_document
from editor.reading_space.state import select_source
from editor.reading_space.state import state_key
from editor.reading_space.state import sync_source_filter
from editor.reading_space.state import sync_user_scope
from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import render_active_database
from editor.source_catalog.shared import safe_error_message
from mathmongo.advanced_reader.streamlit_link import AdvancedReaderHealthStatus
from mathmongo.advanced_reader.streamlit_link import build_advanced_reader_url
from mathmongo.advanced_reader.streamlit_link import probe_advanced_reader
from mathmongo.config import resolve_config
from mathmongo.document_page_maps.service import DocumentPageMapService
from mathmongo.reading_annotations.service import ReadingAnnotationService
from mathmongo.reading_space.service import ReaderContext
from mathmongo.reading_space.service import ReadingOperationStatus
from mathmongo.reading_space.service import ReadingServiceResult
from mathmongo.reading_space.service import ReadingSpaceService
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus

USER_SCOPE = "local"
DOCUMENT_PAGE_SIZE = 20
RECENT_PAGE_SIZE = 10
SPLIT_WORKSPACE = "Split workspace"
STACKED_WORKSPACE = "Stacked layout"


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


def _render_index_status(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    *,
    maintenance: bool = False,
) -> bool:
    """Inspect indexes read-only and apply them only after explicit confirmation."""
    if maintenance:
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
        ui.success(f"✅ Reading Space ready on {context.database_name}.")
    elif conflicts:
        ui.error("Los índices de Reading Space tienen conflictos; no se aplicarán cambios.")
    else:
        ui.warning("Reading Space needs initialization in Maintenance.")
    if not maintenance:
        return initialized
    with ui.expander("Advanced Reading Space diagnostics", expanded=False):
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


def _render_advanced_reader_link(
    ui: Any,
    document_id: str,
    *,
    enabled: bool,
    configured: bool = True,
) -> None:
    """Render the explicit, optional link without starting a process or opening a tab."""
    if not configured:
        ui.caption("Lector avanzado deshabilitado en la configuración.")
        return
    if not enabled:
        ui.caption("Lector avanzado no disponible para este Document.")
        return
    health = probe_advanced_reader()
    try:
        reader_url = build_advanced_reader_url(
            document_id,
            base_url=health.base_url,
        )
    except (TypeError, ValueError):
        reader_url = None
        status = AdvancedReaderHealthStatus.INVALID
    else:
        status = health.status

    if status == AdvancedReaderHealthStatus.AVAILABLE:
        ui.caption("Lector avanzado disponible.")
    elif status == AdvancedReaderHealthStatus.NOT_STARTED:
        ui.caption("Lector avanzado no iniciado. Ejecuta `make advanced-reader`.")
    elif status == AdvancedReaderHealthStatus.TIMEOUT:
        ui.caption(
            "El lector avanzado no respondió a tiempo. "
            "Ejecuta `make advanced-reader` y vuelve a intentar."
        )
    else:
        ui.caption(
            "La configuración o respuesta del lector avanzado no es válida. "
            "Revisa MATHMONGO_ADVANCED_READER_URL."
        )

    if reader_url is not None:
        ui.link_button(
            "Abrir lector avanzado",
            reader_url,
            key=state_key("advanced_reader_link", document_id),
            disabled=not enabled or status != AdvancedReaderHealthStatus.AVAILABLE,
            width="content",
        )


def _render_reading_state_actions(
    ui: Any,
    service: ReadingSpaceService,
    reader: ReaderContext,
    *,
    actions_enabled: bool,
    show_page_controls: bool = True,
    page_map_service: DocumentPageMapService | None = None,
    page_map_actions_enabled: bool = False,
) -> int | None:
    document_id = reader.document.document_id
    reading = reader.reading_state
    entered_page: int | None = None
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
        entered_page = int(ui.number_input("PDF page", **kwargs))
        book_page = (
            current_book_page(page_map_service, document_id, entered_page)
            if page_map_service is not None
            else None
        )
        total_label = f" of {total_pages}" if isinstance(total_pages, int) else ""
        ui.caption(
            f"Book page {book_page or '—'} · PDF page {entered_page}{total_label} · "
            f"Status {_status_value(reader.effective_status)}"
        )
        previous, following, save = ui.columns(3, gap="small")
        with previous:
            if ui.button(
                "Previous",
                key=state_key("page_previous", document_id),
                disabled=entered_page <= 1,
                width="stretch",
            ):
                queue_current_page_value(
                    ui.session_state,
                    document_id=document_id,
                    page_number=entered_page - 1,
                )
                ui.rerun()
        with following:
            if ui.button(
                "Next",
                key=state_key("page_next", document_id),
                disabled=isinstance(total_pages, int) and entered_page >= total_pages,
                width="stretch",
            ):
                queue_current_page_value(
                    ui.session_state,
                    document_id=document_id,
                    page_number=entered_page + 1,
                )
                ui.rerun()
        with save:
            if ui.button(
                "Save PDF page",
                key=state_key("save_page", document_id),
                disabled=not actions_enabled,
                width="stretch",
            ):
                _run_state_action(
                    ui,
                    service.update_current_page(
                        document_id,
                        entered_page,
                        user_scope=USER_SCOPE,
                        total_pages=total_pages,
                    ),
                    success="PDF page saved.",
                )
        set_page, quick_note, quick_annotation = ui.columns(3, gap="small")
        with set_page:
            if (
                ui.button(
                    "Set as Book page 1",
                    key=state_key("set_book_page_one", document_id),
                    disabled=page_map_service is None or not page_map_actions_enabled,
                    width="stretch",
                )
                and page_map_service is not None
            ):
                if set_current_as_book_page_one(
                    ui,
                    page_map_service,
                    document_id=document_id,
                    pdf_page=entered_page,
                ):
                    ui.rerun()
        with quick_note:
            if ui.button(
                "Quick note",
                key=state_key("quick_note_focus", document_id),
                width="stretch",
            ):
                ui.session_state[WORKSPACE_FOCUS] = "note"
                queue_workspace_tab(ui.session_state, "Workspace")
        with quick_annotation:
            if ui.button(
                "Quick annotation",
                key=state_key("quick_annotation_focus", document_id),
                width="stretch",
            ):
                ui.session_state[WORKSPACE_FOCUS] = "annotation"
                queue_workspace_tab(ui.session_state, "Workspace")
        ui.caption(
            "The PDF viewer scroll is manual; MathMongo stores the page metadata separately."
        )
    completed, deferred, reset_column = ui.columns(3, gap="small")
    with completed:
        if ui.button(
            "Completed",
            key=state_key("reader_completed", document_id),
            disabled=not actions_enabled,
            width="stretch",
        ):
            _run_state_action(
                ui,
                service.mark_completed(document_id, user_scope=USER_SCOPE),
                success="Document marked completed.",
            )
    with deferred:
        if ui.button(
            "Deferred",
            key=state_key("reader_deferred", document_id),
            disabled=not actions_enabled,
            width="stretch",
        ):
            _run_state_action(
                ui,
                service.mark_deferred(document_id, user_scope=USER_SCOPE),
                success="Document marked deferred.",
            )
    with reset_column:
        if ui.button(
            "Reset",
            key=state_key("reader_reset", document_id),
            disabled=not actions_enabled or reading is None,
            width="stretch",
        ):
            reset = _run_state_action(
                ui,
                service.reset_reading_state(document_id, user_scope=USER_SCOPE),
                success="Reading state reset.",
            )
            if reset:
                queue_current_page_widget_clear(ui.session_state, document_id)
                ui.rerun()
    return entered_page


def _render_pdf_reader(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    reader: ReaderContext,
    *,
    actions_enabled: bool,
    page_map_service: DocumentPageMapService | None = None,
    page_map_actions_enabled: bool = False,
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
    source_label = reader.source.name if reader.source is not None else document.source_id
    reference_label = (
        reader.reference.title or reader.reference.reference_id
        if reader.reference is not None
        else "—"
    )
    with ui.container(border=True):
        ui.subheader("Document")
        ui.write(document.title)
        ui.caption(f"Source: {source_label} · Reference: {reference_label}")
        ui.caption(
            f"Kind: PDF · Integrity: {'OK' if integrity_ok else 'Not verified'} · "
            f"Size: {version.size_bytes / (1024 * 1024):.1f} MB · SHA: {version.sha256[:12]}…"
        )
    with ui.expander("Technical details", expanded=False):
        ui.write(
            {
                "document_id": document.document_id,
                "source_id": document.source_id,
                "filename": version.original_filename,
                "size_bytes": version.size_bytes,
                "sha256": version.sha256,
                "reading_status": _status_value(reader.effective_status),
            }
        )
    _render_reading_state_actions(
        ui,
        service,
        reader,
        actions_enabled=actions_enabled,
        page_map_service=page_map_service,
        page_map_actions_enabled=page_map_actions_enabled,
    )
    _render_advanced_reader_link(
        ui,
        document.document_id,
        enabled=document.status != DocumentStatus.ARCHIVED,
        configured=resolve_config().advanced_reader_enabled,
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
    source_label = reader.source.name if reader.source is not None else document.source_id
    reference_label = (
        reader.reference.title or reader.reference.reference_id
        if reader.reference is not None
        else "—"
    )
    with ui.container(border=True):
        ui.subheader("Document")
        ui.write(document.title)
        ui.caption(f"Source: {source_label} · Reference: {reference_label}")
        ui.caption(f"Kind: Web · Status: {_status_value(reader.effective_status)}")
        if document.description:
            ui.write(document.description)
    ui.caption("Lector avanzado no disponible: el Document no es PDF.")
    with ui.expander("Technical details", expanded=False):
        ui.write(
            {
                "document_id": document.document_id,
                "source_id": document.source_id,
                "url_normalized": web.url_normalized,
                "url_raw": web.url_raw,
                "accessed_at": getattr(web, "accessed_at", None),
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
    render_s4: bool = True,
    reader: ReaderContext | None = None,
    reader_loaded: bool = False,
    page_map_service: DocumentPageMapService | None = None,
    page_map_actions_enabled: bool = False,
) -> ReaderContext | None:
    ui.subheader("Reader")
    if not reader_loaded:
        document_id = ui.session_state.get(SELECTED_DOCUMENT_ID)
        if not isinstance(document_id, str):
            ui.info("Open a Document from the list or Recent Documents.")
            return None
        result = service.get_reader_context(document_id, user_scope=USER_SCOPE)
        if not _result_ok(result) or result.value is None:
            clear_reader_preview(ui.session_state)
            _render_result(ui, result, success="Reader loaded.")
            return None
        reader = result.value
        apply_pending_page_suggestion(
            ui.session_state,
            total_pages=getattr(reader.reading_state, "total_pages", None),
        )
    if reader is None:
        ui.info("Open a Document from the list or Recent Documents.")
        return None
    if reader.document.kind == DocumentKind.PDF:
        _render_pdf_reader(
            ui,
            context,
            service,
            reader,
            actions_enabled=actions_enabled,
            page_map_service=page_map_service,
            page_map_actions_enabled=page_map_actions_enabled,
        )
    else:
        _render_web_reader(
            ui,
            service,
            reader,
            actions_enabled=actions_enabled,
        )
    if render_s4 and hasattr(context.database, "__getitem__"):
        _render_s4_panel(
            context,
            reader,
            ui=ui,
        )
    return reader


def _load_selected_reader(
    ui: Any,
    service: ReadingSpaceService,
) -> ReaderContext | None:
    """Load one selected ReaderContext and apply pending page state pre-widget."""
    document_id = ui.session_state.get(SELECTED_DOCUMENT_ID)
    if not isinstance(document_id, str):
        return None
    result = service.get_reader_context(document_id, user_scope=USER_SCOPE)
    if not _result_ok(result) or result.value is None:
        clear_reader_preview(ui.session_state)
        _render_result(ui, result, success="Reader loaded.")
        return None
    reader = result.value
    apply_pending_page_suggestion(
        ui.session_state,
        total_pages=getattr(reader.reading_state, "total_pages", None),
    )
    return reader


def _render_reading_workspace(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    *,
    actions_enabled: bool,
    reader: ReaderContext | None = None,
    annotation_service: ReadingAnnotationService | None = None,
    page_map_service: DocumentPageMapService | None = None,
    page_map_actions_enabled: bool = False,
) -> None:
    """Render the selected Document first in split or stacked workspace form."""
    selected_document_id = ui.session_state.get(SELECTED_DOCUMENT_ID)
    if reader is None:
        reader = _load_selected_reader(ui, service)
    with ui.container(border=True):
        heading, layout_control = ui.columns([0.68, 0.32], gap="medium")
        with heading:
            ui.subheader("Reading Workspace")
            if reader is not None:
                document = reader.document
                reading = reader.reading_state
                source_label = (
                    reader.source.name if reader.source is not None else document.source_id
                )
                reference_label = None
                if reader.reference is not None:
                    reference_label = reader.reference.title or reader.reference.reference_id
                current_page = ui.session_state.get(
                    state_key("current_page", document.document_id),
                    getattr(reading, "current_page", None),
                )
                book_page = (
                    current_book_page(
                        page_map_service,
                        document.document_id,
                        int(current_page or 1),
                    )
                    if page_map_service is not None
                    else None
                )
                ui.caption(
                    f"Document: {document.title} · Source: {source_label} · "
                    f"Reference: {reference_label or '—'}"
                )
                ui.caption(
                    f"PDF page: {current_page or '—'} · Book page: {book_page or '—'} · "
                    f"Reading status: {_status_value(reader.effective_status)}"
                )
            elif isinstance(selected_document_id, str):
                ui.caption(f"Selected Document: {selected_document_id}")
            else:
                ui.caption("Select a Document to begin reading and taking notes.")
        with layout_control:
            workspace_layout = ui.selectbox(
                "Workspace layout",
                options=(SPLIT_WORKSPACE, STACKED_WORKSPACE),
                key=state_key("workspace_layout"),
            )

    if workspace_layout == STACKED_WORKSPACE:
        stacked_reader = _render_reader_panel(
            ui,
            context,
            service,
            actions_enabled=actions_enabled,
            render_s4=False,
            reader=reader,
            reader_loaded=True,
            page_map_service=page_map_service,
            page_map_actions_enabled=page_map_actions_enabled,
        )
        if stacked_reader is not None and hasattr(context.database, "__getitem__"):
            linking_service = annotation_service or ReadingAnnotationService(context.database)
            labeler = (
                page_labeler(page_map_service, stacked_reader.document.document_id)
                if page_map_service is not None
                else None
            )
            render_workspace_concept_panel(
                context,
                stacked_reader,
                ui=ui,
                service=linking_service,
                page_map_service=page_map_service,
                page_labeler=labeler,
                actions_enabled=(
                    _manager_ready(linking_service.index_manager)
                    and stacked_reader.document.status == DocumentStatus.ACTIVE
                ),
                lifecycle_enabled=_manager_ready(linking_service.index_manager),
                legacy_panel=render_workspace_notes_panel,
                focus=ui.session_state.get(WORKSPACE_FOCUS),
            )
        return

    reader_column, notes_column = ui.columns([0.58, 0.42], gap="large")
    with reader_column:
        reader = _render_reader_panel(
            ui,
            context,
            service,
            actions_enabled=actions_enabled,
            render_s4=False,
            reader=reader,
            reader_loaded=True,
            page_map_service=page_map_service,
            page_map_actions_enabled=page_map_actions_enabled,
        )
    with notes_column:
        if reader is None:
            ui.subheader("Notes & Evidence")
            ui.info("Select a Document to open its notes and concept evidence.")
        elif hasattr(context.database, "__getitem__"):
            linking_service = annotation_service or ReadingAnnotationService(context.database)
            labeler = (
                page_labeler(page_map_service, reader.document.document_id)
                if page_map_service is not None
                else None
            )
            render_workspace_concept_panel(
                context,
                reader,
                ui=ui,
                service=linking_service,
                page_map_service=page_map_service,
                page_labeler=labeler,
                actions_enabled=(
                    _manager_ready(linking_service.index_manager)
                    and reader.document.status == DocumentStatus.ACTIVE
                ),
                lifecycle_enabled=_manager_ready(linking_service.index_manager),
                legacy_panel=render_workspace_notes_panel,
                focus=ui.session_state.get(WORKSPACE_FOCUS),
            )
        else:
            ui.subheader("Notes & Evidence")
            ui.info("Notes & Evidence requires an active database context.")


def _render_summary(ui: Any, service: ReadingSpaceService, source_id: str | None) -> None:
    if source_id is None:
        return
    result = service.get_source_reading_summary(source_id, user_scope=USER_SCOPE)
    if not _result_ok(result) or result.value is None:
        _render_result(ui, result, success="Source summary loaded.")
        return
    summary = result.value
    ui.subheader("Source Reading Summary")
    ui.caption(
        f"{summary.total_documents} documents · {summary.pdf_documents} PDF · "
        f"{summary.web_documents} web · {summary.unread} unread · "
        f"{summary.in_progress} in progress · {summary.completed} completed · "
        f"{summary.deferred} deferred"
    )
    if summary.last_opened_at is not None:
        ui.caption(f"Last opened: {summary.last_opened_at}")


def _recent_page(result: ReadingServiceResult) -> Any:
    value = result.value
    if hasattr(value, "items"):
        return value
    items = tuple(value or ())
    return SimpleNamespace(items=items, page=1, pages=1 if items else 0, total=len(items))


def _render_document_browser(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    *,
    actions_enabled: bool,
) -> None:
    """Render bounded filters and selection controls inside Change Document."""
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
    list_result = service.list_readable_documents(
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
                _open_pdf(ui, context, service, document.document_id)
            ui.rerun()

        def complete_item(item: Any) -> None:
            _run_state_action(
                ui,
                service.mark_completed(item.document.document_id, user_scope=USER_SCOPE),
                success="Document marked completed.",
            )

        def defer_item(item: Any) -> None:
            _run_state_action(
                ui,
                service.mark_deferred(item.document.document_id, user_scope=USER_SCOPE),
                success="Document marked deferred.",
            )

        def reset_item(item: Any) -> None:
            document_id = item.document.document_id
            reset = _run_state_action(
                ui,
                service.reset_reading_state(
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

    _render_summary(ui, service, filters.source_id)


def _render_recent_reads(
    ui: Any,
    context: CatalogUIContext,
    service: ReadingSpaceService,
    *,
    actions_enabled: bool,
) -> None:
    """Render bounded recent reads without displacing the active workspace."""
    recent_result = service.list_recent_documents(
        user_scope=USER_SCOPE,
        page=1,
        page_size=RECENT_PAGE_SIZE,
    )
    if not _result_ok(recent_result):
        _render_result(ui, recent_result, success="Recent Documents loaded.")
        return

    def open_recent(item: Any) -> None:
        document = item.document
        select_source(ui.session_state, document.source_id)
        select_document(ui.session_state, document.document_id)
        if document.kind == DocumentKind.PDF:
            _open_pdf(ui, context, service, document.document_id)
        ui.rerun()

    render_recent_documents(
        ui,
        _recent_page(recent_result),
        actions_enabled=actions_enabled,
        on_open=open_recent,
    )


def _manager_ready(manager: Any) -> bool:
    try:
        return bool(getattr(manager.plan(), "initialized", False))
    except Exception:
        return False


def _render_compact_header(
    ui: Any,
    reader: ReaderContext | None,
    page_maps: DocumentPageMapService | None,
) -> None:
    with ui.container(border=True):
        if reader is None:
            ui.subheader("Reading Space")
            ui.caption("Choose a Document in the Documents tab to begin.")
            return
        document = reader.document
        source_label = reader.source.name if reader.source is not None else document.source_id
        reference_label = (
            reader.reference.title or reader.reference.reference_id
            if reader.reference is not None
            else "—"
        )
        reading = reader.reading_state
        current_page = int(
            ui.session_state.get(
                state_key("current_page", document.document_id),
                getattr(reading, "current_page", None) or 1,
            )
        )
        book_page = (
            current_book_page(page_maps, document.document_id, current_page)
            if page_maps is not None and document.kind == DocumentKind.PDF
            else None
        )
        ui.subheader(document.title)
        ui.caption(f"Source: {source_label} · Reference: {reference_label}")
        if document.kind == DocumentKind.PDF:
            total = getattr(reading, "total_pages", None)
            total_label = f" of {total}" if isinstance(total, int) else ""
            ui.caption(
                f"Book page {book_page or '—'} · PDF page {current_page}{total_label} · "
                f"{_status_value(reader.effective_status)}"
            )
        else:
            ui.caption(f"Web Document · {_status_value(reader.effective_status)}")


def _render_missing_reader(ui: Any, message: str) -> None:
    ui.info(message)


def _render_hidden_pdf_preview(
    ui: Any,
    context: CatalogUIContext,
    reader: ReaderContext | None,
) -> None:
    """Keep the active PDF media registered while another lazy tab is open."""
    if reader is None or reader.document.kind != DocumentKind.PDF:
        return
    subject = ui.session_state.get(READER_SUBJECT)
    expected = _subject(context, reader)
    if subject != expected:
        return
    render_pdf_preview(
        ui,
        ui.session_state,
        PDF_PREVIEW_NAMESPACE,
        context_identity=_subject_identity(expected),
        height=800,
    )


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
    page_map_service = (
        DocumentPageMapService(context.database)
        if hasattr(context.database, "__getitem__")
        else None
    )
    annotation_service = (
        ReadingAnnotationService(context.database)
        if hasattr(context.database, "__getitem__")
        else None
    )
    ui.title("📖 Reading Space")
    render_active_database(ui, context)
    sync_user_scope(ui.session_state, USER_SCOPE)
    sync_s4_database_context(
        ui.session_state,
        connection_label=context.connection_label,
        database_name=context.database_name,
        database=context.database,
    )
    sync_concept_linking_context(
        ui.session_state,
        connection_label=context.connection_label,
        database_name=context.database_name,
        database=context.database,
        user_scope=USER_SCOPE,
        source_id=ui.session_state.get(SELECTED_SOURCE_ID),
        document_id=ui.session_state.get(SELECTED_DOCUMENT_ID),
    )
    target = consume_pending_target(ui.session_state)
    if target is not None:
        select_source(ui.session_state, target["source_id"])
        select_document(ui.session_state, target["document_id"])
        ui.session_state[state_key("filter_source")] = target["source_id"]
    apply_pending_document_widget_clears(ui.session_state)
    apply_pending_current_page_widget_clears(ui.session_state)
    apply_pending_current_page_value(ui.session_state)
    migrate_legacy_workspace_tab(ui.session_state)
    apply_pending_workspace_tab(ui.session_state)
    actions_enabled = _manager_ready(reading_service.index_manager)
    annotation_actions_enabled = bool(
        annotation_service is not None and _manager_ready(annotation_service.index_manager)
    )
    page_map_actions_enabled = bool(
        page_map_service is not None and _manager_ready(page_map_service.index_manager)
    )
    if target is not None and target["kind"] == "pdf" and actions_enabled:
        _open_pdf(ui, context, reading_service, target["document_id"])
    reader = _load_selected_reader(ui, reading_service)
    _render_compact_header(ui, reader, page_map_service)
    readiness = ["✅ Reading Space ready" if actions_enabled else "⚠️ Reading Space setup"]
    if annotation_service is not None:
        readiness.append(
            "✅ Notes & Evidence ready"
            if annotation_actions_enabled
            else "⚠️ Notes & Evidence setup"
        )
    if page_map_service is not None:
        readiness.append("✅ Page Map ready" if page_map_actions_enabled else "⚠️ Page Map setup")
    ui.caption(" · ".join(readiness))
    if not actions_enabled:
        ui.warning("Reading Space needs initialization in Maintenance before writes are enabled.")
    if page_map_service is not None and not page_map_actions_enabled:
        ui.caption("Page Map writes are available after S4.2 initialization in Maintenance.")

    default_tab = "Workspace" if reader is not None else "Documents"
    tabs = ui.tabs(
        list(WORKSPACE_TABS),
        default=default_tab,
        key=WORKSPACE_TAB,
        width="stretch",
        on_change="rerun",
    )
    (
        workspace_tab,
        documents_tab,
        recent_tab,
        notes_tab,
        concepts_tab,
        page_map_tab,
        maintenance_tab,
    ) = tabs
    if getattr(workspace_tab, "open", True):
        with workspace_tab:
            _render_reading_workspace(
                ui,
                context,
                reading_service,
                actions_enabled=actions_enabled,
                reader=reader,
                annotation_service=annotation_service,
                page_map_service=page_map_service,
                page_map_actions_enabled=(
                    page_map_actions_enabled
                    and reader is not None
                    and reader.document.status == DocumentStatus.ACTIVE
                ),
            )
    else:
        with workspace_tab:
            _render_hidden_pdf_preview(ui, context, reader)
    if getattr(documents_tab, "open", True):
        with documents_tab:
            ui.header("Documents")
            _render_document_browser(
                ui,
                context,
                reading_service,
                actions_enabled=actions_enabled,
            )
    if getattr(recent_tab, "open", True):
        with recent_tab:
            ui.header("Recent Documents")
            _render_recent_reads(
                ui,
                context,
                reading_service,
                actions_enabled=actions_enabled,
            )
    if getattr(notes_tab, "open", True):
        with notes_tab:
            if reader is None or annotation_service is None:
                _render_missing_reader(ui, "Select a Document to browse Reading Notes.")
            else:
                render_notes_tab(
                    context,
                    reader,
                    ui=ui,
                    service=annotation_service,
                    page_labeler=(
                        page_labeler(page_map_service, reader.document.document_id)
                        if page_map_service is not None
                        else None
                    ),
                )
    if getattr(concepts_tab, "open", True):
        with concepts_tab:
            if reader is None or annotation_service is None:
                _render_missing_reader(ui, "Select a Document to browse Concepts & Evidence.")
            else:
                render_concepts_tab(
                    context,
                    reader,
                    ui=ui,
                    service=annotation_service,
                    page_map_service=page_map_service,
                    page_labeler=(
                        page_labeler(page_map_service, reader.document.document_id)
                        if page_map_service is not None
                        else None
                    ),
                    actions_enabled=(
                        annotation_actions_enabled
                        and reader.document.status == DocumentStatus.ACTIVE
                    ),
                    lifecycle_enabled=annotation_actions_enabled,
                )
    if getattr(page_map_tab, "open", True):
        with page_map_tab:
            if reader is None or reader.document.kind != DocumentKind.PDF:
                _render_missing_reader(ui, "Select a PDF Document to manage its Page Map.")
            elif page_map_service is not None:
                current_page = int(
                    ui.session_state.get(
                        state_key("current_page", reader.document.document_id),
                        getattr(reader.reading_state, "current_page", None) or 1,
                    )
                )
                render_page_map_panel(
                    ui,
                    page_map_service,
                    document=reader.document,
                    current_pdf_page=current_page,
                    book_page_label=current_book_page(
                        page_map_service,
                        reader.document.document_id,
                        current_page,
                    ),
                    actions_enabled=(
                        page_map_actions_enabled and reader.document.status == DocumentStatus.ACTIVE
                    ),
                )
    if getattr(maintenance_tab, "open", True):
        with maintenance_tab:
            ui.header("Maintenance")
            _render_index_status(ui, context, reading_service, maintenance=True)
            if annotation_service is not None:
                render_notes_evidence_maintenance(
                    context,
                    ui=ui,
                    service=annotation_service,
                )
            if page_map_service is not None:
                render_page_map_maintenance(ui, context, page_map_service)


__all__ = ["render_reading_space_page"]

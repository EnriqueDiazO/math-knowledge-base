"""Streamlit UI for persistent PDF and web Documents associated with a Source."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePath
from typing import Any

from editor.pdf_preview import PdfPreviewPayload
from editor.pdf_preview import clear_pdf_preview
from editor.pdf_preview import pdf_preview_context
from editor.pdf_preview import render_pdf_preview
from editor.pdf_preview import store_pdf_preview
from editor.reading_space.source_entrypoints import render_reading_space_entrypoint
from editor.source_catalog.shared import CatalogUIContext
from editor.source_catalog.shared import safe_error_message
from editor.source_catalog.shared import split_values
from editor.source_catalog.state import begin_operation
from editor.source_catalog.state import finish_operation
from editor.source_catalog.state import state_key
from mathmongo.source_catalog.models import CopyrightStatus
from mathmongo.source_catalog.models import RedistributionPolicy
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceRights
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import DocumentStatus
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.models import normalize_web_url
from mathmongo.source_documents.service import DocumentOperationResult
from mathmongo.source_documents.service import DocumentOperationStatus
from mathmongo.source_documents.service import SourceDocumentService
from mathmongo.source_documents.storage import MAX_SOURCE_PDF_UPLOAD_BYTES
from mathmongo.source_documents.storage import SourceDocumentBlobStore

PDF_PREVIEW_NAMESPACE = "source_document"
DOCUMENT_PREVIEW_SUBJECT = state_key("document_preview_subject")
DOCUMENT_PAGE_SIZE = 10


def clear_source_document_preview(state: Any) -> None:
    """Clear only the Source Document viewer and its non-payload subject state."""
    clear_pdf_preview(state, PDF_PREVIEW_NAMESPACE)
    state.pop(DOCUMENT_PREVIEW_SUBJECT, None)


def uploaded_pdf_bytes(uploaded_file: Any) -> bytes:
    """Materialize and validate one bounded Streamlit PDF upload without opening a path."""
    if uploaded_file is None:
        return b""
    declared_size = getattr(uploaded_file, "size", None)
    if (
        isinstance(declared_size, int)
        and not isinstance(declared_size, bool)
        and declared_size > MAX_SOURCE_PDF_UPLOAD_BYTES
    ):
        raise ValueError(f"El PDF supera el límite de {MAX_SOURCE_PDF_UPLOAD_BYTES} bytes.")

    position = None
    if hasattr(uploaded_file, "read"):
        if hasattr(uploaded_file, "tell"):
            try:
                position = uploaded_file.tell()
            except (OSError, ValueError):
                position = None
        value = uploaded_file.read(MAX_SOURCE_PDF_UPLOAD_BYTES + 1)
        if position is not None and hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(position)
            except (OSError, ValueError):
                pass
    elif hasattr(uploaded_file, "getvalue"):
        value = uploaded_file.getvalue()
    else:
        raise TypeError("El archivo subido no expone bytes legibles.")

    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("El PDF subido debe contener bytes.")
    data = bytes(value)
    if not data:
        raise ValueError("El PDF subido está vacío.")
    if len(data) > MAX_SOURCE_PDF_UPLOAD_BYTES:
        raise ValueError(f"El PDF supera el límite de {MAX_SOURCE_PDF_UPLOAD_BYTES} bytes.")
    if not data.startswith(b"%PDF-"):
        raise ValueError("El PDF subido no tiene una cabecera %PDF- válida.")
    SourceDocumentBlobStore.prepare_pdf(data)
    return data


def uploaded_pdf_filename(uploaded_file: Any) -> str:
    """Return a safe leaf PDF filename from a Streamlit upload."""
    name = str(getattr(uploaded_file, "name", "") or "").strip()
    if (
        not name
        or PurePath(name).name != name
        or "\\" in name
        or not name.casefold().endswith(".pdf")
    ):
        raise ValueError("El archivo subido debe tener un nombre PDF simple.")
    return name


def _reference_choices(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    current_reference_id: str | None = None,
) -> tuple[list[str | None], dict[str, str]]:
    """Return a bounded list containing only References associated with this Source."""
    try:
        page = context.reference_repository.list(
            source_id=source.source_id,
            page=1,
            page_size=100,
        )
    except Exception as exc:
        ui.error(f"No se pudieron cargar las References: {safe_error_message(exc)}")
        return [None], {}
    labels = {
        reference.reference_id: (
            f"{reference.title or reference.bibtex.key or 'Untitled'} "
            f"({reference.reference_id}, {reference.status.value})"
        )
        for reference in page.items
        if source.source_id in reference.source_ids
    }
    choices: list[str | None] = [None, *labels]
    if current_reference_id is not None and current_reference_id not in labels:
        ui.warning(
            "La Reference guardada ya no está asociada con esta Source; "
            "selecciona una Reference válida o deja la asociación vacía."
        )
    if page.total > len(page.items):
        ui.warning("Hay más de 100 References asociadas; sólo se muestran las 100 más recientes.")
    return choices, labels


def _reference_input(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    key: str,
    current_reference_id: str | None = None,
) -> str | None:
    choices, labels = _reference_choices(
        ui,
        context,
        source,
        current_reference_id=current_reference_id,
    )
    selected_index = choices.index(current_reference_id) if current_reference_id in choices else 0
    return ui.selectbox(
        "Reference asociada (opcional)",
        choices,
        index=selected_index,
        format_func=lambda value: "Sin Reference" if value is None else labels[str(value)],
        key=key,
    )


def _metadata_inputs(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    key_prefix: str,
    title: str,
    description: str = "",
    language: str | None = None,
    tags: tuple[str, ...] | list[str] = (),
    rights: SourceRights | None = None,
    reference_id: str | None = None,
) -> dict[str, Any]:
    current_rights = rights or source.rights_default
    selected_reference = _reference_input(
        ui,
        context,
        source,
        key=state_key(key_prefix, "reference_id"),
        current_reference_id=reference_id,
    )
    entered_title = ui.text_input(
        "Título",
        value=title,
        key=state_key(key_prefix, "title"),
    )
    entered_description = ui.text_area(
        "Descripción",
        value=description,
        key=state_key(key_prefix, "description"),
    )
    entered_language = ui.text_input(
        "Idioma",
        value=language or "",
        key=state_key(key_prefix, "language"),
    )
    entered_tags = ui.text_area(
        "Tags (separados por comas o líneas)",
        value="\n".join(tags),
        key=state_key(key_prefix, "tags"),
    )
    copyright_values = tuple(item.value for item in CopyrightStatus)
    redistribution_values = tuple(item.value for item in RedistributionPolicy)
    copyright_status = ui.selectbox(
        "Copyright",
        copyright_values,
        index=copyright_values.index(current_rights.copyright_status.value),
        key=state_key(key_prefix, "copyright_status"),
    )
    redistribution = ui.selectbox(
        "Redistribución",
        redistribution_values,
        index=redistribution_values.index(current_rights.redistribution.value),
        key=state_key(key_prefix, "redistribution"),
    )
    license_text = ui.text_input(
        "Licencia",
        value=current_rights.license or "",
        key=state_key(key_prefix, "license"),
    )
    rights_notes = ui.text_area(
        "Notas de derechos",
        value=current_rights.notes or "",
        key=state_key(key_prefix, "rights_notes"),
    )
    return {
        "reference_id": selected_reference,
        "title": entered_title,
        "description": entered_description,
        "language": entered_language or None,
        "tags": split_values(entered_tags),
        "rights": SourceRights(
            copyright_status=copyright_status,
            redistribution=redistribution,
            license=license_text or None,
            notes=rights_notes or None,
        ),
    }


def _operation_token(
    context: CatalogUIContext,
    action: str,
    entity_id: str,
    payload: Any,
) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"{context.database_name}:{action}:{entity_id}:{digest}"


def _run_operation_once(
    ui: Any,
    *,
    operation: str,
    token: str,
    action: Any,
) -> DocumentOperationResult | None:
    if not begin_operation(ui.session_state, operation, token):
        ui.info("Esta operación de Document ya fue procesada.")
        return None
    result: DocumentOperationResult | None = None
    try:
        result = action()
        _render_operation_result(ui, result)
        return result
    except Exception as exc:
        ui.error(f"No se pudo completar la operación: {safe_error_message(exc)}")
        return None
    finally:
        finish_operation(
            ui.session_state,
            operation,
            token,
            succeeded=bool(result is not None and result.completed),
        )


def _render_operation_result(ui: Any, result: DocumentOperationResult) -> None:
    message = safe_error_message(result.message or result.status.value)
    if result.status in {DocumentOperationStatus.CREATED, DocumentOperationStatus.SUCCESS}:
        ui.success(message)
    elif result.status == DocumentOperationStatus.IDENTICAL:
        ui.info(message)
    elif result.status == DocumentOperationStatus.PARTIAL:
        ui.warning(message)
    else:
        ui.error(message)


def _preview_subject(context: CatalogUIContext, document: SourceDocument) -> dict[str, str]:
    if document.pdf is None:
        raise ValueError("El Document seleccionado no contiene un PDF.")
    version = document.pdf.current_version
    return {
        "database": context.database_name,
        "source_id": document.source_id,
        "document_id": document.document_id,
        "version_id": version.version_id,
        "sha256": version.sha256,
    }


def _preview_identity(subject: dict[str, str]) -> str:
    return pdf_preview_context(
        subject["database"],
        subject["source_id"],
        subject["document_id"],
        subject["version_id"],
        subject["sha256"],
    )


def _open_pdf_preview(
    ui: Any,
    context: CatalogUIContext,
    service: SourceDocumentService,
    document: SourceDocument,
) -> bool:
    clear_source_document_preview(ui.session_state)
    try:
        payload = service.read_pdf_document(document.document_id)
        if payload.document.source_id != document.source_id:
            raise ValueError("El PDF leído no pertenece a la Source seleccionada.")
        subject = _preview_subject(context, payload.document)
        observed_sha = hashlib.sha256(payload.pdf_bytes).hexdigest()
        if payload.sha256 != subject["sha256"] or observed_sha != subject["sha256"]:
            raise ValueError("La identidad SHA-256 del PDF no coincide.")
        preview = PdfPreviewPayload(
            pdf_bytes=payload.pdf_bytes,
            sha256=payload.sha256,
            file_name=payload.file_name,
            context_identity=_preview_identity(subject),
        )
        store_pdf_preview(ui.session_state, PDF_PREVIEW_NAMESPACE, preview)
        ui.session_state[DOCUMENT_PREVIEW_SUBJECT] = subject
    except Exception as exc:
        ui.error(f"No se pudo abrir el PDF interno: {safe_error_message(exc)}")
        return False
    return True


def _render_current_preview(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
) -> None:
    subject = ui.session_state.get(DOCUMENT_PREVIEW_SUBJECT)
    if not isinstance(subject, dict) or any(
        not isinstance(subject.get(field), str)
        for field in ("database", "source_id", "document_id", "version_id", "sha256")
    ):
        clear_source_document_preview(ui.session_state)
        return
    if subject["database"] != context.database_name or subject["source_id"] != source.source_id:
        clear_source_document_preview(ui.session_state)
        return
    ui.subheader("Vista previa PDF")
    rendered = render_pdf_preview(
        ui,
        ui.session_state,
        PDF_PREVIEW_NAMESPACE,
        context_identity=_preview_identity(subject),
        height=800,
    )
    if not rendered:
        ui.session_state.pop(DOCUMENT_PREVIEW_SUBJECT, None)


def _document_rows(documents: tuple[SourceDocument, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        row: dict[str, Any] = {
            "document_id": document.document_id,
            "kind": document.kind.value,
            "title": document.title,
            "reference_id": document.reference_id,
            "language": document.language,
            "tags": ", ".join(document.tags),
            "status": document.status.value,
            "updated_at": document.updated_at,
        }
        if document.pdf is not None:
            version = document.pdf.current_version
            row.update(
                {
                    "filename": version.original_filename,
                    "size_bytes": version.size_bytes,
                    "sha256": version.sha256,
                }
            )
        elif document.web is not None:
            row["url"] = document.web.url_normalized
        rows.append(row)
    return rows


def _render_metadata_editor(
    ui: Any,
    context: CatalogUIContext,
    service: SourceDocumentService,
    source: Source,
    document: SourceDocument,
    *,
    writes_enabled: bool,
) -> None:
    if not ui.checkbox(
        "Editar metadata",
        key=state_key("document_edit_open", document.document_id),
    ):
        return
    metadata = _metadata_inputs(
        ui,
        context,
        source,
        key_prefix=f"document_edit_{document.document_id}",
        title=document.title,
        description=document.description,
        language=document.language,
        tags=document.tags,
        rights=document.rights,
        reference_id=document.reference_id,
    )
    if not writes_enabled:
        ui.warning("La edición está deshabilitada hasta inicializar el catálogo Source.")
        return
    with ui.form(key=state_key("document_edit_form", document.document_id)):
        confirmed = ui.checkbox(
            f"Confirmo actualizar sólo {document.document_id} en {context.database_name}",
            key=state_key("document_edit_confirm", document.document_id),
        )
        submitted = ui.form_submit_button("Guardar metadata")
    if not submitted:
        return
    if not confirmed:
        ui.warning("Confirma la actualización de metadata antes de guardar.")
        return
    token = _operation_token(
        context,
        "update_document",
        document.document_id,
        {"updated_at": document.updated_at.isoformat(), **metadata},
    )
    _run_operation_once(
        ui,
        operation=f"update_document_{document.document_id}",
        token=token,
        action=lambda: service.update_document_metadata(document.document_id, metadata),
    )


def _render_document_actions(
    ui: Any,
    context: CatalogUIContext,
    service: SourceDocumentService,
    document: SourceDocument,
    *,
    writes_enabled: bool,
) -> None:
    if ui.button(
        "Comprobar integridad",
        key=state_key("document_integrity", document.document_id),
    ):
        try:
            inspection = service.inspect_document_integrity(document.document_id)
            if inspection.ok:
                ui.success("Integridad verificada.")
            else:
                issues = ", ".join(safe_error_message(issue) for issue in inspection.issues)
                ui.error(f"La comprobación de integridad detectó: {issues}")
        except Exception as exc:
            ui.error(f"No se pudo comprobar la integridad: {safe_error_message(exc)}")
    if not writes_enabled:
        return

    archive = document.status == DocumentStatus.ACTIVE
    action_label = "Archivar Document" if archive else "Reactivar Document"
    operation_name = "archive_document" if archive else "reactivate_document"
    with ui.form(key=state_key(operation_name, "form", document.document_id)):
        confirmed = ui.checkbox(
            f"Confirmo {action_label.casefold()} sólo en {context.database_name}",
            key=state_key(operation_name, "confirm", document.document_id),
        )
        submitted = ui.form_submit_button(action_label)
    if not submitted:
        return
    if not confirmed:
        ui.warning(f"Confirma la acción '{action_label}' antes de continuar.")
        return
    token = _operation_token(
        context,
        operation_name,
        document.document_id,
        document.updated_at.isoformat(),
    )
    action = (
        (lambda: service.archive_document(document.document_id))
        if archive
        else (lambda: service.reactivate_document(document.document_id))
    )
    _run_operation_once(
        ui,
        operation=f"{operation_name}_{document.document_id}",
        token=token,
        action=action,
    )


def _render_list(
    ui: Any,
    context: CatalogUIContext,
    service: SourceDocumentService,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    status_label = ui.selectbox(
        "Estado de Documents",
        ("All", *(item.value for item in DocumentStatus)),
        key=state_key("document_status_filter", source.source_id),
    )
    kind_label = ui.selectbox(
        "Tipo de Document",
        ("All", *(item.value for item in DocumentKind)),
        key=state_key("document_kind_filter", source.source_id),
    )
    page_number = int(
        ui.number_input(
            "Página de Documents",
            min_value=1,
            value=1,
            step=1,
            key=state_key("document_page", source.source_id),
        )
    )
    try:
        page = service.list_source_documents(
            source.source_id,
            page=page_number,
            page_size=DOCUMENT_PAGE_SIZE,
            status=None if status_label == "All" else status_label,
            kind=None if kind_label == "All" else kind_label,
        )
    except Exception as exc:
        ui.error(f"No se pudieron listar los Documents: {safe_error_message(exc)}")
        return
    ui.caption(f"{page.total} Documents · página {page.page} de {max(page.pages, 1)}")
    ui.dataframe(_document_rows(page.items), width="stretch", hide_index=True)
    for document in page.items:
        with ui.expander(
            f"{document.title} · {document.kind.value} · {document.status.value}",
            expanded=False,
        ):
            ui.write(
                {
                    "document_id": document.document_id,
                    "reference_id": document.reference_id,
                    "description": document.description,
                    "language": document.language,
                    "tags": document.tags,
                    "rights": document.rights.model_dump(mode="json"),
                    "created_at": document.created_at,
                    "updated_at": document.updated_at,
                }
            )
            if document.kind == DocumentKind.PDF:
                if ui.button(
                    "Abrir PDF",
                    key=state_key("document_open_pdf", document.document_id),
                ):
                    _open_pdf_preview(ui, context, service, document)
            elif document.web is not None:
                ui.link_button(
                    "Abrir recurso web",
                    document.web.url_normalized,
                )
            if render_reading_space_entrypoint(ui, document):
                clear_source_document_preview(ui.session_state)
                ui.rerun()
            _render_metadata_editor(
                ui,
                context,
                service,
                source,
                document,
                writes_enabled=writes_enabled,
            )
            _render_document_actions(
                ui,
                context,
                service,
                document,
                writes_enabled=writes_enabled,
            )


def _render_add_pdf(
    ui: Any,
    context: CatalogUIContext,
    service: SourceDocumentService,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    uploaded = ui.file_uploader(
        "Subir PDF",
        type=["pdf"],
        accept_multiple_files=False,
        max_upload_size=MAX_SOURCE_PDF_UPLOAD_BYTES // (1024 * 1024),
        key=state_key("document_add_pdf_upload", source.source_id),
    )
    if uploaded is None:
        ui.info("Selecciona un PDF para validar su metadata antes de guardarlo.")
        return
    try:
        filename = uploaded_pdf_filename(uploaded)
        pdf_bytes = uploaded_pdf_bytes(uploaded)
        prepared = SourceDocumentBlobStore.prepare_pdf(pdf_bytes)
    except (TypeError, ValueError) as exc:
        ui.error(safe_error_message(exc))
        return
    except Exception as exc:
        ui.error(f"No se pudo validar el PDF: {safe_error_message(exc)}")
        return
    ui.write(
        {
            "filename": filename,
            "size_bytes": prepared.size_bytes,
            "sha256": prepared.sha256,
            "mime_type": "application/pdf",
        }
    )
    key_prefix = f"document_add_pdf_{source.source_id}_{prepared.sha256[:16]}"
    metadata = _metadata_inputs(
        ui,
        context,
        source,
        key_prefix=key_prefix,
        title=PurePath(filename).stem,
    )
    if not writes_enabled:
        ui.warning("El alta está deshabilitada hasta inicializar el catálogo Source.")
        return
    with ui.form(key=state_key(key_prefix, "confirm_form")):
        confirmed = ui.checkbox(
            f"Confirmo guardar este PDF para {source.source_id} sólo en {context.database_name}",
            key=state_key(key_prefix, "confirm"),
        )
        submitted = ui.form_submit_button("Guardar PDF Document")
    if not submitted:
        return
    if not confirmed:
        ui.warning("Confirma el alta del PDF antes de guardarlo.")
        return
    token = _operation_token(
        context,
        "create_pdf_document",
        source.source_id,
        {"sha256": prepared.sha256, "filename": filename, **metadata},
    )
    result = _run_operation_once(
        ui,
        operation=f"create_pdf_document_{source.source_id}",
        token=token,
        action=lambda: service.create_pdf_document(
            source_id=source.source_id,
            pdf_bytes=pdf_bytes,
            original_filename=filename,
            **metadata,
        ),
    )
    if result is not None and result.completed and result.value is not None:
        _open_pdf_preview(ui, context, service, result.value)


def _render_add_web(
    ui: Any,
    context: CatalogUIContext,
    service: SourceDocumentService,
    source: Source,
    *,
    writes_enabled: bool,
) -> None:
    url_raw = ui.text_input(
        "URL HTTP(S)",
        key=state_key("document_add_web_url", source.source_id),
    )
    if not url_raw.strip():
        ui.info("Introduce una URL HTTP o HTTPS; MathMongo no realizará ninguna solicitud.")
        return
    try:
        normalized = normalize_web_url(url_raw)
    except ValueError as exc:
        ui.error(safe_error_message(exc))
        return
    ui.write({"url_normalized": normalized, "network_request": "not performed"})
    key_prefix = f"document_add_web_{source.source_id}"
    metadata = _metadata_inputs(
        ui,
        context,
        source,
        key_prefix=key_prefix,
        title=normalized,
    )
    if not writes_enabled:
        ui.warning("El alta está deshabilitada hasta inicializar el catálogo Source.")
        return
    with ui.form(key=state_key(key_prefix, "confirm_form")):
        confirmed = ui.checkbox(
            f"Confirmo guardar esta URL para {source.source_id} sólo en {context.database_name}",
            key=state_key(key_prefix, "confirm"),
        )
        submitted = ui.form_submit_button("Guardar Web Document")
    if not submitted:
        return
    if not confirmed:
        ui.warning("Confirma el alta del recurso web antes de guardarlo.")
        return
    token = _operation_token(
        context,
        "create_web_document",
        source.source_id,
        {"url": normalized, **metadata},
    )
    _run_operation_once(
        ui,
        operation=f"create_web_document_{source.source_id}",
        token=token,
        action=lambda: service.create_web_document(
            source_id=source.source_id,
            url_raw=url_raw,
            **metadata,
        ),
    )


def render_source_documents(
    ui: Any,
    context: CatalogUIContext,
    source: Source,
    *,
    writes_enabled: bool,
    service: SourceDocumentService | None = None,
) -> None:
    """Render LIST, ADD PDF, and ADD WEB without touching legacy concepts."""
    ui.subheader("D. Documents")
    document_service = service or SourceDocumentService(context.database)
    subject = ui.session_state.get(DOCUMENT_PREVIEW_SUBJECT)
    if isinstance(subject, dict) and (
        subject.get("database") != context.database_name
        or subject.get("source_id") != source.source_id
    ):
        clear_source_document_preview(ui.session_state)
    list_tab, pdf_tab, web_tab = ui.tabs(("LIST", "ADD PDF", "ADD WEB"))
    with list_tab:
        _render_list(
            ui,
            context,
            document_service,
            source,
            writes_enabled=writes_enabled,
        )
    with pdf_tab:
        _render_add_pdf(
            ui,
            context,
            document_service,
            source,
            writes_enabled=writes_enabled,
        )
    with web_tab:
        _render_add_web(
            ui,
            context,
            document_service,
            source,
            writes_enabled=writes_enabled,
        )
    _render_current_preview(ui, context, source)


__all__ = [
    "DOCUMENT_PREVIEW_SUBJECT",
    "PDF_PREVIEW_NAMESPACE",
    "clear_source_document_preview",
    "render_source_documents",
    "uploaded_pdf_bytes",
    "uploaded_pdf_filename",
]

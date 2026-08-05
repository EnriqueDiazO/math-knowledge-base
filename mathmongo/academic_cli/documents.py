"""Read-only Document and Reading Space commands through their domain services."""

from __future__ import annotations

import argparse
from typing import Any

from mathmongo.academic_cli.common import AcademicCliError
from mathmongo.academic_cli.common import ExitCode
from mathmongo.academic_cli.common import add_common_options
from mathmongo.academic_cli.common import close_client
from mathmongo.academic_cli.common import connect_database
from mathmongo.academic_cli.common import diagnostic
from mathmongo.academic_cli.common import emit
from mathmongo.reading_space.service import ReadingSpaceService
from mathmongo.source_documents.repository import SourceDocumentRepository
from mathmongo.source_documents.service import SourceDocumentService


def _document_row(document: Any) -> dict[str, Any]:
    version = document.pdf.current_version if document.pdf is not None else None
    return {
        "document_id": document.document_id,
        "source_id": document.source_id,
        "reference_id": document.reference_id or "",
        "kind": document.kind.value,
        "title": document.title,
        "status": document.status.value,
        "sha256": version.sha256 if version is not None else "",
        "size_bytes": version.size_bytes if version is not None else "",
        "updated_at": document.updated_at,
    }


def _document_list(args: argparse.Namespace) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        page = SourceDocumentRepository(database).list(
            args.source,
            page=args.page,
            page_size=args.limit,
            status=args.status,
            kind=args.kind,
        )
        payload = {"items": [_document_row(item) for item in page.items], "page": page.page, "total": page.total}
        if args.output == "json":
            emit(args, payload)
        else:
            emit(
                args,
                payload["items"],
                columns=("document_id", "kind", "title", "status", "sha256", "size_bytes", "updated_at"),
            )
            diagnostic(args, f"Base: {database.name}; {page.total} Documents para {args.source}.")
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _document_show(args: argparse.Namespace) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        document = SourceDocumentRepository(database).get_by_id(args.document_id)
        if document is None:
            raise AcademicCliError(f"Documento no encontrado: {args.document_id}", ExitCode.NOT_FOUND)
        emit(args, document, columns=("document_id", "source_id", "kind", "title", "status", "updated_at"))
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _document_verify(args: argparse.Namespace) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        inspection = SourceDocumentService(database).inspect_document_integrity(args.document_id)
        if "document_missing" in inspection.issues:
            raise AcademicCliError(f"Documento no encontrado: {args.document_id}", ExitCode.NOT_FOUND)
        payload = {"document_id": inspection.document_id, "ok": inspection.ok, "issues": inspection.issues}
        emit(args, payload, columns=("document_id", "ok", "issues"))
        return ExitCode.SUCCESS if inspection.ok else ExitCode.FILE_MEDIA
    finally:
        close_client(client)


def _reading_list(args: argparse.Namespace) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        result = ReadingSpaceService(database).list_readable_documents(
            user_scope=args.user_scope,
            page=args.page,
            page_size=args.limit,
        )
        if not result.completed or result.value is None:
            raise AcademicCliError(result.message or "No se pudo listar Reading Space.", ExitCode.CONNECTION)
        page = result.value
        items = [
            {
                **_document_row(item.document),
                "reading_status": item.state.status.value if item.state is not None else "unread",
                "current_page": item.state.current_page if item.state is not None else "",
            }
            for item in page.items
        ]
        payload = {"items": items, "page": page.page, "total": page.total}
        if args.output == "json":
            emit(args, payload)
        else:
            emit(
                args,
                items,
                columns=("document_id", "title", "source_id", "kind", "reading_status", "current_page"),
            )
            diagnostic(args, f"Base: {database.name}; {page.total} documentos legibles.")
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _reading_show(args: argparse.Namespace) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        result = ReadingSpaceService(database).get_reader_context(
            args.document_id,
            user_scope=args.user_scope,
        )
        if result.status.value == "not_found":
            raise AcademicCliError(f"Documento no encontrado: {args.document_id}", ExitCode.NOT_FOUND)
        if result.value is None:
            raise AcademicCliError(result.message or "No se pudo abrir el contexto de lectura.")
        context = result.value
        payload = {
            "document": _document_row(context.document),
            "source": {"source_id": context.source.source_id, "name": context.source.name},
            "reference_id": context.reference.reference_id if context.reference else None,
            "effective_status": context.effective_status.value,
            "reading_state": context.reading_state,
            "openable": context.openable,
        }
        emit(args, payload)
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _add_paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--limit", type=int, default=50)


def install_document_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Install only implemented read-only Document and Reading Space commands."""
    document = subparsers.add_parser("document", help="Consulta Documents y su integridad sin escribir.")
    document_commands = document.add_subparsers(dest="document_command", required=True)
    listing = document_commands.add_parser("list", help="Lista Documents de una Source.")
    listing.add_argument("--source", required=True)
    _add_paging(listing)
    listing.add_argument("--status")
    listing.add_argument("--kind", choices=("pdf", "web"))
    add_common_options(listing)
    listing.set_defaults(academic_handler=_document_list)
    show = document_commands.add_parser("show", help="Muestra metadatos de un Document.")
    show.add_argument("document_id")
    add_common_options(show)
    show.set_defaults(academic_handler=_document_show)
    verify = document_commands.add_parser("verify", help="Verifica metadatos y blob sin modificarlo.")
    verify.add_argument("document_id")
    add_common_options(verify)
    verify.set_defaults(academic_handler=_document_verify)

    reading = subparsers.add_parser("reading", help="Consulta el estado persistente de lectura.")
    reading_commands = reading.add_subparsers(dest="reading_command", required=True)
    reading_list = reading_commands.add_parser("list", help="Lista documentos del Reading Space.")
    _add_paging(reading_list)
    reading_list.add_argument("--user-scope", default="local")
    add_common_options(reading_list)
    reading_list.set_defaults(academic_handler=_reading_list)
    reading_show = reading_commands.add_parser("show", help="Muestra el contexto de lectura de un Document.")
    reading_show.add_argument("document_id")
    reading_show.add_argument("--user-scope", default="local")
    add_common_options(reading_show)
    reading_show.set_defaults(academic_handler=_reading_show)

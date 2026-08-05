"""Read-only Source and Reference commands using the catalog repositories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mathmongo.academic_cli.common import AcademicCliError
from mathmongo.academic_cli.common import ExitCode
from mathmongo.academic_cli.common import add_common_options
from mathmongo.academic_cli.common import close_client
from mathmongo.academic_cli.common import connect_database
from mathmongo.academic_cli.common import diagnostic
from mathmongo.academic_cli.common import emit
from mathmongo.academic_cli.common import require_apply_confirmation
from mathmongo.academic_cli.common import validate_write_options
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_catalog.service import CatalogResultStatus
from mathmongo.source_catalog.service import SourceCatalogService


def _source_row(source: Any) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "name": source.name,
        "type": source.source_type.value,
        "status": source.status.value,
        "tags": source.tags,
        "updated_at": source.updated_at,
    }


def _reference_row(reference: Any) -> dict[str, Any]:
    return {
        "reference_id": reference.reference_id,
        "title": reference.title or "",
        "type": reference.reference_type.value,
        "year": reference.year or reference.year_raw or "",
        "sources": reference.source_ids,
        "status": reference.status.value,
        "updated_at": reference.updated_at,
    }


def _source_list(args: argparse.Namespace, *, search: str | None = None) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        repository = SourceRepository(database)
        page = (
            repository.search(
                search,
                page=args.page,
                page_size=args.limit,
                status=args.status,
                source_type=args.source_type,
                tag=args.tag,
            )
            if search is not None
            else repository.list(
                page=args.page,
                page_size=args.limit,
                status=args.status,
                source_type=args.source_type,
                tag=args.tag,
            )
        )
        payload = {"items": [_source_row(item) for item in page.items], "page": page.page, "total": page.total}
        if args.output == "json":
            emit(args, payload)
        else:
            emit(args, payload["items"], columns=("source_id", "name", "type", "status", "tags", "updated_at"))
            diagnostic(args, f"Base: {database.name}; {page.total} Sources.")
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _source_show(args: argparse.Namespace) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        source = SourceRepository(database).get_by_id(args.source_id)
        if source is None:
            raise AcademicCliError(f"Source no encontrada: {args.source_id}", ExitCode.NOT_FOUND)
        emit(args, source, columns=("source_id", "name", "source_type", "status", "tags", "updated_at"))
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _read_text_argument(path_value: str, *, option: str) -> str:
    """Read a UTF-8 text input file without treating its path as persisted data."""
    try:
        return Path(path_value).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AcademicCliError(f"No se pudo leer {option}: {path_value}", ExitCode.FILE_MEDIA) from exc


def _json_input(path_value: str) -> dict[str, Any]:
    """Load one small domain JSON object from a file or explicit standard input."""
    try:
        text = sys.stdin.read() if path_value == "-" else _read_text_argument(path_value, option="--from-json")
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AcademicCliError("--from-json debe contener un objeto JSON válido.") from exc
    if not isinstance(payload, dict):
        raise AcademicCliError("--from-json debe contener un objeto JSON de Source.")
    forbidden = {"_id", "source_id", "created_at", "updated_at", "archived_at"} & set(payload)
    if forbidden:
        raise AcademicCliError(
            "--from-json no acepta campos internos: " + ", ".join(sorted(forbidden))
        )
    return payload


def _source_values(args: argparse.Namespace, *, initial: Source | None = None) -> Source:
    """Build the real Source domain model from flags/files or a domain JSON input."""
    values = initial.model_dump(mode="python") if initial is not None else {}
    if args.from_json:
        values.update(_json_input(args.from_json))
    if args.name is not None:
        values["name"] = args.name
    if args.source_type is not None:
        values["source_type"] = args.source_type
    definition = args.definition
    if args.definition_file:
        definition = _read_text_argument(args.definition_file, option="--definition-file")
    if definition is not None:
        values["description"] = definition
    if args.tag is not None:
        values["tags"] = args.tag
    try:
        return Source.model_validate(values)
    except Exception as exc:
        raise AcademicCliError(f"Source inválida: {exc}") from exc


def _duplicate_payload(matches: list[Any]) -> list[dict[str, Any]]:
    """Expose only stable duplicate evidence in the operation plan."""
    return [
        {
            "entity_id": item.entity_id,
            "classification": item.classification.value,
            "warnings": list(item.warnings),
        }
        for item in matches
    ]


def _catalog_result_code(result: Any) -> ExitCode:
    """Map shared catalog outcomes to the documented CLI exit vocabulary."""
    if result.status == CatalogResultStatus.NOT_FOUND:
        return ExitCode.NOT_FOUND
    if result.status == CatalogResultStatus.CONFLICT:
        return ExitCode.CONFLICT
    return ExitCode.VALIDATION


def _source_add(args: argparse.Namespace) -> int:
    """Preview then optionally create a Source through SourceCatalogService."""
    validate_write_options(args)
    candidate = _source_values(args)
    client = None
    try:
        client, database, _config = connect_database(args)
        service = SourceCatalogService(database)
        duplicates = service.detect_source_duplicates(candidate)
        plan = {
            "operation": "source.add",
            "database": database.name,
            "source": _source_row(candidate),
            "duplicates": _duplicate_payload(duplicates),
            "would_write": True,
        }
        blocking = [item for item in duplicates if item.classification.value in {"exact", "strong"}]
        if not getattr(args, "apply", False):
            emit(args, plan)
            return ExitCode.CONFLICT if blocking and not args.allow_duplicate else ExitCode.SUCCESS
        if args.output != "json":
            emit(args, plan)
        if blocking and not args.allow_duplicate:
            raise AcademicCliError(
                "La vista previa detectó duplicados exactos/fuertes; usa --allow-duplicate "
                "sólo tras revisarlos.",
                ExitCode.CONFLICT,
            )
        require_apply_confirmation(args, operation="source add")
        result = service.create_source(candidate, allow_duplicate=args.allow_duplicate)
        if not result.persisted or result.value is None:
            raise AcademicCliError(
                result.message or "; ".join(result.errors) or "No se creó la Source.",
                _catalog_result_code(result),
            )
        emit(
            args,
            {"plan": plan, "status": result.status.value, "source": _source_row(result.value)},
        )
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _source_edit(args: argparse.Namespace) -> int:
    """Preview only supplied fields and delegate a partial update to the shared service."""
    validate_write_options(args)
    client = None
    try:
        client, database, _config = connect_database(args)
        service = SourceCatalogService(database)
        current = service.sources.get_by_id(args.source_id)
        if current is None:
            raise AcademicCliError(f"Source no encontrada: {args.source_id}", ExitCode.NOT_FOUND)
        candidate = _source_values(args, initial=current)
        candidate_dump = candidate.model_dump(mode="python")
        current_dump = current.model_dump(mode="python")
        mutable_fields = ("name", "source_type", "description", "tags")
        changes = {
            field: candidate_dump[field]
            for field in mutable_fields
            if candidate_dump[field] != current_dump[field]
        }
        plan = {
            "operation": "source.edit",
            "database": database.name,
            "source_id": args.source_id,
            "changes": changes,
            "duplicates": _duplicate_payload(
                service.detect_source_duplicates(candidate, exclude_source_id=args.source_id)
            ),
            "would_write": bool(changes),
        }
        if not changes:
            emit(args, plan)
            return ExitCode.SUCCESS
        duplicates = service.detect_source_duplicates(candidate, exclude_source_id=args.source_id)
        if not getattr(args, "apply", False):
            emit(args, plan)
            return ExitCode.SUCCESS
        if args.output != "json":
            emit(args, plan)
        require_apply_confirmation(args, operation="source edit")
        result = service.update_source(
            args.source_id,
            changes,
            allow_duplicate=args.allow_duplicate,
        )
        if not result.persisted or result.value is None:
            raise AcademicCliError(
                result.message or "; ".join(result.errors) or "No se actualizó la Source.",
                _catalog_result_code(result),
            )
        emit(
            args,
            {
                "plan": plan,
                "status": result.status.value,
                "source": _source_row(result.value),
                "duplicates": _duplicate_payload(duplicates),
            },
        )
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _reference_list(args: argparse.Namespace, *, search: str | None = None) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        repository = ReferenceRepository(database)
        page = (
            repository.search(
                search,
                page=args.page,
                page_size=args.limit,
                status=args.status,
                source_id=args.source,
            )
            if search is not None
            else repository.list(
                page=args.page,
                page_size=args.limit,
                status=args.status,
                source_id=args.source,
                reference_type=args.reference_type,
                year=args.year,
            )
        )
        payload = {"items": [_reference_row(item) for item in page.items], "page": page.page, "total": page.total}
        if args.output == "json":
            emit(args, payload)
        else:
            emit(args, payload["items"], columns=("reference_id", "title", "type", "year", "sources", "status", "updated_at"))
            diagnostic(args, f"Base: {database.name}; {page.total} References.")
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _reference_show(args: argparse.Namespace) -> int:
    client = None
    try:
        client, database, _config = connect_database(args)
        reference = ReferenceRepository(database).get_by_id(args.reference_id)
        if reference is None:
            raise AcademicCliError(f"Reference no encontrada: {args.reference_id}", ExitCode.NOT_FOUND)
        emit(args, reference, columns=("reference_id", "title", "reference_type", "source_ids", "status", "updated_at"))
        return ExitCode.SUCCESS
    finally:
        close_client(client)


def _add_paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--limit", type=int, default=50)


def install_catalog_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Install only implemented, read-only catalog commands."""
    source = subparsers.add_parser("source", help="Consulta Sources mediante el catálogo compartido.")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    source_list = source_commands.add_parser("list", help="Lista Sources sin modificar MongoDB.")
    _add_paging(source_list)
    source_list.add_argument("--status")
    source_list.add_argument("--source-type")
    source_list.add_argument("--tag")
    add_common_options(source_list)
    source_list.set_defaults(academic_handler=lambda args: _source_list(args))
    source_search = source_commands.add_parser("search", help="Busca Sources sin modificar MongoDB.")
    source_search.add_argument("term")
    _add_paging(source_search)
    source_search.add_argument("--status")
    source_search.add_argument("--source-type")
    source_search.add_argument("--tag")
    add_common_options(source_search)
    source_search.set_defaults(academic_handler=lambda args: _source_list(args, search=args.term))
    source_show = source_commands.add_parser("show", help="Muestra una Source por ID estable.")
    source_show.add_argument("source_id")
    add_common_options(source_show)
    source_show.set_defaults(academic_handler=_source_show)
    source_add = source_commands.add_parser("add", help="Planifica o crea una Source validada.")
    source_add.add_argument("--name")
    source_add.add_argument("--source-type")
    definition = source_add.add_mutually_exclusive_group()
    definition.add_argument("--definition")
    definition.add_argument("--definition-file")
    source_add.add_argument("--tag", action="append")
    source_add.add_argument("--from-json")
    source_add.add_argument("--allow-duplicate", action="store_true")
    source_add.add_argument("--apply", action="store_true")
    source_add.add_argument("--yes", action="store_true")
    add_common_options(source_add)
    source_add.set_defaults(academic_handler=_source_add)
    source_edit = source_commands.add_parser("edit", help="Planifica o edita sólo campos Source indicados.")
    source_edit.add_argument("source_id")
    source_edit.add_argument("--name")
    source_edit.add_argument("--source-type")
    edit_definition = source_edit.add_mutually_exclusive_group()
    edit_definition.add_argument("--definition")
    edit_definition.add_argument("--definition-file")
    source_edit.add_argument("--tag", action="append")
    source_edit.add_argument("--from-json")
    source_edit.add_argument("--allow-duplicate", action="store_true")
    source_edit.add_argument("--apply", action="store_true")
    source_edit.add_argument("--yes", action="store_true")
    add_common_options(source_edit)
    source_edit.set_defaults(academic_handler=_source_edit)

    reference = subparsers.add_parser("reference", help="Consulta References mediante el catálogo compartido.")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    reference_list = reference_commands.add_parser("list", help="Lista References sin modificar MongoDB.")
    _add_paging(reference_list)
    reference_list.add_argument("--status")
    reference_list.add_argument("--source")
    reference_list.add_argument("--reference-type")
    reference_list.add_argument("--year", type=int)
    add_common_options(reference_list)
    reference_list.set_defaults(academic_handler=lambda args: _reference_list(args))
    reference_search = reference_commands.add_parser("search", help="Busca References sin modificar MongoDB.")
    reference_search.add_argument("term")
    _add_paging(reference_search)
    reference_search.add_argument("--status")
    reference_search.add_argument("--source")
    add_common_options(reference_search)
    reference_search.set_defaults(academic_handler=lambda args: _reference_list(args, search=args.term))
    reference_show = reference_commands.add_parser("show", help="Muestra una Reference por ID estable.")
    reference_show.add_argument("reference_id")
    add_common_options(reference_show)
    reference_show.set_defaults(academic_handler=_reference_show)

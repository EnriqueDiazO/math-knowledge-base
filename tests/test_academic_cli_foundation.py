"""Parsing, clean output, and preview safety for the academic CLI foundation."""

from __future__ import annotations

import argparse
import json

import pytest

from mathmongo.academic_cli import catalog
from mathmongo.academic_cli.common import AcademicCliError
from mathmongo.academic_cli.common import ExitCode
from mathmongo.academic_cli.common import emit
from mathmongo.academic_cli.common import require_apply_confirmation
from mathmongo.cli import build_parser


def test_catalog_commands_expose_only_implemented_read_only_operations() -> None:
    """Keep the parser tree honest: it advertises only ready read commands."""
    parser = build_parser()

    source = parser.parse_args(
        ["source", "list", "--database", "temporary", "--output", "json", "--quiet"]
    )
    reference = parser.parse_args(
        ["reference", "search", "Fredholm", "--database", "temporary"]
    )
    document = parser.parse_args(
        ["document", "list", "--source", "src_example", "--database", "temporary"]
    )
    reading = parser.parse_args(
        ["reading", "show", "doc_example", "--output", "json", "--database", "temporary"]
    )

    assert source.command == "source"
    assert source.source_command == "list"
    assert source.database == "temporary"
    assert source.output == "json"
    assert reference.reference_command == "search"
    assert document.document_command == "list"
    assert reading.reading_command == "show"
    assert reading.output == "json"
    assert callable(source.academic_handler)
    assert callable(reference.academic_handler)
    assert callable(document.academic_handler)
    assert callable(reading.academic_handler)


def test_json_output_has_no_table_or_diagnostic_noise(capsys: pytest.CaptureFixture[str]) -> None:
    """Ensure script output stays valid JSON on stdout."""
    args = argparse.Namespace(output="json")

    emit(args, {"items": [{"source_id": "src_test", "name": "Teoría"}], "total": 1})

    assert json.loads(capsys.readouterr().out) == {
        "items": [{"name": "Teoría", "source_id": "src_test"}],
        "total": 1,
    }


def test_yes_without_apply_is_rejected_before_any_write() -> None:
    """Reject unsafe automation flags before a handler can persist anything."""
    args = argparse.Namespace(apply=False, yes=True, verbose=False, quiet=False)

    with pytest.raises(AcademicCliError) as caught:
        require_apply_confirmation(args, operation="crear Source")

    assert caught.value.code == ExitCode.VALIDATION
    assert "--yes" in str(caught.value)


def test_preview_does_not_request_confirmation_or_write() -> None:
    """Retain planning as the default behavior."""
    args = argparse.Namespace(apply=False, yes=False, verbose=False, quiet=False)

    assert require_apply_confirmation(args, operation="crear Source") is False


def test_catalog_handlers_do_not_contain_direct_mongo_writes() -> None:
    """Keep handlers on the shared service/repository boundary."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "mathmongo" / "academic_cli"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    for persistence_call in (".insert_one(", ".update_one(", ".delete_one(", ".replace_one("):
        assert persistence_call not in source


def test_source_add_preview_validates_and_never_invokes_the_create_service(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep Source creation in planning mode until --apply is explicitly present."""
    calls = {"created": 0}

    class _Database:
        name = "temporary_cli_test"

    class _Service:
        def __init__(self, _database: object) -> None:
            pass

        def detect_source_duplicates(self, _candidate: object) -> list[object]:
            return []

        def create_source(self, *_args: object, **_kwargs: object) -> object:
            calls["created"] += 1
            raise AssertionError("preview must not create a Source")

    monkeypatch.setattr(catalog, "connect_database", lambda _args: (None, _Database(), object()))
    monkeypatch.setattr(catalog, "SourceCatalogService", _Service)
    args = argparse.Namespace(
        name="Source de prueba",
        source_type=None,
        definition=None,
        definition_file=None,
        tag=None,
        from_json=None,
        apply=False,
        yes=False,
        allow_duplicate=False,
        output="json",
        quiet=False,
        verbose=False,
    )

    assert catalog._source_add(args) == ExitCode.SUCCESS
    assert calls["created"] == 0
    assert json.loads(capsys.readouterr().out)["would_write"] is True


def test_source_add_rejects_yes_without_apply_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not even open MongoDB when an invalid automation combination is supplied."""
    monkeypatch.setattr(catalog, "connect_database", lambda _args: pytest.fail("must not connect"))
    args = argparse.Namespace(
        name="Source de prueba",
        source_type=None,
        definition=None,
        definition_file=None,
        tag=None,
        from_json=None,
        apply=False,
        yes=True,
        allow_duplicate=False,
        output="table",
        quiet=False,
        verbose=False,
    )

    with pytest.raises(AcademicCliError, match="--yes"):
        catalog._source_add(args)

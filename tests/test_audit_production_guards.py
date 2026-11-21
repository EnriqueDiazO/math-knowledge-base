"""Verify invariant failures remain safe when Python removes assertions."""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from editor import database_import_page
from editor.utils import cleanup_exports
from editor.utils import db_update
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from test_database_update import _fixture_archive
from test_database_update import _fixture_database
from test_database_update import _Mongo
from test_source_catalog_migration_bootstrap import _apply
from test_source_catalog_migration_bootstrap import _database
from test_source_catalog_migration_bootstrap import _harness
from test_source_catalog_migration_bootstrap import _manifest

# Reuse the actual corpus fixtures; absence stays a skip, never a synthetic approval.
from test_source_catalog_migration_bootstrap import authoritative_export
from test_source_catalog_migration_bootstrap import authoritative_plan
from test_source_catalog_migration_bootstrap import complete_decisions


def test_cleanup_missing_backup_directory_preserves_the_source(tmp_path, monkeypatch):
    """Even a broken backup collaborator cannot turn move into destructive cleanup."""
    root = tmp_path / "exports"
    root.mkdir()
    original = root / "keep.pdf"
    original.write_bytes(b"keep every byte")
    monkeypatch.setattr(cleanup_exports, "ALLOWED_CLEANUP_DIRS", (root,))
    monkeypatch.setattr(cleanup_exports, "CLEANUP_LOG_FILE", tmp_path / "cleanup.log")
    monkeypatch.setattr(cleanup_exports, "_new_backup_dir", lambda: None)
    result = cleanup_exports.delete_files_safely([original], move_to_backup=True)
    assert original.read_bytes() == b"keep every byte"
    assert result["moved_files"] == result["deleted_files"] == 0
    assert len(result["errors"]) == 1
    assert "validated backup directory" in result["errors"][0]


def test_invalid_update_selection_is_reported_without_a_write(tmp_path, monkeypatch):
    """An invalid UI mode/selection cannot reach a write handler, also under -O."""
    messages = []
    ui = SimpleNamespace(header=lambda *_a: None, caption=lambda *_a: None,
                         radio=lambda *_a, **_k: "invalid persisted mode",
                         file_uploader=lambda *_a, **_k: object(), divider=lambda: None,
                         error=messages.append)
    @contextmanager
    def staged(_upload):
        yield tmp_path / "not-read.zip"
    monkeypatch.setattr(database_import_page, "_staged_upload", staged)
    monkeypatch.setattr(database_import_page, "inspect_update_archive", lambda _path: {})
    monkeypatch.setattr(database_import_page, "_render_archive_preview", lambda *_a: None)
    writes = []
    monkeypatch.setattr(database_import_page, "_render_update_mode", lambda *_a, **_k: writes.append(True))
    database_import_page.render_database_import_page(ui, object())
    assert writes == []
    assert len(messages) == 1 and "Seleccione una base" in messages[0]


def test_unknown_update_action_stops_before_document_mutation(tmp_path, monkeypatch):
    """A corrupted post-analysis action cannot be interpreted as a valid conflict."""
    root = tmp_path / "data"
    archive = tmp_path / "input.zip"
    _fixture_archive(archive)
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(root)
    plan = db_update.analyze_database_update(archive, mongo, source_document_blob_store=store, data_root=root)
    corrupted = replace(plan, actions=(replace(plan.actions[0], classification="unknown"),))
    monkeypatch.setattr(db_update, "analyze_database_update", lambda *_a, **_k: corrupted)
    before = {name: list(database[name].find({})) for name in database.list_collection_names()}
    with pytest.raises(db_update.DatabaseUpdateApplyError) as error:
        db_update.apply_database_update(archive, mongo, corrupted, conflict_policies={}, backup_root=tmp_path / "backup", source_document_blob_store=store, data_root=root)
    assert isinstance(error.value.__cause__, db_update.StaleUpdatePlanError)
    assert "Unsupported document classification" in str(error.value.__cause__)
    assert all(list(database[name].find({})) == value for name, value in before.items())
    assert not any(operation.kind.startswith("document_") for operation in error.value.operations)


def test_missing_expected_catalog_blocks_before_reconciliation(authoritative_export, authoritative_plan, complete_decisions, monkeypatch):
    """A missing prepared catalog is a typed blocker, with no Source/Reference writes."""
    database = _database(authoritative_export)
    harness = _harness(database)
    completed = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)
    assert completed.outcome.value == "applied"
    manifest = _manifest(database)
    before = {name: list(database[name].find({})) for name in database.list_collection_names()}
    monkeypatch.setattr(harness.engine, "_resolve_existing", lambda **_kwargs: (manifest, None))
    result = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)
    assert result.outcome.value == "blocked"
    assert any("prepared manifest and expected catalog are required" in error for error in result.errors)
    assert {name: list(database[name].find({})) for name in database.list_collection_names()} == before

"""Opt-in end-to-end proof for a completely fresh MathMongo database."""

from __future__ import annotations

import json
import os
import re
import zipfile
from datetime import datetime
from datetime import timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo import monitoring

from editor.db.concept_edit_service import ConceptEditStatus
from editor.db.concept_edit_service import update_concept_fields_preserving_identity
from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.helpers.concept_builders import build_concept_metadata
from editor.helpers.managed_source_selection import can_save_with_managed_source
from editor.helpers.managed_source_selection import load_active_sources
from editor.helpers.managed_source_selection import resolve_active_source
from editor.source_catalog.shared import build_catalog_context
from editor.source_catalog.shared import initialize_catalog_indexes
from editor.source_catalog.workflows import execute_add_source
from editor.utils import db_export
from editor.utils import db_import
from editor.utils.db_update import ExistingDatabaseTarget
from editor.utils.db_update import analyze_database_update
from editor.utils.db_update import apply_database_update
from mathmongo.config import resolve_config
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from schemas.schemas import ConceptoBase
from schemas.schemas import TipoTitulo

RUN_ENVIRONMENT_VARIABLE = "MATHMONGO_RUN_FRESH_DB_E2E"
RUN_ID_ENVIRONMENT_VARIABLE = "MATHMONGO_FRESH_DB_E2E_RUN_ID"
DATABASE_PREFIXES = ("mathmongo_e2e_fresh_", "mathmongo_e2e_import_")
PROTECTED_DATABASES = frozenset({"admin", "config", "local", "mathmongo", "mathv0"})
MUTATING_COMMANDS = frozenset(
    {"create", "createIndexes", "delete", "dropDatabase", "insert", "update"}
)


class _WriteAudit(monitoring.CommandListener):
    """Record the target database of every collection-mutating command."""

    def __init__(self) -> None:
        self.database_names: list[str] = []

    def started(self, event: monitoring.CommandStartedEvent) -> None:
        if event.command_name in MUTATING_COMMANDS:
            self.database_names.append(event.database_name)

    def succeeded(self, _event: monitoring.CommandSucceededEvent) -> None:
        return None

    def failed(self, _event: monitoring.CommandFailedEvent) -> None:
        return None


def _database_names() -> tuple[str, str]:
    run_id = os.environ.get(RUN_ID_ENVIRONMENT_VARIABLE, "").strip()
    if not run_id:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")
        run_id = f"{timestamp}_{uuid4().hex[:12]}"
    if re.fullmatch(r"[a-z0-9_]{12,40}", run_id) is None:
        raise ValueError(f"{RUN_ID_ENVIRONMENT_VARIABLE} has an unsafe value")
    names = tuple(f"{prefix}{run_id}" for prefix in DATABASE_PREFIXES)
    assert len(set(names)) == 2
    assert all(name.casefold() not in PROTECTED_DATABASES for name in names)
    assert all(len(name.encode("utf-8")) <= 63 for name in names)
    return names[0], names[1]


def _archive_documents(archive_path: Path, collection: str) -> list[dict]:
    with zipfile.ZipFile(archive_path, "r") as archive:
        metadata_members = [
            name for name in archive.namelist() if name.endswith("/metadata.json")
        ]
        assert len(metadata_members) == 1
        base_name = metadata_members[0].split("/", 1)[0]
        member = f"{base_name}/collections/{collection}.json"
        return json.loads(archive.read(member).decode("utf-8"))


@pytest.mark.skipif(
    os.environ.get(RUN_ENVIRONMENT_VARIABLE) != "1",
    reason=f"set {RUN_ENVIRONMENT_VARIABLE}=1 to use two temporary MongoDB databases",
)
def test_fresh_database_source_concept_edit_export_import_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the supported lifecycle while confining writes to two fresh databases."""
    fresh_name, import_name = _database_names()
    allowed_database_names = {fresh_name, import_name}
    write_audit = _WriteAudit()
    client = MongoClient(
        resolve_config().mongo_uri,
        serverSelectionTimeoutMS=3000,
        event_listeners=[write_audit],
    )
    temporary_root: Path | None = None
    cleanup_authorized = False

    try:
        client.admin.command("ping")
        databases_before = set(client.list_database_names())
        assert allowed_database_names.isdisjoint(databases_before)
        cleanup_authorized = True
        print(f"fresh_database={fresh_name}")
        print(f"import_database={import_name}")

        fresh_database = client[fresh_name]
        fresh_target = ExistingDatabaseTarget(client=client, db=fresh_database)
        catalog_context = build_catalog_context(fresh_name, fresh_target)
        catalog_plan = initialize_catalog_indexes(
            catalog_context,
            confirmation_text=fresh_name,
            confirmed=True,
        )
        assert not catalog_plan.missing
        assert not catalog_plan.conflicts
        fresh_target.ensure_indexes({"concepts", "latex_documents"})

        assert fresh_database["sources"].count_documents({}) == 0
        assert fresh_database["concepts"].count_documents({}) == 0
        assert fresh_database["latex_documents"].count_documents({}) == 0

        source_outcome = execute_add_source(
            catalog_context.service,
            Source(name="Fresh lifecycle source"),
        )
        assert source_outcome.source_created is True
        assert source_outcome.references == ()
        created_source = source_outcome.source_result.value
        assert created_source is not None
        assert fresh_database["sources"].count_documents({}) == 1
        persisted_source = SourceRepository(fresh_database).get_by_id(created_source.source_id)
        assert persisted_source is not None
        assert persisted_source.source_id == created_source.source_id
        assert persisted_source.name == created_source.name
        assert persisted_source.status == created_source.status

        source_options = load_active_sources(catalog_context.source_repository)
        assert len(source_options) == 1
        assert source_options[0].source_id == created_source.source_id
        selected_source = resolve_active_source(
            catalog_context.source_repository,
            created_source.source_id,
        )
        assert selected_source is not None
        assert selected_source.source_id == created_source.source_id
        assert selected_source.name == created_source.name
        assert can_save_with_managed_source(selected_source) is True
        missing_source_id = "src_00000000-0000-4000-8000-000000000099"
        assert (
            resolve_active_source(catalog_context.source_repository, missing_source_id)
            is None
        )
        assert fresh_database["sources"].count_documents({}) == 1

        created_at = datetime.now(timezone.utc)
        concept = ConceptoBase(
            id="definition:fresh_lifecycle",
            tipo="definicion",
            titulo="Fresh lifecycle before edit",
            tipo_titulo=TipoTitulo.ninguno,
            contenido_latex=r"x = x",
            categorias=["E2E"],
            source=selected_source.name,
            source_id=selected_source.source_id,
            fecha_creacion=created_at,
            ultima_actualizacion=created_at,
        )
        insert_concept_with_latex_atomic(
            fresh_database,
            concept.id,
            concept.source,
            build_concept_metadata(concept),
            concept.contenido_latex,
            created_at,
        )
        assert fresh_database["sources"].count_documents({}) == 1

        identity = {"id": concept.id, "source": concept.source}
        concept_before_edit = fresh_database["concepts"].find_one(identity)
        latex_before_edit = fresh_database["latex_documents"].find_one(identity)
        assert concept_before_edit is not None
        assert latex_before_edit is not None
        assert concept_before_edit["source_id"] == selected_source.source_id
        assert latex_before_edit["source_id"] == selected_source.source_id

        edited_at = datetime.now(timezone.utc)
        edited_title = "Fresh lifecycle after edit"
        edited_latex = r"x = x \quad \text{(edited)}"
        edit_result = update_concept_fields_preserving_identity(
            fresh_database,
            concept_id=concept.id,
            source=concept.source,
            expected_source_id=concept.source_id,
            changes={"titulo": edited_title, "comentario": "edited by the E2E contract"},
            contenido_latex=edited_latex,
            now=edited_at,
        )
        assert edit_result.status is ConceptEditStatus.SUCCESS

        concept_after_edit = fresh_database["concepts"].find_one(identity)
        latex_after_edit = fresh_database["latex_documents"].find_one(identity)
        assert concept_after_edit is not None
        assert latex_after_edit is not None
        assert concept_after_edit["_id"] == concept_before_edit["_id"]
        assert latex_after_edit["_id"] == latex_before_edit["_id"]
        assert concept_after_edit["id"] == concept.id
        assert concept_after_edit["source"] == selected_source.name
        assert concept_after_edit["source_id"] == selected_source.source_id
        assert latex_after_edit["id"] == concept.id
        assert latex_after_edit["source"] == selected_source.name
        assert latex_after_edit["source_id"] == selected_source.source_id
        assert concept_after_edit["titulo"] == edited_title
        assert latex_after_edit["contenido_latex"] == edited_latex
        assert fresh_database["concepts"].count_documents(identity) == 1
        assert fresh_database["latex_documents"].count_documents(identity) == 1

        print(
            "minimal_documents="
            + json.dumps(
                {
                    "concepts": {
                        "id": concept_after_edit["id"],
                        "source": concept_after_edit["source"],
                        "source_id": concept_after_edit["source_id"],
                        "titulo": concept_after_edit["titulo"],
                    },
                    "latex_documents": {
                        "id": latex_after_edit["id"],
                        "source": latex_after_edit["source"],
                        "source_id": latex_after_edit["source_id"],
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

        with TemporaryDirectory(prefix="mathmongo-fresh-e2e-") as temporary_directory:
            temporary_root = Path(temporary_directory)
            data_root = temporary_root / "data"
            monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", temporary_root / "legacy")
            monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", temporary_root / "media")
            monkeypatch.setattr(db_import, "DATA_DIR", data_root)
            blob_store = SourceDocumentBlobStore(data_root)

            archive_path = db_export.export_database_to_zip(
                fresh_target,
                temporary_root / "exports",
                source_document_blob_store=blob_store,
            )
            assert archive_path.is_file()
            inspection = db_import.inspect_export_zip(archive_path)
            assert inspection["collections"]["concepts"] == 1
            assert inspection["collections"]["latex_documents"] == 1
            exported_concept = _archive_documents(archive_path, "concepts")[0]
            exported_latex = _archive_documents(archive_path, "latex_documents")[0]
            assert exported_concept["source"] == selected_source.name
            assert exported_concept["source_id"] == selected_source.source_id
            assert exported_latex["source"] == selected_source.name
            assert exported_latex["source_id"] == selected_source.source_id

            import_database = client[import_name]
            import_target = ExistingDatabaseTarget(client=client, db=import_database)
            assert import_name not in client.list_database_names()

            import_report = db_import.import_zip_into_database(
                archive_path,
                import_target,
                source_document_blob_store=blob_store,
                new_database=True,
            )
            assert import_report.catalog_inserted["sources"] == 1
            assert import_database["sources"].count_documents({}) == 1
            imported_source = SourceRepository(import_database).get_by_id(
                selected_source.source_id
            )
            assert imported_source is not None
            assert imported_source.source_id == selected_source.source_id
            assert imported_source.name == selected_source.name
            assert imported_source.status == selected_source.status

            imported_concept = import_database["concepts"].find_one(identity)
            imported_latex = import_database["latex_documents"].find_one(identity)
            assert imported_concept is not None
            assert imported_latex is not None
            assert imported_concept["source"] == selected_source.name
            assert imported_concept["source_id"] == selected_source.source_id
            assert imported_latex["source"] == selected_source.name
            assert imported_latex["source_id"] == selected_source.source_id
            assert imported_concept["titulo"] == edited_title
            assert imported_latex["contenido_latex"] == edited_latex
            assert import_database["concepts"].count_documents(identity) == 1
            assert import_database["latex_documents"].count_documents(identity) == 1
            assert import_database["sources"].count_documents({}) == 1

            update_plan = analyze_database_update(
                archive_path,
                import_target,
                source_document_blob_store=blob_store,
                data_root=data_root,
            )
            assert update_plan.can_apply is True
            update_concept = next(
                action for action in update_plan.actions if action.collection == "concepts"
            )
            update_latex = next(
                action
                for action in update_plan.actions
                if action.collection == "latex_documents"
            )
            assert update_concept.incoming["source_id"] == selected_source.source_id
            assert update_latex.incoming["source_id"] == selected_source.source_id

            update_report = apply_database_update(
                archive_path,
                import_target,
                update_plan,
                conflict_policies={},
                backup_root=temporary_root / "update-backups",
                source_document_blob_store=blob_store,
                data_root=data_root,
            )
            assert update_report.inserted == 0
            assert update_report.replaced == 0
            updated_concept = import_database["concepts"].find_one(identity)
            updated_latex = import_database["latex_documents"].find_one(identity)
            assert updated_concept is not None
            assert updated_latex is not None
            assert updated_concept["source_id"] == selected_source.source_id
            assert updated_latex["source_id"] == selected_source.source_id
            assert import_database["sources"].count_documents({}) == 1

            print(
                "round_trip="
                + json.dumps(
                    {
                        "source": imported_concept["source"],
                        "source_id": imported_concept["source_id"],
                        "preserved": ["id", "source", "source_id"],
                        "lost": [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    finally:
        cleanup_error: Exception | None = None
        try:
            if cleanup_authorized:
                client.drop_database(fresh_name)
                client.drop_database(import_name)
                databases_after = set(client.list_database_names())
                assert allowed_database_names.isdisjoint(databases_after)
                assert set(write_audit.database_names) == allowed_database_names
                assert temporary_root is None or not temporary_root.exists()
            else:
                assert write_audit.database_names == []
        except Exception as exc:  # pragma: no cover - preserves cleanup diagnostics
            cleanup_error = exc
        finally:
            client.close()
        if cleanup_error is not None:
            raise cleanup_error

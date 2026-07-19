"""Opt-in E2E proof for linking a legacy pair in one temporary database."""

from __future__ import annotations

import os
import re
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from uuid import uuid4

import pytest
from pymongo import MongoClient
from pymongo import monitoring

from editor.db.concept_repository import insert_concept_with_latex_atomic
from editor.db.concept_source_link_service import ConceptSourceLinkStatus
from editor.db.concept_source_link_service import link_concept_to_existing_managed_source
from editor.helpers.concept_builders import build_concept_metadata
from editor.source_catalog.shared import build_catalog_context
from editor.source_catalog.workflows import execute_add_source
from editor.utils.db_update import ExistingDatabaseTarget
from mathmongo.config import resolve_config
from mathmongo.source_catalog.models import Source
from schemas.schemas import ConceptoBase
from schemas.schemas import TipoTitulo

RUN_ENVIRONMENT_VARIABLE = "MATHMONGO_RUN_LEGACY_LINK_E2E"
DATABASE_PREFIX = "mathmongo_e2e_legacy_link_"
PROTECTED_DATABASES = frozenset({"admin", "config", "local", "mathmongo", "mathv0"})
MUTATING_COMMANDS = frozenset(
    {"create", "createIndexes", "delete", "dropDatabase", "insert", "update"}
)


class _WriteAudit(monitoring.CommandListener):
    """Record every database receiving a mutating command from this client."""

    def __init__(self) -> None:
        self.database_names: list[str] = []

    def started(self, event: monitoring.CommandStartedEvent) -> None:
        if event.command_name in MUTATING_COMMANDS:
            self.database_names.append(event.database_name)

    def succeeded(self, _event: monitoring.CommandSucceededEvent) -> None:
        return None

    def failed(self, _event: monitoring.CommandFailedEvent) -> None:
        return None


def _temporary_database_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")
    run_id = f"{timestamp}_{uuid4().hex[:12]}"
    assert re.fullmatch(r"[a-z0-9_]{12,40}", run_id) is not None
    name = f"{DATABASE_PREFIX}{run_id}"
    assert name.casefold() not in PROTECTED_DATABASES
    assert len(name.encode("utf-8")) <= 63
    return name


@pytest.mark.skipif(
    os.environ.get(RUN_ENVIRONMENT_VARIABLE) != "1",
    reason=f"set {RUN_ENVIRONMENT_VARIABLE}=1 to use one temporary MongoDB database",
)
def test_link_legacy_concept_to_existing_source_in_temporary_database() -> None:
    """Create, link, verify idempotence, and remove one isolated E2E database."""
    database_name = _temporary_database_name()
    write_audit = _WriteAudit()
    client = MongoClient(
        resolve_config().mongo_uri,
        serverSelectionTimeoutMS=3000,
        event_listeners=[write_audit],
    )
    cleanup_authorized = False

    try:
        client.admin.command("ping")
        assert database_name not in client.list_database_names()
        cleanup_authorized = True
        database = client[database_name]
        target = ExistingDatabaseTarget(client=client, db=database)
        catalog_context = build_catalog_context(database_name, target)

        source_outcome = execute_add_source(
            catalog_context.service,
            Source(name="Current managed Source name"),
        )
        assert source_outcome.source_created
        managed_source = source_outcome.source_result.value
        assert managed_source is not None
        source_before_link = database.sources.find_one(
            {"source_id": managed_source.source_id}
        )
        assert source_before_link is not None

        created_at = datetime.now(timezone.utc)
        concept = ConceptoBase(
            id="definition:legacy_link_e2e",
            tipo="definicion",
            titulo="Legacy link E2E",
            tipo_titulo=TipoTitulo.ninguno,
            contenido_latex=r"G = \{e\}",
            categorias=["E2E"],
            source="Historical snapshot name",
            fecha_creacion=created_at,
            ultima_actualizacion=created_at,
        )
        insert_concept_with_latex_atomic(
            database,
            concept.id,
            concept.source,
            build_concept_metadata(concept),
            concept.contenido_latex,
            created_at,
        )

        identity = {"id": concept.id, "source": concept.source}
        concept_before_link = database.concepts.find_one(identity)
        latex_before_link = database.latex_documents.find_one(identity)
        assert concept_before_link is not None
        assert latex_before_link is not None
        assert "source_id" not in concept_before_link
        assert "source_id" not in latex_before_link

        result = link_concept_to_existing_managed_source(
            database,
            concept_id=concept.id,
            source=concept.source,
            expected_source_id=None,
            target_source_id=managed_source.source_id,
        )
        assert result.status is ConceptSourceLinkStatus.SUCCESS

        concept_after_link = database.concepts.find_one(identity)
        latex_after_link = database.latex_documents.find_one(identity)
        assert concept_after_link is not None
        assert latex_after_link is not None
        assert concept_after_link == {
            **concept_before_link,
            "source_id": managed_source.source_id,
        }
        assert latex_after_link == {
            **latex_before_link,
            "source_id": managed_source.source_id,
        }
        assert concept_after_link["_id"] == concept_before_link["_id"]
        assert latex_after_link["_id"] == latex_before_link["_id"]
        assert concept_after_link["id"] == concept.id
        assert concept_after_link["source"] == concept.source
        assert latex_after_link["id"] == concept.id
        assert latex_after_link["source"] == concept.source
        assert f"{concept_after_link['id']}@{concept_after_link['source']}" == (
            f"{concept.id}@{concept.source}"
        )

        source_after_link = database.sources.find_one(
            {"source_id": managed_source.source_id}
        )
        assert source_after_link == source_before_link
        untouched_source_snapshot = deepcopy(source_after_link)

        second_result = link_concept_to_existing_managed_source(
            database,
            concept_id=concept.id,
            source=concept.source,
            expected_source_id=managed_source.source_id,
            target_source_id=managed_source.source_id,
        )
        assert second_result.status is ConceptSourceLinkStatus.ALREADY_LINKED
        assert database.concepts.find_one(identity) == concept_after_link
        assert database.latex_documents.find_one(identity) == latex_after_link
        assert database.sources.find_one(
            {"source_id": managed_source.source_id}
        ) == untouched_source_snapshot

        dependency_collections = {
            "relations",
            "knowledge_graph_maps",
            "media_assets",
            "concept_evidence_links",
        }
        assert dependency_collections.isdisjoint(database.list_collection_names())
        for collection_name in dependency_collections:
            assert database[collection_name].count_documents({}) == 0
    finally:
        cleanup_error: Exception | None = None
        try:
            if cleanup_authorized:
                client.drop_database(database_name)
                assert database_name not in client.list_database_names()
                assert set(write_audit.database_names) == {database_name}
            else:
                assert write_audit.database_names == []
        except Exception as exc:  # pragma: no cover - preserves cleanup diagnostics
            cleanup_error = exc
        finally:
            client.close()
        if cleanup_error is not None:
            raise cleanup_error

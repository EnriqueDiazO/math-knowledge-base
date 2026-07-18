"""Opt-in MongoDB/XDG end-to-end coverage for safe database updates."""

# ruff: noqa: D103

from __future__ import annotations

import os
from datetime import datetime
from datetime import timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pymongo import MongoClient

from editor.utils import db_export
from editor.utils.db_update import ConflictPolicy
from editor.utils.db_update import ExistingDatabaseTarget
from editor.utils.db_update import analyze_database_update
from editor.utils.db_update import apply_database_update
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared

pytestmark = pytest.mark.skipif(
    os.environ.get("MATHMONGO_RUN_MONGO_E2E") != "1",
    reason="set MATHMONGO_RUN_MONGO_E2E=1 to use a local temporary MongoDB database",
)


def _portable_pdf_documents(ordinal: int, pdf_bytes: bytes) -> tuple[dict, dict, dict, str]:
    fixed = datetime(2026, 7, 18, 12, ordinal, tzinfo=timezone.utc)
    suffix = f"{ordinal:012d}"
    source = Source(
        source_id=f"src_00000000-0000-4000-8000-{suffix}",
        name=f"E2E source {ordinal}",
        created_at=fixed,
        updated_at=fixed,
    )
    reference = Reference(
        reference_id=f"ref_00000000-0000-4000-8000-{suffix}",
        source_ids=[source.source_id],
        title=f"E2E reference {ordinal}",
        created_at=fixed,
        updated_at=fixed,
    )
    prepared = SourceDocumentBlobStore.prepare_pdf(pdf_bytes)
    version = pdf_version_from_prepared(
        prepared,
        original_filename=f"e2e-{ordinal}.pdf",
        version_id=f"dver_00000000-0000-4000-8000-{suffix}",
        created_at=fixed,
    )
    document = SourceDocument(
        document_id=f"doc_00000000-0000-4000-8000-{suffix}",
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind=DocumentKind.PDF,
        title=f"E2E PDF {ordinal}",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
        created_at=fixed,
        updated_at=fixed,
    )
    source_payload = {"_id": f"source-{ordinal}", **source.model_dump(mode="python")}
    reference_payload = {
        "_id": f"reference-{ordinal}",
        **reference.model_dump(mode="python"),
    }
    document_payload = {"_id": f"document-{ordinal}", **document.model_dump(mode="python")}
    return source_payload, reference_payload, document_payload, prepared.logical_path


def _latex(storage_id: str, identity: str, content: str) -> dict:
    return {
        "_id": storage_id,
        "id": identity,
        "source": "e2e",
        "contenido_latex": content,
    }


def test_database_update_e2e_with_temporary_mongo_and_xdg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI")
    mongo_uri = mongo_uri or "mongodb://localhost:27017"
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    suffix = uuid4().hex[:12]
    source_name = f"codex_update_source_{suffix}"
    target_name = f"codex_update_target_{suffix}"
    data_root = tmp_path / "xdg-data" / "mathmongo"
    backup_root = data_root / "backups"
    media_root = data_root / "media"
    blob_store = SourceDocumentBlobStore(data_root)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", tmp_path / "absent-legacy")
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", media_root)

    first_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    second_pdf = b"%PDF-1.4\n2 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    source_1, reference_1, document_1, first_logical = _portable_pdf_documents(1, first_pdf)
    source_2, reference_2, document_2, second_logical = _portable_pdf_documents(2, second_pdf)
    source_db = client[source_name]
    target_db = client[target_name]

    try:
        source_db["latex_documents"].insert_many(
            [
                _latex("same", "same", "same"),
                _latex("conflict", "conflict", "backup"),
                _latex("new", "new", "insert"),
            ]
        )
        source_db["sources"].insert_many([source_1, source_2])
        source_db["references"].insert_many([reference_1, reference_2])
        source_db["source_documents"].insert_many([document_1, document_2])
        source_db["future_collection"].insert_one({"_id": "future", "value": 1})
        source_db.create_collection("future_empty")

        target_db["latex_documents"].insert_many(
            [
                _latex("same", "same", "same"),
                _latex("conflict", "conflict", "current"),
                _latex("local", "local", "keep"),
            ]
        )
        target_db["sources"].insert_one(source_1)
        target_db["references"].insert_one(reference_1)
        target_db["source_documents"].insert_one(document_1)
        target_db["local_only_collection"].insert_one({"_id": "local", "keep": True})

        first_prepared = SourceDocumentBlobStore.prepare_pdf(first_pdf)
        second_prepared = SourceDocumentBlobStore.prepare_pdf(second_pdf)
        blob_store.publish(first_prepared)
        blob_store.publish(second_prepared)
        assert first_prepared.logical_path == first_logical
        assert second_prepared.logical_path == second_logical
        media_root.mkdir(parents=True, mode=0o700)
        (media_root / "existing.png").write_bytes(b"existing-image")
        (media_root / "new.png").write_bytes(b"new-image")

        archive = db_export.export_database_to_zip(
            ExistingDatabaseTarget(client, source_db),
            tmp_path / "exports",
            source_document_blob_store=blob_store,
            include_all_collections=True,
        )
        blob_store.path_for_sha(second_prepared.sha256).unlink()
        (media_root / "new.png").unlink()

        target = ExistingDatabaseTarget(client, target_db)
        plan = analyze_database_update(
            archive,
            target,
            source_document_blob_store=blob_store,
            data_root=data_root,
        )
        policies = {item.token: ConflictPolicy.KEEP_CURRENT for item in plan.conflicts}
        assert plan.can_apply
        assert plan.totals["blobs_new"] == 1
        assert plan.totals["blobs_existing"] == 1
        assert plan.totals["media_new"] == 1
        assert plan.totals["media_existing"] == 1

        first_report = apply_database_update(
            archive,
            target,
            plan,
            conflict_policies=policies,
            backup_root=backup_root,
            source_document_blob_store=blob_store,
            data_root=data_root,
        )
        assert first_report.backup_path.is_file()
        assert first_report.blobs_created == 1
        assert first_report.media_created == 1
        assert target_db["local_only_collection"].find_one({"_id": "local"})["keep"] is True
        assert target_db["latex_documents"].find_one({"_id": "local"}) is not None
        assert (
            target_db["latex_documents"].find_one({"_id": "conflict"})["contenido_latex"]
            == "current"
        )
        assert target_db["future_collection"].count_documents({}) == 1
        assert "future_empty" in target_db.list_collection_names()
        assert target_db["future_empty"].count_documents({}) == 0
        assert target_db["source_documents"].count_documents({}) == 2
        assert blob_store.path_for_sha(second_prepared.sha256).read_bytes() == second_pdf
        assert (media_root / "new.png").read_bytes() == b"new-image"

        second_plan = analyze_database_update(
            archive,
            target,
            source_document_blob_store=blob_store,
            data_root=data_root,
        )
        second_policies = {
            item.token: ConflictPolicy.KEEP_CURRENT for item in second_plan.conflicts
        }
        second_report = apply_database_update(
            archive,
            target,
            second_plan,
            conflict_policies=second_policies,
            backup_root=backup_root,
            source_document_blob_store=blob_store,
            data_root=data_root,
        )
        assert second_report.inserted == 0
        assert second_report.replaced == 0
        assert second_report.blobs_created == 0
        assert second_report.media_created == 0
        assert target_db["local_only_collection"].count_documents({}) == 1
    finally:
        client.drop_database(source_name)
        client.drop_database(target_name)
        assert source_name not in client.list_database_names()
        assert target_name not in client.list_database_names()
        client.close()

"""Focused coverage for safe updates of existing databases."""

# ruff: noqa: D101,D102,D103,D107

from __future__ import annotations

import json
import zipfile
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps

from editor import database_import_page
from editor.utils import db_export
from editor.utils import db_import
from editor.utils import db_update
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_documents.models import DocumentKind
from mathmongo.source_documents.models import PdfDocument
from mathmongo.source_documents.models import SourceDocument
from mathmongo.source_documents.storage import SourceDocumentBlobStore
from mathmongo.source_documents.storage import pdf_version_from_prepared


class _Cursor(list):
    def max_time_ms(self, _milliseconds: int):
        return self

    def limit(self, count: int):
        return _Cursor(self[:count])

    def close(self) -> None:
        return None


class _Collection:
    def __init__(self, database: _Database, name: str, documents=None) -> None:
        self.database = database
        self.name = name
        self.full_name = f"{database.name}.{name}"
        self.documents = [deepcopy(item) for item in (documents or [])]
        self.exists = documents is not None
        self.insert_calls = 0
        self.replace_calls = 0
        self.delete_calls = 0
        self.indexes = [{"name": "_id_", "key": {"_id": 1}}]

    @staticmethod
    def _values(value, parts: tuple[str, ...]) -> list[object]:
        if not parts:
            return [value]
        if isinstance(value, list):
            return [result for child in value for result in _Collection._values(child, parts)]
        if not isinstance(value, dict) or parts[0] not in value:
            return []
        return _Collection._values(value[parts[0]], parts[1:])

    @classmethod
    def _matches(cls, document: dict, query: dict) -> bool:
        return all(
            expected in cls._values(document, tuple(field.split(".")))
            for field, expected in query.items()
        )

    def find(self, query: dict) -> _Cursor:
        return _Cursor(
            deepcopy(document) for document in self.documents if self._matches(document, query)
        )

    def find_one(self, query: dict):
        return next(
            (deepcopy(document) for document in self.documents if self._matches(document, query)),
            None,
        )

    def count_documents(self, query: dict) -> int:
        return sum(self._matches(document, query) for document in self.documents)

    def insert_one(self, document: dict):
        self.exists = True
        self.insert_calls += 1
        self.documents.append(deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("_id"))

    def replace_one(self, query: dict, document: dict, *, upsert: bool):
        self.exists = True
        self.replace_calls += 1
        for index, current in enumerate(self.documents):
            if self._matches(current, query):
                self.documents[index] = deepcopy(document)
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            self.documents.append(deepcopy(document))
            return SimpleNamespace(
                matched_count=0, modified_count=0, upserted_id=document.get("_id")
            )
        return SimpleNamespace(matched_count=0, modified_count=0)

    def delete_one(self, query: dict):
        self.delete_calls += 1
        for index, current in enumerate(self.documents):
            if self._matches(current, query):
                self.documents.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def list_indexes(self):
        return _Cursor(deepcopy(self.indexes))

    def create_index(self, keys, *, name: str | None = None, **options):
        self.exists = True
        name = name or "_".join(field for field, _direction in keys)
        if not any(item["name"] == name for item in self.indexes):
            self.indexes.append({"name": name, "key": dict(keys), **options})
        return name


class _Database:
    def __init__(self, name: str, collections: dict[str, list[dict]]) -> None:
        self.name = name
        self._collections: dict[str, _Collection] = {
            collection: _Collection(self, collection, documents)
            for collection, documents in collections.items()
        }
        self.create_calls = 0
        self.drop_calls = 0

    def __getitem__(self, name: str) -> _Collection:
        if name not in self._collections:
            self._collections[name] = _Collection(self, name)
        return self._collections[name]

    def list_collection_names(self) -> list[str]:
        return sorted(name for name, collection in self._collections.items() if collection.exists)

    def create_collection(self, name: str) -> None:
        self.create_calls += 1
        self[name].exists = True

    def drop_collection(self, name: str) -> None:
        self.drop_calls += 1
        self._collections.pop(name, None)


class _Client:
    def __init__(self, databases: dict[str, _Database]) -> None:
        self.databases = databases

    def __getitem__(self, name: str) -> _Database:
        return self.databases[name]

    def list_database_names(self) -> list[str]:
        return sorted(self.databases)


class _Mongo:
    def __init__(
        self, database: _Database, *, databases: dict[str, _Database] | None = None
    ) -> None:
        self.db = database
        self.client = _Client(databases or {database.name: database})
        self.ensure_indexes_calls = 0

    def ensure_indexes(self, collection_names: set[str] | None = None) -> None:
        self.ensure_indexes_calls += 1


def _latex(storage_id: str, identity: str, value: str) -> dict:
    return {
        "_id": storage_id,
        "id": identity,
        "source": "fixture",
        "contenido_latex": value,
    }


def _write_archive(
    path: Path,
    collections: dict[str, list[dict]],
    *,
    generic: set[str] = frozenset(),
    media: dict[str, bytes] | None = None,
    blobs: dict[str, bytes] | None = None,
    metadata_overrides: dict | None = None,
) -> None:
    base = "mathkb_export_update_test"
    media = media or {}
    blobs = blobs or {}
    encodings = {name: db_update.EXTENDED_JSON_ENCODING for name in collections if name in generic}
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "MathV0",
        "collections": {name: len(documents) for name, documents in collections.items()},
        "collection_encodings": encodings,
        "media_files": {name: len(data) for name, data in media.items()},
        "source_document_blobs": {
            name: {
                "sha256": __import__("hashlib").sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
            for name, data in blobs.items()
        },
    }
    metadata.update(metadata_overrides or {})
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{base}/metadata.json", json.dumps(metadata))
        for name, documents in collections.items():
            payload = (
                bson_json_dumps(documents, json_options=CANONICAL_JSON_OPTIONS)
                if name in generic
                else json.dumps(documents)
            )
            archive.writestr(f"{base}/collections/{name}.json", payload)
        for name, data in media.items():
            archive.writestr(f"{base}/{name}", data)
        for name, data in blobs.items():
            archive.writestr(f"{base}/{name}", data)


@pytest.fixture
def configured_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_root = tmp_path / "xdg-data" / "mathmongo"
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", data_root / "missing-media")
    monkeypatch.setattr(db_update, "get_backups_dir", lambda: data_root / "backups")
    return data_root


def _fixture_database() -> _Database:
    return _Database(
        "MathV0",
        {
            "latex_documents": [
                _latex("same", "same", "same"),
                _latex("conflict", "conflict", "local"),
                _latex("local", "local-only", "keep"),
            ],
            "local_only_collection": [{"_id": "local-generic", "value": "keep"}],
        },
    )


def _fixture_archive(path: Path, *, media: dict[str, bytes] | None = None) -> None:
    _write_archive(
        path,
        {
            "latex_documents": [
                _latex("same", "same", "same"),
                _latex("conflict", "conflict", "backup"),
                _latex("new", "new", "insert"),
            ],
            "future_collection": [{"_id": "future", "value": 1}],
            "future_empty": [],
        },
        generic={"future_collection", "future_empty"},
        media=media,
    )


def _portable_pdf_fixture(pdf_bytes: bytes) -> tuple[dict, dict, dict, str]:
    fixed = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    source = Source(
        source_id="src_00000000-0000-4000-8000-000000000201",
        name="Update fixture",
        created_at=fixed,
        updated_at=fixed,
    )
    reference = Reference(
        reference_id="ref_00000000-0000-4000-8000-000000000202",
        source_ids=[source.source_id],
        title="Update PDF",
        created_at=fixed,
        updated_at=fixed,
    )
    prepared = SourceDocumentBlobStore.prepare_pdf(pdf_bytes)
    version = pdf_version_from_prepared(
        prepared,
        original_filename="update.pdf",
        version_id="dver_00000000-0000-4000-8000-000000000203",
        created_at=fixed,
    )
    document = SourceDocument(
        document_id="doc_00000000-0000-4000-8000-000000000204",
        source_id=source.source_id,
        reference_id=reference.reference_id,
        kind=DocumentKind.PDF,
        title="Update PDF",
        pdf=PdfDocument(versions=[version], current_version_id=version.version_id),
        created_at=fixed,
        updated_at=fixed,
    )
    source_payload = source.model_dump(mode="python")
    source_payload["_id"] = "source-storage"
    reference_payload = reference.model_dump(mode="python")
    reference_payload["_id"] = "reference-storage"
    document_payload = document.model_dump(mode="python")
    document_payload["_id"] = "document-storage"
    return source_payload, reference_payload, document_payload, prepared.logical_path


def test_existing_database_selector_includes_mathv0_and_blocks_system_databases() -> None:
    mathv0 = _fixture_database()
    active = _Database("working", {})
    mongo = _Mongo(
        active,
        databases={
            "admin": _Database("admin", {}),
            "config": _Database("config", {}),
            "local": _Database("local", {}),
            "MathV0": mathv0,
            "working": active,
        },
    )

    assert database_import_page.list_existing_update_databases(mongo) == ["MathV0", "working"]
    assert db_update.bind_existing_database(mongo, "MathV0").db is mathv0


def test_create_mode_requires_absent_name_but_allows_absent_exact_mathv0() -> None:
    current = _Database("working", {})
    mongo = _Mongo(current)

    assert database_import_page.validate_new_database_target(mongo, "MathV0") == "MathV0"
    with pytest.raises(ValueError, match="does not exist"):
        database_import_page.validate_new_database_target(mongo, "working")
    with pytest.raises(ValueError, match="protected"):
        database_import_page.validate_new_database_target(mongo, "admin")
    with pytest.raises(ValueError, match="refuses an existing"):
        db_import.import_zip_into_database(
            Path("missing.zip"),
            mongo,
            new_database=True,
        )


def test_dry_run_classifies_merge_without_writes(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "update.zip"
    _fixture_archive(archive)
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    before_names = database.list_collection_names()

    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )

    latex = next(item for item in plan.collection_plans if item.name == "latex_documents")
    assert (latex.identical, latex.new, latex.conflicts, latex.invalid) == (1, 1, 1, 0)
    assert next(item for item in plan.collection_plans if item.name == "future_collection").new == 1
    assert plan.can_apply is True
    assert database.list_collection_names() == before_names
    assert database.create_calls == 0
    assert all(collection.insert_calls == 0 for collection in database._collections.values())


def test_dry_run_accepts_historical_persisted_concepts_and_their_relations(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    concept = {
        "_id": "legacy-concept-storage",
        "id": "legacy_001",
        "source": "LegacySource",
        "tipo": "definicion",
        "categorias": ["legacy"],
        "referencia": {
            "tipo_referencia": "libro",
            "fuente": "Historical source",
        },
    }
    relation = {
        "_id": "legacy-relation-storage",
        "desde": "legacy_001@LegacySource",
        "hasta": "legacy_001@LegacySource",
        "tipo": "equivalente",
    }
    archive = tmp_path / "historical-concepts.zip"
    _write_archive(archive, {"concepts": [concept], "relations": [relation]})

    plan = db_update.analyze_database_update(
        archive,
        _Mongo(_Database("MathV0", {})),
        source_document_blob_store=SourceDocumentBlobStore(configured_paths),
        data_root=configured_paths,
    )

    concepts = next(item for item in plan.collection_plans if item.name == "concepts")
    relations = next(item for item in plan.collection_plans if item.name == "relations")
    assert (concepts.new, concepts.invalid) == (1, 0)
    assert (relations.new, relations.invalid) == (1, 0)
    assert plan.blocking_issues == ()
    incoming = next(action.incoming for action in plan.actions if action.collection == "concepts")
    assert "contenido_latex" not in incoming
    assert "autor" not in incoming["referencia"]


def test_update_ui_groups_repeated_blocking_issues() -> None:
    issues = (
        db_update.UpdateIssue("concepts", "first", "Invalid historical concept"),
        db_update.UpdateIssue("concepts", "second", "Invalid historical concept"),
        db_update.UpdateIssue("relations", "third", "Invalid endpoint"),
    )

    assert database_import_page._summarize_blocking_issues(issues) == (
        "concepts: Invalid historical concept (2 casos)",
        "relations: Invalid endpoint",
    )


def test_dry_run_blocks_conflicting_managed_index(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    fixed = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
    source = Source(
        source_id="src_00000000-0000-4000-8000-000000000301",
        name="Index fixture",
        created_at=fixed,
        updated_at=fixed,
    ).model_dump(mode="python")
    source["_id"] = "source-storage"
    archive = tmp_path / "index-conflict.zip"
    _write_archive(archive, {"sources": [source]}, generic={"sources"})
    database = _Database("MathV0", {"sources": []})
    database["sources"].indexes.append(
        {
            "name": "sources_source_id_unique",
            "key": {"wrong_field": 1},
            "unique": True,
        }
    )

    plan = db_update.analyze_database_update(
        archive,
        _Mongo(database),
        source_document_blob_store=SourceDocumentBlobStore(configured_paths),
        data_root=configured_paths,
    )

    assert plan.can_apply is False
    assert any("Managed index conflict" in item.reason for item in plan.blocking_issues)
    assert database["sources"].insert_calls == 0


def test_grouped_index_manager_does_not_create_unrequested_collection() -> None:
    database = _Database("MathV0", {"sources": []})

    db_update._apply_known_indexes(_Mongo(database), {"sources"})

    assert "sources_source_id_unique" in {item["name"] for item in database["sources"].indexes}
    assert "references" not in database.list_collection_names()


def test_safe_update_preserves_local_data_creates_future_collections_and_is_noop_twice(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "update.zip"
    _fixture_archive(archive)
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    policies = {action.token: db_update.ConflictPolicy.KEEP_CURRENT for action in plan.conflicts}

    report = db_update.apply_database_update(
        archive,
        mongo,
        plan,
        conflict_policies=policies,
        backup_root=configured_paths / "backups",
        source_document_blob_store=store,
        data_root=configured_paths,
    )

    assert report.inserted == 2
    assert report.conflicts_preserved == 1
    assert report.backup_path.is_file()
    assert database["latex_documents"].find_one({"id": "conflict"})["contenido_latex"] == "local"
    assert database["latex_documents"].find_one({"id": "local-only"}) is not None
    assert database["local_only_collection"].count_documents({}) == 1
    assert database["future_collection"].find_one({"_id": "future"}) is not None
    assert "future_empty" in database.list_collection_names()

    second_plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    second_policies = {
        action.token: db_update.ConflictPolicy.KEEP_CURRENT for action in second_plan.conflicts
    }
    writes_before = sum(item.insert_calls for item in database._collections.values())
    second = db_update.apply_database_update(
        archive,
        mongo,
        second_plan,
        conflict_policies=second_policies,
        backup_root=configured_paths / "backups",
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    assert second.inserted == 0
    assert sum(item.insert_calls for item in database._collections.values()) == writes_before


def test_backup_wins_replaces_only_explicit_conflict(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "update.zip"
    _fixture_archive(archive)
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        strategy=db_update.UpdateStrategy.BACKUP_WINS,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    policies = {action.token: db_update.ConflictPolicy.USE_BACKUP for action in plan.conflicts}

    report = db_update.apply_database_update(
        archive,
        mongo,
        plan,
        conflict_policies=policies,
        backup_root=configured_paths / "backups",
        source_document_blob_store=store,
        data_root=configured_paths,
    )

    assert report.replaced == 1
    assert database["latex_documents"].find_one({"id": "conflict"})["contenido_latex"] == "backup"
    assert database["latex_documents"].find_one({"id": "local-only"}) is not None


def test_generic_collection_without_id_blocks_before_backup_or_writes(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "unsafe-generic.zip"
    _write_archive(
        archive,
        {"future_collection": [{"value": 1}]},
        generic={"future_collection"},
    )
    database = _fixture_database()
    mongo = _Mongo(database)

    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=SourceDocumentBlobStore(configured_paths),
        data_root=configured_paths,
    )

    assert plan.can_apply is False
    assert any("no safe _id" in item.reason for item in plan.blocking_issues)
    assert not (configured_paths / "backups").exists()


def test_metadata_count_mismatch_and_path_traversal_are_rejected(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    mismatch = tmp_path / "mismatch.zip"
    _write_archive(
        mismatch,
        {"future_collection": [{"_id": "one"}]},
        generic={"future_collection"},
        metadata_overrides={"collections": {"future_collection": 2}},
    )
    mongo = _Mongo(_fixture_database())
    with pytest.raises(ValueError, match="count"):
        db_update.analyze_database_update(
            mismatch,
            mongo,
            source_document_blob_store=SourceDocumentBlobStore(configured_paths),
            data_root=configured_paths,
        )

    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("root/metadata.json", json.dumps({"collections": {}}))
        archive.writestr("root/../outside.json", "[]")
    with pytest.raises(ValueError, match="unsafe path component"):
        db_update.inspect_update_archive(traversal)


@pytest.mark.parametrize("database_name", ["admin", "config", "local"])
def test_protected_update_targets_are_blocked(database_name: str) -> None:
    with pytest.raises(ValueError, match="protected"):
        db_update.validate_database_name(database_name, update=True)


def test_empty_backup_collection_never_empties_existing_destination(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "empty.zip"
    _write_archive(archive, {"future_collection": []}, generic={"future_collection"})
    database = _Database("MathV0", {"future_collection": [{"_id": "local"}]})
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    report = db_update.apply_database_update(
        archive,
        mongo,
        plan,
        conflict_policies={},
        backup_root=configured_paths / "backups",
        source_document_blob_store=store,
        data_root=configured_paths,
    )

    assert report.inserted == 0
    assert database["future_collection"].documents == [{"_id": "local"}]


def test_media_is_copied_once_and_conflicting_destination_blocks(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "media.zip"
    media_path = "media/images/example.png"
    _write_archive(archive, {}, media={media_path: b"image-bytes"})
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    report = db_update.apply_database_update(
        archive,
        mongo,
        plan,
        conflict_policies={},
        backup_root=configured_paths / "backups",
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    assert report.media_created == 1
    assert (configured_paths / media_path).read_bytes() == b"image-bytes"

    (configured_paths / media_path).write_bytes(b"changed")
    blocked = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    assert any("different bytes" in item.reason for item in blocked.blocking_issues)


def test_dynamic_backup_contains_local_unknown_collection(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    database = _Database("MathV0", {"future_local": [{"_id": "keep", "value": 1}]})
    mongo = _Mongo(database)

    archive = db_export.export_database_to_zip(
        mongo,
        tmp_path / "backups",
        source_document_blob_store=SourceDocumentBlobStore(configured_paths),
        include_all_collections=True,
    )
    inspection = db_update.inspect_update_archive(archive)

    assert inspection["collections"]["future_local"] == 1
    assert inspection["unmanaged_collections"] == ["future_local"]


def test_pdf_blob_is_verified_copied_once_and_then_skipped(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    source, reference, document, logical_path = _portable_pdf_fixture(pdf_bytes)
    archive = tmp_path / "portable-pdf.zip"
    _write_archive(
        archive,
        {
            "sources": [source],
            "references": [reference],
            "source_documents": [document],
        },
        generic={"sources", "references", "source_documents"},
        blobs={logical_path: pdf_bytes},
    )
    database = _Database("MathV0", {})
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    assert plan.totals["blobs_new"] == 1

    first = db_update.apply_database_update(
        archive,
        mongo,
        plan,
        conflict_policies={},
        backup_root=configured_paths / "backups",
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    assert first.blobs_created == 1
    assert (
        store.path_for_sha(SourceDocumentBlobStore.prepare_pdf(pdf_bytes).sha256).read_bytes()
        == pdf_bytes
    )

    second_plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    assert second_plan.totals["blobs_existing"] == 1


def test_corrupt_pdf_blob_blocks_before_database_update(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    pdf_bytes = b"%PDF-1.4\nvalid\n%%EOF\n"
    source, reference, document, logical_path = _portable_pdf_fixture(pdf_bytes)
    archive = tmp_path / "corrupt-pdf.zip"
    with pytest.raises(ValueError, match="Blob path does not match"):
        _write_archive(
            archive,
            {
                "sources": [source],
                "references": [reference],
                "source_documents": [document],
            },
            generic={"sources", "references", "source_documents"},
            blobs={logical_path: b"%PDF-1.4\ncorrupt\n%%EOF\n"},
        )
        db_update.analyze_database_update(
            archive,
            _Mongo(_Database("MathV0", {})),
            source_document_blob_store=SourceDocumentBlobStore(configured_paths),
            data_root=configured_paths,
        )


def test_existing_corrupt_blob_destination_blocks_before_writes(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    pdf_bytes = b"%PDF-1.4\nvalid destination\n%%EOF\n"
    source, reference, document, logical_path = _portable_pdf_fixture(pdf_bytes)
    archive = tmp_path / "portable-pdf.zip"
    _write_archive(
        archive,
        {
            "sources": [source],
            "references": [reference],
            "source_documents": [document],
        },
        generic={"sources", "references", "source_documents"},
        blobs={logical_path: pdf_bytes},
    )
    store = SourceDocumentBlobStore(configured_paths)
    destination = store.path_for_sha(SourceDocumentBlobStore.prepare_pdf(pdf_bytes).sha256)
    destination.parent.mkdir(parents=True, mode=0o700)
    destination.write_bytes(b"%PDF-1.4\ndifferent\n%%EOF\n")
    destination.chmod(0o600)

    plan = db_update.analyze_database_update(
        archive,
        _Mongo(_Database("MathV0", {})),
        source_document_blob_store=store,
        data_root=configured_paths,
    )

    assert any("blob destination conflicts" in item.reason for item in plan.blocking_issues)


def test_missing_conflict_policy_blocks_before_backup(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "update.zip"
    _fixture_archive(archive)
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )

    with pytest.raises(ValueError, match="Every conflict"):
        db_update.apply_database_update(
            archive,
            mongo,
            plan,
            conflict_policies={},
            backup_root=configured_paths / "backups",
            source_document_blob_store=store,
            data_root=configured_paths,
        )
    assert not (configured_paths / "backups").exists()


def test_backup_failure_aborts_before_first_update_write(
    tmp_path: Path,
    configured_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "update.zip"
    _fixture_archive(archive)
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    policies = {action.token: db_update.ConflictPolicy.KEEP_CURRENT for action in plan.conflicts}
    writes_before = sum(item.insert_calls for item in database._collections.values())
    monkeypatch.setattr(
        db_update,
        "export_database_to_zip",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("backup unavailable")),
    )

    with pytest.raises(OSError, match="backup unavailable"):
        db_update.apply_database_update(
            archive,
            mongo,
            plan,
            conflict_policies=policies,
            backup_root=configured_paths / "backups",
            source_document_blob_store=store,
            data_root=configured_paths,
        )
    assert sum(item.insert_calls for item in database._collections.values()) == writes_before
    assert database["latex_documents"].find_one({"id": "new"}) is None


def test_failed_apply_reports_operations_and_explicit_recovery_restores_state(
    tmp_path: Path,
    configured_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "update.zip"
    media_path = "media/recovery.png"
    _fixture_archive(archive, media={media_path: b"recovery-image"})
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    before = deepcopy(database["latex_documents"].documents)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    policies = {action.token: db_update.ConflictPolicy.KEEP_CURRENT for action in plan.conflicts}
    monkeypatch.setattr(
        db_update,
        "_apply_known_indexes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("index failure")),
    )

    with pytest.raises(db_update.DatabaseUpdateApplyError) as caught:
        db_update.apply_database_update(
            archive,
            mongo,
            plan,
            conflict_policies=policies,
            backup_root=configured_paths / "backups",
            source_document_blob_store=store,
            data_root=configured_paths,
        )
    failure = caught.value
    assert failure.operations
    assert failure.backup_path.is_file()
    assert database["latex_documents"].find_one({"id": "new"}) is not None
    assert (configured_paths / media_path).read_bytes() == b"recovery-image"

    recovery = db_update.restore_failed_update(
        failure,
        mongo,
        confirmation="MathV0",
        data_root=configured_paths,
    )

    assert recovery.reverted_operations == len(failure.operations)
    assert database["latex_documents"].documents == before
    assert "future_collection" not in database.list_collection_names()
    assert "future_empty" not in database.list_collection_names()
    assert not (configured_paths / media_path).exists()


def test_destination_change_after_analysis_requires_new_dry_run(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "update.zip"
    _fixture_archive(archive)
    database = _fixture_database()
    mongo = _Mongo(database)
    store = SourceDocumentBlobStore(configured_paths)
    plan = db_update.analyze_database_update(
        archive,
        mongo,
        source_document_blob_store=store,
        data_root=configured_paths,
    )
    database["latex_documents"].insert_one(_latex("concurrent", "concurrent", "change"))
    policies = {action.token: db_update.ConflictPolicy.KEEP_CURRENT for action in plan.conflicts}

    with pytest.raises(db_update.StaleUpdatePlanError, match="analyze again"):
        db_update.apply_database_update(
            archive,
            mongo,
            plan,
            conflict_policies=policies,
            backup_root=configured_paths / "backups",
            source_document_blob_store=store,
            data_root=configured_paths,
        )


def test_duplicate_managed_identity_blocks_unique_index_conflict_during_dry_run(
    tmp_path: Path,
    configured_paths: Path,
) -> None:
    archive = tmp_path / "duplicates.zip"
    _write_archive(
        archive,
        {
            "latex_documents": [
                _latex("one", "duplicate", "one"),
                _latex("two", "duplicate", "two"),
            ]
        },
    )

    plan = db_update.analyze_database_update(
        archive,
        _Mongo(_Database("MathV0", {})),
        source_document_blob_store=SourceDocumentBlobStore(configured_paths),
        data_root=configured_paths,
    )

    assert plan.can_apply is False
    assert any("duplicate stable identity" in item.reason for item in plan.blocking_issues)


def test_alternate_identity_cannot_collide_with_another_destination_document() -> None:
    database = _Database(
        "MathV0",
        {
            "managed": [
                {"_id": "first", "domain_id": "same", "alternate": "left"},
                {"_id": "second", "domain_id": "other", "alternate": "right"},
            ]
        },
    )
    candidate = db_update._Candidate(
        collection="managed",
        document={"_id": "first", "domain_id": "same", "alternate": "right"},
        managed=True,
        primary_query={"domain_id": "same"},
        unique_queries=[{"domain_id": "same"}, {"alternate": "right"}],
        token="collision",
    )

    action, issue = db_update._candidate_action(
        database,
        candidate,
        existing_names={"managed"},
    )

    assert action.classification is db_update.DocumentClassification.INVALID
    assert action.replace_allowed is False
    assert issue is not None
    assert "multiple destination documents" in issue.reason

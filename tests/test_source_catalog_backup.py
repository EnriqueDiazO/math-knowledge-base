"""Isolated export/import coverage for optional Source Catalog collections."""

# ruff: noqa: D103

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest
from bson import BSON
from bson import ObjectId
from bson.int64 import Int64

from editor.utils import db_export
from editor.utils import db_import
from mathkb_config import EXPORT_COLLECTIONS
from mathkb_config import SOURCE_CATALOG_COLLECTIONS
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.manifest import ManifestBackupEvidence
from mathmongo.source_catalog_migration.manifest import ManifestError
from mathmongo.source_catalog_migration.manifest import ManifestExpectedCounts
from mathmongo.source_catalog_migration.manifest import ManifestIndexStatus
from mathmongo.source_catalog_migration.manifest import ManifestInvariantHashes
from mathmongo.source_catalog_migration.manifest import ManifestState
from mathmongo.source_catalog_migration.manifest import MigrationManifest
from mathmongo.source_catalog_migration.manifest import allocate_prepared_manifest


class _Cursor(list):
    def max_time_ms(self, _milliseconds: int):
        return self


class _Collection:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self.documents = list(documents or [])
        self.insert_calls = 0
        self.replace_calls = 0

    def find(self, query: dict) -> _Cursor:
        return _Cursor(
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        )

    def find_one(self, query: dict):
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in query.items())
            ),
            None,
        )

    def insert_one(self, document: dict) -> None:
        self.insert_calls += 1
        self.documents.append(document)

    def replace_one(self, query: dict, document: dict, upsert: bool) -> None:
        self.replace_calls += 1
        existing = self.find_one(query)
        if existing is None:
            if upsert:
                self.documents.append(document)
            return
        self.documents[self.documents.index(existing)] = document


class _Database:
    name = "isolated-source-catalog-test"

    def __init__(self, documents: dict[str, list[dict]] | None = None) -> None:
        self.collections = {name: _Collection(items) for name, items in (documents or {}).items()}
        self.create_calls = 0

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> None:
        self.create_calls += 1
        self.collections.setdefault(name, _Collection())

    def __getitem__(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


def _mongo(database: _Database):
    return type("FakeMongo", (), {"db": database})()


def _write_archive(path: Path, collections: dict[str, list[dict]]) -> None:
    base = "mathkb_export_test"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{base}/metadata.json",
            json.dumps({"collections": {name: len(docs) for name, docs in collections.items()}}),
        )
        for name, documents in collections.items():
            archive.writestr(
                f"{base}/collections/{name}.json",
                json.dumps(documents),
            )


def _configure_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        db_export,
        "EXPORT_COLLECTIONS",
        ("concepts", "relations", "knowledge_graph_maps", "media_assets"),
    )
    monkeypatch.setattr(
        db_export,
        "SOURCE_CATALOG_COLLECTIONS",
        ("sources", "references", MANIFEST_COLLECTION),
    )
    monkeypatch.setattr(db_export, "LEGACY_PROJECT_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(db_export, "LOCAL_MEDIA_ROOT", tmp_path / "missing-media")


def test_manifest_is_optional_portable_catalog_not_a_legacy_bulk_delete_collection() -> None:
    assert set(SOURCE_CATALOG_COLLECTIONS).isdisjoint(EXPORT_COLLECTIONS)


def test_catalog_comparison_preserves_bson_integer_width() -> None:
    assert not db_import._catalog_documents_identical({"value": 1}, {"value": Int64(1)})


def _portable_catalog_documents() -> tuple[dict, dict, dict]:
    fixed = datetime(2026, 7, 12, 18, 30, 45, 123000, tzinfo=timezone.utc)
    source = Source(
        source_id="src_00000000-0000-4000-8000-000000000001",
        name="Portable Source",
        created_at=fixed,
        updated_at=fixed,
    )
    reference = Reference(
        reference_id="ref_00000000-0000-4000-8000-000000000002",
        source_ids=[source.source_id],
        title="Portable Reference",
        created_at=fixed,
        updated_at=fixed,
    )
    manifest = allocate_prepared_manifest(
        target_database="MathV0",
        zip_sha256="a" * 64,
        plan_semantic_sha256="b" * 64,
        decisions_sha256="c" * 64,
        expected_counts=ManifestExpectedCounts(
            concepts=1,
            source_candidates=1,
            concepts_with_reference=1,
            concepts_without_reference=0,
            reference_candidates=1,
            bindings=1,
            conflicts=0,
            review_items=0,
            weak_suggestions=0,
        ),
        source_candidate_keys=("source-key",),
        reference_candidate_keys=("reference-key",),
        source_entity_hashes={"source-key": "d" * 64},
        reference_entity_hashes={"reference-key": "e" * 64},
        reference_evidence_hashes={"reference-key": "f" * 64},
        invariant_hashes_before=ManifestInvariantHashes(
            collections_sha256="1" * 64,
            indexes_sha256="2" * 64,
            aggregate_sha256="3" * 64,
        ),
        indexes_status=ManifestIndexStatus(
            expected=15,
            missing=15,
            expected_sha256="4" * 64,
        ),
        production_backup_evidence=ManifestBackupEvidence(
            file_name="mathv0-pre-apply.zip",
            sha256="9" * 64,
            size_bytes=12345,
            exported_at=fixed,
            completed_at=fixed,
            write_freeze_at=fixed,
            format_name="mathkb_legacy_export",
            format_version="1",
            collection_counts={"concepts": 1},
            legacy_aggregate_sha256="8" * 64,
            media_aggregate_sha256="7" * 64,
            media_file_count=15,
            file_mode="0600",
            parent_mode="0700",
        ),
        source_id_factory=lambda: source.source_id,
        reference_id_factory=lambda: reference.reference_id,
        migration_id_factory=lambda: "mig_00000000-0000-4000-8000-000000000003",
        clock=lambda: fixed,
    )
    manifest_payload = manifest.model_dump(mode="python")
    manifest_payload["errors"] = (
        ManifestError(
            code="portable_evidence",
            message="Portable timestamp evidence.",
            occurred_at=fixed,
            state=ManifestState.PREPARED,
            attempt=0,
        ),
    )
    manifest = MigrationManifest.model_validate(manifest_payload)
    source_document = source.model_dump(mode="python")
    source_document["_id"] = "64b64c7f0123456789abcde1"
    reference_document = reference.model_dump(mode="python")
    reference_document["_id"] = ObjectId("64b64c7f0123456789abcde2")
    manifest_document = manifest.model_dump(mode="python")
    manifest_document["_id"] = manifest.manifest_key
    return source_document, reference_document, manifest_document


def test_export_includes_catalog_collections_only_when_they_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_export(monkeypatch, tmp_path)

    absent_archive = db_export.export_database_to_zip(
        _mongo(_Database({"concepts": []})),
        tmp_path / "absent",
    )
    with zipfile.ZipFile(absent_archive) as archive:
        names = archive.namelist()
        assert any(name.endswith("collections/concepts.json") for name in names)
        assert not any(name.endswith("collections/sources.json") for name in names)
        assert not any(name.endswith("collections/references.json") for name in names)

    present_archive = db_export.export_database_to_zip(
        _mongo(
            _Database(
                {
                    "concepts": [],
                    "sources": [],
                    "references": [],
                    MANIFEST_COLLECTION: [],
                }
            )
        ),
        tmp_path / "present",
    )
    with zipfile.ZipFile(present_archive) as archive:
        names = archive.namelist()
        assert any(name.endswith("collections/sources.json") for name in names)
        assert any(name.endswith("collections/references.json") for name in names)
        assert any(name.endswith(f"collections/{MANIFEST_COLLECTION}.json") for name in names)


def test_export_does_not_include_unknown_existing_collections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_export(monkeypatch, tmp_path)

    archive_path = db_export.export_database_to_zip(
        _mongo(_Database({"concepts": [], "private_unknown": [{"secret": True}]})),
        tmp_path / "bounded",
    )

    with zipfile.ZipFile(archive_path) as archive:
        assert not any("private_unknown" in name for name in archive.namelist())


def test_import_rejects_nested_ambiguous_collection_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "ambiguous.zip"
    _write_archive(archive, {"sources": []})
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr("mathkb_export_test/collections/nested/sources.json", "[]")
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")

    with pytest.raises(ValueError, match="nested or ambiguous"):
        db_import.import_zip_into_database(archive, _mongo(_Database()))


def test_historical_import_does_not_create_absent_catalog_collections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "historical.zip"
    _write_archive(archive, {"concepts": []})
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        db_import,
        "IMPORT_COLLECTIONS",
        ("concepts", "sources", "references", MANIFEST_COLLECTION),
    )
    database = _Database()

    report = db_import.import_zip_into_database(archive, _mongo(database))

    assert report.imported_counts == {"concepts": 0}
    assert set(database.list_collection_names()) == {"concepts"}


def test_catalog_and_manifest_roundtrip_preserves_bson_ids_state_maps_and_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_export(monkeypatch, tmp_path)
    source, reference, manifest = _portable_catalog_documents()
    concept_id = ObjectId("64b64c7f0123456789abcde3")
    concept_time = datetime(2026, 7, 12, 18, 31, tzinfo=timezone.utc)
    origin = _Database(
        {
            "concepts": [
                {
                    "_id": concept_id,
                    "id": "portable-concept",
                    "source": "Portable Source",
                    "fecha_creacion": concept_time,
                    "ultima_actualizacion": concept_time,
                }
            ],
            "sources": [source],
            "references": [reference],
            MANIFEST_COLLECTION: [manifest],
            "relations": [{"_id": ObjectId("64b64c7f0123456789abcde4"), "tipo": "legacy"}],
            "knowledge_graph_maps": [
                {"_id": ObjectId("64b64c7f0123456789abcde5"), "name": "legacy"}
            ],
            "media_assets": [
                {"_id": ObjectId("64b64c7f0123456789abcde6"), "asset_id": "legacy_asset"}
            ],
        }
    )
    archive = db_export.export_database_to_zip(_mongo(origin), tmp_path / "portable")
    assert archive.stat().st_mode & 0o777 == 0o600
    with zipfile.ZipFile(archive) as export_zip:
        metadata_name = next(
            name for name in export_zip.namelist() if name.endswith("/metadata.json")
        )
        metadata = json.loads(export_zip.read(metadata_name))
    assert metadata["database_name"] == origin.name
    assert metadata["format"] == "mathkb_legacy_export"
    assert metadata["format_version"] == 1
    assert metadata["collection_encodings"] == {
        "sources": db_export.CATALOG_EXTENDED_JSON_ENCODING,
        "references": db_export.CATALOG_EXTENDED_JSON_ENCODING,
        MANIFEST_COLLECTION: db_export.CATALOG_EXTENDED_JSON_ENCODING,
    }
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        db_import,
        "IMPORT_COLLECTIONS",
        (
            "concepts",
            "relations",
            "knowledge_graph_maps",
            "media_assets",
            "sources",
            "references",
            MANIFEST_COLLECTION,
        ),
    )
    restored = _Database()

    first = db_import.import_zip_into_database(archive, _mongo(restored))

    restored_source = restored["sources"].documents[0]
    restored_reference = restored["references"].documents[0]
    restored_manifest = restored[MANIFEST_COLLECTION].documents[0]
    assert first.catalog_inserted == {
        "sources": 1,
        "references": 1,
        MANIFEST_COLLECTION: 1,
    }
    assert restored_source["source_id"] == source["source_id"]
    assert restored_source["_id"] == source["_id"]
    assert restored_source["created_at"] == source["created_at"]
    assert restored_reference["reference_id"] == reference["reference_id"]
    assert restored_reference["source_ids"] == [source["source_id"]]
    assert restored_reference["_id"] == reference["_id"]
    assert restored_manifest["migration_id"] == manifest["migration_id"]
    assert restored_manifest["target_database"] == "MathV0"
    assert restored_manifest["source_id_map"] == manifest["source_id_map"]
    assert restored_manifest["reference_id_map"] == manifest["reference_id_map"]
    assert restored_manifest["source_entity_hashes"] == manifest["source_entity_hashes"]
    assert restored_manifest["production_backup_evidence"] == manifest["production_backup_evidence"]
    assert restored_manifest["state"] == manifest["state"]
    assert restored_manifest["created_at"] == manifest["created_at"]
    assert restored_manifest["errors"][0]["occurred_at"] == manifest["errors"][0]["occurred_at"]
    before_writes = {
        name: (collection.insert_calls, collection.replace_calls)
        for name, collection in restored.collections.items()
    }
    before_creates = restored.create_calls

    second = db_import.import_zip_into_database(archive, _mongo(restored))

    assert second.catalog_identical == {
        "sources": 1,
        "references": 1,
        MANIFEST_COLLECTION: 1,
    }
    assert second.legacy_identical == {
        "concepts": 1,
        "knowledge_graph_maps": 1,
        "media_assets": 1,
        "relations": 1,
    }
    assert second.catalog_inserted == {}
    assert second.legacy_inserted == {}
    assert restored.create_calls == before_creates
    assert {
        name: (collection.insert_calls, collection.replace_calls)
        for name, collection in restored.collections.items()
    } == before_writes


def test_media_collision_remap_is_content_addressed_and_second_import_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "media-collision.zip"
    original_path = "media/images/shared.png"
    incoming_bytes = b"incoming-media-bytes"
    _write_archive(
        archive,
        {
            "media_assets": [
                {
                    "_id": "asset-1",
                    "path": original_path,
                    "filename": "shared.png",
                }
            ]
        },
    )
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr(f"mathkb_export_test/{original_path}", incoming_bytes)

    data_dir = tmp_path / "data"
    original_file = data_dir / original_path
    original_file.parent.mkdir(parents=True)
    original_file.write_bytes(b"preexisting-different-bytes")
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("media_assets",))
    database = _Database()

    first = db_import.import_zip_into_database(archive, _mongo(database))

    restored_document = database["media_assets"].documents[0]
    remapped_file = data_dir / restored_document["path"]
    assert first.legacy_inserted == {"media_assets": 1}
    assert restored_document["path"] != original_path
    assert restored_document["filename"] == remapped_file.name
    assert remapped_file.read_bytes() == incoming_bytes
    before_files = tuple(sorted(path.name for path in original_file.parent.iterdir()))
    before_stat = remapped_file.stat()
    before_directory_stat = remapped_file.parent.stat()
    before_insert_calls = database["media_assets"].insert_calls

    second = db_import.import_zip_into_database(archive, _mongo(database))

    assert second.legacy_identical == {"media_assets": 1}
    assert second.legacy_inserted == {}
    assert database["media_assets"].insert_calls == before_insert_calls
    assert tuple(sorted(path.name for path in original_file.parent.iterdir())) == before_files
    after_stat = remapped_file.stat()
    assert (after_stat.st_ino, after_stat.st_mtime_ns, after_stat.st_ctime_ns) == (
        before_stat.st_ino,
        before_stat.st_mtime_ns,
        before_stat.st_ctime_ns,
    )
    after_directory_stat = remapped_file.parent.stat()
    assert (after_directory_stat.st_mtime_ns, after_directory_stat.st_ctime_ns) == (
        before_directory_stat.st_mtime_ns,
        before_directory_stat.st_ctime_ns,
    )


def test_historical_timestamped_media_remap_is_reused_without_new_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "historical-media-remap.zip"
    original_path = "media/images/shared.png"
    historical_path = "media/images/shared_imported_1700000000_1.png"
    incoming_bytes = b"historically-remapped-media"
    incoming_document = {
        "_id": "asset-historical",
        "path": original_path,
        "filename": "shared.png",
    }
    existing_document = {
        "_id": "asset-historical",
        "path": historical_path,
        "filename": Path(historical_path).name,
    }
    _write_archive(archive, {"media_assets": [incoming_document]})
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr(f"mathkb_export_test/{original_path}", incoming_bytes)

    data_dir = tmp_path / "data"
    original_file = data_dir / original_path
    historical_file = data_dir / historical_path
    original_file.parent.mkdir(parents=True)
    original_file.write_bytes(b"preexisting-different-bytes")
    historical_file.write_bytes(incoming_bytes)
    before_files = tuple(sorted(path.name for path in original_file.parent.iterdir()))
    before_stat = historical_file.stat()
    database = _Database({"media_assets": [existing_document]})
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("media_assets",))

    report = db_import.import_zip_into_database(archive, _mongo(database))

    assert report.legacy_identical == {"media_assets": 1}
    assert report.legacy_inserted == {}
    assert database["media_assets"].documents == [existing_document]
    assert tuple(sorted(path.name for path in original_file.parent.iterdir())) == before_files
    after_stat = historical_file.stat()
    assert (after_stat.st_ino, after_stat.st_mtime_ns, after_stat.st_ctime_ns) == (
        before_stat.st_ino,
        before_stat.st_mtime_ns,
        before_stat.st_ctime_ns,
    )


def test_legacy_conflict_blocks_before_media_or_database_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "legacy-conflict-before-media.zip"
    media_path = "media/images/must-not-write.png"
    _write_archive(
        archive,
        {"concepts": [{"_id": "concept-1", "source": "incoming"}]},
    )
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr(f"mathkb_export_test/{media_path}", b"blocked")
    existing = {"_id": "concept-1", "source": "existing"}
    database = _Database({"concepts": [existing]})
    data_dir = tmp_path / "data"
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    with pytest.raises(db_import.CatalogImportConflictError):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database["concepts"].documents == [existing]
    assert database["concepts"].insert_calls == 0
    assert not data_dir.exists()


def test_concurrent_media_symlink_is_blocked_without_overwrite_or_database_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "media-race.zip"
    media_path = "media/images/raced.png"
    _write_archive(archive, {})
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr(f"mathkb_export_test/{media_path}", b"incoming")
    data_dir = tmp_path / "data"
    destination = data_dir / media_path
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"external-must-survive")
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())
    original_link = os.link
    raced = False

    def race_with_symlink(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination_name: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal raced
        if not raced:
            raced = True
            destination.symlink_to(outside)
        return original_link(
            source,
            destination_name,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(db_import.os, "link", race_with_symlink)

    with pytest.raises(ValueError, match="safely inspect import destination"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert raced is True
    assert outside.read_bytes() == b"external-must-survive"
    assert database.list_collection_names() == []


def test_media_parent_symlink_cannot_mutate_external_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o755)
    (data_dir / "media").symlink_to(outside, target_is_directory=True)
    before_mode = outside.stat().st_mode & 0o777
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)

    with pytest.raises(ValueError, match="Symbolic links are not allowed"):
        db_import._write_media_file_exclusive(
            data_dir / "media/images/escape.png",
            b"must-not-write",
        )

    assert outside.stat().st_mode & 0o777 == before_mode == 0o755
    assert not (outside / "images").exists()


def test_failed_anonymous_media_write_leaves_no_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    destination = data_dir / "media/images/interrupted.png"
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)

    def fail_anonymous_write(_descriptor: int, _data: bytes | memoryview) -> int:
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(db_import.os, "write", fail_anonymous_write)

    with pytest.raises(OSError, match="simulated interrupted write"):
        db_import._write_media_file_exclusive(destination, b"incoming")

    assert not destination.exists()


def test_media_restore_detects_same_inode_mutation_at_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    destination = data_dir / "media/images/raced.png"
    original_open_directory = db_import._open_private_import_directory
    calls = 0
    original_inode: int | None = None

    def mutate_on_final_reopen(directory: Path, *, create: bool = True) -> int:
        nonlocal calls, original_inode
        calls += 1
        descriptor = original_open_directory(directory, create=create)
        if calls == 4:
            original_inode = destination.stat().st_ino
            destination.write_bytes(b"same-inode mutation")
            assert destination.stat().st_ino == original_inode
        return descriptor

    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(
        db_import,
        "_open_private_import_directory",
        mutate_on_final_reopen,
    )

    with pytest.raises(FileExistsError, match="identity or bytes changed at completion"):
        db_import._write_media_file_exclusive(destination, b"incoming")

    assert original_inode is not None


def test_moved_media_parent_is_detected_before_database_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "moved-media-parent.zip"
    media_path = "media/images/moved.png"
    _write_archive(archive, {})
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr(f"mathkb_export_test/{media_path}", b"incoming")
    data_dir = tmp_path / "data"
    destination = data_dir / media_path
    moved_parent = tmp_path / "moved-images"
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())
    original_write = os.write
    moved = False

    def move_parent_then_write(descriptor: int, data: bytes | memoryview) -> int:
        nonlocal moved
        if not moved:
            moved = True
            destination.parent.rename(moved_parent)
            destination.parent.mkdir(parents=True, mode=0o700)
        return original_write(descriptor, data)

    monkeypatch.setattr(db_import.os, "write", move_parent_then_write)

    with pytest.raises(FileExistsError, match="parent changed"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert moved is True
    assert not destination.exists()
    assert not (moved_parent / destination.name).exists()
    assert database.list_collection_names() == []


def test_unknown_collection_is_rejected_before_media_or_database_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "unknown-collection.zip"
    _write_archive(archive, {"arbitrary_out_of_scope": [{"_id": "outside"}]})
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr("mathkb_export_test/media/images/must-not-write.png", b"blocked")
    data_dir = tmp_path / "data"
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)

    with pytest.raises(ValueError, match="unsupported collection"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []
    assert not data_dir.exists()


@pytest.mark.parametrize(
    ("metadata", "expected_message"),
    [
        ({"collections": {"concepts": 999}}, "collection inventory"),
        (
            {
                "collections": {"concepts": 1},
                "media_files": {"media/images/example.png": 999},
            },
            "media inventory",
        ),
    ],
)
def test_metadata_inventory_must_match_physical_members_before_writes(
    metadata: dict,
    expected_message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / f"mismatched-{expected_message.replace(' ', '-')}.zip"
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr(
            "mathkb_export_test/collections/concepts.json",
            json.dumps([{"_id": "concept-1"}]),
        )
        if "media_files" in metadata:
            export_zip.writestr("mathkb_export_test/media/images/example.png", b"one")
    data_dir = tmp_path / "data"
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    with pytest.raises(ValueError, match=expected_message):
        db_import.inspect_export_zip(archive)
    with pytest.raises(ValueError, match=expected_message):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []
    assert not data_dir.exists()


def test_versioned_export_requires_declared_exact_media_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "versioned-without-media-inventory.zip"
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "portable-test",
        "collections": {"concepts": 0},
    }
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr("mathkb_export_test/collections/concepts.json", "[]")
        export_zip.writestr("mathkb_export_test/media/images/undeclared.png", b"media")
    data_dir = tmp_path / "data"
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    with pytest.raises(ValueError, match="versioned metadata requires an exact media inventory"):
        db_import.inspect_export_zip(archive)
    with pytest.raises(ValueError, match="versioned metadata requires an exact media inventory"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []
    assert not data_dir.exists()


def test_versioned_catalog_requires_canonical_extended_json_codec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "versioned-catalog-without-codec.zip"
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "portable-test",
        "collections": {"sources": 1},
        "media_files": {},
    }
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr(
            "mathkb_export_test/collections/sources.json",
            json.dumps(
                [
                    {
                        "_id": "64b64c7f0123456789abcde1",
                        "source_id": "src_00000000-0000-4000-8000-000000000001",
                        "name": "Must remain a string ID",
                    }
                ]
            ),
        )
    data_dir = tmp_path / "data"
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())

    with pytest.raises(ValueError, match="canonical Extended JSON encodings"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []
    assert not data_dir.exists()


@pytest.mark.parametrize("invalid_field", ["source_id", "name_normalized"])
def test_versioned_source_must_match_validated_canonical_domain_model(
    invalid_field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / f"invalid-versioned-source-{invalid_field}.zip"
    source = Source(name="Algebra").model_dump(mode="python")
    if invalid_field == "source_id":
        source["source_id"] = "not-a-source-uuid"
    else:
        source["name_normalized"] = "definitely-wrong"
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "portable-test",
        "collections": {"sources": 1},
        "collection_encodings": {
            "sources": db_export.CATALOG_EXTENDED_JSON_ENCODING,
        },
        "media_files": {},
    }
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr(
            "mathkb_export_test/collections/sources.json",
            db_export.bson_json_dumps(
                [source],
                json_options=db_export.CANONICAL_JSON_OPTIONS,
            ),
        )
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())

    with pytest.raises(db_import.CatalogImportConflictError):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []


def test_versioned_manifest_rejects_relaxed_json_timestamps_under_canonical_codec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, _reference, manifest = _portable_catalog_documents()
    archive = tmp_path / "relaxed-versioned-manifest.zip"
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "portable-test",
        "collections": {MANIFEST_COLLECTION: 1},
        "collection_encodings": {
            MANIFEST_COLLECTION: db_export.CATALOG_EXTENDED_JSON_ENCODING,
        },
        "media_files": {},
    }
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr(
            f"mathkb_export_test/collections/{MANIFEST_COLLECTION}.json",
            json.dumps([manifest], default=str),
        )
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(archive, _mongo(database))

    assert caught.value.report.catalog_conflicts[0].reason == (
        "non-canonical portable manifest document"
    )
    assert database.list_collection_names() == []


def test_duplicate_destination_domain_id_blocks_even_if_first_match_is_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    incoming = {"source_id": source_id, "name": "Algebra"}
    archive = tmp_path / "duplicate-destination-domain-id.zip"
    _write_archive(archive, {"sources": [incoming]})
    database = _Database(
        {
            "sources": [
                dict(incoming),
                {"source_id": source_id, "name": "Different"},
            ]
        }
    )
    before = list(database["sources"].documents)
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(archive, _mongo(database))

    assert "duplicate documents" in caught.value.report.catalog_conflicts[0].reason
    assert database["sources"].documents == before
    assert database["sources"].insert_calls == 0


def test_concurrent_duplicate_domain_insert_never_reports_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    incoming = {"source_id": source_id, "name": "Incoming"}
    archive = tmp_path / "concurrent-domain-duplicate.zip"
    _write_archive(archive, {"sources": [incoming]})
    database = _Database()
    collection = database["sources"]

    def racing_insert(document: dict) -> None:
        collection.insert_calls += 1
        collection.documents.append({"source_id": source_id, "name": "Racer"})
        collection.documents.append(document)

    collection.insert_one = racing_insert
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(archive, _mongo(database))

    assert "duplicate domain IDs" in caught.value.report.catalog_conflicts[-1].reason
    assert len(collection.documents) == 2


@pytest.mark.parametrize("database_name", ["admin", "config", "local", "mathmongo"])
def test_import_always_rejects_protected_database_names(
    database_name: str,
    tmp_path: Path,
) -> None:
    archive = tmp_path / f"protected-{database_name}.zip"
    _write_archive(archive, {"concepts": []})
    database = _Database()
    database.name = database_name

    with pytest.raises(ValueError, match="protected MongoDB targets"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []


def test_import_allows_exact_empty_mathv0_restore_but_blocks_existing_mathv0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "same-name-restore.zip"
    _write_archive(archive, {"concepts": []})
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))
    empty = _Database()
    empty.name = "MathV0"

    report = db_import.import_zip_into_database(archive, _mongo(empty))

    assert report.imported_counts == {"concepts": 0}
    assert empty.list_collection_names() == ["concepts"]

    existing = _Database({"concepts": [{"_id": "existing"}]})
    existing.name = "MathV0"
    with pytest.raises(ValueError, match="physically empty"):
        db_import.import_zip_into_database(archive, _mongo(existing))
    assert existing["concepts"].documents == [{"_id": "existing"}]


def test_versioned_archive_from_another_database_cannot_restore_into_mathv0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "wrong-database-same-name-restore.zip"
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "NotMathV0",
        "collections": {"concepts": 1},
        "collection_encodings": {},
        "media_files": {},
    }
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr(
            "mathkb_export_test/collections/concepts.json",
            json.dumps([{"_id": "must-not-restore"}]),
        )
    database = _Database()
    database.name = "MathV0"
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    with pytest.raises(ValueError, match="requires MathV0 archive metadata"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []


def test_versioned_same_name_mathv0_restore_is_resumable_and_identical_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "versioned-same-name-restore.zip"
    concept = {"_id": "concept-from-backup", "source": "Portable"}
    metadata = {
        "format": "mathkb_legacy_export",
        "format_version": 1,
        "database_name": "MathV0",
        "collections": {"concepts": 1},
        "collection_encodings": {},
        "media_files": {},
    }
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr(
            "mathkb_export_test/collections/concepts.json",
            json.dumps([concept]),
        )
    database = _Database()
    database.name = "MathV0"
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    first = db_import.import_zip_into_database(archive, _mongo(database))
    writes_after_first = database["concepts"].insert_calls
    second = db_import.import_zip_into_database(archive, _mongo(database))

    assert first.legacy_inserted == {"concepts": 1}
    assert second.legacy_identical == {"concepts": 1}
    assert second.legacy_inserted == {}
    assert database["concepts"].insert_calls == writes_after_first
    assert database["concepts"].documents == [concept]


def test_historical_root_collection_layout_remains_importable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "historical-root-layout.zip"
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr(
            "mathkb_export_historical/metadata.json",
            json.dumps({"collections": {"concepts": 1}}),
        )
        export_zip.writestr(
            "mathkb_export_historical/concepts.json",
            json.dumps([{"_id": "historical-concept"}]),
        )
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    inspected = db_import.inspect_export_zip(archive)
    report = db_import.import_zip_into_database(archive, _mongo(database))

    assert inspected["collections"] == {"concepts": 1}
    assert report.legacy_inserted == {"concepts": 1}
    assert database["concepts"].documents == [{"_id": "historical-concept"}]


def test_mixed_historical_and_modern_collection_layout_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "mixed-layout.zip"
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr(
            "mathkb_export_test/metadata.json",
            json.dumps({"collections": {"concepts": 1}}),
        )
        export_zip.writestr(
            "mathkb_export_test/concepts.json",
            json.dumps([{"_id": "historical"}]),
        )
        export_zip.writestr(
            "mathkb_export_test/collections/concepts.json",
            json.dumps([{"_id": "modern"}]),
        )
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    with pytest.raises(ValueError, match="duplicate collection|mixes"):
        db_import.inspect_export_zip(archive)
    with pytest.raises(ValueError, match="duplicate collection|mixes"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []


def test_regular_media_ancestor_collision_is_rejected_before_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "media-ancestor-collision.zip"
    with zipfile.ZipFile(archive, "w") as export_zip:
        export_zip.writestr(
            "mathkb_export_test/metadata.json",
            json.dumps({"collections": {}}),
        )
        export_zip.writestr("mathkb_export_test/media/images", b"poison")
        export_zip.writestr("mathkb_export_test/media/images/x.png", b"image")
    data_dir = tmp_path / "data"
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ())

    with pytest.raises(ValueError, match="ancestor"):
        db_import.inspect_export_zip(archive)
    with pytest.raises(ValueError, match="ancestor"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []
    assert not data_dir.exists()


def test_zip_bomb_ratio_is_rejected_before_payload_read_or_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "compression-ratio.zip"
    metadata = {"collections": {"concepts": 1}}
    payload = json.dumps([{"_id": "concept-1", "value": "0" * 2_000_000}])
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as export_zip:
        export_zip.writestr("mathkb_export_test/metadata.json", json.dumps(metadata))
        export_zip.writestr("mathkb_export_test/collections/concepts.json", payload)
    data_dir = tmp_path / "data"
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", data_dir)
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("concepts",))

    with pytest.raises(ValueError, match="anomalous compression ratio"):
        db_import.inspect_export_zip(archive)
    with pytest.raises(ValueError, match="anomalous compression ratio"):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database.list_collection_names() == []
    assert not data_dir.exists()


def test_historical_plain_json_manifest_restores_naive_bson_datetimes_as_utc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, _reference, manifest = _portable_catalog_documents()
    pymongo_like = BSON.encode(manifest).decode()
    assert pymongo_like["created_at"].tzinfo is None
    assert pymongo_like["errors"][0]["occurred_at"].tzinfo is None
    archive = tmp_path / "historical-manifest.zip"
    _write_archive(
        archive,
        {MANIFEST_COLLECTION: [db_export.mongo_to_json_safe(pymongo_like)]},
    )
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", (MANIFEST_COLLECTION,))
    restored = _Database()

    db_import.import_zip_into_database(archive, _mongo(restored))

    document = restored[MANIFEST_COLLECTION].documents[0]
    assert document["created_at"].tzinfo == timezone.utc
    assert document["errors"][0]["occurred_at"].tzinfo == timezone.utc


def test_catalog_import_reports_identical_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    incoming = {
        "_id": "same-storage-id",
        "source_id": source_id,
        "name": "Algebra",
        "created_at": "2026-07-11T12:00:00+00:00",
        "updated_at": "2026-07-11T12:00:00+00:00",
    }
    archive = tmp_path / "identical.zip"
    _write_archive(archive, {"sources": [incoming]})
    existing = {
        "_id": "same-storage-id",
        "source_id": source_id,
        "name": "Algebra",
        "created_at": datetime(2026, 7, 11, 12, 0, 0),
        "updated_at": datetime(2026, 7, 11, 12, 0, 0),
    }
    database = _Database({"sources": [existing]})
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("sources", "references"))

    report = db_import.import_zip_into_database(archive, _mongo(database))

    assert report.catalog_identical == {"sources": 1}
    assert report.catalog_inserted == {}
    assert database["sources"].documents == [existing]
    assert "references" not in database.list_collection_names()


def test_catalog_import_blocks_same_domain_id_with_different_mongodb_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    archive = tmp_path / "different-storage-id.zip"
    _write_archive(
        archive,
        {"sources": [{"_id": "incoming", "source_id": source_id, "name": "Algebra"}]},
    )
    database = _Database(
        {"sources": [{"_id": "existing", "source_id": source_id, "name": "Algebra"}]}
    )
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("sources", "references"))

    with pytest.raises(db_import.CatalogImportConflictError):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert database["sources"].documents[0]["_id"] == "existing"


def test_catalog_import_blocks_different_document_with_same_domain_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    archive = tmp_path / "conflict.zip"
    _write_archive(
        archive,
        {"sources": [{"source_id": source_id, "name": "Incoming"}]},
    )
    existing = {"source_id": source_id, "name": "Existing"}
    database = _Database({"sources": [existing]})
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("sources", "references"))

    with pytest.raises(db_import.CatalogImportConflictError) as caught:
        db_import.import_zip_into_database(archive, _mongo(database))

    assert caught.value.report.catalog_conflicts[0].domain_id == source_id
    assert database["sources"].documents == [existing]
    assert not (tmp_path / "data").exists()


def test_catalog_import_blocks_orphan_reference_and_manifest_id_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orphan_archive = tmp_path / "orphan-reference.zip"
    _write_archive(
        orphan_archive,
        {
            "references": [
                {
                    "reference_id": "ref_00000000-0000-4000-8000-000000000010",
                    "source_ids": ["src_00000000-0000-4000-8000-000000000099"],
                    "title": "Orphan",
                }
            ]
        },
    )
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        db_import,
        "IMPORT_COLLECTIONS",
        ("sources", "references", MANIFEST_COLLECTION),
    )
    orphan_database = _Database()

    with pytest.raises(db_import.CatalogImportConflictError):
        db_import.import_zip_into_database(orphan_archive, _mongo(orphan_database))

    _source, _reference, manifest = _portable_catalog_documents()
    portable_manifest = MigrationManifest.model_validate(
        {key: value for key, value in manifest.items() if key != "_id"}
    ).model_dump(mode="json")
    portable_manifest["_id"] = "different-manifest-storage-id"
    manifest_archive = tmp_path / "manifest-id-mismatch.zip"
    _write_archive(
        manifest_archive,
        {MANIFEST_COLLECTION: [portable_manifest]},
    )
    manifest_database = _Database()

    with pytest.raises(db_import.CatalogImportConflictError):
        db_import.import_zip_into_database(manifest_archive, _mongo(manifest_database))

    assert manifest_database[MANIFEST_COLLECTION].documents == []


def test_catalog_conflict_occurs_before_touching_legacy_collections_or_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id = "src_12345678-1234-4234-9234-123456789abc"
    archive = tmp_path / "catalog-conflict-before-legacy.zip"
    _write_archive(
        archive,
        {
            "concepts": [{"_id": "incoming-concept", "source": "incoming"}],
            "relations": [{"_id": "incoming-relation"}],
            "knowledge_graph_maps": [{"_id": "incoming-map"}],
            "media_assets": [{"_id": "incoming-media"}],
            "sources": [{"source_id": source_id, "name": "Incoming"}],
        },
    )
    with zipfile.ZipFile(archive, "a") as export_zip:
        export_zip.writestr("mathkb_export_test/media/images/must-not-write.png", b"blocked")
    database = _Database(
        {
            "concepts": [{"_id": "existing-concept", "source": "existing"}],
            "relations": [{"_id": "existing-relation"}],
            "knowledge_graph_maps": [{"_id": "existing-map"}],
            "media_assets": [{"_id": "existing-media"}],
            "sources": [{"source_id": source_id, "name": "Existing"}],
        }
    )
    before = {name: list(collection.documents) for name, collection in database.collections.items()}
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(
        db_import,
        "IMPORT_COLLECTIONS",
        (
            "concepts",
            "relations",
            "knowledge_graph_maps",
            "media_assets",
            "sources",
            "references",
            MANIFEST_COLLECTION,
        ),
    )

    with pytest.raises(db_import.CatalogImportConflictError):
        db_import.import_zip_into_database(archive, _mongo(database))

    assert {
        name: list(collection.documents) for name, collection in database.collections.items()
    } == before
    assert not (tmp_path / "data").exists()


def test_catalog_reference_roundtrip_restores_nested_bson_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Source(name="Roundtrip")
    reference = Reference(
        title="Aware timestamps",
        source_ids=[source.source_id],
        accessed_at=datetime.now().astimezone(),
    )
    archive = tmp_path / "roundtrip.zip"
    _write_archive(
        archive,
        {
            "sources": [db_export.mongo_to_json_safe(source.model_dump(mode="python"))],
            "references": [db_export.mongo_to_json_safe(reference.model_dump(mode="python"))],
        },
    )
    database = _Database()
    monkeypatch.setattr(db_import, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(db_import, "IMPORT_COLLECTIONS", ("sources", "references"))

    report = db_import.import_zip_into_database(archive, _mongo(database))

    restored = database["references"].documents[0]
    assert report.catalog_inserted == {"sources": 1, "references": 1}
    assert restored["reference_id"] == reference.reference_id
    assert restored["source_ids"] == [source.source_id]
    assert isinstance(restored["created_at"], datetime)
    assert isinstance(restored["accessed_at"], datetime)
    assert isinstance(restored["provenance"]["imported_at"], datetime)
    assert restored["created_at"].tzinfo is not None
    assert restored["provenance"]["imported_at"].tzinfo is not None

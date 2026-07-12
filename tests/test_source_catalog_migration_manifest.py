"""Focused fake-only contracts for the S1C2A prepared manifest."""

# ruff: noqa: D103

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from datetime import timezone

import pytest
from source_catalog_migration_fakes import FakeDatabase

from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.manifest import MIGRATION_TYPE
from mathmongo.source_catalog_migration.manifest import ManifestCompatibilityError
from mathmongo.source_catalog_migration.manifest import ManifestConcurrentUpdateError
from mathmongo.source_catalog_migration.manifest import ManifestExpectedCounts
from mathmongo.source_catalog_migration.manifest import ManifestIndexStatus
from mathmongo.source_catalog_migration.manifest import ManifestInvariantHashes
from mathmongo.source_catalog_migration.manifest import ManifestState
from mathmongo.source_catalog_migration.manifest import ManifestStore
from mathmongo.source_catalog_migration.manifest import MigrationManifest
from mathmongo.source_catalog_migration.manifest import allocate_prepared_manifest
from mathmongo.source_catalog_migration.manifest import bounded_safe_error
from mathmongo.source_catalog_migration.manifest import manifest_compatibility_issues
from mathmongo.source_catalog_migration.manifest import stable_manifest_key
from mathmongo.source_catalog_migration.manifest import state_transition_allowed

TARGET = "MathV0_s1c2_validation_manifest_tests"
ZIP_SHA = "a" * 64
PLAN_SHA = "b" * 64
DECISIONS_SHA = "c" * 64
FIXED_TIME = datetime(2026, 7, 12, 15, 16, 17, 123_987, tzinfo=timezone.utc)
MILLISECOND_TIME = FIXED_TIME.replace(microsecond=123_000)
SOURCE_KEYS = ("source_candidate_b", "source_candidate_a")
REFERENCE_KEYS = ("reference_candidate_b", "reference_candidate_a")


def _expected_counts() -> ManifestExpectedCounts:
    return ManifestExpectedCounts(
        concepts=4,
        source_candidates=2,
        concepts_with_reference=2,
        concepts_without_reference=2,
        reference_candidates=2,
        bindings=4,
        conflicts=0,
        review_items=0,
        weak_suggestions=0,
    )


def _id_factory(prefix: str, start: int) -> Callable[[], str]:
    current = start

    def allocate() -> str:
        nonlocal current
        value = f"{prefix}_00000000-0000-4000-8000-{current:012x}"
        current += 1
        return value

    return allocate


def _manifest(*, id_offset: int = 1, decisions_sha: str = DECISIONS_SHA) -> MigrationManifest:
    return allocate_prepared_manifest(
        target_database=TARGET,
        zip_sha256=ZIP_SHA,
        plan_semantic_sha256=PLAN_SHA,
        decisions_sha256=decisions_sha,
        expected_counts=_expected_counts(),
        source_candidate_keys=SOURCE_KEYS,
        reference_candidate_keys=REFERENCE_KEYS,
        source_entity_hashes={key: "d" * 64 for key in SOURCE_KEYS},
        reference_entity_hashes={key: "e" * 64 for key in REFERENCE_KEYS},
        reference_evidence_hashes={key: "f" * 64 for key in REFERENCE_KEYS},
        invariant_hashes_before=ManifestInvariantHashes(
            collections_sha256="1" * 64,
            indexes_sha256="2" * 64,
            aggregate_sha256="3" * 64,
        ),
        indexes_status=ManifestIndexStatus(
            expected=2,
            missing=2,
            expected_sha256="4" * 64,
        ),
        source_id_factory=_id_factory("src", id_offset),
        reference_id_factory=_id_factory("ref", id_offset + 100),
        migration_id_factory=_id_factory("mig", id_offset + 200),
        clock=lambda: FIXED_TIME,
    )


def _manifest_document(manifest: MigrationManifest) -> dict:
    document = manifest.model_dump(mode="python")
    document["_id"] = manifest.manifest_key
    return document


def test_stable_key_excludes_decisions_ids_and_timestamps() -> None:
    first = _manifest(id_offset=1, decisions_sha="1" * 64)
    second = _manifest(id_offset=500, decisions_sha="2" * 64)

    assert first.manifest_key == second.manifest_key
    assert first.manifest_key == stable_manifest_key(
        migration_type=MIGRATION_TYPE,
        target_database=TARGET,
        zip_sha256=ZIP_SHA,
        plan_semantic_sha256=PLAN_SHA,
    )
    assert first.migration_id != second.migration_id
    assert first.source_id_map != second.source_id_map


def test_allocation_is_sorted_uuid4_prefixed_and_timestamped_once() -> None:
    manifest = _manifest()

    assert tuple(manifest.source_id_map) == tuple(sorted(SOURCE_KEYS))
    assert tuple(manifest.reference_id_map) == tuple(sorted(REFERENCE_KEYS))
    assert all(value.startswith("src_") for value in manifest.source_id_map.values())
    assert all(value.startswith("ref_") for value in manifest.reference_id_map.values())
    assert manifest.migration_id.startswith("mig_")
    assert manifest.created_at == MILLISECOND_TIME
    assert manifest.last_updated_at == MILLISECOND_TIME
    assert manifest.state == ManifestState.PREPARED
    assert manifest.revision == 0


def test_applied_manifest_requires_complete_progress_invariants_and_hashed_indexes() -> None:
    prepared = _manifest()
    payload = prepared.model_dump(mode="python")
    payload.update(
        {
            "state": ManifestState.APPLIED,
            "started_at": MILLISECOND_TIME,
            "completed_at": MILLISECOND_TIME,
            "sources_created": 2,
            "references_created": 2,
            "invariant_hashes_before": ManifestInvariantHashes(
                collections_sha256="1" * 64,
                indexes_sha256="2" * 64,
                aggregate_sha256="3" * 64,
            ),
            "invariant_hashes_after": ManifestInvariantHashes(
                collections_sha256="1" * 64,
                indexes_sha256="2" * 64,
                aggregate_sha256="3" * 64,
            ),
            "indexes_status": ManifestIndexStatus(
                expected=2,
                applied=2,
                expected_sha256="4" * 64,
            ),
        }
    )

    with pytest.raises(ValueError, match="complete hashed index status"):
        MigrationManifest.model_validate(payload)

    payload["indexes_status"] = ManifestIndexStatus(
        expected=2,
        applied=2,
        expected_sha256="4" * 64,
        final_sha256="5" * 64,
    )
    assert MigrationManifest.model_validate(payload).state == ManifestState.APPLIED


def test_store_reads_absent_manifest_without_materializing_collection() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    key = _manifest().manifest_key
    before_names = database.list_collection_names()

    assert store.get(key) is None
    assert store.find_for_target(TARGET) == ()
    assert database.list_collection_names() == before_names
    assert MANIFEST_COLLECTION not in database.list_collection_names()
    assert database.write_events == ()


def test_insert_persists_complete_prepared_map_and_round_trips_bson() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest()

    result = store.insert_prepared_if_absent(requested)
    loaded = store.get(requested.manifest_key)

    assert result.created is True
    assert result.manifest == requested
    assert loaded == requested
    assert database.has_collection(MANIFEST_COLLECTION)
    assert database[MANIFEST_COLLECTION].count_documents({}) == 1
    insert = next(
        event
        for event in database.write_events
        if event.operation == "insert_one" and event.collection == MANIFEST_COLLECTION
    )
    assert insert.details["document"]["_id"] == requested.manifest_key
    assert insert.details["document"]["source_id_map"] == requested.source_id_map
    assert insert.details["document"]["reference_id_map"] == requested.reference_id_map
    assert insert.details["document"]["state"] == ManifestState.PREPARED.value
    assert insert.details["document"]["created_at"].tzinfo is None
    assert insert.details["document"]["created_at"].microsecond == 123_000


def test_compatible_duplicate_race_loads_winner_and_reuses_its_ids() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest(id_offset=1)
    winner = _manifest(id_offset=700)

    def install_winner(
        fake: FakeDatabase,
        collection: str | None,
        _details: dict,
    ) -> None:
        assert collection == MANIFEST_COLLECTION
        fake.external_insert(MANIFEST_COLLECTION, _manifest_document(winner))

    race = database.add_failpoint(
        "insert_one",
        collection=MANIFEST_COLLECTION,
        callback=install_winner,
    )

    result = store.insert_prepared_if_absent(requested)

    assert race.fired is True
    assert result.created is False
    assert result.manifest == winner
    assert result.manifest.source_id_map == winner.source_id_map
    assert result.manifest.source_id_map != requested.source_id_map
    assert database[MANIFEST_COLLECTION].count_documents({}) == 1
    assert [
        event.kind
        for event in database.events
        if event.operation in {"external_insert", "insert_one"}
    ][:2] == ["external", "write_attempt"]


def test_incompatible_duplicate_race_blocks_without_replacing_winner() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest(id_offset=1, decisions_sha="1" * 64)
    winner = _manifest(id_offset=900, decisions_sha="2" * 64)

    database.add_failpoint(
        "insert_one",
        collection=MANIFEST_COLLECTION,
        callback=lambda fake, _collection, _details: fake.external_insert(
            MANIFEST_COLLECTION,
            _manifest_document(winner),
        ),
    )

    with pytest.raises(ManifestCompatibilityError) as exc_info:
        store.insert_prepared_if_absent(requested)

    assert "decisions_sha256" in exc_info.value.issues
    assert store.get(winner.manifest_key) == winner
    assert database[MANIFEST_COLLECTION].count_documents({}) == 1


def test_malformed_duplicate_race_winner_is_a_typed_compatibility_failure() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest()

    database.add_failpoint(
        "insert_one",
        collection=MANIFEST_COLLECTION,
        callback=lambda fake, _collection, _details: fake.external_insert(
            MANIFEST_COLLECTION,
            {
                "_id": requested.manifest_key,
                "manifest_key": requested.manifest_key,
                "target_database": TARGET,
            },
        ),
    )

    with pytest.raises(ManifestCompatibilityError) as exc_info:
        store.insert_prepared_if_absent(requested)

    assert exc_info.value.issues == ("malformed_race_winner",)
    assert database[MANIFEST_COLLECTION].count_documents({}) == 1
    assert not any(event.kind == "write" for event in database.events)


def test_compatibility_accepts_winner_maps_but_rejects_external_authority() -> None:
    requested = _manifest(id_offset=1)
    race_winner = _manifest(id_offset=300)
    incompatible = race_winner.model_copy(update={"planner_version": "other-planner"})

    assert manifest_compatibility_issues(race_winner, requested) == ()
    assert manifest_compatibility_issues(incompatible, requested) == ("planner_version",)


def test_cas_transition_updates_revision_counters_and_stable_identity_only() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest()
    store.insert_prepared_if_absent(requested)

    updated = store.update_cas(
        requested.manifest_key,
        expected_revision=0,
        allowed_states=(ManifestState.PREPARED,),
        changes={"state": ManifestState.APPLYING_INDEXES, "started_at": MILLISECOND_TIME},
        attempts_increment=1,
    )

    assert updated.state == ManifestState.APPLYING_INDEXES
    assert updated.revision == 1
    assert updated.attempts == 1
    assert updated.started_at == MILLISECOND_TIME
    assert updated.migration_id == requested.migration_id
    assert updated.source_id_map == requested.source_id_map
    assert updated.reference_id_map == requested.reference_id_map
    assert updated.created_at == requested.created_at


def test_stale_revision_and_storage_race_fail_cas_without_overwrite() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest()
    store.insert_prepared_if_absent(requested)

    with pytest.raises(ManifestConcurrentUpdateError, match="revision or state changed"):
        store.update_cas(
            requested.manifest_key,
            expected_revision=1,
            allowed_states=(ManifestState.PREPARED,),
            changes={"state": ManifestState.APPLYING_INDEXES},
        )

    database.add_failpoint(
        "update_one",
        collection=MANIFEST_COLLECTION,
        callback=lambda fake, _collection, _details: fake.external_update_one(
            MANIFEST_COLLECTION,
            {"_id": requested.manifest_key},
            {"revision": 7},
        ),
    )
    with pytest.raises(ManifestConcurrentUpdateError, match="lost a concurrent race"):
        store.update_cas(
            requested.manifest_key,
            expected_revision=0,
            allowed_states=(ManifestState.PREPARED,),
            changes={"state": ManifestState.APPLYING_INDEXES},
        )

    assert store.get(requested.manifest_key).revision == 7


@pytest.mark.parametrize(
    ("current", "requested", "allowed"),
    [
        (ManifestState.PREPARED, ManifestState.PREPARED, True),
        (ManifestState.PREPARED, ManifestState.APPLYING_INDEXES, True),
        (ManifestState.PREPARED, ManifestState.VERIFYING, False),
        (ManifestState.APPLYING_REFERENCES, ManifestState.VERIFYING, True),
        (ManifestState.VERIFYING, ManifestState.APPLIED, True),
        (ManifestState.APPLYING_SOURCES, ManifestState.FAILED, True),
        (ManifestState.FAILED, ManifestState.APPLYING_INDEXES, True),
        (ManifestState.FAILED, ManifestState.APPLYING_SOURCES, False),
        (ManifestState.FAILED, ManifestState.BLOCKED, True),
        (ManifestState.APPLYING_REFERENCES, ManifestState.APPLYING_SOURCES, False),
        (ManifestState.APPLIED, ManifestState.FAILED, False),
        (ManifestState.APPLIED, ManifestState.BLOCKED, False),
        (ManifestState.APPLIED, ManifestState.APPLIED, False),
        (ManifestState.BLOCKED, ManifestState.FAILED, False),
        (ManifestState.BLOCKED, ManifestState.BLOCKED, False),
    ],
)
def test_manifest_state_transition_contract(
    current: ManifestState,
    requested: ManifestState,
    allowed: bool,
) -> None:
    assert state_transition_allowed(current, requested) is allowed


def test_invalid_backward_cas_transition_does_not_write() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest()
    store.insert_prepared_if_absent(requested)
    applying_indexes = store.update_cas(
        requested.manifest_key,
        expected_revision=0,
        allowed_states=(ManifestState.PREPARED,),
        changes={"state": ManifestState.APPLYING_INDEXES},
    )
    applying_sources = store.update_cas(
        requested.manifest_key,
        expected_revision=applying_indexes.revision,
        allowed_states=(ManifestState.APPLYING_INDEXES,),
        changes={"state": ManifestState.APPLYING_SOURCES},
    )
    applying = store.update_cas(
        requested.manifest_key,
        expected_revision=applying_sources.revision,
        allowed_states=(ManifestState.APPLYING_SOURCES,),
        changes={"state": ManifestState.APPLYING_REFERENCES},
    )
    writes_before = len(database.write_events)

    with pytest.raises(ValueError, match="invalid manifest transition"):
        store.update_cas(
            requested.manifest_key,
            expected_revision=applying.revision,
            allowed_states=(ManifestState.APPLYING_REFERENCES,),
            changes={"state": ManifestState.APPLYING_SOURCES},
        )

    assert len(database.write_events) == writes_before
    assert store.get(requested.manifest_key).state == ManifestState.APPLYING_REFERENCES


def test_error_append_is_redacted_bounded_and_revision_guarded() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    store = ManifestStore(database, clock=lambda: FIXED_TIME)
    requested = _manifest()
    store.insert_prepared_if_absent(requested)
    error = bounded_safe_error(
        "mongodb://alice:secret@example.test/db password=hidden /home/alice/private.txt",
        code="reference_insert_failed",
        state=ManifestState.APPLYING_REFERENCES,
        attempt=1,
        occurred_at=FIXED_TIME,
    )

    failed = store.append_error_cas(
        requested.manifest_key,
        expected_revision=0,
        allowed_states=(ManifestState.PREPARED,),
        error=error,
    )

    assert failed.state == ManifestState.FAILED
    assert failed.revision == 1
    assert failed.errors == (error,)
    assert "alice" not in error.message
    assert "secret" not in error.message
    assert "hidden" not in error.message
    assert "/home/alice" not in error.message
    assert "<redacted" in error.message

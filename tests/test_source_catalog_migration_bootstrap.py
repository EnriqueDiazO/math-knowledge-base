"""End-to-end S1C2A bootstrap tests on the deterministic Mongo fake only."""

# ruff: noqa: D101,D102,D103

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import pytest
from source_catalog_migration_fakes import ALLOWED_DOCUMENT_WRITE_COLLECTIONS
from source_catalog_migration_fakes import ALLOWED_INDEX_WRITE_COLLECTIONS
from source_catalog_migration_fakes import LEGACY_COLLECTIONS
from source_catalog_migration_fakes import FakeDatabase

from mathmongo.source_catalog.indexes import SOURCE_CATALOG_INDEXES
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_catalog.models import CopyrightStatus
from mathmongo.source_catalog.models import ImportMethod
from mathmongo.source_catalog.models import RedistributionPolicy
from mathmongo.source_catalog.models import ReferenceStatus
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.models import SourceType
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_catalog.service import SourceCatalogService
from mathmongo.source_catalog_migration.apply_result import ApplyOutcome
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_PLAN_SEMANTIC_SHA256
from mathmongo.source_catalog_migration.apply_safety import AUTHORITATIVE_ZIP_SHA256
from mathmongo.source_catalog_migration.apply_safety import ApplyAuthorization
from mathmongo.source_catalog_migration.apply_safety import capture_legacy_snapshot
from mathmongo.source_catalog_migration.apply_safety import manifest_invariant_hashes
from mathmongo.source_catalog_migration.apply_safety import validate_authoritative_inputs
from mathmongo.source_catalog_migration.bootstrap import BootstrapEngine
from mathmongo.source_catalog_migration.bootstrap import _prepared_index_status
from mathmongo.source_catalog_migration.bootstrap import build_expected_catalog
from mathmongo.source_catalog_migration.decisions import DecisionSet
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION
from mathmongo.source_catalog_migration.manifest import ManifestState
from mathmongo.source_catalog_migration.manifest import ManifestStore
from mathmongo.source_catalog_migration.manifest import allocate_final_ids
from mathmongo.source_catalog_migration.manifest import build_prepared_manifest_from_allocation
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.planner import AUTHORITATIVE_EXPECTATIONS
from mathmongo.source_catalog_migration.planner import build_plan
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport
from mathmongo.source_catalog_migration.zip_reader import read_legacy_export

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_ZIP = PROJECT_ROOT / "mathkb_export_20260712_073927.zip"
TARGET = "MathV0_s1c2_validation_bootstrap_tests"
FIXED_TIME = datetime(2026, 7, 12, 16, 30, 15, 987_654, tzinfo=timezone.utc)
PERSISTED_TIME = FIXED_TIME.replace(microsecond=987_000)
LOCATOR_FIELDS = {
    "paginas",
    "pages",
    "pagina",
    "capitulo",
    "chapter",
    "seccion",
    "section",
    "ecuacion",
    "equation",
    "teorema",
    "theorem",
}
OUT_OF_SCOPE_COLLECTIONS = {
    "concept_evidence_links",
    "documents",
    "pdfs",
    "annotations",
    "reading_notes",
}


@pytest.fixture(scope="module")
def authoritative_export() -> LoadedLegacyExport:
    if not REAL_ZIP.is_file():
        pytest.skip("The approved untracked authoritative ZIP is not present")
    before = (REAL_ZIP.stat().st_size, REAL_ZIP.stat().st_mtime_ns)
    export = read_legacy_export(
        REAL_ZIP,
        database_name="MathV0",
        fail_on_input_change=True,
    )
    after = (REAL_ZIP.stat().st_size, REAL_ZIP.stat().st_mtime_ns)
    assert before == after
    assert export.input_snapshot.sha256 == AUTHORITATIVE_ZIP_SHA256
    return export


@pytest.fixture(scope="module")
def authoritative_plan(authoritative_export: LoadedLegacyExport) -> MigrationPlan:
    plan = build_plan(authoritative_export, expectations=AUTHORITATIVE_EXPECTATIONS)
    assert plan.semantic_sha256 == AUTHORITATIVE_PLAN_SEMANTIC_SHA256
    return plan


@pytest.fixture(scope="module")
def complete_decisions(authoritative_plan: MigrationPlan) -> DecisionSet:
    return DecisionSet(
        zip_sha256=AUTHORITATIVE_ZIP_SHA256,
        plan_semantic_sha256=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
        accept_all_safe_exact=True,
        accepted_reference_candidates=(),
        weak_suggestion_decisions={
            item.suggestion_key: "keep_separate"
            for item in authoritative_plan.weak_reference_suggestions
        },
        locator_review_decisions={
            item.review_key: "defer" for item in authoritative_plan.review_items
        },
    )


@dataclass
class SequentialIdFactory:
    prefix: str
    next_value: int
    calls: int = 0

    def __call__(self) -> str:
        value = f"{self.prefix}_00000000-0000-4000-8000-{self.next_value:012x}"
        self.next_value += 1
        self.calls += 1
        return value


@dataclass
class EngineHarness:
    engine: BootstrapEngine
    source_ids: SequentialIdFactory
    reference_ids: SequentialIdFactory
    migration_ids: SequentialIdFactory


class InjectedInterruptionError(RuntimeError):
    pass


def _authorization() -> ApplyAuthorization:
    return ApplyAuthorization(
        target_database=TARGET,
        allow_isolated_write=True,
        confirmed_database=TARGET,
        expected_zip_sha=AUTHORITATIVE_ZIP_SHA256,
        expected_plan_sha=AUTHORITATIVE_PLAN_SEMANTIC_SHA256,
    )


def _database(export: LoadedLegacyExport) -> FakeDatabase:
    return FakeDatabase(TARGET, export.collections)


def _harness(
    database: FakeDatabase,
    *,
    offset: int = 1,
    checkpoint: Callable[[str, int | None], None] | None = None,
) -> EngineHarness:
    sources = SequentialIdFactory("src", offset)
    references = SequentialIdFactory("ref", offset + 1_000)
    migrations = SequentialIdFactory("mig", offset + 2_000)
    engine = BootstrapEngine(
        database,
        clock=lambda: FIXED_TIME,
        source_id_factory=sources,
        reference_id_factory=references,
        migration_id_factory=migrations,
        checkpoint=checkpoint,
    )
    return EngineHarness(engine, sources, references, migrations)


def _apply(
    harness: EngineHarness,
    export: LoadedLegacyExport,
    plan: MigrationPlan,
    decisions: DecisionSet,
):
    return harness.engine.apply(
        export=export,
        plan=plan,
        decisions=decisions,
        authorization=_authorization(),
    )


def _manifest(database: FakeDatabase):
    values = ManifestStore(database, clock=lambda: FIXED_TIME).find_for_target(TARGET)
    assert len(values) == 1
    return values[0]


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_all_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_all_keys(item))
    return keys


def _interrupt_at(label: str, ordinal: int | None = None):
    def checkpoint(observed_label: str, observed_ordinal: int | None) -> None:
        if observed_label == label and (ordinal is None or observed_ordinal == ordinal):
            raise InjectedInterruptionError(f"interrupted at {label}:{ordinal}")

    return checkpoint


def _forbidden_id() -> str:
    raise AssertionError("a resume must not allocate another final ID")


def test_imported_engine_construction_has_no_io_or_collection_materialization() -> None:
    database = FakeDatabase(TARGET, {"concepts": ()})
    original_names = database.list_collection_names()
    database.clear_events()

    engine = BootstrapEngine(database)

    assert engine.database is database
    assert database.events == ()
    assert database.list_collection_names() == original_names
    assert not database.has_collection(MANIFEST_COLLECTION)
    assert not database.has_collection("sources")
    assert not database.has_collection("references")


@pytest.mark.parametrize(
    ("keyword", "factory"),
    [
        ("manifest_store", ManifestStore),
        ("source_repository", SourceRepository),
        ("reference_repository", ReferenceRepository),
        ("service", SourceCatalogService),
        ("index_manager", SourceCatalogIndexManager),
    ],
)
def test_engine_constructor_rejects_collaborator_bound_to_another_database_without_io(
    keyword: str,
    factory: Callable[[FakeDatabase], Any],
) -> None:
    target = FakeDatabase(TARGET, {"concepts": ()})
    other = FakeDatabase(f"{TARGET}_other", {"concepts": ()})
    collaborator = factory(other)
    target.clear_events()
    other.clear_events()

    with pytest.raises(ValueError, match="database"):
        BootstrapEngine(target, **{keyword: collaborator})

    assert target.events == ()
    assert other.events == ()


def test_engine_constructor_rejects_service_using_different_repository_instances_without_io() -> (
    None
):
    database = FakeDatabase(TARGET, {"concepts": ()})
    engine_sources = SourceRepository(database)
    engine_references = ReferenceRepository(database)
    service = SourceCatalogService(
        database,
        source_repository=SourceRepository(database),
        reference_repository=ReferenceRepository(database),
    )
    database.clear_events()

    with pytest.raises(ValueError, match="service must use the engine repositories"):
        BootstrapEngine(
            database,
            source_repository=engine_sources,
            reference_repository=engine_references,
            service=service,
        )

    assert database.events == ()


def test_expected_catalog_converts_exactly_16_sources_and_20_references(
    authoritative_plan: MigrationPlan,
) -> None:
    allocation = allocate_final_ids(
        (item.source_candidate_key for item in authoritative_plan.source_candidates),
        (item.reference_candidate_key for item in authoritative_plan.reference_candidates),
        source_id_factory=SequentialIdFactory("src", 1),
        reference_id_factory=SequentialIdFactory("ref", 1_001),
        migration_id_factory=SequentialIdFactory("mig", 2_001),
        clock=lambda: FIXED_TIME,
    )
    expected = build_expected_catalog(authoritative_plan, allocation)
    source_candidates = {
        item.source_candidate_key: item for item in authoritative_plan.source_candidates
    }
    reference_candidates = {
        item.reference_candidate_key: item for item in authoritative_plan.reference_candidates
    }

    assert len(expected.sources) == 16
    assert len(expected.references) == 20
    for key, source in expected.sources.items():
        candidate = source_candidates[key]
        assert source.source_id == allocation.source_id_map[key]
        assert source.name == candidate.exact_string
        assert source.name_normalized == candidate.normalized_string
        assert source.source_type == SourceType.OTHER
        assert source.status == SourceStatus.ACTIVE
        assert source.aliases == []
        assert source.legacy.source_strings == list(candidate.legacy_source_strings)
        assert source.legacy.migration_batch_id == allocation.migration_id
        assert source.rights_default.copyright_status == CopyrightStatus.UNKNOWN
        assert source.rights_default.redistribution == RedistributionPolicy.ASK
        assert source.created_at == PERSISTED_TIME
        assert source.updated_at == PERSISTED_TIME

    for key, reference in expected.references.items():
        candidate = reference_candidates[key]
        bibliography = candidate.proposed_bibliography
        assert reference.reference_id == allocation.reference_id_map[key]
        assert reference.source_ids == [
            allocation.source_id_map[source_key] for source_key in candidate.source_candidate_keys
        ]
        assert reference.title == bibliography["title"]
        assert reference.year == bibliography["year"]
        assert reference.doi == bibliography["doi"]
        assert reference.doi_normalized == candidate.normalized_doi
        assert reference.isbn == bibliography["isbn"]
        assert reference.bibtex.key == bibliography["citekey"]
        assert reference.provenance.import_method == ImportMethod.LEGACY
        assert reference.provenance.imported_at == PERSISTED_TIME
        assert reference.status == ReferenceStatus.ACTIVE
        assert reference.created_at == PERSISTED_TIME
        assert reference.updated_at == PERSISTED_TIME
        assert not LOCATOR_FIELDS & _all_keys(reference.model_dump(mode="python"))

    for suggestion in authoritative_plan.weak_reference_suggestions:
        first, second = suggestion.reference_candidate_keys
        assert allocation.reference_id_map[first] != allocation.reference_id_map[second]


def test_complete_apply_orders_writes_and_preserves_every_legacy_collection(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    legacy_before = database.legacy_snapshot()
    checkpoints: list[tuple[str, int | None]] = []
    harness = _harness(
        database,
        checkpoint=lambda label, ordinal: checkpoints.append((label, ordinal)),
    )

    result = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)
    manifest = _manifest(database)

    assert result.outcome == ApplyOutcome.APPLIED
    assert result.manifest_state == ManifestState.APPLIED.value
    assert result.sources_created == 16
    assert result.references_created == 20
    assert result.sources_identical == 0
    assert result.references_identical == 0
    assert result.invariants_passed is True
    assert result.errors == ()
    assert manifest.state == ManifestState.APPLIED
    assert manifest.sources_created == 16
    assert manifest.references_created == 20
    assert manifest.invariant_hashes_before == manifest.invariant_hashes_after
    assert manifest.indexes_status.expected == len(SOURCE_CATALOG_INDEXES)
    assert manifest.indexes_status.missing == 0
    assert SourceRepository(database).count() == 16
    assert ReferenceRepository(database).count() == 20

    manifest_insert = next(
        event
        for event in database.write_events
        if event.collection == MANIFEST_COLLECTION and event.operation == "insert_one"
    )
    first_index = next(
        event for event in database.write_events if event.operation == "create_index"
    )
    first_source = next(
        event
        for event in database.write_events
        if event.collection == "sources" and event.operation == "insert_one"
    )
    first_reference = next(
        event
        for event in database.write_events
        if event.collection == "references" and event.operation == "insert_one"
    )
    assert (
        manifest_insert.sequence
        < first_index.sequence
        < first_source.sequence
        < first_reference.sequence
    )
    assert set(manifest_insert.details["document"]["source_id_map"]) == {
        item.source_candidate_key for item in authoritative_plan.source_candidates
    }
    assert set(manifest_insert.details["document"]["reference_id_map"]) == {
        item.reference_candidate_key for item in authoritative_plan.reference_candidates
    }
    prepared_indexes = manifest_insert.details["document"]["indexes_status"]
    assert prepared_indexes["expected"] == len(SOURCE_CATALOG_INDEXES)
    assert prepared_indexes["missing"] == len(SOURCE_CATALOG_INDEXES)
    assert prepared_indexes["expected_sha256"] == manifest.indexes_status.expected_sha256
    assert prepared_indexes["final_sha256"] is None
    assert checkpoints[0] == ("manifest_prepared", None)
    assert ("indexes_applied", None) in checkpoints
    assert checkpoints.index(("sources_complete", None)) < checkpoints.index(
        ("references_complete", None)
    )
    assert checkpoints[-1] == ("verification_complete", None)

    assert database.legacy_snapshot() == legacy_before
    assert database.forbidden_events == ()
    assert all(event.collection not in LEGACY_COLLECTIONS for event in database.write_events)
    assert all(
        event.collection in ALLOWED_DOCUMENT_WRITE_COLLECTIONS
        for event in database.write_events
        if event.operation in {"insert_one", "update_one", "replace_one"}
    )
    assert all(
        event.collection in ALLOWED_INDEX_WRITE_COLLECTIONS
        for event in database.write_events
        if event.operation == "create_index"
    )

    expected_collections = {
        *authoritative_export.collections,
        "sources",
        "references",
        MANIFEST_COLLECTION,
    }
    assert set(database.list_collection_names()) == expected_collections
    assert not OUT_OF_SCOPE_COLLECTIONS & set(database.list_collection_names())
    for concept in database.snapshot(("concepts",))["concepts"]:
        assert "source_id" not in concept
        assert "reference_id" not in concept
        assert "concept_uid" not in concept
        assert "concept_evidence_links" not in concept

    manifest_document = database[MANIFEST_COLLECTION].documents[0]
    assert not {"concept_bindings", "binding_map", "locator", "raw_variants"} & _all_keys(
        manifest_document
    )
    assert manifest_document["expected_counts"]["bindings"] == 186
    for reference in database["references"].documents:
        assert not LOCATOR_FIELDS & _all_keys(reference)


def test_second_identical_apply_is_a_read_only_noop_with_stable_ids_and_timestamps(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    harness = _harness(database, offset=10_000)
    first = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)
    assert first.outcome == ApplyOutcome.APPLIED
    first_manifest = _manifest(database)
    catalog_before = database.snapshot(("sources", "references"))
    allocation_calls = (
        harness.source_ids.calls,
        harness.reference_ids.calls,
        harness.migration_ids.calls,
    )
    database.clear_events()

    second = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)

    assert second.outcome == ApplyOutcome.ALREADY_APPLIED
    assert second.sources_created == 0
    assert second.references_created == 0
    assert second.sources_identical == 16
    assert second.references_identical == 20
    assert database.snapshot(("sources", "references")) == catalog_before
    assert _manifest(database).source_id_map == first_manifest.source_id_map
    assert _manifest(database).reference_id_map == first_manifest.reference_id_map
    assert (
        harness.source_ids.calls,
        harness.reference_ids.calls,
        harness.migration_ids.calls,
    ) == allocation_calls
    assert database.write_attempt_events == ()


@pytest.mark.parametrize("mutation", ["legacy", "source"])
def test_verification_checkpoint_mutation_cannot_precede_applied_manifest(
    mutation: str,
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    fired = False

    def mutate_at_boundary(label: str, _ordinal: int | None) -> None:
        nonlocal fired
        if label != "verification_complete" or fired:
            return
        fired = True
        if mutation == "legacy":
            database._documents["concepts"][0]["boundary_mutation"] = True
        else:
            database._documents["sources"].pop()

    harness = _harness(database, offset=11_000, checkpoint=mutate_at_boundary)

    result = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)

    assert fired is True
    assert result.outcome == ApplyOutcome.BLOCKED
    assert result.manifest_state == ManifestState.BLOCKED.value
    assert _manifest(database).state == ManifestState.BLOCKED


def test_applied_rerun_rejects_an_unapproved_index_option_without_writing(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    harness = _harness(database, offset=12_000)
    assert (
        _apply(harness, authoritative_export, authoritative_plan, complete_decisions).outcome
        == ApplyOutcome.APPLIED
    )
    index = next(
        item
        for item in database._indexes["sources"]
        if item.get("name") == "sources_source_id_unique"
    )
    index["partialFilterExpression"] = {"source_id": {"$exists": True}}
    database.clear_events()

    second = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)

    assert second.outcome == ApplyOutcome.CONFLICT
    assert database.write_attempt_events == ()


def test_applied_rerun_blocks_tampered_durable_index_evidence_without_writing(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    harness = _harness(database, offset=15_000)
    assert (
        _apply(harness, authoritative_export, authoritative_plan, complete_decisions).outcome
        == ApplyOutcome.APPLIED
    )
    manifest = _manifest(database)
    assert database.external_update_one(
        MANIFEST_COLLECTION,
        {"_id": manifest.manifest_key},
        {"indexes_status.final_sha256": "0" * 64},
    )
    database.clear_events()

    result = _apply(harness, authoritative_export, authoritative_plan, complete_decisions)

    assert result.outcome == ApplyOutcome.BLOCKED
    assert result.manifest_state == ManifestState.APPLIED.value
    assert _manifest(database).state == ManifestState.APPLIED
    assert database.write_attempt_events == ()


def test_interruption_after_sources_resumes_without_new_ids_or_source_timestamps(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    interrupted = _harness(
        database,
        offset=20_000,
        checkpoint=_interrupt_at("sources_complete"),
    )

    failed = _apply(interrupted, authoritative_export, authoritative_plan, complete_decisions)
    failed_manifest = _manifest(database)
    sources_before = database.snapshot(("sources",))

    assert failed.outcome == ApplyOutcome.FAILED
    assert failed.sources_created == 16
    assert failed.references_created == 0
    assert failed_manifest.state == ManifestState.FAILED
    assert failed_manifest.sources_created == 16
    assert failed_manifest.references_created == 0
    assert database["sources"].count_documents({}) == 16
    assert database["references"].count_documents({}) == 0

    resumed = BootstrapEngine(
        database,
        clock=lambda: FIXED_TIME,
        source_id_factory=_forbidden_id,
        reference_id_factory=_forbidden_id,
        migration_id_factory=_forbidden_id,
    ).apply(
        export=authoritative_export,
        plan=authoritative_plan,
        decisions=complete_decisions,
        authorization=_authorization(),
    )

    assert resumed.outcome == ApplyOutcome.RESUMED
    assert resumed.sources_created == 0
    assert resumed.sources_identical == 16
    assert resumed.references_created == 20
    assert resumed.references_identical == 0
    assert database.snapshot(("sources",)) == sources_before
    assert database["references"].count_documents({}) == 20
    applied_manifest = _manifest(database)
    assert applied_manifest.state == ManifestState.APPLIED
    assert applied_manifest.source_id_map == failed_manifest.source_id_map
    assert applied_manifest.reference_id_map == failed_manifest.reference_id_map


def test_partial_reference_interruption_resumes_only_remaining_references(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    interrupted = _harness(
        database,
        offset=30_000,
        checkpoint=_interrupt_at("reference_confirmed", 5),
    )

    failed = _apply(interrupted, authoritative_export, authoritative_plan, complete_decisions)
    failed_manifest = _manifest(database)
    first_five = database.snapshot(("references",))

    assert failed.outcome == ApplyOutcome.FAILED
    assert failed.sources_created == 16
    assert failed.references_created == 5
    assert failed_manifest.state == ManifestState.FAILED
    assert failed_manifest.sources_created == 16
    assert failed_manifest.references_created == 5
    assert database["references"].count_documents({}) == 5

    database.clear_events()
    resumed = BootstrapEngine(
        database,
        clock=lambda: FIXED_TIME,
        source_id_factory=_forbidden_id,
        reference_id_factory=_forbidden_id,
        migration_id_factory=_forbidden_id,
    ).apply(
        export=authoritative_export,
        plan=authoritative_plan,
        decisions=complete_decisions,
        authorization=_authorization(),
    )

    assert resumed.outcome == ApplyOutcome.RESUMED
    assert resumed.sources_created == 0
    assert resumed.sources_identical == 16
    assert resumed.references_created == 15
    assert resumed.references_identical == 5
    assert database["references"].count_documents({}) == 20
    assert all(
        original in database.snapshot(("references",))["references"]
        for original in first_five["references"]
    )
    reference_inserts = [
        event
        for event in database.write_events
        if event.collection == "references" and event.operation == "insert_one"
    ]
    assert len(reference_inserts) == 15
    assert _manifest(database).state == ManifestState.APPLIED


def test_manifest_race_uses_winner_allocation_and_applies_once(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    preflight = validate_authoritative_inputs(
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )
    invariant = manifest_invariant_hashes(capture_legacy_snapshot(database))
    winner_allocation = allocate_final_ids(
        preflight.source_candidate_keys,
        preflight.reference_candidate_keys,
        source_id_factory=SequentialIdFactory("src", 40_000),
        reference_id_factory=SequentialIdFactory("ref", 41_000),
        migration_id_factory=SequentialIdFactory("mig", 42_000),
        clock=lambda: FIXED_TIME,
    )
    winner_expected = build_expected_catalog(authoritative_plan, winner_allocation)
    winner = build_prepared_manifest_from_allocation(
        allocation=winner_allocation,
        target_database=TARGET,
        zip_sha256=preflight.zip_sha256,
        plan_semantic_sha256=preflight.plan_semantic_sha256,
        decisions_sha256=preflight.decisions_sha256,
        expected_counts=preflight.expected_counts,
        source_entity_hashes=winner_expected.source_entity_hashes,
        reference_entity_hashes=winner_expected.reference_entity_hashes,
        reference_evidence_hashes=winner_expected.reference_evidence_hashes,
        reference_evidence_summaries=winner_expected.reference_evidence_summaries,
        planner_version=preflight.planner_version,
        indexes_status=_prepared_index_status(),
        invariant_hashes_before=invariant,
    )

    def install_winner(
        fake: FakeDatabase,
        collection: str | None,
        _details: dict,
    ) -> None:
        assert collection == MANIFEST_COLLECTION
        document = winner.model_dump(mode="python")
        document["_id"] = winner.manifest_key
        fake.external_insert(MANIFEST_COLLECTION, document)

    database.add_failpoint(
        "insert_one",
        collection=MANIFEST_COLLECTION,
        callback=install_winner,
    )
    loser_harness = _harness(database, offset=50_000)

    result = _apply(
        loser_harness,
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert result.outcome == ApplyOutcome.RESUMED
    applied = _manifest(database)
    assert applied.migration_id == winner.migration_id
    assert applied.source_id_map == winner.source_id_map
    assert applied.reference_id_map == winner.reference_id_map
    assert set(document["source_id"] for document in database["sources"].documents) == set(
        winner.source_id_map.values()
    )
    assert set(document["reference_id"] for document in database["references"].documents) == set(
        winner.reference_id_map.values()
    )
    assert database[MANIFEST_COLLECTION].count_documents({}) == 1


def test_manifest_race_with_different_decisions_blocks_without_altering_winner(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    preflight = validate_authoritative_inputs(
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )
    invariant = manifest_invariant_hashes(capture_legacy_snapshot(database))
    winner_allocation = allocate_final_ids(
        preflight.source_candidate_keys,
        preflight.reference_candidate_keys,
        source_id_factory=SequentialIdFactory("src", 52_000),
        reference_id_factory=SequentialIdFactory("ref", 53_000),
        migration_id_factory=SequentialIdFactory("mig", 54_000),
        clock=lambda: FIXED_TIME,
    )
    winner_expected = build_expected_catalog(authoritative_plan, winner_allocation)
    assert preflight.decisions_sha256 != "0" * 64
    winner = build_prepared_manifest_from_allocation(
        allocation=winner_allocation,
        target_database=TARGET,
        zip_sha256=preflight.zip_sha256,
        plan_semantic_sha256=preflight.plan_semantic_sha256,
        decisions_sha256="0" * 64,
        expected_counts=preflight.expected_counts,
        source_entity_hashes=winner_expected.source_entity_hashes,
        reference_entity_hashes=winner_expected.reference_entity_hashes,
        reference_evidence_hashes=winner_expected.reference_evidence_hashes,
        reference_evidence_summaries=winner_expected.reference_evidence_summaries,
        planner_version=preflight.planner_version,
        indexes_status=_prepared_index_status(),
        invariant_hashes_before=invariant,
    )

    def install_incompatible_winner(
        fake: FakeDatabase,
        collection: str | None,
        _details: dict,
    ) -> None:
        assert collection == MANIFEST_COLLECTION
        document = winner.model_dump(mode="python")
        document["_id"] = winner.manifest_key
        fake.external_insert(MANIFEST_COLLECTION, document)

    database.add_failpoint(
        "insert_one",
        collection=MANIFEST_COLLECTION,
        callback=install_incompatible_winner,
    )

    result = _apply(
        _harness(database, offset=55_000),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert result.outcome == ApplyOutcome.BLOCKED
    loaded = _manifest(database)
    assert loaded == winner
    assert loaded.decisions_sha256 == "0" * 64
    assert loaded.state == ManifestState.PREPARED
    assert loaded.revision == 0
    assert loaded.errors == ()
    assert database[MANIFEST_COLLECTION].count_documents({}) == 1
    assert not database.has_collection("sources")
    assert not database.has_collection("references")
    assert not any(event.operation == "create_index" for event in database.write_events)
    assert database.write_events == ()


def test_manifest_race_with_blocked_compatible_winner_performs_no_successful_write(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    preflight = validate_authoritative_inputs(
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )
    invariant = manifest_invariant_hashes(capture_legacy_snapshot(database))
    allocation = allocate_final_ids(
        preflight.source_candidate_keys,
        preflight.reference_candidate_keys,
        source_id_factory=SequentialIdFactory("src", 54_100),
        reference_id_factory=SequentialIdFactory("ref", 55_100),
        migration_id_factory=SequentialIdFactory("mig", 56_100),
        clock=lambda: FIXED_TIME,
    )
    expected = build_expected_catalog(authoritative_plan, allocation)
    winner = build_prepared_manifest_from_allocation(
        allocation=allocation,
        target_database=TARGET,
        zip_sha256=preflight.zip_sha256,
        plan_semantic_sha256=preflight.plan_semantic_sha256,
        decisions_sha256=preflight.decisions_sha256,
        expected_counts=preflight.expected_counts,
        source_entity_hashes=expected.source_entity_hashes,
        reference_entity_hashes=expected.reference_entity_hashes,
        reference_evidence_hashes=expected.reference_evidence_hashes,
        invariant_hashes_before=invariant,
        reference_evidence_summaries=expected.reference_evidence_summaries,
        planner_version=preflight.planner_version,
        indexes_status=_prepared_index_status(),
    ).model_copy(update={"state": ManifestState.BLOCKED})

    def install_blocked_winner(
        fake: FakeDatabase,
        collection: str | None,
        _details: dict[str, Any],
    ) -> None:
        assert collection == MANIFEST_COLLECTION
        document = winner.model_dump(mode="python")
        document["_id"] = winner.manifest_key
        fake.external_insert(MANIFEST_COLLECTION, document)

    database.add_failpoint(
        "insert_one",
        collection=MANIFEST_COLLECTION,
        callback=install_blocked_winner,
    )

    result = _apply(
        _harness(database, offset=57_100),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert result.outcome == ApplyOutcome.BLOCKED
    assert result.manifest_state == ManifestState.BLOCKED.value
    persisted = _manifest(database)
    assert persisted.state == ManifestState.BLOCKED
    assert persisted.revision == 0
    assert persisted.errors == ()
    assert database.write_events == ()
    assert not database.has_collection("sources")
    assert not database.has_collection("references")


def test_lost_cas_to_advanced_competitor_never_marks_manifest_failed_or_appends_error(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)

    def advance_manifest(
        fake: FakeDatabase,
        collection: str | None,
        _details: dict,
    ) -> None:
        assert collection == MANIFEST_COLLECTION
        assert fake.external_update_one(
            MANIFEST_COLLECTION,
            {"revision": 0, "state": ManifestState.PREPARED.value},
            {
                "revision": 1,
                "state": ManifestState.APPLYING_INDEXES.value,
                "attempts": 1,
                "started_at": PERSISTED_TIME,
                "last_updated_at": PERSISTED_TIME,
            },
        )

    lost_cas = database.add_failpoint(
        "update_one",
        collection=MANIFEST_COLLECTION,
        occurrence=1,
        callback=advance_manifest,
    )

    result = _apply(
        _harness(database, offset=57_000),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert lost_cas.fired is True
    assert result.outcome == ApplyOutcome.FAILED
    assert result.manifest_state == ManifestState.APPLYING_INDEXES.value
    winner = _manifest(database)
    assert winner.state == ManifestState.APPLYING_INDEXES
    assert winner.revision == 1
    assert winner.attempts == 1
    assert winner.errors == ()
    manifest_updates = [
        event
        for event in database.write_events
        if event.collection == MANIFEST_COLLECTION and event.operation == "update_one"
    ]
    assert len(manifest_updates) == 1
    assert manifest_updates[0].details["matched_count"] == 0
    assert "errors" not in manifest_updates[0].details["update"].get("$set", {})
    assert ManifestState.FAILED.value not in str(manifest_updates[0].details)
    assert not database.has_collection("sources")
    assert not database.has_collection("references")
    assert not any(event.operation == "create_index" for event in database.write_events)


def test_identical_entities_inserted_between_lookup_and_duplicate_detection_are_adopted(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    offset = 55_000
    allocation = allocate_final_ids(
        (item.source_candidate_key for item in authoritative_plan.source_candidates),
        (item.reference_candidate_key for item in authoritative_plan.reference_candidates),
        source_id_factory=SequentialIdFactory("src", offset),
        reference_id_factory=SequentialIdFactory("ref", offset + 1_000),
        migration_id_factory=SequentialIdFactory("mig", offset + 2_000),
        clock=lambda: FIXED_TIME,
    )
    expected = build_expected_catalog(authoritative_plan, allocation)
    first_source_key = sorted(expected.sources)[0]
    first_reference_key = sorted(expected.references)[0]

    source_race = database.add_failpoint(
        "find",
        collection="sources",
        occurrence=1,
        callback=lambda fake, collection, _details: fake.external_insert(
            str(collection),
            expected.sources[first_source_key].model_dump(mode="python"),
        ),
    )
    reference_race = database.add_failpoint(
        "find",
        collection="references",
        occurrence=1,
        callback=lambda fake, collection, _details: fake.external_insert(
            str(collection),
            expected.references[first_reference_key].model_dump(mode="python"),
        ),
    )

    result = _apply(
        _harness(database, offset=offset),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert result.outcome == ApplyOutcome.APPLIED
    assert source_race.fired is True
    assert reference_race.fired is True
    assert result.sources_created == 15
    assert result.sources_identical == 1
    assert result.references_created == 19
    assert result.references_identical == 1
    assert database["sources"].count_documents({}) == 16
    assert database["references"].count_documents({}) == 20
    assert len({item["source_id"] for item in database["sources"].documents}) == 16
    assert len({item["reference_id"] for item in database["references"].documents}) == 20
    manifest = _manifest(database)
    assert manifest.sources_created == 15
    assert manifest.sources_identical == 1
    assert manifest.references_created == 19
    assert manifest.references_identical == 1


def test_foreign_source_duplicate_inserted_during_service_recheck_blocks_without_rollback(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    offset = 58_000
    allocation = allocate_final_ids(
        (item.source_candidate_key for item in authoritative_plan.source_candidates),
        (item.reference_candidate_key for item in authoritative_plan.reference_candidates),
        source_id_factory=SequentialIdFactory("src", offset),
        reference_id_factory=SequentialIdFactory("ref", offset + 1_000),
        migration_id_factory=SequentialIdFactory("mig", offset + 2_000),
        clock=lambda: FIXED_TIME,
    )
    expected = build_expected_catalog(authoritative_plan, allocation)
    first_key = sorted(expected.sources)[0]
    candidate = expected.sources[first_key]
    foreign_id = SequentialIdFactory("src", 900_000)()
    foreign = candidate.model_copy(update={"source_id": foreign_id})

    # The engine's first duplicate detector performs two bounded finds.  The
    # third is the first find in create_source's internal recheck.
    race = database.add_failpoint(
        "find",
        collection="sources",
        occurrence=3,
        callback=lambda fake, collection, _details: fake.external_insert(
            str(collection),
            foreign.model_dump(mode="python"),
        ),
    )

    result = _apply(
        _harness(database, offset=offset),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert race.fired is True
    assert result.outcome == ApplyOutcome.CONFLICT
    assert result.manifest_state == ManifestState.BLOCKED.value
    manifest = _manifest(database)
    assert manifest.state == ManifestState.BLOCKED
    assert manifest.sources_created == 1
    assert result.sources_created == 1
    source_ids = {document["source_id"] for document in database["sources"].documents}
    assert source_ids == {foreign_id, candidate.source_id}
    stored_foreign = database["sources"].find_one({"source_id": foreign_id})
    assert stored_foreign is not None
    assert stored_foreign["name"] == candidate.name
    assert database["references"].count_documents({}) == 0
    assert database.forbidden_events == ()
    assert not any(event.operation.startswith(("delete", "drop")) for event in database.events)


def test_foreign_reference_duplicate_inserted_during_service_recheck_blocks_without_rollback(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    offset = 61_000
    allocation = allocate_final_ids(
        (item.source_candidate_key for item in authoritative_plan.source_candidates),
        (item.reference_candidate_key for item in authoritative_plan.reference_candidates),
        source_id_factory=SequentialIdFactory("src", offset),
        reference_id_factory=SequentialIdFactory("ref", offset + 1_000),
        migration_id_factory=SequentialIdFactory("mig", offset + 2_000),
        clock=lambda: FIXED_TIME,
    )
    expected = build_expected_catalog(authoritative_plan, allocation)
    first_key = sorted(expected.references)[0]
    candidate = expected.references[first_key]
    assert candidate.fingerprints.author_title_year
    assert candidate.title
    foreign_id = SequentialIdFactory("ref", 910_000)()
    foreign = candidate.model_copy(update={"reference_id": foreign_id})

    # This authoritative Reference causes one identity find plus one suggestion
    # find in the engine detector; occurrence three enters the service recheck.
    race = database.add_failpoint(
        "find",
        collection="references",
        occurrence=3,
        callback=lambda fake, collection, _details: fake.external_insert(
            str(collection),
            foreign.model_dump(mode="python"),
        ),
    )

    result = _apply(
        _harness(database, offset=offset),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert race.fired is True
    assert result.outcome == ApplyOutcome.CONFLICT
    assert result.manifest_state == ManifestState.BLOCKED.value
    manifest = _manifest(database)
    assert manifest.state == ManifestState.BLOCKED
    assert manifest.sources_created == 16
    assert manifest.references_created == 1
    assert result.references_created == 1
    reference_ids = {document["reference_id"] for document in database["references"].documents}
    assert reference_ids == {foreign_id, candidate.reference_id}
    stored_foreign = database["references"].find_one({"reference_id": foreign_id})
    assert stored_foreign is not None
    assert stored_foreign["title"] == candidate.title
    assert database["sources"].count_documents({}) == 16
    assert database.forbidden_events == ()
    assert not any(event.operation.startswith(("delete", "drop")) for event in database.events)


def test_different_existing_content_blocks_resume_without_overwrite(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    interrupted = _harness(
        database,
        offset=60_000,
        checkpoint=_interrupt_at("sources_complete"),
    )
    assert (
        _apply(interrupted, authoritative_export, authoritative_plan, complete_decisions).outcome
        == ApplyOutcome.FAILED
    )
    manifest = _manifest(database)
    source_id = next(iter(manifest.source_id_map.values()))
    assert database.external_update_one(
        "sources",
        {"source_id": source_id},
        {"name": "externally conflicting Source"},
    )
    conflicting = database["sources"].find_one({"source_id": source_id})
    database.clear_events()

    blocked = BootstrapEngine(
        database,
        clock=lambda: FIXED_TIME,
        source_id_factory=_forbidden_id,
        reference_id_factory=_forbidden_id,
        migration_id_factory=_forbidden_id,
    ).apply(
        export=authoritative_export,
        plan=authoritative_plan,
        decisions=complete_decisions,
        authorization=_authorization(),
    )

    assert blocked.outcome == ApplyOutcome.BLOCKED
    assert blocked.manifest_state == ManifestState.BLOCKED.value
    assert _manifest(database).state == ManifestState.BLOCKED
    assert database["sources"].find_one({"source_id": source_id}) == conflicting
    assert not any(
        event.operation == "insert_one" and event.collection in {"sources", "references"}
        for event in database.write_events
    )


def test_partial_catalog_without_manifest_blocks_before_any_bootstrap_write(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)
    database.seed_collection("sources", ())

    result = _apply(
        _harness(database, offset=70_000),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert result.outcome == ApplyOutcome.BLOCKED
    assert result.migration_id is None
    assert result.manifest_state is None
    assert database.has_collection("sources")
    assert database["sources"].count_documents({}) == 0
    assert not database.has_collection(MANIFEST_COLLECTION)
    assert database.write_attempt_events == ()


def test_index_conflict_blocks_manifest_without_entities_or_index_overwrite(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)

    def install_conflict(label: str, _ordinal: int | None) -> None:
        if label != "manifest_prepared":
            return
        database.seed_collection(
            "sources",
            (),
            indexes=(
                {"name": "_id_", "key": {"_id": 1}, "unique": True},
                {
                    "name": "sources_source_id_unique",
                    "key": {"source_id": 1},
                    "unique": False,
                },
            ),
        )

    result = _apply(
        _harness(database, offset=80_000, checkpoint=install_conflict),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert result.outcome == ApplyOutcome.CONFLICT
    assert result.manifest_state == ManifestState.BLOCKED.value
    blocked_manifest = _manifest(database)
    assert blocked_manifest.state == ManifestState.BLOCKED
    assert blocked_manifest.indexes_status.expected == len(SOURCE_CATALOG_INDEXES)
    assert blocked_manifest.indexes_status.missing == len(SOURCE_CATALOG_INDEXES) - 1
    assert blocked_manifest.indexes_status.conflicts == ("sources_source_id_unique",)
    assert blocked_manifest.indexes_status.final_sha256 == result.indexes.final_state_sha256
    assert result.indexes.conflicts == ("sources_source_id_unique",)
    assert len(result.indexes.planned) == len(SOURCE_CATALOG_INDEXES)
    assert database["sources"].count_documents({}) == 0
    assert database["references"].count_documents({}) == 0
    assert not any(event.operation == "create_index" for event in database.write_events)
    conflict = next(
        item
        for item in database["sources"].list_indexes()
        if item["name"] == "sources_source_id_unique"
    )
    assert conflict["unique"] is False


def test_index_conflict_race_during_apply_is_typed_and_blocks_without_entities(
    authoritative_export: LoadedLegacyExport,
    authoritative_plan: MigrationPlan,
    complete_decisions: DecisionSet,
) -> None:
    database = _database(authoritative_export)

    def race_conflict(
        fake: FakeDatabase,
        collection: str | None,
        _details: dict[str, Any],
    ) -> None:
        assert collection == "sources"
        fake.seed_collection(
            "sources",
            (),
            indexes=(
                {"name": "_id_", "key": {"_id": 1}, "unique": True},
                {
                    "name": "sources_source_id_unique",
                    "key": {"source_id": 1},
                    "unique": False,
                },
            ),
        )

    failpoint = database.add_failpoint(
        "create_index",
        collection="sources",
        callback=race_conflict,
    )

    result = _apply(
        _harness(database, offset=90_000),
        authoritative_export,
        authoritative_plan,
        complete_decisions,
    )

    assert failpoint.fired is True
    assert result.outcome == ApplyOutcome.CONFLICT
    assert result.manifest_state == ManifestState.BLOCKED.value
    blocked_manifest = _manifest(database)
    assert blocked_manifest.state == ManifestState.BLOCKED
    assert blocked_manifest.indexes_status.expected == len(SOURCE_CATALOG_INDEXES)
    assert blocked_manifest.indexes_status.conflicts == ("sources_source_id_unique",)
    assert blocked_manifest.indexes_status.final_sha256 == result.indexes.final_state_sha256
    assert result.indexes.conflicts == ("sources_source_id_unique",)
    assert database["sources"].count_documents({}) == 0
    assert database["references"].count_documents({}) == 0
    assert not any(
        event.kind == "write" and event.operation == "create_index" for event in database.events
    )

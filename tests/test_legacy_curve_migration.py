"""Essential regression tests for the exact Legacy Curve migration."""

# ruff: noqa: D103

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from datetime import timezone
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId

from editor.utils import db_import
from editor.utils.db_portability import legacy_concept_portability_issues
from mathkb_config import PORTABLE_EXTENDED_JSON_COLLECTIONS
from mathmongo import legacy_curve_migration as migration
from mathmongo.legacy_concept_aliases import normalize_legacy_concept_documents

FIXED = datetime(2026, 7, 28, 20, 0, tzinfo=timezone.utc)


class _Cursor(list):
    def limit(self, count: int) -> _Cursor:
        return _Cursor(self[:count])


class _Collection:
    def __init__(self, database: _Database, name: str) -> None:
        self.database, self.name = database, name

    @property
    def documents(self) -> list[dict[str, Any]]:
        return self.database.documents.setdefault(self.name, [])

    @staticmethod
    def matches(document: dict, query: dict) -> bool:
        return all(document.get(key) == value for key, value in query.items())

    def find(self, query: dict) -> _Cursor:
        return _Cursor(
            deepcopy(item)
            for item in self.database.documents.get(self.name, [])
            if self.matches(item, query)
        )

    def find_one(self, query: dict) -> dict | None:
        return next(iter(self.find(query)), None)

    def count_documents(self, query: dict) -> int:
        return sum(self.matches(item, query) for item in self.documents)

    def insert_one(self, document: dict) -> None:
        self.database.insert_count += 1
        if self.database.fail_on_insert == self.database.insert_count:
            raise RuntimeError("injected failure")
        self.documents.append(deepcopy(document))
        self.database.events.append(self.name)

    def delete_one(self, query: dict) -> Any:
        for index, item in enumerate(self.documents):
            if self.matches(item, query):
                self.documents.pop(index)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _Database:
    name = "MathV0"

    def __init__(self, documents: dict[str, list[dict]]) -> None:
        self.documents = deepcopy(documents)
        self.events: list[str] = []
        self.insert_count = 0
        self.fail_on_insert: int | None = None

    def __getitem__(self, name: str) -> _Collection:
        return _Collection(self, name)

    def snapshot(self) -> dict[str, list[dict]]:
        return deepcopy(self.documents)


def _fixture(monkeypatch: pytest.MonkeyPatch) -> tuple[_Database, list[dict]]:
    recovered = [
        {
            "_id": ObjectId("697000000000000000000001"),
            "id": "id_Curves_001",
            "source": migration.SOURCE,
            "title": "fixture-one",
        },
        {
            "_id": ObjectId("697000000000000000000002"),
            "id": "id_Curves_002",
            "source": migration.SOURCE,
            "title": "fixture-two",
        },
    ]
    monkeypatch.setattr(
        migration,
        "EXPECTED_CONCEPT_HASHES",
        {
            (item["id"], item["source"]): migration._hash(item)
            for item in recovered
        },
    )
    links = [
        {
            "_id": ObjectId(),
            "evidence_link_id": link_id,
            "concept_legacy_id": identity[0],
            "concept_legacy_source": identity[1],
        }
        for link_id, identity in migration.EXPECTED_LINK_IDENTITIES.items()
    ]
    database = _Database(
        {
            "concepts": [{"_id": ObjectId(), "id": "unrelated", "source": "other"}],
            "concept_evidence_links": links,
            "source_catalog_migration_manifest": [{"_id": "source-catalog-marker"}],
            migration.MIGRATION_MARKER_COLLECTION: [{"_id": "unrelated-marker"}],
        }
    )
    return database, recovered


@pytest.mark.parametrize("postcondition", ("concepts", "links", "marker"))
def test_restores_two_concepts_validates_six_links_and_marks_last(
    monkeypatch: pytest.MonkeyPatch,
    postcondition: str,
) -> None:
    database, recovered = _fixture(monkeypatch)
    result = migration.apply_legacy_curve_migration(
        database,
        recovered,
        clock=lambda: FIXED,
    )
    issues = legacy_concept_portability_issues(
        database["concept_evidence_links"].documents,
        count_matching_concepts=lambda concept_id, source: database[
            "concepts"
        ].count_documents({"id": concept_id, "source": source}),
    )

    assert result == {
        "already_applied": False,
        "concepts_restored": 2,
        "links_matched": 6,
    }
    checks = {
        "concepts": result["concepts_restored"] == 2,
        "links": issues == (),
        "marker": (
            database.events[-1] == migration.MIGRATION_MARKER_COLLECTION
            and database["source_catalog_migration_manifest"].documents
            == [{"_id": "source-catalog-marker"}]
        ),
    }
    assert checks[postcondition]


def test_second_execution_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    database, recovered = _fixture(monkeypatch)
    migration.apply_legacy_curve_migration(database, recovered, clock=lambda: FIXED)
    snapshot, events = database.snapshot(), list(database.events)

    result = migration.apply_legacy_curve_migration(database, recovered)

    assert result["already_applied"] is True
    assert result["concepts_restored"] == 0
    assert database.snapshot() == snapshot
    assert database.events == events


def test_marker_is_operational_and_not_a_portable_source_catalog_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, recovered = _fixture(monkeypatch)
    migration.apply_legacy_curve_migration(database, recovered, clock=lambda: FIXED)
    marker = database[migration.MIGRATION_MARKER_COLLECTION].documents[1]

    migration.validate_legacy_curve_manifest(marker)
    assert migration.MIGRATION_MARKER_COLLECTION not in PORTABLE_EXTENDED_JSON_COLLECTIONS
    with pytest.raises(ValueError, match="Source Catalog manifest"):
        db_import._validate_portable_manifest(marker)


@pytest.mark.parametrize("failure_at", (1, 2, 3))
def test_partial_failure_rolls_back_without_marker(
    monkeypatch: pytest.MonkeyPatch,
    failure_at: int,
) -> None:
    database, recovered = _fixture(monkeypatch)
    snapshot = database.snapshot()
    database.fail_on_insert = failure_at

    with pytest.raises(migration.LegacyCurveMigrationError, match="rollback verified"):
        migration.apply_legacy_curve_migration(database, recovered)

    assert database.snapshot() == snapshot
    assert database[migration.MIGRATION_MARKER_COLLECTION].count_documents(
        {"_id": migration.MIGRATION_ID}
    ) == 0


def test_inexact_recovered_concept_is_rejected_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, recovered = _fixture(monkeypatch)
    recovered[0]["title"] = "changed"
    with pytest.raises(migration.LegacyCurveMigrationError):
        migration.apply_legacy_curve_migration(database, recovered)
    assert database.events == []


def test_unknown_alias_remains_subject_to_strict_portability() -> None:
    link = {
        "evidence_link_id": "ev_unknown",
        "concept_legacy_id": "unknown",
        "concept_legacy_source": "unknown-source",
    }
    normalized, changes = normalize_legacy_concept_documents(
        "concept_evidence_links",
        [link],
    )
    issues = legacy_concept_portability_issues(
        normalized,
        count_matching_concepts=lambda _concept_id, _source: 0,
    )
    assert changes == ()
    assert issues[0].cause == "absent"


def test_ambiguous_alias_is_rejected() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        normalize_legacy_concept_documents(
            "concepts",
            [{"id": "legacy", "source": "source"}],
            registry={
                ("legacy", "source"): (
                    ("canonical-1", "source"),
                    ("canonical-2", "source"),
                )
            },
        )


@pytest.mark.parametrize("legacy", [True, False])
def test_legacy_is_normalized_once_and_canonical_is_unchanged(legacy: bool) -> None:
    identity = ("legacy", "source") if legacy else ("canonical", "source")
    normalized, changes = normalize_legacy_concept_documents(
        "concepts",
        [{"id": identity[0], "source": identity[1]}],
        registry={("legacy", "source"): (("canonical", "source"),)},
    )
    repeated, repeated_changes = normalize_legacy_concept_documents(
        "concepts",
        normalized,
        registry={("legacy", "source"): (("canonical", "source"),)},
    )
    assert normalized[0]["id"] == "canonical"
    assert len(changes) == int(legacy)
    assert repeated == normalized
    assert repeated_changes == ()

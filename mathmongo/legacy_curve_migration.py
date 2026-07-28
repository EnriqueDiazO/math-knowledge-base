"""Minimal idempotent migration for the six Legacy Curve evidence links."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from datetime import timezone
from typing import Any

from bson.json_util import CANONICAL_JSON_OPTIONS
from bson.json_util import dumps as bson_json_dumps

from mathmongo.legacy_concept_aliases import LEGACY_CONCEPT_ALIAS_REGISTRY
from mathmongo.legacy_concept_aliases import REGISTRY_SHA256
from mathmongo.legacy_concept_aliases import Identity
from mathmongo.source_catalog_migration.manifest import MANIFEST_COLLECTION

MIGRATION_ID = "2026_07_28_canonicalize_bottcher_karlovich_curve_links"
MIGRATION_TYPE = "legacy_concept_evidence_canonicalization"
MIGRATION_CHECKSUM = "43ed779ebfaaf7a0b27fc502cb743f9bd97143e8cb2975a15990c75aa4c895e4"
SOURCE = "BottcherKarlovich1997"

EXPECTED_LINK_IDENTITIES: dict[str, Identity] = {
    "ev_1d959db5-d558-48dc-b244-11e4a016045b": ("id_Curves_002", SOURCE),
    "ev_1f08231b-b33e-4830-9e0d-81bf348a8091": ("id_Curves_001", SOURCE),
    "ev_681b816d-6f3b-4af7-b50e-243d27c1ecff": ("id_Curves_001", SOURCE),
    "ev_871c5f9b-3469-41b7-aae6-10a08c45bd6c": ("id_Curves_002", SOURCE),
    "ev_d071197a-2b25-4655-a055-0b4a016a1a15": ("id_Curves_001", SOURCE),
    "ev_dde39062-3745-4fb1-9503-882629d97587": ("id_Curves_001", SOURCE),
}
EXPECTED_CONCEPT_HASHES: dict[Identity, str] = {
    ("id_Curves_001", SOURCE): (
        "2ea479796f9afedccc726defe4cfa4bab3ca2ee9434ac86bc91ee10e37dd7eb3"
    ),
    ("id_Curves_002", SOURCE): (
        "971b2413bd9c9ccb012c91856b8e1da6b0976af79865cd6512570132008f158a"
    ),
}


class LegacyCurveMigrationError(RuntimeError):
    """An exact migration precondition or postcondition failed."""


def _hash(document: Mapping[str, Any]) -> str:
    encoded = bson_json_dumps(
        document,
        json_options=CANONICAL_JSON_OPTIONS,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _matches(collection: Any, query: Mapping[str, Any]) -> tuple[dict, ...]:
    cursor = collection.find(dict(query))
    if callable(getattr(cursor, "limit", None)):
        cursor = cursor.limit(2)
    return tuple(deepcopy(item) for item in cursor)


def _mapping_records() -> list[dict[str, str]]:
    return [
        {
            "legacy_id": legacy[0],
            "legacy_source": legacy[1],
            "canonical_id": targets[0][0],
            "canonical_source": targets[0][1],
        }
        for legacy, targets in sorted(LEGACY_CONCEPT_ALIAS_REGISTRY.items())
    ]


def validate_legacy_curve_manifest(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the applied marker while preserving its portable payload."""
    payload = dict(document)
    mongo_id = payload.pop("_id", MIGRATION_ID)
    required = {
        "manifest_key": MIGRATION_ID,
        "migration_id": MIGRATION_ID,
        "migration_type": MIGRATION_TYPE,
        "state": "applied",
        "checksum_sha256": MIGRATION_CHECKSUM,
        "registry_sha256": REGISTRY_SHA256,
        "mapping": _mapping_records(),
        "evidence_link_ids": sorted(EXPECTED_LINK_IDENTITIES),
        "links_matched": 6,
    }
    if mongo_id != MIGRATION_ID or any(payload.get(key) != value for key, value in required.items()):
        raise ValueError("Legacy Curve migration manifest is incompatible")
    if not isinstance(payload.get("applied_at"), datetime):
        raise ValueError("Legacy Curve migration manifest has no applied timestamp")
    return payload


def _recovered_documents(
    documents: Iterable[Mapping[str, Any]],
) -> dict[Identity, dict[str, Any]]:
    recovered: dict[Identity, dict[str, Any]] = {}
    for raw in documents:
        document = dict(raw)
        identity = (document.get("id"), document.get("source"))
        if identity not in EXPECTED_CONCEPT_HASHES:
            continue
        if identity in recovered or _hash(document) != EXPECTED_CONCEPT_HASHES[identity]:
            raise LegacyCurveMigrationError("Recovered Concept is ambiguous or inexact")
        recovered[identity] = document
    if set(recovered) != set(EXPECTED_CONCEPT_HASHES):
        raise LegacyCurveMigrationError("Both exact recovered Concepts are required")
    return recovered


def _preflight(database: Any, recovered: Mapping[Identity, Mapping[str, Any]]) -> list[Identity]:
    to_restore: list[Identity] = []
    for identity, expected_hash in EXPECTED_CONCEPT_HASHES.items():
        current = _matches(
            database["concepts"],
            {"id": identity[0], "source": identity[1]},
        )
        if len(current) > 1 or (current and _hash(current[0]) != expected_hash):
            raise LegacyCurveMigrationError("Canonical Concept is ambiguous or inexact")
        if current:
            continue
        if _matches(database["concepts"], {"_id": recovered[identity].get("_id")}):
            raise LegacyCurveMigrationError("Recovered Concept _id is already occupied")
        to_restore.append(identity)
    for link_id, identity in EXPECTED_LINK_IDENTITIES.items():
        links = _matches(
            database["concept_evidence_links"],
            {"evidence_link_id": link_id},
        )
        if len(links) != 1 or (
            links[0].get("concept_legacy_id"),
            links[0].get("concept_legacy_source"),
        ) != identity:
            raise LegacyCurveMigrationError("Evidence Link precondition failed")
    return to_restore


def _validate_links(database: Any) -> None:
    for link_id, identity in EXPECTED_LINK_IDENTITIES.items():
        if len(
            _matches(
                database["concept_evidence_links"],
                {"evidence_link_id": link_id},
            )
        ) != 1 or database["concepts"].count_documents(
            {"id": identity[0], "source": identity[1]}
        ) != 1:
            raise LegacyCurveMigrationError("Evidence Link postcondition failed")


def _rollback(
    database: Any,
    inserted: list[Mapping[str, Any]],
    marker: Mapping[str, Any] | None,
) -> bool:
    verified = True
    if marker is not None:
        current = database[MANIFEST_COLLECTION].find_one({"_id": MIGRATION_ID})
        if current is not None and _hash(current) == _hash(marker):
            result = database[MANIFEST_COLLECTION].delete_one(
                {"_id": MIGRATION_ID, "applied_at": marker["applied_at"]}
            )
            verified &= getattr(result, "deleted_count", 0) == 1
        elif current is not None:
            verified = False
    for document in reversed(inserted):
        current = database["concepts"].find_one({"_id": document.get("_id")})
        if current is None:
            continue
        if _hash(current) != _hash(document):
            verified = False
            continue
        result = database["concepts"].delete_one({"_id": document.get("_id")})
        verified &= getattr(result, "deleted_count", 0) == 1
    return bool(verified)


def apply_legacy_curve_migration(
    database: Any,
    recovered_concepts: Iterable[Mapping[str, Any]],
    *,
    clock: Any = None,
) -> dict[str, Any]:
    """Restore two exact Concepts, validate six links, then persist one marker."""
    existing = database[MANIFEST_COLLECTION].find_one({"_id": MIGRATION_ID})
    if existing is not None:
        validate_legacy_curve_manifest(existing)
        _validate_links(database)
        return {"already_applied": True, "concepts_restored": 0, "links_matched": 6}

    recovered = _recovered_documents(recovered_concepts)
    to_restore = _preflight(database, recovered)
    inserted: list[Mapping[str, Any]] = []
    marker: dict[str, Any] | None = None
    try:
        for identity in to_restore:
            document = deepcopy(recovered[identity])
            inserted.append(document)
            database["concepts"].insert_one(document)
        _validate_links(database)
        applied_at = clock() if callable(clock) else datetime.now(timezone.utc)
        marker = {
            "_id": MIGRATION_ID,
            "manifest_schema_version": 1,
            "manifest_key": MIGRATION_ID,
            "migration_id": MIGRATION_ID,
            "migration_type": MIGRATION_TYPE,
            "target_database": str(database.name),
            "state": "applied",
            "applied_at": applied_at,
            "checksum_sha256": MIGRATION_CHECKSUM,
            "registry_sha256": REGISTRY_SHA256,
            "mapping": _mapping_records(),
            "evidence_link_ids": sorted(EXPECTED_LINK_IDENTITIES),
            "links_matched": 6,
            "links_modified": 0,
            "concepts_restored": len(inserted),
        }
        database[MANIFEST_COLLECTION].insert_one(marker)
    except Exception as exc:
        if not _rollback(database, inserted, marker):
            raise LegacyCurveMigrationError("Migration failed and rollback was incomplete") from exc
        raise LegacyCurveMigrationError("Migration failed; rollback verified") from exc
    return {
        "already_applied": False,
        "concepts_restored": len(inserted),
        "links_matched": 6,
    }

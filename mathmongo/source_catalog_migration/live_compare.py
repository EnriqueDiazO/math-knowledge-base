"""Direct-PyMongo, read-only comparison between a ZIP plan and live MathV0."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mathmongo.config import redact_mongo_uri
from mathmongo.config import resolve_config
from mathmongo.config import sanitize_mongo_error
from mathmongo.source_catalog_migration.canonical import canonical_json
from mathmongo.source_catalog_migration.canonical import json_safe
from mathmongo.source_catalog_migration.canonical import sha256_digest
from mathmongo.source_catalog_migration.inventory import has_embedded_reference
from mathmongo.source_catalog_migration.locator import locator_field_names
from mathmongo.source_catalog_migration.models import CollectionState
from mathmongo.source_catalog_migration.models import LiveComparison
from mathmongo.source_catalog_migration.models import MigrationPlan
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport

LIVE_DATABASE_NAME = "MathV0"
RELEVANT_COLLECTIONS = (
    "concepts",
    "latex_documents",
    "relations",
    "knowledge_graph_maps",
    "media_assets",
    "latex_notes",
)
CATALOG_COLLECTIONS = ("sources", "references")
LIVE_MAX_DOCUMENTS_PER_COLLECTION = 10_000
LIVE_MAX_TOTAL_CANONICAL_BYTES = 256 * 1024 * 1024
LIVE_MAX_INDEXES_PER_COLLECTION = 1_024
LIVE_OPERATION_MAX_TIME_MS = 10_000
# An explicit exclusion projection retains every current/future field for the
# before/after integrity fingerprint. A fixed inclusion allow-list would miss
# concurrent changes to newly introduced legacy fields.
_PROJECTION_GUARD_FIELD = "__mathmongo_s1c1_projection_guard_never_persist__"
READ_PROJECTIONS: dict[str, dict[str, int]] = {
    name: {_PROJECTION_GUARD_FIELD: 0} for name in RELEVANT_COLLECTIONS
}


class LiveComparisonError(RuntimeError):
    """A safe operational failure while reading the explicit live database."""


class LiveReadNotAllowedError(LiveComparisonError):
    """The caller did not provide the explicit live-read authorization flag."""


@dataclass(frozen=True, slots=True)
class ComparisonMetrics:
    """Portable ZIP/live metrics; no document bodies are exposed in reports."""

    collection_counts: dict[str, int]
    concept_keys_sha256: str
    source_counts: dict[str, int]
    concepts_with_reference: int
    concepts_without_reference: int
    raw_reference_multiset_sha256: str
    bibliography_multiset_sha256: str
    raw_reference_bindings_sha256: str
    bibliography_bindings_sha256: str
    consumer_counts: dict[str, int]


def _reference_fingerprints(
    concepts: tuple[dict[str, Any], ...],
) -> tuple[str, str, str, str]:
    raw_fingerprints: Counter[str] = Counter()
    bibliography_fingerprints: Counter[str] = Counter()
    raw_bindings: list[dict[str, Any]] = []
    bibliography_bindings: list[dict[str, Any]] = []
    for concept in concepts:
        if "referencia" not in concept:
            raw_payload: dict[str, Any] = {"state": "absent"}
            bibliography_payload = raw_payload
        else:
            reference = concept.get("referencia")
            raw_payload = {"state": "present", "value": reference}
            if isinstance(reference, Mapping):
                excluded = locator_field_names(reference)
                bibliography = {
                    str(key): value for key, value in reference.items() if str(key) not in excluded
                }
                if "citekey" in concept:
                    bibliography["legacy_concept_citekey"] = concept.get("citekey")
                bibliography_payload = {"state": "present", "value": bibliography}
            else:
                bibliography_payload = raw_payload
        raw_fingerprints[sha256_digest(raw_payload)] += 1
        bibliography_fingerprints[sha256_digest(bibliography_payload)] += 1
        legacy_key = {
            "id": str(concept.get("id")),
            "source": str(concept.get("source")),
        }
        raw_bindings.append({"legacy_key": legacy_key, "reference": raw_payload})
        bibliography_bindings.append({"legacy_key": legacy_key, "reference": bibliography_payload})
    return (
        sha256_digest(dict(sorted(raw_fingerprints.items()))),
        sha256_digest(dict(sorted(bibliography_fingerprints.items()))),
        sha256_digest(sorted(raw_bindings, key=lambda item: canonical_json(item["legacy_key"]))),
        sha256_digest(
            sorted(
                bibliography_bindings,
                key=lambda item: canonical_json(item["legacy_key"]),
            )
        ),
    )


def comparison_metrics(
    collections: Mapping[str, tuple[dict[str, Any], ...]],
) -> ComparisonMetrics:
    """Build export-portable metrics from either ZIP JSON or live BSON documents."""
    concepts = tuple(collections.get("concepts", ()))
    concept_keys = sorted(
        (str(concept.get("id")), str(concept.get("source"))) for concept in concepts
    )
    source_counts = Counter(str(concept.get("source")) for concept in concepts)
    with_reference = sum(has_embedded_reference(concept) for concept in concepts)
    (
        raw_references,
        bibliographies,
        raw_reference_bindings,
        bibliography_bindings,
    ) = _reference_fingerprints(concepts)
    collection_counts = {
        name: len(tuple(documents)) for name, documents in sorted(collections.items())
    }
    consumer_counts = {
        name: collection_counts.get(name, 0) for name in RELEVANT_COLLECTIONS if name != "concepts"
    }
    return ComparisonMetrics(
        collection_counts=collection_counts,
        concept_keys_sha256=sha256_digest(concept_keys),
        source_counts=dict(sorted(source_counts.items())),
        concepts_with_reference=with_reference,
        concepts_without_reference=len(concepts) - with_reference,
        raw_reference_multiset_sha256=raw_references,
        bibliography_multiset_sha256=bibliographies,
        raw_reference_bindings_sha256=raw_reference_bindings,
        bibliography_bindings_sha256=bibliography_bindings,
        consumer_counts=consumer_counts,
    )


def _safe_indexes(
    database: Any, collection_names: tuple[str, ...]
) -> dict[str, tuple[dict[str, Any], ...]]:
    indexes: dict[str, tuple[dict[str, Any], ...]] = {}
    for collection_name in RELEVANT_COLLECTIONS:
        if collection_name not in collection_names:
            indexes[collection_name] = ()
            continue
        rows: list[dict[str, Any]] = []
        cursor = database[collection_name].list_indexes()
        try:
            for index, raw in enumerate(cursor, start=1):
                if index > LIVE_MAX_INDEXES_PER_COLLECTION:
                    raise LiveComparisonError(
                        f"Live collection {collection_name} exceeds the safe index limit"
                    )
                row = {
                    "name": raw.get("name"),
                    "key": list((raw.get("key") or {}).items()),
                    "unique": bool(raw.get("unique", False)),
                    "sparse": bool(raw.get("sparse", False)),
                }
                for option in (
                    "expireAfterSeconds",
                    "partialFilterExpression",
                    "collation",
                ):
                    if option in raw:
                        row[option] = json_safe(raw[option])
                rows.append(row)
        finally:
            close = getattr(cursor, "close", None)
            if callable(close):
                close()
        indexes[collection_name] = tuple(sorted(rows, key=lambda item: canonical_json(item)))
    return indexes


def _capture_state(database: Any) -> tuple[CollectionState, dict[str, tuple[dict[str, Any], ...]]]:
    collection_names = tuple(sorted(database.list_collection_names()))
    counts: dict[str, int] = {}
    fingerprints: dict[str, str] = {}
    documents: dict[str, tuple[dict[str, Any], ...]] = {}
    total_canonical_bytes = 0
    for collection_name in (*RELEVANT_COLLECTIONS, *CATALOG_COLLECTIONS):
        if collection_name not in collection_names:
            counts[collection_name] = 0
            if collection_name in RELEVANT_COLLECTIONS:
                documents[collection_name] = ()
                fingerprints[collection_name] = sha256_digest([])
            continue
        collection = database[collection_name]
        counts[collection_name] = int(
            collection.count_documents({}, maxTimeMS=LIVE_OPERATION_MAX_TIME_MS)
        )
        if collection_name in RELEVANT_COLLECTIONS:
            if counts[collection_name] > LIVE_MAX_DOCUMENTS_PER_COLLECTION:
                raise LiveComparisonError(
                    f"Live collection {collection_name} exceeds the safe document limit"
                )
            cursor = collection.find(
                {},
                projection=READ_PROJECTIONS[collection_name],
                limit=LIVE_MAX_DOCUMENTS_PER_COLLECTION + 1,
                max_time_ms=LIVE_OPERATION_MAX_TIME_MS,
            )
            rows_list: list[dict[str, Any]] = []
            canonical_rows: list[str] = []
            try:
                for document in cursor:
                    if len(rows_list) >= LIVE_MAX_DOCUMENTS_PER_COLLECTION:
                        raise LiveComparisonError(
                            f"Live collection {collection_name} changed beyond the safe "
                            "document limit"
                        )
                    row = dict(document)
                    serialized = canonical_json(row)
                    total_canonical_bytes += len(serialized.encode("utf-8"))
                    if total_canonical_bytes > LIVE_MAX_TOTAL_CANONICAL_BYTES:
                        raise LiveComparisonError(
                            "Live projected data exceeds the safe total byte limit"
                        )
                    rows_list.append(row)
                    canonical_rows.append(serialized)
            finally:
                close = getattr(cursor, "close", None)
                if callable(close):
                    close()
            rows = tuple(rows_list)
            documents[collection_name] = rows
            fingerprints[collection_name] = sha256_digest(sorted(canonical_rows))
    indexes = _safe_indexes(database, collection_names)
    return (
        CollectionState(
            collection_names=collection_names,
            counts=counts,
            fingerprints=fingerprints,
            indexes=indexes,
            indexes_fingerprint=sha256_digest(indexes),
        ),
        documents,
    )


def compare_live(
    export: LoadedLegacyExport,
    plan: MigrationPlan,
    *,
    database_name: str,
    allow_live_read: bool,
    mongo_uri: str | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> tuple[MigrationPlan, LiveComparison]:
    """Read explicit live MathV0 twice, compare, and prove no S1C1 writes."""
    if not allow_live_read:
        raise LiveReadNotAllowedError("compare-live requires --allow-live-read")
    if database_name != LIVE_DATABASE_NAME:
        raise LiveComparisonError("compare-live permits only the explicit database MathV0")
    uri = mongo_uri or resolve_config().mongo_uri
    redacted_uri = redact_mongo_uri(uri)
    if client_factory is None:
        from pymongo import MongoClient

        client_factory = MongoClient
    client = None
    try:
        client = client_factory(
            uri,
            serverSelectionTimeoutMS=2_500,
            connectTimeoutMS=2_500,
            socketTimeoutMS=10_000,
            retryWrites=False,
            appname="MathMongo-S1C1-read-only",
        )
        client.admin.command("ping")
        database_names = tuple(client.list_database_names())
        if database_name not in database_names:
            raise LiveComparisonError(f"Live database {database_name} is not available")
        database = client.get_database(database_name)
        before, before_documents = _capture_state(database)
        zip_metrics = comparison_metrics(export.collections)
        live_metrics = comparison_metrics(before_documents)
        after, _after_documents = _capture_state(database)
    except LiveComparisonError:
        raise
    except Exception as exc:
        safe = sanitize_mongo_error(exc, uri)
        raise LiveComparisonError(f"Live read failed at {redacted_uri}: {safe}") from exc
    finally:
        if client is not None:
            client.close()

    details: list[str] = []
    live_drift = before != after
    if live_drift:
        details.append("Live database state changed between the before and after snapshots.")
    concept_keys_match = zip_metrics.concept_keys_sha256 == live_metrics.concept_keys_sha256
    if not concept_keys_match:
        details.append("The live (id, source) concept key set differs from the ZIP.")
    source_counts_match = zip_metrics.source_counts == live_metrics.source_counts
    if not source_counts_match:
        details.append("Exact Source counts differ between live MathV0 and the ZIP.")
    reference_partition_matches = (
        zip_metrics.concepts_with_reference == live_metrics.concepts_with_reference
        and zip_metrics.concepts_without_reference == live_metrics.concepts_without_reference
    )
    if not reference_partition_matches:
        details.append("Concepts with/without embedded Reference differ from the ZIP.")
    reference_fingerprints_match = (
        zip_metrics.raw_reference_multiset_sha256 == live_metrics.raw_reference_multiset_sha256
        and zip_metrics.bibliography_multiset_sha256 == live_metrics.bibliography_multiset_sha256
        and zip_metrics.raw_reference_bindings_sha256 == live_metrics.raw_reference_bindings_sha256
        and zip_metrics.bibliography_bindings_sha256 == live_metrics.bibliography_bindings_sha256
    )
    if not reference_fingerprints_match:
        details.append("Embedded Reference fingerprints differ from the ZIP.")
    consumer_counts_match = zip_metrics.consumer_counts == live_metrics.consumer_counts
    if not consumer_counts_match:
        details.append("Coupled legacy collection counts differ from the ZIP.")
    sources_absent = (
        "sources" not in before.collection_names and "sources" not in after.collection_names
    )
    references_absent = (
        "references" not in before.collection_names and "references" not in after.collection_names
    )
    if not sources_absent:
        details.append("A live sources collection already exists or appeared during comparison.")
    if not references_absent:
        details.append("A live references collection already exists or appeared during comparison.")
    snapshot_drift = not all(
        (
            concept_keys_match,
            source_counts_match,
            reference_partition_matches,
            reference_fingerprints_match,
            consumer_counts_match,
            sources_absent,
            references_absent,
        )
    )
    comparison = LiveComparison(
        database_name=database_name,
        uri_redacted=redacted_uri,
        before=before,
        after=after,
        read_operations=(
            "ping",
            "list_database_names",
            "list_collection_names",
            "count_documents",
            "find_with_projection",
            "list_indexes",
        ),
        writes_attempted=0,
        live_database_drift=live_drift,
        snapshot_drift=snapshot_drift,
        sources_collection_absent=sources_absent,
        references_collection_absent=references_absent,
        concept_count_expected=plan.summary.concept_count,
        concept_count_live=live_metrics.collection_counts.get("concepts", 0),
        concept_keys_match=concept_keys_match,
        source_counts_match=source_counts_match,
        reference_partition_matches=reference_partition_matches,
        reference_fingerprints_match=reference_fingerprints_match,
        consumer_counts_match=consumer_counts_match,
        drift_details=tuple(details),
    )
    return plan.model_copy(update={"live_comparison": comparison}), comparison


__all__ = [
    "CATALOG_COLLECTIONS",
    "ComparisonMetrics",
    "LIVE_DATABASE_NAME",
    "LIVE_MAX_DOCUMENTS_PER_COLLECTION",
    "LIVE_MAX_INDEXES_PER_COLLECTION",
    "LIVE_MAX_TOTAL_CANONICAL_BYTES",
    "LIVE_OPERATION_MAX_TIME_MS",
    "LiveComparisonError",
    "LiveReadNotAllowedError",
    "READ_PROJECTIONS",
    "RELEVANT_COLLECTIONS",
    "compare_live",
    "comparison_metrics",
]

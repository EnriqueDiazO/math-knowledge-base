"""Pure inventory of authoritative legacy export collections."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mathmongo.source_catalog_migration.models import ConsumerInventory
from mathmongo.source_catalog_migration.models import CoupledCollections
from mathmongo.source_catalog_migration.models import LegacyKey
from mathmongo.source_catalog_migration.zip_reader import LoadedLegacyExport

RELEVANT_CONSUMER_COLLECTIONS = (
    "latex_documents",
    "relations",
    "knowledge_graph_maps",
    "media_assets",
    "latex_notes",
)


class InventoryError(ValueError):
    """The validated archive contains an invalid planning inventory."""


@dataclass(frozen=True, slots=True)
class LegacyInventory:
    """In-memory facts used by source/reference planners without further I/O."""

    concepts: tuple[dict[str, Any], ...]
    legacy_keys: tuple[LegacyKey, ...]
    source_counts: dict[str, int]
    source_reference_counts: dict[str, tuple[int, int]]
    concepts_with_reference: int
    concepts_without_reference: int
    malformed_reference_count: int
    collection_counts: dict[str, int]
    coupled_collections: CoupledCollections
    warnings: tuple[str, ...]


def has_embedded_reference(concept: Mapping[str, Any]) -> bool:
    """Return whether a legacy reference value carries any preserved content."""
    if "referencia" not in concept:
        return False
    value = concept.get("referencia")
    if value is None:
        return False
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _legacy_key(document: Mapping[str, Any], *, collection: str) -> LegacyKey:
    concept_id = document.get("id")
    source = document.get("source")
    if not isinstance(concept_id, str) or not concept_id:
        raise InventoryError(f"{collection} document has no usable string id")
    if not isinstance(source, str) or not source:
        raise InventoryError(f"{collection} document has no usable exact source string")
    return LegacyKey(id=concept_id, source=source)


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from _walk(nested)


def _mapping_legacy_key(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    concept_id = value.get("conceptId")
    if not isinstance(concept_id, str):
        concept_id = value.get("id")
    source = value.get("source")
    if isinstance(concept_id, str) and isinstance(source, str):
        return concept_id, source
    return None


def _consumer_inventory(
    export: LoadedLegacyExport,
    concept_keys: set[tuple[str, str]],
) -> CoupledCollections:
    tokens = {f"{concept_id}@{source}" for concept_id, source in concept_keys}
    consumers: list[ConsumerInventory] = []

    latex_documents = export.collections.get("latex_documents", ())
    latex_pairs: list[tuple[str, str]] = []
    invalid_latex_keys = 0
    for document in latex_documents:
        try:
            key = _legacy_key(document, collection="latex_documents")
        except InventoryError:
            invalid_latex_keys += 1
            continue
        latex_pairs.append((key.id, key.source))
    latex_pair_set = set(latex_pairs)
    counterparts = len(concept_keys & latex_pair_set)
    orphans = len(latex_pair_set - concept_keys)
    latex_warnings: list[str] = []
    if len(latex_pairs) != len(latex_pair_set):
        latex_warnings.append("Duplicate (id, source) keys exist in latex_documents.")
    if invalid_latex_keys:
        latex_warnings.append(f"{invalid_latex_keys} latex_documents have unusable keys.")
    if orphans:
        latex_warnings.append(
            f"{orphans} latex_documents have no concept counterpart and remain untouched."
        )
    consumers.append(
        ConsumerInventory(
            collection="latex_documents",
            document_count=len(latex_documents),
            legacy_key_usages=counterparts,
            warnings=tuple(latex_warnings),
        )
    )

    relations = export.collections.get("relations", ())
    relation_endpoints = [
        endpoint
        for relation in relations
        for field in ("desde", "hasta")
        if isinstance((endpoint := relation.get(field)), str)
    ]
    valid_relation_endpoints = sum(endpoint in tokens for endpoint in relation_endpoints)
    relation_warnings = ()
    if valid_relation_endpoints != len(relation_endpoints):
        relation_warnings = (
            f"{len(relation_endpoints) - valid_relation_endpoints} relation endpoints do not "
            "resolve to snapshot concepts.",
        )
    consumers.append(
        ConsumerInventory(
            collection="relations",
            document_count=len(relations),
            id_at_source_usages=valid_relation_endpoints,
            warnings=relation_warnings,
        )
    )

    maps = export.collections.get("knowledge_graph_maps", ())
    map_token_usages = 0
    map_pair_usages = 0
    for document in maps:
        for value in _walk(document):
            if isinstance(value, str) and value in tokens:
                map_token_usages += 1
            pair = _mapping_legacy_key(value)
            if pair in concept_keys:
                map_pair_usages += 1
    consumers.append(
        ConsumerInventory(
            collection="knowledge_graph_maps",
            document_count=len(maps),
            legacy_key_usages=map_pair_usages,
            id_at_source_usages=map_token_usages,
        )
    )

    media_assets = export.collections.get("media_assets", ())
    media_tokens = [
        value
        for document in media_assets
        for value in document.get("concept_ids", [])
        if isinstance(value, str)
    ]
    valid_media_tokens = sum(value in tokens for value in media_tokens)
    media_warnings = ()
    if valid_media_tokens != len(media_tokens):
        media_warnings = (
            f"{len(media_tokens) - valid_media_tokens} media concept links do not resolve.",
        )
    consumers.append(
        ConsumerInventory(
            collection="media_assets",
            document_count=len(media_assets),
            id_at_source_usages=valid_media_tokens,
            warnings=media_warnings,
        )
    )

    latex_notes = export.collections.get("latex_notes", ())
    note_token_usages = sum(
        isinstance(value, str) and value in tokens
        for document in latex_notes
        for value in _walk(document)
    )
    note_pair_usages = sum(
        _mapping_legacy_key(value) in concept_keys
        for document in latex_notes
        for value in _walk(document)
    )
    consumers.append(
        ConsumerInventory(
            collection="latex_notes",
            document_count=len(latex_notes),
            legacy_key_usages=note_pair_usages,
            id_at_source_usages=note_token_usages,
        )
    )

    return CoupledCollections(
        consumers=tuple(consumers),
        concept_counterparts_in_latex_documents=counterparts,
        orphan_latex_documents=orphans,
        relations=len(relations),
        knowledge_graph_maps=len(maps),
        media_assets=len(media_assets),
        latex_notes=len(latex_notes),
    )


def build_inventory(export: LoadedLegacyExport) -> LegacyInventory:
    """Validate unique concept identities and inventory all coupled consumers."""
    if "concepts" not in export.collections:
        raise InventoryError("The export does not contain collections/concepts.json")
    concepts = export.collections["concepts"]
    legacy_keys: list[LegacyKey] = []
    seen: set[tuple[str, str]] = set()
    source_counts: Counter[str] = Counter()
    with_reference_by_source: Counter[str] = Counter()
    without_reference_by_source: Counter[str] = Counter()
    malformed_reference_count = 0
    warnings: list[str] = []

    for concept in concepts:
        key = _legacy_key(concept, collection="concepts")
        raw_key = (key.id, key.source)
        if raw_key in seen:
            raise InventoryError(f"Duplicate legacy concept key: {key.id!r}, {key.source!r}")
        seen.add(raw_key)
        legacy_keys.append(key)
        source_counts[key.source] += 1
        if has_embedded_reference(concept):
            with_reference_by_source[key.source] += 1
            reference = concept.get("referencia")
            if not isinstance(reference, (Mapping, str)):
                malformed_reference_count += 1
        else:
            without_reference_by_source[key.source] += 1
            if "referencia" in concept and concept.get("referencia") is None:
                warnings.append(f"Null reference preserved for {key.id}@{key.source}.")

    source_reference_counts = {
        source: (
            with_reference_by_source[source],
            without_reference_by_source[source],
        )
        for source in sorted(source_counts)
    }
    coupled = _consumer_inventory(export, seen)
    return LegacyInventory(
        concepts=concepts,
        legacy_keys=tuple(legacy_keys),
        source_counts=dict(sorted(source_counts.items())),
        source_reference_counts=source_reference_counts,
        concepts_with_reference=sum(with_reference_by_source.values()),
        concepts_without_reference=sum(without_reference_by_source.values()),
        malformed_reference_count=malformed_reference_count,
        collection_counts={
            name: len(documents) for name, documents in sorted(export.collections.items())
        },
        coupled_collections=coupled,
        warnings=tuple(warnings),
    )


__all__ = [
    "InventoryError",
    "LegacyInventory",
    "RELEVANT_CONSUMER_COLLECTIONS",
    "build_inventory",
    "has_embedded_reference",
]

"""Exact legacy Concept aliases shared by export, import, and update."""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any
from typing import NamedTuple

Identity = tuple[str, str]
AliasRegistry = Mapping[Identity, tuple[Identity, ...]]
SOURCE = "BottcherKarlovich1997"
REGISTRY_SHA256 = "e8044feec0ea3aa497ee54803e06da0feb77dea22e322911673127ae87104c0c"
LEGACY_CONCEPT_ALIAS_REGISTRY: AliasRegistry = {
    ("id_Curves_001", SOURCE): (("id_Curves_001", SOURCE),),
    ("id_Curves_002", SOURCE): (("id_Curves_002", SOURCE),),
}


class LegacyConceptNormalization(NamedTuple):
    """One exact in-memory identity rewrite."""
    collection: str
    record_id: str
    legacy_identity: Identity
    canonical_identity: Identity

def normalize_legacy_concept_documents(
    collection: str,
    documents: Iterable[Any],
    *,
    registry: AliasRegistry | None = None,
) -> tuple[tuple[Any, ...], tuple[LegacyConceptNormalization, ...]]:
    """Rewrite registered pairs only; schema/portability rejects unknown pairs."""
    selected = registry or LEGACY_CONCEPT_ALIAS_REGISTRY
    normalized, changes = [], []
    for ordinal, raw in enumerate(documents, 1):
        if not isinstance(raw, Mapping):
            normalized.append(raw)
            continue
        document = dict(raw)
        fields = {
            "concepts": (("concept", "id", "source"),),
            "concept_evidence_links": (
                ("evidence", "concept_legacy_id", "concept_legacy_source"),
            ),
        }
        locations = [
            (location, document.get(id_field), document.get(source_field))
            for location, id_field, source_field in fields.get(collection, ())
        ]
        if collection == "relations":
            locations = [
                (field, *str(document[field]).rsplit("@", 1))
                for field in ("desde", "hasta")
                if isinstance(document.get(field), str) and "@" in document[field]
            ]
        for location, concept_id, source in locations:
            if not isinstance(concept_id, str) or not isinstance(source, str):
                continue
            legacy = (concept_id, source)
            targets = selected.get(legacy)
            if targets is None:
                continue
            if len(targets) != 1:
                raise ValueError(f"Legacy Concept alias is ambiguous: {legacy!r}")
            canonical = targets[0]
            if canonical == legacy:
                continue
            record_id = str(
                document.get("evidence_link_id") or document.get("_id") or ordinal
            )
            if location == "concept":
                document["id"], document["source"] = canonical
            elif location == "evidence":
                document["concept_legacy_id"], document["concept_legacy_source"] = canonical
            else:
                document[location] = "@".join(canonical)
            changes.append(LegacyConceptNormalization(collection, record_id, legacy, canonical))
        normalized.append(document)
    return tuple(normalized), tuple(changes)

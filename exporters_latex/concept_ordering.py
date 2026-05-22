from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any


TYPE_ORDER = {
    "definicion": 0,
    "proposicion": 1,
    "teorema": 2,
    "lema": 3,
    "corolario": 4,
    "ejemplo": 5,
    "nota": 6,
}

DEPENDENCY_RELATIONS = {"requiere_concepto", "deriva_de"}
FORWARD_RELATIONS = {"implica"}
UNDIRECTED_OR_WEAK_RELATIONS = {
    "equivalente",
    "inspirado_en",
    "contrasta_con",
    "contradice",
    "contra_ejemplo",
}


def concept_key(concept: dict[str, Any]) -> str:
    return f"{concept.get('id')}@{concept.get('source')}"


def order_by_type(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        concepts,
        key=lambda c: (
            TYPE_ORDER.get(c.get("tipo"), 99),
            (c.get("titulo") or c.get("id") or "").lower(),
        ),
    )


def order_by_title(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(concepts, key=lambda c: (c.get("titulo") or c.get("id") or "").lower())


def _date_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.max


def order_by_date(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        concepts,
        key=lambda c: (
            _date_value(c.get("fecha_creacion") or c.get("ultima_actualizacion")),
            (c.get("titulo") or c.get("id") or "").lower(),
        ),
    )


def order_by_selection(concepts: list[dict[str, Any]], selected_keys: list[str]) -> list[dict[str, Any]]:
    by_key = {concept_key(c): c for c in concepts}
    return [by_key[k] for k in selected_keys if k in by_key]


def _relation_endpoints(relation: dict[str, Any]) -> tuple[str | None, str | None]:
    if relation.get("desde") and relation.get("hasta"):
        return relation.get("desde"), relation.get("hasta")
    if all(
        relation.get(k)
        for k in ("desde_id", "desde_source", "hasta_id", "hasta_source")
    ):
        return (
            f"{relation['desde_id']}@{relation['desde_source']}",
            f"{relation['hasta_id']}@{relation['hasta_source']}",
        )
    return None, None


def order_by_graph(
    concepts: list[dict[str, Any]],
    relations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Topologically sort selected concepts when directed relations are usable."""
    warnings: list[str] = []
    selected_keys = [concept_key(c) for c in concepts]
    selected = set(selected_keys)
    by_key = {concept_key(c): c for c in concepts}

    adjacency: dict[str, set[str]] = defaultdict(set)
    indegree = {key: 0 for key in selected_keys}
    used_edges = 0

    for relation in relations:
        rel_type = relation.get("tipo")
        desde, hasta = _relation_endpoints(relation)
        if not desde or not hasta or desde not in selected or hasta not in selected:
            continue

        edge: tuple[str, str] | None = None
        if rel_type in DEPENDENCY_RELATIONS:
            edge = (hasta, desde)
        elif rel_type in FORWARD_RELATIONS:
            edge = (desde, hasta)
        elif rel_type in UNDIRECTED_OR_WEAK_RELATIONS:
            continue

        if edge is None:
            continue
        a, b = edge
        if b not in adjacency[a]:
            adjacency[a].add(b)
            indegree[b] += 1
            used_edges += 1

    if used_edges == 0:
        warnings.append("No directed graph relations were usable for ordering. Kept current order.")
        return concepts, warnings, {"used_edges": 0, "disconnected": selected_keys}

    queue = deque([key for key in selected_keys if indegree[key] == 0])
    ordered_keys: list[str] = []
    while queue:
        key = queue.popleft()
        ordered_keys.append(key)
        for neighbor in adjacency.get(key, set()):
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered_keys) != len(selected_keys):
        cycle_keys = [key for key in selected_keys if indegree[key] > 0]
        warnings.append(
            "Cycle detected in graph relations. Kept current order as fallback."
        )
        return concepts, warnings, {"used_edges": used_edges, "cycles": cycle_keys}

    connected = set(adjacency.keys())
    for values in adjacency.values():
        connected.update(values)
    disconnected = [key for key in selected_keys if key not in connected]
    if disconnected:
        warnings.append(
            f"{len(disconnected)} selected concepts have no usable graph relation."
        )

    return [by_key[key] for key in ordered_keys], warnings, {
        "used_edges": used_edges,
        "disconnected": disconnected,
    }

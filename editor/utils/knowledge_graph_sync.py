from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from visualizations.grafoconocimiento import GrafoConocimiento


DEFAULT_SYNC_SETTINGS = {
    "suppress_new_nodes_prompt": False,
    "ignored_concept_ids": [],
    "removed_node_ids": [],
    "manually_removed_node_ids": [],
    "last_sync_check_at": None,
    "auto_include_source_new_nodes": False,
}


def utc_timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"


def default_sync_settings(settings: dict | None = None) -> dict:
    normalized = deepcopy(DEFAULT_SYNC_SETTINGS)
    if not isinstance(settings, dict):
        return normalized

    normalized["suppress_new_nodes_prompt"] = bool(settings.get("suppress_new_nodes_prompt", False))
    normalized["auto_include_source_new_nodes"] = bool(settings.get("auto_include_source_new_nodes", False))
    ignored = settings.get("ignored_concept_ids", [])
    if isinstance(ignored, list):
        normalized["ignored_concept_ids"] = [str(item) for item in ignored if item is not None]
    removed = settings.get("removed_node_ids", [])
    if isinstance(removed, list):
        normalized["removed_node_ids"] = [str(item) for item in removed if item is not None]
    manually_removed = settings.get("manually_removed_node_ids", [])
    if isinstance(manually_removed, list):
        normalized["manually_removed_node_ids"] = [str(item) for item in manually_removed if item is not None]
    if settings.get("last_sync_check_at"):
        normalized["last_sync_check_at"] = settings.get("last_sync_check_at")
    return normalized


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def split_concept_key(value: Any) -> tuple[str, str]:
    text = _clean_text(value)
    if "@" not in text:
        return text, ""
    concept_id, source = text.rsplit("@", 1)
    return concept_id.strip(), source.strip()


def concept_key_from_parts(concept_id: Any, source: Any = None) -> str:
    concept_text = _clean_text(concept_id)
    source_text = _clean_text(source)
    if not concept_text:
        return ""
    if "@" in concept_text:
        return concept_text
    if source_text:
        return f"{concept_text}@{source_text}"
    return concept_text


def concept_parts(concept: Any, source: Any = None) -> tuple[str, str]:
    if isinstance(concept, dict):
        concept_id = (
            concept.get("id")
            or concept.get("concept_id")
            or concept.get("conceptId")
            or concept.get("_id")
        )
        source_value = concept.get("source") or source
    else:
        concept_id = concept
        source_value = source

    concept_text = _clean_text(concept_id)
    source_text = _clean_text(source_value)
    if "@" in concept_text:
        base_id, embedded_source = split_concept_key(concept_text)
        return base_id, source_text or embedded_source
    return concept_text, source_text


def concept_key(concept: Any, source: Any = None) -> str:
    concept_id, source_text = concept_parts(concept, source=source)
    return concept_key_from_parts(concept_id, source_text)


def node_concept_parts(node: dict) -> tuple[str, str]:
    if not isinstance(node, dict):
        return "", ""

    node_info = node.get("nodeInfo", {}) if isinstance(node.get("nodeInfo"), dict) else {}
    node_id = _clean_text(node.get("id"))
    source = _clean_text(node.get("source") or node_info.get("source"))
    concept_id = _clean_text(
        node.get("concept_id")
        or node.get("conceptId")
        or node_info.get("concept_id")
        or node_info.get("conceptId")
    )

    if not concept_id and node_id:
        concept_id, embedded_source = split_concept_key(node_id)
        source = source or embedded_source
    elif "@" in concept_id:
        concept_id, embedded_source = split_concept_key(concept_id)
        source = source or embedded_source
    elif "@" in node_id and not source:
        _, source = split_concept_key(node_id)

    return concept_id, source


def node_concept_key(node: dict) -> str:
    concept_id, source = node_concept_parts(node)
    if concept_id:
        return concept_key_from_parts(concept_id, source)
    return _clean_text(node.get("id") if isinstance(node, dict) else "")


def graph_node_items(graph_state: dict | None) -> list[dict]:
    if not isinstance(graph_state, dict):
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for collection_name in ("fullNodes", "nodes"):
        collection = graph_state.get(collection_name)
        if not isinstance(collection, list):
            continue
        for node in collection:
            if not isinstance(node, dict):
                continue
            key = _clean_text(node.get("id")) or node_concept_key(node)
            if key in seen:
                continue
            seen.add(key)
            items.append(node)
    return items


def graph_edge_items(graph_state: dict | None) -> list[dict]:
    if not isinstance(graph_state, dict):
        return []
    items: list[dict] = []
    seen: set[str] = set()
    for collection_name in ("fullEdges", "edges"):
        collection = graph_state.get(collection_name)
        if not isinstance(collection, list):
            continue
        for edge in collection:
            if not isinstance(edge, dict):
                continue
            key = edge_identity(edge)
            if key in seen:
                continue
            seen.add(key)
            items.append(edge)
    return items


def graph_contains_concept(graph_state: dict | None, concept: dict) -> bool:
    candidate_id, candidate_source = concept_parts(concept)
    candidate_full_key = concept_key_from_parts(candidate_id, candidate_source)
    for node in graph_node_items(graph_state):
        node_id, node_source = node_concept_parts(node)
        node_full_key = concept_key_from_parts(node_id, node_source)
        if candidate_full_key and node_full_key == candidate_full_key:
            return True
        if candidate_id and node_id == candidate_id:
            if not candidate_source or not node_source or candidate_source == node_source:
                return True
    return False


def graph_concept_keys(graph_state: dict | None) -> set[str]:
    keys = set()
    for node in graph_node_items(graph_state):
        key = node_concept_key(node)
        if key:
            keys.add(key)
    return keys


def primary_sources(map_doc: dict | None) -> list[str]:
    if not isinstance(map_doc, dict):
        return []
    for field in ("primary_map_source", "primary_source"):
        value = map_doc.get(field)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if isinstance(value, list):
            sources = [source.strip() for source in value if isinstance(source, str) and source.strip()]
            if sources:
                return sources

    filters = map_doc.get("filters", {}) if isinstance(map_doc.get("filters"), dict) else {}
    for field in ("primary_map_source", "primary_source"):
        value = filters.get(field)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    sources = [
        source.strip()
        for source in filters.get("sources", []) or []
        if isinstance(source, str) and source.strip()
    ]
    if sources:
        return sources

    source = map_doc.get("source")
    if isinstance(source, str) and source.strip() and source != "interactive_knowledge_graph":
        return [source.strip()]
    return []


def merge_ordered_values(*value_groups: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for values in value_groups:
        if isinstance(values, str):
            iterable = [values]
        elif isinstance(values, (list, tuple, set)):
            iterable = values
        else:
            continue
        for value in iterable:
            text = _clean_text(value)
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def concept_label(concept: dict) -> str:
    if not isinstance(concept, dict):
        return ""
    return _clean_text(
        concept.get("titulo")
        or concept.get("title")
        or concept.get("name")
        or concept.get("label")
        or concept.get("id")
        or concept.get("concept_id")
    )


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return _clean_text(value)


def concept_table_rows(concepts: list[dict]) -> list[dict]:
    rows = []
    for concept in concepts:
        rows.append(
            {
                "Agregar": False,
                "Título": concept_label(concept),
                "Tipo": _clean_text(concept.get("tipo")),
                "Source": _clean_text(concept.get("source")),
                "ID interno": concept_key(concept),
                "Actualizado": _date_text(concept.get("updated_at") or concept.get("created_at")),
            }
        )
    return rows


def concepts_by_keys(concepts: list[dict], selected_keys: set[str]) -> list[dict]:
    return [concept for concept in concepts if concept_key(concept) in selected_keys]


def detect_missing_source_concepts(
    mongo: Any,
    map_doc: dict,
    graph_state: dict | None = None,
    *,
    include_removed: bool = False,
) -> list[dict]:
    sources = primary_sources(map_doc)
    if not sources:
        return []

    concept_query = {"source": {"$in": sources}}
    concepts = list(mongo.concepts.find(concept_query))
    removed_ids: set[str] = set()
    if not include_removed and isinstance(map_doc, dict):
        sync_settings = default_sync_settings(map_doc.get("sync_settings"))
        removed_ids.update(sync_settings.get("removed_node_ids", []))
        removed_ids.update(sync_settings.get("manually_removed_node_ids", []))
    missing = [
        concept
        for concept in concepts
        if not graph_contains_concept(graph_state, concept) and concept_key(concept) not in removed_ids
    ]
    return sorted(
        missing,
        key=lambda concept: (
            _clean_text(concept.get("source")).lower(),
            _clean_text(concept.get("tipo")).lower(),
            concept_label(concept).lower(),
            concept_key(concept).lower(),
        ),
    )


def find_available_concepts(
    mongo: Any,
    source: str,
    graph_state: dict | None,
    concept_types: list[str] | None = None,
    search_text: str = "",
    limit: int = 300,
) -> list[dict]:
    clean_source = _clean_text(source)
    if not clean_source:
        return []

    query: dict[str, Any] = {"source": clean_source}
    clean_types = [item for item in concept_types or [] if item]
    if clean_types:
        query["tipo"] = {"$in": clean_types}

    concepts = list(mongo.concepts.find(query).limit(limit))
    needle = search_text.strip().lower()
    if needle:
        concepts = [
            concept
            for concept in concepts
            if needle in " ".join(
                [
                    concept_label(concept),
                    _clean_text(concept.get("tipo")),
                    _clean_text(concept.get("id")),
                    _clean_text(concept.get("concept_id")),
                    _clean_text(concept.get("descripcion")),
                    _clean_text(concept.get("contenido")),
                ]
            ).lower()
        ]

    available = [concept for concept in concepts if not graph_contains_concept(graph_state, concept)]
    return sorted(
        available,
        key=lambda concept: (
            _clean_text(concept.get("tipo")).lower(),
            concept_label(concept).lower(),
            concept_key(concept).lower(),
        ),
    )


def _numeric(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def new_node_position(graph_state: dict | None, index: int) -> dict:
    nodes = graph_node_items(graph_state)
    xs = [_numeric(node.get("x")) for node in nodes]
    ys = [_numeric(node.get("y")) for node in nodes]
    xs = [value for value in xs if value is not None]
    ys = [value for value in ys if value is not None]
    max_x = max(xs) if xs else 0
    min_y = min(ys) if ys else 0
    col = index % 3
    row = index // 3
    return {
        "x": max_x + 220 + col * 180,
        "y": min_y + row * 100,
    }


def _concept_node_type(concept: dict) -> str:
    if not isinstance(concept, dict):
        return "otro"
    return _clean_text(
        concept.get("tipo")
        or concept.get("type")
        or concept.get("mmType")
        or concept.get("conceptType")
        or concept.get("node_type")
    ) or "otro"


def concept_graph_node_errors(concept: dict) -> list[str]:
    concept_id, source = concept_parts(concept)
    errors: list[str] = []
    if not concept_label(concept):
        errors.append("label/title")
    if not _clean_text(source):
        errors.append("source")
    if not _clean_text(concept_id):
        errors.append("concept_id")
    return errors


def concept_graph_node_warnings(concept: dict) -> list[str]:
    if _concept_node_type(concept) == "otro":
        return ["type"]
    return []


def _fallback_node(concept: dict) -> dict:
    key = concept_key(concept)
    label = concept_label(concept) or key
    concept_id, source = concept_parts(concept)
    concept_type = _concept_node_type(concept)
    return {
        "id": key,
        "label": label,
        "title": label,
        "shape": "box",
        "color": "#E0E0E0",
        "font": {"size": 18, "multi": True},
        "fixed": False,
        "type": concept_type,
        "mmType": concept_type,
        "conceptType": concept_type,
        "typeBadge": "otro" if concept_type == "otro" else concept_type[:4],
        "shortType": "otro" if concept_type == "otro" else concept_type[:4],
        "displayType": concept_type,
        "rawLabel": label,
        "source": source,
        "concept_id": concept_id,
        "conceptId": concept_id,
        "categories": concept.get("categorias", []) if isinstance(concept.get("categorias"), list) else [],
        "description": concept.get("descripcion") or concept.get("comentario") or concept.get("aclaracion"),
        "content": concept.get("contenido_latex") or concept.get("contenido"),
        "referenceText": _clean_text(concept.get("referencia")),
    }


def _graph_node_required_issues(node: dict) -> list[str]:
    if not isinstance(node, dict):
        return ["node"]
    node_info = node.get("nodeInfo") if isinstance(node.get("nodeInfo"), dict) else {}
    label = _clean_text(
        node.get("rawLabel")
        or node_info.get("label")
        or node.get("label")
        or node.get("title")
    )
    node_type = _clean_text(
        node.get("type")
        or node.get("mmType")
        or node.get("conceptType")
        or node_info.get("type")
    )
    concept_id, source = node_concept_parts(node)
    issues: list[str] = []
    if not _clean_text(node.get("id")):
        issues.append("id")
    if not label and node.get("shape") != "image":
        issues.append("label/title")
    if not node_type:
        issues.append("type")
    if not source:
        issues.append("source")
    if not concept_id:
        issues.append("concept_id")
    return issues


def build_node_from_concept(
    concept: dict,
    position: dict,
    added_at: str,
    sync_origin: str,
    added_from_sync: bool = True,
) -> dict:
    errors = concept_graph_node_errors(concept)
    if errors:
        concept_name = concept_key(concept) or concept_label(concept) or "<sin id>"
        raise ValueError(
            "No se pudo agregar el concepto porque faltan metadatos mínimos "
            f"({concept_name}): {', '.join(errors)}"
        )

    node = None
    try:
        grafo = GrafoConocimiento([concept], [])
        grafo.construir_grafo()
        graph_state = grafo.to_graph_state()
        if graph_state.get("nodes"):
            node = deepcopy(graph_state["nodes"][0])
    except Exception:
        node = None

    if not isinstance(node, dict):
        node = _fallback_node(concept)

    concept_id, source = concept_parts(concept)
    label = concept_label(concept) or concept_key_from_parts(concept_id, source)
    concept_type = _concept_node_type(concept)
    node_info = node.get("nodeInfo") if isinstance(node.get("nodeInfo"), dict) else {}
    node_type = _clean_text(
        node.get("type")
        or node.get("mmType")
        or node.get("conceptType")
        or node_info.get("type")
    ) or concept_type
    type_badge = _clean_text(node.get("typeBadge") or node.get("shortType") or node_info.get("shortType"))
    if not type_badge:
        type_badge = "otro" if node_type == "otro" else node_type[:4]

    node["id"] = concept_key_from_parts(concept_id, source)
    node["x"] = position["x"]
    node["y"] = position["y"]
    node.setdefault("fixed", False)
    node["title"] = node.get("title") or label
    if node.get("shape") != "image" and not node.get("label"):
        node["label"] = label
    node["rawLabel"] = node.get("rawLabel") or node_info.get("label") or label
    node["type"] = node_type
    node["mmType"] = node.get("mmType") or node_type
    node["conceptType"] = node.get("conceptType") or node_type
    node["typeBadge"] = type_badge
    node["shortType"] = node.get("shortType") or type_badge
    node["displayType"] = node.get("displayType") or node_info.get("displayType") or node_type
    concept_categories = concept.get("categorias") if isinstance(concept.get("categorias"), list) else []
    node["categories"] = node.get("categories") or concept_categories
    node["description"] = (
        node.get("description")
        or concept.get("descripcion")
        or concept.get("comentario")
        or concept.get("aclaracion")
    )
    node["content"] = node.get("content") or concept.get("contenido_latex") or concept.get("contenido")
    node["referenceText"] = node.get("referenceText") or _clean_text(concept.get("referencia"))
    node["color"] = node.get("color") or "#E0E0E0"
    if node.get("shape") in {"circle", "dot"} and node_type != "placeholder":
        node["shape"] = "box"
    node["shape"] = node.get("shape") or "box"
    node["font"] = node.get("font") or {"size": 18, "multi": True}
    if added_from_sync:
        node["added_from_sync"] = True
        node["added_at"] = added_at
        node["sync_origin"] = sync_origin
    node["source"] = source
    node["concept_id"] = concept_id
    node["conceptId"] = concept_id

    node["nodeInfo"] = node_info
    node_info.update(
        {
            "id": node["id"],
            "source": source,
            "conceptId": concept_id,
            "concept_id": concept_id,
            "label": node["rawLabel"],
            "type": node_type,
            "shortType": node["shortType"],
            "displayType": node["displayType"],
            "categories": node.get("categories", []),
            "description": node.get("description"),
            "content": node.get("content"),
            "reference": node.get("referenceText"),
        }
    )
    if added_from_sync:
        node["borderWidth"] = max(int(node.get("borderWidth", 1) or 1), 3)
        node["shadow"] = {
            "enabled": True,
            "color": "rgba(17, 24, 39, 0.18)",
            "size": 7,
            "x": 0,
            "y": 0,
        }

    node_issues = _graph_node_required_issues(node)
    if node_issues:
        raise ValueError(
            "No se pudo construir un nodo completo para "
            f"{node.get('id') or concept_key(concept)}: {', '.join(node_issues)}"
        )
    return node


def edge_identity(edge: dict) -> str:
    if not isinstance(edge, dict):
        return ""
    edge_id = _clean_text(edge.get("id"))
    if edge_id:
        return edge_id
    from_id = _clean_text(edge.get("from"))
    to_id = _clean_text(edge.get("to"))
    relation_type = _clean_text(edge.get("title") or edge.get("tipo") or edge.get("label"))
    return f"{from_id}::{relation_type}::{to_id}"


def _relation_color(relation_type: str) -> str:
    colors = GrafoConocimiento([], []).color_por_relacion
    return colors.get(relation_type, "black")


def relation_edge_from_doc(relation: dict, added_at: str) -> dict:
    from_id = _clean_text(relation.get("desde") or relation.get("from"))
    to_id = _clean_text(relation.get("hasta") or relation.get("to"))
    relation_type = _clean_text(relation.get("tipo") or relation.get("type") or "relaciona")
    edge_id = _clean_text(relation.get("id")) or f"{from_id}::{relation_type}::{to_id}"
    color = _relation_color(relation_type)
    return {
        "id": edge_id,
        "from": from_id,
        "to": to_id,
        "title": relation_type,
        "label": relation_type.replace("_", " "),
        "color": {"color": color, "highlight": color, "hover": color},
        "arrows": "to",
        "font": {
            "size": 13,
            "align": "middle",
            "color": color,
            "strokeWidth": 4,
            "strokeColor": "#ffffff",
        },
        "length": 260,
        "added_from_sync": True,
        "added_at": added_at,
    }


def _ensure_graph_state_lists(graph_state: dict) -> None:
    if not isinstance(graph_state.get("nodes"), list):
        graph_state["nodes"] = []
    if not isinstance(graph_state.get("edges"), list):
        graph_state["edges"] = []
    if not isinstance(graph_state.get("fullNodes"), list):
        graph_state["fullNodes"] = deepcopy(graph_state["nodes"])
    if not isinstance(graph_state.get("fullEdges"), list):
        graph_state["fullEdges"] = deepcopy(graph_state["edges"])


def _append_node_to_state(graph_state: dict, node: dict) -> None:
    node_key = node_concept_key(node)
    for collection_name in ("nodes", "fullNodes"):
        collection = graph_state[collection_name]
        if any(node_concept_key(item) == node_key for item in collection if isinstance(item, dict)):
            continue
        collection.append(deepcopy(node))


def _append_edge_to_state(graph_state: dict, edge: dict) -> bool:
    new_identity = edge_identity(edge)
    appended = False
    for collection_name in ("edges", "fullEdges"):
        collection = graph_state[collection_name]
        if any(edge_identity(item) == new_identity for item in collection if isinstance(item, dict)):
            continue
        collection.append(deepcopy(edge))
        appended = True
    return appended


def relation_docs_between_graph_nodes(mongo: Any, graph_state: dict) -> list[dict]:
    node_keys = sorted(graph_concept_keys(graph_state))
    if not node_keys:
        return []
    return list(mongo.relations.find({"desde": {"$in": node_keys}, "hasta": {"$in": node_keys}}))


def node_display_title(node: dict) -> str:
    if not isinstance(node, dict):
        return ""
    node_info = node.get("nodeInfo") if isinstance(node.get("nodeInfo"), dict) else {}
    for value in (
        node.get("rawLabel"),
        node_info.get("label"),
        node.get("label"),
        node.get("title"),
        node.get("id"),
    ):
        text = _clean_text(value).replace("<b>", "").replace("</b>", "")
        if text:
            return " ".join(text.split())
    return ""


def node_type_text(node: dict) -> str:
    if not isinstance(node, dict):
        return ""
    node_info = node.get("nodeInfo") if isinstance(node.get("nodeInfo"), dict) else {}
    return _clean_text(
        node.get("displayType")
        or node_info.get("displayType")
        or node.get("type")
        or node.get("mmType")
        or node.get("conceptType")
        or node_info.get("type")
    )


def node_source_text(node: dict) -> str:
    if not isinstance(node, dict):
        return ""
    _, source = node_concept_parts(node)
    return source


def infer_sources_from_graph_state(graph_state: dict | None) -> list[str]:
    sources = set()
    for node in graph_node_items(graph_state):
        source = node_source_text(node)
        if not source:
            node_info = node.get("nodeInfo") if isinstance(node.get("nodeInfo"), dict) else {}
            source = _clean_text(node_info.get("source"))
        if not source:
            _, source = split_concept_key(node.get("id"))
        if source:
            sources.add(source)
    return sorted(sources, key=str.lower)


def infer_concept_types_from_graph_state(graph_state: dict | None) -> list[str]:
    concept_types = set()
    for node in graph_node_items(graph_state):
        node_info = node.get("nodeInfo") if isinstance(node.get("nodeInfo"), dict) else {}
        node_type = _clean_text(
            node.get("type")
            or node.get("mmType")
            or node.get("conceptType")
            or node_info.get("type")
        )
        if node_type:
            concept_types.add(node_type)
    return sorted(concept_types, key=str.lower)


def edge_counts_by_node(graph_state: dict | None) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for node in graph_node_items(graph_state):
        node_id = _clean_text(node.get("id"))
        if node_id:
            counts[node_id] = {"incoming": 0, "outgoing": 0}

    for edge in graph_edge_items(graph_state):
        from_id = _clean_text(edge.get("from"))
        to_id = _clean_text(edge.get("to"))
        if from_id in counts:
            counts[from_id]["outgoing"] += 1
        if to_id in counts:
            counts[to_id]["incoming"] += 1
    return counts


def map_node_rows(mongo: Any, graph_state: dict | None) -> list[dict]:
    counts = edge_counts_by_node(graph_state)
    rows = []
    for node in sorted(graph_node_items(graph_state), key=lambda item: node_display_title(item).lower()):
        node_id = _clean_text(node.get("id"))
        concept = find_concept_for_node(mongo, node)
        incomplete = _node_is_incomplete_or_stale(node) or concept is None
        rows.append(
            {
                "Quitar": False,
                "Título": node_display_title(node),
                "Tipo": node_type_text(node),
                "Source": node_source_text(node),
                "ID interno": node_id,
                "Entrantes": counts.get(node_id, {}).get("incoming", 0),
                "Salientes": counts.get(node_id, {}).get("outgoing", 0),
                "Estado": "incompleto" if incomplete else "ok",
            }
        )
    return rows


def incomplete_node_ids(mongo: Any, graph_state: dict | None) -> list[str]:
    ids = []
    for node in graph_node_items(graph_state):
        node_id = _clean_text(node.get("id"))
        if not node_id:
            continue
        concept = find_concept_for_node(mongo, node)
        if _node_is_incomplete_or_stale(node) or concept is None:
            ids.append(node_id)
    return sorted(set(ids))


def isolated_node_ids(graph_state: dict | None) -> list[str]:
    counts = edge_counts_by_node(graph_state)
    isolated = [
        node_id
        for node_id, count in counts.items()
        if count.get("incoming", 0) == 0 and count.get("outgoing", 0) == 0
    ]
    return sorted(set(isolated))


def graph_state_integrity_issues(graph_state: dict | None) -> list[str]:
    if not isinstance(graph_state, dict):
        return ["El estado del grafo no es un objeto JSON."]

    issues: list[str] = []
    raw_nodes = graph_state.get("nodes")
    raw_full_nodes = graph_state.get("fullNodes")
    if isinstance(raw_full_nodes, list) and raw_full_nodes and not raw_nodes:
        issues.append("`nodes` está vacío aunque `fullNodes` contiene nodos.")

    nodes = graph_node_items(graph_state)
    node_ids = {_clean_text(node.get("id")) for node in nodes if _clean_text(node.get("id"))}
    for index, node in enumerate(nodes, start=1):
        node_id = _clean_text(node.get("id")) or f"nodo #{index}"
        required_issues = _graph_node_required_issues(node)
        if required_issues:
            issues.append(f"{node_id}: faltan {', '.join(required_issues)}.")
        shape = _clean_text(node.get("shape"))
        node_type = node_type_text(node)
        if shape in {"circle", "dot"} and node_type != "placeholder":
            issues.append(f"{node_id}: usa shape genérico `{shape}` en lugar de un nodo tipado.")

    orphan_edges = []
    for edge in graph_edge_items(graph_state):
        from_id = _clean_text(edge.get("from"))
        to_id = _clean_text(edge.get("to"))
        if from_id not in node_ids or to_id not in node_ids:
            orphan_edges.append(edge_identity(edge) or f"{from_id}->{to_id}")
    if orphan_edges:
        preview = ", ".join(orphan_edges[:5])
        suffix = "..." if len(orphan_edges) > 5 else ""
        issues.append(f"{len(orphan_edges)} aristas apuntan a nodos inexistentes: {preview}{suffix}")

    return issues


def remove_nodes_from_graph_state(graph_state: dict | None, node_ids: list[str]) -> tuple[dict, int, int]:
    removed_ids = {_clean_text(node_id) for node_id in node_ids if _clean_text(node_id)}
    new_state = deepcopy(graph_state) if isinstance(graph_state, dict) else {}
    _ensure_graph_state_lists(new_state)
    if not removed_ids:
        return new_state, 0, 0

    removed_count = 0
    for collection_name in ("nodes", "fullNodes"):
        original_nodes = [node for node in new_state[collection_name] if isinstance(node, dict)]
        kept_nodes = [node for node in original_nodes if _clean_text(node.get("id")) not in removed_ids]
        if collection_name == "nodes":
            removed_count = len(original_nodes) - len(kept_nodes)
        new_state[collection_name] = kept_nodes

    removed_edges = 0
    for collection_name in ("edges", "fullEdges"):
        original_edges = [edge for edge in new_state[collection_name] if isinstance(edge, dict)]
        kept_edges = [
            edge
            for edge in original_edges
            if _clean_text(edge.get("from")) not in removed_ids and _clean_text(edge.get("to")) not in removed_ids
        ]
        if collection_name == "edges":
            removed_edges = len(original_edges) - len(kept_edges)
        new_state[collection_name] = kept_edges

    if isinstance(new_state.get("selection"), list):
        new_state["selection"] = [node_id for node_id in new_state["selection"] if node_id not in removed_ids]

    ui_controls = new_state.get("uiControls")
    if isinstance(ui_controls, dict):
        if ui_controls.get("selectedNodeId") in removed_ids:
            ui_controls["selectedNodeId"] = ""
        if isinstance(ui_controls.get("visibleNodeIds"), list):
            ui_controls["visibleNodeIds"] = [
                node_id for node_id in ui_controls["visibleNodeIds"] if node_id not in removed_ids
            ]
        if isinstance(ui_controls.get("visibleEdgeIds"), list):
            remaining_edge_ids = {edge_identity(edge) for edge in new_state.get("fullEdges", [])}
            ui_controls["visibleEdgeIds"] = [
                edge_id for edge_id in ui_controls["visibleEdgeIds"] if edge_id in remaining_edge_ids
            ]

    new_state["exportedAt"] = utc_timestamp()
    return new_state, removed_count, removed_edges


def _concept_lookup_queries(concept_id: str, source: str) -> list[dict]:
    queries = []
    if concept_id and source:
        queries.append({"id": concept_id, "source": source})
        queries.append({"concept_id": concept_id, "source": source})
        queries.append({"conceptId": concept_id, "source": source})
        queries.append({"id": f"{concept_id}@{source}"})
    if concept_id:
        queries.append({"id": concept_id})
        queries.append({"concept_id": concept_id})
        queries.append({"conceptId": concept_id})
    return queries


def find_concept_for_node(mongo: Any, node: dict) -> dict | None:
    concept_id, source = node_concept_parts(node)
    if not concept_id:
        node_id = _clean_text(node.get("id") if isinstance(node, dict) else "")
        concept_id, source = split_concept_key(node_id)

    for query in _concept_lookup_queries(concept_id, source):
        concept = mongo.concepts.find_one(query)
        if concept:
            return concept
    return None


def _node_is_incomplete_or_stale(node: dict, rebuilt_node: dict | None = None) -> bool:
    if not isinstance(node, dict):
        return False
    missing_required = any(
        not node.get(field)
        for field in ("id", "title", "source", "rawLabel")
    )
    missing_type = not (node.get("type") or node.get("mmType") or node.get("conceptType"))
    missing_concept_id = not (node.get("concept_id") or node.get("conceptId"))
    label_missing = node.get("shape") != "image" and not node.get("label")
    generic_shape = node.get("shape") in {"circle", "dot"} and node_type_text(node) != "placeholder"

    if missing_required or missing_type or missing_concept_id or label_missing:
        return True

    if not rebuilt_node:
        return False

    stale_shape = (
        rebuilt_node.get("shape")
        and node.get("shape") in {"circle", "dot"}
        and rebuilt_node.get("shape") != node.get("shape")
    )
    stale_type = (
        rebuilt_node.get("type")
        and node.get("type")
        and str(node.get("type")).strip().lower() != str(rebuilt_node.get("type")).strip().lower()
    )
    color = node.get("color")
    stale_sync_color = (
        isinstance(color, dict)
        and color.get("border") in {"#2563EB", "#1D4ED8"}
        and node.get("added_from_sync")
    )
    return generic_shape or stale_shape or stale_type or stale_sync_color


def _repair_node_from_concept(node: dict, concept: dict) -> dict:
    position = {
        "x": node.get("x", 0),
        "y": node.get("y", 0),
    }
    repaired = build_node_from_concept(
        concept,
        position,
        added_at=_clean_text(node.get("added_at")) or utc_timestamp(),
        sync_origin=_clean_text(node.get("sync_origin")) or "repair",
        added_from_sync=bool(node.get("added_from_sync") or node.get("sync_origin")),
    )
    for key in ("x", "y", "fixed"):
        if key in node:
            repaired[key] = deepcopy(node[key])
    for key in ("added_from_sync", "added_at", "sync_origin"):
        if key in node:
            repaired[key] = deepcopy(node[key])
    if "borderWidth" in node and node.get("added_from_sync"):
        repaired["borderWidth"] = node["borderWidth"]
    return repaired


def repair_incomplete_graph_nodes(mongo: Any, graph_state: dict | None) -> tuple[dict, int, int]:
    repaired_state = deepcopy(graph_state) if isinstance(graph_state, dict) else {}
    _ensure_graph_state_lists(repaired_state)

    repairs_by_key: dict[str, dict] = {}
    unresolved = 0
    for node in graph_node_items(repaired_state):
        concept = find_concept_for_node(mongo, node)
        if not concept:
            if _node_is_incomplete_or_stale(node):
                unresolved += 1
            continue

        preview_repair = build_node_from_concept(
            concept,
            {"x": node.get("x", 0), "y": node.get("y", 0)},
            added_at=_clean_text(node.get("added_at")) or utc_timestamp(),
            sync_origin=_clean_text(node.get("sync_origin")) or "repair_preview",
            added_from_sync=bool(node.get("added_from_sync") or node.get("sync_origin")),
        )
        if not _node_is_incomplete_or_stale(node, preview_repair):
            continue

        key = node_concept_key(node) or node.get("id")
        if key:
            repairs_by_key[key] = _repair_node_from_concept(node, concept)

    if not repairs_by_key:
        return repaired_state, 0, unresolved

    for collection_name in ("nodes", "fullNodes"):
        repaired_collection = []
        seen_keys = set()
        for node in repaired_state[collection_name]:
            if not isinstance(node, dict):
                continue
            key = node_concept_key(node) or node.get("id")
            replacement = repairs_by_key.get(key)
            repaired_node = deepcopy(replacement or node)
            repaired_key = node_concept_key(repaired_node) or repaired_node.get("id")
            if repaired_key in seen_keys:
                continue
            seen_keys.add(repaired_key)
            repaired_collection.append(repaired_node)
        repaired_state[collection_name] = repaired_collection

    repaired_state["exportedAt"] = utc_timestamp()
    return repaired_state, len(repairs_by_key), unresolved


def add_concepts_to_graph_state(
    mongo: Any,
    graph_state: dict | None,
    concepts: list[dict],
    include_relations: bool = False,
    sync_origin: str = "source_sync",
) -> tuple[dict, int, int]:
    new_state = deepcopy(graph_state) if isinstance(graph_state, dict) else {}
    _ensure_graph_state_lists(new_state)
    added_at = utc_timestamp()

    added_nodes = 0
    for concept in concepts:
        if graph_contains_concept(new_state, concept):
            continue
        position = new_node_position(graph_state, added_nodes)
        node = build_node_from_concept(concept, position, added_at, sync_origin)
        _append_node_to_state(new_state, node)
        added_nodes += 1

    added_edges = 0
    if include_relations:
        valid_node_keys = graph_concept_keys(new_state)
        for relation in relation_docs_between_graph_nodes(mongo, new_state):
            from_id = _clean_text(relation.get("desde"))
            to_id = _clean_text(relation.get("hasta"))
            if from_id not in valid_node_keys or to_id not in valid_node_keys:
                continue
            if _append_edge_to_state(new_state, relation_edge_from_doc(relation, added_at)):
                added_edges += 1

    new_state["exportedAt"] = added_at
    return new_state, added_nodes, added_edges


def merge_preserved_graph_items(new_graph_state: dict, previous_graph_state: dict | None) -> dict:
    merged = deepcopy(new_graph_state) if isinstance(new_graph_state, dict) else {}
    _ensure_graph_state_lists(merged)

    for node in graph_node_items(previous_graph_state):
        if not graph_contains_concept(merged, node):
            _append_node_to_state(merged, node)

    merged_keys = graph_concept_keys(merged)
    for edge in graph_edge_items(previous_graph_state):
        from_id = _clean_text(edge.get("from"))
        to_id = _clean_text(edge.get("to"))
        if from_id in merged_keys and to_id in merged_keys:
            _append_edge_to_state(merged, edge)

    merged["exportedAt"] = utc_timestamp()
    return merged

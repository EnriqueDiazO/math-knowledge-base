"""Graph page helpers; extracted without import-time rendering."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
from bson import ObjectId

from editor.utils.knowledge_graph_sync import concept_table_rows
from editor.utils.knowledge_graph_sync import concepts_by_keys
from editor.utils.knowledge_graph_sync import infer_concept_types_from_graph_state
from editor.utils.knowledge_graph_sync import infer_sources_from_graph_state
from editor.utils.knowledge_graph_sync import merge_ordered_values
from mathdatabase.mathmongo import MathMongo
from visualizations.grafoconocimiento import GrafoConocimiento

DEBUG_KNOWLEDGE_GRAPH = os.getenv("DEBUG_KNOWLEDGE_GRAPH", "0") == "1"

def _kg_debug(message: str, **kwargs) -> None:
    if DEBUG_KNOWLEDGE_GRAPH:
        detail = " ".join(f"{key}={value}" for key, value in kwargs.items())
        print(f"[KG] {message}" + (f" {detail}" if detail else ""))


def _parse_knowledge_graph_state_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Pega primero el JSON del estado actual del grafo.")

    payload = json.loads(text)
    graph_state = payload.get("graph_state", payload) if isinstance(payload, dict) else None
    if not isinstance(graph_state, dict):
        raise ValueError("El JSON debe ser un objeto con el estado del grafo.")
    if not isinstance(graph_state.get("nodes"), list) or not isinstance(graph_state.get("edges"), list):
        raise ValueError("El estado debe incluir listas 'nodes' y 'edges'.")
    return graph_state


def _knowledge_graph_map_label(doc: dict) -> str:
    filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
    sources = filters.get("sources") or []
    concept_types = filters.get("concept_types") or []
    relation_types = filters.get("relation_types") or []
    updated_at = doc.get("updated_at") or doc.get("created_at")
    if isinstance(updated_at, datetime):
        updated_text = updated_at.strftime("%Y-%m-%d %H:%M")
    else:
        updated_text = str(updated_at or "sin fecha")
    return (
        f"{doc.get('name', 'Mapa sin nombre')} · {updated_text} · "
        f"{len(sources)} fuentes · {len(concept_types)} tipos · {len(relation_types)} relaciones"
    )


def _knowledge_graph_map_id_query(map_id: object) -> dict:
    id_text = str(map_id)
    candidates = [id_text]
    try:
        candidates.append(ObjectId(id_text))
    except Exception:
        pass
    return {"_id": {"$in": candidates}}


def _find_knowledge_graph_map(maps_col, map_id: object) -> dict | None:
    return maps_col.find_one(_knowledge_graph_map_id_query(map_id))


def _knowledge_graph_state_counts(graph_state: dict) -> tuple[int, int]:
    if not isinstance(graph_state, dict):
        return 0, 0
    nodes = graph_state.get("nodes") if isinstance(graph_state.get("nodes"), list) else []
    edges = graph_state.get("edges") if isinstance(graph_state.get("edges"), list) else []
    return len(nodes), len(edges)


def merge_sources_before_widget_creation(map_id: object, saved_sources: list[str], graph_state: dict) -> list[str]:
    """Merge saved sources with graph-inferred sources before Streamlit widgets exist."""
    del map_id
    return merge_ordered_values(saved_sources, infer_sources_from_graph_state(graph_state))


def merge_concept_types_before_widget_creation(
    map_id: object,
    saved_types: list[str],
    graph_state: dict,
) -> list[str]:
    """Merge saved concept types with graph-inferred types before widgets exist."""
    del map_id
    return merge_ordered_values(saved_types, infer_concept_types_from_graph_state(graph_state))


def _kg_edit_form_state_key(map_id: str) -> str:
    return f"kg_edit_form_state_{map_id}"


def _kg_edit_pending_widget_key(map_id: str) -> str:
    return f"kg_edit_pending_widget_updates_{map_id}"


def _kg_edit_widget_keys(map_id: str) -> dict[str, str]:
    return {
        "name": f"kg_edit_name_widget_{map_id}",
        "description": f"kg_edit_description_widget_{map_id}",
        "tags": f"kg_edit_tags_widget_{map_id}",
        "sources": f"kg_edit_sources_widget_{map_id}",
        "concept_types": f"kg_edit_concept_types_widget_{map_id}",
        "relation_types": f"kg_edit_relation_types_widget_{map_id}",
        "max_depth": f"kg_edit_max_depth_widget_{map_id}",
        "use_pasted_state_json": f"kg_edit_use_pasted_state_json_widget_{map_id}",
        "graph_state_json": f"kg_edit_graph_state_json_widget_{map_id}",
    }


def _kg_edit_form_state_from_doc(map_id: str, edit_doc: dict, graph_state: dict) -> dict:
    filters = edit_doc.get("filters", {}) if isinstance(edit_doc.get("filters"), dict) else {}
    return {
        "name": edit_doc.get("name", ""),
        "description": edit_doc.get("description", ""),
        "tags": ", ".join(edit_doc.get("tags", []) or []),
        "sources": merge_sources_before_widget_creation(map_id, filters.get("sources", []), graph_state),
        "concept_types": merge_concept_types_before_widget_creation(
            map_id,
            filters.get("concept_types", []),
            graph_state,
        ),
        "relation_types": list(filters.get("relation_types", []) or []),
        "max_depth": min(5, max(1, int(filters.get("max_depth", 3) or 3))),
        "use_pasted_state_json": False,
        "graph_state_json": "",
    }


def _queue_kg_edit_widget_update(map_id: str, updates: dict) -> None:
    pending_key = _kg_edit_pending_widget_key(map_id)
    pending = st.session_state.get(pending_key, {})
    if not isinstance(pending, dict):
        pending = {}
    pending.update(updates)
    st.session_state[pending_key] = pending


def _sync_kg_edit_form_state_from_graph(map_id: str, graph_state: dict) -> dict:
    form_state_key = _kg_edit_form_state_key(map_id)
    form_state = st.session_state.get(form_state_key, {})
    if not isinstance(form_state, dict):
        form_state = {}
    form_state["sources"] = merge_sources_before_widget_creation(
        map_id,
        form_state.get("sources", []),
        graph_state,
    )
    form_state["concept_types"] = merge_concept_types_before_widget_creation(
        map_id,
        form_state.get("concept_types", []),
        graph_state,
    )
    st.session_state[form_state_key] = form_state
    return form_state


def _apply_kg_edit_widget_updates_before_creation(map_id: str, form_state: dict, graph_state: dict) -> dict:
    widget_keys = _kg_edit_widget_keys(map_id)
    pending_key = _kg_edit_pending_widget_key(map_id)
    pending = st.session_state.pop(pending_key, {})
    if not isinstance(pending, dict):
        pending = {}

    for field, key in widget_keys.items():
        base_value = pending.get(field, form_state.get(field))
        if field == "sources":
            current_value = st.session_state.get(key, base_value)
            value = merge_sources_before_widget_creation(map_id, current_value, graph_state)
            st.session_state[key] = value
            form_state[field] = value
        elif field == "concept_types":
            current_value = st.session_state.get(key, base_value)
            value = merge_concept_types_before_widget_creation(map_id, current_value, graph_state)
            st.session_state[key] = value
            form_state[field] = value
        elif key not in st.session_state or field in pending:
            st.session_state[key] = base_value
            form_state[field] = base_value
        else:
            form_state[field] = st.session_state[key]

    st.session_state[_kg_edit_form_state_key(map_id)] = form_state
    return widget_keys


def _knowledge_graph_map_summary(doc: dict) -> dict:
    filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
    tags = doc.get("tags", []) if isinstance(doc.get("tags"), list) else []
    sources = filters.get("sources", []) if isinstance(filters.get("sources"), list) else []
    concept_types = filters.get("concept_types", []) if isinstance(filters.get("concept_types"), list) else []
    relation_types = filters.get("relation_types", []) if isinstance(filters.get("relation_types"), list) else []
    nodes, edges = _knowledge_graph_state_counts(doc.get("graph_state", {}))
    updated_at = doc.get("updated_at") or doc.get("created_at")
    updated_text = updated_at.strftime("%Y-%m-%d %H:%M") if isinstance(updated_at, datetime) else str(updated_at or "")
    description = str(doc.get("description", "") or "")
    return {
        "Nombre": doc.get("name", "Mapa sin nombre"),
        "Descripción": description[:90] + ("..." if len(description) > 90 else ""),
        "Tags": ", ".join(tags),
        "Fuentes": ", ".join(sources),
        "Tipos concepto": ", ".join(concept_types),
        "Tipos relación": ", ".join(relation_types),
        "Última actualización": updated_text,
        "Nodos": nodes,
        "Aristas": edges,
    }


def _render_knowledge_graph_map_html(graph_state: dict, map_key: str) -> str:
    del map_key
    grafo = GrafoConocimiento([], [])
    return grafo.exportar_html(salida=None, initial_state=graph_state)


def _render_knowledge_graph_map_metadata(doc: dict) -> None:
    filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
    tags = doc.get("tags", []) if isinstance(doc.get("tags"), list) else []
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")
    st.caption(doc.get("description", "") or "Sin descripción.")
    st.write(f"**Tags:** {', '.join(tags) if tags else 'Sin tags'}")
    st.write(f"**Fuentes:** {', '.join(filters.get('sources', []) or []) or 'Sin fuentes'}")
    st.write(f"**Tipos de concepto:** {', '.join(filters.get('concept_types', []) or []) or 'Sin tipos'}")
    st.write(f"**Tipos de relación:** {', '.join(filters.get('relation_types', []) or []) or 'Sin relaciones'}")
    st.write(f"**Max depth:** {filters.get('max_depth', 'N/D')}")
    if created_at:
        st.write(f"**Creado:** {created_at}")
    if updated_at:
        st.write(f"**Actualizado:** {updated_at}")


def _source_from_graph_endpoint(value) -> str | None:
    if not isinstance(value, str) or "@" not in value:
        return None
    source = value.rsplit("@", 1)[1].strip()
    return source or None


def _knowledge_graph_source_options(mongo: MathMongo, saved_maps: list[dict] | None = None) -> list[str]:
    sources = set()

    for source in mongo.concepts.distinct("source"):
        if isinstance(source, str) and source.strip():
            sources.add(source.strip())

    for field in ("desde", "hasta"):
        for endpoint in mongo.relations.distinct(field):
            source = _source_from_graph_endpoint(endpoint)
            if source:
                sources.add(source)

    for doc in saved_maps or []:
        for field in ("primary_map_source", "primary_source", "map_sources"):
            value = doc.get(field)
            for source in value if isinstance(value, list) else [value]:
                if isinstance(source, str) and source.strip():
                    sources.add(source.strip())
        filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
        for source in filters.get("sources", []) or []:
            if isinstance(source, str) and source.strip():
                sources.add(source.strip())
        for source in infer_sources_from_graph_state(doc.get("graph_state", {})):
            sources.add(source)

    return sorted(sources, key=str.lower)


def _build_knowledge_graph_state_from_filters(
    mongo: MathMongo,
    sources: list[str],
    relation_types: list[str],
    concept_types: list[str],
    previous_state: dict | None = None,
) -> dict:
    clean_sources = [source for source in sources or [] if source]
    clean_relations = [relation for relation in relation_types or [] if relation]
    clean_types = [concept_type for concept_type in concept_types or [] if concept_type]

    concept_query = {}
    if clean_sources:
        concept_query["source"] = {"$in": clean_sources}
    if clean_types:
        concept_query["tipo"] = {"$in": clean_types}
    concepts = list(mongo.concepts.find(concept_query))

    relation_query = {}
    if clean_sources:
        source_pattern = "|".join(re.escape(source) for source in clean_sources)
        relation_query["$or"] = [
            {"desde": {"$regex": f"@({source_pattern})$"}},
            {"hasta": {"$regex": f"@({source_pattern})$"}},
        ]
    if clean_relations:
        relation_query["tipo"] = {"$in": clean_relations}
    relations = list(mongo.relations.find(relation_query))

    grafo = GrafoConocimiento(concepts, relations)
    grafo.construir_grafo(tipos_relacion=clean_relations, tipos_concepto=clean_types)
    return grafo.to_graph_state(previous_state=previous_state)


def _knowledge_graph_concept_selector(concepts: list[dict], key: str) -> list[dict]:
    if not concepts:
        return []

    rows = concept_table_rows(concepts)
    rows_df = pd.DataFrame(rows)
    edited_rows = st.data_editor(
        rows_df,
        key=key,
        hide_index=True,
        width="stretch",
        column_config={
            "Agregar": st.column_config.CheckboxColumn("Agregar", default=False),
        },
        disabled=["Título", "Tipo", "Source", "ID interno", "Actualizado"],
    )
    if isinstance(edited_rows, pd.DataFrame):
        edited_records = edited_rows.to_dict("records")
    else:
        edited_records = edited_rows
    selected_keys = {
        str(row.get("ID interno"))
        for row in edited_records
        if isinstance(row, dict) and row.get("Agregar") and row.get("ID interno")
    }
    return concepts_by_keys(concepts, selected_keys)


def _knowledge_graph_node_id_selector(rows: list[dict], key: str) -> list[str]:
    if not rows:
        return []

    edited_rows = st.data_editor(
        pd.DataFrame(rows),
        key=key,
        hide_index=True,
        width="stretch",
        column_config={
            "Quitar": st.column_config.CheckboxColumn("Quitar", default=False),
        },
        disabled=["Título", "Tipo", "Source", "ID interno", "Entrantes", "Salientes", "Estado"],
    )
    if isinstance(edited_rows, pd.DataFrame):
        edited_records = edited_rows.to_dict("records")
    else:
        edited_records = edited_rows
    return [
        str(row.get("ID interno"))
        for row in edited_records
        if isinstance(row, dict) and row.get("Quitar") and row.get("ID interno")
    ]

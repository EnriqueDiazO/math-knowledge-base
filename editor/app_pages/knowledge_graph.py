"""Knowledge graph; extracted without import-time rendering."""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

import pandas as pd
import streamlit as st

from editor.database_scope import KNOWLEDGE_GRAPH_LOADED_MAP_KEY
from editor.database_scope import knowledge_map_is_loaded
from editor.database_scope import knowledge_map_session_identity
from editor.database_scope import mark_knowledge_map_loaded
from editor.database_scope import sync_knowledge_graph_scope
from editor.graph_page_helpers import _apply_kg_edit_widget_updates_before_creation
from editor.graph_page_helpers import _build_knowledge_graph_state_from_filters
from editor.graph_page_helpers import _find_knowledge_graph_map
from editor.graph_page_helpers import _kg_debug
from editor.graph_page_helpers import _kg_edit_form_state_from_doc
from editor.graph_page_helpers import _kg_edit_form_state_key
from editor.graph_page_helpers import _kg_edit_widget_keys
from editor.graph_page_helpers import _knowledge_graph_concept_selector
from editor.graph_page_helpers import _knowledge_graph_map_id_query
from editor.graph_page_helpers import _knowledge_graph_map_label
from editor.graph_page_helpers import _knowledge_graph_map_summary
from editor.graph_page_helpers import _knowledge_graph_node_id_selector
from editor.graph_page_helpers import _knowledge_graph_source_options
from editor.graph_page_helpers import _knowledge_graph_state_counts
from editor.graph_page_helpers import _parse_knowledge_graph_state_json
from editor.graph_page_helpers import _queue_kg_edit_widget_update
from editor.graph_page_helpers import _render_knowledge_graph_map_html
from editor.graph_page_helpers import _render_knowledge_graph_map_metadata
from editor.graph_page_helpers import _sync_kg_edit_form_state_from_graph
from editor.helpers.tipo_relacion import TipoRelacion
from editor.utils.knowledge_graph_sync import add_concepts_to_graph_state
from editor.utils.knowledge_graph_sync import concept_graph_node_errors
from editor.utils.knowledge_graph_sync import concept_graph_node_warnings
from editor.utils.knowledge_graph_sync import concept_key
from editor.utils.knowledge_graph_sync import default_sync_settings
from editor.utils.knowledge_graph_sync import detect_missing_source_concepts
from editor.utils.knowledge_graph_sync import find_available_concepts
from editor.utils.knowledge_graph_sync import graph_state_integrity_issues
from editor.utils.knowledge_graph_sync import incomplete_node_ids
from editor.utils.knowledge_graph_sync import infer_concept_types_from_graph_state
from editor.utils.knowledge_graph_sync import infer_sources_from_graph_state
from editor.utils.knowledge_graph_sync import isolated_node_ids
from editor.utils.knowledge_graph_sync import map_node_rows
from editor.utils.knowledge_graph_sync import merge_ordered_values
from editor.utils.knowledge_graph_sync import merge_preserved_graph_items
from editor.utils.knowledge_graph_sync import primary_sources
from editor.utils.knowledge_graph_sync import remove_nodes_from_graph_state
from editor.utils.knowledge_graph_sync import repair_incomplete_graph_nodes
from editor.utils.knowledge_graph_sync import utc_timestamp
from mathmongo.time import naive_utc_now
from visualizations.grafoconocimiento import GrafoConocimiento


def render(context):
    """Render only the selected page using its explicit application context."""
    active_database_name = context.active_database_name
    active_database_scope = context.active_database_scope
    current_db = context.current_db
    db = context.db
    st.title("📊 Knowledge Graph Visualization")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    if not active_database_scope or not active_database_name:
        st.error("The active database scope could not be resolved safely.")
        st.stop()

    sync_knowledge_graph_scope(st.session_state, active_database_scope)
    connection_label = current_db or "<unlabeled connection>"
    st.info(
        f"Connection: **{connection_label}** · Database: **{active_database_name}**"
    )
    graph_message = st.session_state.pop("knowledge_graph_message", None)
    if graph_message:
        message_type, message_text = graph_message
        if message_type == "success":
            st.success(message_text)
        elif message_type == "info":
            st.info(message_text)
        else:
            st.error(message_text)

    maps_col = db.db["knowledge_graph_maps"]
    try:
        all_maps = list(maps_col.find({"study_room": {"$exists": False}}).sort("updated_at", -1).limit(200))
    except Exception as exc:
        all_maps = []
        st.error(f"No se pudieron listar los mapas guardados: {exc}")

    source_options = _knowledge_graph_source_options(db, all_maps)
    default_concept_type_options = ["definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"]
    saved_concept_type_options = {
        concept_type
        for doc in all_maps
        for concept_type in (doc.get("filters", {}) or {}).get("concept_types", [])
        if isinstance(concept_type, str) and concept_type.strip()
    }
    graph_concept_type_options = {
        concept_type
        for doc in all_maps
        for concept_type in infer_concept_types_from_graph_state(doc.get("graph_state", {}))
        if concept_type
    }
    db_concept_type_options = {
        concept_type
        for concept_type in db.concepts.distinct("tipo")
        if isinstance(concept_type, str) and concept_type.strip()
    }
    concept_type_options = sorted(
        set(default_concept_type_options)
        | saved_concept_type_options
        | graph_concept_type_options
        | db_concept_type_options,
        key=str.lower,
    )
    saved_relation_type_options = {
        relation_type
        for doc in all_maps
        for relation_type in (doc.get("filters", {}) or {}).get("relation_types", [])
        if isinstance(relation_type, str) and relation_type.strip()
    }
    db_relation_type_options = {
        relation_type
        for relation_type in db.relations.distinct("tipo")
        if isinstance(relation_type, str) and relation_type.strip()
    }
    relation_type_options = sorted(
        {t.value for t in TipoRelacion} | saved_relation_type_options | db_relation_type_options,
        key=str.lower,
    )
    kg_sections = ["🌐 Esfera editable", "📊 Nuevo mapa", "📚 Mapas guardados", "✏️ Editar mapa", "📤 Exportar / importar"]
    requested_kg_section = st.session_state.pop("knowledge_graph_section_request", None)
    if requested_kg_section in kg_sections:
        st.session_state["knowledge_graph_section"] = requested_kg_section
    elif "knowledge_graph_section" not in st.session_state:
        if st.session_state.get("knowledge_graph_active_mode") == "edit":
            st.session_state["knowledge_graph_section"] = "✏️ Editar mapa"
        elif st.session_state.get("knowledge_graph_active_mode") == "view":
            st.session_state["knowledge_graph_section"] = "📚 Mapas guardados"
        else:
            st.session_state["knowledge_graph_section"] = "🌐 Esfera editable"

    kg_section = st.radio(
        "Sección de mapas",
        kg_sections,
        horizontal=True,
        key="knowledge_graph_section",
        label_visibility="collapsed",
    )

    if kg_section == "🌐 Esfera editable":
        from editor.knowledge_map import render_knowledge_map
        render_knowledge_map(db, active_database_scope)

    elif kg_section == "📊 Nuevo mapa":
        st.subheader("📊 Nuevo mapa")
        col1, col2 = st.columns(2)
        with col1:
            selected_sources = st.multiselect(
                "Select Sources",
                source_options,
                default=source_options[:3] if source_options else [],
                key="kg_new_sources",
            )
            selected_types = st.multiselect(
                "Select Concept Types",
                concept_type_options,
                default=["definicion", "teorema", "proposicion"],
                key="kg_new_concept_types",
            )
        with col2:
            selected_relations = st.multiselect(
                "Select Relation Types",
                relation_type_options,
                default=["implica", "deriva_de", "requiere_concepto"],
                key="kg_new_relation_types",
            )
            max_depth = st.slider("Max Depth", 1, 5, 3, key="kg_new_max_depth")

        if st.button("🔍 Generate Graph", type="primary", key="kg_generate_graph"):
            if selected_sources:
                try:
                    concept_query = {"source": {"$in": selected_sources}}
                    if selected_types:
                        concept_query["tipo"] = {"$in": selected_types}
                    concepts = list(db.concepts.find(concept_query))

                    relation_query = {
                        "$or": [
                            {"desde": {"$regex": f"@({'|'.join(selected_sources)})$"}},
                            {"hasta": {"$regex": f"@({'|'.join(selected_sources)})$"}},
                        ]
                    }
                    if selected_relations:
                        relation_query["tipo"] = {"$in": selected_relations}
                    relations = list(db.relations.find(relation_query))

                    if concepts and relations:
                        grafo = GrafoConocimiento(concepts, relations)
                        grafo.construir_grafo(
                            tipos_relacion=selected_relations,
                            tipos_concepto=selected_types,
                        )
                        st.session_state["knowledge_graph_new_html"] = grafo.exportar_html(salida=None)
                        st.session_state["knowledge_graph_new_stats"] = {
                            "nodes": len(grafo.G.nodes),
                            "edges": len(grafo.G.edges),
                            "sources": len(selected_sources),
                        }
                        st.success("Grafo generado correctamente.")
                    else:
                        st.warning("⚠️ No concepts or relations found with the selected filters.")
                except Exception as e:
                    st.error(f"❌ Error generating graph: {e}")
            else:
                st.error("❌ Please select at least one source.")

        if st.session_state.get("knowledge_graph_new_html"):
            st.subheader("🎯 Interactive Knowledge Graph")
            st.components.v1.html(st.session_state["knowledge_graph_new_html"], height=800)
            st.caption(
                "Edita el grafo y usa 📋 Copiar estado JSON dentro del panel. "
                "Pega ese JSON abajo para guardar el mapa generado."
            )
            stats = st.session_state.get("knowledge_graph_new_stats", {})
            stat_col1, stat_col2, stat_col3 = st.columns(3)
            stat_col1.metric("Nodes", stats.get("nodes", 0))
            stat_col2.metric("Edges", stats.get("edges", 0))
            stat_col3.metric("Sources", stats.get("sources", 0))

        with st.form("kg_save_new_map_form"):
            st.markdown("**Guardar mapa generado**")
            map_name = st.text_input("Nombre del mapa", key="kg_new_map_name")
            map_description = st.text_area("Descripción", height=80, key="kg_new_map_description")
            map_tags = st.text_input("Tags (separados por coma)", key="kg_new_map_tags")
            graph_state_json = st.text_area(
                "Estado JSON actual del grafo",
                height=160,
                key="kg_new_graph_state_json",
                placeholder="Pega aquí el JSON copiado con 📋 Copiar estado JSON...",
            )
            save_map = st.form_submit_button("💾 Guardar mapa generado")

        if save_map:
            if not map_name.strip():
                st.error("El nombre del mapa es obligatorio.")
            else:
                try:
                    graph_state = _parse_knowledge_graph_state_json(graph_state_json)
                    integrity_issues = graph_state_integrity_issues(graph_state)
                    if integrity_issues:
                        st.error("Se detectaron inconsistencias antes de guardar el mapa.")
                        st.warning("\n".join(f"- {issue}" for issue in integrity_issues[:8]))
                        st.stop()
                    now = naive_utc_now()
                    inferred_sources = infer_sources_from_graph_state(graph_state)
                    inferred_types = infer_concept_types_from_graph_state(graph_state)
                    map_sources = merge_ordered_values(selected_sources, inferred_sources)
                    primary_map_source = map_sources[0] if map_sources else ""
                    document = {
                        "name": map_name.strip(),
                        "description": map_description.strip(),
                        "created_at": now,
                        "updated_at": now,
                        "filters": {
                            "sources": map_sources,
                            "relation_types": list(selected_relations or []),
                            "concept_types": merge_ordered_values(selected_types, inferred_types),
                            "max_depth": max_depth,
                        },
                        "primary_map_source": primary_map_source,
                        "map_sources": map_sources,
                        "graph_state": graph_state,
                        "tags": [tag.strip() for tag in map_tags.split(",") if tag.strip()],
                        "source": "interactive_knowledge_graph",
                        "map_uid": str(uuid4()),
                        "sync_settings": default_sync_settings(),
                    }
                    result = maps_col.insert_one(document)
                    if result.acknowledged:
                        st.success("Mapa guardado correctamente.")
                    else:
                        st.error("MongoDB no confirmó el guardado del mapa.")
                except json.JSONDecodeError as exc:
                    st.error(f"No se pudo leer el JSON del estado: {exc}")
                except Exception as exc:
                    st.error(f"No se pudo guardar el mapa: {exc}")

    elif kg_section == "📚 Mapas guardados":
        st.subheader("📚 Mapas guardados")
        if not all_maps:
            st.info("Todavía no hay mapas guardados en knowledge_graph_maps.")
        else:
            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
            with filter_col1:
                search_text = st.text_input("Buscar por nombre", key="kg_maps_search")
            all_tags = sorted({tag for doc in all_maps for tag in doc.get("tags", []) if isinstance(tag, str)})
            all_map_sources = sorted(
                {
                    source
                    for doc in all_maps
                    for source in (doc.get("filters", {}) or {}).get("sources", [])
                    if isinstance(source, str)
                }
            )
            all_map_types = sorted(
                {
                    concept_type
                    for doc in all_maps
                    for concept_type in (doc.get("filters", {}) or {}).get("concept_types", [])
                    if isinstance(concept_type, str)
                }
            )
            with filter_col2:
                tag_filter = st.selectbox("Filtrar por tag", [""] + all_tags, key="kg_maps_tag_filter")
            with filter_col3:
                source_filter = st.selectbox("Filtrar por fuente", [""] + all_map_sources, key="kg_maps_source_filter")
            with filter_col4:
                type_filter = st.selectbox("Filtrar por tipo", [""] + all_map_types, key="kg_maps_type_filter")

            filtered_maps = []
            for doc in all_maps:
                filters = doc.get("filters", {}) if isinstance(doc.get("filters"), dict) else {}
                tags = doc.get("tags", []) if isinstance(doc.get("tags"), list) else []
                if search_text and search_text.lower() not in str(doc.get("name", "")).lower():
                    continue
                if tag_filter and tag_filter not in tags:
                    continue
                if source_filter and source_filter not in (filters.get("sources") or []):
                    continue
                if type_filter and type_filter not in (filters.get("concept_types") or []):
                    continue
                filtered_maps.append(doc)

            if not filtered_maps:
                st.info("No hay mapas que coincidan con los filtros.")
            else:
                st.dataframe(
                    pd.DataFrame([_knowledge_graph_map_summary(doc) for doc in filtered_maps]),
                    width="stretch",
                    hide_index=True,
                )
                map_options = {_knowledge_graph_map_label(doc): str(doc["_id"]) for doc in filtered_maps}
                selected_label = st.selectbox("Seleccionar mapa", list(map_options), key="kg_saved_selected_map")
                selected_map_id = map_options[selected_label]
                selected_doc = next(doc for doc in filtered_maps if str(doc["_id"]) == selected_map_id)

                action_col1, action_col2, action_col3, action_col4 = st.columns(4)
                with action_col1:
                    if st.button("Ver", key="kg_view_map"):
                        st.session_state["knowledge_graph_active_map_id"] = selected_map_id
                        st.session_state["knowledge_graph_active_mode"] = "view"
                with action_col2:
                    if st.button("Editar", key="kg_edit_map"):
                        st.session_state["knowledge_graph_active_map_id"] = selected_map_id
                        st.session_state["knowledge_graph_active_mode"] = "edit"
                        st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                        st.rerun()
                with action_col3:
                    if st.button("Duplicar", key="kg_duplicate_map"):
                        try:
                            now = naive_utc_now()
                            duplicate = {k: v for k, v in selected_doc.items() if k != "_id"}
                            duplicate["name"] = f"Copia de {selected_doc.get('name', 'Mapa sin nombre')}"
                            duplicate["map_uid"] = str(uuid4())
                            duplicate["created_at"] = now
                            duplicate["updated_at"] = now
                            result = maps_col.insert_one(duplicate)
                            if result.acknowledged:
                                st.success("Mapa duplicado correctamente.")
                            else:
                                st.error("MongoDB no confirmó la duplicación.")
                        except Exception as exc:
                            st.error(f"No se pudo duplicar el mapa: {exc}")
                with action_col4:
                    confirm_delete = st.checkbox("Confirmar eliminación", key="kg_saved_confirm_delete")
                    if st.button("Eliminar", key="kg_delete_map"):
                        if not confirm_delete:
                            st.error("Marca la confirmación antes de eliminar el mapa.")
                        else:
                            try:
                                result = maps_col.delete_one(_knowledge_graph_map_id_query(selected_map_id))
                                if result.deleted_count:
                                    st.success("Mapa eliminado correctamente.")
                                    if st.session_state.get("knowledge_graph_active_map_id") == selected_map_id:
                                        st.session_state.pop("knowledge_graph_active_map_id", None)
                                        st.session_state.pop("knowledge_graph_active_mode", None)
                                else:
                                    st.error("No se encontró el mapa que se intentaba eliminar.")
                            except Exception as exc:
                                st.error(f"No se pudo eliminar el mapa: {exc}")

                if st.session_state.get("knowledge_graph_active_mode") == "view":
                    active_id = st.session_state.get("knowledge_graph_active_map_id")
                    active_doc = _find_knowledge_graph_map(maps_col, active_id) if active_id else None
                    if active_doc:
                        st.divider()
                        st.subheader(active_doc.get("name", "Mapa guardado"))
                        _render_knowledge_graph_map_metadata(active_doc)
                        graph_state = active_doc.get("graph_state", {})
                        nodes, edges = _knowledge_graph_state_counts(graph_state)
                        metric_col1, metric_col2 = st.columns(2)
                        metric_col1.metric("Nodos", nodes)
                        metric_col2.metric("Aristas", edges)
                        if st.button("✏️ Editar este mapa", key="kg_view_to_edit"):
                            st.session_state["knowledge_graph_active_mode"] = "edit"
                            st.session_state["knowledge_graph_active_map_id"] = active_id
                            st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                            st.rerun()
                        html_content = _render_knowledge_graph_map_html(graph_state, f"view_{active_id}")
                        st.components.v1.html(html_content, height=800)

    elif kg_section == "✏️ Editar mapa":
        st.subheader("✏️ Editar mapa")
        if not all_maps:
            st.info("No hay mapas guardados para editar.")
        else:
            edit_options = {_knowledge_graph_map_label(doc): str(doc["_id"]) for doc in all_maps}
            active_id = st.session_state.get("knowledge_graph_active_map_id")
            default_index = 0
            if active_id and active_id in edit_options.values():
                default_index = list(edit_options.values()).index(active_id)
            edit_label = st.selectbox(
                "Mapa para editar",
                list(edit_options),
                index=default_index,
                key="kg_edit_selected_map",
            )
            edit_map_id = edit_options[edit_label]
            edit_doc = _find_knowledge_graph_map(maps_col, edit_map_id)
            if not edit_doc:
                st.error("No se encontró el mapa seleccionado.")
            else:
                edit_map_id_text = str(edit_map_id)
                filters = edit_doc.get("filters", {}) if isinstance(edit_doc.get("filters"), dict) else {}
                form_state_key = _kg_edit_form_state_key(edit_map_id_text)
                widget_keys = _kg_edit_widget_keys(edit_map_id_text)
                source_widget_key = widget_keys["sources"]
                concept_type_widget_key = widget_keys["concept_types"]
                edit_map_identity = knowledge_map_session_identity(
                    active_database_scope,
                    edit_map_id_text,
                    edit_doc.get("map_uid"),
                )
                if (
                    st.session_state.get(KNOWLEDGE_GRAPH_LOADED_MAP_KEY)
                    != edit_map_identity
                ):
                    initial_graph_state = deepcopy(edit_doc.get("graph_state", {}))
                    st.session_state["knowledge_graph_editing_map_id"] = edit_map_id_text
                    st.session_state["knowledge_graph_edit_graph_state"] = initial_graph_state
                    st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                        edit_doc.get("sync_settings")
                    )
                    form_state = _kg_edit_form_state_from_doc(edit_map_id_text, edit_doc, initial_graph_state)
                    st.session_state[form_state_key] = form_state
                    _queue_kg_edit_widget_update(edit_map_id_text, form_state)
                    st.session_state["knowledge_graph_edit_dirty"] = False
                    st.session_state["knowledge_graph_render_version"] = 0
                    st.session_state.pop("knowledge_graph_remove_pending", None)
                    mark_knowledge_map_loaded(
                        st.session_state,
                        active_database_scope,
                        edit_map_id_text,
                        edit_doc.get("map_uid"),
                    )
                else:
                    form_state = st.session_state.get(form_state_key, {})
                    if not isinstance(form_state, dict):
                        form_state = _kg_edit_form_state_from_doc(edit_map_id_text, edit_doc, edit_doc.get("graph_state", {}))
                        st.session_state[form_state_key] = form_state
                st.session_state["knowledge_graph_active_map_id"] = edit_map_id_text
                st.session_state["knowledge_graph_active_mode"] = "edit"
                map_state_ready = knowledge_map_is_loaded(
                    st.session_state,
                    active_database_scope,
                    edit_map_id_text,
                    edit_doc.get("map_uid"),
                )

                graph_state = st.session_state.get("knowledge_graph_edit_graph_state") or edit_doc.get("graph_state", {})
                current_node_count, current_edge_count = _knowledge_graph_state_counts(graph_state)
                _kg_debug(
                    "Loaded edit map",
                    map_id=edit_map_id_text,
                    nodes=current_node_count,
                    edges=current_edge_count,
                    dirty=st.session_state.get("knowledge_graph_edit_dirty"),
                )
                repaired_graph_state, repaired_nodes, unresolved_nodes = repair_incomplete_graph_nodes(
                    db,
                    graph_state,
                )
                if repaired_nodes:
                    if not map_state_ready:
                        st.error("Recarga el mapa desde la base activa antes de repararlo.")
                        st.stop()
                    repair_result = maps_col.update_one(
                        _knowledge_graph_map_id_query(edit_map_id),
                        {
                            "$set": {
                                "graph_state": repaired_graph_state,
                                "updated_at": naive_utc_now(),
                            }
                        },
                    )
                    if repair_result.acknowledged:
                        graph_state = repaired_graph_state
                        st.session_state["knowledge_graph_edit_graph_state"] = repaired_graph_state
                        st.session_state["knowledge_graph_edit_dirty"] = False
                        st.session_state["knowledge_graph_render_version"] = (
                            st.session_state.get("knowledge_graph_render_version", 0) + 1
                        )
                        edit_doc["graph_state"] = repaired_graph_state
                        st.success(
                            f"Se repararon {repaired_nodes} nodos incompletos usando los metadatos de MongoDB."
                        )
                    else:
                        st.warning("Se detectaron nodos incompletos, pero MongoDB no confirmó la reparación.")
                elif unresolved_nodes:
                    st.warning(
                        f"Hay {unresolved_nodes} nodos incompletos que no pudieron repararse porque no se encontró "
                        "su concepto en MongoDB."
                    )
                current_node_count, current_edge_count = _knowledge_graph_state_counts(graph_state)
                form_state = _sync_kg_edit_form_state_from_graph(edit_map_id_text, graph_state)
                map_source_options = merge_ordered_values(
                    source_options,
                    filters.get("sources", []),
                    form_state.get("sources", []),
                )
                map_concept_type_options = merge_ordered_values(
                    concept_type_options,
                    filters.get("concept_types", []),
                    form_state.get("concept_types", []),
                )
                st.markdown(f"**Editando:** {edit_doc.get('name', 'Mapa guardado')}")
                st.caption(
                    "Los cambios hechos con controles de Streamlit se guardan directamente. "
                    "Para conservar posiciones movidas dentro del grafo, copia el JSON desde el panel del grafo "
                    "y pégalo abajo."
                )
                st.caption(
                    f"Nodos actuales: {current_node_count} · Enlaces actuales: {current_edge_count} · "
                    f"Cambios no guardados: {'sí' if st.session_state.get('knowledge_graph_edit_dirty') else 'no'}"
                )
                if st.session_state.get("knowledge_graph_edit_dirty"):
                    st.warning("Hay cambios no guardados en este mapa.")
                render_version = st.session_state.get("knowledge_graph_render_version", 0)
                html_content = _render_knowledge_graph_map_html(graph_state, f"edit_{edit_map_id}_{render_version}")
                st.components.v1.html(html_content, height=800)

                sync_settings = default_sync_settings(
                    st.session_state.get("knowledge_graph_edit_sync_settings", edit_doc.get("sync_settings"))
                )
                manual_sync_key = f"kg_sync_manual_{edit_map_id}"
                ignore_sync_key = f"kg_sync_ignore_once_{edit_map_id}"

                def _save_graph_sync_update(
                    selected_concepts: list[dict],
                    include_relations: bool,
                    sync_origin: str,
                ) -> None:
                    if not map_state_ready:
                        st.error("Recarga el mapa desde la base activa antes de modificarlo.")
                        return
                    if not selected_concepts:
                        if sync_origin == "external_source":
                            st.session_state[f"kg_import_nodes_expander_open_{edit_map_id}"] = True
                        st.error("Selecciona al menos un concepto para agregar.")
                        return
                    invalid_concepts = []
                    warning_concepts = []
                    for concept in selected_concepts:
                        errors = concept_graph_node_errors(concept)
                        warnings = concept_graph_node_warnings(concept)
                        concept_name = concept_key(concept) or str(concept.get("titulo") or concept.get("title") or "")
                        if errors:
                            invalid_concepts.append(f"{concept_name or '<sin id>'}: {', '.join(errors)}")
                        elif warnings:
                            warning_concepts.append(concept_name or "<sin id>")
                    if invalid_concepts:
                        st.error(
                            "No se pudieron agregar algunos conceptos porque faltan metadatos mínimos:\n"
                            + "\n".join(f"- {item}" for item in invalid_concepts[:8])
                        )
                        return
                    new_graph_state, added_nodes, added_edges = add_concepts_to_graph_state(
                        db,
                        graph_state,
                        selected_concepts,
                        include_relations=include_relations,
                        sync_origin=sync_origin,
                    )
                    before_nodes, before_edges = _knowledge_graph_state_counts(graph_state)
                    after_nodes, after_edges = _knowledge_graph_state_counts(new_graph_state)
                    _kg_debug(
                        "Added concepts to edit map",
                        map_id=edit_map_id_text,
                        selected=len(selected_concepts),
                        before_nodes=before_nodes,
                        after_nodes=after_nodes,
                        before_edges=before_edges,
                        after_edges=after_edges,
                        added_nodes=added_nodes,
                        added_edges=added_edges,
                    )
                    skipped_duplicates = max(0, len(selected_concepts) - added_nodes)
                    selected_keys = {concept_key(concept) for concept in selected_concepts}
                    updated_sync_settings = default_sync_settings(
                        st.session_state.get("knowledge_graph_edit_sync_settings", edit_doc.get("sync_settings"))
                    )
                    updated_sync_settings["last_sync_check_at"] = utc_timestamp()
                    for field in ("removed_node_ids", "manually_removed_node_ids"):
                        updated_sync_settings[field] = [
                            node_id for node_id in updated_sync_settings.get(field, []) if node_id not in selected_keys
                        ]
                    updated_form_state = _sync_kg_edit_form_state_from_graph(edit_map_id_text, new_graph_state)
                    updated_form_state["sources"] = merge_ordered_values(
                        updated_form_state.get("sources", []),
                        [concept.get("source") for concept in selected_concepts if isinstance(concept, dict)],
                        infer_sources_from_graph_state(new_graph_state),
                    )
                    updated_form_state["concept_types"] = merge_ordered_values(
                        updated_form_state.get("concept_types", []),
                        [
                            concept.get("tipo") or concept.get("type") or concept.get("conceptType")
                            for concept in selected_concepts
                            if isinstance(concept, dict)
                        ],
                        infer_concept_types_from_graph_state(new_graph_state),
                    )
                    st.session_state[form_state_key] = updated_form_state
                    _queue_kg_edit_widget_update(
                        edit_map_id_text,
                        {
                            "sources": updated_form_state["sources"],
                            "concept_types": updated_form_state["concept_types"],
                        },
                    )
                    st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                    st.session_state["knowledge_graph_edit_sync_settings"] = updated_sync_settings
                    st.session_state["knowledge_graph_edit_dirty"] = True
                    st.session_state["knowledge_graph_render_version"] = (
                        st.session_state.get("knowledge_graph_render_version", 0) + 1
                    )
                    st.session_state[manual_sync_key] = False
                    st.session_state.pop(ignore_sync_key, None)
                    st.session_state["knowledge_graph_active_map_id"] = edit_map_id
                    st.session_state["knowledge_graph_active_mode"] = "edit"
                    st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                    if sync_origin == "external_source":
                        st.session_state[f"kg_import_nodes_expander_open_{edit_map_id}"] = True
                    duplicate_text = (
                        f" {skipped_duplicates} conceptos ya estaban en el mapa y se omitieron."
                        if skipped_duplicates
                        else ""
                    )
                    warning_text = (
                        f" {len(warning_concepts)} conceptos no tenían tipo explícito y se agregaron como `otro`."
                        if warning_concepts
                        else ""
                    )
                    st.session_state["knowledge_graph_message"] = (
                        "success" if added_nodes or added_edges else "info",
                        (
                            f"Se agregaron {added_nodes} nodos y {added_edges} relaciones al mapa actual. "
                            f"{duplicate_text}{warning_text} Guarda los cambios para persistirlos."
                        ),
                    )
                    st.rerun()

                sync_col1, sync_col2, sync_col3 = st.columns([1, 1, 2])
                with sync_col1:
                    if st.button("🔎 Revisar nuevos nodos del source", key=f"kg_sync_manual_button_{edit_map_id}"):
                        st.session_state[manual_sync_key] = True
                        st.session_state.pop(ignore_sync_key, None)
                        st.rerun()
                with sync_col2:
                    if st.button("🧩 Reparar nodos incompletos", key=f"kg_repair_nodes_button_{edit_map_id}"):
                        if not map_state_ready:
                            st.error("Recarga el mapa desde la base activa antes de repararlo.")
                            st.stop()
                        repaired_graph_state, repaired_nodes, unresolved_nodes = repair_incomplete_graph_nodes(
                            db,
                            graph_state,
                        )
                        if repaired_nodes:
                            repair_result = maps_col.update_one(
                                _knowledge_graph_map_id_query(edit_map_id),
                                {
                                    "$set": {
                                        "graph_state": repaired_graph_state,
                                        "updated_at": naive_utc_now(),
                                    }
                                },
                            )
                            if repair_result.acknowledged:
                                st.session_state["knowledge_graph_edit_graph_state"] = repaired_graph_state
                                st.session_state["knowledge_graph_render_version"] = (
                                    st.session_state.get("knowledge_graph_render_version", 0) + 1
                                )
                                st.session_state["knowledge_graph_message"] = (
                                    "success",
                                    f"Se repararon {repaired_nodes} nodos incompletos.",
                                )
                                st.rerun()
                            else:
                                st.error("MongoDB no confirmó la reparación.")
                        elif unresolved_nodes:
                            st.warning(
                                f"No se reparó ningún nodo; {unresolved_nodes} nodos no tienen concepto local "
                                "para reconstruirse."
                            )
                        else:
                            st.info("No se encontraron nodos incompletos.")
                with sync_col3:
                    primary_source_values = primary_sources(edit_doc)
                    primary_source_text = primary_source_values[0] if primary_source_values else ""
                    if primary_source_text:
                        st.caption(f"Source principal del mapa: {primary_source_text}")
                    else:
                        st.caption("Este mapa no tiene source principal declarado en sus filtros.")
                    map_sources_text = ", ".join(form_state.get("sources", []))
                    if map_sources_text:
                        st.caption(f"Fuentes presentes en el mapa: {map_sources_text}")
                    if sync_settings.get("suppress_new_nodes_prompt"):
                        st.caption("El aviso automático de nodos nuevos está desactivado para este mapa.")

                include_removed_sync_key = f"kg_sync_include_removed_{edit_map_id}"
                edit_doc_for_sync = dict(edit_doc)
                edit_doc_for_sync["sync_settings"] = sync_settings
                missing_concepts = detect_missing_source_concepts(
                    db,
                    edit_doc_for_sync,
                    graph_state,
                    include_removed=bool(st.session_state.get(include_removed_sync_key, False)),
                )
                show_manual_sync = bool(st.session_state.get(manual_sync_key))
                show_auto_sync = (
                    bool(missing_concepts)
                    and not show_manual_sync
                    and not sync_settings.get("suppress_new_nodes_prompt")
                    and not st.session_state.get(ignore_sync_key)
                )

                if show_manual_sync and not missing_concepts:
                    st.info("No hay conceptos nuevos pendientes para el source principal del mapa.")

                if missing_concepts and (show_auto_sync or show_manual_sync):
                    st.warning(
                        "Se detectaron nuevos conceptos en el source de este mapa que todavía no están incluidos "
                        "como nodos."
                    )
                    st.caption(
                        f"Conceptos faltantes detectados: {len(missing_concepts)}. "
                        "Puedes agregarlos todos o seleccionar una lista parcial."
                    )
                    include_sync_relations = st.checkbox(
                        "También agregar relaciones disponibles entre los nodos presentes y seleccionados",
                        value=True,
                        key=f"kg_sync_include_relations_{edit_map_id}",
                    )
                    st.checkbox(
                        "Mostrar también nodos removidos manualmente",
                        value=False,
                        key=include_removed_sync_key,
                    )
                    action_col1, action_col2, action_col3 = st.columns(3)
                    with action_col1:
                        if st.button("Agregar todos", key=f"kg_sync_add_all_{edit_map_id}"):
                            _save_graph_sync_update(
                                missing_concepts,
                                include_sync_relations,
                                sync_origin="source_sync",
                            )
                    with action_col2:
                        if st.button("Ignorar por ahora", key=f"kg_sync_ignore_now_{edit_map_id}"):
                            st.session_state[ignore_sync_key] = True
                            st.session_state[manual_sync_key] = False
                            st.session_state["knowledge_graph_message"] = (
                                "info",
                                "Sincronización omitida por ahora. El aviso volverá a aparecer en otra edición.",
                            )
                            st.rerun()
                    with action_col3:
                        if st.button("No volver a mostrar para este mapa", key=f"kg_sync_suppress_{edit_map_id}"):
                            if not map_state_ready:
                                st.error("Recarga el mapa desde la base activa antes de guardarlo.")
                                st.stop()
                            updated_sync_settings = default_sync_settings(edit_doc.get("sync_settings"))
                            updated_sync_settings["suppress_new_nodes_prompt"] = True
                            updated_sync_settings["last_sync_check_at"] = utc_timestamp()
                            result = maps_col.update_one(
                                _knowledge_graph_map_id_query(edit_map_id),
                                {
                                    "$set": {
                                        "sync_settings": updated_sync_settings,
                                        "updated_at": naive_utc_now(),
                                    }
                                },
                            )
                            if result.acknowledged:
                                st.session_state[manual_sync_key] = False
                                st.session_state["knowledge_graph_message"] = (
                                    "info",
                                    "Aviso automático desactivado para este mapa. La revisión manual seguirá disponible.",
                                )
                                st.rerun()
                            else:
                                st.error("MongoDB no confirmó el cambio de preferencia.")

                    with st.expander("Seleccionar de una lista", expanded=show_manual_sync):
                        selected_missing_concepts = _knowledge_graph_concept_selector(
                            missing_concepts,
                            key=f"kg_sync_missing_selector_{edit_map_id}",
                        )
                        if st.button("Agregar seleccionados", key=f"kg_sync_add_selected_{edit_map_id}"):
                            _save_graph_sync_update(
                                selected_missing_concepts,
                                include_sync_relations,
                                sync_origin="source_sync",
                            )

                external_expander_key = f"kg_import_nodes_expander_open_{edit_map_id}"
                with st.expander(
                    "Agregar nodos desde otros sources",
                    expanded=st.session_state.get(external_expander_key, False),
                ):
                    current_sources = set(form_state.get("sources", []))
                    external_source_options = [source for source in source_options if source not in current_sources]
                    if not external_source_options:
                        external_source_options = list(source_options)
                    if not external_source_options:
                        st.info("No hay sources disponibles para agregar nodos externos.")
                    else:
                        external_col1, external_col2 = st.columns(2)
                        with external_col1:
                            external_source = st.selectbox(
                                "Source",
                                external_source_options,
                                key=f"kg_external_source_{edit_map_id}",
                                on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                            )
                        with external_col2:
                            external_types = st.multiselect(
                                "Tipos de concepto",
                                concept_type_options,
                                key=f"kg_external_types_{edit_map_id}",
                                on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                            )
                        external_search = st.text_input(
                            "Buscar por texto",
                            key=f"kg_external_search_{edit_map_id}",
                            on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                        )
                        include_external_relations = st.checkbox(
                            "También agregar relaciones disponibles",
                            value=True,
                            key=f"kg_external_include_relations_{edit_map_id}",
                            on_change=lambda: st.session_state.__setitem__(external_expander_key, True),
                        )
                        external_concepts = find_available_concepts(
                            db,
                            external_source,
                            graph_state,
                            concept_types=list(external_types or []),
                            search_text=external_search,
                        )
                        if not external_concepts:
                            st.info("No hay conceptos disponibles con esos filtros o todos ya están en el mapa.")
                        else:
                            st.caption(
                                f"Conceptos disponibles para agregar desde `{external_source}`: "
                                f"{len(external_concepts)}"
                            )
                            selected_external_concepts = _knowledge_graph_concept_selector(
                                external_concepts,
                                key=f"kg_external_selector_{edit_map_id}",
                            )
                            if st.button("Agregar seleccionados al mapa", key=f"kg_external_add_selected_{edit_map_id}"):
                                _save_graph_sync_update(
                                    selected_external_concepts,
                                    include_external_relations,
                                    sync_origin="external_source",
                                )

                node_rows = map_node_rows(db, graph_state)

                def _queue_node_removal(node_ids: list[str], reason: str) -> None:
                    clean_ids = [node_id for node_id in node_ids if node_id]
                    if not clean_ids:
                        st.error("Selecciona al menos un nodo para quitar del mapa.")
                        return
                    st.session_state["knowledge_graph_remove_pending"] = {
                        "map_id": edit_map_id_text,
                        "node_ids": clean_ids,
                        "reason": reason,
                    }
                    st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                    st.rerun()

                pending_removal = st.session_state.get("knowledge_graph_remove_pending")
                if isinstance(pending_removal, dict) and pending_removal.get("map_id") == edit_map_id_text:
                    pending_ids = pending_removal.get("node_ids", [])
                    pending_rows = [row for row in node_rows if row.get("ID interno") in pending_ids]
                    st.warning(
                        f"Vas a quitar {len(pending_ids)} nodo(s) del mapa actual. "
                        "También se quitarán las aristas asociadas. Esto NO borrará los conceptos de MongoDB."
                    )
                    if pending_rows:
                        st.dataframe(
                            pd.DataFrame(pending_rows).drop(columns=["Quitar"], errors="ignore"),
                            width="stretch",
                            hide_index=True,
                        )
                    confirm_col1, confirm_col2 = st.columns(2)
                    with confirm_col1:
                        if st.button("Sí, quitar del mapa", key=f"kg_confirm_remove_nodes_{edit_map_id}"):
                            new_graph_state, removed_nodes, removed_edges = remove_nodes_from_graph_state(
                                graph_state,
                                pending_ids,
                            )
                            before_nodes, before_edges = _knowledge_graph_state_counts(graph_state)
                            after_nodes, after_edges = _knowledge_graph_state_counts(new_graph_state)
                            _kg_debug(
                                "Removed nodes from edit map",
                                map_id=edit_map_id_text,
                                requested=len(pending_ids),
                                removed_nodes=removed_nodes,
                                removed_edges=removed_edges,
                                before_nodes=before_nodes,
                                after_nodes=after_nodes,
                                before_edges=before_edges,
                                after_edges=after_edges,
                            )
                            updated_sync_settings = default_sync_settings(
                                st.session_state.get("knowledge_graph_edit_sync_settings", edit_doc.get("sync_settings"))
                            )
                            for field in ("removed_node_ids", "manually_removed_node_ids"):
                                existing_removed = set(updated_sync_settings.get(field, []))
                                existing_removed.update(pending_ids)
                                updated_sync_settings[field] = sorted(existing_removed)
                            updated_form_state = _sync_kg_edit_form_state_from_graph(edit_map_id_text, new_graph_state)
                            updated_form_state["sources"] = infer_sources_from_graph_state(new_graph_state)
                            updated_form_state["concept_types"] = infer_concept_types_from_graph_state(new_graph_state)
                            st.session_state[form_state_key] = updated_form_state
                            _queue_kg_edit_widget_update(
                                edit_map_id_text,
                                {
                                    "sources": updated_form_state["sources"],
                                    "concept_types": updated_form_state["concept_types"],
                                },
                            )
                            st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                            st.session_state["knowledge_graph_edit_sync_settings"] = updated_sync_settings
                            st.session_state["knowledge_graph_edit_dirty"] = True
                            st.session_state["knowledge_graph_render_version"] = (
                                st.session_state.get("knowledge_graph_render_version", 0) + 1
                            )
                            st.session_state.pop("knowledge_graph_remove_pending", None)
                            st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                            st.session_state["knowledge_graph_message"] = (
                                "info",
                                (
                                    f"Se quitaron {removed_nodes} nodos y {removed_edges} aristas del mapa actual. "
                                    "Guarda los cambios para persistirlos."
                                ),
                            )
                            st.rerun()
                    with confirm_col2:
                        if st.button("Cancelar", key=f"kg_cancel_remove_nodes_{edit_map_id}"):
                            st.session_state.pop("knowledge_graph_remove_pending", None)
                            st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                            st.rerun()

                with st.expander("Administrar nodos del mapa", expanded=False):
                    if not node_rows:
                        st.info("Este mapa no tiene nodos administrables.")
                    else:
                        node_options = {
                            f"{row.get('Título') or row.get('ID interno')} · {row.get('Tipo') or 'sin tipo'} · {row.get('ID interno')}": row.get("ID interno")
                            for row in node_rows
                        }
                        selected_node_label = st.selectbox(
                            "Nodo para quitar",
                            list(node_options),
                            key=f"kg_remove_single_node_selector_{edit_map_id}",
                        )
                        if st.button("🗑️ Quitar nodo seleccionado del mapa", key=f"kg_remove_single_node_{edit_map_id}"):
                            _queue_node_removal([node_options[selected_node_label]], "single")

                        st.divider()
                        selected_node_ids = _knowledge_graph_node_id_selector(
                            node_rows,
                            key=f"kg_manage_nodes_selector_{edit_map_id}",
                        )
                        if st.button("🗑️ Quitar nodos seleccionados del mapa", key=f"kg_remove_selected_nodes_{edit_map_id}"):
                            _queue_node_removal(selected_node_ids, "selected")

                        incomplete_ids = incomplete_node_ids(db, graph_state)
                        if incomplete_ids:
                            st.divider()
                            st.caption(f"Nodos incompletos detectados: {len(incomplete_ids)}")
                            incomplete_rows = [row for row in node_rows if row.get("ID interno") in incomplete_ids]
                            st.dataframe(
                                pd.DataFrame(incomplete_rows).drop(columns=["Quitar"], errors="ignore"),
                                width="stretch",
                                hide_index=True,
                            )
                            if st.button("🧹 Eliminar nodos incompletos", key=f"kg_remove_incomplete_nodes_{edit_map_id}"):
                                _queue_node_removal(incomplete_ids, "incomplete")

                        isolated_ids = isolated_node_ids(graph_state)
                        if isolated_ids:
                            st.divider()
                            st.caption(f"Nodos aislados detectados: {len(isolated_ids)}")
                            isolated_rows = [row for row in node_rows if row.get("ID interno") in isolated_ids]
                            st.dataframe(
                                pd.DataFrame(isolated_rows).drop(columns=["Quitar"], errors="ignore"),
                                width="stretch",
                                hide_index=True,
                            )
                            if st.button("🧹 Quitar nodos aislados", key=f"kg_remove_isolated_nodes_{edit_map_id}"):
                                _queue_node_removal(isolated_ids, "isolated")

                filters = edit_doc.get("filters", {}) if isinstance(edit_doc.get("filters"), dict) else {}
                state_col1, state_col2, state_col3 = st.columns(3)
                with state_col1:
                    st.download_button(
                        "📥 Descargar estado JSON",
                        data=json.dumps(graph_state, ensure_ascii=False, indent=2, default=str),
                        file_name=f"{edit_doc.get('name', 'knowledge_graph_map')}_state.json",
                        mime="application/json",
                        key=f"kg_edit_download_state_{edit_map_id}",
                    )
                with state_col2:
                    if st.button("📋 Mostrar estado JSON", key=f"kg_edit_show_state_json_{edit_map_id}"):
                        st.session_state[f"kg_show_edit_state_json_{edit_map_id}"] = not st.session_state.get(
                            f"kg_show_edit_state_json_{edit_map_id}",
                            False,
                        )
                with state_col3:
                    if st.button("↩️ Deshacer cambios no guardados", key=f"kg_discard_unsaved_{edit_map_id}"):
                        reset_graph_state = deepcopy(edit_doc.get("graph_state", {}))
                        st.session_state["knowledge_graph_edit_graph_state"] = reset_graph_state
                        st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                            edit_doc.get("sync_settings")
                        )
                        reset_form_state = _kg_edit_form_state_from_doc(edit_map_id_text, edit_doc, reset_graph_state)
                        st.session_state[form_state_key] = reset_form_state
                        _queue_kg_edit_widget_update(edit_map_id_text, reset_form_state)
                        st.session_state["knowledge_graph_edit_dirty"] = False
                        st.session_state.pop("knowledge_graph_remove_pending", None)
                        st.session_state["knowledge_graph_render_version"] = (
                            st.session_state.get("knowledge_graph_render_version", 0) + 1
                        )
                        st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                        st.rerun()

                if st.session_state.get(f"kg_show_edit_state_json_{edit_map_id}"):
                    st.code(json.dumps(graph_state, ensure_ascii=False, indent=2, default=str), language="json")

                widget_keys = _apply_kg_edit_widget_updates_before_creation(
                    edit_map_id_text,
                    form_state,
                    graph_state,
                )
                source_widget_key = widget_keys["sources"]
                concept_type_widget_key = widget_keys["concept_types"]
                relation_type_widget_key = widget_keys["relation_types"]
                max_depth_widget_key = widget_keys["max_depth"]
                map_relation_type_options = merge_ordered_values(
                    relation_type_options,
                    filters.get("relation_types", []),
                    form_state.get("relation_types", []),
                )

                with st.form("kg_update_map_form"):
                    updated_name = st.text_input(
                        "Nombre del mapa",
                        key=widget_keys["name"],
                    )
                    updated_description = st.text_area(
                        "Descripción",
                        height=80,
                        key=widget_keys["description"],
                    )
                    updated_tags = st.text_input(
                        "Tags (separados por coma)",
                        key=widget_keys["tags"],
                    )
                    edit_col1, edit_col2 = st.columns(2)
                    with edit_col1:
                        updated_sources = st.multiselect(
                            "Fuentes",
                            map_source_options,
                            key=source_widget_key,
                        )
                        updated_types = st.multiselect(
                            "Tipos de concepto",
                            map_concept_type_options,
                            key=concept_type_widget_key,
                        )
                    with edit_col2:
                        updated_relations = st.multiselect(
                            "Tipos de relación",
                            map_relation_type_options,
                            key=relation_type_widget_key,
                        )
                        updated_max_depth = st.slider(
                            "Max depth",
                            1,
                            5,
                            key=max_depth_widget_key,
                        )
                    st.info(
                        "Guardar mapa usa el estado server-side del editor. "
                        "Para guardar posiciones o física cambiadas dentro del grafo, copia el estado JSON desde el panel "
                        "del grafo, pégalo aquí y activa la casilla."
                    )
                    use_pasted_state_json = st.checkbox(
                        "Guardar con el JSON visual pegado abajo",
                        key=widget_keys["use_pasted_state_json"],
                    )
                    updated_state_json = st.text_area(
                        "Estado JSON actual del grafo",
                        height=180,
                        key=widget_keys["graph_state_json"],
                        placeholder=(
                            "Pega aquí el JSON copiado desde 📋 Copiar estado JSON. "
                            "Sólo se usará si activas la casilla anterior."
                        ),
                    )
                    update_map = st.form_submit_button("💾 Guardar mapa")

                if update_map:
                    if not map_state_ready:
                        st.error("Recarga el mapa desde la base activa antes de guardarlo.")
                    elif not updated_name.strip():
                        st.error("El nombre del mapa es obligatorio.")
                    else:
                        try:
                            current_filter_payload = {
                                "sources": list(filters.get("sources") or []),
                                "relation_types": list(filters.get("relation_types") or []),
                                "concept_types": list(filters.get("concept_types") or []),
                                "max_depth": min(5, max(1, int(filters.get("max_depth", 3) or 3))),
                            }
                            base_graph_state = (
                                _parse_knowledge_graph_state_json(updated_state_json)
                                if use_pasted_state_json and updated_state_json.strip()
                                else graph_state
                            )
                            baseline_sources = merge_ordered_values(
                                current_filter_payload["sources"],
                                infer_sources_from_graph_state(base_graph_state),
                            )
                            baseline_types = merge_ordered_values(
                                current_filter_payload["concept_types"],
                                infer_concept_types_from_graph_state(base_graph_state),
                            )
                            source_filter_changed = set(updated_sources or []) != set(baseline_sources)
                            concept_type_filter_changed = set(updated_types or []) != set(baseline_types)
                            filter_changed = (
                                source_filter_changed
                                or concept_type_filter_changed
                                or list(updated_relations or []) != current_filter_payload["relation_types"]
                                or updated_max_depth != current_filter_payload["max_depth"]
                            )
                            if filter_changed:
                                new_graph_state = _build_knowledge_graph_state_from_filters(
                                    db,
                                    updated_sources,
                                    updated_relations,
                                    updated_types,
                                    previous_state=base_graph_state,
                                )
                                new_graph_state = merge_preserved_graph_items(new_graph_state, base_graph_state)
                            else:
                                new_graph_state = base_graph_state
                            inferred_sources = infer_sources_from_graph_state(new_graph_state)
                            inferred_types = infer_concept_types_from_graph_state(new_graph_state)
                            updated_filter_payload = {
                                "sources": merge_ordered_values(updated_sources, inferred_sources),
                                "relation_types": list(updated_relations or []),
                                "concept_types": merge_ordered_values(updated_types, inferred_types),
                                "max_depth": updated_max_depth,
                            }
                            primary_source_values = primary_sources(edit_doc)
                            primary_map_source = (
                                primary_source_values[0]
                                if primary_source_values
                                else (updated_filter_payload["sources"][0] if updated_filter_payload["sources"] else "")
                            )
                            integrity_issues = graph_state_integrity_issues(new_graph_state)
                            if integrity_issues:
                                st.error("Se detectaron inconsistencias antes de guardar; no se guardó el mapa.")
                                st.warning("\n".join(f"- {issue}" for issue in integrity_issues[:8]))
                                st.info("Usa Reparar nodos incompletos, elimina los nodos inválidos o pega un JSON reparado.")
                                st.stop()
                            result = maps_col.update_one(
                                _knowledge_graph_map_id_query(edit_map_id),
                                {
                                    "$set": {
                                        "name": updated_name.strip(),
                                        "description": updated_description.strip(),
                                        "tags": [tag.strip() for tag in updated_tags.split(",") if tag.strip()],
                                        "filters": updated_filter_payload,
                                        "primary_map_source": primary_map_source,
                                        "map_sources": updated_filter_payload["sources"],
                                        "graph_state": new_graph_state,
                                        "sync_settings": default_sync_settings(
                                            st.session_state.get(
                                                "knowledge_graph_edit_sync_settings",
                                                edit_doc.get("sync_settings"),
                                            )
                                        ),
                                        "map_uid": edit_doc.get("map_uid") or str(uuid4()),
                                        "updated_at": naive_utc_now(),
                                    }
                                },
                            )
                            saved_nodes, saved_edges = _knowledge_graph_state_counts(new_graph_state)
                            _kg_debug(
                                "Saving edit map",
                                map_id=edit_map_id_text,
                                nodes=saved_nodes,
                                edges=saved_edges,
                                filter_changed=filter_changed,
                                using_pasted_json=bool(use_pasted_state_json and updated_state_json.strip()),
                            )
                            saved_form_state = {
                                "name": updated_name.strip(),
                                "description": updated_description.strip(),
                                "tags": updated_tags,
                                "sources": updated_filter_payload["sources"],
                                "concept_types": updated_filter_payload["concept_types"],
                                "relation_types": updated_filter_payload["relation_types"],
                                "max_depth": updated_filter_payload["max_depth"],
                                "use_pasted_state_json": False,
                                "graph_state_json": "",
                            }
                            if not result.acknowledged:
                                st.error("MongoDB no confirmó la actualización del mapa.")
                            elif result.matched_count == 0:
                                st.error("No se encontró el mapa que se intentaba actualizar.")
                            elif result.modified_count == 0:
                                st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                                st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                                    st.session_state.get(
                                        "knowledge_graph_edit_sync_settings",
                                        edit_doc.get("sync_settings"),
                                    )
                                )
                                st.session_state[form_state_key] = saved_form_state
                                _queue_kg_edit_widget_update(edit_map_id_text, saved_form_state)
                                st.session_state["knowledge_graph_edit_dirty"] = False
                                st.info("No hubo cambios nuevos que guardar.")
                            else:
                                st.session_state["knowledge_graph_edit_graph_state"] = new_graph_state
                                st.session_state["knowledge_graph_edit_sync_settings"] = default_sync_settings(
                                    st.session_state.get(
                                        "knowledge_graph_edit_sync_settings",
                                        edit_doc.get("sync_settings"),
                                    )
                                )
                                st.session_state[form_state_key] = saved_form_state
                                _queue_kg_edit_widget_update(edit_map_id_text, saved_form_state)
                                st.session_state["knowledge_graph_edit_dirty"] = False
                                st.session_state["knowledge_graph_active_map_id"] = edit_map_id
                                st.session_state["knowledge_graph_active_mode"] = "edit"
                                st.session_state["knowledge_graph_section_request"] = "✏️ Editar mapa"
                                st.session_state["knowledge_graph_message"] = (
                                    "success",
                                    "Mapa actualizado correctamente.",
                                )
                                st.rerun()
                        except json.JSONDecodeError as exc:
                            st.error(f"No se pudo leer el JSON del estado: {exc}")
                        except Exception as exc:
                            st.error(f"No se pudo actualizar el mapa: {exc}")

    elif kg_section == "📤 Exportar / importar":
        st.subheader("📤 Exportar / importar")
        st.info(
            "El estado visual real vive en JavaScript. Usa 📋 Copiar estado JSON dentro del grafo "
            "para traer el estado actual a Streamlit y guardarlo o importarlo."
        )
        if all_maps:
            export_options = {_knowledge_graph_map_label(doc): str(doc["_id"]) for doc in all_maps}
            export_label = st.selectbox("Mapa para exportar", list(export_options), key="kg_export_selected_map")
            export_doc = _find_knowledge_graph_map(maps_col, export_options[export_label])
            if export_doc:
                export_state = export_doc.get("graph_state", {})
                export_sources = infer_sources_from_graph_state(export_state)
                export_types = infer_concept_types_from_graph_state(export_state)
                if export_sources:
                    st.caption(f"Fuentes inferidas del estado exportado: {', '.join(export_sources)}")
                if export_types:
                    st.caption(f"Tipos inferidos del estado exportado: {', '.join(export_types)}")
                st.download_button(
                    "📥 Descargar JSON guardado",
                    data=json.dumps(export_state, ensure_ascii=False, indent=2, default=str),
                    file_name=f"{export_doc.get('name', 'knowledge_graph_map')}.json",
                    mime="application/json",
                    key=f"kg_export_json_{export_doc['_id']}",
                )
                html_content = _render_knowledge_graph_map_html(export_state, f"export_{export_doc['_id']}")
                st.download_button(
                    "📥 Descargar HTML restaurado",
                    data=html_content,
                    file_name=f"{export_doc.get('name', 'knowledge_graph_map')}.html",
                    mime="text/html",
                    key=f"kg_export_html_{export_doc['_id']}",
                )
        else:
            st.info("No hay mapas guardados para exportar.")

        with st.form("kg_import_state_form"):
            st.markdown("**Importar estado JSON como mapa nuevo**")
            import_name = st.text_input("Nombre del mapa importado", key="kg_import_name")
            import_description = st.text_area("Descripción", height=80, key="kg_import_description")
            import_tags = st.text_input("Tags (separados por coma)", key="kg_import_tags")
            import_state_json = st.text_area("Estado JSON", height=180, key="kg_import_state_json")
            import_map = st.form_submit_button("📥 Importar estado JSON")

        if import_map:
            if not import_name.strip():
                st.error("El nombre del mapa es obligatorio.")
            else:
                try:
                    graph_state = _parse_knowledge_graph_state_json(import_state_json)
                    integrity_issues = graph_state_integrity_issues(graph_state)
                    if integrity_issues:
                        st.error("Se detectaron inconsistencias antes de importar el mapa.")
                        st.warning("\n".join(f"- {issue}" for issue in integrity_issues[:8]))
                        st.stop()
                    inferred_sources = infer_sources_from_graph_state(graph_state)
                    inferred_types = infer_concept_types_from_graph_state(graph_state)
                    primary_map_source = inferred_sources[0] if inferred_sources else ""
                    now = naive_utc_now()
                    result = maps_col.insert_one(
                        {
                            "name": import_name.strip(),
                            "description": import_description.strip(),
                            "created_at": now,
                            "updated_at": now,
                            "filters": {
                                "sources": inferred_sources,
                                "relation_types": [],
                                "concept_types": inferred_types,
                                "max_depth": 3,
                            },
                            "primary_map_source": primary_map_source,
                            "map_sources": inferred_sources,
                            "graph_state": graph_state,
                            "tags": [tag.strip() for tag in import_tags.split(",") if tag.strip()],
                            "source": "interactive_knowledge_graph",
                            "map_uid": str(uuid4()),
                            "sync_settings": default_sync_settings(),
                        }
                    )
                    if result.acknowledged:
                        st.success("Mapa importado correctamente.")
                    else:
                        st.error("MongoDB no confirmó la importación.")
                except json.JSONDecodeError as exc:
                    st.error(f"No se pudo leer el JSON del estado: {exc}")
                except Exception as exc:
                    st.error(f"No se pudo importar el mapa: {exc}")

# Document Builder page

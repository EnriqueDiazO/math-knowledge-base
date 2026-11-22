"""Home; extracted without import-time rendering."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from editor.ui.theme import THEME_TOKENS
from editor.ui.theme import apply_chart_theme


def render(context):
    """Render only the selected page using its explicit application context."""
    active_theme = context.active_theme
    current_database_label = context.current_database_label
    db = context.db
    st.title("MathMongo")
    st.caption("Un cuaderno académico para organizar conceptos, fuentes y lecturas.")

    if db is None:
        st.error("No hay una conexión a la base. Selecciona una conexión en la barra lateral.")
        st.stop()

    # Show current database info
    st.caption(f"Base activa: {current_database_label}")

    # Statistics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        concept_count = db.concepts.count_documents({})
        st.metric("Conceptos", concept_count)

    with col2:
        relation_count = db.relations.count_documents({})
        st.metric("Relaciones", relation_count)

    with col3:
        sources = db.concepts.distinct("source")
        st.metric("Fuentes", len(sources))

    with col4:
        categories = db.concepts.distinct("categorias")
        st.metric("Categorías", len(categories))

    st.markdown("---")

    # Recent concepts
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Conceptos recientes")
        recent_concepts = list(db.concepts.find().sort("fecha_creacion", -1).limit(2))

        if recent_concepts:
            for concept in recent_concepts:
                with st.container(border=True):
                    st.markdown(f"**{concept.get('titulo', concept['id'])}**")
                    st.caption(
                        f"{concept.get('tipo', '—')} · {concept.get('source', '—')} · "
                        f"{concept.get('fecha_creacion', 'sin fecha')}"
                    )
                    concept_categories = ", ".join(concept.get("categorias", []))
                    st.write(concept_categories or "Sin categorías")
        else:
            st.info("Aún no hay conceptos. Puedes añadir el primero desde la navegación.")

    with col2:
        st.subheader("Panorama")

        # --- MVP: filter Quick Stats by Source (All vs selected) ---
        # Behavior:
        # - If "All sources" is enabled, charts use the full dataset.
        # - If disabled, user must select at least one source and charts are filtered.
        try:
            all_sources = st.toggle("All sources", value=True, key="qs_all_sources")
        except Exception:
            # Streamlit versions without st.toggle
            all_sources = st.checkbox("All sources", value=True, key="qs_all_sources")

        # Load available sources (sanitized)
        try:
            available_sources = db.concepts.distinct("source")
            available_sources = sorted(
                [s for s in available_sources if isinstance(s, str) and s.strip()],
                key=lambda x: x.lower(),
            )
        except Exception:
            available_sources = []

        selected_sources = []
        if not all_sources:
            selected_sources = st.multiselect(
                "Sources (min 1)",
                options=available_sources,
                default=available_sources[:1] if available_sources else [],
                key="qs_selected_sources",
            )
            if not selected_sources:
                st.warning("Select at least one source to filter Quick Stats.")

        # Build optional MongoDB match stage
        match_stage = None
        if (not all_sources) and selected_sources:
            match_stage = {"source": {"$in": selected_sources}}

        # Concept types distribution
        types_pipeline = []
        if match_stage:
            types_pipeline.append({"$match": match_stage})
        types_pipeline += [
            {"$group": {"_id": "$tipo", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]

        type_data = list(db.concepts.aggregate(types_pipeline))
        if type_data:
            df_types = pd.DataFrame(type_data)
            try:
                import plotly.graph_objects as go
            except Exception:
                st.bar_chart(df_types.set_index("_id")["count"])
            else:
                type_counts = df_types.set_index("_id")["count"]
                type_figure = go.Figure(
                    go.Bar(
                        x=type_counts.index.tolist(),
                        y=type_counts.tolist(),
                        marker_color=THEME_TOKENS[active_theme]["primary"],
                    )
                )
                apply_chart_theme(type_figure, active_theme)
                type_figure.update_layout(
                    xaxis_title="Tipo de concepto",
                    yaxis_title="Cantidad",
                    margin=dict(l=10, r=10, t=24, b=10),
                )
                st.plotly_chart(type_figure, width="stretch", key="dashboard_type_distribution")
        else:
            if match_stage:
                st.info("No data for the selected source filter.")

        # Top categories
        category_pipeline = []
        if match_stage:
            category_pipeline.append({"$match": match_stage})
        category_pipeline += [
            {"$unwind": "$categorias"},
            {"$group": {"_id": "$categorias", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]

        top_categories = list(db.concepts.aggregate(category_pipeline))
        if top_categories:
            st.write("**Top Categories:**")
            for cat in top_categories:
                st.write(f"• {cat['_id']}: {cat['count']}")

            # --- MVP: Relaciones (Sankey) por Source y Tipo ---
            # Flujo: Source (origen) -> Tipo de relacion -> Source (destino)
            # Util para ver conectividad entre fuentes y distribucion de tipos.
            with st.expander("Flujo de relaciones (Sankey)", expanded=False):
                st.caption(
                    "Resume relaciones como flujo Fuente → tipo → Fuente. "
                    "Si desactivaste todas las fuentes, el gráfico usa ese filtro."
                    )

                try:
                    import plotly.graph_objects as go
                except Exception:
                    st.warning("Plotly no esta disponible. Instala con: pip install plotly")
                else:
                    rels = list(db.relations.find({}, {"_id": 0, "desde": 1, "hasta": 1, "tipo": 1}))

                    def _src(key):
                        if isinstance(key, str) and "@" in key:
                            return key.rsplit("@", 1)[-1].strip()
                        return None

                    triples = []
                    for r in rels:
                        fs = _src(r.get("desde"))
                        ts = _src(r.get("hasta"))
                        rt = r.get("tipo") or "relacion"
                        if not fs or not ts:
                            continue
                        if (not all_sources) and selected_sources:
                            # Mantener relaciones donde al menos uno de los endpoints pertenece al filtro
                            if (fs not in selected_sources) and (ts not in selected_sources):
                                continue
                        triples.append((fs, rt, ts))

                    if not triples:
                        st.info("No hay relaciones suficientes para graficar con este filtro.")
                    else:
                        from collections import Counter

                        c_st = Counter((fs, rt) for fs, rt, ts in triples)
                        _c_tt = Counter((rt, ts) for fs, rt, ts in triples)

                        node_ids = []
                        labels = []

                        def add_node(nid, label):
                            """Append a graph node only when its identifier is new."""
                            if nid not in node_ids:
                                node_ids.append(nid)
                                labels.append(label)

                        for fs, rt, ts in triples:
                            add_node(f"S:{fs}", fs)
                            add_node(f"T:{rt}", rt)
                            add_node(f"S:{ts}", ts)

                        idx = {nid: i for i, nid in enumerate(node_ids)}

                        sources = []
                        targets = []
                        values = []

                        for (fs, rt), v in c_st.items():
                            sources.append(idx[f"S:{fs}"])
                            targets.append(idx[f"T:{rt}"])
                            values.append(v)

                        #for (rt, ts), v in c_tt.items():
                        #    sources.append(idx[f"T:{rt}"])
                        #    targets.append(idx[f"S:{ts}"])
                        #    values.append(v)

                        fig = go.Figure(
                            data=[
                                go.Sankey(
                                    node=dict(label=labels, pad=12, thickness=12),
                                    link=dict(source=sources, target=targets, value=values),
                                )
                            ]
                        )
                        apply_chart_theme(fig, active_theme)
                        fig.update_layout(
                            height=600,
                            margin=dict(l=10, r=10, t=10, b=10),
                        )
                        st.plotly_chart(fig, width='stretch')

            # --- MVP: Relaciones (Sankey) a nivel de conceptos ---
            # Flujo: Concepto (desde) -> Tipo de relacion -> Concepto (hasta)
            # Nota: usa llaves flexibles para soportar esquemas {desde/hasta/tipo} o {from/to/relation_type}.
            with st.expander("Flujo de conceptos (Sankey)", expanded=False):
                st.caption(
                    "Resume relaciones como flujo Concepto → tipo → Concepto. "
                    "Incluye límites para mantener el gráfico legible."
                )

                # Controles MVP
                c1, c2 = st.columns(2)
                with c1:
                    max_edges = st.slider(
                        "Máximo de relaciones",
                        min_value=50,
                        max_value=2000,
                        value=400,
                        step=50,
                        help="Limite de relaciones (agregadas) que se grafican",
                        key="concept_sankey_max_edges",
                    )
                with c2:
                    top_concepts = st.slider(
                        "Conceptos frecuentes",
                        min_value=10,
                        max_value=400,
                        value=60,
                        step=10,
                        help="Limite de conceptos por frecuencia (nodos)",
                        key="concept_sankey_top_concepts",
                    )

                try:
                    import plotly.graph_objects as go
                except Exception:
                    st.warning("Plotly no esta disponible. Instala con: pip install plotly")
                else:
                    from collections import Counter

                    def _pick(d: dict, *keys):
                        for k in keys:
                            v = d.get(k)
                            if v is not None and v != "":
                                return v
                        return None

                    def _parse_endpoint(v):
                        # Soporta:
                        # - string "id@source"
                        # - dict {id: '...', source: '...'} (o llaves equivalentes)
                        if isinstance(v, str):
                            if "@" in v:
                                a, b = v.split("@", 1)
                                a = (a or "").strip()
                                b = (b or "").strip()
                                if a and b:
                                    return f"{a}@{b}"
                            return None
                        if isinstance(v, dict):
                            cid = _pick(v, "id", "concept_id", "from_id", "to_id")
                            csrc = _pick(v, "source", "concept_source", "from_source", "to_source")
                            if isinstance(cid, str) and isinstance(csrc, str) and cid.strip() and csrc.strip():
                                return f"{cid.strip()}@{csrc.strip()}"
                        return None

                    def _src_from_key(k: str) -> str | None:
                        if isinstance(k, str) and "@" in k:
                            return k.rsplit("@", 1)[-1].strip()
                        return None

                    # Cargar relaciones (proyeccion amplia para compatibilidad)
                    try:
                        rels = list(
                            db.relations.find(
                                {},
                                {
                                    "_id": 0,
                                    "desde": 1,
                                    "hasta": 1,
                                    "tipo": 1,
                                    "from": 1,
                                    "to": 1,
                                    "relation_type": 1,
                                    "type": 1,
                                },
                            )
                        )
                    except Exception as e:
                        st.error(f"❌ Error cargando relaciones: {e}")
                        rels = []

                    triples = []
                    for r in rels:
                        a = _pick(r, "desde", "from")
                        b = _pick(r, "hasta", "to")
                        rt = _pick(r, "tipo", "relation_type", "type") or "relacion"

                        a_key = _parse_endpoint(a)
                        b_key = _parse_endpoint(b)
                        if not a_key or not b_key:
                            continue

                        # Respeta filtro por source del Dashboard (Quick Stats)
                        if (not all_sources) and selected_sources:
                            sa = _src_from_key(a_key)
                            sb = _src_from_key(b_key)
                            if (sa not in selected_sources) and (sb not in selected_sources):
                                continue

                        triples.append((a_key, str(rt), b_key))

                    if not triples:
                        st.info("No hay relaciones suficientes para graficar a nivel de conceptos con este filtro.")
                    else:
                        # -----------------------------
                        # Split por clases de relación
                        # -----------------------------
                        available_types = sorted({rt for _a, rt, _b in triples}, key=lambda x: str(x).lower())

                        def _render_concept_sankey(triples_in, selected_types, key_suffix: str):
                            # Filtrar por tipo
                            if selected_types:
                                triples_t = [(a, rt, b) for (a, rt, b) in triples_in if rt in set(selected_types)]
                            else:
                                triples_t = []

                            if not triples_t:
                                st.info("No hay relaciones para los tipos seleccionados (con el filtro actual).")
                                return

                            # Top conceptos por frecuencia (nodos)
                            freq = Counter()
                            for a_key, _rt, b_key in triples_t:
                                freq[a_key] += 1
                                freq[b_key] += 1

                            top_nodes = {k for k, _ in freq.most_common(int(top_concepts))}
                            triples_f = [(a, rt, b) for (a, rt, b) in triples_t if a in top_nodes and b in top_nodes]

                            if not triples_f:
                                st.info("No hay relaciones despues de aplicar el limite de top_concepts.")
                                return

                            # Agregar edges identicos y limitar por max_edges
                            edge_counts = Counter(triples_f)
                            top_edges = edge_counts.most_common(int(max_edges))

                            # Labels: mostrar TITULOS en lugar de IDs
                            # - Intenta usar concept.titulo / concept.title / concept.name
                            # - Si no hay titulo, cae a id
                            # - Si el titulo colisiona en multiples sources, desambigua con " — <source>"
                            def _split_key(k: str):
                                if not isinstance(k, str) or "@" not in k:
                                    return None, None
                                cid, csrc = k.split("@", 1)
                                cid = (cid or "").strip()
                                csrc = (csrc or "").strip()
                                if not cid or not csrc:
                                    return None, None
                                return cid, csrc

                            # Cache: key "id@source" -> title (solo para nodos usados)
                            concept_title_by_key = {}
                            try:
                                or_conditions = []
                                for k in top_nodes:
                                    cid, csrc = _split_key(k)
                                    if cid and csrc:
                                        or_conditions.append({"id": cid, "source": csrc})

                                if or_conditions:
                                    for doc in db.concepts.find(
                                        {"$or": or_conditions},
                                        {"_id": 0, "id": 1, "source": 1, "titulo": 1, "title": 1, "name": 1},
                                    ):
                                        _id = (doc.get("id") or "").strip()
                                        _src = (doc.get("source") or "").strip()
                                        if not _id or not _src:
                                            continue
                                        key = f"{_id}@{_src}"
                                        title = (doc.get("titulo") or doc.get("title") or doc.get("name") or "").strip()
                                        if title:
                                            concept_title_by_key[key] = title
                            except Exception:
                                concept_title_by_key = {}

                            # Detectar colisiones de titulo
                            title_counts = Counter()
                            for k in top_nodes:
                                cid, csrc = _split_key(k)
                                if not cid or not csrc:
                                    continue
                                key = f"{cid}@{csrc}"
                                t = concept_title_by_key.get(key) or cid
                                title_counts[t] += 1

                            def _concept_label(k: str) -> str:
                                cid, csrc = _split_key(k)
                                if not cid or not csrc:
                                    return str(k)
                                key = f"{cid}@{csrc}"
                                t = (concept_title_by_key.get(key) or cid).strip()
                                if title_counts.get(t, 0) > 1:
                                    return f"{t} — {csrc}"
                                return t

                            # Construir nodos y enlaces para Sankey: C -> T -> C
                            node_ids = []
                            labels = []

                            def add_node(nid: str, label: str):
                                if nid not in node_ids:
                                    node_ids.append(nid)
                                    labels.append(label)

                            for (a_key, rt, b_key), _v in top_edges:
                                add_node(f"C:{a_key}", _concept_label(a_key))
                                add_node(f"T:{rt}", rt)
                                add_node(f"C:{b_key}", _concept_label(b_key))

                            idx = {nid: i for i, nid in enumerate(node_ids)}

                            sources = []
                            targets = []
                            values = []

                            # Agregar dos capas de links: (C->T) y (T->C)
                            c_ct = Counter()
                            c_tc = Counter()
                            for (a_key, rt, b_key), v in top_edges:
                                c_ct[(a_key, rt)] += v
                                c_tc[(rt, b_key)] += v

                            for (a_key, rt), v in c_ct.items():
                                sources.append(idx[f"C:{a_key}"])
                                targets.append(idx[f"T:{rt}"])
                                values.append(v)

                            for (rt, b_key), v in c_tc.items():
                                sources.append(idx[f"T:{rt}"])
                                targets.append(idx[f"C:{b_key}"])
                                values.append(v)

                            fig = go.Figure(
                                data=[
                                    go.Sankey(
                                        node=dict(label=labels, pad=12, thickness=12),
                                        link=dict(source=sources, target=targets, value=values),
                                    )
                                ]
                            )
                            apply_chart_theme(fig, active_theme)
                            fig.update_layout(
                                height=650,
                                margin=dict(l=10, r=10, t=10, b=10),
                            )
                            st.plotly_chart(fig, width='stretch', key=f"concept_sankey_{key_suffix}")

                        tab_dep, tab_log = st.tabs(["🧠 Dependencies", "⚖️ Logical / Critical"])

                        with tab_dep:
                            default_dep = [t for t in ["requiere_concepto", "deriva_de"] if t in available_types]
                            sel_dep = st.multiselect(
                                "Relation types (Dependencies)",
                                options=available_types,
                                default=default_dep if default_dep else available_types[: min(3, len(available_types))],
                                help="Tipos de relación enfocados en prerequisitos y derivación.",
                                key="concept_sankey_types_dependencies",
                            )
                            _render_concept_sankey(triples, sel_dep, "dep")

                        with tab_log:
                            default_log = [t for t in ["equivalente", "implica", "contradice", "contrasta_con", "contra_ejemplo"] if t in available_types]
                            sel_log = st.multiselect(
                                "Relation types (Logical/Critical)",
                                options=available_types,
                                default=default_log if default_log else available_types[: min(5, len(available_types))],
                                help="Tipos de relación lógicos o críticos (equivalencias, implicaciones, contradicciones, etc.).",
                                key="concept_sankey_types_logical",
                                )
                            _render_concept_sankey(triples, sel_log, "log")
            # --- end MVP: concept-level sankey ---

# Add Concept page

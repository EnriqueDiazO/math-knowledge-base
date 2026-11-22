"""Relations; extracted without import-time rendering."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from editor.helpers.tipo_relacion import TipoRelacion
from editor.ui.theme import THEME_TOKENS
from editor.ui.theme import apply_chart_theme
from visualizations.grafoconocimiento import GrafoConocimiento


def render(context):
    """Render only the selected page using its explicit application context."""
    active_theme = context.active_theme
    current_database_label = context.current_database_label
    db = context.db
    st.title("🔗 Manage Concept Relations")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Managing relations in: **{current_database_label}**")

    # Import interactive graph manager
    from editor.interactive_graph import InteractiveGraphManager
    _graph_manager = InteractiveGraphManager(db)

    # Tab navigation for relations
    tab1, tab2, tab3 = st.tabs(["➕ Add New Relation", "✏️ Edit Relations", "📊 View Relations"])

    with tab1:
        st.subheader("➕ Add New Relation")
        # Inicializa IDs y fuentes para que siempre existan
        desde_id, desde_source = "", ""
        hasta_id, hasta_source = "", ""

        # Smart concept selection
        st.write("**Select Concepts:**")

        col_from, col_to = st.columns(2)

        with col_from:
            st.write("**From Concept:**")
            # Filter concepts for "from" selection
            desde_source_filter = st.selectbox("From Source", ["All"] + list(db.concepts.distinct("source")), key="desde_source_filter")
            desde_type_filter = st.selectbox("From Type", ["All"] + list(db.concepts.distinct("tipo")), key="desde_type_filter")

            # Build query for "from" concepts
            desde_query = {}
            if desde_source_filter != "All":
                desde_query["source"] = desde_source_filter
            if desde_type_filter != "All":
                desde_query["tipo"] = desde_type_filter

            desde_concepts = list(db.concepts.find(desde_query).sort("fecha_creacion", -1))

            if desde_concepts:
                desde_options = []
                desde_map = {}
                for concept in desde_concepts:
                    display_name = f"{concept.get('titulo', concept['id'])} ({concept['tipo']} - {concept['source']})"
                    desde_options.append(display_name)
                    desde_map[display_name] = concept

                selected_desde = st.selectbox("Choose From Concept", desde_options, key="desde_select")
                if selected_desde:
                    desde_concept = desde_map[selected_desde]
                    desde_id = desde_concept['id']
                    desde_source = desde_concept['source']
                    st.info(f"Selected: {desde_id}@{desde_source}")
            else:
                st.warning("No concepts found with selected filters")
                desde_id = ""
                desde_source = ""

        with col_to:
            st.write("**To Concept:**")
            # Filter concepts for "to" selection
            hasta_source_filter = st.selectbox("To Source", ["All"] + list(db.concepts.distinct("source")), key="hasta_source_filter")
            hasta_type_filter = st.selectbox("To Type", ["All"] + list(db.concepts.distinct("tipo")), key="hasta_type_filter")

            # Build query for "to" concepts
            hasta_query = {}
            if hasta_source_filter != "All":
                hasta_query["source"] = hasta_source_filter
            if hasta_type_filter != "All":
                hasta_query["tipo"] = hasta_type_filter

            hasta_concepts = list(db.concepts.find(hasta_query).sort("fecha_creacion", -1))

            if hasta_concepts:
                hasta_options = []
                hasta_map = {}
                for concept in hasta_concepts:
                    display_name = f"{concept.get('titulo', concept['id'])} ({concept['tipo']} - {concept['source']})"
                    hasta_options.append(display_name)
                    hasta_map[display_name] = concept

                selected_hasta = st.selectbox("Choose To Concept", hasta_options, key="hasta_select")
                if selected_hasta:
                    hasta_concept = hasta_map[selected_hasta]
                    hasta_id = hasta_concept['id']
                    hasta_source = hasta_concept['source']
                    st.info(f"Selected: {hasta_id}@{hasta_source}")
            else:
                st.warning("No concepts found with selected filters")
                hasta_id = ""
                hasta_source = ""

        # Relation details
        st.subheader("🔗 Relation Details")

        col_rel_type, col_rel_desc = st.columns(2)
        with col_rel_type:
            tipo_relacion = st.selectbox("Relation Type", [t.value for t in TipoRelacion], key="new_rel_type")
        with col_rel_desc:
            descripcion = st.text_area("Description (Optional)", placeholder="Describe the relationship...", key="new_rel_desc")

        # -----------------------
        # 🎓 Relation Tutor (educational guidance)
        # -----------------------
        if desde_id and hasta_id:
            st.markdown("---")
            st.subheader("🎓 Relation Tutor")
            # Fetch full concept docs once (for cards + heuristics)
            _from_doc = db.concepts.find_one({"id": desde_id, "source": desde_source}) or {}
            _to_doc = db.concepts.find_one({"id": hasta_id, "source": hasta_source}) or {}

            def _concept_label(doc: dict, fallback_id: str) -> str:
                return doc.get("titulo") or doc.get("title") or fallback_id

            def _node_key(cid: str, csource: str) -> str:
                return f"{cid}@{csource}"
            # A/B cards + relation notation
            a_col, mid_col, b_col = st.columns([5, 2, 5])
            with a_col:
                st.markdown("**A (From)**")
                with st.container(border=True):
                    st.markdown(f"**{_concept_label(_from_doc, desde_id)}**")
                    st.caption(f"Tipo: {_from_doc.get('tipo', '—')} · Fuente: {desde_source}")
                    st.caption(f"ID: {desde_id}")
            with mid_col:
                st.markdown("**Relation**")
                rel_symbol = {
                    "equivalente": "≡",
                    "implica": "⇒",
                    "requiere_concepto": "↗",
                    "deriva_de": "↩",
                    "inspirado_en": "≈",
                    "contrasta_con": "≠",
                    "contradice": "⊥",
                    "contra_ejemplo": "→/",
                }.get(tipo_relacion, "→")
                with st.container(border=True):
                    st.subheader(rel_symbol)
                    st.caption(tipo_relacion)
            with b_col:
                st.markdown("**B (To)**")
                with st.container(border=True):
                    st.markdown(f"**{_concept_label(_to_doc, hasta_id)}**")
                    st.caption(f"Tipo: {_to_doc.get('tipo', '—')} · Fuente: {hasta_source}")
                    st.caption(f"ID: {hasta_id}")

            # Heuristic warnings
            warnings = []
            a_key = _node_key(desde_id, desde_source)
            b_key = _node_key(hasta_id, hasta_source)

            _direct = db.relations.find_one({"desde": a_key, "hasta": b_key, "tipo": tipo_relacion})
            _inverse = db.relations.find_one({"desde": b_key, "hasta": a_key, "tipo": tipo_relacion})

            if _direct:
                warnings.append(f"Direct relation exists: {_direct['desde']} --[{_direct['tipo']}]--> {_direct['hasta']}")
            if _inverse:
                warnings.append(f"Inverse relation exists: {_inverse['desde']} --[{_inverse['tipo']}]--> {_inverse['hasta']}")

            if tipo_relacion == "equivalente":
                if _from_doc.get("tipo") and _to_doc.get("tipo") and _from_doc.get("tipo") != _to_doc.get("tipo"):
                    warnings.append("Equivalence across different concept types is often non-trivial. Document the bridge explicitly.")
                if desde_source != hasta_source:
                    warnings.append("Equivalence across different sources can indicate duplicates or parallel formulations. Add a short justification or reference.")

            if tipo_relacion == "implica" and (_from_doc.get("tipo") == "nota" and _to_doc.get("tipo") in {"teorema", "proposicion", "corolario", "lema"}):
                warnings.append("A 'nota' implying a formal statement can be valid, but usually requires explicit assumptions. Capture them in the proof sketch.")

            for w in warnings:
                st.warning(f"⚠️ {w}")

            # Checklist
            st.markdown("### ✅ Verification Checklist")

            relation_checklist = {
                "equivalente": {
                    "definition": "Two concepts are equivalent when they define the same object/statement under compatible hypotheses, typically via A⇒B and B⇒A.",
            "essential": [
                "Same mathematical object/statement (up to notation or framework).",
                "Hypotheses and scope are compatible (no hidden assumptions).",
                "You can justify both directions (A⇒B and B⇒A), or cite a reliable reference.",
            ],
            "optional": [
                "You can map notation/terminology from A to B explicitly.",
                "You can explain why equivalence is pedagogically useful (deduplication or alternate viewpoint).",
            ],},
            "implica": {
            "definition": "A implies B when, assuming A (and its hypotheses), B follows without adding extra assumptions beyond those stated.",
            "essential": [
                "You can state the implication A ⇒ B clearly.",
                "No extra hypotheses are required beyond what is already in A (or you list them explicitly).",
                "You can provide at least a short proof idea or reference.",
            ],
            "optional": [
                "You can provide a counterexample showing why the reverse does not hold (if applicable).",
            ],},
            "requiere_concepto": {
            "definition": "A requires B when understanding/using A depends on knowing B (B appears in the definition/proof/notation).",
            "essential": [
                "B appears in the definition/proof/notation of A, or is a prerequisite to parse it.",
                "You can point to where B is used (section, line, or short description).",
            ],
            "optional": [
                "You can suggest an order of study (B before A) in one sentence.",
            ],},

            "deriva_de": {
                "definition": "A derives from B when A is obtained as a specialization, reformulation, or construction based on B.",
                "essential": ["You can explain how A is obtained from B (special case, restriction, construction, or reformulation).",],
            "optional": ["You can specify what changes from B to A (hypotheses, notation, scope, or level of abstraction).",],},

            "inspirado_en": {
        "definition": "A is inspired by B when B motivated the ideas or approach of A, without strict logical dependence.",
        "essential": [
            "You can identify the idea, technique, or intuition from B that influenced A.",
        ],
        "optional": [
            "You can explain why the relation is not 'implica' or 'equivalente'.",
        ],
    },

    "contrasta_con": {
        "definition": "A contrasts with B when they address similar topics but differ in assumptions, scope, or conclusions.",
        "essential": [
            "You can state at least one concrete conceptual difference between A and B.",
        ],
        "optional": [
            "You can explain when one is preferable over the other.",
        ],
    },

    "contradice": {
    "definition": "A contradicts B when both cannot be true simultaneously under the same framework and compatible hypotheses.",
    "essential": [
        "You can state the conflicting claims precisely (what A asserts vs what B asserts).",
        "You can specify the framework/definitions under which the contradiction holds (same meanings for terms).",
        "You can point to the exact assumption(s) where the conflict arises, or cite a reliable reference.",
    ],
    "optional": [
        "You can clarify whether the contradiction is absolute or only under certain hypotheses.",
        "You can suggest how to resolve it (add a missing hypothesis, refine a definition, or restrict scope).",
    ],},
    "contra_ejemplo": {
    "definition": "A is a counterexample to B when A shows that a general claim in B fails, typically by satisfying the stated hypotheses while violating the conclusion (or revealing a missing hypothesis).",
    "essential": [
        "You can state the claim in B that is being refuted (hypotheses ⇒ conclusion).",
        "A satisfies the stated hypotheses (or you clearly explain which hypothesis is missing/incorrect in B).",
        "A violates the conclusion, and you can explain why (brief argument or reference).",
    ],
    "optional": [
        "You can indicate the minimal additional hypothesis needed to make B true.",
        "You can provide a short intuition of why the claim fails and what it teaches.",
    ], },
    }
            spec = relation_checklist.get(tipo_relacion, None)
            if spec:
                st.info(spec["definition"])
                tutor_key = f"rel_tutor::{a_key}::{b_key}::{tipo_relacion}"

                def _tri_state(label: str, key: str):
                    return st.selectbox(label, ["✅ Sí", "🤔 No sé", "❌ No"], index=1, key=key)

                essential_answers = []
                for idx, crit in enumerate(spec["essential"]):
                    essential_answers.append(_tri_state(f"Essential {idx+1}: {crit}", f"{tutor_key}::ess::{idx}"))

                with st.expander("Optional checks", expanded=False):
                    for idx, crit in enumerate(spec.get("optional", [])):
                        _tri_state(f"Optional {idx+1}: {crit}", f"{tutor_key}::opt::{idx}")

                # Semáforo
                if any(a == "❌ No" for a in essential_answers):
                    st.error("🔴 Quality: one or more essential criteria are not satisfied.")
                elif all(a == "✅ Sí" for a in essential_answers):
                    st.success("🟢 Quality: essential criteria satisfied.")
                else:
                    st.warning("🟡 Quality: some essential criteria are unknown. Consider adding evidence.")
                # Plantilla de prueba
                if tipo_relacion in {"equivalente", "implica"}:
                    st.markdown("### ✍️ Proof / Justification Sketch")
                    if tipo_relacion == "equivalente":
                        st.text_area("A ⇒ B (idea / key steps)", key=f"{tutor_key}::proof::a_to_b", height=90)
                        st.text_area("B ⇒ A (idea / key steps)", key=f"{tutor_key}::proof::b_to_a", height=90)
                    else:
                        st.text_area("A ⇒ B (idea / key steps)", key=f"{tutor_key}::proof::a_to_b", height=110)
                        st.text_area("Extra hypotheses (if any)", key=f"{tutor_key}::proof::extra_hyp", height=70)
                # Strict mode
                strict_mode = st.checkbox("Strict mode (block saving unless essential criteria are ✅ Sí)", value=False, key=f"{tutor_key}::strict")
                st.session_state["__rel_can_save__"] = (not strict_mode) or all(a == "✅ Sí" for a in essential_answers)
            else:
                st.caption("No tutor checklist is defined yet for this relation type. You can still add it, but consider documenting it in the description.")
                st.session_state["__rel_can_save__"] = True
        else:
            st.session_state["__rel_can_save__"] = False
        # Visual preview of selected concepts
        if desde_id and hasta_id:
            st.markdown("---")
            st.subheader("👁️ Visual Preview")

            preview_concepts = []
            preview_relations = []

            a_key = f"{desde_id}@{desde_source}"
            b_key = f"{hasta_id}@{hasta_source}"

            # Add both selected concepts
            desde_concept = db.concepts.find_one({"id": desde_id, "source": desde_source})
            hasta_concept = db.concepts.find_one({"id": hasta_id, "source": hasta_source})

            if desde_concept:
                preview_concepts.append(desde_concept)
            if hasta_concept:
                preview_concepts.append(hasta_concept)

            # Mini Camino B: 1-hop context
            col_ctx1, col_ctx2 = st.columns([2, 3])
            with col_ctx1:
                include_context = st.checkbox(
                    "Include context",
                    value=True,
                    key="rel_preview_context")
            with col_ctx2:
                _preview_depth = st.slider(
                    "Preview depth (hops)",
                    min_value=1,
                    max_value=3,
                    value=1,
                    step=1,
                    disabled=not include_context,
                    help="1 = neighbors, 2 = neighbors of neighbors, 3 = deeper context",
                    key="rel_preview_depth"
                    )

            if include_context:
                ctx_relations = list(db.relations.find({
                    "$or": [
                         {"desde": a_key}, {"hasta": a_key},
                          {"desde": b_key}, {"hasta": b_key},
                    ]
                }))
                ctx_nodes = {a_key, b_key}
                for rctx in ctx_relations:
                    if rctx.get("desde"):
                        ctx_nodes.add(rctx["desde"])
                    if rctx.get("hasta"):
                        ctx_nodes.add(rctx["hasta"])
                existing_nodes = {(c.get("id"), c.get("source")) for c in preview_concepts}
                for nk in sorted(ctx_nodes):
                    try:
                        cid, csrc = nk.split("@", 1)
                    except ValueError:
                        continue
                    if (cid, csrc) in existing_nodes:
                        continue
                    doc = db.concepts.find_one({"id": cid, "source": csrc})
                    if doc:
                        preview_concepts.append(doc)
                        existing_nodes.add((cid, csrc))

                existing_triplets = {(r.get("desde"), r.get("hasta"), r.get("tipo")) for r in preview_relations}
                for rctx in ctx_relations:
                    trip = (rctx.get("desde"), rctx.get("hasta"), rctx.get("tipo"))
                    if trip not in existing_triplets:
                        preview_relations.append(rctx)
                        existing_triplets.add(trip)
            # Existing relations between A and B
            existing_relations = db.relations.find({
                "$or": [
                    {"desde": a_key, "hasta": b_key},
                    {"desde": b_key, "hasta": a_key}
                ]
            })
            for rel in existing_relations:
                preview_relations.append(rel)

            # Add new relation preview
            preview_relations.append({
                "desde": a_key,
                "hasta": b_key,
                "tipo": tipo_relacion,
                "descripcion": descripcion
            })

            # Generate mini preview graph
            if preview_concepts:
                try:
                    with st.spinner("🔄 Generating preview..."):
                        # Debug: Show the data being used for preview

                        with st.expander("🔍 Debug: Preview Data", expanded=False):
                            # 1) Toggle de display
                            display_mode = st.radio(
                                "Show nodes/relations as:",
                                ["Titles", "IDs", "Both"],
                                horizontal=True,
                                key="debug_display_mode"
                            )

                            # 2) Index para resolver id@source -> titulo
                            def _node_key(cid: str, csrc: str) -> str:
                                return f"{cid}@{csrc}"

                            def _title(doc: dict) -> str:
                                return doc.get("titulo") or doc.get("title") or doc.get("id", "—")

                            concept_by_key = {}
                            for c in preview_concepts:
                                cid = c.get("id")
                                csrc = c.get("source")
                                if cid and csrc:
                                    concept_by_key[_node_key(cid, csrc)] = c

                            def _fmt_node(node_key: str) -> str:
                                doc = concept_by_key.get(node_key, {})
                                t = _title(doc)
                                if display_mode == "Titles":
                                    return t
                                if display_mode == "IDs":
                                    return node_key
                                # Both
                                return f"{t}  ({node_key})"

                            # 3) Tabla amigable de conceptos
                            st.markdown("**Concepts**")
                            concept_rows = []
                            for c in preview_concepts:
                                node_key = _node_key(c.get("id",""), c.get("source",""))
                                concept_rows.append({
                                    "Title": _title(c),
                                    "Type": c.get("tipo", "—"),
                                    "Source": c.get("source", "—"),
                                    "ID": c.get("id", "—"),
                                    "NodeKey": node_key,})
                            st.dataframe(concept_rows, width='stretch', hide_index=True)
                            # 4) Tabla amigable de relaciones
                            st.markdown("**Relations**")
                            rel_rows = []
                            for r in preview_relations:
                                desde = r.get("desde","")
                                hasta = r.get("hasta","")
                                rel_rows.append({
                                    "From": _fmt_node(desde) if "@" in desde else desde,
                                    "Type": r.get("tipo","—"),
                                    "To": _fmt_node(hasta) if "@" in hasta else hasta,
                                    "FromKey": desde,
                                    "ToKey": hasta,
                                    })
                            st.dataframe(rel_rows, width='stretch', hide_index=True)
                            # 5) Export JSON (preview completo)
                            import json
                            export_payload = {
                                "concepts": preview_concepts,
                                "relations": preview_relations,
                                 "meta": {
                                     "from": {"id": desde_id, "source": desde_source},
                                     "to": {"id": hasta_id, "source": hasta_source},
                                     "new_relation": {"tipo": tipo_relacion, "descripcion": descripcion},
                                     "include_1hop_context": st.session_state.get("rel_preview_context", False),
                                 }
                             }
                            st.download_button(
                                "⬇️ Export preview as JSON",
                                data=json.dumps(
                                    export_payload,
                                    ensure_ascii=False,
                                    indent=2,
                                    default=str
                                ),
                                file_name="relation_preview.json",
                                mime="application/json",
                                key="download_preview_json")

                        def _sanitize_mongo(doc: dict) -> dict:
                            out = dict(doc)
                            if "_id" in out:
                                out["_id"] = str(out["_id"])
                            return out

                        concepts_clean = [_sanitize_mongo(c) for c in preview_concepts if c]
                        relations_clean = [_sanitize_mongo(r) for r in preview_relations if r]

                        grafo = GrafoConocimiento(concepts_clean, relations_clean)
                        grafo.construir_grafo(
                            tipos_relacion=list({r.get("tipo") for r in relations_clean if r.get("tipo")}),
                            tipos_concepto=list({c.get("tipo") for c in concepts_clean if c.get("tipo")}),)

                        html = grafo.exportar_html(salida=None)
                        st.download_button(
                            label="⬇️ Download map (HTML)",
                            data=html.encode("utf-8"),
                            file_name="relation_preview_map.html",
                            mime="text/html",
                            key="download_preview_map_html",
                        )
                        components.html(html, height=650, scrolling=False)

                except Exception as e:
                    st.error(f"❌ Could not generate preview: {e}")
                    st.exception(e)
        ###################################################################################################
        # Add relation button
        can_save = st.session_state.get("__rel_can_save__", True)
        if not can_save:
            st.info("ℹ️ Strict mode is enabled and essential criteria are not all satisfied. Complete the checklist to enable saving.")
        if st.button("🔗 Add Relation", type="primary", key="add_rel_btn", disabled=not can_save):
            if desde_id and desde_source and hasta_id and hasta_source:
                if desde_id == hasta_id and desde_source == hasta_source:
                    st.error("❌ Cannot create relation from a concept to itself.")
                else:
                    try:
                        relation = db.add_relation(
                            desde_id=desde_id,
                            desde_source=desde_source,
                            hasta_id=hasta_id,
                            hasta_source=hasta_source,
                            tipo=tipo_relacion,
                            descripcion=descripcion
                        )
                        if relation:
                            st.success("✅ Relation added successfully!")
                            st.balloons()

                            # Auto-refresh the interactive graph if it exists
                            if hasattr(st.session_state, 'current_graph_file'):
                                st.info("🔄 The interactive graph will be updated on next refresh.")

                        else:
                            st.error("❌ Failed to add relation. Check if both concepts exist.")
                    except Exception as e:
                        st.error(f"❌ Error adding relation: {e}")
            else:
                st.error("❌ Please select both concepts.")

        # Live Graph Viewer

    with tab2:
        st.subheader("✏️ Edit Relations")

        # Filter relations for editing
        col1, col2 = st.columns(2)
        with col1:
            edit_filter_source = st.selectbox("Filter by Source", ["All"] + list(db.concepts.distinct("source")), key="edit_source_filter")
        with col2:
            edit_filter_type = st.selectbox("Filter by Type", ["All"] + [t.value for t in TipoRelacion], key="edit_type_filter")

        # Build query for relations to edit
        edit_query = {}
        if edit_filter_source != "All":
            edit_query["$or"] = [
                {"desde": {"$regex": f"@{edit_filter_source}$"}},
                {"hasta": {"$regex": f"@{edit_filter_source}$"}}
            ]
        if edit_filter_type != "All":
            edit_query["tipo"] = edit_filter_type

        edit_relations = list(db.relations.find(edit_query))

        if edit_relations:
            st.write(f"**Found {len(edit_relations)} relations to edit:**")

            for i, rel in enumerate(edit_relations):
                with st.expander(f"Edit: {rel['desde']} --[{rel['tipo']}]--> {rel['hasta']}", expanded=False):
                    st.write(f"**Current Relation:** {rel['desde']} --[{rel['tipo']}]--> {rel['hasta']}")

                    # Get concept details for display
                    desde_parts = rel['desde'].split('@')
                    hasta_parts = rel['hasta'].split('@')

                    desde_concept = db.concepts.find_one({"id": desde_parts[0], "source": desde_parts[1]})
                    hasta_concept = db.concepts.find_one({"id": hasta_parts[0], "source": hasta_parts[1]})

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**From Concept:**")
                        if desde_concept:
                            st.write(f"• **Title:** {desde_concept.get('titulo', desde_parts[0])}")
                            st.write(f"• **Type:** {desde_concept['tipo']}")
                            st.write(f"• **Source:** {desde_parts[1]}")
                        else:
                            st.write(f"• **ID:** {desde_parts[0]}")
                            st.write(f"• **Source:** {desde_parts[1]}")
                            st.warning("⚠️ Concept not found in database")

                    with col2:
                        st.write("**To Concept:**")
                        if hasta_concept:
                            st.write(f"• **Title:** {hasta_concept.get('titulo', hasta_parts[0])}")
                            st.write(f"• **Type:** {hasta_concept['tipo']}")
                            st.write(f"• **Source:** {hasta_parts[1]}")
                        else:
                            st.write(f"• **ID:** {hasta_parts[0]}")
                            st.write(f"• **Source:** {hasta_parts[1]}")
                            st.warning("⚠️ Concept not found in database")

                    st.markdown("---")

                    # Edit relation details
                    st.write("**Edit Relation Details:**")

                    col1, col2 = st.columns(2)
                    with col1:
                        new_tipo = st.selectbox(
                            "Relation Type",
                            [t.value for t in TipoRelacion],
                            index=[t.value for t in TipoRelacion].index(rel['tipo']),
                            key=f"edit_type_{i}")
                    with col2:
                        new_desc = st.text_area(
                            "Description",
                            value=rel.get('descripcion', ''),
                            key=f"edit_desc_{i}")

                    # Action buttons
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        if st.button("💾 Update Relation", key=f"update_rel_{i}"):
                            try:
                                # Update the relation
                                db.relations.update_one(
                                    {"_id": rel["_id"]},
                                    {
                                        "$set": {
                                            "tipo": new_tipo,
                                            "descripcion": new_desc
                                        }
                                    }
                                )
                                st.success("✅ Relation updated successfully!")
                            except Exception as e:
                                st.error(f"❌ Error updating relation: {e}")

                    with col2:
                        if st.button("🔄 Reset", key=f"reset_rel_{i}"):
                            st.rerun()

                    with col3:
                        delete_btn_key = f"delete_btn_{i}"
                        confirm_state_key = f"confirm_delete_state_{i}"
                        confirm_btn_key = f"confirm_delete_btn_{i}"



                        if confirm_state_key not in st.session_state:
                            st.session_state[confirm_state_key] = False

                        if st.button("🗑️ Delete", key=delete_btn_key):
                            st.session_state[confirm_state_key] = True

                        if st.session_state[confirm_state_key]:
                            st.warning("⚠️ This action is irreversible. Confirm deletion.")
                            if st.button("❌ Confirm Delete", key=confirm_btn_key):
                                try:
                                    db.relations.delete_one({"_id": rel["_id"]})
                                    st.success("✅ Relation deleted successfully!")
                                    st.session_state.pop(confirm_state_key, None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error deleting relation: {e}")
        else:
            st.info("No relations found with the selected filters.")

    with tab3:
        st.subheader("📊 View Relations")

        # Filter relations for viewing
        col1, col2 = st.columns(2)
        with col1:
            view_filter_source = st.selectbox("Filter by Source", ["All"] + list(db.concepts.distinct("source")), key="view_source_filter")
        with col2:
            view_filter_type = st.selectbox("Filter by Type", ["All"] + [t.value for t in TipoRelacion], key="view_type_filter")

        # Build query
        view_query = {}
        if view_filter_source != "All":
            view_query["$or"] = [
                {"desde": {"$regex": f"@{view_filter_source}$"}},
                {"hasta": {"$regex": f"@{view_filter_source}$"}}
            ]
        if view_filter_type != "All":
            view_query["tipo"] = view_filter_type

        view_relations = list(db.relations.find(view_query))

        if view_relations:
            st.write(f"**Found {len(view_relations)} relations:**")

            # Create a summary table
            relation_data = []
            for rel in view_relations:
                desde_parts = rel['desde'].split('@')
                hasta_parts = rel['hasta'].split('@')

                desde_concept = db.concepts.find_one({"id": desde_parts[0], "source": desde_parts[1]})
                hasta_concept = db.concepts.find_one({"id": hasta_parts[0], "source": hasta_parts[1]})

                relation_data.append({
                    "From": desde_concept.get('titulo', desde_parts[0]) if desde_concept else desde_parts[0],
                    "From Type": desde_concept['tipo'] if desde_concept else "Unknown",
                    "From Source": desde_parts[1],
                    "Relation": rel['tipo'],
                    "To": hasta_concept.get('titulo', hasta_parts[0]) if hasta_concept else hasta_parts[0],
                    "To Type": hasta_concept['tipo'] if hasta_concept else "Unknown",
                    "To Source": hasta_parts[1],
                    "Description": rel.get('descripcion', '')
                })

            df = pd.DataFrame(relation_data)
            st.dataframe(df, width='stretch')

            # Statistics
            st.subheader("📈 Relation Statistics")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Total Relations", len(view_relations))

            with col2:
                relation_types = [rel['tipo'] for rel in view_relations]
                unique_types = len(set(relation_types))
                st.metric("Unique Types", unique_types)

            with col3:
                sources_involved = set()
                for rel in view_relations:
                    desde_parts = rel['desde'].split('@')
                    hasta_parts = rel['hasta'].split('@')
                    sources_involved.add(desde_parts[1])
                    sources_involved.add(hasta_parts[1])
                st.metric("Sources Involved", len(sources_involved))

            # Type distribution
            if relation_types:
                type_counts = pd.Series(relation_types).value_counts()
                st.subheader("📊 Relation Type Distribution")
                try:
                    import plotly.graph_objects as go
                except Exception:
                    st.bar_chart(type_counts)
                else:
                    relation_figure = go.Figure(
                        go.Bar(
                            x=type_counts.index.tolist(),
                            y=type_counts.tolist(),
                            marker_color=THEME_TOKENS[active_theme]["primary"],
                        )
                    )
                    apply_chart_theme(relation_figure, active_theme)
                    relation_figure.update_layout(
                        xaxis_title="Tipo de relación",
                        yaxis_title="Cantidad",
                        margin=dict(l=10, r=10, t=24, b=10),
                    )
                    st.plotly_chart(
                        relation_figure,
                        width="stretch",
                        key="relation_type_distribution",
                    )
        else:
            st.info("No relations found with the selected filters.")

# Knowledge Graph page

from editor.db.concept_repository import concept_exists
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import bibtexparser
import pandas as pd
import streamlit as st
from streamlit_ace import st_ace
from bson import ObjectId

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

import streamlit.components.v1 as components
from pdf_export import generar_y_abrir_pdf_desde_formulario

from exporters_latex.exportadorlatex import ExportadorLatex
from exporters_quarto.quarto_exporter import QuartoBookExporter

# Render preview graph using the same renderer as "Knowledge Graph"
from mathdatabase.mathmongo import MathMongo
from schemas.schemas import ConceptoBase
from editor.helpers.tipo_presentacion import TipoPresentacion
from editor.helpers.tipo_referencia import TipoReferencia
from editor.helpers.tipo_relacion import TipoRelacion
from editor.helpers.tipo_titulo import TipoTitulo
from visualizations.grafoconocimiento import GrafoConocimiento

# OJO: mapea a tu Enum TipoReferencia: libro, articulo, tesis, tesina, pagina_web, miscelanea
_TIPO_MAP = {
    "book": "libro",
    "article": "articulo",
    "phdthesis": "tesis",
    "mastersthesis": "tesis",
    "inproceedings": "articulo",   # o "miscelanea" si prefieres
    "incollection": "miscelanea",  # capítulo en libro → miscelanea (si no tienes "capitulo" como tipo)
    "proceedings": "miscelanea",
    "techreport": "miscelanea",
    "misc": "miscelanea",
    "unpublished": "miscelanea",
    "online": "pagina_web",
    "www": "pagina_web",
}

def _bib_to_referencia(entry: dict) -> dict:
    get = entry.get

    # Autor/es
    autores = []
    if get("author"):
        for a in get("author").split(" and "):
            autores.append(a.strip())
    autores_str = "; ".join(autores) if autores else None

    # TipoReferencia compatible con tu Enum
    tipo_ref = _TIPO_MAP.get(get("ENTRYTYPE", "").lower(), "miscelanea")

    # Fuente (journal/booktitle/publisher/title como fallback)
    fuente = get("journal") or get("booktitle") or get("publisher") or get("title")

    # Año
    try:
        anio = int(get("year")) if get("year") and get("year").isdigit() else None
    except Exception:
        anio = None

    # Varios campos
    paginas = get("pages").replace("--", "-").strip() if get("pages") else None
    edicion = get("edition")
    tomo = get("volume")
    capitulo = get("chapter")
    seccion = get("number") or get("issue")
    editorial = get("publisher")
    doi = get("doi")
    url = get("url")
    issbn = get("isbn") or get("issn")  # OJO: en tu modelo el campo se llama "issbn"

    return {
        "autor": autores_str,
        "fuente": fuente,
        "anio": anio,
        "tomo": tomo,
        "edicion": edicion,
        "paginas": paginas,
        "capitulo": capitulo,
        "seccion": seccion,
        "editorial": editorial,
        "doi": doi,
        "url": url,
        "issbn": issbn,
    }

def _parse_bibtex(file_bytes: bytes) -> list[dict]:
    if not bibtexparser:
        raise RuntimeError("Falta bibtexparser. Instala con: pip install bibtexparser==1.4.0")
    db = bibtexparser.loads(file_bytes.decode("utf-8", errors="ignore"))
    return db.entries or []
# ---------------------------------------------------------

def _normalize_ref_dict(ref: dict) -> dict:
    """
    Normaliza la referencia para soportar:
    - esquema nuevo: tipo_referencia, issbn
    - esquema viejo: tipo, isbn
    - citekey opcional
    """
    if not isinstance(ref, dict):
        return {}

    # soporta ambos nombres de campo
    tipo = ref.get("tipo_referencia") or ref.get("tipo")
    issbn = ref.get("issbn") or ref.get("isbn")  # tu modelo usa issbn

    out = dict(ref)
    if tipo is not None:
        out["tipo_referencia"] = tipo
    if issbn is not None:
        out["issbn"] = issbn

    return out


def load_last_reference_by_source(db, source: str) -> dict | None:
    """
    Busca el último concepto (fecha_creacion DESC) del mismo source
    que tenga un campo 'referencia' utilizable.
    """
    if not source or not isinstance(source, str) or not source.strip():
        return None

    query = {
        "source": source,
        "referencia": {"$exists": True, "$ne": None},
    }
    projection = {"referencia": 1, "id": 1, "titulo": 1, "fecha_creacion": 1, "_id": 0}

    doc = db.concepts.find_one(query, projection=projection, sort=[("fecha_creacion", -1)])
    if not doc:
        return None

    ref = _normalize_ref_dict(doc.get("referencia") or {})
    # “utilizable” = al menos autor o fuente o citekey (ajústalo si quieres)
    if not (ref.get("autor") or ref.get("fuente") or ref.get("citekey")):
        return None

    # (opcional) Adjunta metadatos para debug
    ref["__from_concept_id"] = doc.get("id")
    ref["__from_concept_title"] = doc.get("titulo")
    ref["__from_concept_date"] = doc.get("fecha_creacion")

    return ref



# Page configuration
st.set_page_config(
    page_title="Math Knowledge Base",
    page_icon="🧮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    :root {
        --bg: #0B0F19;
        --panel: #111827;
        --panel-2: #0F172A;
        --border: #243244;
        --text: #E5E7EB;
        --muted: #9CA3AF;
        --accent: #60A5FA;
        --good: #22C55E;
        --bad: #EF4444;
    }

    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: var(--text);
        text-align: center;
        margin-bottom: 2rem;
    }

    /* Cards */
    .metric-card {
        background-color: var(--panel);
        color: var(--text);
        padding: 1rem;
        border-radius: 0.75rem;
        border-left: 4px solid var(--accent);
        border: 1px solid var(--border);
    }

    .concept-card {
        background-color: var(--panel);
        color: var(--text);
        padding: 1.5rem;
        border-radius: 0.75rem;
        border: 1px solid var(--border);
        margin-bottom: 1rem;
        box-shadow: none;
    }


    /* MVP: make Recent Concepts a fixed-height scroll panel */
    .recent-concepts-panel {
        max-height: 520px;
        overflow-y: auto;
        padding-right: 0.5rem;
    }

    .latex-preview {
        background-color: #0B1220;
        color: var(--text);
        padding: 1rem;
        border-radius: 0.75rem;
        border: 1px solid var(--border);
        font-family: monospace;
    }

    .db-connection-card {
        background-color: #0B1220;
        color: var(--text);
        padding: 1rem;
        border-radius: 0.75rem;
        border: 1px solid var(--border);
        margin-bottom: 1rem;
    }

    .db-status-connected {
        color: var(--good);
        font-weight: bold;
    }

    .db-status-disconnected {
        color: var(--bad);
        font-weight: bold;
    }

    /* Buttons */
    .stButton > button {
        width: 100%;
        border-radius: 0.75rem;
        background: var(--panel);
        color: var(--text);
        border: 1px solid var(--border);
    }

    /* Sidebar fix (you were forcing light) */
    [data-testid="stSidebar"] {
        background-color: var(--panel-2);
    }
</style>
""", unsafe_allow_html=True)

# Database connection management
class DatabaseManager:
    def __init__(self):
        self.connections = {}
        self.current_connection = None

    def add_connection(self, name, mongo_uri, db_name):
        """Add a new database connection."""
        try:
            connection = MathMongo(mongo_uri, db_name)
            self.connections[name] = {
                'connection': connection,
                'uri': mongo_uri,
                'db_name': db_name,
                'status': 'connected'
            }
            return True
        except Exception as e:
            st.error(f"Failed to connect to {name}: {e}")
            return False

    def get_connection(self, name):
        """Get a specific database connection."""
        return self.connections.get(name, {}).get('connection')

    def list_connections(self):
        """List all available connections."""
        return list(self.connections.keys())

    def get_current_connection(self):
        """Get the currently active connection."""
        return self.current_connection

    def set_current_connection(self, name):
        """Set the current active connection."""
        if name in self.connections:
            self.current_connection = self.connections[name]['connection']
            return True
        return False

# Initialize database manager in session state
if 'db_manager' not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

    # Add default connections
    st.session_state.db_manager.add_connection(
        "MathMongo (Current)",
        "mongodb://localhost:27017",
        "mathmongo"
    )

    # Add MathV0 connection
    st.session_state.db_manager.add_connection(
        "MathV0",
        "mongodb://localhost:27017",
        "MathV0"
    )

    # Set current connection
    st.session_state.db_manager.set_current_connection("MathMongo (Current)")

# Database connection sidebar
st.sidebar.title("🧮 Math Knowledge Base")
st.sidebar.markdown("---")

# Database connection section
st.sidebar.subheader("🗄️ Database Connection")

# Show current connection
current_db = None
for name, conn_info in st.session_state.db_manager.connections.items():
    if st.session_state.db_manager.get_current_connection() == conn_info['connection']:
        current_db = name
        break

if current_db:
    st.sidebar.markdown(f"""
    <div class="db-connection-card">
        <strong>Current Database:</strong><br>
        {current_db}<br>
        <span class="db-status-connected">✅ Connected</span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
    <div class="db-connection-card">
        <strong>Current Database:</strong><br>
        <span class="db-status-disconnected">❌ Not Connected</span>
    </div>
    """, unsafe_allow_html=True)

# Database switcher
available_dbs = st.session_state.db_manager.list_connections()
if available_dbs:
    selected_db = st.sidebar.selectbox(
        "Switch Database",
        available_dbs,
        index=available_dbs.index(current_db) if current_db in available_dbs else 0
    )

    if selected_db != current_db:
        if st.session_state.db_manager.set_current_connection(selected_db):
            st.sidebar.success(f"✅ Switched to {selected_db}")
            st.rerun()

# Add new database connection
with st.sidebar.expander("➕ Add New Database", expanded=False):
    new_db_name = st.text_input("Database Name", placeholder="e.g., MathV1, ResearchDB")
    new_db_uri = st.text_input("MongoDB URI", value="mongodb://localhost:27017")
    new_db_collection = st.text_input("Database Name", placeholder="e.g., mathmongo")

    if st.button("Add Connection"):
        if new_db_name and new_db_uri and new_db_collection:
            if st.session_state.db_manager.add_connection(new_db_name, new_db_uri, new_db_collection):
                st.success(f"✅ Added {new_db_name}")
                st.rerun()
        else:
            st.error("Please fill in all fields")

# Test database connection
if st.sidebar.button("🔍 Test Connection"):
    current_conn = st.session_state.db_manager.get_current_connection()
    if current_conn:
        try:
            # Test connection by getting collection count
            concept_count = current_conn.concepts.count_documents({})
            st.sidebar.success(f"✅ Connection successful! {concept_count} concepts found.")
        except Exception as e:
            st.sidebar.error(f"❌ Connection failed: {e}")
    else:
        st.sidebar.error("❌ No active connection")

st.sidebar.markdown("---")

# Get current database connection
db = st.session_state.db_manager.get_current_connection()
def _cuaderno_is_installed(conn) -> bool:
    """Detecta si el modo cuaderno está instalado en la DB actual.

    Se considera instalado si existen las 4 colecciones base.
    """
    try:
        if conn is None:
            return False
        mongo_db = getattr(conn, "db", None)
        if mongo_db is None:
            return False
        names = set(mongo_db.list_collection_names())
        required = {"worklog_entries", "backlog_items", "weekly_reviews", "deliverables"}
        return required.issubset(names)
    except Exception:
        return False


page = st.sidebar.selectbox(
    "Navigation",
    ["🏠 Dashboard", "➕ Add Concept", "✏️ Edit Concept", "📚 Browse Concepts", "🔗 Manage Relations", "📊 Knowledge Graph", "📤 Export", "⚙️ Settings"]
)

# Experimental navigation (optional)
_exp_options = ["(none)"]
if _cuaderno_is_installed(db):
    _exp_options.append("🧪 Cuaderno")

exp_page = st.sidebar.selectbox("Experimental", _exp_options, index=0)
if exp_page == "🧪 Cuaderno":
    page = "🧪 Cuaderno"


# Dashboard page
if page == "🏠 Dashboard":
    st.markdown('<h1 class="main-header">Math Knowledge Base</h1>', unsafe_allow_html=True)

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    # Show current database info
    st.info(f"📊 Currently connected to: **{current_db}**")

    # Statistics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        concept_count = db.concepts.count_documents({})
        st.metric("📚 Total Concepts", concept_count)

    with col2:
        relation_count = db.relations.count_documents({})
        st.metric("🔗 Total Relations", relation_count)

    with col3:
        sources = db.concepts.distinct("source")
        st.metric("📁 Sources", len(sources))

    with col4:
        categories = db.concepts.distinct("categorias")
        st.metric("🏷️ Categories", len(categories))

    st.markdown("---")

    # Recent concepts
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("📝 Recent Concepts")
        recent_concepts = list(db.concepts.find().sort("fecha_creacion", -1).limit(2))

        if recent_concepts:
            st.markdown('<div class=\"recent-concepts-panel\">', unsafe_allow_html=True)
            for concept in recent_concepts:
                with st.container():
                    st.markdown(f"""
                    <div class="concept-card">
                        <h4>{concept.get('titulo', concept['id'])}</h4>
                        <p><strong>Type:</strong> {concept['tipo']} | <strong>Source:</strong> {concept['source']}</p>
                        <p><strong>Categories:</strong> {', '.join(concept.get('categorias', []))}</p>
                        <p><strong>Created:</strong> {concept.get('fecha_creacion', 'Unknown')}</p>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("No concepts found. Add your first concept!")

    with col2:
        st.subheader("📊 Quick Stats")

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
            st.bar_chart(df_types.set_index("_id")["count"])
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
            with st.expander("🔗 Relations Flow (Sankey)", expanded=False):
                st.caption(
                    "MVP: resume relaciones como flujo Source -> Tipo -> Source. "
                    "Si desactivaste 'All sources' arriba, el grafico se filtra por esas sources."
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
                        c_tt = Counter((rt, ts) for fs, rt, ts in triples)

                        node_ids = []
                        labels = []

                        def add_node(nid, label):
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
                        fig.update_layout(height=600, margin=dict(l=10, r=10, t=10, b=10))
                        st.plotly_chart(fig, width='stretch')

            # --- MVP: Relaciones (Sankey) a nivel de conceptos ---
            # Flujo: Concepto (desde) -> Tipo de relacion -> Concepto (hasta)
            # Nota: usa llaves flexibles para soportar esquemas {desde/hasta/tipo} o {from/to/relation_type}.
            with st.expander("Concepts Flow (Sankey) [MVP]", expanded=False):
                st.caption(
                    "MVP: resume relaciones como flujo Concept -> Tipo -> Concept. "
                    "Incluye limites para evitar sobrecargar el grafico."
                )

                # Controles MVP
                c1, c2 = st.columns(2)
                with c1:
                    max_edges = st.slider(
                        "max_edges",
                        min_value=50,
                        max_value=2000,
                        value=400,
                        step=50,
                        help="Limite de relaciones (agregadas) que se grafican",
                        key="concept_sankey_max_edges",
                    )
                with c2:
                    top_concepts = st.slider(
                        "top_concepts",
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
                            fig.update_layout(height=650, margin=dict(l=10, r=10, t=10, b=10))
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
elif page == "🧪 Cuaderno":
    from cuaderno_page import render_cuaderno
    render_cuaderno(db, _cuaderno_is_installed)
elif page == "➕ Add Concept":
    st.title("➕ Add New Mathematical Concept")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Adding concept to: **{current_db}**")

    # Concept type selection
    concept_type = st.selectbox(
        "Concept Type",
        ["definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"],
        help="Select the type of mathematical concept you want to add"
    )

    # Basic information
    st.subheader("📋 Basic Information")

    col1, col2 = st.columns(2)
    with col1:
        concept_id = st.text_input("ID", placeholder="e.g., def:grupo_001", help="Unique identifier for the concept")

        try:
            existing_sources = db.concepts.distinct("source")
            existing_sources = sorted([s for s in existing_sources if isinstance(s, str) and s.strip()], key=lambda x: x.lower())
        except Exception:
            existing_sources = []

        source_choice = st.selectbox(
            "Source",
            ["(Custom...)"] + existing_sources,
            help="Pick an existing source to avoid duplicates like 'Python' vs 'python'. Choose (Custom...) to type a new one.")
        if source_choice == "(Custom...)":
            source = st.text_input("New source name", placeholder="e.g., ProGit2024")
        else:
            source = source_choice
        
        if source:
            try:
                docs = list(
                    db.concepts.find({"source": source},{"id": 1, "titulo": 1, "_id": 0}))
                    # Normaliza y ordena por id
                items = sorted(
                        [
                            {"id": d.get("id", "").strip(),
                             "titulo": (d.get("titulo") or "").strip()}
                            for d in docs
                            if isinstance(d.get("id"), str)
                        ],
                        key=lambda x: x["id"]
                )
            except Exception:
                items = []
            
            st.markdown("#### Existing IDs for this source")
            if items:
                show_n = 50
                lines = []
                for it in items[-show_n:]:
                    if it["titulo"]:
                        lines.append(f"{it['id']}  —  {it['titulo']}")
                    else:
                        lines.append(f"{it['id']}")
                text = "\n".join(lines)
                st.text_area(
        "Existing IDs (latest 10)",
        value="\n".join(lines),
        height=220,
        disabled=True,
        label_visibility="collapsed"
    )
            else:
                st.caption("No concepts yet for this source.")

    with col2:
        titulo = st.text_input("Title (Optional)", placeholder="e.g., Definition of Group")
        tipo_titulo = st.selectbox("Title Type", [t.value for t in TipoTitulo])

    # 1. Categorías base (predefinidas)
    categorias_base = [
    "Algebra", "Analysis", "Topology", "Geometry", "Number Theory",
    "Combinatorics", "Logic", "Statistics", "Calculus"]

    # 2. Categorías adicionales ya existentes en la base de datos
    categorias_db = db.concepts.distinct("categorias")
    categorias_db = [cat for cat in categorias_db if isinstance(cat, str)]

    # 3. Opcional: incluir categorías sugeridas por usuarios previos
    try:
        categorias_sugeridas = [doc["nombre"] for doc in db.categorias.find()]
    except Exception:
        categorias_sugeridas = []

    # 4. Combinar todas las categorías conocidas y eliminar duplicados
    categorias_existentes = sorted(set(categorias_base + categorias_db + categorias_sugeridas))

    # 🔒 Asegurar estado inicial
    if 'categorias_seleccionadas' not in st.session_state:
        st.session_state.categorias_seleccionadas = []

    # 5. Input para nueva categoría
    nueva_categoria = st.text_input("➕ Add New Category (Optional)", placeholder="e.g., Discrete Math")

    # 6. Agregar a lista si es nueva
    if nueva_categoria:
        nueva_categoria = nueva_categoria.strip()
        if nueva_categoria and nueva_categoria not in st.session_state.categorias_seleccionadas:
            st.session_state.categorias_seleccionadas.append(nueva_categoria)

    # ⚠️ Agregar seleccionadas a las opciones visibles
    categorias_existentes = sorted(set(categorias_base + categorias_db + categorias_sugeridas + st.session_state.categorias_seleccionadas))

    # 7. Mostrar multiselect
    st.session_state.categorias_seleccionadas = st.multiselect("Categories",
    options=categorias_existentes,
    default=st.session_state.categorias_seleccionadas,
    help="Select relevant mathematical categories")

    # 8. Resultado final para guardar
    categorias = st.session_state.categorias_seleccionadas

    # LaTeX content with helper toolbar
    st.subheader("📝 LaTeX Content")

    # LaTeX Helper Toolbar
    st.write("**🔧 LaTeX Helper Tools:**")

    # Main structures
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("📝 Definition", key="btn_def"):
            st.session_state.latex_insert = r"\begin{definition}{% add Name or leave it in blank}" + "\n" + r"% Definition content here" + "\n" + r"\end{definition}"

        if st.button("📋 Theorem", key="btn_theorem"):
            st.session_state.latex_insert = r"\begin{theorem}{% add Name or leave it in blank}" + "\n" + r"% Theorem statement here" + "\n" + r"\end{theorem}"

        if st.button("📖 Proof", key="btn_proof"):
            st.session_state.latex_insert = r"\begin{proof}" + "\n" + r"% Proof content here" + "\n" + r"\end{proof}"

        if st.button("📊 Example", key="btn_example"):
            st.session_state.latex_insert = r"\begin{example}{% add Name or leave it in blank}" + "\n" + r"% Example content here" + "\n" + r"\end{example}"

    with col2:
        if st.button("📋 Lemma", key="btn_lemma"):
            st.session_state.latex_insert = r"\begin{lemma}{% add Name or leave it in blank}" + "\n" + r"% Lemma statement here" + "\n" + r"\end{lemma}"

        if st.button("📋 Proposition", key="btn_prop"):
            st.session_state.latex_insert = r"\begin{proposition}{% add Name or leave it in blank}" + "\n" + r"% Proposition statement here" + "\n" + r"\end{proposition}"

        if st.button("📋 Corollary", key="btn_corollary"):
            st.session_state.latex_insert = r"\begin{corollary}{% add Name or leave it in blank}" + "\n" + r"% Corollary statement here" + "\n" + r"\end{corollary}"

        if st.button("📋 Remark", key="btn_remark"):
            st.session_state.latex_insert = r"\begin{remark}{% add Name or leave it in blank}" + "\n" + r"% Remark content here" + "\n" + r"\end{remark}"

    with col3:
        if st.button("🔢 Equation", key="btn_eq"):
            st.session_state.latex_insert = r"\begin{equation}" + "\n" + r"% Equation here" + "\n" + r"\end{equation}"

        if st.button("🔢 Align", key="btn_align"):
            st.session_state.latex_insert = r"\begin{align}" + "\n" + r"% Multiple equations here" + "\n" + r"\end{align}"

        if st.button("🔢 Matrix", key="btn_matrix"):
            st.session_state.latex_insert = r"\begin{pmatrix}" + "\n" + r"a & b \\" + "\n" + r"c & d" + "\n" + r"\end{pmatrix}"

        if st.button("🔢 Cases", key="btn_cases"):
            st.session_state.latex_insert = r"\begin{cases}" + "\n" + r"% Case 1 \\" + "\n" + r"% Case 2" + "\n" + r"\end{cases}"

    with col4:
        if st.button("📋 Itemize", key="btn_itemize"):
            st.session_state.latex_insert = r"\begin{itemize}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{itemize}"

        if st.button("📋 Enumerate", key="btn_enumerate"):
            st.session_state.latex_insert = r"\begin{enumerate}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{enumerate}"

        if st.button("📋 Description", key="btn_description"):
            st.session_state.latex_insert = r"\begin{description}" + "\n" + r"\item[Term 1] Description 1" + "\n" + r"\item[Term 2] Description 2" + "\n" + r"\end{description}"

        if st.button("📋 Quote", key="btn_quote"):
            st.session_state.latex_insert = r"\begin{quote}" + "\n" + r"% Quoted text here" + "\n" + r"\end{quote}"

        if st.button("🧩 Code", key="btn_code_listing"):
            st.session_state["latex_insert"] = (
                r"\begin{lstlisting}[language=ValorLanguage, caption=NombreParaCaption]" "\n"
                r"# Comentario" "\n"
                r"codigo" "\n"
                r"\end{lstlisting}"
            )
        if st.button("🌳 Dir Tree", key="btn_dir_tree"):
            st.session_state["latex_insert"] = (
                r"\dirtree{%" "\n"
                r".1 main folder." "\n"
                r".2 subfolder." "\n"
                r".3 subsubfolder." "\n"
                r".4 subsubsubfolder." "\n"
                r"}")

    # Mathematical symbols and operators
    st.write("**🔢 Mathematical Symbols:**")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("∑ Sum", key="btn_sum"):
            st.session_state.latex_insert = r"\sum_{i=1}^{n}"
        if st.button("∏ Product", key="btn_prod"):
            st.session_state.latex_insert = r"\prod_{i=1}^{n}"
        if st.button("∫ Integral", key="btn_int"):
            st.session_state.latex_insert = r"\int_{a}^{b}"
        if st.button("∂ Partial", key="btn_partial"):
            st.session_state.latex_insert = r"\partial"

    with col2:
        if st.button("∞ Infinity", key="btn_inf"):
            st.session_state.latex_insert = r"\infty"
        if st.button("→ Arrow", key="btn_arrow"):
            st.session_state.latex_insert = r"\rightarrow"
        if st.button("↔ Bidirectional", key="btn_bidir"):
            st.session_state.latex_insert = r"\leftrightarrow"
        if st.button("∈ Belongs", key="btn_in"):
            st.session_state.latex_insert = r"\in"

    with col3:
        if st.button("⊂ Subset", key="btn_subset"):
            st.session_state.latex_insert = r"\subset"
        if st.button("∪ Union", key="btn_union"):
            st.session_state.latex_insert = r"\cup"
        if st.button("∩ Intersection", key="btn_intersection"):
            st.session_state.latex_insert = r"\cap"
        if st.button("∅ Empty Set", key="btn_empty"):
            st.session_state.latex_insert = r"\emptyset"

    with col4:
        if st.button("∀ For All", key="btn_forall"):
            st.session_state.latex_insert = r"\forall"
        if st.button("∃ Exists", key="btn_exists"):
            st.session_state.latex_insert = r"\exists"
        if st.button("∴ Therefore", key="btn_therefore"):
            st.session_state.latex_insert = r"\therefore"
        if st.button("∵ Because", key="btn_because"):
            st.session_state.latex_insert = r"\because"

    # Greek letters
    st.write("**🇬🇷 Greek Letters:**")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("α Alpha", key="btn_alpha"):
            st.session_state.latex_insert = r"\alpha"
        if st.button("β Beta", key="btn_beta"):
            st.session_state.latex_insert = r"\beta"
        if st.button("γ Gamma", key="btn_gamma"):
            st.session_state.latex_insert = r"\gamma"
        if st.button("δ Delta", key="btn_delta"):
            st.session_state.latex_insert = r"\delta"

    with col2:
        if st.button("ε Epsilon", key="btn_epsilon"):
            st.session_state.latex_insert = r"\epsilon"
        if st.button("θ Theta", key="btn_theta"):
            st.session_state.latex_insert = r"\theta"
        if st.button("λ Lambda", key="btn_lambda"):
            st.session_state.latex_insert = r"\lambda"
        if st.button("μ Mu", key="btn_mu"):
            st.session_state.latex_insert = r"\mu"

    with col3:
        if st.button("π Pi", key="btn_pi"):
            st.session_state.latex_insert = r"\pi"
        if st.button("σ Sigma", key="btn_sigma"):
            st.session_state.latex_insert = r"\sigma"
        if st.button("τ Tau", key="btn_tau"):
            st.session_state.latex_insert = r"\tau"
        if st.button("φ Phi", key="btn_phi"):
            st.session_state.latex_insert = r"\phi"

    with col4:
        if st.button("χ Chi", key="btn_chi"):
            st.session_state.latex_insert = r"\chi"
        if st.button("ψ Psi", key="btn_psi"):
            st.session_state.latex_insert = r"\psi"
        if st.button("ω Omega", key="btn_omega"):
            st.session_state.latex_insert = r"\omega"
        if st.button("Γ Gamma", key="btn_Gamma"):
            st.session_state.latex_insert = r"\Gamma"

    # Initialize latex_insert in session state if not exists
    if 'latex_insert' not in st.session_state:
        st.session_state.latex_insert = ""

    # Show current insertion if any
    if st.session_state.latex_insert:
        st.info(f"**Ready to insert:** `{st.session_state.latex_insert}`")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Insert at Cursor", key="insert_btn"):
                st.session_state.insert_latex = True
        with col2:
            if st.button("❌ Clear", key="clear_insert"):
                st.session_state.latex_insert = ""
                st.session_state.insert_latex = False

    # LaTeX text area
    # -------------------------
    # LaTeX editor (state real + remount para inserciones)
    # -------------------------
    # Estado real del texto (NO es el key del widget)
    if "latex_text" not in st.session_state:
       st.session_state["latex_text"] = ""
    # Revisión para forzar re-mount del componente cuando insertas
    if "latex_editor_rev" not in st.session_state:
        st.session_state["latex_editor_rev"] = 0
    # Flags de inserción
    if "latex_insert" not in st.session_state:
        st.session_state["latex_insert"] = ""
    if "insert_latex" not in st.session_state:
        st.session_state["insert_latex"] = False


    # Handle insertion (DEBE IR ANTES del st_ace)
    if st.session_state.get("insert_latex") and st.session_state.get("latex_insert"):
        current_text = st.session_state.get("latex_text", "") or ""
        to_insert = st.session_state["latex_insert"]

        if current_text and not current_text.endswith("\n"):
            current_text += "\n"

        st.session_state["latex_text"] = current_text + to_insert + "\n"
        # limpiar flags
        st.session_state["insert_latex"] = False
        st.session_state["latex_insert"] = ""
        # IMPORTANT: fuerza re-mount para que el nuevo value se refleje
        st.session_state["latex_editor_rev"] += 1
        st.rerun()

    contenido_latex = st_ace(
        value=st.session_state["latex_text"],
        language="latex",
        theme="monokai",
        font_size=16,
        tab_size=2,
        height=800,
        wrap=True,
        show_gutter=True,
        auto_update=True,
        key=f"latex_editor_{st.session_state['latex_editor_rev']}"
    )
    # Sincronizar el contenido del editor con el estado
    st.session_state["latex_text"] = contenido_latex or ""
    # Este es el contenido que usarás para guardar en DB
    contenido_latex = st.session_state["latex_text"]
    ###----

    # Algorithm section

    st.subheader("⚙️ Algorithm Information")
    col1, col2 = st.columns(2)
    with col1:
        es_algoritmo = st.checkbox("Is this an algorithm?")
    with col2:
        if es_algoritmo:
            pasos_algoritmo = st.text_area("Algorithm Steps", placeholder="Enter algorithm steps...")

    st.subheader("📚 Reference Information")
    if st.button("📋 Cargar referencia del concepto anterior", key="load_prev_ref"):
        try:
            ref = load_last_reference_by_source(db, source)
            if not ref:
                st.warning(f"⚠️ No se encontró ninguna referencia previa para el source: {source!r}")
            else:
                # Poblar session_state (Add Concept usa claves edit_ref_*)
                st.session_state["edit_ref_tipo"] = ref.get("tipo_referencia", st.session_state.get("edit_ref_tipo", "libro"))
                st.session_state["edit_ref_autor"] = ref.get("autor", "") or ""
                st.session_state["edit_ref_fuente"] = ref.get("fuente", "") or ""
                st.session_state["edit_ref_anio"] = ref.get("anio", 2024) or 2024
                st.session_state["edit_ref_tomo"] = ref.get("tomo", "") or ""
                st.session_state["edit_ref_edicion"] = ref.get("edicion", "") or ""
                st.session_state["edit_ref_paginas"] = ref.get("paginas", "") or ""
                st.session_state["edit_ref_capitulo"] = ref.get("capitulo", "") or ""
                st.session_state["edit_ref_seccion"] = ref.get("seccion", "") or ""
                st.session_state["edit_ref_editorial"] = ref.get("editorial", "") or ""
                st.session_state["edit_ref_doi"] = ref.get("doi", "") or ""
                st.session_state["edit_ref_url"] = ref.get("url", "") or ""
                st.session_state["edit_ref_issbn"] = ref.get("issbn", "") or ""
                st.session_state["edit_ref_citekey"] = ref.get("citekey", "") or ""

                # Debug opcional (puedes quitarlo)
                with st.expander("Debug (loaded from last concept)", expanded=False):
                    st.write({
                    "from_id": ref.get("__from_concept_id"),
                    "from_title": ref.get("__from_concept_title"),
                    "from_date": ref.get("__from_concept_date"),
                })

                st.success("✅ Referencia cargada desde el último concepto de este source. Puedes editar los campos.")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Error cargando referencia previa: {e}")


    

    with st.expander("Add / Edit Reference", expanded=False):
        # --- Carga opcional de BibTeX ---
        st.write("Opcional: cargar desde un archivo BibTeX")
        bib_file_add = st.file_uploader("Cargar .bib", type=["bib"], key="bib_add")

        if bib_file_add is not None:
            try:
                bib_entries = _parse_bibtex(bib_file_add.getvalue())
                if bib_entries:
                    keys = [
                            (e.get("ID", "(sin key)"), f'{e.get("title","(sin título)")[:60]}')
                            for e in bib_entries
                        ]
                    idx = st.selectbox(
                            "Selecciona entrada",
                            list(range(len(keys))),
                            format_func=lambda i: f"{keys[i][0]} — {keys[i][1]}",
                            key="bib_choice_edit"
                        )
                    selected_bib_entry_edit = bib_entries[idx]

                    if st.button("Usar esta entrada", key="use_bib_edit"):
                        ref_dict = _bib_to_referencia(selected_bib_entry_edit)
                        st.session_state["edit_ref_tipo"] = ref_dict["tipo_referencia"]
                        st.session_state["edit_ref_autor"] = ref_dict["autor"] or ""
                        st.session_state["edit_ref_fuente"] = ref_dict["fuente"] or ""
                        st.session_state["edit_ref_anio"] = ref_dict["anio"] or 2024
                        st.session_state["edit_ref_tomo"] = ref_dict["tomo"] or ""
                        st.session_state["edit_ref_edicion"] = ref_dict["edicion"] or ""
                        st.session_state["edit_ref_paginas"] = ref_dict["paginas"] or ""
                        st.session_state["edit_ref_capitulo"] = ref_dict["capitulo"] or ""
                        st.session_state["edit_ref_seccion"] = ref_dict["seccion"] or ""
                        st.session_state["edit_ref_editorial"] = ref_dict["editorial"] or ""
                        st.session_state["edit_ref_doi"] = ref_dict["doi"] or ""
                        st.session_state["edit_ref_url"] = ref_dict["url"] or ""
                        st.session_state["edit_ref_issbn"] = ref_dict["issbn"] or ""
                        st.session_state["edit_ref_citekey"] = selected_bib_entry_edit.get("ID")
                        st.success("Campos de referencia actualizados desde BibTeX.")
                        st.rerun()  # <-- fuerza refresco de widgets
                else:
                    st.info("El archivo .bib no contiene entradas.")
            except Exception as e:
                st.error(f"No se pudo leer el .bib: {e}")

            # --- Campos editables enlazados a session_state (claves edit_ref_*) ---
        col1, col2 = st.columns(2)
        with col1:
            ref_tipo = st.selectbox(
                    "Reference Type",
                    [t.value for t in TipoReferencia],
                    key="edit_ref_tipo",
                )
            ref_autor = st.text_input("Author", key="edit_ref_autor")
            ref_fuente = st.text_input("Source/Title", key="edit_ref_fuente")
            ref_anio = st.number_input(
                    "Year",
                    min_value=1800, max_value=3000,
                    value=st.session_state.get("edit_ref_anio"),
                    key="edit_ref_anio"
                )

        with col2:
            ref_tomo = st.text_input("Volume", key="edit_ref_tomo")
            ref_edicion = st.text_input("Edition", key="edit_ref_edicion")
            ref_paginas = st.text_input("Pages", key="edit_ref_paginas")
            ref_capitulo = st.text_input("Chapter", key="edit_ref_capitulo")

        ref_seccion = st.text_input("Section", key="edit_ref_seccion")
        ref_editorial = st.text_input("Publisher", key="edit_ref_editorial")
        ref_doi = st.text_input("DOI", key="edit_ref_doi")
        ref_url = st.text_input("URL", key="edit_ref_url")
        ref_issbn = st.text_input("ISBN", key="edit_ref_issbn")

        # Citekey opcional (si lo guardas en tu modelo)
        st.text_input("Citekey (opcional)", key="edit_ref_citekey")

    # Teaching context
    st.subheader("🎓 Teaching Context")
    with st.expander("Add Teaching Context", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            nivel_contexto = st.selectbox("Context Level", [n.value for n in NivelContexto])
        with col2:
            grado_formalidad = st.selectbox("Formality Degree", [g.value for g in GradoFormalidad])

    # Technical metadata
    st.subheader("🔧 Technical Metadata")
    with st.expander("Add Technical Metadata", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            usa_notacion_formal = st.checkbox("Uses Formal Notation", value=True)
            incluye_demostracion = st.checkbox("Includes Proof")
            es_definicion_operativa = st.checkbox("Is Operational Definition")
            es_concepto_fundamental = st.checkbox("Is Fundamental Concept")

        with col2:
            requiere_conceptos_previos = st.text_area("Required Previous Concepts", placeholder="Enter concepts separated by commas")
            incluye_ejemplo = st.checkbox("Includes Example")
            es_autocontenible = st.checkbox("Is Self-Contained", value=True)

        tipo_presentacion = st.selectbox("Presentation Type", [t.value for t in TipoPresentacion])
        nivel_simbolico = st.selectbox("Symbolic Level", [n.value for n in NivelSimbolico])
        tipo_aplicacion = st.multiselect("Application Type", [t.value for t in TipoAplicacion])

    # Comment
    comentario = st.text_area("Comment (Optional)", placeholder="Additional comments or notes...")

    # Submit button
    if st.button("💾 Save Concept", type="primary"):
        if not concept_id or not source or not contenido_latex:
            st.error("❌ Please fill in all required fields: ID, Source, and LaTeX Content")
        else:
            try:
                # Build concept data
                concept_data = {
                    "id": concept_id,
                    "tipo": concept_type,
                    "titulo": titulo if titulo else None,
                    "tipo_titulo": tipo_titulo,
                    "categorias": categorias,
                    "contenido_latex": contenido_latex,
                    "es_algoritmo": es_algoritmo,
                    "pasos_algoritmo": pasos_algoritmo.split('\n') if es_algoritmo and pasos_algoritmo else None,
                    "comentario": comentario if comentario else None,
                    "source": source,
                    "fecha_creacion": datetime.now(),
                    "ultima_actualizacion": datetime.now(),
                    # NOTE: We keep concept.citekey for backward compatibility with existing exporters.
                    # The authoritative citekey should live inside concept.referencia.citekey.
                    "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                }

                # Add reference if provided
                if ref_autor or ref_fuente:
                    concept_data["referencia"] = {
                        "tipo_referencia": ref_tipo,
                        "autor": ref_autor if ref_autor else None,
                        "fuente": ref_fuente if ref_fuente else None,
                        "anio": ref_anio if ref_anio else None,
                        "tomo": ref_tomo if ref_tomo else None,
                        "edicion": ref_edicion if ref_edicion else None,
                        "paginas": ref_paginas if ref_paginas else None,
                        "capitulo": ref_capitulo if ref_capitulo else None,
                        "seccion": ref_seccion if ref_seccion else None,
                        "editorial": ref_editorial if ref_editorial else None,
                        "doi": ref_doi if ref_doi else None,
                        "url": ref_url if ref_url else None,
                        "issbn": ref_issbn if ref_issbn else None
                        ,
                        # NEW: Persist citekey at reference-level (needed for stable Quarto/BibTeX export).
                        "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }

                # Add teaching context if provided
                if nivel_contexto or grado_formalidad:
                    concept_data["contexto_docente"] = {
                        "nivel_contexto": nivel_contexto,
                        "grado_formalidad": grado_formalidad
                    }

                # Add technical metadata if provided
                if usa_notacion_formal is not None or incluye_demostracion is not None:
                    concept_data["metadatos_tecnicos"] = {
                        "usa_notacion_formal": usa_notacion_formal,
                        "incluye_demostracion": incluye_demostracion,
                        "es_definicion_operativa": es_definicion_operativa,
                        "es_concepto_fundamental": es_concepto_fundamental,
                        "requiere_conceptos_previos": [c.strip() for c in requiere_conceptos_previos.split(',')] if requiere_conceptos_previos else None,
                        "incluye_ejemplo": incluye_ejemplo,
                        "es_autocontenible": es_autocontenible,
                        "tipo_presentacion": tipo_presentacion,
                        "nivel_simbolico": nivel_simbolico,
                        "tipo_aplicacion": tipo_aplicacion if tipo_aplicacion else None
                    }

                # Create concept object
                concepto = ConceptoBase(**concept_data)

                # Save to database
                if concept_exists(db, concepto.id, source):
                    existing = db.concepts.find_one(
                        {"id": concepto.id, "source": source},
                        {"_id": 1, "id": 1, "source": 1, "titulo": 1, "fecha_creacion": 1, "ultima_actualizacion": 1}
                    )
                    st.warning("⚠️ Este concepto ya existe. Usa ✏️ Edit Concept o cambia el ID.")
                    if existing:
                        st.json(existing)
                    return
                concepto_dict = build_concept_metadata(concepto)

                insert_concept_metadata(db, concepto.id, source, concepto_dict) 

                # Save LaTeX content
                now = datetime.now()
                db.latex_documents.update_one(
                    {"id": concepto.id, "source": source},
                    {
                        "$set": {
                            "contenido_latex": contenido_latex,
                            "ultima_actualizacion": now
                        },
                        "$setOnInsert": {"fecha_creacion": now}
                    }, upsert=True
                )

                st.success(f"✅ Concept '{concept_id}' saved successfully to {current_db}!")
                st.balloons()

            except Exception as e:
                st.error(f"❌ Error saving concept: {e}")

    # PDF Generation Button
    st.markdown("---")
    st.subheader("📄 Generar PDF")

    # Check if we have the minimum required data for PDF generation
    if concept_id and source and contenido_latex:
        if st.button("📄 Generar y abrir PDF", type="secondary"):
            # Build concept data for PDF generation
            pdf_concept_data = {
                "id": concept_id,
                "tipo": concept_type,
                "titulo": titulo if titulo else concept_id,
                "categorias": categorias,
                "contenido_latex": contenido_latex,
                "source": source,
                "comentario": comentario if comentario else None
            }

            # Add reference if provided
            if ref_autor or ref_fuente:
                pdf_concept_data["referencia"] = {
                    "tipo_referencia": ref_tipo,
                    "autor": ref_autor if ref_autor else None,
                    "fuente": ref_fuente if ref_fuente else None,
                    "anio": ref_anio if ref_anio else None,
                    "tomo": ref_tomo if ref_tomo else None,
                    "edicion": ref_edicion if ref_edicion else None,
                    "paginas": ref_paginas if ref_paginas else None,
                    "capitulo": ref_capitulo if ref_capitulo else None,
                    "seccion": ref_seccion if ref_seccion else None,
                    "editorial": ref_editorial if ref_editorial else None,
                    "doi": ref_doi if ref_doi else None,
                    "url": ref_url if ref_url else None,
                    "issbn": ref_issbn if ref_issbn else None
                }

            # Generate and open PDF
            generar_y_abrir_pdf_desde_formulario(pdf_concept_data)
    else:
        st.info("ℹ️ Complete los campos requeridos (ID, Source, LaTeX Content) para generar el PDF")

# Edit Concept page
elif page == "✏️ Edit Concept":
    st.title("✏️ Edit Mathematical Concept")

    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()

    st.info(f"📊 Editing concepts in: **{current_db}**")

    # Concept selection
    st.subheader("🔍 Select Concept to Edit")

    col1, col2 = st.columns(2)

    with col1:
        # Filter by source
        filter_source = st.selectbox("Filter by Source", ["All"] + list(db.concepts.distinct("source")))

    with col2:
        # Filter by type
        filter_type = st.selectbox("Filter by Type", ["All"] + list(db.concepts.distinct("tipo")))

    # Build query for concept selection
    query = {}
    if filter_source != "All":
        query["source"] = filter_source
    if filter_type != "All":
        query["tipo"] = filter_type

    # Get concepts for selection
    concepts = list(db.concepts.find(query).sort("fecha_creacion", -1))

    if not concepts:
        st.warning("⚠️ No concepts found with the selected filters.")
        st.stop()

    # Create concept options for selection
    concept_options = []
    concept_map = {}

    for concept in concepts:
        display_name = f"{concept.get('titulo', concept['id'])} ({concept['tipo']} - {concept['source']})"
        concept_options.append(display_name)
        concept_map[display_name] = concept

    # Concept selector
    selected_concept_display = st.selectbox(
        "Choose Concept to Edit",
        concept_options,
        help="Select the concept you want to edit"
    )

    # Handle concept selection and data loading
    if selected_concept_display:
        selected_concept = concept_map[selected_concept_display]

        # Check if concept has changed and update session state
        if ("last_selected_id" not in st.session_state or
            st.session_state.last_selected_id != selected_concept["id"]):

            # Update last selected ID
            st.session_state.last_selected_id = selected_concept["id"]

            # Get LaTeX content from database
            latex_doc = db.latex_documents.find_one({
                "id": selected_concept['id'], 
                "source": selected_concept['source']
            })
            current_latex = latex_doc['contenido_latex'] if latex_doc else ""

            # Update all form fields in session state
            st.session_state.edit_id = selected_concept.get("id", "")
            st.session_state.edit_source = selected_concept.get("source", "")
            st.session_state.edit_titulo = selected_concept.get("titulo", "")
            st.session_state.edit_tipo_titulo = selected_concept.get("tipo_titulo", "ninguno")
            st.session_state["edit_latex_text"] = current_latex
            # estado para remount del editor en Edit Concept
            # fuerza re-mount REAL cuando cambias de concepto (evita que ACE se quede pegado)
            st.session_state["edit_latex_editor_rev"] = st.session_state.get("edit_latex_editor_rev", 0) + 1
            st.session_state["edit_latex_insert"] = ""
            st.session_state["edit_insert_latex"] = False

            st.session_state.edit_comentario = selected_concept.get("comentario", "")
            st.session_state.edit_es_algoritmo = selected_concept.get("es_algoritmo", False)
            st.session_state.edit_categorias = selected_concept.get("categorias", [])
            st.session_state.edit_referencia = selected_concept.get("referencia", {})
            st.session_state.edit_pasos_algoritmo = selected_concept.get("pasos_algoritmo", [])
            st.session_state.edit_contexto_docente = selected_concept.get("contexto_docente", {})
            st.session_state.edit_metadatos_tecnicos = selected_concept.get("metadatos_tecnicos", {})

            # Initialize reference fields in session state
            ref = selected_concept.get("referencia", {})
            st.session_state.edit_ref_tipo = ref.get('tipo_referencia', 'libro')
            st.session_state.edit_ref_autor = ref.get('autor', '')
            st.session_state.edit_ref_fuente = ref.get('fuente', '')
            st.session_state.edit_ref_anio = ref.get('anio', 2024)
            st.session_state.edit_ref_tomo = ref.get('tomo', '')
            st.session_state.edit_ref_edicion = ref.get('edicion', '')
            st.session_state.edit_ref_paginas = ref.get('paginas', '')
            st.session_state.edit_ref_capitulo = ref.get('capitulo', '')
            st.session_state.edit_ref_seccion = ref.get('seccion', '')
            st.session_state.edit_ref_editorial = ref.get('editorial', '')
            st.session_state.edit_ref_doi = ref.get('doi', '')
            st.session_state.edit_ref_url = ref.get('url', '')
            st.session_state.edit_ref_issbn = ref.get('issbn', '')
            # Citekey can be stored either at concept-level (legacy) or inside referencia (preferred).
            st.session_state.edit_ref_citekey = (
                (selected_concept.get("citekey") or "")
                or (ref.get('citekey') or '')
            )

            # Initialize teaching context fields in session state
            context = selected_concept.get("contexto_docente", {})
            st.session_state.edit_nivel = context.get('nivel_contexto', 'introductorio')
            st.session_state.edit_formalidad = context.get('grado_formalidad', 'informal')

            # Initialize technical metadata fields in session state
            meta = selected_concept.get("metadatos_tecnicos", {})
            st.session_state.edit_notacion = meta.get('usa_notacion_formal', True)
            st.session_state.edit_demostracion = meta.get('incluye_demostracion', False)
            st.session_state.edit_operativa = meta.get('es_definicion_operativa', False)
            st.session_state.edit_fundamental = meta.get('es_concepto_fundamental', False)
            st.session_state.edit_previos = ', '.join(meta.get('requiere_conceptos_previos', [])) if meta.get('requiere_conceptos_previos') else ""
            st.session_state.edit_ejemplo = meta.get('incluye_ejemplo', False)
            st.session_state.edit_autocontenible = meta.get('es_autocontenible', True)
            st.session_state.edit_presentacion = meta.get('tipo_presentacion', 'expositivo')
            st.session_state.edit_simbolico = meta.get('nivel_simbolico', 'bajo')
            st.session_state.edit_aplicacion = meta.get('tipo_aplicacion', [])

            # Initialize algorithm fields in session state
            st.session_state.edit_algoritmo = selected_concept.get("es_algoritmo", False)
            st.session_state.edit_pasos = '\n'.join(selected_concept.get("pasos_algoritmo", [])) if selected_concept.get("pasos_algoritmo") else ""

            # Clear any pending LaTeX insertions
            st.session_state.edit_latex_insert = ""
            st.session_state.edit_insert_latex = False

            # Force rerun to update all widgets
            st.rerun()

        # Display header
        st.markdown("---")
        st.subheader(f"✏️ Editing: {selected_concept.get('titulo', selected_concept['id'])}")

        # Basic information
        st.subheader("📋 Basic Information")

        col1, col2 = st.columns(2)
        with col1:
            concept_id = st.text_input("ID", key="edit_id")
            source = st.text_input("Source", key="edit_source")

        with col2:
            titulo = st.text_input("Title", key="edit_titulo")
            tipo_titulo = st.selectbox(
                "Title Type", 
                [t.value for t in TipoTitulo],
                key="edit_tipo_titulo"
            )

        # Concept type (read-only for now to avoid complications)
        st.info(f"**Concept Type:** {selected_concept['tipo']} (cannot be changed)")

        # Categories
        # Get all available categories from database
        categorias_db = db.concepts.distinct("categorias")
        categorias_db = [cat for cat in categorias_db if isinstance(cat, str)]

        # Combine predefined and database categories
        categorias_predefinidas = ["Algebra", "Analysis", "Topology", "Geometry", "Number Theory", "Combinatorics", "Logic", "Statistics", "Calculus"]
        all_categories = sorted(set(categorias_predefinidas + categorias_db))

        categorias = st.multiselect(
            "Categories",
            all_categories,
            key="edit_categorias"
        )
        
        # LaTeX content with helper toolbar
        st.subheader("📝 LaTeX Content")
        
        # LaTeX Helper Toolbar (same as Add Concept)
        st.write("**🔧 LaTeX Helper Tools:**")
        
        # Main structures
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📝 Definition", key="edit_btn_def"):
                st.session_state.edit_latex_insert = r"\begin{definition}" + "\n" + r"% Definition content here" + "\n" + r"\end{definition}"
            
            if st.button("📋 Theorem", key="edit_btn_theorem"):
                st.session_state.edit_latex_insert = r"\begin{theorem}" + "\n" + r"% Theorem statement here" + "\n" + r"\end{theorem}"

            if st.button("📖 Proof", key="edit_btn_proof"):
                st.session_state.edit_latex_insert = r"\begin{proof}" + "\n" + r"% Proof content here" + "\n" + r"\end{proof}"

            if st.button("📊 Example", key="edit_btn_example"):
                st.session_state.edit_latex_insert = r"\begin{example}" + "\n" + r"% Example content here" + "\n" + r"\end{example}"

        with col2:
            if st.button("📋 Lemma", key="edit_btn_lemma"):
                st.session_state.edit_latex_insert = r"\begin{lemma}" + "\n" + r"% Lemma statement here" + "\n" + r"\end{lemma}"

            if st.button("📋 Proposition", key="edit_btn_prop"):
                st.session_state.edit_latex_insert = r"\begin{proposition}" + "\n" + r"% Proposition statement here" + "\n" + r"\end{proposition}"

            if st.button("📋 Corollary", key="edit_btn_corollary"):
                st.session_state.edit_latex_insert = r"\begin{corollary}" + "\n" + r"% Corollary statement here" + "\n" + r"\end{corollary}"

            if st.button("📋 Remark", key="edit_btn_remark"):
                st.session_state.edit_latex_insert = r"\begin{remark}" + "\n" + r"% Remark content here" + "\n" + r"\end{remark}"

        with col3:
            if st.button("🔢 Equation", key="edit_btn_eq"):
                st.session_state.edit_latex_insert = r"\begin{equation}" + "\n" + r"% Equation here" + "\n" + r"\end{equation}"

            if st.button("🔢 Align", key="edit_btn_align"):
                st.session_state.edit_latex_insert = r"\begin{align}" + "\n" + r"% Multiple equations here" + "\n" + r"\end{align}"

            if st.button("🔢 Matrix", key="edit_btn_matrix"):
                st.session_state.edit_latex_insert = r"\begin{pmatrix}" + "\n" + r"a & b \\" + "\n" + r"c & d" + "\n" + r"\end{pmatrix}"

            if st.button("🔢 Cases", key="edit_btn_cases"):
                st.session_state.edit_latex_insert = r"\begin{cases}" + "\n" + r"% Case 1 \\" + "\n" + r"% Case 2" + "\n" + r"\end{cases}"

        with col4:
            if st.button("📋 Itemize", key="edit_btn_itemize"):
                st.session_state.edit_latex_insert = r"\begin{itemize}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{itemize}"

            if st.button("📋 Enumerate", key="edit_btn_enumerate"):
                st.session_state.edit_latex_insert = r"\begin{enumerate}" + "\n" + r"\item First item" + "\n" + r"\item Second item" + "\n" + r"\end{enumerate}"

            if st.button("📋 Description", key="edit_btn_description"):
                st.session_state.edit_latex_insert = r"\begin{description}" + "\n" + r"\item[Term 1] Description 1" + "\n" + r"\item[Term 2] Description 2" + "\n" + r"\end{description}"

            if st.button("📋 Quote", key="edit_btn_quote"):
                st.session_state.edit_latex_insert = r"\begin{quote}" + "\n" + r"% Quoted text here" + "\n" + r"\end{quote}"

            if st.button("🧩 Code", key="edit_btn_code_listing"):
                st.session_state["edit_latex_insert"] = (
                    r"\begin{lstlisting}[language=ValorLanguage, caption=NombreParaCaption]" "\n"
                    r"# Comentario" "\n"
                    r"codigo" "\n"
                    r"\end{lstlisting}")

            if st.button("🌳 Dir Tree", key="edit_btn_dir_tree"):
                st.session_state["edit_latex_insert"] = (
                    r"\dirtree{%" "\n"
                    r".1 main folder." "\n"
                    r".2 subfolder." "\n"
                    r".3 subsubfolder." "\n"
                    r".4 subsubsubfolder." "\n"
                    r"}"
                )

        # Mathematical symbols (abbreviated for edit page)
        st.write("**🔢 Common Symbols:**")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("∑ Sum", key="edit_btn_sum"):
                st.session_state.edit_latex_insert = r"\sum_{i=1}^{n}"
            if st.button("∫ Integral", key="edit_btn_int"):
                st.session_state.edit_latex_insert = r"\int_{a}^{b}"
            if st.button("→ Arrow", key="edit_btn_arrow"):
                st.session_state.edit_latex_insert = r"\rightarrow"
            if st.button("∈ Belongs", key="edit_btn_in"):
                st.session_state.edit_latex_insert = r"\in"

        with col2:
            if st.button("∞ Infinity", key="edit_btn_inf"):
                st.session_state.edit_latex_insert = r"\infty"
            if st.button("∪ Union", key="edit_btn_union"):
                st.session_state.edit_latex_insert = r"\cup"
            if st.button("∩ Intersection", key="edit_btn_intersection"):
                st.session_state.edit_latex_insert = r"\cap"
            if st.button("∀ For All", key="edit_btn_forall"):
                st.session_state.edit_latex_insert = r"\forall"

        with col3:
            if st.button("α Alpha", key="edit_btn_alpha"):
                st.session_state.edit_latex_insert = r"\alpha"
            if st.button("β Beta", key="edit_btn_beta"):
                st.session_state.edit_latex_insert = r"\beta"
            if st.button("γ Gamma", key="edit_btn_gamma"):
                st.session_state.edit_latex_insert = r"\gamma"
            if st.button("δ Delta", key="edit_btn_delta"):
                st.session_state.edit_latex_insert = r"\delta"

        with col4:
            if st.button("π Pi", key="edit_btn_pi"):
                st.session_state.edit_latex_insert = r"\pi"
            if st.button("σ Sigma", key="edit_btn_sigma"):
                st.session_state.edit_latex_insert = r"\sigma"
            if st.button("λ Lambda", key="edit_btn_lambda"):
                st.session_state.edit_latex_insert = r"\lambda"
            if st.button("θ Theta", key="edit_btn_theta"):
                st.session_state.edit_latex_insert = r"\theta"
        
        # Initialize edit_latex_insert in session state if not exists
        if 'edit_latex_insert' not in st.session_state:
            st.session_state["edit_latex_insert"] = ""
        
        # Show current insertion if any
        if st.session_state["edit_latex_insert"]:
            st.info(f"**Ready to insert:** `{st.session_state['edit_latex_insert']}`")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Insert at Cursor", key="edit_insert_btn"):
                    st.session_state["edit_insert_latex"] = True
            with col2:
                if st.button("❌ Clear", key="edit_clear_insert"):
                    st.session_state["edit_latex_insert"] = ""
                    st.session_state["edit_insert_latex"] = False


        # -------------------------
        # LaTeX editor (ACE) - Edit Concept
        # -------------------------

        # Estado real del texto (NO es el key del widget)
        if "edit_latex_text" not in st.session_state:
            st.session_state["edit_latex_text"] = ""

        # Revisión para forzar re-mount del componente cuando insertas
        if "edit_latex_editor_rev" not in st.session_state:
            st.session_state["edit_latex_editor_rev"] = 0

        # Flags de inserción (asegurar existencia)
        if "edit_latex_insert" not in st.session_state:
            st.session_state["edit_latex_insert"] = ""
        if "edit_insert_latex" not in st.session_state:
            st.session_state["edit_insert_latex"] = False
        
        # Handle insertion (DEBE IR ANTES del st_ace)
        if st.session_state.get("edit_insert_latex") and st.session_state.get("edit_latex_insert"):
            current_text = st.session_state.get("edit_latex_text", "") or ""
            to_insert = st.session_state["edit_latex_insert"]
            if current_text and not current_text.endswith("\n"):
                current_text += "\n"
            st.session_state["edit_latex_text"] = current_text + to_insert + "\n"
            # limpiar flags
            st.session_state["edit_insert_latex"] = False
            st.session_state["edit_latex_insert"] = ""

            # fuerza re-mount
            st.session_state["edit_latex_editor_rev"] += 1
            st.rerun()

        editor_seed = f"{st.session_state.get('edit_id','')}@{st.session_state.get('edit_source','')}"
        contenido_latex = st_ace(
            value=st.session_state["edit_latex_text"],
            language="latex",
            theme="monokai",
            font_size=16,
            tab_size=2,
            height=800,        # aquí súbele para edición cómoda
            wrap=True,
            show_gutter=True,
            auto_update=True,
            key=f"edit_latex_editor__{editor_seed}__{st.session_state['edit_latex_editor_rev']}",
            )

        # Sincronizar el contenido del editor con el estado
        st.session_state["edit_latex_text"] = contenido_latex or ""
        contenido_latex = st.session_state["edit_latex_text"]  # este es el que se guarda

        ##----------------------------------------
        # Algorithm section
        st.subheader("⚙️ Algorithm Information")
        col1, col2 = st.columns(2)
        with col1:
            es_algoritmo = st.checkbox("Is this an algorithm?", key="edit_algoritmo")
        with col2:
            if es_algoritmo:
                pasos_algoritmo = st.text_area("Algorithm Steps", key="edit_pasos")
        
        # Reference information
        st.subheader("📚 Reference Information")
        current_ref = st.session_state.edit_referencia
        
        with st.expander("Edit Reference", expanded=bool(current_ref)):
            col1, col2 = st.columns(2)
            with col1:
                ref_tipo = st.selectbox(
                    "Reference Type", 
                    [t.value for t in TipoReferencia],
                    key="edit_ref_tipo"
                )
                ref_autor = st.text_input("Author", key="edit_ref_autor")
                ref_fuente = st.text_input("Source/Title", key="edit_ref_fuente")
                ref_anio = st.number_input("Year", min_value=1800, max_value=2030, key="edit_ref_anio")
            
            with col2:
                ref_tomo = st.text_input("Volume", key="edit_ref_tomo")
                ref_edicion = st.text_input("Edition", key="edit_ref_edicion")
                ref_paginas = st.text_input("Pages", key="edit_ref_paginas")
                ref_capitulo = st.text_input("Chapter", key="edit_ref_capitulo")
            
            ref_seccion = st.text_input("Section", key="edit_ref_seccion")
            ref_editorial = st.text_input("Publisher", key="edit_ref_editorial")
            ref_doi = st.text_input("DOI", key="edit_ref_doi")
            ref_url = st.text_input("URL", key="edit_ref_url")
            ref_issbn = st.text_input("ISBN", key="edit_ref_issbn")
            # Optional citekey used for bibliography export (Quarto/Pandoc).
            st.text_input("Citekey (opcional)", key="edit_ref_citekey")
        
        # Teaching context
        st.subheader("🎓 Teaching Context")
        current_context = st.session_state.edit_contexto_docente
        
        with st.expander("Edit Teaching Context", expanded=bool(current_context)):
            col1, col2 = st.columns(2)
            with col1:
                nivel_contexto = st.selectbox(
                    "Context Level", 
                    [n.value for n in NivelContexto],
                    key="edit_nivel"
                )
            with col2:
                grado_formalidad = st.selectbox(
                    "Formality Degree", 
                    [g.value for g in GradoFormalidad],
                    key="edit_formalidad"
                )
        
        # Technical metadata
        st.subheader("🔧 Technical Metadata")
        current_meta = st.session_state.edit_metadatos_tecnicos
        
        with st.expander("Edit Technical Metadata", expanded=bool(current_meta)):
            col1, col2 = st.columns(2)
            with col1:
                usa_notacion_formal = st.checkbox("Uses Formal Notation", key="edit_notacion")
                incluye_demostracion = st.checkbox("Includes Proof", key="edit_demostracion")
                es_definicion_operativa = st.checkbox("Is Operational Definition", key="edit_operativa")
                es_concepto_fundamental = st.checkbox("Is Fundamental Concept", key="edit_fundamental")
            
            with col2:
                requiere_conceptos_previos = st.text_area(
                    "Required Previous Concepts", 
                    key="edit_previos"
                )
                incluye_ejemplo = st.checkbox("Includes Example", key="edit_ejemplo")
                es_autocontenible = st.checkbox("Is Self-Contained", key="edit_autocontenible")
            
            tipo_presentacion = st.selectbox(
                "Presentation Type", 
                [t.value for t in TipoPresentacion],
                key="edit_presentacion"
            )
            nivel_simbolico = st.selectbox(
                "Symbolic Level", 
                [n.value for n in NivelSimbolico],
                key="edit_simbolico"
            )
            tipo_aplicacion = st.multiselect(
                "Application Type", 
                [t.value for t in TipoAplicacion],
                key="edit_aplicacion"
            )
        
        # Comment
        comentario = st.text_area(
            "Comment", 
            key="edit_comentario"
        )
        
        # Action buttons
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💾 Update Concept", type="primary"):
                try:
                    # Build updated concept data
                    concept_data = {
                        "id": concept_id,
                        "tipo": selected_concept['tipo'],  # Keep original type
                        "titulo": titulo if titulo else None,
                        "tipo_titulo": tipo_titulo,
                        "categorias": categorias,
                        "contenido_latex": contenido_latex,
                        "es_algoritmo": es_algoritmo,
                        "pasos_algoritmo": pasos_algoritmo.split('\n') if es_algoritmo and pasos_algoritmo else None,
                        "comentario": comentario if comentario else None,
                        "source": source,
                        "ultima_actualizacion": datetime.now(),
                        # Keep concept-level citekey for backward compatibility.
                        "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }
                    
                    # Add reference if provided
                    if ref_autor or ref_fuente:
                        concept_data["referencia"] = {
                            "tipo_referencia": ref_tipo,
                            "autor": ref_autor if ref_autor else None,
                            "fuente": ref_fuente if ref_fuente else None,
                            "anio": ref_anio if ref_anio else None,
                            "tomo": ref_tomo if ref_tomo else None,
                            "edicion": ref_edicion if ref_edicion else None,
                            "paginas": ref_paginas if ref_paginas else None,
                            "capitulo": ref_capitulo if ref_capitulo else None,
                            "seccion": ref_seccion if ref_seccion else None,
                            "editorial": ref_editorial if ref_editorial else None,
                            "doi": ref_doi if ref_doi else None,
                            "url": ref_url if ref_url else None,
                            "issbn": ref_issbn if ref_issbn else None,
                            # NEW: Persist citekey at reference-level (preferred).
                            "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                        }
                    
                    # Add teaching context if provided
                    if nivel_contexto or grado_formalidad:
                        concept_data["contexto_docente"] = {
                            "nivel_contexto": nivel_contexto,
                            "grado_formalidad": grado_formalidad
                        }
                    
                    # Add technical metadata if provided
                    if usa_notacion_formal is not None or incluye_demostracion is not None:
                        concept_data["metadatos_tecnicos"] = {
                            "usa_notacion_formal": usa_notacion_formal,
                            "incluye_demostracion": incluye_demostracion,
                            "es_definicion_operativa": es_definicion_operativa,
                            "es_concepto_fundamental": es_concepto_fundamental,
                            "requiere_conceptos_previos": [c.strip() for c in requiere_conceptos_previos.split(',')] if requiere_conceptos_previos else None,
                            "incluye_ejemplo": incluye_ejemplo,
                            "es_autocontenible": es_autocontenible,
                            "tipo_presentacion": tipo_presentacion,
                            "nivel_simbolico": nivel_simbolico,
                            "tipo_aplicacion": tipo_aplicacion if tipo_aplicacion else None
                        }
                    
                    # Update in database
                    db.concepts.update_one(
                        {"id": selected_concept['id'], "source": selected_concept['source']},
                        {"$set": concept_data}
                    )
                    
                    # Update LaTeX content
                    now = datetime.now()
                    db.latex_documents.update_one(
                        {"id": selected_concept['id'], "source": selected_concept['source']},
                        {
                            "$set": {
                                "contenido_latex": contenido_latex,
                                "ultima_actualizacion": now
                            }
                        }
                    )
                    
                    st.success(f"✅ Concept '{concept_id}' updated successfully in {current_db}!")
                    st.balloons()
                    
                except Exception as e:
                    st.error(f"❌ Error updating concept: {e}")
        
        # PDF Generation Button for Edit Concept
        st.markdown("---")
        st.subheader("📄 Generar PDF")
        
        # Check if we have the minimum required data for PDF generation
        if concept_id and source and contenido_latex:
            if st.button("📄 Generar y abrir PDF", key="edit_pdf_btn", type="secondary"):
                # Build concept data for PDF generation
                pdf_concept_data = {
                    "id": concept_id,
                    "tipo": selected_concept['tipo'],
                    "titulo": titulo if titulo else concept_id,
                    "categorias": categorias,
                    "contenido_latex": contenido_latex,
                    "source": source,
                    "comentario": comentario if comentario else None
                }
                
                # Add reference if provided
                if ref_autor or ref_fuente:
                    pdf_concept_data["referencia"] = {
                        "tipo_referencia": ref_tipo,
                        "autor": ref_autor if ref_autor else None,
                        "fuente": ref_fuente if ref_fuente else None,
                        "anio": ref_anio if ref_anio else None,
                        "tomo": ref_tomo if ref_tomo else None,
                        "edicion": ref_edicion if ref_edicion else None,
                        "paginas": ref_paginas if ref_paginas else None,
                        "capitulo": ref_capitulo if ref_capitulo else None,
                        "seccion": ref_seccion if ref_seccion else None,
                        "editorial": ref_editorial if ref_editorial else None,
                        "doi": ref_doi if ref_doi else None,
                        "url": ref_url if ref_url else None,
                            "issbn": ref_issbn if ref_issbn else None,
                            # NEW: Persist citekey at reference-level too.
                            "citekey": (st.session_state.get("edit_ref_citekey") or "").strip() or None,
                    }
                
                # Generate and open PDF
                generar_y_abrir_pdf_desde_formulario(pdf_concept_data)
        else:
            st.info("ℹ️ Complete los campos requeridos (ID, Source, LaTeX Content) para generar el PDF")
        
        with col2:
            if st.button("🔄 Reset to Original"):
                st.rerun()
        
        with col3:
            # Persistent delete confirmation (Streamlit buttons are one-shot per rerun)
            if "delete_armed_edit" not in st.session_state:
                st.session_state["delete_armed_edit"] = False

            if st.button("🗑️ Delete Concept", key="delete_edit"):
                st.session_state["delete_armed_edit"] = True

            if st.session_state["delete_armed_edit"]:
                st.warning("⚠️ This will permanently delete the concept and related data.")
                col_del_1, col_del_2 = st.columns(2)

                with col_del_1:
                    if st.button("⚠️ Confirm Delete", key="confirm_delete_edit"):
                        try:
                            # Delete concept and LaTeX content
                            db.concepts.delete_one({"id": selected_concept['id'], "source": selected_concept['source']})
                            db.latex_documents.delete_one({"id": selected_concept['id'], "source": selected_concept['source']})

                            # Delete related relations
                            db.relations.delete_many({
                                "$or": [
                                    {"desde": f"{selected_concept['id']}@{selected_concept['source']}"},
                                    {"hasta": f"{selected_concept['id']}@{selected_concept['source']}"}
                                ]
                            })

                            st.session_state["delete_armed_edit"] = False
                            st.success("✅ Concept deleted successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error deleting concept: {e}")

                with col_del_2:
                    if st.button("Cancel", key="cancel_delete_edit"):
                        st.session_state["delete_armed_edit"] = False
                        st.info("Deletion cancelled.")

# Browse Concepts page
elif page == "📚 Browse Concepts":
    st.title("📚 Browse Mathematical Concepts")
    
    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()
    
    st.info(f"📊 Browsing concepts in: **{current_db}**")
    
    # Filters
    st.subheader("🔍 Filters")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filter_type = st.selectbox("Type", ["All"] + list(db.concepts.distinct("tipo")))
    
    with col2:
        filter_source = st.selectbox("Source", ["All"] + list(db.concepts.distinct("source")))
    
    with col3:
        search_term = st.text_input("Search", placeholder="Search by title or ID...")
    
    # Build query
    query = {}
    if filter_type != "All":
        query["tipo"] = filter_type
    if filter_source != "All":
        query["source"] = filter_source
    if search_term:
        query["$or"] = [
            {"titulo": {"$regex": search_term, "$options": "i"}},
            {"id": {"$regex": search_term, "$options": "i"}}
        ]
    
    # Execute query
    concepts = list(db.concepts.find(query).sort("fecha_creacion", -1))
    
    st.subheader(f"📊 Results ({len(concepts)} concepts)")

    # =========================
    # Quarto Book Export (NEW)
    # =========================
    st.markdown("---")
    st.subheader("📘 Export to Quarto Book")

    # Build list of selectable IDs
    concept_id_map = {
        f"{c.get('titulo', c['id'])} [{c['tipo']}]": c["id"]
        for c in concepts
    }

    selected_labels = st.multiselect(
        "Select concepts to export",
        options=list(concept_id_map.keys())
    )


    build_dir = st.text_input(
        "Quarto build directory",
        value="quarto_book_build"
    )


    force_build = st.checkbox(
        "Overwrite existing build directory",
        value=True
    )

    # MVP-B: LaTeX preflight (pdflatex compile check) before export
    preflight_compile = st.checkbox(
        "Preflight LaTeX (pdflatex compile check) before export",
        value=True,
        help="Compiles each selected concept with pdflatex + miestilo.sty. Blocks export on fatal errors."
    )

    if st.button("🚀 Export selected concepts to Quarto"):
        if not selected_labels:
            st.warning("Please select at least one concept.")
        else:
            try:
                from pathlib import Path

                from exporters_quarto.quarto_exporter import QuartoBookExporter
                from scripts.export_quarto_book import _write_book_quarto_yml
                selected_ids = {concept_id_map[l] for l in selected_labels}
                selected_concepts = []
                for c in concepts:
                    if c["id"] in selected_ids:
                        latex_doc = db.latex_documents.find_one({"id": c["id"], "source": c["source"]})
                        c2 = dict(c)  # copia para no mutar la lista base
                        c2["contenido_latex"] = (latex_doc or {}).get("contenido_latex", "")
                        selected_concepts.append(c2)

                # --- MVP-B: LaTeX preflight (pdflatex compile check) ---
                if preflight_compile:
                    import shutil
                    import subprocess
                    import tempfile

                    if not shutil.which("pdflatex"):
                        raise RuntimeError(
                            "pdflatex not found. Install TeX Live (texlive-latex-base) or disable the preflight checkbox."
                        )

                    #miestilo_src = Path("templates_latex/miestilo.sty")
                    #if not miestilo_src.exists():
                    quarto_styles_dir = Path("quarto_book/styles")
                    miestilo_src = quarto_styles_dir / "miestilo.sty"
                    if not miestilo_src.exists():
                        raise FileNotFoundError(
                            "miestilo.sty not found in templates_latex/ or quarto_book/styles/"
                        )

                    #coloredtheorem_src = Path("templates_latex/coloredtheorem.sty")
                    #if not coloredtheorem_src.exists():
                    coloredtheorem_src = quarto_styles_dir / "coloredtheorem.sty"
                    if not coloredtheorem_src.exists():
                        raise FileNotFoundError(
                            "coloredtheorem.sty not found in templates_latex/ or quarto_book/styles/"
                        )


                    failures: list[tuple[str, str, str]] = []
                    progress = st.progress(0, text="Preflight LaTeX: compiling selected concepts...")
                    total = max(1, len(selected_concepts))

                    for idx, c in enumerate(selected_concepts, start=1):
                        latex_body = (c.get("contenido_latex") or "").strip()
                        # Empty LaTeX content is treated as OK (non-blocking)
                        if not latex_body:
                            progress.progress(int(idx * 100 / total))
                            continue

                        with tempfile.TemporaryDirectory(prefix="mkb_preflight_") as td:
                            td_path = Path(td)
                            shutil.copy2(miestilo_src, td_path / "miestilo.sty")
                            (td_path / "styles").mkdir(parents=True, exist_ok=True)
                            shutil.copy2(coloredtheorem_src, td_path / "styles" / "coloredtheorem.sty")

                            tex = (
                                "\\documentclass{article}\n"
                                "\\usepackage{miestilo}\n"
                                "\\begin{document}\n"
                                + latex_body
                                + "\n\\end{document}\n"
                            )
                            (td_path / "main.tex").write_text(tex, encoding="utf-8")

                            proc = subprocess.run(
                                [
                                    "pdflatex",
                                    "-interaction=nonstopmode",
                                    "-halt-on-error",
                                    "-file-line-error",
                                    "main.tex",
                                ],
                                cwd=str(td_path),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=25,
                            )

                            if proc.returncode != 0:
                                log = proc.stdout or ""
                                tail = "\n".join(log.splitlines()[-80:])
                                key = f"{c.get('id')}@{c.get('source')}"
                                failures.append((key, str(c.get("titulo") or ""), tail))

                        progress.progress(int(idx * 100 / total))

                    progress.empty()
                    if failures:
                        st.error(
                            f"❌ LaTeX preflight failed for {len(failures)} concept(s). Export blocked."
                        )
                        for key, title, tail in failures:
                            with st.expander(f"Preflight error: {title or key}"):
                                st.code(tail)
                        st.stop()
                # --- end MVP-B ---

                template_dir = Path("quarto_book").resolve()
                build_path = Path(build_dir).resolve()

                exporter = QuartoBookExporter(
                    template_dir=template_dir,
                    build_dir=build_path)

                exporter.prepare_build(force=force_build)
                exporter.export_concepts(selected_concepts)

                _write_book_quarto_yml(build_path)

                st.success(f"Quarto book exported to: {build_path}")
                st.info("Next step: run `quarto render` inside that directory.")

            except Exception as e:
                st.error(f"Quarto export failed: {e}")
    if concepts:
        for concept in concepts:
            with st.expander(f"{concept.get('titulo', concept['id'])} ({concept['tipo']})"):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.write(f"**ID:** {concept['id']}")
                    st.write(f"**Source:** {concept['source']}")
                    st.write(f"**Categories:** {', '.join(concept.get('categorias', []))}")

                    if concept.get('comentario'):
                        st.write(f"**Comment:** {concept['comentario']}")

                    # Show LaTeX content
                    latex_doc = db.latex_documents.find_one({"id": concept['id'], "source": concept['source']})
                    if latex_doc:
                        st.subheader("LaTeX Content")
                        st.code(latex_doc['contenido_latex'], language="latex")

                with col2:
                    # Actions
                    if st.button("📤 Export PDF", key=f"export_{concept['id']}"):
                        try:
                            exportador = ExportadorLatex()
                            exportador.exportar_concepto(concept, latex_doc['contenido_latex'])
                            st.success("PDF exported successfully!")
                        except Exception as e:
                            st.error(f"Export failed: {e}")

                    if st.button("🔗 View Relations", key=f"relations_{concept['id']}"):
                        relations = db.get_relations(desde_id=concept['id'], desde_source=concept['source'])
                        if relations:
                            st.write("**Relations:**")
                            for rel in relations:
                                st.write(f"• {rel.tipo}: {rel.hasta_id}@{rel.hasta_source}")
                        else:
                            st.write("No relations found.")
                    
                    if st.button("🗑️ Delete", key=f"delete_{concept['id']}"):
                        if st.button("⚠️ Confirm Delete", key=f"confirm_{concept['id']}"):
                            db.concepts.delete_one({"id": concept['id'], "source": concept['source']})
                            db.latex_documents.delete_one({"id": concept['id'], "source": concept['source']})
                            st.success("Concept deleted!")
                            st.rerun()
    else:
        st.info("No concepts found matching the criteria.")

# Manage Relations page
elif page == "🔗 Manage Relations":
    st.title("🔗 Manage Concept Relations")
    
    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()
    
    st.info(f"📊 Managing relations in: **{current_db}**")
    
    # Import interactive graph manager
    from editor.interactive_graph import InteractiveGraphManager
    graph_manager = InteractiveGraphManager(db)
    
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
                st.markdown(
                    f"""<div class="concept-card">
                    <div style="font-size:1.05rem;font-weight:700">{_concept_label(_from_doc, desde_id)}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>Type:</b> {_from_doc.get('tipo','—')} &nbsp;&nbsp; <b>Source:</b> {desde_source}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>ID:</b> {desde_id}</div>
                    </div>""",
                    unsafe_allow_html=True
                )
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
                st.markdown(
                    f"""<div class="metric-card" style="text-align:center">
                    <div style="font-size:1.6rem;font-weight:800">{rel_symbol}</div>
                    <div style="margin-top:0.25rem"><b>{tipo_relacion}</b></div>
                    </div>""",
                    unsafe_allow_html=True
                )
            with b_col:
                st.markdown("**B (To)**")
                st.markdown(
                    f"""<div class="concept-card">
                    <div style="font-size:1.05rem;font-weight:700">{_concept_label(_to_doc, hasta_id)}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>Type:</b> {_to_doc.get('tipo','—')} &nbsp;&nbsp; <b>Source:</b> {hasta_source}</div>
                    <div style="opacity:0.85;margin-top:0.25rem"><b>ID:</b> {hasta_id}</div>
                    </div>""",
                    unsafe_allow_html=True
                )

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

            RELATION_CHECKLIST = {
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
            spec = RELATION_CHECKLIST.get(tipo_relacion, None)
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
                preview_depth = st.slider(
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

                        preview_html_file = "relation_preview_graph.html"
                        grafo.exportar_html(salida=preview_html_file)

                        with open(preview_html_file, "r", encoding="utf-8") as f:
                            html = f.read()
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
                            key=f"edit_type_{i}"
                        )
                    with col2:
                        new_desc = st.text_area(
                            "Description",
                            value=rel.get('descripcion', ''),
                            key=f"edit_desc_{i}"
                        )
                    
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
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error updating relation: {e}")
                    
                    with col2:
                        if st.button("🔄 Reset", key=f"reset_rel_{i}"):
                            st.rerun()
                    
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_rel_{i}"):
                            if st.button("⚠️ Confirm Delete", key=f"confirm_delete_rel_{i}"):
                                try:
                                    db.relations.delete_one({"_id": rel["_id"]})
                                    st.success("✅ Relation deleted successfully!")
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
                st.bar_chart(type_counts)
        else:
            st.info("No relations found with the selected filters.")

# Knowledge Graph page
elif page == "📊 Knowledge Graph":
    st.title("📊 Knowledge Graph Visualization")
    
    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()
    
    st.info(f"📊 Generating graph from: **{current_db}**")
    
    st.subheader("🔧 Graph Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Filter by source
        selected_sources = st.multiselect(
            "Select Sources",
            db.concepts.distinct("source"),
            default=db.concepts.distinct("source")[:3] if db.concepts.distinct("source") else []
        )
        
        # Filter by concept types
        selected_types = st.multiselect(
            "Select Concept Types",
            ["definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"],
            default=["definicion", "teorema", "proposicion"]
        )
    
    with col2:
        # Filter by relation types
        selected_relations = st.multiselect(
            "Select Relation Types",
            [t.value for t in TipoRelacion],
            default=["implica", "deriva_de", "requiere_concepto"]
        )
        
        max_depth = st.slider("Max Depth", 1, 5, 3)
    
    if st.button("🔍 Generate Graph", type="primary"):
        if selected_sources:
            try:
                # Get concepts
                concept_query = {"source": {"$in": selected_sources}}
                if selected_types:
                    concept_query["tipo"] = {"$in": selected_types}
                
                concepts = list(db.concepts.find(concept_query))
                
                # Get relations
                relation_query = {
                    "$or": [
                        {"desde": {"$regex": f"@({'|'.join(selected_sources)})$"}},
                        {"hasta": {"$regex": f"@({'|'.join(selected_sources)})$"}}
                    ]
                }
                if selected_relations:
                    relation_query["tipo"] = {"$in": selected_relations}
                
                relations = list(db.relations.find(relation_query))
                
                if concepts and relations:
                    # Generate graph
                    grafo = GrafoConocimiento(concepts, relations)
                    grafo.construir_grafo(
                        tipos_relacion=selected_relations,
                        tipos_concepto=selected_types
                    )

                    # Export to HTML
                    html_file = "knowledge_graph.html"
                    grafo.exportar_html(salida=html_file)
                    
                    # Display the graph
                    with open(html_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    
                    st.subheader("🎯 Interactive Knowledge Graph")
                    st.components.v1.html(html_content, height=600)
                    
                    # Download link
                    with open(html_file, 'r', encoding='utf-8') as f:
                        st.download_button(
                            label="📥 Download Graph HTML",
                            data=f.read(),
                            file_name="knowledge_graph.html",
                            mime="text/html"
                        )
                    
                    # Statistics
                    st.subheader("📊 Graph Statistics")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Nodes", len(grafo.G.nodes))
                    with col2:
                        st.metric("Edges", len(grafo.G.edges))
                    with col3:
                        st.metric("Sources", len(selected_sources))
                
                else:
                    st.warning("⚠️ No concepts or relations found with the selected filters.")
            
            except Exception as e:
                st.error(f"❌ Error generating graph: {e}")
        else:
            st.error("❌ Please select at least one source.")

# Export page
elif page == "📤 Export":
    st.title("📤 Export Concepts")
    
    if db is None:
        st.error("❌ No database connection. Please select a database in the sidebar.")
        st.stop()
    
    st.info(f"📊 Exporting from: **{current_db}**")
    
    st.subheader("📄 LaTeX/PDF Export")
    
    # Export options
    col1, col2 = st.columns(2)
    
    with col1:
        export_source = st.selectbox("Select Source", [""] + list(db.concepts.distinct("source")))
        export_type = st.selectbox("Export Type", ["All", "definicion", "teorema", "proposicion", "corolario", "lema", "ejemplo", "nota"])
    
    with col2:
        export_format = st.selectbox("Export Format", ["PDF", "LaTeX"])
        output_dir = st.text_input("Output Directory", value="./exported")
    
    if st.button("📤 Export", type="primary"):
        if export_source:
            try:
                exportador = ExportadorLatex()
                
                # Build query
                query = {"source": export_source}
                if export_type != "All":
                    query["tipo"] = export_type
                
                concepts = list(db.concepts.find(query))
                
                if concepts:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, concept in enumerate(concepts):
                        status_text.text(f"Exporting {concept['id']}...")
                        
                        latex_doc = db.latex_documents.find_one({"id": concept['id'], "source": export_source})
                        if latex_doc:
                            exportador.exportar_concepto(concept, latex_doc['contenido_latex'], salida=output_dir)
                        
                        progress_bar.progress((i + 1) / len(concepts))
                    
                    status_text.text("✅ Export completed!")
                    st.success(f"✅ Exported {len(concepts)} concepts to {output_dir}")
                    
                    # Show exported files
                    if Path(output_dir).exists():
                        st.subheader("📁 Exported Files")
                        files = list(Path(output_dir).glob("*.pdf" if export_format == "PDF" else "*.tex"))
                        for file in files:
                            st.write(f"• {file.name}")
                
                else:
                    st.warning("⚠️ No concepts found for the selected source and type.")
            
            except Exception as e:
                st.error(f"❌ Export failed: {e}")
        else:
            st.error("❌ Please select a source to export.")
    
    st.markdown("---")
    
    # Bulk operations
    st.subheader("🔄 Bulk Operations")
    
    if st.button("🔄 Export All Sources"):
        try:
            sources = db.concepts.distinct("source")
            exportador = ExportadorLatex()
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, source in enumerate(sources):
                status_text.text(f"Exporting source: {source}")
                exportador.exportar_todos_de_source(db.client, source, salida=f"./exported/{source}")
                progress_bar.progress((i + 1) / len(sources))
            
            status_text.text("✅ Bulk export completed!")
            st.success(f"✅ Exported all {len(sources)} sources")
        
        except Exception as e:
            st.error(f"❌ Bulk export failed: {e}")

# Settings page
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    
    st.subheader("🔧 Database Configuration")
    
    # Database status
    if db is None:
        st.error("❌ No database connection.")
        st.stop()
    else:
        st.success(f"✅ Connected to: **{current_db}**")
    
    # Database statistics
    st.subheader("📊 Database Statistics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        concept_count = db.concepts.count_documents({})
        st.metric("Total Concepts", concept_count)
        
        relation_count = db.relations.count_documents({})
        st.metric("Total Relations", relation_count)
    
    with col2:
        source_count = len(db.concepts.distinct("source"))
        st.metric("Sources", source_count)
        
        category_count = len(db.concepts.distinct("categorias"))
        st.metric("Categories", category_count)
    
    # Database operations
    st.subheader("🗄️ Database Operations")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🧹 Clear All Data", type="secondary"):
            if st.button("⚠️ Confirm Clear All", type="primary"):
                db.concepts.delete_many({})
                db.relations.delete_many({})
                db.latex_documents.delete_many({})
                st.success("✅ All data cleared!")
                st.rerun()
    
    with col2:
        if st.button("📊 Rebuild Indexes"):
            try:
                db.concepts.create_index([("id", 1), ("source", 1)], unique=True)
                db.latex_documents.create_index([("id", 1), ("source", 1)], unique=True)
                db.relations.create_index([("desde", 1), ("hasta", 1), ("tipo", 1)], unique=True)
                st.success("✅ Indexes rebuilt successfully!")
            except Exception as e:
                st.error(f"❌ Error rebuilding indexes: {e}")
    
    # Application information
    st.subheader("ℹ️ Application Information")
    
    st.write("**Math Knowledge Base** - Version 0.1.0b1")
    st.write("A platform for managing mathematical knowledge with LaTeX support and MongoDB storage.")
    st.write("**Author:** Enrique Díaz Ocampo")
    st.write("**License:** MIT")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        Math Knowledge Base - Built with Streamlit and MongoDB
    </div>
    """,
    unsafe_allow_html=True
)

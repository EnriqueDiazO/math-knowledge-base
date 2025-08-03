import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
import os

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mathdatabase.mathmongo import MathMongo
from schemas.schemas import (
    ConceptoBase, Definicion, Teorema, Proposicion, Corolario, Lema, Ejemplo, Nota,
    TipoTitulo, TipoReferencia, TipoPresentacion, NivelContexto, GradoFormalidad,
    NivelSimbolico, TipoAplicacion, TipoRelacion, Referencia, ContextoDocente, MetadatosTecnicos
)
from visualizations.grafoconocimiento import GrafoConocimiento
from exporters.exportadorlatex import ExportadorLatex

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
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .concept-card {
        background-color: white;
        padding: 1.5rem;
        border-radius: 0.5rem;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .latex-preview {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #dee2e6;
        font-family: 'Courier New', monospace;
    }
    .stButton > button {
        width: 100%;
        border-radius: 0.5rem;
    }
    .sidebar .sidebar-content {
        background-color: #f8f9fa;
    }
    .db-connection-card {
        background-color: #e8f4fd;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 2px solid #1f77b4;
        margin-bottom: 1rem;
    }
    .db-status-connected {
        color: #28a745;
        font-weight: bold;
    }
    .db-status-disconnected {
        color: #dc3545;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Database connection management
class DatabaseManager:
    def __init__(self):
        self.connections = {}
        self.current_connection = None
    
    def add_connection(self, name, mongo_uri, db_name):
        """Add a new database connection"""
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
        """Get a specific database connection"""
        return self.connections.get(name, {}).get('connection')
    
    def list_connections(self):
        """List all available connections"""
        return list(self.connections.keys())
    
    def get_current_connection(self):
        """Get the currently active connection"""
        return self.current_connection
    
    def set_current_connection(self, name):
        """Set the current active connection"""
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

page = st.sidebar.selectbox(
    "Navigation",
    ["🏠 Dashboard", "➕ Add Concept", "✏️ Edit Concept", "📚 Browse Concepts", "🔗 Manage Relations", "📊 Knowledge Graph", "📤 Export", "⚙️ Settings"]
)

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
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📝 Recent Concepts")
        recent_concepts = list(db.concepts.find().sort("fecha_creacion", -1).limit(10))
        
        if recent_concepts:
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
        else:
            st.info("No concepts found. Add your first concept!")
    
    with col2:
        st.subheader("📊 Quick Stats")
        
        # Concept types distribution
        concept_types = db.concepts.aggregate([
            {"$group": {"_id": "$tipo", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ])
        
        type_data = list(concept_types)
        if type_data:
            df_types = pd.DataFrame(type_data)
            st.bar_chart(df_types.set_index("_id")["count"])
        
        # Top categories
        category_pipeline = [
            {"$unwind": "$categorias"},
            {"$group": {"_id": "$categorias", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        
        top_categories = list(db.concepts.aggregate(category_pipeline))
        if top_categories:
            st.write("**Top Categories:**")
            for cat in top_categories:
                st.write(f"• {cat['_id']}: {cat['count']}")

# Add Concept page
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
        source = st.text_input("Source", placeholder="e.g., BookA", help="Source or folder name")
    
    with col2:
        titulo = st.text_input("Title (Optional)", placeholder="e.g., Definition of Group")
        tipo_titulo = st.selectbox("Title Type", [t.value for t in TipoTitulo])
    
    categorias = st.multiselect(
        "Categories",
        ["Algebra", "Analysis", "Topology", "Geometry", "Number Theory", "Combinatorics", "Logic", "Statistics", "Calculus"],
        help="Select relevant mathematical categories"
    )
    
    # LaTeX content with helper toolbar
    st.subheader("📝 LaTeX Content")
    
    # LaTeX Helper Toolbar
    st.write("**🔧 LaTeX Helper Tools:**")
    
    # Main structures
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📝 Definition", key="btn_def"):
            st.session_state.latex_insert = r"\begin{definition}" + "\n" + r"% Definition content here" + "\n" + r"\end{definition}"
        
        if st.button("📋 Theorem", key="btn_theorem"):
            st.session_state.latex_insert = r"\begin{theorem}" + "\n" + r"% Theorem statement here" + "\n" + r"\end{theorem}"
        
        if st.button("📖 Proof", key="btn_proof"):
            st.session_state.latex_insert = r"\begin{proof}" + "\n" + r"% Proof content here" + "\n" + r"\end{proof}"
        
        if st.button("📊 Example", key="btn_example"):
            st.session_state.latex_insert = r"\begin{example}" + "\n" + r"% Example content here" + "\n" + r"\end{example}"

    with col2:
        if st.button("📋 Lemma", key="btn_lemma"):
            st.session_state.latex_insert = r"\begin{lemma}" + "\n" + r"% Lemma statement here" + "\n" + r"\end{lemma}"
        
        if st.button("📋 Proposition", key="btn_prop"):
            st.session_state.latex_insert = r"\begin{proposition}" + "\n" + r"% Proposition statement here" + "\n" + r"\end{proposition}"
        
        if st.button("📋 Corollary", key="btn_corollary"):
            st.session_state.latex_insert = r"\begin{corollary}" + "\n" + r"% Corollary statement here" + "\n" + r"\end{corollary}"
        
        if st.button("📋 Remark", key="btn_remark"):
            st.session_state.latex_insert = r"\begin{remark}" + "\n" + r"% Remark content here" + "\n" + r"\end{remark}"

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
    # Initialize latex_textarea_value in session state if not exists
    if 'latex_textarea_value' not in st.session_state:
        st.session_state.latex_textarea_value = ""
    
    contenido_latex = st.text_area(
        "LaTeX Content",
        value=st.session_state.latex_textarea_value,
        height=200,
        placeholder="Enter your LaTeX content here...",
        help="Write the mathematical content in LaTeX format. Use the buttons above to insert common structures.",
        key="latex_textarea"
    )
    
    # Handle insertion
    if 'insert_latex' in st.session_state and st.session_state.insert_latex:
        if st.session_state.latex_insert:
            # Get current cursor position (approximate)
            current_text = contenido_latex
            insertion_point = len(current_text)  # Insert at end for now
            
            # Insert the LaTeX code
            new_text = current_text[:insertion_point] + "\n" + st.session_state.latex_insert + current_text[insertion_point:]
            
            # Update session state and trigger rerun
            st.session_state.insert_latex = False
            st.session_state.latex_insert = ""
            st.session_state.latex_textarea_value = new_text
            st.rerun()
    
    # Algorithm section
    st.subheader("⚙️ Algorithm Information")
    col1, col2 = st.columns(2)
    with col1:
        es_algoritmo = st.checkbox("Is this an algorithm?")
    with col2:
        if es_algoritmo:
            pasos_algoritmo = st.text_area("Algorithm Steps", placeholder="Enter algorithm steps...")
    
    # Reference information
    st.subheader("📚 Reference Information")
    with st.expander("Add Reference", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            ref_tipo = st.selectbox("Reference Type", [t.value for t in TipoReferencia])
            ref_autor = st.text_input("Author")
            ref_fuente = st.text_input("Source/Title")
            ref_anio = st.number_input("Year", min_value=1800, max_value=2030, value=2024)
        
        with col2:
            ref_tomo = st.text_input("Volume")
            ref_edicion = st.text_input("Edition")
            ref_paginas = st.text_input("Pages")
            ref_capitulo = st.text_input("Chapter")
        
        ref_seccion = st.text_input("Section")
        ref_editorial = st.text_input("Publisher")
        ref_doi = st.text_input("DOI")
        ref_url = st.text_input("URL")
        ref_issbn = st.text_input("ISBN")
    
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
                    "ultima_actualizacion": datetime.now()
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
                concepto_dict = concepto.model_dump(mode="python", exclude={"contenido_latex"}, exclude_none=True)
                
                db.concepts.update_one(
                    {"id": concepto.id, "source": source},
                    {"$set": concepto_dict}, upsert=True
                )
                
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
    
    if selected_concept_display:
        selected_concept = concept_map[selected_concept_display]
        
        st.markdown("---")
        st.subheader(f"✏️ Editing: {selected_concept.get('titulo', selected_concept['id'])}")
        
        # Get LaTeX content
        latex_doc = db.latex_documents.find_one({
            "id": selected_concept['id'], 
            "source": selected_concept['source']
        })
        current_latex = latex_doc['contenido_latex'] if latex_doc else ""
        
        # Basic information
        st.subheader("📋 Basic Information")
        
        col1, col2 = st.columns(2)
        with col1:
            concept_id = st.text_input("ID", value=selected_concept['id'], key="edit_id")
            source = st.text_input("Source", value=selected_concept['source'], key="edit_source")
        
        with col2:
            titulo = st.text_input("Title", value=selected_concept.get('titulo', ''), key="edit_titulo")
            tipo_titulo = st.selectbox(
                "Title Type", 
                [t.value for t in TipoTitulo],
                index=[t.value for t in TipoTitulo].index(selected_concept.get('tipo_titulo', 'ninguno')),
                key="edit_tipo_titulo"
            )
        
        # Concept type (read-only for now to avoid complications)
        st.info(f"**Concept Type:** {selected_concept['tipo']} (cannot be changed)")
        
        # Categories
        current_categories = selected_concept.get('categorias', [])
        all_categories = ["Algebra", "Analysis", "Topology", "Geometry", "Number Theory", "Combinatorics", "Logic", "Statistics", "Calculus"]
        categorias = st.multiselect(
            "Categories",
            all_categories,
            default=[cat for cat in current_categories if cat in all_categories],
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
            st.session_state.edit_latex_insert = ""
        
        # Show current insertion if any
        if st.session_state.edit_latex_insert:
            st.info(f"**Ready to insert:** `{st.session_state.edit_latex_insert}`")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Insert at Cursor", key="edit_insert_btn"):
                    st.session_state.edit_insert_latex = True
            with col2:
                if st.button("❌ Clear", key="edit_clear_insert"):
                    st.session_state.edit_latex_insert = ""
                    st.session_state.edit_insert_latex = False
        
        # LaTeX text area
        # Initialize edit_latex_value in session state if not exists
        if 'edit_latex_value' not in st.session_state:
            st.session_state.edit_latex_value = current_latex
        
        contenido_latex = st.text_area(
            "LaTeX Content",
            value=st.session_state.edit_latex_value,
            height=200,
            key="edit_latex"
        )
        
        # Handle insertion for edit page
        if 'edit_insert_latex' in st.session_state and st.session_state.edit_insert_latex:
            if st.session_state.edit_latex_insert:
                # Get current cursor position (approximate)
                current_text = contenido_latex
                insertion_point = len(current_text)  # Insert at end for now
                
                # Insert the LaTeX code
                new_text = current_text[:insertion_point] + "\n" + st.session_state.edit_latex_insert + current_text[insertion_point:]
                
                # Update session state and trigger rerun
                st.session_state.edit_insert_latex = False
                st.session_state.edit_latex_insert = ""
                st.session_state.edit_latex_value = new_text
                st.rerun()
        
        # Algorithm section
        st.subheader("⚙️ Algorithm Information")
        col1, col2 = st.columns(2)
        with col1:
            es_algoritmo = st.checkbox("Is this an algorithm?", value=selected_concept.get('es_algoritmo', False), key="edit_algoritmo")
        with col2:
            if es_algoritmo:
                current_pasos = selected_concept.get('pasos_algoritmo', [])
                pasos_text = '\n'.join(current_pasos) if current_pasos else ""
                pasos_algoritmo = st.text_area("Algorithm Steps", value=pasos_text, key="edit_pasos")
        
        # Reference information
        st.subheader("📚 Reference Information")
        current_ref = selected_concept.get('referencia', {})
        
        with st.expander("Edit Reference", expanded=bool(current_ref)):
            col1, col2 = st.columns(2)
            with col1:
                ref_tipo = st.selectbox(
                    "Reference Type", 
                    [t.value for t in TipoReferencia],
                    index=[t.value for t in TipoReferencia].index(current_ref.get('tipo_referencia', 'libro')),
                    key="edit_ref_tipo"
                )
                ref_autor = st.text_input("Author", value=current_ref.get('autor', ''), key="edit_ref_autor")
                ref_fuente = st.text_input("Source/Title", value=current_ref.get('fuente', ''), key="edit_ref_fuente")
                ref_anio = st.number_input("Year", min_value=1800, max_value=2030, value=current_ref.get('anio', 2024), key="edit_ref_anio")
            
            with col2:
                ref_tomo = st.text_input("Volume", value=current_ref.get('tomo', ''), key="edit_ref_tomo")
                ref_edicion = st.text_input("Edition", value=current_ref.get('edicion', ''), key="edit_ref_edicion")
                ref_paginas = st.text_input("Pages", value=current_ref.get('paginas', ''), key="edit_ref_paginas")
                ref_capitulo = st.text_input("Chapter", value=current_ref.get('capitulo', ''), key="edit_ref_capitulo")
            
            ref_seccion = st.text_input("Section", value=current_ref.get('seccion', ''), key="edit_ref_seccion")
            ref_editorial = st.text_input("Publisher", value=current_ref.get('editorial', ''), key="edit_ref_editorial")
            ref_doi = st.text_input("DOI", value=current_ref.get('doi', ''), key="edit_ref_doi")
            ref_url = st.text_input("URL", value=current_ref.get('url', ''), key="edit_ref_url")
            ref_issbn = st.text_input("ISBN", value=current_ref.get('issbn', ''), key="edit_ref_issbn")
        
        # Teaching context
        st.subheader("🎓 Teaching Context")
        current_context = selected_concept.get('contexto_docente', {})
        
        with st.expander("Edit Teaching Context", expanded=bool(current_context)):
            col1, col2 = st.columns(2)
            with col1:
                nivel_contexto = st.selectbox(
                    "Context Level", 
                    [n.value for n in NivelContexto],
                    index=[n.value for n in NivelContexto].index(current_context.get('nivel_contexto', 'introductorio')),
                    key="edit_nivel"
                )
            with col2:
                grado_formalidad = st.selectbox(
                    "Formality Degree", 
                    [g.value for g in GradoFormalidad],
                    index=[g.value for g in GradoFormalidad].index(current_context.get('grado_formalidad', 'informal')),
                    key="edit_formalidad"
                )
        
        # Technical metadata
        st.subheader("🔧 Technical Metadata")
        current_meta = selected_concept.get('metadatos_tecnicos', {})
        
        with st.expander("Edit Technical Metadata", expanded=bool(current_meta)):
            col1, col2 = st.columns(2)
            with col1:
                usa_notacion_formal = st.checkbox("Uses Formal Notation", value=current_meta.get('usa_notacion_formal', True), key="edit_notacion")
                incluye_demostracion = st.checkbox("Includes Proof", value=current_meta.get('incluye_demostracion', False), key="edit_demostracion")
                es_definicion_operativa = st.checkbox("Is Operational Definition", value=current_meta.get('es_definicion_operativa', False), key="edit_operativa")
                es_concepto_fundamental = st.checkbox("Is Fundamental Concept", value=current_meta.get('es_concepto_fundamental', False), key="edit_fundamental")
            
            with col2:
                requiere_conceptos_previos = st.text_area(
                    "Required Previous Concepts", 
                    value=', '.join(current_meta.get('requiere_conceptos_previos', [])) if current_meta.get('requiere_conceptos_previos') else "",
                    key="edit_previos"
                )
                incluye_ejemplo = st.checkbox("Includes Example", value=current_meta.get('incluye_ejemplo', False), key="edit_ejemplo")
                es_autocontenible = st.checkbox("Is Self-Contained", value=current_meta.get('es_autocontenible', True), key="edit_autocontenible")
            
            tipo_presentacion = st.selectbox(
                "Presentation Type", 
                [t.value for t in TipoPresentacion],
                index=[t.value for t in TipoPresentacion].index(current_meta.get('tipo_presentacion', 'expositivo')),
                key="edit_presentacion"
            )
            nivel_simbolico = st.selectbox(
                "Symbolic Level", 
                [n.value for n in NivelSimbolico],
                index=[n.value for n in NivelSimbolico].index(current_meta.get('nivel_simbolico', 'bajo')),
                key="edit_simbolico"
            )
            tipo_aplicacion = st.multiselect(
                "Application Type", 
                [t.value for t in TipoAplicacion],
                default=current_meta.get('tipo_aplicacion', []),
                key="edit_aplicacion"
            )
        
        # Comment
        comentario = st.text_area(
            "Comment", 
            value=selected_concept.get('comentario', ''),
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
                        "ultima_actualizacion": datetime.now()
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
        
        with col2:
            if st.button("🔄 Reset to Original"):
                st.rerun()
        
        with col3:
            if st.button("🗑️ Delete Concept"):
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
                        
                        st.success("✅ Concept deleted successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error deleting concept: {e}")

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
    
    # Tab navigation for relations
    tab1, tab2, tab3 = st.tabs(["➕ Add New Relation", "✏️ Edit Relations", "📊 View Relations"])
    
    with tab1:
        st.subheader("➕ Add New Relation")
        
        # Smart concept selection
        st.write("**Select Concepts:**")
        
        col1, col2 = st.columns(2)
        
        with col1:
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
        
        with col2:
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
        
        col1, col2 = st.columns(2)
        with col1:
            tipo_relacion = st.selectbox("Relation Type", [t.value for t in TipoRelacion], key="new_rel_type")
        with col2:
            descripcion = st.text_area("Description (Optional)", placeholder="Describe the relationship...", key="new_rel_desc")
        
        # Add relation button
        if st.button("🔗 Add Relation", type="primary", key="add_rel_btn"):
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
                        else:
                            st.error("❌ Failed to add relation. Check if both concepts exist.")
                    except Exception as e:
                        st.error(f"❌ Error adding relation: {e}")
            else:
                st.error("❌ Please select both concepts.")
    
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
            st.dataframe(df, use_container_width=True)
            
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
                    grafo.construir_grafo(tipos_relacion=selected_relations)
                    
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

#!/usr/bin/env python3
"""
Interactive Graph Visualization for Manage Relations Section
Provides real-time, clickable graph visualization with MongoDB sync
"""

import networkx as nx
from pyvis.network import Network
import streamlit as st
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

class InteractiveGraphManager:
    """
    Manages interactive graph visualization for the Manage Relations section
    """
    
    def __init__(self, db):
        self.db = db
        self.temp_dir = Path("~/math_knowledge_graphs").expanduser()
        self.temp_dir.mkdir(exist_ok=True)
        
        # Color schemes
        self.node_colors = {
            "definicion": "#2E8B57",      # Sea Green
            "teorema": "#4169E1",         # Royal Blue
            "proposicion": "#FF8C00",     # Dark Orange
            "corolario": "#9932CC",       # Dark Orchid
            "lema": "#FF69B4",            # Hot Pink
            "ejemplo": "#F0E68C",         # Khaki
            "nota": "#D3D3D3",            # Light Gray
            "otro": "#FFFFFF",            # White
            "selected": "#FF4444",        # Red for selected
            "highlighted": "#FFD700"      # Gold for highlighted
        }
        
        self.edge_colors = {
            "implica": "#8B0000",         # Dark Red
            "equivalente": "#B066B3",     # Navy
            "deriva_de": "#800080",       # Purple
            "inspirado_en": "#008080",    # Teal
            "requiere_concepto": "#DC143C", # Crimson
            "contrasta_con": "#FF4500",   # Orange Red
            "contradice": "#000000",      # Black
            "contra_ejemplo": "#696969"   # Dim Gray
        }
        
        self.edge_styles = {
            "implica": "solid",
            "equivalente": "dashed",
            "deriva_de": "dotted",
            "inspirado_en": "dashdot",
            "requiere_concepto": "solid",
            "contrasta_con": "dashed",
            "contradice": "solid",
            "contra_ejemplo": "dotted"
        }
    
    def _apply_style(self, net, profile: str = "full"):
        if profile == "full":
            net.set_options(self.FULL_OPTIONS_JSON)
        else:
            net.set_options(self.FULL_OPTIONS_JSON)  # mismo estilo, solo cambia height si quieres

    def get_graph_data(self, selected_concept_id: Optional[str] = None,
                      selected_concept_source: Optional[str] = None,
                      filter_sources: Optional[List[str]] = None,
                      filter_types: Optional[List[str]] = None,
                      filter_relations: Optional[List[str]] = None) -> Tuple[List[Dict], List[Dict]]:
        """
        Get concepts and relations from MongoDB with optional filtering
        """
        # Build concept query
        concept_query = {}
        if filter_sources:
            concept_query["source"] = {"$in": filter_sources}
        if filter_types:
            concept_query["tipo"] = {"$in": filter_types}
        
        concepts = list(self.db.concepts.find(concept_query))
        
        # Build relation query
        relation_query = {}
        if filter_sources:
            relation_query["$or"] = [
                {"desde": {"$regex": f"@({'|'.join(filter_sources)})$"}},
                {"hasta": {"$regex": f"@({'|'.join(filter_sources)})$"}}
            ]
        if filter_relations:
            relation_query["tipo"] = {"$in": filter_relations}
        
        relations = list(self.db.relations.find(relation_query))
        
        return concepts, relations
    
    def build_interactive_graph(self, concepts: List[Dict], relations: List[Dict],
                               selected_concept_id: Optional[str] = None,
                               selected_concept_source: Optional[str] = None,
                               highlighted_concepts: Optional[List[str]] = None) -> str:
        """
        Build an interactive graph using PyVis
        """
        import streamlit as st

        added_node_ids = set()
        # Create network with basic configuration
        net = Network(height="600px", width="100%", directed=True, 
                     bgcolor="#ffffff", font_color="#000000")
        
        net.force_atlas_2based()
        
        # Enable physics and interaction
        net.show_buttons(filter_=["physics"])
        
        # For very small graphs, use a simple HTML fallback
        if len(concepts) <= 1 and len(relations) <= 1:
            st.info("📊 Using simple HTML preview for very small graph")
            # Create a simple HTML fallback for very small graphs
            fallback_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>Simple Graph Preview</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .graph-container {{ 
                        border: 2px solid #ccc; 
                        padding: 20px; 
                        border-radius: 10px;
                        background: #f9f9f9;
                        text-align: center;
                    }}
                    .node {{ 
                        display: inline-block; 
                        margin: 10px; 
                        padding: 10px; 
                        border: 2px solid #333; 
                        border-radius: 5px;
                        background: white;
                        min-width: 150px;
                    }}
                    .edge {{ 
                        display: inline-block; 
                        margin: 10px; 
                        font-size: 18px; 
                        color: #666;
                    }}
                    .relation-type {{ 
                        background: #007bff; 
                        color: white; 
                        padding: 5px 10px; 
                        border-radius: 15px; 
                        font-size: 12px;
                        margin: 5px;
                    }}
                    #mynetwork {{
                        width: 100%;
                        height: 400px;
                        border: 1px solid lightgray;
                        background: #f9f9f9;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        flex-direction: column;
                    }}
                </style>
            </head>
            <body>
                <div id="mynetwork">
                    <div class="graph-container">
                        <h3>Preview: Relation Being Created</h3>
                        <div>
            """
            
            # Add nodes and edges
            for i, concept in enumerate(concepts):
                # Handle None concepts gracefully
                if concept is None:
                    continue
                
                # Use safe access with fallbacks
                concept_id = concept.get('id', f'unknown_{i}')
                concept_source = concept.get('source', 'unknown_source')
                concept_titulo = concept.get('titulo', concept_id)
                concept_tipo = concept.get('tipo', 'unknown')
                
                node_color = "#ff4444" if (concept_id == selected_concept_id and concept_source == selected_concept_source) else "#4CAF50"
                fallback_html += f"""
                        <div class="node" style="border-color: {node_color};">
                            <strong>{concept_titulo}</strong><br>
                            <small>{concept_tipo} - {concept_source}</small>
                        </div>
                """
                
                if i < len(relations):
                    rel = relations[i]
                    fallback_html += f"""
                        <div class="edge">
                            <span class="relation-type">{rel['tipo']}</span><br>
                            →
                        </div>
                    """
            
            fallback_html += """
                    </div>
                    <p><em>This is a simple preview. The full interactive graph will be available after creation.</em></p>
                </div>
            </div>
            </body>
            </html>
            """
            
            # Write fallback HTML
            fallback_file = self.temp_dir / f"fallback_graph_{len(concepts)}_{len(relations)}.html"
            with open(fallback_file, 'w', encoding='utf-8') as f:
                f.write(fallback_html)
            
            return str(fallback_file)
        
        # Add nodes
        skipped_concepts = 0
        added_nodes = 0
        added_edges = 0  # Initialize here
        
        # Debug: Show what we're processing
        import streamlit as st
        #st.info(f"🔍 Processing {len(concepts)} concepts and {len(relations)} relations")
        
        for concept in concepts:
            # Handle None concepts gracefully
            if concept is None:
                skipped_concepts += 1
                continue
            
            # Use safe access with fallbacks
            concept_id = concept.get('id', 'unknown')
            concept_source = concept.get('source', 'unknown_source')
            title = concept.get('titulo', concept_id)
            tipo = concept.get('tipo', 'otro')
            
            node_id = f"{concept_id}@{concept_source}"
            
            # Debug: Show node being added
            #st.write(f"➕ Adding node: {node_id} ({title})")
            
            # Determine node color
            if (selected_concept_id and selected_concept_source and 
                concept_id == selected_concept_id and concept_source == selected_concept_source):
                color = self.node_colors["selected"]
                size = 30
            elif highlighted_concepts and node_id in highlighted_concepts:
                color = self.node_colors["highlighted"]
                size = 25
            else:
                color = self.node_colors.get(tipo, self.node_colors["otro"])
                size = 20
            
            # Create tooltip with metadata
            comentario = concept.get('comentario', 'No comment')
            if comentario and len(comentario) > 100:
                comentario = comentario[:100] + "..."
            
            categorias = concept.get('categorias', [])
            categorias_str = ', '.join(categorias) if categorias else 'No categories'
            
            tooltip = f"""
            <div style='font-family: Arial; font-size: 12px;'>
                <b>{title}</b><br>
                <b>ID:</b> {concept_id}<br>
                <b>Type:</b> {tipo}<br>
                <b>Source:</b> {concept_source}<br>
                <b>Categories:</b> {categorias_str}<br>
                <b>Comment:</b> {comentario}
            </div>
            """
            
            if node_id not in added_node_ids:
                net.add_node(node_id, 
                        label=title[:30] + "..." if len(title) > 30 else title,
                        title=tooltip,
                        color=color,
                        size=size,
                        font={"size": 12, "face": "Arial"},
                        borderWidth=2,
                        borderColor="#000000")
                added_node_ids.add(node_id)
            else:
                pass
                #st.warning(f"⚠️ Duplicate node ID skipped: {node_id}")
            
            added_nodes += 1
        
        # Log graph generation summary
        if skipped_concepts > 0:
            st.warning(f"⚠️ Skipped {skipped_concepts} None concepts during graph generation")
        
        #st.success(f"✅ Graph generated with {added_nodes} nodes and {added_edges} edges")
        
        # Add edges
        for relation in relations:
            desde = relation["desde"]
            hasta = relation["hasta"]
            tipo_rel = relation["tipo"]
            
            # Debug: Show edge being processed
            #st.write(f"🔗 Processing edge: {desde} --[{tipo_rel}]--> {hasta}")
            
            # Check if both nodes exist (handle None concepts)
            valid_node_ids = []
            for c in concepts:
                if c is not None:
                    valid_node_ids.append(f"{c.get('id', 'unknown')}@{c.get('source', 'unknown_source')}")
            
            if desde in valid_node_ids and hasta in valid_node_ids:
                #st.write(f"✅ Adding edge: {desde} --[{tipo_rel}]--> {hasta}")
                
                color = self.edge_colors.get(tipo_rel, "#000000")
                style = self.edge_styles.get(tipo_rel, "solid")
                
                # Create edge tooltip
                tooltip = f"""
                <div style='font-family: Arial; font-size: 12px;'>
                    <b>Relation Type:</b> {tipo_rel}<br>
                    <b>From:</b> {desde}<br>
                    <b>To:</b> {hasta}<br>
                    <b>Description:</b> {relation.get('descripcion', 'No description')[:100]}...
                </div>
                """
                
                # Add edge with error handling
                try:
                    net.add_edge(desde, hasta,
                                title=tooltip,
                                color=color,
                                width=3,
                                arrows="to",
                                dashes=True if style == "dashed" else False,
                                length=200)
                    added_edges += 1
                    #st.write(f"✅ Edge added successfully")
                except Exception as edge_error:
                    st.error(f"❌ Failed to add edge: {edge_error}")
            else:
                st.warning(f"⚠️ Skipping edge: {desde} --[{tipo_rel}]--> {hasta} (nodes not found)")
                #st.write(f"   Valid nodes: {valid_node_ids}")
        
        # Configure network options for better interactivity
        net.set_options("""
        {
          "physics": {
            "forceAtlas2Based": {
              "gravitationalConstant": -50,
              "centralGravity": 0.01,
              "springLength": 100,
              "springConstant": 0.08
            },
            "maxVelocity": 50,
            "minVelocity": 0.1,
            "solver": "forceAtlas2Based",
            "timestep": 0.35
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true,
            "tooltipDelay": 200
          },
          "edges": {
            "smooth": {
              "type": "continuous"
            },
            "color": {
              "inherit": false
            },
            "width": 3,
            "arrows": {
              "to": {
                "enabled": true,
                "scaleFactor": 1
              }
            }
          },
          "nodes": {
            "font": {
              "size": 12,
              "face": "Arial"
            },
            "borderWidth": 2,
            "borderColor": "#000000",
            "shadow": {
              "enabled": true,
              "color": "rgba(0,0,0,0.3)",
              "size": 10,
              "x": 5,
              "y": 5
            }
          }
        }
        """)
        
        # Generate unique filename
        graph_file = self.temp_dir / f"interactive_graph_{len(concepts)}_{len(relations)}.html"
        
        # Check if we have any valid nodes to render
        if added_nodes == 0:
            st.warning("⚠️ No valid nodes to display. Creating empty graph placeholder.")
            #return self._generate_empty_html(concepts, relations)
            
        try:
            net.show(str(graph_file))  
            net.write_html(str(graph_file))
            with open(graph_file, "r", encoding="utf-8") as f:
                content = f.read()
                if '<div id="mynetwork"' not in content:
                    pass
                    #st.warning("⚠️ PyVis generated HTML without network container")
                    raise ValueError("Missing <div id='mynetwork'> in output HTML")

            
            # Verify the file was created and has content
            import os
            if os.path.exists(graph_file):
                file_size = os.path.getsize(graph_file)
                if file_size > 0:
                    # Verify the HTML contains the network container
                    with open(graph_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    #if all(tag in content for tag in ['<html', '<body', '<div id="mynetwork"', 'new vis.Network']):
                    if '<div id="mynetwork"' in content and 'new vis.Network' in content:
                        st.success("✅ PyVis graph generated successfully")
                        return str(graph_file)
                    else:
                        st.warning("⚠️ PyVis generated HTML is incomplete")
                        raise Exception("PyVis HTML missing required sections")
                else:
                    raise Exception(f"Generated file is empty ({file_size} bytes)")
            else:
                raise Exception("Generated file does not exist")
                
        except Exception as e:
            #st.warning(f"⚠️ PyVis generation failed: {e}. Using fallback HTML.")
            # If Pyvis fails, try to create a simple fallback
            try:
                fallback_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Graph Fallback</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 20px; }}
                        .graph-container {{ 
                            border: 2px solid #ccc; 
                            padding: 20px; 
                            border-radius: 10px;
                            background: #f9f9f9;
                            text-align: center;
                        }}
                        .node {{ 
                            display: inline-block; 
                            margin: 10px; 
                            padding: 10px; 
                            border: 2px solid #333; 
                            border-radius: 5px;
                            background: white;
                            min-width: 150px;
                        }}
                        .edge {{ 
                            display: inline-block; 
                            margin: 10px; 
                            font-size: 18px; 
                            color: #666;
                        }}
                        #mynetwork {{
                            width: 100%;
                            height: 400px;
                            border: 1px solid lightgray;
                            background: #f9f9f9;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            flex-direction: column;
                        }}
                    </style>
                </head>
                <body>
                    <div id="mynetwork">
                        <div class="graph-container">
                            <p><strong>Concepts:</strong> {len(concepts)}</p>
                            <p><strong>Relation:</strong> {tipo_rel}</p>
                            <div>
                """
                
                # Add nodes
                for concept in concepts:
                    if concept is not None:
                        concept_id = concept.get('id', 'unknown')
                        concept_titulo = concept.get('titulo', concept_id)
                        concept_tipo = concept.get('tipo', 'unknown')
                        concept_source = concept.get('source', 'unknown')
                        
                        fallback_html += f"""
                            <div class="node">
                                <strong>{concept_titulo}</strong><br>
                                <small>{concept_tipo} - {concept_source}</small>
                            </div>
                        """
                
                fallback_html += """
                        </div>
                    </div>
                </div>
                </body>
                </html>
                """
                
                # Write fallback HTML
                fallback_file = self.temp_dir / f"fallback_graph_{len(concepts)}_{len(relations)}.html"
                with open(fallback_file, 'w', encoding='utf-8') as f:
                    f.write(fallback_html)
                
                return str(fallback_file)
                
            except Exception as fallback_error:
                raise Exception(f"Failed to generate graph: {e}. Fallback also failed: {fallback_error}")
    
    def render_graph_in_streamlit(self, graph_file: str, 
                                 concepts: List[Dict],
                                 relations: List[Dict],
                                 selected_concept_id: Optional[str] = None,
                                 selected_concept_source: Optional[str] = None,
                                 unique_suffix: Optional[str] = None) -> None:
        """
        Render the interactive graph in Streamlit with controls
        """
        if not graph_file or not os.path.exists(graph_file):
            st.error("❌ El archivo del grafo no existe o es inválido.")
            return
        # Generate unique keys for buttons
        if unique_suffix is None:
            import hashlib
            unique_suffix = hashlib.md5(graph_file.encode()).hexdigest()[:8]
        
        refresh_key = f"refresh_graph_{unique_suffix}"
        fullscreen_key = f"fullscreen_graph_{unique_suffix}"
        
        # Graph controls
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown("**🎯 Graph Controls:**")
        
        with col2:
            if st.button("🔄 Refresh Graph/ Create Graph", key=refresh_key):
                st.rerun()
        
        #with col3:
        #    if st.button("📊 Full Screen", key=fullscreen_key):
        #        st.markdown(f"""
        #        <script>
        #            window.open('{graph_file}', '_blank', 'width=1200,height=800');
        #        </script>
        #        """, unsafe_allow_html=True)
        
        # Display the graph
        try:
            with open(graph_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Debug: Check if HTML content is valid
            #st.info(f"📄 Graph file loaded: {len(html_content)} bytes")
            
            if len(html_content) < 100:
                st.error(f"❌ HTML content is too small ({len(html_content)} bytes). File may be empty or corrupted.")
                st.code(html_content, language='html')
                return
            
            # Debug: Check HTML structure
            if '<html>' not in html_content:
                st.error("❌ HTML file does not contain <html> tag")
                st.code(html_content[:500], language='html')
                return
            
            if '<div id="mynetwork"' in html_content or 'vis.Network' in html_content:
                pass
                #st.info("✅ Network container found or PyVis initialized.")
            else:
                st.warning("⚠️ Network container not explicitly found. Rendering anyway.")
                
        except Exception as e:
            st.error(f"❌ Error reading graph file: {e}")
            return
        
        # Add interactive features and styling
        interactive_script = """
        <script>
        // Wait for the network to be ready
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, looking for network container...');
            
            // Find the network container
            var networkContainer = document.querySelector('#mynetwork');
            if (networkContainer) {
                console.log('Network container found');
                
                // Wait a bit for vis.js to initialize
                setTimeout(function() {
                    if (window.vis && window.vis.Network) {
                        // Get the network instance
                        var network = window.vis.Network.getNetwork(networkContainer);
                        if (network) {
                            console.log('Network instance found, adding event listeners');
                            
                            // Add click event listener
                            network.on('click', function(params) {
                                if (params.nodes.length > 0) {
                                    var nodeId = params.nodes[0];
                                    var node = network.body.data.nodes.get(nodeId);
                                    
                                    // Show tooltip with node info
                                    showNodeTooltip(node, params.pointer.DOM);
                                }
                            });
                            
                            // Add hover event listener
                            network.on('hoverNode', function(params) {
                                var node = network.body.data.nodes.get(params.node);
                                showNodeTooltip(node, params.event.center);
                            });
                            
                            // Hide tooltip when not hovering
                            network.on('blurNode', function(params) {
                                hideNodeTooltip();
                            });
                            
                            // Log network data for debugging
                            console.log('Network data:', {
                                nodes: network.body.data.nodes.length,
                                edges: network.body.data.edges.length
                            });
                        } else {
                            console.log('Network instance not found');
                        }
                    } else {
                        console.log('vis.js not available');
                    }
                }, 1000);
            } else {
                console.log('Network container not found');
            }
        });
        
        // Tooltip functions
        function showNodeTooltip(node, position) {
            var tooltip = document.getElementById('node-tooltip');
            if (!tooltip) {
                tooltip = document.createElement('div');
                tooltip.id = 'node-tooltip';
                tooltip.style.cssText = `
                    position: fixed;
                    background: white;
                    border: 1px solid #ccc;
                    padding: 10px;
                    border-radius: 5px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.3);
                    max-width: 300px;
                    z-index: 1000;
                    font-family: Arial, sans-serif;
                    font-size: 12px;
                    pointer-events: none;
                `;
                document.body.appendChild(tooltip);
            }
            
            tooltip.innerHTML = node.title || 'No information available';
            tooltip.style.left = (position.x + 10) + 'px';
            tooltip.style.top = (position.y - 10) + 'px';
            tooltip.style.display = 'block';
        }
        
        function hideNodeTooltip() {
            var tooltip = document.getElementById('node-tooltip');
            if (tooltip) {
                tooltip.style.display = 'none';
            }
        }
        </script>
        """
        
        # Add interactive features to the HTML
        if '</body>' in html_content:
            html_content = html_content.replace(
                '</body>',
                interactive_script + '</body>'
            )
            #st.info("✅ Interactive script added to HTML")
        else:
            st.warning("⚠️ Could not find </body> tag to add interactive script")
        
        # Add Streamlit-specific styling and tips
        if '</body>' in html_content:
            html_content = html_content.replace(
                '</body>',
                '''
                <div style="margin-top: 10px; font-size: 12px; color: #666; text-align: center;">
                </div>
                </body>
                ''')
            #st.info("✅ Tips injected before </body>")
        else:
            st.warning("⚠️ Could not find network container to add tips")
        
        # Debug: Show final HTML size
        #st.info(f"📄 Final HTML size: {len(html_content)} bytes")
        
        # Render the graph with error handling
        try:
            st.components.v1.html(html_content, height=650, scrolling=False)
            #st.success("✅ Graph rendered successfully")
        except Exception as e:
            st.error(f"❌ Error rendering graph: {e}")
            # Fallback: show raw HTML
            with st.expander("🔍 Raw HTML Content", expanded=False):
                st.code(html_content[:2000], language='html')
        
        # Graph statistics
        #with st.expander("📊 Graph Statistics", expanded=False):
        #    col1, col2, col3, col4 = st.columns(4)
            
        #    with col1:
        #        st.metric("Total Nodes", len(concepts) if 'concepts' in locals() else 0)
            
        #    with col2:
        #        st.metric("Total Edges", len(relations) if 'relations' in locals() else 0)
            
        #    with col3:
        #        if selected_concept_id:
        #            st.metric("Selected Node", f"{selected_concept_id}@{selected_concept_source}")
        #        else:
        #            st.metric("Selected Node", "None")
            
        #    with col4:
        #        st.metric("Graph Density", f"{len(relations) / max(len(concepts), 1):.2f}")
    
    def get_related_concepts(self, concept_id: str, concept_source: str, 
                           relation_type: Optional[str] = None) -> List[Dict]:
        """
        Get concepts related to a specific concept
        """
        concept_node = f"{concept_id}@{concept_source}"
        
        # Find incoming and outgoing relations
        query = {
            "$or": [
                {"desde": concept_node},
                {"hasta": concept_node}
            ]
        }
        
        if relation_type:
            query["tipo"] = relation_type
        
        relations = list(self.db.relations.find(query))
        
        # Get related concept IDs
        related_ids = set()
        for rel in relations:
            if rel["desde"] == concept_node:
                related_ids.add(rel["hasta"])
            else:
                related_ids.add(rel["desde"])
        
        # Get concept details
        related_concepts = []
        for node_id in related_ids:
            parts = node_id.split('@')
            concept = self.db.concepts.find_one({"id": parts[0], "source": parts[1]})
            if concept:
                related_concepts.append(concept)
        
        return related_concepts
    
    def cleanup_temp_files(self):
        """
        Clean up temporary graph files
        """
        try:
            for file in self.temp_dir.glob("*.html"):
                if file.exists():
                    file.unlink()
        except Exception as e:
            st.warning(f"Could not cleanup temp files: {e}")
    
    def _generate_empty_html(self, concepts, relations):
        graph_file = self.temp_dir / f"empty_graph_{len(concepts)}_{len(relations)}.html"
        empty_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Empty Graph</title>
    </head>
    <body>
        <div id="mynetwork">
            <h3>No Graph to Display</h3>
            <p><strong>Concepts:</strong> {len(concepts)}</p>
            <p><strong>Relations:</strong> {len(relations)}</p>
        </div>
    </body>
    </html>
    """
        with open(graph_file, 'w', encoding='utf-8') as f:
            f.write(empty_html)
        return str(graph_file)

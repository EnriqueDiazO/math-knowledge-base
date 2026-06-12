import html as html_lib
import json
import math
import urllib.parse

import networkx as nx
from pyvis.network import Network


class GrafoConocimiento:
    """Clase para construir y visualizar grafos de conocimiento
    usando los datos de MathMongo (conceptos + relaciones).
    """

    def __init__(self, conceptos: list[dict], relaciones: list[dict]) -> None:
        self.conceptos = conceptos
        self.relaciones = relaciones
        self.MaxLengthLabel=20
        self.MaxLinesLabel=6
        self.G = nx.MultiDiGraph()

        self.color_por_tipo = {
            "definicion": "#b5e8b8",      # green dark
            "definición": "#b5e8b8",
            "definition": "#b5e8b8",
            "teorema": "#eceb98",         # blue
            "theorem": "#eceb98",
            "proposicion": "#00E7EF",     # orange
            "proposición": "#00E7EF",
            "proposition": "#00E7EF",
            "corolario": "#D5BFE2",       # purple
            "corollary": "#D5BFE2",
            "lema": "#F17A7A",            # rose
            "lemma": "#F17A7A",
            "ejemplo": "#F9A825",         # yellow
            "example": "#F9A825",
            "observacion": "#D7CCC8",      # soft brown-gray
            "observación": "#D7CCC8",
            "remark": "#D7CCC8",
            "nota": "#B0BEC5",            # blue-gray (nuevo)
            "otro": "#E0E0E0",
            "placeholder": "#F5F5F5"      # aún más tenue
        }


        # Colores por tipo de relación
        self.color_por_relacion = {
            "implica": "indigo",
            "equivalente": "navy",
            "deriva_de": "purple",
            "inspirado_en": "teal",
            "requiere_concepto": "crimson",
            "contrasta_con": "orange",
            "contradice": "black",
            "contra_ejemplo": "gray"
        }

        self.forma_por_tipo = {
            "definicion": "box",
            "definición": "box",
            "definition": "box",
            "teorema": "ellipse",
            "theorem": "ellipse",
            "proposicion": "box",
            "proposición": "box",
            "proposition": "box",
            "corolario": "triangleDown_svg",# <- SVG
            "corollary": "triangleDown_svg",
            "lema": "triangle_svg",         # <- SVG
            "lemma": "triangle_svg",
            "ejemplo": "diamond_svg",   # <- SVG
            "example": "diamond_svg",
            "observacion": "box",
            "observación": "box",
            "remark": "box",
            "nota": "hexagon_svg",          # <- SVG
            "otro": "circle",
            "placeholder": "dot"
        }

        self.abreviatura_por_tipo = {
            "definicion": "def",
            "definición": "def",
            "definition": "def",
            "teorema": "teo",
            "theorem": "teo",
            "proposicion": "prop",
            "proposición": "prop",
            "proposition": "prop",
            "ejemplo": "ejem",
            "example": "ejem",
            "corolario": "cor",
            "corollary": "cor",
            "lema": "lem",
            "lemma": "lem",
            "observacion": "obs",
            "observación": "obs",
            "remark": "obs",
            "nota": "nota",
            "note": "nota",
        }

    def _svg_data_uri(self, svg: str) -> str:
        # Importante: encodear para usarlo como data URI
        return "data:image/svg+xml;charset=utf-8," + urllib.parse.quote(svg)

    def _estimate_text_width_px(self, lines: list[str], font_size: int = 45) -> int:
        # Estimación razonable sin medir en canvas:
        # ~0.58em por carácter (depende de la fuente, pero funciona bien)
        if not lines:
            return 120
        max_chars = max(len(line) for line in lines)
        return int(max(120, min(520, max_chars * font_size * 0.58)))


    def _make_svg_polygon_node(self, wrapped_label: str, fill: str, kind: str, type_badge: str = "") -> str:
        """kind: 'hexagon' | 'diamond' | 'triangle' | 'triangleDown'
        Devuelve un data URI (SVG) con el texto SIEMPRE dentro.
        """  # noqa: D205
        font_size = 45
        badge_font_size = 24
        padding_x = 22
        padding_y = 18
        line_gap = 6

        lines = wrapped_label.split("\n") if wrapped_label else [""]
        text_w = self._estimate_text_width_px(lines, font_size=font_size)
        badge_w = len(type_badge) * badge_font_size * 0.62 + 30 if type_badge else 0
        line_h = font_size + line_gap
        text_h = len(lines) * line_h

        width = max(text_w, badge_w) + 2 * padding_x
        badge_h = badge_font_size + 16 if type_badge else 0
        badge_gap = 8 if type_badge else 0
        height = text_h + badge_h + badge_gap + 2 * padding_y

        # límites por seguridad (evita nodos gigantes)
        width = int(max(200, min(620, width)))
        height = int(max(250, min(360, height)))

        stroke = "#6b7280"  # gris neutro
        stroke_w = 2

        # Coordenadas del polígono (en px)
        if kind == "hexagon":
            cut = max(22, min(50, width * 0.18))
            pts = [
            (cut, 0),
            (width - cut, 0),
            (width, height / 2),
            (width - cut, height),
            (cut, height),
            (0, height / 2),]
        elif kind == "diamond":
            pts = [
            (width / 2, 0),
            (width, height / 2),
            (width / 2, height),
            (0, height / 2),]
        elif kind == "triangle":
            # punta arriba
            pts = [
            (width / 2, 0),
            (width, height),
            (0, height),
        ]
        elif kind == "triangleDown":
            # punta abajo
            pts = [
            (0, 0),
            (width, 0),
            (width / 2, height),]

        else:
            # fallback: box-like polygon
            pts = [(0, 0), (width, 0), (width, height), (0, height)]
        
        points_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        # Texto centrado: usamos dominant-baseline para que quede bien
        # Empezamos y centramos verticalmente con un offset calculado.
        total_text_h = len(lines) * line_h
        content_h = total_text_h + badge_h + badge_gap
        start_y = (height - content_h) / 2 + badge_h + badge_gap + font_size  # primera línea

        # Escapar XML básico
        def esc(s: str) -> str:
            return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        text_items = []
        if type_badge:
            badge_x = width / 2
            badge_y = (height - content_h) / 2
            badge_width = max(48, badge_w)
            badge_height = badge_font_size + 10
            text_items.append(
                f'<rect x="{badge_x - badge_width / 2:.1f}" y="{badge_y:.1f}" '
                f'width="{badge_width:.1f}" height="{badge_height:.1f}" rx="8" '
                f'fill="#ffffff" opacity="0.72" stroke="#6b7280" stroke-width="1" />'
                f'<text x="{badge_x:.1f}" y="{badge_y + badge_font_size:.1f}" text-anchor="middle" '
                f'font-family="Arial, sans-serif" font-size="{badge_font_size}" '
                f'font-weight="700" fill="#374151">{esc(type_badge)}</text>'
            )
        y = start_y
        for line in lines:
            text_items.append(
                 f'<text x="{width/2:.1f}" y="{y:.1f}" text-anchor="middle" '
                 f'font-family="Arial, sans-serif" font-size="{font_size}" fill="#111827">{esc(line)}</text>'
            )
            y += line_h

        scale = 3  # 2 o 3 normalmente basta
        svg = f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="{width*scale}" height="{height*scale}"
             viewBox="0 0 {width} {height}">
             <polygon points="{points_str}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}" />
             {"".join(text_items)}
        </svg>
        """.strip()

        return self._svg_data_uri(svg)

    def _node_render_strategy(self, tipo: str) -> str:
        """Decide si renderizamos con vis.js nativo o con SVG."""
        shape = self.forma_por_tipo.get(str(tipo or "").strip().lower(), "circle")
        if shape.endswith("_svg"):
            return "svg"
        return "native"

    def _native_shape(self, tipo: str) -> str:
        shape = self.forma_por_tipo.get(str(tipo or "").strip().lower(), "circle")
        # Normaliza: si viene 'hexagon_svg' -> 'hexagon' (no lo usaremos en native, pero por limpieza)
        return shape.replace("_svg", "")


    def _concepto_permitido(self, tipo: str, tipos_concepto: list[str] | None) -> bool:
        if not tipos_concepto:
            return True
        tipo_key = str(tipo or "").strip().lower()
        allowed = {str(t or "").strip().lower() for t in tipos_concepto}
        return tipo_key in allowed

    def _node_type_value(self, node: dict) -> str:
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        for value in (
            node.get("tipo"),
            node.get("concept_type"),
            node.get("type"),
            node.get("node_type"),
            node.get("category"),
            node.get("kind"),
            node.get("label_type"),
            metadata.get("type"),
        ):
            if value is not None and str(value).strip():
                return str(value).strip()
        return "otro"

    def _node_type_abbreviation(self, tipo: str) -> str:
        return self.abreviatura_por_tipo.get(str(tipo or "").strip().lower(), "")

    def _node_label_with_badge(self, wrapped_label: str, type_badge: str) -> str:
        if not type_badge:
            return wrapped_label
        return f"<b>{type_badge}</b>\n{wrapped_label}"

    def _node_source(self, node_id: str) -> str:
        if "@" not in node_id:
            return ""
        return node_id.rsplit("@", 1)[1]

    def _group_centers(self, groups: list[str], radius: int = 620) -> dict[str, dict[str, float]]:
        if not groups:
            return {}
        if len(groups) == 1:
            return {groups[0]: {"x": 0.0, "y": 0.0}}
        centers = {}
        for idx, group in enumerate(groups):
            angle = (2 * math.pi * idx) / len(groups)
            centers[group] = {
                "x": round(math.cos(angle) * radius, 2),
                "y": round(math.sin(angle) * radius, 2),
            }
        return centers

    def _offset_for_index(self, idx: int, count: int, spacing: int = 145) -> tuple[float, float]:
        cols = max(1, math.ceil(math.sqrt(count)))
        row = idx // cols
        col = idx % cols
        rows = math.ceil(count / cols)
        x = (col - (cols - 1) / 2) * spacing
        y = (row - (rows - 1) / 2) * spacing
        return round(x, 2), round(y, 2)

    def _positions_by_group(self, group_by_node: dict[str, str], radius: int = 620) -> dict[str, dict[str, float]]:
        grouped: dict[str, list[str]] = {}
        for node_id, group in group_by_node.items():
            grouped.setdefault(group or "sin grupo", []).append(node_id)

        centers = self._group_centers(sorted(grouped), radius=radius)
        positions = {}
        for group, node_ids in grouped.items():
            sorted_nodes = sorted(node_ids)
            center = centers[group]
            for idx, node_id in enumerate(sorted_nodes):
                ox, oy = self._offset_for_index(idx, len(sorted_nodes))
                positions[node_id] = {
                    "x": round(center["x"] + ox, 2),
                    "y": round(center["y"] + oy, 2),
                }
        return positions

    def _layout_payload(self) -> dict[str, dict]:
        nodes = sorted(self.G.nodes)
        type_by_node = {node_id: str(self.G.nodes[node_id].get("tipo", "otro")) for node_id in nodes}
        source_by_node = {node_id: self._node_source(node_id) for node_id in nodes}

        component_by_node = {}
        for idx, component in enumerate(nx.connected_components(self.G.to_undirected())):
            for node_id in component:
                component_by_node[node_id] = f"componente {idx + 1}"

        return {
            "byType": self._positions_by_group(type_by_node, radius=680),
            "byComponent": self._positions_by_group(component_by_node, radius=720),
            "bySource": self._positions_by_group(source_by_node, radius=680),
            "meta": {
                node_id: {
                    "type": type_by_node.get(node_id, ""),
                    "source": source_by_node.get(node_id, ""),
                    "component": component_by_node.get(node_id, ""),
                }
                for node_id in nodes
            },
        }

    def _relation_value(self, rel: dict) -> str:
        for key in ("tipo", "relation", "relationship", "label", "type", "edge_type", "predicate", "title", "kind"):
            value = rel.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return "relaciona"

    def _relation_label(self, relation_value: str) -> str:
        label = str(relation_value or "").replace("_", " ").strip()
        return label or "relaciona"

    def _ensure_placeholder(self, node_id: str) -> None:
        if node_id in self.G.nodes:
            return
        label = node_id
        if len(label) > self.MaxLengthLabel:
            label = label[:self.MaxLengthLabel] + "..."
        self.G.add_node(node_id, label=label, tipo="placeholder", color="#F0F0F0")

    def _wrap_label(self, text: str, max_chars: int | None = None, max_lines : int | None = None) -> str:
        """Convierte un texto en multilínea usando \\n para que vis.js lo renderice con saltos.
        - max_chars: ancho aproximado por línea
        - max_lines: límite de líneas (para evitar nodos gigantes).
        """  # noqa: D202, D205, D301

        if not text:
            return ""

        if max_chars is None:
            max_chars = self.MaxLengthLabel

        if max_lines is None:
            max_lines = self.MaxLinesLabel

        words = text.split()
        lines = []
        current = ""

        for w in words:
            if len(current) + (1 if current else 0) + len(w) <= max_chars:
                current = f"{current} {w}".strip()
            else:
                lines.append(current)
                current = w
                if len(lines) >= max_lines:
                    break

        if len(lines) < max_lines and current:
            lines.append(current)

        # Si truncamos por max_lines, agrega "..."
        joined = "\n".join(lines)
        #if len(words) > 0 and (" ".join(lines).strip() != text):
            #if not joined.endswith("..."):
            #    joined = joined.rstrip(".") + "..."
        return joined

    def _shape_permitida_para_texto(self, shape: str) -> bool:
        # Shapes que se llevan bien con texto multilínea en vis.js
        return shape in {"box", "ellipse", "diamond", "hexagon", "triangle", "triangleDown", "circle"}




    def construir_grafo(self, tipos_relacion: list[str] = None, tipos_concepto: list[str] = None)  -> None:
        """Crea el grafo con los conceptos y relaciones."""
        usar_placeholders = not tipos_concepto  # True si None o []
        relaciones_omitidas_por_nodos_faltantes = 0
        ejemplos_omitidos = []

        self.G.clear()

        # Crear nodos
        for doc in self.conceptos:
            tipo = self._node_type_value(doc)
            if not self._concepto_permitido(tipo, tipos_concepto):
                continue

            etiqueta = f"{doc['id']}@{doc['source']}"
            titulo = doc.get("titulo", etiqueta)
            color = self.color_por_tipo.get(str(tipo or "").strip().lower(), "white")
            type_badge = self._node_type_abbreviation(tipo)
            self.G.add_node(etiqueta, label=titulo, tipo=tipo, type_badge=type_badge, color=color)

        # Crear aristas
        for rel in self.relaciones:
            # Detectar el formato de relaciones
            if "desde" in rel and "hasta" in rel:
                desde = rel["desde"]
                hasta = rel["hasta"]
            else:
                desde = f"{rel['desde_id']}@{rel['desde_source']}"
                hasta = f"{rel['hasta_id']}@{rel['hasta_source']}"

            tipo_rel = self._relation_value(rel)
            # 🔎 Filtrar si se pidió solo ciertos tipos
            if tipos_relacion and tipo_rel not in tipos_relacion:
                continue

            color = self.color_por_relacion.get(tipo_rel, "black")
            relation_label = self._relation_label(tipo_rel)

            falta_desde = desde not in self.G.nodes
            falta_hasta = hasta not in self.G.nodes

            if falta_desde or falta_hasta:
                relaciones_omitidas_por_nodos_faltantes += 1
                ejemplos_omitidos.append((desde, tipo_rel, hasta, falta_desde, falta_hasta))

                if usar_placeholders:
                    if falta_desde:
                        self._ensure_placeholder(desde)
                    if falta_hasta:
                        self._ensure_placeholder(hasta)
                else:
                    continue

            # agregar SIEMPRE la arista (ya existen los nodos: reales o placeholder)
            self.G.add_edge(
                desde,
                hasta,
                key=tipo_rel,
                tipo=tipo_rel,
                label=relation_label,
                color=color,
                descripcion=rel.get("descripcion", ""),
            )
        print("DEBUG tipos_concepto:", tipos_concepto, "usar_placeholders:", usar_placeholders)
        print(f"🧠 Nodos creados: {len(self.G.nodes)} | Relaciones creadas: {len(self.G.edges)}")
        if relaciones_omitidas_por_nodos_faltantes > 0:
            print(f"⚠️  Relaciones con placeholders por nodos faltantes: {relaciones_omitidas_por_nodos_faltantes}")
            if ejemplos_omitidos:
                print("⚠️  Ejemplos (placeholders usados):")
            for d, t, h, fd, fh in ejemplos_omitidos:
                faltan = []
                if fd: faltan.append("desde")
                if fh: faltan.append("hasta")
                print(f"   - {d} -({t})-> {h}   [faltan: {', '.join(faltan)}]")


    def exportar_html(self, salida="grafo_conceptos.html", size: int | None = None) -> None:
        """Genera un archivo HTML interactivo."""
        if size is None:
            size = self.MaxLengthLabel
        net = Network(height="100vh", width="100%", directed=True)
        layout_payload = self._layout_payload()
        initial_positions = layout_payload["byType"]

        for n, datos in self.G.nodes(data=True):
            raw_label = datos.get("label", n)
            tipo = datos.get("tipo", "otro")
            type_badge = datos.get("type_badge", "")
            color = datos.get("color", "white")
            position = initial_positions.get(n, {"x": 0, "y": 0})
            wrapped_label = self._wrap_label(raw_label)
            strategy = self._node_render_strategy(tipo)
            tooltip = f"<b>{html_lib.escape(str(raw_label))}</b><br>Tipo: {html_lib.escape(str(tipo))}"
            if type_badge:
                tooltip = f"{tooltip} ({html_lib.escape(str(type_badge))})"

            if strategy == "svg":
                logical_shape = self._native_shape(tipo)  # e.g. "hexagon" de "hexagon_svg"
                # Mapeo: vis no tiene hexagon "real" para texto, pero nosotros sí por SVG
                svg_kind = logical_shape
                # Si por alguna razón no coincide, fuerza un fallback
                if svg_kind not in {"hexagon", "diamond", "triangle", "triangleDown"}:
                    svg_kind = "hexagon"

                img_uri = self._make_svg_polygon_node(
                    wrapped_label=wrapped_label,
                    fill=color,
                    kind=svg_kind,
                    type_badge=type_badge,
                )

                net.add_node(
                    n,
                    shape="image",
                    image=img_uri,
                    label="",
                    font={"size": 0, "color": "rgba(0,0,0,0)"},                # 👈 importante: NO string vacío
                    title=tooltip,           # 👈 tooltip con texto humano
                    x=position["x"],
                    y=position["y"],
                    fixed=False,
                    size=38,   # ajusta 24–40
                    shapeProperties={"useImageSize": False}
                )
            else:
                # Nativo (rápido, y queda bien para box/ellipse/circle/dot)
                shape = self._native_shape(tipo)
                net.add_node(
                    n,
                    label=self._node_label_with_badge(wrapped_label, type_badge),
                    title=tooltip,
                    color=color,
                    shape=shape,
                    x=position["x"],
                    y=position["y"],
                    fixed=False,
                    font={
                        "size": 18,
                        "multi": True,
                        "bold": {"size": 11, "color": "#374151"},
                    })

        for u, v, k, d in self.G.edges(keys=True, data=True):
            edge_len = 260
            # Si alguno de los nodos es nota, alarga la arista
            if self.G.nodes[u].get("tipo") == "nota" or self.G.nodes[v].get("tipo") == "nota":
                edge_len = 340
            edge_color = d.get("color", "black")
            
            net.add_edge(
                u,
                v,
                title=d.get("tipo", ""),
                label=d.get("label", "relaciona"),
                color={
                    "color": edge_color,
                    "highlight": edge_color,
                    "hover": edge_color,
                },
                arrows="to",
                font={
                    "size": 13,
                    "align": "middle",
                    "color": edge_color,
                    "strokeWidth": 4,
                    "strokeColor": "#ffffff",
                },
                length=edge_len,
            )

        #net.show_buttons(filter_=["physics"])  # Panel para mover nodos
        net.set_options("""
{
  "configure": {
    "enabled": false
  },
  "physics": {
    "enabled": true,
    "stabilization": {
      "enabled": false
    },
    "solver": "forceAtlas2Based",
    "forceAtlas2Based": {
      "gravitationalConstant": -120,
      "centralGravity": 0.01,
      "springLength": 260,
      "springConstant": 0.04,
      "avoidOverlap": 0.8
    },
    "damping": 0.2,
    "maxVelocity": 50,
    "minVelocity": 0.1,
    "timestep": 0.35
  },
  "interaction": {
    "hover": true,
    "navigationButtons": false,
    "keyboard": true,
    "multiselect": true,
    "selectable": true,
    "selectConnectedEdges": false,
    "dragNodes": true,
    "dragView": true,
    "zoomView": true
  },
  "edges": {
    "font": {
      "size": 13,
      "align": "middle",
      "color": "#111827",
      "strokeWidth": 4,
      "strokeColor": "#ffffff"
    },
    "smooth": {
      "enabled": true,
      "type": "dynamic",
      "roundness": 0.15
    }
  }
}
""")

        net.write_html(salida)
        with open(salida, "r", encoding="utf-8") as f:
            html = f.read()
        layout_payload_json = json.dumps(layout_payload, ensure_ascii=False)
        
        overlay = """
<script>
(function () {
  function hidePyvisLoadingBar() {
    const loadingBar = document.getElementById("loadingBar");
    if (!loadingBar) return;
    loadingBar.style.display = "none";
    loadingBar.style.opacity = "0";
    loadingBar.style.visibility = "hidden";
    loadingBar.style.pointerEvents = "none";
  }

  function waitForNetwork() {
    hidePyvisLoadingBar();
    if (window.network && typeof window.network.setOptions === "function") {
      window.mmNetwork = network;
      return;
    }
    setTimeout(waitForNetwork, 300);
  }
  waitForNetwork();
  window.addEventListener("load", hidePyvisLoadingBar);
  setTimeout(hidePyvisLoadingBar, 800);
})();

const GRAPH_LAYOUTS = __GRAPH_LAYOUTS__;

const GRAPH_UI_STATE = {
  physics: {
    mode: "active",
    enabled: true
  },
  edgeControls: {
    style: "dynamic",
    roundness: 0.15,
    smooth: {
      enabled: true,
      type: "dynamic",
      roundness: 0.15
    }
  }
};

const DEFAULT_PHYSICS = {
  grav: 120,
  central: 1,
  springLen: 260,
  springConst: 40,
  damping: 20,
  maxVel: 50,
  minVel: 10,
  timestep: 35
};

function physicsValue(id) {
  return Number(document.getElementById(id).value);
}

function physicsControlState(mode = GRAPH_UI_STATE.physics.mode, enabled = GRAPH_UI_STATE.physics.enabled) {
  return {
    mode,
    enabled,
    gravitationalConstant: physicsValue("grav"),
    centralGravity: physicsValue("central"),
    springLength: physicsValue("springLen"),
    springConstant: physicsValue("springConst"),
    damping: physicsValue("damping"),
    maxVelocity: physicsValue("maxVel"),
    minVelocity: physicsValue("minVel"),
    timestep: physicsValue("timestep")
  };
}

function setPhysicsState(mode, enabled) {
  GRAPH_UI_STATE.physics = physicsControlState(mode, enabled);
}

function enablePhysics() {
  if (!window.mmNetwork) return;
  applyCurrentPhysics();
}


function freezePhysics() {
  if (!window.mmNetwork) return;
  window.mmNetwork.stopSimulation();
  window.mmNetwork.setOptions({ physics: { enabled: false } });
  setPhysicsState("frozen", false);
}

function applyCurrentPhysics() {
  if (!window.mmNetwork) return;

  const opts = {
    enabled: true,
    solver: "forceAtlas2Based",
    forceAtlas2Based: {
      gravitationalConstant: -physicsValue("grav"),
      centralGravity: physicsValue("central") / 100,
      springLength: physicsValue("springLen"),
      springConstant: physicsValue("springConst") / 1000,
      avoidOverlap: 0.8
    },
    damping: physicsValue("damping") / 100,
    maxVelocity: physicsValue("maxVel"),
    minVelocity: physicsValue("minVel") / 100,
    timestep: physicsValue("timestep") / 100
  };

  window.mmNetwork.setOptions({ physics: opts });
  window.mmNetwork.startSimulation();
  setPhysicsState("active", true);
}



function resetPhysics() {
  for (const [id, value] of Object.entries(DEFAULT_PHYSICS)) {
    document.getElementById(id).value = value;
  }
  applyCurrentPhysics();
}

function graphNodes() {
  if (!window.mmNetwork || !window.mmNetwork.body || !window.mmNetwork.body.data) return null;
  return window.mmNetwork.body.data.nodes;
}

function graphEdges() {
  if (!window.mmNetwork || !window.mmNetwork.body || !window.mmNetwork.body.data) return null;
  return window.mmNetwork.body.data.edges;
}

function setLayoutStatus(text) {
  const el = document.getElementById("layout-status");
  if (el) el.textContent = text || "";
}

function selectedNodeIds() {
  if (!window.mmNetwork) return [];
  return window.mmNetwork.getSelectedNodes();
}

function currentPositionUpdates(nodeIds, fixedValue) {
  const positions = window.mmNetwork.getPositions(nodeIds);
  return nodeIds.map((nodeId) => ({
    id: nodeId,
    x: positions[nodeId]?.x,
    y: positions[nodeId]?.y,
    fixed: { x: fixedValue, y: fixedValue }
  }));
}

function fixSelectedNodes() {
  const nodes = graphNodes();
  const selected = selectedNodeIds();
  if (!nodes || selected.length === 0) {
    setLayoutStatus("Selecciona nodos primero.");
    return;
  }
  nodes.update(currentPositionUpdates(selected, true));
  setLayoutStatus(`Nodos fijados: ${selected.length}`);
}

function releaseSelectedNodes() {
  const nodes = graphNodes();
  const selected = selectedNodeIds();
  if (!nodes || selected.length === 0) {
    setLayoutStatus("Selecciona nodos primero.");
    return;
  }
  nodes.update(currentPositionUpdates(selected, false));
  setLayoutStatus(`Nodos liberados: ${selected.length}`);
  applyCurrentPhysics();
}

function applyLayout(layoutName, options = {}) {
  const nodes = graphNodes();
  if (!nodes || !GRAPH_LAYOUTS[layoutName]) return;
  const updates = Object.entries(GRAPH_LAYOUTS[layoutName]).map(([id, pos]) => ({
    id,
    x: pos.x,
    y: pos.y,
    fixed: { x: Boolean(options.fixed), y: Boolean(options.fixed) }
  }));
  nodes.update(updates);
  if (options.runPhysics) {
    applyCurrentPhysics();
  } else if (window.mmNetwork) {
    window.mmNetwork.redraw();
  }
  setLayoutStatus(options.message || "");
}

function separateByType() {
  applyLayout("byType", {
    runPhysics: true,
    message: "Separado por tipo de concepto."
  });
}

function separateBySource() {
  applyLayout("bySource", {
    runPhysics: true,
    message: "Separado por fuente."
  });
}

function separateByComponent() {
  applyLayout("byComponent", {
    runPhysics: true,
    message: "Separado por componente conexa."
  });
}

function resetPositions() {
  applyLayout("byType", {
    runPhysics: true,
    message: "Posiciones reiniciadas por tipo."
  });
}

function edgeStyleValue() {
  const select = document.getElementById("edgeStyle");
  return select ? select.value : "dynamic";
}

function edgeRoundnessValue() {
  const input = document.getElementById("edgeRoundness");
  return input ? Number(input.value) / 100 : 0.15;
}

function updateEdgeRoundnessLabel() {
  const label = document.getElementById("edgeRoundnessValue");
  if (label) label.textContent = edgeRoundnessValue().toFixed(2);
}

function edgeSmoothConfig(style, roundness) {
  if (style === "straight") {
    return false;
  }
  if (style === "soft") {
    return {
      enabled: true,
      type: "continuous",
      roundness
    };
  }
  if (style === "curved") {
    return {
      enabled: true,
      type: "curvedCW",
      roundness
    };
  }
  return {
    enabled: true,
    type: "dynamic",
    roundness
  };
}

function edgeControlState(style = edgeStyleValue(), roundness = edgeRoundnessValue()) {
  return {
    style,
    roundness,
    smooth: edgeSmoothConfig(style, roundness)
  };
}

function preserveCurrentNodePositions(callback) {
  const nodes = graphNodes();
  if (!window.mmNetwork || !nodes) return;
  const nodeIds = nodes.getIds ? nodes.getIds() : nodes.get().map((node) => node.id);
  const positions = window.mmNetwork.getPositions(nodeIds);
  const currentNodes = nodes.get(nodeIds);
  const updates = currentNodes.map((node) => ({
    id: node.id,
    x: positions[node.id]?.x,
    y: positions[node.id]?.y,
    fixed: node.fixed ?? false
  }));

  window.mmNetwork.stopSimulation();
  window.mmNetwork.setOptions({ physics: { enabled: false } });
  setPhysicsState("paused", false);
  callback();
  nodes.update(updates);
  window.mmNetwork.redraw();
}

function applyEdgeStyle(options = {}) {
  if (!window.mmNetwork) return;
  updateEdgeRoundnessLabel();
  const style = options.style || edgeStyleValue();
  const roundness = options.roundness ?? edgeRoundnessValue();
  const smooth = edgeSmoothConfig(style, roundness);
  GRAPH_UI_STATE.edgeControls = edgeControlState(style, roundness);

  preserveCurrentNodePositions(() => {
    window.mmNetwork.setOptions({
      edges: {
        smooth,
        font: {
          align: "middle",
          vadjust: 0,
          strokeWidth: 4,
          strokeColor: "#ffffff"
        }
      }
    });
  });

  const status = document.getElementById("edge-status");
  if (status) status.textContent = options.message || "Enlaces recalculados sin mover nodos.";
}

function straightenEdges() {
  const select = document.getElementById("edgeStyle");
  const roundness = document.getElementById("edgeRoundness");
  if (select) select.value = "straight";
  if (roundness) roundness.value = 0;
  applyEdgeStyle({
    style: "straight",
    roundness: 0,
    message: "Enlaces enderezados sin mover nodos."
  });
}

function recalculateEdges() {
  applyEdgeStyle({
    message: "Geometría de enlaces recalculada sin mover nodos."
  });
}

function alignEdgeLabels() {
  applyEdgeStyle({
    message: "Etiquetas alineadas; los colores por relación se conservan."
  });
}

function currentNodeSnapshot() {
  const nodes = graphNodes();
  if (!window.mmNetwork || !nodes) return [];
  const nodeIds = nodes.getIds ? nodes.getIds() : nodes.get().map((node) => node.id);
  const positions = window.mmNetwork.getPositions(nodeIds);
  return nodes.get(nodeIds).map((node) => ({
    ...node,
    x: positions[node.id]?.x ?? node.x,
    y: positions[node.id]?.y ?? node.y,
    fixed: node.fixed ?? false
  }));
}

function currentGraphState() {
  const edges = graphEdges();
  const edgeControls = edgeControlState();
  GRAPH_UI_STATE.edgeControls = edgeControls;
  GRAPH_UI_STATE.physics = {
    ...GRAPH_UI_STATE.physics,
    ...physicsControlState(GRAPH_UI_STATE.physics.mode, GRAPH_UI_STATE.physics.enabled)
  };

  return {
    version: 1,
    exportedAt: new Date().toISOString(),
    nodes: currentNodeSnapshot(),
    edges: edges ? edges.get() : [],
    physics: GRAPH_UI_STATE.physics,
    edgeControls,
    selection: selectedNodeIds(),
    note: "Exported from the interactive graph. It opens frozen to preserve the saved composition; use Activar física to resume simulation."
  };
}

function setInputValue(id, value) {
  const input = document.getElementById(id);
  if (input && value !== undefined && value !== null) {
    input.value = value;
  }
}

function exportedStateRestoreSource(stateJson) {
  return `
window.EXPORTED_GRAPH_STATE = ${stateJson};
(function () {
  const state = window.EXPORTED_GRAPH_STATE;

  function setInputValue(id, value) {
    const input = document.getElementById(id);
    if (input && value !== undefined && value !== null) input.value = value;
  }

  function restore() {
    const net = window.network || window.mmNetwork;
    if (!net || !net.body || !net.body.data) {
      setTimeout(restore, 150);
      return;
    }

    window.mmNetwork = net;
    const nodes = net.body.data.nodes;
    const edges = net.body.data.edges;

    if (Array.isArray(state.nodes)) {
      nodes.clear();
      nodes.add(state.nodes);
    }
    if (Array.isArray(state.edges)) {
      edges.clear();
      edges.add(state.edges);
    }

    if (state.physics) {
      setInputValue("grav", state.physics.gravitationalConstant);
      setInputValue("central", state.physics.centralGravity);
      setInputValue("springLen", state.physics.springLength);
      setInputValue("springConst", state.physics.springConstant);
      setInputValue("damping", state.physics.damping);
      setInputValue("maxVel", state.physics.maxVelocity);
      setInputValue("minVel", state.physics.minVelocity);
      setInputValue("timestep", state.physics.timestep);
    }

    if (state.edgeControls) {
      setInputValue("edgeStyle", state.edgeControls.style);
      setInputValue("edgeRoundness", Math.round((state.edgeControls.roundness ?? 0.15) * 100));
    }

    if (typeof updateEdgeRoundnessLabel === "function") {
      updateEdgeRoundnessLabel();
    }
    if (typeof GRAPH_UI_STATE !== "undefined") {
      GRAPH_UI_STATE.physics = {
        ...(state.physics || {}),
        enabled: false,
        mode: state.physics?.mode || "restored"
      };
      GRAPH_UI_STATE.edgeControls = state.edgeControls || GRAPH_UI_STATE.edgeControls;
    }

    net.stopSimulation();
    net.setOptions({
      physics: { enabled: false },
      edges: {
        smooth: state.edgeControls?.smooth ?? { enabled: true, type: "dynamic", roundness: 0.15 },
        font: {
          align: "middle",
          vadjust: 0,
          strokeWidth: 4,
          strokeColor: "#ffffff"
        }
      }
    });
    net.redraw();
    if (Array.isArray(state.selection) && state.selection.length > 0) {
      net.selectNodes(state.selection);
    }

    const layoutStatus = document.getElementById("layout-status");
    if (layoutStatus) layoutStatus.textContent = "Estado exportado restaurado; física pausada para conservar posiciones.";
    const edgeStatus = document.getElementById("edge-status");
    if (edgeStatus) edgeStatus.textContent = "Estilo de enlaces restaurado.";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restore);
  } else {
    restore();
  }
  window.addEventListener("load", restore);
})();
`;
}

function buildCurrentGraphHtml() {
  const state = currentGraphState();
  const clone = document.implementation.createHTMLDocument(document.title || "Knowledge Graph");
  clone.documentElement.innerHTML = document.documentElement.innerHTML;

  clone.querySelectorAll("#exported-graph-state-script").forEach((script) => script.remove());
  const networkContainer = clone.getElementById("mynetwork");
  if (networkContainer) networkContainer.innerHTML = "";

  const safeStateJson = JSON.stringify(state).replace(/</g, "\\u003c");
  const script = clone.createElement("script");
  script.id = "exported-graph-state-script";
  script.textContent = exportedStateRestoreSource(safeStateJson);
  clone.body.appendChild(script);

  return "<!DOCTYPE html>\\n" + clone.documentElement.outerHTML;
}

function downloadCurrentGraphHtml() {
  if (!window.mmNetwork) {
    const status = document.getElementById("download-status");
    if (status) status.textContent = "El grafo todavía no está listo para exportar.";
    return;
  }

  const html = buildCurrentGraphHtml();
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  link.href = url;
  link.download = `knowledge_graph_current_${stamp}.html`;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);

  const status = document.getElementById("download-status");
  if (status) status.textContent = "HTML del grafo actual generado.";
}
</script>

<style>
#physics-overlay {
  position: fixed;
  top: 12px;
  right: 12px;
  z-index: 9999;
  background: rgba(255,255,255,0.96);
  border: 1px solid #bbb;
  border-radius: 10px;
  padding: 10px;
  font-family: Arial, sans-serif;
  width: 268px;
  max-height: calc(100vh - 28px);
  overflow-y: auto;
  box-shadow: 0 4px 16px rgba(0,0,0,.2);
}

#physics-overlay h4 {
  margin: 2px 0 4px;
  font-size: 14px;
  text-align: center;
}

#physics-overlay .physics-note {
  margin: 0 0 8px;
  color: #4b5563;
  font-size: 11px;
  line-height: 1.25;
}

#physics-overlay .physics-control {
  margin: 7px 0;
}

#physics-overlay label {
  font-size: 11px;
  font-weight: 600;
  display: block;
}

#physics-overlay .physics-help {
  color: #4b5563;
  font-size: 10px;
  line-height: 1.2;
  margin: 1px 0 2px;
}

#physics-overlay input[type=range] {
  width: 100%;
  margin: 0;
}

#physics-overlay button {
  width: 100%;
  margin-top: 6px;
}

#physics-overlay select {
  width: 100%;
  margin-top: 3px;
}

#physics-overlay .layout-section {
  border-top: 1px solid #d1d5db;
  margin-top: 9px;
  padding-top: 8px;
}

#physics-overlay .layout-title {
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
}

#physics-overlay .layout-tip,
#physics-overlay #layout-status,
#physics-overlay #edge-status,
#physics-overlay #download-status {
  color: #4b5563;
  font-size: 10px;
  line-height: 1.25;
}

#physics-overlay #layout-status,
#physics-overlay #edge-status,
#physics-overlay #download-status {
  min-height: 13px;
  margin-top: 5px;
}

#physics-overlay .value-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
}

#loadingBar,
#loadingBar *,
.outerBorder {
  display: none !important;
  opacity: 0 !important;
  visibility: hidden !important;
  pointer-events: none !important;
}
</style>

<div id="physics-overlay">
  <h4>🧲 Physics Controls</h4>
  <p class="physics-note">Ajusta estos controles para separar, compactar o estabilizar el grafo.</p>

  <div class="physics-control" title="Controla la repulsión entre nodos.">
    <label for="grav">Gravitational Constant</label>
    <div class="physics-help">Más alto separa más los nodos.</div>
    <input id="grav" type="range" min="0" max="300" value="120" oninput="applyCurrentPhysics()">
  </div>

  <div class="physics-control" title="Atrae los nodos hacia el centro.">
    <label for="central">Central Gravity</label>
    <div class="physics-help">Más alto compacta el grafo.</div>
    <input id="central" type="range" min="0" max="10" value="1" oninput="applyCurrentPhysics()">
  </div>

  <div class="physics-control" title="Define la longitud ideal de las flechas.">
    <label for="springLen">Spring Length</label>
    <div class="physics-help">Más alto alarga las flechas.</div>
    <input id="springLen" type="range" min="50" max="450" value="260" oninput="applyCurrentPhysics()">
  </div>

  <div class="physics-control" title="Controla la rigidez de las conexiones.">
    <label for="springConst">Spring Constant</label>
    <div class="physics-help">Más alto tira más fuerte de los nodos.</div>
    <input id="springConst" type="range" min="10" max="200" value="40" oninput="applyCurrentPhysics()">
  </div>

  <div class="physics-control" title="Reduce la velocidad del movimiento.">
    <label for="damping">Damping</label>
    <div class="physics-help">Más alto estabiliza más rápido.</div>
    <input id="damping" type="range" min="0" max="100" value="20" oninput="applyCurrentPhysics()">
  </div>

  <div class="physics-control" title="Limita la velocidad máxima de movimiento.">
    <label for="maxVel">Max Velocity</label>
    <div class="physics-help">Tope de velocidad de los nodos.</div>
    <input id="maxVel" type="range" min="10" max="100" value="50" oninput="applyCurrentPhysics()">
  </div>

  <div class="physics-control" title="Define cuándo la simulación se considera estable.">
    <label for="minVel">Min Velocity</label>
    <div class="physics-help">Umbral mínimo antes de estabilizar.</div>
    <input id="minVel" type="range" min="0" max="50" value="10" oninput="applyCurrentPhysics()">
  </div>

  <div class="physics-control" title="Controla el tamaño del paso de simulación.">
    <label for="timestep">Timestep</label>
    <div class="physics-help">Más alto mueve más rápido; puede inestabilizar.</div>
    <input id="timestep" type="range" min="10" max="100" value="35" oninput="applyCurrentPhysics()">
  </div>

  <button onclick="enablePhysics()" title="Activa o reanuda la simulación física del grafo.">▶ Activar física</button>
  <button onclick="freezePhysics()" title="Detiene la simulación y conserva las posiciones actuales.">📌 Congelar posiciones</button>
  <button onclick="resetPhysics()" title="Restaura los valores iniciales y reactiva la física.">♻ Resetear física</button>

  <div class="layout-section">
    <div class="layout-title">Herramientas de organización</div>
    <div class="layout-tip">Tip: Ctrl/Shift + click selecciona varios nodos; vis-network no incluye selección por caja aquí.</div>
    <button onclick="fixSelectedNodes()" title="Fija los nodos seleccionados en su posición actual.">📌 Fijar nodos seleccionados</button>
    <button onclick="releaseSelectedNodes()" title="Libera los nodos seleccionados para que vuelvan a la simulación.">🔓 Liberar nodos seleccionados</button>
    <button onclick="separateByType()" title="Reubica los nodos por tipo de concepto sin fijarlos.">🧲 Separar por tipo</button>
    <button onclick="separateBySource()" title="Reubica los nodos por fuente sin fijarlos.">🧭 Separar por fuente</button>
    <button onclick="separateByComponent()" title="Reubica los nodos por componente conexa sin fijarlos.">🧩 Separar componentes</button>
    <button onclick="resetPositions()" title="Libera todos los nodos y vuelve a la distribución inicial por tipo.">♻ Resetear posiciones</button>
    <div id="layout-status"></div>
  </div>

  <div class="layout-section">
    <div class="layout-title">Controles de enlaces</div>
    <div class="layout-tip">Endereza o suaviza flechas sin mover nodos. El ajuste es global; vis-network no edita puntos intermedios manualmente aquí.</div>
    <label for="edgeStyle">Estilo de enlaces</label>
    <select id="edgeStyle" onchange="applyEdgeStyle()">
      <option value="straight">Rectos</option>
      <option value="soft">Suaves</option>
      <option value="curved">Curvos</option>
      <option value="dynamic" selected>Dinámicos</option>
    </select>
    <div class="value-row">
      <label for="edgeRoundness">Curvatura de enlaces</label>
      <span id="edgeRoundnessValue">0.15</span>
    </div>
    <div class="physics-help">Valores bajos hacen las flechas más rectas; valores altos separan flechas paralelas.</div>
    <input id="edgeRoundness" type="range" min="0" max="60" value="15" oninput="applyEdgeStyle()">
    <button onclick="straightenEdges()" title="Cambia las aristas a líneas rectas sin mover nodos.">↔ Enderezar enlaces</button>
    <button onclick="recalculateEdges()" title="Redibuja la geometría actual de enlaces sin recalcular posiciones de nodos.">🔁 Recalcular enlaces</button>
    <button onclick="alignEdgeLabels()" title="Reaplica alineación de etiquetas de aristas sin cambiar sus colores.">📐 Alinear etiquetas</button>
    <div id="edge-status"></div>
  </div>

  <div class="layout-section">
    <div class="layout-title">Exportar estado</div>
    <div class="layout-tip">Este botón guarda el estado actual: posiciones, nodos fijados, física y estilos.</div>
    <button onclick="downloadCurrentGraphHtml()" title="Descarga el HTML con el estado actual del grafo.">💾 Descargar grafo actual</button>
    <div id="download-status"></div>
  </div>
</div>
"""

        # Insert before closing body
        overlay = overlay.replace("__GRAPH_LAYOUTS__", layout_payload_json)
        if "</body>" in html:
            html = html.replace("</body>", overlay + "\n</body>")
        with open(salida, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ Grafo exportado en: {salida}")

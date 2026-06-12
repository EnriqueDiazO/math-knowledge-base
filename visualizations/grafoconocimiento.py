import html as html_lib
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

        for n, datos in self.G.nodes(data=True):
            raw_label = datos.get("label", n)
            tipo = datos.get("tipo", "otro")
            type_badge = datos.get("type_badge", "")
            color = datos.get("color", "white")
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
    "keyboard": true
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
      "type": "dynamic"
    }
  }
}
""")

        net.write_html(salida)
        with open(salida, "r", encoding="utf-8") as f:
            html = f.read()
        
        overlay = """
<script>
(function () {
  function waitForNetwork() {
    if (window.network && typeof window.network.setOptions === "function") {
      window.mmNetwork = network;
      return;
    }
    setTimeout(waitForNetwork, 300);
  }
  waitForNetwork();
})();

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

function enablePhysics() {
  if (!window.mmNetwork) return;
  applyCurrentPhysics();
}


function freezePhysics() {
  if (!window.mmNetwork) return;
  window.mmNetwork.stopSimulation();
  window.mmNetwork.setOptions({ physics: { enabled: false } });
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
}



function resetPhysics() {
  for (const [id, value] of Object.entries(DEFAULT_PHYSICS)) {
    document.getElementById(id).value = value;
  }
  applyCurrentPhysics();
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
</div>
"""

        
        # Insert before closing body
        if "</body>" in html:
            html = html.replace("</body>", overlay + "\n</body>")
        with open(salida, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✅ Grafo exportado en: {salida}")

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
            "teorema": "#eceb98",         # blue
            "proposicion": "#00E7EF",     # orange
            "corolario": "#D5BFE2",       # purple
            "lema": "#F17A7A",            # rose
            "ejemplo": "#F9A825",         # yellow
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
            "teorema": "ellipse",
            "proposicion": "diamond_svg",   # <- SVG
            "corolario": "triangleDown_svg",# <- SVG
            "lema": "triangle_svg",         # <- SVG
            "ejemplo": "box",
            "nota": "hexagon_svg",          # <- SVG
            "otro": "circle",
            "placeholder": "dot"
        }

    def _svg_data_uri(self, svg: str) -> str:
        # Importante: encodear para usarlo como data URI
        return "data:image/svg+xml;charset=utf-8," + urllib.parse.quote(svg)

    def _estimate_text_width_px(self, lines: list[str], font_size: int = 14) -> int:
        # Estimación razonable sin medir en canvas:
        # ~0.58em por carácter (depende de la fuente, pero funciona bien)
        if not lines:
            return 120
        max_chars = max(len(line) for line in lines)
        return int(max(120, min(520, max_chars * font_size * 0.58)))


    def _make_svg_polygon_node(self, wrapped_label: str, fill: str, kind: str) -> str:
        """kind: 'hexagon' | 'diamond' | 'triangle' | 'triangleDown'
        Devuelve un data URI (SVG) con el texto SIEMPRE dentro.
        """  # noqa: D205
        font_size = 14
        padding_x = 18
        padding_y = 14
        line_gap = 4

        lines = wrapped_label.split("\n") if wrapped_label else [""]
        text_w = self._estimate_text_width_px(lines, font_size=font_size)
        line_h = font_size + line_gap
        text_h = len(lines) * line_h

        width = text_w + 2 * padding_x
        height = text_h + 2 * padding_y

        # límites por seguridad (evita nodos gigantes)
        width = int(max(160, min(620, width)))
        height = int(max(70, min(360, height)))

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
        start_y = (height - total_text_h) / 2 + font_size  # primera línea

        # Escapar XML básico
        def esc(s: str) -> str:
            return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        text_items = []
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
        shape = self.forma_por_tipo.get(tipo, "circle")
        if shape.endswith("_svg"):
            return "svg"
        return "native"

    def _native_shape(self, tipo: str) -> str:
        shape = self.forma_por_tipo.get(tipo, "circle")
        # Normaliza: si viene 'hexagon_svg' -> 'hexagon' (no lo usaremos en native, pero por limpieza)
        return shape.replace("_svg", "")


    def _concepto_permitido(self, tipo: str, tipos_concepto: list[str] | None) -> bool:
        return (not tipos_concepto) or (tipo in tipos_concepto)

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
            tipo = doc.get("tipo", "otro")
            if not self._concepto_permitido(tipo, tipos_concepto):
                continue

            etiqueta = f"{doc['id']}@{doc['source']}"
            titulo = doc.get("titulo", etiqueta)
            color = self.color_por_tipo.get(tipo, "white")
            self.G.add_node(etiqueta, label=titulo, tipo=tipo, color=color)

        # Crear aristas
        for rel in self.relaciones:
            # Detectar el formato de relaciones
            if "desde" in rel and "hasta" in rel:
                desde = rel["desde"]
                hasta = rel["hasta"]
            else:
                desde = f"{rel['desde_id']}@{rel['desde_source']}"
                hasta = f"{rel['hasta_id']}@{rel['hasta_source']}"

            tipo_rel = rel["tipo"]
            # 🔎 Filtrar si se pidió solo ciertos tipos
            if tipos_relacion and tipo_rel not in tipos_relacion:
                continue

            color = self.color_por_relacion.get(tipo_rel, "black")

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
            self.G.add_edge(desde, hasta, key=tipo_rel, tipo=tipo_rel, color=color)
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
        net = Network(height="750px", width="100%", directed=True)

        for n, datos in self.G.nodes(data=True):
            raw_label = datos.get("label", n)
            tipo = datos.get("tipo", "otro")
            color = datos.get("color", "white")
            wrapped_label = self._wrap_label(raw_label)
            strategy = self._node_render_strategy(tipo)

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
                    kind=svg_kind
                )

                net.add_node(
                    n,
                    shape="image",
                    image=img_uri,
                    label="",
                    font={"size": 0, "color": "rgba(0,0,0,0)"},                # 👈 importante: NO string vacío
                    title=tipo,           # 👈 tooltip con texto humano
                    size=30,   # ajusta 24–40
                    shapeProperties={"useImageSize": False}
                )
            else:
                # Nativo (rápido, y queda bien para box/ellipse/circle/dot)
                shape = self._native_shape(tipo)
                net.add_node(
                    n,
                    label=wrapped_label,
                    title=tipo,
                    color=color,
                    shape=shape,
                    font={"size": 14})

        for u, v, k, d in self.G.edges(keys=True, data=True):
            edge_len = 160
            # Si alguno de los nodos es nota, alarga la arista
            if self.G.nodes[u].get("tipo") == "nota" or self.G.nodes[v].get("tipo") == "nota":
                edge_len = 240
            
            net.add_edge(u, v,
                         title=d.get("tipo", ""),
                         color=d.get("color", "black"),
                         length=edge_len
                         )

        net.show_buttons(filter_=["physics"])  # Panel para mover nodos
        net.write_html(salida)
        print(f"✅ Grafo exportado en: {salida}")

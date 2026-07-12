import html as html_lib
import json
import math
import os
import urllib.parse
from datetime import datetime
from pathlib import Path

import networkx as nx
from pyvis.network import Network

from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


DEBUG_KNOWLEDGE_GRAPH = os.getenv("DEBUG_KNOWLEDGE_GRAPH", "0") == "1"


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
            "conj": "#fbcfe8",
            "conjetura": "#fbcfe8",
            "axioma": "#ccfbf1",
            "axiom": "#ccfbf1",
            "preg": "#bae6fd",
            "pregunta": "#bae6fd",
            "question": "#bae6fd",
            "ref": "#d9f99d",
            "referencia": "#d9f99d",
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
            "conj": "diamond_svg",
            "conjetura": "diamond_svg",
            "axioma": "hexagon_svg",
            "axiom": "hexagon_svg",
            "preg": "ellipse",
            "pregunta": "ellipse",
            "question": "ellipse",
            "ref": "box",
            "referencia": "box",
            "otro": "box",
            "placeholder": "dot"
        }

        self.tipo_aliases = {
            "def": "definicion",
            "definicion": "definicion",
            "definición": "definicion",
            "definition": "definicion",
            "teo": "teorema",
            "teorema": "teorema",
            "theorem": "teorema",
            "prop": "proposicion",
            "proposicion": "proposicion",
            "proposición": "proposicion",
            "proposition": "proposicion",
            "cor": "corolario",
            "corolario": "corolario",
            "corollary": "corolario",
            "lem": "lema",
            "lema": "lema",
            "lemma": "lema",
            "obs": "observacion",
            "observacion": "observacion",
            "observación": "observacion",
            "remark": "observacion",
            "ejem": "ejemplo",
            "ejemplo": "ejemplo",
            "example": "ejemplo",
            "nota": "nota",
            "note": "nota",
            "conj": "conj",
            "conjetura": "conj",
            "axioma": "axioma",
            "axiom": "axioma",
            "preg": "preg",
            "pregunta": "preg",
            "question": "preg",
            "ref": "ref",
            "referencia": "ref",
            "placeholder": "placeholder",
            "otro": "otro",
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
            "conj": "conj",
            "conjetura": "conj",
            "axioma": "axioma",
            "axiom": "axioma",
            "preg": "preg",
            "pregunta": "preg",
            "question": "preg",
            "ref": "ref",
            "referencia": "ref",
        }

        self.nombre_corto_por_tipo = {
            "definicion": "definición",
            "definición": "definición",
            "definition": "definición",
            "teorema": "teorema",
            "theorem": "teorema",
            "proposicion": "proposición",
            "proposición": "proposición",
            "proposition": "proposición",
            "ejemplo": "ejemplo",
            "example": "ejemplo",
            "corolario": "corolario",
            "corollary": "corolario",
            "lema": "lema",
            "lemma": "lema",
            "observacion": "observación",
            "observación": "observación",
            "remark": "observación",
            "nota": "nota",
            "note": "nota",
            "conj": "conjetura",
            "conjetura": "conjetura",
            "axioma": "axioma",
            "axiom": "axioma",
            "preg": "pregunta",
            "pregunta": "pregunta",
            "question": "pregunta",
            "ref": "referencia",
            "referencia": "referencia",
            "placeholder": "placeholder",
            "otro": "otro",
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
        shape = self.forma_por_tipo.get(self._canonical_type(tipo), "box")
        if shape.endswith("_svg"):
            return "svg"
        return "native"

    def _native_shape(self, tipo: str) -> str:
        shape = self.forma_por_tipo.get(self._canonical_type(tipo), "box")
        # Normaliza: si viene 'hexagon_svg' -> 'hexagon' (no lo usaremos en native, pero por limpieza)
        return shape.replace("_svg", "")


    def _concepto_permitido(self, tipo: str, tipos_concepto: list[str] | None) -> bool:
        if not tipos_concepto:
            return True
        tipo_key = self._canonical_type(tipo)
        allowed = {self._canonical_type(t) for t in tipos_concepto}
        return tipo_key in allowed

    def _canonical_type(self, tipo: str) -> str:
        key = str(tipo or "").strip().lower()
        return self.tipo_aliases.get(key, key or "otro")

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
                return self._canonical_type(str(value).strip())
        return "otro"

    def _node_type_abbreviation(self, tipo: str) -> str:
        return self.abreviatura_por_tipo.get(self._canonical_type(tipo), "")

    def _node_type_display_name(self, tipo: str) -> str:
        key = self._canonical_type(tipo)
        return self.nombre_corto_por_tipo.get(key, str(tipo or "").strip() or "otro")

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
            "initial": self._positions_by_group(type_by_node, radius=680),
            "meta": {
                node_id: {
                    "type": type_by_node.get(node_id, ""),
                    "shortType": self._node_type_abbreviation(type_by_node.get(node_id, "")),
                    "displayType": self._node_type_display_name(type_by_node.get(node_id, "")),
                    "source": source_by_node.get(node_id, ""),
                    "component": component_by_node.get(node_id, ""),
                    "categories": self._list_or_empty(self.G.nodes[node_id].get("categorias")),
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

    def _text_or_none(self, value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _list_or_empty(self, value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _reference_summary(self, reference) -> str:
        if not isinstance(reference, dict):
            return self._text_or_none(reference) or ""
        parts = []
        for key in ("autor", "fuente", "anio", "capitulo", "seccion", "paginas", "doi", "url"):
            value = reference.get(key)
            if value is not None and str(value).strip():
                parts.append(str(value).strip())
        return " · ".join(parts)

    def _node_metadata(self, node_id: str, datos: dict) -> dict:
        tipo = datos.get("tipo", "otro")
        type_badge = datos.get("type_badge", "") or self._node_type_abbreviation(tipo)
        raw_label = datos.get("label", node_id)
        reference = datos.get("referencia")
        description = (
            self._text_or_none(datos.get("descripcion"))
            or self._text_or_none(datos.get("comentario"))
            or self._text_or_none(datos.get("aclaracion"))
        )
        content = self._text_or_none(datos.get("contenido_latex"))
        source = self._text_or_none(datos.get("source")) or self._node_source(node_id)
        concept_id = self._text_or_none(datos.get("concept_id")) or node_id.split("@", 1)[0]
        categories = self._list_or_empty(datos.get("categorias"))
        reference_text = self._reference_summary(reference)
        type_display = self._node_type_display_name(tipo)

        return {
            "type": tipo,
            "mmType": tipo,
            "conceptType": tipo,
            "typeBadge": type_badge,
            "shortType": type_badge,
            "displayType": f"{type_badge} - {type_display}" if type_badge else type_display,
            "rawLabel": raw_label,
            "source": source,
            "conceptId": concept_id,
            "categories": categories,
            "description": description,
            "content": content,
            "referenceText": reference_text,
            "nodeInfo": {
                "id": node_id,
                "conceptId": concept_id,
                "label": raw_label,
                "type": tipo,
                "shortType": type_badge,
                "displayType": type_display,
                "source": source,
                "categories": categories,
                "description": description,
                "content": content,
                "reference": reference_text,
            },
        }

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
            color = self.color_por_tipo.get(self._canonical_type(tipo), self.color_por_tipo["otro"])
            type_badge = self._node_type_abbreviation(tipo)
            self.G.add_node(
                etiqueta,
                label=titulo,
                tipo=tipo,
                type_badge=type_badge,
                color=color,
                source=doc.get("source"),
                concept_id=doc.get("id"),
                categorias=doc.get("categorias", []),
                comentario=doc.get("comentario"),
                descripcion=doc.get("descripcion"),
                aclaracion=doc.get("aclaracion"),
                contenido_latex=doc.get("contenido_latex"),
                referencia=doc.get("referencia"),
            )

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
        if DEBUG_KNOWLEDGE_GRAPH:
            print("DEBUG tipos_concepto:", tipos_concepto, "usar_placeholders:", usar_placeholders)
            print(f"🧠 Nodos creados: {len(self.G.nodes)} | Relaciones creadas: {len(self.G.edges)}")
            if relaciones_omitidas_por_nodos_faltantes > 0:
                print(
                    "⚠️  Relaciones con placeholders por nodos faltantes: "
                    f"{relaciones_omitidas_por_nodos_faltantes}"
                )
                if ejemplos_omitidos:
                    print("⚠️  Ejemplos (placeholders usados):")
                for d, t, h, fd, fh in ejemplos_omitidos:
                    faltan = []
                    if fd:
                        faltan.append("desde")
                    if fh:
                        faltan.append("hasta")
                    print(f"   - {d} -({t})-> {h}   [faltan: {', '.join(faltan)}]")


    def to_graph_state(self, previous_state: dict | None = None) -> dict:
        """Build a serializable vis-network state, preserving existing layout when possible."""
        previous_state = previous_state if isinstance(previous_state, dict) else {}
        previous_node_items = []
        if isinstance(previous_state.get("fullNodes"), list):
            previous_node_items.extend(previous_state.get("fullNodes", []))
        if isinstance(previous_state.get("nodes"), list):
            previous_node_items.extend(previous_state.get("nodes", []))
        previous_edge_items = []
        if isinstance(previous_state.get("fullEdges"), list):
            previous_edge_items.extend(previous_state.get("fullEdges", []))
        if isinstance(previous_state.get("edges"), list):
            previous_edge_items.extend(previous_state.get("edges", []))
        previous_nodes = {
            node.get("id"): node
            for node in previous_node_items
            if isinstance(node, dict) and node.get("id")
        }
        previous_edges = {
            edge.get("id"): edge
            for edge in previous_edge_items
            if isinstance(edge, dict) and edge.get("id")
        }
        node_controls = previous_state.get("nodeControls", {}) if isinstance(previous_state.get("nodeControls"), dict) else {}
        edge_label_size = int(node_controls.get("edgeLabelSize", 13) or 13)
        node_label_size = int(node_controls.get("nodeLabelSize", 18) or 18)
        previous_ui_controls = previous_state.get("uiControls", {})
        if not isinstance(previous_ui_controls, dict):
            previous_ui_controls = {}
        previous_ui = previous_state.get("ui", {})
        if not isinstance(previous_ui, dict):
            previous_ui = {}
        physics_overlay_visible = previous_ui_controls.get("physicsOverlayVisible")
        if not isinstance(physics_overlay_visible, bool):
            physics_overlay_visible = previous_ui.get("physicsOverlayVisible")
        left_controls_visible = previous_ui_controls.get("leftControlsVisible")
        if not isinstance(left_controls_visible, bool):
            left_controls_visible = previous_ui.get("leftControlsVisible")
        ui_controls = {
            "physicsOverlayVisible": physics_overlay_visible
            if isinstance(physics_overlay_visible, bool)
            else True,
            "leftControlsVisible": left_controls_visible
            if isinstance(left_controls_visible, bool)
            else True,
            "selectedType": previous_ui_controls.get("selectedType", previous_ui.get("selectedType", "")),
            "selectedNodeId": previous_ui_controls.get("selectedNodeId", previous_ui.get("selectedNodeId", "")),
            "visibleNodeIds": previous_ui_controls.get("visibleNodeIds")
            if isinstance(previous_ui_controls.get("visibleNodeIds"), list)
            else None,
            "visibleEdgeIds": previous_ui_controls.get("visibleEdgeIds")
            if isinstance(previous_ui_controls.get("visibleEdgeIds"), list)
            else None,
        }

        layout_payload = self._layout_payload()
        initial_positions = layout_payload["initial"]
        nodes = []
        for node_id, datos in self.G.nodes(data=True):
            raw_label = datos.get("label", node_id)
            tipo = datos.get("tipo", "otro")
            type_badge = datos.get("type_badge", "")
            color = datos.get("color", "white")
            position = initial_positions.get(node_id, {"x": 0, "y": 0})
            wrapped_label = self._wrap_label(raw_label)
            tooltip = f"<b>{html_lib.escape(str(raw_label))}</b><br>Tipo: {html_lib.escape(str(tipo))}"
            if type_badge:
                tooltip = f"{tooltip} ({html_lib.escape(str(type_badge))})"
            node_metadata = self._node_metadata(node_id, datos)

            if self._node_render_strategy(tipo) == "svg":
                svg_kind = self._native_shape(tipo)
                if svg_kind not in {"hexagon", "diamond", "triangle", "triangleDown"}:
                    svg_kind = "hexagon"
                node_data = {
                    "id": node_id,
                    "shape": "image",
                    "image": self._make_svg_polygon_node(
                        wrapped_label=wrapped_label,
                        fill=color,
                        kind=svg_kind,
                        type_badge=type_badge,
                    ),
                    "label": "",
                    "font": {"size": 0, "color": "rgba(0,0,0,0)"},
                    "title": tooltip,
                    "x": position["x"],
                    "y": position["y"],
                    "fixed": False,
                    "size": max(22, round(node_label_size * 2.1)),
                    "shapeProperties": {"useImageSize": False},
                    **node_metadata,
                }
            else:
                node_data = {
                    "id": node_id,
                    "label": self._node_label_with_badge(wrapped_label, type_badge),
                    "title": tooltip,
                    "color": color,
                    "shape": self._native_shape(tipo),
                    "x": position["x"],
                    "y": position["y"],
                    "fixed": False,
                    "font": {
                        "size": node_label_size,
                        "multi": True,
                        "bold": {"size": max(9, round(node_label_size * 0.62)), "color": "#374151"},
                    },
                    **node_metadata,
                }

            previous_node = previous_nodes.get(node_id, {})
            for key in ("x", "y", "fixed", "font", "size"):
                if key in previous_node:
                    node_data[key] = previous_node[key]
            nodes.append(node_data)

        edges = []
        for u, v, k, d in self.G.edges(keys=True, data=True):
            edge_len = 340 if self.G.nodes[u].get("tipo") == "nota" or self.G.nodes[v].get("tipo") == "nota" else 260
            edge_color = d.get("color", "black")
            edge_id = d.get("id") or f"{u}::{k}::{v}"
            edge_data = {
                "id": edge_id,
                "from": u,
                "to": v,
                "title": d.get("tipo", ""),
                "label": d.get("label", "relaciona"),
                "color": {
                    "color": edge_color,
                    "highlight": edge_color,
                    "hover": edge_color,
                },
                "arrows": "to",
                "font": {
                    "size": edge_label_size,
                    "align": "middle",
                    "color": edge_color,
                    "strokeWidth": 4,
                    "strokeColor": "#ffffff",
                },
                "length": edge_len,
            }
            previous_edge = previous_edges.get(edge_id, {})
            if isinstance(previous_edge.get("font"), dict):
                edge_data["font"].update(previous_edge["font"])
                edge_data["font"]["color"] = edge_color
            for key in ("smooth", "width", "dashes"):
                if key in previous_edge:
                    edge_data[key] = previous_edge[key]
            edges.append(edge_data)

        return {
            "version": previous_state.get("version", 1),
            "exportedAt": datetime.utcnow().isoformat() + "Z",
            "nodes": nodes,
            "edges": edges,
            "fullNodes": nodes,
            "fullEdges": edges,
            "physics": previous_state.get("physics", {"mode": "frozen", "enabled": False}),
            "edgeControls": previous_state.get(
                "edgeControls",
                {
                    "style": "dynamic",
                    "roundness": 0.15,
                    "smooth": {"enabled": True, "type": "dynamic", "roundness": 0.15},
                },
            ),
            "nodeControls": {
                "edgeLabelSize": edge_label_size,
                "nodeLabelSize": node_label_size,
            },
            "uiControls": ui_controls,
            "layout": layout_payload,
            "selection": previous_state.get("selection", []),
            "note": "Generated from filters in Streamlit; existing node positions are preserved when possible.",
        }


    def _restore_state_bootstrap(self, graph_state: dict | None) -> str:
        if not graph_state:
            return ""
        state_json = json.dumps(graph_state, ensure_ascii=False).replace("</script>", "<\\/script>")
        state_json_literal = json.dumps(state_json, ensure_ascii=False)
        return f"""
<script id="exported-graph-state-script">
(function () {{
  const stateJson = {state_json_literal};

  function installRestoreScript() {{
    if (typeof exportedStateRestoreSource !== "function") {{
      setTimeout(installRestoreScript, 150);
      return;
    }}
    document.querySelectorAll("#exported-graph-state-runner").forEach((script) => script.remove());
    const script = document.createElement("script");
    script.id = "exported-graph-state-runner";
    script.textContent = exportedStateRestoreSource(stateJson);
    document.body.appendChild(script);
  }}

  installRestoreScript();
}})();
</script>
"""

    def exportar_html(
        self,
        salida: str | Path | None = None,
        size: int | None = None,
        initial_state: dict | None = None,
    ) -> str:
        """Genera HTML interactivo; si `salida` existe, también lo escribe a disco."""
        if size is None:
            size = self.MaxLengthLabel
        net = Network(height="100vh", width="100%", directed=True, cdn_resources="in_line")
        layout_payload = self._layout_payload()
        initial_positions = layout_payload["initial"]

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
            node_metadata = self._node_metadata(n, datos)

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
                    shapeProperties={"useImageSize": False},
                    **node_metadata,
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
                    },
                    **node_metadata,
                )

        for u, v, k, d in self.G.edges(keys=True, data=True):
            edge_len = 260
            # Si alguno de los nodos es nota, alarga la arista
            if self.G.nodes[u].get("tipo") == "nota" or self.G.nodes[v].get("tipo") == "nota":
                edge_len = 340
            edge_color = d.get("color", "black")
            edge_id = d.get("id") or f"{u}::{k}::{v}"
            
            net.add_edge(
                u,
                v,
                id=edge_id,
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

        html = net.generate_html(name=str(salida or "knowledge_graph.html"), local=True, notebook=False)
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
	      setTimeout(() => initializeGraphNavigation(), 0);
	      return;
	    }
	    setTimeout(waitForNetwork, 300);
	  }
  waitForNetwork();
  window.addEventListener("load", hidePyvisLoadingBar);
  setTimeout(hidePyvisLoadingBar, 800);
})();

	let GRAPH_LAYOUTS = __GRAPH_LAYOUTS__;
	window.allNodes = window.allNodes || {};
	window.allEdges = window.allEdges || {};
	window.originalNodes = window.originalNodes || {};
	window.originalEdges = window.originalEdges || {};

	const ORIGINAL_GRAPH_DATA = {
	  nodes: [],
	  edges: []
	};

	let MM_SUPPRESS_SELECT_HANDLER = false;
	let MM_PENDING_FIT_FRAME = null;

	const TYPE_ALIASES = {
	  def: "definicion",
	  definicion: "definicion",
	  "definición": "definicion",
	  definition: "definicion",
	  teo: "teorema",
	  teorema: "teorema",
	  theorem: "teorema",
	  prop: "proposicion",
	  proposicion: "proposicion",
	  "proposición": "proposicion",
	  proposition: "proposicion",
	  cor: "corolario",
	  corolario: "corolario",
	  corollary: "corolario",
	  lem: "lema",
	  lema: "lema",
	  lemma: "lema",
	  obs: "observacion",
	  observacion: "observacion",
	  "observación": "observacion",
	  remark: "observacion",
	  ejem: "ejemplo",
	  ejemplo: "ejemplo",
	  example: "ejemplo",
	  nota: "nota",
	  note: "nota",
	  conj: "conj",
	  conjetura: "conj",
	  axioma: "axioma",
	  axiom: "axioma",
	  preg: "preg",
	  pregunta: "preg",
	  question: "preg",
	  ref: "ref",
	  referencia: "ref",
	  placeholder: "placeholder",
	  otro: "otro"
	};

	const TYPE_BADGES = {
	  definicion: "def",
	  teorema: "teo",
	  proposicion: "prop",
	  corolario: "cor",
	  lema: "lem",
	  observacion: "obs",
	  ejemplo: "ejem",
	  nota: "nota",
	  conj: "conj",
	  axioma: "axioma",
	  preg: "preg",
	  ref: "ref",
	  placeholder: "placeholder",
	  otro: "otro"
	};

	const TYPE_LABELS = {
	  definicion: "definición",
	  teorema: "teorema",
	  proposicion: "proposición",
	  corolario: "corolario",
	  lema: "lema",
	  observacion: "observación",
	  ejemplo: "ejemplo",
	  nota: "nota",
	  conj: "conjetura",
	  axioma: "axioma",
	  preg: "pregunta",
	  ref: "referencia",
	  placeholder: "placeholder",
	  otro: "otro"
	};

	const TYPE_COLORS = {
	  definicion: "#b5e8b8",
	  teorema: "#eceb98",
	  proposicion: "#00E7EF",
	  corolario: "#D5BFE2",
	  lema: "#F17A7A",
	  observacion: "#D7CCC8",
	  ejemplo: "#F9A825",
	  nota: "#B0BEC5",
	  conj: "#fbcfe8",
	  axioma: "#ccfbf1",
	  preg: "#bae6fd",
	  ref: "#d9f99d",
	  placeholder: "#F5F5F5",
	  otro: "#E0E0E0"
	};

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
  },
	  nodeControls: {
	    edgeLabelSize: 13,
	    nodeLabelSize: 18
	  },
	  ui: {
	    physicsOverlayVisible: true,
	    leftControlsVisible: true,
	    selectedType: "",
	    selectedNodeId: "",
	    visibleNodeIds: null,
	    visibleEdgeIds: null
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

	function cloneGraphItem(item) {
	  return JSON.parse(JSON.stringify(item || {}));
	}

	function edgeStableId(edge) {
	  if (!edge) return "";
	  if (edge.id !== undefined && edge.id !== null && edge.id !== "") return edge.id;
	  return `${edge.from}::${edge.to}::${edge.label || edge.title || ""}`;
	}

	function visibleNodeIds() {
	  const nodes = graphNodes();
	  return nodes ? nodes.getIds() : [];
	}

	function visibleEdgeIds() {
	  const edges = graphEdges();
	  return edges ? edges.get().map(edgeStableId) : [];
	}

	function datasetMap(dataset, keyFn = (item) => item.id) {
	  const out = {};
	  if (!dataset) return out;
	  dataset.get().forEach((item) => {
	    const key = keyFn(item);
	    if (key !== undefined && key !== null && key !== "") out[key] = cloneGraphItem(item);
	  });
	  return out;
	}

	function nodeMeta(nodeId) {
	  return (GRAPH_LAYOUTS && GRAPH_LAYOUTS.meta && GRAPH_LAYOUTS.meta[nodeId]) || {};
	}

	function cacheOriginalGraphData(force = false) {
	  const nodes = graphNodes();
	  const edges = graphEdges();
	  if (!nodes || !edges) return;

	  if (force || ORIGINAL_GRAPH_DATA.nodes.length === 0) {
	    ORIGINAL_GRAPH_DATA.nodes = nodes.get().map(cloneGraphItem);
	  }
	  if (force || ORIGINAL_GRAPH_DATA.edges.length === 0) {
	    ORIGINAL_GRAPH_DATA.edges = edges.get().map(cloneGraphItem);
	  }

	  if (force || Object.keys(window.allNodes).length === 0) {
	    window.allNodes = {};
	    ORIGINAL_GRAPH_DATA.nodes.forEach((node) => {
	      if (node && node.id !== undefined) window.allNodes[node.id] = cloneGraphItem(node);
	    });
	    window.originalNodes = datasetMap(nodes);
	  }
	  if (force || Object.keys(window.allEdges).length === 0) {
	    window.allEdges = {};
	    ORIGINAL_GRAPH_DATA.edges.forEach((edge) => {
	      const id = edgeStableId(edge);
	      if (id) window.allEdges[id] = cloneGraphItem(edge);
	    });
	    window.originalEdges = datasetMap(edges, edgeStableId);
	  }
	}

	function ensureFullGraphData() {
	  const nodes = graphNodes();
	  const edges = graphEdges();
	  if (!nodes || !edges) return;
	  if (ORIGINAL_GRAPH_DATA.nodes.length === 0 || ORIGINAL_GRAPH_DATA.edges.length === 0) {
	    cacheOriginalGraphData(true);
	  }
	}

	function mergeCurrentVisibleStateIntoAllData() {
	  const nodes = graphNodes();
	  const edges = graphEdges();
	  if (!window.mmNetwork || !nodes || !edges) return;
	  ensureFullGraphData();

	  const ids = nodes.getIds ? nodes.getIds() : nodes.get().map((node) => node.id);
	  const positions = window.mmNetwork.getPositions(ids);
	  nodes.get(ids).forEach((node) => {
	    const stored = window.allNodes[node.id] || {};
	    window.allNodes[node.id] = {
	      ...cloneGraphItem(stored),
	      ...cloneGraphItem(node),
	      x: positions[node.id]?.x ?? node.x,
	      y: positions[node.id]?.y ?? node.y,
	      fixed: node.fixed ?? stored.fixed ?? false
	    };
	  });

	  edges.get().forEach((edge) => {
	    const edgeId = edgeStableId(edge);
	    if (edgeId) window.allEdges[edgeId] = cloneGraphItem(edge);
	  });
	}

	function stripHtml(value) {
	  const div = document.createElement("div");
	  div.innerHTML = String(value || "").replace(/<br\\s*\\/?\\s*>/gi, "\\n");
	  return div.textContent || div.innerText || "";
	}

	function escapeHtml(value) {
	  return String(value ?? "")
	    .replace(/&/g, "&amp;")
	    .replace(/</g, "&lt;")
	    .replace(/>/g, "&gt;")
	    .replace(/"/g, "&quot;")
	    .replace(/'/g, "&#39;");
	}

	function canonicalType(value) {
	  const normalized = String(value || "").trim().toLowerCase();
	  return TYPE_ALIASES[normalized] || normalized;
	}

	function typeBadge(type) {
	  const canonical = canonicalType(type);
	  return TYPE_BADGES[canonical] || String(type || "").trim();
	}

	function typeLabel(type) {
	  const canonical = canonicalType(type);
	  const badge = typeBadge(canonical);
	  const label = TYPE_LABELS[canonical] || canonical || "otro";
	  return badge && badge !== label ? `${badge} - ${label}` : label;
	}

	function colorValue(color) {
	  if (!color) return "";
	  if (typeof color === "string") return color;
	  return color.background || color.color || color.border || "";
	}

	function nodeTypeValue(nodeOrId) {
	  const node = typeof nodeOrId === "string" ? (window.allNodes[nodeOrId] || {}) : (nodeOrId || {});
	  const meta = nodeMeta(node.id);
	  const direct = node.type || node.mmType || node.conceptType || node.node_type || meta.type;
	  if (direct) return canonicalType(direct);

	  const titleMatch = String(node.title || "").match(/Tipo:\\s*([^<(\\n]+)/i);
	  if (titleMatch && titleMatch[1]) return canonicalType(titleMatch[1]);

	  const labelMatch = String(node.label || "").match(/<b>([^<]+)<\\/b>/i);
	  if (labelMatch && labelMatch[1]) return canonicalType(labelMatch[1]);

	  return "otro";
	}

	function nodeDisplayName(node) {
	  if (!node) return "";
	  if (node.rawLabel) return String(node.rawLabel);
	  if (node.nodeInfo && node.nodeInfo.label) return String(node.nodeInfo.label);
	  const titleText = stripHtml(node.title || "");
	  if (titleText) return titleText.split(/Tipo:/i)[0].trim();
	  const labelText = stripHtml(node.label || "").replace(/\\s+/g, " ").trim();
	  const badge = typeBadge(nodeTypeValue(node));
	  if (badge && labelText.toLowerCase().startsWith(`${badge.toLowerCase()} `)) {
	    return labelText.slice(badge.length).trim();
	  }
	  return labelText || String(node.id || "");
	}

	function nodeSource(node) {
	  if (!node) return "";
	  if (node.source) return String(node.source);
	  if (node.nodeInfo && node.nodeInfo.source) return String(node.nodeInfo.source);
	  const meta = nodeMeta(node.id);
	  if (meta.source) return String(meta.source);
	  const id = String(node.id || "");
	  return id.includes("@") ? id.split("@").slice(1).join("@") : "";
	}

	function nodeCategories(node) {
	  const direct = node.categories || node.categorias || (node.nodeInfo && node.nodeInfo.categories);
	  if (Array.isArray(direct)) return direct.filter(Boolean).map(String);
	  const meta = nodeMeta(node.id);
	  return Array.isArray(meta.categories) ? meta.categories.filter(Boolean).map(String) : [];
	}

	function originalNodeById(nodeId) {
	  return ORIGINAL_GRAPH_DATA.nodes.find((node) => node.id === nodeId) || null;
	}

	function originalEdgeById(edgeId) {
	  return ORIGINAL_GRAPH_DATA.edges.find((edge) => edgeStableId(edge) === edgeId) || null;
	}

	function graphNodeDataForSubset(nodeId) {
	  const original = originalNodeById(nodeId);
	  const stored = window.allNodes[nodeId] || {};
	  return {
	    ...(original ? cloneGraphItem(original) : {}),
	    ...cloneGraphItem(stored),
	    id: nodeId
	  };
	}

	function graphEdgeDataForSubset(edgeId) {
	  const original = originalEdgeById(edgeId);
	  const stored = window.allEdges[edgeId] || {};
	  const edge = {
	    ...(original ? cloneGraphItem(original) : {}),
	    ...cloneGraphItem(stored)
	  };
	  if (edge.id === undefined || edge.id === null || edge.id === "") edge.id = edgeId;
	  return edge;
	}

	function edgeIdsForVisibleNodes(nodeIds) {
	  const visible = new Set(nodeIds);
	  return ORIGINAL_GRAPH_DATA.edges
	    .filter((edge) => visible.has(edge.from) && visible.has(edge.to))
	    .map(edgeStableId);
	}

	function stopGraphMotion() {
	  if (!window.mmNetwork) return;
	  window.mmNetwork.stopSimulation();
	  window.mmNetwork.setOptions({ physics: { enabled: false } });
	  GRAPH_UI_STATE.physics = {
	    ...(GRAPH_UI_STATE.physics || {}),
	    mode: "filtered",
	    enabled: false
	  };
	}

	function safeFitToNodes(nodeIds) {
	  if (!window.mmNetwork || !Array.isArray(nodeIds)) return;
	  const ids = Array.from(new Set(nodeIds)).filter(Boolean);
	  if (ids.length === 0) return;

	  stopGraphMotion();
	  if (MM_PENDING_FIT_FRAME !== null) {
	    if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(MM_PENDING_FIT_FRAME);
	    clearTimeout(MM_PENDING_FIT_FRAME);
	    MM_PENDING_FIT_FRAME = null;
	  }

	  const fitOnce = () => {
	    MM_PENDING_FIT_FRAME = null;
	    if (!window.mmNetwork) return;
	    stopGraphMotion();
	    window.mmNetwork.fit({
	      nodes: ids,
	      animation: { duration: 250, easingFunction: "easeInOutQuad" }
	    });
	    window.mmNetwork.redraw();
	  };

	  if (typeof requestAnimationFrame === "function") {
	    MM_PENDING_FIT_FRAME = requestAnimationFrame(fitOnce);
	  } else {
	    MM_PENDING_FIT_FRAME = setTimeout(fitOnce, 0);
	  }
	}

	function setSelectedNodesQuietly(nodeIds) {
	  if (!window.mmNetwork || !Array.isArray(nodeIds)) return;
	  const ids = Array.from(new Set(nodeIds)).filter(Boolean);
	  MM_SUPPRESS_SELECT_HANDLER = true;
	  window.mmNetwork.selectNodes(ids);
	  if (ids.length > 0) {
	    const selector = document.getElementById("nodeIdSelector");
	    const input = document.getElementById("nodeSearchInput");
	    if (selector) selector.value = ids[0];
	    if (input) input.value = ids[0];
	    updateNodeInfo(ids[0]);
	    GRAPH_UI_STATE.ui = {
	      ...(GRAPH_UI_STATE.ui || {}),
	      selectedNodeId: ids[0]
	    };
	  }
	  setTimeout(() => {
	    MM_SUPPRESS_SELECT_HANDLER = false;
	  }, 0);
	}

	function renderGraphSubset(nodeIds, edgeIds = null, options = {}) {
	  const nodes = graphNodes();
	  const edges = graphEdges();
	  if (!nodes || !edges) return;
	  ensureFullGraphData();
	  mergeCurrentVisibleStateIntoAllData();

	  const uniqueNodeIds = Array.from(new Set(nodeIds || []))
	    .filter((id) => originalNodeById(id) || window.allNodes[id]);
	  const visible = new Set(uniqueNodeIds);
	  const requestedEdgeIds = Array.isArray(edgeIds)
	    ? Array.from(new Set(edgeIds))
	    : edgeIdsForVisibleNodes(uniqueNodeIds);
	  const edgeData = requestedEdgeIds
	    .map(graphEdgeDataForSubset)
	    .filter((edge) => edge && visible.has(edge.from) && visible.has(edge.to));

	  stopGraphMotion();
	  nodes.clear();
	  edges.clear();
	  nodes.add(uniqueNodeIds.map(graphNodeDataForSubset));
	  edges.add(edgeData);
	  GRAPH_UI_STATE.ui = {
	    ...(GRAPH_UI_STATE.ui || {}),
	    visibleNodeIds: uniqueNodeIds,
	    visibleEdgeIds: edgeData.map(edgeStableId)
	  };
	  applyTextSizes();
	  stopGraphMotion();
	  if (options.focusId && visible.has(options.focusId)) {
	    setSelectedNodesQuietly([options.focusId]);
	  }
	  if (options.fit !== false) safeFitToNodes(uniqueNodeIds);
	  setLayoutStatus(options.status || `Nodos visibles: ${uniqueNodeIds.length}`);
	}

	function showAllNodes(fit = true, options = {}) {
	  const nodes = graphNodes();
	  const edges = graphEdges();
	  if (!nodes || !edges) return;
	  ensureFullGraphData();
	  mergeCurrentVisibleStateIntoAllData();

	  const nodeIds = ORIGINAL_GRAPH_DATA.nodes.map((node) => node.id);
	  const edgeIds = ORIGINAL_GRAPH_DATA.edges.map(edgeStableId);
	  stopGraphMotion();
	  nodes.clear();
	  edges.clear();
	  nodes.add(nodeIds.map(graphNodeDataForSubset));
	  edges.add(edgeIds.map(graphEdgeDataForSubset));
	  GRAPH_UI_STATE.ui = {
	    ...(GRAPH_UI_STATE.ui || {}),
	    selectedType: "",
	    visibleNodeIds: null,
	    visibleEdgeIds: null
	  };
	  const typeSelector = document.getElementById("nodeTypeSelector");
	  if (typeSelector && !options.preserveTypeSelector) typeSelector.value = "";
	  applyTextSizes();
	  stopGraphMotion();
	  if (fit && !options.skipFit) safeFitToNodes(nodeIds);
	  setLayoutStatus("Grafo completo restaurado.");
	  const info = document.getElementById("node-info");
	  if (info && !GRAPH_UI_STATE.ui.selectedNodeId) info.textContent = "Selecciona un nodo para ver su ficha.";
	}

	function filterByType(type) {
	  ensureFullGraphData();
	  const selectedType = canonicalType(type);
	  if (!selectedType) {
	    showAllNodes(true);
	    return;
	  }

	  const ids = ORIGINAL_GRAPH_DATA.nodes
	    .filter((node) => nodeTypeValue(node) === selectedType)
	    .map((node) => node.id);
	  if (ids.length === 0) {
	    setLayoutStatus(`No hay nodos de tipo ${typeLabel(selectedType)}.`);
	    return;
	  }

	  GRAPH_UI_STATE.ui = {
	    ...(GRAPH_UI_STATE.ui || {}),
	    selectedType
	  };
	  const typeSelector = document.getElementById("nodeTypeSelector");
	  if (typeSelector) typeSelector.value = selectedType;
	  renderGraphSubset(ids, edgeIdsForVisibleNodes(ids), {
	    status: `${typeLabel(selectedType)}: ${ids.length} nodos`,
	    fit: true
	  });
	  const info = document.getElementById("node-info");
	  if (info) info.textContent = `${typeLabel(selectedType)}: ${ids.length} nodos visibles.`;
	}

	function resolveNodeId(rawValue) {
	  ensureFullGraphData();
	  const raw = String(rawValue || "").trim();
	  if (!raw) return "";
	  if (window.allNodes[raw]) return raw;
	  const lower = raw.toLowerCase();
	  return Object.keys(window.allNodes).find((id) => {
	    const node = window.allNodes[id];
	    return id.toLowerCase() === lower ||
	      id.toLowerCase().includes(lower) ||
	      nodeDisplayName(node).toLowerCase() === lower ||
	      nodeDisplayName(node).toLowerCase().includes(lower);
	  }) || "";
	}

	function focusNodeByInput() {
	  const selector = document.getElementById("nodeIdSelector");
	  const input = document.getElementById("nodeSearchInput");
	  const nodeId = resolveNodeId((input && input.value) || (selector && selector.value) || "");
	  if (!nodeId) {
	    updateNodeInfo(null);
	    setLayoutStatus("Selecciona o escribe un nodo valido.");
	    return;
	  }
	  focusNodeById(nodeId);
	}

	function focusNodeFromSelector() {
	  const selector = document.getElementById("nodeIdSelector");
	  const input = document.getElementById("nodeSearchInput");
	  const nodeId = resolveNodeId((selector && selector.value) || "");
	  if (input) input.value = nodeId || "";
	  if (!nodeId) {
	    updateNodeInfo(null);
	    setLayoutStatus("Selecciona un nodo valido.");
	    return;
	  }
	  focusNodeById(nodeId);
	}

	function focusNodeById(nodeId) {
	  ensureFullGraphData();
	  const resolvedId = resolveNodeId(nodeId);
	  if (!resolvedId || !window.allNodes[resolvedId]) {
	    setLayoutStatus("Nodo no encontrado.");
	    return;
	  }
	  if (!visibleNodeIds().includes(resolvedId)) {
	    showAllNodes(false, { skipFit: true });
	  }
	  stopGraphMotion();
	  setSelectedNodesQuietly([resolvedId]);
	  safeFitToNodes([resolvedId]);
	  updateNodeInfo(resolvedId);
	  setLayoutStatus(`Nodo enfocado: ${resolvedId}`);
	}

	function selectedOrInputNodeId() {
	  const selected = selectedNodeIds();
	  if (selected.length > 0) return selected[0];
	  const input = document.getElementById("nodeSearchInput");
	  const selector = document.getElementById("nodeIdSelector");
	  return resolveNodeId((input && input.value) || (selector && selector.value) || "");
	}

	function showSelectedNeighborhood() {
	  const nodeId = selectedOrInputNodeId();
	  if (!nodeId) {
	    setLayoutStatus("Selecciona o escribe un nodo primero.");
	    return;
	  }
	  const ids = new Set([nodeId]);
	  ensureFullGraphData();
	  ORIGINAL_GRAPH_DATA.edges.forEach((edge) => {
	    if (edge.from === nodeId) ids.add(edge.to);
	    if (edge.to === nodeId) ids.add(edge.from);
	  });
	  const visibleIds = Array.from(ids);
	  renderGraphSubset(visibleIds, edgeIdsForVisibleNodes(visibleIds), {
	    focusId: nodeId,
	    status: `Vecinos de ${nodeId}: ${visibleIds.length} nodos`
	  });
	}

	function typeNamesInGraph() {
	  ensureFullGraphData();
	  return Array.from(new Set(
	    ORIGINAL_GRAPH_DATA.nodes.map(nodeTypeValue).filter(Boolean)
	  )).sort((a, b) => typeLabel(a).localeCompare(typeLabel(b)));
	}

	function populateNodeSelector(attempt = 0) {
	  const selector = document.getElementById("nodeIdSelector");
	  const list = document.getElementById("nodeSearchList");
	  if (!selector || !list) {
	    if (attempt < 40) setTimeout(() => populateNodeSelector(attempt + 1), 150);
	    return;
	  }
	  ensureFullGraphData();
	  selector.innerHTML = '<option value="">Seleccionar nodo</option>';
	  list.innerHTML = "";
	  Object.values(window.allNodes)
	    .sort((a, b) => nodeDisplayName(a).localeCompare(nodeDisplayName(b)))
	    .forEach((node) => {
	      const name = nodeDisplayName(node);
	      const option = document.createElement("option");
	      option.value = node.id;
	      option.textContent = name && name !== node.id ? `${name} (${node.id})` : node.id;
	      selector.appendChild(option);

	      const dataOption = document.createElement("option");
	      dataOption.value = node.id;
	      dataOption.label = name || node.id;
	      list.appendChild(dataOption);
	    });
	}

	function populateTypeSelector(attempt = 0) {
	  const selector = document.getElementById("nodeTypeSelector");
	  if (!selector) {
	    if (attempt < 40) setTimeout(() => populateTypeSelector(attempt + 1), 150);
	    return;
	  }
	  ensureFullGraphData();
	  const currentValue = selector.value || GRAPH_UI_STATE.ui.selectedType || "";
	  selector.innerHTML = '<option value="">Todos los tipos</option>';
	  typeNamesInGraph().forEach((type) => {
	    const option = document.createElement("option");
	    option.value = type;
	    option.textContent = typeLabel(type);
	    selector.appendChild(option);
	  });
	  if (currentValue && Array.from(selector.options).some((option) => option.value === currentValue)) {
	    selector.value = currentValue;
	  }
	}

	function renderTypeLegend(attempt = 0) {
	  const legend = document.getElementById("node-type-legend");
	  if (!legend) {
	    if (attempt < 40) setTimeout(() => renderTypeLegend(attempt + 1), 150);
	    return;
	  }
	  ensureFullGraphData();
	  const rows = typeNamesInGraph().map((type) => {
	    const node = ORIGINAL_GRAPH_DATA.nodes.find((item) => nodeTypeValue(item) === type) || {};
	    const color = colorValue(node.color) || TYPE_COLORS[type] || "#E0E0E0";
	    return `<button class="type-legend-row" type="button" onclick="filterByType(${JSON.stringify(type)})">
	      <span class="type-legend-dot" style="background:${escapeHtml(color)}"></span>
	      <span>${escapeHtml(typeLabel(type))}</span>
	    </button>`;
	  });
	  legend.innerHTML = rows.length ? rows.join("") : '<div class="left-panel-empty">Sin tipos visibles.</div>';
	}

	function updateNodeInfo(nodeId) {
	  const info = document.getElementById("node-info");
	  if (!info) return;
	  ensureFullGraphData();
	  const resolvedId = resolveNodeId(nodeId);
	  if (!resolvedId) {
	    info.textContent = "Selecciona un nodo para ver su ficha.";
	    return;
	  }
	  const nodes = graphNodes();
	  const node = (nodes && nodes.get(resolvedId)) || window.allNodes[resolvedId];
	  if (!node) {
	    info.textContent = "Nodo no encontrado.";
	    return;
	  }
	  const incoming = ORIGINAL_GRAPH_DATA.edges.filter((edge) => edge.to === resolvedId).length;
	  const outgoing = ORIGINAL_GRAPH_DATA.edges.filter((edge) => edge.from === resolvedId).length;
	  const nodeInfo = node.nodeInfo || {};
	  const description = node.description || nodeInfo.description || node.content || nodeInfo.content || "";
	  const shortDescription = String(description || "").replace(/\\s+/g, " ").trim().slice(0, 420);
	  const categories = nodeCategories(node);
	  const rows = [
	    ["Tipo", typeLabel(nodeTypeValue(node))],
	    ["Area", categories.join(", ")],
	    ["Fuente", nodeSource(node)],
	    ["ID", resolvedId],
	    ["Relaciones entrantes", incoming],
	    ["Relaciones salientes", outgoing],
	    ["Referencia", node.referenceText || nodeInfo.reference],
	    ["Contenido breve", shortDescription]
	  ].filter((row) => row[1] !== undefined && row[1] !== null && row[1] !== "");

	  info.innerHTML = `<div class="node-info-title">${escapeHtml(nodeDisplayName(node))}</div>` +
	    rows.map(([key, value]) => `<div><strong>${escapeHtml(key)}:</strong> ${escapeHtml(value)}</div>`).join("");
	  GRAPH_UI_STATE.ui = {
	    ...(GRAPH_UI_STATE.ui || {}),
	    selectedNodeId: resolvedId
	  };
	}

	function isLeftControlsVisible() {
	  return GRAPH_UI_STATE.ui.leftControlsVisible !== false;
	}

	function setLeftControlsVisible(visible) {
	  const resolvedVisible = Boolean(visible);
	  const panel = document.getElementById("left-graph-controls");
	  const button = document.getElementById("toggle-left-controls");
	  GRAPH_UI_STATE.ui = {
	    ...(GRAPH_UI_STATE.ui || {}),
	    leftControlsVisible: resolvedVisible
	  };
	  if (panel) panel.style.display = resolvedVisible ? "block" : "none";
	  if (button) {
	    button.textContent = resolvedVisible ? "🎨 Ocultar leyenda" : "🎨 Mostrar leyenda";
	    button.setAttribute("aria-expanded", String(resolvedVisible));
	    button.classList.toggle("panel-hidden", !resolvedVisible);
	  }
	  if (window.mmNetwork) {
	    window.mmNetwork.redraw();
	  }
	}

	function toggleLeftControls() {
	  setLeftControlsVisible(!isLeftControlsVisible());
	}

	function bindGraphNavigationEvents() {
	  if (!window.mmNetwork || window.mmNavigationEventsBound) return;
	  window.mmNetwork.on("selectNode", function(params) {
	    if (MM_SUPPRESS_SELECT_HANDLER) return;
	    if (params.nodes && params.nodes.length > 0) {
	      const nodeId = params.nodes[0];
	      const selector = document.getElementById("nodeIdSelector");
	      const input = document.getElementById("nodeSearchInput");
	      if (selector) selector.value = nodeId;
	      if (input) input.value = nodeId;
	      updateNodeInfo(nodeId);
	    }
	  });
	  window.mmNetwork.on("deselectNode", function() {
	    if (MM_SUPPRESS_SELECT_HANDLER) return;
	    GRAPH_UI_STATE.ui = {
	      ...(GRAPH_UI_STATE.ui || {}),
	      selectedNodeId: ""
	    };
	  });
	  window.mmNavigationEventsBound = true;
	}

	function initializeGraphNavigation(attempt = 0) {
	  const nodes = graphNodes();
	  const edges = graphEdges();
	  if (!window.mmNetwork || !nodes || !edges) {
	    if (attempt < 60) setTimeout(() => initializeGraphNavigation(attempt + 1), 150);
	    return;
	  }
	  cacheOriginalGraphData();
	  bindGraphNavigationEvents();
	  populateNodeSelector();
	  populateTypeSelector();
	  renderTypeLegend();
	  const selectedNodeId = GRAPH_UI_STATE.ui.selectedNodeId;
	  if (selectedNodeId) updateNodeInfo(selectedNodeId);
	  else updateNodeInfo(null);
	  setLeftControlsVisible(isLeftControlsVisible());
	}

	function setLayoutStatus(text) {
	  const el = document.getElementById("layout-status");
	  if (el) el.textContent = text || "";
	}

function isPhysicsOverlayVisible() {
  const panel = document.getElementById("physics-overlay");
  if (!panel) return true;
  return panel.style.display !== "none";
}

function setPhysicsOverlayVisible(visible) {
  const panel = document.getElementById("physics-overlay");
  const button = document.getElementById("toggle-physics-overlay");
  const resolvedVisible = Boolean(visible);

  if (typeof GRAPH_UI_STATE !== "undefined") {
    GRAPH_UI_STATE.ui = {
      ...(GRAPH_UI_STATE.ui || {}),
      physicsOverlayVisible: resolvedVisible
    };
  }

  if (!panel || !button) return;

  panel.style.display = resolvedVisible ? "block" : "none";
  button.textContent = resolvedVisible ? "⚙️ Ocultar controles" : "⚙️ Mostrar controles";
  button.setAttribute("aria-expanded", String(resolvedVisible));
  button.classList.toggle("panel-hidden", !resolvedVisible);
}

function togglePhysicsOverlay() {
  setPhysicsOverlayVisible(!isPhysicsOverlayVisible());
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

	let MM_ACTIVE_LAYOUT_FRAME = null;
	let MM_ACTIVE_LAYOUT_TIMER = null;

	function visibleLayoutContext() {
	  const nodes = graphNodes();
	  const edges = graphEdges();
	  if (!window.mmNetwork || !nodes || !edges) return null;
	  ensureFullGraphData();
	  mergeCurrentVisibleStateIntoAllData();
	  const nodeItems = nodes.get().map(cloneGraphItem);
	  const nodeIds = nodeItems.map((node) => node.id).filter(Boolean);
	  const nodeSet = new Set(nodeIds);
	  const edgeItems = edges.get()
	    .map(cloneGraphItem)
	    .filter((edge) => nodeSet.has(edge.from) && nodeSet.has(edge.to));
	  const positions = window.mmNetwork.getPositions(nodeIds);
	  return { nodes, edges, nodeItems, nodeIds, nodeSet, edgeItems, positions };
	}

	function stableNodeKey(node) {
	  return nodeDisplayName(node).toLowerCase() || String(node.id || "").toLowerCase();
	}

	function degreeMapFor(nodeIds, edges) {
	  const degree = {};
	  nodeIds.forEach((id) => { degree[id] = 0; });
	  edges.forEach((edge) => {
	    if (degree[edge.from] !== undefined) degree[edge.from] += 1;
	    if (degree[edge.to] !== undefined) degree[edge.to] += 1;
	  });
	  return degree;
	}

	function groupNodesBy(nodeItems, groupFn) {
	  const groups = new Map();
	  nodeItems.forEach((node) => {
	    const rawGroup = groupFn(node) || "sin grupo";
	    const group = String(rawGroup).trim() || "sin grupo";
	    if (!groups.has(group)) groups.set(group, []);
	    groups.get(group).push(node.id);
	  });
	  for (const ids of groups.values()) {
	    ids.sort((a, b) => String(a).localeCompare(String(b)));
	  }
	  return groups;
	}

	function groupRadius(count, spacing = 170) {
	  if (count <= 1) return 170;
	  return Math.max(220, Math.sqrt(count) * spacing);
	}

	function edgeSubsetFor(nodeIds, edges) {
	  const nodeSet = new Set(nodeIds);
	  return edges.filter((edge) => nodeSet.has(edge.from) && nodeSet.has(edge.to));
	}

	function localForceLayout(nodeIds, edges, options = {}) {
	  const count = nodeIds.length;
	  if (count === 0) return {};
	  if (count === 1) return { [nodeIds[0]]: { x: 0, y: 0 } };

	  const degree = degreeMapFor(nodeIds, edges);
	  const sortedIds = [...nodeIds].sort((a, b) => {
	    const degreeDelta = (degree[b] || 0) - (degree[a] || 0);
	    return degreeDelta || String(a).localeCompare(String(b));
	  });
	  const positions = {};
	  const baseSpacing = options.spacing || 175;
	  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
	  sortedIds.forEach((id, index) => {
	    if (index === 0 && (degree[id] || 0) > 0) {
	      positions[id] = { x: 0, y: 0 };
	      return;
	    }
	    const adjusted = index + 0.35;
	    const radius = baseSpacing * Math.sqrt(adjusted) * 0.82;
	    const angle = adjusted * goldenAngle;
	    positions[id] = {
	      x: Math.cos(angle) * radius,
	      y: Math.sin(angle) * radius
	    };
	  });

	  const nodeSet = new Set(nodeIds);
	  const internalEdges = edges.filter((edge) => nodeSet.has(edge.from) && nodeSet.has(edge.to));
	  const iterations = options.iterations || 85;
	  const repulsion = options.repulsion || 5400;
	  const springLength = options.springLength || Math.max(180, Math.min(310, baseSpacing * 1.25));
	  const springStrength = options.springStrength || 0.018;
	  const gravity = options.gravity || 0.018;
	  const maxStep = options.maxStep || 28;

	  for (let iter = 0; iter < iterations; iter += 1) {
	    const delta = {};
	    nodeIds.forEach((id) => { delta[id] = { x: 0, y: 0 }; });

	    for (let i = 0; i < nodeIds.length; i += 1) {
	      for (let j = i + 1; j < nodeIds.length; j += 1) {
	        const a = nodeIds[i];
	        const b = nodeIds[j];
	        const pa = positions[a];
	        const pb = positions[b];
	        let dx = pa.x - pb.x;
	        let dy = pa.y - pb.y;
	        let distanceSq = dx * dx + dy * dy;
	        if (distanceSq < 25) {
	          dx = (i + 1) * 0.17;
	          dy = (j + 1) * 0.19;
	          distanceSq = dx * dx + dy * dy;
	        }
	        const distance = Math.sqrt(distanceSq);
	        const force = repulsion / distanceSq;
	        const fx = (dx / distance) * force;
	        const fy = (dy / distance) * force;
	        delta[a].x += fx;
	        delta[a].y += fy;
	        delta[b].x -= fx;
	        delta[b].y -= fy;
	      }
	    }

	    internalEdges.forEach((edge) => {
	      const a = edge.from;
	      const b = edge.to;
	      const pa = positions[a];
	      const pb = positions[b];
	      if (!pa || !pb) return;
	      const dx = pb.x - pa.x;
	      const dy = pb.y - pa.y;
	      const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy));
	      const force = (distance - springLength) * springStrength;
	      const fx = (dx / distance) * force;
	      const fy = (dy / distance) * force;
	      delta[a].x += fx;
	      delta[a].y += fy;
	      delta[b].x -= fx;
	      delta[b].y -= fy;
	    });

	    nodeIds.forEach((id) => {
	      delta[id].x -= positions[id].x * gravity;
	      delta[id].y -= positions[id].y * gravity;
	      const step = Math.sqrt(delta[id].x * delta[id].x + delta[id].y * delta[id].y);
	      const scale = step > maxStep ? maxStep / step : 1;
	      positions[id].x += delta[id].x * scale;
	      positions[id].y += delta[id].y * scale;
	    });
	  }

	  const centroid = nodeIds.reduce((acc, id) => {
	    acc.x += positions[id].x;
	    acc.y += positions[id].y;
	    return acc;
	  }, { x: 0, y: 0 });
	  centroid.x /= count;
	  centroid.y /= count;
	  nodeIds.forEach((id) => {
	    positions[id].x = Math.round((positions[id].x - centroid.x) * 100) / 100;
	    positions[id].y = Math.round((positions[id].y - centroid.y) * 100) / 100;
	  });
	  return positions;
	}

	function componentGroupsFromContext(ctx) {
	  const adjacency = {};
	  ctx.nodeIds.forEach((id) => { adjacency[id] = new Set(); });
	  ctx.edgeItems.forEach((edge) => {
	    if (!adjacency[edge.from] || !adjacency[edge.to]) return;
	    adjacency[edge.from].add(edge.to);
	    adjacency[edge.to].add(edge.from);
	  });

	  const visited = new Set();
	  const components = [];
	  ctx.nodeIds.forEach((start) => {
	    if (visited.has(start)) return;
	    const queue = [start];
	    const component = [];
	    visited.add(start);
	    while (queue.length > 0) {
	      const current = queue.shift();
	      component.push(current);
	      adjacency[current].forEach((next) => {
	        if (visited.has(next)) return;
	        visited.add(next);
	        queue.push(next);
	      });
	    }
	    component.sort((a, b) => String(a).localeCompare(String(b)));
	    components.push(component);
	  });
	  components.sort((a, b) => b.length - a.length || String(a[0]).localeCompare(String(b[0])));
	  return components;
	}

	function sourceGroupCenters(groups) {
	  const entries = [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
	  const maxRadius = Math.max(...entries.map(([, ids]) => groupRadius(ids.length, 180)), 240);
	  const columns = Math.max(1, Math.ceil(Math.sqrt(entries.length)));
	  const xGap = Math.max(900, maxRadius * 2 + 520);
	  const yGap = Math.max(680, maxRadius * 2 + 380);
	  const centers = {};
	  entries.forEach(([group], index) => {
	    const row = Math.floor(index / columns);
	    const col = index % columns;
	    const rowOffset = row % 2 === 1 ? xGap * 0.22 : 0;
	    centers[group] = {
	      x: (col - (columns - 1) / 2) * xGap + rowOffset,
	      y: (row - Math.floor((entries.length - 1) / columns) / 2) * yGap
	    };
	  });
	  return centers;
	}

	function typeGroupCenters(groups) {
	  const canonicalOrder = [
	    "definicion",
	    "lema",
	    "teorema",
	    "proposicion",
	    "corolario",
	    "ejemplo",
	    "nota",
	    "observacion",
	    "otro",
	    "placeholder"
	  ];
	  const maxRadius = Math.max(...[...groups.values()].map((ids) => groupRadius(ids.length, 165)), 240);
	  const scale = Math.max(1, maxRadius / 360);
	  const template = {
	    definicion: { x: -1250, y: -420 },
	    lema: { x: -470, y: -700 },
	    teorema: { x: 350, y: -720 },
	    proposicion: { x: -250, y: -30 },
	    corolario: { x: 720, y: -20 },
	    ejemplo: { x: -520, y: 680 },
	    nota: { x: 520, y: 680 },
	    observacion: { x: 1180, y: 620 },
	    otro: { x: 0, y: 1180 },
	    placeholder: { x: 1220, y: -680 }
	  };
	  const centers = {};
	  const present = [...groups.keys()];
	  present.forEach((group) => {
	    const canonical = canonicalType(group);
	    if (template[canonical]) {
	      centers[group] = {
	        x: template[canonical].x * scale,
	        y: template[canonical].y * scale
	      };
	    }
	  });
	  const extras = present
	    .filter((group) => !centers[group])
	    .sort((a, b) => a.localeCompare(b));
	  const extraRadius = 1250 * scale;
	  extras.forEach((group, index) => {
	    const angle = (Math.PI * 2 * index) / Math.max(1, extras.length) + Math.PI / 8;
	    centers[group] = {
	      x: Math.cos(angle) * extraRadius,
	      y: Math.sin(angle) * extraRadius + 1200 * scale
	    };
	  });

	  const orderedPresent = canonicalOrder.filter((type) => present.some((group) => canonicalType(group) === type));
	  if (orderedPresent.length <= 2 && extras.length === 0) {
	    present.forEach((group, index) => {
	      centers[group].x = (index - (present.length - 1) / 2) * 1050 * scale;
	      centers[group].y = centers[group].y * 0.35;
	    });
	  }
	  return centers;
	}

	function componentGroupCenters(components) {
	  const maxRadius = Math.max(...components.map((ids) => groupRadius(ids.length, 190)), 260);
	  const columns = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(components.length))));
	  const xGap = Math.max(1250, maxRadius * 2 + 900);
	  const yGap = Math.max(950, maxRadius * 2 + 650);
	  const rows = Math.ceil(components.length / columns);
	  const centers = {};
	  components.forEach((ids, index) => {
	    const row = Math.floor(index / columns);
	    const col = index % columns;
	    centers[`component:${index}`] = {
	      x: (col - (columns - 1) / 2) * xGap,
	      y: (row - (rows - 1) / 2) * yGap
	    };
	  });
	  return centers;
	}

	function edgeAwareOffsets(groupByNode, centersByGroup, edges, strength = 0.16) {
	  const offsets = {};
	  Object.keys(groupByNode).forEach((id) => { offsets[id] = { x: 0, y: 0, count: 0 }; });
	  edges.forEach((edge) => {
	    const fromGroup = groupByNode[edge.from];
	    const toGroup = groupByNode[edge.to];
	    if (!fromGroup || !toGroup || fromGroup === toGroup) return;
	    const fromCenter = centersByGroup[fromGroup];
	    const toCenter = centersByGroup[toGroup];
	    if (!fromCenter || !toCenter) return;
	    const dx = toCenter.x - fromCenter.x;
	    const dy = toCenter.y - fromCenter.y;
	    const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy));
	    const pushX = (dx / distance) * 130 * strength;
	    const pushY = (dy / distance) * 130 * strength;
	    offsets[edge.from].x += pushX;
	    offsets[edge.from].y += pushY;
	    offsets[edge.from].count += 1;
	    offsets[edge.to].x -= pushX;
	    offsets[edge.to].y -= pushY;
	    offsets[edge.to].count += 1;
	  });
	  const normalized = {};
	  Object.entries(offsets).forEach(([id, offset]) => {
	    if (!offset.count) {
	      normalized[id] = { x: 0, y: 0 };
	      return;
	    }
	    const x = offset.x / Math.sqrt(offset.count);
	    const y = offset.y / Math.sqrt(offset.count);
	    const magnitude = Math.sqrt(x * x + y * y);
	    const maxOffset = 155;
	    const scale = magnitude > maxOffset ? maxOffset / magnitude : 1;
	    normalized[id] = { x: x * scale, y: y * scale };
	  });
	  return normalized;
	}

	function composeGroupedLayout(ctx, groups, centers, options = {}) {
	  const groupByNode = {};
	  for (const [group, ids] of groups.entries()) {
	    ids.forEach((id) => { groupByNode[id] = group; });
	  }
	  const offsets = options.crossEdgeOffsets
	    ? edgeAwareOffsets(groupByNode, centers, ctx.edgeItems, options.crossEdgeStrength || 0.16)
	    : {};
	  const targetPositions = {};
	  for (const [group, ids] of groups.entries()) {
	    const center = centers[group] || { x: 0, y: 0 };
	    const localEdges = options.localEdges === false ? [] : edgeSubsetFor(ids, ctx.edgeItems);
	    const local = localForceLayout(ids, localEdges, options.local || {});
	    ids.forEach((id) => {
	      const offset = offsets[id] || { x: 0, y: 0 };
	      targetPositions[id] = {
	        x: center.x + (local[id]?.x || 0) + offset.x,
	        y: center.y + (local[id]?.y || 0) + offset.y
	      };
	    });
	  }
	  return targetPositions;
	}

	function buildSourceLayout(ctx) {
	  const groups = groupNodesBy(ctx.nodeItems, nodeSource);
	  const centers = sourceGroupCenters(groups);
	  return composeGroupedLayout(ctx, groups, centers, {
	    crossEdgeOffsets: true,
	    crossEdgeStrength: 0.22,
	    local: {
	      spacing: 180,
	      iterations: 95,
	      repulsion: 6600,
	      springLength: 215,
	      springStrength: 0.02,
	      gravity: 0.02
	    }
	  });
	}

	function buildTypeLayout(ctx) {
	  const groups = groupNodesBy(ctx.nodeItems, nodeTypeValue);
	  const centers = typeGroupCenters(groups);
	  return composeGroupedLayout(ctx, groups, centers, {
	    crossEdgeOffsets: true,
	    crossEdgeStrength: 0.12,
	    local: {
	      spacing: 165,
	      iterations: 90,
	      repulsion: 5600,
	      springLength: 205,
	      springStrength: 0.018,
	      gravity: 0.022
	    }
	  });
	}

	function buildComponentLayout(ctx) {
	  const components = componentGroupsFromContext(ctx);
	  const centers = componentGroupCenters(components);
	  const groups = new Map();
	  components.forEach((ids, index) => {
	    groups.set(`component:${index}`, ids);
	  });
	  return composeGroupedLayout(ctx, groups, centers, {
	    crossEdgeOffsets: false,
	    local: {
	      spacing: 190,
	      iterations: 120,
	      repulsion: 7200,
	      springLength: 230,
	      springStrength: 0.024,
	      gravity: 0.016
	    }
	  });
	}

	const GRAPH_LAYOUT_STRATEGIES = {
	  type: {
	    label: "tipo de concepto",
	    build: buildTypeLayout,
	    status: "Separado por tipo: cada tipo ocupa una zona semantica propia.",
	    physics: {
	      gravitationalConstant: -95,
	      centralGravity: 0.0008,
	      springLength: 245,
	      springConstant: 0.004,
	      damping: 0.33,
	      maxVelocity: 26,
	      minVelocity: 0.18,
	      timestep: 0.28,
	      duration: 900
	    }
	  },
	  source: {
	    label: "fuente",
	    build: buildSourceLayout,
	    status: "Separado por fuente: sources en islas con espacio visible entre grupos.",
	    physics: {
	      gravitationalConstant: -110,
	      centralGravity: 0.0006,
	      springLength: 265,
	      springConstant: 0.003,
	      damping: 0.36,
	      maxVelocity: 24,
	      minVelocity: 0.16,
	      timestep: 0.26,
	      duration: 850
	    }
	  },
	  component: {
	    label: "componente conexa",
	    build: buildComponentLayout,
	    status: "Separado por componentes: las partes desconectadas quedan en islas lejanas.",
	    physics: {
	      gravitationalConstant: -125,
	      centralGravity: 0.0008,
	      springLength: 260,
	      springConstant: 0.02,
	      damping: 0.38,
	      maxVelocity: 22,
	      minVelocity: 0.14,
	      timestep: 0.24,
	      duration: 1900
	    }
	  }
	};

	function cancelActiveLayoutAnimation() {
	  if (MM_ACTIVE_LAYOUT_FRAME !== null) {
	    if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(MM_ACTIVE_LAYOUT_FRAME);
	    clearTimeout(MM_ACTIVE_LAYOUT_FRAME);
	    MM_ACTIVE_LAYOUT_FRAME = null;
	  }
	  if (MM_ACTIVE_LAYOUT_TIMER !== null) {
	    clearTimeout(MM_ACTIVE_LAYOUT_TIMER);
	    MM_ACTIVE_LAYOUT_TIMER = null;
	  }
	}

	function easeInOutCubic(t) {
	  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
	}

	function layoutPhysicsOptions(profile) {
	  return {
	    enabled: true,
	    solver: "forceAtlas2Based",
	    stabilization: {
	      enabled: true,
	      iterations: 120,
	      updateInterval: 20,
	      fit: false
	    },
	    forceAtlas2Based: {
	      gravitationalConstant: profile.gravitationalConstant,
	      centralGravity: profile.centralGravity,
	      springLength: profile.springLength,
	      springConstant: profile.springConstant,
	      avoidOverlap: 0.95
	    },
	    damping: profile.damping,
	    maxVelocity: profile.maxVelocity,
	    minVelocity: profile.minVelocity,
	    timestep: profile.timestep,
	    adaptiveTimestep: true
	  };
	}

	function settleLayoutWithPhysics(strategy, ids, targetPositions) {
	  if (!window.mmNetwork) return;
	  const profile = strategy.physics;
	  window.mmNetwork.setOptions({ physics: layoutPhysicsOptions(profile) });
	  GRAPH_UI_STATE.physics = {
	    mode: `layout:${strategy.label}`,
	    enabled: true,
	    gravitationalConstant: Math.abs(profile.gravitationalConstant),
	    centralGravity: Math.round(profile.centralGravity * 100),
	    springLength: profile.springLength,
	    springConstant: Math.round(profile.springConstant * 1000),
	    damping: Math.round(profile.damping * 100),
	    maxVelocity: profile.maxVelocity,
	    minVelocity: Math.round(profile.minVelocity * 100),
	    timestep: Math.round(profile.timestep * 100)
	  };
	  window.mmNetwork.startSimulation();
	  MM_ACTIVE_LAYOUT_TIMER = setTimeout(() => {
	    MM_ACTIVE_LAYOUT_TIMER = null;
	    if (!window.mmNetwork) return;
	    window.mmNetwork.stopSimulation();
	    window.mmNetwork.setOptions({ physics: { enabled: false } });
	    const settledPositions = window.mmNetwork.getPositions(ids);
	    const corrected = ids.map((id) => {
	      const target = targetPositions[id];
	      const settled = settledPositions[id] || target;
	      return {
	        id,
	        x: target.x * 0.82 + settled.x * 0.18,
	        y: target.y * 0.82 + settled.y * 0.18,
	        fixed: { x: false, y: false }
	      };
	    });
	    graphNodes().update(corrected);
	    GRAPH_UI_STATE.physics = {
	      ...(GRAPH_UI_STATE.physics || {}),
	      enabled: false,
	      mode: `layout:${strategy.label}:stable`
	    };
	    mergeCurrentVisibleStateIntoAllData();
	    window.mmNetwork.fit({
	      nodes: ids,
	      animation: { duration: 450, easingFunction: "easeInOutQuad" }
	    });
	    setLayoutStatus(`${strategy.status} Fisica estabilizada.`);
	  }, profile.duration || 1700);
	}

	function animateNodePositions(targetPositions, strategy) {
	  const nodes = graphNodes();
	  if (!window.mmNetwork || !nodes) return;
	  const ids = Object.keys(targetPositions).filter((id) => ctxNodeExists(nodes, id));
	  if (ids.length === 0) return;
	  const currentPositions = window.mmNetwork.getPositions(ids);
	  cancelActiveLayoutAnimation();
	  window.mmNetwork.stopSimulation();
	  window.mmNetwork.setOptions({ physics: { enabled: false } });

	  const start = performance.now();
	  const duration = 1050;
	  const frame = (now) => {
	    const t = Math.min(1, (now - start) / duration);
	    const eased = easeInOutCubic(t);
	    const updates = ids.map((id) => {
	      const from = currentPositions[id] || { x: 0, y: 0 };
	      const to = targetPositions[id];
	      return {
	        id,
	        x: from.x + (to.x - from.x) * eased,
	        y: from.y + (to.y - from.y) * eased,
	        fixed: { x: true, y: true }
	      };
	    });
	    nodes.update(updates);
	    if (t < 1) {
	      MM_ACTIVE_LAYOUT_FRAME = requestAnimationFrame(frame);
	      return;
	    }
	    MM_ACTIVE_LAYOUT_FRAME = null;
	    nodes.update(ids.map((id) => ({
	      id,
	      x: targetPositions[id].x,
	      y: targetPositions[id].y,
	      fixed: { x: false, y: false }
	    })));
	    window.mmNetwork.fit({
	      nodes: ids,
	      animation: { duration: 500, easingFunction: "easeInOutQuad" }
	    });
	    settleLayoutWithPhysics(strategy, ids, targetPositions);
	  };
	  MM_ACTIVE_LAYOUT_FRAME = requestAnimationFrame(frame);
	}

	function ctxNodeExists(nodes, id) {
	  try {
	    return Boolean(nodes.get(id));
	  } catch (err) {
	    return false;
	  }
	}

	function runGraphLayoutStrategy(strategyName) {
	  const strategy = GRAPH_LAYOUT_STRATEGIES[strategyName];
	  const ctx = visibleLayoutContext();
	  if (!strategy || !ctx || ctx.nodeIds.length === 0) {
	    setLayoutStatus("No hay nodos visibles para organizar.");
	    return;
	  }
	  setLayoutStatus(`Calculando layout por ${strategy.label}...`);
	  const targetPositions = strategy.build(ctx);
	  animateNodePositions(targetPositions, strategy);
	}

	function separateByType() {
	  runGraphLayoutStrategy("type");
	}

	function separateBySource() {
	  runGraphLayoutStrategy("source");
	}

	function separateByComponent() {
	  runGraphLayoutStrategy("component");
	}

	function resetPositions() {
	  runGraphLayoutStrategy("type");
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

function edgeLabelSizeValue() {
  const input = document.getElementById("edgeLabelSize");
  return input ? Number(input.value) : 13;
}

function nodeLabelSizeValue() {
  const input = document.getElementById("nodeLabelSize");
  return input ? Number(input.value) : 18;
}

function updateTextSizeLabels() {
  const edgeLabel = document.getElementById("edgeLabelSizeValue");
  const nodeLabel = document.getElementById("nodeLabelSizeValue");
  if (edgeLabel) edgeLabel.textContent = String(edgeLabelSizeValue());
  if (nodeLabel) nodeLabel.textContent = String(nodeLabelSizeValue());
}

function textControlState() {
  return {
    edgeLabelSize: edgeLabelSizeValue(),
    nodeLabelSize: nodeLabelSizeValue()
  };
}

function applyTextSizes() {
  const nodes = graphNodes();
  const edges = graphEdges();
  const edgeSize = edgeLabelSizeValue();
  const nodeSize = nodeLabelSizeValue();
  updateTextSizeLabels();
  GRAPH_UI_STATE.nodeControls = textControlState();

  if (edges) {
    const edgeUpdates = edges.get().map((edge) => ({
      id: edge.id,
      font: {
        ...(edge.font || {}),
        size: edgeSize
      }
    }));
    edges.update(edgeUpdates);
  }

  if (nodes) {
    const nodeUpdates = nodes.get().map((node) => {
      const update = {
        id: node.id,
        font: {
          ...(node.font || {}),
          size: nodeSize,
          bold: {
            ...((node.font && node.font.bold) || {}),
            size: Math.max(9, Math.round(nodeSize * 0.62))
          }
        }
      };
      if (node.shape === "image") {
        update.size = Math.max(22, Math.round(nodeSize * 2.1));
      }
      return update;
    });
    nodes.update(nodeUpdates);
  }

  if (window.mmNetwork) {
    window.mmNetwork.redraw();
  }
}

	function currentNodeSnapshot() {
	  const nodes = graphNodes();
	  if (!window.mmNetwork || !nodes) return [];
	  const nodeIds = nodes.getIds ? nodes.getIds() : nodes.get().map((node) => node.id);
	  const positions = window.mmNetwork.getPositions(nodeIds);
	  return nodes.get(nodeIds).map((node) => ({
	    ...cloneGraphItem(node),
	    x: positions[node.id]?.x ?? node.x,
	    y: positions[node.id]?.y ?? node.y,
	    fixed: node.fixed ?? false
	  }));
	}

	function currentEdgeSnapshot() {
	  const edges = graphEdges();
	  return edges ? edges.get().map(cloneGraphItem) : [];
	}

	function currentFullNodeSnapshot() {
	  ensureFullGraphData();
	  mergeCurrentVisibleStateIntoAllData();
	  return Object.values(window.allNodes).map(cloneGraphItem);
	}

	function currentFullEdgeSnapshot() {
	  ensureFullGraphData();
	  mergeCurrentVisibleStateIntoAllData();
	  return Object.values(window.allEdges).map(cloneGraphItem);
	}

	function currentGraphState() {
	  const edgeControls = edgeControlState();
	  const nodeControls = textControlState();
	  const selection = selectedNodeIds();
	  const uiControls = {
	    ...(GRAPH_UI_STATE.ui || {}),
	    physicsOverlayVisible: isPhysicsOverlayVisible(),
	    leftControlsVisible: isLeftControlsVisible(),
	    selectedType: document.getElementById("nodeTypeSelector")?.value || GRAPH_UI_STATE.ui.selectedType || "",
	    selectedNodeId: selection[0] || GRAPH_UI_STATE.ui.selectedNodeId || "",
	    visibleNodeIds: visibleNodeIds(),
	    visibleEdgeIds: visibleEdgeIds()
	  };
	  GRAPH_UI_STATE.edgeControls = edgeControls;
	  GRAPH_UI_STATE.nodeControls = nodeControls;
	  GRAPH_UI_STATE.ui = uiControls;
  GRAPH_UI_STATE.physics = {
    ...GRAPH_UI_STATE.physics,
    ...physicsControlState(GRAPH_UI_STATE.physics.mode, GRAPH_UI_STATE.physics.enabled)
  };

	  return {
	    version: 1,
	    exportedAt: new Date().toISOString(),
	    nodes: currentNodeSnapshot(),
	    edges: currentEdgeSnapshot(),
	    fullNodes: currentFullNodeSnapshot(),
	    fullEdges: currentFullEdgeSnapshot(),
	    physics: GRAPH_UI_STATE.physics,
	    edgeControls,
	    nodeControls,
	    uiControls,
	    layout: GRAPH_LAYOUTS,
	    selection,
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

	  function restoredPhysicsOverlayVisible() {
	    if (state.uiControls && typeof state.uiControls.physicsOverlayVisible === "boolean") {
	      return state.uiControls.physicsOverlayVisible;
	    }
    if (state.ui && typeof state.ui.physicsOverlayVisible === "boolean") {
      return state.ui.physicsOverlayVisible;
    }
	    return true;
	  }

	  function restoredLeftControlsVisible() {
	    if (state.uiControls && typeof state.uiControls.leftControlsVisible === "boolean") {
	      return state.uiControls.leftControlsVisible;
	    }
	    if (state.ui && typeof state.ui.leftControlsVisible === "boolean") {
	      return state.ui.leftControlsVisible;
	    }
	    return true;
	  }

	  function exportedFullNodes() {
	    if (Array.isArray(state.fullNodes) && state.fullNodes.length > 0) {
	      return state.fullNodes;
	    }
	    return Array.isArray(state.nodes) ? state.nodes : [];
	  }

	  function exportedFullEdges() {
	    if (Array.isArray(state.fullEdges)) {
	      return state.fullEdges;
	    }
	    return Array.isArray(state.edges) ? state.edges : [];
	  }

	  function rebuildFullGraphCaches(fullNodes, fullEdges) {
	    if (typeof ORIGINAL_GRAPH_DATA === "undefined") return;
	    const copy = (item) => JSON.parse(JSON.stringify(item || {}));
	    const stableEdgeId = (edge) => {
	      if (!edge) return "";
	      if (edge.id !== undefined && edge.id !== null && edge.id !== "") return edge.id;
	      return String(edge.from || "") + "::" + String(edge.to || "") + "::" + String(edge.label || edge.title || "");
	    };
	    ORIGINAL_GRAPH_DATA.nodes = fullNodes.map(copy);
	    ORIGINAL_GRAPH_DATA.edges = fullEdges.map(copy);
	    window.allNodes = {};
	    fullNodes.forEach((node) => {
	      if (node && node.id !== undefined) window.allNodes[node.id] = copy(node);
	    });
	    window.allEdges = {};
	    fullEdges.forEach((edge) => {
	      const id = stableEdgeId(edge);
	      if (id) window.allEdges[id] = copy(edge);
	    });
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
	    const fullNodes = exportedFullNodes();
	    const fullEdges = exportedFullEdges();

	    nodes.clear();
	    edges.clear();
	    nodes.add(fullNodes);
	    edges.add(fullEdges);
	    rebuildFullGraphCaches(fullNodes, fullEdges);

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
    if (state.nodeControls) {
      setInputValue("edgeLabelSize", state.nodeControls.edgeLabelSize);
      setInputValue("nodeLabelSize", state.nodeControls.nodeLabelSize);
    }

    if (typeof updateEdgeRoundnessLabel === "function") {
      updateEdgeRoundnessLabel();
    }
    if (typeof updateTextSizeLabels === "function") {
      updateTextSizeLabels();
    }
	    if (typeof GRAPH_UI_STATE !== "undefined") {
	      const physicsOverlayVisible = restoredPhysicsOverlayVisible();
	      const leftControlsVisible = restoredLeftControlsVisible();
	      GRAPH_UI_STATE.physics = {
	        ...(state.physics || {}),
	        enabled: false,
	        mode: state.physics?.mode || "restored"
	      };
      GRAPH_UI_STATE.edgeControls = state.edgeControls || GRAPH_UI_STATE.edgeControls;
      GRAPH_UI_STATE.nodeControls = state.nodeControls || GRAPH_UI_STATE.nodeControls;
	      GRAPH_UI_STATE.ui = {
	        ...(state.uiControls || state.ui || GRAPH_UI_STATE.ui || {}),
	        physicsOverlayVisible,
	        leftControlsVisible
	      };
	    }
    if (state.layout) {
      GRAPH_LAYOUTS = state.layout;
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
	    if (typeof applyTextSizes === "function") {
	      applyTextSizes();
	    }
	    if (typeof setPhysicsOverlayVisible === "function") {
	      setPhysicsOverlayVisible(restoredPhysicsOverlayVisible());
	    }
	    if (typeof initializeGraphNavigation === "function") {
	      initializeGraphNavigation();
	    }
	    const visibleIds = state.uiControls && Array.isArray(state.uiControls.visibleNodeIds)
	      ? state.uiControls.visibleNodeIds
	      : null;
	    const visibleEdges = state.uiControls && Array.isArray(state.uiControls.visibleEdgeIds)
	      ? state.uiControls.visibleEdgeIds
	      : null;
	    if (
	      visibleIds &&
	      visibleIds.length > 0 &&
	      fullNodes.length > 0 &&
	      visibleIds.length < fullNodes.length &&
	      typeof renderGraphSubset === "function"
	    ) {
	      renderGraphSubset(visibleIds, visibleEdges, {
	        status: "Vista exportada restaurada.",
	        fit: true
	      });
	    }
	    if (typeof populateTypeSelector === "function") populateTypeSelector();
	    if (typeof populateNodeSelector === "function") populateNodeSelector();
	    if (typeof renderTypeLegend === "function") renderTypeLegend();
	    if (state.uiControls && state.uiControls.selectedType) {
	      const typeSelector = document.getElementById("nodeTypeSelector");
	      if (typeSelector) typeSelector.value = state.uiControls.selectedType;
	    }
	    if (typeof setLeftControlsVisible === "function") {
	      setLeftControlsVisible(restoredLeftControlsVisible());
	    }
	    net.redraw();
	    if (Array.isArray(state.selection) && state.selection.length > 0) {
	      if (typeof setSelectedNodesQuietly === "function") {
	        setSelectedNodesQuietly(state.selection);
	      } else {
	        net.selectNodes(state.selection);
	      }
	    } else if (state.uiControls && state.uiControls.selectedNodeId && typeof updateNodeInfo === "function") {
	      updateNodeInfo(state.uiControls.selectedNodeId);
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

  clone.querySelectorAll("#exported-graph-state-script, #exported-graph-state-runner").forEach((script) => script.remove());
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

function currentGraphStateJson() {
  return JSON.stringify(currentGraphState(), null, 2);
}

async function copyGraphStateJson() {
  const status = document.getElementById("download-status");
  if (!window.mmNetwork) {
    if (status) status.textContent = "El grafo todavía no está listo para copiar estado.";
    return;
  }

  const text = currentGraphStateJson();
  try {
    await navigator.clipboard.writeText(text);
    if (status) status.textContent = "Estado JSON copiado. Pégalo en Streamlit para guardar el mapa.";
  } catch (err) {
    downloadGraphStateJson();
    if (status) status.textContent = "No se pudo copiar; descargué el JSON como respaldo.";
  }
}

function downloadGraphStateJson() {
  if (!window.mmNetwork) {
    const status = document.getElementById("download-status");
    if (status) status.textContent = "El grafo todavía no está listo para exportar JSON.";
    return;
  }

  const blob = new Blob([currentGraphStateJson()], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  link.href = url;
  link.download = `knowledge_graph_state_${stamp}.json`;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);

  const status = document.getElementById("download-status");
  if (status) status.textContent = "JSON del estado actual generado.";
}
	</script>

	<style>
	#left-graph-controls {
	  position: fixed;
	  top: 50px;
	  left: 12px;
	  z-index: 9999;
	  background: rgba(255,255,255,0.96);
	  border: 1px solid #bbb;
	  border-radius: 8px;
	  padding: 10px;
	  font-family: Arial, sans-serif;
	  width: 282px;
	  max-height: calc(100vh - 66px);
	  overflow-y: auto;
	  box-shadow: 0 4px 16px rgba(0,0,0,.2);
	  box-sizing: border-box;
	}

	#toggle-left-controls {
	  position: fixed;
	  top: 12px;
	  left: 12px;
	  z-index: 10000;
	  background: rgba(255,255,255,0.96);
	  border: 1px solid #bbb;
	  border-radius: 8px;
	  padding: 6px 10px;
	  font-family: Arial, sans-serif;
	  font-size: 12px;
	  cursor: pointer;
	  box-shadow: 0 2px 8px rgba(0,0,0,.18);
	}

	#toggle-left-controls.panel-hidden {
	  background: rgba(255,255,255,0.9);
	}

	#left-graph-controls .left-panel-title {
	  font-size: 13px;
	  font-weight: 700;
	  margin: 2px 0 7px;
	  text-align: center;
	}

	#left-graph-controls .left-panel-section {
	  border-top: 1px solid #d1d5db;
	  margin-top: 9px;
	  padding-top: 8px;
	}

	#left-graph-controls .left-panel-section:first-of-type {
	  border-top: 0;
	  margin-top: 0;
	  padding-top: 0;
	}

	#left-graph-controls label {
	  display: block;
	  font-size: 11px;
	  font-weight: 600;
	  margin-bottom: 3px;
	}

	#left-graph-controls select,
	#left-graph-controls input[type=text] {
	  box-sizing: border-box;
	  width: 100%;
	  min-height: 28px;
	  border: 1px solid #d1d5db;
	  border-radius: 6px;
	  background: #ffffff;
	  font-family: Arial, sans-serif;
	  font-size: 11px;
	  margin-bottom: 5px;
	  padding: 4px 6px;
	}

	#left-graph-controls button {
	  width: 100%;
	  margin-top: 5px;
	}

	#left-graph-controls button:not(.type-legend-row) {
	  background: #ffffff;
	  border: 1px solid #d1d5db;
	  border-radius: 6px;
	  color: #111827;
	  cursor: pointer;
	  font-family: Arial, sans-serif;
	  font-size: 11px;
	  min-height: 28px;
	  padding: 5px 6px;
	}

	#left-graph-controls .type-legend-row {
	  align-items: center;
	  background: transparent;
	  border: 0;
	  color: #374151;
	  cursor: pointer;
	  display: flex;
	  font-size: 11px;
	  gap: 7px;
	  justify-content: flex-start;
	  margin: 3px 0;
	  padding: 2px 0;
	  text-align: left;
	}

	#left-graph-controls .type-legend-dot {
	  border: 1px solid #6b7280;
	  border-radius: 999px;
	  display: inline-block;
	  flex: 0 0 11px;
	  height: 11px;
	  width: 11px;
	}

	#left-graph-controls #node-info {
	  background: #f9fafb;
	  border: 1px solid #e5e7eb;
	  border-radius: 6px;
	  color: #4b5563;
	  font-size: 10px;
	  line-height: 1.3;
	  margin-top: 6px;
	  min-height: 28px;
	  padding: 7px;
	}

	#left-graph-controls .node-info-title {
	  color: #111827;
	  font-size: 12px;
	  font-weight: 700;
	  margin-bottom: 4px;
	}

	#left-graph-controls .left-panel-empty {
	  color: #6b7280;
	  font-size: 10px;
	}

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

#toggle-physics-overlay {
  position: fixed;
  top: 12px;
  right: 312px;
  z-index: 10000;
  background: rgba(255,255,255,0.96);
  border: 1px solid #bbb;
  border-radius: 8px;
  padding: 6px 10px;
  font-family: Arial, sans-serif;
  font-size: 12px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,.18);
}

#toggle-physics-overlay.panel-hidden {
  right: 12px;
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

	@media (max-width: 700px) {
	  #left-graph-controls {
	    top: 46px;
	    left: 8px;
	    width: min(282px, calc(100vw - 16px));
	    max-height: min(46vh, calc(100vh - 60px));
	  }

	  #toggle-left-controls {
	    left: 8px;
	  }

	  #physics-overlay {
	    top: 48px;
	    right: 8px;
	    width: min(268px, calc(100vw - 38px));
    max-height: calc(100vh - 64px);
  }

  #toggle-physics-overlay {
    right: 8px;
  }
	}
	</style>

	<button
	  id="toggle-left-controls"
	  type="button"
	  aria-controls="left-graph-controls"
	  aria-expanded="true"
	  onclick="toggleLeftControls()"
	>🎨 Ocultar leyenda</button>

	<div id="left-graph-controls">
	  <div class="left-panel-title">Navegación del mapa</div>

	  <div class="left-panel-section">
	    <label for="nodeIdSelector">Nodo</label>
	    <select id="nodeIdSelector" onchange="focusNodeFromSelector()">
	      <option value="">Seleccionar nodo</option>
	    </select>
	    <input id="nodeSearchInput" type="text" list="nodeSearchList" placeholder="id o nombre" oninput="document.getElementById('nodeIdSelector').value = ''">
	    <datalist id="nodeSearchList"></datalist>
	    <button onclick="focusNodeByInput()" title="Selecciona y centra el nodo indicado.">🔎 Enfocar nodo</button>
	    <button onclick="showSelectedNeighborhood()" title="Muestra el nodo seleccionado y sus vecinos directos.">🕸 Mostrar vecinos</button>
	  </div>

	  <div class="left-panel-section">
	    <label for="nodeTypeSelector">Tipo matemático</label>
	    <select id="nodeTypeSelector" onchange="filterByType(this.value)">
	      <option value="">Todos los tipos</option>
	    </select>
	    <button onclick="showAllNodes()" title="Restaura todos los nodos y enlaces del mapa.">🌐 Mostrar todo</button>
	  </div>

	  <div class="left-panel-section">
	    <div class="left-panel-title">Leyenda de tipos</div>
	    <div id="node-type-legend"></div>
	  </div>

	  <div class="left-panel-section">
	    <div class="left-panel-title">Ficha del nodo</div>
	    <div id="node-info">Selecciona un nodo para ver su ficha.</div>
	  </div>
	</div>

	<script>
	  initializeGraphNavigation();
	</script>

	<button
	  id="toggle-physics-overlay"
	  type="button"
  aria-controls="physics-overlay"
  aria-expanded="true"
  onclick="togglePhysicsOverlay()"
>⚙️ Ocultar controles</button>

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
    <div class="layout-title">Tamaño de texto</div>
    <div class="value-row">
      <label for="edgeLabelSize">Etiquetas de enlaces</label>
      <span id="edgeLabelSizeValue">13</span>
    </div>
    <input id="edgeLabelSize" type="range" min="8" max="100" value="13" oninput="applyTextSizes()">
    <div class="value-row">
      <label for="nodeLabelSize">Nombres de nodos</label>
      <span id="nodeLabelSizeValue">18</span>
    </div>
    <input id="nodeLabelSize" type="range" min="10" max="100" value="18" oninput="applyTextSizes()">
  </div>

  <div class="layout-section">
    <div class="layout-title">Exportar estado</div>
    <div class="layout-tip">Este botón guarda el estado actual: posiciones, nodos fijados, física y estilos.</div>
    <button onclick="downloadCurrentGraphHtml()" title="Descarga el HTML con el estado actual del grafo.">💾 Descargar grafo actual</button>
    <button onclick="copyGraphStateJson()" title="Copia el JSON actual para guardarlo en MongoDB desde Streamlit.">📋 Copiar estado JSON</button>
    <button onclick="downloadGraphStateJson()" title="Descarga solo el JSON del estado actual.">📥 Descargar estado JSON</button>
    <div id="download-status"></div>
  </div>
</div>
"""

        # Insert before closing body
        overlay = overlay.replace("__GRAPH_LAYOUTS__", layout_payload_json)
        overlay += self._restore_state_bootstrap(initial_state)
        if "</body>" in html:
            html = html.replace("</body>", overlay + "\n</body>")
        if salida:
            salida_path = validate_mutable_path(resolve_home_path(salida))
            salida_path.parent.mkdir(parents=True, exist_ok=True)
            salida_path.write_text(html, encoding="utf-8")
            if DEBUG_KNOWLEDGE_GRAPH:
                print(f"✅ Grafo exportado en: {salida_path}")
        return html

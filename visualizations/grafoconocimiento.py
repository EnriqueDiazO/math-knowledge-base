import networkx as nx
from pyvis.network import Network

class GrafoConocimiento:
    """
    Clase para construir y visualizar grafos de conocimiento
    usando los datos de MathMongo (conceptos + relaciones).
    """

    def __init__(self, conceptos: list[dict], relaciones: list[dict]) -> None:
        self.conceptos = conceptos
        self.relaciones = relaciones
        self.MaxLengthLabel=300
        self.G = nx.MultiDiGraph()

        # Colores por tipo de concepto
        self.color_por_tipo = {
            "definicion": "green",
            "teorema": "blue",
            "proposicion": "orange",
            "corolario": "violet",
            "lema": "pink",
            "ejemplo": "khaki",
            "nota": "lightgray",
            "otro": "white"
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
    def _ensure_placeholder(self, node_id: str) -> None:
        if node_id in self.G.nodes:
            return
        label = node_id
        if len(label) > self.MaxLengthLabel:
            label = label[:self.MaxLengthLabel] + "..."
        self.G.add_node(node_id, label=label, tipo="placeholder", color="#F0F0F0")

    def construir_grafo(self, tipos_relacion: list[str] = None, tipos_concepto: list[str] = None)  -> None:
        """Crea el grafo con los conceptos y relaciones."""
        usar_placeholders = not tipos_concepto  # True si None o []
        relaciones_omitidas_por_nodos_faltantes = 0
        ejemplos_omitidos = []

        self.G.clear()

        # Crear nodos
        for doc in self.conceptos:
            tipo = doc.get("tipo", "otro")
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
            label = datos.get("label", n)
            if len(label) > size:
                label = label[:size] + "..."
            net.add_node(n, label=label, title=datos.get("tipo", ""), color=datos.get("color", "white"))

        for u, v, k, d in self.G.edges(keys=True, data=True):
            net.add_edge(u, v,
                         title=d.get("tipo", ""),
                         color=d.get("color", "black")
                         )

        net.show_buttons(filter_=["physics"])  # Panel para mover nodos
        net.write_html(salida)
        print(f"✅ Grafo exportado en: {salida}")

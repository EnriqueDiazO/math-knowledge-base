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
        self.G = nx.DiGraph()

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
            "equivalente": "navy",
            "deriva_de": "purple",
            "inspirado_en": "teal",
            "requiere_concepto": "crimson",
            "contrasta_con": "orange",
            "contradice": "black",
            "contra_ejemplo": "gray"
        }

    def construir_grafo(self) -> None:
        """Crea el grafo con los conceptos y relaciones."""
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
            color = self.color_por_relacion.get(tipo_rel, "black")

            if desde in self.G.nodes and hasta in self.G.nodes:
                self.G.add_edge(desde, hasta, tipo=tipo_rel, color=color)

        print(f"🧠 Nodos creados: {len(self.G.nodes)} | Relaciones creadas: {len(self.G.edges)}")

    def exportar_html(self, salida="grafo_conceptos.html", size=30) -> None:
        """Genera un archivo HTML interactivo."""
        net = Network(height="750px", width="100%", directed=True)

        for n, datos in self.G.nodes(data=True):
            label = datos.get("label", n)
            if len(label) > size:
                label = label[:size] + "..."
            net.add_node(n, label=label, title=datos.get("tipo", ""), color=datos.get("color", "white"))

        for u, v, d in self.G.edges(data=True):
            net.add_edge(u, v, title=d.get("tipo", ""), color=d.get("color", "black"))

        net.show_buttons(filter_=["physics"])  # Panel para mover nodos
        net.write_html(salida)
        print(f"✅ Grafo exportado en: {salida}")

from pyvis.network import Network
import networkx as nx

class GrafoConocimiento:
    """
    → Clase para construir, filtrar y visualizar grafos de conocimiento
    a partir de documentos matemáticos estructurados.
    """
    def __init__(self, documentos: list[dict]) -> None:
        self.documentos_originales = documentos
        self.documentos = documentos
        self.G = nx.DiGraph()

        # Colores para tipos de objetos (nodos)
        self.color_por_tipo = {
            "definicion": "green",
            "teorema": "blue",
            "proposicion": "orange",
            "corolario": "violet",
            "lema": "pink",  # color pastel rosado más visible
            "ejemplo": "khaki",
            "esquema": "gray",
            "otro": "white"
        }

        # Colores para tipos de relaciones (aristas)
        self.color_por_enlace = {
            "enlace_salida": "navy",
            "enlace_entrada": "seagreen",
            "dependencia": "crimson",
            "relacionado_con": "darkgray"
        }

    def filtrar(self, categorias: list[str] | None = None, tipos: list[str] | None = None) -> None:
        def normalizar(texto: str | None) -> str:
            return texto.lower().strip() if isinstance(texto, str) else ""

        docs = self.documentos_originales

        if categorias:
            categorias_norm = [normalizar(c) for c in categorias]
            docs = [d for d in docs if any(normalizar(cat) in categorias_norm for cat in d.get("categoria", []))]

        if tipos:
            tipos_norm = [normalizar(t) for t in tipos]
            def tipo_match(doc):
                tipo_doc = doc.get("tipo", "otro")
                if isinstance(tipo_doc, list):
                    return any(normalizar(t) in tipos_norm for t in tipo_doc)
                return normalizar(tipo_doc) in tipos_norm

            docs = [d for d in docs if tipo_match(d)]

        self.documentos = docs
        print(f"🔍 Documentos después del filtro: {len(self.documentos)}")

    def construir_grafo(self) -> None:
        self.G.clear()

        for doc in self.documentos:
            tipo = doc["tipo"][0] if isinstance(doc["tipo"], list) else doc.get("tipo", "otro")
            self.G.add_node(doc["id"], label=doc.get("titulo", doc["id"]), tipo=tipo)

        ids_presentes = set(self.G.nodes)

        for doc in self.documentos:
            origen = doc["id"]
            for destino in doc.get("enlaces_salida", []):
                if destino in ids_presentes:
                    self.G.add_edge(origen, destino, tipo="enlace_salida")
            for entrada in doc.get("enlaces_entrada", []):
                if entrada in ids_presentes:
                    self.G.add_edge(entrada, origen, tipo="enlace_entrada")
            for dep in doc.get("dependencias", []):
                if dep in ids_presentes:
                    self.G.add_edge(origen, dep, tipo="dependencia")
            for rel in doc.get("relacionado_con", []):
                if rel in ids_presentes:
                    self.G.add_edge(origen, rel, tipo="relacionado_con")

        print(f"🧠 Nodos: {len(self.G.nodes)} | Aristas: {len(self.G.edges)}")

    def exportar_html(self, salida="grafo.html") -> None:
        net = Network(height="750px", width="100%", directed=True)

        for n in self.G.nodes():
            tipo = self.G.nodes[n].get("tipo", "otro")
            label = self.G.nodes[n].get("label", n)
            if len(label) > 30:
                label = label[:30] + "..."
            color = self.color_por_tipo.get(tipo, "white")
            net.add_node(n, label=label, title=tipo, color=color)

        for u, v, d in self.G.edges(data=True):
            tipo_enlace = d.get("tipo", "")
            color = self.color_por_enlace.get(tipo_enlace, "black")
            net.add_edge(u, v, title=tipo_enlace, color=color)

        net.write_html(salida)
        print(f"✅ Grafo exportado en: {salida}")

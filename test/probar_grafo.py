import sys, os
sys.path.append(os.path.abspath(".."))

from db.mathmongo import MathMongoDB
from visualizacion.grafoconocimiento import GrafoConocimiento  # Asumiendo que tienes esta clase en grafo_conocimiento.py

# Paso 1: Conectarse a la base de datos
db = MathMongoDB(db_name="matematica", collection_name="contenido")

# Paso 2: Obtener todos los documentos
documentos = db.mostrar_todos()

# Paso 3: Crear grafo con esos documentos
grafo = GrafoConocimiento(documentos)

# Paso 4: (Opcional) Filtrar solo ciertos tipos o categorías
# grafo.filtrar(categorias=["Espacios métricos"], tipos=["teorema", "lema", "corolario"])

# Paso 5: Construir el grafo
grafo.construir_grafo()

# Paso 6: Exportar a HTML interactivo
grafo.exportar_html("grafo_espacios_metricos.html")

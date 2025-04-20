import sys, os
sys.path.append(os.path.abspath(".."))

from db.mathmongo import MathMongoDB
from pprint import pprint

# 1. Conectarse a MongoDB
db = MathMongoDB(db_name="matematica", collection_name="contenido")

# 2. Insertar documentos desde carpeta con archivos .md/.tex/.json
db.insertar_desde_directorio("../app/data")  # ← ajusta la ruta si usas otra

# 3. Mostrar un resumen
#print("\n📂 Documentos insertados:")
#for doc in db.mostrar_todos():
#    print(f"🔹 {doc['id']} — {doc['titulo']}")

# 4. Mostrar en tabla los campos tipo texto
#print("\n📋 Vista previa de contenido textual:")
#db.mostrar_campos_texto()

# 5. Opcional: Exportar un documento a HTML
# db.exportar_documento_html("def:espacio-metrico")

# 6. Cerrar conexión
#db.cerrar_conexion()


#db.editar_documento("cor:espacio-metrico", "formato_corolario.md")

#db = MathMongoDB()

#db.exportar_a_md("cor:espacio-metrico")
try: 
    db.editar_documento("cor:espacio-metrico", "exportados/cor__espacio-metrico.md")
except:
    print("Error")

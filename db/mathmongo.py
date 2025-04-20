# mathbongodb.py
# Versión documentada: 2025-04-19

import os
import json
import subprocess
from pymongo import MongoClient
import re
import pandas as pd

class MathMongoDB:
    """
    Clase para gestionar documentos matemáticos en una base de datos MongoDB.
    Permite insertar, editar, buscar y exportar documentos con contenido matemático.
    """
    def __init__(self, db_name="matematicas", collection_name="objetos", uri="mongodb://localhost:27017/")-> None:
        """
        Inicializa la conexión con MongoDB.

        Parámetros:
        - db_name (str): Nombre de la base de datos.
        - collection_name (str): Nombre de la colección.
        - uri (str): URI de conexión.
        """
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        print(f"✅ Conectado a la base de datos '{db_name}', colección '{collection_name}'")

    def insertar_desde_directorio(self, ruta="./plantillas")-> None:
        """
        Inserta todos los archivos JSON de un directorio en la colección.

        Parámetros:
        - ruta (str): Carpeta donde se encuentran los archivos .json
        """
        count = 0
        for archivo in os.listdir(ruta):
            if archivo.endswith(".json"):
                with open(os.path.join(ruta, archivo), encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("id") and data.get("titulo"):
                        self.collection.insert_one(data)
                        count += 1
                    else:
                        print(f"⚠️ Archivo ignorado por estar vacío o incompleto: {archivo}")
        print(f"📥 Insertados {count} documentos desde '{ruta}'")

    def mostrar_todos(self) -> list:
        """
        Devuelve una lista con todos los documentos (sin campo _id).
        """
        return list(self.collection.find({}, {"_id": 0}))

    def buscar_por_id(self, doc_id)-> dict:
        """
        Busca un documento por su campo "id".

        Parámetros:
        - doc_id (str): ID del documento

        Devuelve:
        - dict: Documento encontrado o None
        """
        return self.collection.find_one({"id": doc_id}, {"_id": 0})
    
    def editar_documento(self, doc_id, nuevos_campos)-> None:
        """
        Edita un documento actualizando los campos indicados.

        Parámetros:
        - doc_id (str): ID del documento
        - nuevos_campos (dict): Campos a modificar
        """
        resultado = self.collection.update_one({"id": doc_id}, {"$set": nuevos_campos})
        if resultado.modified_count:
            print(f"✏️ Documento '{doc_id}' actualizado.")
        else:
            print(f"⚠️ No se realizaron cambios en el documento '{doc_id}' o no se encontró.")
    
    def exportar_documento_html(self, doc_id, salida="./exportados")-> None:
        doc = self.collection.find_one({"id": doc_id}, {"_id": 0})
        if not doc:
            print(f"❌ Documento con ID '{doc_id}' no encontrado.")
            return

        os.makedirs(salida, exist_ok=True)
        safe_id = doc_id.replace(":", "__").replace("/", "__")
        html_path = os.path.join(salida, f"{safe_id}.html")

        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write("""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>{titulo}</title>
  <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
  <script type="text/javascript" id="MathJax-script" async
    src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <style>
    body {{ font-family: sans-serif; margin: 40px; }}
    h1 {{ color: darkblue; }}
    .seccion {{ margin-top: 1.5em; }}
  </style>
</head>
<body>
""".format(titulo=doc.get("titulo", "Documento sin título")))

                f.write(f"<h1>{doc.get('titulo', 'Sin título')}</h1>\n")

                if "contenido_latex" in doc:
                    #f.write(f"<div class='seccion'>$$\n{doc['contenido_latex']}\n$$</div>\n")
                    #f.write(f"<div class='seccion'>\n\n$$\n{doc['contenido_latex']}\n$$\n\n</div>\n")
                    #f.write(f"<div class='seccion'><li>{doc['contenido_latex']}</li></div>\n")
                    #f.write(f"<div class='seccion'><p>\\({doc['contenido_latex']}\\)</p></div>\n")
                    #f.write(f"<div class='seccion'>\\[{doc['contenido_latex']}\\]</div>\n")
                    #f.write(f"{doc['contenido_latex']}")
                    f.write(f"<div class='seccion'><p>{doc['contenido_latex']}</p></div>\n")

                if "demostracion" in doc:
                    f.write("<div class='seccion'><h2>Demostración</h2><ul>\n")
                    for paso in doc["demostracion"].get("pasos", []):
                        desc = paso["descripcion"]
                        refs = ", ".join(paso.get("referencias", []))
                        f.write(f"<li>{desc} <em>[{refs}]</em></li>\n")
                    f.write("</ul></div>\n")

                if "categoria" in doc:
                    categorias = ", ".join(doc["categoria"])
                    f.write(f"<div class='seccion'><h2>Categorías</h2>{categorias}</div>\n")

                if "dependencias" in doc:
                    deps = ", ".join(doc["dependencias"])
                    f.write(f"<div class='seccion'><h2>Dependencias</h2>{deps}</div>\n")

                if "referencia" in doc:
                    ref = doc["referencia"]
                    autor = ref.get("autor", "")
                    anio = ref.get("año", "")
                    obra = ref.get("obra", "")
                    f.write(f"<div class='seccion'><h2>Referencia</h2>{autor}, {anio}, <em>{obra}</em></div>\n")

                if "bibtex_entry" in doc:
                    f.write("<div class='seccion'><h2>Bibliografía</h2><pre>\n")
                    f.write(doc["bibtex_entry"])
                    f.write("</pre></div>\n")

                f.write("</body>\n</html>")

            print(f"🌐 HTML generado en: {html_path}")

        except Exception as e:
            print(f"❌ Error al exportar HTML: {e}")

    def borrar_documento(self, doc_id)-> None:
        """
        → Elimina un documento por su ID.

        Parámetros:
        - doc_id (str): ID del documento a eliminar
        """
        resultado = self.collection.delete_one({"id": doc_id})
        if resultado.deleted_count:
            print(f"🗑️ Documento '{doc_id}' eliminado.")
        else:
            print(f"⚠️ Documento '{doc_id}' no encontrado.")

    def hacer_backup(self, directorio="backup")-> None:
        """
        → Realiza un respaldo completo de la base de datos usando mongodump.

        Parámetros:
        - directorio (str): Carpeta donde se guardará el backup
        """
        os.makedirs(directorio, exist_ok=True)
        comando = ["mongodump", "--db", self.db.name, "--out", directorio]
        try:
            subprocess.run(comando, check=True)
            print(f"💾 Backup creado en: {directorio}/{self.db.name}")
        except subprocess.CalledProcessError as e:
            print("❌ Error al realizar el backup:", e)
    
    

    def mostrar_campos_texto(self, limite=10) -> None:
        """
        Muestra un DataFrame con los campos tipo texto (str, list[str], dicts simples) de cada documento.

        Parámetros:
        - limite (int): Número de documentos a mostrar (default: 10)
        """
        documentos = list(self.collection.find({}, {"_id": 0}))
        registros = []

        for doc in documentos[:limite]:
            fila = {}
            for clave, valor in doc.items():
                if isinstance(valor, str):
                    fila[clave] = valor.strip()
                elif isinstance(valor, list) and all(isinstance(x, str) for x in valor):
                    fila[clave] = ", ".join(valor)
                elif isinstance(valor, dict):
                    partes = []
                    for k, v in valor.items():
                        if isinstance(v, (str, int)):
                            partes.append(f"{k}: {v}")                   
                    if partes:
                        fila[clave] = "; ".join(partes)
            
            if fila:  # asegura que tenga al menos un campo de texto
                registros.append(fila)

        df = pd.DataFrame(registros)
        if df.empty:
            print("⚠️ No hay campos de texto para mostrar.")
        else:
            print("📄 Campos tipo texto en los documentos:")
        print(df.to_string(index=False))


    
    def cerrar_conexion(self) -> None:
        """
        → Cierra la conexión con la base de datos MongoDB.
        """
        self.client.close()
        print("🔌 Conexión con MongoDB cerrada correctamente.")
    
    


def conectar_y_restaurar(db_name="matematica", collection_name="contenido", backup_dir="backup") -> MathMongoDB:
    """
    → Restaura una base de datos MongoDB desde backup y devuelve una instancia activa.

    Parámetros:
    - db_name (str): Nombre de la base de datos a restaurar
    - collection_name (str): Nombre de la colección
    - backup_dir (str): Carpeta donde se guardó el respaldo

    Retorna:
    - MathMongoDB: instancia conectada a la base restaurada o None si falla
    """
    db_backup_path = os.path.join(backup_dir, db_name)

    if not os.path.exists(db_backup_path):
        print(f"❌ No se encontró el respaldo en: {db_backup_path}")
        return None

    comando = ["mongorestore", "--drop", "--db", db_name, db_backup_path]

    try:
        subprocess.run(comando, check=True)
        print(f"✅ Base de datos '{db_name}' restaurada exitosamente desde '{backup_dir}'")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al restaurar la base de datos: {e}")
        return None

    return MathMongoDB(db_name=db_name, collection_name=collection_name)



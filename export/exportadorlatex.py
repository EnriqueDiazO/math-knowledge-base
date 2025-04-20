# exportador_latex.py
# → Clase para exportar documentos desde MongoDB a LaTeX

import os
import subprocess
from pymongo import MongoClient
from db.mathmongo import MathMongoDB

class ExportadorLatex:
    def __init__(self, mathdb: MathMongoDB) -> None:
        """
        → Inicializa la conexión a MongoDB para exportar documentos.

        Parámetros:
        - mathdb (MathMongoDB): Instancia conectada de MathMongoDB
        """
        self.mathdb = mathdb
        self.collection = mathdb.collection
        print("✅ ExportadorLatex listo usando MathMongoDB")

    def exportar_documento_latex(self, doc_id: str, salida: str = "./exportados") -> None:
        """
        → Exporta un documento de la base de datos a un archivo LaTeX compilado como PDF.

        Parámetros:
        - doc_id (str): ID del documento.
        - salida (str): Carpeta donde se guardará el .tex y el .pdf
        """
        doc = self.collection.find_one({"id": doc_id}, {"_id": 0})
        if not doc:
            print(f"❌ Documento con ID '{doc_id}' no encontrado.")
            return

        os.makedirs(salida, exist_ok=True)
        safe_id = doc_id.replace(":", "__").replace("/", "__")
        tex_path = os.path.join(salida, f"{safe_id}.tex")

        plantilla_local = os.path.join(os.path.dirname(__file__), "templates", "miestilo.sty")
        destino_local = os.path.join(salida, "miestilo.sty")
        if not os.path.exists(destino_local):
            try:
                os.makedirs(salida, exist_ok=True)
                with open(plantilla_local, "r", encoding="utf-8") as f_src:
                     with open(destino_local, "w", encoding="utf-8") as f_dst:
                         f_dst.write(f_src.read())
                print(f"📄 Plantilla miestilo.sty copiada a {salida}")
            except Exception as e:
                print(f"⚠️ No se pudo copiar miestilo.sty: {e}")

        #tex_path = os.path.join(salida, f"{doc_id}.tex")

        try:
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write("\\documentclass[12pt]{article}\n")
                f.write("\\usepackage{miestilo}\n")
                f.write("\\begin{document}\n\n")

                titulo = doc.get("titulo", "Sin título")
                f.write("\\section*{" + titulo + "}\n\n")

                contenido = doc.get("contenido_latex", "")
                f.write(contenido + "\n\n")

                #explicacion = doc.get("explicacion", "")
                #f.write(explicacion + "\n\n")

                # Campos opcionales de ejemplos
                if "caso" in doc and doc["caso"]:
                     f.write("\\section*{Caso}\n")
                     f.write(f"{doc['caso']}\n\n")

                if "explicacion" in doc and doc["explicacion"]:
                    f.write("\\section*{Explicación}\n")
                    f.write(f"{doc['explicacion']}\n\n")

                if "contexto" in doc and doc["contexto"]:
                   f.write("\\section*{Contexto}\n")
                   f.write(f"{doc['contexto']}\n\n")

                if "explicacion_latex" in doc and doc["explicacion_latex"]:
                   f.write("\\section*{Explicación (LaTeX)}\n")
                   f.write(f"\\[{doc['explicacion_latex']}\\]\n\n")


                if doc.get("demostracion", {}).get("pasos"): 
                    f.write("\n \\section*{Demostración}\n \\begin{itemize}\n")
                    for paso in doc["demostracion"].get("pasos", []):
                        desc = paso["descripcion"].replace("\n", r"\\")
                        refs = ", ".join(paso.get("referencias", []))
                        if refs:
                            f.write(f"\n  \\item {desc} \\textit{{[{refs}]}} \n")
                        else:
                            f.write(f"\n  \\item {desc} \n")
                    f.write("\\end{itemize} \n $\\blacksquare$ \n ")#\\hfill

                if "ejemplos_rapidos" in doc and doc["ejemplos_rapidos"]:  
                    f.write("\n \\section*{Ejemplos Rápidos}\n \\begin{itemize}\n")
                    for ejemplo in doc["ejemplos_rapidos"]:
                        descripcion = ejemplo.get("descripcion", "")
                        latex = ejemplo.get("latex", "")
                        f.write(f"  \\item \\textbf{{{descripcion}}}: $${latex}$$\n")
                    f.write("\\end{itemize}\n")

                if "categoria" in doc:
                    categorias = ", ".join(cat for cat in doc["categoria"])
                    f.write("\\section*{Categorías}\n")
                    f.write(f"{categorias}\n\n")

                if "dependencias" in doc:
                    deps = ", ".join(doc["dependencias"])
                    f.write("\\section*{Dependencias}\n")
                    f.write(f"{deps}\n\n")

                if "relacionado_con" in doc:
                    relacionados = ", ".join(doc["relacionado_con"])
                    f.write("\\section*{Relacionado con}\n")
                    f.write(f"{relacionados}\n\n")

                if "referencia" in doc:
                    ref = doc["referencia"]
                    autor = ref.get("autor", "")
                    anio = ref.get("año", "")
                    obra = ref.get("obra", "")
                    capitulo = ref.get("capitulo", "")
                    pagina = ref.get("página", "")
                    f.write("\\section*{Referencia}\n")
                    f.write(f"{autor}, {anio}, {obra}, Cap. {capitulo}, Pag. {pagina}\n\n")

                zettel = {
                    "enlaces_salida": doc.get("enlaces_salida", []),
                    "enlaces_entrada": doc.get("enlaces_entrada", []),
                    "inspirado_en": doc.get("inspirado_en", []),
                    "creado_a_partir_de": doc.get("creado_a_partir_de", ""),
                    "comentario_personal": doc.get("comentario_personal", ""),
                    "referencia_textual": doc.get("referencia_textual", "")
                }

                if any(zettel.values()):
                    f.write("\\section*{Notas Zettelkasten}\n\\begin{itemize}\n")
                    if zettel["enlaces_entrada"]:
                        f.write(f"\n  \\item \\textbf{{Enlaces de entrada}}: {', '.join(zettel['enlaces_entrada'])}\n")
                    if zettel["enlaces_salida"]:
                        f.write(f"\n  \\item \\textbf{{Enlaces de salida}}: {', '.join(zettel['enlaces_salida'])}\n")
                    if zettel["inspirado_en"]:
                        f.write(f"\n  \\item \\textbf{{Inspirado en}}: {', '.join(zettel['inspirado_en'])}\n")
                    if zettel["creado_a_partir_de"]:
                        f.write(f"\n  \\item \\textbf{{Creado a partir de}}: {zettel['creado_a_partir_de']}\n")
                    if zettel["comentario_personal"]:
                        f.write(f"\n  \\item \\textbf{{Comentario personal}}: {zettel['comentario_personal']}\n")
                    if zettel["referencia_textual"]:
                        f.write(f"\n  \\item \\textbf{{Referencia textual}}: {zettel['referencia_textual']}\n")
                    f.write("\\end{itemize}\n")

                f.write("\\end{document}")

        except Exception as e:
            print(f"❌ Error al escribir el archivo .tex: {e}")
            return

        try:
            subprocess.run(["pdflatex", "-interaction=nonstopmode", "-output-directory", salida, tex_path], check=True)
            print(f"📄 PDF generado en: {salida}/{doc_id}.pdf")
        except subprocess.CalledProcessError:
            print("❌ Error al compilar el archivo LaTeX.")


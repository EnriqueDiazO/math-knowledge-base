import os
import subprocess
from datetime import datetime
from pymongo import MongoClient

class ExportadorLatex:
    def __init__(self, plantilla_path: str = "../export/templates/miestilo.sty") -> None:
        self.plantilla_path = plantilla_path
        print("✅ ExportadorLatex listo para conceptos y LaTeX")

    def exportar_concepto(self, concepto: dict, contenido_latex: str, salida: str = "./exportados") -> None:
        """Genera el .tex y PDF de un concepto."""
        
        if not concepto or not contenido_latex:
            print("❌ Datos incompletos para exportar.")
            return

        doc_id = concepto.get("id", "documento_sin_id").replace(":", "__")
        tex_path = os.path.join(salida, f"{doc_id}.tex")
        os.makedirs(salida, exist_ok=True)

        destino_sty = os.path.join(salida, "miestilo.sty")
        if not os.path.exists(destino_sty) and os.path.exists(self.plantilla_path):
            with open(self.plantilla_path, encoding="utf-8") as f_src, open(destino_sty, "w", encoding="utf-8") as f_dst:
                f_dst.write(f_src.read())
            print(f"📄 Plantilla miestilo.sty copiada a {salida}")

        try:
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write("\\documentclass[12pt]{article}\n")
                f.write("\\usepackage{miestilo}\n")
                f.write("\\begin{document}\n\n")

                f.write(f"\\section*{{{concepto.get('titulo', 'Sin título')}}}\n\n")
                f.write(contenido_latex + "\n\n")

                if concepto.get("comentario"):
                    f.write(f"\\section*{{Comentario}}\n{concepto['comentario']}\n\n")

                if concepto.get("referencia"):
                    ref = concepto["referencia"]
                    f.write("\\section*{{Referencia}}\n")
                    f.write(f"{ref.get('autor', '')}, {ref.get('fuente', '')}, {ref.get('anio', '')}\n\n")

                f.write("\\end{document}\n")

            subprocess.run(["pdflatex", "-interaction=nonstopmode", "-output-directory", salida, tex_path], check=True)
            print(f"📄 PDF generado: {os.path.join(salida, doc_id)}.pdf")

        except Exception as e:
            print(f"❌ Error al generar el documento: {e}")
    
    def exportar_todos_de_source(self, db: MongoClient, source: str, salida: str = "./exportados") -> None:
        """
        Exporta todos los conceptos de un mismo source a PDF.
        :param db: Conexión a la base de datos MathMongo.
        :param source: Nombre exacto del campo source a exportar.
        :param salida: Carpeta destino para los archivos.
        """
        conceptos = list(db.concepts.find({"source": source}))
        print(f"🔎 Conceptos encontrados para source '{source}': {len(conceptos)}")

        for c in conceptos:
            latex_doc = db.latex_documents.find_one({"id": c["id"], "source": source})
            if not latex_doc:
                print(f"⚠️ LaTeX no encontrado para {c['id']}")
                continue

            contenido = latex_doc.get("contenido_latex", "")
            self.exportar_concepto(c, contenido, salida=salida)

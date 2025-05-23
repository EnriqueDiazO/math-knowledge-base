import os
import subprocess
import json

class ExportadorLatex:
    def __init__(self, plantilla_path: str = "../export/templates/miestilo.sty") -> None:
        """
        Inicializa el exportador usando una plantilla LaTeX personalizada.

        Parámetros:
        - plantilla_path (str): Ruta al archivo .sty a usar para formato.
        """
        self.plantilla_path = plantilla_path
        print("✅ ExportadorLatex listo (sin MongoDB)")

    def exportar_desde_dict(self, doc: dict, salida: str = "./exportados") -> None:
        """
        Exporta un documento (ya en dict) a LaTeX y PDF.

        Parámetros:
        - doc (dict): Documento en formato dict (con campos como 'titulo', 'contenido_latex', etc.)
        - salida (str): Carpeta de salida
        """
        if not isinstance(doc, dict):
            print("❌ Entrada no válida: se esperaba un diccionario.")
            return

        doc_id = doc.get("id", "documento_sin_id")
        safe_id = doc_id.replace(":", "__").replace("/", "__")
        tex_path = os.path.join(salida, f"{safe_id}.tex")
        os.makedirs(salida, exist_ok=True)

        # Copiar plantilla .sty si es necesario
        destino_sty = os.path.join(salida, "miestilo.sty")
        if not os.path.exists(destino_sty) and os.path.exists(self.plantilla_path):
            with open(self.plantilla_path, "r", encoding="utf-8") as f_src, \
                 open(destino_sty, "w", encoding="utf-8") as f_dst:
                f_dst.write(f_src.read())
            print(f"📄 Plantilla miestilo.sty copiada a {salida}")

        try:
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write("\\documentclass[12pt]{article}\n")
                f.write("\\usepackage{miestilo}\n")
                f.write("\\begin{document}\n\n")

                f.write(f"\\section*{{{doc.get('titulo', 'Sin título')}}}\n\n")
                f.write(doc.get("contenido_latex", "") + "\n\n")

                for campo in ["caso", "explicacion", "contexto"]:
                    if doc.get(campo):
                        f.write(f"\\section*{{{campo.capitalize()}}}\n{doc[campo]}\n\n")

                if doc.get("explicacion_latex"):
                    f.write("\\section*{Explicación (LaTeX)}\n")
                    f.write(f"\\[{doc['explicacion_latex']}\\]\n\n")

                if doc.get("demostracion", {}).get("pasos"):
                    f.write("\\section*{Demostración}\n\\begin{itemize}\n")
                    for paso in doc["demostracion"]["pasos"]:
                        desc = paso.get("descripcion", "").replace("\n", r"\\")
                        refs = ", ".join(paso.get("referencias", []))
                        if refs:
                            f.write(f"  \\item {desc} \\textit{{[{refs}]}}\n")
                        else:
                            f.write(f"  \\item {desc}\n")
                    f.write("\\end{itemize}\n$\\blacksquare$\n\n")

                if doc.get("ejemplos_rapidos"):
                    f.write("\\section*{Ejemplos Rápidos}\n\\begin{itemize}\n")
                    for ej in doc["ejemplos_rapidos"]:
                        f.write(f"  \\item \\textbf{{{ej.get('descripcion','')}}}: $${ej.get('latex','')}$$\n")
                    f.write("\\end{itemize}\n")

                if doc.get("categoria"):
                    f.write(f"\\section*{{Categorías}}\n{', '.join(doc['categoria'])}\n\n")
                if doc.get("dependencias"):
                    f.write(f"\\section*{{Dependencias}}\n{', '.join(doc['dependencias'])}\n\n")
                if doc.get("relacionado_con"):
                    f.write(f"\\section*{{Relacionado con}}\n{', '.join(doc['relacionado_con'])}\n\n")

                if doc.get("referencia"):
                    ref = doc["referencia"]
                    f.write("\\section*{Referencia}\n")
                    f.write(f"{ref.get('autor','')}, {ref.get('año','')}, {ref.get('obra','')}, Ed. {ref.get('edición','')} Cap. {ref.get('capitulo','')}, Pag. {ref.get('pagina','')} \n\n")

                zettel = {
                    "enlaces_entrada": doc.get("enlaces_entrada", []),
                    "enlaces_salida": doc.get("enlaces_salida", []),
                    "inspirado_en": doc.get("inspirado_en", []),
                    "creado_a_partir_de": doc.get("creado_a_partir_de", "")
                }
                if any(zettel.values()):
                    f.write("\\section*{Notas Zettelkasten}\n\\begin{itemize}\n")
                    for key, val in zettel.items():
                        if isinstance(val, list) and val:
                            f.write(f"  \\item \\textbf{{{key.replace('_',' ').title()}}}: {', '.join(val)}\n")
                        elif isinstance(val, str) and val.strip():
                            f.write(f"  \\item \\textbf{{{key.replace('_',' ').title()}}}: {val}\n")
                    f.write("\\end{itemize}\n")

                f.write("\\end{document}")

        except Exception as e:
            print(f"❌ Error al escribir el archivo .tex: {e}")
            return

        try:
            subprocess.run(["pdflatex", "-interaction=nonstopmode", "-output-directory", salida, tex_path], check=True)
            print(f"📄 PDF generado en: {salida}/{safe_id}.pdf")
        except subprocess.CalledProcessError:
            print("❌ Error al compilar el archivo LaTeX.")

    def exportar_desde_json(self, json_path: str, salida: str = "./exportados") -> None:
        """
        Carga un documento desde archivo JSON y lo exporta a LaTeX y PDF.

        Parámetros:
        - json_path (str): Ruta al archivo .json
        - salida (str): Carpeta de salida
        """
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
            self.exportar_desde_dict(doc, salida)
        except Exception as e:
            print(f"❌ Error al leer archivo JSON: {e}")

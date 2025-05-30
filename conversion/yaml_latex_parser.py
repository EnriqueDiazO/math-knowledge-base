# conversion/yaml_latex_parser.py
import os
import re

import yaml


class YamlLatexParser:
    @staticmethod
    def extraer_yaml_y_contenido(tex_path: str) -> dict:
        with open(tex_path, encoding="utf-8") as f:
            texto = f.read()

        yaml_match = re.search(r"---\s*(.*?)---", texto, re.DOTALL)
        if not yaml_match:
            raise ValueError("Encabezado YAML no encontrado")

        datos_yaml = yaml.safe_load(yaml_match.group(1).replace("%", "").strip())
        contenido_latex = texto[yaml_match.end():].strip()

        return {
            **datos_yaml,
            "contenido_latex": contenido_latex
        }
    @staticmethod
    def procesar_directorio(carpeta: str) -> list[dict]:
        archivos = [f for f in os.listdir(carpeta) if f.endswith((".md", ".tex"))]
        resultados = []
        for archivo in archivos:
            ruta = os.path.join(carpeta, archivo)
            try:
                resultados.append(YamlLatexParser.extraer_yaml_y_contenido(ruta))
            except Exception as e:
                print(f"❌ Error en {archivo}: {e}")
        return resultados

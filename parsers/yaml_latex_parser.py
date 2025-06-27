# conversion/yaml_latex_parser.py
import os
import re
from rapidfuzz import fuzz
import yaml

def normalize(text: str) -> str:
    return re.sub(r'[\s\.\-_]+', ' ', text.lower()).strip()

class YamlLatexParser:
    @staticmethod
    def extraer_yaml_y_contenido(tex_path: str) -> tuple[dict, str]:
        """
        Extrae metadatos (YAML) y contenido LaTeX separados.

        Retorna:
            - dict con campos YAML parseados
            - str con el contenido LaTeX
        """
        with open(tex_path, encoding="utf-8") as f:
            texto = f.read()
        
        if texto.count("---") < 2:
            raise ValueError(f"Archivo {tex_path} no tiene encabezado YAML bien formado.")

        partes = texto.split("---", 2)
        datos_yaml = yaml.safe_load(partes[1].strip())
        contenido_latex = partes[2].strip()

        return datos_yaml, contenido_latex
    
    @staticmethod
    def procesar_directorio(carpeta: str, conceptos_db: list[dict], generar_relaciones: bool = True) -> list[dict]:
        """
        Procesa todos los archivos en un directorio, devuelve lista con:
            {
                'doc': {campos del concepto},
                'contenido_latex': str,
                'relations': [ ... ]
            }
        """
        resultados = []
        archivos = [f for f in os.listdir(carpeta) if f.endswith((".md", ".tex"))]
        docs_local = []

        for archivo in archivos:
            ruta = os.path.join(carpeta, archivo)
            try:
                meta, latex = YamlLatexParser.extraer_yaml_y_contenido(ruta)
                doc = {**meta, "contenido_latex": latex}
                docs_local.append(doc)
            except Exception as e:
                print(f"❌ Error en {archivo}: {e}")

        candidatos = conceptos_db + docs_local

        for doc in docs_local:
            pendientes = []
            relations = []

            if generar_relaciones:
                for alias in doc.get("alias_previos_pendientes") or []:
                    alias_norm = normalize(alias)
                    best_score = 0
                    match = None

                    for c in candidatos:
                        for field in [c.get("titulo") or "", c.get("id", "")]:
                            score = fuzz.token_set_ratio(alias_norm, normalize(field))
                            if score > best_score:
                                best_score, match = score, c
                    
                    if best_score >= 85 and match:
                        relations.append({
                            "desde_id": doc["id"],
                            "desde_source": doc["source"],
                            "hasta_id": match["id"],
                            "hasta_source": match["source"],
                            "tipo": "requiere_concepto",
                            "descripcion": ""
                        })
                    else:
                        pendientes.append(alias)

            doc["alias_previos_pendientes"] = pendientes
            resultados.append({"doc": doc, "contenido_latex": doc["contenido_latex"], "relations": relations})

        return resultados

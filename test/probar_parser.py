import os
import sys

sys.path.append(os.path.abspath(".."))
#from export.exportadorlatex import ExportadorLatex

#def extraer_yaml_y_contenido(tex_path: str) -> dict:
#    with open(tex_path, encoding="utf-8") as f:
#        texto = f.read()

#    yaml_match = re.search(r"---\s*(.*?)---", texto, re.DOTALL)
#    if not yaml_match:
#        raise ValueError("Encabezado YAML no encontrado")

#    datos_yaml = yaml.safe_load(yaml_match.group(1).replace("%", "").strip())

#    contenido_latex = texto[yaml_match.end():].strip()

#    return {
#        **datos_yaml,
#        "contenido_latex": contenido_latex
#    }

#data = extraer_yaml_y_contenido("test.md")

#from pprint import pprint
#pprint(data)


#exportador = ExportadorLatex(plantilla_path="../export/templates/miestilo.sty")
#exportador.exportar_desde_dict(data)  # ✅ Esto es lo correcto

from pprint import pprint

from conversion.yaml_latex_parser import YamlLatexParser
from export.exportadorlatex import ExportadorLatex

# Cargar archivo con encabezado YAML + contenido LaTeX
data = YamlLatexParser.extraer_yaml_y_contenido("test.md")

# Mostrar estructura
pprint(data)

# Exportar a PDF usando LaTeX
exportador = ExportadorLatex(plantilla_path="../export/templates/miestilo.sty")
exportador.exportar_desde_dict(data)




from pathlib import Path

from pymongo import MongoClient
from slugify import slugify

# Configuración MongoDB
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "math_v0_db"
COLLECTION_NAME = "collection"

# Carpeta base del Quarto Book
CARPETA_BASE = "quarto_book"

# Conexión a la base de datos
cliente = MongoClient(MONGO_URI)
db = cliente[DB_NAME]
coleccion = db[COLLECTION_NAME]

# Función para crear .qmd
def crear_qmd(concepto):
    tipo_raw = concepto.get("tipo", "otros")
    tipo = str(tipo_raw[0] if isinstance(tipo_raw, list) else tipo_raw).lower().replace(" ", "_")
    carpeta = Path(CARPETA_BASE) / f"{tipo}s"
    carpeta.mkdir(parents=True, exist_ok=True)

    titulo = concepto.get("titulo", "sin_titulo")
    contenido_latex = concepto.get("contenido_latex", "").strip()
    referencia = concepto.get("referencia", "N/A")
    comentario = concepto.get("comentario", "")
    concepto_id = concepto.get("id", "")

    slug = slugify(f"{tipo}_{titulo}")[:60]
    archivo_qmd = carpeta / f"{slug}.qmd"

    with open(archivo_qmd, "w", encoding="utf-8") as f:
        f.write(f"# {titulo}\n\n")
        f.write(f"**ID:** `{concepto_id}`\n\n")
        f.write(f"**Tipo:** {tipo}\n\n")
        if referencia and referencia != "N/A":
            f.write(f"**Referencia:** {referencia}\n\n")
        if comentario:
            f.write(f"**Comentario:** {comentario}\n\n")

        f.write("## Contenido (renderizado)\n\n")
        f.write("$$\n" + contenido_latex + "\n$$\n\n")

        f.write("## Código fuente LaTeX\n\n")
        f.write("```latex\n" + contenido_latex + "\n```\n")

    print(f"✅ Generado: {archivo_qmd}")

# Recorrer todos los conceptos y generar archivos
for concepto in coleccion.find():
    if concepto.get("contenido_latex"):
        try:
            crear_qmd(concepto)
        except Exception as e:
            print(f"❌ Error en concepto ID: {concepto.get('id', 'sin_id')} – {e}")



class ExportadorQuarto:
    def __init__(self, base_quarto_dir: str):
        pass

    def exportar_conceptos(self, conceptos: list[ConceptoBase]) -> None:
        pass

    def actualizar_archivo_yml(self) -> None:
        pass

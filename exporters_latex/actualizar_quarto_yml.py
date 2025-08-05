
from pathlib import Path

import yaml

CARPETA_BASE = Path("quarto_book")
ARCHIVO_YML = CARPETA_BASE / "_quarto.yml"

# Título del libro
titulo = "Base de Conocimiento Matemática"

# Index
capitulos = ["index.qmd"]

# Explorar subcarpetas como 'definicions', 'teoremas', etc.
for subcarpeta in sorted(CARPETA_BASE.iterdir()):
    if subcarpeta.is_dir():
        archivos = sorted(subcarpeta.glob("*.qmd"))
        capitulos.extend([str(p.relative_to(CARPETA_BASE)) for p in archivos])

# Estructura del YAML
estructura = {
    "project": {"type": "book"},
    "book": {
        "title": titulo,
        "author": "Enrique Díaz Ocampo",
        "chapters": capitulos
    },
    "format": {
        "html": {"theme": "cosmo", "toc": True},
        "pdf": {"documentclass": "article"}
    }
}

# Guardar en _quarto.yml
with open(ARCHIVO_YML, "w", encoding="utf-8") as f:
    yaml.dump(estructura, f, sort_keys=False, allow_unicode=True)

print(f"✅ Archivo actualizado: {ARCHIVO_YML}")

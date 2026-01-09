from __future__ import annotations

import argparse
from pathlib import Path
from mathdatabase.mathmongo import MathMongo
from exporters_quarto.quarto_exporter import QuartoBookExporter

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    p.add_argument("--db", default="mathmongo")
    p.add_argument("--template", default="quarto_book")
    p.add_argument("--build", default="quarto_book_build")
    p.add_argument("--ids", nargs="+", required=True, help="IDs de conceptos a exportar")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    root = Path(__file__).resolve().parents[1]
    template_dir = (root / args.template).resolve()
    build_dir = (root / args.build).resolve()

    mm = MathMongo(mongo_uri=args.mongo_uri, db_name=args.db)

    # OJO: tu colección es mm.concepts
    concepts = list(mm.concepts.find({"id": {"$in": args.ids}}))
    if not concepts:
        raise SystemExit("No se encontraron conceptos con esos IDs.")

    exporter = QuartoBookExporter(template_dir=template_dir, build_dir=build_dir)
    exporter.prepare_build(force=args.force)
    res = exporter.export_concepts(concepts)

    # Reutiliza tu auto-TOC actual (script existente)
    from scripts.export_quarto_book import _write_book_quarto_yml
    _write_book_quarto_yml(build_dir)

    print(f"OK. Build: {res.build_dir}")
    print(f"Archivos escritos: {len(res.written_files)}")

if __name__ == "__main__":
    main()

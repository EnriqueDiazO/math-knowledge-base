"""Export the existing knowledge graph from one explicitly selected MongoDB database."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from mathmongo.config import resolve_config
from mathmongo.paths import get_exports_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


def main(argv: Sequence[str] | None = None) -> int:
    """Restore make grafo with read-only Mongo access and XDG-safe HTML output."""
    settings = resolve_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=settings.mongo_uri)
    parser.add_argument("--database", default=settings.mongo_database)
    parser.add_argument("--output", help="HTML output path; relative paths resolve against HOME")
    args = parser.parse_args(argv)
    output = (resolve_home_path(args.output) if args.output else
              get_exports_dir(configured=settings.export_directory) / "knowledge_graphs/current.html")
    output = validate_mutable_path(output)

    from pymongo import MongoClient

    from visualizations.grafoconocimiento import GrafoConocimiento

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        database = client[args.database]
        graph = GrafoConocimiento(list(database.concepts.find()), list(database.relations.find()))
        graph.construir_grafo()
        graph.exportar_html(salida=output)
    finally:
        client.close()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

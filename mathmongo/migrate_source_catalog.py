"""Importable entry point for Source Catalog planning and isolated bootstrap."""

from __future__ import annotations

from mathmongo.source_catalog_migration.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

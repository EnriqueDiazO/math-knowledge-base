"""Importable entry point for the non-writing S1C1 migration planner."""

from __future__ import annotations

from mathmongo.source_catalog_migration.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

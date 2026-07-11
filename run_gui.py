#!/usr/bin/env python3
"""Backward-compatible wrapper for the installable MathMongo CLI."""

from mathmongo.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

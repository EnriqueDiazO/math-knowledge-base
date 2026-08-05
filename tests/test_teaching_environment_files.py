"""Keep the documented teaching runtime and constraints aligned."""

from __future__ import annotations

from pathlib import Path

# ruff: noqa: D103


ROOT = Path(__file__).resolve().parents[1]


def test_teaching_constraints_pin_the_verified_runtime() -> None:
    constraints = (ROOT / "constraints/teaching-2026.txt").read_text(encoding="utf-8")
    assert "streamlit==1.59.2" in constraints
    assert "pymongo==4.17.0" in constraints
    assert "pydantic==2.13.4" in constraints
    assert "Pillow==12.3.0" in constraints


def test_pyproject_declares_production_imports_directly() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'pandas = ">=2.3,<2.4"' in pyproject
    assert 'pillow = ">=12.3,<13"' in pyproject
    assert 'streamlit = { version = ">=1.59,<1.60", extras = ["pdf"] }' in pyproject

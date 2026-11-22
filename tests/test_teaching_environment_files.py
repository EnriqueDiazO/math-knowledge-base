"""Keep the documented teaching runtime and constraints aligned."""

from __future__ import annotations

from pathlib import Path

# ruff: noqa: D103


ROOT = Path(__file__).resolve().parents[1]


def test_teaching_constraints_pin_the_verified_runtime() -> None:
    constraints = (ROOT / "constraints/teaching-2026.txt").read_text(encoding="utf-8")
    assert "streamlit==1.67.0" in constraints
    assert "pymongo==4.18.3" in constraints
    assert "pydantic==2.13.4" in constraints
    assert "Pillow==13.0.0" in constraints


def test_pyproject_declares_production_imports_directly() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'pandas = ">=2.3,<2.4"' in pyproject
    assert 'pillow = ">=13.0,<14"' in pyproject
    assert 'streamlit = { version = ">=1.67,<1.68", extras = ["pdf"] }' in pyproject

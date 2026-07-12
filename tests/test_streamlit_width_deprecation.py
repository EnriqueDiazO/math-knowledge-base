"""Static guard against deprecated Streamlit width arguments."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = (
    "app",
    "editor",
    "exporters_latex",
    "exporters_quarto",
    "mathdatabase",
    "mathmongo",
    "parsers",
    "schemas",
    "scripts",
    "visualizations",
)
TOP_LEVEL_MODULES = (
    "interface.py",
    "mathkb_config.py",
    "run_gui.py",
)
DEPRECATED_ARGUMENT = "use_container_width"


def _production_python_files() -> list[Path]:
    files = [ROOT / filename for filename in TOP_LEVEL_MODULES]
    for directory in PRODUCTION_ROOTS:
        files.extend((ROOT / directory).rglob("*.py"))
    return sorted(path for path in files if path.is_file())


def test_executable_streamlit_code_uses_width_argument() -> None:
    """Reject deprecated width keywords in production call syntax."""
    violations: list[str] = []

    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == DEPRECATED_ARGUMENT:
                    relative_path = path.relative_to(ROOT)
                    violations.append(f"{relative_path}:{keyword.value.lineno}")

    assert not violations, (
        f"Replace deprecated Streamlit {DEPRECATED_ARGUMENT} calls with width: "
        + ", ".join(violations)
    )

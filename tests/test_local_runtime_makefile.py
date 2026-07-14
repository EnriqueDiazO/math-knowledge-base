"""Static regression tests for the unified local-runtime Make targets."""

# ruff: noqa: D103

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"


def _target_recipe(source: str, target: str) -> str:
    match = re.search(
        rf"(?m)^{re.escape(target)}\s*:[^\n]*\n(?P<recipe>(?:\t[^\n]*(?:\n|$))+)",
        source,
    )
    assert match is not None, f"No se encontró el target {target!r}"
    return match.group("recipe")


def test_make_defaults_and_unified_run_cli_contract() -> None:
    source = MAKEFILE.read_text(encoding="utf-8")
    recipe = _target_recipe(source, "run")

    assert re.search(r"(?m)^DATABASE\s*\?=\s*MathV0\s*$", source)
    assert "mathdbmongo/bin/python -m mathmongo.local_runtime" in recipe
    for option in (
        '--database "$(DATABASE)"',
        '--streamlit-host "$(STREAMLIT_HOST)"',
        '--streamlit-port "$(STREAMLIT_PORT)"',
        '--advanced-reader-host "$(ADVANCED_READER_HOST)"',
        '--advanced-reader-port "$(ADVANCED_READER_PORT)"',
        '--log-level "$(LOG_LEVEL)"',
    ):
        assert option in recipe


def test_separate_targets_keep_database_and_reader_url_explicit() -> None:
    source = MAKEFILE.read_text(encoding="utf-8")
    reader_recipe = _target_recipe(source, "advanced-reader")
    streamlit_recipe = _target_recipe(source, "run-streamlit")

    assert '--database "$(DATABASE)"' in reader_recipe
    assert 'MONGODB_DB="$(DATABASE)"' in streamlit_recipe
    assert "MATHMONGO_ADVANCED_READER_URL=" in streamlit_recipe


def test_runtime_never_uses_machine_wide_process_killers() -> None:
    runtime_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "mathmongo" / "local_runtime").glob("*.py"))
    )
    make_source = MAKEFILE.read_text(encoding="utf-8")
    supervised_recipes = "\n".join(
        _target_recipe(make_source, target)
        for target in ("run", "run-streamlit", "advanced-reader")
    )

    forbidden = re.compile(r"\b(?:pkill|killall)\b")
    assert forbidden.search(runtime_source) is None
    assert forbidden.search(supervised_recipes) is None


def test_run_streamlit_brackets_ipv6_reader_url() -> None:
    result = subprocess.run(
        ["make", "-n", "run-streamlit", "ADVANCED_READER_HOST=::1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert 'MATHMONGO_ADVANCED_READER_URL="http://[::1]:8766"' in result.stdout
    assert "http://::1:8766" not in result.stdout

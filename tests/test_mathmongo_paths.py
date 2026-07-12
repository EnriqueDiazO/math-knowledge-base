"""Tests for side-effect-free XDG path resolution."""

# ruff: noqa: D103

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mathmongo.paths import ensure_user_directories
from mathmongo.paths import get_cache_dir
from mathmongo.paths import get_config_dir
from mathmongo.paths import get_cornell_runtime_dir
from mathmongo.paths import get_cpi_runtime_dir
from mathmongo.paths import get_data_dir
from mathmongo.paths import get_exports_dir
from mathmongo.paths import get_logs_dir
from mathmongo.paths import get_media_dir
from mathmongo.paths import get_runtime_dir
from mathmongo.paths import get_state_dir
from mathmongo.paths import get_templates_dir
from mathmongo.paths import resolve_home_path
from mathmongo.paths import validate_mutable_path


def env(tmp_path: Path) -> dict[str, str]:
    return {
        "HOME": str(tmp_path / "Casa con espacios á"),
        "XDG_CONFIG_HOME": str(tmp_path / "configuración"),
        "XDG_DATA_HOME": str(tmp_path / "datos"),
        "XDG_CACHE_HOME": str(tmp_path / "caché"),
        "XDG_STATE_HOME": str(tmp_path / "estado"),
        "PATH": "",
    }


def test_custom_xdg_roots_and_unicode_home(tmp_path: Path) -> None:
    environment = env(tmp_path)
    assert get_config_dir(environment) == tmp_path / "configuración/mathmongo"
    assert get_data_dir(environment) == tmp_path / "datos/mathmongo"
    assert get_cache_dir(environment) == tmp_path / "caché/mathmongo"
    assert get_state_dir(environment) == tmp_path / "estado/mathmongo"
    assert get_logs_dir(environment) == tmp_path / "estado/mathmongo/logs"
    assert get_media_dir(environment) == tmp_path / "datos/mathmongo/media"


def test_valid_xdg_runtime_and_safe_fallback(tmp_path: Path) -> None:
    environment = env(tmp_path)
    runtime = tmp_path / "user-runtime"
    runtime.mkdir()
    environment["XDG_RUNTIME_DIR"] = str(runtime)
    assert get_runtime_dir(environment) == runtime / "mathmongo"
    assert get_cornell_runtime_dir(environment) == runtime / "mathmongo/cornell"
    assert get_cpi_runtime_dir(environment) == runtime / "mathmongo/cpi"

    environment["XDG_RUNTIME_DIR"] = str(tmp_path / "missing")
    assert get_runtime_dir(environment) == tmp_path / "caché/mathmongo/runtime"


def test_relative_xdg_values_never_depend_on_cwd(tmp_path: Path) -> None:
    environment = env(tmp_path)
    environment["XDG_DATA_HOME"] = "relative-data"
    assert get_data_dir(environment) == Path(environment["HOME"]) / ".local/share/mathmongo"
    assert get_exports_dir(environment, "relative-export") == Path(environment["HOME"]) / "relative-export"


def test_home_expansion_uses_injected_environment_not_process_home(tmp_path: Path) -> None:
    environment = env(tmp_path)
    assert resolve_home_path("~/Exports", environment) == Path(environment["HOME"]) / "Exports"
    environment["MATHMONGO_LEGACY_ROOT"] = "legacy checkout"
    from mathmongo.paths import get_legacy_project_root

    assert get_legacy_project_root(environment) == Path(environment["HOME"]) / "legacy checkout"


def test_import_and_resolution_do_not_create_directories(tmp_path: Path) -> None:
    environment = env(tmp_path)
    code = (
        "import sys, types; sys.modules['streamlit']=types.ModuleType('streamlit'); "
        "import mathmongo.paths, mathmongo.config, mathkb_config, editor.pdf_export; "
        "print('imported')"
    )
    process_env = os.environ.copy()
    process_env.update(environment)
    project_python = Path(__file__).resolve().parents[1] / "mathdbmongo/bin/python"
    executable = str(project_python) if project_python.exists() else sys.executable
    result = subprocess.run(
        [executable, "-c", code], env=process_env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert not Path(environment["XDG_CONFIG_HOME"]).exists()
    assert not Path(environment["XDG_DATA_HOME"]).exists()
    assert not Path(environment["XDG_CACHE_HOME"]).exists()
    assert not Path(environment["XDG_STATE_HOME"]).exists()


def test_explicit_directory_creation_and_permissions(tmp_path: Path) -> None:
    environment = env(tmp_path)
    created = ensure_user_directories(environment)
    for directory in created.values():
        assert directory.is_dir()
        assert directory.stat().st_mode & 0o777 == 0o700


def test_resources_remain_in_read_only_package_tree() -> None:
    templates = get_templates_dir()
    assert (templates / "notes.cls").is_file()
    assert "templates_latex" in templates.parts


def test_mutable_path_rejects_symlink_leaf_and_ancestors(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    direct = tmp_path / "direct"
    direct.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Symbolic links"):
        validate_mutable_path(direct / "file.txt", allowed_root=tmp_path)

    ancestor = tmp_path / "ancestor"
    ancestor.symlink_to(outside, target_is_directory=True)
    allowed = ancestor / "not-created-yet"
    with pytest.raises(ValueError, match="Symbolic links"):
        validate_mutable_path(allowed / "file.txt", allowed_root=allowed)


def test_cleanup_never_resolves_a_symlink_candidate_to_its_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from editor.utils import cleanup_exports

    root = tmp_path / "exports"
    root.mkdir()
    target = root / "actual.log"
    target.write_bytes(b"keep")
    link = root / "link.log"
    link.symlink_to(target.name)
    monkeypatch.setattr(cleanup_exports, "ALLOWED_CLEANUP_DIRS", (root,))
    monkeypatch.setattr(cleanup_exports, "CLEANUP_LOG_FILE", tmp_path / "state/cleanup.log")

    result = cleanup_exports.delete_files_safely([link])

    assert result["deleted_files"] == 0
    assert result["errors"]
    assert link.is_symlink()
    assert target.read_bytes() == b"keep"


def test_cleanup_stats_do_not_scan_a_symlinked_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from editor.utils import cleanup_exports

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("private", encoding="utf-8")
    root = tmp_path / "exports"
    root.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(cleanup_exports, "ALLOWED_CLEANUP_DIRS", (root,))

    stats = cleanup_exports.get_directory_stats(root)

    assert stats["allowed"] is False
    assert stats["files"] == 0
    assert stats["preview"] == []


def test_cornell_and_cpi_previews_use_central_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    cornell = (root / "editor/cornell/streamlit_page.py").read_text(encoding="utf-8")
    cpi = (root / "editor/cpi/streamlit_page.py").read_text(encoding="utf-8")
    assert 'RUNTIME_DIR / "cornell_preview"' in cornell
    assert 'RUNTIME_DIR / "cpi_preview"' in cpi
    assert 'PROJECT_ROOT / "runtime"' not in cornell
    assert 'PROJECT_ROOT / "runtime"' not in cpi

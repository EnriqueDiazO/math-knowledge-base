"""Tests for safe per-user MathMongo desktop integration."""

# ruff: noqa: D103

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from mathmongo.desktop import DESKTOP_FILENAME
from mathmongo.desktop import DesktopInstallError
from mathmongo.desktop import desktop_directory
from mathmongo.desktop import desktop_file_content
from mathmongo.desktop import install_desktop_launcher
from mathmongo.desktop import resolve_executable
from mathmongo.desktop import source_icon_path
from mathmongo.desktop import uninstall_desktop_launcher
from mathmongo.desktop import xdg_paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "make_desktop_shortcut.sh"


def executable_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n[ \"$1\" = --help ]\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def environment(tmp_path: Path, *, path: str = "") -> dict[str, str]:
    return {
        "HOME": str(tmp_path / "home-usuario-á"),
        "XDG_DATA_HOME": str(tmp_path / "datos con espacios"),
        "XDG_STATE_HOME": str(tmp_path / "estado"),
        "PATH": path,
    }


def test_existing_script_is_refactored_as_compatible_wrapper() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert SCRIPT.is_file()
    assert "mathmongo-desktop" in source
    assert "python3 -m mathmongo.desktop" in source
    assert "streamlit run" not in source
    assert "make start" not in source


def test_install_uses_xdg_and_writes_valid_application_files(tmp_path: Path) -> None:
    env = environment(tmp_path)
    executable = executable_file(tmp_path / "entorno con espacios" / "bin" / "mathmongo")

    installed = install_desktop_launcher(
        executable=str(executable), environment=env, copy_to_desktop=False
    )

    desktop_file, icon, png_icon = installed
    content = desktop_file.read_text(encoding="utf-8")
    assert desktop_file == Path(env["XDG_DATA_HOME"]) / "applications" / DESKTOP_FILENAME
    assert icon == Path(env["XDG_DATA_HOME"]) / "icons/hicolor/scalable/apps/mathmongo.svg"
    assert icon.read_bytes() == source_icon_path().read_bytes()
    assert png_icon == Path(env["XDG_DATA_HOME"]) / "icons/hicolor/256x256/apps/mathmongo.png"
    assert png_icon.is_file()
    assert "Name=MathMongo\n" in content
    assert "GenericName=Math Knowledge Base\n" in content
    assert "Icon=mathmongo\n" in content
    assert "Terminal=false\n" in content
    assert f'Exec="{executable.resolve()}" run --desktop-launch' in content
    assert "TryExec=" not in content
    exec_line = next(line for line in content.splitlines() if line.startswith("Exec="))
    assert "streamlit" not in exec_line.lower()
    assert "source " not in content


def test_explicit_executable_precedes_environment_and_path(tmp_path: Path) -> None:
    explicit = executable_file(tmp_path / "explicit" / "mathmongo")
    other = executable_file(tmp_path / "other" / "mathmongo")
    env = environment(tmp_path)
    env["MATHMONGO_EXECUTABLE"] = str(other)

    assert resolve_executable(str(explicit), env) == explicit.resolve()


def test_environment_executable_precedes_command_path(tmp_path: Path) -> None:
    selected = executable_file(tmp_path / "selected" / "mathmongo")
    executable_file(tmp_path / "bin" / "mathmongo")
    env = environment(tmp_path, path=str(tmp_path / "bin"))
    env["MATHMONGO_EXECUTABLE"] = str(selected)
    assert resolve_executable(None, env) == selected.resolve()


def test_command_v_detection(tmp_path: Path) -> None:
    executable = executable_file(tmp_path / "bin" / "mathmongo")
    env = environment(tmp_path, path=str(executable.parent))
    assert resolve_executable(None, env) == executable.resolve()


def test_rejects_missing_and_non_executable_files(tmp_path: Path) -> None:
    env = environment(tmp_path)
    with pytest.raises(DesktopInstallError, match="no existe"):
        resolve_executable(str(tmp_path / "missing"), env)
    plain = tmp_path / "plain"
    plain.write_text("not executable")
    with pytest.raises(DesktopInstallError, match="no es ejecutable"):
        resolve_executable(str(plain), env)


def test_desktop_copy_uses_xdg_user_dir(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    xdg = fake_bin / "xdg-user-dir"
    desktop = tmp_path / "Escritorio personalizado"
    xdg.write_text(f"#!/bin/sh\nprintf '%s\\n' '{desktop}'\n")
    xdg.chmod(0o755)
    env = environment(tmp_path, path=str(fake_bin))
    executable = executable_file(tmp_path / "venv" / "mathmongo")

    install_desktop_launcher(executable=str(executable), environment=env, copy_to_desktop=True)

    copy = desktop / DESKTOP_FILENAME
    assert copy.is_file()
    assert os.access(copy, os.X_OK)


def test_desktop_directory_falls_back_without_xdg_user_dir(tmp_path: Path) -> None:
    env = environment(tmp_path)
    assert desktop_directory(env) == Path(env["HOME"]) / "Desktop"


def test_relative_xdg_data_home_falls_back_without_using_cwd(tmp_path: Path) -> None:
    env = environment(tmp_path)
    env["XDG_DATA_HOME"] = "relative-data"
    paths = xdg_paths(env)
    assert paths["data_home"] == Path(env["HOME"]) / ".local/share"


def test_install_and_uninstall_are_idempotent_and_preserve_other_data(tmp_path: Path) -> None:
    env = environment(tmp_path)
    executable = executable_file(tmp_path / "bin" / "mathmongo")
    unrelated = Path(env["XDG_DATA_HOME"]) / "mathmongo-user-data.db"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep")

    for _ in range(2):
        install_desktop_launcher(executable=str(executable), environment=env)
    for _ in range(2):
        uninstall_desktop_launcher(environment=env)

    assert unrelated.read_text() == "keep"


def test_dry_run_writes_and_removes_nothing(tmp_path: Path) -> None:
    env = environment(tmp_path)
    executable = executable_file(tmp_path / "bin" / "mathmongo")

    targets = install_desktop_launcher(
        executable=str(executable), environment=env, copy_to_desktop=True, dry_run=True
    )
    uninstall_desktop_launcher(environment=env, dry_run=True)

    assert not any(target.exists() for target in targets)
    assert not Path(env["XDG_DATA_HOME"]).exists()


def test_desktop_file_has_required_stable_fields(tmp_path: Path) -> None:
    executable = tmp_path / "ruta con espacios" / "mathmongo"
    content = desktop_file_content(executable.resolve())
    assert content.startswith("[Desktop Entry]\nType=Application\n")
    assert "StartupNotify=true\n" in content
    assert "Categories=Education;Science;Office;\n" in content
    assert "Keywords=mathematics;knowledge;MongoDB;LaTeX;Streamlit;\n" in content
    assert "bash -c" not in content


def test_implementation_has_no_machine_paths_or_shell_true() -> None:
    sources = [
        SCRIPT.read_text(encoding="utf-8"),
        (PROJECT_ROOT / "mathmongo" / "desktop.py").read_text(encoding="utf-8"),
    ]
    combined = "\n".join(sources)
    assert "/home/enriquedo" not in combined
    assert "/home/enrique" not in combined
    assert "shell=True" not in combined


def test_icon_is_original_svg_without_external_resources() -> None:
    content = source_icon_path().read_text(encoding="utf-8")
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in content
    assert "href=" not in content
    assert "<text" not in content

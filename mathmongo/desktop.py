"""Install and remove the per-user Linux desktop launcher for MathMongo."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path

DESKTOP_FILENAME = "mathmongo.desktop"
ICON_FILENAME = "mathmongo.svg"
PNG_ICON_FILENAME = "mathmongo-256.png"


class DesktopInstallError(RuntimeError):
    """A safe, user-facing desktop integration error."""


def source_icon_path() -> Path:
    """Return the SVG shipped in both the checkout and installed wheel."""
    path = Path(__file__).resolve().parents[1] / "assets" / "icons" / ICON_FILENAME
    if not path.is_file():
        raise DesktopInstallError(f"No se encontró el icono empaquetado: {path}")
    return path


def source_png_icon_path() -> Path:
    """Return the optional 256px icon generated from the SVG master."""
    path = Path(__file__).resolve().parents[1] / "assets" / "icons" / PNG_ICON_FILENAME
    if not path.is_file():
        raise DesktopInstallError(f"No se encontró el icono PNG empaquetado: {path}")
    return path


def xdg_paths(environment: Mapping[str, str]) -> dict[str, Path]:
    """Resolve per-user XDG destinations without creating them."""
    home_value = environment.get("HOME")
    if not home_value:
        raise DesktopInstallError("HOME no está definido.")
    home = Path(home_value)
    if not home.is_absolute():
        raise DesktopInstallError("HOME debe ser una ruta absoluta.")
    configured_data_home = Path(environment.get("XDG_DATA_HOME") or "")
    data_home = (
        configured_data_home
        if configured_data_home.is_absolute()
        else home / ".local" / "share"
    )
    return {
        "data_home": data_home,
        "applications": data_home / "applications",
        "desktop_file": data_home / "applications" / DESKTOP_FILENAME,
        "icon_dir": data_home / "icons" / "hicolor" / "scalable" / "apps",
        "icon": data_home / "icons" / "hicolor" / "scalable" / "apps" / ICON_FILENAME,
        "png_icon_dir": data_home / "icons" / "hicolor" / "256x256" / "apps",
        "png_icon": data_home / "icons" / "hicolor" / "256x256" / "apps" / "mathmongo.png",
        "home": home,
    }


def desktop_directory(environment: Mapping[str, str]) -> Path:
    """Use xdg-user-dir when useful, otherwise fall back safely to HOME/Desktop."""
    paths = xdg_paths(environment)
    command = shutil.which("xdg-user-dir", path=environment.get("PATH"))
    if command:
        result = subprocess.run(
            [command, "DESKTOP"], capture_output=True, text=True, check=False, env=dict(environment)
        )
        candidate = result.stdout.strip()
        if result.returncode == 0 and candidate and Path(candidate).is_absolute():
            return Path(candidate)
    return paths["home"] / "Desktop"


def resolve_executable(
    explicit: str | None,
    environment: Mapping[str, str],
    *,
    validate_help: bool = True,
) -> Path:
    """Resolve and validate the installed MathMongo console executable."""
    candidate = explicit or environment.get("MATHMONGO_EXECUTABLE")
    if candidate is None:
        candidate = shutil.which("mathmongo", path=environment.get("PATH"))
    if not candidate:
        raise DesktopInstallError(
            "No se encontró el ejecutable mathmongo. Usa --executable o MATHMONGO_EXECUTABLE."
        )
    path = Path(candidate)
    if not path.is_absolute():
        raise DesktopInstallError(f"El ejecutable debe usar una ruta absoluta: {path}")
    path = path.resolve()
    if not path.is_file():
        raise DesktopInstallError(f"El ejecutable no existe o no es un archivo: {path}")
    if not os.access(path, os.X_OK):
        raise DesktopInstallError(f"El archivo no es ejecutable: {path}")
    if validate_help:
        result = subprocess.run([str(path), "--help"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise DesktopInstallError("El ejecutable mathmongo no respondió correctamente a --help.")
    return path


def quote_exec_path(path: Path) -> str:
    """Quote one absolute executable path according to desktop Exec field rules."""
    value = str(path)
    escaped = "".join(f"\\{character}" if character in '\\`$"' else character for character in value)
    return f'"{escaped}"'


def desktop_file_content(executable: Path) -> str:
    """Build the stable desktop entry without invoking a shell."""
    quoted = quote_exec_path(executable)
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=MathMongo",
            "GenericName=Math Knowledge Base",
            "Comment=Mathematical knowledge base with MongoDB, LaTeX and Streamlit",
            f"Exec={quoted} run --desktop-launch",
            "Icon=mathmongo",
            "Terminal=false",
            "StartupNotify=true",
            "Categories=Education;Science;Office;",
            "Keywords=mathematics;knowledge;MongoDB;LaTeX;Streamlit;",
            "",
        ]
    )


def _optional_command(arguments: list[str], environment: Mapping[str, str]) -> None:
    executable = shutil.which(arguments[0], path=environment.get("PATH"))
    if executable:
        subprocess.run([executable, *arguments[1:]], check=False, env=dict(environment))


def install_desktop_launcher(
    *,
    executable: str | None = None,
    copy_to_desktop: bool = False,
    dry_run: bool = False,
    environment: Mapping[str, str] | None = None,
) -> list[Path]:
    """Install the icon and desktop entry idempotently for the current user."""
    env = dict(os.environ if environment is None else environment)
    paths = xdg_paths(env)
    desktop = desktop_directory(env)
    command = resolve_executable(executable, env)
    content = desktop_file_content(command)
    targets = [paths["desktop_file"], paths["icon"], paths["png_icon"]]
    if copy_to_desktop:
        targets.append(desktop / DESKTOP_FILENAME)

    print(f"Ejecutable: {command}")
    print(f"Applications: {paths['applications']}")
    print(f"Icono: {paths['icon']}")
    print(f"Icono PNG: {paths['png_icon']}")
    print(f"Lanzador: {paths['desktop_file']}")
    print(f"Escritorio: {desktop}")
    print(f"Exec={quote_exec_path(command)} run --desktop-launch")
    if dry_run:
        print("Dry-run: no se escribieron archivos.")
        return targets

    paths["applications"].mkdir(parents=True, exist_ok=True)
    paths["icon_dir"].mkdir(parents=True, exist_ok=True)
    paths["png_icon_dir"].mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_icon_path(), paths["icon"])
    shutil.copyfile(source_png_icon_path(), paths["png_icon"])
    paths["desktop_file"].write_text(content, encoding="utf-8")
    paths["desktop_file"].chmod(0o644)

    validator = shutil.which("desktop-file-validate", path=env.get("PATH"))
    if validator:
        result = subprocess.run([validator, str(paths["desktop_file"])], check=False)
        if result.returncode != 0:
            raise DesktopInstallError("desktop-file-validate rechazó el lanzador generado.")

    if copy_to_desktop:
        desktop.mkdir(parents=True, exist_ok=True)
        desktop_copy = desktop / DESKTOP_FILENAME
        shutil.copyfile(paths["desktop_file"], desktop_copy)
        desktop_copy.chmod(0o755)
        gio = shutil.which("gio", path=env.get("PATH"))
        if gio:
            subprocess.run(
                [gio, "set", str(desktop_copy), "metadata::trusted", "true"],
                check=False,
                env=env,
            )

    _optional_command(["update-desktop-database", str(paths["applications"])], env)
    _optional_command(
        ["gtk-update-icon-cache", "-f", "-t", str(paths["data_home"] / "icons" / "hicolor")],
        env,
    )
    return targets


def uninstall_desktop_launcher(
    *,
    remove_desktop_copy: bool = True,
    dry_run: bool = False,
    environment: Mapping[str, str] | None = None,
) -> list[Path]:
    """Remove only files owned by this desktop integration, idempotently."""
    env = dict(os.environ if environment is None else environment)
    paths = xdg_paths(env)
    desktop_copy = desktop_directory(env) / DESKTOP_FILENAME
    targets = [paths["desktop_file"], paths["icon"], paths["png_icon"]]
    if remove_desktop_copy:
        targets.append(desktop_copy)
    for target in targets:
        print(f"Eliminar: {target}")
        if not dry_run:
            target.unlink(missing_ok=True)
    if dry_run:
        print("Dry-run: no se eliminaron archivos.")
    else:
        _optional_command(["update-desktop-database", str(paths["applications"])], env)
    return targets


def build_parser() -> argparse.ArgumentParser:
    """Build the backwards-compatible desktop integration parser."""
    parser = argparse.ArgumentParser(description="Instala el acceso directo de MathMongo.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--install", action="store_true", help="Instalar el acceso directo.")
    action.add_argument("--uninstall", action="store_true", help="Retirar sólo el acceso directo.")
    desktop = parser.add_mutually_exclusive_group()
    desktop.add_argument("--desktop", action="store_true", help="Copiar también al escritorio.")
    desktop.add_argument("--no-desktop", action="store_true", help="No copiar al escritorio.")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar acciones sin escribir.")
    parser.add_argument("--executable", help="Ruta absoluta al comando mathmongo instalado.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run installation or removal and return a shell-friendly status."""
    args = build_parser().parse_args(argv)
    try:
        if args.uninstall:
            uninstall_desktop_launcher(
                remove_desktop_copy=not args.no_desktop,
                dry_run=args.dry_run,
            )
        else:
            # Historical no-argument use created a desktop copy; preserve that behavior.
            install_desktop_launcher(
                executable=args.executable,
                copy_to_desktop=args.desktop or not args.no_desktop,
                dry_run=args.dry_run,
            )
    except DesktopInstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

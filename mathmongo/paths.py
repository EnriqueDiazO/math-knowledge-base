"""Central, side-effect-free filesystem policy for MathMongo on Linux."""

# ruff: noqa: D103

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

APP_NAME = "mathmongo"


def _environment(environment: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environment is None else environment


def get_home_dir(environment: Mapping[str, str] | None = None) -> Path:
    """Return HOME without creating or resolving any user directory."""
    env = _environment(environment)
    value = env.get("HOME")
    if not value:
        raise RuntimeError("HOME is required to resolve MathMongo user paths")
    home = Path(value)
    if not home.is_absolute():
        raise RuntimeError("HOME must be an absolute path")
    return home


def resolve_home_path(
    path: str | Path,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Resolve a user path against the supplied HOME, never the process cwd."""
    home = get_home_dir(environment)
    text = str(path)
    if text == "~":
        return home
    if text.startswith("~/"):
        return home / text[2:]
    candidate = Path(text)
    return candidate if candidate.is_absolute() else home / candidate


def _xdg_dir(name: str, fallback: Path, environment: Mapping[str, str] | None) -> Path:
    value = _environment(environment).get(name)
    candidate = Path(value) if value else fallback
    return candidate if candidate.is_absolute() else fallback


def get_config_dir(environment: Mapping[str, str] | None = None) -> Path:
    home = get_home_dir(environment)
    return _xdg_dir("XDG_CONFIG_HOME", home / ".config", environment) / APP_NAME


def get_data_dir(environment: Mapping[str, str] | None = None) -> Path:
    home = get_home_dir(environment)
    return _xdg_dir("XDG_DATA_HOME", home / ".local" / "share", environment) / APP_NAME


def get_cache_dir(environment: Mapping[str, str] | None = None) -> Path:
    home = get_home_dir(environment)
    return _xdg_dir("XDG_CACHE_HOME", home / ".cache", environment) / APP_NAME


def get_state_dir(environment: Mapping[str, str] | None = None) -> Path:
    home = get_home_dir(environment)
    return _xdg_dir("XDG_STATE_HOME", home / ".local" / "state", environment) / APP_NAME


def get_runtime_dir(environment: Mapping[str, str] | None = None) -> Path:
    """Prefer a valid user-owned XDG runtime directory, otherwise use cache."""
    env = _environment(environment)
    candidate_value = env.get("XDG_RUNTIME_DIR")
    if candidate_value:
        candidate = Path(candidate_value)
        try:
            if (
                candidate.is_absolute()
                and
                candidate.is_dir()
                and candidate.stat().st_uid == os.getuid()
                and os.access(candidate, os.W_OK | os.X_OK)
            ):
                return candidate / APP_NAME
        except OSError:
            pass
    return get_cache_dir(environment) / "runtime"


def get_logs_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_state_dir(environment) / "logs"


def get_media_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_data_dir(environment) / "media"


def get_source_documents_dir(environment: Mapping[str, str] | None = None) -> Path:
    """Return the persistent XDG data root for Source-associated documents."""
    return get_data_dir(environment) / "source_documents"


def get_source_document_blobs_dir(environment: Mapping[str, str] | None = None) -> Path:
    """Return the content-addressed PDF blob root without creating it."""
    return get_source_documents_dir(environment) / "blobs" / "sha256"


def get_projects_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_data_dir(environment) / "projects"


def get_backups_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_data_dir(environment) / "backups"


def get_graph_data_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_data_dir(environment) / "graphs"


def get_cornell_runtime_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_runtime_dir(environment) / "cornell"


def get_cpi_runtime_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_runtime_dir(environment) / "cpi"


def get_pdf_preview_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_runtime_dir(environment) / "pdf_preview"


def get_latex_runtime_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_runtime_dir(environment) / "latex"


def get_graph_runtime_dir(environment: Mapping[str, str] | None = None) -> Path:
    return get_runtime_dir(environment) / "knowledge_graphs"


def get_resource_root() -> Path:
    """Return the installed read-only resource root."""
    return Path(__file__).resolve().parents[1]


def get_templates_dir() -> Path:
    return get_resource_root() / "templates_latex"


def get_assets_dir() -> Path:
    return get_resource_root() / "assets"


def find_symlink_component(path: str | Path) -> Path | None:
    """Return the first symbolic-link component in an absolute lexical path."""
    lexical = Path(os.path.abspath(Path(path).expanduser()))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if current.is_symlink():
            return current
    return None


def validate_mutable_path(
    path: str | Path,
    *,
    allowed_root: str | Path | None = None,
) -> Path:
    """Return a mutable path after enforcing containment and no-symlink policy."""
    candidate_lexical = Path(os.path.abspath(Path(path).expanduser()))
    root_lexical: Path | None = None
    if allowed_root is not None:
        root_lexical = Path(os.path.abspath(Path(allowed_root).expanduser()))
        if candidate_lexical != root_lexical and not candidate_lexical.is_relative_to(root_lexical):
            raise ValueError(f"Mutable path escapes its allowed root {root_lexical}: {candidate_lexical}")

    symlink = find_symlink_component(candidate_lexical)
    if symlink is not None:
        raise ValueError(f"Symbolic links are not allowed in mutable paths: {symlink}")

    candidate = candidate_lexical.resolve(strict=False)
    resource_root = get_resource_root().resolve(strict=False)
    if candidate == resource_root or candidate.is_relative_to(resource_root):
        raise ValueError(f"Refusing to write inside the installed MathMongo package: {candidate}")
    if root_lexical is not None:
        root = root_lexical.resolve(strict=False)
        if candidate != root and not candidate.is_relative_to(root):
            raise ValueError(f"Mutable path escapes its allowed root {root}: {candidate}")
    return candidate


def get_legacy_project_root(environment: Mapping[str, str] | None = None) -> Path:
    """Return the historical checkout root used only for fallback/migration."""
    override = _environment(environment).get("MATHMONGO_LEGACY_ROOT")
    return resolve_home_path(override, environment) if override else get_resource_root()


def get_documents_dir(environment: Mapping[str, str] | None = None) -> Path:
    env = _environment(environment)
    executable = shutil.which("xdg-user-dir", path=env.get("PATH"))
    if executable:
        result = subprocess.run(
            [executable, "DOCUMENTS"],
            capture_output=True,
            text=True,
            check=False,
            env=dict(env),
        )
        if result.returncode == 0 and result.stdout.strip():
            candidate = resolve_home_path(result.stdout.strip(), environment)
            if candidate.is_absolute():
                return candidate
    return get_home_dir(environment) / "Documents"


def get_exports_dir(
    environment: Mapping[str, str] | None = None,
    configured: str | Path | None = None,
) -> Path:
    if configured:
        return resolve_home_path(configured, environment)
    return get_documents_dir(environment) / "MathMongo"


def ensure_user_directories(environment: Mapping[str, str] | None = None) -> dict[str, Path]:
    """Explicitly create the controlled XDG roots with private permissions."""
    directories = {
        "config": get_config_dir(environment),
        "data": get_data_dir(environment),
        "cache": get_cache_dir(environment),
        "state": get_state_dir(environment),
        "runtime": get_runtime_dir(environment),
        "logs": get_logs_dir(environment),
        "media": get_media_dir(environment),
    }
    for key, directory in tuple(directories.items()):
        directory = validate_mutable_path(directory)
        directories[key] = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            directory.chmod(0o700)
        except OSError:
            pass
    return directories
